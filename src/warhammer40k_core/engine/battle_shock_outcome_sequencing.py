from __future__ import annotations

from collections.abc import Callable
from functools import partial
from typing import TYPE_CHECKING

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
)
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

if TYPE_CHECKING:
    from warhammer40k_core.engine.battle_shock_hooks import (
        BattleShockHookRegistry,
        BattleShockOutcomeContext,
    )


def outcome_candidate(
    context: BattleShockOutcomeContext,
    *,
    source_rule_id: str,
    owner_player_id: str,
    occurrence_id: str,
    activate: Callable[[], LifecycleStatus | None],
) -> TimingRuleCandidate:
    return TimingRuleCandidate(
        participant=SequencingParticipant(
            participant_id=f"{context.result.result_id}:{occurrence_id}:{owner_player_id}",
            player_id=owner_player_id,
            source_rule_id=source_rule_id,
            requirement=SequencingRequirement.MANDATORY,
            payload={"battle_shock_result_id": context.result.result_id},
        ),
        activate=activate,
    )


def outcome_recorded(
    context: BattleShockOutcomeContext,
    *,
    event_types: tuple[str, ...],
    owner_player_id: str,
    source_rule_id: str,
) -> bool:
    return any(
        event.event_type in event_types
        and isinstance(event.payload, dict)
        and event.payload.get("battle_shock_result_id") == context.result.result_id
        and event.payload.get("player_id") == owner_player_id
        and event.payload.get("source_rule_id") == source_rule_id
        for event in context.decisions.event_log.records
    )


def outcome_timing_context(context: BattleShockOutcomeContext) -> SequencingConflictContext:
    identifier = f"battle-shock-outcome:{context.result.result_id}"
    active = context.state.effective_active_player_id()
    return SequencingConflictContext(
        conflict_id=identifier,
        game_id=context.state.game_id,
        player_ids=context.state.player_ids,
        active_player_id=active,
        timing_window=TimingWindow(
            window_id=identifier,
            game_id=context.state.game_id,
            battle_round=context.result.request.battle_round,
            active_player_id=active,
            phase=context.phase,
            descriptor=TimingWindowDescriptor(
                descriptor_id=f"{identifier}:descriptor",
                source_rule_id=RULES_SEQUENCING_SOURCE_ID,
                trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
                phase=context.phase,
                source_step="battle_shock_outcome",
            ),
        ),
    )


def resolve_outcome_candidates(
    context: BattleShockOutcomeContext,
    registry: BattleShockHookRegistry,
) -> LifecycleStatus | None:
    if context.decisions.queue.pending_requests:
        raise GameLifecycleError("Battle-shock outcome hooks require an empty decision queue.")

    outcome = resolve_timing_rule_candidates(
        decisions=context.decisions,
        context=outcome_timing_context(context),
        discover=partial(outcome_candidates, context, registry),
        next_request_id=context.state.next_decision_request_id,
    )
    if isinstance(outcome, DecisionRequest):
        context.decisions.request_decision(outcome)
        return LifecycleStatus.waiting_for_decision(
            stage=context.state.stage,
            decision_request=outcome,
            payload={
                "phase": context.phase.value,
                "phase_body_status": "battle_shock_outcome_order_pending",
            },
        )
    if (
        outcome is not None
        and outcome.decision_request is not None
        and (
            len(context.decisions.queue.pending_requests) != 1
            or outcome.decision_request != context.decisions.queue.pending_requests[0]
        )
    ):
        raise GameLifecycleError("Battle-shock outcome status must identify its pending decision.")
    return outcome


def outcome_candidates(
    context: BattleShockOutcomeContext,
    registry: BattleShockHookRegistry,
) -> tuple[TimingRuleCandidate, ...]:
    before = (context.state.to_payload(), context.decisions.to_payload())
    candidates: list[TimingRuleCandidate] = []
    for binding in registry.bindings:
        if binding.outcome_handler is None:
            continue
        if binding.outcome_candidate_handler is None:
            raise GameLifecycleError("Battle-shock outcome requires source candidate discovery.")
        found = binding.outcome_candidate_handler(context)
        if type(found) is not tuple or any(type(item) is not TimingRuleCandidate for item in found):
            raise GameLifecycleError("Battle-shock outcome candidates must be typed.")
        candidates.extend(found)
    if before != (context.state.to_payload(), context.decisions.to_payload()):
        raise GameLifecycleError("Battle-shock outcome discovery mutated authoritative state.")
    return tuple(candidates)
