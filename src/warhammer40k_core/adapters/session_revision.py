from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.adapters.command_protocol import (
    SessionCommandEnvelope,
    SessionCommandJournalEntry,
    SessionCommandSubmissionKind,
)
from warhammer40k_core.adapters.contracts import AdapterSessionHistoryPayload
from warhammer40k_core.adapters.session_events import SessionCursor
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value

SESSION_REVISION_COMMITMENT_SCHEMA_VERSION = "session-revision-commitment-v2"


class SessionRevisionIntegrityError(ValueError):
    """Raised when one session revision cannot be tied to its authoritative history."""


_REVISION_IDENTIFIER = IdentifierValidator(error_factory=SessionRevisionIntegrityError)


class SessionRevisionOriginKind(StrEnum):
    NONCOMMAND = "noncommand"
    PROTOCOL_COMMAND = "protocol_command"


class SessionNonCommandOrigin(StrEnum):
    SESSION_CREATED = "session_created"
    SESSION_CLOSED = "session_closed"
    LEGACY_ADVANCE_SESSION = "legacy_advance_session"
    LEGACY_FINITE_DECISION = "legacy_finite_decision"
    LEGACY_PARAMETERIZED_DECISION = "legacy_parameterized_decision"


class SessionRevisionOriginPayload(TypedDict):
    origin_kind: str
    operation: str
    command_envelope: JsonValue | None
    envelope_fingerprint: str | None


class SessionRevisionCursorCommitmentPayload(TypedDict):
    token: str
    cursor: JsonValue


class SessionRevisionCommitmentPayload(TypedDict):
    schema_version: str
    session_id: str
    session_revision: int
    previous_revision_commitment: str | None
    origin: SessionRevisionOriginPayload
    decision_count: int
    decision_records_hash: str
    event_count: int
    event_records_hash: str
    rng_history_count: int
    rng_history_hash: str
    rng_draw_count: int
    rng_state_hash: str
    checkpoint_hash: str
    authoritative_state_hash: str
    authoritative_session_hash: str
    started: bool
    closed: bool
    journal_entry_hash: str | None
    response_hash: str | None
    from_cursor: SessionRevisionCursorCommitmentPayload | None
    to_cursor: SessionRevisionCursorCommitmentPayload | None
    revision_commitment: str


