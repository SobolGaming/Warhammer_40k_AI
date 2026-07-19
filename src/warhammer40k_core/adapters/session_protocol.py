from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.command_protocol import (
    SessionCommandJournalEntry,
    SessionCommandOutcomeCode,
)
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.external_contract import (
    EXTERNAL_CONTRACT_VERSION,
    SESSION_COMMAND_OUTCOME_SCHEMA_VERSION,
    SESSION_COMMAND_RESULT_SCHEMA_VERSION,
    SESSION_METADATA_SCHEMA_VERSION,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind

ENGINE_BUILD_ID = f"warhammer40k-core-v2:{ENGINE_VERSION}"
MAX_REVISION_SNAPSHOTS = 128

type OperationalClock = Callable[[], datetime]


def _new_command_journal() -> dict[str, SessionCommandJournalEntry]:
    return {}


def _new_revision_snapshots() -> dict[int, SessionRevisionSnapshot]:
    return {}


class SessionProtocolError(ValueError):
    """Raised when server-owned session protocol state is invalid."""


class SessionState(StrEnum):
    CREATED = "created"
    ACTIVE = "active"
    TERMINAL = "terminal"
    CLOSED = "closed"


class TerminalReasonPayload(TypedDict):
    code: str
    message: str


class VisibilityPolicyPayload(TypedDict):
    role: str
    player_id: str | None
    delay_revisions: int
    may_mutate_lifecycle: bool
    may_submit_decision: bool
    omniscient: bool


class SessionMetadataPayload(TypedDict):
    schema_version: str
    session_id: str
    game_id: str
    session_state: str
    session_revision: int
    ruleset_id: JsonValue
    catalog_id: str
    source_package_id: str
    source_hash: str
    projection_state_hash: str
    event_cursor: str
    lifecycle_status: JsonValue
    terminal_reason: TerminalReasonPayload | None
    created_at: str
    last_activity_at: str
    visibility: VisibilityPolicyPayload
    server_contract_version: str
    engine_version: str
    engine_build_id: str


class SessionCheckpointPayload(TypedDict):
    visibility_role: str
    viewer_player_id: str | None
    session_revision: int
    projection_state_hash: str
    event_cursor: str


class SessionEventRangePayload(TypedDict):
    from_cursor: str
    to_cursor: str


class SessionCommandResultPayload(TypedDict):
    schema_version: str
    operation: str
    committed: bool
    accepted: bool
    session: SessionMetadataPayload
    checkpoint: SessionCheckpointPayload
    event_range: SessionEventRangePayload


class SessionCommandOutcomePayload(SessionCommandResultPayload):
    command_id: str
    outcome_code: str


@dataclass(frozen=True, slots=True)
class SessionRevisionSnapshot:
    session_revision: int
    adapter_session: AdapterGameSession
    lifecycle_status: LifecycleStatus
    event_count: int
    last_activity_at: str
    started: bool
    closed: bool

    def __post_init__(self) -> None:
        if type(self.session_revision) is not int or self.session_revision < 0:
            raise SessionProtocolError("Snapshot revision must be non-negative.")
        adapter_session: object = self.adapter_session
        if not isinstance(  # pyright: ignore[reportUnnecessaryIsInstance]
            adapter_session, AdapterGameSession
        ):
            raise SessionProtocolError("Snapshot requires AdapterGameSession.")
        if type(self.lifecycle_status) is not LifecycleStatus:
            raise SessionProtocolError("Snapshot lifecycle status is invalid.")
        if type(self.event_count) is not int or self.event_count < 0:
            raise SessionProtocolError("Snapshot event count must be non-negative.")
        _validate_timestamp("snapshot last_activity_at", self.last_activity_at)
        if type(self.started) is not bool or type(self.closed) is not bool:
            raise SessionProtocolError("Snapshot state flags must be bool values.")

    @property
    def state(self) -> SessionState:
        if self.closed:
            return SessionState.CLOSED
        if self.lifecycle_status.status_kind is LifecycleStatusKind.TERMINAL:
            return SessionState.TERMINAL
        if self.started:
            return SessionState.ACTIVE
        return SessionState.CREATED


@dataclass(slots=True)
class AuthoritativeSession:
    session_id: str
    game_id: str
    adapter_session: AdapterGameSession
    player_ids: tuple[str, ...]
    ruleset_id: JsonValue
    catalog_id: str
    source_package_id: str
    source_hash: str
    lifecycle_status: LifecycleStatus
    created_at: str
    last_activity_at: str
    session_revision: int = 0
    started: bool = False
    closed: bool = False
    command_journal: dict[str, SessionCommandJournalEntry] = field(
        default_factory=_new_command_journal
    )
    revision_snapshots: dict[int, SessionRevisionSnapshot] = field(
        default_factory=_new_revision_snapshots
    )

    def __post_init__(self) -> None:
        self.session_id = _validate_identifier("session_id", self.session_id)
        self.game_id = _validate_identifier("game_id", self.game_id)
        self.player_ids = _validated_player_ids(self.player_ids)
        self.ruleset_id = validate_json_value(self.ruleset_id)
        self.catalog_id = _validate_identifier("catalog_id", self.catalog_id)
        self.source_package_id = _validate_identifier(
            "source_package_id",
            self.source_package_id,
        )
        self.source_hash = _validate_sha256("source_hash", self.source_hash)
        if type(self.lifecycle_status) is not LifecycleStatus:
            raise SessionProtocolError("Session lifecycle status is invalid.")
        self.created_at = _validate_timestamp("created_at", self.created_at)
        self.last_activity_at = _validate_timestamp("last_activity_at", self.last_activity_at)
        if _parse_timestamp(self.last_activity_at) < _parse_timestamp(self.created_at):
            raise SessionProtocolError("Session activity timestamp predates creation.")
        if type(self.session_revision) is not int or self.session_revision < 0:
            raise SessionProtocolError("Session revision must be non-negative.")
        if type(self.started) is not bool or type(self.closed) is not bool:
            raise SessionProtocolError("Session state flags must be bool values.")
        self._validate_journal()
        self._validate_snapshots()

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        adapter_session: AdapterGameSession,
        config: GameConfig,
        lifecycle_status: LifecycleStatus,
        created_at: str,
    ) -> AuthoritativeSession:
        if type(config) is not GameConfig:
            raise SessionProtocolError("Session creation requires GameConfig.")
        catalog_view = adapter_session.rules_catalog_view()
        if catalog_view["catalog_id"] != config.army_catalog.catalog_id:
            raise SessionProtocolError("Session catalog identity drifted during creation.")
        if catalog_view["source_package_id"] != config.army_catalog.source_package_id:
            raise SessionProtocolError("Session source package drifted during creation.")
        record = cls(
            session_id=session_id,
            game_id=config.game_id,
            adapter_session=adapter_session,
            player_ids=config.player_ids,
            ruleset_id=validate_json_value(config.ruleset_descriptor.ruleset_id.to_payload()),
            catalog_id=catalog_view["catalog_id"],
            source_package_id=catalog_view["source_package_id"],
            source_hash=catalog_view["source_hash"],
            lifecycle_status=lifecycle_status,
            created_at=created_at,
            last_activity_at=created_at,
        )
        record.capture_current_revision()
        return record

    @property
    def state(self) -> SessionState:
        return self.current_snapshot().state

    def touch(self, timestamp: str) -> None:
        activity = _validate_timestamp("last_activity_at", timestamp)
        if _parse_timestamp(activity) < _parse_timestamp(self.last_activity_at):
            raise SessionProtocolError("Session activity timestamp cannot move backwards.")
        self.last_activity_at = activity

    def fork_for_command(self) -> AuthoritativeSession:
        return replace(
            self,
            adapter_session=self.adapter_session.fork(),
            command_journal=dict(self.command_journal),
            revision_snapshots=dict(self.revision_snapshots),
        )

    def command_entry(self, command_id: str) -> SessionCommandJournalEntry | None:
        return self.command_journal.get(_validate_identifier("command_id", command_id))

    def record_command(self, entry: SessionCommandJournalEntry) -> None:
        if type(entry) is not SessionCommandJournalEntry:
            raise SessionProtocolError("Session command journal requires a typed entry.")
        if entry.command_id in self.command_journal:
            raise SessionProtocolError("Session command_id was already recorded.")
        self.command_journal[entry.command_id] = entry

    def commit_status(self, status: LifecycleStatus, *, timestamp: str) -> None:
        if type(status) is not LifecycleStatus:
            raise SessionProtocolError("Committed session status is invalid.")
        self.lifecycle_status = status
        self.session_revision += 1
        self.touch(timestamp)
        self.capture_current_revision()

    def observe_uncommitted_status(self, status: LifecycleStatus, *, timestamp: str) -> None:
        if type(status) is not LifecycleStatus:
            raise SessionProtocolError("Uncommitted session status is invalid.")
        self.lifecycle_status = status
        self.touch(timestamp)
        self.capture_current_revision(replace_existing=True)

    def close(self, *, timestamp: str) -> None:
        self.closed = True
        self.session_revision += 1
        self.touch(timestamp)
        self.capture_current_revision()

    def capture_current_revision(self, *, replace_existing: bool = False) -> None:
        if self.session_revision in self.revision_snapshots and not replace_existing:
            raise SessionProtocolError("Session revision snapshot already exists.")
        event_count = self.adapter_session.event_record_count()
        self.revision_snapshots[self.session_revision] = SessionRevisionSnapshot(
            session_revision=self.session_revision,
            adapter_session=self.adapter_session.fork(),
            lifecycle_status=self.lifecycle_status,
            event_count=event_count,
            last_activity_at=self.last_activity_at,
            started=self.started,
            closed=self.closed,
        )
        self._prune_snapshots()

    def current_snapshot(self) -> SessionRevisionSnapshot:
        return self.snapshot(self.session_revision)

    def snapshot(self, revision: int) -> SessionRevisionSnapshot:
        if type(revision) is not int or revision < 0:
            raise SessionProtocolError("Requested snapshot revision is invalid.")
        snapshot = self.revision_snapshots.get(revision)
        if snapshot is None:
            raise SessionProtocolError("Requested session revision is no longer retained.")
        return snapshot

    def snapshot_for_viewer(self, viewer: ViewerContext) -> SessionRevisionSnapshot:
        if type(viewer) is not ViewerContext:
            raise SessionProtocolError("Session snapshot requires ViewerContext.")
        target_revision = max(0, self.session_revision - viewer.policy.delay_revisions)
        return self.snapshot(target_revision)

    def snapshot_at_event_offset(
        self,
        *,
        offset: int,
        maximum_revision: int,
    ) -> SessionRevisionSnapshot:
        candidates = [
            snapshot
            for snapshot in self.revision_snapshots.values()
            if snapshot.session_revision <= maximum_revision and snapshot.event_count <= offset
        ]
        if not candidates:
            raise SessionProtocolError("Event offset predates retained revision snapshots.")
        return max(candidates, key=lambda snapshot: snapshot.session_revision)

    def metadata_payload(
        self,
        *,
        snapshot: SessionRevisionSnapshot,
        viewer: ViewerContext,
        lifecycle_status: JsonValue,
        projection_state_hash: str,
        event_cursor: str,
    ) -> SessionMetadataPayload:
        projection_hash = _validate_sha256("projection_state_hash", projection_state_hash)
        cursor = _validate_cursor(event_cursor)
        payload: SessionMetadataPayload = {
            "schema_version": SESSION_METADATA_SCHEMA_VERSION,
            "session_id": self.session_id,
            "game_id": self.game_id,
            "session_state": snapshot.state.value,
            "session_revision": snapshot.session_revision,
            "ruleset_id": self.ruleset_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "source_hash": self.source_hash,
            "projection_state_hash": projection_hash,
            "event_cursor": cursor,
            "lifecycle_status": validate_json_value(lifecycle_status),
            "terminal_reason": self._terminal_reason(snapshot),
            "created_at": self.created_at,
            "last_activity_at": snapshot.last_activity_at,
            "visibility": {
                "role": viewer.role.value,
                "player_id": viewer.viewer_player_id,
                "delay_revisions": viewer.policy.delay_revisions,
                "may_mutate_lifecycle": viewer.policy.may_mutate_lifecycle,
                "may_submit_decision": viewer.policy.may_submit_decision,
                "omniscient": viewer.policy.omniscient,
            },
            "server_contract_version": EXTERNAL_CONTRACT_VERSION,
            "engine_version": ENGINE_VERSION,
            "engine_build_id": ENGINE_BUILD_ID,
        }
        validate_json_value(cast(JsonValue, payload))
        return payload

    def _terminal_reason(
        self,
        snapshot: SessionRevisionSnapshot,
    ) -> TerminalReasonPayload | None:
        if snapshot.closed:
            return {"code": "session_closed", "message": "Session was closed."}
        if snapshot.lifecycle_status.status_kind is LifecycleStatusKind.TERMINAL:
            message = snapshot.lifecycle_status.message
            if message is None:
                raise SessionProtocolError("Terminal lifecycle status requires a message.")
            return {"code": "game_complete", "message": message}
        return None

    def _prune_snapshots(self) -> None:
        if len(self.revision_snapshots) <= MAX_REVISION_SNAPSHOTS:
            return
        retained_revisions = sorted(self.revision_snapshots)[-MAX_REVISION_SNAPSHOTS:]
        self.revision_snapshots = {
            revision: self.revision_snapshots[revision] for revision in retained_revisions
        }

    def _validate_journal(self) -> None:
        if type(self.command_journal) is not dict:
            raise SessionProtocolError("Session command journal must be a dictionary.")
        for command_id, entry in self.command_journal.items():
            if type(entry) is not SessionCommandJournalEntry or entry.command_id != command_id:
                raise SessionProtocolError("Session command journal entry is invalid.")

    def _validate_snapshots(self) -> None:
        if type(self.revision_snapshots) is not dict:
            raise SessionProtocolError("Session revision snapshots must be a dictionary.")
        for revision, snapshot in self.revision_snapshots.items():
            if (
                type(snapshot) is not SessionRevisionSnapshot
                or snapshot.session_revision != revision
            ):
                raise SessionProtocolError("Session revision snapshot is invalid.")


