from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum
from typing import Self

from warhammer40k_core.adapters.access_control import AuthorizationContext
from warhammer40k_core.adapters.external_contract import SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


class SessionCommandProtocolError(ValueError):
    """Raised when an optimistic-concurrency command payload is invalid."""


class SessionCommandSubmissionKind(StrEnum):
    START_SESSION = "start_session"
    ADVANCE_SESSION = "advance_session"
    CLOSE_SESSION = "close_session"
    FINITE_OPTION = "finite_option"
    PARAMETERIZED_PAYLOAD = "parameterized_payload"


class SessionCommandOutcomeCode(StrEnum):
    COMMAND_COMMITTED = "command_committed"
    PROPOSAL_INVALID = "proposal_invalid"
    RULE_PATH_UNSUPPORTED = "rule_path_unsupported"


@dataclass(frozen=True, slots=True)
class SessionCommandEnvelope:
    command_id: str
    session_id: str
    expected_session_revision: int
    request_id: str | None
    result_id: str | None
    submission_kind: SessionCommandSubmissionKind
    submission: dict[str, JsonValue]
    schema_version: str = SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "schema_version",
            _validate_schema_version(self.schema_version),
        )
        object.__setattr__(self, "command_id", _validate_identifier("command_id", self.command_id))
        object.__setattr__(self, "session_id", _validate_identifier("session_id", self.session_id))
        if type(self.expected_session_revision) is not int or self.expected_session_revision < 0:
            raise SessionCommandProtocolError(
                "expected_session_revision must be a non-negative integer."
            )
        if type(self.submission_kind) is not SessionCommandSubmissionKind:
            raise SessionCommandProtocolError("Command submission kind is invalid.")
        submission = _json_object(self.submission, field_name="submission")
        object.__setattr__(self, "submission", copy.deepcopy(submission))
        self._validate_operation_fields()

    @classmethod
    def from_payload(cls, payload: JsonValue) -> Self:
        value = _json_object(payload, field_name="command envelope")
        expected_keys = {
            "schema_version",
            "command_id",
            "session_id",
            "expected_session_revision",
            "request_id",
            "result_id",
            "submission",
        }
        if set(value) != expected_keys:
            raise SessionCommandProtocolError("Command envelope keys are invalid.")
        submission = _json_object(value["submission"], field_name="submission")
        if "submission_kind" not in submission:
            raise SessionCommandProtocolError("Command submission_kind is required.")
        submission_kind_value = submission["submission_kind"]
        if type(submission_kind_value) is not str:
            raise SessionCommandProtocolError("Command submission_kind must be a string.")
        try:
            submission_kind = SessionCommandSubmissionKind(submission_kind_value)
        except ValueError as exc:
            raise SessionCommandProtocolError("Command submission_kind is unsupported.") from exc
        request_id = value["request_id"]
        result_id = value["result_id"]
        if request_id is not None and type(request_id) is not str:
            raise SessionCommandProtocolError("Command request_id is invalid.")
        if result_id is not None and type(result_id) is not str:
            raise SessionCommandProtocolError("Command result_id is invalid.")
        schema_version = value["schema_version"]
        command_id = value["command_id"]
        session_id = value["session_id"]
        expected_revision = value["expected_session_revision"]
        if type(schema_version) is not str:
            raise SessionCommandProtocolError("Command schema_version must be a string.")
        if type(command_id) is not str or type(session_id) is not str:
            raise SessionCommandProtocolError("Command identifiers must be strings.")
        if type(expected_revision) is not int:
            raise SessionCommandProtocolError("Command expected revision must be an integer.")
        return cls(
            schema_version=schema_version,
            command_id=command_id,
            session_id=session_id,
            expected_session_revision=expected_revision,
            request_id=request_id,
            result_id=result_id,
            submission_kind=submission_kind,
            submission=submission,
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "schema_version": self.schema_version,
            "command_id": self.command_id,
            "session_id": self.session_id,
            "expected_session_revision": self.expected_session_revision,
            "request_id": self.request_id,
            "result_id": self.result_id,
            "submission": copy.deepcopy(self.submission),
        }

    def fingerprint(self) -> str:
        encoded = json.dumps(
            self.to_payload(),
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def option_id(self) -> str:
        if self.submission_kind is not SessionCommandSubmissionKind.FINITE_OPTION:
            raise SessionCommandProtocolError("Command does not contain a finite option.")
        return _validate_identifier("option_id", self.submission["option_id"])

    def parameterized_payload(self) -> JsonValue:
        if self.submission_kind is not SessionCommandSubmissionKind.PARAMETERIZED_PAYLOAD:
            raise SessionCommandProtocolError("Command does not contain a parameterized payload.")
        return validate_json_value(copy.deepcopy(self.submission["payload"]))

    def _validate_operation_fields(self) -> None:
        if self.submission_kind in {
            SessionCommandSubmissionKind.START_SESSION,
            SessionCommandSubmissionKind.ADVANCE_SESSION,
            SessionCommandSubmissionKind.CLOSE_SESSION,
        }:
            if self.request_id is not None or self.result_id is not None:
                raise SessionCommandProtocolError(
                    "Lifecycle commands require null request_id and result_id."
                )
            if set(self.submission) != {"submission_kind"}:
                raise SessionCommandProtocolError("Lifecycle command submission keys are invalid.")
            return
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("result_id", self.result_id),
        )
        if self.submission_kind is SessionCommandSubmissionKind.FINITE_OPTION:
            if set(self.submission) != {"submission_kind", "option_id"}:
                raise SessionCommandProtocolError("Finite command submission keys are invalid.")
            self.option_id()
            return
        if set(self.submission) != {"submission_kind", "payload"}:
            raise SessionCommandProtocolError("Parameterized command submission keys are invalid.")
        self.parameterized_payload()


@dataclass(frozen=True, slots=True)
class SessionCommandJournalEntry:
    command_id: str
    principal_id: str
    authorization_context: AuthorizationContext
    envelope_fingerprint: str
    status_code: int
    response_payload: JsonValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "command_id", _validate_identifier("command_id", self.command_id))
        object.__setattr__(
            self,
            "principal_id",
            _validate_identifier("principal_id", self.principal_id),
        )
        if type(self.authorization_context) is not AuthorizationContext:
            raise SessionCommandProtocolError("Command journal authorization context is invalid.")
        if self.authorization_context.principal_id != self.principal_id:
            raise SessionCommandProtocolError(
                "Command journal principal and authorization context differ."
            )
        object.__setattr__(
            self,
            "envelope_fingerprint",
            _validate_sha256("envelope_fingerprint", self.envelope_fingerprint),
        )
        if type(self.status_code) is not int or not 200 <= self.status_code <= 599:
            raise SessionCommandProtocolError("Command journal status code is invalid.")
        object.__setattr__(
            self,
            "response_payload",
            copy.deepcopy(validate_json_value(self.response_payload)),
        )

    def public_payload(self) -> JsonValue:
        return copy.deepcopy(self.response_payload)


def _validate_schema_version(value: object) -> str:
    if value != SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION:
        raise SessionCommandProtocolError("Command envelope schema_version is unsupported.")
    return SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION


def _validate_sha256(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    if len(identifier) != 64 or any(
        character not in "0123456789abcdef" for character in identifier
    ):
        raise SessionCommandProtocolError(f"{field_name} must be a lowercase SHA-256 digest.")
    return identifier


def _json_object(value: JsonValue, *, field_name: str) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise SessionCommandProtocolError(f"{field_name} must be a JSON object.")
    return value


_validate_identifier = IdentifierValidator(SessionCommandProtocolError)