@dataclass(frozen=True, slots=True)
class SessionRevisionOrigin:
    origin_kind: SessionRevisionOriginKind
    operation: str
    command_envelope: JsonValue | None = None
    envelope_fingerprint: str | None = None

    def __post_init__(self) -> None:
        if type(self.origin_kind) is not SessionRevisionOriginKind:
            raise SessionRevisionIntegrityError("Revision origin kind is invalid.")
        operation = _validate_operation(self.operation)
        object.__setattr__(self, "operation", operation)
        if self.origin_kind is SessionRevisionOriginKind.NONCOMMAND:
            try:
                SessionNonCommandOrigin(operation)
            except ValueError as exc:
                raise SessionRevisionIntegrityError(
                    "Revision noncommand origin is unsupported."
                ) from exc
            if self.command_envelope is not None or self.envelope_fingerprint is not None:
                raise SessionRevisionIntegrityError(
                    "Revision noncommand origin cannot contain a command envelope."
                )
            return
        if self.command_envelope is None:
            raise SessionRevisionIntegrityError(
                "Protocol-command revision origin requires its exact envelope."
            )
        envelope = SessionCommandEnvelope.from_payload(self.command_envelope)
        if operation != envelope.submission_kind.value:
            raise SessionRevisionIntegrityError("Revision command operation drifted.")
        fingerprint = _validate_sha256("Revision envelope fingerprint", self.envelope_fingerprint)
        if envelope.fingerprint() != fingerprint:
            raise SessionRevisionIntegrityError("Revision command envelope fingerprint drifted.")
        object.__setattr__(self, "command_envelope", envelope.to_payload())
        object.__setattr__(self, "envelope_fingerprint", fingerprint)

    @classmethod
    def noncommand(cls, origin: SessionNonCommandOrigin) -> SessionRevisionOrigin:
        if type(origin) is not SessionNonCommandOrigin:
            raise SessionRevisionIntegrityError("Revision noncommand origin is invalid.")
        return cls(
            origin_kind=SessionRevisionOriginKind.NONCOMMAND,
            operation=origin.value,
        )

    @classmethod
    def protocol_command(cls, envelope: SessionCommandEnvelope) -> SessionRevisionOrigin:
        if type(envelope) is not SessionCommandEnvelope:
            raise SessionRevisionIntegrityError("Revision command origin is invalid.")
        return cls(
            origin_kind=SessionRevisionOriginKind.PROTOCOL_COMMAND,
            operation=envelope.submission_kind.value,
            command_envelope=cast(JsonValue, envelope.to_payload()),
            envelope_fingerprint=envelope.fingerprint(),
        )

    @property
    def envelope(self) -> SessionCommandEnvelope | None:
        if self.command_envelope is None:
            return None
        return SessionCommandEnvelope.from_payload(self.command_envelope)

    def to_payload(self) -> SessionRevisionOriginPayload:
        return {
            "origin_kind": self.origin_kind.value,
            "operation": self.operation,
            "command_envelope": copy.deepcopy(self.command_envelope),
            "envelope_fingerprint": self.envelope_fingerprint,
        }

    @classmethod
    def from_payload(cls, payload: JsonValue) -> SessionRevisionOrigin:
        value = _object(
            payload,
            field_name="revision origin",
            expected_keys={
                "origin_kind",
                "operation",
                "command_envelope",
                "envelope_fingerprint",
            },
        )
        kind = value["origin_kind"]
        operation = value["operation"]
        fingerprint = value["envelope_fingerprint"]
        if type(kind) is not str or type(operation) is not str:
            raise SessionRevisionIntegrityError("Persisted revision origin field is invalid.")
        if fingerprint is not None and type(fingerprint) is not str:
            raise SessionRevisionIntegrityError("Persisted revision origin fingerprint is invalid.")
        try:
            origin_kind = SessionRevisionOriginKind(kind)
        except ValueError as exc:
            raise SessionRevisionIntegrityError(
                "Persisted revision origin kind is unsupported."
            ) from exc
        return cls(
            origin_kind=origin_kind,
            operation=operation,
            command_envelope=value["command_envelope"],
            envelope_fingerprint=fingerprint,
        )


@dataclass(frozen=True, slots=True)
class SessionRevisionCursorCommitment:
    token: str
    cursor: SessionCursor

    def __post_init__(self) -> None:
        if type(self.token) is not str or not self.token:
            raise SessionRevisionIntegrityError("Revision cursor token is invalid.")
        if type(self.cursor) is not SessionCursor:
            raise SessionRevisionIntegrityError("Revision cursor state is invalid.")

    def to_payload(self) -> SessionRevisionCursorCommitmentPayload:
        return {
            "token": self.token,
            "cursor": cast(JsonValue, self.cursor.to_payload()),
        }

    @classmethod
    def from_payload(cls, payload: JsonValue) -> SessionRevisionCursorCommitment:
        value = _object(
            payload,
            field_name="revision cursor commitment",
            expected_keys={"token", "cursor"},
        )
        token = value["token"]
        if type(token) is not str:
            raise SessionRevisionIntegrityError("Persisted revision cursor token is invalid.")
        return cls(token=token, cursor=SessionCursor.from_payload(value["cursor"]))


