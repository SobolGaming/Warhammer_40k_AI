"""Public adapter progression starts at the rule boundary, without setup or replay."""

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import boundary_session, boundary_state, payloads
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload


@pytest.mark.parametrize("first", ["owner", "opponent"])
def test_public_two_round_order_fixed_first_player_and_boundary_recurrence(
    section07_definitions: Section02Definitions, section07_mission: MissionSetup, first: str
) -> None:
    state = boundary_state(
        section07_definitions, first=first, active=first, mission=section07_mission
    )
    session = boundary_session(section07_definitions, state)
    for index in range(70):
        status = session.advance_until_decision_or_terminal()
        if state.battle_round == 3:
            break
        request = status.decision_request
        assert request is not None, status
        if request.decision_type == "submit_stratagem_target_proposal":
            status = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"s07-{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            options = tuple(
                option
                for option in request.options
                if option.option_id.startswith("complete_")
                or option.option_id in {"remain_stationary", "continue_to_shooting", "decline"}
                or option.option_id.endswith(":decline")
            )
            if request.decision_type == "select_movement_unit":
                options = request.options[:1]
            assert options, request
            status = session.submit_option(
                request_id=request.request_id,
                result_id=f"s07-{index}",
                option_id=options[0].option_id,
            )
        assert status.status_kind not in {
            LifecycleStatusKind.INVALID,
            LifecycleStatusKind.UNSUPPORTED,
        }
    else:
        pytest.fail("Bounded two-round progression did not finish")
    assert (state.battle_round, state.active_player_id) == (3, first)
    completed = payloads(session, "battle_phase_completed")
    assert [row["completed_phase"] for row in completed] == [
        phase
        for _turn in range(4)
        for phase in ("command", "movement", "shooting", "charge", "fight")
    ] + ["command"]
    windows = [
        cast(dict[str, JsonValue], row["timing_window"])
        for row in payloads(session, "timing_window_resolved")
    ]
    observed = [
        (
            window["battle_round"],
            window["active_player_id"],
            cast(dict[str, JsonValue], window["descriptor"])["trigger_kind"],
            window["phase"],
        )
        for window in windows
        if cast(dict[str, JsonValue], window["descriptor"])["trigger_kind"] != "during_phase"
        and window["battle_round"] in (1, 2)
    ]
    expected: list[tuple[JsonValue, JsonValue, JsonValue, JsonValue]] = []
    for round_number in (1, 2):
        expected.append((round_number, first, "start_battle_round", None))
        for player in state.turn_order:
            expected.append((round_number, player, "start_turn", None))
            for phase in ("command", "movement", "shooting", "charge", "fight"):
                expected.extend(
                    (
                        (round_number, player, "start_phase", phase),
                        (round_number, player, "end_phase", phase),
                    )
                )
            expected.append((round_number, player, "end_turn", None))
        expected.append((round_number, first, "end_battle_round", None))
    assert observed == expected
    for row in payloads(session, "timing_window_resolved"):
        window = cast(dict[str, JsonValue], row["timing_window"])
        trigger = cast(dict[str, JsonValue], window["descriptor"])["trigger_kind"]
        if trigger in {"end_turn", "end_battle_round"}:
            assert row["resolution_order"] == ["non_mission_rules", "mission_rules"]
    for viewer in state.player_ids:
        assert session.events_since(EventStreamCursor(), viewer_player_id=viewer)
