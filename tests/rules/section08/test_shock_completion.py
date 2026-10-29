# pyright: reportPrivateUsage=false
"""Actual Command owner chooses clearance policy; tests supply only RNG seed."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section07_fixtures import payloads
from tests.support.section08_contracts import command_session
from tests.support.section08_fixtures import command_state, damage_to_count, mark_shocked


@pytest.mark.parametrize("remaining", [4, 5, 10])
@pytest.mark.parametrize("seed", [0, 1, 3, 4])
def test_required_roll_clears_start_shock_only_on_success_and_is_not_repeated(
    section08_definitions: Section02Definitions, remaining: int, seed: int
) -> None:
    state = command_state(section08_definitions)
    state.game_id = f"constructed-s08-roll-{seed}"
    damage_to_count(state, remaining)
    unit_id = mark_shocked(state)
    session = command_session(section08_definitions, state)
    handler = session.lifecycle._command_phase_handler
    handler.begin_phase(state=state, decisions=session.lifecycle.decision_controller)
    results = payloads(session, "battle_shock_test_resolved")
    assert len(results) == 1
    result = results[0]["battle_shock_result"]
    assert isinstance(result, dict)
    modified = result["modified_roll"]
    target = result["leadership_target"]
    assert isinstance(modified, dict)
    total = modified["final_value"]
    assert isinstance(total, int)
    assert isinstance(target, int)
    passed = total >= target
    assert result["passed"] is passed
    print(
        f"Command seed={seed}, remaining={remaining}, "
        f"total={total}, target={target}, passed={passed}"
    )
    assert (unit_id in state.battle_shocked_unit_ids) is (not passed)
    assert state.command_step_state is not None
    assert len(state.command_step_state.completed_battle_shock_test_request_ids) == 1
    for _ in range(2):
        handler.begin_phase(state=state, decisions=session.lifecycle.decision_controller)
    assert payloads(session, "battle_shock_test_resolved") == results
