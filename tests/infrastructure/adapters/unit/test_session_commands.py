from __future__ import annotations

import cProfile
import errno
import socket
import sys
from dataclasses import fields
from types import CodeType
from typing import Protocol, cast

from jsonschema.exceptions import ValidationError

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
from warhammer40k_core.adapters.access_control import (
    DEV_COACH_A_TOKEN,
    DEV_SPECTATOR_TOKEN,
    ViewerContext,
)
from warhammer40k_core.adapters.http_transport import create_http_server
from warhammer40k_core.adapters.projection import DecisionRequestViewPayload
from warhammer40k_core.adapters.redaction import redacted_lifecycle_status
from warhammer40k_core.adapters.server_commands import uncommitted_command_response
from warhammer40k_core.adapters.session_protocol import AuthoritativeSession, SessionProtocolError
from warhammer40k_core.engine.phase import GameLifecycleStage, LifecycleStatus
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pathing import PathWitness, TerrainPathLegalityContext
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.volume import Model, ModelVolume


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

    http_server = _http_server(server)
    host, port = cast(tuple[str, int], http_server.server_address)
    thread = Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        status_code, outcome = _http_player_command(
            f"http://{host}:{port}",
            session_id,
            envelope,
            DEV_PLAYER_A_TOKEN if player_id == PLAYER_A else DEV_PLAYER_B_TOKEN,
        )
    finally:
        http_server.shutdown()
        http_server.server_close()
        thread.join(timeout=5.0)
    assert status_code == 422
    response = ServerResponse(status_code=status_code, payload=outcome)
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


