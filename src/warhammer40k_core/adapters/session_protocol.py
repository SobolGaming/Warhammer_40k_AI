from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from enum import StrEnum
from typing import TypedDict, cast

from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core.adapters.access_control import ROLE_POLICY_BY_ROLE, ViewerContext
from warhammer40k_core.adapters.command_protocol import (
    SessionCommandJournalEntry,
    SessionCommandOutcomeCode,
    SessionCommandSubmissionKind,
)
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.external_contract import (
    EXTERNAL_CONTRACT_VERSION,
    SESSION_COMMAND_OUTCOME_SCHEMA_VERSION,
    SESSION_COMMAND_RESULT_SCHEMA_VERSION,
    SESSION_METADATA_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.redaction import redacted_lifecycle_status
from warhammer40k_core.adapters.session_events import DEFAULT_EVENT_RETENTION_LIMIT
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.phase import (
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    LifecycleStatusPayload,
)

ENGINE_BUILD_ID = f"warhammer40k-core-v2:{ENGINE_VERSION}"
DEFAULT_REVISION_RETENTION_LIMIT = 128

type OperationalClock = Callable[[], datetime]
type SessionRecoveryFactory = Callable[[JsonValue], AdapterGameSession]


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
    ruleset_descriptor_hash: str
    rules_overlay_ids: list[str]
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

    def to_persistence_payload(self) -> dict[str, JsonValue]:
        return {
            "session_revision": self.session_revision,
            "adapter_session": self.adapter_session.to_persistence_payload(),
            "lifecycle_status": cast(JsonValue, self.lifecycle_status.to_payload()),
            "event_count": self.event_count,
            "last_activity_at": self.last_activity_at,
            "started": self.started,
            "closed": self.closed,
        }

    @classmethod
    def from_persistence_payload(
        cls,
        payload: JsonValue,
        *,
        session_recovery_factory: SessionRecoveryFactory,
    ) -> SessionRevisionSnapshot:
        value = _persistence_object(
            payload,
            field_name="session revision snapshot",
            expected_keys={
                "session_revision",
                "adapter_session",
                "lifecycle_status",
                "event_count",
                "last_activity_at",
                "started",
                "closed",
            },
        )
        revision = value["session_revision"]
        event_count = value["event_count"]
        last_activity_at = value["last_activity_at"]
        started = value["started"]
        closed = value["closed"]
        if type(revision) is not int or type(event_count) is not int:
            raise SessionProtocolError("Persisted snapshot integer field is invalid.")
        if type(last_activity_at) is not str:
            raise SessionProtocolError("Persisted snapshot timestamp is invalid.")
        if type(started) is not bool or type(closed) is not bool:
            raise SessionProtocolError("Persisted snapshot state flag is invalid.")
        return cls(
            session_revision=revision,
            adapter_session=session_recovery_factory(value["adapter_session"]),
            lifecycle_status=_lifecycle_status_from_persistence(value["lifecycle_status"]),
            event_count=event_count,
            last_activity_at=last_activity_at,
            started=started,
            closed=closed,
        )


@dataclass(slots=True)
class AuthoritativeSession:
    session_id: str
    game_id: str
    adapter_session: AdapterGameSession
    player_ids: tuple[str, ...]
    ruleset_id: JsonValue
    ruleset_descriptor_hash: str
    rules_overlay_ids: tuple[str, ...]
    catalog_id: str
    source_package_id: str
    source_hash: str
    lifecycle_status: LifecycleStatus
    created_at: str
    last_activity_at: str
    event_retention_limit: int = DEFAULT_EVENT_RETENTION_LIMIT
    revision_retention_limit: int = DEFAULT_REVISION_RETENTION_LIMIT
    session_revision: int = 0
    started: bool = False
    closed: bool = False
    cursor_registry_finalized: bool = False
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
        self.ruleset_descriptor_hash = _validate_sha256(
            "ruleset_descriptor_hash", self.ruleset_descriptor_hash
        )
        self.rules_overlay_ids = _validated_rules_overlay_ids(self.rules_overlay_ids)
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
        self.event_retention_limit = _validated_retention_limit(
            "event_retention_limit",
            self.event_retention_limit,
        )
        self.revision_retention_limit = _validated_retention_limit(
            "revision_retention_limit",
            self.revision_retention_limit,
        )
        if type(self.cursor_registry_finalized) is not bool:
            raise SessionProtocolError("Cursor registry finalization flag must be bool.")
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
        event_retention_limit: int = DEFAULT_EVENT_RETENTION_LIMIT,
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
            ruleset_descriptor_hash=config.ruleset_descriptor.descriptor_hash,
            rules_overlay_ids=config.ruleset_descriptor.rules_overlay_ids,
            catalog_id=catalog_view["catalog_id"],
            source_package_id=catalog_view["source_package_id"],
            source_hash=catalog_view["source_hash"],
            lifecycle_status=lifecycle_status,
            created_at=created_at,
            last_activity_at=created_at,
            event_retention_limit=event_retention_limit,
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
        if entry.command_envelope.session_id != self.session_id:
            raise SessionProtocolError("Session command journal envelope targets another session.")
        if entry.committed_session_revision != self.session_revision:
            raise SessionProtocolError("Session command journal revision drifted.")
        if any(
            retained.committed_session_revision == entry.committed_session_revision
            for retained in self.command_journal.values()
        ):
            raise SessionProtocolError("Session command journal revision is duplicated.")
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

    def to_persistence_payload(self) -> dict[str, JsonValue]:
        return {
            "session_id": self.session_id,
            "game_id": self.game_id,
            "adapter_session": self.adapter_session.to_persistence_payload(),
            "player_ids": list(self.player_ids),
            "ruleset_id": self.ruleset_id,
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "rules_overlay_ids": list(self.rules_overlay_ids),
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "source_hash": self.source_hash,
            "lifecycle_status": cast(JsonValue, self.lifecycle_status.to_payload()),
            "created_at": self.created_at,
            "last_activity_at": self.last_activity_at,
            "event_retention_limit": self.event_retention_limit,
            "revision_retention_limit": self.revision_retention_limit,
            "session_revision": self.session_revision,
            "started": self.started,
            "closed": self.closed,
            "cursor_registry_finalized": self.cursor_registry_finalized,
            "command_journal": [
                entry.to_persistence_payload()
                for entry in sorted(
                    self.command_journal.values(),
                    key=lambda entry: (entry.committed_session_revision, entry.command_id),
                )
            ],
            "revision_snapshots": [
                self.revision_snapshots[revision].to_persistence_payload()
                for revision in sorted(self.revision_snapshots)
            ],
        }

    @classmethod
    def from_persistence_payload(
        cls,
        payload: JsonValue,
        *,
        session_recovery_factory: SessionRecoveryFactory,
    ) -> AuthoritativeSession:
        expected_keys = {
            "session_id",
            "game_id",
            "adapter_session",
            "player_ids",
            "ruleset_id",
            "ruleset_descriptor_hash",
            "rules_overlay_ids",
            "catalog_id",
            "source_package_id",
            "source_hash",
            "lifecycle_status",
            "created_at",
            "last_activity_at",
            "event_retention_limit",
            "revision_retention_limit",
            "session_revision",
            "started",
            "closed",
            "cursor_registry_finalized",
            "command_journal",
            "revision_snapshots",
        }
        value = _persistence_object(
            payload,
            field_name="authoritative session",
            expected_keys=expected_keys,
        )
        string_names = (
            "session_id",
            "game_id",
            "ruleset_descriptor_hash",
            "catalog_id",
            "source_package_id",
            "source_hash",
            "created_at",
            "last_activity_at",
        )
        if any(type(value[name]) is not str for name in string_names):
            raise SessionProtocolError("Persisted session string field is invalid.")
        int_names = (
            "event_retention_limit",
            "revision_retention_limit",
            "session_revision",
        )
        if any(type(value[name]) is not int for name in int_names):
            raise SessionProtocolError("Persisted session integer field is invalid.")
        bool_names = ("started", "closed", "cursor_registry_finalized")
        if any(type(value[name]) is not bool for name in bool_names):
            raise SessionProtocolError("Persisted session state flag is invalid.")
        player_ids = _persistence_string_list(value["player_ids"], field_name="player_ids")
        overlay_ids = _persistence_string_list(
            value["rules_overlay_ids"],
            field_name="rules_overlay_ids",
        )
        journal_payload = value["command_journal"]
        snapshot_payload = value["revision_snapshots"]
        if not isinstance(journal_payload, list) or not isinstance(snapshot_payload, list):
            raise SessionProtocolError("Persisted session collections are invalid.")
        journal_entries = [
            SessionCommandJournalEntry.from_persistence_payload(item) for item in journal_payload
        ]
        snapshots = [
            SessionRevisionSnapshot.from_persistence_payload(
                item,
                session_recovery_factory=session_recovery_factory,
            )
            for item in snapshot_payload
        ]
        if len({entry.command_id for entry in journal_entries}) != len(journal_entries):
            raise SessionProtocolError(
                "Persisted session command journal contains duplicate command IDs."
            )
        if len({snapshot.session_revision for snapshot in snapshots}) != len(snapshots):
            raise SessionProtocolError(
                "Persisted session revision snapshots contain duplicate revisions."
            )
        session_id = value["session_id"]
        game_id = value["game_id"]
        ruleset_descriptor_hash = value["ruleset_descriptor_hash"]
        catalog_id = value["catalog_id"]
        source_package_id = value["source_package_id"]
        source_hash = value["source_hash"]
        created_at = value["created_at"]
        last_activity_at = value["last_activity_at"]
        event_retention_limit = value["event_retention_limit"]
        revision_retention_limit = value["revision_retention_limit"]
        session_revision = value["session_revision"]
        started = value["started"]
        closed = value["closed"]
        finalized = value["cursor_registry_finalized"]
        if (
            type(session_id) is not str
            or type(game_id) is not str
            or type(ruleset_descriptor_hash) is not str
            or type(catalog_id) is not str
            or type(source_package_id) is not str
            or type(source_hash) is not str
            or type(created_at) is not str
            or type(last_activity_at) is not str
            or type(event_retention_limit) is not int
            or type(revision_retention_limit) is not int
            or type(session_revision) is not int
            or type(started) is not bool
            or type(closed) is not bool
            or type(finalized) is not bool
        ):
            raise SessionProtocolError("Persisted session field type is invalid.")
        record = cls(
            session_id=session_id,
            game_id=game_id,
            adapter_session=session_recovery_factory(value["adapter_session"]),
            player_ids=tuple(player_ids),
            ruleset_id=value["ruleset_id"],
            ruleset_descriptor_hash=ruleset_descriptor_hash,
            rules_overlay_ids=tuple(overlay_ids),
            catalog_id=catalog_id,
            source_package_id=source_package_id,
            source_hash=source_hash,
            lifecycle_status=_lifecycle_status_from_persistence(value["lifecycle_status"]),
            created_at=created_at,
            last_activity_at=last_activity_at,
            event_retention_limit=event_retention_limit,
            revision_retention_limit=revision_retention_limit,
            session_revision=session_revision,
            started=started,
            closed=closed,
            cursor_registry_finalized=finalized,
            command_journal={entry.command_id: entry for entry in journal_entries},
            revision_snapshots={snapshot.session_revision: snapshot for snapshot in snapshots},
        )
        record._validate_recovered_state()
        return record

    @property
    def minimum_retained_revision(self) -> int:
        return max(0, self.session_revision - self.revision_retention_limit + 1)

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
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "rules_overlay_ids": list(self.rules_overlay_ids),
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
        if len(self.revision_snapshots) <= self.revision_retention_limit:
            return
        retained_revisions = sorted(self.revision_snapshots)[-self.revision_retention_limit :]
        self.revision_snapshots = {
            revision: self.revision_snapshots[revision] for revision in retained_revisions
        }

    def _validate_journal(self) -> None:
        if type(self.command_journal) is not dict:
            raise SessionProtocolError("Session command journal must be a dictionary.")
        committed_revisions: set[int] = set()
        for command_id, entry in self.command_journal.items():
            if type(entry) is not SessionCommandJournalEntry or entry.command_id != command_id:
                raise SessionProtocolError("Session command journal entry is invalid.")
            if entry.command_envelope.session_id != self.session_id:
                raise SessionProtocolError(
                    "Session command journal envelope targets another session."
                )
            if entry.committed_session_revision > self.session_revision:
                raise SessionProtocolError(
                    "Session command journal revision exceeds session state."
                )
            if entry.committed_session_revision in committed_revisions:
                raise SessionProtocolError("Session command journal revision is duplicated.")
            committed_revisions.add(entry.committed_session_revision)
            self._validate_recovered_journal_response(entry)

    def _validate_recovered_journal_response(
        self,
        entry: SessionCommandJournalEntry,
    ) -> None:
        response = _persistence_object(
            entry.response_payload,
            field_name="command journal response",
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
        kind = entry.command_envelope.submission_kind
        operation_by_kind = {
            SessionCommandSubmissionKind.START_SESSION: "start_session",
            SessionCommandSubmissionKind.ADVANCE_SESSION: "advance_session",
            SessionCommandSubmissionKind.CLOSE_SESSION: "close_session",
            SessionCommandSubmissionKind.FINITE_OPTION: "submit_finite_decision",
            SessionCommandSubmissionKind.PARAMETERIZED_PAYLOAD: ("submit_parameterized_decision"),
        }
        accepted = response["accepted"]
        outcome_code = response["outcome_code"]
        if (
            response["schema_version"] != SESSION_COMMAND_OUTCOME_SCHEMA_VERSION
            or response["command_id"] != entry.command_id
            or response["operation"] != operation_by_kind[kind]
            or response["committed"] is not True
            or type(accepted) is not bool
            or type(outcome_code) is not str
        ):
            raise SessionProtocolError("Recovered command journal outcome drifted.")
        expected_status = 200 if accepted else 422
        if entry.status_code != expected_status:
            raise SessionProtocolError("Recovered command journal status code drifted.")
        expected_outcome = SessionCommandOutcomeCode.COMMAND_COMMITTED.value if accepted else None
        if expected_outcome is not None and outcome_code != expected_outcome:
            raise SessionProtocolError("Recovered accepted command outcome drifted.")
        if not accepted and outcome_code not in {
            SessionCommandOutcomeCode.PROPOSAL_INVALID.value,
            SessionCommandOutcomeCode.RULE_PATH_UNSUPPORTED.value,
        }:
            raise SessionProtocolError("Recovered rejected command outcome drifted.")
        self._validate_recovered_journal_session(entry=entry, response=response)

    def _validate_recovered_journal_session(
        self,
        *,
        entry: SessionCommandJournalEntry,
        response: dict[str, JsonValue],
    ) -> None:
        metadata = _persistence_object(
            response["session"],
            field_name="command journal session metadata",
            expected_keys=set(SessionMetadataPayload.__required_keys__),
        )
        checkpoint = _persistence_object(
            response["checkpoint"],
            field_name="command journal checkpoint",
            expected_keys=set(SessionCheckpointPayload.__required_keys__),
        )
        event_range = _persistence_object(
            response["event_range"],
            field_name="command journal event range",
            expected_keys={"from_cursor", "to_cursor"},
        )
        lifecycle = self._validate_recovered_journal_metadata_shape(metadata)
        rejection_kind_by_outcome = {
            SessionCommandOutcomeCode.PROPOSAL_INVALID.value: (LifecycleStatusKind.INVALID.value),
            SessionCommandOutcomeCode.RULE_PATH_UNSUPPORTED.value: (
                LifecycleStatusKind.UNSUPPORTED.value
            ),
        }
        outcome_code = response["outcome_code"]
        if type(outcome_code) is not str:
            raise SessionProtocolError("Recovered command journal outcome drifted.")
        expected_rejection_kind = rejection_kind_by_outcome.get(outcome_code)
        if expected_rejection_kind is not None and (
            lifecycle["status_kind"] != expected_rejection_kind
        ):
            raise SessionProtocolError("Recovered rejected command lifecycle drifted.")
        revision = entry.committed_session_revision
        if (
            type(metadata["session_revision"]) is not int
            or type(checkpoint["session_revision"]) is not int
            or metadata["session_id"] != self.session_id
            or metadata["game_id"] != self.game_id
            or metadata["session_revision"] != revision
            or checkpoint["session_revision"] != revision
        ):
            raise SessionProtocolError("Recovered command journal session identity drifted.")
        if (
            canonical_json(metadata["ruleset_id"]) != canonical_json(self.ruleset_id)
            or metadata["ruleset_descriptor_hash"] != self.ruleset_descriptor_hash
            or metadata["rules_overlay_ids"] != list(self.rules_overlay_ids)
            or metadata["catalog_id"] != self.catalog_id
            or metadata["source_package_id"] != self.source_package_id
            or metadata["source_hash"] != self.source_hash
        ):
            raise SessionProtocolError("Recovered command journal source identity drifted.")
        authorization = entry.authorization_context
        visibility = _persistence_object(
            metadata["visibility"],
            field_name="command journal visibility",
            expected_keys=set(VisibilityPolicyPayload.__required_keys__),
        )
        if (
            type(visibility["delay_revisions"]) is not int
            or type(visibility["may_mutate_lifecycle"]) is not bool
            or type(visibility["may_submit_decision"]) is not bool
            or type(visibility["omniscient"]) is not bool
            or visibility["role"] != authorization.role.value
            or visibility["player_id"] != authorization.player_id
            or visibility["delay_revisions"] != authorization.delay_revisions
            or visibility["may_mutate_lifecycle"] is not authorization.may_mutate_lifecycle
            or visibility["may_submit_decision"] is not authorization.may_submit_decision
            or visibility["omniscient"] is not authorization.omniscient
            or checkpoint["visibility_role"] != authorization.role.value
            or checkpoint["viewer_player_id"] != authorization.player_id
        ):
            raise SessionProtocolError("Recovered command journal visibility drifted.")
        event_cursor = _validate_cursor(metadata["event_cursor"])
        _validate_sha256("projection_state_hash", checkpoint["projection_state_hash"])
        if (
            checkpoint["event_cursor"] != event_cursor
            or event_range["to_cursor"] != event_cursor
            or checkpoint["projection_state_hash"] != metadata["projection_state_hash"]
        ):
            raise SessionProtocolError("Recovered command journal checkpoint drifted.")
        _validate_cursor(event_range["from_cursor"])
        retained = self.revision_snapshots.get(revision)
        viewer = ViewerContext(
            principal_id=authorization.principal_id,
            role=authorization.role,
            viewer_player_id=authorization.player_id,
            policy=ROLE_POLICY_BY_ROLE[authorization.role],
            authorization_epoch=authorization.authorization_epoch,
        )
        if retained is not None and (
            metadata["session_state"] != retained.state.value
            or canonical_json(metadata["terminal_reason"])
            != canonical_json(cast(JsonValue, self._terminal_reason(retained)))
            or canonical_json(metadata["lifecycle_status"])
            != canonical_json(
                cast(
                    JsonValue,
                    redacted_lifecycle_status(retained.lifecycle_status, viewer=viewer),
                )
            )
        ):
            raise SessionProtocolError("Recovered command journal retained snapshot drifted.")
        activity = metadata["last_activity_at"]
        if type(activity) is not str:
            raise SessionProtocolError("Recovered command journal activity timestamp drifted.")
        activity_time = _parse_timestamp(activity)
        if activity_time < _parse_timestamp(self.created_at) or (
            retained is not None and activity_time > _parse_timestamp(retained.last_activity_at)
        ):
            raise SessionProtocolError("Recovered command journal activity timestamp drifted.")
        if (
            metadata["created_at"] != self.created_at
            or metadata["server_contract_version"] != EXTERNAL_CONTRACT_VERSION
            or metadata["engine_version"] != ENGINE_VERSION
            or metadata["engine_build_id"] != ENGINE_BUILD_ID
        ):
            raise SessionProtocolError("Recovered command journal runtime metadata drifted.")

    def _validate_recovered_journal_metadata_shape(
        self,
        metadata: dict[str, JsonValue],
    ) -> dict[str, JsonValue]:
        if (
            metadata["schema_version"] != SESSION_METADATA_SCHEMA_VERSION
            or type(metadata["session_state"]) is not str
            or metadata["session_state"] not in {state.value for state in SessionState}
            or not isinstance(metadata["ruleset_id"], dict)
        ):
            raise SessionProtocolError("Recovered command journal metadata shape drifted.")
        _validate_sha256("projection_state_hash", metadata["projection_state_hash"])
        lifecycle = _persistence_object(
            metadata["lifecycle_status"],
            field_name="command journal lifecycle status",
            expected_keys={
                "stage",
                "status_kind",
                "message",
                "payload",
                "pending_request_id",
                "decision_type",
                "actor_id",
            },
        )
        if (
            lifecycle["stage"] not in {stage.value for stage in GameLifecycleStage}
            or lifecycle["status_kind"] not in {status.value for status in LifecycleStatusKind}
            or any(
                value is not None and type(value) is not str
                for value in (
                    lifecycle["message"],
                    lifecycle["pending_request_id"],
                    lifecycle["decision_type"],
                    lifecycle["actor_id"],
                )
            )
        ):
            raise SessionProtocolError("Recovered command journal lifecycle shape drifted.")
        terminal_reason = metadata["terminal_reason"]
        if terminal_reason is not None:
            reason = _persistence_object(
                terminal_reason,
                field_name="command journal terminal reason",
                expected_keys={"code", "message"},
            )
            if reason["code"] not in {"game_complete", "session_closed"} or (
                type(reason["message"]) is not str or not reason["message"]
            ):
                raise SessionProtocolError("Recovered command journal terminal reason drifted.")
        return lifecycle

    def _validate_snapshots(self) -> None:
        if type(self.revision_snapshots) is not dict:
            raise SessionProtocolError("Session revision snapshots must be a dictionary.")
        for revision, snapshot in self.revision_snapshots.items():
            if (
                type(snapshot) is not SessionRevisionSnapshot
                or snapshot.session_revision != revision
            ):
                raise SessionProtocolError("Session revision snapshot is invalid.")

    def _validate_recovered_state(self) -> None:
        snapshot = self.current_snapshot()
        if snapshot.lifecycle_status != self.lifecycle_status:
            raise SessionProtocolError("Recovered current lifecycle status drifted.")
        if snapshot.started != self.started or snapshot.closed != self.closed:
            raise SessionProtocolError("Recovered current session state flags drifted.")
        if _parse_timestamp(snapshot.last_activity_at) > _parse_timestamp(self.last_activity_at):
            raise SessionProtocolError("Recovered current activity timestamp predates snapshot.")
        if snapshot.event_count != self.adapter_session.event_record_count():
            raise SessionProtocolError("Recovered current event count drifted.")
        if canonical_json(snapshot.adapter_session.to_persistence_payload()) != canonical_json(
            self.adapter_session.to_persistence_payload()
        ):
            raise SessionProtocolError("Recovered current adapter checkpoint drifted.")
        expected_revisions = set(range(self.minimum_retained_revision, self.session_revision + 1))
        if set(self.revision_snapshots) != expected_revisions:
            raise SessionProtocolError("Recovered snapshot revision range is not contiguous.")
        previous_event_count = -1
        previous_activity = _parse_timestamp(self.created_at)
        previous_started = False
        previous_closed = False
        for revision in sorted(self.revision_snapshots):
            retained = self.revision_snapshots[revision]
            if retained.session_revision > self.session_revision:
                raise SessionProtocolError("Recovered snapshot revision exceeds session state.")
            if retained.event_count != retained.adapter_session.event_record_count():
                raise SessionProtocolError("Recovered snapshot event count drifted.")
            activity = _parse_timestamp(retained.last_activity_at)
            if retained.event_count < previous_event_count or activity < previous_activity:
                raise SessionProtocolError("Recovered snapshot history moved backwards.")
            if previous_started and not retained.started:
                raise SessionProtocolError("Recovered snapshot started state moved backwards.")
            if previous_closed and not retained.closed:
                raise SessionProtocolError("Recovered snapshot closed state moved backwards.")
            self._validate_recovered_adapter_identity(retained.adapter_session)
            previous_event_count = retained.event_count
            previous_activity = activity
            previous_started = retained.started
            previous_closed = retained.closed
        self._validate_recovered_adapter_identity(self.adapter_session)

    def _validate_recovered_adapter_identity(
        self,
        adapter_session: AdapterGameSession,
    ) -> None:
        identity = adapter_session.authoritative_identity_payload()
        if identity["game_id"] != self.game_id:
            raise SessionProtocolError("Recovered game identity drifted.")
        if tuple(identity["player_ids"]) != self.player_ids:
            raise SessionProtocolError("Recovered player identity order drifted.")
        if canonical_json(identity["ruleset_id"]) != canonical_json(self.ruleset_id):
            raise SessionProtocolError("Recovered ruleset identity drifted.")
        if (
            identity["ruleset_descriptor_hash"] != self.ruleset_descriptor_hash
            or tuple(identity["rules_overlay_ids"]) != self.rules_overlay_ids
        ):
            raise SessionProtocolError("Recovered ruleset descriptor identity drifted.")
        if (
            identity["catalog_id"] != self.catalog_id
            or identity["source_package_id"] != self.source_package_id
            or identity["source_hash"] != self.source_hash
        ):
            raise SessionProtocolError("Recovered catalog identity drifted.")


def utc_operational_clock() -> datetime:
    return datetime.now(UTC)


def operational_timestamp(clock: OperationalClock) -> str:
    if not callable(clock):
        raise SessionProtocolError("Operational clock must be callable.")
    value = clock()
    if type(value) is not datetime or value.tzinfo is None or value.utcoffset() is None:
        raise SessionProtocolError("Operational clock must return an aware datetime.")
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _validated_retention_limit(name: str, value: object) -> int:
    if type(value) is not int or value < 1:
        raise SessionProtocolError(f"Session {name} must be positive.")
    return value


def _persistence_object(
    payload: JsonValue,
    *,
    field_name: str,
    expected_keys: set[str],
) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise SessionProtocolError(f"Persisted {field_name} must be an object.")
    if set(payload) != expected_keys:
        raise SessionProtocolError(f"Persisted {field_name} keys are invalid.")
    return payload


def _persistence_string_list(payload: JsonValue, *, field_name: str) -> list[str]:
    if not isinstance(payload, list) or any(type(value) is not str for value in payload):
        raise SessionProtocolError(f"Persisted {field_name} must be a string list.")
    return [value for value in payload if type(value) is str]


def _lifecycle_status_from_persistence(payload: JsonValue) -> LifecycleStatus:
    value = _persistence_object(
        payload,
        field_name="lifecycle status",
        expected_keys={"stage", "status_kind", "decision_request", "message", "payload"},
    )
    stage = value["stage"]
    status_kind = value["status_kind"]
    message = value["message"]
    if type(stage) is not str or type(status_kind) is not str:
        raise SessionProtocolError("Persisted lifecycle status token is invalid.")
    if message is not None and type(message) is not str:
        raise SessionProtocolError("Persisted lifecycle status message is invalid.")
    try:
        return LifecycleStatus.from_payload(cast(LifecycleStatusPayload, value))
    except DecisionError as exc:
        raise SessionProtocolError("Persisted lifecycle decision request is invalid.") from exc


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


def _validated_rules_overlay_ids(values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise SessionProtocolError("rules_overlay_ids must be a tuple.")
    validated = tuple(sorted(_validate_identifier("rules_overlay_id", value) for value in values))
    if len(validated) != len(set(validated)):
        raise SessionProtocolError("rules_overlay_ids must not contain duplicates.")
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
