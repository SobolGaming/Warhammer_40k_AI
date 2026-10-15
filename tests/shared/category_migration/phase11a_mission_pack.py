from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from warhammer40k_core.adapters.battlefield_projection import project_battlefield_view
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    SecondaryMissionAvailability,
    mission_source_status_from_token,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import DetachmentSelection, UnitMusterSelection
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    MissionSetupError,
    MissionSetupPayload,
)
from warhammer40k_core.engine.missions import (
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    supported_mission_packs,
    validate_mission_setup_source_layout,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReservePlacementViolationCode,
    ReserveState,
)
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as source_data,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)

PHASE16A_BATTLEFIELD_LAYOUT_ID = "take-and-hold-vs-purge-the-foe-layout-3"
PHASE16A_DEPLOYMENT_MAP_ID = "take-and-hold-vs-purge-the-foe-layout-3-deployment"
PHASE16A_MISSION_POOL_ENTRY_ID = "mission-take-and-hold-vs-purge-the-foe-layout-3"
TYPED_TAKE_AND_HOLD_LAYOUT_C_ID = "take-and-hold-vs-take-and-hold-layout-3"


def _battle_state_with_mission_setup(
    *,
    attacker_player_id: str,
    defender_player_id: str,
    mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID,
    terrain_layout_id: str = PHASE16A_BATTLEFIELD_LAYOUT_ID,
    reserve_base_diameter_mm: float = 32.0,
    custom_layoutless: bool = False,
) -> tuple[GameState, ReserveState]:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=mission_pool_entry_id,
        terrain_layout_id=terrain_layout_id,
        attacker_player_id=attacker_player_id,
        attacker_force_disposition_id="take-and-hold",
        defender_player_id=defender_player_id,
        defender_force_disposition_id="purge-the-foe",
    )
    if custom_layoutless:
        mission_setup = replace(
            mission_setup,
            deployment_map_id="phase11a-custom-deployment-map",
            terrain_layout_id="phase11a-custom-terrain-layout",
        )
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    armies = _with_single_model_reserve_unit(
        armies,
        base_diameter_mm=reserve_base_diameter_mm,
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11a-battlefield",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _ruleset().mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, reserve_state


def _battle_state_without_mission_setup() -> tuple[GameState, ReserveState]:
    config = _config(mission_setup=None)
    armies = _mustered_armies(config)
    armies = _with_single_model_reserve_unit(armies, base_diameter_mm=32.0)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11a-missing-setup-battlefield",
        armies=armies,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _ruleset().mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, reserve_state


def _enter_reinforcements_choice(
    *,
    state: GameState,
    battle_round: int,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.battle_round = battle_round
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-2",),
        moved_unit_ids=("army-alpha:intercessor-unit-2",),
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    status = handler.begin_phase(state=state, decisions=decisions)
    return handler, decisions, _decision_request(status)


def _submit_handler_decision(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _submit_reserve_ingress_action(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    selection_request: DecisionRequest,
    unit_instance_id: str,
    result_id_prefix: str,
) -> LifecycleStatus | None:
    selection_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=selection_request,
        option_id=unit_instance_id,
        result_id=f"{result_id_prefix}-select",
    )
    if selection_status is not None:
        raise AssertionError("reserve selection must continue to an action request")
    action_request = _decision_request(handler.begin_phase(state=state, decisions=decisions))
    return _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=action_request,
        option_id=MovementPhaseActionKind.INGRESS.value,
        result_id=f"{result_id_prefix}-ingress",
    )


def _submit_reserve_placement_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    reserve_unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
    attempted_placement: UnitPlacement,
    result_id: str,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=reserve_unit.unit_instance_id,
        placement_kind=placement_kind,
        attempted_placement=attempted_placement,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.decision_request is not None
    return status.decision_request


def _reserve_unit(*, state: GameState, reserve_state: ReserveState) -> UnitInstance:
    army = state.army_definition_for_player(reserve_state.player_id)
    assert army is not None
    return army.unit_by_id(reserve_state.unit_instance_id)


def _single_model_reserve_placement(*, reserve_unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                pose=pose,
            ),
        ),
    )


