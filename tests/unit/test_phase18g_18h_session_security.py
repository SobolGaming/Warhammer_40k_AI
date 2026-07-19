from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Protocol, cast

from jsonschema import Draft202012Validator

from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    DEV_COACH_A_TOKEN,
    DEV_PLAYER_A_TOKEN,
    DEV_PLAYER_B_TOKEN,
    DEV_REPLAY_TOKEN,
    DEV_SPECTATOR_TOKEN,
    AuthenticatedPrincipal,
    PrincipalCredential,
    PrincipalRegistry,
    PrincipalRole,
    bearer_authorization,
)
from warhammer40k_core.adapters.external_contract import (
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.redaction import HIDDEN_REQUEST_ID
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.server_types import ServerResponse
from warhammer40k_core.adapters.session_events import CURSOR_TOKEN_LENGTH
from warhammer40k_core.adapters.session_protocol import DEFAULT_REVISION_RETENTION_LIMIT
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.engine.event_log import JsonValue

PLAYER_A = "player-a"
PLAYER_B = "player-b"
REPO_ROOT = Path(__file__).resolve().parents[2]


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...


def test_phase18g_paginates_authoritative_offsets_and_resumes_from_projection() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18g-pagination")
    initial_projection = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    initial_cursor = _string(initial_projection, "event_cursor")
    initial_sequence = server.cursor_codec.decode(initial_cursor).visible_sequence

    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18g-pagination-start",
        expected_revision=0,
        submission_kind="start_session",
    )

    cursor = initial_cursor
    pages: list[dict[str, JsonValue]] = []
    while True:
        page = _events(
            server,
            session_id=session_id,
            token=DEV_PLAYER_A_TOKEN,
            cursor=cursor,
            limit=2,
        )
        pages.append(page)
        assert page["resync_required"] is False
        cursor = _string(page, "next_cursor")
        if page["has_more"] is False:
            break

    events = [_object(event) for page in pages for event in _list(page, "events")]
    sequence_numbers = [_integer(event, "sequence_number") for event in events]
    assert sequence_numbers == list(range(initial_sequence + 1, initial_sequence + len(events) + 1))
    assert all(len(_list(page, "events")) <= 2 for page in pages)
    assert _integer(pages[0], "from_revision") == 0
    assert all(_integer(page, "to_revision") == 0 for page in pages[:-1])
    assert all(
        page["projection_state_hash"] == initial_projection["projection_state_hash"]
        for page in pages[:-1]
    )
    assert _integer(pages[-1], "to_revision") == 1
    assert server.cursor_codec.decode(cursor).session_revision == 1

    current_projection = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    assert cursor == current_projection["event_cursor"]
    assert pages[-1]["projection_state_hash"] == current_projection["projection_state_hash"]
    empty = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=cursor,
    )
    assert empty["events"] == []
    assert empty["has_more"] is False
    assert empty["resync_required"] is False


