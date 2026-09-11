from __future__ import annotations

from functools import partial

from warhammer40k_core.engine.catalog_return_on_death_runtime import record_pending_return_on_death
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.return_on_death import (
    PendingReturnOnDeath,
    resolve_return_on_death_occurrence,
)
from warhammer40k_core.engine.sequencing import SequencingParticipant, SequencingRequirement
from warhammer40k_core.engine.timing_rule_candidates import TimingRuleCandidate
from warhammer40k_core.engine.turn_end_hooks import TurnEndRequestContext


def candidates_for_captures(
    context: TurnEndRequestContext,
    captures: tuple[tuple[str, PendingReturnOnDeath], ...],
) -> tuple[TimingRuleCandidate, ...]:
    return tuple(
        TimingRuleCandidate(
            participant=SequencingParticipant(
                participant_id=f"return-on-death:{pending.pending_id}",
                source_rule_id=pending.source_rule_id,
                player_id=pending.owner_player_id,
                requirement=SequencingRequirement.MANDATORY,
                payload={"pending_id": pending.pending_id},
            ),
            activate=partial(_activate_capture, context, event_id, pending),
        )
        for event_id, pending in captures
    )


def _activate_capture(
    context: TurnEndRequestContext,
    event_id: str,
    pending: PendingReturnOnDeath,
) -> DecisionRequest | None:
    if not record_pending_return_on_death(
        pending=pending,
        event_log=context.decisions.event_log,
        state=context.state,
        phase=context.completed_phase.value,
        model_destroyed_event_id=event_id,
    ):
        raise GameLifecycleError("Selected return-on-death capture was already consumed.")
    return resolve_return_on_death_occurrence(
        state=context.state,
        decisions=context.decisions,
        pending=pending,
    )
