from __future__ import annotations

import json
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, datetime
from http.client import HTTPResponse
from http.server import ThreadingHTTPServer
from pathlib import Path
from threading import Barrier, Thread
from typing import Protocol, cast
from urllib.request import Request, urlopen

from jsonschema import Draft202012Validator
from referencing import Resource
from referencing.jsonschema import DRAFT202012, EMPTY_REGISTRY, Schema, SchemaRegistry
from tests.phase18f_command_helpers import (
    pre_record_unsupported_session,
    recorded_unsupported_session,
)

from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    DEV_PLAYER_A_TOKEN,
    DEV_PLAYER_B_TOKEN,
    bearer_authorization,
)
from warhammer40k_core.adapters.external_contract import (
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.projection import project_game_view
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.server_types import ServerResponse
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    BattlePhaseKind,
    BattlePhaseSequenceDescriptor,
    MovementMode,
    RulesetDescriptor,
)
from warhammer40k_core.engine.army_mustering import ArmyMusterRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
)
from warhammer40k_core.engine.replay import (
    ReplayArtifactPayload,
    ReplayProjectionCheckpoint,
    ReplayProjectionSnapshot,
    ReplayRunner,
    ReplayRunStatus,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2026_27_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import tacoma_open_2026

REPO_ROOT = Path(__file__).resolve().parents[2]
PLAYER_A = "player-a"
PLAYER_B = "player-b"
PARTICIPANT_A = "participant-a"
PARTICIPANT_B = "participant-b"
FIXED_SECONDARY_OPTION_ID = "fixed:assassination:bring_it_down"
NORMAL_MOVE_ACTION_OPTION_ID = "normal_move"
SELECT_DEPLOYMENT_UNIT = "select_deployment_unit"
SUBMIT_DEPLOYMENT_PLACEMENT = "submit_deployment_placement"


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...

    def iter_errors(self, instance: object) -> Iterator[object]: ...


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
    assert len(proposal_paths) == 23
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


def _create_session(server: AdapterGameServer, *, game_id: str) -> str:
    created = _request(
        server,
        "POST",
        "/sessions",
        body=_session_create_body(game_id),
        expected_status=201,
    )
    return _field_string(created, "session_id")


def _start_command(server: AdapterGameServer, session_id: str, command_id: str) -> None:
    _submit_command(
        server,
        participant_id=PARTICIPANT_A,
        envelope=_command_envelope(
            session_id=session_id,
            command_id=command_id,
            expected_revision=0,
            submission_kind="start_session",
        ),
    )


def _session_create_body(game_id: str) -> dict[str, JsonValue]:
    config = canonical_setup_prebattle_smoke_config(game_id=game_id)
    return _session_create_body_from_config(config)


def _session_create_body_from_config(config: GameConfig) -> dict[str, JsonValue]:
    return {
        "schema_version": SESSION_CREATE_SCHEMA_VERSION,
        "config": validate_json_value(config.to_payload()),
    }


def _compact_terminal_config(*, game_id: str) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    descriptor = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="core-v2-phase18f-terminal"
    )
    compact_descriptor = replace(
        descriptor,
        descriptor_hash="",
        battle_phase_sequence=BattlePhaseSequenceDescriptor(
            phases=(BattlePhaseKind.COMMAND, BattlePhaseKind.FIGHT)
        ),
    )
    return GameConfig(
        game_id=game_id,
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=compact_descriptor,
        army_catalog=catalog,
        army_muster_requests=(
            _compact_army_muster_request(
                catalog=catalog,
                player_id=PLAYER_A,
                army_id="army-alpha",
                unit_selection_id="terminal-unit-a",
            ),
            _compact_army_muster_request(
                catalog=catalog,
                player_id=PLAYER_B,
                army_id="army-beta",
                unit_selection_id="terminal-unit-b",
            ),
        ),
        player_ids=(PLAYER_A, PLAYER_B),
        turn_order=(PLAYER_A, PLAYER_B),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=MissionSetup.from_mission_pack(
            mission_pack=chapter_approved_2026_27_mission_pack(),
            mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-3",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            attacker_player_id=PLAYER_A,
            defender_player_id=PLAYER_B,
        ),
    )


