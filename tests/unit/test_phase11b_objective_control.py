from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    CharacteristicValueKind,
)
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.objectives import Objective, ObjectiveMarker, ObjectiveMarkerPayload
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    TerrainFeatureKind,
    TerrainObjectiveControlPolicy,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldScenario,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.endpoint_placement import (
    ObjectiveMarkerEndpointPlacementViolation,
    ObjectiveMarkerEndpointPlacementViolationPayload,
    objective_marker_endpoint_placement_violation,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, GameStatePayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlRecordPayload,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    ObjectiveMarkerEndpointViolation,
    ObjectiveMarkerEndpointViolationPayload,
    model_objective_control_characteristic,
    objective_control_status_from_token,
    objective_control_timing_from_token,
    objective_marker_endpoint_violations,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model as GeometryModel
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)


def test_objective_control_sums_oc_by_player_from_current_runtime_models() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0), (-2.0, 0.0)),
        player_b_offsets=((0.0, 2.0),),
    )
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
        )
    )
    result = _center_result(record)

    assert result.status is ObjectiveControlStatus.CONTROLLED
    assert result.controlled_by_player_id == "player-a"
    assert [(score.player_id, score.score) for score in result.scores] == [
        ("player-a", 4),
        ("player-b", 2),
    ]
    assert all(contribution.effective_objective_control > 0 for contribution in result.contributors)


def test_battle_shocked_unit_contributes_oc_zero() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0), (-2.0, 0.0)),
        player_b_offsets=((0.0, 2.0),),
        battle_shocked_unit_ids=("army-alpha:intercessor-unit-1",),
    )

    result = _center_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert result.controlled_by_player_id == "player-b"
    assert [(score.player_id, score.score) for score in result.scores] == [("player-b", 2)]
    assert {
        contribution.model_instance_id: contribution.effective_objective_control
        for contribution in result.contributors
        if contribution.player_id == "player-a"
    } == {
        "army-alpha:intercessor-unit-1:core-intercessor-like:001": 0,
        "army-alpha:intercessor-unit-1:core-intercessor-like:002": 0,
    }
    assert all(
        contribution.battle_shocked
        for contribution in result.contributors
        if contribution.player_id == "player-a"
    )
    player_a_army = state.army_definition_for_player("player-a")
    assert player_a_army is not None
    shocked_characteristic = model_objective_control_characteristic(
        player_a_army.units[0].own_models[0],
        battle_shocked=True,
    )
    assert shocked_characteristic.value_kind is CharacteristicValueKind.REPLACEMENT_DASH
    assert shocked_characteristic.applied_modifier_ids == ("battle_shock",)


def test_contested_objective_has_deterministic_uncontrolled_result() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((-2.0, 0.0),),
    )

    result = _center_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert result.status is ObjectiveControlStatus.CONTESTED
    assert result.controlled_by_player_id is None
    assert [(score.player_id, score.score) for score in result.scores] == [
        ("player-a", 2),
        ("player-b", 2),
    ]


def test_objective_without_controlling_models_is_uncontrolled() -> None:
    far_offsets = (
        (20.0, 20.0),
        (24.0, 20.0),
        (28.0, 20.0),
        (32.0, 20.0),
        (36.0, 20.0),
    )
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=far_offsets,
        player_b_offsets=far_offsets,
    )

    result = _center_result(
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=ObjectiveControlTiming.PHASE_END,
                phase=BattlePhase.COMMAND,
            )
        )
    )

    assert result.status is ObjectiveControlStatus.UNCONTROLLED
    assert result.controlled_by_player_id is None
    assert result.scores == ()
    assert result.contributors == ()


def test_objective_marker_payloads_round_trip_with_default_geometry() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    marker = _center_marker_definition(state).to_objective_marker()
    payload = cast(
        ObjectiveMarkerPayload,
        json.loads(json.dumps(marker.to_payload(), sort_keys=True)),
    )

    restored = ObjectiveMarker.from_payload(payload)
    from_point_objective = ObjectiveMarker.from_objective(
        Objective.point(
            objective_id="point-objective",
            name="Point Objective",
            x=1.0,
            y=2.0,
            z=0.5,
            control_radius_inches=4.0,
        )
    )

    assert restored == marker
    assert marker.stable_identity() == f"objective-marker:{marker.objective_marker_id}"
    assert math.isclose(marker.marker_diameter_inches, 40.0 / 25.4, rel_tol=0.0, abs_tol=1e-12)
    assert from_point_objective.control_horizontal_inches == 4.0
    assert from_point_objective.control_vertical_inches == 5.0