def utc_operational_clock() -> datetime:
    return datetime.now(UTC)


def operational_timestamp(clock: OperationalClock) -> str:
    if not callable(clock):
        raise SessionProtocolError("Operational clock must be callable.")
    value = clock()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SessionProtocolError("Operational clock must return an aware datetime.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def session_command_result_payload(
    *,
    operation: str,
    committed: bool,
    accepted: bool,
    session: SessionMetadataPayload,
    checkpoint: SessionCheckpointPayload,
    from_cursor: str,
) -> SessionCommandResultPayload:
    operation_id = _validate_identifier("operation", operation)
    if type(committed) is not bool or type(accepted) is not bool:
        raise SessionProtocolError("Session command flags must be bool values.")
    if accepted and not committed:
        raise SessionProtocolError("Accepted session command must be committed.")
    payload: SessionCommandResultPayload = {
        "schema_version": SESSION_COMMAND_RESULT_SCHEMA_VERSION,
        "operation": operation_id,
        "committed": committed,
        "accepted": accepted,
        "session": session,
        "checkpoint": checkpoint,
        "event_range": {
            "from_cursor": _validate_cursor(from_cursor),
            "to_cursor": _validate_cursor(checkpoint["event_cursor"]),
        },
    }
    validate_json_value(cast(JsonValue, payload))
    return payload


