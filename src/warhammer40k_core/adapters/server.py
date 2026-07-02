from __future__ import annotations

import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import RLock
from types import TracebackType
from typing import ClassVar, Protocol, TypedDict, cast
from urllib.parse import parse_qs, urlparse

from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import (
    DecisionRequestViewPayload,
    RulesCatalogViewPayload,
)
from warhammer40k_core.adapters.redaction import (
    decision_request_hidden_from_viewer,
    redacted_decision_type_for_hidden_viewer,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.event_log import EventLogError, JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameConfigPayload
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifactError

type SessionFactory = Callable[[], AdapterGameSession]
type RulesCatalogProvider = Callable[[], RulesCatalogViewPayload]


class _Lock(Protocol):
    def __enter__(self) -> object: ...

    def __exit__(
        self,
        t: type[BaseException] | None,
        v: BaseException | None,
        tb: TracebackType | None,
    ) -> bool | None: ...


def _empty_session_registry() -> dict[str, AdapterGameSession]:
    return {}


def _server_lock() -> _Lock:
    return RLock()


class ServerErrorPayload(TypedDict):
    code: str
    message: str


class ServerLifecycleStatusPayload(TypedDict):
    stage: str
    status_kind: str
    message: str | None
    payload: JsonValue
    pending_request_id: str | None
    decision_type: str | None
    actor_id: str | None


class ServerGameStatusPayload(TypedDict):
    game_id: str
    status: ServerLifecycleStatusPayload


@dataclass(frozen=True, slots=True)
class ServerResponse:
    status_code: int
    payload: JsonValue

    def __post_init__(self) -> None:
        if type(self.status_code) is not int:
            raise ServerApiError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="invalid_server_response",
                message="ServerResponse status_code must be an integer.",
            )
        if self.status_code < 100 or self.status_code > 599:
            raise ServerApiError(
                status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                code="invalid_server_response",
                message="ServerResponse status_code must be an HTTP status code.",
            )
        validate_json_value(self.payload)


