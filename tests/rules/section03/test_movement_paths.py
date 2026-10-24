"""03.01: whole native unit witnesses at the movement evaluator boundary."""

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, INFRACTORS, Section02Definitions
from tests.support.section03_fixtures import geometry, grid, native_state, paths, scenario
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("datasheet", [INFRACTORS, CHAOS_SPAWN])
@pytest.mark.parametrize("moved_count", [1, 2])
def test_only_selected_members_displace(
    section03_definitions: Section02Definitions, datasheet: str, moved_count: int
) -> None:
    unit = section03_definitions.unit(datasheet)
    starts = grid(unit)
    ends = tuple(
        Pose.at(p.position.x, p.position.y + 0.5) if i < moved_count else p
        for i, p in enumerate(starts)
    )
    state = native_state(section03_definitions, unit, starts)
    board = scenario(state)
    before = board.battlefield_state.to_payload()
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        path_witness=paths(unit, starts, ends),
    )
    assert result.is_valid
    assert tuple(p.pose for p in result.attempted_placement.model_placements) == ends
    assert result.rollback_record is None
    assert board.battlefield_state.to_payload() == before


@pytest.mark.parametrize("reverse", [False, True])
def test_sequential_swap_rejected_before_any_mutation(
    section03_definitions: Section02Definitions, reverse: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    state = native_state(section03_definitions, unit, starts)
    board = scenario(state)
    witness = paths(unit, starts, tuple(reversed(starts)))
    if reverse:
        witness = PathWitness.for_paths(tuple(reversed(witness.model_paths)))
    before = state.to_payload()
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        path_witness=witness,
    )
    assert not result.is_valid
    assert any(
        v.violation_code == "end_on_model_overlap"
        for r in result.path_validation_results
        for v in r.violations
    )
    assert state.to_payload() == before


@pytest.mark.parametrize("vacate_first", [False, True])
def test_vacated_space_requires_actual_model_order(
    section03_definitions: Section02Definitions, vacate_first: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    state = native_state(section03_definitions, unit, starts)
    board = scenario(state)
    witness = paths(unit, starts, (starts[1], Pose.at(12.5, 12.5)))
    if vacate_first:
        witness = PathWitness.for_paths(tuple(reversed(witness.model_paths)))
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        path_witness=witness,
    )
    assert result.is_valid is vacate_first


@pytest.mark.parametrize("end", [Pose.at(18, 10), Pose.at(10, 18)])
def test_incoherent_endpoint_returns_whole_original_placement(
    section03_definitions: Section02Definitions, end: Pose
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    starts = (Pose.at(10, 10), Pose.at(12.5, 10))
    state = native_state(section03_definitions, unit, starts)
    board = scenario(state)
    original = board.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    result = resolve_normal_move(
        scenario=board,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=original,
        path_witness=paths(unit, starts, (end, starts[1])),
    )
    assert not result.is_valid
    assert not result.coherency_result.is_coherent
    assert result.rollback_record is not None
    assert board.battlefield_state.unit_placement_by_id(unit.unit_instance_id) == original


@pytest.mark.parametrize(
    ("enemy", "permission", "end_x", "code"),
    [
        (False, False, 18, None),
        (False, False, 13, "end_on_model_overlap"),
        (True, False, 18, "enemy_model_base_crossed"),
        (True, True, 18, None),
        (True, True, 13, "end_on_model_overlap"),
        (True, True, 16, "enemy_engagement_range_end_forbidden"),
        (True, True, 0, "battlefield_edge_crossed"),
    ],
)
def test_transit_permission_preserves_endpoint_and_edge_rules(
    section03_definitions: Section02Definitions,
    enemy: bool,
    permission: bool,
    end_x: float,
    code: str | None,
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    moving, blocker = geometry(unit, (Pose.at(10, 10), Pose.at(13, 10)))
    result = PathValidationContext(
        moving_model=moving,
        witness=PathWitness.for_paths(((moving.model_id, (moving.pose, Pose.at(end_x, 10))),)),
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        friendly_models=() if enemy else (blocker,),
        enemy_models=(blocker,) if enemy else (),
        may_transit_enemy_models=permission,
        enemy_engagement_horizontal_inches=2,
        enemy_engagement_vertical_inches=5,
    ).validate()
    assert result.is_valid is (code is None)
    if code is not None:
        assert result.violations[0].violation_code == code


@pytest.mark.parametrize("permission", [False, True])
def test_while_moving_checks_midpath_engagement(
    section03_definitions: Section02Definitions, permission: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    moving, blocker = geometry(unit, (Pose.at(8, 10), Pose.at(13, 12.5)))
    result = PathValidationContext(
        moving_model=moving,
        witness=PathWitness.for_paths(((moving.model_id, (moving.pose, Pose.at(18, 10))),)),
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        enemy_models=(blocker,),
        may_transit_enemy_engagement=permission,
        enemy_engagement_horizontal_inches=2,
        enemy_engagement_vertical_inches=5,
    ).validate()
    assert result.is_valid is permission
    if not permission:
        assert result.violations[0].violation_code == "enemy_engagement_range_transit_forbidden"
