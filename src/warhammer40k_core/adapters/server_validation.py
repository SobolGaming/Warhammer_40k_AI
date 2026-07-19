from __future__ import annotations

from collections.abc import Mapping
from http import HTTPStatus

from warhammer40k_core.adapters.server_types import ServerApiError
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue


def not_found() -> ServerApiError:
    return ServerApiError(
        status_code=HTTPStatus.NOT_FOUND,
        code="route_not_found",
        message="Route was not found.",
    )


def method_token(method: object) -> str:
    value = validate_identifier("HTTP method", method)
    normalized = value.upper()
    if normalized not in {"GET", "POST"}:
        raise ServerApiError(
            status_code=HTTPStatus.METHOD_NOT_ALLOWED,
            code="method_not_allowed",
            message="HTTP method is not supported by the adapter game server.",
        )
    return normalized


def path_segments(path: object) -> tuple[str, ...]:
    value = validate_identifier("HTTP path", path)
    return tuple(segment for segment in value.strip("/").split("/") if segment)


def query_string(query: Mapping[str, str], *, key: str) -> str:
    if key not in query:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="missing_query_parameter",
            message=f"Missing required query parameter: {key}.",
        )
    return validate_identifier(key, query[key])


def optional_query_string(query: Mapping[str, str], *, key: str) -> str | None:
    if key not in query:
        return None
    return validate_identifier(key, query[key])


def query_int(query: Mapping[str, str], *, key: str) -> int:
    raw = query_string(query, key=key)
    if not raw.isdecimal():
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="invalid_query_parameter",
            message=f"Query parameter must be a non-negative integer: {key}.",
        )
    return int(raw)


def json_object(field_name: str, value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="malformed_payload",
            message=f"{field_name} must be an object.",
        )
    return value


def require_exact_keys(payload: dict[str, JsonValue], *, keys: frozenset[str]) -> None:
    if frozenset(payload) == keys:
        return
    raise ServerApiError(
        status_code=HTTPStatus.BAD_REQUEST,
        code="malformed_payload",
        message="Payload keys do not match the route contract.",
    )


def required_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="malformed_payload",
            message=f"Payload missing required key: {key}.",
        )
    return validate_identifier(key, payload[key])


def reject_raw_dice_payload(value: JsonValue) -> None:
    if isinstance(value, list):
        for item in value:
            reject_raw_dice_payload(item)
        return
    if not isinstance(value, dict):
        return
    keys = frozenset(value)
    if {"roll_id", "spec", "values", "total", "source"} <= keys:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="client_raw_dice_rejected",
            message="Server decision routes do not accept raw dice roll result payloads.",
        )
    if {"source_d6_value", "source_d6_result", "replacement_result", "injected_results"} & keys:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="client_raw_dice_rejected",
            message="Server decision routes do not accept raw dice values from clients.",
        )
    for item in value.values():
        reject_raw_dice_payload(item)


def _malformed_identifier_error(message: str) -> ServerApiError:
    return ServerApiError(
        status_code=HTTPStatus.BAD_REQUEST,
        code="malformed_identifier",
        message=message,
    )


validate_identifier = IdentifierValidator(_malformed_identifier_error)
