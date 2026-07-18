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
from warhammer40k_core.adapters.external_contract import (
    CREATE_SESSION_SCHEMA_NAME,
    CREATE_SESSION_SCHEMA_VERSION,
    ERROR_ENVELOPE_SCHEMA_VERSION,
    FINITE_SUBMISSION_SCHEMA_NAME,
    FINITE_SUBMISSION_SCHEMA_VERSION,
    LIFECYCLE_STATUS_SCHEMA_VERSION,
    PARAMETERIZED_SUBMISSION_SCHEMA_NAME,
    PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_NAME,
    SESSION_CREATE_SCHEMA_VERSION,
    ExternalContractValidationError,
    require_schema_version,
    validate_external_request_payload,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.projection import (
    DecisionRequestViewPayload,
    RulesCatalogViewPayload,
)
from warhammer40k_core.adapters.redaction import (
    decision_request_hidden_from_viewer,
    redacted_decision_type_for_hidden_viewer,
)
from warhammer40k_core.adapters.session_protocol import (
    AuthoritativeSession,
    OperationalClock,
    ParticipantAssignment,
    SessionCheckpointPayload,
    SessionProtocolError,
    default_participant_assignments,
    operational_timestamp,
    participant_assignments_from_payload,
    session_command_result_payload,
    utc_operational_clock,
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


def _empty_session_registry() -> dict[str, AuthoritativeSession]:
    return {}


def _empty_game_session_index() -> dict[str, str]:
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
    schema_version: str
    game_id: str
    status: ServerLifecycleStatusPayload


@dataclass(frozen=True, slots=True)
class _MutationOutcome:
    actor_id: str
    status: LifecycleStatus
    accepted: bool
    from_cursor: int


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
                "schema_version": ERROR_ENVELOPE_SCHEMA_VERSION,
                "error": {
                    "code": self.code,
                    "message": str(self),
                },
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
    clock: OperationalClock = utc_operational_clock
    _sessions: dict[str, AuthoritativeSession] = field(
        default_factory=_empty_session_registry,
        init=False,
        repr=False,
    )
    _session_id_by_game_id: dict[str, str] = field(
        default_factory=_empty_game_session_index,
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
            except GameLifecycleError:
                return _error_response(
                    status_code=HTTPStatus.CONFLICT,
                    code="session_contract_rejected",
                    message="Session operation was rejected.",
                )
            except ReplayArtifactError:
                return _error_response(
                    status_code=HTTPStatus.CONFLICT,
                    code="replay_export_rejected",
                    message="Replay export was rejected.",
                )
            except EventLogError:
                return _error_response(
                    status_code=HTTPStatus.BAD_REQUEST,
                    code="malformed_json_payload",
                    message="Event payload was rejected.",
                )
            except SessionProtocolError:
                return _error_response(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    code="session_protocol_failure",
                    message="Session protocol processing failed.",
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
        if method == "POST" and path_segments == ("sessions",):
            return self._create_protocol_session(body)
        if path_segments and path_segments[0] == "sessions":
            return self._handle_protocol_session(
                method=method,
                path_segments=path_segments,
                query=query,
                body=body,
            )
        if len(path_segments) < 2 or path_segments[0] != "games":
            raise _not_found()

        game_id = _validate_identifier("game_id", path_segments[1])
        record = self._session_record_for_game(game_id)
        session = record.adapter_session
        if method == "POST" and path_segments == ("games", game_id, "advance"):
            _ensure_session_open(record)
            status = session.advance_until_decision_or_terminal()
            record.started = True
            record.accept_status(status, timestamp=self._timestamp())
            return _status_response(
                game_id=game_id,
                status=status,
                viewer_player_id=_optional_query_string(query, key="viewer_player_id"),
            )
        if method == "GET" and path_segments == ("games", game_id, "view"):
            record.touch(self._timestamp())
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
            record.touch(self._timestamp())
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
            record.touch(self._timestamp())
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
            record.touch(self._timestamp())
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
                record=record,
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
                record=record,
                request_id=_validate_identifier("request_id", path_segments[3]),
                body=body,
            )
        raise _not_found()

    def _handle_protocol_session(
        self,
        *,
        method: str,
        path_segments: tuple[str, ...],
        query: Mapping[str, str],
        body: JsonValue,
    ) -> ServerResponse:
        if len(path_segments) < 2:
            raise _not_found()
        session_id = _validate_identifier("session_id", path_segments[1])
        record = self._protocol_session(session_id)
        base = ("sessions", session_id)
        if method == "GET" and path_segments == base:
            viewer_player_id = _optional_query_string(query, key="viewer_player_id")
            record.touch(self._timestamp())
            return _session_metadata_response(
                record=record,
                viewer_player_id=viewer_player_id,
            )
        if method == "POST" and path_segments == (*base, "start"):
            return self._start_protocol_session(
                record=record,
                viewer_player_id=_query_string(query, key="viewer_player_id"),
            )
        if method == "POST" and path_segments == (*base, "advance"):
            return self._advance_protocol_session(
                record=record,
                viewer_player_id=_query_string(query, key="viewer_player_id"),
            )
        if method == "POST" and path_segments == (*base, "close"):
            return self._close_protocol_session(
                record=record,
                viewer_player_id=_query_string(query, key="viewer_player_id"),
            )
        if method == "GET" and path_segments == (*base, "projection"):
            projection = record.adapter_session.view(
                viewer_player_id=_query_string(query, key="viewer_player_id")
            )
            record.touch(self._timestamp())
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, projection)),
            )
        if method == "GET" and path_segments == (*base, "catalog"):
            catalog = record.adapter_session.rules_catalog_view()
            record.touch(self._timestamp())
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, catalog)),
            )
        if method == "GET" and path_segments == (*base, "events"):
            delta = record.adapter_session.events_since(
                EventStreamCursor(_query_int(query, key="cursor")),
                viewer_player_id=_query_string(query, key="viewer_player_id"),
            )
            record.touch(self._timestamp())
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, delta)),
            )
        if method == "GET" and path_segments == (*base, "replay"):
            replay = record.adapter_session.replay_artifact(
                artifact_id=f"session-replay:{session_id}"
            )
            record.touch(self._timestamp())
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, replay)),
            )
        if method == "GET" and path_segments == (*base, "support-profile"):
            profile = record.adapter_session.support_profile()
            record.touch(self._timestamp())
            return ServerResponse(
                status_code=int(HTTPStatus.OK),
                payload=validate_json_value(cast(JsonValue, profile)),
            )
        if (
            method == "POST"
            and len(path_segments) == 5
            and path_segments[:3] == ("sessions", session_id, "decisions")
            and path_segments[4] == "option"
        ):
            outcome = self._apply_option(
                record=record,
                request_id=_validate_identifier("request_id", path_segments[3]),
                body=body,
                require_started=True,
            )
            return _session_command_response(
                record=record,
                operation="submit_finite_decision",
                accepted=outcome.accepted,
                viewer_player_id=outcome.actor_id,
                from_cursor=outcome.from_cursor,
                status_code=(
                    HTTPStatus.OK if outcome.accepted else HTTPStatus.UNPROCESSABLE_ENTITY
                ),
            )
        if (
            method == "POST"
            and len(path_segments) == 5
            and path_segments[:3] == ("sessions", session_id, "decisions")
            and path_segments[4] == "payload"
        ):
            outcome = self._apply_parameterized_payload(
                record=record,
                request_id=_validate_identifier("request_id", path_segments[3]),
                body=body,
                require_started=True,
            )
            return _session_command_response(
                record=record,
                operation="submit_parameterized_decision",
                accepted=outcome.accepted,
                viewer_player_id=outcome.actor_id,
                from_cursor=outcome.from_cursor,
                status_code=(
                    HTTPStatus.OK if outcome.accepted else HTTPStatus.UNPROCESSABLE_ENTITY
                ),
            )
        raise _not_found()

    def _create_protocol_session(self, body: JsonValue) -> ServerResponse:
        payload = _json_object("POST /sessions body", body)
        _require_exact_keys(
            payload,
            keys=frozenset({"schema_version", "config", "participant_assignments"}),
        )
        _require_external_schema_version(
            payload,
            expected=SESSION_CREATE_SCHEMA_VERSION,
            payload_name="session create payload",
        )
        _require_canonical_request_schema(
            payload,
            schema_name=SESSION_CREATE_SCHEMA_NAME,
            payload_name="session create payload",
        )
        config = GameConfig.from_payload(cast(GameConfigPayload, payload["config"]))
        try:
            assignments = participant_assignments_from_payload(
                payload["participant_assignments"],
                player_ids=config.player_ids,
            )
        except SessionProtocolError as exc:
            raise ServerApiError(
                status_code=HTTPStatus.BAD_REQUEST,
                code="participant_assignments_invalid",
                message="Participant assignments do not match the game players.",
            ) from exc
        record = self._create_authoritative_session(
            config=config,
            participant_assignments=assignments,
        )
        return _session_metadata_response(
            record=record,
            viewer_player_id=None,
            status_code=HTTPStatus.CREATED,
        )

    def _create_game(self, body: JsonValue) -> ServerResponse:
        payload = _json_object("POST /games body", body)
        _require_exact_keys(payload, keys=frozenset({"schema_version", "config"}))
        _require_external_schema_version(
            payload,
            expected=CREATE_SESSION_SCHEMA_VERSION,
            payload_name="create session payload",
        )
        _require_canonical_request_schema(
            payload,
            schema_name=CREATE_SESSION_SCHEMA_NAME,
            payload_name="create session payload",
        )
        config = GameConfig.from_payload(cast(GameConfigPayload, payload["config"]))
        record = self._create_authoritative_session(
            config=config,
            participant_assignments=default_participant_assignments(config.player_ids),
        )
        return _status_response(
            game_id=config.game_id,
            status=record.lifecycle_status,
            status_code=HTTPStatus.CREATED,
            viewer_player_id=None,
        )

    def _create_authoritative_session(
        self,
        *,
        config: GameConfig,
        participant_assignments: tuple[ParticipantAssignment, ...],
    ) -> AuthoritativeSession:
        if config.game_id in self._session_id_by_game_id:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="game_already_exists",
                message="Game already exists.",
            )
        session_id = _session_id_for_game(config.game_id)
        if session_id in self._sessions:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="session_already_exists",
                message="Session already exists.",
            )
        session = self.session_factory()
        status = session.start(config)
        record = AuthoritativeSession.create(
            session_id=session_id,
            adapter_session=session,
            config=config,
            participant_assignments=participant_assignments,
            lifecycle_status=status,
            created_at=self._timestamp(),
        )
        self._sessions[session_id] = record
        self._session_id_by_game_id[config.game_id] = session_id
        return record

    def _start_protocol_session(
        self,
        *,
        record: AuthoritativeSession,
        viewer_player_id: str,
    ) -> ServerResponse:
        _ensure_session_open(record)
        if record.started:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="session_already_started",
                message="Session has already started.",
            )
        before = _session_checkpoint(record=record, viewer_player_id=viewer_player_id)
        status = record.adapter_session.advance_until_decision_or_terminal()
        record.started = True
        record.accept_status(status, timestamp=self._timestamp())
        return _session_command_response(
            record=record,
            operation="start_session",
            accepted=True,
            viewer_player_id=viewer_player_id,
            from_cursor=before["event_cursor"],
        )

    def _advance_protocol_session(
        self,
        *,
        record: AuthoritativeSession,
        viewer_player_id: str,
    ) -> ServerResponse:
        _ensure_session_active(record)
        before = _session_checkpoint(record=record, viewer_player_id=viewer_player_id)
        status = record.adapter_session.advance_until_decision_or_terminal()
        record.accept_status(status, timestamp=self._timestamp())
        return _session_command_response(
            record=record,
            operation="advance_session",
            accepted=True,
            viewer_player_id=viewer_player_id,
            from_cursor=before["event_cursor"],
        )

    def _close_protocol_session(
        self,
        *,
        record: AuthoritativeSession,
        viewer_player_id: str,
    ) -> ServerResponse:
        _ensure_session_open(record)
        before = _session_checkpoint(record=record, viewer_player_id=viewer_player_id)
        record.close(timestamp=self._timestamp())
        return _session_command_response(
            record=record,
            operation="close_session",
            accepted=True,
            viewer_player_id=viewer_player_id,
            from_cursor=before["event_cursor"],
        )

    def _submit_option(
        self,
        *,
        game_id: str,
        record: AuthoritativeSession,
        request_id: str,
        body: JsonValue,
    ) -> ServerResponse:
        outcome = self._apply_option(
            record=record,
            request_id=request_id,
            body=body,
            require_started=False,
        )
        return _status_response(
            game_id=game_id,
            status=outcome.status,
            status_code=(HTTPStatus.OK if outcome.accepted else HTTPStatus.UNPROCESSABLE_ENTITY),
            viewer_player_id=outcome.actor_id,
        )

    def _apply_option(
        self,
        *,
        record: AuthoritativeSession,
        request_id: str,
        body: JsonValue,
        require_started: bool,
    ) -> _MutationOutcome:
        payload = _json_object("finite option submission body", body)
        _require_exact_keys(
            payload,
            keys=frozenset({"schema_version", "actor_id", "option_id", "result_id"}),
        )
        _require_external_schema_version(
            payload,
            expected=FINITE_SUBMISSION_SCHEMA_VERSION,
            payload_name="finite option submission",
        )
        _require_canonical_request_schema(
            payload,
            schema_name=FINITE_SUBMISSION_SCHEMA_NAME,
            payload_name="finite option submission",
        )
        actor_id = _required_string(payload, key="actor_id")
        option_id = _required_string(payload, key="option_id")
        _ensure_session_open(record)
        if require_started and not record.started:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="session_not_started",
                message="Session has not started.",
            )
        session = record.adapter_session
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
        before = _session_checkpoint(record=record, viewer_player_id=actor_id)
        status = session.submit_option(
            request_id=request_id,
            option_id=option_id,
            result_id=_required_string(payload, key="result_id"),
        )
        accepted = status.status_kind is not LifecycleStatusKind.INVALID
        if accepted:
            status = _drain_after_submission(session=session, status=status)
            record.accept_status(status, timestamp=self._timestamp())
        else:
            record.reject_status(status, timestamp=self._timestamp())
        return _MutationOutcome(
            actor_id=actor_id,
            status=status,
            accepted=accepted,
            from_cursor=before["event_cursor"],
        )

    def _submit_parameterized_payload(
        self,
        *,
        game_id: str,
        record: AuthoritativeSession,
        request_id: str,
        body: JsonValue,
    ) -> ServerResponse:
        outcome = self._apply_parameterized_payload(
            record=record,
            request_id=request_id,
            body=body,
            require_started=False,
        )
        return _status_response(
            game_id=game_id,
            status=outcome.status,
            status_code=(HTTPStatus.OK if outcome.accepted else HTTPStatus.UNPROCESSABLE_ENTITY),
            viewer_player_id=outcome.actor_id,
        )

    def _apply_parameterized_payload(
        self,
        *,
        record: AuthoritativeSession,
        request_id: str,
        body: JsonValue,
        require_started: bool,
    ) -> _MutationOutcome:
        payload = _json_object("parameterized submission body", body)
        _require_exact_keys(
            payload,
            keys=frozenset({"schema_version", "actor_id", "payload", "result_id"}),
        )
        _require_external_schema_version(
            payload,
            expected=PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
            payload_name="parameterized submission",
        )
        actor_id = _required_string(payload, key="actor_id")
        submitted_payload = validate_json_value(payload["payload"])
        _reject_raw_dice_payload(submitted_payload)
        _require_canonical_request_schema(
            payload,
            schema_name=PARAMETERIZED_SUBMISSION_SCHEMA_NAME,
            payload_name="parameterized submission",
        )
        _ensure_session_open(record)
        if require_started and not record.started:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="session_not_started",
                message="Session has not started.",
            )
        session = record.adapter_session
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
        before = _session_checkpoint(record=record, viewer_player_id=actor_id)
        status = session.submit_parameterized_payload(
            request_id=request_id,
            payload=submitted_payload,
            result_id=_required_string(payload, key="result_id"),
        )
        accepted = status.status_kind is not LifecycleStatusKind.INVALID
        if accepted:
            status = _drain_after_submission(session=session, status=status)
            record.accept_status(status, timestamp=self._timestamp())
        else:
            record.reject_status(status, timestamp=self._timestamp())
        return _MutationOutcome(
            actor_id=actor_id,
            status=status,
            accepted=accepted,
            from_cursor=before["event_cursor"],
        )

    def _session_record_for_game(self, game_id: str) -> AuthoritativeSession:
        session_id = self._session_id_by_game_id.get(game_id)
        if session_id is None:
            raise ServerApiError(
                status_code=HTTPStatus.NOT_FOUND,
                code="game_not_found",
                message="Game was not found.",
            )
        return self._protocol_session(session_id)

    def _protocol_session(self, session_id: str) -> AuthoritativeSession:
        record = self._sessions.get(session_id)
        if record is None:
            raise ServerApiError(
                status_code=HTTPStatus.NOT_FOUND,
                code="session_not_found",
                message="Session was not found.",
            )
        return record

    def _timestamp(self) -> str:
        return operational_timestamp(self.clock)


