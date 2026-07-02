from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import GameLifecycleError

HIDDEN_DECISION_TYPE = "hidden_decision"


def decision_request_hidden_from_viewer(
    *,
    request: DecisionRequest,
    viewer_player_id: str | None,
) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("DecisionRequest redaction requires a DecisionRequest.")
    return secret_payload_hidden_from_viewer(
        actor_id=request.actor_id,
        payload=request.payload,
        viewer_player_id=viewer_player_id,
    )


def decision_request_payload_hidden_from_viewer(
    *,
    request_payload: Mapping[str, JsonValue],
    viewer_player_id: str | None,
) -> bool:
    actor_id = _optional_string(request_payload, key="actor_id")
    return secret_payload_hidden_from_viewer(
        actor_id=actor_id,
        payload=request_payload["payload"],
        viewer_player_id=viewer_player_id,
    )


def secret_payload_hidden_from_viewer(
    *,
    actor_id: str | None,
    payload: JsonValue,
    viewer_player_id: str | None,
) -> bool:
    if actor_id is not None and viewer_player_id is not None and actor_id == viewer_player_id:
        return False
    if not isinstance(payload, dict):
        return False
    secret = payload.get("secret")
    if secret is None:
        return False
    if type(secret) is not bool:
        raise GameLifecycleError("Secret DecisionRequest payload flag must be a bool.")
    return secret


def redacted_decision_type_for_hidden_viewer() -> str:
    return HIDDEN_DECISION_TYPE


def _optional_string(payload: Mapping[str, JsonValue], *, key: str) -> str | None:
    value = payload[key]
    if value is None:
        return None
    if type(value) is not str:
        raise GameLifecycleError(f"DecisionRequest payload key must be a string or null: {key}.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"DecisionRequest payload key must not be empty: {key}.")
    return stripped
