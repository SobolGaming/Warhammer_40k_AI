from __future__ import annotations

import copy
import hashlib
import sqlite3
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
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
)
from warhammer40k_core.adapters.session_protocol import (
    AuthoritativeSession,
    SessionProtocolError,
)
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
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleStage,
    LifecycleStatusKind,
)
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


def test_phase18l_local_session_checkpoint_round_trips_exact_replay_projection_events_and_rng() -> (
    None
):
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config(game_id="phase18l-local-checkpoint"))
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert request is not None

    session.submit_option(
        request_id=request.request_id,
        option_id=FIXED_SECONDARY_OPTION_ID,
        result_id="phase18l-local-checkpoint-secondary",
    )
    payload = copy.deepcopy(session.to_persistence_payload())
    restored = LocalGameSession.from_persistence_payload(copy.deepcopy(payload))

    assert restored.to_persistence_payload() == payload
    assert restored.lifecycle.to_payload() == session.lifecycle.to_payload()
    assert restored.view(viewer_player_id=PLAYER_A) == session.view(viewer_player_id=PLAYER_A)
    assert restored.view(viewer_player_id=PLAYER_B) == session.view(viewer_player_id=PLAYER_B)
    assert restored.decision_record_count() == session.decision_record_count() == 1
    assert restored.event_record_count() == session.event_record_count()
    assert _rng_payload(restored) == _rng_payload(session)

    original_replay = session.replay_artifact(artifact_id="phase18l-local-replay")
    restored_replay = restored.replay_artifact(artifact_id="phase18l-local-replay")
    assert restored_replay == original_replay
    assert len(original_replay["decision_records"]) == 1
    assert len(original_replay["event_records"]) > 0
    replay_result = ReplayRunner.from_payload(restored_replay).run()
    assert replay_result.status is ReplayRunStatus.REPRODUCED


@pytest.mark.parametrize(
    "boundary",
    ["setup", "movement", "shooting", "charge", "fight", "terminal"],
)
def test_phase18l_local_session_round_trips_each_major_phase_boundary(
    boundary: str,
    tmp_path: Path,
) -> None:
    session = _phase_boundary_session(boundary)
    status = session.advance_until_decision_or_terminal()
    record = AuthoritativeSession.create(
        session_id=f"session:phase18l-checkpoint-{boundary}",
        adapter_session=session,
        config=session.lifecycle.config,
        lifecycle_status=status,
        created_at="2026-08-21T16:00:00Z",
        started=True,
    )
    checkpoint = _server_checkpoint_payload(record)
    database_path = tmp_path / f"phase18l-checkpoint-{boundary}.sqlite3"
    SQLiteSessionPersistenceStore(database_path=database_path).initialize(checkpoint)

    recovered_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    recovered_checkpoint = recovered_server.persistence_payload()

    assert recovered_checkpoint == checkpoint
    original_adapter = _object(_first_session_payload(checkpoint), "adapter_session")
    recovered_adapter = _object(
        _first_session_payload(recovered_checkpoint),
        "adapter_session",
    )
    for hash_field in (
        "lifecycle_hash",
        "decision_records_hash",
        "event_log_hash",
        "rng_state_hash",
        "content_hash",
    ):
        assert recovered_adapter[hash_field] == original_adapter[hash_field]
    state = session.lifecycle.state
    assert state is not None
    if boundary == "terminal":
        assert state.stage is GameLifecycleStage.COMPLETE
        assert status.status_kind is LifecycleStatusKind.TERMINAL
    elif boundary == "setup":
        assert state.stage is GameLifecycleStage.SETUP
    else:
        assert state.stage is GameLifecycleStage.BATTLE
        assert state.current_battle_phase is BattlePhase(boundary)


def test_phase18l_authoritative_closed_checkpoint_round_trips(tmp_path: Path) -> None:
    session = _phase_boundary_session("terminal")
    status = session.advance_until_decision_or_terminal()
    record = AuthoritativeSession.create(
        session_id="session:phase18l-closed",
        adapter_session=session,
        config=session.lifecycle.config,
        lifecycle_status=status,
        created_at="2026-08-21T16:00:00Z",
        started=True,
    )
    record.revision_retention_limit = 1
    record.close(
        timestamp="2026-08-21T16:00:01Z",
        origin=SessionRevisionOrigin.noncommand(SessionNonCommandOrigin.SESSION_CLOSED),
    )
    checkpoint = _server_checkpoint_payload(record)
    database_path = tmp_path / "phase18l-checkpoint-closed.sqlite3"
    SQLiteSessionPersistenceStore(database_path=database_path).initialize(checkpoint)

    recovered_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    recovered_checkpoint = recovered_server.persistence_payload()
    restored_payload = _first_session_payload(recovered_checkpoint)

    assert recovered_checkpoint == checkpoint
    assert restored_payload["closed"] is True
    assert restored_payload["started"] is True
    assert restored_payload["session_revision"] == 1


