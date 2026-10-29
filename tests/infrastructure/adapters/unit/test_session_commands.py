from __future__ import annotations

import errno
import socket
import sys
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
from warhammer40k_core.adapters.http_transport import create_http_server


def test_phase18f_session_source_identity_publishes_active_rules_overlay() -> None:
    config = canonical_setup_prebattle_smoke_config(game_id="phase18f-tacoma-overlay")
    descriptor = tacoma_open_2026.apply_rules_overlay(config.ruleset_descriptor)
    config = replace(config, ruleset_descriptor=descriptor)

    created = _request(
        AdapterGameServer(),
        "POST",
        "/sessions",
        body=_session_create_body_from_config(config),
        expected_status=201,
    )

    _schema_validator("session-metadata.schema.json").validate(created)
    assert created["ruleset_descriptor_hash"] == descriptor.descriptor_hash
    assert created["rules_overlay_ids"] == [tacoma_open_2026.RULES_OVERLAY_ID]


def test_phase18f_command_is_idempotent_and_enforces_revision_ordering() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18f-idempotent")
    start = _command_envelope(
        session_id=session_id,
        command_id="phase18f-start-000001",
        expected_revision=0,
        submission_kind="start_session",
    )

    first = _submit_command(server, participant_id=PARTICIPANT_A, envelope=start)
    duplicate = _submit_command(server, participant_id=PARTICIPANT_A, envelope=start)

    _schema_validator("session-command-envelope.schema.json").validate(start)
    _schema_validator("session-command-outcome.schema.json").validate(first)
    assert first == duplicate
    assert first["command_id"] == "phase18f-start-000001"
    assert first["outcome_code"] == "command_committed"
    assert first["committed"] is True
    assert first["accepted"] is True
    assert _field_int(_field_object(first, "session"), "session_revision") == 1

    reused = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope={
            **start,
            "submission": {"submission_kind": "advance_session"},
        },
    )
    assert reused.status_code == 409
    assert _error_code(reused) == "command_id_conflict"

    stale = _request_raw(
        server,
        session_id=session_id,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-stale-revision-000001",
            expected_revision=0,
            submission_kind="advance_session",
        ),
    )
    assert stale.status_code == 409
    assert _error_code(stale) == "session_revision_conflict"
    assert _session_revision(server, session_id=session_id) == 1


def test_phase18f_duplicate_http_commands_are_byte_equivalent_after_reconnect() -> None:
    server = AdapterGameServer()
    http_server = _http_server(server)
    host, port = cast(tuple[str, int], http_server.server_address)
    thread = Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{host}:{port}"
    try:
        created = _http_json(
            Request(
                f"{base_url}/sessions",
                data=json.dumps(_session_create_body("phase18f-http-idempotent")).encode(),
                headers={
                    "Authorization": bearer_authorization(DEV_ADMIN_TOKEN),
                    "Content-Type": "application/json",
                },
                method="POST",
            )
        )
        session_id = _field_string(created, "session_id")
        envelope = _command_envelope(
            session_id=session_id,
            command_id="phase18f-http-start",
            expected_revision=0,
            submission_kind="start_session",
        )

        first_status, first_bytes = _http_command_bytes(base_url, session_id, envelope)
        second_status, second_bytes = _http_command_bytes(base_url, session_id, envelope)

        assert first_status == 200
        assert second_status == 200
        assert first_bytes == second_bytes
    finally:
        http_server.shutdown()
        http_server.server_close()
        thread.join(timeout=5.0)


def test_phase18f_well_formed_illegal_proposal_is_uncommitted_and_retryable() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18f-illegal-proposal")
    _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-illegal-proposal-start",
            expected_revision=0,
            submission_kind="start_session",
        ),
    )
    placement_request = _advance_to_deployment_placement(server, session_id=session_id)
    player_id = _field_string(placement_request, "actor_id")
    projection = _request(
        server,
        "GET",
        f"/sessions/{session_id}/projection",
        query={"viewer_player_id": player_id},
    )
    legal_payload = _deployment_payload_from_proposal(_field_object(projection, "pending_proposal"))
    illegal_payload = dict(legal_payload)
    illegal_payload["proposal_request_id"] = "phase18f-drifted-proposal-request"
    revision = _session_revision(server, session_id=session_id)
    before = _authoritative_snapshot(server, session_id=session_id)
    command_id = "phase18f-illegal-proposal-submit"

    rejected = _request_raw(
        server,
        session_id=session_id,
        participant_id=_participant_for_player(player_id),
        envelope=_command_envelope(
            session_id=session_id,
            command_id=command_id,
            expected_revision=revision,
            submission_kind="parameterized_payload",
            request_id=_field_string(placement_request, "request_id"),
            result_id="phase18f-illegal-proposal-result",
            payload=illegal_payload,
        ),
    )

    assert rejected.status_code == 422
    assert _error_code(rejected) == "proposal_invalid"
    assert _authoritative_snapshot(server, session_id=session_id) == before
    corrected = _submit_command(
        server,
        participant_id=_participant_for_player(player_id),
        envelope=_command_envelope(
            session_id=session_id,
            command_id=command_id,
            expected_revision=revision,
            submission_kind="parameterized_payload",
            request_id=_field_string(placement_request, "request_id"),
            result_id="phase18f-corrected-proposal-result",
            payload=legal_payload,
        ),
    )
    assert corrected["committed"] is True
    assert corrected["accepted"] is True


