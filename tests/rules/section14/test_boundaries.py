"""Real boundary owners and facade submissions without a preceding phase replay."""

import json

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import choose, movement_case, propose, select
from tests.support.section14_boundaries import boundary_case, constructed_sticky, move_checkpoint
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.engine.boundary_rule_flow import (
    prepare_phase_end_boundary,
    prepare_turn_end_control_boundary,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionError
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.geometry.pose import Pose


def test_public_movement_boundary_determines_control_before_nonempty_end_rule(
    section14_definitions: Section02Definitions,
) -> None:
    from tests.support.section09_timing import timing_session
    from warhammer40k_core.engine.game_state import SecondaryMissionChoice, SecondaryMissionMode

    state, unit, _ = boundary_case(section14_definitions)
    for player in state.player_ids:
        state.record_secondary_mission_choice(
            SecondaryMissionChoice(
                player, SecondaryMissionMode.FIXED, ("assassination", "bring-it-down")
            )
        )
    # Explicit source-compiled timing contract, not a native Lord datasheet grant.
    session = timing_session(section14_definitions, state, "At the end of your Movement phase")
    for i in range(4):
        status = session.advance_until_decision_or_terminal()
        if state.current_battle_phase is BattlePhase.SHOOTING:
            break
        request = status.decision_request
        assert request is not None
        option = (
            unit.unit_instance_id
            if request.decision_type == "select_movement_unit"
            else "remain_stationary"
        )
        session.submit_option(
            request_id=request.request_id, option_id=option, result_id=f"s14:boundary:{i}"
        )
    else:
        pytest.fail("Native Movement boundary did not complete")
    events = session.lifecycle.decision_controller.event_log.records
    kinds = [e.event_type for e in events]
    assert kinds.index("end_boundary_objective_control_determined") < kinds.index(
        "catalog_ir_command_point_phase_gain_resolved"
    )
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    record = next(
        r for r in state.objective_control_records if r.phase == BattlePhase.MOVEMENT.value
    )
    assert (
        record.result_by_objective_id(marker.objective_marker_id).controlled_by_player_id == "owner"
    )
    assert state.command_point_total("owner") == 1


@pytest.mark.parametrize("turn_end", [False, True])
def test_control_is_frozen_first_and_later_boundary_queries_do_not_recompute(
    section14_definitions: Section02Definitions,
    turn_end: bool,
) -> None:
    phase = BattlePhase.FIGHT if turn_end else BattlePhase.MOVEMENT
    state, unit, enemy = boundary_case(section14_definitions, phase=phase)
    decisions = DecisionController()
    registry = RuntimeModifierRegistry.empty()
    prepare = prepare_turn_end_control_boundary if turn_end else prepare_phase_end_boundary
    assert not state.objective_control_records
    assert prepare(state=state, decisions=decisions, runtime_modifier_registry=registry) is None
    timing = ObjectiveControlTiming.TURN_END if turn_end else ObjectiveControlTiming.PHASE_END
    record = next(r for r in state.objective_control_records if r.timing is timing)
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    assert (
        record.result_by_objective_id(marker.objective_marker_id).controlled_by_player_id == "owner"
    )
    assert len(decisions.event_log.records) == 1
    assert decisions.event_log.records[0].event_type == "end_boundary_objective_control_determined"
    frozen = json.loads(json.dumps(record.to_payload()))
    # Explicit later-rule checkpoint, not native movement. Existing boundary
    # authority must remain valid after another rule changes the live occupants.
    move_checkpoint(state, unit, marker.x_inches + 20, marker.y_inches)
    move_checkpoint(state, enemy, marker.x_inches, marker.y_inches)
    assert (
        resolve_objective_control(
            ObjectiveControlContext.from_game_state(
                state,
                timing=timing,
                phase=phase,
                ruleset_descriptor=state.runtime_ruleset_descriptor(),
            )
        )
        .result_by_objective_id(marker.objective_marker_id)
        .controlled_by_player_id
        == "opponent"
    )
    assert prepare(state=state, decisions=decisions, runtime_modifier_registry=registry) is None
    assert record.to_payload() == frozen
    assert len(decisions.event_log.records) == 1
    assert sum(r.record_id == record.record_id for r in state.objective_control_records) == 1


def test_faq19_newly_gained_movement_control_can_be_secured_by_permitted_boundary_rule(
    section14_definitions: Section02Definitions,
) -> None:
    state, unit, _ = boundary_case(section14_definitions)
    decisions = DecisionController()
    assert (
        prepare_phase_end_boundary(
            state=state,
            decisions=decisions,
            runtime_modifier_registry=RuntimeModifierRegistry.empty(),
        )
        is None
    )
    record = state.objective_control_records[0]
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    assert (
        record.result_by_objective_id(marker.objective_marker_id).controlled_by_player_id == "owner"
    )
    # Core FAQ grants ordering, not a native securing ability. Supply only a
    # labelled permission checkpoint after the control owner has run.
    sticky = constructed_sticky(state, unit, marker.objective_marker_id)
    state.record_sticky_objective_control_state(sticky)
    move_checkpoint(state, unit, marker.x_inches + 20, marker.y_inches)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    following = state.record_objective_control_boundary(
        completed_phase=BattlePhase.SHOOTING,
        timing=ObjectiveControlTiming.PHASE_END,
        runtime_modifier_registry=RuntimeModifierRegistry.empty(),
    )
    result = following.result_by_objective_id(marker.objective_marker_id)
    assert result.controlled_by_player_id == "owner"
    assert result.retained_control_source_id == sticky.source_rule_id
    assert not result.contributors


@pytest.mark.parametrize("endpoint_offset", [0, 2])
def test_native_marker_movement_accepts_crossing_and_on_top_after_invalid_retry(
    section14_definitions: Section02Definitions,
    endpoint_offset: float,
) -> None:
    session, state, unit = movement_case(section14_definitions, datasheet="000004078")
    assert state.mission_setup is not None
    marker = state.mission_setup.objective_markers[0]
    enemy = next(a for a in state.army_definitions if a.player_id == "opponent").units[0]
    move_checkpoint(state, enemy, 50, 40)
    move_checkpoint(state, unit, marker.x_inches - 2, marker.y_inches)
    session = movement_session(section14_definitions, state)
    action = select(session, unit)
    request = choose(session, action, "normal_move")
    before = session.lifecycle.to_payload()
    with pytest.raises((DecisionError, GameLifecycleError)):
        session.submit_parameterized_payload(request_id="stale:s14", result_id="stale", payload={})
    assert session.lifecycle.to_payload() == before
    rejected = propose(
        session,
        request,
        unit,
        (Pose.at(marker.x_inches + 20, marker.y_inches),),
        result_id="s14:too-far",
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    retry = session.lifecycle.decision_controller.queue.peek_next()
    assert retry.request_id != request.request_id
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements[
        0
    ].pose == Pose.at(marker.x_inches - 2, marker.y_inches)
    accepted = propose(
        session,
        retry,
        unit,
        (Pose.at(marker.x_inches + endpoint_offset, marker.y_inches),),
        result_id="s14:legal",
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID
    assert state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements[
        0
    ].pose == Pose.at(marker.x_inches + endpoint_offset, marker.y_inches)
    result = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.MOVEMENT,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
    ).result_by_objective_id(marker.objective_marker_id)
    assert result.controlled_by_player_id == "owner"
    assert {c.model_instance_id for c in result.contributors} == set(unit.own_model_ids())
    assert (
        sum(
            e.event_type == "movement_activation_completed"
            for e in session.lifecycle.decision_controller.event_log.records
        )
        == 1
    )
    assert session.events_since(EventStreamCursor(), viewer_player_id="owner")
    assert session.view(viewer_player_id="opponent")
