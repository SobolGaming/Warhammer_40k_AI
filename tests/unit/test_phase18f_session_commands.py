from __future__ import annotations

from typing import Protocol, cast

from tests.shared.category_migration.phase18f_session_commands import (
    DEV_ADMIN_TOKEN,
    DEV_PLAYER_A_TOKEN,
    DEV_PLAYER_B_TOKEN,
    DRAFT202012,
    EMPTY_REGISTRY,
    FIXED_SECONDARY_OPTION_ID,
    HTTP_REQUEST_TIMEOUT_SECONDS,
    NORMAL_MOVE_ACTION_OPTION_ID,
    PARTICIPANT_A,
    PARTICIPANT_B,
    PLAYER_A,
    PLAYER_B,
    REPO_ROOT,
    SECONDARY_MISSION_DECISION_TYPE,
    SELECT_DEPLOYMENT_UNIT,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
    SUBMIT_DEPLOYMENT_PLACEMENT,
    UTC,
    AdapterGameServer,
    ArmyCatalog,
    ArmyMusterRequest,
    Barrier,
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    DetachmentSelection,
    Draft202012Validator,
    GameConfig,
    GameLifecycle,
    HTTPResponse,
    Iterator,
    JsonValue,
    MissionSetup,
    ModelProfileSelection,
    MovementMode,
    Path,
    ReplayArtifactPayload,
    ReplayProjectionCheckpoint,
    ReplayProjectionSnapshot,
    ReplayRunner,
    ReplayRunStatus,
    Request,
    Resource,
    RulesetDescriptor,
    Schema,
    SchemaRegistry,
    ServerResponse,
    SessionPersistenceError,
    SessionPersistenceStore,
    SQLiteSessionPersistenceStore,
    Thread,
    ThreadingHTTPServer,
    ThreadPoolExecutor,
    UnitMusterSelection,
    _advance_to_deployment_placement,
    _advance_to_movement_selection,
    _authoritative_snapshot,
    _command_envelope,
    _compact_army_muster_request,
    _compact_terminal_config,
    _create_session,
    _cursor_offset,
    _deployment_payload_from_proposal,
    _error_code,
    _field_float,
    _field_int,
    _field_list,
    _field_object,
    _field_string,
    _first_option_id,
    _http_command_bytes,
    _http_json,
    _http_server,
    _invalid_distance_witness,
    _json_object,
    _json_string,
    _participant_for_player,
    _PayloadValidator,
    _pending_decision,
    _pending_decision_for_any_player,
    _pose_payload,
    _read_json,
    _replay_projection,
    _request,
    _request_raw,
    _request_token,
    _schema_payloads,
    _schema_registry,
    _schema_validator,
    _session_create_body,
    _session_create_body_from_config,
    _session_revision,
    _start_command,
    _submit_command,
    _submit_visible_option_command,
    _terminal_progress_option_id,
    bearer_authorization,
    canonical_setup_prebattle_smoke_config,
    chapter_approved_2026_27_mission_pack,
    datetime,
    json,
    pre_record_unsupported_session,
    project_game_view,
    pytest,
    recorded_unsupported_session,
    replace,
    tacoma_open_2026,
    urlopen,
    validate_json_value,
)


