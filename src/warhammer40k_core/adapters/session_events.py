from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import secrets
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventRecordPayload, JsonValue, canonical_json

CURSOR_TOKEN_VERSION = 1
DEFAULT_EVENT_PAGE_LIMIT = 100
MAX_EVENT_PAGE_LIMIT = 500
DEFAULT_EVENT_RETENTION_LIMIT = 4096


def _new_cursor_secret() -> bytes:
    return secrets.token_bytes(32)


class SessionEventProtocolError(ValueError):
    """Raised when session cursor or event synchronization state is invalid."""


class CursorResyncReason(StrEnum):
    MALFORMED = "malformed"
    EXPIRED = "expired"
    AHEAD = "ahead"
    WRONG_SESSION = "wrong_session"
    WRONG_VIEWER = "wrong_viewer"
    REVISION_MISMATCH = "revision_mismatch"
    PROJECTION_HASH_MISMATCH = "projection_hash_mismatch"


class CursorValidationError(SessionEventProtocolError):
    def __init__(self, reason: CursorResyncReason) -> None:
        if type(reason) is not CursorResyncReason:
            raise SessionEventProtocolError("Cursor validation reason is invalid.")
        self.reason = reason
        super().__init__("Event cursor requires projection resynchronization.")


class SequencedEventPayload(TypedDict):
    sequence_number: int
    event_id: str
    event_type: str
    payload: JsonValue


class SessionEventDeltaPayload(TypedDict):
    schema_version: str
    session_id: str
    game_id: str
    visibility_role: str
    from_revision: int
    to_revision: int
    projection_state_hash: str
    supplied_cursor: str
    next_cursor: str
    has_more: bool
    resync_required: bool
    resync_reason: str | None
    command_id: str | None
    retention_limit: int
    events: list[SequencedEventPayload]


class SessionProjectionPayload(TypedDict):
    schema_version: str
    session_id: str
    game_id: str
    session_revision: int
    visibility_role: str
    projection_state_hash: str
    event_cursor: str
    retention_limit: int
    projection: JsonValue


@dataclass(frozen=True, slots=True)
class SessionCursor:
    session_id: str
    principal_id: str
    cursor_scope: str
    offset: int
    session_revision: int
    projection_state_hash: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "session_id", _validate_identifier("session_id", self.session_id))
        object.__setattr__(
            self,
            "principal_id",
            _validate_identifier("principal_id", self.principal_id),
        )
        object.__setattr__(
            self,
            "cursor_scope",
            _validate_identifier("cursor_scope", self.cursor_scope),
        )
        if type(self.offset) is not int or self.offset < 0:
            raise SessionEventProtocolError("Cursor offset must be non-negative.")
        if type(self.session_revision) is not int or self.session_revision < 0:
            raise SessionEventProtocolError("Cursor revision must be non-negative.")
        object.__setattr__(
            self,
            "projection_state_hash",
            _validate_sha256(self.projection_state_hash),
        )

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "v": CURSOR_TOKEN_VERSION,
            "s": self.session_id,
            "p": self.principal_id,
            "c": self.cursor_scope,
            "o": self.offset,
            "r": self.session_revision,
            "h": self.projection_state_hash,
        }


