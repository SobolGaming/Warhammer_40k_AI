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


def test_phase16a_rejects_illegal_terrain_endpoint_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement(
        _config_with_terrain_endpoint_feature()
    )

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-terrain-endpoint-placement",
        expected_codes={DeploymentPlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value},
        pose_factory=_terrain_endpoint_pose,
    )


def test_phase16a_rejects_blocking_objective_marker_endpoint_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement(
        _config_with_blocking_objective_marker()
    )

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-objective-endpoint-placement",
        expected_codes={DeploymentPlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value},
        pose_factory=_blocking_objective_marker_endpoint_pose,
    )


def test_phase16a_rejects_broken_coherency_without_mutation() -> None:
    lifecycle, placement_request = _advance_to_first_deployment_placement()

    _assert_invalid_deployment_without_mutation(
        lifecycle,
        placement_request=placement_request,
        result_id="phase16a-broken-coherency-placement",
        expected_codes={DeploymentPlacementViolationCode.UNIT_COHERENCY_BROKEN.value},
        pose_factory=_broken_coherency_pose,
    )


def test_phase16a_infiltrators_may_deploy_outside_zone_more_than_eight_from_enemy_zone() -> None:
    state = _deployment_state_with_mustered_armies(player_b_infiltrators=True)
    request = _deployment_placement_request_for_player(state, player_id="player-b")
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)

    valid_resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=request_context,
        proposal=deployment_proposal_for_state(
            state,
            request=request,
            pose_factory=_infiltrators_valid_midfield_pose,
        ),
    )

    assert valid_resolution.is_valid
    assert valid_resolution.transition_batch is not None
    assert len(valid_resolution.transition_batch.placements) == 5

    invalid_resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=request_context,
        proposal=deployment_proposal_for_state(
            state,
            request=request,
            pose_factory=_infiltrators_too_close_to_enemy_zone_pose,
        ),
    )

    assert not invalid_resolution.is_valid
    assert DeploymentPlacementViolationCode.INFILTRATORS_ENEMY_ZONE_DISTANCE in {
        violation.violation_code for violation in invalid_resolution.violations
    }


def test_phase16a_infiltrators_datasheet_ability_enables_midfield_deployment() -> None:
    state = _deployment_state_with_mustered_armies(player_b_infiltrators_ability=True)
    request = _deployment_placement_request_for_player(state, player_id="player-b")
    request_context = DeploymentPlacementRequest.from_decision_request_payload(request.payload)

    resolution = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=_ruleset(),
        request=request_context,
        proposal=deployment_proposal_for_state(
            state,
            request=request,
            pose_factory=_infiltrators_valid_midfield_pose,
        ),
    )

    assert resolution.is_valid
    assert resolution.transition_batch is not None
    assert len(resolution.transition_batch.placements) == 5


def test_phase16a_attached_rules_unit_deploys_group_aware_component_models() -> None:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    config = _config(
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _attached_army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
            ),
        )
    )
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    request = _decision_request(deployment_status)

    assert request.actor_id == "player-b"
    assert _option_ids(request) == ("deploy:attached-unit:army-beta:bodyguard-unit",)
    option_payload = request.options[0].payload
    assert isinstance(option_payload, dict)
    assert option_payload["is_attached_rules_unit"] is True
    assert option_payload["component_unit_instance_ids"] == [
        "army-beta:bodyguard-unit",
        "army-beta:leader-unit",
        "army-beta:support-unit",
    ]

    placement_status = submit_deployment_unit_selection(
        lifecycle,
        request=request,
        result_id="phase16a-attached-select",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    follow_up = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id="phase16a-attached-place",
    )

    assert follow_up.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    for unit_id in (
        "army-beta:bodyguard-unit",
        "army-beta:leader-unit",
        "army-beta:support-unit",
    ):
        assert lifecycle.state.battlefield_state.unit_placement_by_id(unit_id).player_id == (
            "player-b"
        )
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        lifecycle.state.battlefield_state.unit_placement_by_id(
            "attached-unit:army-beta:bodyguard-unit"
        )


def test_phase16a_unavailable_reserve_units_are_excluded_from_deployment_options() -> None:
    state = _deployment_state_with_mustered_armies()
    state.record_reserve_state(
        ReserveState.declared_before_battle(
            player_id="player-b",
            unit_instance_id="army-beta:intercessor-unit-2",
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        )
    )

    assert deployment_unit_views_for_player(state=state, player_id="player-b") == ()