def test_phase18f_simultaneous_commands_commit_once_and_replay_projection_hashes() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18f-concurrent")
    _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-concurrent-start",
            expected_revision=0,
            submission_kind="start_session",
        ),
    )
    pending = _pending_decision(server, session_id=session_id, player_id=PLAYER_A)
    option_id = _first_option_id(pending)
    barrier = Barrier(2)
    envelopes = (
        _command_envelope(
            session_id=session_id,
            command_id="phase18f-concurrent-a",
            expected_revision=1,
            submission_kind="finite_option",
            request_id=_field_string(pending, "request_id"),
            result_id="phase18f-concurrent-result-a",
            option_id=option_id,
        ),
        _command_envelope(
            session_id=session_id,
            command_id="phase18f-concurrent-b",
            expected_revision=1,
            submission_kind="finite_option",
            request_id=_field_string(pending, "request_id"),
            result_id="phase18f-concurrent-result-b",
            option_id=option_id,
        ),
    )

    def submit(envelope: dict[str, JsonValue]) -> ServerResponse:
        barrier.wait()
        return _request_raw(
            server,
            session_id=session_id,
            participant_id=PARTICIPANT_A,
            envelope=envelope,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        responses = tuple(executor.map(submit, envelopes))

    assert sorted(response.status_code for response in responses) == [200, 409]
    winner = next(response for response in responses if response.status_code == 200)
    loser = next(response for response in responses if response.status_code == 409)
    assert _json_object(winner.payload)["committed"] is True
    assert _error_code(loser) == "session_revision_conflict"
    assert _session_revision(server, session_id=session_id) == 2
    replay_payload = _request(
        server,
        "GET",
        f"/sessions/{session_id}/replay",
    )
    assert len(_field_list(replay_payload, "decision_records")) == 1
    replay = ReplayRunner.from_payload(cast(ReplayArtifactPayload, replay_payload)).run()
    assert replay.status is ReplayRunStatus.REPRODUCED

    projection = _request(
        server,
        "GET",
        f"/sessions/{session_id}/projection",
        query={"viewer_player_id": PLAYER_A},
    )
    replay_payload["projection_checkpoints"] = [
        {
            "checkpoint_id": "phase18f-command-final",
            "decision_record_index": len(_field_list(replay_payload, "decision_records")),
            "event_count": replay.reproduced_event_count,
            "event_log_hash": replay.final_event_log_hash,
            "viewer_player_id": PLAYER_A,
            "projection_schema": _field_string(projection, "projection_schema"),
            "projection_state_hash": _field_string(projection, "projection_state_hash"),
        }
    ]
    replay_with_projection = ReplayRunner.from_payload(
        cast(ReplayArtifactPayload, replay_payload),
        projection_provider=_replay_projection,
    ).run()
    assert replay_with_projection.status is ReplayRunStatus.REPRODUCED
    assert replay_with_projection.final_event_log_hash == replay.final_event_log_hash


def test_phase18f_precommit_rejections_preserve_authoritative_state() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18f-precommit-rejections")
    _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-rejections-start",
            expected_revision=0,
            submission_kind="start_session",
        ),
    )
    pending = _pending_decision(server, session_id=session_id, player_id=PLAYER_A)
    request_id = _field_string(pending, "request_id")
    before = _authoritative_snapshot(server, session_id=session_id)
    rejected = (
        (
            _request_raw(
                server,
                session_id=session_id,
                participant_id=PARTICIPANT_A,
                envelope=_command_envelope(
                    session_id=session_id,
                    command_id="phase18f-rejection-stale-revision",
                    expected_revision=0,
                    submission_kind="finite_option",
                    request_id=request_id,
                    result_id="phase18f-rejection-stale-revision-result",
                    option_id=_first_option_id(pending),
                ),
            ),
            409,
            "session_revision_conflict",
        ),
        (
            _request_raw(
                server,
                session_id=session_id,
                participant_id=PARTICIPANT_A,
                envelope=_command_envelope(
                    session_id=session_id,
                    command_id="phase18f-rejection-stale-request",
                    expected_revision=1,
                    submission_kind="finite_option",
                    request_id="phase18f-stale-decision-request",
                    result_id="phase18f-rejection-stale-request-result",
                    option_id=_first_option_id(pending),
                ),
            ),
            409,
            "stale_decision_request",
        ),
        (
            _request_raw(
                server,
                session_id=session_id,
                participant_id=PARTICIPANT_B,
                envelope=_command_envelope(
                    session_id=session_id,
                    command_id="phase18f-rejection-wrong-actor",
                    expected_revision=1,
                    submission_kind="finite_option",
                    request_id=request_id,
                    result_id="phase18f-rejection-wrong-actor-result",
                    option_id=_first_option_id(pending),
                ),
            ),
            403,
            "access_denied",
        ),
        (
            _request_raw(
                server,
                session_id=session_id,
                participant_id=PARTICIPANT_A,
                envelope={
                    **_command_envelope(
                        session_id=session_id,
                        command_id="phase18f-rejection-malformed",
                        expected_revision=1,
                        submission_kind="finite_option",
                        request_id=request_id,
                        result_id="phase18f-rejection-malformed-result",
                        option_id=_first_option_id(pending),
                    ),
                    "actor_id": PLAYER_A,
                },
            ),
            400,
            "canonical_schema_invalid",
        ),
        (
            _request_raw(
                server,
                session_id=session_id,
                participant_id=PARTICIPANT_A,
                envelope=_command_envelope(
                    session_id=session_id,
                    command_id="phase18f-rejection-illegal-option",
                    expected_revision=1,
                    submission_kind="finite_option",
                    request_id=request_id,
                    result_id="phase18f-rejection-illegal-option-result",
                    option_id="phase18f-option-not-emitted-by-engine",
                ),
            ),
            422,
            "proposal_invalid",
        ),
    )
    for response, expected_status, expected_code in rejected:
        assert response.status_code == expected_status
        assert _error_code(response) == expected_code
        assert _authoritative_snapshot(server, session_id=session_id) == before

    corrected = _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-rejection-illegal-option",
            expected_revision=1,
            submission_kind="finite_option",
            request_id=request_id,
            result_id="phase18f-rejection-corrected-result",
            option_id=_first_option_id(pending),
        ),
    )
    assert corrected["committed"] is True
    assert _session_revision(server, session_id=session_id) == 2