class ServerApiError(ValueError):
    status_code: HTTPStatus
    code: str

    def __init__(self, *, status_code: HTTPStatus, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = _validate_identifier("ServerApiError code", code)

    def to_response(self) -> ServerResponse:
        return ServerResponse(
            status_code=int(self.status_code),
            payload={
                "error": {
                    "code": self.code,
                    "message": str(self),
                }
            },
        )


def _default_rules_catalog_view() -> RulesCatalogViewPayload:
    session = LocalGameSession()
    session.start(canonical_setup_prebattle_smoke_config(game_id="rules-catalog-view"))
    return session.rules_catalog_view()


@dataclass(slots=True)
class AdapterGameServer:
    session_factory: SessionFactory = LocalGameSession
    rules_catalog_provider: RulesCatalogProvider = _default_rules_catalog_view
    _sessions: dict[str, AdapterGameSession] = field(
        default_factory=_empty_session_registry,
        init=False,
        repr=False,
    )
    _lock: _Lock = field(default_factory=_server_lock, init=False, repr=False)

    def handle(
        self,
        *,
        method: str,
        path: str,
        query: Mapping[str, str] | None = None,
        body: JsonValue = None,
    ) -> ServerResponse:
        # Phase 18E keeps the local dev server authoritative by serializing access to
        # the in-memory session registry. A production server can replace this with
        # an explicit session store or per-game actor loop.
        with self._lock:
            try:
                return self._handle(
                    method=_method(method),
                    path_segments=_path_segments(path),
                    query={} if query is None else query,
                    body=validate_json_value(body),
                )
            except ServerApiError as exc:
                return exc.to_response()
            except GameLifecycleError as exc:
                return _error_response(
                    status_code=HTTPStatus.CONFLICT,
                    code="session_contract_rejected",
                    message=str(exc),
                )
            except ReplayArtifactError as exc:
                return _error_response(
                    status_code=HTTPStatus.CONFLICT,
                    code="replay_export_rejected",
                    message=str(exc),
                )
            except EventLogError as exc:
                return _error_response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_payload",
                    message=str(exc),
                )

    def _handle(
        self,
        *,
        method: str,
        path_segments: tuple[str, ...],
        query: Mapping[str, str],
        body: JsonValue,
    ) -> ServerResponse:
        if method == "GET" and path_segments == ("rules-catalog",):
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, self.rules_catalog_provider())),
            )
        if method == "POST" and path_segments == ("games",):
            return self._create_game(body)
        if len(path_segments) < 2 or path_segments[0] != "games":
            raise _not_found()

        game_id = _validate_identifier("game_id", path_segments[1])
        session = self._session(game_id)
        if method == "POST" and path_segments == ("games", game_id, "advance"):
            return _status_response(
                game_id=game_id,
                status=session.advance_until_decision_or_terminal(),
                viewer_player_id=_optional_query_string(query, key="viewer_player_id"),
            )
        if method == "GET" and path_segments == ("games", game_id, "view"):
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(
                    cast(
                        JsonValue,
                        session.view(viewer_player_id=_query_string(query, key="viewer_player_id")),
                    )
                ),
            )
        if method == "GET" and path_segments == ("games", game_id, "events"):
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(
                    cast(
                        JsonValue,
                        session.events_since(
                            EventStreamCursor(_query_int(query, key="cursor")),
                            viewer_player_id=_query_string(query, key="viewer_player_id"),
                        ),
                    )
                ),
            )
        if method == "GET" and path_segments == ("games", game_id, "replay"):
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(
                    cast(
                        JsonValue,
                        session.replay_artifact(artifact_id=f"server-replay:{game_id}"),
                    )
                ),
            )
        if method == "GET" and path_segments == ("games", game_id, "support-profile"):
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, session.support_profile())),
            )
        if (
            method == "POST"
            and len(path_segments) == 5
            and path_segments[:3] == ("games", game_id, "decisions")
            and path_segments[4] == "option"
        ):
            return self._submit_option(
                game_id=game_id,
                session=session,
                request_id=_validate_identifier("request_id", path_segments[3]),
                body=body,
            )
        if (
            method == "POST"
            and len(path_segments) == 5
            and path_segments[:3] == ("games", game_id, "decisions")
            and path_segments[4] == "payload"
        ):
            return self._submit_parameterized_payload(
                game_id=game_id,
                session=session,
                request_id=_validate_identifier("request_id", path_segments[3]),
                body=body,
            )
        raise _not_found()

    def _create_game(self, body: JsonValue) -> ServerResponse:
        payload = _json_object("POST /games body", body)
        _require_exact_keys(payload, keys=frozenset({"config"}))
        config = GameConfig.from_payload(cast(GameConfigPayload, payload["config"]))
        if config.game_id in self._sessions:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="game_already_exists",
                message="Game already exists.",
            )
        session = self.session_factory()
        status = session.start(config)
        self._sessions[config.game_id] = session
        return _status_response(
            game_id=config.game_id,
            status=status,
            status_code=HTTPStatus.CREATED,
            viewer_player_id=None,
        )

    def _submit_option(
        self,
        *,
        game_id: str,
        session: AdapterGameSession,
        request_id: str,
        body: JsonValue,
    ) -> ServerResponse:
        payload = _json_object("finite option submission body", body)
        _require_exact_keys(payload, keys=frozenset({"actor_id", "option_id", "result_id"}))
        actor_id = _required_string(payload, key="actor_id")
        option_id = _required_string(payload, key="option_id")
        pending = _pending_decision_for_submission(
            session=session,
            request_id=request_id,
            actor_id=actor_id,
        )
        if not any(option["option_id"] == option_id for option in pending["options"]):
            raise ServerApiError(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="wrong_selected_option",
                message="Selected option is not one of the pending engine-emitted options.",
            )
        status = session.submit_option(
            request_id=request_id,
            option_id=option_id,
            result_id=_required_string(payload, key="result_id"),
        )
        return _status_response(game_id=game_id, status=status, viewer_player_id=actor_id)

    def _submit_parameterized_payload(
        self,
        *,
        game_id: str,
        session: AdapterGameSession,
        request_id: str,
        body: JsonValue,
    ) -> ServerResponse:
        payload = _json_object("parameterized submission body", body)
        _require_exact_keys(payload, keys=frozenset({"actor_id", "payload", "result_id"}))
        actor_id = _required_string(payload, key="actor_id")
        submitted_payload = validate_json_value(payload["payload"])
        _reject_raw_dice_payload(submitted_payload)
        pending = _pending_decision_for_submission(
            session=session,
            request_id=request_id,
            actor_id=actor_id,
        )
        if pending["is_parameterized"] is not True:
            raise ServerApiError(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="request_is_not_parameterized",
                message="Pending request does not accept a parameterized payload.",
            )
        status = session.submit_parameterized_payload(
            request_id=request_id,
            payload=submitted_payload,
            result_id=_required_string(payload, key="result_id"),
        )
        status_code = (
            HTTPStatus.UNPROCESSABLE_ENTITY
            if status.status_kind is LifecycleStatusKind.INVALID
            else HTTPStatus.OK
        )
        return _status_response(
            game_id=game_id,
            status=status,
            status_code=status_code,
            viewer_player_id=actor_id,
        )

    def _session(self, game_id: str) -> AdapterGameSession:
        session = self._sessions.get(game_id)
        if session is None:
            raise ServerApiError(
                status_code=HTTPStatus.NOT_FOUND,
                code="game_not_found",
                message="Game was not found.",
            )
        return session


