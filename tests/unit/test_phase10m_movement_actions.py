from __future__ import annotations

import json
import math
from dataclasses import replace
from functools import cache
from typing import cast

import pytest
from tests.deployment_submission_helpers import submit_all_deployments_if_pending
from tests.support.wahapedia_bridge_fixtures import screamers_bridge_artifacts
from tests.support.wahapedia_source_fixtures import catalog_package_id, catalog_version

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.abilities import (
    GENERIC_RULE_IR_ABILITY_HANDLER_ID,
    AbilityCatalogIndex,
    AbilityCatalogRecord,
    AbilityDefinition,
    AbilitySourceKind,
    AbilityTimingDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    ModelDisplacementKind,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_proposals import MOVEMENT_PROPOSAL_DECISION_TYPE
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    FallBackModeKind,
    MovementActionAvailabilityContext,
    MovementActionAvailabilityResult,
    MovementPhaseActionKind,
    NormalMoveResolution,
    resolve_normal_move,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.runtime_modifiers import (
    AdvanceRollModifierBinding,
    AdvanceRollModifierContext,
    MovementBudgetModifierBinding,
    MovementBudgetModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.stratagems import (
    STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
    stratagem_decline_payload,
)
from warhammer40k_core.engine.timing_windows import TimingTriggerKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pathing import PathWitness, TerrainEndpointViolationCode
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)


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


@pytest.mark.parametrize(
    ("ignored_kind", "expected_movement_inches", "expected_advance_modifier_ids"),
    [
        (
            "movement_characteristic",
            6.0,
            ("test:modifier-ignore:advance-penalty",),
        ),
        ("advance_roll", 4.0, ()),
    ],
)
def test_movement_action_modifier_ignore_subsets_use_finite_lifecycle_and_round_trip(
    ignored_kind: str,
    expected_movement_inches: float,
    expected_advance_modifier_ids: tuple[str, ...],
) -> None:
    config = replace(
        _infantry_config(),
        game_id=f"phase10m-modifier-ignore-{ignored_kind}",
    )
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    ability_index = AbilityCatalogIndex.from_records((_movement_modifier_ignore_ability_record(),))
    registry = _movement_modifier_ignore_registry()
    _install_movement_modifier_ignore_runtime(
        lifecycle,
        ability_index=ability_index,
        registry=registry,
    )
    action_request = _decision_request(
        _submit_result(
            lifecycle,
            request=_decision_request(movement_status),
            option_id="army-alpha:intercessor-unit-1",
            result_id=f"phase10m-modifier-ignore-{ignored_kind}-select-unit",
        )
    )
    advance_options = tuple(
        option
        for option in action_request.options
        if isinstance(option.payload, dict)
        and option.payload.get("movement_phase_action") == MovementPhaseActionKind.ADVANCE.value
    )
    assert len(advance_options) == 4
    selected_option = next(
        option for option in advance_options if _ignored_modifier_kinds(option) == (ignored_kind,)
    )
    restored_request = DecisionRequest.from_payload(
        json.loads(json.dumps(action_request.to_payload(), sort_keys=True))
    )
    assert restored_request == action_request

    status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=selected_option.option_id,
        result_id=f"phase10m-modifier-ignore-{ignored_kind}-select-action",
    )
    state = lifecycle.state
    assert state is not None
    source_unit = next(
        unit
        for army in state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == "army-alpha:intercessor-unit-1"
    )
    model_id = source_unit.own_model_ids()[0]
    assert (
        registry.modified_movement_inches(
            MovementBudgetModifierContext(
                state=state,
                unit_instance_id="army-alpha:intercessor-unit-1",
                model_instance_id=model_id,
                base_movement_inches=6.0,
                current_movement_inches=6.0,
            )
        )
        == expected_movement_inches
    )
    advance_event = next(
        event
        for event in reversed(lifecycle.decision_controller.event_log.records)
        if event.event_type == "advance_roll_resolved"
    )
    assert isinstance(advance_event.payload, dict)
    advance_roll = cast(dict[str, object], advance_event.payload["advance_roll"])
    advance_request = cast(dict[str, object], advance_roll["request"])
    roll_modifiers = cast(list[dict[str, object]], advance_request["roll_modifiers"])
    assert tuple(cast(str, item["modifier_id"]) for item in roll_modifiers) == (
        expected_advance_modifier_ids
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert lifecycle.decision_controller.records[-1].result.payload == selected_option.payload
    modifier_events = tuple(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "modifier_ignores_selected"
    )
    assert len(modifier_events) == 1
    assert isinstance(modifier_events[0].payload, dict)
    effect_payload = cast(
        dict[str, object],
        cast(dict[str, object], modifier_events[0].payload)["modifier_ignore_effect"],
    )
    assert effect_payload["effect_id"] == (
        f"phase10m-modifier-ignore-{ignored_kind}-select-action:modifier-ignore-selection"
    )
    lifecycle_payload = json.loads(json.dumps(lifecycle.to_payload(), sort_keys=True))
    assert GameLifecycle.from_payload(lifecycle_payload).to_payload() == lifecycle_payload
    assert "object at 0x" not in json.dumps(lifecycle_payload, sort_keys=True)


def test_movement_modifier_ignore_option_drift_rejects_before_queue_pop() -> None:
    config = replace(_infantry_config(), game_id="phase10m-modifier-ignore-stale")
    lifecycle, movement_status = _advance_to_movement_unit_selection(config)
    ability_index = AbilityCatalogIndex.from_records((_movement_modifier_ignore_ability_record(),))
    _install_movement_modifier_ignore_runtime(
        lifecycle,
        ability_index=ability_index,
        registry=_movement_modifier_ignore_registry(),
    )
    action_request = _decision_request(
        _submit_result(
            lifecycle,
            request=_decision_request(movement_status),
            option_id="army-alpha:intercessor-unit-1",
            result_id="phase10m-modifier-ignore-stale-select-unit",
        )
    )
    stale_option = next(
        option
        for option in action_request.options
        if _ignored_modifier_kinds(option) == ("advance_roll",)
    )
    _install_movement_modifier_ignore_runtime(
        lifecycle,
        ability_index=ability_index,
        registry=RuntimeModifierRegistry.empty(),
    )
    record_count = len(lifecycle.decision_controller.records)

    status = _submit_result(
        lifecycle,
        request=action_request,
        option_id=stale_option.option_id,
        result_id="phase10m-modifier-ignore-stale-select-action",
    )

    assert status.status_kind is LifecycleStatusKind.INVALID
    assert isinstance(status.payload, dict)
    assert status.payload["invalid_reason"] == "movement_action_option_drift"
    assert lifecycle.decision_controller.queue.pending_requests == (action_request,)
    assert len(lifecycle.decision_controller.records) == record_count
    assert all(
        event.event_type != "modifier_ignores_selected"
        for event in lifecycle.decision_controller.event_log.records
    )


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


def test_normal_move_full_unit_no_op_witness_emits_only_changed_displacement() -> None:
    scenario = _infantry_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    moved_model = unit_placement.model_placements[0]
    moved_end_pose = Pose.at(
        moved_model.pose.position.x,
        moved_model.pose.position.y + 1.0,
        moved_model.pose.position.z,
        facing_degrees=moved_model.pose.facing.degrees,
    )
    witness = _full_unit_witness_with_only_first_model_moved(
        unit_placement,
        first_model_end_pose=moved_end_pose,
    )

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
    )
    batch = resolution.transition_batch(before=unit_placement)
    model_movements = tuple(
        cast(dict[str, object], movement)
        for movement in cast(list[JsonValue], resolution.movement_payload["model_movements"])
    )
    no_op_movements = tuple(
        movement for movement in model_movements if movement["start_pose"] == movement["end_pose"]
    )
    displacement = batch.displacements[0]

    assert resolution.is_valid
    assert len(model_movements) == len(unit_placement.model_placements)
    assert len(no_op_movements) == len(unit_placement.model_placements) - 1
    assert len(batch.displacements) == 1
    assert displacement.model_instance_id == moved_model.model_instance_id
    assert displacement.displacement_kind is ModelDisplacementKind.NORMAL_MOVE
    assert displacement.start_pose == moved_model.pose
    assert displacement.end_pose == moved_end_pose
    assert displacement.path_witness is not None
    assert displacement.path_witness.poses_for_model(moved_model.model_instance_id) == (
        witness.poses_for_model(moved_model.model_instance_id)
    )


