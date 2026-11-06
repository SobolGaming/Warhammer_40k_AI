from __future__ import annotations

from typing import Protocol, cast

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.contracts import AdapterGameSession
from warhammer40k_core.adapters.projection import GameViewPayload
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phase import (
    GameLifecycleError,
    LifecycleStatus,
    LifecycleStatusKind,
)


class HeadlessFiniteOptionRanker(Protocol):
    def choose_option(
        self,
        *,
        request: DecisionRequest,
        view: GameViewPayload,
    ) -> str:
        """Return one option ID emitted by the pending DecisionRequest."""
        ...


class HeadlessParameterizedPayloadGenerator(Protocol):
    def generate_payload(
        self,
        *,
        request: DecisionRequest,
        view: GameViewPayload,
    ) -> JsonValue:
        """Return one JSON-safe payload for the pending parameterized request."""
        ...


def submit_headless_decision(
    *,
    session: AdapterGameSession,
    status: LifecycleStatus,
    viewer_player_id: str,
    result_id: str,
    finite_option_ranker: HeadlessFiniteOptionRanker,
    parameterized_payload_generator: HeadlessParameterizedPayloadGenerator,
) -> LifecycleStatus:
    request = _decision_request(status)
    if request.actor_id != viewer_player_id:
        raise GameLifecycleError("Headless viewer does not own the pending decision.")
    view = session.view(viewer_player_id=viewer_player_id)
    pending = view["pending_decision"]
    if pending is None or pending["actor_id"] != viewer_player_id:
        raise GameLifecycleError("Headless decision is absent from the player projection.")
    request = DecisionRequest.from_payload(
        cast(
            DecisionRequestPayload,
            {
                "request_id": pending["request_id"],
                "decision_type": pending["decision_type"],
                "actor_id": pending["actor_id"],
                "payload": pending["payload"],
                "options": pending["options"],
            },
        )
    )
    viewer = ViewerContext.for_player(viewer_player_id)
    if request.is_parameterized_submission_request():
        return session.submit_viewer_parameterized_payload(
            viewer=viewer,
            request_id=request.request_id,
            payload=parameterized_payload_generator.generate_payload(
                request=request,
                view=view,
            ),
            result_id=result_id,
        )
    return session.submit_viewer_option(
        viewer=viewer,
        request_id=request.request_id,
        option_id=finite_option_ranker.choose_option(request=request, view=view),
        result_id=result_id,
    )


def _decision_request(status: LifecycleStatus) -> DecisionRequest:
    if type(status) is not LifecycleStatus:
        raise GameLifecycleError("Headless adapter requires a LifecycleStatus.")
    if status.status_kind is not LifecycleStatusKind.WAITING_FOR_DECISION:
        raise GameLifecycleError("Headless adapter requires a pending DecisionRequest.")
    request = status.decision_request
    if request is None:
        raise GameLifecycleError("Headless adapter requires a pending DecisionRequest.")
    return request