def test_phase18f_recorded_invalid_retry_is_atomically_journaled() -> None:
    server = AdapterGameServer()
    compact = _compact_terminal_config(game_id="phase18f-recorded-invalid")
    config = replace(
        compact,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-phase18f-recorded-invalid"
        ),
    )
    created = _request(
        server,
        "POST",
        "/sessions",
        body=_session_create_body_from_config(config),
        expected_status=201,
    )
    session_id = _field_string(created, "session_id")
    _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id="phase18f-recorded-invalid-start",
            expected_revision=0,
            submission_kind="start_session",
        ),
    )
    movement_request = _advance_to_movement_selection(server, session_id=session_id)
    player_id = _field_string(movement_request, "actor_id")
    _submit_visible_option_command(
        server,
        session_id=session_id,
        request=movement_request,
        option_id=_first_option_id(movement_request),
        command_id="phase18f-recorded-invalid-unit",
    )
    action_request = _pending_decision_for_any_player(server, session_id=session_id)
    assert action_request["decision_type"] == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    _submit_visible_option_command(
        server,
        session_id=session_id,
        request=action_request,
        option_id=NORMAL_MOVE_ACTION_OPTION_ID,
        command_id="phase18f-recorded-invalid-action",
    )
    proposal_request = _pending_decision_for_any_player(server, session_id=session_id)
    proposal_view = _request(
        server,
        "GET",
        f"/sessions/{session_id}/projection",
        query={"viewer_player_id": player_id},
    )
    proposal = _field_object(proposal_view, "pending_proposal")
    revision_before = _session_revision(server, session_id=session_id)
    replay_before = _request(server, "GET", f"/sessions/{session_id}/replay")
    before_record_count = len(_field_list(replay_before, "decision_records"))
    envelope = _command_envelope(
        session_id=session_id,
        command_id="phase18f-recorded-invalid-proposal",
        expected_revision=revision_before,
        submission_kind="parameterized_payload",
        request_id=_field_string(proposal_request, "request_id"),
        result_id="phase18f-recorded-invalid-result",
        payload={
            "proposal_request_id": _field_string(proposal, "request_id"),
            "proposal_kind": _field_string(proposal, "proposal_kind"),
            "unit_instance_id": _field_string(proposal, "unit_instance_id"),
            "movement_phase_action": "normal_move",
            "movement_mode": MovementMode.NORMAL.value,
            "witness": _invalid_distance_witness(
                projection=proposal_view,
                unit_instance_id=_field_string(proposal, "unit_instance_id"),
            ),
        },
    )

    response = _request_raw(
        server,
        session_id=session_id,
        participant_id=_participant_for_player(player_id),
        envelope=envelope,
    )

    assert response.status_code == 422
    outcome = _json_object(response.payload)
    _schema_validator("session-command-outcome.schema.json").validate(outcome)
    assert outcome["outcome_code"] == "proposal_invalid"
    assert outcome["committed"] is True
    assert outcome["accepted"] is False
    assert _field_int(_field_object(outcome, "session"), "session_revision") == (
        revision_before + 1
    )
    event_range = _field_object(outcome, "event_range")
    assert _cursor_offset(server, _field_string(event_range, "to_cursor")) > _cursor_offset(
        server,
        _field_string(event_range, "from_cursor"),
    )
    retry = _pending_decision_for_any_player(server, session_id=session_id)
    assert _field_string(retry, "request_id") != _field_string(
        proposal_request,
        "request_id",
    )
    replay_after = _request(server, "GET", f"/sessions/{session_id}/replay")
    assert len(_field_list(replay_after, "decision_records")) == before_record_count + 1
    after = _authoritative_snapshot(server, session_id=session_id)
    duplicate = _request_raw(
        server,
        session_id=session_id,
        participant_id=_participant_for_player(player_id),
        envelope=envelope,
    )
    assert duplicate == response
    assert _authoritative_snapshot(server, session_id=session_id) == after


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyMusterRequest", "Barrier", "BattlePhaseKind"]
__all__ += ["DEV_PLAYER_A_TOKEN", "DEV_PLAYER_B_TOKEN", "BattlePhaseSequenceDescriptor"]
__all__ += ["DRAFT202012", "EMPTY_REGISTRY", "DetachmentSelection", "Draft202012Validator"]
__all__ += ["FIXED_SECONDARY_OPTION_ID", "GameConfig", "GameLifecycle", "HTTPResponse"]
__all__ += ["HTTP_REQUEST_TIMEOUT_SECONDS", "Iterator", "JsonValue", "MissionSetup"]
__all__ += ["PARTICIPANT_B", "PLAYER_A", "PLAYER_B", "ModelProfileSelection", "Path", "Protocol"]
__all__ += ["REPO_ROOT", "ReplayArtifactPayload", "ReplayProjectionCheckpoint"]
__all__ += ["ReplayProjectionSnapshot", "ReplayRunStatus", "ReplayRunner", "Resource"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SELECT_DEPLOYMENT_UNIT"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION"]
__all__ += ["SESSION_CREATE_SCHEMA_VERSION", "SQLiteSessionPersistenceStore"]
__all__ += ["SUBMIT_DEPLOYMENT_PLACEMENT", "Schema", "SchemaRegistry", "ServerResponse"]
__all__ += ["SessionPersistenceError", "SessionPersistenceStore", "ThreadPoolExecutor"]
__all__ += ["UTC", "ThreadingHTTPServer", "UnitMusterSelection", "_PayloadValidator"]
__all__ += ["_compact_army_muster_request", "_field_float", "_json_string", "_pending_decision"]
__all__ += ["_pose_payload", "_read_json", "_replay_projection", "_request_token"]
__all__ += ["_schema_payloads", "_schema_registry", "_start_command"]
__all__ += ["_terminal_progress_option_id", "chapter_approved_2026_27_mission_pack", "datetime"]
__all__ += ["pre_record_unsupported_session", "project_game_view", "pytest"]
__all__ += ["recorded_unsupported_session", "urlopen", "validate_json_value"]


