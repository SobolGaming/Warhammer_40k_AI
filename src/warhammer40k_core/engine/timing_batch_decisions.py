from __future__ import annotations

from dataclasses import replace
from typing import cast

from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecord
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.sequencing import (
    SequencingNextParticipantDecision,
    SequencingNextParticipantDecisionPayload,
    apply_select_next_sequencing_participant_from_request,
    create_select_next_sequencing_participant_request,
    sequencing_tier,
)
from warhammer40k_core.engine.timing_batch_state import TimingBatch


def request_for_timing_batch(batch: TimingBatch, *, request_id: str) -> DecisionRequest:
    if batch.selected_participant_id is not None or batch.current_batch_complete:
        raise GameLifecycleError("Timing batch has no pending sequencing choice.")
    eligible = batch.eligible_participants()
    tier = sequencing_tier(eligible[0], context=batch.context)
    tier_ids = {
        participant.participant_id
        for participant in batch.participants
        if sequencing_tier(participant, context=batch.context) == tier
    }
    return create_select_next_sequencing_participant_request(
        request_id=request_id,
        context=replace(batch.context, conflict_id=f"{batch.batch_id}:tier-{tier}"),
        previously_selected_participant_ids=tuple(
            identifier for identifier in batch.completed_participant_ids if identifier in tier_ids
        ),
        remaining_participants=eligible,
    )


def recorded_timing_selection(
    batch: TimingBatch,
    *,
    events: tuple[EventRecord, ...],
    records: tuple[DecisionRecord, ...],
) -> SequencingNextParticipantDecision | None:
    if any(
        event.event_type == "sequencing_next_participant_selected"
        and not isinstance(event.payload, dict)
        for event in events
    ):
        raise GameLifecycleError("Timing sequencing payload is malformed.")
    expected_context = request_for_timing_batch(batch, request_id="timing-authority-template")
    expected_payload = expected_context.payload
    if not isinstance(expected_payload, dict):
        raise GameLifecycleError("Timing authority requires an object payload.")
    conflict = expected_payload["sequencing_conflict"]
    if not isinstance(conflict, dict):
        raise GameLifecycleError("Timing authority requires a conflict object.")
    choices = tuple(
        SequencingNextParticipantDecision.from_payload(
            cast(SequencingNextParticipantDecisionPayload, event.payload)
        )
        for event in events
        if event.event_type == "sequencing_next_participant_selected"
        and isinstance(event.payload, dict)
        and event.payload.get("conflict_id") == conflict["conflict_id"]
        and event.payload.get("previously_selected_participant_ids")
        == expected_payload["previously_selected_participant_ids"]
    )
    if not choices:
        return None
    if len(choices) != 1:
        raise GameLifecycleError("Timing prefix has duplicate ordering decisions.")
    choice = choices[0]
    matching_records = tuple(
        record for record in records if record.request.request_id == choice.request_id
    )
    if len(matching_records) != 1:
        raise GameLifecycleError("Timing selection lacks its unique decision record.")
    record = matching_records[0]
    expected = request_for_timing_batch(batch, request_id=choice.request_id)
    if record.request != expected:
        raise GameLifecycleError("Timing selection request authority drifted.")
    if choice != apply_select_next_sequencing_participant_from_request(
        request=record.request,
        result=record.result,
    ):
        raise GameLifecycleError("Timing selection result authority drifted.")
    requested = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "decision_requested" and event.payload == record.request.to_payload()
    )
    recorded = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "decision_recorded" and event.payload == record.to_payload()
    )
    resolved = tuple(
        index
        for index, event in enumerate(events)
        if event.event_type == "sequencing_next_participant_selected"
        and event.payload == choice.to_payload()
    )
    if not (
        len(requested) == len(recorded) == len(resolved) == 1
        and requested[0] < recorded[0] < resolved[0]
    ):
        raise GameLifecycleError("Timing selection event lineage drifted.")
    return choice