def test_phase18f_unsupported_outcomes_preserve_recording_and_retry_semantics() -> None:
    pre_server = AdapterGameServer(session_factory=pre_record_unsupported_session)
    pre_session_id = _create_session(pre_server, game_id="phase18f-pre-record-unsupported")
    _start_command(pre_server, pre_session_id, "phase18f-pre-unsupported-start")
    pre_request = _pending_decision(pre_server, session_id=pre_session_id, player_id=PLAYER_A)
    pre_snapshot = _authoritative_snapshot(pre_server, session_id=pre_session_id)
    pre_response = _request_raw(
        pre_server,
        session_id=pre_session_id,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=pre_session_id,
            command_id="phase18f-pre-unsupported-command",
            expected_revision=1,
            submission_kind="finite_option",
            request_id=_field_string(pre_request, "request_id"),
            result_id="phase18f-pre-unsupported-result",
            option_id=_first_option_id(pre_request),
        ),
    )
    assert pre_response.status_code == 422
    assert _error_code(pre_response) == "rule_path_unsupported"
    assert _authoritative_snapshot(pre_server, session_id=pre_session_id) == pre_snapshot

    recorded_server = AdapterGameServer(session_factory=recorded_unsupported_session)
    session_id = _create_session(recorded_server, game_id="phase18f-recorded-unsupported")
    _start_command(recorded_server, session_id, "phase18f-recorded-unsupported-start")
    request = _pending_decision(recorded_server, session_id=session_id, player_id=PLAYER_A)
    envelope = _command_envelope(
        session_id=session_id,
        command_id="phase18f-recorded-unsupported-command",
        expected_revision=1,
        submission_kind="finite_option",
        request_id=_field_string(request, "request_id"),
        result_id="phase18f-recorded-unsupported-result",
        option_id=_first_option_id(request),
    )
    response = _request_raw(
        recorded_server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope=envelope,
    )
    outcome = _json_object(response.payload)
    assert response.status_code == 422
    assert outcome["outcome_code"] == "rule_path_unsupported"
    assert outcome["committed"] is True
    assert outcome["accepted"] is False
    assert _session_revision(recorded_server, session_id=session_id) == 2
    replay = _request(recorded_server, "GET", f"/sessions/{session_id}/replay")
    assert len(_field_list(replay, "decision_records")) == 1
    snapshot = _authoritative_snapshot(recorded_server, session_id=session_id)
    assert (
        _request_raw(
            recorded_server,
            session_id=session_id,
            participant_id=PARTICIPANT_A,
            envelope=envelope,
        )
        == response
    )
    assert _authoritative_snapshot(recorded_server, session_id=session_id) == snapshot


