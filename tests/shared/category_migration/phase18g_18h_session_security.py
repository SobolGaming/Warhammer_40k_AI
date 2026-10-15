from __future__ import annotations

import base64
import copy
import hashlib
import json
from dataclasses import replace
from pathlib import Path
from typing import Protocol, cast

import pytest
from jsonschema import Draft202012Validator

from tests.shared.repository_root import REPOSITORY_ROOT
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
    ViewerContext,
    bearer_authorization,
    default_principal_registry,
)
from warhammer40k_core.adapters.command_protocol import SessionCommandEnvelope
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.external_contract import (
    SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION,
    SESSION_CREATE_SCHEMA_VERSION,
)
from warhammer40k_core.adapters.redaction import HIDDEN_REQUEST_ID
from warhammer40k_core.adapters.server import AdapterGameServer
from warhammer40k_core.adapters.server_types import ServerResponse
from warhammer40k_core.adapters.session_events import CURSOR_TOKEN_LENGTH, SessionCursor
from warhammer40k_core.adapters.session_protocol import (
    DEFAULT_REVISION_RETENTION_LIMIT,
    AuthoritativeSession,
    SessionProtocolError,
)
from warhammer40k_core.adapters.session_recovery import (
    SessionRecoveryError,
    recover_server_persistence_payload,
    server_persistence_payload,
)
from warhammer40k_core.adapters.session_revision import (
    SessionNonCommandOrigin,
    SessionRevisionCommitment,
    SessionRevisionCursorCommitment,
    SessionRevisionIntegrityError,
    SessionRevisionOrigin,
    SessionRevisionOriginKind,
)
from warhammer40k_core.adapters.setup_smoke import canonical_setup_prebattle_smoke_config
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import LifecycleStatus

PLAYER_A = "player-a"
PLAYER_B = "player-b"
REPO_ROOT = REPOSITORY_ROOT


class _PayloadValidator(Protocol):
    def validate(self, instance: object) -> None: ...


@pytest.fixture(scope="module")
def phase18l_security_checkpoint() -> tuple[AdapterGameServer, str, dict[str, JsonValue]]:
    server = AdapterGameServer()
    session_id = _create_session(server, game_id="phase18l-security-coverage")
    _submit_lifecycle_command(
        server,
        session_id=session_id,
        command_id="phase18l-security-start",
        expected_revision=0,
        submission_kind="start_session",
    )
    return server, session_id, server.persistence_payload()


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


def _rehash_persistence_root(payload: dict[str, JsonValue]) -> None:
    content = {key: value for key, value in payload.items() if key != "content_hash"}
    payload["content_hash"] = hashlib.sha256(
        canonical_json(cast(JsonValue, content)).encode("utf-8")
    ).hexdigest()


def _validate_event_delta(payload: dict[str, JsonValue]) -> None:
    schema_path = REPO_ROOT / "contracts" / "schemas" / "event-delta.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    validator = cast(_PayloadValidator, Draft202012Validator(schema))
    validator.validate(payload)


__all__: list[str] = []
__all__ += ["AdapterGameServer", "AdapterGameSession", "AuthenticatedPrincipal"]
__all__ += ["CURSOR_TOKEN_LENGTH", "DEFAULT_REVISION_RETENTION_LIMIT", "AuthoritativeSession"]
__all__ += ["DEV_ADMIN_TOKEN", "DEV_COACH_A_TOKEN", "DEV_PLAYER_A_TOKEN", "DEV_PLAYER_B_TOKEN"]
__all__ += ["DEV_REPLAY_TOKEN", "DEV_SPECTATOR_TOKEN", "Draft202012Validator"]
__all__ += ["HIDDEN_REQUEST_ID", "PLAYER_A", "PLAYER_B", "JsonValue", "LifecycleStatus", "Path"]
__all__ += ["PrincipalCredential", "PrincipalRegistry", "PrincipalRole", "Protocol"]
__all__ += ["REPOSITORY_ROOT", "REPO_ROOT", "SESSION_COMMAND_ENVELOPE_SCHEMA_VERSION"]
__all__ += ["SESSION_CREATE_SCHEMA_VERSION", "ServerResponse", "SessionCommandEnvelope"]
__all__ += ["SessionCursor", "SessionNonCommandOrigin", "SessionProtocolError"]
__all__ += ["SessionRecoveryError", "SessionRevisionCommitment"]
__all__ += ["SessionRevisionCursorCommitment", "SessionRevisionIntegrityError"]
__all__ += ["SessionRevisionOrigin", "SessionRevisionOriginKind", "ViewerContext"]
__all__ += ["_PayloadValidator", "_command_response", "_create_session", "_error_code", "_events"]
__all__ += ["_integer", "_list", "_metadata", "_object", "_projection"]
__all__ += ["_registry_replacing_principal", "_rehash_persistence_root", "_request"]
__all__ += ["_session_create_body", "_string", "_submit_lifecycle_command"]
__all__ += ["_validate_event_delta", "base64", "bearer_authorization", "canonical_json"]
__all__ += ["canonical_setup_prebattle_smoke_config", "cast", "copy"]
__all__ += ["default_principal_registry", "hashlib", "json", "phase18l_security_checkpoint"]
__all__ += ["pytest", "recover_server_persistence_payload", "replace"]
__all__ += ["server_persistence_payload"]