def test_normal_move_rejects_forbidden_terrain_transit_in_terrain_layer() -> None:
    scenario = _vehicle_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    witness = _single_model_pivot_witness(unit_placement, movement_inches=8.0)
    ruins = _ruins_wall_feature(center_x_inches=10.0, center_y_inches=6.0)
    scenario = _scenario_with_terrain_features(scenario, (ruins,))

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
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
    scenario = _scenario_with_terrain_features(scenario, (ruins,))

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_witness_to_pose(unit_placement, end_pose=Pose.at(12.0, 6.0)),
    )

    assert resolution.path_validation_results[0].is_valid
    assert resolution.terrain_path_legality_results[0].is_valid
    assert resolution.is_valid


def test_vehicle_normal_move_cannot_traverse_ruins_wall() -> None:
    scenario = _vehicle_scenario()
    unit_placement = scenario.battlefield_state.unit_placement_by_id("army-alpha:transport-1")
    ruins = _ruins_wall_feature(center_x_inches=10.0, center_y_inches=6.0)
    scenario = _scenario_with_terrain_features(scenario, (ruins,))

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_witness_to_pose(unit_placement, end_pose=Pose.at(14.0, 6.0)),
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
    scenario = _scenario_with_terrain_features(scenario, (ruins,))

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_single_model_witness_to_pose(unit_placement, end_pose=Pose.at(9.0, 6.0)),
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
    removed_model_ids = tuple(
        placement.model_instance_id for placement in unit_placement.model_placements[2:]
    )
    battlefield_state = scenario.battlefield_state.with_removed_models(removed_model_ids)
    unit_placement = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")

    exact_setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    ruins = next(
        feature
        for feature in exact_setup.terrain_features
        if feature.feature_id
        == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-14-component-01"
    )
    upper_floor = next(floor for floor in ruins.floors if floor.bottom_z_inches == 3.0)
    floor_axis_radians = math.radians(upper_floor.rotation_degrees)
    model_center_offset_inches = 0.7
    unit_placement = unit_placement.with_model_placements(
        tuple(
            placement.with_pose(
                Pose.at(
                    upper_floor.center_x_inches
                    + ((-1.0 if index == 0 else 1.0) * model_center_offset_inches)
                    * math.cos(floor_axis_radians),
                    upper_floor.center_y_inches
                    + ((-1.0 if index == 0 else 1.0) * model_center_offset_inches)
                    * math.sin(floor_axis_radians),
                    facing_degrees=placement.pose.facing.degrees,
                )
            )
            for index, placement in enumerate(unit_placement.model_placements)
        )
    )
    scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=battlefield_state.with_unit_placement(unit_placement),
    )
    scenario = _scenario_with_terrain_features(scenario, (ruins,))

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=_unit_vertical_witness_to_z(unit_placement, z_inches=3.0),
    )

    assert resolution.is_valid
    assert resolution.coherency_result.is_coherent
    assert ruins.source_id is not None
    assert "purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in ruins.source_id
    assert len(resolution.attempted_placement.model_placements) == 2
    assert all(
        placement.pose.position.z == upper_floor.bottom_z_inches
        for placement in resolution.attempted_placement.model_placements
    )
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
            if segment.terrain_id == f"{ruins.feature_id}:{upper_floor.floor_id}"
        )
        assert len(upper_floor_segments) == 1
        assert upper_floor_segments[0].traversal_mode.value == "freely_traversable"


