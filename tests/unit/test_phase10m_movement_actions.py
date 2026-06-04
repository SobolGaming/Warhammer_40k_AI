from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    FallBackModeKind,
    MovementActionAvailabilityContext,
    MovementActionAvailabilityResult,
    MovementPhaseActionKind,
    resolve_normal_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pathing import PathWitness, TerrainEndpointViolationCode
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


def test_action_options_outside_engagement_are_remain_normal_and_advance() -> None:
    _lifecycle, action_request = _advance_to_movement_action_request(_infantry_config())

    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        MovementPhaseActionKind.NORMAL_MOVE.value,
        MovementPhaseActionKind.ADVANCE.value,
    }
    assert MovementPhaseActionKind.FALL_BACK.value not in {
        option.option_id for option in action_request.options
    }


def test_action_options_inside_engagement_are_remain_and_fall_back() -> None:
    config = replace(_infantry_config(), game_id="phase10m-fallback-v2-0001")
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    _move_first_enemy_model_into_engagement(lifecycle)

    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10m-result-000003",
    )
    action_request = _decision_request(action_status)

    assert {option.option_id for option in action_request.options} == {
        MovementPhaseActionKind.REMAIN_STATIONARY.value,
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.ORDERED_RETREAT.value}",
        f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}",
    }
    assert MovementPhaseActionKind.NORMAL_MOVE.value not in {
        option.option_id for option in action_request.options
    }
    assert MovementPhaseActionKind.ADVANCE.value not in {
        option.option_id for option in action_request.options
    }

    fall_back_status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=(
            f"{MovementPhaseActionKind.FALL_BACK.value}:{FallBackModeKind.DESPERATE_ESCAPE.value}"
        ),
        result_id="phase10m-result-000004",
    )
    fall_back_status = _decline_optional_stratagem_if_pending(
        lifecycle,
        status=fall_back_status,
        result_id="phase10m-decline-fire-overwatch",
    )
    if fall_back_status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION:
        assert _decision_request(fall_back_status).decision_type in {
            MOVEMENT_PROPOSAL_DECISION_TYPE,
            SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
            SELECT_MOVEMENT_UNIT_DECISION_TYPE,
        }
    else:
        assert fall_back_status.status_kind is LifecycleStatusKind.UNSUPPORTED


def test_movement_action_availability_payload_round_trips_without_object_reprs() -> None:
    context = MovementActionAvailabilityContext(
        ruleset_descriptor_hash="descriptor-phase10m",
        unit_instance_id="army-alpha:intercessor-unit-1",
        player_id="player-a",
        enemy_engagement_model_ids=("army-beta:intercessor-unit-2:model-001",),
    )
    result = context.evaluate()

    context_blob = json.dumps(context.to_payload(), sort_keys=True)
    result_blob = json.dumps(result.to_payload(), sort_keys=True)

    assert "aircraft_movement_policy" not in context.to_payload()
    assert "<" not in context_blob
    assert "object at 0x" not in context_blob
    assert "<" not in result_blob
    assert "object at 0x" not in result_blob
    assert MovementActionAvailabilityContext.from_payload(context.to_payload()) == context
    assert MovementActionAvailabilityResult.from_payload(result.to_payload()) == result


def test_normal_move_rejects_path_through_enemy_model_base() -> None:
    scenario = _infantry_scenario()
    scenario = _with_first_enemy_model_pose(scenario, Pose.at(9.0, 6.0))
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    witness = _normal_witness_with_first_model_path(
        scenario=scenario,
        unit_placement=unit_placement,
        first_model_end_pose=Pose.at(12.0, 6.0),
    )

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
    )

    assert not resolution.is_valid
    assert resolution.path_validation_results[0].violations[0].violation_code == (
        "enemy_model_base_crossed"
    )