def test_terrain_objective_control_policy_is_explicitly_unsupported() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    ruleset = _ruleset()
    unsupported_ruleset = replace(
        ruleset,
        objective_policy=replace(
            ruleset.objective_policy,
            terrain_objective_control_policy=TerrainObjectiveControlPolicy.UNSUPPORTED,
        ),
        descriptor_hash="",
    )
    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=unsupported_ruleset,
        terrain_objectives=(Objective.terrain("ruin-objective", "Ruin", "ruin-alpha"),),
    )

    result = resolve_objective_control(context).result_by_objective_id("ruin-objective")

    assert result.status is ObjectiveControlStatus.UNSUPPORTED
    assert result.unsupported_reason == "terrain_objective_control_policy_unsupported"
    assert result.scores == ()
    assert result.controlled_by_player_id is None


def test_terrain_objectives_derive_from_coincident_marker_and_control_area() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((0.0, 0.0),))
    marker = _center_marker_definition(state)
    terrain_feature = TerrainFeatureDefinition(
        feature_id="center-terrain-objective",
        feature_kind=TerrainFeatureKind.WOODS,
        footprint_center_x_inches=marker.x_inches,
        footprint_center_y_inches=marker.y_inches,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=marker.x_inches,
            center_y_inches=marker.y_inches,
            width_inches=6.0,
            depth_inches=6.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=marker.x_inches,
            center_y_inches=marker.y_inches,
            width_inches=6.0,
            depth_inches=6.0,
        ),
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    state.battlefield_state = replace(
        state.battlefield_state,
        terrain_features=(terrain_feature,),
    )

    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=_ruleset(),
    )
    record = resolve_objective_control(context)
    result = record.result_by_objective_id(marker.objective_marker_id)

    assert marker.objective_marker_id not in {
        objective_marker.objective_marker_id for objective_marker in context.objective_markers
    }
    assert context.terrain_objectives == (
        Objective.terrain(
            marker.objective_marker_id,
            marker.name,
            terrain_feature.feature_id,
        ),
    )
    assert result.status is ObjectiveControlStatus.CONTROLLED
    assert result.controlled_by_player_id == "player-a"
    assert result.contributors[0].horizontal_distance_inches == 0.0
    assert (
        ObjectiveControlRecord.from_payload(
            cast(
                ObjectiveControlRecordPayload,
                json.loads(json.dumps(record.to_payload(), sort_keys=True)),
            )
        ).to_payload()
        == record.to_payload()
    )


def test_terrain_objective_control_requires_terrain_area_containment_not_marker_radius() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((5.0, 0.0),))
    marker = _center_marker_definition(state)
    terrain_feature = TerrainFeatureDefinition(
        feature_id="center-terrain-objective",
        feature_kind=TerrainFeatureKind.WOODS,
        footprint_center_x_inches=marker.x_inches,
        footprint_center_y_inches=marker.y_inches,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=marker.x_inches,
            center_y_inches=marker.y_inches,
            width_inches=6.0,
            depth_inches=6.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=marker.x_inches,
            center_y_inches=marker.y_inches,
            width_inches=6.0,
            depth_inches=6.0,
        ),
    )
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    state.battlefield_state = replace(
        state.battlefield_state,
        terrain_features=(terrain_feature,),
    )

    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=_ruleset(),
    )
    result = resolve_objective_control(context).result_by_objective_id(marker.objective_marker_id)

    assert marker.objective_marker_id not in {
        objective_marker.objective_marker_id for objective_marker in context.objective_markers
    }
    assert context.terrain_objectives == (
        Objective.terrain(
            marker.objective_marker_id,
            marker.name,
            terrain_feature.feature_id,
        ),
    )
    assert result.status is ObjectiveControlStatus.UNCONTROLLED
    assert result.contributors == ()


