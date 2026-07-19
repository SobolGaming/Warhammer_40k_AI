from __future__ import annotations

from datetime import UTC, datetime

from warhammer40k_core.adapters.access_control import (
    DEV_ADMIN_TOKEN,
    bearer_authorization,
)
from warhammer40k_core.adapters.external_contract import (
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.server import AdapterGameServer, ServerResponse
from warhammer40k_core.adapters.session_events import SessionCursorCodec
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


def phase18e_session_examples() -> dict[str, JsonValue]:
    config = canonical_setup_prebattle_smoke_config(game_id="phase18e-contract-session")
    create_payload: JsonValue = {
        "schema_version": SESSION_CREATE_SCHEMA_VERSION,
        "config": config.to_payload(),
    }
    timestamp = datetime(2026, 7, 18, 20, 0, tzinfo=UTC)
    server = AdapterGameServer(
        clock=lambda: timestamp,
        cursor_codec=SessionCursorCodec(secret=b"core-v2-local-dev-cursor-secret"),
    )
    created = _successful_payload(
        server.handle(
            method="POST",
            path="/sessions",
            body=create_payload,
            authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        ),
        expected_status=201,
    )
    session_id = _required_string(created, "session_id")
    start_envelope: JsonValue = {
        "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
        "command_id": "phase18g-contract-start-000001",
        "session_id": session_id,
        "expected_session_revision": 0,
        "request_id": None,
        "result_id": None,
        "submission": {"submission_kind": "start_session"},
    }
    started = _successful_payload(
        server.handle(
            method="POST",
            path=f"/sessions/{session_id}/commands",
            body=start_envelope,
            authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        ),
        expected_status=200,
    )
    command_envelope: JsonValue = {
        "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
        "command_id": "phase18f-contract-command-000001",
        "session_id": session_id,
        "expected_session_revision": 1,
        "request_id": None,
        "result_id": None,
        "submission": {"submission_kind": "close_session"},
    }
    command_outcome = _successful_payload(
        server.handle(
            method="POST",
            path=f"/sessions/{session_id}/commands",
            body=command_envelope,
            authorization=bearer_authorization(DEV_ADMIN_TOKEN),
        ),
        expected_status=200,
    )
    return {
        "session-create.json": create_payload,
        "session-metadata-created.json": created,
        "session-command-started.json": started,
        "session-command-envelope.json": command_envelope,
        "session-command-outcome.json": command_outcome,
    }


def _successful_payload(response: ServerResponse, *, expected_status: int) -> dict[str, JsonValue]:
    if response.status_code != expected_status:
        raise ValueError("Phase 18E contract session example request failed.")
    payload = validate_json_value(response.payload)
    if not isinstance(payload, dict):
        raise TypeError("Phase 18E contract session example must be an object.")
    return payload


def _required_string(payload: dict[str, JsonValue], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value:
        raise ValueError(f"Phase 18E contract session example requires {key}.")
    return value
