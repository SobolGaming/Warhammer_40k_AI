from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING, cast

from warhammer40k_core.engine.attack_completion_sequencing import attack_completion_timing_context
from warhammer40k_core.engine.attack_completion_triggers import (
    attack_context_for_trigger,
    resolve_attack_trigger,
)
from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.battle_shock_outcome_sequencing import (
    outcome_candidates,
    outcome_timing_context,
)
from warhammer40k_core.engine.move_completion_candidates import move_completion_candidates
from warhammer40k_core.engine.move_completion_sequencing import move_completion_timing_context
from warhammer40k_core.engine.move_completion_triggers import (
    move_context_for_trigger,
    resolve_move_trigger,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.phases.shooting_completion_candidates import (
    shooting_completion_candidates,
)
from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_batch_state import TimingBatch
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.timing_windows import TimingTriggerKind

if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.bundle import RuntimeContentBundle
    from warhammer40k_core.engine.unit_move_completed_hooks import UnitMoveCompletedContext
from warhammer40k_core.engine.battle_shock_outcome_triggers import (
    battle_shock_context_for_trigger,
    resolve_battle_shock_trigger,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.rule_trigger_state import (
    RuleTrigger,
    RuleTriggerKind,
    rule_trigger_history,
)


def advance_rule_triggers(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
    shooting_handler_provider: Callable[[], ShootingPhaseHandler],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.model_destruction_triggers import (
        resolve_model_destruction_trigger,
    )

    record_loaded_model_destruction_occurrences(
        state=state,
        decisions=decisions,
        runtime_bundle_provider=runtime_bundle_provider,
    )
    if decisions.queue.pending_requests:
        return None
    while ready := rule_trigger_history(decisions).ready():
        trigger = ready[0]
        if _internal_action_in_progress(state, trigger):
            return None
        runtime_bundle = runtime_bundle_provider()
        if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION:
            status = resolve_model_destruction_trigger(
                state=state,
                decisions=decisions,
                trigger=trigger,
                registry=runtime_bundle.unit_destroyed_hook_registry,
            )
        elif trigger.kind is RuleTriggerKind.BATTLE_SHOCK_OUTCOME:
            status = resolve_battle_shock_trigger(
                state=state,
                decisions=decisions,
                trigger=trigger,
                registry=runtime_bundle.battle_shock_hook_registry,
            )
        elif trigger.kind is RuleTriggerKind.MOVE_COMPLETION:
            move_context = move_context_for_trigger(
                state=state,
                decisions=decisions,
                trigger=trigger,
                runtime_modifiers=runtime_bundle.runtime_modifier_registry,
                ability_indexes=runtime_bundle.ability_indexes_by_player_id,
            )
            status = resolve_move_trigger(
                additional_candidates=partial(_loaded_move_reactions, runtime_bundle),
                context=move_context,
                trigger=trigger,
                mortal_wound_hooks=runtime_bundle.unit_move_completed_mortal_wound_hook_registry,
                battle_shock_move_hooks=runtime_bundle.unit_move_completed_battle_shock_hook_registry,
                battle_shock_hooks=runtime_bundle.battle_shock_hook_registry,
            )
        elif trigger.kind is RuleTriggerKind.ATTACK_COMPLETION:
            context = attack_context_for_trigger(
                state=state,
                decisions=decisions,
                trigger=trigger,
                runtime_modifiers=runtime_bundle.runtime_modifier_registry,
            )

            status = resolve_attack_trigger(
                context=context,
                trigger=trigger,
                discover=partial(
                    _attack_candidates, context, runtime_bundle, shooting_handler_provider()
                ),
            )
        else:
            raise GameLifecycleError("Rule trigger has no loaded lifecycle continuation.")
        if status is not None:
            return status
    return None


def validate_rule_trigger_history(
    *, state: GameState, decisions: DecisionController, pending_only: bool = False
) -> None:
    from warhammer40k_core.engine.model_destruction_triggers import (
        validate_model_destruction_observations,
    )

    validate_model_destruction_observations(state=state, decisions=decisions)
    history = rule_trigger_history(decisions)
    from warhammer40k_core.engine.command_battle_shock_batch_history import (
        validate_command_test_batches,
    )

    validate_command_test_batches(state=state, decisions=decisions, history=history)
    for trigger in history.observed:
        if pending_only and trigger.trigger_id in history.completed:
            continue
        if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION:
            from warhammer40k_core.engine.model_destruction_triggers import destruction_source_event

            destruction_source_event(state=state, decisions=decisions, trigger=trigger)
        elif trigger.kind is RuleTriggerKind.BATTLE_SHOCK_OUTCOME:
            battle_shock_context_for_trigger(state=state, decisions=decisions, trigger=trigger)
        elif trigger.kind is RuleTriggerKind.MOVE_COMPLETION:
            from warhammer40k_core.engine.faction_content.unit_move_completed import (
                move_completion_rule_registry,
            )

            move_context = move_context_for_trigger(
                state=state,
                decisions=decisions,
                trigger=trigger,
                runtime_modifiers=RuntimeModifierRegistry.empty(),
                ability_indexes={},
            )
            move_completion_rule_registry().candidates_for(move_context)
        elif trigger.kind is RuleTriggerKind.ATTACK_COMPLETION:
            attack_context_for_trigger(
                state=state,
                decisions=decisions,
                trigger=trigger,
                runtime_modifiers=RuntimeModifierRegistry.empty(),
            )
        else:
            raise GameLifecycleError("Rule trigger has no source authority validator.")


def _attack_candidates(
    context: AttackSequenceCompletedContext,
    bundle: RuntimeContentBundle,
    shooting_handler: ShootingPhaseHandler,
) -> tuple[TimingRuleCandidate, ...]:
    additional = (
        shooting_completion_candidates(
            handler=shooting_handler,
            state=context.state,
            decisions=context.decisions,
            sequence=context.attack_sequence,
            completed_event_id=context.attack_sequence_completed_event_id,
        )
        if context.source_phase is BattlePhase.SHOOTING
        else ()
    )
    return (*bundle.attack_sequence_completed_hook_registry.candidates_for(context), *additional)


def _internal_action_in_progress(state: GameState, trigger: RuleTrigger) -> bool:
    if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION:
        return False
    own_sequence_id: str | None = None
    if trigger.kind is RuleTriggerKind.ATTACK_COMPLETION:
        context = trigger.context
        if not isinstance(context, dict) or not isinstance(context.get("attack_sequence"), dict):
            raise GameLifecycleError("Attack trigger has no sequence context.")
        sequence = context["attack_sequence"]
        if not isinstance(sequence, dict) or type(sequence.get("sequence_id")) is not str:
            raise GameLifecycleError("Attack trigger has no sequence identity.")
        own_sequence_id = cast(str, sequence["sequence_id"])
    shooting = state.out_of_phase_shooting_state
    if shooting is not None:
        completed = shooting.pending_completed_attack_sequence
        return completed is None or completed.sequence_id != own_sequence_id
    fight = state.fight_phase_state
    if fight is not None and fight.forced_activation_context is not None:
        completed = fight.pending_completed_attack_sequence
        if fight.attack_sequence is None and completed is None:
            # A response queue or its completed Overrun pile-in is not an
            # executing attack. Resolve that move before attack declaration.
            return False
        return completed is None or completed.sequence_id != own_sequence_id
    ordinary_shooting = state.shooting_phase_state
    if ordinary_shooting is not None and ordinary_shooting.attack_sequence is not None:
        return True
    return fight is not None and fight.attack_sequence is not None


def validate_trigger_order_candidates(
    *,
    state: GameState,
    decisions: DecisionController,
    batch: TimingBatch,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
    shooting_handler_provider: Callable[[], ShootingPhaseHandler],
) -> None:
    if batch.context.timing_window.descriptor.trigger_kind not in (
        TimingTriggerKind.AFTER_UNIT_DESTROYED,
        TimingTriggerKind.AFTER_DICE_ROLL,
        TimingTriggerKind.AFTER_UNIT_ATTACKS_RESOLVED,
        TimingTriggerKind.AFTER_UNIT_ENDS_MOVE,
        TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE,
        TimingTriggerKind.MODEL_PLACED_ON_BATTLEFIELD,
    ):
        return
    runtime_bundle = runtime_bundle_provider()
    shooting_handler = shooting_handler_provider()
    history = rule_trigger_history(decisions)
    triggers = tuple(
        trigger for trigger in history.ready() if trigger.conflict_id == batch.context.conflict_id
    )
    if len(triggers) != 1 or triggers[0].trigger_id not in history.released:
        raise GameLifecycleError("Sequencing request has no released source trigger.")
    trigger = triggers[0]
    if trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION:
        from warhammer40k_core.engine.model_destruction_triggers import destroyed_unit_context
        from warhammer40k_core.engine.unit_destruction_sequencing import (
            unit_destruction_timing_context,
        )

        destruction_context = destroyed_unit_context(
            state=state, decisions=decisions, trigger=trigger
        )
        if destruction_context is None:
            raise GameLifecycleError("Unit sequencing has no destroyed logical unit.")
        authority = unit_destruction_timing_context(destruction_context)
        candidates = runtime_bundle.unit_destroyed_hook_registry.candidates_for(destruction_context)
    elif trigger.kind is RuleTriggerKind.ATTACK_COMPLETION:
        context = attack_context_for_trigger(
            state=state,
            decisions=decisions,
            trigger=trigger,
            runtime_modifiers=runtime_bundle.runtime_modifier_registry,
        )
        authority = attack_completion_timing_context(context)
        candidates = _attack_candidates(context, runtime_bundle, shooting_handler)
    elif trigger.kind is RuleTriggerKind.BATTLE_SHOCK_OUTCOME:
        outcome_context = battle_shock_context_for_trigger(
            state=state, decisions=decisions, trigger=trigger
        )
        authority = outcome_timing_context(outcome_context)
        candidates = outcome_candidates(outcome_context, runtime_bundle.battle_shock_hook_registry)
    elif trigger.kind is RuleTriggerKind.MOVE_COMPLETION:
        move_context = move_context_for_trigger(
            state=state,
            decisions=decisions,
            trigger=trigger,
            runtime_modifiers=runtime_bundle.runtime_modifier_registry,
            ability_indexes=runtime_bundle.ability_indexes_by_player_id,
        )
        authority = move_completion_timing_context(move_context)
        candidates = move_completion_candidates(
            additional_candidates=partial(_loaded_move_reactions, runtime_bundle),
            context=move_context,
            mortal_wound_hooks=runtime_bundle.unit_move_completed_mortal_wound_hook_registry,
            battle_shock_move_hooks=runtime_bundle.unit_move_completed_battle_shock_hook_registry,
            battle_shock_hooks=runtime_bundle.battle_shock_hook_registry,
        )
    else:
        raise GameLifecycleError("Sequencing trigger has no source candidate authority.")
    if batch.context != authority:
        raise GameLifecycleError("Sequencing request source trigger context drift.")
    current = {
        candidate.participant.participant_id: candidate.participant for candidate in candidates
    }
    if len(current) != len(candidates) or any(
        current.get(participant.participant_id) != participant
        for participant in batch.eligible_participants()
    ):
        raise GameLifecycleError("Sequencing request source candidate authority drift.")


def _loaded_move_reactions(
    bundle: RuntimeContentBundle,
    context: UnitMoveCompletedContext,
) -> tuple[TimingRuleCandidate, ...]:
    from warhammer40k_core.engine.phases.movement_completion_candidates import (
        move_reaction_candidates,
    )

    reactions = move_reaction_candidates(
        context,
        surge_hooks=bundle.movement_end_surge_hook_registry,
        stratagem_index=bundle.stratagem_indexes_by_player_id[context.triggering_player_id],
        cost_modifiers=bundle.stratagem_cost_modifier_registry,
    )
    return (*bundle.move_completion_rule_registry.candidates_for(context), *reactions)


def record_loaded_model_destruction_occurrences(
    *,
    state: GameState,
    decisions: DecisionController,
    runtime_bundle_provider: Callable[[], RuntimeContentBundle],
) -> None:
    from warhammer40k_core.engine.model_destruction_triggers import (
        record_model_destruction_occurrences,
        recorded_model_destruction_occurrences,
    )

    recorded = set(recorded_model_destruction_occurrences(decisions))
    if any(
        trigger.kind is RuleTriggerKind.MODEL_DESTRUCTION and trigger.trigger_id not in recorded
        for trigger in rule_trigger_history(decisions).observed
    ):
        record_model_destruction_occurrences(
            state=state,
            decisions=decisions,
            registry=runtime_bundle_provider().unit_destroyed_hook_registry,
        )
