from __future__ import annotations

from http import HTTPStatus
from typing import cast

from warhammer40k_core.adapters.command_protocol import (
    SessionCommandEnvelope,
    SessionCommandOutcomeCode,
    SessionCommandProtocolError,
)
from warhammer40k_core.adapters.external_contract import (
    SESSION_COMMAND_ENVELOPE_SCHEMA_NAME,
    ExternalContractValidationError,
    validate_external_request_payload,
)
from warhammer40k_core.adapters.projection import DecisionRequestViewPayload
from warhammer40k_core.adapters.redaction import redacted_decision_type_for_hidden_viewer
from warhammer40k_core.adapters.server_authorization import actor_not_authorized
from warhammer40k_core.adapters.server_types import ServerApiError, ServerResponse
from warhammer40k_core.adapters.server_validation import json_object, validate_identifier
from warhammer40k_core.adapters.session_protocol import (
    AuthoritativeSession,
    SessionCheckpointPayload,
    SessionMetadataPayload,
    SessionProtocolError,
    session_command_outcome_payload,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatusKind


def session_id_for_game(game_id: str) -> str:
    return validate_identifier("session_id", f"session-{game_id}")


def session_command_envelope(body: JsonValue) -> SessionCommandEnvelope:
    payload = json_object("session command envelope", body)
    try:
        validate_external_request_payload(
            schema_name=SESSION_COMMAND_ENVELOPE_SCHEMA_NAME,
            payload=payload,
            payload_name="session command envelope",
        )
    except ExternalContractValidationError as exc:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="canonical_schema_invalid",
            message=str(exc),
        ) from exc
    try:
        return SessionCommandEnvelope.from_payload(payload)
    except SessionCommandProtocolError as exc:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="malformed_command_envelope",
            message="Session command envelope was malformed.",
        ) from exc


def command_request_id(envelope: SessionCommandEnvelope) -> str:
    request_id = envelope.request_id
    if request_id is None:
        raise SessionCommandProtocolError("Decision command request_id is missing.")
    return request_id


def command_result_id(envelope: SessionCommandEnvelope) -> str:
    result_id = envelope.result_id
    if result_id is None:
        raise SessionCommandProtocolError("Decision command result_id is missing.")
    return result_id


def command_pending_decision(
    *,
    record: AuthoritativeSession,
    request_id: str,
    player_id: str,
) -> DecisionRequestViewPayload:
    pending = record.adapter_session.view(viewer_player_id=player_id)["pending_decision"]
    if pending is None:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="stale_decision_request",
            message="Command does not target the current pending decision.",
        )
    if pending["decision_type"] == redacted_decision_type_for_hidden_viewer():
        raise actor_not_authorized()
    if pending["actor_id"] != player_id:
        raise actor_not_authorized()
    if pending["request_id"] != request_id:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="stale_decision_request",
            message="Command does not target the current pending decision.",
        )
    return pending


def session_command_outcome_response(
    *,
    command_id: str,
    response: ServerResponse,
) -> ServerResponse:
    base = json_object("session command result", response.payload)
    accepted = base.get("accepted")
    if type(accepted) is not bool:
        raise SessionProtocolError("Session command result accepted flag is invalid.")
    if accepted:
        outcome_code = SessionCommandOutcomeCode.COMMAND_COMMITTED
    else:
        session = json_object("session command session", base["session"])
        lifecycle = json_object("session command lifecycle status", session["lifecycle_status"])
        status_kind = lifecycle.get("status_kind")
        if status_kind == LifecycleStatusKind.INVALID.value:
            outcome_code = SessionCommandOutcomeCode.PROPOSAL_INVALID
        elif status_kind == LifecycleStatusKind.UNSUPPORTED.value:
            outcome_code = SessionCommandOutcomeCode.RULE_PATH_UNSUPPORTED
        else:
            raise SessionProtocolError("Rejected command lifecycle status is invalid.")
    committed = base.get("committed")
    if type(committed) is not bool:
        raise SessionProtocolError("Session command result committed flag is invalid.")
    operation = base.get("operation")
    if type(operation) is not str:
        raise SessionProtocolError("Session command result operation is invalid.")
    event_range = json_object("session command event range", base["event_range"])
    from_cursor = event_range.get("from_cursor")
    if type(from_cursor) is not str:
        raise SessionProtocolError("Session command result event range is invalid.")
    payload = session_command_outcome_payload(
        command_id=command_id,
        outcome_code=outcome_code,
        operation=operation,
        committed=committed,
        accepted=accepted,
        session=cast(SessionMetadataPayload, base["session"]),
        checkpoint=cast(SessionCheckpointPayload, base["checkpoint"]),
        from_cursor=from_cursor,
    )
    return ServerResponse(
        status_code=response.status_code,
        payload=validate_json_value(cast(JsonValue, payload)),
    )
