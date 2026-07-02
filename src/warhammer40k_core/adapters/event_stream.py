from __future__ import annotations

from dataclasses import dataclass
from typing import TypedDict, cast

from warhammer40k_core.adapters.redaction import (
    decision_request_payload_hidden_from_viewer,
    redacted_decision_type_for_hidden_viewer,
)
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
            _public_event_record_payload(
                event_id=record.event_id,
                event_type=record.event_type,
                payload=record.payload,
                viewer_player_id=viewer,
            )
            for record in records[self.value :]
        ]
        return {
            "viewer_player_id": viewer,
            "cursor": self.value,
            "next_cursor": len(records),
            "events": events,
        }


def _public_event_record_payload(
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    viewer_player_id: str,
) -> EventRecordPayload:
    public_type = event_type
    public_payload = _public_event_payload(
        event_type=event_type,
        payload=payload,
        viewer_player_id=viewer_player_id,
    )
    if _is_generic_hidden_event_payload(public_payload):
        public_type = "hidden_event"
    return cast(
        EventRecordPayload,
        {
            "event_id": event_id,
            "event_type": public_type,
            "payload": public_payload,
        },
    )


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
    if event_type == "tactical_secondary_missions_drawn":
        return _public_tactical_secondary_drawn_payload(
            payload,
            viewer_player_id=viewer_player_id,
        )
    if event_type == "tactical_secondary_mission_discarded":
        return _public_tactical_secondary_discarded_payload(
            payload,
            viewer_player_id=viewer_player_id,
        )
    if event_type == "tactical_secondary_missions_discarded":
        return _public_tactical_secondary_discarded_payload(
            payload,
            viewer_player_id=viewer_player_id,
        )
    if event_type == "mission_action_started":
        return _public_hidden_player_event_payload(
            "mission_action_started",
            payload,
            viewer_player_id=viewer_player_id,
        )
    return validate_json_value(payload)


def _is_generic_hidden_event_payload(payload: JsonValue) -> bool:
    if not isinstance(payload, dict):
        return False
    hidden_event = payload.get("hidden_event")
    if hidden_event is None:
        return False
    if type(hidden_event) is not bool:
        raise GameLifecycleError("Hidden event payload flag must be a bool.")
    return hidden_event


def _public_decision_request_payload(
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    request_payload = _json_object("decision_requested payload", payload)
    if decision_request_payload_hidden_from_viewer(
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
    if not decision_request_payload_hidden_from_viewer(
        request_payload=request_payload,
        viewer_player_id=viewer_player_id,
    ):
        return validate_json_value(record_payload)
    result_payload = _json_object("decision_recorded result payload", record_payload["result"])
    return {
        "record_id": _required_string(record_payload, key="record_id"),
        "request": _redacted_request_payload(request_payload),
        "result": _redacted_result_payload(result_payload),
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


def _public_tactical_secondary_drawn_payload(
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    draw_payload = _json_object("tactical_secondary_missions_drawn payload", payload)
    player_id = _required_string(draw_payload, key="player_id")
    hidden = draw_payload.get("hidden")
    if hidden is not None and type(hidden) is not bool:
        raise GameLifecycleError("Tactical secondary draw hidden flag must be a bool.")
    if player_id == viewer_player_id or hidden is not True:
        return validate_json_value(draw_payload)
    return {
        "game_id": _required_string(draw_payload, key="game_id"),
        "hidden": True,
        "hidden_event": True,
    }


def _public_tactical_secondary_discarded_payload(
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    discard_payload = _json_object("tactical_secondary_mission_discarded payload", payload)
    player_id = _required_string(discard_payload, key="player_id")
    hidden = discard_payload.get("hidden")
    if hidden is not None and type(hidden) is not bool:
        raise GameLifecycleError("Tactical secondary discard hidden flag must be a bool.")
    if player_id == viewer_player_id or hidden is not True:
        return validate_json_value(discard_payload)
    return {
        "game_id": _required_string(discard_payload, key="game_id"),
        "hidden": True,
        "hidden_event": True,
    }


def _public_hidden_player_event_payload(
    event_name: str,
    payload: JsonValue,
    *,
    viewer_player_id: str,
) -> JsonValue:
    event_payload = _json_object(f"{event_name} payload", payload)
    player_id = _required_string(event_payload, key="player_id")
    hidden = event_payload.get("hidden")
    if hidden is not None and type(hidden) is not bool:
        raise GameLifecycleError("Hidden player event payload flag must be a bool.")
    if player_id == viewer_player_id or hidden is not True:
        return validate_json_value(event_payload)
    return {
        "game_id": _required_string(event_payload, key="game_id"),
        "hidden": True,
        "hidden_event": True,
    }


def _redacted_request_payload(request_payload: dict[str, JsonValue]) -> JsonValue:
    return {
        "request_id": _required_string(request_payload, key="request_id"),
        "decision_type": redacted_decision_type_for_hidden_viewer(),
        "actor_id": _optional_string(request_payload, key="actor_id"),
        "secret": True,
        "hidden": True,
    }


def _redacted_result_payload(result_payload: dict[str, JsonValue]) -> JsonValue:
    return {
        "result_id": _required_string(result_payload, key="result_id"),
        "request_id": _required_string(result_payload, key="request_id"),
        "decision_type": redacted_decision_type_for_hidden_viewer(),
        "actor_id": _optional_string(result_payload, key="actor_id"),
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