def test_phase16a_replay_restore_preserves_pending_deployment_request() -> None:
    lifecycle, deployment_status = _advance_to_first_deployment_selection()
    request = _decision_request(deployment_status)
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )

    restored = GameLifecycle.from_payload(payload)
    restored_status = restored.advance_until_decision_or_terminal()

    assert _decision_request(restored_status).to_payload() == request.to_payload()
    assert GameLifecycle.from_payload(payload).to_payload() == payload


@pytest.mark.parametrize("drift_target", ["mission_setup", "deployment_zone"])
def test_phase16a_replay_restore_rejects_pending_deployment_geometry_drift(
    drift_target: str,
) -> None:
    lifecycle, _placement_request = _advance_to_first_deployment_placement()
    payload = cast(
        GameLifecyclePayload,
        json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True)),
    )
    decisions = cast(dict[str, JsonValue], payload["decisions"])
    queue = cast(dict[str, JsonValue], decisions["queue"])
    pending_requests = cast(list[JsonValue], queue["pending_requests"])
    pending_request = cast(dict[str, JsonValue], pending_requests[0])
    request_payload = cast(dict[str, JsonValue], pending_request["payload"])
    proposal_request = cast(dict[str, JsonValue], request_payload["proposal_request"])
    if drift_target == "mission_setup":
        mission_setup = cast(dict[str, JsonValue], proposal_request["mission_setup"])
        mission_setup["mission_pool_entry_id"] = "phase16a-drifted-mission-entry"
        expected_error = "mission_setup drifted from state"
    else:
        zones = cast(list[JsonValue], proposal_request["legal_deployment_zones"])
        zone = cast(dict[str, JsonValue], zones[0])
        shape = cast(dict[str, JsonValue], zone["shape"])
        polygons = cast(list[JsonValue], shape["polygons"])
        polygon = cast(dict[str, JsonValue], polygons[0])
        vertices = cast(list[JsonValue], polygon["vertices"])
        vertex = cast(dict[str, JsonValue], vertices[0])
        vertex["x"] = cast(float, vertex["x"]) + 0.05
        expected_error = "deployment zones drifted from state"

    with pytest.raises(GameLifecycleError, match=expected_error):
        GameLifecycle.from_payload(payload)


__all__: list[str] = []
__all__ += ["ArmyMusterRequest", "AttachmentDeclaration", "BattlefieldPlacementKind", "Callable"]
__all__ += ["CatalogAbilitySourceKind", "CatalogAbilitySupport", "DatasheetAbilityDescriptor"]
__all__ += ["DecisionRequest", "DecisionResult", "DeploymentOrderPolicy"]
__all__ += ["DeploymentOrderPolicyKind", "DeploymentPlacementProposal"]
__all__ += ["DeploymentPlacementResolution", "DeploymentPlacementViolation"]
__all__ += ["DeploymentPoseFactory", "DeploymentSetupState", "DetachmentSelection", "GameConfig"]
__all__ += ["GameLifecycleStage", "GameState", "LifecycleStatus", "MissionSetup"]
__all__ += ["ModelProfileSelection", "ObjectiveMarkerDefinition", "ObjectiveMarkerRole", "Pose"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "RulesetDescriptor"]
__all__ += ["SELECT_DEPLOYMENT_UNIT_DECISION_TYPE", "SetupStep", "TerrainDisplayGeometry"]
__all__ += ["TerrainFeatureDefinition", "TerrainFeatureKind", "UnitMusterSelection"]
__all__ += ["_advance_to_second_deployment_placement", "_army_muster_requests"]
__all__ += ["_deployment_transition_source_event_ids"]
__all__ += ["_drift_first_model_and_append_wrong_unit_model", "_drop_model_placements"]
__all__ += ["_enemy_engagement_range_pose", "_invalid_reason"]
__all__ += ["_midfield_outside_deployment_zone_pose", "_mission_setup"]
__all__ += ["_omit_last_model_placement", "_out_of_bounds_pose", "_overlapping_models_pose"]
__all__ += ["_submit_result", "_terrain_endpoint_feature", "_unit_selection", "_violation_codes"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_empty_deployment_battlefield_state"]
__all__ += ["deployment_order_policy_kind_from_token"]
__all__ += ["deployment_placement_request_from_selection"]
__all__ += ["deployment_placement_violation_code_from_token", "deployment_unit_selection_request"]
__all__ += ["muster_army", "replace", "submit_all_deployments_if_pending", "with_unit_keywords"]
