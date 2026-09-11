from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.core.ruleset_descriptor import battle_phase_kind_from_token
from warhammer40k_core.engine.attack_sequence_completion_hooks import AttackSequenceCompletedContext
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingConflictContext
from warhammer40k_core.engine.timing_rule_candidates import (
    TimingRuleCandidate,
    resolve_timing_rule_candidates,
)
from warhammer40k_core.engine.timing_windows import (
    TimingTriggerKind,
    TimingWindow,
    TimingWindowDescriptor,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_sequencing_2026_09 import (
    RULES_SEQUENCING_SOURCE_ID,
)


def attack_completion_timing_context(
    context: AttackSequenceCompletedContext,
) -> SequencingConflictContext:
    identifier = (
        f"attack-completion:{context.attack_sequence_completed_event_id}:"
        f"{context.attack_sequence.sequence_id}"
    )
    state = context.state
    active = state.effective_active_player_id()
    if active is None:
        raise GameLifecycleError("Attack completion requires active-player authority.")
    phase = battle_phase_kind_from_token(context.source_phase.value)
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=state.game_id,
        player_ids=state.player_ids,
        active_player_id=active,
        timing_window=TimingWindow(
            window_id=identifier,
            game_id=state.game_id,
            battle_round=state.battle_round,
            active_player_id=active,
            phase=phase,
            trigger_event_id=context.attack_sequence_completed_event_id,
            descriptor=TimingWindowDescriptor(
                descriptor_id="attack-completion-sequencing",
                trigger_kind=TimingTriggerKind.AFTER_UNIT_ATTACKS_RESOLVED,
                source_rule_id=RULES_SEQUENCING_SOURCE_ID,
                phase=phase,
                source_step="attack_sequence_completed",
            ),
        ),
    )


def resolve_attack_completion_candidates_now(
    context: AttackSequenceCompletedContext,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> LifecycleStatus | None:
    outcome = resolve_timing_rule_candidates(
        decisions=context.decisions,
        context=attack_completion_timing_context(context),
        discover=discover,
        next_request_id=context.state.next_decision_request_id,
    )
    if isinstance(outcome, DecisionRequest):
        context.decisions.request_decision(outcome)
        context.decisions.event_log.append(
            "attack_sequence_completion_order_requested",
            {
                "game_id": context.state.game_id,
                "attack_sequence_id": context.attack_sequence.sequence_id,
                "attack_sequence_completed_event_id": context.attack_sequence_completed_event_id,
                "request_id": outcome.request_id,
            },
        )
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage,
            decision_request=outcome,
            payload={
                "phase": context.source_phase.value,
                "phase_body_status": "attack_completion_order_pending",
            },
        )
    return outcome


def resolve_attack_completion_candidates(
    context: AttackSequenceCompletedContext,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.attack_completion_triggers import observe_attack_completion

    return observe_attack_completion(context, discover)
