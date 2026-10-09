"""Core Counter targets fight eligibility before its own Fights First grant.

The predeclared bounded Core catalog uses real public Charge/Fight decisions;
it does not certify a faction provider or replace started state, history or RNG.
"""

import json
from copy import deepcopy
from typing import cast

import pytest
from tests.order128_helpers import assert_checkpoint
from tests.order135_counteroffensive_helpers import (
    actual_fought_events,
    army_id,
    native_combat_session,
    other_player,
    proposal_from_native_request,
    submit_native_combat_choice,
)

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.fight_order import (
    FightsFirstRegistry,
    eligible_fight_contexts_for_player,
    fight_eligibility_reasons_for_unit,
    unit_is_currently_engaged,
)
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.stratagems import StratagemTargetBinding, StratagemTargetKind


def _first_opponent_fought(
    session: LocalGameSession, *, first_player: str
) -> tuple[DecisionRequest, str]:
    opponent = other_player(first_player)
    for _ in range(200):
        request = session.advance_until_decision_or_terminal().decision_request
        assert request is not None
        state = session.lifecycle.state
        assert state is not None
        events = [
            event
            for event in actual_fought_events(session)
            if isinstance(event.payload, dict)
            and event.payload["battle_round"] == 2
            and isinstance(event.payload["activation_selection"], dict)
            and event.payload["activation_selection"]["player_id"] == opponent
        ]
        if (
            state.battle_round == 2
            and state.current_battle_phase is BattlePhase.FIGHT
            and state.active_player_id == opponent
            and events
        ):
            assert len(events) == 1
            assert isinstance(events[0].payload, dict)
            assert events[0].payload["attack_sequence_id"] is not None
            return request, events[0].event_id
        submit_native_combat_choice(session, request, first_player=first_player)
    raise AssertionError("Actual opponent Charge/Fights First completion was not reached")


def _accept_and_complete(
    session: LocalGameSession, *, request: DecisionRequest, first_player: str, target: str
) -> None:
    proposal = proposal_from_native_request(request)
    submitted = proposal.with_binding(
        StratagemTargetBinding(
            target_kind=StratagemTargetKind.FRIENDLY_UNIT,
            target_player_id=first_player,
            target_unit_instance_id=target,
        )
    )
    state = session.lifecycle.state
    assert state is not None
    cp_before = state.command_point_total(first_player)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-counter-band:accept",
        payload={"proposal": validate_json_value(submitted.to_payload())},
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted.to_payload()
    assert state.command_point_total(first_player) == cp_before - 2
    assert state.stratagem_use_records[-1].stratagem_id == "counteroffensive"
    fight = state.fight_phase_state
    assert fight is not None
    assert fight.current_ordering_band.value == "fights_first"
    assert fight.active_activation is not None
    assert fight.active_activation.unit_instance_id == target
    assert fight.active_activation.interrupt_id is not None
    assert fight.active_activation.interrupt_id.startswith("counteroffensive:")
    assert FightsFirstRegistry.from_state(state).has_unit(target)
    for _ in range(60):
        pending = session.advance_until_decision_or_terminal().decision_request
        assert pending is not None
        completed = [
            event
            for event in actual_fought_events(session)
            if isinstance(event.payload, dict)
            and isinstance(event.payload["activation_selection"], dict)
            and event.payload["activation_selection"]["unit_instance_id"] == target
        ]
        if completed:
            assert len(completed) == 1
            assert isinstance(completed[0].payload, dict)
            assert completed[0].payload["attack_sequence_id"] is not None
            # Counter interrupts once; the other charging enemy keeps its normal turn.
            assert pending.decision_type == "select_fight_activation"
            assert pending.actor_id == other_player(first_player)
            fight = state.fight_phase_state
            assert fight is not None
            assert fight.current_ordering_band.value == "fights_first"
            assert target in fight.fight_order_state.selected_to_fight_unit_ids
            assert len(state.stratagem_use_records) == 1
            assert state.command_point_total(first_player) == cp_before - 2
            return
        submit_native_combat_choice(session, pending, first_player=first_player)
    raise AssertionError("Counter target did not complete genuine melee and resume the band")


@pytest.mark.parametrize("first_player", ["player-a", "player-b"])
def test_native_counter_targets_non_first_unit_before_grant(first_player: str) -> None:
    session = native_combat_session(first_player=first_player)
    request, event_id = _first_opponent_fought(session, first_player=first_player)
    state = session.lifecycle.state
    assert state is not None
    fight = state.fight_phase_state
    assert fight is not None
    target = f"{army_id(first_player)}:one"
    assert fight.current_ordering_band.value == "fights_first"
    assert unit_is_currently_engaged(state=state, unit_instance_id=target)
    assert fight_eligibility_reasons_for_unit(
        state=state,
        fight_state=fight,
        unit_instance_id=target,
        policy=session.lifecycle.config.ruleset_descriptor.fight_policy,
    )
    assert not FightsFirstRegistry.from_state(state).has_unit(target)
    assert target not in fight.fight_order_state.selected_to_fight_unit_ids
    assert state.command_point_total(first_player) >= 2
    assert state.stratagem_use_records == []
    # Ordinary band selection remains restricted, while the Core target query is not.
    assert (
        eligible_fight_contexts_for_player(
            state=state,
            fight_state=fight,
            player_id=first_player,
            policy=session.lifecycle.config.ruleset_descriptor.fight_policy,
        )
        == ()
    )
    assert request.decision_type == "submit_stratagem_target_proposal"
    proposal = proposal_from_native_request(request)
    assert proposal.stratagem_id == "counteroffensive"
    assert proposal.player_id == first_player
    assert proposal.context.active_player_id == other_player(first_player)
    trigger = cast(dict[str, JsonValue], proposal.context.trigger_payload)
    assert trigger["trigger_event_id"] == event_id
    assert target in cast(list[str], trigger["eligible_unit_instance_ids"])
    assert_checkpoint(session)
    before = session.lifecycle.to_payload()
    malformed = deepcopy(proposal.to_payload())
    malformed["catalog_record"]["definition"]["effect_payload"] = {"requires_opponent_turn": 1}
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order135-counter-band:boolean-number-rejected",
        payload={"proposal": validate_json_value(malformed)},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert invalid.payload == {"invalid_reason": "wrong_context"}
    assert session.lifecycle.to_payload() == before
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    forked = session.fork()
    for continuation in (session, restored, forked):
        _accept_and_complete(
            continuation, request=request, first_player=first_player, target=target
        )
    assert restored.to_persistence_payload() == session.to_persistence_payload()
    assert forked.to_persistence_payload() == session.to_persistence_payload()
    assert_checkpoint(session)