def test_mustered_infantry_normal_move_traverses_exact_event_ruin_wall() -> None:
    scenario, unit_placement, witness, ruins, wall = _exact_ruin_wall_traversal_scenario(
        scenario=_infantry_scenario(),
        unit_instance_id="army-alpha:intercessor-unit-1",
    )
    unit = scenario.unit_instance_for_placement(unit_placement)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
    )

    assert "INFANTRY" in unit.keywords
    _assert_exact_ruin_wall_traversal(
        resolution=resolution,
        ruins=ruins,
        wall=wall,
    )


def test_mustered_beast_normal_move_traverses_exact_event_ruin_wall() -> None:
    scenario, unit_placement, witness, ruins, wall = _exact_ruin_wall_traversal_scenario(
        scenario=_screamers_scenario(),
        unit_instance_id="army-alpha:screamers-unit-1",
    )
    unit = scenario.unit_instance_for_placement(unit_placement)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        path_witness=witness,
    )

    assert unit.datasheet_id == "000001127"
    assert unit.name == "Screamers"
    assert "BEAST" in unit.keywords
    _assert_exact_ruin_wall_traversal(
        resolution=resolution,
        ruins=ruins,
        wall=wall,
    )


def test_mustered_fly_unit_takes_to_the_skies_over_exact_dense_non_ruin() -> None:
    scenario, unit_placement, witness, dense_non_ruin, wall = (
        _exact_dense_non_ruin_air_path_scenario(
            scenario=_screamers_scenario(),
            unit_instance_id="army-alpha:screamers-unit-1",
        )
    )
    unit = scenario.unit_instance_for_placement(unit_placement)

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        unit_placement=unit_placement,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=witness,
    )

    assert unit.datasheet_id == "000001127"
    assert unit.name == "Screamers"
    assert "FLY" in unit.keywords
    assert resolution.is_valid
    assert resolution.coherency_result.is_coherent
    assert dense_non_ruin.source_id is not None
    assert "purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in dense_non_ruin.source_id
    assert all(result.is_valid for result in resolution.path_validation_results)
    assert all(result.is_valid for result in resolution.terrain_path_legality_results)
    for terrain_result in resolution.terrain_path_legality_results:
        air_path_segments = tuple(
            segment
            for segment in terrain_result.segments
            if segment.terrain_id == f"{dense_non_ruin.feature_id}:{wall.wall_id}"
            and segment.traversal_mode.value == "air_path"
        )
        assert air_path_segments
        assert all(segment.air_path_measurement_pending for segment in air_path_segments)
        assert sum(segment.vertical_distance_inches for segment in air_path_segments) > 0.0


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