def test_phase18g_returns_typed_non_leaking_resync_for_invalid_cursor_classes() -> None:
    server = AdapterGameServer(event_retention_limit=2)
    first_session = _create_session(server, game_id="phase18g-resync-first")
    second_session = _create_session(server, game_id="phase18g-resync-second")
    old_projection = _projection(
        server,
        session_id=first_session,
        token=DEV_PLAYER_A_TOKEN,
    )
    old_cursor = _string(old_projection, "event_cursor")
    _submit_lifecycle_command(
        server,
        session_id=first_session,
        command_id="phase18g-resync-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    current_projection = _projection(
        server,
        session_id=first_session,
        token=DEV_PLAYER_A_TOKEN,
    )
    current_cursor = _string(current_projection, "event_cursor")
    decoded = server.cursor_codec.decode(current_cursor)
    player = server.principal_registry.authenticate(
        bearer_authorization(DEV_PLAYER_A_TOKEN)
    ).bind_to_session(player_ids=(PLAYER_A, PLAYER_B))
    ahead_cursor = server.cursor_codec.issue(
        session_id=first_session,
        viewer=player,
        offset=decoded.offset + 1,
        visible_sequence=decoded.visible_sequence,
        session_revision=decoded.session_revision,
        projection_state_hash=decoded.projection_state_hash,
        minimum_offset=0,
        minimum_revision=0,
    )
    hash_mismatch_cursor = server.cursor_codec.issue(
        session_id=first_session,
        viewer=player,
        offset=decoded.offset,
        visible_sequence=decoded.visible_sequence,
        session_revision=decoded.session_revision,
        projection_state_hash="0" * 64,
        minimum_offset=0,
        minimum_revision=0,
    )

    cases = (
        (first_session, DEV_PLAYER_A_TOKEN, "not-a-cursor", "malformed"),
        (first_session, DEV_PLAYER_A_TOKEN, old_cursor, "expired"),
        (first_session, DEV_PLAYER_A_TOKEN, ahead_cursor, "ahead"),
        (second_session, DEV_PLAYER_A_TOKEN, current_cursor, "wrong_session"),
        (first_session, DEV_COACH_A_TOKEN, current_cursor, "wrong_viewer"),
        (
            first_session,
            DEV_PLAYER_A_TOKEN,
            hash_mismatch_cursor,
            "projection_hash_mismatch",
        ),
    )
    for session_id, token, cursor, reason in cases:
        delta = _events(server, session_id=session_id, token=token, cursor=cursor)
        assert delta["resync_required"] is True
        assert delta["resync_reason"] == reason
        assert delta["events"] == []
        assert delta["has_more"] is False
        assert _string(delta, "next_cursor") != cursor

    malformed_cases = (
        "é.x",
        "x" * 2049,
        "!" * CURSOR_TOKEN_LENGTH,
        current_cursor[:-1] + ("A" if current_cursor[-1] != "A" else "B"),
    )
    for malformed_cursor in malformed_cases:
        delta = _events(
            server,
            session_id=first_session,
            token=DEV_PLAYER_A_TOKEN,
            cursor=malformed_cursor,
        )
        assert delta["resync_required"] is True
        assert delta["resync_reason"] == "malformed"
        assert delta["supplied_cursor"] == "invalid-cursor"
        assert len(_string(delta, "supplied_cursor")) <= 2048
        _validate_event_delta(delta)

    expired = _events(
        server,
        session_id=first_session,
        token=DEV_PLAYER_A_TOKEN,
        cursor=old_cursor,
    )
    replacement = _projection(
        server,
        session_id=first_session,
        token=DEV_PLAYER_A_TOKEN,
    )
    assert expired["next_cursor"] == replacement["event_cursor"]
    assert expired["projection_state_hash"] == replacement["projection_state_hash"]
    resumed = _events(
        server,
        session_id=first_session,
        token=DEV_PLAYER_A_TOKEN,
        cursor=_string(expired, "next_cursor"),
    )
    assert resumed["resync_required"] is False
    assert resumed["events"] == []


def test_phase18g_eventless_revision_change_requires_full_projection_resync() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18g-eventless-revision")
    historical_cursor = _string(
        _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN),
        "event_cursor",
    )
    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18g-eventless-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    before_close = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    registered_before_close = server.cursor_codec.registered_cursor_count(session_id=session_id)
    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18g-eventless-close",
        expected_revision=1,
        submission_kind="close_session",
    )
    registered_after_close = server.cursor_codec.registered_cursor_count(session_id=session_id)

    delta = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=_string(before_close, "event_cursor"),
    )
    assert delta["resync_required"] is True
    assert delta["resync_reason"] == "revision_mismatch"
    assert _integer(delta, "from_revision") == 2
    assert _integer(delta, "to_revision") == 2
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    assert record.cursor_registry_finalized is True
    assert registered_before_close > 1
    assert registered_after_close < registered_before_close
    historical = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=historical_cursor,
    )
    assert historical["resync_required"] is True
    assert historical["resync_reason"] == "expired"
    final_player_cursor = _string(
        _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN),
        "event_cursor",
    )
    assert final_player_cursor == delta["next_cursor"]
    assert server.cursor_codec.registered_cursor_count(session_id=session_id) == 4