def _http_player_command(
    base_url: str, session_id: str, envelope: dict[str, JsonValue], token: str
) -> tuple[int, dict[str, JsonValue]]:
    from urllib.error import HTTPError

    request = Request(
        f"{base_url}/sessions/{session_id}/commands",
        data=json.dumps(envelope).encode(),
        headers={
            "Authorization": bearer_authorization(token),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        response = urlopen(request, timeout=HTTP_REQUEST_TIMEOUT_SECONDS)
    except HTTPError as exc:
        response = exc
    with response:
        status_code = response.status
        assert type(status_code) is int
        return status_code, _json_object(validate_json_value(json.loads(response.read())))


def test_authenticated_http_movement_inventory_rejection_preserves_diagnostics_and_retry() -> None:
    server = AdapterGameServer()
    compact = _compact_terminal_config(game_id="http-rejection")
    config = replace(
        compact,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="core-v2-http-rejection"
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
            command_id="http-rejection-start",
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
        command_id="http-rejection-unit",
    )
    action_request = _pending_decision_for_any_player(server, session_id=session_id)
    assert action_request["decision_type"] == SELECT_MOVEMENT_ACTION_DECISION_TYPE
    _submit_visible_option_command(
        server,
        session_id=session_id,
        request=action_request,
        option_id=NORMAL_MOVE_ACTION_OPTION_ID,
        command_id="http-rejection-action",
    )
    proposal_request = _pending_decision_for_any_player(server, session_id=session_id)
    proposal_view = _request(
        server,
        "GET",
        f"/sessions/{session_id}/projection",
        query={"viewer_player_id": player_id},
    )
    proposal = _field_object(proposal_view, "pending_proposal")

    request_id = _field_string(proposal_request, "request_id")
    revision = _session_revision(server, session_id=session_id)
    legal_witness = _invalid_distance_witness(
        projection=proposal_view, unit_instance_id=_field_string(proposal, "unit_instance_id")
    )
    for row in _field_list(legal_witness, "model_paths"):
        model_path = _json_object(row)
        origin = _field_list(model_path, "poses")[0]
        model_path["poses"] = [origin, origin]
    legal_payload: dict[str, JsonValue] = {
        "proposal_request_id": _field_string(proposal, "request_id"),
        "proposal_kind": _field_string(proposal, "proposal_kind"),
        "unit_instance_id": _field_string(proposal, "unit_instance_id"),
        "movement_phase_action": "normal_move",
        "movement_mode": MovementMode.NORMAL.value,
        "witness": legal_witness,
    }
    wrong_witness = _json_object(validate_json_value(json.loads(json.dumps(legal_witness))))
    _json_object(_field_list(wrong_witness, "model_paths")[0])["model_id"] = "foreign-model"
    envelope = _command_envelope(
        session_id=session_id,
        command_id="http-rejection-wrong-inventory",
        expected_revision=revision,
        submission_kind="parameterized_payload",
        request_id=request_id,
        result_id="http-rejection-wrong-result",
        payload={**legal_payload, "witness": wrong_witness},
    )
    token = DEV_PLAYER_A_TOKEN if player_id == PLAYER_A else DEV_PLAYER_B_TOKEN
    before = _request(server, "GET", f"/sessions/{session_id}/replay")
    snapshot = _authoritative_snapshot(server, session_id=session_id)
    http_server = _http_server(server)
    host, port = cast(tuple[str, int], http_server.server_address)
    thread = Thread(target=http_server.serve_forever, daemon=True)
    thread.start()
    try:
        base_url = f"http://{host}:{port}"
        status, rejected = _http_player_command(base_url, session_id, envelope, token)
        assert status == 422
        _error_envelope_validator().validate(rejected)
        assert _field_object(rejected, "error") == {
            "code": "proposal_invalid",
            "message": "Submitted proposal was invalid.",
            "diagnostics": {
                "kind": "proposal_validation",
                "violations": [
                    {
                        "violation_code": "movement_witness_model_inventory_mismatch",
                        "field": "witness",
                    }
                ],
            },
        }
        assert _request(server, "GET", f"/sessions/{session_id}/replay") == before
        assert _authoritative_snapshot(server, session_id=session_id) == snapshot
        assert _pending_decision_for_any_player(server, session_id=session_id) == proposal_request
        for denied_token in (
            DEV_PLAYER_B_TOKEN if player_id == PLAYER_A else DEV_PLAYER_A_TOKEN,
            DEV_COACH_A_TOKEN,
            DEV_SPECTATOR_TOKEN,
        ):
            denied_status, denied = _http_player_command(
                base_url, session_id, envelope, denied_token
            )
            assert denied_status == 403
            assert _field_object(denied, "error") == {
                "code": "access_denied",
                "message": "Authenticated principal is not authorized for this resource.",
            }
            _error_envelope_validator().validate(denied)
            assert _request(server, "GET", f"/sessions/{session_id}/replay") == before
        retry = _command_envelope(
            session_id=session_id,
            command_id="http-rejection-corrected-command",
            expected_revision=revision,
            submission_kind="parameterized_payload",
            request_id=request_id,
            result_id="http-rejection-corrected-result",
            payload=legal_payload,
        )
        status, accepted = _http_player_command(base_url, session_id, retry, token)
        assert status == 200
        assert accepted["accepted"] is True
        assert accepted["committed"] is True
        assert _field_int(_field_object(accepted, "session"), "session_revision") == revision + 1
        after = _request(server, "GET", f"/sessions/{session_id}/replay")
        server.principal_registry = replace(
            server.principal_registry,
            authorization_epoch=server.principal_registry.authorization_epoch + 1,
        )
        denied_status, denied = _http_player_command(base_url, session_id, retry, token)
        assert denied_status == 403
        assert _field_object(denied, "error")["code"] == "access_denied"
        assert "diagnostics" not in _field_object(denied, "error")
        assert _request(server, "GET", f"/sessions/{session_id}/replay") == after
    finally:
        http_server.shutdown()
        http_server.server_close()
        thread.join(timeout=5.0)


def _error_envelope_validator() -> _PayloadValidator:
    return cast(
        _PayloadValidator,
        Draft202012Validator(
            cast(
                Schema,
                _read_json(REPO_ROOT / "contracts" / "schemas" / "error-envelope.schema.json"),
            )
        ),
    )


@pytest.mark.parametrize("reason", [None, "phase_body_not_implemented"])
def test_uncommitted_unsupported_diagnostics_are_closed_and_optional(reason: str | None) -> None:
    # Pure response assembly: the setup HTTP scenario has no native unsupported path.
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="unsupported-diagnostics")
    _start_command(server, session_id, "unsupported-diagnostics-start")
    pending = cast(
        DecisionRequestViewPayload,
        _pending_decision(server, session_id=session_id, player_id=PLAYER_A),
    )
    viewer = ViewerContext.for_player(PLAYER_A)
    status = LifecycleStatus.unsupported(
        stage=GameLifecycleStage.SETUP,
        message="private message must not escape",
        payload=None
        if reason is None
        else {
            "unsupported_reason": reason,
            "private_snapshot": {"opponent_secret": "private sentinel"},
        },
    )
    outcome: dict[str, JsonValue] = {
        "outcome_code": "rule_path_unsupported",
        "session": {
            "lifecycle_status": cast(JsonValue, redacted_lifecycle_status(status, viewer=viewer))
        },
    }
    response = uncommitted_command_response(
        response_payload=outcome, viewer=viewer, pending=pending
    )
    assert response.status_code == 422
    _error_envelope_validator().validate(response.payload)
    error = _field_object(_json_object(response.payload), "error")
    if reason is None:
        assert "diagnostics" not in error
    else:
        assert error["diagnostics"] == {"kind": "unsupported_reason", "reason_code": reason}
    assert "private" not in json.dumps(response.payload)
    hidden = uncommitted_command_response(
        response_payload=outcome, viewer=ViewerContext.for_player(PLAYER_B), pending=pending
    )
    assert "diagnostics" not in _field_object(_json_object(hidden.payload), "error")


def test_error_diagnostic_schema_rejects_unknown_mixed_and_private_members() -> None:
    validator = _error_envelope_validator()
    base_error = {"code": "proposal_invalid", "message": "Proposal invalid."}
    base = {
        "schema_version": "error-envelope-v2-diagnostics",
        "error": base_error,
    }
    diagnostics: dict[str, JsonValue] = {
        "kind": "proposal_validation",
        "violations": [
            {"violation_code": "movement_witness_model_inventory_mismatch", "field": "witness"}
        ],
    }
    validator.validate(base)
    validator.validate({**base, "error": {**base_error, "diagnostics": diagnostics}})
    invalid_diagnostics: list[JsonValue] = [
        {},
        {"kind": "unknown"},
        {**diagnostics, "private_snapshot": {}},
        {**diagnostics, "reason_code": "unsupported"},
        {**diagnostics, "violations": []},
        {
            **diagnostics,
            "violations": [{"violation_code": "bad", "field": None, "message": "private contents"}],
        },
        {"kind": "unsupported_reason", "reason_code": "unsupported"},
    ]
    for invalid in invalid_diagnostics:
        with pytest.raises(ValidationError):
            validator.validate({**base, "error": {**base_error, "diagnostics": invalid}})


def test_command_fork_isolates_live_owners_without_reexporting_retained_history() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="trusted-command-fork")
    _start_command(server, session_id, "trusted-command-fork-start")
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    original_history = record.adapter_session.authoritative_history_payload()
    snapshot_histories = {
        revision: snapshot.adapter_session.authoritative_history_payload()
        for revision, snapshot in record.revision_snapshots.items()
    }

    with cProfile.Profile() as profile:
        fork = record.fork_for_command()
    exported_history_calls = sum(
        entry.callcount
        for entry in profile.getstats()
        if isinstance(entry.code, CodeType)
        and entry.code.co_name == "authoritative_history_payload"
    )
    assert exported_history_calls == 0

    copied_fields = {
        "adapter_session",
        "ruleset_id",
        "command_journal",
        "revision_snapshots",
        "revision_history",
    }
    for field in fields(record):
        original = getattr(record, field.name)
        cloned = getattr(fork, field.name)
        if field.name in copied_fields:
            assert cloned is not original, field.name
        else:
            assert cloned is original, field.name
    for revision, snapshot in record.revision_snapshots.items():
        assert fork.revision_snapshots[revision] is snapshot
        assert fork.revision_history[revision] is record.revision_history[revision]
    for command_id, entry in record.command_journal.items():
        assert fork.command_journal[command_id] is entry

    pending = _pending_decision_for_any_player(server, session_id=session_id)
    fork.adapter_session.submit_option(
        request_id=_field_string(pending, "request_id"),
        option_id=_first_option_id(pending),
        result_id="trusted-command-fork-result",
    )
    assert (
        fork.adapter_session.decision_record_count()
        > record.adapter_session.decision_record_count()
    )
    assert record.adapter_session.authoritative_history_payload() == original_history
    assert {
        revision: snapshot.adapter_session.authoritative_history_payload()
        for revision, snapshot in record.revision_snapshots.items()
    } == snapshot_histories
    fork.command_journal.clear()
    fork.revision_snapshots.clear()
    fork.revision_history.clear()
    _json_object(fork.ruleset_id)["fork_only"] = ["isolated"]
    assert record.command_journal
    assert record.revision_snapshots
    assert record.revision_history
    assert "fork_only" not in _json_object(record.ruleset_id)