def _movement_modifier_ignore_ability_record() -> AbilityCatalogRecord:
    text = "This model can ignore any or all modifiers to Move, Advance and Charge."
    span = TextSpan(text=text, start=0, end=len(text))
    clause = RuleClause(
        clause_id="test:modifier-ignore:movement-clause",
        source_span=span,
        target=RuleTargetSpec(kind=RuleTargetKind.THIS_MODEL, source_span=span),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.GRANT_ABILITY,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("ability", "modifier_ignore_permission"),
                        (
                            "modifier_kinds",
                            (
                                "movement_characteristic",
                                "advance_roll",
                                "charge_roll",
                            ),
                        ),
                        ("selection", "any_or_all"),
                    )
                ),
            ),
        ),
        duration=RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=span,
        ),
    )
    rule_ir = RuleIR(
        rule_id="test:modifier-ignore:movement-rule",
        source_id="test:modifier-ignore:movement-source",
        normalized_text=text,
        parser_version="test:modifier-ignore:v1",
        clauses=(clause,),
    )
    return AbilityCatalogRecord(
        record_id="test:modifier-ignore:movement-record",
        definition=AbilityDefinition(
            ability_id="test:modifier-ignore:movement-ability",
            name="Test Modifier Ignore",
            source_id=rule_ir.source_id,
            when_descriptor="Passive.",
            effect_descriptor=text,
            restrictions_descriptor="This model only.",
            timing=AbilityTimingDescriptor(
                trigger_kind=TimingTriggerKind.PASSIVE_QUERY,
                phase=BattlePhaseKind.MOVEMENT,
            ),
            handler_id=GENERIC_RULE_IR_ABILITY_HANDLER_ID,
            replay_payload=validate_json_value({"rule_ir": cast(JsonValue, rule_ir.to_payload())}),
        ),
        source_kind=AbilitySourceKind.DATASHEET,
        datasheet_id="core-intercessor-like-infantry",
    )


def _movement_modifier_ignore_registry() -> RuntimeModifierRegistry:
    return RuntimeModifierRegistry.from_bindings(
        movement_budget_modifier_bindings=(
            MovementBudgetModifierBinding(
                modifier_id="test:modifier-ignore:movement-penalty",
                source_id="test:modifier-ignore:movement-penalty-source",
                handler=_modifier_ignore_movement_penalty,
            ),
        ),
        advance_roll_modifier_bindings=(
            AdvanceRollModifierBinding(
                modifier_id="test:modifier-ignore:advance-binding",
                source_id="test:modifier-ignore:advance-binding-source",
                handler=_modifier_ignore_advance_penalty,
            ),
        ),
    )