def test_phase18g_publishes_revision_retention_and_bounds_cursor_state() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18g-revision-retention")
    initial_projection = _projection(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
    )
    initial_cursor = _string(initial_projection, "event_cursor")
    record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
    initial_event_count = record.adapter_session.event_record_count()

    for _ in range(DEFAULT_REVISION_RETENTION_LIMIT + 1):
        record.commit_status(record.lifecycle_status, timestamp=record.last_activity_at)
        _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)

    assert record.session_revision == DEFAULT_REVISION_RETENTION_LIMIT + 1
    assert record.adapter_session.event_record_count() == initial_event_count
    assert initial_event_count < server.event_retention_limit
    assert record.minimum_retained_revision == 2
    assert len(record.revision_snapshots) == DEFAULT_REVISION_RETENTION_LIMIT
    assert (
        server.cursor_codec.registered_cursor_count(session_id=session_id)
        == DEFAULT_REVISION_RETENTION_LIMIT
    )

    current_projection = _projection(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
    )
    assert current_projection["retention_limit"] == server.event_retention_limit
    assert current_projection["revision_retention_limit"] == DEFAULT_REVISION_RETENTION_LIMIT
    expired = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=initial_cursor,
    )
    assert expired["resync_required"] is True
    assert expired["resync_reason"] == "expired"
    assert expired["retention_limit"] == server.event_retention_limit
    assert expired["revision_retention_limit"] == DEFAULT_REVISION_RETENTION_LIMIT
    assert (
        server.cursor_codec.registered_cursor_count(session_id=session_id)
        == DEFAULT_REVISION_RETENTION_LIMIT
    )


def test_phase18h_derives_live_visibility_and_delay_from_server_owned_roles() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18h-role-visibility")
    spectator_metadata_before = _metadata(
        server,
        session_id=session_id,
        token=DEV_SPECTATOR_TOKEN,
    )
    spectator_before = _projection(
        server,
        session_id=session_id,
        token=DEV_SPECTATOR_TOKEN,
    )
    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18h-role-start",
        expected_revision=0,
        submission_kind="start_session",
    )

    player_a = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    player_b = _projection(server, session_id=session_id, token=DEV_PLAYER_B_TOKEN)
    coach = _projection(server, session_id=session_id, token=DEV_COACH_A_TOKEN)
    spectator = _projection(server, session_id=session_id, token=DEV_SPECTATOR_TOKEN)
    spectator_metadata = _metadata(
        server,
        session_id=session_id,
        token=DEV_SPECTATOR_TOKEN,
    )
    administrator = _projection(server, session_id=session_id, token=DEV_ADMIN_TOKEN)

    assert _integer(player_a, "session_revision") == 1
    assert _integer(coach, "session_revision") == 1
    assert _integer(administrator, "session_revision") == 1
    assert _integer(spectator, "session_revision") == 0
    assert _integer(spectator_metadata, "session_revision") == 0
    assert spectator_metadata["last_activity_at"] == spectator_metadata_before["last_activity_at"]
    assert spectator["projection_state_hash"] == spectator_before["projection_state_hash"]
    assert _object(spectator, "projection")["pending_decision"] is None

    player_a_pending = _object(_object(player_a, "projection"), "pending_decision")
    coach_pending = _object(_object(coach, "projection"), "pending_decision")
    admin_pending = _object(_object(administrator, "projection"), "pending_decision")
    player_b_pending = _object(_object(player_b, "projection"), "pending_decision")
    assert coach_pending == player_a_pending
    assert admin_pending == player_a_pending
    assert player_b_pending == {
        "schema_version": "decision-request-view-v1",
        "request_id": HIDDEN_REQUEST_ID,
        "decision_type": "hidden_decision",
        "actor_id": None,
        "payload": {"secret": True, "hidden": True},
        "options": [],
        "is_parameterized": False,
    }
    assert _object(player_a, "projection")["viewer_role"] == "player"
    assert _object(coach, "projection")["viewer_role"] == "coach"
    assert _object(administrator, "projection")["viewer_role"] == "administrator"
    assert _object(spectator, "projection")["viewer_role"] == "delayed_spectator"


