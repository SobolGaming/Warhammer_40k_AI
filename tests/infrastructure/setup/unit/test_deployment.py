from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase16a_deployment import (
    SECONDARY_MISSION_DECISION_TYPE,
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    ArmyCatalog,
    ArmyMusterRequest,
    AttachmentDeclaration,
    BattlefieldPlacementKind,
    Callable,
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
    DecisionRequest,
    DecisionResult,
    DeploymentOrderPolicy,
    DeploymentOrderPolicyKind,
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
    DeploymentPlacementResolution,
    DeploymentPlacementViolation,
    DeploymentPlacementViolationCode,
    DeploymentPoseFactory,
    DeploymentSetupState,
    DetachmentSelection,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelProfileSelection,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerRole,
    PlacementError,
    Pose,
    ReserveKind,
    ReserveState,
    RulesetDescriptor,
    SetupStep,
    TerrainDisplayGeometry,
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    UnitMusterSelection,
    _advance_to_first_deployment_placement,
    _advance_to_first_deployment_selection,
    _advance_to_second_deployment_placement,
    _army_muster_request,
    _army_muster_requests,
    _assert_invalid_deployment_without_mutation,
    _attached_army_muster_request,
    _blocking_objective_marker_endpoint_pose,
    _broken_coherency_pose,
    _config,
    _config_with_blocking_objective_marker,
    _config_with_terrain_endpoint_feature,
    _decision_request,
    _deployment_placement_request_for_player,
    _deployment_state_with_mustered_armies,
    _deployment_transition_source_event_ids,
    _drift_first_model_and_append_wrong_unit_model,
    _drop_model_placements,
    _enemy_engagement_range_pose,
    _infiltrators_too_close_to_enemy_zone_pose,
    _infiltrators_valid_midfield_pose,
    _invalid_reason,
    _midfield_outside_deployment_zone_pose,
    _mission_setup,
    _omit_last_model_placement,
    _option_ids,
    _out_of_bounds_pose,
    _overlapping_models_pose,
    _ruleset,
    _submit_result,
    _terrain_endpoint_feature,
    _terrain_endpoint_pose,
    _unit_selection,
    _violation_codes,
    chapter_approved_2026_27_mission_pack,
    create_empty_deployment_battlefield_state,
    deployment_order_policy_kind_from_token,
    deployment_placement_request_from_selection,
    deployment_placement_violation_code_from_token,
    deployment_proposal_for_state,
    deployment_unit_selection_request,
    deployment_unit_views_for_player,
    json,
    muster_army,
    pytest,
    replace,
    resolve_deployment_placement,
    submit_all_deployments_if_pending,
    submit_deployment_placement,
    submit_deployment_unit_selection,
    with_unit_keywords,
)


def test_phase16a_deploy_armies_uses_lifecycle_decisions_not_deterministic_bridge() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()
    request = _decision_request(deployment_status)

    assert request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    assert request.actor_id == "player-b"
    assert _option_ids(request) == ("deploy:army-beta:intercessor-unit-2",)
    option_payload = request.options[0].payload
    assert isinstance(option_payload, dict)
    assert option_payload["submission_kind"] == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE

    battle_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase16a-deploy",
    )

    assert lifecycle.state is not None
    assert lifecycle.state.stage is GameLifecycleStage.BATTLE
    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.battlefield_state.battlefield_id == (
        "phase16a-game:take-and-hold-vs-purge-the-foe-layout-3-deployment:battlefield"
    )
    assert len(lifecycle.state.battlefield_state.placed_model_ids()) == 10
    assert battle_status.decision_request is None or (
        battle_status.decision_request.decision_type
        not in {
            SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
            SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
        }
    )

    decision_types = tuple(
        record.request.decision_type for record in lifecycle.decision_controller.records
    )
    assert decision_types.count(SELECT_DEPLOYMENT_UNIT_DECISION_TYPE) == 2
    assert decision_types.count(SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE) == 2
    event_types = tuple(
        event.event_type for event in lifecycle.decision_controller.event_log.records
    )
    assert event_types.count("battlefield_created") == 1
    assert event_types.count("deployment_unit_selected") == 2
    assert event_types.count("deployment_unit_placed") == 2
    assert event_types.count("battlefield_models_placed") == 2
    assert _deployment_transition_source_event_ids(lifecycle) == {
        "phase16a-deploy-000002",
        "phase16a-deploy-000004",
    }

    payload_blob = json.dumps(lifecycle.to_payload(), sort_keys=True)
    assert "phase10a_deterministic_bridge" not in payload_blob
    assert "phase10a" not in lifecycle.state.battlefield_state.battlefield_id
    assert "<" not in payload_blob
    assert "object at 0x" not in payload_blob