def _modifier_ignore_movement_penalty(context: MovementBudgetModifierContext) -> float:
    source_unit = next(
        unit
        for army in context.state.army_definitions
        for unit in army.units
        if unit.unit_instance_id == context.unit_instance_id
    )
    if context.model_instance_id != source_unit.own_model_ids()[0]:
        return context.current_movement_inches
    return context.current_movement_inches - 2.0


def _modifier_ignore_advance_penalty(
    context: AdvanceRollModifierContext,
) -> tuple[RollModifier, ...]:
    return (
        *context.current_roll_modifiers,
        RollModifier(
            modifier_id="test:modifier-ignore:advance-penalty",
            source_id="test:modifier-ignore:advance-penalty-source",
            operand=-1,
        ),
    )


def _install_movement_modifier_ignore_runtime(
    lifecycle: GameLifecycle,
    *,
    ability_index: AbilityCatalogIndex,
    registry: RuntimeModifierRegistry,
) -> None:
    handler = replace(
        lifecycle._movement_phase_handler,  # pyright: ignore[reportPrivateUsage]
        ability_indexes_by_player_id={
            "player-a": ability_index,
            "player-b": AbilityCatalogIndex.from_records(()),
        },
        runtime_modifier_registry=registry,
    )
    lifecycle._movement_phase_handler = handler  # pyright: ignore[reportPrivateUsage]
    flow = lifecycle._battle_round_flow  # pyright: ignore[reportPrivateUsage]
    assert flow is not None
    flow._phase_handlers[BattlePhase.MOVEMENT] = handler  # pyright: ignore[reportPrivateUsage]


def _ignored_modifier_kinds(option: DecisionOption) -> tuple[str, ...]:
    payload = option.payload
    if not isinstance(payload, dict):
        return ()
    raw_context = payload.get("modifier_ignore_context")
    if not isinstance(raw_context, dict):
        return ()
    ignored = raw_context.get("ignored_modifiers")
    assert isinstance(ignored, list)
    return tuple(cast(str, item["kind"]) for item in ignored if isinstance(item, dict))


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
    deployment_status = _submit_result(
        lifecycle,
        request=_decision_request(second_status),
        option_id="fixed:assassination:bring_it_down",
        result_id="phase10m-result-000002",
    )
    movement_status = submit_all_deployments_if_pending(
        lifecycle,
        deployment_status,
        result_id_prefix="phase10m-deploy",
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
        allow_legacy_non_strict_rosters=True,
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
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
        terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
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


@cache
def _screamers_package() -> CanonicalCatalogPackage:
    return build_canonical_catalog_package(
        package_id=catalog_package_id(),
        catalog_version=catalog_version(),
        source_artifacts=screamers_bridge_artifacts(),
    )


def _screamers_scenario() -> BattlefieldScenario:
    package = _screamers_package()
    detachment_id = "phase17n-screamers-detachment"
    catalog = replace(
        package.army_catalog,
        detachments=(
            DetachmentDefinition(
                detachment_id=detachment_id,
                name="Phase 17N Screamers movement fixture",
                faction_id="CD",
                detachment_point_cost=1,
                unit_datasheet_ids=("000001127",),
                force_disposition_ids=("purge-the-foe",),
                source_ids=("test:phase17n:screamers-movement-detachment",),
            ),
        ),
    )
    armies = tuple(
        muster_army(
            catalog=catalog,
            request=ArmyMusterRequest(
                army_id=army_id,
                player_id=player_id,
                catalog_id=catalog.catalog_id,
                source_package_id=catalog.source_package_id,
                ruleset_id=catalog.ruleset_id,
                detachment_selection=DetachmentSelection(
                    faction_id="CD",
                    detachment_ids=(detachment_id,),
                ),
                force_disposition_id="purge-the-foe",
                unit_selections=(
                    UnitMusterSelection(
                        unit_selection_id=unit_selection_id,
                        datasheet_id="000001127",
                        model_profile_selections=(
                            ModelProfileSelection(
                                model_profile_id="000001127:screamers",
                                model_count=3,
                            ),
                        ),
                    ),
                ),
            ),
            model_geometries=package.model_geometries,
        )
        for player_id, army_id, unit_selection_id in (
            ("player-a", "army-alpha", "screamers-unit-1"),
            ("player-b", "army-beta", "screamers-unit-2"),
        )
    )
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10m-screamers-battlefield",
        armies=armies,
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


def _scenario_with_terrain_features(
    scenario: BattlefieldScenario,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> BattlefieldScenario:
    return BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=replace(
            scenario.battlefield_state,
            terrain_features=terrain_features,
        ),
    )


@cache
def _exact_phase17n_layout_a_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )


