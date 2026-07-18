from __future__ import annotations

from datetime import UTC, datetime

from warhammer40k_core.adapters.external_contract import SESSION_CREATE_SCHEMA_VERSION
from warhammer40k_core.adapters.server import AdapterGameServer, ServerResponse
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value


def phase18e_session_examples() -> dict[str, JsonValue]:
    config = canonical_setup_prebattle_smoke_config(game_id="phase18e-contract-session")
    create_payload: JsonValue = {
        "schema_version": SESSION_CREATE_SCHEMA_VERSION,
        "config": config.to_payload(),
        "participant_assignments": [
            {
                "participant_id": "participant-a",
                "role": "player",
                "player_id": "player-a",
            },
            {
                "participant_id": "participant-b",
                "role": "player",
                "player_id": "player-b",
            },
            {
                "participant_id": "spectator-one",
                "role": "spectator",
                "player_id": None,
            },
            {
                "participant_id": "observer-one",
                "role": "observer",
                "player_id": None,
            },
        ],
    }
    timestamp = datetime(2026, 7, 18, 20, 0, tzinfo=UTC)
    server = AdapterGameServer(clock=lambda: timestamp)
    created = _successful_payload(
        server.handle(method="POST", path="/sessions", body=create_payload),
        expected_status=201,
    )
    session_id = _required_string(created, "session_id")
    started = _successful_payload(
        server.handle(
            method="POST",
            path=f"/sessions/{session_id}/start",
            query={"viewer_player_id": "player-a"},
        ),
        expected_status=200,
    )
    return {
        "session-create.json": create_payload,
        "session-metadata-created.json": created,
        "session-command-started.json": started,
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