def test_normal_move_rejects_forbidden_terrain_transit_in_terrain_layer() -> None:
    scenario = _vehicle_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    witness = _single_model_pivot_witness(unit_placement, movement_inches=8.0)
    ruins = _ruins_wall_feature(center_x_inches=10.0, center_y_inches=6.0)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
        terrain_features=(ruins,),
    )

    assert not resolution.is_valid
    assert resolution.path_validation_results[0].is_valid
    assert not resolution.terrain_path_legality_results[0].is_valid
    assert (
        resolution.terrain_path_legality_results[0].violations[0].violation_code
        == "terrain_feature_transit_forbidden"
    )
    with pytest.raises(GameLifecycleError, match="Invalid Normal Move"):
        resolution.transition_batch(before=unit_placement)


def test_infantry_normal_move_can_traverse_ruins_wall() -> None:
    scenario = _single_model_infantry_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    ruins = _ruins_wall_feature(center_x_inches=9.0, center_y_inches=6.0)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_witness_to_pose(unit_placement, end_pose=Pose.at(12.0, 6.0)),
        terrain_features=(ruins,),
    )

    assert resolution.path_validation_results[0].is_valid
    assert resolution.terrain_path_legality_results[0].is_valid
    assert resolution.is_valid


def test_vehicle_normal_move_cannot_traverse_ruins_wall() -> None:
    scenario = _vehicle_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    ruins = _ruins_wall_feature(center_x_inches=10.0, center_y_inches=6.0)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_witness_to_pose(unit_placement, end_pose=Pose.at(14.0, 6.0)),
        terrain_features=(ruins,),
    )

    assert resolution.path_validation_results[0].is_valid
    assert not resolution.terrain_path_legality_results[0].is_valid
    assert (
        resolution.terrain_path_legality_results[0].violations[0].violation_code
        == "terrain_feature_transit_forbidden"
    )
    assert not resolution.is_valid


def test_infantry_normal_move_cannot_end_inside_ruins_wall() -> None:
    scenario = _single_model_infantry_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    ruins = _ruins_wall_feature(center_x_inches=9.0, center_y_inches=6.0)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_witness_to_pose(unit_placement, end_pose=Pose.at(9.0, 6.0)),
        terrain_features=(ruins,),
    )

    assert resolution.path_validation_results[0].is_valid
    assert not resolution.terrain_path_legality_results[0].is_valid
    assert (
        resolution.terrain_path_legality_results[0].violations[0].violation_code
        == TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value
    )
    assert not resolution.is_valid


def test_infantry_normal_move_can_end_on_upper_ruins_floor_with_vertical_movement() -> None:
    scenario = _infantry_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    ruins = _multilevel_ruins_feature(
        center_x_inches=10.0,
        center_y_inches=6.0,
        upper_floor_z_inches=3.0,
    )

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_unit_vertical_witness_to_z(unit_placement, z_inches=3.0),
        terrain_features=(ruins,),
    )

    assert resolution.is_valid
    assert all(result.is_valid for result in resolution.path_validation_results)
    assert all(result.is_valid for result in resolution.terrain_path_legality_results)
    for path_result in resolution.path_validation_results:
        movement_distance_witness = path_result.movement_distance_witness
        assert movement_distance_witness is not None
        assert math.isclose(
            movement_distance_witness.total_distance_inches,
            3.0,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        assert movement_distance_witness.is_within_budget
    for terrain_result in resolution.terrain_path_legality_results:
        upper_floor_segments = tuple(
            segment
            for segment in terrain_result.segments
            if segment.terrain_id == "phase10m-multilevel-ruins:upper"
        )
        assert len(upper_floor_segments) == 1
        assert upper_floor_segments[0].traversal_mode.value == "freely_traversable"


def test_non_round_vehicle_or_monster_normal_move_records_cost_free_rotation() -> None:
    for keywords, base_size in (
        (("Vehicle",), BaseSizeDefinition.rectangular(length_mm=100.0, width_mm=60.0)),
        (("Monster",), BaseSizeDefinition.oval(length_mm=100.0, width_mm=60.0)),
    ):
        scenario = _vehicle_scenario_with_active_unit_keywords_and_base(
            keywords=keywords,
            base_size=base_size,
        )
        unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
        resolution = resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            unit_placement=unit_placement,
            path_witness=_single_model_pivot_witness(unit_placement, movement_inches=8.0),
        )

        movement_distance_witness = resolution.path_validation_results[0].movement_distance_witness
        assert movement_distance_witness is not None
        assert resolution.is_valid
        assert movement_distance_witness.total_distance_inches == 8.0
        assert len(movement_distance_witness.rotation_events) == 2
        assert tuple(
            event.facing_delta_degrees for event in movement_distance_witness.rotation_events
        ) == (45.0, 45.0)


