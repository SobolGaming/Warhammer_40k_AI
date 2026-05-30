from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from warhammer40k_core.engine.event_log import EventLog, EventRecordPayload
from warhammer40k_core.engine.phase import GameLifecycleError


class EventStreamDeltaPayload(TypedDict):
    cursor: int
    next_cursor: int
    events: list[EventRecordPayload]


@dataclass(frozen=True, slots=True)
class EventStreamCursor:
    value: int = 0

    def __post_init__(self) -> None:
        if type(self.value) is not int:
            raise GameLifecycleError("EventStreamCursor value must be an integer.")
        if self.value < 0:
            raise GameLifecycleError("EventStreamCursor value must not be negative.")

    def events_since(self, event_log: EventLog) -> EventStreamDeltaPayload:
        if type(event_log) is not EventLog:
            raise GameLifecycleError("EventStreamCursor requires an EventLog.")
        records = event_log.records
        if self.value > len(records):
            raise GameLifecycleError("EventStreamCursor is ahead of the event log.")
        events = [record.to_payload() for record in records[self.value :]]
        return {
            "cursor": self.value,
            "next_cursor": len(records),
            "events": events,
        }
