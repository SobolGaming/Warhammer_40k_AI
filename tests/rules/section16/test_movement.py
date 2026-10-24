"""16.01 completed native witnessed reactive moves, including zero-net paths."""

import json

import pytest
from tests.action_movement_interruption_helpers import MovementCase, request_action_move
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section16_fixtures import accept, facade_checkpoint

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.actions import MissionActionStatus
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.triggered_movement import DECLINE_TRIGGERED_MOVEMENT_OPTION_ID


@pytest.mark.parametrize("case", ["translation", "return", "zero", "rotation", "rotation_return"])
@pytest.mark.parametrize("permission", [False, True])
def test_completed_witnessed_move_interrupts_even_at_same_endpoint_and_with_faq_permission(
    section16_definitions: Section02Definitions, case: MovementCase, permission: bool
) -> None:
    session, state, unit = facade_checkpoint(section16_definitions, permission=permission)
    started = accept(session, state, unit)
    assert state.battlefield_state is not None
    before = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    # Explicit Core trigger permission to exercise the shared movement owner;
    # no native faction/provider granting ability is asserted.
    request = request_action_move(session, unit.unit_instance_id, case)
    option = next(o for o in request.options if o.option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID)
    cursor = EventStreamCursor(session.event_record_count())
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="s16:move"
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    current = state.mission_action_state_by_id(started.action_id)
    assert current.status is MissionActionStatus.INTERRUPTED
    assert current.interrupted_reason == "unit_moved"
    completed = next(
        e
        for e in session.lifecycle.decision_controller.event_log.records
        if e.event_type == "triggered_movement_resolved"
    )
    history = [h for h in state.model_movement_history if h.event_id == completed.event_id]
    assert {h.model_instance_id for h in history} == set(unit.own_model_ids())
    assert {h.distance_inches for h in history} == (
        {0.25} if case in {"translation", "return"} else {0.0}
    )
    after = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    if case in {"return", "zero", "rotation_return"}:
        assert after == before
    else:
        assert after != before
    assert not state.secondary_objective_cleanse_states
    for viewer in state.player_ids:
        delta = session.events_since(cursor, viewer_player_id=viewer)
        assert (
            len([e for e in delta["events"] if e["event_type"] == "mission_action_interrupted"])
            == 1
        )
        assert json.loads(json.dumps(delta, allow_nan=False)) == delta


def test_declined_move_does_not_interrupt_and_completion_applies_effect(
    section16_definitions: Section02Definitions,
) -> None:
    from warhammer40k_core.engine.phase import BattlePhase

    session, state, unit = facade_checkpoint(section16_definitions)
    started = accept(session, state, unit)
    assert state.battlefield_state is not None
    before = state.battlefield_state.to_payload()
    request = request_action_move(session, unit.unit_instance_id, "return")
    status = session.submit_option(
        request_id=request.request_id,
        option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        result_id="s16:decline",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert state.battlefield_state.to_payload() == before
    assert state.mission_action_state_by_id(started.action_id).status is MissionActionStatus.STARTED
    completed = state.complete_mission_action(
        action_id=started.action_id, completion_phase=BattlePhase.FIGHT
    )
    assert completed.status is MissionActionStatus.COMPLETED
    assert len(state.secondary_objective_cleanse_states) == 1


@pytest.mark.parametrize("kind", ["embark", "into_reserves", "temporarily_removed"])
def test_native_departure_record_interrupts_and_suppresses_effect(
    section16_definitions: Section02Definitions, kind: str
) -> None:
    from warhammer40k_core.engine.battlefield_state import BattlefieldRemovalKind
    from warhammer40k_core.engine.primary_battlefield_departure import (
        record_primary_battlefield_departure,
    )
    from warhammer40k_core.engine.primary_historical_events import (
        record_primary_battlefield_departure_event,
    )
    from warhammer40k_core.engine.primary_mission_action_interruptions import (
        reconcile_primary_mission_action_interruptions,
    )

    session, state, unit = facade_checkpoint(section16_definitions)
    started = accept(session, state, unit)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        state.battlefield_state.without_unit_placement(unit.unit_instance_id)
    )
    # Constructed post-departure boundary; no reserve/cargo/provider admission is
    # claimed. Real physical IDs and the engine's typed departure owner are used.
    departure = record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=unit.unit_instance_id,
        affected_component_unit_instance_ids=(unit.unit_instance_id,),
        departed_component_unit_instance_ids=(unit.unit_instance_id,),
        removed_model_instance_ids=unit.own_model_ids(),
        removal_kind=BattlefieldRemovalKind(kind),
        occurrence_id="constructed:s16:departure",
        source_id="constructed:s16:departure",
    )
    assert departure is not None
    event = record_primary_battlefield_departure_event(
        event_log=session.lifecycle.decision_controller.event_log, departure=departure
    )
    interrupted = reconcile_primary_mission_action_interruptions(
        state=state, decisions=session.lifecycle.decision_controller
    )
    assert len(interrupted) == 1
    assert interrupted[0].action_id == started.action_id
    assert interrupted[0].interrupted_reason == "unit_left_battlefield"
    assert state.mission_action_state_by_id(started.action_id) == interrupted[0]
    assert not set(unit.own_model_ids()).intersection(state.battlefield_state.placed_model_ids())
    terminal = session.lifecycle.decision_controller.event_log.records[-1]
    assert terminal.event_type == "mission_action_interrupted"
    assert isinstance(terminal.payload, dict)
    assert terminal.payload["source_evidence_event_id"] == event.event_id
    assert not state.secondary_objective_cleanse_states
