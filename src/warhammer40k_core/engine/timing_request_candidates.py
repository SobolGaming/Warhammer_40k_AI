from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
    SequencingRequirement,
)
from warhammer40k_core.engine.timing_batch_runtime import timing_batches_for_context
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate


def timing_candidate_for_request(
    *,
    template: DecisionRequest,
    participant_id: str,
    source_rule_id: str,
    requirement: SequencingRequirement,
    next_request_id: Callable[[], str],
    label: str | None = None,
    participant_payload: JsonValue = None,
) -> TimingRuleCandidate:
    """Materialize a pure request template only after its rule has been selected."""
    if template.actor_id is None:
        raise GameLifecycleError("A player rule request requires an owning player.")
    secret = False
    if isinstance(template.payload, dict) and "secret" in template.payload:
        secret_value = template.payload["secret"]
        if type(secret_value) is not bool:
            raise GameLifecycleError("Timing request secrecy must be boolean.")
        secret = secret_value
    return TimingRuleCandidate(
        participant=SequencingParticipant(
            participant_id=participant_id,
            player_id=template.actor_id,
            source_rule_id=source_rule_id,
            requirement=requirement,
            secret=secret,
            label=label,
            payload=participant_payload,
        ),
        activate=lambda: replace(template, request_id=next_request_id()),
        request_template=template,
    )


def selected_timing_request_is_current(
    *,
    decisions: DecisionController,
    context: SequencingConflictContext,
    request: DecisionRequest,
    candidates: tuple[TimingRuleCandidate, ...],
) -> bool:
    batches = timing_batches_for_context(decisions, context)
    if not batches or batches[-1].selected_participant_id is None:
        raise GameLifecycleError("Timing request lacks selected timing authority.")
    selected = batches[-1].selected_participant_id
    current = tuple(
        candidate for candidate in candidates if candidate.participant.participant_id == selected
    )
    if not current:
        return False
    if len(current) != 1:
        raise GameLifecycleError("Timing request has ambiguous timing authority.")
    template = current[0].request_template
    if template is None:
        raise GameLifecycleError("Timing finite request lacks a source template.")
    return replace(template, request_id=request.request_id) == request