def test_phase18h_enforces_mutation_replay_support_and_viewer_claim_policies() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18h-role-permissions")
    player_lifecycle = _command_response(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        command_id="phase18h-player-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    assert player_lifecycle.status_code == 403
    assert _error_code(player_lifecycle) == "access_denied"

    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18h-admin-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    coach_view = _projection(server, session_id=session_id, token=DEV_COACH_A_TOKEN)
    pending = _object(_object(coach_view, "projection"), "pending_decision")
    coach_decision = _command_response(
        server,
        session_id=session_id,
        token=DEV_COACH_A_TOKEN,
        command_id="phase18h-coach-decision",
        expected_revision=1,
        submission_kind="finite_option",
        request_id=_string(pending, "request_id"),
        result_id="phase18h-coach-result",
        option_id=_string(_object(_list(pending, "options")[0]), "option_id"),
    )
    spectator_decision = _command_response(
        server,
        session_id=session_id,
        token=DEV_SPECTATOR_TOKEN,
        command_id="phase18h-spectator-decision",
        expected_revision=1,
        submission_kind="finite_option",
        request_id=_string(pending, "request_id"),
        result_id="phase18h-spectator-result",
        option_id=_string(_object(_list(pending, "options")[0]), "option_id"),
    )
    assert coach_decision.status_code == 403
    assert spectator_decision.status_code == 403
    assert coach_decision.payload == spectator_decision.payload
    assert _error_code(coach_decision) == "access_denied"

    spectator_support = _request(
        server,
        method="GET",
        path=f"/games/{session_id.removeprefix('session-')}/support-profile",
        token=DEV_SPECTATOR_TOKEN,
    )
    replay_projection = _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/projection",
        token=DEV_REPLAY_TOKEN,
    )
    replay_metadata = _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}",
        token=DEV_REPLAY_TOKEN,
    )
    assert spectator_support.status_code == 403
    assert replay_projection.status_code == 403
    assert replay_metadata.status_code == 403
    assert spectator_support.payload == replay_projection.payload
    assert replay_metadata.payload == replay_projection.payload
    active_replays = (
        _request(
            server,
            method="GET",
            path=f"/sessions/{session_id}/replay",
            token=DEV_REPLAY_TOKEN,
        ),
        _request(
            server,
            method="GET",
            path=f"/games/{session_id.removeprefix('session-')}/replay",
            token=DEV_REPLAY_TOKEN,
        ),
    )
    assert all(response.status_code == 403 for response in active_replays)
    assert all(response.payload == replay_projection.payload for response in active_replays)
    assert (
        _request(
            server,
            method="GET",
            path=f"/sessions/{session_id}/catalog",
            token=DEV_REPLAY_TOKEN,
        ).status_code
        == 200
    )

    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18h-admin-close",
        expected_revision=1,
        submission_kind="close_session",
    )
    assert (
        _request(
            server,
            method="GET",
            path=f"/sessions/{session_id}/replay",
            token=DEV_REPLAY_TOKEN,
        ).status_code
        == 200
    )

    wrong_viewer_claim = _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/projection",
        token=DEV_PLAYER_A_TOKEN,
        query={"viewer_player_id": PLAYER_B},
    )
    assert wrong_viewer_claim.status_code == 403
    assert _error_code(wrong_viewer_claim) == "access_denied"


def test_phase18h_auth_failures_share_one_redacted_shape_and_ignore_legacy_header() -> None:
    server = AdapterGameServer()
    other_server = AdapterGameServer()
    assert len(server.cursor_codec.secret) == 32
    assert server.cursor_codec.secret != other_server.cursor_codec.secret
    session_id = _create_session(server, game_id="phase18h-auth-shape")
    missing = server.handle(method="GET", path=f"/sessions/{session_id}/projection")
    invalid_responses = (
        server.handle(
            method="GET",
            path=f"/sessions/{session_id}/projection",
            authorization=bearer_authorization("invalid-token"),
        ),
        server.handle(
            method="GET",
            path=f"/sessions/{session_id}/projection",
            authorization="Basic invalid-token",
        ),
        server.handle(
            method="GET",
            path=f"/sessions/{session_id}/projection",
            authorization="Bearer ",
        ),
        server.handle(
            method="GET",
            path=f"/sessions/{session_id}/projection",
            authorization=f"Bearer {'x' * 257}",
        ),
    )
    assert missing.status_code == 401
    assert all(response.status_code == 401 for response in invalid_responses)
    assert all(response.payload == missing.payload for response in invalid_responses)
    serialized = json.dumps(missing.payload, sort_keys=True)
    for forbidden in (
        session_id,
        PLAYER_A,
        PLAYER_B,
        "decision-request",
        "source_id",
        "support",
        "terminal_reason",
    ):
        assert forbidden not in serialized

    client_bindings = _session_create_body(game_id="phase18h-client-bindings")
    client_bindings["participant_assignments"] = []
    rejected = _request(
        server,
        method="POST",
        path="/sessions",
        token=DEV_ADMIN_TOKEN,
        body=client_bindings,
    )
    assert rejected.status_code == 400
    assert _error_code(rejected) == "malformed_payload"