def test_phase18f_noop_advance_cannot_consume_revision_or_win_decision_race() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18f-noop-advance")
    unauthorized = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_B,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-non-coordinator-start",
            expected_revision=0,
            submission_kind="start_session",
        ),
    )
    assert unauthorized.status_code == 403
    assert _session_revision(server, session_id=session_id) == 0
    _start_command(server, session_id, "phase18f-noop-start")
    pending = _pending_decision(server, session_id=session_id, player_id=PLAYER_A)
    snapshot = _authoritative_snapshot(server, session_id=session_id)
    no_op_id = "phase18f-noop-command"
    rejected = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id=no_op_id,
            expected_revision=1,
            submission_kind="advance_session",
        ),
    )
    assert rejected.status_code == 409
    assert _error_code(rejected) == "advance_not_required"
    assert _authoritative_snapshot(server, session_id=session_id) == snapshot
    outcome = _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id=no_op_id,
            expected_revision=1,
            submission_kind="finite_option",
            request_id=_field_string(pending, "request_id"),
            result_id="phase18f-noop-reused-result",
            option_id=_first_option_id(pending),
        ),
    )
    assert outcome["committed"] is True

    race_server = AdapterGameServer()
    race_session = _create_session(race_server, game_id="phase18f-noop-race")
    _start_command(race_server, race_session, "phase18f-noop-race-start")
    race_request = _pending_decision(race_server, session_id=race_session, player_id=PLAYER_A)
    barrier = Barrier(2)

    def race(envelope: dict[str, JsonValue]) -> ServerResponse:
        barrier.wait()
        return _request_raw(
            race_server,
            session_id=race_session,
            participant_id=PARTICIPANT_A,
            envelope=envelope,
        )

    commands = (
        _command_envelope(
            session_id=race_session,
            command_id="phase18f-racing-noop",
            expected_revision=1,
            submission_kind="advance_session",
        ),
        _command_envelope(
            session_id=race_session,
            command_id="phase18f-racing-decision",
            expected_revision=1,
            submission_kind="finite_option",
            request_id=_field_string(race_request, "request_id"),
            result_id="phase18f-racing-decision-result",
            option_id=_first_option_id(race_request),
        ),
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        advance_response, decision_response = tuple(executor.map(race, commands))
    assert decision_response.status_code == 200
    assert advance_response.status_code == 409
    assert _error_code(advance_response) in {"advance_not_required", "session_revision_conflict"}
    assert _session_revision(race_server, session_id=race_session) == 2


def test_phase18f_injected_precommit_failure_and_closed_session_preserve_state() -> None:
    current_time = [datetime(2026, 7, 18, 20, 0, tzinfo=UTC)]
    server = AdapterGameServer(clock=lambda: current_time[0])
    session_id = _create_session(server, game_id="phase18f-atomic-failure")
    before = _authoritative_snapshot(server, session_id=session_id)
    start = _command_envelope(
        session_id=session_id,
        command_id="phase18f-atomic-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    current_time[0] = datetime(2026, 7, 18, 19, 59, tzinfo=UTC)

    failed = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope=start,
    )

    assert failed.status_code == 500
    assert _error_code(failed) == "session_protocol_failure"
    current_time[0] = datetime(2026, 7, 18, 20, 0, tzinfo=UTC)
    assert _authoritative_snapshot(server, session_id=session_id) == before
    current_time[0] = datetime(2026, 7, 18, 20, 1, tzinfo=UTC)
    started = _submit_command(server, participant_id=PARTICIPANT_A, envelope=start)
    assert _field_int(_field_object(started, "session"), "session_revision") == 1

    close = _command_envelope(
        session_id=session_id,
        command_id="phase18f-atomic-close",
        expected_revision=1,
        submission_kind="close_session",
    )
    closed = _submit_command(server, participant_id=PARTICIPANT_A, envelope=close)
    closed_snapshot = _authoritative_snapshot(server, session_id=session_id)
    rejected = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-after-close",
            expected_revision=2,
            submission_kind="advance_session",
        ),
    )
    assert rejected.status_code == 409
    assert _error_code(rejected) == "session_closed"
    assert _authoritative_snapshot(server, session_id=session_id) == closed_snapshot
    assert _submit_command(server, participant_id=PARTICIPANT_A, envelope=close) == closed


