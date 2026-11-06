"""Matched native player projection, command, retention and server restore costs.

The fixed config is public test data, not secret competitive entropy. Both runtime
arms decode its identical bytes with their own GameConfig.from_payload. This is
a component measurement; retained-cursor outcomes are recorded without claiming
the baseline implements the head's privacy guarantees.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import TYPE_CHECKING, cast

from scripts.measure_order63 import _host_inventory, _select_runtime_src

if TYPE_CHECKING:
    from warhammer40k_core.adapters.server import AdapterGameServer, ServerResponse
    from warhammer40k_core.engine.event_log import JsonValue

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests/support/fixtures/player_boundary_config.json"
WORKLOAD_ID = "native-player-boundary-v1"
CASES = (
    "projection",
    "visible_events",
    "metadata",
    "finite_command",
    "server_restore",
    "retained_cursor",
)
FROZEN_TIME = datetime(2026, 11, 6, 12, tzinfo=UTC)


def _object(value: JsonValue) -> dict[str, JsonValue]:
    assert isinstance(value, dict), value
    return value


def _string(value: JsonValue) -> str:
    assert isinstance(value, str), value
    return value


def _integer(value: JsonValue) -> int:
    assert type(value) is int, value
    return value


def _request(
    server: AdapterGameServer,
    *,
    method: str,
    path: str,
    token: str,
    body: JsonValue = None,
    query: dict[str, str] | None = None,
) -> ServerResponse:
    return server.handle(
        method=method, path=path, authorization=f"Bearer {token}", body=body, query=query
    )


def _ok(response: ServerResponse, *, status: int = 200) -> dict[str, JsonValue]:
    assert response.status_code == status, response.payload
    return _object(response.payload)


def _command(
    server: AdapterGameServer,
    session_id: str,
    *,
    token: str,
    command_id: str,
    submission_kind: str,
    pending: dict[str, JsonValue] | None = None,
    option_id: str | None = None,
) -> dict[str, JsonValue]:
    from warhammer40k_core.adapters.external_contract import SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION

    metadata = _ok(_request(server, method="GET", path=f"/sessions/{session_id}", token=token))
    submission: dict[str, JsonValue] = {"submission_kind": submission_kind}
    if option_id is not None:
        submission["option_id"] = option_id
    return {
        "schema_version": SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
        "session_id": session_id,
        "command_id": command_id,
        "expected_session_revision": _integer(metadata["session_revision"]),
        "request_id": None if pending is None else _string(pending["request_id"]),
        "result_id": None if pending is None else f"{command_id}:result",
        "submission": submission,
    }


def _projection(server: AdapterGameServer, session_id: str, token: str) -> ServerResponse:
    return _request(server, method="GET", path=f"/sessions/{session_id}/projection", token=token)


def _pending(projection: dict[str, JsonValue], *, actor: str, kind: str) -> dict[str, JsonValue]:
    pending = _object(_object(projection["projection"])["pending_decision"])
    assert pending["actor_id"] == actor, pending
    assert pending["decision_type"] == kind, pending
    return pending


def _option(pending: dict[str, JsonValue], expected: dict[str, JsonValue]) -> str:
    options = pending["options"]
    assert isinstance(options, list), options
    matches = [
        _string(option["option_id"])
        for value in options
        if isinstance(value, dict)
        for option in [value]
        if isinstance(option["payload"], dict)
        and all(option["payload"].get(key) == value for key, value in expected.items())
    ]
    assert len(matches) == 1, (expected, options)
    return matches[0]


def _prepare(config_bytes: bytes) -> tuple[AdapterGameServer, str]:
    from warhammer40k_core.adapters.access_control import (
        DEV_ADMIN_TOKEN,
        DEV_PLAYER_A_TOKEN,
        DEV_PLAYER_B_TOKEN,
    )
    from warhammer40k_core.adapters.external_contract import SESSION_CREATE_SCHEMA_VERSION
    from warhammer40k_core.adapters.server import AdapterGameServer
    from warhammer40k_core.engine.event_log import validate_json_value
    from warhammer40k_core.engine.game_state import GameConfig, GameConfigPayload

    config = GameConfig.from_payload(cast(GameConfigPayload, json.loads(config_bytes)))
    server = AdapterGameServer(clock=lambda: FROZEN_TIME)
    created = _ok(
        _request(
            server,
            method="POST",
            path="/sessions",
            token=DEV_ADMIN_TOKEN,
            body={
                "schema_version": SESSION_CREATE_SCHEMA_VERSION,
                "config": validate_json_value(config.to_payload()),
            },
        ),
        status=201,
    )
    session_id = _string(created["session_id"])
    # Operator retention configuration precedes start; no engine choice is bypassed.
    server._sessions[session_id].revision_retention_limit = 2  # pyright: ignore[reportPrivateUsage]
    start = _command(
        server,
        session_id,
        token=DEV_ADMIN_TOKEN,
        command_id="start",
        submission_kind="start_session",
    )
    assert (
        _ok(
            _request(
                server,
                method="POST",
                path=f"/sessions/{session_id}/commands",
                token=DEV_ADMIN_TOKEN,
                body=start,
            )
        )["accepted"]
        is True
    )
    for actor, token in (("player-a", DEV_PLAYER_A_TOKEN), ("player-b", DEV_PLAYER_B_TOKEN)):
        projection = _ok(_projection(server, session_id, token))
        pending = _pending(projection, actor=actor, kind="select_secondary_missions")
        envelope = _command(
            server,
            session_id,
            token=token,
            command_id=f"fixed:{actor}",
            submission_kind="finite_option",
            pending=pending,
            option_id=_option(
                pending, {"mode": "fixed", "fixed_mission_ids": ["assassination", "bring_it_down"]}
            ),
        )
        result = _ok(
            _request(
                server,
                method="POST",
                path=f"/sessions/{session_id}/commands",
                token=token,
                body=envelope,
            )
        )
        assert result["accepted"] is True, result
    _pending(
        _ok(_projection(server, session_id, DEV_PLAYER_A_TOKEN)),
        actor="player-a",
        kind="select_reserve_declaration",
    )
    return server, session_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-src", type=Path, default=ROOT / "src")
    parser.add_argument("--revision", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    _select_runtime_src(args.runtime_src)
    from warhammer40k_core.adapters.access_control import DEV_PLAYER_A_TOKEN, DEV_PLAYER_B_TOKEN
    from warhammer40k_core.adapters.event_stream import EventStreamCursor
    from warhammer40k_core.adapters.local_session import LocalGameSession
    from warhammer40k_core.adapters.session_recovery import (
        recover_server_persistence_payload,
        server_persistence_payload,
    )
    from warhammer40k_core.build_identity import verified_engine_build_identity
    from warhammer40k_core.engine.event_log import canonical_json

    times: dict[str, list[float]] = {case: [] for case in CASES}
    outcomes: dict[str, list[dict[str, JsonValue]]] = {case: [] for case in CASES}
    config_bytes = FIXTURE.read_bytes()
    for sample in range(7):
        server, session_id = _prepare(config_bytes)
        record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
        started = perf_counter()
        response = _projection(server, session_id, DEV_PLAYER_B_TOKEN)
        times["projection"].append(perf_counter() - started)
        projection = _ok(response)
        retained_cursor = _string(projection["event_cursor"])
        outcomes["projection"].append({"status_code": response.status_code})

        started = perf_counter()
        events = record.adapter_session.events_since(
            EventStreamCursor(), viewer_player_id="player-b"
        )
        times["visible_events"].append(perf_counter() - started)
        assert events["viewer_player_id"] == "player-b"
        assert events["events"], events
        outcomes["visible_events"].append(
            {"event_count": len(events["events"]), "next_cursor": events["next_cursor"]}
        )

        started = perf_counter()
        response = _request(
            server, method="GET", path=f"/sessions/{session_id}", token=DEV_PLAYER_B_TOKEN
        )
        times["metadata"].append(perf_counter() - started)
        _ok(response)
        outcomes["metadata"].append({"status_code": response.status_code})

        pending = _pending(
            _ok(_projection(server, session_id, DEV_PLAYER_A_TOKEN)),
            actor="player-a",
            kind="select_reserve_declaration",
        )
        envelope = _command(
            server,
            session_id,
            token=DEV_PLAYER_A_TOKEN,
            command_id="private:deep-strike",
            submission_kind="finite_option",
            pending=pending,
            option_id=_option(
                pending,
                {"unit_instance_id": "army-alpha:deep-strike-unit", "reserve_kind": "deep_strike"},
            ),
        )
        started = perf_counter()
        response = _request(
            server,
            method="POST",
            path=f"/sessions/{session_id}/commands",
            token=DEV_PLAYER_A_TOKEN,
            body=envelope,
        )
        times["finite_command"].append(perf_counter() - started)
        assert _ok(response)["accepted"] is True, response.payload
        record = server._sessions[session_id]  # pyright: ignore[reportPrivateUsage]
        assert record.revision_retention_limit == 2
        assert max(record.revision_snapshots) == record.session_revision
        assert len(record.revision_snapshots) < record.session_revision + 1
        outcomes["finite_command"].append(
            {
                "status_code": 200,
                "accepted": True,
                "retained_snapshots": len(record.revision_snapshots),
                "authoritative_revision": record.session_revision,
            }
        )

        saved = server.persistence_payload()
        started = perf_counter()
        restored = recover_server_persistence_payload(
            saved,
            principal_registry=server.principal_registry,
            session_recovery_factory=LocalGameSession.from_persistence_payload,
        )
        times["server_restore"].append(perf_counter() - started)
        restored_payload = server_persistence_payload(
            sessions=restored.sessions,
            session_id_by_game_id=restored.session_id_by_game_id,
            cursor_codec=restored.cursor_codec,
            principal_registry=server.principal_registry,
            event_retention_limit=restored.event_retention_limit,
        )
        assert canonical_json(restored_payload) == canonical_json(saved)
        outcomes["server_restore"].append({"exact_round_trip": True})

        started = perf_counter()
        response = _request(
            server,
            method="GET",
            path=f"/sessions/{session_id}/events",
            token=DEV_PLAYER_B_TOKEN,
            query={"cursor": retained_cursor},
        )
        times["retained_cursor"].append(perf_counter() - started)
        retained = _ok(response)
        outcomes["retained_cursor"].append(
            {
                "status_code": 200,
                "resync_required": retained["resync_required"],
                "resync_reason": retained["resync_reason"],
            }
        )
        print(f"Completed player-boundary sample {sample + 1}/7", flush=True)
    cpu, memory = _host_inventory()
    report = {
        "workload_id": WORKLOAD_ID,
        "revision": args.revision,
        "runtime_build_id": verified_engine_build_identity().build_id,
        "fixture_sha256": hashlib.sha256(config_bytes).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "cpu": cpu,
        "memory_bytes": memory,
        "cpu_allocation": os.cpu_count(),
        "platform": platform.platform(),
        "python": platform.python_version(),
        "concurrency": 1,
        "coverage": False,
        "completed": True,
        "full_game_certified": False,
        "timing_boundary": "Native operation only; preparation and verification excluded.",
        "visible_events_scope": "Native events_since from zero for player-b; nonempty records.",
        "rows": [
            {
                "case": case,
                "samples_seconds": times[case],
                "operations": 1,
                "native_outcomes": outcomes[case],
            }
            for case in CASES
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
