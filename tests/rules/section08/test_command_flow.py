# pyright: reportPrivateUsage=false
"""Command-only public submissions and observable timing/effect order."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_state, payloads
from tests.support.section08_contracts import command_session
from tests.support.section08_fixtures import command_state
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.command_abilities import command_abilities_window
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.sequencing import SEQUENCING_DECISION_TYPE
from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload


@pytest.mark.parametrize("active", ["owner", "opponent"])
@pytest.mark.parametrize("round_number", [1, 2])
def test_both_players_receive_one_core_cp_with_idempotent_reentry(
    section08_definitions: Section02Definitions, active: str, round_number: int
) -> None:
    state = command_state(section08_definitions, "000004078")
    state.active_player_id = active
    state.battle_round = round_number
    session = command_session(section08_definitions, state)
    handler = session.lifecycle._command_phase_handler
    decisions = session.lifecycle.decision_controller
    for _ in range(3):
        handler.begin_phase(state=state, decisions=decisions)
    assert [state.command_point_total(p) for p in state.player_ids] == [1, 1]
    gains = payloads(session, "command_points_gained")
    assert len(gains) == 2
    assert {str(g["player_id"]) for g in gains} == set(state.player_ids)
    assert all(g["applied_amount"] == 1 for g in gains)


@pytest.mark.parametrize(
    ("timing", "position"),
    [
        ("At the start of your Command phase", "start"),
        ("In your Command phase", "body"),
        ("At the end of your Command phase", "end"),
    ],
)
@pytest.mark.parametrize("active", ["owner", "opponent"])
def test_source_compiled_effect_runs_only_in_its_own_command_window(
    section08_definitions: Section02Definitions,
    timing: str,
    position: str,
    active: str,
    section07_mission: MissionSetup,
) -> None:
    state = boundary_state(section08_definitions, mission=section07_mission)
    state.active_player_id = active
    session = command_session(section08_definitions, state, (timing,))
    for i in range(8):
        status = session.advance_until_decision_or_terminal()
        if state.current_battle_phase is BattlePhase.MOVEMENT:
            break
        request = status.decision_request
        assert request is not None
        assert request.decision_type == "submit_stratagem_target_proposal"
        session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"decline-{i}",
            payload=stratagem_decline_payload(),
        )
    else:
        pytest.fail("Command phase did not reach Movement")
    gains = payloads(session, "catalog_ir_command_point_phase_gain_resolved")
    assert len(gains) == int(active == "owner")
    assert state.command_point_total("owner") == (2 if active == "owner" else 1)
    assert state.command_point_total("opponent") == 1
    events = session.lifecycle.decision_controller.event_log.records
    types = [e.event_type for e in events]
    core = next(
        i
        for i, event in enumerate(events)
        if event.event_type == "command_points_gained"
        and isinstance(event.payload, dict)
        and event.payload.get("source_kind") == "command_phase_start"
    )
    shock = types.index("battle_shock_step_completed")
    assert core < shock < types.index("battle_phase_completed")
    if gains:
        effect = types.index("catalog_ir_command_point_phase_gain_resolved")
        assert gains[0]["source_rule_id"] == "constructed:section08:timing:0"
        assert gains[0]["passed"] is True
        if position == "start":
            assert effect < core
        else:
            assert shock < effect < types.index("battle_phase_completed")
        windows: list[tuple[int, dict[str, JsonValue]]] = []
        for i, event in enumerate(events):
            if event.event_type != "timing_window_opened":
                continue
            assert isinstance(event.payload, dict)
            window = event.payload["timing_window"]
            assert isinstance(window, dict)
            descriptor = window["descriptor"]
            assert isinstance(descriptor, dict)
            windows.append((i, descriptor))
        body = next(i for i, d in windows if d["source_step"] == "command_abilities")
        end = next(i for i, d in windows if d["trigger_kind"] == "end_phase")
        if position == "body":
            assert shock < body < effect < end
        elif position == "end":
            assert body < end < effect
    session.advance_until_decision_or_terminal()
    assert payloads(session, "catalog_ir_command_point_phase_gain_resolved") == gains
    for viewer in state.player_ids:
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)


def test_pending_body_order_rejects_stale_wrong_actor_and_then_continues(
    section08_definitions: Section02Definitions, section07_mission: MissionSetup
) -> None:
    state = boundary_state(section08_definitions, mission=section07_mission)
    session = command_session(
        section08_definitions,
        state,
        ("In your Command phase", "In your Command phase", "At the end of your Command phase"),
    )
    status = session.advance_until_decision_or_terminal()
    request = status.decision_request
    for i in range(4):
        request = status.decision_request
        assert request is not None
        if request.decision_type == SEQUENCING_DECISION_TYPE:
            break
        status = session.submit_parameterized_payload(
            request_id=request.request_id, result_id=f"pre-{i}", payload=stratagem_decline_payload()
        )
    assert request is not None
    assert request.decision_type == SEQUENCING_DECISION_TYPE
    assert not payloads(session, "catalog_ir_command_point_phase_gain_resolved")
    assert state.command_step_state is not None
    assert state.command_step_state.battle_shock_step_resolved
    before = state.to_payload(), session.lifecycle.decision_controller.to_payload()
    with pytest.raises((DecisionError, GameLifecycleError)):
        session.submit_option(
            request_id="stale", option_id=request.options[0].option_id, result_id="stale"
        )
    result = DecisionResult.for_request(
        result_id="wrong", request=request, selected_option_id=request.options[0].option_id
    )
    with pytest.raises((DecisionError, GameLifecycleError)):
        session.lifecycle.submit_decision(replace(result, actor_id="opponent"))
    assert (state.to_payload(), session.lifecycle.decision_controller.to_payload()) == before
    session.submit_option(
        request_id=request.request_id,
        option_id=request.options[0].option_id,
        result_id="legal-order",
    )
    session.advance_until_decision_or_terminal()
    gains = payloads(session, "catalog_ir_command_point_phase_gain_resolved")
    assert [g["source_rule_id"] for g in gains] == [
        "constructed:section08:timing:1",
        "constructed:section08:timing:0",
        "constructed:section08:timing:2",
    ]
    assert state.current_battle_phase is BattlePhase.MOVEMENT


@pytest.mark.parametrize("phase", [BattlePhase.COMMAND, BattlePhase.MOVEMENT])
def test_command_body_guard_rejects_early_or_wrong_phase_then_valid_boundary_works(
    section08_definitions: Section02Definitions, phase: BattlePhase
) -> None:
    state = command_state(section08_definitions, "000004078")
    state.battle_phase_index = state.battle_phase_sequence.index(phase)
    before = state.to_payload()
    with pytest.raises(GameLifecycleError, match="completed Core CP"):
        command_abilities_window(state)
    assert state.to_payload() == before
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    session = command_session(section08_definitions, state)
    session.lifecycle._command_phase_handler.begin_phase(
        state=state, decisions=session.lifecycle.decision_controller
    )
    window = command_abilities_window(state)
    assert window.descriptor.source_rule_id == "rule:08:08.04:1"