def _exact_ruin_wall_traversal_scenario(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[
    BattlefieldScenario,
    UnitPlacement,
    PathWitness,
    TerrainFeatureDefinition,
    TerrainWallDefinition,
]:
    setup = _exact_phase17n_layout_a_setup()
    ruins = next(
        feature
        for feature in setup.terrain_features
        if feature.feature_id
        == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-03-component-01"
    )
    wall = next(wall for wall in ruins.walls if wall.wall_id == "ground-long-solid-wall")
    battlefield_state = _battlefield_state_with_only_unit_placed(
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    formation_offsets = _ruin_wall_traversal_formation_offsets(len(unit_placement.model_placements))
    wall_axis_radians = math.radians(wall.rotation_degrees)
    tangent_x = math.cos(wall_axis_radians)
    tangent_y = math.sin(wall_axis_radians)
    normal_x = -math.sin(wall_axis_radians)
    normal_y = math.cos(wall_axis_radians)
    crossing_distance_inches = 6.0
    start_normal_offset_inches = -3.0
    updated_placements: list[ModelPlacement] = []
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement, (tangent_offset, normal_offset) in zip(
        unit_placement.model_placements,
        formation_offsets,
        strict=True,
    ):
        start_normal = start_normal_offset_inches + normal_offset
        start_pose = Pose.at(
            wall.center_x_inches + (tangent_offset * tangent_x) + (start_normal * normal_x),
            wall.center_y_inches + (tangent_offset * tangent_y) + (start_normal * normal_y),
            facing_degrees=wall.rotation_degrees,
        )
        end_pose = Pose.at(
            start_pose.position.x + (crossing_distance_inches * normal_x),
            start_pose.position.y + (crossing_distance_inches * normal_y),
            facing_degrees=wall.rotation_degrees,
        )
        midpoint = Pose.at(
            (start_pose.position.x + end_pose.position.x) / 2.0,
            (start_pose.position.y + end_pose.position.y) / 2.0,
            facing_degrees=wall.rotation_degrees,
        )
        updated_placements.append(placement.with_pose(start_pose))
        model_paths.append((placement.model_instance_id, (start_pose, midpoint, end_pose)))
    unit_placement = unit_placement.with_model_placements(tuple(updated_placements))
    battlefield_state = replace(
        battlefield_state.with_unit_placement(unit_placement),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield_state),
        unit_placement,
        PathWitness.for_paths(tuple(model_paths)),
        ruins,
        wall,
    )


def _exact_dense_non_ruin_air_path_scenario(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> tuple[
    BattlefieldScenario,
    UnitPlacement,
    PathWitness,
    TerrainFeatureDefinition,
    TerrainWallDefinition,
]:
    setup = _exact_phase17n_layout_a_setup()
    dense_non_ruin = next(
        feature
        for feature in setup.terrain_features
        if feature.feature_id
        == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-05-component-01"
    )
    wall = dense_non_ruin.walls[0]
    battlefield_state = _battlefield_state_with_only_unit_placed(
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )
    unit_placement = battlefield_state.unit_placement_by_id(unit_instance_id)
    tangent_offsets = (-1.4, 0.0, 1.4)
    if len(unit_placement.model_placements) != len(tangent_offsets):
        raise AssertionError("Exact dense non-ruin traversal requires three Screamers.")
    wall_axis_radians = math.radians(wall.rotation_degrees)
    tangent_x = math.cos(wall_axis_radians)
    tangent_y = math.sin(wall_axis_radians)
    normal_x = -math.sin(wall_axis_radians)
    normal_y = math.cos(wall_axis_radians)
    updated_placements: list[ModelPlacement] = []
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for placement, tangent_offset in zip(
        unit_placement.model_placements,
        tangent_offsets,
        strict=True,
    ):
        start_pose = Pose.at(
            wall.center_x_inches + (tangent_offset * tangent_x) - (2.0 * normal_x),
            wall.center_y_inches + (tangent_offset * tangent_y) - (2.0 * normal_y),
            facing_degrees=wall.rotation_degrees,
        )
        apex_pose = Pose.at(
            wall.center_x_inches + (tangent_offset * tangent_x),
            wall.center_y_inches + (tangent_offset * tangent_y),
            wall.height_inches,
            facing_degrees=wall.rotation_degrees,
        )
        end_pose = Pose.at(
            wall.center_x_inches + (tangent_offset * tangent_x) + (2.0 * normal_x),
            wall.center_y_inches + (tangent_offset * tangent_y) + (2.0 * normal_y),
            facing_degrees=wall.rotation_degrees,
        )
        updated_placements.append(placement.with_pose(start_pose))
        model_paths.append((placement.model_instance_id, (start_pose, apex_pose, end_pose)))
    unit_placement = unit_placement.with_model_placements(tuple(updated_placements))
    battlefield_state = replace(
        battlefield_state.with_unit_placement(unit_placement),
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=setup.terrain_features,
    )
    return (
        BattlefieldScenario(armies=scenario.armies, battlefield_state=battlefield_state),
        unit_placement,
        PathWitness.for_paths(tuple(model_paths)),
        dense_non_ruin,
        wall,
    )


def _battlefield_state_with_only_unit_placed(
    *,
    scenario: BattlefieldScenario,
    unit_instance_id: str,
) -> BattlefieldRuntimeState:
    battlefield_state = scenario.battlefield_state
    other_unit_ids = tuple(
        unit_placement.unit_instance_id
        for placed_army in battlefield_state.placed_armies
        for unit_placement in placed_army.unit_placements
        if unit_placement.unit_instance_id != unit_instance_id
    )
    for other_unit_id in other_unit_ids:
        battlefield_state = battlefield_state.without_unit_placement(other_unit_id)
    return battlefield_state


def _ruin_wall_traversal_formation_offsets(
    model_count: int,
) -> tuple[tuple[float, float], ...]:
    if model_count == 3:
        return ((-1.4, 0.0), (0.0, 0.0), (1.4, 0.0))
    if model_count == 5:
        return (
            (-1.4, 0.0),
            (0.0, 0.0),
            (1.4, 0.0),
            (-0.7, -1.4),
            (0.7, -1.4),
        )
    raise AssertionError("Exact ruin traversal requires a three- or five-model unit.")


def _assert_exact_ruin_wall_traversal(
    *,
    resolution: NormalMoveResolution,
    ruins: TerrainFeatureDefinition,
    wall: TerrainWallDefinition,
) -> None:
    assert resolution.is_valid
    assert resolution.coherency_result.is_coherent
    assert ruins.source_id is not None
    assert "purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in ruins.source_id
    assert all(result.is_valid for result in resolution.path_validation_results)
    assert all(result.is_valid for result in resolution.terrain_path_legality_results)
    for terrain_result in resolution.terrain_path_legality_results:
        wall_segments = tuple(
            segment
            for segment in terrain_result.segments
            if segment.terrain_id == f"{ruins.feature_id}:{wall.wall_id}"
        )
        assert wall_segments
        assert all(segment.traversal_mode.value == "through_feature" for segment in wall_segments)


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
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=("take-and-hold" if player_id == "player-a" else "purge-the-foe"),
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


def _full_unit_witness_with_only_first_model_moved(
    unit_placement: UnitPlacement,
    *,
    first_model_end_pose: Pose,
) -> PathWitness:
    model_paths: list[tuple[str, tuple[Pose, ...]]] = []
    for index, placement in enumerate(unit_placement.model_placements):
        start = placement.pose
        if index == 0:
            midpoint = Pose.at(
                (start.position.x + first_model_end_pose.position.x) / 2.0,
                (start.position.y + first_model_end_pose.position.y) / 2.0,
                (start.position.z + first_model_end_pose.position.z) / 2.0,
                facing_degrees=(start.facing.degrees + first_model_end_pose.facing.degrees) / 2.0,
            )
            model_paths.append(
                (placement.model_instance_id, (start, midpoint, first_model_end_pose))
            )
            continue
        model_paths.append((placement.model_instance_id, (start, start)))
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
        rules_footprint_polygon=_display_geometry(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=8.0,
            depth_inches=6.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=center_x_inches,
            center_y_inches=center_y_inches,
            width_inches=8.0,
            depth_inches=6.0,
        ),
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
