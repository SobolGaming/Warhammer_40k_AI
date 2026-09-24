# pyright: reportPrivateUsage=false
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import pytest
from tests.order81_projection_helpers import revival_projection_session
from tests.parameterized_projection_helpers import assert_parameterized_session_projection

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.headless import submit_headless_decision
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.network import submit_network_parameterized_payload
from warhammer40k_core.adapters.projection import (
    GameViewPayload,
    _proposal_view,
    public_decision_request_view,
)
from warhammer40k_core.adapters.ui import (
    UiParameterizedSubmissionPayload,
    submit_ui_parameterized_payload,
)
from warhammer40k_core.engine.decision_request import (
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.interaction_metadata import (
    InteractionKind,
    ParameterizedInteractionSpec,
    ParameterizedRequestLayout,
    interaction_descriptor_for_request,
    parameterized_proposal_request_payload,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE

FLAT_FAMILIES = frozenset(
    {
        "submit_healing_revival_placement",
        "submit_return_on_death_placement",
        "submit_catalog_model_materialization_placement",
        "submit_cult_ambush_marker_placement",
    }
)


@dataclass(frozen=True)
class RevivalPlacementChoice:
    """A deterministic adapter choice consuming the real engine view."""

    payload: dict[str, JsonValue]

    def generate_payload(self, *, request: DecisionRequest, view: GameViewPayload) -> JsonValue:
        proposal = view["pending_proposal"]
        assert isinstance(proposal, dict)
        assert proposal["request_id"] == request.request_id
        assert proposal["model_instance_id"]
        return self.payload

    def choose_option(self, *, request: DecisionRequest, view: GameViewPayload) -> str:
        raise AssertionError("Revival placement requires a parameterized submission.")


@pytest.mark.parametrize("adapter", ["local", "ui", "network", "headless"])
def test_revival_projection_submission_restore_and_replay(adapter: str) -> None:
    session, payload = revival_projection_session()
    assert_parameterized_session_projection(session)
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    assert_parameterized_session_projection(restored)
    for player in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=player) == session.view(viewer_player_id=player)
    status = restored.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    assert request.actor_id is not None
    submission: UiParameterizedSubmissionPayload = {
        "request_id": request.request_id,
        "result_id": "revive-model",
        "payload": payload,
    }
    if adapter == "ui":
        result = submit_ui_parameterized_payload(restored, submission)
    elif adapter == "network":
        result = submit_network_parameterized_payload(restored, submission)
    elif adapter == "headless":
        choice = RevivalPlacementChoice(payload)
        result = submit_headless_decision(
            session=restored,
            status=status,
            viewer_player_id=request.actor_id,
            result_id="revive-model",
            finite_option_ranker=choice,
            parameterized_payload_generator=choice,
        )
    else:
        result = restored.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="revive-model",
            payload=payload,
        )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    assert isinstance(request.payload, dict)
    model_id = request.payload["model_instance_id"]
    state = restored.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    assert model_id not in state.battlefield_state.removed_model_ids
    for player in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=player)["pending_proposal"] is None
        delta = restored.events_since(EventStreamCursor(), viewer_player_id=player)
        assert any(event["event_type"] == "healing_step_resolved" for event in delta["events"])
        assert json.loads(json.dumps(delta)) == delta
    final = restored.to_persistence_payload()
    assert (
        LocalGameSession.from_persistence_payload(
            json.loads(json.dumps(final))
        ).to_persistence_payload()
        == final
    )
    replay = ReplayRunner.from_payload(restored.replay_artifact(artifact_id="order81-projection"))
    assert replay.run().status is ReplayRunStatus.REPRODUCED
    assert json.loads(json.dumps(final)) == final


@pytest.mark.parametrize("corruption", ["stale", "kind", "malformed", "unit", "pose"])
def test_invalid_revival_submission_preserves_visible_pending_request(corruption: str) -> None:
    session, payload = revival_projection_session()
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    assert request is not None
    bad = dict(payload)
    if corruption == "stale":
        bad["proposal_request_id"] = "stale-request"
    elif corruption == "kind":
        bad["proposal_kind"] = "reinforcement_placement"
    elif corruption == "unit":
        bad["unit_instance_id"] = "another-unit"
    elif corruption == "pose":
        bad["attempted_placement"] = {}
    else:
        bad = {}
    before = session.lifecycle.to_payload()
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="invalid-revival",
        payload=bad,
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    assert_parameterized_session_projection(session)