def test_round_large_flying_stem_or_hover_vehicle_records_cost_free_rotation() -> None:
    for keywords in (("Vehicle", "Fly"), ("Vehicle", "Hover")):
        scenario = _vehicle_scenario_with_active_unit_keywords_and_base(
            keywords=keywords,
            base_size=BaseSizeDefinition.circular(100.0),
        )
        unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
        resolution = resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            unit_placement=unit_placement,
            path_witness=_single_model_pivot_witness(unit_placement, movement_inches=8.0),
        )

        movement_distance_witness = resolution.path_validation_results[0].movement_distance_witness
        assert movement_distance_witness is not None
        assert resolution.is_valid
        assert movement_distance_witness.total_distance_inches == 8.0
        assert len(movement_distance_witness.rotation_events) == 2
        assert tuple(
            event.facing_delta_degrees for event in movement_distance_witness.rotation_events
        ) == (45.0, 45.0)


def test_fly_take_to_the_skies_applies_budget_modifier() -> None:
    scenario = _vehicle_scenario_with_active_unit_keywords_and_base(
        keywords=("FLY", "INFANTRY"),
        base_size=BaseSizeDefinition.circular(32.0),
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    start_pose = unit_placement.model_placements[0].pose
    valid_resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=_single_model_witness_to_pose(
            unit_placement,
            end_pose=Pose.at(
                start_pose.position.x + 10.0,
                start_pose.position.y,
                start_pose.position.z,
                facing_degrees=start_pose.facing.degrees,
            ),
        ),
    )
    over_budget_resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=_single_model_witness_to_pose(
            unit_placement,
            end_pose=Pose.at(
                start_pose.position.x + 12.0,
                start_pose.position.y,
                start_pose.position.z,
                facing_degrees=start_pose.facing.degrees,
            ),
        ),
    )

    assert valid_resolution.is_valid
    model_movements = cast(list[JsonValue], valid_resolution.movement_payload["model_movements"])
    model_payload = cast(dict[str, object], model_movements[0])
    assert model_payload["movement_mode"] == MovementMode.FLY_TAKE_TO_SKIES.value
    assert model_payload["base_movement_inches"] == 12.0
    assert model_payload["movement_distance_modifier_inches"] == -2.0
    distance_witness = cast(dict[str, object], model_payload["movement_distance_witness"])
    budget = cast(dict[str, object], distance_witness["budget"])
    assert budget["max_distance_inches"] == 10.0
    assert budget["remaining_distance_inches"] == 0.0
    assert not over_budget_resolution.is_valid
    assert over_budget_resolution.path_validation_results[0].violations[0].violation_code == (
        "movement_distance_exceeded"
    )


def test_fly_take_to_the_skies_rejects_non_fly_and_wrong_action_mode() -> None:
    scenario = _single_model_infantry_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    witness = _single_model_witness_to_pose(
        unit_placement,
        end_pose=Pose.at(7.0, 6.0),
    )

    with pytest.raises(GameLifecycleError, match="requires the FLY keyword"):
        resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            unit_placement=unit_placement,
            movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
            path_witness=witness,
        )
    with pytest.raises(GameLifecycleError, match="not legal for the selected movement action"):
        resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            unit_placement=unit_placement,
            movement_mode=MovementMode.ADVANCE,
            path_witness=witness,
        )