def _south_edge_touching_pose(*, reserve_unit: UnitInstance, x: float) -> Pose:
    return Pose.at(
        x=x,
        y=_base_radius_inches(reserve_unit),
        z=0.0,
        facing_degrees=0.0,
    )


def _enemy_deployment_zone_center_pose(*, state: GameState, player_id: str) -> Pose:
    assert state.mission_setup is not None
    zone = state.mission_setup.enemy_deployment_zones_for_player(player_id)[0]
    return Pose.at(
        x=(zone.min_x + zone.max_x) / 2.0,
        y=(zone.min_y + zone.max_y) / 2.0,
        z=0.0,
        facing_degrees=0.0,
    )


def _first_placement_pose(placement: UnitPlacement) -> dict[str, float]:
    pose = placement.model_placements[0].pose
    return {"x": pose.position.x, "y": pose.position.y}


def _base_radius_inches(reserve_unit: UnitInstance) -> float:
    return reserve_unit.own_models[0].geometry.primary_part().radius_x_inches


def _blocking_terrain_feature(*, x: float, y: float) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase11a-live-blocking-terrain",
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=x,
            center_y_inches=y,
            width_inches=4.0,
            depth_inches=4.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=x,
            center_y_inches=y,
            width_inches=4.0,
            depth_inches=4.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="center-wall",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
        source_id="phase11a-live-blocking-terrain",
    )


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _violation_codes(status: LifecycleStatus) -> tuple[str, ...]:
    payload = status.payload
    assert isinstance(payload, dict)
    violations = payload["violations"]
    assert isinstance(violations, list)
    codes: list[str] = []
    for violation in violations:
        assert isinstance(violation, dict)
        code = violation["violation_code"]
        assert isinstance(code, str)
        codes.append(code)
    return tuple(sorted(codes))


def _objective_coordinate_snapshot(
    mission_pack: MissionPackDefinition,
) -> dict[str, dict[str, tuple[float, float]]]:
    return {
        deployment_map.deployment_map_id: {
            marker.objective_marker_id.removeprefix(f"{deployment_map.deployment_map_id}-"): (
                marker.x_inches,
                marker.y_inches,
            )
            for marker in deployment_map.objective_markers
        }
        for deployment_map in mission_pack.deployment_maps
    }


def _config(*, mission_setup: MissionSetup | None) -> GameConfig:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=("purge-the-foe", "take-and-hold"),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )
    player_a_force_disposition_id = (
        "purge-the-foe"
        if mission_setup is None
        else mission_setup.force_disposition_id_for_player("player-a")
    )
    player_b_force_disposition_id = (
        "purge-the-foe"
        if mission_setup is None
        else mission_setup.force_disposition_id_for_player("player-b")
    )
    return GameConfig(
        game_id="phase11a-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
                force_disposition_id=player_a_force_disposition_id,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=player_b_force_disposition_id,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup,
    )


def _custom_layoutless_mission_setup() -> MissionSetup:
    setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    return replace(
        setup,
        deployment_map_id="phase11a-custom-deployment-map",
        terrain_layout_id="phase11a-custom-terrain-layout",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        objective_markers=(),
        deployment_zones=(),
        battlefield_regions=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        terrain_features=(),
    )


