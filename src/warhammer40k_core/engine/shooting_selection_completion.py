"""Resume precommitted selection obligations after an automatic no-attack terminal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_state import AttackSequence
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.shooting_without_attacks import (
    NO_ATTACK_COMPLETION_EVENT,
    NoAttackCompletion,
    completion_from_event,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.attack_sequence_completion_hooks import (
        AttackSequenceCompletedHookRegistry,
    )
    from warhammer40k_core.engine.decision_controller import DecisionController
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry


def selection_completion_sequence(row: NoAttackCompletion) -> AttackSequence:
    return AttackSequence.start(
        sequence_id=row.activity_id,
        attacker_player_id=row.player_id,
        attacking_unit_instance_id=row.unit_instance_id,
        source_phase=BattlePhase.SHOOTING,
        attack_pools=(),
        weapons_without_attacks=(),
    )


def selection_completion_origin(
    *, events: tuple[EventRecord, ...], sequence_id: str
) -> tuple[EventRecord, AttackSequence] | None:
    matches = [
        (event, row)
        for event in events
        if event.event_type == NO_ATTACK_COMPLETION_EVENT
        and (row := completion_from_event(event)).activity_id == sequence_id
    ]
    if not matches:
        return None
    if len(matches) != 1:
        raise GameLifecycleError("Selection completion requires a unique no-attack origin.")
    event, row = matches[0]
    return event, selection_completion_sequence(row)


def pending_selection_obligations(
    *,
    row: NoAttackCompletion,
    event: EventRecord,
    state: GameState,
    decisions: DecisionController,
    hooks: AttackSequenceCompletedHookRegistry,
    modifiers: RuntimeModifierRegistry,
) -> AttackSequence | None:
    from warhammer40k_core.engine.attack_sequence_completion_hooks import (
        AttackSequenceCompletedContext,
    )
    from warhammer40k_core.engine.dice import DiceRollManager

    sequence = selection_completion_sequence(row)
    context = AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=modifiers,
        source_phase=BattlePhase.SHOOTING,
        attack_sequence=sequence,
        attack_sequence_completed_event_id=event.event_id,
    )
    return sequence if hooks.candidates_for(context) else None