def test_phase18h_event_redaction_hides_secret_counts_and_uses_viewer_sequences() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18h-event-redaction")
    player_a_cursor = _string(
        _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN),
        "event_cursor",
    )
    player_b_cursor = _string(
        _projection(server, session_id=session_id, token=DEV_PLAYER_B_TOKEN),
        "event_cursor",
    )
    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18h-redaction-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    player_a_delta = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=player_a_cursor,
    )
    player_b_delta = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_B_TOKEN,
        cursor=player_b_cursor,
    )
    player_a_events = [_object(value) for value in _list(player_a_delta, "events")]
    player_b_events = [_object(value) for value in _list(player_b_delta, "events")]
    player_a_initial_sequence = server.cursor_codec.decode(player_a_cursor).visible_sequence
    player_b_initial_sequence = server.cursor_codec.decode(player_b_cursor).visible_sequence
    assert [_integer(value, "sequence_number") for value in player_a_events] == list(
        range(player_a_initial_sequence + 1, player_a_initial_sequence + len(player_a_events) + 1)
    )
    assert [_integer(value, "sequence_number") for value in player_b_events] == list(
        range(player_b_initial_sequence + 1, player_b_initial_sequence + len(player_b_events) + 1)
    )
    assert len(player_a_events) == len(player_b_events) + 1

    visible_request = next(
        event for event in player_a_events if event["event_type"] == "decision_requested"
    )
    visible_payload = _object(visible_request, "payload")
    assert _string(visible_payload, "request_id") != HIDDEN_REQUEST_ID
    assert all(event["event_type"] != "decision_requested" for event in player_b_events)
    serialized_opponent_delta = json.dumps(player_b_delta, sort_keys=True)
    assert HIDDEN_REQUEST_ID not in serialized_opponent_delta
    assert "hidden_event" not in serialized_opponent_delta
    assert "event_count" not in serialized_opponent_delta
    assert _string(player_a_delta, "next_cursor") != _string(
        player_b_delta,
        "next_cursor",
    )

    player_b_projection = _projection(
        server,
        session_id=session_id,
        token=DEV_PLAYER_B_TOKEN,
    )
    assert "event_count" not in _object(player_b_projection, "projection")
    opaque_cursor = _string(player_b_projection, "event_cursor")
    assert "." not in opaque_cursor
    assert session_id not in opaque_cursor
    decoded_token = base64.urlsafe_b64decode(opaque_cursor)
    try:
        decoded_text = decoded_token.decode("utf-8")
    except UnicodeDecodeError:
        decoded_json = None
    else:
        try:
            decoded_json = json.loads(decoded_text)
        except json.JSONDecodeError:
            decoded_json = None
    assert decoded_json is None


def test_phase18h_role_change_invalidates_existing_cursor_scope() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18h-role-change")
    cursor = _string(
        _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN),
        "event_cursor",
    )
    credentials = list(server.principal_registry.credentials)
    for index, credential in enumerate(credentials):
        if credential.token != DEV_PLAYER_A_TOKEN:
            continue
        credentials[index] = PrincipalCredential(
            token=credential.token,
            principal=AuthenticatedPrincipal(
                principal_id=credential.principal.principal_id,
                role=PrincipalRole.COACH,
                player_id=PLAYER_A,
            ),
        )
        break
    server.principal_registry = PrincipalRegistry(
        credentials=tuple(credentials),
        authorization_epoch=1,
    )

    delta = _events(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        cursor=cursor,
    )
    assert delta["resync_required"] is True
    assert delta["resync_reason"] == "wrong_viewer"


