from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def reserve_arrival_restriction_expiry_is_proven(
    *,
    state: GameState,
    arrival_active_player_id: str,
    restriction_battle_round: int,
) -> bool:
    """Return whether the authoritative turn cursor passed the arrival turn end."""
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Reserve restriction expiry requires GameState.")
    if arrival_active_player_id not in state.player_ids:
        raise GameLifecycleError("Reserve restriction expiry arrival player is not in this game.")
    if type(restriction_battle_round) is not int or restriction_battle_round <= 0:
        raise GameLifecycleError("Reserve restriction expiry round must be positive.")
    if state.stage is GameLifecycleStage.COMPLETE:
        return state.battle_round >= restriction_battle_round
    if state.battle_round > restriction_battle_round:
        return True
    if state.battle_round != restriction_battle_round or state.active_player_id is None:
        return False
    return state.turn_order.index(state.active_player_id) > state.turn_order.index(
        arrival_active_player_id
    )


def reserve_arrival_restriction_cleanup_is_due(
    *,
    restriction_battle_round: int,
    completed_battle_round: int,
) -> bool:
    """Return whether the turn ending now is the recorded arrival turn."""
    if type(restriction_battle_round) is not int or restriction_battle_round <= 0:
        raise GameLifecycleError("Reserve restriction round must be positive.")
    if type(completed_battle_round) is not int or completed_battle_round <= 0:
        raise GameLifecycleError("Reserve restriction completed round must be positive.")
    return completed_battle_round == restriction_battle_round


__all__ = (
    "reserve_arrival_restriction_cleanup_is_due",
    "reserve_arrival_restriction_expiry_is_proven",
)
