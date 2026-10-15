from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
from collections.abc import Callable, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from threading import Event
from typing import Literal, cast

import pytest

from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase15c_fight_order_helpers import fight_config, fight_lifecycle
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core import build_identity
from warhammer40k_core.adapters import session_recovery as session_recovery_module
from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    DEV_COACH_A_TOKEN,
    DEV_PLAYER_A_TOKEN,
    DEV_PLAYER_B_TOKEN,
    DEV_SPECTATOR_TOKEN,
    AuthenticatedPrincipal,
    PrincipalCredential,
    PrincipalRegistry,
    PrincipalRole,
    bearer_authorization,
    default_principal_registry,
)
from warhammer40k_core.adapters.command_protocol import (
    SessionCommandEnvelope,
    SessionCommandJournalEntry,
    SessionCommandSubmissionKind,
)
from warhammer40k_core.adapters.external_contract import SESSION_CREATE_SCHEMA_VERSION
from warhammer40k_core.adapters.local_session import (
    LocalGameSession,
    LocalGameSessionPersistenceError,
)
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.server_types import ServerResponse
from warhammer40k_core.adapters.session_events import SessionCursorCodec
from warhammer40k_core.adapters.session_persistence import (
    SESSION_PERSISTENCE_STORE_SCHEMA_VERSION,
    SQLITE_SESSION_PERSISTENCE_USER_VERSION,
    SQLITE_SESSION_STATE_TABLE,
    SessionPersistenceCorruptionError,
    SessionPersistenceDriftError,
    SessionPersistenceError,
    SessionPersistenceStorageError,
    SessionPersistenceStore,
    SQLiteSessionPersistenceStore,
    commit_persistence_store,
)
from warhammer40k_core.adapters.session_protocol import AuthoritativeSession, SessionProtocolError
from warhammer40k_core.adapters.session_recovery import (
    SessionRecoveryError,
    recover_server_persistence_payload,
    server_persistence_payload,
)
from warhammer40k_core.adapters.session_revision import (
    SessionNonCommandOrigin,
    SessionRevisionCommitment,
    SessionRevisionOrigin,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
    MovementProposalRequestPayload,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.engine.replay import (
    ReplayArtifact,
    ReplayArtifactPayload,
    ReplayProjectionCheckpoint,
    ReplayRunner,
    ReplayRunStatus,
)
from warhammer40k_core.geometry.pose import Pose

PLAYER_A = "player-a"
PLAYER_B = "player-b"
FIXED_SECONDARY_OPTION_ID = "fixed:assassination:bring_it_down"
FROZEN_TIME = datetime(2026, 8, 21, 16, 0, tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class _MemoryResource:
    name: str
    resource_kind: Literal["directory", "file", "unsupported"]
    children: tuple[_MemoryResource, ...] = ()
    content: bytes = b""
    unreadable: bool = False
    enumeration_error: bool = False

    @classmethod
    def directory(
        cls,
        name: str,
        *children: _MemoryResource,
        enumeration_error: bool = False,
    ) -> _MemoryResource:
        return cls(
            name=name,
            resource_kind="directory",
            children=children,
            enumeration_error=enumeration_error,
        )

    @classmethod
    def file(
        cls,
        name: str,
        content: bytes,
        *,
        unreadable: bool = False,
    ) -> _MemoryResource:
        return cls(
            name=name,
            resource_kind="file",
            content=content,
            unreadable=unreadable,
        )

    @classmethod
    def unsupported(cls, name: str) -> _MemoryResource:
        return cls(name=name, resource_kind="unsupported")

    @classmethod
    def packaged_schema_directory(cls) -> _MemoryResource:
        return cls.directory(
            "contracts",
            cls.directory("schemas", cls.file("session.schema.json", b"{}\n")),
        )

    def is_dir(self) -> bool:
        return self.resource_kind == "directory"

    def is_file(self) -> bool:
        return self.resource_kind == "file"

    def iterdir(self) -> Iterator[_MemoryResource]:
        if self.enumeration_error:
            raise OSError("injected enumeration failure")
        return iter(self.children)

    def joinpath(self, *descendants: str) -> _MemoryResource:
        selected = self
        for descendant in descendants:
            match = next((child for child in selected.children if child.name == descendant), None)
            if match is None:
                return self.unsupported(descendant)
            selected = match
        return selected

    def read_bytes(self) -> bytes:
        if self.unreadable:
            raise OSError("injected resource read failure")
        return self.content


def _runtime_package_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    package_root = tmp_path / "warhammer40k_core"
    schema_root = package_root / "contracts" / "schemas"
    schema_root.mkdir(parents=True)
    (package_root / "runtime.py").write_bytes(b"RUNTIME_RULE = 1\r\n")
    (package_root / "py.typed").write_bytes(b"")
    (schema_root / "session.schema.json").write_text("{}\n", encoding="utf-8")
    cache_root = package_root / "__pycache__"
    cache_root.mkdir()
    (cache_root / "ignored.py").write_text("IGNORED = True\n", encoding="utf-8")

    def package_files(_package_name: str) -> Path:
        return package_root

    monkeypatch.setattr(build_identity, "files", package_files)
    return package_root


def _write_runtime_manifest(
    package_root: Path,
    manifest: build_identity.EngineBuildManifestPayload,
) -> None:
    (package_root / "_engine_build_manifest.json").write_text(
        build_identity.canonical_engine_build_manifest_text(manifest),
        encoding="utf-8",
        newline="",
    )


@pytest.fixture
def isolated_engine_build_identity_cache() -> Iterator[None]:
    build_identity.verified_engine_build_identity.cache_clear()
    yield
    build_identity.verified_engine_build_identity.cache_clear()


@pytest.fixture(scope="module")
def phase18l_root_checkpoint_payload() -> dict[str, JsonValue]:
    config = fight_config(
        game_id="phase18l-root-tamper",
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        datasheet_id="core-intercessor-like-infantry",
        model_profile_id="core-intercessor-like",
        model_count=5,
    )
    session = LocalGameSession()
    status = session.start(config)
    record = AuthoritativeSession.create(
        session_id="session:phase18l-root-tamper",
        adapter_session=session,
        config=config,
        lifecycle_status=status,
        created_at="2026-08-21T16:00:00Z",
    )
    return server_persistence_payload(
        sessions={record.session_id: record},
        session_id_by_game_id={record.game_id: record.session_id},
        cursor_codec=SessionCursorCodec(),
        principal_registry=default_principal_registry(),
        event_retention_limit=record.event_retention_limit,
    )


@pytest.fixture(scope="module")
def phase18l_journaled_root_checkpoint_payload() -> dict[str, JsonValue]:
    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=lambda: FROZEN_TIME,
    )
    session_id = _create_session(server, game_id="phase18l-journaled-root-tamper")
    _command(
        server,
        token=DEV_ADMIN_TOKEN,
        envelope=_lifecycle_envelope(
            session_id=session_id,
            command_id="phase18l-journaled-root-start",
            expected_revision=0,
            submission_kind=SessionCommandSubmissionKind.START_SESSION,
        ),
    )
    pending = _pending_decision(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    _command(
        server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=_finite_envelope(
            session_id=session_id,
            command_id="phase18l-journaled-root-secondary",
            expected_revision=1,
            request_id=_string(pending, "request_id"),
            result_id="phase18l-journaled-root-secondary-result",
            option_id=FIXED_SECONDARY_OPTION_ID,
        ),
    )
    return server.persistence_payload()


@pytest.fixture(scope="module")
def phase18l_legacy_revision_root_checkpoint_payload() -> dict[str, JsonValue]:
    config = canonical_setup_prebattle_smoke_config(game_id="phase18l-legacy-origins")
    session = LocalGameSession()
    initial_status = session.start(config)
    record = AuthoritativeSession.create(
        session_id="session:phase18l-legacy-origins",
        adapter_session=session,
        config=config,
        lifecycle_status=initial_status,
        created_at="2026-08-21T16:00:00Z",
    )
    decision_status = session.advance_until_decision_or_terminal()
    record.started = True
    record.commit_status(
        decision_status,
        timestamp="2026-08-21T16:00:01Z",
        origin=SessionRevisionOrigin.noncommand(SessionNonCommandOrigin.LEGACY_ADVANCE_SESSION),
    )
    request = decision_status.decision_request
    assert request is not None
    next_status = session.submit_option(
        request_id=request.request_id,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id="phase18l-legacy-origin-finite-result",
    )
    record.commit_status(
        next_status,
        timestamp="2026-08-21T16:00:02Z",
        origin=SessionRevisionOrigin.noncommand(SessionNonCommandOrigin.LEGACY_FINITE_DECISION),
    )
    return _server_checkpoint_payload(record)


@dataclass(slots=True)
class _FaultingPersistenceStore:
    delegate: SessionPersistenceStore
    _failure_point: Literal["before", "after"] | None = None

    def arm(self, failure_point: Literal["before", "after"]) -> None:
        self._failure_point = failure_point

    def initialize(self, payload: JsonValue) -> None:
        self.delegate.initialize(payload)

    def load(self) -> JsonValue:
        return self.delegate.load()

    def commit(self, payload: JsonValue) -> None:
        failure_point = self._failure_point
        self._failure_point = None
        if failure_point == "before":
            raise SessionPersistenceStorageError("Injected failure before durable commit.")
        self.delegate.commit(payload)
        if failure_point == "after":
            raise SessionPersistenceStorageError("Injected failure after durable commit.")


@dataclass(slots=True)
class _UntypedAfterCommitStore:
    delegate: SessionPersistenceStore
    error_type: type[OSError] | type[RuntimeError]

    def initialize(self, payload: JsonValue) -> None:
        self.delegate.initialize(payload)

    def load(self) -> JsonValue:
        return self.delegate.load()

    def commit(self, payload: JsonValue) -> None:
        self.delegate.commit(payload)
        raise self.error_type("Injected untyped failure after durable commit.")


@dataclass(slots=True)
class _UntypedAfterInitializeStore:
    delegate: SessionPersistenceStore

    def initialize(self, payload: JsonValue) -> None:
        self.delegate.initialize(payload)
        raise OSError("Injected failure after durable initialization.")

    def load(self) -> JsonValue:
        return self.delegate.load()

    def commit(self, payload: JsonValue) -> None:
        self.delegate.commit(payload)


@dataclass(slots=True)
class _FalseyPersistenceStore:
    delegate: SessionPersistenceStore

    def __bool__(self) -> bool:
        return False

    def initialize(self, payload: JsonValue) -> None:
        self.delegate.initialize(payload)

    def load(self) -> JsonValue:
        return self.delegate.load()

    def commit(self, payload: JsonValue) -> None:
        self.delegate.commit(payload)


def _phase_boundary_session(boundary: str) -> LocalGameSession:
    if boundary == "setup":
        session = LocalGameSession()
        session.start(
            fight_config(
                game_id="phase18l-checkpoint-setup",
                alpha_unit_ids=("intercessor-1",),
                enemy_unit_ids=("enemy",),
                datasheet_id="core-intercessor-like-infantry",
                model_profile_id="core-intercessor-like",
                model_count=5,
            )
        )
        return session
    phase_by_boundary = {
        "movement": BattlePhase.MOVEMENT,
        "shooting": BattlePhase.SHOOTING,
        "charge": BattlePhase.CHARGE,
        "fight": BattlePhase.FIGHT,
        "terminal": BattlePhase.FIGHT,
    }
    phase = phase_by_boundary[boundary]
    lifecycle, _units = fight_lifecycle(
        alpha_unit_ids=("intercessor-1",),
        enemy_unit_ids=("enemy",),
        origins={
            "intercessor-1": Pose.at(10.0, 20.0),
            "enemy": Pose.at(20.0 if boundary == "charge" else 30.0, 20.0),
        },
        game_id=f"phase18l-checkpoint-{boundary}",
        battle_phase=phase,
        charge_fights_first_unit_keys=(("intercessor-1",) if boundary == "fight" else ()),
    )
    session = LocalGameSession(lifecycle=lifecycle)
    if boundary != "terminal":
        return session
    state = lifecycle.state
    assert state is not None
    state.battle_round = 5
    state.active_player_id = "player-b"
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.FIGHT)
    record_primary_turn_start_evidence_for_fixture(
        state,
        decisions=lifecycle.decision_controller,
    )
    terminal = session.advance_until_decision_or_terminal()
    assert terminal.status_kind is LifecycleStatusKind.TERMINAL
    assert state.stage is GameLifecycleStage.COMPLETE
    return session


def _movement_proposal_server(
    *,
    database_path: Path,
    session_suffix: str,
) -> tuple[
    AdapterGameServer,
    SQLiteSessionPersistenceStore,
    str,
    dict[str, JsonValue],
    dict[str, JsonValue],
]:
    session = _phase_boundary_session("movement")
    status = session.advance_until_decision_or_terminal()
    record = AuthoritativeSession.create(
        session_id=f"session:phase18l-{session_suffix}",
        adapter_session=session,
        config=session.lifecycle.config,
        lifecycle_status=status,
        created_at="2026-08-21T16:00:00Z",
        started=True,
    )
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    store.initialize(_server_checkpoint_payload(record))
    server = _server(store)
    session_id = record.session_id

    unit_request = _pending_decision(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    unit_options = _list(unit_request, "options")
    assert unit_options
    _command(
        server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=_finite_envelope(
            session_id=session_id,
            command_id=f"phase18l-{session_suffix}-unit",
            expected_revision=0,
            request_id=_string(unit_request, "request_id"),
            result_id=f"phase18l-{session_suffix}-unit-result",
            option_id=_string(_object(unit_options[0]), "option_id"),
        ),
    )
    action_request = _pending_decision(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    _command(
        server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=_finite_envelope(
            session_id=session_id,
            command_id=f"phase18l-{session_suffix}-action",
            expected_revision=1,
            request_id=_string(action_request, "request_id"),
            result_id=f"phase18l-{session_suffix}-action-result",
            option_id=MovementPhaseActionKind.NORMAL_MOVE.value,
        ),
    )
    proposal_request = _pending_decision(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
    )
    projected = _object(
        _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN),
        "projection",
    )
    proposal_context = MovementProposalRequest.from_payload(
        cast(MovementProposalRequestPayload, _object(projected, "pending_proposal"))
    )
    invalid_payload = cast(
        dict[str, JsonValue],
        MovementProposalPayload(
            proposal_request_id=proposal_context.request_id,
            proposal_kind=proposal_context.proposal_kind,
            unit_instance_id=proposal_context.unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
            movement_mode=MovementMode.NORMAL.value,
            witness=straight_line_witness_for_unit(
                session.lifecycle,
                unit_instance_id=proposal_context.unit_instance_id,
                dx=1000.0,
            ),
        ).to_payload(),
    )
    return server, store, session_id, proposal_request, invalid_payload


def _first_session_payload(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    sessions = _list(payload, "sessions")
    assert len(sessions) == 1
    return _object(sessions[0])


def _server_checkpoint_payload(record: AuthoritativeSession) -> dict[str, JsonValue]:
    return server_persistence_payload(
        sessions={record.session_id: record},
        session_id_by_game_id={record.game_id: record.session_id},
        cursor_codec=SessionCursorCodec(),
        principal_registry=default_principal_registry(),
        event_retention_limit=record.event_retention_limit,
    )


def _rehash_content_addressed_payload(payload: dict[str, JsonValue]) -> None:
    content = {key: value for key, value in payload.items() if key != "content_hash"}
    payload["content_hash"] = hashlib.sha256(
        canonical_json(cast(JsonValue, content)).encode("utf-8")
    ).hexdigest()


def _revision_domain_hash(payload: JsonValue, *, domain: str) -> str:
    digest = hashlib.sha256()
    digest.update(b"warhammer40k-core-v2-session-revision-v1\x00")
    digest.update(domain.encode("ascii"))
    digest.update(b"\x00")
    digest.update(canonical_json(payload).encode("utf-8"))
    return digest.hexdigest()


def _revision_item(
    session_payload: dict[str, JsonValue],
    collection_name: str,
    *,
    revision: int,
) -> dict[str, JsonValue]:
    matches = [
        item
        for value in _list(session_payload, collection_name)
        if _integer(item := _object(value), "session_revision") == revision
    ]
    assert len(matches) == 1
    return matches[0]


def _bind_snapshot_evidence(
    *,
    commitment: dict[str, JsonValue],
    snapshot: dict[str, JsonValue],
) -> None:
    adapter_session = LocalGameSession.from_persistence_payload(
        copy.deepcopy(_object(snapshot, "adapter_session"))
    )
    history = adapter_session.authoritative_history_payload()
    decision_records = history["decision_records"]
    event_records = history["event_records"]
    rng_history = history["rng_history"]
    commitment["decision_count"] = len(decision_records)
    commitment["decision_records_hash"] = _revision_domain_hash(
        decision_records,
        domain="decision-prefix",
    )
    commitment["event_count"] = len(event_records)
    commitment["event_records_hash"] = _revision_domain_hash(
        event_records,
        domain="event-prefix",
    )
    commitment["rng_history_count"] = len(rng_history)
    commitment["rng_history_hash"] = _revision_domain_hash(
        cast(JsonValue, rng_history),
        domain="rng-history-prefix",
    )
    commitment["rng_draw_count"] = history["rng_draw_count"]
    commitment["rng_state_hash"] = _revision_domain_hash(
        {
            "seed": history["rng_seed"],
            "history": list(rng_history),
            "draw_count": history["rng_draw_count"],
        },
        domain="rng-state",
    )
    commitment["checkpoint_hash"] = history["checkpoint_hash"]
    commitment["authoritative_state_hash"] = history["authoritative_state_hash"]
    commitment["started"] = snapshot["started"]
    commitment["closed"] = snapshot["closed"]
    commitment["authoritative_session_hash"] = _revision_domain_hash(
        {
            "session_revision": snapshot["session_revision"],
            "lifecycle_status": snapshot["lifecycle_status"],
            "event_count": snapshot["event_count"],
            "last_activity_at": snapshot["last_activity_at"],
            "started": snapshot["started"],
            "closed": snapshot["closed"],
        },
        domain="authoritative-session-state",
    )


def _rehash_revision_chain(session_payload: dict[str, JsonValue]) -> None:
    previous_commitment: str | None = None
    history = _list(session_payload, "revision_history")
    assert history
    for expected_revision, value in enumerate(history):
        commitment = _object(value)
        assert _integer(commitment, "session_revision") == expected_revision
        commitment["previous_revision_commitment"] = previous_commitment
        content = {key: item for key, item in commitment.items() if key != "revision_commitment"}
        previous_commitment = _revision_domain_hash(
            cast(JsonValue, content),
            domain="revision-commitment",
        )
        commitment["revision_commitment"] = previous_commitment
    assert previous_commitment is not None
    session_payload["history_head"] = previous_commitment


def _assert_revision_chain_hashes_are_self_consistent(
    session_payload: dict[str, JsonValue],
) -> None:
    previous_commitment: str | None = None
    history = _list(session_payload, "revision_history")
    assert history
    for expected_revision, value in enumerate(history):
        commitment = SessionRevisionCommitment.from_payload(copy.deepcopy(value))
        assert commitment.session_revision == expected_revision
        assert commitment.previous_revision_commitment == previous_commitment
        previous_commitment = commitment.revision_commitment
    assert session_payload["history_head"] == previous_commitment


def _rehash_command_revision(
    session_payload: dict[str, JsonValue],
    *,
    journal_entry: dict[str, JsonValue],
) -> None:
    revision = _integer(journal_entry, "committed_session_revision")
    commitment = _revision_item(session_payload, "revision_history", revision=revision)
    commitment["journal_entry_hash"] = _revision_domain_hash(
        cast(JsonValue, journal_entry),
        domain="command-journal-entry",
    )
    commitment["response_hash"] = _revision_domain_hash(
        cast(JsonValue, _object(journal_entry, "response_payload")),
        domain="command-response",
    )
    _rehash_revision_chain(session_payload)


def _assert_command_hashes_are_self_consistent(
    session_payload: dict[str, JsonValue],
    *,
    journal_entry: dict[str, JsonValue],
) -> None:
    entry = SessionCommandJournalEntry.from_persistence_payload(copy.deepcopy(journal_entry))
    commitment = SessionRevisionCommitment.from_payload(
        copy.deepcopy(
            _revision_item(
                session_payload,
                "revision_history",
                revision=entry.committed_session_revision,
            )
        )
    )
    assert commitment.journal_entry_hash == _revision_domain_hash(
        cast(JsonValue, entry.to_persistence_payload()),
        domain="command-journal-entry",
    )
    assert commitment.response_hash == _revision_domain_hash(
        entry.response_payload,
        domain="command-response",
    )


def _server_with_fixed_secondary_choice(
    *,
    game_id: str,
    option_index: int,
) -> AdapterGameServer:
    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=lambda: FROZEN_TIME,
    )
    session_id = _create_session(server, game_id=game_id)
    _command(
        server,
        token=DEV_ADMIN_TOKEN,
        envelope=_lifecycle_envelope(
            session_id=session_id,
            command_id="phase18l-alternate-valid-branch-start",
            expected_revision=0,
            submission_kind=SessionCommandSubmissionKind.START_SESSION,
        ),
    )
    pending = _pending_decision(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    option_ids = [_string(_object(option), "option_id") for option in _list(pending, "options")]
    assert len(option_ids) >= 2
    assert len(set(option_ids)) == len(option_ids)
    assert 0 <= option_index < len(option_ids)
    _command(
        server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=_finite_envelope(
            session_id=session_id,
            command_id="phase18l-alternate-valid-branch-choice",
            expected_revision=1,
            request_id=_string(pending, "request_id"),
            result_id="phase18l-alternate-valid-branch-result",
            option_id=option_ids[option_index],
        ),
    )
    player_b_pending = _pending_decision(
        server,
        session_id=session_id,
        token=DEV_PLAYER_B_TOKEN,
    )
    assert _string(player_b_pending, "actor_id") == PLAYER_B
    player_b_option_ids = [
        _string(_object(option), "option_id") for option in _list(player_b_pending, "options")
    ]
    assert FIXED_SECONDARY_OPTION_ID in player_b_option_ids
    _command(
        server,
        token=DEV_PLAYER_B_TOKEN,
        envelope=_finite_envelope(
            session_id=session_id,
            command_id="phase18l-alternate-valid-branch-common-choice",
            expected_revision=2,
            request_id=_string(player_b_pending, "request_id"),
            result_id="phase18l-alternate-valid-branch-common-result",
            option_id=FIXED_SECONDARY_OPTION_ID,
        ),
    )
    return server


def _server(
    persistence_store: SessionPersistenceStore,
    *,
    principal_registry: PrincipalRegistry | None = None,
) -> AdapterGameServer:
    registry = default_principal_registry() if principal_registry is None else principal_registry
    if _store_requires_initialization(persistence_store):
        server = AdapterGameServer(
            principal_registry=registry,
            clock=lambda: FROZEN_TIME,
        )
        server.initialize_persistence(persistence_store)
        return server
    return AdapterGameServer(
        persistence_store=persistence_store,
        principal_registry=registry,
        clock=lambda: FROZEN_TIME,
    )


def _store_requires_initialization(store: SessionPersistenceStore) -> bool:
    if isinstance(store, SQLiteSessionPersistenceStore):
        return not store.database_path.exists()
    if isinstance(store, _FaultingPersistenceStore):
        return _store_requires_initialization(store.delegate)
    if isinstance(store, _UntypedAfterCommitStore):
        return _store_requires_initialization(store.delegate)
    return False


def _create_session(server: AdapterGameServer, *, game_id: str) -> str:
    response = _request(
        server,
        method="POST",
        path="/sessions",
        token=DEV_ADMIN_TOKEN,
        body={
            "schema_version": SESSION_CREATE_SCHEMA_VERSION,
            "config": cast(
                JsonValue,
                canonical_setup_prebattle_smoke_config(game_id=game_id).to_payload(),
            ),
        },
        expected_status=HTTPStatus.CREATED,
    )
    return _string(response, "session_id")


def _lifecycle_envelope(
    *,
    session_id: str,
    command_id: str,
    expected_revision: int,
    submission_kind: SessionCommandSubmissionKind,
) -> SessionCommandEnvelope:
    assert submission_kind in {
        SessionCommandSubmissionKind.START_SESSION,
        SessionCommandSubmissionKind.ADVANCE_SESSION,
        SessionCommandSubmissionKind.CLOSE_SESSION,
    }
    return SessionCommandEnvelope(
        command_id=command_id,
        session_id=session_id,
        expected_session_revision=expected_revision,
        request_id=None,
        result_id=None,
        submission_kind=submission_kind,
        submission={"submission_kind": submission_kind.value},
    )


def _finite_envelope(
    *,
    session_id: str,
    command_id: str,
    expected_revision: int,
    request_id: str,
    result_id: str,
    option_id: str,
) -> SessionCommandEnvelope:
    return SessionCommandEnvelope(
        command_id=command_id,
        session_id=session_id,
        expected_session_revision=expected_revision,
        request_id=request_id,
        result_id=result_id,
        submission_kind=SessionCommandSubmissionKind.FINITE_OPTION,
        submission={
            "submission_kind": SessionCommandSubmissionKind.FINITE_OPTION.value,
            "option_id": option_id,
        },
    )


def _parameterized_envelope(
    *,
    session_id: str,
    command_id: str,
    expected_revision: int,
    request_id: str,
    result_id: str,
    payload: JsonValue,
) -> SessionCommandEnvelope:
    return SessionCommandEnvelope(
        command_id=command_id,
        session_id=session_id,
        expected_session_revision=expected_revision,
        request_id=request_id,
        result_id=result_id,
        submission_kind=SessionCommandSubmissionKind.PARAMETERIZED_PAYLOAD,
        submission={
            "submission_kind": SessionCommandSubmissionKind.PARAMETERIZED_PAYLOAD.value,
            "payload": payload,
        },
    )


def _command(
    server: AdapterGameServer,
    *,
    token: str,
    envelope: SessionCommandEnvelope,
) -> dict[str, JsonValue]:
    response = _command_response(server, token=token, envelope=envelope)
    assert response.status_code == HTTPStatus.OK, response.payload
    return _object(response.payload)


def _command_response(
    server: AdapterGameServer,
    *,
    token: str,
    envelope: SessionCommandEnvelope,
) -> ServerResponse:
    return server.handle(
        method="POST",
        path=f"/sessions/{envelope.session_id}/commands",
        body=cast(JsonValue, envelope.to_payload()),
        authorization=bearer_authorization(token),
    )


def _projection(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
) -> dict[str, JsonValue]:
    return _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/projection",
        token=token,
    )


def _pending_decision(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
) -> dict[str, JsonValue]:
    projection = _object(_projection(server, session_id=session_id, token=token), "projection")
    return _object(projection, "pending_decision")


def _metadata(server: AdapterGameServer, *, session_id: str) -> dict[str, JsonValue]:
    return _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}",
        token=DEV_ADMIN_TOKEN,
    )