def _custom_layoutless_state_and_battlefield() -> tuple[GameState, BattlefieldRuntimeState]:
    setup = _custom_layoutless_mission_setup()
    config = _config(mission_setup=setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11a-custom-layoutless-runtime-dimensions",
        armies=armies,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=(_blocking_terrain_feature(x=30.0, y=22.0),),
    )
    return state, scenario.battlefield_state


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11a-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    force_disposition_id: str,
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
        force_disposition_id=force_disposition_id,
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _with_single_model_reserve_unit(
    armies: tuple[ArmyDefinition, ...],
    *,
    base_diameter_mm: float,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id != "army-alpha":
            updated_armies.append(army)
            continue
        reserve_unit = army.unit_by_id("army-alpha:intercessor-unit-1")
        updated_unit = _single_model_unit(reserve_unit, base_diameter_mm=base_diameter_mm)
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return tuple(updated_armies)


def _single_model_unit(unit: UnitInstance, *, base_diameter_mm: float) -> UnitInstance:
    base_size = BaseSizeDefinition.circular(base_diameter_mm)
    model = replace(
        unit.own_models[0],
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            geometry_source_id="phase11a-reserve-base",
            keywords=unit.keywords,
        ),
    )
    return replace(unit, own_models=(model,))


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["BattlePhase", "BattlefieldPlacementKind", "BattlefieldRuntimeState"]
__all__ += ["DecisionController", "DecisionRequest", "DecisionResult", "DetachmentSelection"]
__all__ += ["FrozenInstanceError", "GameConfig", "GameLifecycleError", "GameLifecycleStage"]
__all__ += ["GameState", "JsonValue", "LifecycleStatus", "MissionPackDefinition"]
__all__ += ["MissionPackDefinitionPayload", "MissionPackError", "MissionSetup"]
__all__ += ["MissionSetupError", "MissionSetupPayload", "MissionSourcePackageDefinition"]
__all__ += ["MissionSourceStatus", "ModelGeometry", "ModelPlacement", "ModelProfileSelection"]
__all__ += ["MovementPhaseActionKind", "MovementPhaseHandler", "MovementPhaseState"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "MovementProposalRequest"]
__all__ += ["PHASE16A_BATTLEFIELD_LAYOUT_ID", "PHASE16A_DEPLOYMENT_MAP_ID"]
__all__ += ["PHASE16A_MISSION_POOL_ENTRY_ID", "PlacementProposalPayload", "Pose"]
__all__ += ["ReserveDestructionTimingPolicy", "ReserveKind", "ReservePlacementViolationCode"]
__all__ += ["ReserveState", "RulesetDescriptor", "SecondaryMissionAvailability"]
__all__ += ["TYPED_TAKE_AND_HOLD_LAYOUT_C_ID", "TerrainDisplayGeometry"]
__all__ += ["TerrainFeatureDefinition", "TerrainFeatureKind", "TerrainWallDefinition"]
__all__ += ["UnitInstance", "UnitMusterSelection", "UnitPlacement", "VictoryPointSourceKind"]
__all__ += ["_army_muster_request", "_base_radius_inches", "_battle_state_with_mission_setup"]
__all__ += ["_battle_state_without_mission_setup", "_blocking_terrain_feature", "_config"]
__all__ += ["_custom_layoutless_mission_setup", "_custom_layoutless_state_and_battlefield"]
__all__ += ["_decision_request", "_display_geometry", "_enemy_deployment_zone_center_pose"]
__all__ += ["_enter_reinforcements_choice", "_first_placement_pose", "_mustered_armies"]
__all__ += ["_objective_coordinate_snapshot", "_reserve_unit", "_ruleset"]
__all__ += ["_single_model_reserve_placement", "_single_model_unit", "_south_edge_touching_pose"]
__all__ += ["_submit_handler_decision", "_submit_parameterized_handler_payload"]
__all__ += ["_submit_reserve_ingress_action", "_submit_reserve_placement_payload"]
__all__ += ["_violation_codes", "_with_single_model_reserve_unit", "cast"]
__all__ += ["chapter_approved_2026_27_mission_pack", "create_deterministic_battlefield_scenario"]
__all__ += ["event_layouts", "json", "mission_pack_for_id", "mission_scoring_policies_from_setup"]
__all__ += ["mission_source_status_from_token", "muster_army", "project_battlefield_view"]
__all__ += ["pytest", "replace", "source_data", "supported_mission_packs", "validate_json_value"]
__all__ += ["validate_mission_setup_source_layout"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack"]
