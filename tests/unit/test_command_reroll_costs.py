"""Offered attack rerolls and submission must share the loaded CP cost rules."""

from typing import cast

import pytest
from tests.command_reroll_cost_helpers import discounted_attack_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.phase import LifecycleStatusKind


@pytest.mark.parametrize("restore", [False, True])
@pytest.mark.parametrize("cp", [0, 1])
@pytest.mark.parametrize("roll", ["hit", "wound", "save", "damage"])
def test_attack_command_reroll_offers_and_applies_loaded_discount(
    cp: int,
    roll: str,
    restore: bool,
) -> None:
    session, status = discounted_attack_session(cp=cp)
    for index in range(150):
        assert status.status_kind is not LifecycleStatusKind.INVALID, status
        request = status.decision_request
        assert request is not None, (roll, status)
        if (
            isinstance(status.payload, dict)
            and status.payload.get("phase_body_status") == f"attack_{roll}_command_reroll_pending"
        ):
            break
        assert request.decision_type != "select_shooting_unit", f"No {roll} reroll offered"
        option = next((o for o in request.options if "decline" in o.option_id), request.options[0])
        status = session.submit_option(
            request_id=request.request_id,
            option_id=option.option_id,
            result_id=f"order49:skip:{index}",
        )
    else:
        raise AssertionError(f"No {roll} reroll window")
    if restore:
        session = LocalGameSession.from_persistence_payload(session.to_persistence_payload())
        assert session.lifecycle.decision_controller.queue.pending_requests[0] == request
    assert isinstance(request.payload, dict)
    window = cast(dict[str, object], request.payload["opportunity_window"])
    actions = cast(list[dict[str, object]], window["legal_actions"])
    costs = [action["cost"] for action in actions if action["cost"]]
    assert costs == [[{"resource": "cp", "amount": 0}]]
    state = session.lifecycle.state
    assert state is not None
    assert request.actor_id is not None
    assert state.command_point_total(request.actor_id) == cp
    prior_event_count = len(session.lifecycle.decision_controller.event_log.records)
    option = next(o for o in request.options if "decline" not in o.option_id)
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order49:free-reroll"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    state = session.lifecycle.state
    assert state is not None
    use = state.stratagem_use_records[-1]
    assert use.command_point_cost == 0
    assert use.command_point_modifier_ids
    assert not any(
        event.event_type == "command_points_spent"
        for event in session.lifecycle.decision_controller.event_log.records[prior_event_count:]
    )