@dataclass(frozen=True, slots=True)
class SessionRevisionCommitment:
    session_id: str
    session_revision: int
    previous_revision_commitment: str | None
    origin: SessionRevisionOrigin
    decision_count: int
    decision_records_hash: str
    event_count: int
    event_records_hash: str
    rng_history_count: int
    rng_history_hash: str
    rng_draw_count: int
    rng_state_hash: str
    checkpoint_hash: str
    authoritative_state_hash: str
    authoritative_session_hash: str
    started: bool
    closed: bool
    journal_entry_hash: str | None = None
    response_hash: str | None = None
    from_cursor: SessionRevisionCursorCommitment | None = None
    to_cursor: SessionRevisionCursorCommitment | None = None
    revision_commitment: str = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "session_id",
            _REVISION_IDENTIFIER("Revision session_id", self.session_id),
        )
        if type(self.session_revision) is not int or self.session_revision < 0:
            raise SessionRevisionIntegrityError("Revision commitment index is invalid.")
        previous = self.previous_revision_commitment
        if self.session_revision == 0:
            if previous is not None:
                raise SessionRevisionIntegrityError(
                    "Initial revision commitment cannot have a predecessor."
                )
        else:
            _validate_sha256("Previous revision commitment", previous)
        if type(self.origin) is not SessionRevisionOrigin:
            raise SessionRevisionIntegrityError("Revision commitment origin is invalid.")
        for name, count_value in (
            ("decision_count", self.decision_count),
            ("event_count", self.event_count),
            ("rng_history_count", self.rng_history_count),
            ("rng_draw_count", self.rng_draw_count),
        ):
            if type(count_value) is not int or count_value < 0:
                raise SessionRevisionIntegrityError(f"Revision {name} is invalid.")
        for name, digest_value in (
            ("decision_records_hash", self.decision_records_hash),
            ("event_records_hash", self.event_records_hash),
            ("rng_history_hash", self.rng_history_hash),
            ("rng_state_hash", self.rng_state_hash),
            ("checkpoint_hash", self.checkpoint_hash),
            ("authoritative_state_hash", self.authoritative_state_hash),
            ("authoritative_session_hash", self.authoritative_session_hash),
        ):
            _validate_sha256(f"Revision {name}", digest_value)
        if type(self.started) is not bool or type(self.closed) is not bool:
            raise SessionRevisionIntegrityError("Revision authoritative session flags are invalid.")
        command_values = (
            self.journal_entry_hash,
            self.response_hash,
            self.from_cursor,
            self.to_cursor,
        )
        if any(value is not None for value in command_values):
            if any(value is None for value in command_values):
                raise SessionRevisionIntegrityError(
                    "Revision command response commitments must be complete."
                )
            if self.origin.origin_kind is not SessionRevisionOriginKind.PROTOCOL_COMMAND:
                raise SessionRevisionIntegrityError(
                    "Noncommand revision cannot contain response commitments."
                )
            _validate_sha256("Revision journal entry hash", self.journal_entry_hash)
            _validate_sha256("Revision response hash", self.response_hash)
            if (
                type(self.from_cursor) is not SessionRevisionCursorCommitment
                or type(self.to_cursor) is not SessionRevisionCursorCommitment
            ):
                raise SessionRevisionIntegrityError(
                    "Revision response cursor commitment is invalid."
                )
        object.__setattr__(
            self,
            "revision_commitment",
            _payload_hash(self._content_payload(), domain="revision-commitment"),
        )

    @property
    def is_finalized(self) -> bool:
        if self.origin.origin_kind is SessionRevisionOriginKind.NONCOMMAND:
            return True
        return self.journal_entry_hash is not None

    def bind_command_response(
        self,
        *,
        entry: SessionCommandJournalEntry,
        from_cursor: SessionRevisionCursorCommitment,
        to_cursor: SessionRevisionCursorCommitment,
    ) -> SessionRevisionCommitment:
        if not self.is_finalized and self.origin.envelope == entry.command_envelope:
            return replace(
                self,
                journal_entry_hash=_payload_hash(
                    cast(JsonValue, entry.to_persistence_payload()),
                    domain="command-journal-entry",
                ),
                response_hash=_payload_hash(
                    entry.response_payload,
                    domain="command-response",
                ),
                from_cursor=from_cursor,
                to_cursor=to_cursor,
            )
        raise SessionRevisionIntegrityError(
            "Revision command response does not match its pending origin."
        )

    def _content_payload(self) -> dict[str, JsonValue]:
        return {
            "schema_version": SESSION_REVISION_COMMITMENT_SCHEMA_VERSION,
            "session_id": self.session_id,
            "session_revision": self.session_revision,
            "previous_revision_commitment": self.previous_revision_commitment,
            "origin": cast(JsonValue, self.origin.to_payload()),
            "decision_count": self.decision_count,
            "decision_records_hash": self.decision_records_hash,
            "event_count": self.event_count,
            "event_records_hash": self.event_records_hash,
            "rng_history_count": self.rng_history_count,
            "rng_history_hash": self.rng_history_hash,
            "rng_draw_count": self.rng_draw_count,
            "rng_state_hash": self.rng_state_hash,
            "checkpoint_hash": self.checkpoint_hash,
            "authoritative_state_hash": self.authoritative_state_hash,
            "authoritative_session_hash": self.authoritative_session_hash,
            "started": self.started,
            "closed": self.closed,
            "journal_entry_hash": self.journal_entry_hash,
            "response_hash": self.response_hash,
            "from_cursor": (
                None if self.from_cursor is None else cast(JsonValue, self.from_cursor.to_payload())
            ),
            "to_cursor": (
                None if self.to_cursor is None else cast(JsonValue, self.to_cursor.to_payload())
            ),
        }

    def to_payload(self) -> SessionRevisionCommitmentPayload:
        return cast(
            SessionRevisionCommitmentPayload,
            {**self._content_payload(), "revision_commitment": self.revision_commitment},
        )

    @classmethod
    def from_payload(cls, payload: JsonValue) -> SessionRevisionCommitment:
        expected_keys = set(SessionRevisionCommitmentPayload.__required_keys__)
        value = _object(
            payload,
            field_name="revision commitment",
            expected_keys=expected_keys,
        )
        if value["schema_version"] != SESSION_REVISION_COMMITMENT_SCHEMA_VERSION:
            raise SessionRevisionIntegrityError(
                "Persisted revision commitment schema version drifted."
            )
        integer_fields = (
            "session_revision",
            "decision_count",
            "event_count",
            "rng_history_count",
            "rng_draw_count",
        )
        if any(type(value[name]) is not int for name in integer_fields):
            raise SessionRevisionIntegrityError(
                "Persisted revision commitment integer field is invalid."
            )
        if type(value["session_id"]) is not str:
            raise SessionRevisionIntegrityError(
                "Persisted revision commitment session identifier is invalid."
            )
        if type(value["started"]) is not bool or type(value["closed"]) is not bool:
            raise SessionRevisionIntegrityError(
                "Persisted revision commitment session flag is invalid."
            )
        optional_strings = (
            "previous_revision_commitment",
            "journal_entry_hash",
            "response_hash",
        )
        if any(
            value[name] is not None and type(value[name]) is not str for name in optional_strings
        ):
            raise SessionRevisionIntegrityError(
                "Persisted revision commitment optional digest is invalid."
            )
        digest_fields = (
            "decision_records_hash",
            "event_records_hash",
            "rng_history_hash",
            "rng_state_hash",
            "checkpoint_hash",
            "authoritative_state_hash",
            "authoritative_session_hash",
            "revision_commitment",
        )
        if any(type(value[name]) is not str for name in digest_fields):
            raise SessionRevisionIntegrityError("Persisted revision commitment digest is invalid.")
        commitment = cls(
            session_id=value["session_id"],
            session_revision=cast(int, value["session_revision"]),
            previous_revision_commitment=cast(str | None, value["previous_revision_commitment"]),
            origin=SessionRevisionOrigin.from_payload(value["origin"]),
            decision_count=cast(int, value["decision_count"]),
            decision_records_hash=cast(str, value["decision_records_hash"]),
            event_count=cast(int, value["event_count"]),
            event_records_hash=cast(str, value["event_records_hash"]),
            rng_history_count=cast(int, value["rng_history_count"]),
            rng_history_hash=cast(str, value["rng_history_hash"]),
            rng_draw_count=cast(int, value["rng_draw_count"]),
            rng_state_hash=cast(str, value["rng_state_hash"]),
            checkpoint_hash=cast(str, value["checkpoint_hash"]),
            authoritative_state_hash=cast(str, value["authoritative_state_hash"]),
            authoritative_session_hash=cast(str, value["authoritative_session_hash"]),
            started=value["started"],
            closed=value["closed"],
            journal_entry_hash=cast(str | None, value["journal_entry_hash"]),
            response_hash=cast(str | None, value["response_hash"]),
            from_cursor=_optional_cursor_commitment(value["from_cursor"]),
            to_cursor=_optional_cursor_commitment(value["to_cursor"]),
        )
        if commitment.revision_commitment != value["revision_commitment"]:
            raise SessionRevisionIntegrityError("Persisted revision commitment hash drifted.")
        return commitment