def test_phase18f_terminal_session_rejects_new_command_and_preserves_cached_outcome() -> None:
    server = AdapterGameServer()
    config = _compact_terminal_config(game_id="phase18f-terminal")
    created = _request(
        server,
        "POST",
        "/sessions",
        body=_session_create_body_from_config(config),
        expected_status=201,
    )
    session_id = _field_string(created, "session_id")
    last_envelope = _command_envelope(
        session_id=session_id,
        command_id="phase18f-terminal-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    last_outcome = _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=last_envelope,
    )

    for command_index in range(80):
        session = _request(server, "GET", f"/sessions/{session_id}")
        if session["session_state"] == "terminal":
            break
        pending = _pending_decision_for_any_player(server, session_id=session_id)
        player_id = _field_string(pending, "actor_id")
        request_id = _field_string(pending, "request_id")
        revision = _field_int(session, "session_revision")
        if pending["is_parameterized"] is True:
            assert pending["decision_type"] == SUBMIT_DEPLOYMENT_PLACEMENT
            projection = _request(
                server,
                "GET",
                f"/sessions/{session_id}/projection",
                query={"viewer_player_id": player_id},
            )
            last_envelope = _command_envelope(
                session_id=session_id,
                command_id=f"phase18f-terminal-command-{command_index:03d}",
                expected_revision=revision,
                submission_kind="parameterized_payload",
                request_id=request_id,
                result_id=f"phase18f-terminal-result-{command_index:03d}",
                payload=_deployment_payload_from_proposal(
                    _field_object(projection, "pending_proposal")
                ),
            )
        else:
            last_envelope = _command_envelope(
                session_id=session_id,
                command_id=f"phase18f-terminal-command-{command_index:03d}",
                expected_revision=revision,
                submission_kind="finite_option",
                request_id=request_id,
                result_id=f"phase18f-terminal-result-{command_index:03d}",
                option_id=_terminal_progress_option_id(pending),
            )
        last_outcome = _submit_command(
            server,
            participant_id=_participant_for_player(player_id),
            envelope=last_envelope,
        )
    else:
        raise AssertionError("Compact real session did not reach its terminal boundary.")

    terminal_session = _field_object(last_outcome, "session")
    assert terminal_session["session_state"] == "terminal"
    assert _field_object(terminal_session, "lifecycle_status")["status_kind"] == "terminal"
    terminal_snapshot = _authoritative_snapshot(server, session_id=session_id)
    rejected = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-after-terminal",
            expected_revision=_field_int(terminal_session, "session_revision"),
            submission_kind="advance_session",
        ),
    )
    assert rejected.status_code == 409
    assert _error_code(rejected) == "session_terminal"
    assert _authoritative_snapshot(server, session_id=session_id) == terminal_snapshot
    assert (
        _submit_command(
            server,
            participant_id=_participant_for_player(
                _field_string(_field_object(last_outcome, "checkpoint"), "viewer_player_id")
            ),
            envelope=last_envelope,
        )
        == last_outcome
    )


def test_phase18f_command_schema_rejects_client_actor_and_invalid_boolean_outcomes() -> None:
    envelope = _read_json(
        REPO_ROOT / "contracts" / "examples" / "sessions" / "session-command-envelope.json"
    )
    outcome = _read_json(
        REPO_ROOT / "contracts" / "examples" / "sessions" / "session-command-outcome.json"
    )
    envelope_validator = _schema_validator("session-command-envelope.schema.json")
    outcome_validator = _schema_validator("session-command-outcome.schema.json")

    envelope_validator.validate(envelope)
    outcome_validator.validate(outcome)
    assert list(envelope_validator.iter_errors({**envelope, "actor_id": PLAYER_A}))
    assert list(outcome_validator.iter_errors({**outcome, "committed": False}))
    assert list(
        outcome_validator.iter_errors(
            {**outcome, "accepted": False, "outcome_code": "command_committed"}
        )
    )
    proposal_paths = tuple(
        sorted((REPO_ROOT / "contracts/examples/decisions/proposals").glob("*.json"))
    )
    assert len(proposal_paths) == 24
    typed_envelope: dict[str, JsonValue] = {}
    for index, path in enumerate(proposal_paths):
        typed_envelope = _command_envelope(
            session_id="phase18f-schema-session",
            command_id=f"phase18f-schema-command-{index:02d}",
            expected_revision=0,
            submission_kind="parameterized_payload",
            request_id="phase18f-schema-request",
            result_id="phase18f-schema-result",
            payload=_read_json(path),
        )
        envelope_validator.validate(typed_envelope)
    for invalid_payload in ({"arbitrary": True}, None):
        invalid_envelope = {
            **typed_envelope,
            "submission": {"submission_kind": "parameterized_payload", "payload": invalid_payload},
        }
        assert list(envelope_validator.iter_errors(invalid_envelope))


