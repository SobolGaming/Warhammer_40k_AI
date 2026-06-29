from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from export_ui_contract_fixtures import (
    PLAYER_A,
    PLAYER_B,
    build_local_session_at_movement_request,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8766
ROUTES = (
    "/",
    "/health",
    "/rules-catalog",
    "/view/player-a",
    "/view/player-b",
    "/decision-request/player-a",
    "/decision-request/player-b",
    "/events/player-a?cursor=0",
    "/events/player-b?cursor=0",
)


@dataclass(frozen=True, slots=True)
class LocalSessionDevState:
    session: LocalGameSession
    game_id: str


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Serve a read-only LocalGameSession fixture for UI contract development.",
    )
    parser.add_argument("--host", default=DEFAULT_HOST)
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--game-id", default="ui-contract-dev-server")
    parser.add_argument(
        "--dump-routes",
        action="store_true",
        help="Print route metadata and exit without starting the server.",
    )
    args = parser.parse_args(argv)

    state = _build_dev_state(game_id=args.game_id)
    if args.dump_routes:
        print(json.dumps(_route_index(state), indent=2, sort_keys=True))
        return 0

    handler = _handler_for(state=state)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(f"Serving LocalGameSession UI contract harness at http://{args.host}:{args.port}/")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped LocalGameSession UI contract harness.")
    finally:
        server.server_close()
    return 0


def _build_dev_state(*, game_id: str) -> LocalSessionDevState:
    session, _status = build_local_session_at_movement_request(game_id=game_id)
    return LocalSessionDevState(session=session, game_id=game_id)


def _handler_for(*, state: LocalSessionDevState) -> type[BaseHTTPRequestHandler]:
    class LocalSessionDevHandler(BaseHTTPRequestHandler):
        dev_state: ClassVar[LocalSessionDevState] = state

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/":
                self._send_json(_route_index(self.dev_state))
                return
            if parsed.path == "/health":
                self._send_json({"status": "ok", "game_id": self.dev_state.game_id})
                return
            if parsed.path == "/rules-catalog":
                self._send_json(self.dev_state.session.rules_catalog_view())
                return
            if parsed.path == "/view/player-a":
                self._send_json(self.dev_state.session.view(viewer_player_id=PLAYER_A))
                return
            if parsed.path == "/view/player-b":
                self._send_json(self.dev_state.session.view(viewer_player_id=PLAYER_B))
                return
            if parsed.path == "/decision-request/player-a":
                self._send_json(
                    self.dev_state.session.view(viewer_player_id=PLAYER_A)["pending_decision"]
                )
                return
            if parsed.path == "/decision-request/player-b":
                self._send_json(
                    self.dev_state.session.view(viewer_player_id=PLAYER_B)["pending_decision"]
                )
                return
            if parsed.path == "/events/player-a":
                self._send_events(query=parsed.query, viewer_player_id=PLAYER_A)
                return
            if parsed.path == "/events/player-b":
                self._send_events(query=parsed.query, viewer_player_id=PLAYER_B)
                return
            self.send_error(HTTPStatus.NOT_FOUND, "Unknown UI contract dev server route.")

        def _send_events(self, *, query: str, viewer_player_id: str) -> None:
            try:
                cursor = _cursor_from_query(query)
            except ValueError as exc:
                self.send_error(HTTPStatus.BAD_REQUEST, str(exc))
                return
            self._send_json(
                self.dev_state.session.events_since(
                    EventStreamCursor(cursor),
                    viewer_player_id=viewer_player_id,
                )
            )

        def _send_json(self, payload: JsonValue) -> None:
            encoded = (
                json.dumps(validate_json_value(payload), indent=2, sort_keys=True) + "\n"
            ).encode("utf-8")
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

    return LocalSessionDevHandler


def _cursor_from_query(query: str) -> int:
    values = parse_qs(query).get("cursor", ["0"])
    if len(values) != 1:
        raise ValueError("cursor query parameter must appear at most once.")
    try:
        cursor = int(values[0])
    except ValueError as exc:
        raise ValueError("cursor query parameter must be an integer.") from exc
    if cursor < 0:
        raise ValueError("cursor query parameter must not be negative.")
    return cursor


def _route_index(state: LocalSessionDevState) -> dict[str, JsonValue]:
    return {
        "game_id": state.game_id,
        "routes": list(ROUTES),
        "viewer_player_ids": [PLAYER_A, PLAYER_B],
    }


if __name__ == "__main__":
    raise SystemExit(main())