def _compact_army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id="purge-the-foe",
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )


def _command_envelope(
    *,
    session_id: str,
    command_id: str,
    expected_revision: int,
    submission_kind: str,
    request_id: str | None = None,
    result_id: str | None = None,
    option_id: str | None = None,
    payload: JsonValue = None,
) -> dict[str, JsonValue]:
    submission: dict[str, JsonValue] = {"submission_kind": submission_kind}
    if option_id is not None:
        submission["option_id"] = option_id
    if submission_kind == "parameterized_payload":
        submission["payload"] = payload
    return {
        "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
        "command_id": command_id,
        "session_id": session_id,
        "expected_session_revision": expected_revision,
        "request_id": request_id,
        "result_id": result_id,
        "submission": submission,
    }


def _submit_command(
    server: AdapterGameServer,
    *,
    participant_id: str,
    envelope: dict[str, JsonValue],
) -> dict[str, JsonValue]:
    response = _request_raw(
        server,
        session_id=_field_string(envelope, "session_id"),
        participant_id=participant_id,
        envelope=envelope,
    )
    assert response.status_code == 200, response.payload
    return _json_object(response.payload)


def _request_raw(
    server: AdapterGameServer,
    *,
    session_id: str,
    participant_id: str | None,
    envelope: dict[str, JsonValue],
) -> ServerResponse:
    submission = _field_object(envelope, "submission")
    lifecycle_command = _field_string(submission, "submission_kind") in {
        "start_session",
        "advance_session",
        "close_session",
    }
    if participant_id == PARTICIPANT_A and lifecycle_command:
        token = DEV_ADMIN_TOKEN
    elif participant_id == PARTICIPANT_A:
        token = DEV_PLAYER_A_TOKEN
    elif participant_id == PARTICIPANT_B:
        token = DEV_PLAYER_B_TOKEN
    else:
        token = "invalid-principal-token"
    return server.handle(
        method="POST",
        path=f"/sessions/{session_id}/commands",
        authorization=bearer_authorization(token),
        body=envelope,
    )


def _request(
    server: AdapterGameServer,
    method: str,
    path: str,
    *,
    query: dict[str, str] | None = None,
    body: JsonValue = None,
    expected_status: int = 200,
) -> dict[str, JsonValue]:
    response = server.handle(
        method=method,
        path=path,
        query=query,
        body=body,
        authorization=bearer_authorization(_request_token(path=path, query=query, body=body)),
    )
    assert response.status_code == expected_status, response.payload
    payload = _json_object(response.payload)
    if path.endswith("/projection") and "projection" in payload:
        return _field_object(payload, "projection")
    return payload


def _pending_decision(
    server: AdapterGameServer,
    *,
    session_id: str,
    player_id: str,
) -> dict[str, JsonValue]:
    projection = _request(
        server,
        "GET",
        f"/sessions/{session_id}/projection",
        query={"viewer_player_id": player_id},
    )
    return _field_object(projection, "pending_decision")


