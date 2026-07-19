from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from http import HTTPStatus
from threading import RLock
from types import TracebackType
from typing import TYPE_CHECKING, Protocol, TypedDict, cast

if TYPE_CHECKING:
    from http.server import ThreadingHTTPServer

from warhammer40k_core.adapters.command_protocol import (
    SessionCommandEnvelope,
    SessionCommandJournalEntry,
    SessionCommandOutcomeCode,
    SessionCommandProtocolError,
    SessionCommandSubmissionKind,
)
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
    SESSION_COMMAND_ENVELOPE_SCHEMA_NAME,
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
from warhammer40k_core.adapters.server_types import (
    ServerApiError as ServerApiError,
)
from warhammer40k_core.adapters.server_types import (
    ServerResponse as ServerResponse,
)
from warhammer40k_core.adapters.server_validation import (
    json_object as _json_object,
)
from warhammer40k_core.adapters.server_validation import (
    method_token as _method,
)
from warhammer40k_core.adapters.server_validation import (
    not_found as _not_found,
)
from warhammer40k_core.adapters.server_validation import (
    optional_query_string as _optional_query_string,
)
from warhammer40k_core.adapters.server_validation import (
    path_segments as _path_segments,
)
from warhammer40k_core.adapters.server_validation import (
    query_int as _query_int,
)
from warhammer40k_core.adapters.server_validation import (
    query_string as _query_string,
)
from warhammer40k_core.adapters.server_validation import (
    reject_raw_dice_payload as _reject_raw_dice_payload,
)
from warhammer40k_core.adapters.server_validation import (
    require_exact_keys as _require_exact_keys,
)
from warhammer40k_core.adapters.server_validation import (
    required_string as _required_string,
)
from warhammer40k_core.adapters.server_validation import (
    validate_identifier as _validate_identifier,
)
from warhammer40k_core.adapters.session_protocol import (
    AuthoritativeSession,
    OperationalClock,
    ParticipantAssignment,
    SessionCheckpointPayload,
    SessionMetadataPayload,
    SessionProtocolError,
    default_participant_assignments,
    operational_timestamp,
    participant_assignments_from_payload,
    session_command_outcome_payload,
    session_command_result_payload,
    utc_operational_clock,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
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
    committed: bool
    accepted: bool
    from_cursor: int


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
        participant_id: str | None = None,
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
                    participant_id=participant_id,
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
            except SessionCommandProtocolError:
                return _error_response(
                    status_code=HTTPStatus.INTERNAL_SERVER_ERROR,
                    code="session_command_protocol_failure",
                    message="Session command protocol processing failed.",
                )

    def _handle(
        self,
        *,
        method: str,
        path_segments: tuple[str, ...],
        query: Mapping[str, str],
        body: JsonValue,
        participant_id: str | None,
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
                participant_id=participant_id,
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
            record.commit_status(status, timestamp=self._timestamp())
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
        participant_id: str | None,
    ) -> ServerResponse:
        if len(path_segments) < 2:
            raise _not_found()
        session_id = _validate_identifier("session_id", path_segments[1])
        record = self._protocol_session(session_id)
        base = ("sessions", session_id)
        if method == "POST" and path_segments == (*base, "commands"):
            return self._execute_protocol_command(
                record=record,
                participant_id=participant_id,
                body=body,
            )
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
                committed=outcome.committed,
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
                committed=outcome.committed,
                accepted=outcome.accepted,
                viewer_player_id=outcome.actor_id,
                from_cursor=outcome.from_cursor,
                status_code=(
                    HTTPStatus.OK if outcome.accepted else HTTPStatus.UNPROCESSABLE_ENTITY
                ),
            )
        raise _not_found()

    def _execute_protocol_command(
        self,
        *,
        record: AuthoritativeSession,
        participant_id: str | None,
        body: JsonValue,
    ) -> ServerResponse:
        envelope = _session_command_envelope(body)
        if envelope.session_id != record.session_id:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="session_id_mismatch",
                message="Command session_id does not match the target session.",
            )
        participant = _command_participant_id(participant_id)
        fingerprint = envelope.fingerprint()
        existing = record.command_entry(envelope.command_id)
        if existing is not None:
            if existing.participant_id != participant:
                raise _actor_not_authorized()
            if existing.envelope_fingerprint != fingerprint:
                raise ServerApiError(
                    status_code=HTTPStatus.CONFLICT,
                    code="command_id_conflict",
                    message="Command ID was already used for a different command.",
                )
            return ServerResponse(
                status_code=existing.status_code,
                payload=existing.public_payload(),
            )
        if envelope.expected_session_revision != record.session_revision:
            raise ServerApiError(
                status_code=HTTPStatus.CONFLICT,
                code="session_revision_conflict",
                message="Session revision conflicted.",
            )
        player_id = record.controlling_player_id(participant)
        if player_id is None:
            raise _actor_not_authorized()
        staged = record.fork_for_command()
        response = self._apply_protocol_command(
            record=staged,
            envelope=envelope,
            player_id=player_id,
        )
        response_payload = _json_object("session command outcome", response.payload)
        if response_payload.get("committed") is not True:
            return _error_response(
                status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
                code="proposal_invalid",
                message="Submitted proposal was invalid.",
            )
        staged.record_command(
            SessionCommandJournalEntry(
                command_id=envelope.command_id,
                participant_id=participant,
                envelope_fingerprint=fingerprint,
                status_code=response.status_code,
                response_payload=response.payload,
            )
        )
        self._sessions[record.session_id] = staged
        return response

    def _apply_protocol_command(
        self,
        *,
        record: AuthoritativeSession,
        envelope: SessionCommandEnvelope,
        player_id: str,
    ) -> ServerResponse:
        kind = envelope.submission_kind
        if kind is SessionCommandSubmissionKind.START_SESSION:
            response = self._start_protocol_session(record=record, viewer_player_id=player_id)
        elif kind is SessionCommandSubmissionKind.ADVANCE_SESSION:
            response = self._advance_protocol_session(record=record, viewer_player_id=player_id)
        elif kind is SessionCommandSubmissionKind.CLOSE_SESSION:
            response = self._close_protocol_session(record=record, viewer_player_id=player_id)
        else:
            _ensure_session_active(record)
            request_id = _command_request_id(envelope)
            pending = _command_pending_decision(
                record=record,
                request_id=request_id,
                player_id=player_id,
            )
            if kind is SessionCommandSubmissionKind.FINITE_OPTION:
                option_id = envelope.option_id()
                if not any(option["option_id"] == option_id for option in pending["options"]):
                    raise _proposal_invalid()
                outcome = self._apply_option(
                    record=record,
                    request_id=request_id,
                    body={
                        "schema_version": FINITE_SUBMISSION_SCHEMA_VERSION,
                        "actor_id": player_id,
                        "option_id": option_id,
                        "result_id": _command_result_id(envelope),
                    },
                    require_started=True,
                )
                operation = "submit_finite_decision"
            else:
                if pending["is_parameterized"] is not True:
                    raise _proposal_invalid()
                outcome = self._apply_parameterized_payload(
                    record=record,
                    request_id=request_id,
                    body={
                        "schema_version": PARAMETERIZED_SUBMISSION_SCHEMA_VERSION,
                        "actor_id": player_id,
                        "payload": envelope.parameterized_payload(),
                        "result_id": _command_result_id(envelope),
                    },
                    require_started=True,
                )
                operation = "submit_parameterized_decision"
            response = _session_command_response(
                record=record,
                operation=operation,
                committed=outcome.committed,
                accepted=outcome.accepted,
                viewer_player_id=player_id,
                from_cursor=outcome.from_cursor,
                status_code=(
                    HTTPStatus.OK if outcome.accepted else HTTPStatus.UNPROCESSABLE_ENTITY
                ),
            )
        return _session_command_outcome_response(
            command_id=envelope.command_id,
            response=response,
        )

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
        record.commit_status(status, timestamp=self._timestamp())
        return _session_command_response(
            record=record,
            operation="start_session",
            committed=True,
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
        record.commit_status(status, timestamp=self._timestamp())
        return _session_command_response(
            record=record,
            operation="advance_session",
            committed=True,
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
            committed=True,
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
        record_count_before = _decision_record_count(record)
        result_id = _required_string(payload, key="result_id")
        status = session.submit_option(
            request_id=request_id,
            option_id=option_id,
            result_id=result_id,
        )
        status, committed, accepted = _commit_submission_status(
            record=record,
            session=session,
            status=status,
            record_count_before=record_count_before,
            timestamp=self._timestamp(),
        )
        return _MutationOutcome(
            actor_id=actor_id,
            status=status,
            committed=committed,
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
        record_count_before = _decision_record_count(record)
        result_id = _required_string(payload, key="result_id")
        status = session.submit_parameterized_payload(
            request_id=request_id,
            payload=submitted_payload,
            result_id=result_id,
        )
        status, committed, accepted = _commit_submission_status(
            record=record,
            session=session,
            status=status,
            record_count_before=record_count_before,
            timestamp=self._timestamp(),
        )
        return _MutationOutcome(
            actor_id=actor_id,
            status=status,
            committed=committed,
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


def _session_command_envelope(body: JsonValue) -> SessionCommandEnvelope:
    payload = _json_object("session command envelope", body)
    _require_canonical_request_schema(
        payload,
        schema_name=SESSION_COMMAND_ENVELOPE_SCHEMA_NAME,
        payload_name="session command envelope",
    )
    try:
        return SessionCommandEnvelope.from_payload(payload)
    except SessionCommandProtocolError as exc:
        raise ServerApiError(
            status_code=HTTPStatus.BAD_REQUEST,
            code="malformed_command_envelope",
            message="Session command envelope was malformed.",
        ) from exc


def _command_participant_id(participant_id: str | None) -> str:
    if type(participant_id) is not str or not participant_id.strip():
        raise _actor_not_authorized()
    return participant_id.strip()


def _command_request_id(envelope: SessionCommandEnvelope) -> str:
    request_id = envelope.request_id
    if request_id is None:
        raise SessionCommandProtocolError("Decision command request_id is missing.")
    return request_id


def _command_result_id(envelope: SessionCommandEnvelope) -> str:
    result_id = envelope.result_id
    if result_id is None:
        raise SessionCommandProtocolError("Decision command result_id is missing.")
    return result_id


def _command_pending_decision(
    *,
    record: AuthoritativeSession,
    request_id: str,
    player_id: str,
) -> DecisionRequestViewPayload:
    pending = record.adapter_session.view(viewer_player_id=player_id)["pending_decision"]
    if pending is None:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="stale_decision_request",
            message="Command does not target the current pending decision.",
        )
    if pending["decision_type"] == redacted_decision_type_for_hidden_viewer():
        raise _actor_not_authorized()
    if pending["actor_id"] != player_id:
        raise _actor_not_authorized()
    if pending["request_id"] != request_id:
        raise ServerApiError(
            status_code=HTTPStatus.CONFLICT,
            code="stale_decision_request",
            message="Command does not target the current pending decision.",
        )
    return pending


def _session_command_outcome_response(
    *,
    command_id: str,
    response: ServerResponse,
) -> ServerResponse:
    base = _json_object("session command result", response.payload)
    accepted = base.get("accepted")
    if type(accepted) is not bool:
        raise SessionProtocolError("Session command result accepted flag is invalid.")
    outcome_code = (
        SessionCommandOutcomeCode.COMMAND_COMMITTED
        if accepted
        else SessionCommandOutcomeCode.PROPOSAL_INVALID
    )
    committed = base.get("committed")
    if type(committed) is not bool:
        raise SessionProtocolError("Session command result committed flag is invalid.")
    operation = base.get("operation")
    if type(operation) is not str:
        raise SessionProtocolError("Session command result operation is invalid.")
    event_range = _json_object("session command event range", base["event_range"])
    from_cursor = event_range.get("from_cursor")
    if type(from_cursor) is not int:
        raise SessionProtocolError("Session command result event range is invalid.")
    payload = session_command_outcome_payload(
        command_id=command_id,
        outcome_code=outcome_code,
        operation=operation,
        committed=committed,
        accepted=accepted,
        session=cast(SessionMetadataPayload, base["session"]),
        checkpoint=cast(SessionCheckpointPayload, base["checkpoint"]),
        from_cursor=from_cursor,
    )
    return ServerResponse(
        status_code=response.status_code,
        payload=validate_json_value(cast(JsonValue, payload)),
    )


def _actor_not_authorized() -> ServerApiError:
    return ServerApiError(
        status_code=HTTPStatus.FORBIDDEN,
        code="actor_not_authorized",
        message="Participant is not authorized to submit this command.",
    )


def _proposal_invalid() -> ServerApiError:
    return ServerApiError(
        status_code=HTTPStatus.UNPROCESSABLE_ENTITY,
        code="proposal_invalid",
        message="Submitted proposal was invalid.",
    )


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


def _commit_submission_status(
    *,
    record: AuthoritativeSession,
    session: AdapterGameSession,
    status: LifecycleStatus,
    record_count_before: int,
    timestamp: str,
) -> tuple[LifecycleStatus, bool, bool]:
    committed = _decision_history_advanced(
        record=record,
        record_count_before=record_count_before,
    )
    accepted = _submission_was_applied(status=status, committed=committed)
    committed_status = (
        _drain_after_submission(session=session, status=status) if accepted else status
    )
    if committed:
        record.commit_status(committed_status, timestamp=timestamp)
    else:
        record.observe_uncommitted_status(committed_status, timestamp=timestamp)
    return committed_status, committed, accepted


def _submission_was_applied(*, status: LifecycleStatus, committed: bool) -> bool:
    if status.status_kind is LifecycleStatusKind.INVALID:
        return False
    if status.status_kind is LifecycleStatusKind.UNSUPPORTED:
        return committed and _is_transition_budget_boundary(status)
    if not committed:
        raise SessionProtocolError("Accepted session submission was not recorded.")
    return True


def _is_transition_budget_boundary(status: LifecycleStatus) -> bool:
    payload = status.payload
    if not isinstance(payload, dict) or "unsupported_reason" not in payload:
        return False
    return payload["unsupported_reason"] == "transition_budget_exhausted"


def _decision_record_count(record: AuthoritativeSession) -> int:
    count = record.adapter_session.decision_record_count()
    if type(count) is not int or count < 0:
        raise SessionProtocolError("Session decision record count is invalid.")
    return count


def _decision_history_advanced(
    *,
    record: AuthoritativeSession,
    record_count_before: int,
) -> bool:
    record_count_after = _decision_record_count(record)
    if record_count_after < record_count_before:
        raise SessionProtocolError("Session decision history moved backwards.")
    return record_count_after > record_count_before


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
    committed: bool,
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
        committed=committed,
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
    from warhammer40k_core.adapters.http_transport import create_http_server

    return create_http_server(
        host=host,
        port=port,
        api=AdapterGameServer() if api is None else api,
    )


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
