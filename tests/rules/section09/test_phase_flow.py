"""09.00/01/02/03: phase order with actual nonempty source-compiled effects."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section09_fixtures import attach_mission, events
from tests.support.section09_timing import timing_session
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode
from warhammer40k_core.engine.phase import BattlePhase


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize(
    ("timing", "position"),
    [
        ("At the start of your Movement phase", "start"),
        ("At the end of your Movement phase", "end"),
    ],
)
def test_nonempty_start_and_end_rules_surround_all_active_units_exactly_once(
    section09_definitions: Section02Definitions,
    active: str,
    timing: str,
    position: str,
) -> None:
    state = native_state(
        section09_definitions,
        section09_definitions.unit("000004078"),
        enemy=section09_definitions.unit("000004090", army_id="enemy", identity="target"),
    )
    state.active_player_id = active
    attach_mission(state)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    session = timing_session(section09_definitions, state, timing)
    observed_types: list[str] = []
    for i in range(12):
        status = session.advance_until_decision_or_terminal()
        if state.current_battle_phase is BattlePhase.SHOOTING:
            break
        request = status.decision_request
        assert request is not None
        observed_types.append(request.decision_type)
        assert request.actor_id == active
        if request.decision_type == "select_movement_unit":
            assert len(request.options) == 1
            option = request.options[0].option_id
        else:
            assert request.decision_type == "select_movement_action"
            option = "remain_stationary"
        session.submit_option(
            request_id=request.request_id, option_id=option, result_id=f"flow:{i}"
        )
    else:
        pytest.fail("Movement did not complete")
    assert observed_types == ["select_movement_unit", "select_movement_action"]
    gains = events(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(active == "owner")
    types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
    assert types.index("movement_phase_entered") < types.index("movement_unit_selected")
    assert (
        types.index("movement_activation_completed")
        < types.index("move_units_completed")
        < types.index("battle_phase_completed")
    )
    if gains:
        assert gains[0]["passed"] is True
        assert state.command_point_total("owner") == 1
        effect = types.index("catalog_ir_command_point_phase_gain_resolved")
        if position == "start":
            assert effect < types.index("movement_unit_selected")
        else:
            assert (
                types.index("move_units_completed") < effect < types.index("battle_phase_completed")
            )
    assert session.events_since(EventStreamCursor(), viewer_player_id="owner")
    assert session.events_since(EventStreamCursor(), viewer_player_id="opponent")
    assert len(events(session, "move_units_completed")) == 1