def _pending_decision_for_any_player(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> dict[str, JsonValue]:
    for player_id in (PLAYER_A, PLAYER_B):
        pending = _pending_decision(server, session_id=session_id, player_id=player_id)
        if pending["decision_type"] != "hidden_decision":
            return pending
    raise AssertionError("No actor-visible protocol decision found.")


def _request_token(
    *,
    path: str,
    query: dict[str, str] | None,
    body: JsonValue,
) -> str:
    if query is not None:
        viewer = query.get("viewer_player_id")
        if viewer == PLAYER_A:
            return DEV_PLAYER_A_TOKEN
        if viewer == PLAYER_B:
            return DEV_PLAYER_B_TOKEN
    if isinstance(body, dict):
        actor = body.get("actor_id")
        if actor == PLAYER_A:
            return DEV_PLAYER_A_TOKEN
        if actor == PLAYER_B:
            return DEV_PLAYER_B_TOKEN
    return DEV_ADMIN_TOKEN


def _advance_to_deployment_placement(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> dict[str, JsonValue]:
    while True:
        pending = _pending_decision_for_any_player(server, session_id=session_id)
        decision_type = _field_string(pending, "decision_type")
        if decision_type == SUBMIT_DEPLOYMENT_PLACEMENT:
            return pending
        if decision_type == SECONDARY_MISSION_DECISION_TYPE:
            option_id = FIXED_SECONDARY_OPTION_ID
        else:
            assert decision_type in {"select_reserve_declaration", SELECT_DEPLOYMENT_UNIT}
            option_id = _first_option_id(pending)
        revision = _session_revision(server, session_id=session_id)
        _submit_command(
            server,
            participant_id=_participant_for_player(_field_string(pending, "actor_id")),
            envelope=_command_envelope(
                session_id=session_id,
                command_id=f"phase18f-setup-{_field_string(pending, 'request_id')}",
                expected_revision=revision,
                submission_kind="finite_option",
                request_id=_field_string(pending, "request_id"),
                result_id=f"phase18f-result-{_field_string(pending, 'request_id')}",
                option_id=option_id,
            ),
        )


def _advance_to_movement_selection(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> dict[str, JsonValue]:
    while True:
        pending = _pending_decision_for_any_player(server, session_id=session_id)
        decision_type = _field_string(pending, "decision_type")
        if decision_type == SELECT_MOVEMENT_UNIT_DECISION_TYPE:
            return pending
        if decision_type == SUBMIT_DEPLOYMENT_PLACEMENT:
            player_id = _field_string(pending, "actor_id")
            projection = _request(
                server,
                "GET",
                f"/sessions/{session_id}/projection",
                query={"viewer_player_id": player_id},
            )
            _submit_command(
                server,
                participant_id=_participant_for_player(player_id),
                envelope=_command_envelope(
                    session_id=session_id,
                    command_id=f"phase18f-movement-{_field_string(pending, 'request_id')}",
                    expected_revision=_session_revision(server, session_id=session_id),
                    submission_kind="parameterized_payload",
                    request_id=_field_string(pending, "request_id"),
                    result_id=f"phase18f-movement-result-{_field_string(pending, 'request_id')}",
                    payload=_deployment_payload_from_proposal(
                        _field_object(projection, "pending_proposal")
                    ),
                ),
            )
            continue
        if decision_type == SECONDARY_MISSION_DECISION_TYPE:
            option_id = FIXED_SECONDARY_OPTION_ID
        else:
            assert decision_type == SELECT_DEPLOYMENT_UNIT
            option_id = _first_option_id(pending)
        _submit_visible_option_command(
            server,
            session_id=session_id,
            request=pending,
            option_id=option_id,
            command_id=f"phase18f-movement-{_field_string(pending, 'request_id')}",
        )


def _submit_visible_option_command(
    server: AdapterGameServer,
    *,
    session_id: str,
    request: dict[str, JsonValue],
    option_id: str,
    command_id: str,
) -> dict[str, JsonValue]:
    player_id = _field_string(request, "actor_id")
    return _submit_command(
        server,
        participant_id=_participant_for_player(player_id),
        envelope=_command_envelope(
            session_id=session_id,
            command_id=command_id,
            expected_revision=_session_revision(server, session_id=session_id),
            submission_kind="finite_option",
            request_id=_field_string(request, "request_id"),
            result_id=f"{command_id}-result",
            option_id=option_id,
        ),
    )


def _deployment_payload_from_proposal(value: JsonValue) -> dict[str, JsonValue]:
    proposal = _json_object(value)
    player_id = _field_string(proposal, "player_id")
    unit_instance_id = _field_string(proposal, "unit_instance_id")
    army_id = unit_instance_id.split(":", maxsplit=1)[0]
    zone = _json_object(_field_list(proposal, "legal_deployment_zones")[0])
    polygon = _json_object(_field_list(_field_object(zone, "shape"), "polygons")[0])
    vertices = [_json_object(vertex) for vertex in _field_list(polygon, "vertices")]
    min_x = min(_field_float(vertex, "x") for vertex in vertices)
    min_y = min(_field_float(vertex, "y") for vertex in vertices)
    facing = 180.0 if player_id == PLAYER_B else 0.0
    placements: list[JsonValue] = []
    for index, model_id in enumerate(_field_list(proposal, "model_instance_ids")):
        placements.append(
            {
                "army_id": army_id,
                "player_id": player_id,
                "unit_instance_id": unit_instance_id,
                "model_instance_id": _json_string(model_id),
                "pose": {
                    "position": {
                        "x": min_x + 3.0 + ((index // 3) * 1.8),
                        "y": min_y + 3.0 + ((index % 3) * 1.8),
                        "z": 0.0,
                    },
                    "facing": {"degrees": facing},
                },
            }
        )
    return {
        "proposal_request_id": _field_string(proposal, "request_id"),
        "proposal_kind": _field_string(proposal, "proposal_kind"),
        "game_id": _field_string(proposal, "game_id"),
        "ruleset_descriptor_hash": _field_string(proposal, "ruleset_descriptor_hash"),
        "setup_step": _field_string(proposal, "setup_step"),
        "player_id": player_id,
        "unit_instance_id": unit_instance_id,
        "placement_kind": _field_string(proposal, "placement_kind"),
        "model_placements": placements,
        "context": proposal["context"],
    }


def _invalid_distance_witness(
    *,
    projection: dict[str, JsonValue],
    unit_instance_id: str,
) -> dict[str, JsonValue]:
    battlefield = _field_object(projection, "battlefield_state")
    for army_value in _field_list(battlefield, "placed_armies"):
        army = _json_object(army_value)
        for unit_value in _field_list(army, "unit_placements"):
            unit = _json_object(unit_value)
            if unit["unit_instance_id"] != unit_instance_id:
                continue
            model_paths: list[JsonValue] = []
            for model_value in _field_list(unit, "model_placements"):
                model = _json_object(model_value)
                pose = _field_object(model, "pose")
                position = _field_object(pose, "position")
                facing = _field_object(pose, "facing")
                x = _field_float(position, "x")
                y = _field_float(position, "y")
                z = _field_float(position, "z")
                degrees = _field_float(facing, "degrees")
                model_paths.append(
                    {
                        "model_id": _field_string(model, "model_instance_id"),
                        "poses": [
                            _pose_payload(x=x, y=y, z=z, degrees=degrees),
                            _pose_payload(x=x + 500.0, y=y, z=z, degrees=degrees),
                            _pose_payload(x=x + 1000.0, y=y, z=z, degrees=degrees),
                        ],
                    }
                )
            return {"model_paths": model_paths}
    raise AssertionError("Movement proposal unit placement was not visible.")


def _pose_payload(*, x: float, y: float, z: float, degrees: float) -> dict[str, JsonValue]:
    return {
        "position": {"x": x, "y": y, "z": z},
        "facing": {"degrees": degrees},
    }


def _authoritative_snapshot(
    server: AdapterGameServer,
    *,
    session_id: str,
) -> tuple[int, str | None, str, int, int]:
    metadata = _request(
        server,
        "GET",
        f"/sessions/{session_id}",
        query={"viewer_player_id": PLAYER_A},
    )
    replay = _request(server, "GET", f"/sessions/{session_id}/replay")
    projection_hash = metadata["projection_state_hash"]
    assert projection_hash is None or type(projection_hash) is str
    return (
        _field_int(metadata, "session_revision"),
        projection_hash,
        _field_string(metadata, "event_cursor"),
        len(_field_list(replay, "decision_records")),
        len(_field_list(replay, "event_records")),
    )


def _cursor_offset(server: AdapterGameServer, token: str) -> int:
    return server.cursor_codec.decode(token).offset


def _session_revision(server: AdapterGameServer, *, session_id: str) -> int:
    metadata = _request(server, "GET", f"/sessions/{session_id}")
    return _field_int(metadata, "session_revision")


def _participant_for_player(player_id: str) -> str:
    if player_id == PLAYER_A:
        return PARTICIPANT_A
    assert player_id == PLAYER_B
    return PARTICIPANT_B


def _replay_projection(
    lifecycle: GameLifecycle,
    checkpoint: ReplayProjectionCheckpoint,
) -> ReplayProjectionSnapshot:
    projection = project_game_view(
        lifecycle=lifecycle,
        viewer_player_id=checkpoint.viewer_player_id,
    )
    return ReplayProjectionSnapshot(
        viewer_player_id=checkpoint.viewer_player_id,
        projection_schema=projection["projection_schema"],
        projection_state_hash=projection["projection_state_hash"],
    )


def _http_server(server: AdapterGameServer) -> ThreadingHTTPServer:
    from warhammer40k_core.adapters.server import create_local_dev_http_server

    return create_local_dev_http_server(api=server)


def _http_json(request: Request) -> dict[str, JsonValue]:
    response = cast(HTTPResponse, urlopen(request, timeout=10.0))
    try:
        return _json_object(validate_json_value(json.loads(response.read().decode("utf-8"))))
    finally:
        response.close()


def _http_command_bytes(
    base_url: str,
    session_id: str,
    envelope: dict[str, JsonValue],
) -> tuple[int, bytes]:
    request = Request(
        f"{base_url}/sessions/{session_id}/commands",
        data=json.dumps(envelope, sort_keys=True).encode("utf-8"),
        headers={
            "Authorization": bearer_authorization(DEV_ADMIN_TOKEN),
            "Content-Type": "application/json",
        },
        method="POST",
    )
    response = cast(HTTPResponse, urlopen(request, timeout=10.0))
    try:
        return response.status, response.read()
    finally:
        response.close()


def _schema_validator(schema_name: str) -> _PayloadValidator:
    schemas = _schema_payloads()
    return cast(
        _PayloadValidator,
        Draft202012Validator(schemas[schema_name], registry=_schema_registry(schemas)),
    )


def _schema_payloads() -> dict[str, Schema]:
    names = (
        "lifecycle-status.schema.json",
        "proposal-payload.schema.json",
        "session-command-envelope.schema.json",
        "session-command-outcome.schema.json",
        "session-metadata.schema.json",
    )
    return {
        name: cast(Schema, _read_json(REPO_ROOT / "contracts" / "schemas" / name)) for name in names
    }


def _schema_registry(schemas: dict[str, Schema]) -> SchemaRegistry:
    registry = EMPTY_REGISTRY
    for schema in schemas.values():
        if not isinstance(schema, dict):
            raise TypeError("Contract schemas must be JSON objects.")
        schema_id = schema.get("$id")
        assert type(schema_id) is str
        registry = registry.with_resource(
            schema_id,
            cast(
                Resource[Schema],
                Resource.from_contents(schema, default_specification=DRAFT202012),
            ),
        )
    return registry


def _read_json(path: Path) -> dict[str, JsonValue]:
    return _json_object(validate_json_value(json.loads(path.read_text(encoding="utf-8"))))


def _error_code(response: ServerResponse) -> str:
    return _field_string(_field_object(_json_object(response.payload), "error"), "code")


def _first_option_id(request: dict[str, JsonValue]) -> str:
    return _field_string(_json_object(_field_list(request, "options")[0]), "option_id")


def _terminal_progress_option_id(request: dict[str, JsonValue]) -> str:
    option_ids = tuple(
        _field_string(_json_object(option), "option_id")
        for option in _field_list(request, "options")
    )
    if request["decision_type"] == SECONDARY_MISSION_DECISION_TYPE:
        assert FIXED_SECONDARY_OPTION_ID in option_ids
        return FIXED_SECONDARY_OPTION_ID
    for preferred in ("complete_prebattle_actions", "declare_no_reserves"):
        if preferred in option_ids:
            return preferred
    for option_id in option_ids:
        if any(token in option_id for token in ("decline", "complete", "none", "skip")):
            return option_id
    return option_ids[0]


def _json_object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict)
    return value


def _field_object(value: dict[str, JsonValue], key: str) -> dict[str, JsonValue]:
    return _json_object(value[key])


def _field_list(value: dict[str, JsonValue], key: str) -> list[JsonValue]:
    result = value[key]
    assert isinstance(result, list)
    return result


def _field_string(value: dict[str, JsonValue], key: str) -> str:
    return _json_string(value[key])


def _json_string(value: JsonValue) -> str:
    assert type(value) is str
    return value


def _field_int(value: dict[str, JsonValue], key: str) -> int:
    result = value[key]
    assert type(result) is int
    return result


def _field_float(value: dict[str, JsonValue], key: str) -> float:
    result = value[key]
    if type(result) is int:
        return float(result)
    assert type(result) is float
    return result
