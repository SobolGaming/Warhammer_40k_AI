from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.decision_record import DecisionRecord, DecisionRecordPayload
from warhammer40k_core.engine.decision_request import DecisionRequestPayload
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_mutation_decision_closure(
    *,
    event_records: tuple[EventRecord, ...],
    decision_records: tuple[DecisionRecord, ...],
    mutation_index: int,
    request_id: str,
    result_id: str,
) -> DecisionRecord:
    """Require one exact request, recorded result, and ledger row before mutation."""
    records = authoritative_decision_records(decision_records)
    matches = tuple(
        record
        for record in records
        if record.request.request_id == request_id
        and record.result.request_id == request_id
        and record.result.result_id == result_id
    )
    if len(matches) != 1:
        raise GameLifecycleError("Mutation decision authority drifted.")
    record = matches[0]
    validate_record_event_closure(
        event_records=event_records,
        mutation_index=mutation_index,
        record=record,
    )
    return record


def decision_event_payload_matches(
    event_payload: JsonValue, ledger_payload: DecisionRecordPayload | DecisionRequestPayload
) -> bool:
    """Compare an event with its ledger payload, including the JSON scalar types."""
    return event_payload == ledger_payload and canonical_json(event_payload) == canonical_json(
        ledger_payload
    )


def validate_record_event_closure(
    *,
    event_records: tuple[EventRecord, ...],
    mutation_index: int,
    record: DecisionRecord,
) -> None:
    prior = event_records[:mutation_index]
    record_payload = record.to_payload()
    recorded = tuple(
        (index, event)
        for index, event in enumerate(prior)
        if event.event_type == "decision_recorded"
        and decision_event_payload_matches(event.payload, record_payload)
    )
    if len(recorded) != 1:
        raise GameLifecycleError("Mutation lacks its exact decision ledger event.")
    record_index, _record_event = recorded[0]
    request_payload = record_payload["request"]
    requested = tuple(
        event
        for event in prior[:record_index]
        if event.event_type == "decision_requested"
        and decision_event_payload_matches(event.payload, request_payload)
    )
    if len(requested) != 1:
        raise GameLifecycleError("Mutation lacks its exact decision request event.")


def authoritative_decision_records(value: object) -> tuple[DecisionRecord, ...]:
    if type(value) is not tuple or any(
        type(record) is not DecisionRecord for record in cast(tuple[object, ...], value)
    ):
        raise GameLifecycleError("Mutation decision ledger is invalid.")
    return cast(tuple[DecisionRecord, ...], value)


__all__ = (
    "authoritative_decision_records",
    "decision_event_payload_matches",
    "validate_mutation_decision_closure",
    "validate_record_event_closure",
)