def create_local_dev_http_server(
    *,
    host: str = "127.0.0.1",
    port: int = 0,
    api: AdapterGameServer | None = None,
) -> ThreadingHTTPServer:
    if api is not None and type(api) is not AdapterGameServer:
        raise ServerApiError(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="invalid_server_api",
            message="Local dev HTTP server requires AdapterGameServer.",
        )
    handler = _handler_for_api(AdapterGameServer() if api is None else api)
    return ThreadingHTTPServer((host, port), handler)


def _handler_for_api(api: AdapterGameServer) -> type[BaseHTTPRequestHandler]:
    class AdapterGameRequestHandler(BaseHTTPRequestHandler):
        server_version = "COREV2AdapterGameHTTP/0.1"
        _api: ClassVar[AdapterGameServer] = api

        def do_GET(self) -> None:
            self._send_api_response(body=None)

        def do_POST(self) -> None:
            try:
                body = self._read_json_body()
            except ServerApiError as exc:
                self._write_response(exc.to_response())
                return
            self._send_api_response(body=body)

        def _send_api_response(self, *, body: JsonValue) -> None:
            parsed = urlparse(self.path)
            try:
                query = _single_value_query(parsed.query)
            except ServerApiError as exc:
                self._write_response(exc.to_response())
                return
            response = self._api.handle(
                method=self.command,
                path=parsed.path,
                query=query,
                body=body,
            )
            self._write_response(response)

        def _write_response(self, response: ServerResponse) -> None:
            encoded = json.dumps(response.payload, sort_keys=True).encode("utf-8")
            self.send_response(response.status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)

        def _read_json_body(self) -> JsonValue:
            length_header = self.headers.get("Content-Length")
            if length_header is None:
                return None
            length = _parse_content_length(length_header)
            if length == 0:
                return None
            raw_body = self.rfile.read(length)
            try:
                decoded = raw_body.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise ServerApiError(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_body",
                    message="Request body must be UTF-8 JSON.",
                ) from exc
            try:
                return validate_json_value(json.loads(decoded))
            except json.JSONDecodeError as exc:
                raise ServerApiError(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_body",
                    message="Request body must be valid JSON.",
                ) from exc

    return AdapterGameRequestHandler


def _pending_decision_for_submission(
    *,
    session: AdapterGameSession,
    request_id: str,
    actor_id: str,
) -> DecisionRequestViewPayload:
    view = session.view(viewer_player_id=actor_id)
    pending = view["pending_decision"]
    if pending is None:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="closed_or_terminal_session",
            message="Session has no pending decision to submit.",
        )
    if pending["request_id"] != request_id:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="stale_request_id",
            message="Submitted request_id does not match the pending request.",
        )
    if pending["actor_id"] != actor_id:
        raise ServerApiError(
            status_code=HTTPStatus.FORBIDDEN,
            code="wrong_actor",
            message="Submitted actor does not own the pending request.",
        )
    return pending


def _status_response(
    *,
    game_id: str,
    status: LifecycleStatus,
    viewer_player_id: str | None,
    status_code: HTTPStatus = HTTPStatus.OK,
) -> ServerResponse:
    payload: ServerGameStatusPayload = {
        "game_id": game_id,
        "status": _status_summary(status, viewer_player_id=viewer_player_id),
    }
    return ServerResponse(
        status_code=int(status_code),
        payload=validate_json_value(cast(JsonValue, payload)),
    )


