"""Native live/retained PSYKER public finite choices at declared Core checkpoints."""

import json
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section22_fixtures import psychic_public_scene
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.psychic_ability_usage import psychic_uses


@pytest.mark.parametrize("retained", [False, True])
def test_native_psyker_finite_activation_invalid_retry_and_both_viewers(
    section22_definitions: Section02Definitions, retained: bool
) -> None:
    session, state, source = psychic_public_scene(section22_definitions, retained=retained)
    session.advance_until_decision_or_terminal()
    request = pending(session)
    assert "catalog_any_phase_once_per_battle" in request.decision_type
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict) and o.payload.get("activate") is True
    )
    before = session.lifecycle.to_payload()
    invalid = replace(
        DecisionResult.for_request(
            result_id="s22:invalid", request=request, selected_option_id=option.option_id
        ),
        payload={},
    )
    status = session.lifecycle.submit_decision(invalid)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.lifecycle.to_payload() == before
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="s22:legal"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    uses = psychic_uses(session.lifecycle.decision_controller.event_log)
    assert len(uses) == 1
    assert uses[0].rules_unit_instance_id == source.unit_instance_id
    assert uses[0].source_model_instance_id == source.own_model_ids()[0]
    assert uses[0].request_id == request.request_id
    for viewer in state.player_ids:
        events = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert any(e["event_type"] == "psychic_ability_used" for e in events["events"])
        json.dumps(events, allow_nan=False)
