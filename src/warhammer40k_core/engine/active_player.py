from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def effective_active_player_id(
    state: GameState, *, trigger_kind: TimingTriggerKind | None = None
) -> str | None:
    """Apply 01.03 without changing the player whose turn it is."""
    if trigger_kind in (TimingTriggerKind.START_BATTLE_ROUND, TimingTriggerKind.END_BATTLE_ROUND):
        if not state.turn_order:
            raise GameLifecycleError("Between-turn sequencing requires the first-turn player.")
        return state.turn_order[0]
    if state.active_player_scopes:
        return state.active_player_scopes[-1].player_id
    shooting = state.shooting_phase_state
    if (
        shooting is not None
        and shooting.active_selection is not None
        and shooting.pending_completed_attack_sequence is None
    ):
        return shooting.active_selection.player_id
    charge = state.charge_phase_state
    if charge is not None and charge.active_selection is not None:
        return charge.active_selection.player_id
    movement = state.movement_phase_state
    if movement is not None and movement.active_selection is not None:
        return movement.active_selection.player_id
    return state.active_player_id
