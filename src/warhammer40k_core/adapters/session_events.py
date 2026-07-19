from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import secrets
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TypedDict

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventRecordPayload, JsonValue, canonical_json

CURSOR_TOKEN_VERSION = 1
CURSOR_IDENTIFIER_BYTES = 32
CURSOR_AUTHENTICATION_TAG_BYTES = 16
CURSOR_TOKEN_LENGTH = 64
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
    revision_retention_limit: int
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
    revision_retention_limit: int
    projection: JsonValue


@dataclass(frozen=True, slots=True)
class SessionCursor:
    session_id: str
    principal_id: str
    cursor_scope: str
    offset: int
    visible_sequence: int
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
        if type(self.visible_sequence) is not int or self.visible_sequence < 0:
            raise SessionEventProtocolError("Cursor visible sequence must be non-negative.")
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
            "q": self.visible_sequence,
            "r": self.session_revision,
            "h": self.projection_state_hash,
        }


def _new_cursor_registry() -> dict[str, SessionCursor]:
    return {}


@dataclass(frozen=True, slots=True)
class SessionCursorCodec:
    secret: bytes = field(default_factory=_new_cursor_secret)
    _cursor_by_token: dict[str, SessionCursor] = field(
        default_factory=_new_cursor_registry,
        init=False,
        repr=False,
        compare=False,
    )

    def __post_init__(self) -> None:
        if type(self.secret) is not bytes or len(self.secret) < 16:
            raise SessionEventProtocolError("Cursor secret must contain 16 bytes.")

    def issue(
        self,
        *,
        session_id: str,
        viewer: ViewerContext,
        offset: int,
        visible_sequence: int,
        session_revision: int,
        projection_state_hash: str,
        minimum_offset: int,
        minimum_revision: int,
    ) -> str:
        if type(viewer) is not ViewerContext:
            raise SessionEventProtocolError("Cursor issue requires ViewerContext.")
        cursor = SessionCursor(
            session_id=session_id,
            principal_id=viewer.principal_id,
            cursor_scope=viewer.cursor_scope,
            offset=offset,
            visible_sequence=visible_sequence,
            session_revision=session_revision,
            projection_state_hash=projection_state_hash,
        )
        event_floor = _validate_floor("minimum_offset", minimum_offset)
        revision_floor = _validate_floor("minimum_revision", minimum_revision)
        if cursor.offset < event_floor or cursor.session_revision < revision_floor:
            raise SessionEventProtocolError("Cannot issue an already-expired event cursor.")
        self._prune_expired(
            cursor=cursor,
            minimum_offset=event_floor,
            minimum_revision=revision_floor,
        )
        protected_state = canonical_json(cursor.to_payload()).encode("utf-8")
        identifier = hmac.new(
            self.secret,
            b"core-v2-session-cursor-state\x00" + protected_state,
            hashlib.sha256,
        ).digest()
        authentication_tag = hmac.new(
            self.secret,
            b"core-v2-session-cursor-auth\x00" + identifier,
            hashlib.sha256,
        ).digest()[:CURSOR_AUTHENTICATION_TAG_BYTES]
        token = _urlsafe_encode(identifier + authentication_tag)
        existing = self._cursor_by_token.get(token)
        if existing is not None and existing != cursor:
            raise SessionEventProtocolError("Opaque cursor identifier collision detected.")
        self._cursor_by_token[token] = cursor
        return token

    def decode(self, token: str) -> SessionCursor:
        if type(token) is not str or token != token.strip():
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        if len(token) != CURSOR_TOKEN_LENGTH or any(
            character not in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-"
            for character in token
        ):
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        protected_identifier = _urlsafe_decode(token)
        identifier = protected_identifier[:CURSOR_IDENTIFIER_BYTES]
        authentication_tag = protected_identifier[CURSOR_IDENTIFIER_BYTES:]
        expected_tag = hmac.new(
            self.secret,
            b"core-v2-session-cursor-auth\x00" + identifier,
            hashlib.sha256,
        ).digest()[:CURSOR_AUTHENTICATION_TAG_BYTES]
        if not hmac.compare_digest(authentication_tag, expected_tag):
            raise CursorValidationError(CursorResyncReason.MALFORMED)
        cursor = self._cursor_by_token.get(token)
        if cursor is None:
            raise CursorValidationError(CursorResyncReason.EXPIRED)
        return cursor

    def finalize_session(self, session_id: str) -> None:
        session = _validate_identifier("session_id", session_id)
        latest_token_by_scope: dict[tuple[str, str], str] = {}
        latest_position_by_scope: dict[tuple[str, str], tuple[int, int, int]] = {}
        for token, cursor in self._cursor_by_token.items():
            if cursor.session_id != session:
                continue
            scope = (cursor.principal_id, cursor.cursor_scope)
            position = (cursor.session_revision, cursor.offset, cursor.visible_sequence)
            if position >= latest_position_by_scope.get(scope, (-1, -1, -1)):
                latest_position_by_scope[scope] = position
                latest_token_by_scope[scope] = token
        retained_tokens = set(latest_token_by_scope.values())
        stale_tokens = [
            token
            for token, cursor in self._cursor_by_token.items()
            if cursor.session_id == session and token not in retained_tokens
        ]
        for token in stale_tokens:
            del self._cursor_by_token[token]

    def registered_cursor_count(self, *, session_id: str | None = None) -> int:
        if session_id is None:
            return len(self._cursor_by_token)
        session = _validate_identifier("session_id", session_id)
        return sum(cursor.session_id == session for cursor in self._cursor_by_token.values())

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

    def _prune_expired(
        self,
        *,
        cursor: SessionCursor,
        minimum_offset: int,
        minimum_revision: int,
    ) -> None:
        stale_tokens = [
            token
            for token, retained in self._cursor_by_token.items()
            if retained.session_id == cursor.session_id
            and (
                retained.session_revision < minimum_revision
                or (
                    retained.principal_id == cursor.principal_id
                    and (
                        retained.cursor_scope != cursor.cursor_scope
                        or retained.offset < minimum_offset
                    )
                )
            )
        ]
        for token in stale_tokens:
            del self._cursor_by_token[token]


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
    try:
        decoded = base64.b64decode(value, altchars=b"-_", validate=True)
    except binascii.Error as exc:
        raise CursorValidationError(CursorResyncReason.MALFORMED) from exc
    expected_length = CURSOR_IDENTIFIER_BYTES + CURSOR_AUTHENTICATION_TAG_BYTES
    if len(decoded) != expected_length:
        raise CursorValidationError(CursorResyncReason.MALFORMED)
    return decoded


def _validate_floor(name: str, value: object) -> int:
    if type(value) is not int or value < 0:
        raise SessionEventProtocolError(f"Cursor {name} must be non-negative.")
    return value


def _validate_sha256(value: object) -> str:
    digest = _validate_identifier("projection_state_hash", value)
    if len(digest) != 64 or any(character not in "0123456789abcdef" for character in digest):
        raise SessionEventProtocolError("Projection state hash must be a SHA-256 digest.")
    return digest


_validate_identifier = IdentifierValidator(SessionEventProtocolError)