def test_phase18h_idempotent_retry_requires_exact_current_authorization_context() -> None:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18h-idempotent-auth-context")
    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18h-idempotent-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    projection = _projection(server, session_id=session_id, token=DEV_PLAYER_A_TOKEN)
    pending = _object(_object(projection, "projection"), "pending_decision")
    request_id = _string(pending, "request_id")
    result_id = "phase18h-idempotent-result"
    option_id = _string(_object(_list(pending, "options")[0]), "option_id")
    command_id = "phase18h-idempotent-player-command"
    accepted = _command_response(
        server,
        session_id=session_id,
        token=DEV_PLAYER_A_TOKEN,
        command_id=command_id,
        expected_revision=1,
        submission_kind="finite_option",
        request_id=request_id,
        result_id=result_id,
        option_id=option_id,
    )
    assert accepted.status_code == 200
    base_credentials = server.principal_registry.credentials
    original = next(
        credential for credential in base_credentials if credential.token == DEV_PLAYER_A_TOKEN
    ).principal
    reassigned_principals = (
        AuthenticatedPrincipal(
            principal_id=original.principal_id,
            role=PrincipalRole.COACH,
            player_id=PLAYER_A,
        ),
        AuthenticatedPrincipal(
            principal_id=original.principal_id,
            role=PrincipalRole.REPLAY_VIEWER,
        ),
        AuthenticatedPrincipal(
            principal_id=original.principal_id,
            role=PrincipalRole.PLAYER,
            player_id=PLAYER_B,
        ),
        original,
    )
    denied: list[ServerResponse] = []
    for epoch, reassigned in enumerate(reassigned_principals, start=1):
        server.principal_registry = _registry_replacing_principal(
            credentials=base_credentials,
            token=DEV_PLAYER_A_TOKEN,
            principal=reassigned,
            authorization_epoch=epoch,
        )
        denied.append(
            _command_response(
                server,
                session_id=session_id,
                token=DEV_PLAYER_A_TOKEN,
                command_id=command_id,
                expected_revision=1,
                submission_kind="finite_option",
                request_id=request_id,
                result_id=result_id,
                option_id=option_id,
            )
        )

    admin_server = AdapterGameServer()
    admin_session_id = _create_session(
        admin_server,
        game_id="phase18h-idempotent-admin-context",
    )
    admin_command_id = "phase18h-idempotent-admin-start"
    original_admin_response = _command_response(
        admin_server,
        session_id=admin_session_id,
        token=DEV_ADMIN_TOKEN,
        command_id=admin_command_id,
        expected_revision=0,
        submission_kind="start_session",
    )
    assert original_admin_response.status_code == 200
    admin_credentials = admin_server.principal_registry.credentials
    original_admin = next(
        credential for credential in admin_credentials if credential.token == DEV_ADMIN_TOKEN
    ).principal
    admin_server.principal_registry = _registry_replacing_principal(
        credentials=admin_credentials,
        token=DEV_ADMIN_TOKEN,
        principal=AuthenticatedPrincipal(
            principal_id=original_admin.principal_id,
            role=PrincipalRole.PLAYER,
            player_id=PLAYER_A,
        ),
        authorization_epoch=1,
    )
    denied.append(
        _command_response(
            admin_server,
            session_id=admin_session_id,
            token=DEV_ADMIN_TOKEN,
            command_id=admin_command_id,
            expected_revision=0,
            submission_kind="start_session",
        )
    )

    assert all(response.status_code == 403 for response in denied)
    assert all(response.payload == denied[0].payload for response in denied)
    assert _error_code(denied[0]) == "access_denied"
    serialized = json.dumps(denied[0].payload, sort_keys=True)
    assert command_id not in serialized
    assert request_id not in serialized
    assert PLAYER_A not in serialized