def build_revision_commitment(
    *,
    session_id: str,
    session_revision: int,
    previous_revision_commitment: str | None,
    origin: SessionRevisionOrigin,
    history: AdapterSessionHistoryPayload,
    authoritative_session_payload: JsonValue,
) -> SessionRevisionCommitment:
    validated = _validated_history(history)
    started, closed = _authoritative_session_flags(authoritative_session_payload)
    return SessionRevisionCommitment(
        session_id=session_id,
        session_revision=session_revision,
        previous_revision_commitment=previous_revision_commitment,
        origin=origin,
        decision_count=len(validated["decision_records"]),
        decision_records_hash=_payload_hash(
            validated["decision_records"], domain="decision-prefix"
        ),
        event_count=len(validated["event_records"]),
        event_records_hash=_payload_hash(validated["event_records"], domain="event-prefix"),
        rng_history_count=len(validated["rng_history"]),
        rng_history_hash=_payload_hash(
            cast(JsonValue, validated["rng_history"]), domain="rng-history-prefix"
        ),
        rng_draw_count=validated["rng_draw_count"],
        rng_state_hash=_rng_state_hash(validated),
        checkpoint_hash=validated["checkpoint_hash"],
        authoritative_state_hash=validated["authoritative_state_hash"],
        authoritative_session_hash=_payload_hash(
            authoritative_session_payload,
            domain="authoritative-session-state",
        ),
        started=started,
        closed=closed,
    )