@pytest.mark.parametrize("layout_number", [1, 2, 3])
def test_phase17n_opponent_home_control_uses_source_linked_area_not_marker_radius(
    layout_number: int,
) -> None:
    state = _phase17n_linked_objective_state(layout_number)
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    defender_home = next(
        marker
        for marker in state.mission_setup.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.DEFENDER_HOME
    )
    link = next(
        definition
        for definition in state.mission_setup.objective_terrain_areas
        if definition.objective_marker_id == defender_home.objective_marker_id
    )
    areas_by_id = {area.terrain_area_id: area for area in state.mission_setup.terrain_areas}
    farthest_point = max(
        (
            point
            for terrain_area_id in link.terrain_area_ids
            for point in areas_by_id[terrain_area_id].footprint_polygon
        ),
        key=lambda point: math.hypot(
            point.x_inches - defender_home.x_inches,
            point.y_inches - defender_home.y_inches,
        ),
    )
    assert (
        math.hypot(
            farthest_point.x_inches - defender_home.x_inches,
            farthest_point.y_inches - defender_home.y_inches,
        )
        > 7.0
    )

    battlefield = state.battlefield_state
    player_a = battlefield.unit_placement_by_id("army-alpha:intercessor-unit-1")
    selected = player_a.model_placements[0]
    moved_player_a = player_a.with_model_placements(
        (
            selected.with_pose(
                Pose.at(
                    farthest_point.x_inches,
                    farthest_point.y_inches,
                    0.0,
                    facing_degrees=selected.pose.facing.degrees,
                )
            ),
            *player_a.model_placements[1:],
        )
    )
    battlefield = battlefield.with_unit_placement(moved_player_a)
    battlefield = battlefield.with_removed_models(
        tuple(
            model_instance_id
            for model_instance_id in battlefield.placed_model_ids()
            if model_instance_id != selected.model_instance_id
        )
    )
    state.replace_battlefield_state(battlefield)

    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=_ruleset(),
    )
    result = resolve_objective_control(context).result_by_objective_id(
        defender_home.objective_marker_id
    )

    assert defender_home.objective_marker_id not in {
        marker.objective_marker_id for marker in context.objective_markers
    }
    assert link in context.objective_terrain_areas
    assert defender_home.to_objective_marker() in context.objective_terrain_area_markers
    assert result.status is ObjectiveControlStatus.CONTROLLED
    assert result.controlled_by_player_id == "player-a"
    assert tuple(contributor.model_instance_id for contributor in result.contributors) == (
        selected.model_instance_id,
    )
    assert result.contributors[0].horizontal_distance_inches == 0.0


def test_source_linked_and_explicit_terrain_objectives_are_mutually_exclusive() -> None:
    state = _phase17n_linked_objective_state(1)

    with pytest.raises(GameLifecycleError, match="mutually exclusive"):
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
            ruleset_descriptor=_ruleset(),
            terrain_objectives=(
                Objective.terrain("explicit-terrain-objective", "Explicit", "ruin-alpha"),
            ),
        )