def test_phase18l_sqlite_restart_restores_idempotency_cursors_and_exact_role_views(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase18l-restart.sqlite3"
    first_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    session_id = _create_session(first_server, game_id="phase18l-sqlite-restart")
    start_envelope = _lifecycle_envelope(
        session_id=session_id,
        command_id="phase18l-restart-start",
        expected_revision=0,
        submission_kind=SessionCommandSubmissionKind.START_SESSION,
    )
    _command(first_server, token=DEV_ADMIN_TOKEN, envelope=start_envelope)
    pending = _pending_decision(
        first_server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
    )
    finite_envelope = _finite_envelope(
        session_id=session_id,
        command_id="phase18l-restart-secondary",
        expected_revision=1,
        request_id=_string(pending, "request_id"),
        result_id="phase18l-restart-secondary-result",
        option_id=FIXED_SECONDARY_OPTION_ID,
    )
    committed = _command(
        first_server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=finite_envelope,
    )

    role_tokens = {
        "player": DEV_PLAYER_A_TOKEN,
        "opponent": DEV_PLAYER_B_TOKEN,
        "coach": DEV_COACH_A_TOKEN,
        "delayed_spectator": DEV_SPECTATOR_TOKEN,
        "administrator": DEV_ADMIN_TOKEN,
    }
    views_before = {
        role: _projection(first_server, session_id=session_id, token=token)
        for role, token in role_tokens.items()
    }
    player_cursor = _string(views_before["player"], "event_cursor")
    metadata_before = _metadata(first_server, session_id=session_id)
    replay_before = _replay(first_server, session_id=session_id)

    recovered_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    retried = _command(
        recovered_server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=finite_envelope,
    )

    assert retried == committed
    assert _metadata(recovered_server, session_id=session_id) == metadata_before
    assert _replay(recovered_server, session_id=session_id) == replay_before
    assert len(_list(replay_before, "decision_records")) == 1
    assert {
        role: _projection(recovered_server, session_id=session_id, token=token)
        for role, token in role_tokens.items()
    } == views_before
    assert _string(views_before["player"], "visibility_role") == "player"
    assert _string(views_before["opponent"], "visibility_role") == "player"
    assert _string(views_before["coach"], "visibility_role") == "coach"
    assert _string(views_before["delayed_spectator"], "visibility_role") == ("delayed_spectator")
    assert _string(views_before["administrator"], "visibility_role") == "administrator"

    resumed = _events(
        recovered_server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=player_cursor,
    )
    assert resumed["resync_required"] is False
    assert resumed["events"] == []
    assert resumed["next_cursor"] == player_cursor

    wrong_role = _events(
        recovered_server,
        session_id=session_id,
        token=DEV_PLAYER_B_TOKEN,
        cursor=player_cursor,
    )
    assert wrong_role["resync_required"] is True
    assert wrong_role["resync_reason"] == "wrong_viewer"
    coach_mutation = _command_response(
        recovered_server,
        token=DEV_COACH_A_TOKEN,
        envelope=finite_envelope,
    )
    assert coach_mutation.status_code == HTTPStatus.FORBIDDEN
    assert _error_code(coach_mutation) == "access_denied"


def test_phase18l_restart_tolerates_retained_cursor_expired_for_another_principal(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase18l-expired-cross-principal-cursor.sqlite3"
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    first_server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        event_retention_limit=2,
        clock=lambda: FROZEN_TIME,
    )
    first_server.initialize_persistence(store)
    session_id = _create_session(
        first_server,
        game_id="phase18l-expired-cross-principal-cursor",
    )
    player_b_cursor = _string(
        _projection(first_server, session_id=session_id, token=DEV_PLAYER_B_TOKEN),
        "event_cursor",
    )
    _command(
        first_server,
        token=DEV_ADMIN_TOKEN,
        envelope=_lifecycle_envelope(
            session_id=session_id,
            command_id="phase18l-expired-cross-principal-start",
            expected_revision=0,
            submission_kind=SessionCommandSubmissionKind.START_SESSION,
        ),
    )
    player_a_cursor = _string(
        _projection(first_server, session_id=session_id, token=DEV_PLAYER_A_TOKEN),
        "event_cursor",
    )
    assert first_server.cursor_codec.decode(player_b_cursor).principal_id != (
        first_server.cursor_codec.decode(player_a_cursor).principal_id
    )

    recovered_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    expired = _events(
        recovered_server,
        session_id=session_id,
        token=DEV_PLAYER_B_TOKEN,
        cursor=player_b_cursor,
    )

    assert expired["resync_required"] is True
    assert expired["resync_reason"] == "expired"
    assert expired["events"] == []
    assert expired["next_cursor"] != player_b_cursor


def test_phase18l_restart_restores_latest_activity_after_successful_reads(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase18l-read-touch.sqlite3"
    tick = 0

    def advancing_clock() -> datetime:
        nonlocal tick
        value = FROZEN_TIME + timedelta(seconds=tick)
        tick += 1
        return value

    store = SQLiteSessionPersistenceStore(database_path=database_path)
    first_server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=advancing_clock,
    )
    first_server.initialize_persistence(store)
    session_id = _create_session(first_server, game_id="phase18l-read-touch")
    _metadata(first_server, session_id=session_id)
    _projection(first_server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    checkpoint = first_server.persistence_payload()
    checkpoint_session = _first_session_payload(checkpoint)
    expected_last_activity = "2026-08-21T16:00:02Z"

    recovered_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    recovered = recovered_server.persistence_payload()

    assert recovered == checkpoint
    assert checkpoint_session["last_activity_at"] == expected_last_activity
    snapshots = _list(checkpoint_session, "revision_snapshots")
    assert _object(snapshots[-1])["last_activity_at"] == "2026-08-21T16:00:00Z"


def test_phase18l_restart_accepts_journal_timestamp_before_later_read_touch(
    tmp_path: Path,
) -> None:
    tick = 0

    def advancing_clock() -> datetime:
        nonlocal tick
        value = FROZEN_TIME + timedelta(seconds=tick)
        tick += 1
        return value

    store = SQLiteSessionPersistenceStore(
        database_path=tmp_path / "phase18l-journal-read-touch.sqlite3"
    )
    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=advancing_clock,
    )
    server.initialize_persistence(store)
    session_id = _create_session(server, game_id="phase18l-journal-read-touch")
    _command(
        server,
        token=DEV_ADMIN_TOKEN,
        envelope=_lifecycle_envelope(
            session_id=session_id,
            command_id="phase18l-journal-read-touch-start",
            expected_revision=0,
            submission_kind=SessionCommandSubmissionKind.START_SESSION,
        ),
    )
    _metadata(server, session_id=session_id)
    checkpoint = server.persistence_payload()

    recovered = _server(store)

    assert recovered.persistence_payload() == checkpoint


def test_phase18l_recovery_rejects_participant_role_widening(tmp_path: Path) -> None:
    database_path = tmp_path / "phase18l-role-drift.sqlite3"
    server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    _create_session(server, game_id="phase18l-role-drift")
    widened_registry = _registry_with_coach_promoted_to_administrator()

    with pytest.raises(SessionRecoveryError):
        _server(
            SQLiteSessionPersistenceStore(database_path=database_path),
            principal_registry=widened_registry,
        )


def test_phase18l_recorded_invalid_command_is_durable_and_idempotent(
    tmp_path: Path,
) -> None:
    server, store, session_id, request, invalid_payload = _movement_proposal_server(
        database_path=tmp_path / "phase18l-recorded-invalid.sqlite3",
        session_suffix="recorded-invalid",
    )
    envelope = _parameterized_envelope(
        session_id=session_id,
        command_id="phase18l-recorded-invalid-command",
        expected_revision=2,
        request_id=_string(request, "request_id"),
        result_id="phase18l-recorded-invalid-result",
        payload=invalid_payload,
    )

    rejected = _command_response(server, token=DEV_PLAYER_A_TOKEN, envelope=envelope)

    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    outcome = _object(rejected.payload)
    assert outcome["committed"] is True
    assert outcome["accepted"] is False
    assert outcome["outcome_code"] == "proposal_invalid"
    assert _integer(_object(outcome, "session"), "session_revision") == 3
    checkpoint = server.persistence_payload()
    recovered = _server(store)
    duplicate = _command_response(
        recovered,
        token=DEV_PLAYER_A_TOKEN,
        envelope=envelope,
    )

    assert duplicate == rejected
    assert recovered.persistence_payload() == checkpoint
    assert _integer(_metadata(recovered, session_id=session_id), "session_revision") == 3
    assert len(_list(_replay(recovered, session_id=session_id), "decision_records")) == 3


def test_phase18l_unrecorded_invalid_command_preserves_exact_checkpoint(
    tmp_path: Path,
) -> None:
    server, store, session_id, request, invalid_payload = _movement_proposal_server(
        database_path=tmp_path / "phase18l-unrecorded-invalid.sqlite3",
        session_suffix="unrecorded-invalid",
    )
    invalid_payload["proposal_request_id"] = "phase18l-stale-proposal-request"
    envelope = _parameterized_envelope(
        session_id=session_id,
        command_id="phase18l-unrecorded-invalid-command",
        expected_revision=2,
        request_id=_string(request, "request_id"),
        result_id="phase18l-unrecorded-invalid-result",
        payload=invalid_payload,
    )
    before = server.persistence_payload()

    rejected = _command_response(server, token=DEV_PLAYER_A_TOKEN, envelope=envelope)

    assert rejected.status_code == HTTPStatus.UNPROCESSABLE_ENTITY
    assert _error_code(rejected) == "proposal_invalid"
    assert server.persistence_payload() == before
    recovered = _server(store)
    assert recovered.persistence_payload() == before
    repeated = _command_response(recovered, token=DEV_PLAYER_A_TOKEN, envelope=envelope)
    assert repeated == rejected
    assert recovered.persistence_payload() == before


@pytest.mark.parametrize("failure_point", ["before", "after"])
def test_phase18l_crash_before_or_after_atomic_commit_recovers_exactly_once(
    tmp_path: Path,
    failure_point: Literal["before", "after"],
) -> None:
    database_path = tmp_path / f"phase18l-crash-{failure_point}.sqlite3"
    durable_store = SQLiteSessionPersistenceStore(database_path=database_path)
    faulting_store = _FaultingPersistenceStore(delegate=durable_store)
    crashing_server = _server(faulting_store)
    session_id = _create_session(
        crashing_server,
        game_id=f"phase18l-crash-{failure_point}",
    )
    envelope = _lifecycle_envelope(
        session_id=session_id,
        command_id=f"phase18l-crash-{failure_point}-start",
        expected_revision=0,
        submission_kind=SessionCommandSubmissionKind.START_SESSION,
    )
    faulting_store.arm(failure_point)

    interrupted = _command_response(
        crashing_server,
        token=DEV_ADMIN_TOKEN,
        envelope=envelope,
    )

    assert interrupted.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert _error_code(interrupted) == "session_persistence_unavailable"
    unavailable = crashing_server.handle(
        method="GET",
        path=f"/sessions/{session_id}",
        authorization=bearer_authorization(DEV_ADMIN_TOKEN),
    )
    assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert _error_code(unavailable) == "session_persistence_unavailable"
    with pytest.raises(SessionPersistenceError, match="cannot export a checkpoint"):
        crashing_server.persistence_payload()

    recovered_server = _server(SQLiteSessionPersistenceStore(database_path=database_path))
    recovered_before_retry = _metadata(recovered_server, session_id=session_id)
    expected_revision = 0 if failure_point == "before" else 1
    assert _integer(recovered_before_retry, "session_revision") == expected_revision

    committed = _command(recovered_server, token=DEV_ADMIN_TOKEN, envelope=envelope)
    duplicate = _command(recovered_server, token=DEV_ADMIN_TOKEN, envelope=envelope)
    assert duplicate == committed
    assert _integer(_object(committed, "session"), "session_revision") == 1
    assert _integer(_metadata(recovered_server, session_id=session_id), "session_revision") == 1
    replay_after_commit = _replay(recovered_server, session_id=session_id)
    assert _replay(recovered_server, session_id=session_id) == replay_after_commit


@pytest.mark.parametrize("error_type", [OSError, RuntimeError])
def test_phase18l_untyped_custom_store_post_commit_failure_latches_fail_stop(
    tmp_path: Path,
    error_type: type[OSError] | type[RuntimeError],
) -> None:
    database_path = tmp_path / f"phase18l-untyped-{error_type.__name__}.sqlite3"
    delegate = SQLiteSessionPersistenceStore(database_path=database_path)
    store = _UntypedAfterCommitStore(delegate=delegate, error_type=error_type)
    server = _server(store)
    game_id = f"phase18l-untyped-{error_type.__name__}"
    response = server.handle(
        method="POST",
        path="/sessions",
        authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        body={
            "schema_version": SESSION_CREATE_SCHEMA_VERSION,
            "config": cast(
                JsonValue,
                canonical_setup_prebattle_smoke_config(game_id=game_id).to_payload(),
            ),
        },
    )

    assert response.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert _error_code(response) == "session_persistence_unavailable"
    unavailable = server.handle(
        method="GET",
        path="/rules-catalog",
        authorization=bearer_authorization(DEV_ADMIN_TOKEN),
    )
    assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    recovered = _server(delegate)
    assert _string(_metadata(recovered, session_id=f"session-{game_id}"), "game_id") == game_id


@pytest.mark.parametrize("tamper_kind", ["payload_json", "content_hash"])
def test_phase18l_sqlite_tampering_fails_closed(
    tmp_path: Path,
    tamper_kind: Literal["payload_json", "content_hash"],
) -> None:
    database_path = tmp_path / f"phase18l-tamper-{tamper_kind}.sqlite3"
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    server = _server(store)
    _create_session(server, game_id=f"phase18l-tamper-{tamper_kind}")

    with sqlite3.connect(database_path) as connection:
        if tamper_kind == "payload_json":
            connection.execute(
                f"UPDATE {SQLITE_SESSION_STATE_TABLE} SET payload_json = ?",
                ("{",),
            )
        else:
            connection.execute(
                f"UPDATE {SQLITE_SESSION_STATE_TABLE} SET content_hash = ?",
                ("0" * 64,),
            )
        connection.commit()

    with pytest.raises(SessionPersistenceCorruptionError):
        SQLiteSessionPersistenceStore(database_path=database_path).load()
    with pytest.raises(SessionRecoveryError):
        _server(SQLiteSessionPersistenceStore(database_path=database_path))


def test_phase18l_sqlite_requires_explicit_first_boot_initialization(tmp_path: Path) -> None:
    database_path = tmp_path / "phase18l-explicit-initialize.sqlite3"
    store = SQLiteSessionPersistenceStore(database_path=database_path)

    assert not database_path.exists()
    with pytest.raises(SessionPersistenceStorageError):
        store.load()
    assert not database_path.exists()

    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=lambda: FROZEN_TIME,
    )
    initial_root = server.persistence_payload()
    server.initialize_persistence(store)

    assert store.load() == initial_root
    assert (
        AdapterGameServer(
            persistence_store=store,
            principal_registry=default_principal_registry(),
            clock=lambda: FROZEN_TIME,
        ).persistence_payload()
        == initial_root
    )
    with pytest.raises(SessionPersistenceDriftError):
        store.initialize(initial_root)


