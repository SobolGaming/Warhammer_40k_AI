"""10.02 and FAQ02: native eligibility, choices, optionality and continuation."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import (
    choose,
    combat_state,
    pending,
    weapon_rows,
)
from tests.support.section09_fixtures import unplace
from tests.support.section10_fixtures import (
    AVENGERS,
    DEFILER,
    LORD,
    SPAWN,
    SPINNER,
    WRAITHLORD,
    assert_valid,
    case,
    declaration_request,
    shooting_mission,
    submit,
)
from tests.support.section10_fixtures import shooting_session as combat_session
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.phase import GameLifecycleError


@pytest.mark.parametrize(
    ("sheet", "engaged", "advance", "expected"),
    [
        (LORD, False, False, {"normal"}),
        (LORD, True, False, {"close_quarters"}),
        (SPAWN, False, False, {"normal"}),
        (SPAWN, True, False, set[str]()),
        (AVENGERS, False, True, {"assault"}),
        (AVENGERS, True, True, set[str]()),
        (LORD, False, True, set[str]()),
        (LORD, True, True, set[str]()),
        (SPINNER, False, False, {"normal", "indirect"}),
        (SPINNER, False, True, {"assault"}),
        (SPINNER, True, False, {"close_quarters"}),
        (DEFILER, True, False, {"close_quarters"}),
        (DEFILER, True, True, set[str]()),
        (AVENGERS, False, False, {"normal"}),
        (WRAITHLORD, False, False, {"normal"}),
        (WRAITHLORD, True, False, {"close_quarters"}),
        (WRAITHLORD, False, True, {"assault"}),
        (WRAITHLORD, True, True, set[str]()),
    ],
)
def test_native_type_eligibility_is_independent_of_targets(
    section10_definitions: Section02Definitions,
    sheet: str,
    engaged: bool,
    advance: bool,
    expected: set[str],
) -> None:
    session, state, unit = case(section10_definitions, sheet, engaged=engaged, advance=advance)
    request = pending(session)
    assert request.decision_type == "select_shooting_unit"
    assert (unit.unit_instance_id in {o.option_id for o in request.options}) is bool(expected)
    if expected:
        choose(session, request, unit.unit_instance_id)
        request = pending(session)
        assert request.decision_type == "select_shooting_type"
        assert {o.option_id for o in request.options} == expected
        assert state.shooting_phase_state is not None
        assert state.shooting_phase_state.selected_unit_ids == (unit.unit_instance_id,)
    else:
        assert state.shooting_phase_state is not None
        assert unit.unit_instance_id not in state.shooting_phase_state.selected_unit_ids


@pytest.mark.parametrize("location", ["reserves", "embarked"])
def test_offboard_friendly_units_are_absent_from_shooting_selection(
    section10_definitions: Section02Definitions, location: str
) -> None:
    d = section10_definitions
    unit = d.unit(LORD)
    state = combat_state(d, unit)
    from tests.support.section03_fixtures import grid
    from tests.support.section09_fixtures import add_unit

    add_unit(
        state, d.unit(SPAWN, identity="keeper"), grid(d.unit(SPAWN, identity="keeper"), 40, 30)
    )
    reserve_unit(state, unit)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(unplace(state, unit))
    if location == "embarked":
        from warhammer40k_core.engine.transports import (
            TransportCapacityProfile,
            TransportCargoState,
        )

        # Constructed cargo-location boundary, no Transport admission claim.
        transport = d.unit(SPINNER, identity="transport")
        add_unit(state, transport, grid(transport, 30, 30))
        state.reserve_states.clear()
        state.transport_cargo_states.append(
            TransportCargoState(
                "owner",
                transport.unit_instance_id,
                TransportCapacityProfile(SPINNER, 12, source_id="constructed:section10:cargo"),
                (unit.unit_instance_id,),
            )
        )
    session = combat_session(d, state, shooting_mission())
    assert unit.unit_instance_id not in {o.option_id for o in pending(session).options}
    assert all(not o.option_id.startswith("enemy:") for o in pending(session).options)


@pytest.mark.parametrize("invalid", ["stale", "wrong_actor", "enemy", "unknown"])
def test_invalid_selection_preserves_state_and_legal_retry(
    section10_definitions: Section02Definitions, invalid: str
) -> None:
    session, state, unit = case(section10_definitions)
    request = pending(session)
    before = session.lifecycle.to_payload()
    result = DecisionResult.for_request(
        result_id="invalid", request=request, selected_option_id=unit.unit_instance_id
    )
    result = replace(
        result,
        **{
            "stale": {"request_id": "stale"},
            "wrong_actor": {"actor_id": "opponent"},
            "enemy": {"selected_option_id": "enemy:target"},
            "unknown": {"selected_option_id": "unknown"},
        }[invalid],
    )
    with pytest.raises((DecisionError, GameLifecycleError)):
        session.lifecycle.submit_decision(result)
    assert session.lifecycle.to_payload() == before
    assert pending(session) == request
    choose(session, request, unit.unit_instance_id)
    assert pending(session).decision_type == "select_shooting_type"
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.selected_unit_ids == (unit.unit_instance_id,)


@pytest.mark.parametrize(
    ("sheet", "distance", "kind"),
    [(SPAWN, 12, "normal"), (LORD, 60, "normal"), (SPAWN, 60, "normal")],
)
def test_faq02_no_weapon_or_target_still_consumes_selected_type_without_attacks(
    section10_definitions: Section02Definitions, sheet: str, distance: float, kind: str
) -> None:
    session, state, unit = case(section10_definitions, sheet, distance=distance)
    declaration_request(session, unit, kind)
    assert pending(session).decision_type == "select_shooting_unit"
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id in state.shooting_phase_state.selected_unit_ids
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    assert unit.unit_instance_id not in {o.option_id for o in pending(session).options}
    events = session.lifecycle.decision_controller.event_log.records
    assert any(e.event_type == "shooting_without_attacks_completed" for e in events)
    assert not any(e.event_type == "attack_sequence_step" for e in events)


@pytest.mark.parametrize("decline_weapons", [False, True])
def test_optional_declaration_completes_before_next_unit_is_selected(
    section10_definitions: Section02Definitions, decline_weapons: bool
) -> None:
    session, state, unit = case(section10_definitions)
    declaration_request(session, unit, "normal")
    rows = [] if decline_weapons else weapon_rows(pending(session))[:1]
    assert_valid(submit(session, rows, [None] * len(rows), "normal"))
    assert pending(session).decision_type == "select_shooting_unit"
    assert unit.unit_instance_id not in {o.option_id for o in pending(session).options}
    assert state.shooting_phase_state is not None
    assert unit.unit_instance_id not in state.shooting_phase_state.shot_unit_ids
    assert not any(
        e.event_type == "attack_sequence_step"
        for e in session.lifecycle.decision_controller.event_log.records
    )


def test_ineligible_type_is_rejected_before_valid_choice(
    section10_definitions: Section02Definitions,
) -> None:
    session, _state, unit = case(section10_definitions)
    choose(session, pending(session), unit.unit_instance_id)
    request = pending(session)
    before = session.lifecycle.to_payload()
    with pytest.raises((DecisionError, GameLifecycleError)):
        session.submit_option(
            request_id=request.request_id, option_id="indirect", result_id="wrong-type"
        )
    assert session.lifecycle.to_payload() == before
    choose(session, request, "normal")
    assert pending(session).decision_type == "submit_shooting_declaration"


def test_player_can_end_shooting_with_eligible_units_unselected(
    section10_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.phase import LifecycleStatusKind
    from warhammer40k_core.engine.phases.shooting import ShootingPhaseHandler

    session, state, unit = case(section10_definitions)
    request = pending(session)
    assert unit.unit_instance_id in {o.option_id for o in request.options}
    result = DecisionResult.for_request(
        result_id="finish-optional", request=request, selected_option_id="complete_shooting_phase"
    )
    decisions = session.lifecycle.decision_controller
    decisions.submit_result(result)
    handler = ShootingPhaseHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        army_catalog=section10_definitions.package.army_catalog,
    )
    handler.apply_decision(state=state, result=result, decisions=decisions)
    status = handler.begin_phase(state=state, decisions=decisions)
    assert status.status_kind is LifecycleStatusKind.ADVANCED
    assert state.shooting_phase_state is not None
    assert state.shooting_phase_state.phase_complete
    assert state.shooting_phase_state.selected_unit_ids == ()
    assert state.shooting_phase_state.shot_unit_ids == ()
    assert not any(e.event_type == "attack_sequence_step" for e in decisions.event_log.records)
