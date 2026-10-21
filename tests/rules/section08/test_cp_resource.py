# pyright: reportPrivateUsage=false
"""Core CP enters the ordinary spendable resource; no separate Core pool."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section08_contracts import command_session
from tests.support.section08_fixtures import command_state
from warhammer40k_core.engine.command_points import CommandPointSpendStatus


@pytest.mark.parametrize("player", ["owner", "opponent"])
def test_core_cp_can_be_spent_and_insufficient_spend_preserves_balance(
    section08_definitions: Section02Definitions, player: str
) -> None:
    state = command_state(section08_definitions)
    session = command_session(section08_definitions, state)
    session.lifecycle._command_phase_handler.begin_phase(
        state=state, decisions=session.lifecycle.decision_controller
    )
    before = state.to_payload()
    rejected = state.spend_command_points(
        player_id=player, amount=2, source_id="constructed:s08:stratagem-cost"
    )
    assert rejected.status is CommandPointSpendStatus.INSUFFICIENT
    assert state.to_payload() == before
    accepted = state.spend_command_points(
        player_id=player, amount=1, source_id="constructed:s08:stratagem-cost"
    )
    assert accepted.status is CommandPointSpendStatus.APPLIED
    assert state.command_point_total(player) == 0
    assert state.command_point_total("opponent" if player == "owner" else "owner") == 1