def _events(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
    cursor: str,
) -> dict[str, JsonValue]:
    return _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/events",
        token=token,
        query={"cursor": cursor},
    )


def _replay(server: AdapterGameServer, *, session_id: str) -> dict[str, JsonValue]:
    return _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/replay",
        token=DEV_ADMIN_TOKEN,
    )


def _request(
    server: AdapterGameServer,
    *,
    method: str,
    path: str,
    token: str,
    query: dict[str, str] | None = None,
    body: JsonValue = None,
    expected_status: HTTPStatus = HTTPStatus.OK,
) -> dict[str, JsonValue]:
    response = server.handle(
        method=method,
        path=path,
        query=query,
        body=body,
        authorization=bearer_authorization(token),
    )
    assert response.status_code == expected_status, response.payload
    return _object(response.payload)


def _registry_with_coach_promoted_to_administrator() -> PrincipalRegistry:
    default = default_principal_registry()
    credentials = tuple(
        PrincipalCredential(
            token=credential.token,
            principal=AuthenticatedPrincipal(
                principal_id=credential.principal.principal_id,
                role=PrincipalRole.ADMINISTRATOR,
            ),
        )
        if credential.token == DEV_COACH_A_TOKEN
        else credential
        for credential in default.credentials
    )
    return PrincipalRegistry(
        credentials=credentials,
        authorization_epoch=default.authorization_epoch,
    )


