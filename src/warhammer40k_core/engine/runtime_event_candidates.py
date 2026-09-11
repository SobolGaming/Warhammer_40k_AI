from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.faction_content.events import (
    RuntimeContentEventContext,
    RuntimeContentEventResult,
    RuntimeContentEventSubscription,
    RuntimeEventHandler,
    RuntimeEventStatus,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def runtime_event_candidate(
    context: RuntimeContentEventContext,
    subscription: RuntimeContentEventSubscription,
    *,
    occurrence_id: str,
    requirement: SequencingRequirement,
    handler: RuntimeEventHandler,
    source_payload: JsonValue = None,
) -> TimingRuleCandidate | None:
    identifier = f"{context.event.event_id}:{subscription.subscription_id}:{occurrence_id}"
    if any(
        event.event_type == "runtime_content_event_resolved"
        and isinstance(event.payload, dict)
        and event.payload.get("timing_participant_id") == identifier
        for event in context.decisions.event_log.records
    ):
        return None
    return TimingRuleCandidate(
        participant=SequencingParticipant(
            participant_id=identifier,
            player_id=context.event.player_id,
            source_rule_id=subscription.source_rule_id,
            requirement=requirement,
            payload={
                "runtime_event_id": context.event.event_id,
                "subscription_id": subscription.subscription_id,
                "handler_id": subscription.handler_id,
                "source_occurrence": source_payload,
            },
        ),
        activate=partial(_activate, context, subscription, identifier, handler),
    )


def _activate(
    context: RuntimeContentEventContext,
    subscription: RuntimeContentEventSubscription,
    identifier: str,
    handler: RuntimeEventHandler,
) -> LifecycleStatus | None:
    if context.decisions.queue.pending_requests:
        raise GameLifecycleError("Runtime timing activation requires an empty decision queue.")
    result = handler(context)
    if type(result) is not RuntimeContentEventResult or (
        result.subscription_id != subscription.subscription_id
        or result.source_rule_id != subscription.source_rule_id
    ):
        raise GameLifecycleError("Runtime timing activation source identity drift.")
    if result.status is not RuntimeEventStatus.APPLIED:
        raise GameLifecycleError(f"Selected runtime timing rule cannot resolve: {result.reason}.")
    context.decisions.event_log.append(
        "runtime_content_event_resolved",
        validate_json_value(
            {
                "game_id": context.state.game_id,
                "battle_round": context.event.battle_round,
                "player_id": context.event.player_id,
                "trigger_kind": context.event.trigger_kind.value,
                "runtime_event": context.event.to_payload(),
                "result": result.to_payload(),
                "timing_participant_id": identifier,
            }
        ),
    )
    requests = context.decisions.queue.pending_requests
    if not requests:
        return None
    if len(requests) != 1:
        raise GameLifecycleError("One selected runtime rule emitted multiple pending requests.")
    return LifecycleStatus.waiting_for_decision(
        stage=context.state.stage,
        decision_request=requests[0],
        payload={"phase_body_status": "runtime_timing_rule_pending"},
    )