@dataclass(frozen=True, slots=True)
class SessionCursorCodec:
    secret: bytes = field(default_factory=_new_cursor_secret)

    def __post_init__(self) -> None:
        if type(self.secret) is not bytes or len(self.secret) < 16:
            raise SessionEventProtocolError("Cursor signing secret must contain 16 bytes.")

    def issue(
        self,
        *,
        session_id: str,
        viewer: ViewerContext,
        offset: int,
        session_revision: int,
        projection_state_hash: str,
    ) -> str:
        if type(viewer) is not ViewerContext:
            raise SessionEventProtocolError("Cursor issue requires ViewerContext.")
        cursor = SessionCursor(
            session_id=session_id,
            principal_id=viewer.principal_id,
            cursor_scope=viewer.cursor_scope,
            offset=offset,
            session_revision=session_revision,
            projection_state_hash=projection_state_hash,
        )
        encoded_payload = _urlsafe_encode(canonical_json(cursor.to_payload()).encode("utf-8"))
        signature = hmac.new(self.secret, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        return f"{encoded_payload}.{_urlsafe_encode(signature)}"

    def decode(self, token: str) -> SessionCursor:
        if (
            type(token) is not str
            or not token.strip()
            or len(token) > 2048
            or token.count(".") != 1
        ):
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        encoded_payload, encoded_signature = token.strip().split(".")
        expected_signature = hmac.new(
            self.secret,
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        try:
            supplied_signature = _urlsafe_decode(encoded_signature)
        except (binascii.Error, ValueError) as exc:
            raise CursorValidationError(CursorResyncReason.MALFORMED) from exc
        if not hmac.compare_digest(expected_signature, supplied_signature):
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        try:
            decoded = _urlsafe_decode(encoded_payload).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
            raise CursorValidationError(CursorResyncReason.MALFORMED) from exc
        try:
            decoded_payload: object = json.loads(decoded)
        except json.JSONDecodeError as exc:
            raise CursorValidationError(CursorResyncReason.MALFORMED) from exc
        if not isinstance(decoded_payload, dict):
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        payload = cast(dict[str, object], decoded_payload)
        if set(payload) != {"v", "s", "p", "c", "o", "r", "h"}:
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        if payload["v"] != CURSOR_TOKEN_VERSION:
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        try:
            return SessionCursor(
                session_id=cast(str, payload["s"]),
                principal_id=cast(str, payload["p"]),
                cursor_scope=cast(str, payload["c"]),
                offset=cast(int, payload["o"]),
                session_revision=cast(int, payload["r"]),
                projection_state_hash=cast(str, payload["h"]),
            )
        except SessionEventProtocolError as exc:
            raise CursorValidationError(CursorResyncReason.MALFORMED) from exc

    def validate_binding(
        self,
        cursor: SessionCursor,
        *,
        session_id: str,
        viewer: ViewerContext,
    ) -> None:
        if cursor.session_id != session_id:
            raise CursorValidationError(CursorResyncReason.WRONG_SESSION)
        if cursor.principal_id != viewer.principal_id or cursor.cursor_scope != viewer.cursor_scope:
            raise CursorValidationError(CursorResyncReason.WRONG_VIEWER)


def sequenced_events(
    records: list[EventRecordPayload],
    *,
    first_sequence_number: int,
) -> list[SequencedEventPayload]:
    if type(first_sequence_number) is not int or first_sequence_number < 1:
        raise SessionEventProtocolError("First event sequence number must be positive.")
    return [
        {
            "sequence_number": first_sequence_number + index,
            "event_id": record["event_id"],
            "event_type": record["event_type"],
            "payload": record["payload"],
        }
        for index, record in enumerate(records)
    ]


def validate_page_limit(value: int) -> int:
    if type(value) is not int or not 1 <= value <= MAX_EVENT_PAGE_LIMIT:
        raise SessionEventProtocolError(
            f"Event page limit must be between 1 and {MAX_EVENT_PAGE_LIMIT}."
        )
    return value


def validate_retention_limit(value: int) -> int:
    if type(value) is not int or value < 1:
        raise SessionEventProtocolError("Event retention limit must be positive.")
    return value


def retention_floor(*, event_count: int, retention_limit: int) -> int:
    if type(event_count) is not int or event_count < 0:
        raise SessionEventProtocolError("Event count must be non-negative.")
    limit = validate_retention_limit(retention_limit)
    return max(0, event_count - limit)


def _urlsafe_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _urlsafe_decode(value: str) -> bytes:
    padding = "=" * (-len(value) % 4)
    return base64.urlsafe_b64decode((value + padding).encode("ascii"))


def _validate_sha256(value: object) -> str:
    digest = _validate_identifier("projection_state_hash", value)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SessionEventProtocolError("Projection state hash must be a SHA-256 digest.")
    return digest


_validate_identifier = IdentifierValidator(SessionEventProtocolError)