def _rng_payload(session: LocalGameSession) -> JsonValue:
    state = session.lifecycle.state
    assert state is not None
    manager = DiceRollManager(
        state.game_id,
        event_log=session.lifecycle.decision_controller.event_log,
    )
    return cast(JsonValue, manager.rng.to_payload())


def _error_code(response: ServerResponse) -> str:
    return _string(_object(response.payload), "error", "code")


def _object(
    value: JsonValue,
    key: str | None = None,
    nested_key: str | None = None,
) -> dict[str, JsonValue]:
    selected = value
    if key is not None:
        assert isinstance(selected, dict)
        selected = selected[key]
    if nested_key is not None:
        assert isinstance(selected, dict)
        selected = selected[nested_key]
    assert isinstance(selected, dict)
    return selected


def _list(value: dict[str, JsonValue], key: str) -> list[JsonValue]:
    selected = value[key]
    assert isinstance(selected, list)
    return selected


def _string_list(value: dict[str, JsonValue], key: str) -> list[str]:
    result: list[str] = []
    for item in _list(value, key):
        assert type(item) is str
        result.append(item)
    return result


def _string(
    value: dict[str, JsonValue],
    key: str,
    nested_key: str | None = None,
) -> str:
    selected: JsonValue = value[key]
    if nested_key is not None:
        assert isinstance(selected, dict)
        selected = selected[nested_key]
    assert type(selected) is str
    return selected