def test_source_linked_objective_context_requires_exact_area_and_marker_containment() -> None:
    state = _phase17n_linked_objective_state(1)
    runtime_ruleset = state.ruleset_descriptor_for_runtime_policy()
    assert runtime_ruleset.mission_policy.terrain_objective_missions_supported
    context = ObjectiveControlContext.from_game_state(
        state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=runtime_ruleset,
    )
    first_link = context.objective_terrain_areas[0]
    areas_by_logical_id: dict[str, list[str]] = {}
    for area in context.terrain_areas:
        areas_by_logical_id.setdefault(area.logical_terrain_area_id, []).append(
            area.terrain_area_id
        )
    grouped_area_ids = next(
        tuple(sorted(area_ids)) for area_ids in areas_by_logical_id.values() if len(area_ids) > 1
    )

    with pytest.raises(GameLifecycleError, match="every physical member"):
        replace(
            context,
            objective_terrain_areas=tuple(
                replace(link, terrain_area_ids=(grouped_area_ids[0],))
                if link == first_link
                else link
                for link in context.objective_terrain_areas
            ),
        )

    omitted_group_member_id = grouped_area_ids[0]
    with pytest.raises(GameLifecycleError, match="must group at least two physical areas"):
        replace(
            context,
            terrain_areas=tuple(
                area
                for area in context.terrain_areas
                if area.terrain_area_id != omitted_group_member_id
            ),
        )

    retained_group_member_id = grouped_area_ids[-1]
    with pytest.raises(GameLifecycleError, match="terrain areas drifted from MissionSetup"):
        replace(
            context,
            terrain_areas=tuple(
                replace(area, logical_terrain_area_id=retained_group_member_id)
                if area.terrain_area_id == retained_group_member_id
                else area
                for area in context.terrain_areas
                if area.terrain_area_id not in grouped_area_ids[:-1]
            ),
        )

    omitted_link = context.objective_terrain_areas[0]
    with pytest.raises(
        GameLifecycleError,
        match="objective terrain-area membership drifted from MissionSetup",
    ):
        replace(
            context,
            objective_terrain_areas=context.objective_terrain_areas[1:],
            objective_terrain_area_markers=tuple(
                marker
                for marker in context.objective_terrain_area_markers
                if marker.objective_marker_id != omitted_link.objective_marker_id
            ),
        )

    mixed_state = _phase17n_layout_state("priority-assets-vs-priority-assets-layout-1")
    mixed_context = ObjectiveControlContext.from_game_state(
        mixed_state,
        timing=ObjectiveControlTiming.PHASE_END,
        phase=BattlePhase.COMMAND,
        ruleset_descriptor=mixed_state.ruleset_descriptor_for_runtime_policy(),
    )
    assert mixed_context.objective_markers
    with pytest.raises(GameLifecycleError, match="objective source inventory drifted"):
        replace(mixed_context, objective_markers=mixed_context.objective_markers[1:])

    supported_ruleset = _ruleset()
    unsupported_ruleset = replace(
        supported_ruleset,
        objective_policy=replace(
            supported_ruleset.objective_policy,
            terrain_objective_control_policy=TerrainObjectiveControlPolicy.UNSUPPORTED,
        ),
        descriptor_hash="",
    )
    with pytest.raises(GameLifecycleError, match="objective source inventory drifted"):
        replace(
            context,
            ruleset_descriptor=unsupported_ruleset,
            objective_terrain_areas=(),
            objective_terrain_area_markers=(),
        )

    with pytest.raises(GameLifecycleError, match="mutually exclusive"):
        replace(
            context,
            terrain_objectives=(
                Objective.terrain(
                    "injected-extra-objective",
                    "Injected Extra Objective",
                    context.terrain_features[0].feature_id,
                ),
            ),
        )

    with pytest.raises(GameLifecycleError, match="runtime state drifted"):
        replace(
            context,
            scenario=replace(
                context.scenario,
                battlefield_state=replace(
                    context.scenario.battlefield_state,
                    terrain_features=(),
                ),
            ),
        )

    with pytest.raises(GameLifecycleError, match="unknown terrain area"):
        replace(
            context,
            terrain_areas=tuple(
                area
                for area in context.terrain_areas
                if area.terrain_area_id not in first_link.terrain_area_ids
            ),
        )

    linked_marker = next(
        marker
        for marker in context.objective_terrain_area_markers
        if marker.objective_marker_id == first_link.objective_marker_id
    )
    with pytest.raises(GameLifecycleError, match="must intersect"):
        replace(
            context,
            objective_terrain_area_markers=tuple(
                replace(marker, x_inches=0.0, y_inches=0.0) if marker == linked_marker else marker
                for marker in context.objective_terrain_area_markers
            ),
        )


def test_nonblocking_objective_marker_can_be_occupied_at_endpoint() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    scenario = _scenario_from_state(state)
    marker_definition = _center_marker_definition(state)
    marker = marker_definition.to_objective_marker()
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    overlapping = _with_model_offsets(
        unit_placement,
        marker_definition,
        offsets=((0.0, 0.0),),
    )
    geometry_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(overlapping.model_placements[0]),
        placement=overlapping.model_placements[0],
    )

    assert not marker.blocks_placement
    assert (
        objective_marker_endpoint_violations(
            scenario=scenario,
            objective_markers=(marker,),
            unit_placement=overlapping,
        )
        == ()
    )
    assert (
        objective_marker_endpoint_placement_violation(
            model=geometry_model,
            objective_markers=(marker,),
            violation_code="objective_marker_endpoint_overlap",
            placement_label="Normal Move",
        )
        is None
    )


