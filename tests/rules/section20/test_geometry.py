"""20.03/20.04: actual native physical setup, horizontal distance and round rules."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import placement, scenario
from tests.support.section20_fixtures import SPAWN, reserve_scene
from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.ingress_placement_restrictions import restrictions_for_arrival
from warhammer40k_core.engine.reserves import StrategicReserveRule, resolve_reserve_arrival
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("edge", ["north", "south", "east", "west"])
@pytest.mark.parametrize("outside", [False, True])
def test_every_edge_measures_whole_native_base_inclusive_six_inches(
    section20_definitions: Section02Definitions, edge: str, outside: bool
) -> None:
    s = reserve_scene(section20_definitions)
    radius = s.unit.own_models[0].geometry.parts[0].radius_x_inches
    distance = 6 - radius + (0.001 if outside else 0)
    x, y = {
        "west": (distance, 15),
        "east": (60 - distance, 15),
        "south": (20, distance),
        "north": (20, 44 - distance),
    }[edge]
    before = s.state.to_payload()
    result = resolve_reserve_arrival(
        scenario=scenario(s.state),
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        reserve_state=s.state.reserve_states[0],
        attempted_placement=placement(s.unit, (Pose.at(x, y),)),
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid is (not outside)
    assert (result.transition_batch is not None) is (not outside)
    if outside:
        assert "strategic_reserves_edge_distance" in {
            v.violation_code.value for v in result.violations
        }
    assert s.state.to_payload() == before


@pytest.mark.parametrize(("gap", "valid"), [(7.999, False), (8, False), (8.001, True)])
@pytest.mark.parametrize("height", [0, 20])
def test_enemy_distance_is_strictly_more_than_eight_horizontally(
    section20_definitions: Section02Definitions, gap: float, valid: bool, height: float
) -> None:
    s = reserve_scene(section20_definitions)
    r = s.unit.own_models[0].geometry.parts[0].radius_x_inches
    er = s.enemy.own_models[0].geometry.parts[0].radius_x_inches
    assert s.state.battlefield_state is not None
    board = s.state.battlefield_state
    enemy_place = board.unit_placement_by_id(s.enemy.unit_instance_id)
    target = replace(
        enemy_place,
        model_placements=(
            replace(enemy_place.model_placements[0], pose=Pose.at(2 + r + er + gap, 15, height)),
        ),
    )
    s.state.replace_battlefield_state(
        replace(
            board,
            placed_armies=tuple(
                replace(a, unit_placements=(target,)) if a.player_id == "opponent" else a
                for a in board.placed_armies
            ),
        )
    )
    result = resolve_reserve_arrival(
        scenario=scenario(s.state),
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        reserve_state=s.state.reserve_states[0],
        attempted_placement=placement(s.unit, (Pose.at(2, 15),)),
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid is valid
    assert ("reserve_enemy_distance" in {v.violation_code.value for v in result.violations}) is (
        not valid
    )


@pytest.mark.parametrize("round_number", [1, 2, 3])
@pytest.mark.parametrize("inside", [False, True])
def test_early_arrival_permission_does_not_erase_pre_third_round_enemy_zone_exclusion(
    section20_definitions: Section02Definitions, round_number: int, inside: bool
) -> None:
    s = reserve_scene(section20_definitions)
    zone = DeploymentZone.rectangle(
        "constructed:s20:enemy-zone", "opponent", min_x=0, min_y=10, max_x=10, max_y=30
    )
    result = resolve_reserve_arrival(
        scenario=scenario(s.state),
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        reserve_state=s.state.reserve_states[0],
        attempted_placement=placement(s.unit, (Pose.at(2, 15 if inside else 5),)),
        battle_round=round_number,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        enemy_deployment_zones=(zone,),
        strategic_reserve_rule=StrategicReserveRule(
            earliest_arrival_battle_round=1, ignores_mission_arrival_round_blocks=True
        ),
    )
    forbidden = inside and round_number < 3
    assert result.is_valid is (not forbidden)
    assert (
        "strategic_reserves_enemy_deployment_zone"
        in {v.violation_code.value for v in result.violations}
    ) is forbidden


@pytest.mark.parametrize("round_number", [1, 2, 3])
@pytest.mark.parametrize(
    "kind", [BattlefieldPlacementKind.STRATEGIC_RESERVES, BattlefieldPlacementKind.DEEP_STRIKE]
)
def test_retained_ingress_policy_preserves_early_enemy_zone_exclusion(
    round_number: int, kind: BattlefieldPlacementKind
) -> None:
    result = restrictions_for_arrival(
        placement_kind=kind,
        battle_round=round_number,
        strategic_rule=StrategicReserveRule(
            earliest_arrival_battle_round=1, ignores_mission_arrival_round_blocks=True
        ),
        deep_strike_enemy_distance=None,
        source_restrictions=(),
        distance_grants=(),
    )
    assert result.excludes_enemy_deployment_zone is (
        kind is BattlefieldPlacementKind.STRATEGIC_RESERVES and round_number < 3
    )


@pytest.mark.parametrize("round_number", [1, 2, 3, 4])
def test_default_arrival_requires_second_round_then_ingress(
    section20_definitions: Section02Definitions, round_number: int
) -> None:
    s = reserve_scene(section20_definitions)
    result = resolve_reserve_arrival(
        scenario=scenario(s.state),
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        reserve_state=s.state.reserve_states[0],
        attempted_placement=placement(s.unit, (Pose.at(2, 15),)),
        battle_round=round_number,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid is (round_number >= 2)
    assert (result.transition_batch is not None) is (round_number >= 2)


@pytest.mark.parametrize("case", ["two-edges", "incoherent", "overlap", "missing", "off-board"])
def test_all_models_can_use_different_edges_but_must_complete_legal_setup(
    section20_definitions: Section02Definitions, case: str
) -> None:
    s = reserve_scene(section20_definitions, sheet=SPAWN)
    poses = {
        "two-edges": (Pose.at(1.1, 6.1), Pose.at(3.5, 4)),
        "incoherent": (Pose.at(1.1, 15), Pose.at(1.1, 30)),
        "overlap": (Pose.at(1.1, 15), Pose.at(1.1, 15)),
        "missing": (Pose.at(1.1, 15), Pose.at(1.1, 17.5)),
        "off-board": (Pose.at(0.1, 15), Pose.at(1.1, 17.5)),
    }[case]
    attempted = placement(s.unit, poses)
    if case == "missing":
        attempted = replace(attempted, model_placements=attempted.model_placements[:1])
    before = s.state.to_payload()
    result = resolve_reserve_arrival(
        scenario=scenario(s.state),
        ruleset_descriptor=s.state.runtime_ruleset_descriptor(),
        reserve_state=s.state.reserve_states[0],
        attempted_placement=attempted,
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
    )
    assert result.is_valid is (case == "two-edges")
    codes = {v.violation_code.value for v in result.violations}
    if case != "two-edges":
        assert {
            "incoherent": "unit_coherency_broken",
            "overlap": "end_on_model_overlap",
            "missing": "unit_placement_drift",
            "off-board": "battlefield_edge_crossed",
        }[case] in codes
    assert s.state.to_payload() == before
