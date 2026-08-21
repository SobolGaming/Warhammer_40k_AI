from __future__ import annotations

import hashlib
from dataclasses import dataclass

from warhammer40k_core import __version__ as ENGINE_VERSION
from warhammer40k_core.adapters.access_control import (
    AccessControlError,
    AuthenticatedPrincipal,
    PrincipalRegistry,
)
from warhammer40k_core.adapters.command_protocol import SessionCommandProtocolError
from warhammer40k_core.adapters.external_contract import (
    EXTERNAL_CONTRACT_VERSION,
    SESSION_PERSISTENCE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.server_sync import validate_cursor_position
from warhammer40k_core.adapters.session_events import (
    CursorResyncReason,
    CursorValidationError,
    SessionCursorCodec,
    SessionEventProtocolError,
    validate_retention_limit,
)
from warhammer40k_core.adapters.session_persistence import (
    SessionPersistenceDriftError,
    SessionPersistenceError,
)
from warhammer40k_core.adapters.session_protocol import (
    ENGINE_BUILD_ID,
    AuthoritativeSession,
    SessionProtocolError,
    SessionRecoveryFactory,
)
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.replay import ReplayArtifactError


class SessionRecoveryError(SessionPersistenceDriftError):
    """Raised before a server can publish recovered authoritative state."""


@dataclass(frozen=True, slots=True)
class RecoveredServerState:
    sessions: dict[str, AuthoritativeSession]
    session_id_by_game_id: dict[str, str]
    cursor_codec: SessionCursorCodec
    event_retention_limit: int


def server_persistence_payload(
    *,
    sessions: dict[str, AuthoritativeSession],
    session_id_by_game_id: dict[str, str],
    cursor_codec: SessionCursorCodec,
    principal_registry: PrincipalRegistry,
    event_retention_limit: int,
) -> dict[str, JsonValue]:
    retention = validate_retention_limit(event_retention_limit)
    _validate_runtime_registry(
        sessions=sessions,
        session_id_by_game_id=session_id_by_game_id,
        event_retention_limit=retention,
    )
    content: dict[str, JsonValue] = {
        "schema_version": SESSION_PERSISTENCE_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "engine_build_id": ENGINE_BUILD_ID,
        "external_contract_version": EXTERNAL_CONTRACT_VERSION,
        "authorization_bindings": principal_registry.binding_payload(),
        "cursor_codec": cursor_codec.to_persistence_payload(),
        "event_retention_limit": retention,
        "sessions": [
            sessions[session_id].to_persistence_payload() for session_id in sorted(sessions)
        ],
        "game_session_index": [
            {"game_id": game_id, "session_id": session_id_by_game_id[game_id]}
            for game_id in sorted(session_id_by_game_id)
        ],
    }
    payload = {**content, "content_hash": _content_hash(content)}
    return _validated_json_object(payload)


def recover_server_persistence_payload(
    payload: JsonValue,
    *,
    principal_registry: PrincipalRegistry,
    session_recovery_factory: SessionRecoveryFactory,
) -> RecoveredServerState:
    value = _root_payload(payload)
    content = {key: item for key, item in value.items() if key != "content_hash"}
    if value["content_hash"] != _content_hash(content):
        raise SessionRecoveryError("Persisted server content hash drifted.")
    _validate_runtime_versions(value)
    try:
        principal_registry.validate_binding_payload(value["authorization_bindings"])
        cursor_codec = SessionCursorCodec.from_persistence_payload(value["cursor_codec"])
        retention_value = value["event_retention_limit"]
        if type(retention_value) is not int:
            raise SessionRecoveryError("Persisted event retention limit is invalid.")
        retention = validate_retention_limit(retention_value)
        sessions = _recover_sessions(
            value["sessions"],
            session_recovery_factory=session_recovery_factory,
        )
        index = _recover_game_index(value["game_session_index"])
        _validate_runtime_registry(
            sessions=sessions,
            session_id_by_game_id=index,
            event_retention_limit=retention,
        )
        _validate_recovered_authority(
            sessions=sessions,
            cursor_codec=cursor_codec,
            principal_registry=principal_registry,
            event_retention_limit=retention,
        )
        recovered_payload = server_persistence_payload(
            sessions=sessions,
            session_id_by_game_id=index,
            cursor_codec=cursor_codec,
            principal_registry=principal_registry,
            event_retention_limit=retention,
        )
        if canonical_json(recovered_payload) != canonical_json(value):
            raise SessionRecoveryError("Persisted server state did not round-trip canonically.")
    except (
        AccessControlError,
        GameLifecycleError,
        ReplayArtifactError,
        SessionCommandProtocolError,
        SessionEventProtocolError,
        SessionPersistenceError,
        SessionProtocolError,
    ) as exc:
        raise SessionRecoveryError("Persisted authoritative session state drifted.") from exc
    return RecoveredServerState(
        sessions=sessions,
        session_id_by_game_id=index,
        cursor_codec=cursor_codec,
        event_retention_limit=retention,
    )


def _root_payload(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise SessionRecoveryError("Persisted server state must be an object.")
    expected_keys = {
        "schema_version",
        "engine_version",
        "engine_build_id",
        "external_contract_version",
        "authorization_bindings",
        "cursor_codec",
        "event_retention_limit",
        "sessions",
        "game_session_index",
        "content_hash",
    }
    if set(payload) != expected_keys:
        raise SessionRecoveryError("Persisted server state keys are invalid.")
    content_hash = payload["content_hash"]
    if type(content_hash) is not str or not _is_sha256(content_hash):
        raise SessionRecoveryError("Persisted server content hash is invalid.")
    return payload


def _validate_runtime_versions(payload: dict[str, JsonValue]) -> None:
    expected = {
        "schema_version": SESSION_PERSISTENCE_SCHEMA_VERSION,
        "engine_version": ENGINE_VERSION,
        "engine_build_id": ENGINE_BUILD_ID,
        "external_contract_version": EXTERNAL_CONTRACT_VERSION,
    }
    if any(payload[name] != value for name, value in expected.items()):
        raise SessionRecoveryError("Persisted server runtime identity drifted.")


def _recover_sessions(
    payload: JsonValue,
    *,
    session_recovery_factory: SessionRecoveryFactory,
) -> dict[str, AuthoritativeSession]:
    if not isinstance(payload, list):
        raise SessionRecoveryError("Persisted sessions must be a list.")
    sessions: dict[str, AuthoritativeSession] = {}
    for item in payload:
        record = AuthoritativeSession.from_persistence_payload(
            item,
            session_recovery_factory=session_recovery_factory,
        )
        if record.session_id in sessions:
            raise SessionRecoveryError("Persisted session identifier is duplicated.")
        sessions[record.session_id] = record
    return sessions


def _recover_game_index(payload: JsonValue) -> dict[str, str]:
    if not isinstance(payload, list):
        raise SessionRecoveryError("Persisted game index must be a list.")
    index: dict[str, str] = {}
    for item in payload:
        if not isinstance(item, dict) or set(item) != {"game_id", "session_id"}:
            raise SessionRecoveryError("Persisted game index entry is invalid.")
        game_id = item["game_id"]
        session_id = item["session_id"]
        if type(game_id) is not str or type(session_id) is not str:
            raise SessionRecoveryError("Persisted game index identifier is invalid.")
        if game_id in index:
            raise SessionRecoveryError("Persisted game identifier is duplicated.")
        index[game_id] = session_id
    return index


def _validate_runtime_registry(
    *,
    sessions: dict[str, AuthoritativeSession],
    session_id_by_game_id: dict[str, str],
    event_retention_limit: int,
) -> None:
    expected_index = {record.game_id: record.session_id for record in sessions.values()}
    if len(expected_index) != len(sessions):
        raise SessionRecoveryError("Authoritative sessions contain duplicate game IDs.")
    if session_id_by_game_id != expected_index:
        raise SessionRecoveryError("Authoritative game-to-session index drifted.")
    for session_id, record in sessions.items():
        if record.session_id != session_id:
            raise SessionRecoveryError("Authoritative session registry key drifted.")
        if record.event_retention_limit != event_retention_limit:
            raise SessionRecoveryError("Authoritative session retention policy drifted.")


def _validate_recovered_authority(
    *,
    sessions: dict[str, AuthoritativeSession],
    cursor_codec: SessionCursorCodec,
    principal_registry: PrincipalRegistry,
    event_retention_limit: int,
) -> None:
    principal_by_id = _principal_by_id(principal_registry)
    for record in sessions.values():
        for entry in record.command_journal.values():
            principal = principal_by_id.get(entry.principal_id)
            if principal is None:
                raise SessionRecoveryError("Command journal principal is no longer registered.")
            viewer = principal.bind_to_session(
                player_ids=record.player_ids,
                authorization_epoch=principal_registry.authorization_epoch,
            )
            if entry.authorization_context != viewer.authorization_context:
                raise SessionRecoveryError("Command journal authorization context drifted.")
    for _token, cursor in cursor_codec.retained_entries():
        cursor_record = sessions.get(cursor.session_id)
        if cursor_record is None:
            raise SessionRecoveryError("Persisted cursor targets an unknown session.")
        principal = principal_by_id.get(cursor.principal_id)
        if principal is None:
            raise SessionRecoveryError("Persisted cursor principal is no longer registered.")
        viewer = principal.bind_to_session(
            player_ids=cursor_record.player_ids,
            authorization_epoch=principal_registry.authorization_epoch,
        )
        cursor_codec.validate_binding(
            cursor,
            session_id=cursor_record.session_id,
            viewer=viewer,
        )
        try:
            validate_cursor_position(
                record=cursor_record,
                viewer=viewer,
                cursor=cursor,
                target=cursor_record.snapshot_for_viewer(viewer),
                retention_limit=event_retention_limit,
            )
        except CursorValidationError as exc:
            if exc.reason is not CursorResyncReason.EXPIRED:
                raise


def _principal_by_id(registry: PrincipalRegistry) -> dict[str, AuthenticatedPrincipal]:
    return {
        credential.principal.principal_id: credential.principal
        for credential in registry.credentials
    }


def _content_hash(payload: dict[str, JsonValue]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _is_sha256(value: str) -> bool:
    return len(value) == 64 and all(character in "0123456789abcdef" for character in value)


def _validated_json_object(payload: dict[str, JsonValue]) -> dict[str, JsonValue]:
    validated = validate_json_value(payload)
    if not isinstance(validated, dict):
        raise SessionRecoveryError("Persisted server state must remain an object.")
    return validated
