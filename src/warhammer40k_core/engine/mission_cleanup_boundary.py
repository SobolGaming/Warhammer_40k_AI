"""Apply coherency destruction consistently to physical and mission state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_model_destruction_unplaced import (
    destroy_end_turn_coherency_models,
)
from warhammer40k_core.engine.turn_cleanup import EndTurnCleanupState, resolve_end_turn_cleanup

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_mission_cleanup_boundary(
    *, state: GameState, completed_phase: BattlePhase
) -> EndTurnCleanupState:
    if state.battlefield_state is None:
        raise GameLifecycleError("End-turn cleanup requires battlefield_state.")
    if state.active_player_id is None:
        raise GameLifecycleError("End-turn cleanup requires an active player.")
    cleanup, updated_battlefield = resolve_end_turn_cleanup(
        game_id=state.game_id,
        scenario=BattlefieldScenario(
            armies=tuple(state.army_definitions), battlefield_state=state.battlefield_state
        ),
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=completed_phase,
    )
    destroy_end_turn_coherency_models(state=state, cleanup=cleanup)
    state.replace_battlefield_state(updated_battlefield)
    return cleanup
