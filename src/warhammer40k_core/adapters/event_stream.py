from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.redaction import public_event_record_payload
from warhammer40k_core.engine.event_log import EventLog, EventRecordPayload
from warhammer40k_core.engine.phase import GameLifecycleError

ADAPTER_EVENT_STREAM_DELTA_SCHEMA_VERSION = "event-delta-v1"


class EventStreamDeltaPayload(TypedDict):
    schema_version: str
    viewer_player_id: str
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

    def events_since(
        self,
        event_log: EventLog,
        *,
        viewer_player_id: str,
    ) -> EventStreamDeltaPayload:
        if type(viewer_player_id) is not str:
            raise GameLifecycleError("viewer_player_id must be a string.")
        if not viewer_player_id.strip():
            raise GameLifecycleError("viewer_player_id must not be empty.")
        viewer = ViewerContext.for_player(viewer_player_id)
        payload = self.events_since_for_context(event_log, viewer=viewer)
        return {
            "schema_version": payload["schema_version"],
            "viewer_player_id": viewer_player_id,
            "cursor": payload["cursor"],
            "next_cursor": payload["next_cursor"],
            "events": payload["events"],
        }

    def events_since_for_context(
        self,
        event_log: EventLog,
        *,
        viewer: ViewerContext,
    ) -> EventStreamDeltaPayload:
        if type(event_log) is not EventLog:
            raise GameLifecycleError("EventStreamCursor requires an EventLog.")
        if type(viewer) is not ViewerContext:
            raise GameLifecycleError("EventStreamCursor requires a ViewerContext.")
        records = event_log.records
        if self.value > len(records):
            raise GameLifecycleError("EventStreamCursor is ahead of the event log.")
        events = [
            public_event_record_payload(
                event_id=record.event_id,
                event_type=record.event_type,
                payload=record.payload,
                viewer=viewer,
            )
            for record in records[self.value :]
        ]
        return {
            "schema_version": ADAPTER_EVENT_STREAM_DELTA_SCHEMA_VERSION,
            "viewer_player_id": (
                "shared" if viewer.viewer_player_id is None else viewer.viewer_player_id
            ),
            "cursor": self.value,
            "next_cursor": len(records),
            "events": events,
        }