def _status_summary(
    status: LifecycleStatus,
    *,
    viewer_player_id: str | None,
) -> ServerLifecycleStatusPayload:
    decision_request = status.decision_request
    hidden_pending = (
        False
        if decision_request is None
        else decision_request_hidden_from_viewer(
            request=decision_request,
            viewer_player_id=viewer_player_id,
        )
    )
    metadata_payload = (
        status.payload
        if status.status_kind
        in {
            LifecycleStatusKind.TERMINAL,
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
        else None
    )
    return {
        "stage": status.stage.value,
        "status_kind": status.status_kind.value,
        "message": status.message,
        "payload": metadata_payload,
        "pending_request_id": (
            None if decision_request is None or hidden_pending else decision_request.request_id
        ),
        "decision_type": (
            None
            if decision_request is None
            else redacted_decision_type_for_hidden_viewer()
            if hidden_pending
            else decision_request.decision_type
        ),
        "actor_id": (
            None if decision_request is None or hidden_pending else decision_request.actor_id
        ),
    }


def _error_response(*, status_code: HTTPStatus, code: str, message: str) -> ServerResponse:
    payload: dict[str, ServerErrorPayload] = {
        "error": {
            "code": _validate_identifier("error code", code),
            "message": _validate_identifier("error message", message),
        }
    }
    return ServerResponse(
        status_code=int(status_code),
        payload=validate_json_value(cast(JsonValue, payload)),
    )


def _not_found() -> ServerApiError:
    return ServerApiError(
        status_code=HTTPStatus.NOT_FOUND,
        code="route_not_found",
        message="Route was not found.",
    )


def _method(method: object) -> str:
    value = _validate_identifier("HTTP method", method)
    normalized = value.upper()
    if normalized not in {"GET", "POST"}:
        raise ServerApiError(
            status_code=HTTPStatus.METHOD_NOT_ALLOWED,
            code="method_not_allowed",
            message="HTTP method is not supported by the adapter game server.",
        )
    return normalized


def _path_segments(path: object) -> tuple[str, ...]:
    value = _validate_identifier("HTTP path", path)
    return tuple(segment for segment in value.strip("/").split("/") if segment)


def _single_value_query(query: str) -> dict[str, str]:
    parsed = parse_qs(query, keep_blank_values=True)
    values: dict[str, str] = {}
    for key, items in parsed.items():
        if len(items) != 1:
            raise ServerApiError(
                status_code=HTTPStatus.BAD_REQUEST,
                code="ambiguous_query_parameter",
                message="Query parameters must have a single value.",
            )
        values[key] = items[0]
    return values


def _query_string(query: Mapping[str, str], *, key: str) -> str:
    if key not in query:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="missing_query_parameter",
            message=f"Missing required query parameter: {key}.",
        )
    return _validate_identifier(key, query[key])


def _optional_query_string(query: Mapping[str, str], *, key: str) -> str | None:
    if key not in query:
        return None
    return _validate_identifier(key, query[key])


def _query_int(query: Mapping[str, str], *, key: str) -> int:
    raw = _query_string(query, key=key)
    if not raw.isdecimal():
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="invalid_query_parameter",
            message=f"Query parameter must be a non-negative integer: {key}.",
        )
    return int(raw)


def _json_object(field_name: str, value: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(value, dict):
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="malformed_payload",
            message=f"{field_name} must be an object.",
        )
    return value


def _require_exact_keys(payload: dict[str, JsonValue], *, keys: frozenset[str]) -> None:
    actual_keys = frozenset(payload)
    if actual_keys == keys:
        return
    raise ServerApiError(
        status_code=HTTPStatus.BAD_REQUEST,
        code="malformed_payload",
        message="Payload keys do not match the route contract.",
    )


def _required_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="malformed_payload",
            message=f"Payload missing required key: {key}.",
        )
    return _validate_identifier(key, payload[key])


def _malformed_identifier_error(message: str) -> ServerApiError:
    return ServerApiError(
        status_code=HTTPStatus.BAD_REQUEST,
        code="malformed_identifier",
        message=message,
    )


_validate_identifier = IdentifierValidator(_malformed_identifier_error)


def _parse_content_length(value: str) -> int:
    stripped = value.strip()
    if not stripped.isdecimal():
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="invalid_content_length",
            message="Content-Length must be a non-negative integer.",
        )
    return int(stripped)


def _reject_raw_dice_payload(value: JsonValue) -> None:
    if isinstance(value, list):
        for item in value:
            _reject_raw_dice_payload(item)
        return
    if not isinstance(value, dict):
        return
    keys = frozenset(value)
    if {"roll_id", "spec", "values", "total", "source"} <= keys:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="client_raw_dice_rejected",
            message="Server decision routes do not accept raw dice roll result payloads.",
        )
    if {"source_d6_value", "source_d6_result", "replacement_result", "injected_results"} & keys:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="client_raw_dice_rejected",
            message="Server decision routes do not accept raw dice values from clients.",
        )
    for item in value.values():
        _reject_raw_dice_payload(item)