def test_phase18l_persistence_initialization_cannot_escape_fail_stop_or_replace_falsey_store(
    tmp_path: Path,
) -> None:
    first_delegate = SQLiteSessionPersistenceStore(
        database_path=tmp_path / "phase18l-ambiguous-initialize.sqlite3"
    )
    replacement = SQLiteSessionPersistenceStore(
        database_path=tmp_path / "phase18l-replacement-initialize.sqlite3"
    )
    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=lambda: FROZEN_TIME,
    )
    initial_root = server.persistence_payload()

    with pytest.raises(OSError, match="after durable initialization"):
        server.initialize_persistence(_UntypedAfterInitializeStore(first_delegate))
    with pytest.raises(SessionPersistenceError, match="fresh server authority"):
        server.initialize_persistence(replacement)
    with pytest.raises(SessionPersistenceError, match="cannot export a checkpoint"):
        server.persistence_payload()

    assert not replacement.database_path.exists()
    unavailable = server.handle(
        method="GET",
        path="/rules-catalog",
        authorization=bearer_authorization(DEV_ADMIN_TOKEN),
    )
    assert unavailable.status_code == HTTPStatus.SERVICE_UNAVAILABLE
    assert _error_code(unavailable) == "session_persistence_unavailable"
    assert first_delegate.load() == initial_root

    attached_delegate = SQLiteSessionPersistenceStore(
        database_path=tmp_path / "phase18l-falsey-attached.sqlite3"
    )
    attached_store = _FalseyPersistenceStore(attached_delegate)
    attached_server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=lambda: FROZEN_TIME,
    )
    attached_server.initialize_persistence(attached_store)
    with pytest.raises(SessionPersistenceError, match="requires empty state"):
        attached_server.initialize_persistence(replacement)

    assert attached_server.persistence_store is attached_store