@pytest.mark.parametrize("competitor", ["factory", "reuse_address"])
def test_http_listener_excludes_competitors_and_preserves_authenticated_session(
    competitor: str,
) -> None:
    server = create_http_server(host="127.0.0.1", port=0, api=AdapterGameServer())
    host, port = cast(tuple[str, int], server.server_address)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://{host}:{port}"
    try:
        if sys.platform == "win32":
            assert server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE) == 1
            assert server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 0
        else:
            assert server.allow_reuse_address is True
            assert server.socket.getsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR) == 1
        created = _http_json(
            Request(
                f"{base_url}/sessions",
                data=json.dumps(_session_create_body("listener-exclusivity")).encode(),
                headers={
                    "Authorization": bearer_authorization(DEV_ADMIN_TOKEN),
                    "Content-Type": "application/json",
                },
                method="POST",
            )
        )
        session_id = _field_string(created, "session_id")
        envelope = _command_envelope(
            session_id=session_id,
            command_id="listener-exclusivity-start",
            expected_revision=0,
            submission_kind="start_session",
        )
        first_status, first_bytes = _http_command_bytes(base_url, session_id, envelope)
        assert first_status == 200
        first = _json_object(validate_json_value(json.loads(first_bytes)))
        assert first["committed"] is True
        assert _field_int(_field_object(first, "session"), "session_revision") == 1

        with pytest.raises(OSError) as refused:
            if competitor == "factory":
                with create_http_server(host=host, port=port, api=AdapterGameServer()):
                    pytest.fail("A second factory listener acquired an occupied address")
            else:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as competing_socket:
                    competing_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
                    competing_socket.bind((host, port))
        assert refused.value.errno in {errno.EADDRINUSE, errno.EACCES}

        # The original authority and its committed session survive both failed binds.
        retry_status, retry_bytes = _http_command_bytes(base_url, session_id, envelope)
        assert retry_status == 200
        assert retry_bytes == first_bytes
        assert thread.is_alive()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5.0)
    assert not thread.is_alive()
    if sys.platform != "win32":
        # Preserve the existing POSIX quick-restart behavior after real HTTP traffic.
        with create_http_server(host=host, port=port, api=AdapterGameServer()) as restarted:
            assert restarted.server_address == (host, port)