def _session_id_for_game(game_id: str) -> str:
    return _validate_identifier("session_id", f"session-{game_id}")


def _ensure_session_open(record: AuthoritativeSession) -> None:
    if record.closed:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="session_closed",
            message="Session is closed.",
        )


def _ensure_session_active(record: AuthoritativeSession) -> None:
    _ensure_session_open(record)
    if not record.started:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="session_not_started",
            message="Session has not started.",
        )
    if record.lifecycle_status.status_kind is LifecycleStatusKind.TERMINAL:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="session_terminal",
            message="Session is terminal.",
        )


def _drain_after_submission(
    *,
    session: AdapterGameSession,
    status: LifecycleStatus,
) -> LifecycleStatus:
    if status.status_kind is not LifecycleStatusKind.ADVANCED:
        return status
    drained = session.advance_until_decision_or_terminal()
    if drained.status_kind is LifecycleStatusKind.ADVANCED:
        raise ServerApiError(
            status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
            code="drain_boundary_missing",
            message="Session drain did not reach an adapter-visible boundary.",
        )
    return drained


def _session_checkpoint(
    *,
    record: AuthoritativeSession,
    viewer_player_id: str,
) -> SessionCheckpointPayload:
    view = record.adapter_session.view(viewer_player_id=viewer_player_id)
    return {
        "viewer_player_id": viewer_player_id,
        "projection_state_hash": view["projection_state_hash"],
        "event_cursor": view["event_count"],
    }