def test_phase18l_deleted_sqlite_singleton_root_is_corruption_not_first_boot(
    tmp_path: Path,
) -> None:
    database_path = tmp_path / "phase18l-deleted-root.sqlite3"
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    server = _server(store)
    _create_session(server, game_id="phase18l-deleted-root")
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DELETE FROM {SQLITE_SESSION_STATE_TABLE}")
        connection.commit()

    with pytest.raises(SessionPersistenceCorruptionError):
        store.load()
    with pytest.raises(SessionRecoveryError):
        AdapterGameServer(
            persistence_store=store,
            principal_registry=default_principal_registry(),
            clock=lambda: FROZEN_TIME,
        )


@pytest.mark.parametrize(
    ("trigger_name", "trigger_timing", "trigger_operation", "trigger_body"),
    [
        pytest.param(
            "forged_ignore_insert",
            "BEFORE",
            "INSERT",
            "SELECT RAISE(IGNORE);",
            id="before-insert-raise-ignore",
        ),
        pytest.param(
            "forged_rewrite_update",
            "AFTER",
            "UPDATE",
            (
                f"UPDATE {SQLITE_SESSION_STATE_TABLE} "
                "SET payload_json = 'null', content_hash = '"
                + hashlib.sha256(b"null").hexdigest()
                + "' WHERE singleton_id = 1;"
            ),
            id="after-update-rewrite",
        ),
    ],
)
def test_phase18l_sqlite_commit_rejects_ignore_and_rewrite_triggers(
    tmp_path: Path,
    trigger_name: str,
    trigger_timing: Literal["BEFORE", "AFTER"],
    trigger_operation: Literal["INSERT", "UPDATE"],
    trigger_body: str,
) -> None:
    database_path = tmp_path / "phase18l-trigger.sqlite3"
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    server = _server(store)
    before = store.load()
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            f"CREATE TRIGGER {trigger_name} {trigger_timing} {trigger_operation} "
            f"ON {SQLITE_SESSION_STATE_TABLE} "
            f"BEGIN {trigger_body} END"
        )
        connection.commit()

    with pytest.raises(SessionPersistenceDriftError):
        store.commit({"forged": True})
    with sqlite3.connect(database_path) as connection:
        connection.execute(f"DROP TRIGGER {trigger_name}")
        connection.commit()
    assert store.load() == before
    assert server.persistence_payload() == before


