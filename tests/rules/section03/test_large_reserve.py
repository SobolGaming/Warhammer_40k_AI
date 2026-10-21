"""Oversized Strategic Reserves: explicit unavailable-size/aircraft rule contracts."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_contracts import oversized_contract
from tests.support.section03_fixtures import geometry, native_state, placement, scenario
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.large_model_restrictions import large_model_activity_reason
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reserves import (
    BattlefieldEdge,
    LargeModelReservePlacementException,
    resolve_reserve_arrival,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("aircraft", [False, True])
@pytest.mark.parametrize(("gap", "valid"), [(8, False), (8.001, True)])
def test_oversized_reserve_keeps_enemy_distance_and_aircraft_exemption(
    section03_definitions: Section02Definitions, aircraft: bool, gap: float, valid: bool
) -> None:
    unit = oversized_contract(section03_definitions, aircraft=aircraft)
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    em = geometry(enemy, (Pose.at(30, 20), Pose.at(30, 22.5)), enemy=True)[0]
    assert isinstance(em.base, CircularBase)
    ex = 8 + gap + em.base.radius
    state = native_state(
        section03_definitions, unit, enemy=enemy, enemy_poses=(Pose.at(ex, 20), Pose.at(ex, 22.5))
    )
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        placed_armies=tuple(
            a for a in state.battlefield_state.placed_armies if a.player_id == "opponent"
        ),
    )
    state.battle_round = 2
    reserve_unit(state, unit)
    reserve = state.reserve_states[0]
    result = resolve_reserve_arrival(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        reserve_state=reserve,
        attempted_placement=placement(unit, (Pose.at(4, 20),)),
        battle_round=2,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        large_model_exceptions=(
            LargeModelReservePlacementException(unit.own_model_ids()[0], BattlefieldEdge.WEST),
        ),
    )
    assert result.is_valid is valid
    if not valid:
        assert any(v.violation_code.value == "reserve_enemy_distance" for v in result.violations)
        return
    assert result.large_model_exception_used
    assert bool(result.post_arrival_restrictions) is (not aircraft)
    state.reserve_states[:] = [
        reserve.mark_arrived(
            battle_round=2,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=True,
            post_arrival_restrictions=result.post_arrival_restrictions,
        )
    ]
    for action in ("normal", "advance", "fall_back", "charge", "ranged_attacks"):
        assert (large_model_activity_reason(state, unit.unit_instance_id, action) is not None) is (
            not aircraft
        )
    assert large_model_activity_reason(state, unit.unit_instance_id, "melee_attacks") is None
    state.reserve_states[:] = [
        state.reserve_states[0].clear_expired_post_arrival_restrictions(
            player_id="owner", battle_round=2
        )
    ]
    assert large_model_activity_reason(state, unit.unit_instance_id, "ranged_attacks") is None
