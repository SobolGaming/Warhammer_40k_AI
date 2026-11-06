from __future__ import annotations

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.contracts import (
    AdapterGameSession,
    FiniteOptionSubmission,
    ParameterizedSubmission,
)
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatus


def viewer_for_issued_request(*, session: AdapterGameSession, request_id: str) -> ViewerContext:
    """Bind a local UI/CLI request capability to its sole projected player owner.

    Network authentication remains server-owned. This local host helper never
    authorizes a remote principal or accepts authoritative request IDs.
    """
    owners: list[str] = []
    for player in session.authoritative_identity_payload()["player_ids"]:
        pending = session.view(viewer_player_id=player)["pending_decision"]
        if (
            pending is not None
            and pending["actor_id"] == player
            and pending["request_id"] == request_id
        ):
            owners.append(player)
    if len(owners) != 1:
        raise GameLifecycleError("Local submission requires one current issued viewer request.")
    return ViewerContext.for_player(owners[0])


def result_for_option(
    *,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> DecisionResult:
    return FiniteOptionSubmission(
        request_id=request.request_id,
        selected_option_id=option_id,
        result_id=result_id,
    ).to_result(request)


def result_for_parameterized_payload(
    *,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> DecisionResult:
    return ParameterizedSubmission(
        request_id=request.request_id,
        payload=payload,
        result_id=result_id,
    ).to_result(request)


def submit_option(
    *,
    lifecycle: GameLifecycle,
    request_id: str,
    option_id: str,
    result_id: str,
) -> LifecycleStatus:
    request = _pending_request(lifecycle, request_id=request_id)
    return lifecycle.submit_decision(
        result_for_option(request=request, option_id=option_id, result_id=result_id)
    )


def submit_parameterized_payload(
    *,
    lifecycle: GameLifecycle,
    request_id: str,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus:
    request = _pending_request(lifecycle, request_id=request_id)
    return lifecycle.submit_decision(
        result_for_parameterized_payload(request=request, payload=payload, result_id=result_id)
    )


def _pending_request(lifecycle: GameLifecycle, *, request_id: str | None = None) -> DecisionRequest:
    if type(lifecycle) is not GameLifecycle:
        raise GameLifecycleError("Adapter submission requires a GameLifecycle.")
    pending_request = lifecycle.pending_decision_request()
    if pending_request is None:
        raise GameLifecycleError("Adapter submission requires a pending DecisionRequest.")
    if request_id is None:
        return pending_request
    expected_request_id = _validate_request_id(request_id)
    if pending_request.request_id != expected_request_id:
        raise GameLifecycleError("Adapter submission request_id does not match pending request.")
    return pending_request


def _validate_request_id(value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError("Adapter submission request_id must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError("Adapter submission request_id must not be empty.")
    return stripped
