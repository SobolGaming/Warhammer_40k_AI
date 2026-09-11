from __future__ import annotations

from collections.abc import Callable
from typing import cast

from warhammer40k_core.engine.attack_sequence import AttackSequence, AttackSequencePayload
from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)
from warhammer40k_core.engine.rule_trigger_state import (
    RuleTrigger,
    RuleTriggerKind,
    complete_rule_trigger,
    observe_rule_trigger,
    release_rule_trigger,
)
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def observe_attack_completion(
    context: AttackSequenceCompletedContext,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> LifecycleStatus | None:
    trigger = observe_rule_trigger(
        decisions=context.decisions,
        kind=RuleTriggerKind.ATTACK_COMPLETION,
        context=validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.state.battle_round,
                "phase": context.state.current_battle_phase.value
                if context.state.current_battle_phase is not None
                else None,
                "source_phase": context.source_phase.value,
                "trigger_event_id": context.attack_sequence_completed_event_id,
                "attack_sequence": context.attack_sequence.to_payload(),
            }
        ),
    )
    return resolve_attack_trigger(context=context, trigger=trigger, discover=discover)


def attack_context_for_trigger(
    *,
    state: GameState,
    decisions: DecisionController,
    trigger: RuleTrigger,
    runtime_modifiers: RuntimeModifierRegistry,
) -> AttackSequenceCompletedContext:
    payload = trigger.context
    if (
        trigger.kind is not RuleTriggerKind.ATTACK_COMPLETION
        or not isinstance(payload, dict)
        or set(payload)
        != {
            "game_id",
            "battle_round",
            "phase",
            "source_phase",
            "trigger_event_id",
            "attack_sequence",
        }
    ):
        raise GameLifecycleError("Attack completion trigger context schema drift.")
    if (
        not isinstance(payload["attack_sequence"], dict)
        or type(payload["source_phase"]) is not str
        or type(payload["trigger_event_id"]) is not str
    ):
        raise GameLifecycleError("Attack completion trigger context fields are malformed.")
    sequence = AttackSequence.from_payload(cast(AttackSequencePayload, payload["attack_sequence"]))
    from warhammer40k_core.engine.attack_completion_authority import completed_attack_sequence

    if sequence != completed_attack_sequence(
        event_records=decisions.event_log.records, sequence_id=sequence.sequence_id
    ):
        raise GameLifecycleError("Attack completion trigger executor state drift.")
    try:
        phase = BattlePhase(payload["source_phase"])
    except ValueError as error:
        raise GameLifecycleError("Attack completion trigger phase is invalid.") from error
    source = tuple(
        event
        for event in decisions.event_log.records
        if event.event_id == payload["trigger_event_id"]
    )
    if (
        len(source) != 1
        or source[0].event_type != "attack_sequence_completed"
        or source[0].payload
        != {
            "sequence_id": sequence.sequence_id,
            "attacker_player_id": sequence.attacker_player_id,
            "attacking_unit_instance_id": sequence.attacking_unit_instance_id,
        }
    ):
        raise GameLifecycleError("Attack completion trigger source authority drift.")
    participation = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "attack_sequence_models_attacked"
        and isinstance(event.payload, dict)
        and event.payload.get("sequence_id") == sequence.sequence_id
    )
    if len(participation) != 1 or not isinstance(participation[0].payload, dict):
        raise GameLifecycleError("Attack completion trigger lacks model participation authority.")
    evidence = participation[0].payload
    if (
        payload["game_id"] != state.game_id
        or evidence.get("game_id") != state.game_id
        or evidence.get("battle_round") != payload["battle_round"]
        or evidence.get("phase") != payload["phase"]
        or evidence.get("attack_phase") != phase.value
    ):
        raise GameLifecycleError("Attack completion trigger boundary context drift.")
    return AttackSequenceCompletedContext(
        state=state,
        decisions=decisions,
        dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        runtime_modifier_registry=runtime_modifiers,
        source_phase=phase,
        attack_sequence=sequence,
        attack_sequence_completed_event_id=payload["trigger_event_id"],
    )


def resolve_attack_trigger(
    *,
    context: AttackSequenceCompletedContext,
    trigger: RuleTrigger,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_completion_sequencing import (
        resolve_attack_completion_candidates_now,
    )

    attack_context_for_trigger(
        state=context.state,
        decisions=context.decisions,
        trigger=trigger,
        runtime_modifiers=context.runtime_modifier_registry,
    )
    if not release_rule_trigger(decisions=context.decisions, trigger=trigger):
        from warhammer40k_core.engine.rule_trigger_state import unreleased_rule_trigger_status

        return unreleased_rule_trigger_status(
            decisions=context.decisions, trigger=trigger, stage=context.state.stage
        )
    payload = trigger.context
    if (
        not isinstance(payload, dict)
        or context.state.current_battle_phase is None
        or payload["battle_round"] != context.state.battle_round
        or payload["phase"] != context.state.current_battle_phase.value
    ):
        raise GameLifecycleError("Attack completion trigger escaped its source timing window.")
    status = resolve_attack_completion_candidates_now(context, discover)
    from warhammer40k_core.engine.attack_completion_sequencing import (
        attack_completion_timing_context,
    )
    from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context

    batches = timing_batches_for_context(
        context.decisions, attack_completion_timing_context(context)
    )
    if status is None or (
        status.status_kind is LifecycleStatusKind.ADVANCED
        and batches
        and batches[-1].current_batch_complete
    ):
        complete_rule_trigger(decisions=context.decisions, trigger=trigger)
    return status