def validate_history_prefix(
    commitment: SessionRevisionCommitment,
    history: AdapterSessionHistoryPayload,
) -> None:
    validated = _validated_history(history)
    decisions = validated["decision_records"]
    events = validated["event_records"]
    rng_history = validated["rng_history"]
    if (
        commitment.decision_count > len(decisions)
        or commitment.event_count > len(events)
        or commitment.rng_history_count > len(rng_history)
    ):
        raise SessionRevisionIntegrityError(
            "Revision commitment history count exceeds current authority."
        )
    if commitment.decision_records_hash != _payload_hash(
        cast(JsonValue, decisions[: commitment.decision_count]),
        domain="decision-prefix",
    ):
        raise SessionRevisionIntegrityError("Revision decision-history prefix drifted.")
    if commitment.event_records_hash != _payload_hash(
        cast(JsonValue, events[: commitment.event_count]),
        domain="event-prefix",
    ):
        raise SessionRevisionIntegrityError("Revision event-history prefix drifted.")
    if commitment.rng_history_hash != _payload_hash(
        cast(JsonValue, rng_history[: commitment.rng_history_count]),
        domain="rng-history-prefix",
    ):
        raise SessionRevisionIntegrityError("Revision RNG-history prefix drifted.")


def validate_exact_history(
    commitment: SessionRevisionCommitment,
    history: AdapterSessionHistoryPayload,
    *,
    authoritative_session_payload: JsonValue,
) -> None:
    validated = _validated_history(history)
    started, closed = _authoritative_session_flags(authoritative_session_payload)
    validate_history_prefix(commitment, validated)
    if (
        commitment.decision_count != len(validated["decision_records"])
        or commitment.event_count != len(validated["event_records"])
        or commitment.rng_history_count != len(validated["rng_history"])
        or commitment.rng_draw_count != validated["rng_draw_count"]
        or commitment.rng_state_hash != _rng_state_hash(validated)
        or commitment.checkpoint_hash != validated["checkpoint_hash"]
        or commitment.authoritative_state_hash != validated["authoritative_state_hash"]
        or commitment.authoritative_session_hash
        != _payload_hash(
            authoritative_session_payload,
            domain="authoritative-session-state",
        )
        or commitment.started is not started
        or commitment.closed is not closed
    ):
        raise SessionRevisionIntegrityError("Revision exact authoritative state drifted.")


