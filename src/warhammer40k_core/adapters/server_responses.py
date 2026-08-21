from __future__ import annotations

from http import HTTPStatus
from typing import TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.external_contract import LIFECYCLE_STATUS_SCHEMA_VERSION
from warhammer40k_core.adapters.redaction import public_error_envelope, redacted_lifecycle_status
from warhammer40k_core.adapters.server_types import ServerResponse
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import LifecycleStatus


class ServerLifecycleStatusPayload(TypedDict):
    stage: str
    status_kind: str
    message: str | None
    payload: JsonValue
    pending_request_id: str | None
    decision_type: str | None
    actor_id: str | None


class ServerGameStatusPayload(TypedDict):
    schema_version: str
    game_id: str
    status: ServerLifecycleStatusPayload


def status_response(
    *,
    game_id: str,
    status: LifecycleStatus,
    viewer: ViewerContext,
    status_code: HTTPStatus = HTTPStatus.OK,
) -> ServerResponse:
    payload: ServerGameStatusPayload = {
        "schema_version": LIFECYCLE_STATUS_SCHEMA_VERSION,
        "game_id": game_id,
        "status": redacted_lifecycle_status(status, viewer=viewer),
    }
    return ServerResponse(
        status_code=int(status_code),
        payload=validate_json_value(cast(JsonValue, payload)),
    )


def error_response(*, status_code: HTTPStatus, code: str, message: str) -> ServerResponse:
    return ServerResponse(
        status_code=int(status_code),
        payload=public_error_envelope(
            code=_validate_identifier("error code", code),
            message=_validate_identifier("error message", message),
        ),
    )


def authentication_required_response() -> ServerResponse:
    return error_response(
        status_code=HTTPStatus.UNAUTHORIZED,
        code="authentication_required",
        message="A valid bearer credential is required.",
    )


def access_denied_response() -> ServerResponse:
    return error_response(
        status_code=HTTPStatus.FORBIDDEN,
        code="access_denied",
        message="Authenticated principal is not authorized for this resource.",
    )


_validate_identifier = IdentifierValidator(ValueError)