def test_explicit_blocking_objective_marker_endpoint_is_rejected() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    scenario = _scenario_from_state(state)
    marker_definition = _center_marker_definition(state)
    marker = replace(marker_definition.to_objective_marker(), blocks_placement=True)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )
    overlapping = _with_model_offsets(
        unit_placement,
        marker_definition,
        offsets=((0.0, 0.0),),
    )

    violations = objective_marker_endpoint_violations(
        scenario=scenario,
        objective_markers=(marker,),
        unit_placement=overlapping,
    )
    scenario_wide_violations = objective_marker_endpoint_violations(
        scenario=scenario,
        objective_markers=(marker,),
    )
    violation_payload = cast(
        ObjectiveMarkerEndpointViolationPayload,
        json.loads(json.dumps(violations[0].to_payload(), sort_keys=True)),
    )

    assert len(violations) == 1
    assert violations[0].objective_marker_id == marker.objective_marker_id
    assert violations[0].model_instance_id == overlapping.model_placements[0].model_instance_id
    assert violations[0].violation_code == "objective_marker_endpoint_overlap"
    assert scenario_wide_violations == ()
    assert ObjectiveMarkerEndpointViolation.from_payload(violation_payload) == violations[0]


def test_normal_move_endpoint_on_blocking_objective_marker_is_rejected_by_shared_resolver() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((4.0, 0.0), (4.0, 2.0), (4.0, 4.0), (4.0, 6.0), (4.0, 8.0)),
    )
    scenario = _scenario_from_state(state)
    marker = replace(_center_marker_definition(state).to_objective_marker(), blocks_placement=True)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        "army-alpha:intercessor-unit-1"
    )

    resolution = resolve_normal_move(
        scenario=scenario,
        ruleset_descriptor=_ruleset(),
        unit_placement=unit_placement,
        path_witness=_straight_line_witness(unit_placement, delta_x=-4.0),
        objective_markers=(marker,),
    )

    assert not resolution.is_valid
    assert any(
        violation.violation_code == "objective_marker_endpoint_overlap"
        and violation.blocker_id == marker.objective_marker_id
        for path_result in resolution.path_validation_results
        for violation in path_result.violations
    )


def test_setup_endpoint_on_nonblocking_objective_marker_is_allowed_by_game_state() -> None:
    mission_setup = _mission_setup()
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11b-invalid-setup-battlefield",
        armies=armies,
    )
    marker = _center_marker_definition(state)
    player_a = scenario.battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = scenario.battlefield_state.with_unit_placement(
        _with_model_offsets(player_a, marker, offsets=((0.0, 0.0),))
    )

    state.record_battlefield_state(battlefield_state)

    assert state.battlefield_state is battlefield_state


def test_objective_marker_endpoint_placement_violation_payload_round_trips() -> None:
    violation = ObjectiveMarkerEndpointPlacementViolation(
        violation_code="objective_marker_endpoint_overlap",
        message="Normal Move cannot end on an objective marker.",
        model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
        blocker_id="mission-a-center",
    )
    payload = cast(
        ObjectiveMarkerEndpointPlacementViolationPayload,
        json.loads(json.dumps(violation.to_payload(), sort_keys=True)),
    )

    assert ObjectiveMarkerEndpointPlacementViolation.from_payload(payload) == violation


def test_battlefield_state_replacement_requires_existing_battlefield_state() -> None:
    mission_setup = _mission_setup()
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    battlefield_state = create_deterministic_battlefield_scenario(
        battlefield_id="phase11b-replace-missing-battlefield",
        armies=armies,
    ).battlefield_state

    with pytest.raises(GameLifecycleError, match="BattlefieldRuntimeState"):
        state.replace_battlefield_state(cast(BattlefieldRuntimeState, object()))
    with pytest.raises(GameLifecycleError, match="does not exist"):
        state.replace_battlefield_state(battlefield_state)
    with pytest.raises(GameLifecycleError, match="already exists"):
        state.record_mission_setup(_mission_setup())
    with pytest.raises(GameLifecycleError, match="geometry Model"):
        objective_marker_endpoint_placement_violation(
            model=cast(GeometryModel, object()),
            objective_markers=(),
            violation_code="objective_marker_endpoint_overlap",
            placement_label="Normal Move",
        )