def validate_command_binding(
    *,
    commitment: SessionRevisionCommitment,
    previous: SessionRevisionCommitment,
    entry: SessionCommandJournalEntry,
    decision_records: list[JsonValue],
) -> None:
    envelope = commitment.origin.envelope
    if envelope is None or envelope != entry.command_envelope:
        raise SessionRevisionIntegrityError("Revision command envelope drifted from journal.")
    if (
        commitment.origin.envelope_fingerprint != entry.envelope_fingerprint
        or commitment.journal_entry_hash
        != _payload_hash(
            cast(JsonValue, entry.to_persistence_payload()),
            domain="command-journal-entry",
        )
        or commitment.response_hash
        != _payload_hash(entry.response_payload, domain="command-response")
    ):
        raise SessionRevisionIntegrityError("Revision command journal commitment drifted.")
    response = _object(
        entry.response_payload,
        field_name="revision command response",
        expected_keys={
            "schema_version",
            "command_id",
            "outcome_code",
            "operation",
            "committed",
            "accepted",
            "session",
            "checkpoint",
            "event_range",
        },
    )
    event_range = _object(
        response["event_range"],
        field_name="revision command event range",
        expected_keys={"from_cursor", "to_cursor"},
    )
    if (
        commitment.from_cursor is None
        or commitment.to_cursor is None
        or event_range["from_cursor"] != commitment.from_cursor.token
        or event_range["to_cursor"] != commitment.to_cursor.token
    ):
        raise SessionRevisionIntegrityError("Revision response cursor commitment drifted.")
    delta = decision_records[previous.decision_count : commitment.decision_count]
    kind = envelope.submission_kind
    if kind in {
        SessionCommandSubmissionKind.START_SESSION,
        SessionCommandSubmissionKind.ADVANCE_SESSION,
        SessionCommandSubmissionKind.CLOSE_SESSION,
    }:
        if delta:
            raise SessionRevisionIntegrityError(
                "Lifecycle command unexpectedly consumed a player decision."
            )
        return
    if len(delta) != 1:
        raise SessionRevisionIntegrityError(
            "Decision command must commit exactly one authoritative decision record."
        )
    result = _decision_result(delta)
    if (
        result["request_id"] != envelope.request_id
        or result["result_id"] != envelope.result_id
        or result["actor_id"] != entry.authorization_context.player_id
    ):
        raise SessionRevisionIntegrityError("Revision command decision identity drifted.")
    if kind is SessionCommandSubmissionKind.FINITE_OPTION:
        if result["selected_option_id"] != envelope.option_id():
            raise SessionRevisionIntegrityError("Revision finite option drifted.")
    elif result["selected_option_id"] != PARAMETERIZED_DECISION_OPTION_ID or canonical_json(
        result["payload"]
    ) != canonical_json(envelope.parameterized_payload()):
        raise SessionRevisionIntegrityError("Revision parameterized payload drifted.")


