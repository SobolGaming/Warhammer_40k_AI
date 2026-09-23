"""Separate the first turn-end control snapshot from later turn cleanup."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.effects import EffectExpirationBoundary
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def determine_turn_end_control(
    *,
    state: GameState,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    """Freeze control after the final phase, before any turn-end rule can mutate it."""
    player_id = _validate_boundary(state, completed_phase)
    existing = tuple(
        record
        for record in state.objective_control_records
        if record.timing is ObjectiveControlTiming.TURN_END
        and record.battle_round == state.battle_round
        and record.active_player_id == state.active_player_id
        and record.phase == completed_phase.value
    )
    if len(existing) > 1:
        raise GameLifecycleError("Turn-end preparation found duplicate objective records.")
    if existing:
        return existing[0]
    # Phase-end rules have finished. Their expiring effects must not reach the
    # distinct turn boundary; the already-retained phase record stays unchanged.
    expire_completed_phase_effects(
        state=state, completed_phase=completed_phase, player_id=player_id
    )
    return state.record_objective_control_boundary(
        completed_phase=completed_phase,
        timing=ObjectiveControlTiming.TURN_END,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def prepare_turn_end_boundary(
    *,
    state: GameState,
    completed_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> ObjectiveControlRecord:
    """Finish non-mission cleanup once, preserving the earlier control snapshot."""
    record = determine_turn_end_control(
        state=state,
        completed_phase=completed_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    completed_cleanup = tuple(
        cleanup
        for cleanup in state.end_turn_cleanup_states
        if cleanup.battle_round == state.battle_round
        and cleanup.active_player_id == state.active_player_id
        and cleanup.phase == completed_phase.value
    )
    if len(completed_cleanup) > 1:
        raise GameLifecycleError("Turn-end preparation found duplicate cleanup records.")
    if completed_cleanup:
        return record
    state.clear_turn_action_states(
        player_id=record.active_player_id, battle_round=state.battle_round
    )
    state.resolve_end_turn_cleanup_boundary(completed_phase=completed_phase)
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.turn_end(
            battle_round=state.battle_round, player_id=record.active_player_id
        )
    )
    return record


def expire_completed_phase_effects(
    *, state: GameState, completed_phase: BattlePhase, player_id: str
) -> None:
    # The final phase can already have expired before turn rules. Cleanup often
    # leaves no effects at all; avoid a redundant expiry call in that case.
    # Effects created by turn-end rules still expire at the later phase advance.
    if completed_phase is state.battle_phase_sequence[-1] and not state.persisting_effects:
        return
    state.expire_persisting_effects_at_boundary(
        EffectExpirationBoundary.phase_end(
            battle_round=state.battle_round, phase=completed_phase, player_id=player_id
        )
    )


def _validate_boundary(state: GameState, completed_phase: BattlePhase) -> str:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Turn-end preparation requires battle stage.")
    if state.active_player_id is None or state.battle_phase_index is None:
        raise GameLifecycleError("Turn-end preparation requires an active battle turn.")
    if state.battle_phase_index + 1 != len(state.battle_phase_sequence):
        raise GameLifecycleError("Turn-end preparation requires the final battle phase.")
    if completed_phase is not state.current_battle_phase:
        raise GameLifecycleError("Turn-end preparation phase drifted.")
    return state.active_player_id