def test_objective_control_records_update_at_phase_and_turn_end() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))

    completed_phase = state.advance_to_next_battle_phase()

    assert completed_phase is BattlePhase.COMMAND
    assert len(state.objective_control_records) == 1
    assert state.objective_control_records[0].timing is ObjectiveControlTiming.PHASE_END
    assert state.objective_control_records[0].phase == BattlePhase.COMMAND.value

    while state.current_battle_phase is not BattlePhase.FIGHT:
        state.advance_to_next_battle_phase()
    state.advance_to_next_battle_phase()

    assert [record.timing for record in state.objective_control_records[-2:]] == [
        ObjectiveControlTiming.PHASE_END,
        ObjectiveControlTiming.TURN_END,
    ]
    assert state.objective_control_records[-1].phase == BattlePhase.FIGHT.value
    assert state.objective_control_records[-1].active_player_id == "player-a"


def test_end_boundary_control_is_fixed_before_later_end_of_phase_mutation() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))

    determined = state.determine_current_end_objective_control()
    marker = _center_marker_definition(state)
    battlefield = state.battlefield_state
    assert battlefield is not None
    player_a = battlefield.unit_placement_by_id("army-alpha:intercessor-unit-1")
    state.replace_battlefield_state(
        battlefield.with_unit_placement(
            _with_model_offsets(player_a, marker, offsets=((20.0, 0.0),))
        )
    )

    state.advance_to_next_battle_phase()

    assert len(determined) == 1
    assert len(state.objective_control_records) == 1
    assert state.objective_control_records[0] == determined[0]
    assert determined[0].results[0].controlled_by_player_id == "player-a"


def test_objective_control_boundary_requires_mission_setup() -> None:
    state = GameState.from_config(_config(mission_setup=None))
    state.enter_battle()

    with pytest.raises(GameLifecycleError, match="MissionSetup"):
        state.advance_to_next_battle_phase()


