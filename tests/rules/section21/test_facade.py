"""Native selected-unit facade behavior and separate supported Core persistence."""

import json

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission, begin, events, propose
from tests.support.section11_fixtures import modifier, roll, select, session_for, state_case
from tests.support.section21_fixtures import (
    LORD,
    SERPENT,
    offer_surge,
    submit_surge,
    surge_path,
    surge_scene,
)
from warhammer40k_core.engine.model_movement_history import models_within_turn_distance
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.phase_movement_history import surge_locked
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("skies", [False, True])
@pytest.mark.parametrize("action", ["normal_move", "advance", "fall_back"])
def test_native_flight_choice_commits_before_roll_and_records_accepted_distance(
    section21_definitions: Section02Definitions, skies: bool, action: str
) -> None:
    unit = section21_definitions.unit(SERPENT)
    enemy = section21_definitions.unit(LORD, army_id="enemy", identity="target")
    state = native_state(
        section21_definitions,
        unit,
        (Pose.at(10, 10),),
        enemy=enemy,
        enemy_poses=(Pose.at(10, 13),) if action == "fall_back" else (Pose.at(35, 10),),
    )
    attach_mission(state)
    add_unit(state, section21_definitions.unit(LORD, identity="spare"), (Pose.at(10, 35),))
    session = movement_session(section21_definitions, state)
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:unit", option_id=unit.unit_instance_id
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    choices = [
        o
        for o in request.options
        if isinstance(o.payload, dict)
        and o.payload.get("movement_phase_action") == action
        and o.payload.get("fall_back_mode", "ordered_retreat") == "ordered_retreat"
    ]
    assert len(choices) == 2
    assert not events(session, "advance_roll_resolved")
    option = next(
        o
        for o in choices
        if isinstance(o.payload, dict)
        and (o.payload["movement_mode"] == "fly_take_to_skies") is skies
    )
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:mode", option_id=option.option_id
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    if action == "advance":
        assert len(events(session, "advance_roll_resolved")) == 1
        recorded = session.lifecycle.decision_controller.records
        assert recorded[1].result.selected_option_id == option.option_id
        assert isinstance(recorded[1].result.payload, dict)
        assert recorded[1].result.payload["movement_mode"] == (
            "fly_take_to_skies" if skies else "advance"
        )
    status = propose(
        session, request, unit, (Pose.at(10, 8) if action == "fall_back" else Pose.at(12, 10),)
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert len(state.model_movement_history) == 1
    assert state.model_movement_history[0].distance_inches == 2
    assert models_within_turn_distance(
        state=state, model_ids=unit.own_model_ids(), maximum_inches=3
    )
    completion = events(session, "movement_activation_completed")[-1]
    model_movements = completion["model_movements"]
    assert isinstance(model_movements, list)
    model_movement = model_movements[0]
    assert isinstance(model_movement, dict)
    assert model_movement["movement_distance_modifier_inches"] == (-2 if skies else 0)
    for viewer in ("owner", "opponent"):
        view = session.view(viewer_player_id=viewer)
        assert json.loads(json.dumps(view)) == view
        assert "model_movement_history" not in view


@pytest.mark.parametrize("skies", [False, True])
def test_charge_flight_is_selected_before_dice_and_filters_targets_after_penalty(
    section21_definitions: Section02Definitions, skies: bool
) -> None:
    state, unit, enemy = state_case(
        section21_definitions, datasheet=SERPENT, gap=5, seed="s21-charge"
    )
    modifier(state, unit.unit_instance_id, 6)
    session = session_for(section21_definitions, state)
    request = select(session, unit, skies=skies)
    assert request.decision_type == "select_charge_targets"
    rolled = roll(session)
    assert rolled.request.take_to_the_skies is skies
    assert rolled.movement_budget.maximum_distance_inches == rolled.value - (2 if skies else 0)
    events_ = session.lifecycle.decision_controller.event_log.records
    assert next(
        i for i, e in enumerate(events_) if e.event_type == "charging_unit_selected"
    ) < next(i for i, e in enumerate(events_) if e.event_type == "charge_roll_started")
    assert enemy.unit_instance_id in rolled.reachable_target_distances_inches


@pytest.mark.parametrize("multi", [False, True])
def test_surge_public_reject_retry_commits_all_survivors_and_phase_lock(
    section21_definitions: Section02Definitions, multi: bool
) -> None:
    s = surge_scene(section21_definitions, multi=multi, gap=9)
    session = s.session()
    request = offer_surge(session, s)
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:surge-target",
        option_id=f"surge:{s.unit.unit_instance_id}:target:{s.target.unit_instance_id}",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    before = s.state.to_payload()
    decisions = session.lifecycle.decision_controller.to_payload()
    invalid = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s21:malformed",
        payload={"proposal_request_id": request.request_id},
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.to_payload() == before
    assert session.lifecycle.decision_controller.to_payload() == decisions
    invalid = submit_surge(
        session, request, surge_path(s, (3,) * len(s.unit.own_models)), result_id="s21:short"
    )
    assert invalid.status_kind is LifecycleStatusKind.INVALID
    assert s.state.battlefield_state is not None
    assert not s.state.phase_movement_history
    pending_request = session.lifecycle.pending_decision_request()
    assert pending_request is not None
    request = pending_request
    assert request is not None
    status = submit_surge(session, request, surge_path(s, (4,) * len(s.unit.own_models)))
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert len(s.state.phase_movement_history) == 1
    record = s.state.phase_movement_history[0]
    assert record.is_surge
    assert record.model_instance_ids == s.unit.own_model_ids()
    assert surge_locked(s.state, s.unit.unit_instance_id)
    placed = s.state.battlefield_state.unit_placement_by_id(s.unit.unit_instance_id)
    moved = placed.with_model_placements(
        tuple(
            p.with_pose(Pose.at(p.pose.position.x, p.pose.position.y + 0.1))
            for p in placed.model_placements
        )
    )
    with pytest.raises(GameLifecycleError, match="surge_movement_locked_this_phase"):
        s.state.replace_battlefield_state(s.state.battlefield_state.with_unit_placement(moved))
    for phase, turn, locked in [
        (BattlePhase.SHOOTING, "owner", True),
        (BattlePhase.CHARGE, "owner", False),
        (BattlePhase.SHOOTING, "opponent", False),
    ]:
        s.state.battle_phase_index = s.state.battle_phase_sequence.index(phase)
        s.state.active_player_id = turn
        assert surge_locked(s.state, s.unit.unit_instance_id) is locked
    s.state.battle_phase_index = s.state.battle_phase_sequence.index(BattlePhase.SHOOTING)
    s.state.active_player_id = "owner"
    assert not [o for o in offer_surge(session, s).options if o.option_id.startswith("surge:")]
    assert events(session, "triggered_movement_resolved")
    for viewer in ("owner", "opponent"):
        assert json.loads(json.dumps(session.view(viewer_player_id=viewer))) == session.view(
            viewer_player_id=viewer
        )