def _integer(value: dict[str, JsonValue], key: str) -> int:
    selected = value[key]
    assert type(selected) is int
    return selected


__all__: list[str] = []
__all__ += ["AdapterGameServer", "AuthenticatedPrincipal", "AuthoritativeSession", "BattlePhase"]
__all__ += ["DEV_ADMIN_TOKEN", "DEV_COACH_A_TOKEN", "DEV_PLAYER_A_TOKEN", "Callable"]
__all__ += ["DEV_PLAYER_B_TOKEN", "DEV_SPECTATOR_TOKEN", "ENGINE_VERSION", "DiceRollManager"]
__all__ += ["FIXED_SECONDARY_OPTION_ID", "FROZEN_TIME", "Event", "GameLifecycle"]
__all__ += ["GameLifecycleStage", "HTTPStatus", "Iterator", "JsonValue", "LifecycleStatusKind"]
__all__ += ["Literal", "LocalGameSession", "LocalGameSessionPersistenceError", "MovementMode"]
__all__ += ["MovementPhaseActionKind", "MovementProposalPayload", "MovementProposalRequest"]
__all__ += ["PLAYER_A", "PLAYER_B", "MovementProposalRequestPayload", "Path", "Pose"]
__all__ += ["PrincipalCredential", "PrincipalRegistry", "PrincipalRole", "ReplayArtifact"]
__all__ += ["ReplayArtifactPayload", "ReplayProjectionCheckpoint", "ReplayRunStatus"]
__all__ += ["SESSION_CREATE_SCHEMA_VERSION", "ReplayRunner"]
__all__ += ["SESSION_PERSISTENCE_STORE_SCHEMA_VERSION", "SQLITE_SESSION_PERSISTENCE_USER_VERSION"]
__all__ += ["SQLITE_SESSION_STATE_TABLE", "SQLiteSessionPersistenceStore", "ServerResponse"]
__all__ += ["SessionCommandEnvelope", "SessionCommandJournalEntry"]
__all__ += ["SessionCommandSubmissionKind", "SessionCursorCodec", "SessionNonCommandOrigin"]
__all__ += ["SessionPersistenceCorruptionError", "SessionPersistenceDriftError"]
__all__ += ["SessionPersistenceError", "SessionPersistenceStorageError"]
__all__ += ["SessionPersistenceStore", "SessionProtocolError", "SessionRecoveryError"]
__all__ += ["UTC", "SessionRevisionCommitment", "SessionRevisionOrigin", "ThreadPoolExecutor"]
__all__ += ["_FalseyPersistenceStore", "_FaultingPersistenceStore", "_MemoryResource"]
__all__ += ["_UntypedAfterCommitStore", "_UntypedAfterInitializeStore"]
__all__ += ["_assert_command_hashes_are_self_consistent"]
__all__ += ["_assert_revision_chain_hashes_are_self_consistent", "_bind_snapshot_evidence"]
__all__ += ["_command", "_command_response", "_create_session", "_error_code", "_events"]
__all__ += ["_finite_envelope", "_first_session_payload", "_integer", "_lifecycle_envelope"]
__all__ += ["_list", "_metadata", "_movement_proposal_server", "_object"]
__all__ += ["_parameterized_envelope", "_pending_decision", "_phase_boundary_session"]
__all__ += ["_projection", "_registry_with_coach_promoted_to_administrator"]
__all__ += ["_rehash_command_revision", "_rehash_content_addressed_payload"]
__all__ += ["_rehash_revision_chain", "_replay", "_request", "_revision_domain_hash"]
__all__ += ["_revision_item", "_rng_payload", "_runtime_package_root", "_server"]
__all__ += ["_server_checkpoint_payload", "_server_with_fixed_secondary_choice"]
__all__ += ["_store_requires_initialization", "_string", "_string_list"]
__all__ += ["_write_runtime_manifest", "bearer_authorization", "build_identity", "canonical_json"]
__all__ += ["canonical_setup_prebattle_smoke_config", "cast", "closing"]
__all__ += ["commit_persistence_store", "copy", "dataclass", "datetime"]
__all__ += ["default_principal_registry", "fight_config", "fight_lifecycle", "hashlib"]
__all__ += ["isolated_engine_build_identity_cache", "json"]
__all__ += ["phase18l_journaled_root_checkpoint_payload"]
__all__ += ["phase18l_legacy_revision_root_checkpoint_payload"]
__all__ += ["phase18l_root_checkpoint_payload", "pytest"]
__all__ += ["record_primary_turn_start_evidence_for_fixture"]
__all__ += ["recover_server_persistence_payload", "server_persistence_payload"]
__all__ += ["session_recovery_module", "sqlite3", "straight_line_witness_for_unit", "timedelta"]
