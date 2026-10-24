"""Locally owned FAQ27: step2/3 execute outside Charge through a real consumer."""

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section11_fixtures import choose, events, modifier, propose, witness
from tests.support.section11_reactive import reactive_case
from warhammer40k_core.engine.charge_declaration import ChargeRollResult, ChargeRollResultPayload
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind


@pytest.mark.parametrize("decline", [False, True])
def test_constructed_out_of_phase_charge_roll_attempt_reject_retry_and_legal_continuation(
    section11_definitions: Section02Definitions,
    decline: bool,
) -> None:
    session, state, unit, enemy = reactive_case(section11_definitions)
    modifier(state, unit.unit_instance_id, 12)
    request = pending(session)
    assert request.decision_type == "select_catalog_setup_reactive_shoot_charge"
    assert request.actor_id == "owner"
    assert state.active_player_id == "opponent"
    choose(session, "charge", result_id="reactive:charge")
    rolls = events(session, "catalog_setup_reactive_charge_roll_resolved")
    assert len(rolls) == 1
    result = ChargeRollResult.from_payload(cast(ChargeRollResultPayload, rolls[0]["roll_result"]))
    assert result.request.spec.expression.quantity == 2
    assert result.request.spec.expression.sides == 6
    assert result.request.player_id == "owner"
    assert result.move_available
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert pending(session).decision_type == "submit_movement_proposal"
    before = state.battlefield_state
    bad = propose(
        session,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 0),
        result_id="reactive:bad",
    )
    assert bad.status_kind is LifecycleStatusKind.INVALID, bad
    assert state.battlefield_state == before
    assert not events(session, "catalog_setup_reactive_charge_move_completed")
    retry = pending(session)
    assert retry.actor_id == "owner"
    result_status = propose(
        session,
        unit.unit_instance_id,
        () if decline else (enemy.unit_instance_id,),
        None if decline else witness(state, unit.unit_instance_id, 2.25),
        result_id="reactive:legal",
    )
    assert result_status.status_kind is not LifecycleStatusKind.INVALID, result_status
    assert len(events(session, "catalog_setup_reactive_charge_move_completed")) == int(not decline)
    assert len(events(session, "catalog_setup_reactive_charge_move_declined")) == int(decline)
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.current_battle_phase is not BattlePhase.CHARGE
    assert not any(
        isinstance(e.effect_payload, dict)
        and e.effect_payload.get("effect_kind") == "charge_grants_fights_first"
        for e in state.persisting_effects
    )
    assert len(events(session, "catalog_setup_reactive_charge_roll_resolved")) == 1