def _conformance_requests() -> tuple[DecisionRequest, ...]:
    path = (
        Path(__file__).resolve().parents[2]
        / "contracts/examples/decisions/interaction-conformance.json"
    )
    cases = json.loads(path.read_text())["cases"]
    requests: list[DecisionRequest] = []
    for case in cases:
        if not case["case_id"].startswith("parameterized:"):
            continue
        raw = case["request"]
        requests.append(
            DecisionRequest(
                request_id=raw["request_id"],
                decision_type=raw["decision_type"],
                actor_id=raw["actor_id"],
                payload=raw["payload"],
                options=(parameterized_decision_option(),),
            )
        )
    return tuple(requests)


@pytest.mark.parametrize("pending", _conformance_requests(), ids=lambda value: value.request_id)
def test_every_parameterized_family_projects_exact_context(pending: DecisionRequest) -> None:
    request = pending
    context = cast(dict[str, JsonValue], request.payload)
    if request.decision_type not in FLAT_FAMILIES:
        context = cast(dict[str, JsonValue], context["proposal_request"])
    expected = {
        **context,
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
    }
    assert _proposal_view(request, viewer=ViewerContext.for_player("player-a")) == expected
    assert interaction_descriptor_for_request(request)["proposal_kind"]


@pytest.mark.parametrize("family", ["submit_healing_revival_placement", "submit_movement_proposal"])
@pytest.mark.parametrize(
    "corruption", ["scalar", "layout", "null", "request_id", "actor_id", "decision_type"]
)
def test_projection_and_interaction_reject_the_same_invalid_context(
    family: str, corruption: str
) -> None:
    context: dict[str, JsonValue] = {
        "proposal_kind": "healing_revival_placement" if family in FLAT_FAMILIES else "normal_move"
    }
    if corruption in {"request_id", "actor_id", "decision_type"}:
        context[corruption] = "drifted"
    payload: JsonValue = context if family in FLAT_FAMILIES else {"proposal_request": context}
    if corruption == "scalar":
        payload = []
    elif corruption == "layout":
        payload = {"proposal_request": context} if family in FLAT_FAMILIES else context
    elif corruption == "null":
        payload = {"proposal_request": None}
    request = DecisionRequest(
        request_id="request",
        decision_type=family,
        actor_id="player-a",
        payload=payload,
        options=(parameterized_decision_option(),),
    )
    before = request.to_payload()
    with pytest.raises(GameLifecycleError):
        _proposal_view(request, viewer=ViewerContext.for_player("player-a"))
    with pytest.raises(GameLifecycleError):
        interaction_descriptor_for_request(request)
    assert request.to_payload() == before


def test_hidden_parameterized_request_is_redacted_before_context_reading() -> None:
    # The redaction policy owns visibility even for an unregistered parameterized layout.
    request = DecisionRequest(
        request_id="secret",
        decision_type=SECONDARY_MISSION_DECISION_TYPE,
        actor_id="player-a",
        payload={"secret": True, "sensitive": "must-not-leak"},
        options=(parameterized_decision_option(),),
    )
    viewer = ViewerContext.for_player("player-b")
    assert _proposal_view(request, viewer=viewer) is None
    view = public_decision_request_view(request, viewer=viewer)
    assert view["interaction"] is None
    assert "must-not-leak" not in json.dumps(view)
    with pytest.raises(GameLifecycleError):
        _proposal_view(request, viewer=ViewerContext.for_player("player-a"))


def test_unregistered_parameterized_request_fails_closed() -> None:
    request = DecisionRequest(
        request_id="unknown",
        decision_type="unknown",
        actor_id="player-a",
        payload={"proposal_request": {"proposal_kind": "normal_move"}},
        options=(parameterized_decision_option(),),
    )
    with pytest.raises(GameLifecycleError):
        _proposal_view(request, viewer=ViewerContext.for_player("player-a"))
    with pytest.raises(GameLifecycleError):
        interaction_descriptor_for_request(request)


def test_parameterized_context_rejects_finite_requests_and_untyped_layouts() -> None:
    finite = DecisionRequest(
        request_id="finite",
        decision_type="select_healing_model",
        actor_id="player-a",
        payload={},
        options=(DecisionOption("model", "Model", {}),),
    )
    with pytest.raises(GameLifecycleError, match="requires a parameterized request"):
        parameterized_proposal_request_payload(finite)
    with pytest.raises(GameLifecycleError, match="typed request layout"):
        ParameterizedInteractionSpec(
            InteractionKind.MODEL_POSE_PLACEMENT,
            request_layout=cast(ParameterizedRequestLayout, "flat_request"),
        )