@pytest.mark.parametrize("missing_constraint", ["strict", "singleton_check"])
def test_phase18l_sqlite_rejects_missing_strict_or_singleton_check(
    tmp_path: Path,
    missing_constraint: Literal["strict", "singleton_check"],
) -> None:
    database_path = tmp_path / f"phase18l-missing-{missing_constraint}.sqlite3"
    payload: JsonValue = {"initialized": True}
    payload_json = canonical_json(payload)
    content_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
    check_sql = "" if missing_constraint == "singleton_check" else " CHECK(singleton_id = 1)"
    strict_sql = "" if missing_constraint == "strict" else " STRICT"
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute(
            f"CREATE TABLE {SQLITE_SESSION_STATE_TABLE} ("
            f"singleton_id INTEGER NOT NULL PRIMARY KEY{check_sql}, "
            "schema_version TEXT NOT NULL, payload_json TEXT NOT NULL, "
            f"content_hash TEXT NOT NULL){strict_sql}"
        )
        connection.execute(f"PRAGMA user_version={SQLITE_SESSION_PERSISTENCE_USER_VERSION}")
        connection.execute(
            f"INSERT INTO {SQLITE_SESSION_STATE_TABLE} VALUES (1, ?, ?, ?)",
            (SESSION_PERSISTENCE_STORE_SCHEMA_VERSION, payload_json, content_hash),
        )
        connection.commit()

    with pytest.raises(SessionPersistenceDriftError):
        SQLiteSessionPersistenceStore(database_path=database_path).load()


def test_phase18l_sqlite_schema_cannot_change_between_validation_and_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    database_path = tmp_path / "phase18l-schema-race.sqlite3"
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    _server(store)
    entered_validation = Event()
    release_commit = Event()
    original_validation = cast(
        Callable[[SQLiteSessionPersistenceStore, sqlite3.Connection], None],
        vars(SQLiteSessionPersistenceStore)["_validate_database_schema"],
    )

    def paused_validation(
        target: SQLiteSessionPersistenceStore,
        connection: sqlite3.Connection,
    ) -> None:
        original_validation(target, connection)
        entered_validation.set()
        assert release_commit.wait(timeout=5)

    monkeypatch.setattr(
        SQLiteSessionPersistenceStore,
        "_validate_database_schema",
        paused_validation,
    )
    with ThreadPoolExecutor(max_workers=1) as executor:
        commit = executor.submit(store.commit, {"generation": 2})
        assert entered_validation.wait(timeout=5)
        try:
            with sqlite3.connect(database_path, timeout=0.05) as concurrent:
                concurrent.execute("PRAGMA busy_timeout=50")
                with pytest.raises(sqlite3.OperationalError, match="locked"):
                    concurrent.execute("CREATE TABLE raced_schema(value TEXT) STRICT")
        finally:
            release_commit.set()
        commit.result(timeout=5)
    assert store.load() == {"generation": 2}


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