def test_phase17j_deployment_queue_drains_opponent_remaining_units() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = _config(
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
                unit_selections=(
                    _unit_selection(unit_selection_id="intercessor-unit-2"),
                    _unit_selection(unit_selection_id="intercessor-unit-3"),
                ),
            ),
        )
    )
    lifecycle, first_status = _advance_to_first_deployment_selection(config)
    first_request = _decision_request(first_status)

    assert first_request.actor_id == "player-b"
    assert _option_ids(first_request) == (
        "deploy:army-beta:intercessor-unit-2",
        "deploy:army-beta:intercessor-unit-3",
    )

    first_placement = submit_deployment_unit_selection(
        lifecycle,
        request=first_request,
        result_id="phase17j-drain-select-b1",
        option_id="deploy:army-beta:intercessor-unit-2",
    )
    second_selection = submit_deployment_placement(
        lifecycle,
        request=_decision_request(first_placement),
        result_id="phase17j-drain-place-b1",
    )
    second_request = _decision_request(second_selection)
    assert second_request.actor_id == "player-a"
    assert _option_ids(second_request) == ("deploy:army-alpha:intercessor-unit-1",)

    second_placement = submit_deployment_unit_selection(
        lifecycle,
        request=second_request,
        result_id="phase17j-drain-select-a1",
    )
    drain_selection = submit_deployment_placement(
        lifecycle,
        request=_decision_request(second_placement),
        result_id="phase17j-drain-place-a1",
    )
    drain_request = _decision_request(drain_selection)

    assert drain_request.actor_id == "player-b"
    assert _option_ids(drain_request) == ("deploy:army-beta:intercessor-unit-3",)


def test_phase16a_invalid_deployment_rejects_before_queue_pop_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_request_id = placement_request.request_id

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-invalid-placement",
        expected_codes={DeploymentPlacementViolationCode.DEPLOYMENT_ZONE_VIOLATION.value},
        pose_factory=_midfield_outside_deployment_zone_pose,
    )

    assert lifecycle.decision_controller.queue.peek_next().request_id == before_request_id


def test_phase16a_rejects_out_of_bounds_pose_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-out-of-bounds-placement",
        expected_codes={DeploymentPlacementViolationCode.BATTLEFIELD_EDGE_CROSSED.value},
        pose_factory=_out_of_bounds_pose,
    )


def test_phase16a_rejects_model_overlap_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-model-overlap-placement",
        expected_codes={DeploymentPlacementViolationCode.MODEL_OVERLAP.value},
        pose_factory=_overlapping_models_pose,
    )


def test_phase16a_rejects_enemy_engagement_range_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_second_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-enemy-engagement-placement",
        expected_codes={DeploymentPlacementViolationCode.ENEMY_ENGAGEMENT_RANGE.value},
        pose_factory=_enemy_engagement_range_pose,
    )


