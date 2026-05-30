from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecordPayload,
    JsonValue,
    validate_json_value,
)
from warhammer40k_core.engine.phase import GameLifecycleError


class EventStreamDeltaPayload(TypedDict):
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
        if type(event_log) is not EventLog:
            raise GameLifecycleError("EventStreamCursor requires an EventLog.")
        viewer = _validate_viewer_player_id(viewer_player_id)
        records = event_log.records
        if self.value > len(records):
            raise GameLifecycleError("EventStreamCursor is ahead of the event log.")
        events: list[EventRecordPayload] = [
            cast(
                EventRecordPayload,
                {
                    "event_id": record.event_id,
                    "event_type": record.event_type,
                    "payload": _public_event_payload(
                        event_type=record.event_type,
                        payload=record.payload,
                        viewer_player_id=viewer,
                    ),
                },
            )
            for record in records[self.value :]
        ]
        return {
            "viewer_player_id": viewer,
            "cursor": self.value,
            "next_cursor": len(records),
            "events": events,
        }


def _public_event_payload(
    *,
    event_type: str,
    payload: JsonValue,
    viewer_player_id: str,
) -> JsonValue:
    if event_type == "decision_requested":
        return _public_decision_request_payload(payload, viewer_player_id=viewer_player_id)
    if event_type == "decision_recorded":
        return _public_decision_record_payload(payload, viewer_player_id=viewer_player_id)
    if event_type == "secondary_mission_choice_recorded":
        return _public_secondary_mission_choice_recorded_payload(
            payload,
            viewer_player_id=viewer_player_id,
        )
    return validate_json_value(payload)


def _public_decision_request_payload(
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    request_payload = _json_object("decision_requested payload", payload)
    if _secret_request_hidden_from_viewer(
        request_payload=request_payload,
        viewer_player_id=viewer_player_id,
    ):
        return _redacted_request_payload(request_payload)
    return validate_json_value(request_payload)


def _public_decision_record_payload(
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    record_payload = _json_object("decision_recorded payload", payload)
    request_payload = _json_object("decision_recorded request payload", record_payload["request"])
    if not _secret_request_hidden_from_viewer(
        request_payload=request_payload,
        viewer_player_id=viewer_player_id,
    ):
        return validate_json_value(record_payload)
    result_payload = _json_object("decision_recorded result payload", record_payload["result"])
    return {
        "record_id": _required_string(record_payload, key="record_id"),
        "request": _redacted_request_payload(request_payload),
        "result": {
            "result_id": _required_string(result_payload, key="result_id"),
            "request_id": _required_string(result_payload, key="request_id"),
            "decision_type": _required_string(result_payload, key="decision_type"),
            "actor_id": _optional_string(result_payload, key="actor_id"),
            "secret": True,
            "hidden": True,
        },
    }


def _public_secondary_mission_choice_recorded_payload(
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    choice_payload = _json_object("secondary_mission_choice_recorded payload", payload)
    player_id = _required_string(choice_payload, key="player_id")
    if player_id == viewer_player_id:
        return validate_json_value(choice_payload)
    return {
        "game_id": _required_string(choice_payload, key="game_id"),
        "player_id": player_id,
        "setup_step": _required_string(choice_payload, key="setup_step"),
        "selected": True,
        "hidden": True,
    }


def _secret_request_hidden_from_viewer(
    *,
    request_payload: dict[str, JsonValue],
    viewer_player_id: str,
) -> bool:
    actor_id = _optional_string(request_payload, key="actor_id")
    body = request_payload["payload"]
    if not isinstance(body, dict):
        return False
    secret = body.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret DecisionRequest payload flag must be a bool.")
    return secret and actor_id != viewer_player_id


def _redacted_request_payload(request_payload: dict[str, JsonValue]) -> JsonValue:
    return {
        "request_id": _required_string(request_payload, key="request_id"),
        "decision_type": _required_string(request_payload, key="decision_type"),
        "actor_id": _optional_string(request_payload, key="actor_id"),
        "secret": True,
        "hidden": True,
    }


def _json_object(field_name: str, value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def _required_string(payload: dict[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Event payload key must be a string: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Event payload key must not be empty: {key}.")
    return stripped


def _optional_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Event payload key must be a string or null: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Event payload key must not be empty: {key}.")
    return stripped


def _validate_viewer_player_id(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("viewer_player_id must be a string.")
    viewer = value.strip()
    if not viewer:
        raise GameLifecycleError("viewer_player_id must not be empty.")
    return viewer