def test_objective_control_payloads_round_trip_without_object_reprs() -> None:
    state = _battle_state_with_center_objective_positions(
        player_a_offsets=((2.0, 0.0),),
        player_b_offsets=((-2.0, 0.0),),
    )
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
        )
    )
    state.record_objective_control_record(record)
    record_payload = cast(
        ObjectiveControlRecordPayload,
        json.loads(json.dumps(record.to_payload(), sort_keys=True)),
    )
    state_payload = cast(GameStatePayload, json.loads(json.dumps(state.to_payload())))
    blob = json.dumps({"record": record_payload, "state": state_payload}, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert ObjectiveControlRecord.from_payload(record_payload).to_payload() == record.to_payload()
    assert GameState.from_payload(state_payload).to_payload() == state.to_payload()


def test_objective_control_validation_is_fail_fast() -> None:
    state = _battle_state_with_center_objective_positions(player_a_offsets=((2.0, 0.0),))
    scenario = _scenario_from_state(state)
    marker = _center_marker_definition(state).to_objective_marker()
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.COMMAND,
        )
    )
    score_a = ObjectiveControlScore(player_id="player-a", score=2)
    score_b = ObjectiveControlScore(player_id="player-b", score=1)

    with pytest.raises(GameLifecycleError, match="ObjectiveControlTiming token"):
        objective_control_timing_from_token(10)
    with pytest.raises(GameLifecycleError, match="Unsupported ObjectiveControlTiming"):
        objective_control_timing_from_token("bad-timing")
    with pytest.raises(GameLifecycleError, match="ObjectiveControlStatus token"):
        objective_control_status_from_token(10)
    with pytest.raises(GameLifecycleError, match="Unsupported ObjectiveControlStatus"):
        objective_control_status_from_token("bad-status")
    with pytest.raises(GameLifecycleError, match="Unsupported battle phase token"):
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase="psychic",
        )
    with pytest.raises(GameLifecycleError, match="phase must be a BattlePhase token"):
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=cast(BattlePhase | str, 10),
        )
    with pytest.raises(GameLifecycleError, match="ObjectiveControlRecord objective_id"):
        record.result_by_objective_id("missing-objective")
    with pytest.raises(GameLifecycleError, match="resolve_objective_control requires"):
        resolve_objective_control(cast(ObjectiveControlContext, object()))
    with pytest.raises(GameLifecycleError, match="objective marker endpoint validation"):
        objective_marker_endpoint_violations(
            scenario=cast(BattlefieldScenario, object()),
            objective_markers=(marker,),
        )
    with pytest.raises(GameLifecycleError, match="unit_placement must be"):
        objective_marker_endpoint_violations(
            scenario=scenario,
            objective_markers=(marker,),
            unit_placement=cast(UnitPlacement, object()),
        )
    with pytest.raises(GameLifecycleError, match="battle_shocked must be a bool"):
        ObjectiveControlContribution(
            player_id="player-a",
            unit_instance_id="army-alpha:intercessor-unit-1",
            model_instance_id="army-alpha:intercessor-unit-1:core-intercessor-like:001",
            objective_control=2,
            effective_objective_control=2,
            battle_shocked=cast(bool, "yes"),
            horizontal_distance_inches=0.0,
            vertical_gap_inches=0.0,
        )
    with pytest.raises(GameLifecycleError, match="Unsupported objective control requires"):
        ObjectiveControlResult(
            objective_id="unsupported-objective",
            status=ObjectiveControlStatus.UNSUPPORTED,
            controlled_by_player_id=None,
            scores=(),
        )
    with pytest.raises(GameLifecycleError, match="Uncontrolled objective results"):
        ObjectiveControlResult(
            objective_id="uncontrolled-objective",
            status=ObjectiveControlStatus.UNCONTROLLED,
            controlled_by_player_id=None,
            scores=(score_a,),
        )
    with pytest.raises(GameLifecycleError, match="Contested objective results cannot"):
        ObjectiveControlResult(
            objective_id="contested-with-controller",
            status=ObjectiveControlStatus.CONTESTED,
            controlled_by_player_id="player-a",
            scores=(
                ObjectiveControlScore(player_id="player-a", score=2),
                ObjectiveControlScore(player_id="player-b", score=2),
            ),
        )
    with pytest.raises(GameLifecycleError, match="Contested objective results require"):
        ObjectiveControlResult(
            objective_id="contested-objective",
            status=ObjectiveControlStatus.CONTESTED,
            controlled_by_player_id=None,
            scores=(score_a, score_b),
        )
    with pytest.raises(GameLifecycleError, match="Controlled objective results require"):
        ObjectiveControlResult(
            objective_id="controlled-without-controller",
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id=None,
            scores=(score_a,),
        )
    with pytest.raises(GameLifecycleError, match="Controlled objective controller must"):
        ObjectiveControlResult(
            objective_id="controlled-unknown-controller",
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id="player-c",
            scores=(score_a,),
        )
    with pytest.raises(GameLifecycleError, match="Controlled objective controller score"):
        ObjectiveControlResult(
            objective_id="controlled-objective",
            status=ObjectiveControlStatus.CONTROLLED,
            controlled_by_player_id="player-b",
            scores=(score_a, score_b),
        )


def _phase17n_linked_objective_state(layout_number: int) -> GameState:
    return _phase17n_layout_state(f"purge-the-foe-vs-purge-the-foe-layout-{layout_number}")


def _phase17n_layout_state(layout_id: str) -> GameState:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    mission_pool_entry = next(
        entry
        for entry in mission_pack.mission_pool_entries
        if layout_id in entry.terrain_layout_ids
    )
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=mission_pool_entry.mission_pool_entry_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id=mission_pool_entry.player_force_disposition_id,
        defender_player_id="player-b",
        defender_force_disposition_id=mission_pool_entry.opponent_force_disposition_id,
    )
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id=f"phase17n-linked-objective-{layout_id}",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    _force_battle_for_objective_fixture(state)
    return state