def test_aircraft_normal_move_records_cost_free_aircraft_rotation() -> None:
    scenario = _vehicle_scenario_with_active_unit_keywords_and_base(
        keywords=("Aircraft", "Vehicle"),
        base_size=BaseSizeDefinition.oval(length_mm=120.0, width_mm=80.0),
    )
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    moving_model = scenario.model_instance_for_placement(unit_placement.model_placements[0])
    movement_inches = float(_model_movement_inches(moving_model))

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_aircraft_pivot_witness(
            unit_placement,
            movement_inches=movement_inches,
        ),
    )

    movement_distance_witness = resolution.path_validation_results[0].movement_distance_witness
    assert movement_distance_witness is not None
    assert resolution.is_valid
    assert movement_distance_witness.total_distance_inches == movement_inches
    assert len(movement_distance_witness.rotation_events) == 1
    assert movement_distance_witness.rotation_events[0].facing_delta_degrees == 90.0


def test_normal_move_rejects_witness_model_set_drift() -> None:
    scenario = _vehicle_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    placement = unit_placement.model_placements[0]
    witness = PathWitness.for_straight_line_endpoints(
        (("army-alpha:other-unit:model-001", placement.pose, Pose.at(10.0, 6.0)),)
    )

    with pytest.raises(GameLifecycleError, match="witness must match"):
        resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
            unit_placement=unit_placement,
            path_witness=witness,
        )


def _advance_to_movement_unit_selection(
    config: GameConfig,
) -> tuple[GameLifecycle, LifecycleStatus]:
    lifecycle = GameLifecycle()
    lifecycle.start(config)
    first_status = lifecycle.advance_until_decision_or_terminal()
    assert _decision_request(first_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    second_status = _submit_result(
        lifecycle,
        request=_decision_request(first_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10m-result-000001",
    )
    assert _decision_request(second_status).decision_type == SECONDARY_MISSION_DECISION_TYPE
    movement_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10m-result-000002",
    )
    assert _decision_request(movement_status).decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE
    return lifecycle, movement_status


def _advance_to_movement_action_request(
    config: GameConfig,
) -> tuple[GameLifecycle, DecisionRequest]:
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    action_status = _submit_result(
        lifecycle,
        request=_decision_request(movement_status),
        option_id="army-alpha:intercessor-unit-1",
        result_id="phase10m-result-000003",
    )
    action_request = _decision_request(action_status)
    assert action_request.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    return lifecycle, action_request


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


def _decline_optional_stratagem_if_pending(
    lifecycle: GameLifecycle,
    *,
    status: LifecycleStatus,
    result_id: str,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        return status
    return lifecycle.submit_decision(
        DecisionResult(
            result_id=result_id,
            request_id=request.request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=request.actor_id,
            selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
            payload=stratagem_decline_payload(),
        )
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    return status.decision_request


def _infantry_config() -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase10m-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase10m-test"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=_mission_setup(),
    )


def _mission_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _infantry_scenario() -> BattlefieldScenario:
    config = _infantry_config()
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10m-infantry-battlefield",
        armies=tuple(
            muster_army(catalog=config.army_catalog, request=request)
            for request in config.army_muster_requests
        ),
    )


def _single_model_infantry_scenario() -> BattlefieldScenario:
    return _vehicle_scenario_with_active_unit_keywords_and_base(
        keywords=("INFANTRY",),
        base_size=BaseSizeDefinition.circular(32.0),
    )


def _vehicle_scenario() -> BattlefieldScenario:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    armies = tuple(
        muster_army(
            catalog=catalog,
            request=_army_muster_request(
                catalog=catalog,
                player_id=player_id,
                army_id=army_id,
                unit_selection_id=unit_selection_id,
                datasheet_id="core-transport",
                model_profile_id="core-transport",
                model_count=1,
            ),
        )
        for player_id, army_id, unit_selection_id in (
            ("player-a", "army-alpha", "transport-1"),
            ("player-b", "army-beta", "transport-2"),
        )
    )
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10m-vehicle-battlefield",
        armies=armies,
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
    datasheet_id: str,
    model_profile_id: str,
    model_count: int,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id=datasheet_id,
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id=model_profile_id,
                        model_count=model_count,
                    ),
                ),
            ),
        ),
    )


