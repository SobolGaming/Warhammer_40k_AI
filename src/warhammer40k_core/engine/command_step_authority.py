from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.command_points import CommandStepState
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def ensure_command_step_state(
    state: GameState,
    *,
    active_player_id: str,
) -> CommandStepState:
    if state.command_step_state is None:
        command_state = CommandStepState.start(
            battle_round=state.battle_round,
            active_player_id=active_player_id,
        )
        state.replace_command_step_state(command_state)
        return command_state
    command_state = state.command_step_state
    if command_state.active_player_id != active_player_id:
        raise GameLifecycleError("CommandStepState active player drift.")
    if command_state.battle_round != state.battle_round:
        raise GameLifecycleError("CommandStepState battle round drift.")
    return command_state


def command_step_state(state: GameState) -> CommandStepState:
    if state.command_step_state is None:
        raise GameLifecycleError("Command phase requires CommandStepState.")
    return state.command_step_state