@pytest.mark.parametrize(
    "origin_tamper",
    [
        "creation_moved_off_revision_zero",
        "legacy_finite_relabelled_parameterized",
        "close_origin_without_closed_state",
    ],
)
def test_phase18l_coherent_typed_origin_swaps_fail_closed(
    phase18l_legacy_revision_root_checkpoint_payload: dict[str, JsonValue],
    origin_tamper: str,
) -> None:
    payload = copy.deepcopy(phase18l_legacy_revision_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    revision_zero = _revision_item(session_payload, "revision_history", revision=0)
    revision_one = _revision_item(session_payload, "revision_history", revision=1)
    revision_two = _revision_item(session_payload, "revision_history", revision=2)
    if origin_tamper == "creation_moved_off_revision_zero":
        revision_zero["origin"] = copy.deepcopy(_object(revision_one, "origin"))
        revision_one["origin"] = cast(
            JsonValue,
            SessionRevisionOrigin.noncommand(SessionNonCommandOrigin.SESSION_CREATED).to_payload(),
        )
    elif origin_tamper == "legacy_finite_relabelled_parameterized":
        revision_two["origin"] = cast(
            JsonValue,
            SessionRevisionOrigin.noncommand(
                SessionNonCommandOrigin.LEGACY_PARAMETERIZED_DECISION
            ).to_payload(),
        )
    else:
        assert origin_tamper == "close_origin_without_closed_state"
        assert session_payload["closed"] is False
        revision_one["origin"] = cast(
            JsonValue,
            SessionRevisionOrigin.noncommand(SessionNonCommandOrigin.SESSION_CLOSED).to_payload(),
        )
    _rehash_revision_chain(session_payload)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_serialization_rejects_live_history_beyond_latest_commitment() -> None:
    config = canonical_setup_prebattle_smoke_config(game_id="phase18l-live-history-drift")
    session = LocalGameSession()
    initial_status = session.start(config)
    record = AuthoritativeSession.create(
        session_id="session:phase18l-live-history-drift",
        adapter_session=session,
        config=config,
        lifecycle_status=initial_status,
        created_at="2026-08-21T16:00:00Z",
    )
    latest_snapshot = record.current_snapshot()
    captured_checkpoint = latest_snapshot.adapter_session.to_persistence_payload()
    captured_event_count = latest_snapshot.event_count

    session.advance_until_decision_or_terminal()

    assert session.event_record_count() > captured_event_count
    assert canonical_json(session.to_persistence_payload()) != canonical_json(captured_checkpoint)
    with pytest.raises(SessionProtocolError):
        _server_checkpoint_payload(record)


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "schema",
        "engine",
        "external_contract",
        "ruleset",
        "catalog",
        "source",
        "package",
    ],
)
def test_phase18l_root_identity_drift_fails_closed(
    phase18l_root_checkpoint_payload: dict[str, JsonValue],
    tamper_kind: str,
) -> None:
    payload = copy.deepcopy(phase18l_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    if tamper_kind == "schema":
        payload["schema_version"] = "forged-session-persistence-schema"
    elif tamper_kind == "engine":
        payload["engine_build_id"] = "forged-engine-build"
    elif tamper_kind == "external_contract":
        payload["external_contract_version"] = "forged-external-contract"
    elif tamper_kind == "ruleset":
        session_payload["ruleset_descriptor_hash"] = "0" * 64
    elif tamper_kind == "catalog":
        session_payload["catalog_id"] = "forged-catalog"
    elif tamper_kind == "source":
        session_payload["source_hash"] = "0" * 64
    else:
        assert tamper_kind == "package"
        session_payload["source_package_id"] = "forged-source-package"
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_same_package_version_different_build_fingerprint_fails_before_recovery(
    phase18l_root_checkpoint_payload: dict[str, JsonValue],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = copy.deepcopy(phase18l_root_checkpoint_payload)
    persisted_build_id = _string(payload, "engine_build_id")
    changed_fingerprint = "0" if persisted_build_id[-1] != "0" else "1"
    other_build_id = f"{persisted_build_id[:-1]}{changed_fingerprint}"
    recovery_calls: list[JsonValue] = []

    def unexpected_recovery(checkpoint: JsonValue) -> LocalGameSession:
        recovery_calls.append(checkpoint)
        return LocalGameSession.from_persistence_payload(checkpoint)

    assert payload["engine_version"] == ENGINE_VERSION
    monkeypatch.setattr(session_recovery_module, "ENGINE_BUILD_ID", other_build_id)
    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=unexpected_recovery,
        )
    assert recovery_calls == []


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "duplicate_journal",
        "duplicate_snapshot",
        "missing_snapshot",
        "authorization_epoch_bool",
        "cursor_version_bool",
        "cursor_secret_noncanonical",
        "journal_response_command",
        "journal_response_schema",
        "journal_response_revision_bool",
        "lifecycle_decision_request",
    ],
)
def test_phase18l_structural_and_cached_outcome_drift_fails_closed(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
    tamper_kind: str,
) -> None:
    payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    journal = _list(session_payload, "command_journal")
    snapshots = _list(session_payload, "revision_snapshots")
    assert journal
    assert len(snapshots) >= 3
    if tamper_kind == "duplicate_journal":
        journal.append(copy.deepcopy(journal[0]))
    elif tamper_kind == "duplicate_snapshot":
        snapshots.append(copy.deepcopy(snapshots[0]))
    elif tamper_kind == "missing_snapshot":
        snapshots.pop(1)
    elif tamper_kind == "authorization_epoch_bool":
        bindings = _object(payload, "authorization_bindings")
        bindings["authorization_epoch"] = False
    elif tamper_kind == "cursor_version_bool":
        cursor_codec = _object(payload, "cursor_codec")
        cursors = _list(cursor_codec, "cursors")
        assert cursors
        _object(_object(cursors[0]), "cursor")["v"] = True
    elif tamper_kind == "cursor_secret_noncanonical":
        cursor_codec = _object(payload, "cursor_codec")
        cursor_codec["secret_hex"] = f" {_string(cursor_codec, 'secret_hex')}"
    elif tamper_kind == "journal_response_command":
        response = _object(_object(journal[0]), "response_payload")
        response["command_id"] = "phase18l-forged-command"
    elif tamper_kind == "journal_response_schema":
        response = _object(_object(journal[0]), "response_payload")
        _object(response, "session")["schema_version"] = "forged-session-metadata"
    elif tamper_kind == "journal_response_revision_bool":
        response = _object(_object(journal[0]), "response_payload")
        _object(response, "session")["session_revision"] = True
    else:
        assert tamper_kind == "lifecycle_decision_request"
        lifecycle_status = _object(session_payload, "lifecycle_status")
        decision_request = _object(lifecycle_status, "decision_request")
        decision_request["request_id"] = ""
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_retained_snapshot_from_another_game_fails_closed(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
) -> None:
    payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    snapshots = _list(session_payload, "revision_snapshots")
    other = _phase_boundary_session("movement")
    other.advance_until_decision_or_terminal()
    _object(snapshots[0])["adapter_session"] = other.to_persistence_payload()
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_valid_alternate_branch_snapshot_fails_exact_history_chain() -> None:
    game_id = "phase18l-alternate-valid-branch"
    original_server = _server_with_fixed_secondary_choice(game_id=game_id, option_index=0)
    alternate_server = _server_with_fixed_secondary_choice(game_id=game_id, option_index=1)
    payload = copy.deepcopy(original_server.persistence_payload())
    original_session = _first_session_payload(payload)
    alternate_session = _first_session_payload(alternate_server.persistence_payload())
    current_revision = _integer(original_session, "session_revision")
    assert current_revision >= 3
    current_snapshot = _revision_item(
        original_session,
        "revision_snapshots",
        revision=current_revision,
    )
    current_snapshot_before_tamper = copy.deepcopy(current_snapshot)
    current_adapter_before_tamper = copy.deepcopy(_object(original_session, "adapter_session"))
    original_snapshot = _revision_item(original_session, "revision_snapshots", revision=2)
    alternate_snapshot = _revision_item(alternate_session, "revision_snapshots", revision=2)
    original_snapshot.clear()
    original_snapshot.update(copy.deepcopy(alternate_snapshot))
    commitment = _revision_item(original_session, "revision_history", revision=2)
    _bind_snapshot_evidence(commitment=commitment, snapshot=original_snapshot)
    _rehash_revision_chain(original_session)
    _assert_revision_chain_hashes_are_self_consistent(original_session)
    assert current_snapshot == current_snapshot_before_tamper
    assert _object(original_session, "adapter_session") == current_adapter_before_tamper
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_coherent_projection_and_authenticated_cursor_drift_fails_closed(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
) -> None:
    payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    journal_entry = _object(_list(session_payload, "command_journal")[-1])
    revision = _integer(journal_entry, "committed_session_revision")
    commitment = _revision_item(session_payload, "revision_history", revision=revision)
    to_cursor = _object(commitment, "to_cursor")
    cursor_state = _object(to_cursor, "cursor")
    codec = SessionCursorCodec.from_persistence_payload(_object(payload, "cursor_codec"))
    registry = default_principal_registry()
    principal = registry.authenticate(bearer_authorization(DEV_PLAYER_A_TOKEN))
    viewer = principal.bind_to_session(
        player_ids=tuple(_string_list(session_payload, "player_ids")),
        authorization_epoch=registry.authorization_epoch,
    )
    forged_hash = "0" * 64
    forged_token = codec.issue(
        session_id=_string(cursor_state, "s"),
        viewer=viewer,
        offset=_integer(cursor_state, "o"),
        visible_sequence=_integer(cursor_state, "q"),
        session_revision=_integer(cursor_state, "r"),
        projection_state_hash=forged_hash,
        minimum_offset=0,
        minimum_revision=0,
    )
    forged_cursor = codec.committed_cursor(forged_token)
    codec_payload = codec.to_persistence_payload()
    codec_payload["cursors"] = [
        item
        for item in _list(codec_payload, "cursors")
        if _string(_object(item), "token") != forged_token
    ]
    payload["cursor_codec"] = cast(JsonValue, codec_payload)
    to_cursor["token"] = forged_token
    to_cursor["cursor"] = cast(JsonValue, forged_cursor.to_payload())
    response = _object(journal_entry, "response_payload")
    metadata = _object(response, "session")
    checkpoint = _object(response, "checkpoint")
    event_range = _object(response, "event_range")
    metadata["projection_state_hash"] = forged_hash
    metadata["event_cursor"] = forged_token
    checkpoint["projection_state_hash"] = forged_hash
    checkpoint["event_cursor"] = forged_token
    event_range["to_cursor"] = forged_token
    _rehash_command_revision(session_payload, journal_entry=journal_entry)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _assert_command_hashes_are_self_consistent(
        session_payload,
        journal_entry=journal_entry,
    )
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=registry,
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_another_authenticated_cursor_cannot_replace_command_cursor(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
) -> None:
    payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    journal_entry = _object(_list(session_payload, "command_journal")[-1])
    revision = _integer(journal_entry, "committed_session_revision")
    commitment = _revision_item(session_payload, "revision_history", revision=revision)
    from_cursor = copy.deepcopy(_object(commitment, "from_cursor"))
    commitment["to_cursor"] = cast(JsonValue, from_cursor)
    replacement_token = _string(from_cursor, "token")
    replacement_hash = _string(_object(from_cursor, "cursor"), "h")
    response = _object(journal_entry, "response_payload")
    metadata = _object(response, "session")
    checkpoint = _object(response, "checkpoint")
    metadata["projection_state_hash"] = replacement_hash
    metadata["event_cursor"] = replacement_token
    checkpoint["projection_state_hash"] = replacement_hash
    checkpoint["event_cursor"] = replacement_token
    _object(response, "event_range")["to_cursor"] = replacement_token
    _rehash_command_revision(session_payload, journal_entry=journal_entry)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _assert_command_hashes_are_self_consistent(
        session_payload,
        journal_entry=journal_entry,
    )
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_missing_journal_is_detected_after_origin_snapshot_pruned() -> None:
    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=lambda: FROZEN_TIME,
    )
    session_id = _create_session(server, game_id="phase18l-pruned-journal")
    server._sessions[session_id].revision_retention_limit = 1  # pyright: ignore[reportPrivateUsage]
    _command(
        server,
        token=DEV_ADMIN_TOKEN,
        envelope=_lifecycle_envelope(
            session_id=session_id,
            command_id="phase18l-pruned-journal-start",
            expected_revision=0,
            submission_kind=SessionCommandSubmissionKind.START_SESSION,
        ),
    )
    pending = _pending_decision(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    options = _list(pending, "options")
    _command(
        server,
        token=DEV_PLAYER_A_TOKEN,
        envelope=_finite_envelope(
            session_id=session_id,
            command_id="phase18l-pruned-journal-choice",
            expected_revision=1,
            request_id=_string(pending, "request_id"),
            result_id="phase18l-pruned-journal-choice-result",
            option_id=_string(_object(options[0]), "option_id"),
        ),
    )
    payload = copy.deepcopy(server.persistence_payload())
    session_payload = _first_session_payload(payload)
    snapshots = _list(session_payload, "revision_snapshots")
    assert [_integer(_object(item), "session_revision") for item in snapshots] == [2]
    journal = _list(session_payload, "command_journal")
    journal.pop(0)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_changed_envelope_and_fingerprint_must_match_decision_history(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
) -> None:
    payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    journal_entry = _object(_list(session_payload, "command_journal")[-1])
    envelope_payload = _object(journal_entry, "command_envelope")
    submission = _object(envelope_payload, "submission")
    submission["option_id"] = "syntactically-valid-but-unselected-option"
    changed_envelope = SessionCommandEnvelope.from_payload(envelope_payload)
    changed_fingerprint = changed_envelope.fingerprint()
    journal_entry["envelope_fingerprint"] = changed_fingerprint
    revision = _integer(journal_entry, "committed_session_revision")
    commitment = _revision_item(session_payload, "revision_history", revision=revision)
    origin = _object(commitment, "origin")
    origin["command_envelope"] = copy.deepcopy(envelope_payload)
    origin["envelope_fingerprint"] = changed_fingerprint
    _rehash_command_revision(session_payload, journal_entry=journal_entry)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _assert_command_hashes_are_self_consistent(
        session_payload,
        journal_entry=journal_entry,
    )
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_coherent_start_to_advance_relabel_fails_transition_semantics(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
) -> None:
    payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    session_payload = _first_session_payload(payload)
    journal_entry = _object(_list(session_payload, "command_journal")[0])
    assert _integer(journal_entry, "committed_session_revision") == 1
    envelope_payload = _object(journal_entry, "command_envelope")
    submission = _object(envelope_payload, "submission")
    submission["submission_kind"] = SessionCommandSubmissionKind.ADVANCE_SESSION.value
    changed_envelope = SessionCommandEnvelope.from_payload(envelope_payload)
    changed_fingerprint = changed_envelope.fingerprint()
    journal_entry["envelope_fingerprint"] = changed_fingerprint
    response = _object(journal_entry, "response_payload")
    response["operation"] = "advance_session"
    commitment = _revision_item(session_payload, "revision_history", revision=1)
    origin = _object(commitment, "origin")
    origin["operation"] = SessionCommandSubmissionKind.ADVANCE_SESSION.value
    origin["command_envelope"] = copy.deepcopy(envelope_payload)
    origin["envelope_fingerprint"] = changed_fingerprint
    assert commitment["started"] is True
    assert _revision_item(session_payload, "revision_history", revision=0)["started"] is False
    _rehash_command_revision(session_payload, journal_entry=journal_entry)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _assert_command_hashes_are_self_consistent(
        session_payload,
        journal_entry=journal_entry,
    )
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


def test_phase18l_coherent_journal_activity_drift_fails_retained_snapshot_timestamp() -> None:
    tick = 0

    def advancing_clock() -> datetime:
        nonlocal tick
        value = FROZEN_TIME + timedelta(seconds=tick)
        tick += 1
        return value

    server = AdapterGameServer(
        principal_registry=default_principal_registry(),
        clock=advancing_clock,
    )
    session_id = _create_session(server, game_id="phase18l-journal-activity-drift")
    _command(
        server,
        token=DEV_ADMIN_TOKEN,
        envelope=_lifecycle_envelope(
            session_id=session_id,
            command_id="phase18l-journal-activity-drift-start",
            expected_revision=0,
            submission_kind=SessionCommandSubmissionKind.START_SESSION,
        ),
    )
    _metadata(server, session_id=session_id)
    payload = copy.deepcopy(server.persistence_payload())
    session_payload = _first_session_payload(payload)
    journal_entry = _object(_list(session_payload, "command_journal")[0])
    revision = _integer(journal_entry, "committed_session_revision")
    retained_snapshot = _revision_item(
        session_payload,
        "revision_snapshots",
        revision=revision,
    )
    response_metadata = _object(
        _object(journal_entry, "response_payload"),
        "session",
    )
    assert response_metadata["last_activity_at"] == retained_snapshot["last_activity_at"]
    assert session_payload["last_activity_at"] != retained_snapshot["last_activity_at"]
    response_metadata["last_activity_at"] = session_payload["last_activity_at"]
    _rehash_command_revision(session_payload, journal_entry=journal_entry)
    _assert_revision_chain_hashes_are_self_consistent(session_payload)
    _assert_command_hashes_are_self_consistent(
        session_payload,
        journal_entry=journal_entry,
    )
    _rehash_content_addressed_payload(payload)

    with pytest.raises(SessionRecoveryError):
        recover_server_persistence_payload(
            payload,
            principal_registry=default_principal_registry(),
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "rng_draw_count_bool",
        "replay_rng_draw_count_bool",
        "replay_projection_checkpoint",
        "replay_record",
        "replay_extra_field",
    ],
)
def test_phase18l_local_checkpoint_rejects_noncanonical_nested_replay_state(
    phase18l_journaled_root_checkpoint_payload: dict[str, JsonValue],
    tamper_kind: str,
) -> None:
    root_payload = copy.deepcopy(phase18l_journaled_root_checkpoint_payload)
    checkpoint = _object(_first_session_payload(root_payload), "adapter_session")
    replay_payload = _object(checkpoint, "replay_artifact")
    if tamper_kind == "rng_draw_count_bool":
        rng_state = _object(checkpoint, "rng_state")
        rng_state["draw_count"] = False
        checkpoint["rng_state_hash"] = hashlib.sha256(
            canonical_json(cast(JsonValue, rng_state)).encode("utf-8")
        ).hexdigest()
    elif tamper_kind == "replay_rng_draw_count_bool":
        _object(replay_payload, "initial_rng_state")["draw_count"] = False
    elif tamper_kind == "replay_projection_checkpoint":
        artifact = ReplayArtifact.from_payload(cast(ReplayArtifactPayload, replay_payload))
        initial_lifecycle = GameLifecycle.from_payload(
            copy.deepcopy(artifact.initial_lifecycle_payload)
        )
        projection_checkpoint = ReplayProjectionCheckpoint.from_lifecycle(
            checkpoint_id="phase18l-forged-projection-checkpoint",
            decision_record_index=0,
            lifecycle=initial_lifecycle,
            viewer_player_id=PLAYER_A,
            projection_schema="phase18l-forged-projection-v1",
            projection_state_hash="0" * 64,
        )
        _list(replay_payload, "projection_checkpoints").append(
            cast(JsonValue, projection_checkpoint.to_payload())
        )
    elif tamper_kind == "replay_record":
        records = _list(replay_payload, "decision_records")
        assert records
        _object(records[0])["record_id"] = ""
    else:
        assert tamper_kind == "replay_extra_field"
        replay_payload["unexpected"] = True
    _rehash_content_addressed_payload(checkpoint)

    with pytest.raises(LocalGameSessionPersistenceError):
        LocalGameSession.from_persistence_payload(checkpoint)


