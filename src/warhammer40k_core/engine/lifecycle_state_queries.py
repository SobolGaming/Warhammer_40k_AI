from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def embarked_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        unit_id
        for cargo_state in state.transport_cargo_states
        if cargo_state.player_id == player_id
        for unit_id in cargo_state.embarked_unit_instance_ids
    }


def unarrived_reserve_unit_ids_for_player(*, state: GameState, player_id: str) -> set[str]:
    return {
        reserve_state.unit_instance_id
        for reserve_state in state.unarrived_reserve_states_for_player(player_id)
    }
