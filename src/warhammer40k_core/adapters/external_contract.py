from __future__ import annotations

import json
from functools import cache
from importlib.resources import files
from pathlib import Path
from typing import Protocol, cast

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError
from referencing.jsonschema import Schema

from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

EXTERNAL_CONTRACT_VERSION = "1.2.0"

CREATE_SESSION_SCHEMA_VERSION = "create-session-v1"
DECISION_FAMILY_COVERAGE_SCHEMA_VERSION = "decision-family-coverage-v1"
DECISION_REQUEST_VIEW_SCHEMA_VERSION = "decision-request-view-v1"
ERROR_ENVELOPE_SCHEMA_VERSION = "error-envelope-v1"
EVENT_STREAM_DELTA_SCHEMA_VERSION = "event-delta-v1"
FINITE_SUBMISSION_SCHEMA_VERSION = "finite-submission-v1"
LIFECYCLE_STATUS_SCHEMA_VERSION = "lifecycle-status-v1"
PARAMETERIZED_SUBMISSION_SCHEMA_VERSION = "parameterized-submission-v1"
SESSION_COMMAND_RESULT_SCHEMA_VERSION = "session-command-result-v1"
SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION = "session-command-envelope-v1"
SESSION_COMMAND_OUTCOME_SCHEMA_VERSION = "session-command-outcome-v1"
SESSION_CREATE_SCHEMA_VERSION = "session-create-v1"
SESSION_METADATA_SCHEMA_VERSION = "session-metadata-v1"

CREATE_SESSION_SCHEMA_NAME = "create-session.schema.json"
FINITE_SUBMISSION_SCHEMA_NAME = "finite-submission.schema.json"
PARAMETERIZED_SUBMISSION_SCHEMA_NAME = "parameterized-submission.schema.json"
PROPOSAL_PAYLOAD_SCHEMA_NAME = "proposal-payload.schema.json"
SESSION_CREATE_SCHEMA_NAME = "session-create.schema.json"
SESSION_COMMAND_ENVELOPE_SCHEMA_NAME = "session-command-envelope.schema.json"

_REQUEST_SCHEMA_NAMES = frozenset(
    {
        CREATE_SESSION_SCHEMA_NAME,
        FINITE_SUBMISSION_SCHEMA_NAME,
        PARAMETERIZED_SUBMISSION_SCHEMA_NAME,
        SESSION_COMMAND_ENVELOPE_SCHEMA_NAME,
        SESSION_CREATE_SCHEMA_NAME,
    }
)


class ExternalContractValidationError(ValueError):
    """Raised when an adapter request violates the canonical external schema."""


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def require_schema_version(*, actual: object, expected: str, payload_name: str) -> None:
    if type(actual) is not str:
        raise ValueError(f"{payload_name} schema_version must be a string.")
    if actual != expected:
        raise ValueError(
            f"{payload_name} schema_version mismatch: expected {expected}, got {actual}."
        )


def validate_external_request_payload(
    *,
    schema_name: str,
    payload: JsonValue,
    payload_name: str,
) -> None:
    if schema_name not in _REQUEST_SCHEMA_NAMES:
        raise ExternalContractValidationError("Unknown canonical external request schema.")
    try:
        _request_validator(schema_name).validate(payload)
    except ValidationError as exc:
        location = "$" + "".join(
            f"[{part}]" if type(part) is int else f".{part}" for part in exc.absolute_path
        )
        raise ExternalContractValidationError(
            f"{payload_name} failed canonical schema validation at {location}."
        ) from exc


@cache
def _request_validator(schema_name: str) -> _PayloadValidator:
    schema = _schema_payload(schema_name)
    if schema_name == PARAMETERIZED_SUBMISSION_SCHEMA_NAME:
        properties = _json_object(schema["properties"], "parameterized schema properties")
        properties["payload"] = _schema_payload(PROPOSAL_PAYLOAD_SCHEMA_NAME)
    if schema_name == SESSION_COMMAND_ENVELOPE_SCHEMA_NAME:
        definitions = _json_object(schema["$defs"], "session command definitions")
        parameterized = _json_object(
            definitions["parameterized_submission"],
            "parameterized session command schema",
        )
        properties = _json_object(
            parameterized["properties"],
            "parameterized session command properties",
        )
        properties["payload"] = _schema_payload(PROPOSAL_PAYLOAD_SCHEMA_NAME)
    if schema_name == SESSION_CREATE_SCHEMA_NAME:
        properties = _json_object(schema["properties"], "session create schema properties")
        create_schema = _schema_payload(CREATE_SESSION_SCHEMA_NAME)
        create_properties = _json_object(
            create_schema["properties"],
            "create session schema properties",
        )
        properties["config"] = _json_object(
            create_properties["config"],
            "create session config schema",
        )
    typed_schema = cast(Schema, schema)
    Draft202012Validator.check_schema(typed_schema)
    return cast(_PayloadValidator, Draft202012Validator(typed_schema))


def _schema_payload(schema_name: str) -> dict[str, JsonValue]:
    try:
        decoded = json.loads(_schema_text(schema_name))
    except json.JSONDecodeError as exc:
        raise ExternalContractValidationError(
            f"Canonical external schema is invalid JSON: {schema_name}."
        ) from exc
    return _json_object(
        validate_json_value(decoded),
        f"canonical external schema {schema_name}",
    )


def _schema_text(schema_name: str) -> str:
    repository_path = Path(__file__).resolve().parents[3] / "contracts" / "schemas" / schema_name
    if repository_path.is_file():
        return repository_path.read_text(encoding="utf-8")
    package_path = files("warhammer40k_core").joinpath("contracts", "schemas", schema_name)
    if not package_path.is_file():
        raise ExternalContractValidationError(
            f"Canonical external schema is unavailable: {schema_name}."
        )
    return package_path.read_text(encoding="utf-8")


def _json_object(value: JsonValue, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ExternalContractValidationError(f"{field_name} must be a JSON object.")
    return value