def test_command_fork_keeps_creation_and_persistence_history_validation() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="trusted-command-boundaries")
    _start_command(server, session_id, "trusted-command-boundaries-start")
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    payload = record.fork_for_command().to_persistence_payload()
    restored = AuthoritativeSession.from_persistence_payload(
        payload, session_recovery_factory=server.session_recovery_factory
    )
    assert restored.to_persistence_payload() == payload
    with pytest.raises(SessionProtocolError, match="revision history is missing"):
        replace(record, revision_history={})
    payload["revision_history"] = []
    with pytest.raises(SessionProtocolError, match="revision history is missing"):
        AuthoritativeSession.from_persistence_payload(
            payload, session_recovery_factory=server.session_recovery_factory
        )
    fork = record.fork_for_command()
    fork.revision_history.clear()
    with pytest.raises(SessionProtocolError, match="revision history is missing"):
        fork.to_persistence_payload()


@pytest.mark.parametrize(
    "base",
    [
        CircularBase(radius=0.5),
        OvalBase(length=1.4, width=0.6),
        RectangularBase(length=1.2, width=0.8),
    ],
    ids=["circular", "oval", "rectangular"],
)
@pytest.mark.parametrize("case", ["valid", "blocked", "clear"])
def test_terrain_path_reuses_volume_footprint_preserving_complete_result(
    base: BaseShape, case: str
) -> None:
    mover = Model(
        model_id="terrain-work-mover",
        pose=Pose.at(1, 1, facing_degrees=25),
        base=base,
        volume=ModelVolume(height=2),
    )
    terrain = TerrainVolume(
        terrain_id="terrain-work-volume",
        bottom_center=Point3(3, 10 if case == "clear" else 1, 0),
        width=1,
        depth=1,
        height=4 if case == "blocked" else 1,
        rotation_degrees=30,
    )
    context = TerrainPathLegalityContext(
        moving_model=mover,
        terrain=(terrain,),
        witness=PathWitness.for_paths(
            (
                (
                    mover.model_id,
                    (
                        mover.pose,
                        Pose.at(3, 1, facing_degrees=40),
                        Pose.at(5, 1, facing_degrees=65),
                    ),
                ),
            )
        ),
        terrain_movement_policy=RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy,
    )
    with cProfile.Profile() as profile:
        result = context.validate()
    footprint_constructions = sum(
        entry.callcount
        for entry in profile.getstats()
        if isinstance(entry.code, CodeType) and entry.code.co_name == "footprint_for_terrain"
    )
    # One traversal footprint; intersecting paths also inspect the endpoint once.
    assert footprint_constructions == (1 if case == "clear" else 2)
    # Exact pre-optimization results, including touching poses, diagnostics and
    # sample counts, for all three base shapes against a rotated terrain volume.
    assert result.to_payload() == {
        "is_valid": case != "blocked",
        "violations": [
            {
                "violation_code": "terrain_feature_transit_forbidden",
                "message": "Terrain path crosses terrain without traversal permission.",
                "terrain_id": "terrain-work-volume",
                "surface_id": None,
            }
        ]
        if case == "blocked"
        else [],
        "segments": [
            {
                "terrain_id": "terrain-work-volume",
                "traversal_mode": "freely_traversable",
                "start_pose": Pose.at(2, 1, facing_degrees=32.5).to_payload(),
                "end_pose": Pose.at(4, 1, facing_degrees=52.5).to_payload(),
                "horizontal_distance_inches": 4.0,
                "vertical_distance_inches": 0.0,
                "counted_distance_inches": 4.0,
                "air_path_measurement_pending": False,
            }
        ]
        if case == "valid"
        else [],
        "sampled_pose_count": 9,
    }
