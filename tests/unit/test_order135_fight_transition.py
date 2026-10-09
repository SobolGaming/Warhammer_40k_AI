"""A spent Fights First band preserves the player owed the next selection."""

import json

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_counteroffensive_helpers import actual_fought_events, army_id, other_player
from tests.order135_fight_transition_helpers import submit_transition_choice, transition_session

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.fight_order import (
    FightsFirstRegistry,
    eligible_fight_contexts_for_player,
)
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import BattlePhase


def _remaining_request(session: LocalGameSession, *, first_player: str) -> DecisionRequest:
    opponent = other_player(first_player)
    for _ in range(250):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        fight = state.fight_phase_state
        if (
            state.battle_round == 2
            and state.active_player_id == opponent
            and state.current_battle_phase is BattlePhase.FIGHT
            and fight is not None
            and fight.current_ordering_band.value == "remaining_combats"
            and request.decision_type == "select_fight_activation"
        ):
            completed = [
                event
                for event in actual_fought_events(session)
                if isinstance(event.payload, dict)
                and event.payload.get("battle_round") == 2
                and isinstance(event.payload["activation_selection"], dict)
                and event.payload["activation_selection"].get("player_id") == opponent
                and event.payload["activation_selection"].get("ordering_band") == "fights_first"
            ]
            assert len(completed) == 1
            assert isinstance(completed[0].payload, dict)
            assert completed[0].payload["attack_sequence_id"] is not None
            selection = completed[0].payload["activation_selection"]
            assert isinstance(selection, dict)
            assert selection["unit_instance_id"] == (f"{army_id(opponent)}:one")
            by_player = {
                player: eligible_fight_contexts_for_player(
                    state=state,
                    fight_state=fight,
                    player_id=player,
                    policy=session.lifecycle.config.ruleset_descriptor.fight_policy,
                    respect_ordering_band=False,
                )
                for player in state.player_ids
            }
            assert all(by_player.values())
            assert not any(
                FightsFirstRegistry.from_state(state).has_unit(context.unit_instance_id)
                for contexts in by_player.values()
                for context in contexts
            )
            assert request.actor_id == first_player
            return request
        submit_transition_choice(session, request, first_player=first_player)
    raise AssertionError("Genuine last charged activation did not reach Remaining Combats")


def _finish_through_consolidation(session: LocalGameSession, *, first_player: str) -> None:
    saw_consolidation = False
    for _ in range(100):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        if state.battle_round == 3:
            assert saw_consolidation
            assert_checkpoint(session)
            return
        if request.decision_type == "submit_movement_proposal":
            move = MovementProposalRequest.from_decision_request_payload(request.payload)
            if move.proposal_kind is ProposalKind.CONSOLIDATE and not saw_consolidation:
                saw_consolidation = True
                assert_checkpoint(session)
        submit_transition_choice(session, request, first_player=first_player)
    raise AssertionError("Remaining activation and genuine consolidation did not complete")


@pytest.mark.parametrize("first_player", ["player-a", "player-b"])
def test_native_fights_first_exhaustion_keeps_owed_player(first_player: str) -> None:
    session = transition_session(first_player=first_player)
    request = _remaining_request(session, first_player=first_player)
    assert_checkpoint(session)
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    forked = session.fork()
    for continuation in (session, restored, forked):
        pending = continuation.advance_until_decision_or_terminal().decision_request
        assert pending == request
        _finish_through_consolidation(continuation, first_player=first_player)
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert forked.to_persistence_payload() == session.to_persistence_payload()
