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


@pytest.mark.parametrize(
    ("zone_width", "x", "accepted"),
    [(3.0, None, True), (3.0, 5.0, False), (10.0, None, True), (10.0, 9.0, False)],
)
def test_order54_oversized_deployment_requires_impossibility_and_own_edge(
    zone_width: float, x: float | None, accepted: bool
) -> None:
    from tests.large_model_setup_helpers import oversized_deployment_case

    state, request, proposal = oversized_deployment_case(zone_width=zone_width, x=x)
    result = resolve_deployment_placement(
        state=state,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        request=request,
        proposal=proposal,
    )
    assert result.is_valid is accepted


@pytest.mark.parametrize("reverse", [False, True])
def test_order54_composite_zone_cannot_authorize_oversized_deployment(reverse: bool) -> None:
    from tests.large_model_setup_helpers import composite_deployment_case

    for redundant in (False, True):
        state, request, proposal = composite_deployment_case(redundant=redundant, reverse=reverse)
        before = state.to_payload()
        result = resolve_deployment_placement(
            state=state,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            request=request,
            proposal=proposal,
        )
        assert not result.is_valid
        assert {violation.violation_code for violation in result.violations} == {
            DeploymentPlacementViolationCode.DEPLOYMENT_ZONE_VIOLATION
        }
        assert state.to_payload() == before


def test_order54_facade_deployment_restore_replay_and_pregame_duration() -> None:
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.core.datasheet import BaseSizeDefinition
    from warhammer40k_core.core.deployment_zones import DeploymentZone
    from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
    from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus

    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        catalog,
        datasheets=tuple(
            replace(
                sheet,
                model_profiles=tuple(
                    replace(profile, base_size=BaseSizeDefinition.circular(200))
                    for profile in sheet.model_profiles
                ),
            )
            if sheet.datasheet_id == "core-character-leader"
            else sheet
            for sheet in catalog.datasheets
        ),
    )
    base = _config()
    assert base.mission_setup is not None
    mission = replace(
        base.mission_setup,
        deployment_map_id="order54-custom-zone",
        terrain_layout_id="order54-custom-terrain",
        attacker_battlefield_edge="west",
        defender_battlefield_edge="east",
        deployment_zones=(
            DeploymentZone.rectangle("narrow-a", "player-a", min_x=0, min_y=0, max_x=3, max_y=44),
            DeploymentZone.rectangle("narrow-b", "player-b", min_x=57, min_y=0, max_x=60, max_y=44),
        ),
        terrain_features=(),
    )
    config = replace(
        base,
        army_catalog=catalog,
        mission_setup=mission,
        army_muster_requests=tuple(
            _army_muster_request(
                catalog=catalog,
                player_id=player,
                army_id=army,
                unit_selection_id="large",
                unit_selections=(
                    _unit_selection(
                        unit_selection_id="large",
                        datasheet_id="core-character-leader",
                        model_profile_id="core-character-leader",
                        model_count=1,
                    ),
                ),
            )
            for player, army in (("player-a", "army-alpha"), ("player-b", "army-beta"))
        ),
    )
    session = LocalGameSession()
    session.start(config)
    status = session.advance_until_decision_or_terminal()
    number = 0
    while (
        status.decision_request is not None
        and session.lifecycle.state is not None
        and session.lifecycle.state.stage is GameLifecycleStage.SETUP
    ):
        request = status.decision_request
        number += 1
        if request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE:
            payload = deployment_proposal_for_state(
                session.lifecycle.state,
                request=request,
                pose_factory=lambda _i, p, _m: Pose.at(
                    200 / 25.4 / 2 if p == "player-a" else 60 - 200 / 25.4 / 2, 20
                ),
            ).to_payload()
            before = session.lifecycle.to_payload()
            bad = cast(dict[str, JsonValue], json.loads(json.dumps(payload)))
            cast(list[dict[str, JsonValue]], bad["model_placements"])[0]["pose"] = cast(
                JsonValue, Pose.at(30, 20).to_payload()
            )
            invalid = session.submit_parameterized_payload(
                request_id=request.request_id, payload=bad, result_id=f"bad-{number}"
            )
            assert invalid.status_kind is LifecycleStatusKind.INVALID
            assert session.lifecycle.to_payload() == before
            restored = GameLifecycle.from_payload(json.loads(json.dumps(before)))
            assert restored.to_payload() == before
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                payload=cast(JsonValue, payload),
                result_id=f"place-{number}",
            )
        else:
            option = (
                "fixed:assassination:bring_it_down"
                if request.decision_type == SECONDARY_MISSION_DECISION_TYPE
                else request.options[0].option_id
            )
            status = session.submit_option(
                request_id=request.request_id, option_id=option, result_id=f"select-{number}"
            )
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.stage is GameLifecycleStage.BATTLE
    for player, army in (("player-a", "army-alpha"), ("player-b", "army-beta")):
        assert session.view(viewer_player_id=player)
        assert (
            large_model_activity_reason(session.lifecycle.state, f"{army}:large", "normal") is None
        )
    assert (
        ReplayRunner.from_payload(session.replay_artifact(artifact_id="order54-deployment"))
        .run()
        .status
        is ReplayRunStatus.REPRODUCED
    )


