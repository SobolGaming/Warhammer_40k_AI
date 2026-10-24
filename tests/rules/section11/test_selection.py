"""11.02: native eligibility, actual 2D6 producer, one activation at a time."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section09_fixtures import unplace
from tests.support.section10_fixtures import advanced
from tests.support.section11_fixtures import (
    begin,
    choose,
    events,
    roll,
    select,
    session_for,
    state_case,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import FellBackUnitState


def test_native_charge_roll_follows_declaration_before_target_selection(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions)
    session = session_for(section11_definitions, state)
    request = select(session, unit)
    result = roll(session)
    print("NATIVE_ROLL", result.to_payload())
    assert result.request.unit_instance_id == unit.unit_instance_id
    assert result.request.spec.expression.quantity == 2
    assert result.request.spec.expression.sides == 6
    assert result.value == sum(result.roll_state.original_result.values)
    assert result.movement_budget.maximum_distance_inches == result.value
    assert state.charge_phase_state is not None
    assert state.charge_phase_state.selected_unit_ids == (unit.unit_instance_id,)
    assert request.actor_id == "owner"
    types = [e.event_type for e in session.lifecycle.decision_controller.event_log.records]
    assert (
        types.index("charging_unit_selected")
        < types.index("charge_roll_started")
        < types.index("charge_roll_resolved")
    )
    assert not events(session, "charge_move_completed")
    if request.decision_type == "select_charge_targets":
        assert result.value >= 5
        assert any(
            isinstance(o.payload, dict) and o.payload.get("target_ids") == [enemy.unit_instance_id]
            for o in request.options
        )
    else:
        assert result.value < 5
        assert request.decision_type == "select_charging_unit"


@pytest.mark.parametrize("gap", [11.999, 12, 12.001])
def test_twelve_inch_declaration_boundary_is_inclusive(
    section11_definitions: Section02Definitions,
    gap: float,
) -> None:
    state, unit, _ = state_case(section11_definitions, gap=gap, origin=2)
    request = begin(session_for(section11_definitions, state))
    assert (unit.unit_instance_id in {o.option_id for o in request.options}) is (gap <= 12)


@pytest.mark.parametrize("restriction", ["advance", "fall_back", "off_battlefield", "engaged"])
@pytest.mark.parametrize("current", [False, True])
def test_native_declaration_exclusions_and_stale_turn_controls(
    section11_definitions: Section02Definitions,
    restriction: str,
    current: bool,
) -> None:
    state, unit, _ = state_case(
        section11_definitions, gap=1.5 if restriction == "engaged" and current else 5
    )
    if restriction == "advance":
        advanced(state, unit)
        if not current:
            state.battle_round = 2
    elif restriction == "fall_back":
        state.record_fell_back_unit_state(
            FellBackUnitState("owner", 1 if current else 2, unit.unit_instance_id)
        )
    elif restriction == "off_battlefield" and current:
        from tests.support.section01_fixtures import reserve_unit

        reserve_unit(state, unit)
        state.replace_battlefield_state(unplace(state, unit))
    session = session_for(section11_definitions, state)
    request = begin(session)
    assert request.actor_id == "owner"
    assert (unit.unit_instance_id in {o.option_id for o in request.options}) is (not current)
    assert "enemy:target" not in {o.option_id for o in request.options}
    assert not events(session, "charge_roll_started")


@pytest.mark.parametrize("field", ["actor", "phase", "unit", "request"])
def test_invalid_selection_keeps_queue_state_and_legal_retry(
    section11_definitions: Section02Definitions,
    field: str,
) -> None:
    state, unit, _ = state_case(section11_definitions)
    session = session_for(section11_definitions, state)
    request = begin(session)
    result = DecisionResult.for_request(
        result_id="invalid", request=request, selected_option_id=unit.unit_instance_id
    )
    assert isinstance(result.payload, dict)
    base_payload = result.payload
    if field == "actor":
        result = replace(result, actor_id="opponent")
    elif field == "request":
        result = replace(result, request_id="wrong-request")
    else:
        result = replace(
            result,
            payload=base_payload
            | ({"phase": "shooting"} if field == "phase" else {"unit_instance_id": "enemy:target"}),
        )
    before = state.to_payload()
    records = session.lifecycle.decision_controller.records
    status = session.lifecycle.submit_decision(result)
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert pending(session) == request
    assert session.lifecycle.decision_controller.records == records
    assert state.to_payload() == before
    choose(session, unit.unit_instance_id)
    assert len(events(session, "charge_roll_resolved")) == 1


def test_pilot_public_target_and_move_boundary(section11_definitions: Section02Definitions) -> None:
    from tests.support.section11_fixtures import propose, targets, witness

    state, unit, enemy = state_case(section11_definitions, gap=3)
    session = session_for(section11_definitions, state)
    request = select(session, unit)
    assert request.decision_type == "select_charge_targets"
    targets(session, (enemy.unit_instance_id,))
    status = propose(
        session,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 2.5),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert events(session, "charge_move_completed")
    assert pending(session).decision_type == "select_charging_unit"


def test_native_double_one_fails_without_moving_and_cannot_declare_again(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, _ = state_case(section11_definitions, gap=3, seed="section11-failed-10")
    session = session_for(section11_definitions, state)
    before = state.battlefield_state
    request = select(session, unit)
    result = roll(session)
    assert result.roll_state.original_result.values == (1, 1)
    assert result.value == 2
    assert not result.move_available
    assert state.battlefield_state == before
    assert request.decision_type == "select_charging_unit"
    assert unit.unit_instance_id not in {o.option_id for o in request.options}
    assert not events(session, "charge_move_completed")