def _battle_state_with_center_objective_positions(
    *,
    player_a_offsets: tuple[tuple[float, float], ...],
    player_b_offsets: tuple[tuple[float, float], ...] = (),
    battle_shocked_unit_ids: tuple[str, ...] = (),
) -> GameState:
    mission_setup = _mission_setup()
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11b-battlefield",
        armies=armies,
    )
    marker = _center_marker_definition(state)
    battlefield_state = scenario.battlefield_state
    if player_a_offsets:
        player_a = battlefield_state.unit_placement_by_id("army-alpha:intercessor-unit-1")
        battlefield_state = battlefield_state.with_unit_placement(
            _with_model_offsets(player_a, marker, offsets=player_a_offsets)
        )
    if player_b_offsets:
        player_b = battlefield_state.unit_placement_by_id("army-beta:intercessor-unit-3")
        battlefield_state = battlefield_state.with_unit_placement(
            _with_model_offsets(player_b, marker, offsets=player_b_offsets)
        )
    state.record_battlefield_state(battlefield_state)
    _force_battle_for_objective_fixture(state)
    state.battle_shocked_unit_ids = list(battle_shocked_unit_ids)
    return state


def _force_battle_for_objective_fixture(state: GameState) -> None:
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    state.complete_final_setup_step_before_battle()
    state.enter_battle()


def _with_model_offsets(
    unit_placement: UnitPlacement,
    marker: ObjectiveMarkerDefinition,
    *,
    offsets: tuple[tuple[float, float], ...],
) -> UnitPlacement:
    placements = list(unit_placement.model_placements)
    for index, (offset_x, offset_y) in enumerate(offsets):
        placement = placements[index]
        placements[index] = placement.with_pose(
            Pose.at(
                marker.x_inches + offset_x,
                marker.y_inches + offset_y,
                marker.z_inches,
                facing_degrees=placement.pose.facing.degrees,
            )
        )
    return unit_placement.with_model_placements(tuple(placements))


def _straight_line_witness(
    unit_placement: UnitPlacement,
    *,
    delta_x: float,
) -> PathWitness:
    return PathWitness.for_straight_line_endpoints(
        tuple(
            (
                placement.model_instance_id,
                placement.pose,
                Pose.at(
                    placement.pose.position.x + delta_x,
                    placement.pose.position.y,
                    placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
            for placement in unit_placement.model_placements
        )
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


def _center_marker_definition(state: GameState) -> ObjectiveMarkerDefinition:
    if state.mission_setup is None:
        raise AssertionError("test state requires mission setup")
    for marker in state.mission_setup.objective_markers:
        if _is_center_objective_id(marker.objective_marker_id):
            return marker
    raise AssertionError("missing center objective marker")


def _center_result(record: ObjectiveControlRecord) -> ObjectiveControlResult:
    for result in record.results:
        if _is_center_objective_id(result.objective_id):
            return result
    raise AssertionError("missing center objective control result")


def _is_center_objective_id(objective_id: str) -> bool:
    return objective_id.endswith(("-center", "-center-central"))


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


def _scenario_from_state(state: GameState) -> BattlefieldScenario:
    if state.battlefield_state is None:
        raise AssertionError("test state requires battlefield state")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=state.battlefield_state,
    )


def _config(*, mission_setup: MissionSetup | None) -> GameConfig:
    base_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    mission_force_disposition_ids = (
        ()
        if mission_setup is None
        else tuple(
            sorted(
                {
                    assignment.force_disposition_id
                    for assignment in mission_setup.primary_mission_assignments
                }
            )
        )
    )
    catalog = replace(
        base_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=(
                    *detachment.force_disposition_ids,
                    *(
                        force_disposition_id
                        for force_disposition_id in mission_force_disposition_ids
                        if force_disposition_id not in detachment.force_disposition_ids
                    ),
                ),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in base_catalog.detachments
        ),
    )
    return GameConfig(
        game_id="phase11b-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1",),
                mission_setup=mission_setup,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                mission_setup=mission_setup,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11b-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    mission_setup: MissionSetup | None,
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
        force_disposition_id=(
            mission_setup.force_disposition_id_for_player(player_id)
            if mission_setup is not None
            else ("take-and-hold" if player_id == "player-a" else "purge-the-foe")
        ),
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
    armies = tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )
    assert all(
        _model_objective_control(model.characteristics) == 2
        for army in armies
        for unit in army.units
        for model in unit.own_models
    )
    return armies


def _model_objective_control(characteristics: tuple[CharacteristicValue, ...]) -> int:
    if type(characteristics) is not tuple:
        raise AssertionError("model characteristics must be a tuple")
    for characteristic in characteristics:
        if characteristic.characteristic is Characteristic.OBJECTIVE_CONTROL:
            return characteristic.final
    raise AssertionError("model missing Objective Control")
