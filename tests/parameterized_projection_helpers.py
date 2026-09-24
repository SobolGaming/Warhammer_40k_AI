# pyright: reportPrivateUsage=false
"""Real pending-request projection checks shared by parameterized producer tests."""

from __future__ import annotations

import json

from warhammer40k_core.adapters.access_control import ViewerContext
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.adapters.network import network_view_payload
from warhammer40k_core.adapters.projection import _proposal_view, public_decision_request_view
from warhammer40k_core.adapters.ui import ui_view
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.lifecycle import GameLifecycle


def assert_parameterized_projection(lifecycle: GameLifecycle) -> None:
    request = lifecycle.pending_decision_request()
    assert request is not None
    assert request.is_parameterized_submission_request()
    assert isinstance(request.payload, dict)
    context = request.payload.get("proposal_request", request.payload)
    assert isinstance(context, dict)
    expected = {
        **context,
        "request_id": request.request_id,
        "decision_type": request.decision_type,
        "actor_id": request.actor_id,
    }
    assert DecisionRequest.from_payload(json.loads(json.dumps(request.to_payload()))) == request
    before = lifecycle.to_payload()
    state = lifecycle.state
    assert state is not None
    for player_id in state.player_ids:
        viewer = ViewerContext.for_player(player_id)
        assert _proposal_view(request, viewer=viewer) == expected
        pending = public_decision_request_view(request, viewer=viewer)
        assert pending["payload"] == request.payload
        interaction = pending["interaction"]
        assert interaction is not None
        assert interaction["submission_kind"] == "parameterized"
        assert interaction["constraints"]["proposal_schema_ref"] is not None
        assert json.loads(json.dumps(pending)) == pending

    assert lifecycle.to_payload() == before


def assert_parameterized_session_projection(session: LocalGameSession) -> None:
    assert_parameterized_projection(session.lifecycle)
    state = session.lifecycle.state
    assert state is not None
    for player_id in state.player_ids:
        view = session.view(viewer_player_id=player_id)
        assert view["pending_proposal"] is not None
        assert json.loads(json.dumps(view)) == view
        assert network_view_payload(session, viewer_player_id=player_id) == view
        assert ui_view(session, viewer_player_id=player_id) == view
