from __future__ import annotations

from collections.abc import Mapping
from typing import TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.external_contract import ERROR_ENVELOPE_SCHEMA_VERSION
from warhammer40k_core.adapters.support_profile import SupportProfilePayload
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import EventRecordPayload, JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind

HIDDEN_DECISION_TYPE = "hidden_decision"
HIDDEN_REQUEST_ID = "hidden-request"
HIDDEN_RESULT_ID = "hidden-result"


class RedactedLifecycleStatusPayload(TypedDict):
    stage: str
    status_kind: str
    message: str | None
    payload: JsonValue
    pending_request_id: str | None
    decision_type: str | None
    actor_id: str | None


def public_error_envelope(*, code: str, message: str) -> dict[str, JsonValue]:
    public_code = _public_error_string("error code", code)
    public_message = _public_error_string("error message", message)
    return {
        "schema_version": ERROR_ENVELOPE_SCHEMA_VERSION,
        "error": {
            "code": public_code,
            "message": public_message,
        },
    }


def public_support_profile_payload(
    payload: SupportProfilePayload,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("Support-profile redaction requires a ViewerContext.")
    if not viewer.policy.may_view_support:
        raise GameLifecycleError("Viewer role cannot receive a support profile.")
    return validate_json_value(cast(JsonValue, payload))


def decision_request_hidden_from_context(
    *,
    request: DecisionRequest,
    viewer: ViewerContext,
) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("DecisionRequest redaction requires a DecisionRequest.")
    return secret_payload_hidden_from_context(
        actor_id=request.actor_id,
        payload=request.payload,
        viewer=viewer,
    )


def decision_request_payload_hidden_from_context(
    *,
    request_payload: Mapping[str, JsonValue],
    viewer: ViewerContext,
) -> bool:
    actor_id = _optional_string(request_payload, key="actor_id")
    return secret_payload_hidden_from_context(
        actor_id=actor_id,
        payload=request_payload["payload"],
        viewer=viewer,
    )


def secret_payload_hidden_from_context(
    *,
    actor_id: str | None,
    payload: JsonValue,
    viewer: ViewerContext,
) -> bool:
    if type(viewer) is not ViewerContext:
        raise GameLifecycleError("Redaction requires a ViewerContext.")
    if viewer.policy.omniscient or viewer.owns_player(actor_id):
        return False
    if not isinstance(payload, dict):
        return False
    secret = payload.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret DecisionRequest payload flag must be a bool.")
    return secret


def decision_request_hidden_from_viewer(
    *,
    request: DecisionRequest,
    viewer_player_id: str | None,
) -> bool:
    return decision_request_hidden_from_context(
        request=request,
        viewer=_legacy_viewer_context(viewer_player_id),
    )


def decision_request_payload_hidden_from_viewer(
    *,
    request_payload: Mapping[str, JsonValue],
    viewer_player_id: str | None,
) -> bool:
    return decision_request_payload_hidden_from_context(
        request_payload=request_payload,
        viewer=_legacy_viewer_context(viewer_player_id),
    )


def redacted_decision_type_for_hidden_viewer() -> str:
    return HIDDEN_DECISION_TYPE


def redacted_lifecycle_status(
    status: LifecycleStatus,
    *,
    viewer: ViewerContext,
) -> RedactedLifecycleStatusPayload:
    if type(status) is not LifecycleStatus:
        raise GameLifecycleError("Lifecycle status redaction requires LifecycleStatus.")
    decision_request = status.decision_request
    hidden_pending = (
        False
        if decision_request is None
        else decision_request_hidden_from_context(request=decision_request, viewer=viewer)
    )
    metadata_payload = (
        status.payload
        if status.status_kind
        in {
            LifecycleStatusKind.TERMINAL,
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
        else None
    )
    if hidden_pending:
        return {
            "stage": status.stage.value,
            "status_kind": status.status_kind.value,
            "message": None,
            "payload": None,
            "pending_request_id": None,
            "decision_type": HIDDEN_DECISION_TYPE,
            "actor_id": None,
        }
    return {
        "stage": status.stage.value,
        "status_kind": status.status_kind.value,
        "message": status.message,
        "payload": metadata_payload,
        "pending_request_id": None if decision_request is None else decision_request.request_id,
        "decision_type": None if decision_request is None else decision_request.decision_type,
        "actor_id": None if decision_request is None else decision_request.actor_id,
    }


def public_event_record_payload(
    *,
    event_id: str,
    event_type: str,
    payload: JsonValue,
    viewer: ViewerContext,
) -> EventRecordPayload:
    public_payload = _public_event_payload(
        event_type=event_type,
        payload=payload,
        viewer=viewer,
    )
    public_type = "hidden_event" if _is_generic_hidden_event_payload(public_payload) else event_type
    public_id = "hidden-event" if public_type == "hidden_event" else event_id
    return cast(
        EventRecordPayload,
        {
            "event_id": public_id,
            "event_type": public_type,
            "payload": public_payload,
        },
    )


def _public_event_payload(
    *,
    event_type: str,
    payload: JsonValue,
    viewer: ViewerContext,
) -> JsonValue:
    if event_type == "decision_requested":
        return _public_decision_request_payload(payload, viewer=viewer)
    if event_type == "decision_recorded":
        return _public_decision_record_payload(payload, viewer=viewer)
    if event_type == "secondary_mission_choice_recorded":
        return _public_secondary_mission_choice_recorded_payload(payload, viewer=viewer)
    if event_type == "tactical_secondary_missions_drawn":
        return _public_tactical_secondary_drawn_payload(payload, viewer=viewer)
    if event_type in {
        "tactical_secondary_mission_discarded",
        "tactical_secondary_missions_discarded",
    }:
        return _public_tactical_secondary_discarded_payload(payload, viewer=viewer)
    if event_type == "mission_action_started":
        return _public_hidden_player_event_payload(
            "mission_action_started",
            payload,
            viewer=viewer,
        )
    return validate_json_value(payload)


def _public_decision_request_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    request_payload = _json_object("decision_requested payload", payload)
    if decision_request_payload_hidden_from_context(
        request_payload=request_payload,
        viewer=viewer,
    ):
        return _redacted_request_payload()
    return validate_json_value(request_payload)


def _public_decision_record_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    record_payload = _json_object("decision_recorded payload", payload)
    request_payload = _json_object("decision_recorded request payload", record_payload["request"])
    if not decision_request_payload_hidden_from_context(
        request_payload=request_payload,
        viewer=viewer,
    ):
        return validate_json_value(record_payload)
    return {
        "record_id": "hidden-record",
        "request": _redacted_request_payload(),
        "result": _redacted_result_payload(),
    }


def _public_secondary_mission_choice_recorded_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    choice_payload = _json_object("secondary_mission_choice_recorded payload", payload)
    player_id = _required_string(choice_payload, key="player_id")
    if viewer.policy.omniscient or viewer.owns_player(player_id):
        return validate_json_value(choice_payload)
    return {
        "game_id": _required_string(choice_payload, key="game_id"),
        "selected": True,
        "hidden": True,
    }


def _public_tactical_secondary_drawn_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    return _public_hidden_player_event_payload(
        "tactical_secondary_missions_drawn",
        payload,
        viewer=viewer,
    )


def _public_tactical_secondary_discarded_payload(
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    return _public_hidden_player_event_payload(
        "tactical_secondary_mission_discarded",
        payload,
        viewer=viewer,
    )


def _public_hidden_player_event_payload(
    event_name: str,
    payload: JsonValue,
    *,
    viewer: ViewerContext,
) -> JsonValue:
    event_payload = _json_object(f"{event_name} payload", payload)
    player_id = _required_string(event_payload, key="player_id")
    hidden = event_payload.get("hidden")
    if hidden is not None and type(hidden) is not bool:
        raise GameLifecycleError("Hidden player event payload flag must be a bool.")
    if viewer.policy.omniscient or viewer.owns_player(player_id) or hidden is not True:
        return validate_json_value(event_payload)
    return {
        "game_id": _required_string(event_payload, key="game_id"),
        "hidden": True,
        "hidden_event": True,
    }


def _is_generic_hidden_event_payload(payload: JsonValue) -> bool:
    if not isinstance(payload, dict):
        return False
    hidden_event = payload.get("hidden_event")
    if hidden_event is None:
        return False
    if type(hidden_event) is not bool:
        raise GameLifecycleError("Hidden event payload flag must be a bool.")
    return hidden_event


def _redacted_request_payload() -> JsonValue:
    return {
        "request_id": HIDDEN_REQUEST_ID,
        "decision_type": HIDDEN_DECISION_TYPE,
        "actor_id": None,
        "secret": True,
        "hidden": True,
    }


def _redacted_result_payload() -> JsonValue:
    return {
        "result_id": HIDDEN_RESULT_ID,
        "request_id": HIDDEN_REQUEST_ID,
        "decision_type": HIDDEN_DECISION_TYPE,
        "actor_id": None,
        "secret": True,
        "hidden": True,
    }


def _legacy_viewer_context(viewer_player_id: str | None) -> ViewerContext:
    if viewer_player_id is None:
        return ViewerContext.for_player("redacted-viewer")
    return ViewerContext.for_player(viewer_player_id)


def _json_object(field_name: str, value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise GameLifecycleError(f"{field_name} must be an object.")
    return value


def _required_string(payload: Mapping[str, JsonValue], *, key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Redacted payload key must be a string: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Redacted payload key must not be empty: {key}.")
    return stripped


def _optional_string(payload: Mapping[str, JsonValue], *, key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"Redacted payload key must be a string or null: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Redacted payload key must not be empty: {key}.")
    return stripped


def _public_error_string(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Public {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Public {field_name} must not be empty.")
    return stripped
