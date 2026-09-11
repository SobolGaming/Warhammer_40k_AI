from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SequencingConflictContext,
    SequencingParticipant,
)
from warhammer40k_core.engine.timing_batch_decisions import (
    recorded_timing_selection,
    request_for_timing_batch,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch, TimingBatchPayload

TIMING_BATCH_EVENT_TYPE = "timing_batch_transition"


@dataclass(frozen=True, slots=True)
class TimingParticipantSelection:
    participant_id: str | None
    request: DecisionRequest | None

    def __post_init__(self) -> None:
        if self.participant_id is not None and self.request is not None:
            raise GameLifecycleError("Timing selection cannot select and request simultaneously.")


def _record_batch(decisions: DecisionController, batch: TimingBatch, *, transition: str) -> None:
    decisions.event_log.append(
        TIMING_BATCH_EVENT_TYPE,
        validate_json_value({"transition": transition, "batch": batch.to_payload()}),
    )


def timing_batches_for_context(
    decisions: DecisionController, context: SequencingConflictContext
) -> tuple[TimingBatch, ...]:
    return timing_batches_from_records(
        events=decisions.event_log.records,
        records=decisions.records,
        context=context,
    )


def timing_batches_from_records(
    *,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
    context: SequencingConflictContext,
) -> tuple[TimingBatch, ...]:
    batches: dict[int, TimingBatch] = {}
    for event_index, event in enumerate(events):
        if event.event_type != TIMING_BATCH_EVENT_TYPE:
            continue
        batch = timing_batch_from_event(event)
        if batch.context.conflict_id != context.conflict_id:
            continue
        if batch.context != context:
            raise GameLifecycleError("Timing batch trigger authority drifted.")
        validate_timing_batch_transition(
            batch=batch,
            event=event,
            event_index=event_index,
            batches=batches,
            events=events,
            records=records,
        )
        batches[batch.generation] = batch
    return tuple(batches[index] for index in sorted(batches))


def timing_batch_from_event(event: EventRecord) -> TimingBatch:
    payload = event.payload
    if (
        event.event_type != TIMING_BATCH_EVENT_TYPE
        or not isinstance(payload, dict)
        or set(payload) != {"transition", "batch"}
        or not isinstance(payload["batch"], dict)
    ):
        raise GameLifecycleError("Timing batch event must contain its exact transition and batch.")
    return TimingBatch.from_payload(cast(TimingBatchPayload, payload["batch"]))


def validate_timing_batch_transition(
    *,
    batch: TimingBatch,
    event: EventRecord,
    event_index: int,
    batches: dict[int, TimingBatch],
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
) -> None:
    if not isinstance(event.payload, dict):
        raise GameLifecycleError("Timing batch transition requires an object payload.")
    previous = batches.get(batch.generation)
    transition = event.payload["transition"]
    _validate_transition(previous, batch, transition, batches)
    if previous is not None and transition == "selected":
        choice = recorded_timing_selection(
            previous,
            events=events[:event_index],
            records=records,
        )
        if len(previous.eligible_participants()) > 1 and (
            choice is None or choice.selected_participant_id != batch.selected_participant_id
        ):
            raise GameLifecycleError("Timing rule order requires the owner's recorded choice.")


def _validate_transition(
    previous: TimingBatch | None,
    batch: TimingBatch,
    transition: JsonValue,
    batches: dict[int, TimingBatch],
) -> None:
    expected: TimingBatch | None
    if previous is None:
        if transition == "opened" and not batches:
            expected = TimingBatch.open(context=batch.context, participants=batch.participants)
        elif transition == "released" and batch.generation - 1 in batches:
            expected = batches[batch.generation - 1].release_deferred()
        else:
            raise GameLifecycleError("Timing batch has no authoritative opening transition.")
    elif transition == "selected" and batch.selected_participant_id is not None:
        expected = previous.select(batch.selected_participant_id)
    elif transition == "completed" and previous.selected_participant_id is not None:
        expected = previous.complete(previous.selected_participant_id)
    elif transition == "ineligible" and previous.selected_participant_id is None:
        if len(batch.completed_participant_ids) != len(previous.completed_participant_ids) + 1:
            raise GameLifecycleError("Timing ineligibility must dispose of exactly one rule.")
        identifier = batch.completed_participant_ids[-1]
        expected = previous.select(identifier).complete(identifier)
    elif transition == "deferred":
        old_count = len(previous.deferred_participants)
        expected = previous.defer(batch.deferred_participants[old_count:])
    else:
        raise GameLifecycleError("Timing batch transition is not permitted.")
    if batch != expected:
        raise GameLifecycleError("Timing batch transition authority drifted.")


def select_timing_participant(
    *,
    decisions: DecisionController,
    context: SequencingConflictContext,
    unresolved_participants: tuple[SequencingParticipant, ...],
    next_request_id: Callable[[], str],
    completed_participant_id: str | None = None,
) -> TimingParticipantSelection:
    """Choose within a fixed population; the caller still owns rule validation and execution.

    A caller supplies unresolved source-backed candidates after completing any
    internal continuation. Disappearance makes an unselected rule ineligible;
    new identities are retained in the next generation, never the current tier.
    """
    history = timing_batches_for_context(decisions, context)
    if not history:
        if not unresolved_participants:
            return TimingParticipantSelection(None, None)
        batch = TimingBatch.open(context=context, participants=unresolved_participants)
        _record_batch(decisions, batch, transition="opened")
        history = (batch,)
    batch = history[-1]
    known = {
        participant.participant_id: participant
        for retained in history
        for participant in (*retained.participants, *retained.deferred_participants)
    }
    current = {participant.participant_id: participant for participant in unresolved_participants}
    if len(current) != len(unresolved_participants):
        raise GameLifecycleError("Timing candidates duplicate participant identities.")
    for identifier, participant in current.items():
        if identifier in known and known[identifier] != participant:
            raise GameLifecycleError("Timing participant source or owner authority drifted.")
    new = tuple(
        participant
        for participant in unresolved_participants
        if participant.participant_id not in known
    )
    if new:
        if batch.current_batch_complete:
            # A subsequent call can discover a fresh timing population after the
            # previous population completed; preserve the same generation chain.
            raise GameLifecycleError(
                "New timing rules require observation before batch completion."
            )
        batch = batch.defer(new)
        _record_batch(decisions, batch, transition="deferred")
    if batch.selected_participant_id is not None:
        if (
            completed_participant_id is not None
            and completed_participant_id != batch.selected_participant_id
        ):
            raise GameLifecycleError("Timing completion does not match the active rule.")
        if completed_participant_id is None and batch.selected_participant_id in current:
            return TimingParticipantSelection(batch.selected_participant_id, None)
        batch = batch.complete(batch.selected_participant_id)
        _record_batch(decisions, batch, transition="completed")
    elif completed_participant_id is not None:
        raise GameLifecycleError("Timing completion has no selected rule.")
    while True:
        if batch.current_batch_complete:
            released = batch.release_deferred()
            if released is None:
                return TimingParticipantSelection(None, None)
            batch = released
            _record_batch(decisions, batch, transition="released")
        eligible = batch.eligible_participants()
        missing = tuple(
            participant for participant in eligible if participant.participant_id not in current
        )
        if missing:
            batch = batch.select(missing[0].participant_id)
            batch = batch.complete(missing[0].participant_id)
            _record_batch(decisions, batch, transition="ineligible")
            continue
        choice = recorded_timing_selection(
            batch,
            events=decisions.event_log.records,
            records=decisions.records,
        )
        if choice is not None:
            identifier = choice.selected_participant_id
        elif len(eligible) == 1:
            identifier = eligible[0].participant_id
        else:
            request = request_for_timing_batch(batch, request_id=next_request_id())
            return TimingParticipantSelection(None, request)
        batch = batch.select(identifier)
        _record_batch(decisions, batch, transition="selected")
        return TimingParticipantSelection(identifier, None)


def complete_timing_participant(
    *,
    decisions: DecisionController,
    context: SequencingConflictContext,
    participant_id: str,
) -> None:
    history = timing_batches_for_context(decisions, context)
    if not history:
        raise GameLifecycleError("Cannot complete a rule without a timing batch.")
    _record_batch(decisions, history[-1].complete(participant_id), transition="completed")
