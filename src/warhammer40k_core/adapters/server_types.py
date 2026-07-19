from __future__ import annotations

from dataclasses import dataclass
from http import HTTPStatus

from warhammer40k_core.adapters.external_contract import ERROR_ENVELOPE_SCHEMA_VERSION
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


@dataclass(frozen=True, slots=True)
class ServerResponse:
    status_code: int
    payload: JsonValue

    def __post_init__(self) -> None:
        if type(self.status_code) is not int:
            raise ServerApiError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="invalid_server_response",
                message="ServerResponse status_code must be an integer.",
            )
        if self.status_code < 100 or self.status_code > 599:
            raise ServerApiError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="invalid_server_response",
                message="ServerResponse status_code must be an HTTP status code.",
            )
        validate_json_value(self.payload)


class ServerApiError(ValueError):
    status_code: HTTPStatus
    code: str

    def __init__(self, *, status_code: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = _validate_identifier("ServerApiError code", code)

    def to_response(self) -> ServerResponse:
        return ServerResponse(
            status_code=int(self.status_code),
            payload={
                "schema_version": ERROR_ENVELOPE_SCHEMA_VERSION,
                "error": {
                    "code": self.code,
                    "message": str(self),
                },
            },
        )


_validate_identifier = IdentifierValidator(ValueError)