def test_phase16a_stale_drift_and_malformed_proposals_reject_before_queue_pop() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_record_count = len(lifecycle.decision_controller.records)

    stale_status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-stale-placement",
        payload_mutation=lambda payload: payload.__setitem__(
            "ruleset_descriptor_hash",
            "stale-ruleset-hash",
        ),
    )

    assert stale_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(stale_status) == "deployment_request_drift"
    assert DeploymentPlacementViolationCode.RULESET_HASH_DRIFT.value in _violation_codes(
        stale_status
    )
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count

    malformed_status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-malformed-placement",
        payload_mutation=_drop_model_placements,
    )

    assert malformed_status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(malformed_status) == "malformed_deployment_placement"
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16a_omitted_models_reject_before_queue_pop() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_record_count = len(lifecycle.decision_controller.records)

    status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-omitted-model-placement",
        payload_mutation=_omit_last_model_placement,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(status) == "deployment_placement_invalid"
    assert DeploymentPlacementViolationCode.MODEL_SET_DRIFT.value in _violation_codes(status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16a_model_identity_player_and_component_drift_are_typed_violations() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    before_record_count = len(lifecycle.decision_controller.records)

    status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-model-identity-drift-placement",
        payload_mutation=_drift_first_model_and_append_wrong_unit_model,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(status) == "deployment_placement_invalid"
    assert {
        DeploymentPlacementViolationCode.MODEL_SET_DRIFT.value,
        DeploymentPlacementViolationCode.PLAYER_DRIFT.value,
        DeploymentPlacementViolationCode.WRONG_UNIT_MODEL.value,
    } <= _violation_codes(status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count


def test_phase16a_deployment_payload_round_trips_and_reports_request_drift() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    assert lifecycle.state is not None
    assert isinstance(placement_request.payload, dict)
    assert "proposal_request" in placement_request.payload
    assert "deployment_request" not in placement_request.payload
    request = DeploymentPlacementRequest.from_decision_request_payload(placement_request.payload)
    proposal = deployment_proposal_for_state(lifecycle.state, request=placement_request)

    assert DeploymentPlacementRequest.from_payload(request.to_payload()) == request
    assert DeploymentPlacementProposal.from_payload(proposal.to_payload()) == proposal
    grouped = proposal.grouped_unit_placements()
    assert len(grouped) == 1
    assert grouped[0].unit_instance_id == request.unit_instance_id

    drifted = replace(
        proposal,
        proposal_request_id="phase16a-stale-request",
        game_id="phase16a-other-game",
        ruleset_descriptor_hash="phase16a-other-ruleset",
        player_id="player-a",
        unit_instance_id="army-alpha:other-unit",
        placement_kind=BattlefieldPlacementKind.REDEPLOY,
    )

    assert {
        violation.violation_code for violation in drifted.request_drift_violations(request)
    } == {
        DeploymentPlacementViolationCode.STALE_PROPOSAL_REQUEST,
        DeploymentPlacementViolationCode.GAME_ID_DRIFT,
        DeploymentPlacementViolationCode.RULESET_HASH_DRIFT,
        DeploymentPlacementViolationCode.PLAYER_DRIFT,
        DeploymentPlacementViolationCode.UNIT_DRIFT,
        DeploymentPlacementViolationCode.PLACEMENT_KIND_DRIFT,
    }


def test_phase16a_deployment_public_guards_are_fail_fast() -> None:
    assert (
        deployment_order_policy_kind_from_token(
            DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
        )
        is DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
    )
    assert (
        deployment_order_policy_kind_from_token("defender_first_alternating")
        is DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING
    )
    assert (
        deployment_placement_violation_code_from_token("unit_drift")
        is DeploymentPlacementViolationCode.UNIT_DRIFT
    )
    with pytest.raises(GameLifecycleError, match="DeploymentOrderPolicyKind token"):
        deployment_order_policy_kind_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported DeploymentOrderPolicyKind"):
        deployment_order_policy_kind_from_token("random_policy")
    with pytest.raises(GameLifecycleError, match="DeploymentPlacementViolationCode token"):
        deployment_placement_violation_code_from_token(1)
    with pytest.raises(GameLifecycleError, match="Unsupported DeploymentPlacementViolationCode"):
        deployment_placement_violation_code_from_token("random_violation")
    with pytest.raises(GameLifecycleError, match="DeploymentSetupState requires DEPLOY_ARMIES"):
        DeploymentSetupState(
            setup_step=SetupStep.MUSTER_ARMIES,
            order_policy=DeploymentOrderPolicyKind.DEFENDER_FIRST_ALTERNATING,
            next_player_id=None,
            remaining_unit_count_by_player={},
        )
    with pytest.raises(GameLifecycleError, match="Deployment order requires GameState"):
        DeploymentOrderPolicy.core_rules().next_player_id(cast(GameState, object()))


def test_phase16a_deployment_request_and_resolution_guards_reject_invalid_shapes() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()
    assert lifecycle.state is not None
    request = DeploymentPlacementRequest.from_decision_request_payload(placement_request.payload)
    proposal = deployment_proposal_for_state(lifecycle.state, request=placement_request)
    resolution = resolve_deployment_placement(
        state=lifecycle.state,
        ruleset_descriptor=_ruleset(),
        request=request,
        proposal=proposal,
    )
    assert resolution.is_valid
    assert resolution.transition_batch is not None

    with pytest.raises(GameLifecycleError, match="payload must be an object"):
        DeploymentPlacementRequest.from_decision_request_payload("not-an-object")
    with pytest.raises(GameLifecycleError, match="payload missing request"):
        DeploymentPlacementRequest.from_decision_request_payload({})
    with pytest.raises(GameLifecycleError, match="actor_id must match player_id"):
        replace(request, actor_id="player-a" if request.player_id == "player-b" else "player-b")
    with pytest.raises(GameLifecycleError, match="requires deployment placement"):
        replace(request, placement_kind=BattlefieldPlacementKind.REDEPLOY)

    violation = DeploymentPlacementViolation(
        violation_code=DeploymentPlacementViolationCode.UNIT_DRIFT,
        message="Deployment proposal unit does not match the pending request.",
        field="unit_instance_id",
    )
    with pytest.raises(GameLifecycleError, match="Invalid deployment placement"):
        DeploymentPlacementResolution(
            proposal=proposal,
            violations=(violation,),
            coherency_result=resolution.coherency_result,
            transition_batch=resolution.transition_batch,
        )
    with pytest.raises(GameLifecycleError, match="Valid deployment placement requires transitions"):
        DeploymentPlacementResolution(
            proposal=proposal,
            violations=(),
            coherency_result=resolution.coherency_result,
            transition_batch=None,
        )


__all__: list[str] = []
__all__ += ["ArmyMusterRequest", "AttachmentDeclaration", "Callable", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "DatasheetAbilityDescriptor", "DecisionRequest"]
__all__ += ["DecisionResult", "DeploymentPoseFactory", "DetachmentSelection", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecyclePayload", "JsonValue", "LifecycleStatus"]
__all__ += ["MissionSetup", "ModelProfileSelection", "ObjectiveMarkerDefinition"]
__all__ += ["ObjectiveMarkerRole", "PlacementError", "Pose", "ReserveKind", "ReserveState"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "RulesetDescriptor", "TerrainDisplayGeometry"]
__all__ += ["TerrainFeatureDefinition", "TerrainFeatureKind", "UnitMusterSelection"]
__all__ += ["_army_muster_requests", "_attached_army_muster_request"]
__all__ += ["_blocking_objective_marker_endpoint_pose", "_broken_coherency_pose"]
__all__ += ["_config_with_blocking_objective_marker", "_config_with_terrain_endpoint_feature"]
__all__ += ["_deployment_placement_request_for_player", "_deployment_state_with_mustered_armies"]
__all__ += ["_infiltrators_too_close_to_enemy_zone_pose", "_infiltrators_valid_midfield_pose"]
__all__ += ["_mission_setup", "_submit_result", "_terrain_endpoint_feature"]
__all__ += ["_terrain_endpoint_pose", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_empty_deployment_battlefield_state"]
__all__ += ["deployment_placement_request_from_selection", "deployment_unit_selection_request"]
__all__ += ["deployment_unit_views_for_player", "muster_army", "with_unit_keywords"]