def validate_origin_transition(
    *,
    commitment: SessionRevisionCommitment,
    previous: SessionRevisionCommitment | None,
    decision_records: list[JsonValue],
    is_final_revision: bool,
    session_closed: bool,
) -> None:
    """Bind every typed origin to the history transition it claims to represent."""

    operation = commitment.origin.operation
    if previous is None:
        if (
            commitment.session_revision != 0
            or commitment.origin.origin_kind is not SessionRevisionOriginKind.NONCOMMAND
            or operation != SessionNonCommandOrigin.SESSION_CREATED.value
            or commitment.closed
            or (is_final_revision and commitment.closed is not session_closed)
        ):
            raise SessionRevisionIntegrityError(
                "Initial revision must be the open session-creation transition."
            )
        return
    if operation == SessionNonCommandOrigin.SESSION_CREATED.value:
        raise SessionRevisionIntegrityError("Session creation can occur only at revision zero.")

    if previous.closed or (previous.started and not commitment.started):
        raise SessionRevisionIntegrityError(
            "Revision session flags moved backwards or continued after closure."
        )
    start_operations = {
        SessionNonCommandOrigin.LEGACY_ADVANCE_SESSION.value,
        SessionCommandSubmissionKind.START_SESSION.value,
    }
    if not previous.started and commitment.started:
        if operation not in start_operations:
            raise SessionRevisionIntegrityError(
                "Revision started the session without a start transition."
            )
    elif commitment.started is not previous.started:
        raise SessionRevisionIntegrityError("Revision session-start state drifted.")
    if (
        operation == SessionNonCommandOrigin.LEGACY_ADVANCE_SESSION.value
        and not previous.started
        and not commitment.started
    ):
        raise SessionRevisionIntegrityError("Initial legacy advance did not start the session.")
    if (
        commitment.origin.origin_kind is SessionRevisionOriginKind.PROTOCOL_COMMAND
        and operation
        in {
            SessionCommandSubmissionKind.ADVANCE_SESSION.value,
            SessionCommandSubmissionKind.FINITE_OPTION.value,
            SessionCommandSubmissionKind.PARAMETERIZED_PAYLOAD.value,
        }
        and not previous.started
    ):
        raise SessionRevisionIntegrityError(
            "Protocol active-session command preceded the start transition."
        )

    decision_delta = commitment.decision_count - previous.decision_count
    if decision_delta < 0:
        raise SessionRevisionIntegrityError("Revision decision history moved backwards.")
    if commitment.origin.origin_kind is SessionRevisionOriginKind.PROTOCOL_COMMAND:
        if operation in {
            SessionCommandSubmissionKind.FINITE_OPTION.value,
            SessionCommandSubmissionKind.PARAMETERIZED_PAYLOAD.value,
        }:
            if decision_delta != 1:
                raise SessionRevisionIntegrityError(
                    "Protocol decision revision must append exactly one decision."
                )
        elif decision_delta:
            raise SessionRevisionIntegrityError(
                "Protocol lifecycle revision unexpectedly appended a decision."
            )
    elif operation in {
        SessionNonCommandOrigin.LEGACY_FINITE_DECISION.value,
        SessionNonCommandOrigin.LEGACY_PARAMETERIZED_DECISION.value,
    }:
        if decision_delta != 1:
            raise SessionRevisionIntegrityError(
                "Legacy decision revision must append exactly one decision."
            )
        result = _decision_result(
            decision_records[previous.decision_count : commitment.decision_count]
        )
        selected_option_id = result["selected_option_id"]
        if operation == SessionNonCommandOrigin.LEGACY_FINITE_DECISION.value:
            if selected_option_id == PARAMETERIZED_DECISION_OPTION_ID:
                raise SessionRevisionIntegrityError(
                    "Legacy finite origin drifted to a parameterized decision."
                )
        elif selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
            raise SessionRevisionIntegrityError(
                "Legacy parameterized origin drifted to a finite decision."
            )
    elif decision_delta:
        raise SessionRevisionIntegrityError(
            "Non-decision revision unexpectedly appended a decision."
        )

    close_operations = {
        SessionNonCommandOrigin.SESSION_CLOSED.value,
        SessionCommandSubmissionKind.CLOSE_SESSION.value,
    }
    if operation in close_operations:
        if not is_final_revision or not session_closed or previous.closed or not commitment.closed:
            raise SessionRevisionIntegrityError(
                "Session-close origin must be the final closed revision."
            )
        _validate_close_preserves_engine_state(commitment=commitment, previous=previous)
    elif commitment.closed is not previous.closed:
        raise SessionRevisionIntegrityError(
            "Revision closed the session without a close transition."
        )
    elif is_final_revision and commitment.closed is not session_closed:
        raise SessionRevisionIntegrityError("Closed session is missing its final close transition.")
    if operation == SessionCommandSubmissionKind.START_SESSION.value and (
        previous.started
        or not commitment.started
        or commitment.session_revision != 1
        or previous.origin.operation != SessionNonCommandOrigin.SESSION_CREATED.value
    ):
        raise SessionRevisionIntegrityError(
            "Protocol session start must directly follow session creation."
        )


def _decision_result(delta: list[JsonValue]) -> dict[str, JsonValue]:
    if len(delta) != 1:
        raise SessionRevisionIntegrityError(
            "Decision transition must contain exactly one decision record."
        )
    record = _object(
        delta[0],
        field_name="revision decision record",
        expected_keys={"record_id", "request", "result"},
    )
    return _object(
        record["result"],
        field_name="revision decision result",
        expected_keys={
            "result_id",
            "request_id",
            "decision_type",
            "actor_id",
            "selected_option_id",
            "payload",
        },
    )


def _validate_close_preserves_engine_state(
    *,
    commitment: SessionRevisionCommitment,
    previous: SessionRevisionCommitment,
) -> None:
    current_engine_state = (
        commitment.decision_count,
        commitment.decision_records_hash,
        commitment.event_count,
        commitment.event_records_hash,
        commitment.rng_history_count,
        commitment.rng_history_hash,
        commitment.rng_draw_count,
        commitment.rng_state_hash,
        commitment.checkpoint_hash,
        commitment.authoritative_state_hash,
    )
    previous_engine_state = (
        previous.decision_count,
        previous.decision_records_hash,
        previous.event_count,
        previous.event_records_hash,
        previous.rng_history_count,
        previous.rng_history_hash,
        previous.rng_draw_count,
        previous.rng_state_hash,
        previous.checkpoint_hash,
        previous.authoritative_state_hash,
    )
    if current_engine_state != previous_engine_state:
        raise SessionRevisionIntegrityError(
            "Session-close transition changed engine-owned authoritative state."
        )


