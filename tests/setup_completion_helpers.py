from __future__ import annotations

from warhammer40k_core.engine.game_state import GameState


def enter_battle_for_fixture(state: GameState) -> None:
    final_setup_step = state.setup_sequence[-1]
    while state.current_setup_step is not final_setup_step:
        state.complete_current_setup_step()
    state.complete_final_setup_step_before_battle()
    state.enter_battle()