def _registry_replacing_principal(
    *,
    credentials: tuple[PrincipalCredential, ...],
    token: str,
    principal: AuthenticatedPrincipal,
    authorization_epoch: int,
) -> PrincipalRegistry:
    replaced = tuple(
        PrincipalCredential(token=credential.token, principal=principal)
        if credential.token == token
        else credential
        for credential in credentials
    )
    return PrincipalRegistry(
        credentials=replaced,
        authorization_epoch=authorization_epoch,
    )


def _create_session(server: AdapterGameServer, *, game_id: str) -> str:
    response = _request(
        server,
        method="POST",
        path="/sessions",
        token=DEV_ADMIN_TOKEN,
        body=_session_create_body(game_id=game_id),
    )
    assert response.status_code == 201, response.payload
    return _string(_object(response.payload), "session_id")


def _session_create_body(*, game_id: str) -> dict[str, JsonValue]:
    return {
        "schema_version": SESSION_CREATE_SCHEMA_VERSION,
        "config": cast(
            JsonValue,
            canonical_setup_prebattle_smoke_config(game_id=game_id).to_payload(),
        ),
    }


def _projection(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
) -> dict[str, JsonValue]:
    response = _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/projection",
        token=token,
    )
    assert response.status_code == 200, response.payload
    return _object(response.payload)


def _metadata(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
) -> dict[str, JsonValue]:
    response = _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}",
        token=token,
    )
    assert response.status_code == 200, response.payload
    return _object(response.payload)


def _events(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
    cursor: str,
    limit: int = 100,
) -> dict[str, JsonValue]:
    response = _request(
        server,
        method="GET",
        path=f"/sessions/{session_id}/events",
        token=token,
        query={"cursor": cursor, "limit": str(limit)},
    )
    assert response.status_code == 200, response.payload
    return _object(response.payload)


def _submit_lifecycle_command(
    server: AdapterGameServer,
    *,
    session_id: str,
    command_id: str,
    expected_revision: int,
    submission_kind: str,
) -> dict[str, JsonValue]:
    response = _command_response(
        server,
        session_id=session_id,
        token=DEV_ADMIN_TOKEN,
        command_id=command_id,
        expected_revision=expected_revision,
        submission_kind=submission_kind,
    )
    assert response.status_code == 200, response.payload
    return _object(response.payload)


def _command_response(
    server: AdapterGameServer,
    *,
    session_id: str,
    token: str,
    command_id: str,
    expected_revision: int,
    submission_kind: str,
    request_id: str | None = None,
    result_id: str | None = None,
    option_id: str | None = None,
) -> ServerResponse:
    submission: dict[str, JsonValue] = {"submission_kind": submission_kind}
    if option_id is not None:
        submission["option_id"] = option_id
    body: dict[str, JsonValue] = {
        "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
        "command_id": command_id,
        "session_id": session_id,
        "expected_session_revision": expected_revision,
        "request_id": request_id,
        "result_id": result_id,
        "submission": submission,
    }
    return _request(
        server,
        method="POST",
        path=f"/sessions/{session_id}/commands",
        token=token,
        body=body,
    )


def _request(
    server: AdapterGameServer,
    *,
    method: str,
    path: str,
    token: str,
    query: dict[str, str] | None = None,
    body: JsonValue = None,
) -> ServerResponse:
    return server.handle(
        method=method,
        path=path,
        query=query,
        body=body,
        authorization=bearer_authorization(token),
    )


def _error_code(response: ServerResponse) -> str:
    return _string(_object(_object(response.payload), "error"), "code")


def _object(value: JsonValue, key: str | None = None) -> dict[str, JsonValue]:
    target = value if key is None else _object(value)[key]
    assert isinstance(target, dict)
    return target


def _list(value: dict[str, JsonValue], key: str) -> list[JsonValue]:
    target = value[key]
    assert isinstance(target, list)
    return target


def _string(value: dict[str, JsonValue], key: str) -> str:
    target = value[key]
    assert type(target) is str
    return target


def _integer(value: dict[str, JsonValue], key: str) -> int:
    target = value[key]
    assert type(target) is int
    return target


def _validate_event_delta(payload: dict[str, JsonValue]) -> None:
    schema_path = REPO_ROOT / "contracts" / "schemas" / "event-delta.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = cast(_PayloadValidator, Draft202012Validator(schema))
    validator.validate(payload)
