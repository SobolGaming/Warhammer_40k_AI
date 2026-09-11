from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING

import msgspec

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.phase import GameLifecycleError, GameLifecycleStage, LifecycleStatus
from warhammer40k_core.engine.sequencing import SequencingConflictContext, SequencingParticipant
from warhammer40k_core.engine.timing_batch_runtime import (
    select_timing_participant,
    timing_batches_for_context,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def rule_discovery_snapshot(state: GameState, decisions: DecisionController) -> object:
    """Copy all domain fields without revalidating every retained replay artifact."""
    return msgspec.to_builtins(
        (state, decisions.queue.pending_requests, decisions.records, decisions.event_log.records)
    )


@dataclass(frozen=True, slots=True)
class TimingRuleCandidate:
    """A discovered source occurrence and its engine-owned activation continuation."""

    participant: SequencingParticipant
    activate: Callable[[], DecisionRequest | LifecycleStatus | None]
    request_template: DecisionRequest | None = None

    def __post_init__(self) -> None:
        if type(self.participant) is not SequencingParticipant or not callable(self.activate):
            raise GameLifecycleError("Timing rule requires a participant and an activation.")
        if self.request_template is not None:
            if type(self.request_template) is not DecisionRequest:
                raise GameLifecycleError("Timing rule request template must be DecisionRequest.")
            if self.request_template.actor_id != self.participant.player_id:
                raise GameLifecycleError("Timing rule request template owner drift.")


def resolve_timing_rule_candidates(
    *,
    decisions: DecisionController,
    context: SequencingConflictContext,
    discover: Callable[[], tuple[TimingRuleCandidate, ...]],
    next_request_id: Callable[[], str],
) -> DecisionRequest | LifecycleStatus | None:
    """Discover without activation; finish each chosen rule before choosing another."""
    completed_participant_id: str | None = None
    while True:
        candidates = discover()
        selection = select_timing_participant(
            decisions=decisions,
            context=context,
            unresolved_participants=tuple(candidate.participant for candidate in candidates),
            next_request_id=next_request_id,
            completed_participant_id=completed_participant_id,
        )
        if selection.request is not None:
            return selection.request
        if selection.participant_id is None:
            from warhammer40k_core.engine.rule_trigger_state import rule_trigger_history

            own_batches = {
                batch.batch_id for batch in timing_batches_for_context(decisions, context)
            }
            if any(
                trigger.parent_batch_id in own_batches
                for trigger in rule_trigger_history(decisions).ready()
            ):
                return LifecycleStatus.advanced(
                    stage=GameLifecycleStage.BATTLE,
                    payload={
                        "phase_body_status": "deferred_rules_ready",
                        "conflict_id": context.conflict_id,
                    },
                )
            return None
        candidate = next(
            item
            for item in candidates
            if item.participant.participant_id == selection.participant_id
        )
        continuation = candidate.activate()
        if continuation is not None:
            if type(continuation) not in (DecisionRequest, LifecycleStatus):
                raise GameLifecycleError("Timing activation returned an invalid continuation.")
            return continuation
        completed_participant_id = selection.participant_id
