"""09.02/09.04/09.05/09.07: public legal choices and selection consumption."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section09_fixtures import begin, events, movement_case, select
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind


@pytest.mark.parametrize("engaged", [False, True])
@pytest.mark.parametrize("shocked", [False, True])
def test_battlefield_choices_apply_exclusive_eligibility_and_optional_retreat(
    section09_definitions: Section02Definitions,
    engaged: bool,
    shocked: bool,
) -> None:
    session, state, unit = movement_case(section09_definitions, engaged=engaged)
    if shocked:
        # Constructed prior failed-test boundary, not evidence of roll admission.
        state.battle_shocked_unit_ids.append(unit.unit_instance_id)
    request = select(session, unit)
    actual = {o.option_id for o in request.options}
    expected = {"remain_stationary"}
    if engaged:
        expected.add("fall_back:desperate_escape")
        if not shocked:
            expected.add("fall_back:ordered_retreat")
    else:
        expected.update(("normal_move", "advance"))
    assert actual == expected
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.selected_unit_ids == (unit.unit_instance_id,)
    assert state.movement_phase_state.moved_unit_ids == ()


@pytest.mark.parametrize("location", ["battlefield", "reserves", "embarked"])
def test_all_locations_can_be_selected_and_remain_stationary(
    section09_definitions: Section02Definitions,
    location: str,
) -> None:
    session, state, unit = movement_case(section09_definitions, location=location)
    request = select(session, unit)
    assert "remain_stationary" in {o.option_id for o in request.options}
    before = state.battlefield_state
    status = session.submit_option(
        request_id=request.request_id, option_id="remain_stationary", result_id="hold"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert state.movement_phase_state is not None
    assert unit.unit_instance_id in state.movement_phase_state.moved_unit_ids
    following = status.decision_request
    assert following is not None
    assert following.decision_type == "select_movement_unit"
    assert unit.unit_instance_id not in {o.option_id for o in following.options}
    assert all("enemy:" not in o.option_id for o in following.options)
    assert not events(session, "move_start_rules_completed")
    assert not [
        e
        for e in events(session, "rule_trigger_observed")
        if e.get("trigger_kind") == "move_completion"
    ]
    complete = events(session, "movement_activation_completed")
    assert len(complete) == 1
    assert complete[0]["witness"] is None
    assert complete[0]["movement_phase_action"] == "remain_stationary"


@pytest.mark.parametrize("location", ["reserves", "embarked"])
def test_offboard_units_cannot_choose_normal_advance_or_fall_back(
    section09_definitions: Section02Definitions,
    location: str,
) -> None:
    session, _state, unit = movement_case(section09_definitions, location=location)
    request = select(session, unit)
    assert not {
        "normal_move",
        "advance",
        "fall_back:ordered_retreat",
        "fall_back:desperate_escape",
    }.intersection(o.option_id for o in request.options)
    if location == "reserves":
        assert {o.option_id for o in request.options}.issubset({"remain_stationary", "ingress"})
    else:
        assert "disembark" in {o.option_id for o in request.options}


@pytest.mark.parametrize("invalid", ["stale", "wrong_actor", "enemy", "unknown"])
def test_selection_rejects_without_consumption_then_legal_choice_continues(
    section09_definitions: Section02Definitions,
    invalid: str,
) -> None:
    session, state, unit = movement_case(section09_definitions)
    request = begin(session)
    before = state.to_payload(), session.lifecycle.decision_controller.to_payload()
    result = DecisionResult.for_request(
        result_id="invalid", request=request, selected_option_id=unit.unit_instance_id
    )
    result = replace(
        result,
        **{
            "stale": {"request_id": "old"},
            "wrong_actor": {"actor_id": "opponent"},
            "enemy": {"selected_option_id": "enemy:enemy"},
            "unknown": {"selected_option_id": "missing"},
        }[invalid],
    )
    with pytest.raises((DecisionError, GameLifecycleError)):
        session.lifecycle.submit_decision(result)
    assert (state.to_payload(), session.lifecycle.decision_controller.to_payload()) == before
    status = session.submit_option(
        request_id=request.request_id, option_id=unit.unit_instance_id, result_id="valid"
    )
    assert status.decision_request is not None
    assert status.decision_request.decision_type == "select_movement_action"


def test_reserve_ingress_is_offered_in_move_units_step_when_eligible(
    section09_definitions: Section02Definitions,
) -> None:
    session, state, unit = movement_case(section09_definitions, location="reserves")
    state.battle_round = 2
    request = select(session, unit)
    assert {o.option_id for o in request.options} == {"remain_stationary", "ingress"}
    assert state.movement_phase_state is not None
    assert state.movement_phase_state.step.value == "move_units"


def test_pending_selected_unit_has_no_implicit_translation_or_rotation(
    section09_definitions: Section02Definitions,
) -> None:
    session, state, unit = movement_case(section09_definitions)
    original = state.battlefield_state
    select(session, unit)
    assert state.battlefield_state == original
    assert not events(session, "movement_activation_completed")
