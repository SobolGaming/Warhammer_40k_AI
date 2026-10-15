from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from tests.deployment_submission_helpers import (
    DeploymentPoseFactory,
    deployment_proposal_for_state,
    submit_all_deployments_if_pending,
    submit_deployment_placement,
    submit_deployment_unit_selection,
)
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind, PlacementError
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.deployment import (
    SELECT_DEPLOYMENT_UNIT_DECISION_TYPE,
    SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE,
    DeploymentOrderPolicy,
    DeploymentOrderPolicyKind,
    DeploymentPlacementProposal,
    DeploymentPlacementRequest,
    DeploymentPlacementResolution,
    DeploymentPlacementViolation,
    DeploymentPlacementViolationCode,
    DeploymentSetupState,
    create_empty_deployment_battlefield_state,
    deployment_order_policy_kind_from_token,
    deployment_placement_request_from_selection,
    deployment_placement_violation_code_from_token,
    deployment_unit_selection_request,
    deployment_unit_views_for_player,
    resolve_deployment_placement,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    SetupStep,
)
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack


def _advance_to_first_deployment_selection(
    config: GameConfig | None = None,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(_config() if config is None else config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16a-secondary-player-a",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase16a-secondary-player-b",
    )
    assert _decision_request(deployment_status).decision_type == (
        SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    )
    return lifecycle, deployment_status


def _advance_to_first_deployment_placement(
    config: GameConfig | None = None,
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, deployment_status = _advance_to_first_deployment_selection(config)
    placement_status = submit_deployment_unit_selection(
        lifecycle,
        request=_decision_request(deployment_status),
        result_id="phase16a-first-deployment-selection",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    return lifecycle, placement_request


def _advance_to_second_deployment_placement() -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, first_request = _advance_to_first_deployment_placement()
    next_selection_status = submit_deployment_placement(
        lifecycle,
        request=first_request,
        result_id="phase16a-first-valid-placement",
    )
    next_selection_request = _decision_request(next_selection_status)
    assert next_selection_request.decision_type == SELECT_DEPLOYMENT_UNIT_DECISION_TYPE
    placement_status = submit_deployment_unit_selection(
        lifecycle,
        request=next_selection_request,
        result_id="phase16a-second-deployment-selection",
    )
    placement_request = _decision_request(placement_status)
    assert placement_request.decision_type == SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE
    return lifecycle, placement_request


def _deployment_state_with_mustered_armies(
    *,
    player_b_infiltrators: bool = False,
    player_b_infiltrators_ability: bool = False,
) -> GameState:
    config = _config()
    state = GameState.from_config(config)
    for request in config.army_muster_requests:
        army = muster_army(catalog=config.army_catalog, request=request)
        if army.player_id == "player-b" and (
            player_b_infiltrators or player_b_infiltrators_ability
        ):
            unit = army.units[0]
            keywords = unit.keywords
            abilities = unit.datasheet_abilities
            if player_b_infiltrators:
                keywords = (*keywords, "INFILTRATORS")
            if player_b_infiltrators_ability:
                abilities = (
                    *abilities,
                    DatasheetAbilityDescriptor(
                        ability_id="core-infiltrators",
                        name="Core Infiltrators",
                        source_id="datasheet:core-intercessor-like-infantry:ability:infiltrators",
                        support=CatalogAbilitySupport.DESCRIPTOR_ONLY,
                        source_kind=CatalogAbilitySourceKind.CORE,
                        effect_description="Core Infiltrators descriptor.",
                        timing_tags=("deployment",),
                    ),
                )
            army = replace(
                army,
                units=(
                    with_unit_keywords(
                        replace(unit, datasheet_abilities=abilities), keywords=keywords
                    ),
                ),
            )
        state.record_army_definition(army)
    while state.current_setup_step is not SetupStep.DEPLOY_ARMIES:
        if state.current_setup_step is SetupStep.CREATE_BATTLEFIELD:
            state.record_battlefield_state(create_empty_deployment_battlefield_state(state=state))
        state.complete_current_setup_step()
    return state


def _deployment_placement_request_for_player(
    state: GameState,
    *,
    player_id: str,
) -> DecisionRequest:
    selection_request = deployment_unit_selection_request(
        state=state,
        ruleset_descriptor=_ruleset(),
        player_id=player_id,
    )
    selection_result = DecisionResult.for_request(
        result_id=f"phase16a-{player_id}-selection",
        request=selection_request,
        selected_option_id=selection_request.options[0].option_id,
    )
    return deployment_placement_request_from_selection(
        state=state,
        ruleset_descriptor=_ruleset(),
        selection_request=selection_request,
        result=selection_result,
    ).to_decision_request()


def _midfield_outside_deployment_zone_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(24.0, 20.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _out_of_bounds_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(61.0, 3.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _terrain_endpoint_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(44.5, 5.0 + (index * 1.8), 0.5, facing_degrees=180.0)


def _blocking_objective_marker_endpoint_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    if index == 0:
        return Pose.at(57.0, 20.0, 0.0, facing_degrees=180.0)
    return Pose.at(57.0, 24.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _overlapping_models_pose(
    _index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(57.0, 3.0, 0.0, facing_degrees=180.0)


def _broken_coherency_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    if index == 4:
        return Pose.at(57.0, 40.0, 0.0, facing_degrees=180.0)
    return Pose.at(57.0, 3.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _enemy_engagement_range_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(54.0, 3.0 + (index * 1.8), 0.0, facing_degrees=0.0)


def _infiltrators_valid_midfield_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(31.0, 3.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _infiltrators_too_close_to_enemy_zone_pose(
    index: int,
    _player_id: str,
    _model_instance_id: str,
) -> Pose:
    return Pose.at(25.0, 20.0 + (index * 1.8), 0.0, facing_degrees=180.0)


def _drop_model_placements(payload: dict[str, JsonValue]) -> None:
    payload.pop("model_placements")


def _omit_last_model_placement(payload: dict[str, JsonValue]) -> None:
    cast(list[JsonValue], payload["model_placements"]).pop()


def _drift_first_model_and_append_wrong_unit_model(payload: dict[str, JsonValue]) -> None:
    placements = cast(list[dict[str, JsonValue]], payload["model_placements"])
    first = placements[0]
    extra = dict(first)
    first["player_id"] = "player-a"
    extra["player_id"] = "player-a"
    extra["army_id"] = "army-alpha"
    extra["unit_instance_id"] = "army-alpha:intercessor-unit-1"
    extra["model_instance_id"] = "army-alpha:intercessor-unit-1:core-intercessor-like:001"
    placements.append(extra)


def _assert_invalid_deployment_without_mutation(
    lifecycle: GameLifecycle,
    *,
    placement_request: DecisionRequest,
    result_id: str,
    expected_codes: set[str],
    pose_factory: DeploymentPoseFactory | None = None,
    payload_mutation: Callable[[dict[str, JsonValue]], None] | None = None,
) -> LifecycleStatus:
    assert lifecycle.state is not None
    assert lifecycle.state.battlefield_state is not None
    before_record_count = len(lifecycle.decision_controller.records)
    before_battlefield_payload = lifecycle.state.battlefield_state.to_payload()

    status = submit_deployment_placement(
        lifecycle,
        request=placement_request,
        result_id=result_id,
        pose_factory=pose_factory,
        payload_mutation=payload_mutation,
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert _invalid_reason(status) == "deployment_placement_invalid"
    assert expected_codes <= _violation_codes(status)
    assert lifecycle.decision_controller.queue.peek_next().request_id == (
        placement_request.request_id
    )
    assert len(lifecycle.decision_controller.records) == before_record_count
    assert lifecycle.state.battlefield_state is not None
    assert lifecycle.state.battlefield_state.to_payload() == before_battlefield_payload
    return status


def _submit_result(
    lifecycle: GameLifecycle,
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    return lifecycle.submit_decision(
        DecisionResult.for_request(
            result_id=result_id,
            request=request,
            selected_option_id=option_id,
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _invalid_reason(status: LifecycleStatus) -> str:
    assert isinstance(status.payload, dict)
    value = status.payload["invalid_reason"]
    assert type(value) is str
    return value


def _violation_codes(status: LifecycleStatus) -> set[str]:
    assert isinstance(status.payload, dict)
    violations = status.payload["violations"]
    assert isinstance(violations, list)
    codes: set[str] = set()
    for violation in violations:
        assert isinstance(violation, dict)
        code = violation["violation_code"]
        assert type(code) is str
        codes.add(code)
    return codes


def _deployment_transition_source_event_ids(lifecycle: GameLifecycle) -> set[str]:
    source_event_ids: set[str] = set()
    for event in lifecycle.decision_controller.event_log.records:
        if event.event_type != "battlefield_models_placed":
            continue
        assert isinstance(event.payload, dict)
        transition_batch = event.payload["transition_batch"]
        assert isinstance(transition_batch, dict)
        placements = transition_batch["placements"]
        assert isinstance(placements, list)
        for placement in placements:
            assert isinstance(placement, dict)
            source_event_id = placement["source_event_id"]
            assert type(source_event_id) is str
            source_event_ids.add(source_event_id)
    return source_event_ids


def _option_ids(request: DecisionRequest) -> tuple[str, ...]:
    return tuple(option.option_id for option in request.options)


def _config(
    *,
    army_muster_requests: tuple[ArmyMusterRequest, ...] | None = None,
) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase16a-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_requests(catalog) if army_muster_requests is None else army_muster_requests
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
        mission_setup=_mission_setup(),
    )


def _config_with_blocking_objective_marker() -> GameConfig:
    base = _config()
    assert base.mission_setup is not None
    blocking_marker = ObjectiveMarkerDefinition(
        objective_marker_id="phase16a-blocking-objective",
        name="Phase 16A Blocking Objective",
        objective_role=ObjectiveMarkerRole.CENTRAL,
        x_inches=57.0,
        y_inches=20.0,
        blocks_placement=True,
        source_id="phase16a-test:objective-marker",
    )
    mission_setup = replace(
        base.mission_setup,
        deployment_map_id="phase16a-blocking-objective-custom-deployment",
        terrain_layout_id="phase16a-blocking-objective-custom-terrain",
        objective_markers=(*base.mission_setup.objective_markers, blocking_marker),
    )
    return replace(base, mission_setup=mission_setup)


def _config_with_terrain_endpoint_feature() -> GameConfig:
    base = _config()
    assert base.mission_setup is not None
    mission_setup = replace(
        base.mission_setup,
        deployment_map_id="phase16a-terrain-endpoint-custom-deployment",
        terrain_layout_id="phase16a-terrain-endpoint-custom-terrain",
        terrain_features=(
            _terrain_endpoint_feature(
                feature_id="phase16a-terrain-endpoint-hill",
                center_x_inches=44.5,
                center_y_inches=8.5,
                width_inches=8.0,
                depth_inches=12.0,
            ),
        ),
    )
    return replace(base, mission_setup=mission_setup)


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh(descriptor_version="core-v2-phase16a-test")


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _terrain_endpoint_feature(
    *,
    feature_id: str,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=width_inches,
        footprint_depth_inches=depth_inches,
        rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=width_inches,
            depth_inches=depth_inches,
            display_template_id="phase16a_terrain_endpoint_hill_rules",
        ).footprint_polygon,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=width_inches,
            depth_inches=depth_inches,
            display_template_id="phase16a_terrain_endpoint_hill",
        ),
        source_id=f"phase16a-test:terrain:{feature_id}",
    )


def _army_muster_requests(catalog: ArmyCatalog) -> tuple[ArmyMusterRequest, ...]:
    return (
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
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
    unit_selections: tuple[UnitMusterSelection, ...] | None = None,
    attachment_declarations: tuple[AttachmentDeclaration, ...] = (),
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
        unit_selections=(
            (_unit_selection(unit_selection_id=unit_selection_id),)
            if unit_selections is None
            else unit_selections
        ),
        attachment_declarations=attachment_declarations,
    )


def _attached_army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
) -> ArmyMusterRequest:
    return _army_muster_request(
        catalog=catalog,
        player_id=player_id,
        army_id=army_id,
        unit_selection_id="bodyguard-unit",
        unit_selections=(
            _unit_selection(unit_selection_id="bodyguard-unit"),
            _unit_selection(
                unit_selection_id="leader-unit",
                datasheet_id="core-character-leader",
                model_profile_id="core-character-leader",
                model_count=1,
            ),
            _unit_selection(
                unit_selection_id="support-unit",
                datasheet_id="core-character-support",
                model_profile_id="core-character-support",
                model_count=1,
            ),
        ),
        attachment_declarations=(
            AttachmentDeclaration(
                source_unit_selection_id="leader-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
            AttachmentDeclaration(
                source_unit_selection_id="support-unit",
                bodyguard_unit_selection_id="bodyguard-unit",
            ),
        ),
    )


def _unit_selection(
    *,
    unit_selection_id: str,
    datasheet_id: str = "core-intercessor-like-infantry",
    model_profile_id: str = "core-intercessor-like",
    model_count: int = 5,
) -> UnitMusterSelection:
    return UnitMusterSelection(
        unit_selection_id=unit_selection_id,
        datasheet_id=datasheet_id,
        model_profile_selections=(
            ModelProfileSelection(
                model_profile_id=model_profile_id,
                model_count=model_count,
            ),
        ),
    )


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "AttachmentDeclaration"]
__all__ += ["BattlefieldPlacementKind", "Callable", "CatalogAbilitySourceKind"]
__all__ += ["CatalogAbilitySupport", "DatasheetAbilityDescriptor", "DecisionRequest"]
__all__ += ["DecisionResult", "DeploymentOrderPolicy", "DeploymentOrderPolicyKind"]
__all__ += ["DeploymentPlacementProposal", "DeploymentPlacementRequest"]
__all__ += ["DeploymentPlacementResolution", "DeploymentPlacementViolation"]
__all__ += ["DeploymentPlacementViolationCode", "DeploymentPoseFactory", "DeploymentSetupState"]
__all__ += ["DetachmentSelection", "GameConfig", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecyclePayload", "GameLifecycleStage", "GameState", "JsonValue"]
__all__ += ["LifecycleStatus", "LifecycleStatusKind", "MissionSetup", "ModelProfileSelection"]
__all__ += ["ObjectiveMarkerDefinition", "ObjectiveMarkerRole", "PlacementError", "Pose"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "ReserveKind", "ReserveState", "RulesetDescriptor"]
__all__ += ["SELECT_DEPLOYMENT_UNIT_DECISION_TYPE", "SUBMIT_DEPLOYMENT_PLACEMENT_DECISION_TYPE"]
__all__ += ["SetupStep", "TerrainDisplayGeometry", "TerrainFeatureDefinition"]
__all__ += ["TerrainFeatureKind", "UnitMusterSelection", "_advance_to_first_deployment_placement"]
__all__ += ["_advance_to_first_deployment_selection", "_advance_to_second_deployment_placement"]
__all__ += ["_army_muster_request", "_army_muster_requests"]
__all__ += ["_assert_invalid_deployment_without_mutation", "_attached_army_muster_request"]
__all__ += ["_blocking_objective_marker_endpoint_pose", "_broken_coherency_pose", "_config"]
__all__ += ["_config_with_blocking_objective_marker", "_config_with_terrain_endpoint_feature"]
__all__ += ["_decision_request", "_deployment_placement_request_for_player"]
__all__ += ["_deployment_state_with_mustered_armies", "_deployment_transition_source_event_ids"]
__all__ += ["_drift_first_model_and_append_wrong_unit_model", "_drop_model_placements"]
__all__ += ["_enemy_engagement_range_pose", "_infiltrators_too_close_to_enemy_zone_pose"]
__all__ += ["_infiltrators_valid_midfield_pose", "_invalid_reason"]
__all__ += ["_midfield_outside_deployment_zone_pose", "_mission_setup"]
__all__ += ["_omit_last_model_placement", "_option_ids", "_out_of_bounds_pose"]
__all__ += ["_overlapping_models_pose", "_ruleset", "_submit_result", "_terrain_endpoint_feature"]
__all__ += ["_terrain_endpoint_pose", "_unit_selection", "_violation_codes", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_empty_deployment_battlefield_state"]
__all__ += ["deployment_order_policy_kind_from_token"]
__all__ += ["deployment_placement_request_from_selection"]
__all__ += ["deployment_placement_violation_code_from_token", "deployment_proposal_for_state"]
__all__ += ["deployment_unit_selection_request", "deployment_unit_views_for_player", "json"]
__all__ += ["muster_army", "pytest", "replace", "resolve_deployment_placement"]
__all__ += ["submit_all_deployments_if_pending", "submit_deployment_placement"]
__all__ += ["submit_deployment_unit_selection", "with_unit_keywords"]
