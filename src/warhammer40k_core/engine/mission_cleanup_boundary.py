"""Apply coherency destruction consistently to physical and mission state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_unit_destructions_for_end_turn_cleanup,
)
from warhammer40k_core.engine.turn_cleanup import resolve_end_turn_cleanup

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_mission_cleanup_boundary(*, state: GameState, completed_phase: BattlePhase) -> None:
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
    for model_id in cleanup.removed_model_instance_ids:
        # Coherency destruction suppresses destroyed-model rules, not the death.
        # The cleanup already owns the exact physical removal and its evidence.
        destroy_model_by_rule(
            state=state, model_instance_id=model_id, remove_from_battlefield=False
        )
    state.battlefield_state = updated_battlefield
    record_primary_unit_destructions_for_end_turn_cleanup(state=state, cleanup=cleanup)
    state.end_turn_cleanup_states.append(cleanup)
    state.end_turn_cleanup_states.sort(key=lambda row: row.cleanup_id)