def session_command_outcome_payload(
    *,
    command_id: str,
    outcome_code: SessionCommandOutcomeCode,
    operation: str,
    committed: bool,
    accepted: bool,
    session: SessionMetadataPayload,
    checkpoint: SessionCheckpointPayload,
    from_cursor: str,
) -> SessionCommandOutcomePayload:
    if type(outcome_code) is not SessionCommandOutcomeCode:
        raise SessionProtocolError("Session command outcome code is invalid.")
    base = session_command_result_payload(
        operation=operation,
        committed=committed,
        accepted=accepted,
        session=session,
        checkpoint=checkpoint,
        from_cursor=from_cursor,
    )
    payload: SessionCommandOutcomePayload = {
        **base,
        "schema_version": SESSION_COMMAND_OUTCOME_SCHEMA_VERSION,
        "command_id": _validate_identifier("command_id", command_id),
        "outcome_code": outcome_code.value,
    }
    validate_json_value(cast(JsonValue, payload))
    return payload


def _validated_player_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple or not values:
        raise SessionProtocolError("Session player IDs must be a non-empty tuple.")
    validated = tuple(_validate_identifier("player_id", value) for value in values)
    if len(validated) != len(set(validated)):
        raise SessionProtocolError("Session player IDs must be unique.")
    return validated


def _validate_sha256(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    if len(identifier) != 64 or any(
        character not in "0123456789abcdef" for character in identifier
    ):
        raise SessionProtocolError(f"{field_name} must be a lowercase SHA-256 digest.")
    return identifier


def _validate_cursor(value: object) -> str:
    if type(value) is not str or not value.strip() or len(value) > 2048:
        raise SessionProtocolError("Session event cursor is invalid.")
    return value.strip()


def _validate_timestamp(field_name: str, value: object) -> str:
    if type(value) is not str or not value.endswith("Z"):
        raise SessionProtocolError(f"{field_name} must be a UTC timestamp.")
    _parse_timestamp(value)
    return value


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SessionProtocolError("Session timestamp is invalid.") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise SessionProtocolError("Session timestamp must be timezone-aware.")
    return parsed.astimezone(UTC)


_validate_identifier = IdentifierValidator(SessionProtocolError)
