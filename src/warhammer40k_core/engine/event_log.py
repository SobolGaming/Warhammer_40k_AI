from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class EventLogError(ValueError):
    """Raised when an event record is not deterministic and serializable."""


class EventRecordPayload(TypedDict):
    event_id: str
    event_type: str
    payload: JsonValue


_MEMORY_REPR = re.compile(r"<[^>]+ object at 0x[0-9a-fA-F]+>")


def _new_event_records() -> list[EventRecord]:
    return []


@dataclass(frozen=True, slots=True)
class EventRecord:
    event_id: str
    event_type: str
    payload: JsonValue

    def __post_init__(self) -> None:
        if not self.event_id.strip():
            raise EventLogError("EventRecord event_id must not be empty.")
        if not self.event_type.strip():
            raise EventLogError("EventRecord event_type must not be empty.")
        object.__setattr__(self, "payload", validate_json_value(self.payload))

    def history_token(self) -> str:
        return canonical_json(self.to_payload())

    def to_payload(self) -> EventRecordPayload:
        return {
            "event_id": self.event_id,
            "event_type": self.event_type,
            "payload": self.payload,
        }

    @classmethod
    def from_payload(cls, payload: EventRecordPayload) -> Self:
        return cls(
            event_id=payload["event_id"],
            event_type=payload["event_type"],
            payload=payload["payload"],
        )


@dataclass(slots=True)
class EventLog:
    _records: list[EventRecord] = field(default_factory=_new_event_records)

    @property
    def records(self) -> tuple[EventRecord, ...]:
        return tuple(self._records)

    def append(self, event_type: str, payload: object) -> EventRecord:
        record = EventRecord(
            event_id=f"event-{len(self._records) + 1:06d}",
            event_type=event_type,
            payload=validate_json_value(payload),
        )
        self._records.append(record)
        return record

    def mark_secret_suffix(
        self,
        *,
        start_index: int,
        player_id: str,
        visibility_source: str,
    ) -> tuple[EventRecord, ...]:
        """Mark only a newly appended player-owned event suffix as secret."""
        if type(start_index) is not int or start_index < 0 or start_index > len(self._records):
            raise EventLogError("Secret event suffix start index is invalid.")
        if type(player_id) is not str or not player_id.strip():
            raise EventLogError("Secret event suffix player_id is invalid.")
        if type(visibility_source) is not str or not visibility_source.strip():
            raise EventLogError("Secret event suffix visibility_source is invalid.")
        marked: list[EventRecord] = []
        for index in range(start_index, len(self._records)):
            record = self._records[index]
            if not isinstance(record.payload, dict):
                raise EventLogError("Secret event suffix payload must be an object.")
            secret = record.payload.get("secret")
            if secret is not None and secret is not True:
                raise EventLogError("Secret event suffix contains conflicting visibility metadata.")
            existing_player = record.payload.get("player_id")
            if existing_player is not None and existing_player != player_id:
                raise EventLogError("Secret event suffix contains conflicting visibility metadata.")
            existing_source = record.payload.get("visibility_source")
            if existing_source is not None and existing_source != visibility_source:
                raise EventLogError("Secret event suffix contains conflicting visibility metadata.")
            updated = EventRecord(
                event_id=record.event_id,
                event_type=record.event_type,
                payload={
                    **record.payload,
                    "secret": True,
                    "player_id": player_id,
                    "visibility_source": visibility_source,
                },
            )
            self._records[index] = updated
            marked.append(updated)
        return tuple(marked)

    def to_payload(self) -> list[EventRecordPayload]:
        return [record.to_payload() for record in self._records]

    @classmethod
    def from_payload(cls, payload: list[EventRecordPayload]) -> Self:
        event_log = cls()
        for expected_index, record_payload in enumerate(payload, start=1):
            record = EventRecord.from_payload(record_payload)
            expected_event_id = f"event-{expected_index:06d}"
            if record.event_id != expected_event_id:
                raise EventLogError("EventLog payload contains non-sequential event IDs.")
            event_log._records.append(record)
        return event_log

    def replace_records(self, records: tuple[EventRecord, ...]) -> None:
        """Restore an exact sequential event suffix after a transactional rollback."""
        if type(records) is not tuple or any(type(record) is not EventRecord for record in records):
            raise EventLogError("EventLog replace_records requires typed EventRecord values.")
        rebuilt: list[EventRecord] = []
        for expected_index, record in enumerate(records, start=1):
            expected_event_id = f"event-{expected_index:06d}"
            if record.event_id != expected_event_id:
                raise EventLogError("EventLog replacement contains non-sequential event IDs.")
            rebuilt.append(record)
        self._records = rebuilt


def canonical_json(value: object) -> str:
    return json.dumps(
        validate_json_value(value),
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    )


def validate_json_value(value: object) -> JsonValue:
    if value is None:
        return None
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not math.isfinite(value):
            raise EventLogError("JSON payload floats must be finite.")
        return value
    if isinstance(value, str):
        if _MEMORY_REPR.search(value):
            raise EventLogError("JSON payload must not contain Python object reprs.")
        return value
    if isinstance(value, list):
        list_value = cast(list[object], value)
        return [validate_json_value(item) for item in list_value]
    if isinstance(value, tuple):
        tuple_value = cast(tuple[object, ...], value)
        return [validate_json_value(item) for item in tuple_value]
    if isinstance(value, dict):
        dict_value = cast(dict[object, object], value)
        validated: dict[str, JsonValue] = {}
        for key, item in dict_value.items():
            if not isinstance(key, str):
                raise EventLogError("JSON payload dictionary keys must be strings.")
            if _MEMORY_REPR.search(key):
                raise EventLogError("JSON payload keys must not contain Python object reprs.")
            validated[key] = validate_json_value(item)
        return validated
    raise EventLogError("Event payloads must contain only deterministic JSON values.")