__all__: list[str] = []
__all__ += ["ArmyMusterRequest", "AttachmentDeclaration", "BattlefieldPlacementKind", "Callable"]
__all__ += ["CatalogAbilitySourceKind", "CatalogAbilitySupport", "DatasheetAbilityDescriptor"]
__all__ += ["DecisionRequest", "DecisionResult", "DeploymentOrderPolicy"]
__all__ += ["DeploymentOrderPolicyKind", "DeploymentPlacementProposal"]
__all__ += ["DeploymentPlacementRequest", "DeploymentPlacementResolution"]
__all__ += ["DeploymentPlacementViolation", "DeploymentPoseFactory", "DeploymentSetupState"]
__all__ += ["DetachmentSelection", "GameConfig", "GameLifecycleError", "GameLifecyclePayload"]
__all__ += ["GameState", "LifecycleStatus", "MissionSetup", "ModelProfileSelection"]
__all__ += ["ObjectiveMarkerDefinition", "ObjectiveMarkerRole", "PlacementError", "ReserveKind"]
__all__ += ["SELECT_DEPLOYMENT_UNIT_DECISION_TYPE", "ReserveState", "RulesetDescriptor"]
__all__ += ["SetupStep", "TerrainDisplayGeometry", "TerrainFeatureDefinition"]
__all__ += ["TerrainFeatureKind", "UnitMusterSelection", "_advance_to_first_deployment_placement"]
__all__ += ["_advance_to_first_deployment_selection", "_advance_to_second_deployment_placement"]
__all__ += ["_army_muster_requests", "_assert_invalid_deployment_without_mutation"]
__all__ += ["_attached_army_muster_request", "_blocking_objective_marker_endpoint_pose"]
__all__ += ["_broken_coherency_pose", "_config_with_blocking_objective_marker"]
__all__ += ["_config_with_terrain_endpoint_feature", "_decision_request"]
__all__ += ["_deployment_placement_request_for_player", "_deployment_state_with_mustered_armies"]
__all__ += ["_deployment_transition_source_event_ids"]
__all__ += ["_drift_first_model_and_append_wrong_unit_model", "_drop_model_placements"]
__all__ += ["_enemy_engagement_range_pose", "_infiltrators_too_close_to_enemy_zone_pose"]
__all__ += ["_infiltrators_valid_midfield_pose", "_invalid_reason"]
__all__ += ["_midfield_outside_deployment_zone_pose", "_mission_setup"]
__all__ += ["_omit_last_model_placement", "_option_ids", "_out_of_bounds_pose"]
__all__ += ["_overlapping_models_pose", "_ruleset", "_submit_result", "_terrain_endpoint_feature"]
__all__ += ["_terrain_endpoint_pose", "_violation_codes", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_empty_deployment_battlefield_state"]
__all__ += ["deployment_order_policy_kind_from_token"]
__all__ += ["deployment_placement_request_from_selection"]
__all__ += ["deployment_placement_violation_code_from_token", "deployment_unit_selection_request"]
__all__ += ["deployment_unit_views_for_player", "muster_army"]
__all__ += ["submit_all_deployments_if_pending", "submit_deployment_placement"]
__all__ += ["submit_deployment_unit_selection", "with_unit_keywords"]