@pytest.mark.parametrize(
    "tamper_kind",
    [
        "schema",
        "ruleset",
        "catalog",
        "source",
        "package",
        "checkpoint",
        "rng",
    ],
)
def test_phase18l_local_checkpoint_identity_and_hash_drift_fails_closed(
    phase18l_root_checkpoint_payload: dict[str, JsonValue],
    tamper_kind: str,
) -> None:
    root_payload = copy.deepcopy(phase18l_root_checkpoint_payload)
    checkpoint = _object(_first_session_payload(root_payload), "adapter_session")
    source_identity = _object(checkpoint, "source_identity")
    if tamper_kind == "schema":
        checkpoint["schema_version"] = "forged-local-checkpoint-schema"
    elif tamper_kind == "ruleset":
        source_identity["ruleset_descriptor_hash"] = "0" * 64
    elif tamper_kind == "catalog":
        source_identity["catalog_hash"] = "0" * 64
    elif tamper_kind == "source":
        source_identity["source_ids"] = ["forged-source"]
    elif tamper_kind == "package":
        source_identity["source_package_id"] = "forged-source-package"
    elif tamper_kind == "checkpoint":
        checkpoint["lifecycle_hash"] = "0" * 64
    else:
        assert tamper_kind == "rng"
        checkpoint["rng_state_hash"] = "0" * 64
    _rehash_content_addressed_payload(checkpoint)

    with pytest.raises(LocalGameSessionPersistenceError):
        LocalGameSession.from_persistence_payload(checkpoint)


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