def test_phase18l_persisted_transaction_fails_closed_on_invalid_checkpoint(
    tmp_path: Path,
) -> None:
    server = AdapterGameServer()
    with pytest.raises(SessionPersistenceError, match="does not conform"):
        server.initialize_persistence(cast(SessionPersistenceStore, object()))

    store = SQLiteSessionPersistenceStore(database_path=tmp_path / "phase18l-server.sqlite3")
    server.initialize_persistence(store)
    durable_before = store.load()
    server.event_retention_limit = 0

    rejected = server.handle(
        method="GET",
        path="/rules-catalog",
        authorization=bearer_authorization(DEV_ADMIN_TOKEN),
    )

    assert rejected.status_code == 503
    assert _error_code(rejected) == "session_persistence_unavailable"
    assert store.load() == durable_before
    assert (
        _error_code(
            server.handle(
                method="GET",
                path="/rules-catalog",
                authorization=bearer_authorization(DEV_ADMIN_TOKEN),
            )
        )
        == "session_persistence_unavailable"
    )
    with pytest.raises(SessionPersistenceError, match="cannot export a checkpoint"):
        server.persistence_payload()


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "BattlePhaseKind"]
__all__ += ["DEV_PLAYER_A_TOKEN", "DEV_PLAYER_B_TOKEN", "BattlePhaseSequenceDescriptor"]
__all__ += ["DRAFT202012", "EMPTY_REGISTRY", "DetachmentSelection", "Draft202012Validator"]
__all__ += ["FIXED_SECONDARY_OPTION_ID", "GameConfig", "GameLifecycle", "HTTPResponse"]
__all__ += ["HTTP_REQUEST_TIMEOUT_SECONDS", "Iterator", "MissionSetup", "ModelProfileSelection"]
__all__ += ["NORMAL_MOVE_ACTION_OPTION_ID", "PLAYER_B", "MovementMode", "Protocol"]
__all__ += ["ReplayProjectionCheckpoint", "ReplayProjectionSnapshot", "Request", "Resource"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SELECT_DEPLOYMENT_UNIT", "RulesetDescriptor"]
__all__ += ["SELECT_MOVEMENT_ACTION_DECISION_TYPE", "SELECT_MOVEMENT_UNIT_DECISION_TYPE"]
__all__ += ["SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION", "SESSION_CREATE_SCHEMA_VERSION", "Schema"]
__all__ += ["SchemaRegistry", "Thread", "ThreadingHTTPServer", "UnitMusterSelection"]
__all__ += ["_PayloadValidator", "_advance_to_deployment_placement"]
__all__ += ["_advance_to_movement_selection", "_compact_army_muster_request", "_cursor_offset"]
__all__ += ["_field_float", "_http_command_bytes", "_http_json", "_http_server"]
__all__ += ["_invalid_distance_witness", "_json_string", "_pose_payload", "_request_token"]
__all__ += ["_schema_payloads", "_schema_registry", "_session_create_body"]
__all__ += ["_submit_visible_option_command", "canonical_setup_prebattle_smoke_config"]
__all__ += ["chapter_approved_2026_27_mission_pack", "json", "project_game_view", "replace"]
__all__ += ["tacoma_open_2026", "urlopen", "validate_json_value"]