def _session_metadata_payload(
    *,
    record: AuthoritativeSession,
    viewer_player_id: str | None,
) -> JsonValue:
    anchor_viewer = record.player_ids[0] if viewer_player_id is None else viewer_player_id
    checkpoint = _session_checkpoint(
        record=record,
        viewer_player_id=anchor_viewer,
    )
    metadata = record.metadata_payload(
        lifecycle_status=cast(
            JsonValue,
            _status_summary(record.lifecycle_status, viewer_player_id=viewer_player_id),
        ),
        projection_state_hash=(
            None if viewer_player_id is None else checkpoint["projection_state_hash"]
        ),
        event_cursor=checkpoint["event_cursor"],
    )
    return validate_json_value(cast(JsonValue, metadata))


def _session_metadata_response(
    *,
    record: AuthoritativeSession,
    viewer_player_id: str | None,
    status_code: HTTPStatus = HTTPStatus.OK,
) -> ServerResponse:
    return ServerResponse(
        status_code=int(status_code),
        payload=_session_metadata_payload(
            record=record,
            viewer_player_id=viewer_player_id,
        ),
    )


def _session_command_response(
    *,
    record: AuthoritativeSession,
    operation: str,
    accepted: bool,
    viewer_player_id: str,
    from_cursor: int,
    status_code: HTTPStatus = HTTPStatus.OK,
) -> ServerResponse:
    checkpoint = _session_checkpoint(
        record=record,
        viewer_player_id=viewer_player_id,
    )
    metadata = record.metadata_payload(
        lifecycle_status=cast(
            JsonValue,
            _status_summary(record.lifecycle_status, viewer_player_id=viewer_player_id),
        ),
        projection_state_hash=checkpoint["projection_state_hash"],
        event_cursor=checkpoint["event_cursor"],
    )
    payload = session_command_result_payload(
        operation=operation,
        accepted=accepted,
        session=metadata,
        checkpoint=checkpoint,
        from_cursor=from_cursor,
    )
    return ServerResponse(
        status_code=int(status_code),
        payload=validate_json_value(cast(JsonValue, payload)),
    )


def _require_canonical_request_schema(
    payload: dict[str, JsonValue],
    *,
    schema_name: str,
    payload_name: str,
) -> None:
    try:
        validate_external_request_payload(
            schema_name=schema_name,
            payload=payload,
            payload_name=payload_name,
        )
    except ExternalContractValidationError as exc:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="canonical_schema_invalid",
            message=str(exc),
        ) from exc


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
        "schema_version": LIFECYCLE_STATUS_SCHEMA_VERSION,
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
    payload: dict[str, JsonValue] = {
        "schema_version": ERROR_ENVELOPE_SCHEMA_VERSION,
        "error": {
            "code": _validate_identifier("error code", code),
            "message": _validate_identifier("error message", message),
        },
    }
    return ServerResponse(
        status_code=int(status_code),
        payload=validate_json_value(cast(JsonValue, payload)),
    )


def _require_external_schema_version(
    payload: dict[str, JsonValue],
    *,
    expected: str,
    payload_name: str,
) -> None:
    try:
        require_schema_version(
            actual=payload["schema_version"],
            expected=expected,
            payload_name=payload_name,
        )
    except ValueError as exc:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="schema_version_mismatch",
            message=str(exc),
        ) from exc


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
