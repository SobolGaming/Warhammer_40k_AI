"""Shared 15.07 eligibility; independent Ingress permissions do not waive it."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.cult_ambush import reserve_state_is_cult_ambush
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState, ReserveStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def rapid_ingress_window_error(*, state: GameState, player_id: str) -> str | None:
    if state.battle_round == 1:
        return "rapid_ingress_first_battle_round"
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        return "rapid_ingress_requires_movement_phase"
    if state.active_player_id is None or state.active_player_id == player_id:
        return "rapid_ingress_requires_opponent_turn"
    return None


def rapid_ingress_reserve_error(*, state: GameState, reserve: ReserveState) -> str | None:
    if (
        reserve.status is not ReserveStatus.IN_RESERVES
        or reserve.reserve_kind is not ReserveKind.STRATEGIC_RESERVES
        or reserve_state_is_cult_ambush(reserve)
    ):
        return "unit_not_eligible_for_rapid_ingress"
    unit = rules_unit_view_by_id(state=state, unit_instance_id=reserve.unit_instance_id)
    if "AIRCRAFT" in unit.keywords:
        return "rapid_ingress_aircraft_target"
    return None


def rapid_ingress_target_error(
    *, state: GameState, player_id: str, unit_instance_id: str
) -> str | None:
    window_error = rapid_ingress_window_error(state=state, player_id=player_id)
    if window_error is not None:
        return window_error
    reserve = state.reserve_state_for_unit(unit_instance_id)
    if (
        reserve is None
        or reserve.player_id != player_id
        or reserve.unit_instance_id != unit_instance_id
    ):
        return "unit_not_eligible_for_rapid_ingress"
    return rapid_ingress_reserve_error(state=state, reserve=reserve)
