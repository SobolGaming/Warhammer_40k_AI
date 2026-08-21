from __future__ import annotations

import copy
import hashlib
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from http import HTTPStatus
from pathlib import Path
from typing import Literal, cast

import pytest
from tests.movement_submission_helpers import straight_line_witness_for_unit
from tests.phase15c_fight_order_helpers import fight_config, fight_lifecycle
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture

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
    SQLITE_SESSION_STATE_TABLE,
    SessionPersistenceCorruptionError,
    SessionPersistenceStorageError,
    SessionPersistenceStore,
    SQLiteSessionPersistenceStore,
)
from warhammer40k_core.adapters.session_protocol import AuthoritativeSession
from warhammer40k_core.adapters.session_recovery import (
    SessionRecoveryError,
    recover_server_persistence_payload,
    server_persistence_payload,
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
    )
    record.started = True
    record.capture_current_revision(replace_existing=True)
    checkpoint = _server_checkpoint_payload(record)
    database_path = tmp_path / f"phase18l-checkpoint-{boundary}.sqlite3"
    SQLiteSessionPersistenceStore(database_path=database_path).commit(checkpoint)

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
    )
    record.revision_retention_limit = 1
    record.started = True
    record.capture_current_revision(replace_existing=True)
    record.close(timestamp="2026-08-21T16:00:01Z")
    checkpoint = _server_checkpoint_payload(record)
    database_path = tmp_path / "phase18l-checkpoint-closed.sqlite3"
    SQLiteSessionPersistenceStore(database_path=database_path).commit(checkpoint)

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
    first_server = AdapterGameServer(
        persistence_store=SQLiteSessionPersistenceStore(database_path=database_path),
        principal_registry=default_principal_registry(),
        event_retention_limit=2,
        clock=lambda: FROZEN_TIME,
    )
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
        persistence_store=store,
        principal_registry=default_principal_registry(),
        clock=advancing_clock,
    )
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
        persistence_store=store,
        principal_registry=default_principal_registry(),
        clock=advancing_clock,
    )
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

    def load(self) -> JsonValue | None:
        return self.delegate.load()

    def commit(self, payload: JsonValue) -> None:
        failure_point = self._failure_point
        self._failure_point = None
        if failure_point == "before":
            raise SessionPersistenceStorageError("Injected failure before durable commit.")
        self.delegate.commit(payload)
        if failure_point == "after":
            raise SessionPersistenceStorageError("Injected failure after durable commit.")


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
    )
    record.started = True
    record.capture_current_revision(replace_existing=True)
    store = SQLiteSessionPersistenceStore(database_path=database_path)
    store.commit(_server_checkpoint_payload(record))
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


def _server(
    persistence_store: SessionPersistenceStore,
    *,
    principal_registry: PrincipalRegistry | None = None,
) -> AdapterGameServer:
    return AdapterGameServer(
        persistence_store=persistence_store,
        principal_registry=(
            default_principal_registry() if principal_registry is None else principal_registry
        ),
        clock=lambda: FROZEN_TIME,
    )


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