def _move_first_enemy_model_into_engagement(lifecycle: GameLifecycle) -> None:
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    friendly = state.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    enemy = state.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    friendly_pose = friendly.model_placements[0].pose
    updated_enemy = _with_first_model_pose(
        enemy,
        Pose.at(
            friendly_pose.position.x + 2.0,
            friendly_pose.position.y,
            friendly_pose.position.z,
            facing_degrees=180.0,
        ),
    )
    state.battlefield_state = state.battlefield_state.with_unit_placement(updated_enemy)


def _with_first_enemy_model_pose(
    scenario: BattlefieldScenario,
    pose: Pose,
) -> BattlefieldScenario:
    enemy = scenario.battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-2")
    updated_state = scenario.battlefield_state.with_unit_placement(
        _with_first_model_pose(enemy, pose)
    )
    return BattlefieldScenario(armies=scenario.armies, battlefield_state=updated_state)


def _with_first_model_pose(unit_placement: UnitPlacement, pose: Pose) -> UnitPlacement:
    first, *rest = unit_placement.model_placements
    return unit_placement.with_model_placements((first.with_pose(pose), *rest))


def _normal_witness_with_first_model_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    first_model_end_pose: Pose,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, placement in enumerate(unit_placement.model_placements):
        model = scenario.model_instance_for_placement(placement)
        end_pose = (
            first_model_end_pose
            if index == 0
            else Pose.at(
                placement.pose.position.x + _model_movement_inches(model),
                placement.pose.position.y,
                placement.pose.position.z,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
        midpoint = Pose.at(
            (placement.pose.position.x + end_pose.position.x) / 2.0,
            (placement.pose.position.y + end_pose.position.y) / 2.0,
            (placement.pose.position.z + end_pose.position.z) / 2.0,
            facing_degrees=(placement.pose.facing.degrees + end_pose.facing.degrees) / 2.0,
        )
        model_paths.append((placement.model_instance_id, (placement.pose, midpoint, end_pose)))
    return PathWitness.for_paths(tuple(model_paths))


def _single_model_pivot_witness(
    unit_placement: UnitPlacement,
    *,
    movement_inches: float,
) -> PathWitness:
    placement = unit_placement.model_placements[0]
    start = placement.pose
    end = Pose.at(
        start.position.x + movement_inches,
        start.position.y,
        start.position.z,
        facing_degrees=start.facing.degrees + 90.0,
    )
    midpoint = Pose.at(
        (start.position.x + end.position.x) / 2.0,
        start.position.y,
        start.position.z,
        facing_degrees=start.facing.degrees + 45.0,
    )
    return PathWitness.for_paths(((placement.model_instance_id, (start, midpoint, end)),))


def _single_model_aircraft_pivot_witness(
    unit_placement: UnitPlacement,
    *,
    movement_inches: float,
) -> PathWitness:
    placement = unit_placement.model_placements[0]
    start = placement.pose
    moved = Pose.at(
        start.position.x + movement_inches,
        start.position.y,
        start.position.z,
        facing_degrees=start.facing.degrees,
    )
    pivoted = Pose.at(
        moved.position.x,
        moved.position.y,
        moved.position.z,
        facing_degrees=start.facing.degrees + 90.0,
    )
    return PathWitness.for_paths(((placement.model_instance_id, (start, moved, pivoted)),))


def _single_model_witness_to_pose(
    unit_placement: UnitPlacement,
    *,
    end_pose: Pose,
) -> PathWitness:
    placement = unit_placement.model_placements[0]
    start = placement.pose
    midpoint = Pose.at(
        (start.position.x + end_pose.position.x) / 2.0,
        (start.position.y + end_pose.position.y) / 2.0,
        (start.position.z + end_pose.position.z) / 2.0,
        facing_degrees=(start.facing.degrees + end_pose.facing.degrees) / 2.0,
    )
    return PathWitness.for_paths(((placement.model_instance_id, (start, midpoint, end_pose)),))


def _unit_vertical_witness_to_z(
    unit_placement: UnitPlacement,
    *,
    z_inches: float,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement in unit_placement.model_placements:
        start = placement.pose
        midpoint = Pose.at(
            start.position.x,
            start.position.y,
            z_inches / 2.0,
            facing_degrees=start.facing.degrees,
        )
        end = Pose.at(
            start.position.x,
            start.position.y,
            z_inches,
            facing_degrees=start.facing.degrees,
        )
        model_paths.append((placement.model_instance_id, (start, midpoint, end)))
    return PathWitness.for_paths(tuple(model_paths))


def _ruins_wall_feature(
    *,
    center_x_inches: float,
    center_y_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase10m-ruins-wall",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=8.0,
        footprint_depth_inches=6.0,
        walls=(
            TerrainWallDefinition(
                wall_id="center-wall",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=8.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
        ),
    )


def _multilevel_ruins_feature(
    *,
    center_x_inches: float,
    center_y_inches: float,
    upper_floor_z_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase10m-multilevel-ruins",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=center_x_inches,
        footprint_center_y_inches=center_y_inches,
        footprint_width_inches=12.0,
        footprint_depth_inches=6.0,
        walls=(
            TerrainWallDefinition(
                wall_id="north-wall",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches + 2.5,
                bottom_z_inches=0.0,
                width_inches=12.0,
                depth_inches=0.12,
                height_inches=upper_floor_z_inches,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=12.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
            TerrainFloorDefinition(
                floor_id="upper",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=upper_floor_z_inches,
                width_inches=12.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
        ),
    )


def _vehicle_scenario_with_active_unit_keywords_and_base(
    *,
    keywords: tuple[str, ...],
    base_size: BaseSizeDefinition,
) -> BattlefieldScenario:
    scenario = _vehicle_scenario()
    active_unit_id = "army-alpha:transport-1"
    updated_armies: list[ArmyDefinition] = []
    for army in scenario.armies:
        updated_units = tuple(
            _unit_with_keywords_and_base(unit, keywords=keywords, base_size=base_size)
            if unit.unit_instance_id == active_unit_id
            else unit
            for unit in army.units
        )
        updated_armies.append(replace(army, units=updated_units))
    return BattlefieldScenario(
        armies=tuple(updated_armies),
        battlefield_state=scenario.battlefield_state,
    )


def _unit_with_keywords_and_base(
    unit: UnitInstance,
    *,
    keywords: tuple[str, ...],
    base_size: BaseSizeDefinition,
) -> UnitInstance:
    return replace(
        unit,
        keywords=keywords,
        own_models=tuple(
            _model_with_base(model, base_size=base_size, keywords=keywords)
            for model in unit.own_models
        ),
    )


def _model_with_base(
    model: ModelInstance,
    *,
    base_size: BaseSizeDefinition,
    keywords: tuple[str, ...],
) -> ModelInstance:
    geometry_source_id = model.geometry.geometry_source_id
    assert geometry_source_id is not None
    return replace(
        model,
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            geometry_source_id=geometry_source_id,
            keywords=keywords,
        ),
    )


def _model_movement_inches(model: ModelInstance) -> int:
    for characteristic in model.characteristics:
        if characteristic.characteristic.value == "movement":
            return characteristic.final
    raise AssertionError("Model is missing Movement.")