def _validated_history(
    history: AdapterSessionHistoryPayload,
) -> AdapterSessionHistoryPayload:
    if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        history, dict
    ) or set(history) != set(AdapterSessionHistoryPayload.__required_keys__):
        raise SessionRevisionIntegrityError("Adapter authoritative history fields are invalid.")
    decisions = history["decision_records"]
    events = history["event_records"]
    rng_seed = history["rng_seed"]
    rng_history = history["rng_history"]
    rng_draw_count = history["rng_draw_count"]
    if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        decisions, list
    ) or not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        events, list
    ):
        raise SessionRevisionIntegrityError("Adapter authoritative record history is invalid.")
    if type(rng_seed) is not str or not rng_seed:
        raise SessionRevisionIntegrityError("Adapter authoritative RNG seed is invalid.")
    if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
        rng_history, list
    ) or any(type(token) is not str or not token for token in rng_history):
        raise SessionRevisionIntegrityError("Adapter authoritative RNG history is invalid.")
    if type(rng_draw_count) is not int or rng_draw_count < 0:
        raise SessionRevisionIntegrityError("Adapter authoritative RNG draw count is invalid.")
    checkpoint_hash = _validate_sha256("Adapter checkpoint hash", history["checkpoint_hash"])
    state_hash = _validate_sha256(
        "Adapter authoritative state hash", history["authoritative_state_hash"]
    )
    return {
        "decision_records": cast(list[JsonValue], validate_json_value(decisions)),
        "event_records": cast(list[JsonValue], validate_json_value(events)),
        "rng_seed": rng_seed,
        "rng_history": list(rng_history),
        "rng_draw_count": rng_draw_count,
        "checkpoint_hash": checkpoint_hash,
        "authoritative_state_hash": state_hash,
    }


def _authoritative_session_flags(payload: JsonValue) -> tuple[bool, bool]:
    if not isinstance(payload, dict):
        raise SessionRevisionIntegrityError(
            "Revision authoritative session state must be an object."
        )
    started = payload.get("started")
    closed = payload.get("closed")
    if type(started) is not bool or type(closed) is not bool:
        raise SessionRevisionIntegrityError("Revision authoritative session flags are invalid.")
    return started, closed


def _rng_state_hash(history: AdapterSessionHistoryPayload) -> str:
    return _payload_hash(
        {
            "seed": history["rng_seed"],
            "history": list(history["rng_history"]),
            "draw_count": history["rng_draw_count"],
        },
        domain="rng-state",
    )


def _optional_cursor_commitment(
    value: JsonValue,
) -> SessionRevisionCursorCommitment | None:
    if value is None:
        return None
    return SessionRevisionCursorCommitment.from_payload(value)


def _object(
    payload: JsonValue,
    *,
    field_name: str,
    expected_keys: set[str],
) -> dict[str, JsonValue]:
    if not isinstance(payload, dict) or set(payload) != expected_keys:
        raise SessionRevisionIntegrityError(f"Persisted {field_name} fields are invalid.")
    return payload


def _validate_operation(value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise SessionRevisionIntegrityError("Revision operation is invalid.")
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise SessionRevisionIntegrityError(f"{field_name} must be a SHA-256 digest.")
    return value


def _payload_hash(payload: JsonValue, *, domain: str) -> str:
    validated = validate_json_value(copy.deepcopy(payload))
    digest = hashlib.sha256()
    digest.update(b"warhammer40k-core-v2-session-revision-v1\x00")
    digest.update(_REVISION_IDENTIFIER("Revision hash domain", domain).encode("ascii"))
    digest.update(b"\x00")
    digest.update(canonical_json(validated).encode("utf-8"))
    return digest.hexdigest()


__all__ = [
    "SESSION_REVISION_COMMITMENT_SCHEMA_VERSION",
    "SessionNonCommandOrigin",
    "SessionRevisionCommitment",
    "SessionRevisionCursorCommitment",
    "SessionRevisionIntegrityError",
    "SessionRevisionOrigin",
    "SessionRevisionOriginKind",
    "build_revision_commitment",
    "validate_command_binding",
    "validate_exact_history",
    "validate_history_prefix",
    "validate_origin_transition",
]
