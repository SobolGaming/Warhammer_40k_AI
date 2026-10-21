"""12.08 mode precedence, objective consumers and immediate enemy responses."""

from __future__ import annotations

from dataclasses import replace
from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import axis_endpoint_within_range, geometry
from tests.support.section04_fixtures import choose, pending
from tests.support.section12_fixtures import (
    LORD,
    add_native,
    begin,
    checkpoint,
    declare,
    engaged_case,
    events,
    finish_activation,
    paths,
    session_for,
    set_pose,
    submit_move,
)
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, FightPhaseStepKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("gap", [1.5, 2.5, 3, 3.001, 8])
def test_consolidation_mode_precedence_and_three_inch_target_boundary(
    section12_definitions: Section02Definitions, gap: float
) -> None:
    s, u, e = engaged_case(section12_definitions)
    # Later physical checkpoint; all cases began in genuine native engagement.
    first = geometry(u, (Pose.at(10, 10),))[0]
    second = geometry(e, (Pose.at(10, 10),), enemy=True)[0]
    x = axis_endpoint_within_range(10, first.base.max_radius(), second.base.max_radius(), gap)
    set_pose(s, e, (Pose.at(x, 10),), enemy=True)
    assert s.mission_setup is not None
    marker = replace(s.mission_setup.objective_markers[0], x_inches=14, y_inches=10)
    s.mission_setup = replace(s.mission_setup, objective_markers=(marker,))
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    enemy_spare = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(10, 30),))
    add_native(s, enemy_spare, (Pose.at(13, 30),), enemy=True)
    checkpoint(s, FightPhaseStepKind.CONSOLIDATE)
    session = session_for(section12_definitions, s)
    r = begin(session)
    request = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert request.context is not None
    expected = "ongoing" if gap <= 2 else "engaging" if gap <= 3 else "objective"
    assert request.context["legal_consolidation_modes"] == [expected]
    wrong = ConsolidationModeKind.OBJECTIVE if gap <= 3 else ConsolidationModeKind.ENGAGING
    before = s.battlefield_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id,) if wrong is ConsolidationModeKind.ENGAGING else (),
        mode=wrong,
        objective=marker.objective_marker_id if wrong is ConsolidationModeKind.OBJECTIVE else None,
        witness=paths(s, (u.unit_instance_id,), 0.25),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    mode = ConsolidationModeKind(expected)
    result = submit_move(
        session,
        targets=(e.unit_instance_id,) if expected != "objective" else (),
        mode=mode,
        objective=marker.objective_marker_id if expected == "objective" else None,
        witness=paths(s, (u.unit_instance_id,), 0.25 if expected != "engaging" else 1.25),
        identity="right-mode",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert len(events(session, "fight_movement_completed")) == 1
    assert bool(events(session, "forced_fight_activation_queue_started")) == (
        expected == "engaging"
    )


@pytest.mark.parametrize("gap", [2.5, 3])
def test_engaging_consolidation_requires_every_selected_enemy_at_endpoint(
    section12_definitions: Section02Definitions, gap: float
) -> None:
    s, u, e = engaged_case(section12_definitions)
    first = geometry(u, (Pose.at(10, 10),))[0]
    second = geometry(e, (Pose.at(10, 10),), enemy=True)[0]
    x = axis_endpoint_within_range(10, first.base.max_radius(), second.base.max_radius(), gap)
    set_pose(s, e, (Pose.at(x, 10),), enemy=True)
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    enemy_spare = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(10, 30),))
    add_native(s, enemy_spare, (Pose.at(13, 30),), enemy=True)
    checkpoint(s, FightPhaseStepKind.CONSOLIDATE)
    session = session_for(section12_definitions, s)
    r = begin(session)
    before = s.battlefield_state
    assert (
        MovementProposalRequest.from_decision_request_payload(r.payload).unit_instance_id
        == u.unit_instance_id
    )
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=ConsolidationModeKind.ENGAGING,
        witness=paths(s, (u.unit_instance_id,), 0.1),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=ConsolidationModeKind.ENGAGING,
        witness=paths(s, (u.unit_instance_id,), 1.25),
        identity="engage",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    r = pending(session)
    assert r.actor_id == "opponent"
    assert r.decision_type == "select_fight_activation"


@pytest.mark.parametrize("select_all", [False, True])
def test_engaging_consolidation_forces_all_newly_engaged_opponents_once_and_resumes(
    section12_definitions: Section02Definitions, select_all: bool
) -> None:
    s, u, e = engaged_case(section12_definitions)
    set_pose(s, e, (Pose.at(14, 9),), enemy=True)
    other = section12_definitions.unit(LORD, identity="other", army_id="enemy")
    add_native(s, other, (Pose.at(14, 11),), enemy=True)
    later = section12_definitions.unit(LORD, identity="z-later")
    add_native(s, later, (Pose.at(10, 20),))
    later_enemy = section12_definitions.unit(LORD, identity="later-enemy", army_id="enemy")
    add_native(s, later_enemy, (Pose.at(13, 20),), enemy=True)
    checkpoint(
        s, FightPhaseStepKind.CONSOLIDATE, engaged_ids=(u.unit_instance_id, later.unit_instance_id)
    )
    session = session_for(section12_definitions, s)
    begin(session)
    original = s.fight_phase_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id, other.unit_instance_id)
        if select_all
        else (e.unit_instance_id,),
        mode=ConsolidationModeKind.ENGAGING,
        witness=paths(s, (u.unit_instance_id,), 0.8),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert s.fight_phase_state is not None
    assert s.fight_phase_state.suspended_state is not None
    assert s.fight_phase_state.suspended_state.current_step is FightPhaseStepKind.CONSOLIDATE
    selected: list[str] = []
    for _ in range(2):
        r = begin(session)
        assert r.decision_type == "select_fight_activation"
        assert r.actor_id == "opponent"
        option = next(
            o
            for o in r.options
            if cast(dict[str, JsonValue], o.payload).get("fight_type") == "normal"
        )
        selected.append(cast(str, cast(dict[str, JsonValue], option.payload)["unit_instance_id"]))
        choose(session, r, option.option_id)
        result = declare(session)
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
        finish_activation(session)
    assert set(selected) == {e.unit_instance_id, other.unit_instance_id}
    assert len(selected) == len(set(selected))
    assert len(events(session, "forced_fight_activation_queue_started")) == 1
    assert len(events(session, "forced_fight_activation_queue_completed")) == 1
    assert s.fight_phase_state is not None
    from warhammer40k_core.engine.phases.fight import require_fight_state

    resumed = require_fight_state(s)
    assert resumed.suspended_state is None
    assert s.fight_phase_state.current_step is FightPhaseStepKind.CONSOLIDATE
    assert original is not None
    assert (
        s.fight_phase_state.fight_order_state.current_band_index
        == original.fight_order_state.current_band_index
    )
    r = begin(session)
    m = MovementProposalRequest.from_decision_request_payload(r.payload)
    assert m.unit_instance_id == later.unit_instance_id
    assert r.actor_id == "owner"


@pytest.mark.parametrize("dx", [-0.25, 0, 0.25])
def test_objective_consolidation_already_in_range_may_stay_or_reposition_in_range(
    section12_definitions: Section02Definitions, dx: float
) -> None:
    s, u, e = engaged_case(section12_definitions)
    set_pose(s, e, (Pose.at(30, 10),), enemy=True)
    assert s.mission_setup is not None
    marker = replace(s.mission_setup.objective_markers[0], x_inches=13, y_inches=10)
    s.mission_setup = replace(s.mission_setup, objective_markers=(marker,))
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    enemy_spare = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(10, 30),))
    add_native(s, enemy_spare, (Pose.at(13, 30),), enemy=True)
    checkpoint(s, FightPhaseStepKind.CONSOLIDATE)
    session = session_for(section12_definitions, s)
    begin(session)
    result = submit_move(
        session,
        objective=marker.objective_marker_id,
        mode=ConsolidationModeKind.OBJECTIVE,
        witness=paths(s, (u.unit_instance_id,), dx),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    completed = events(session, "fight_movement_completed")
    assert len(completed) == 1
    assert cast(str, completed[0]["unit_instance_id"]) == u.unit_instance_id
    assert not events(session, "forced_fight_activation_queue_started")


@pytest.mark.parametrize("failure", ["wrong_objective", "engaged_after", "outside_range"])
def test_objective_consolidation_requires_authoritative_target_unengaged_and_in_range(
    section12_definitions: Section02Definitions, failure: str
) -> None:
    s, u, e = engaged_case(section12_definitions)
    set_pose(s, e, (Pose.at(10 + 1.574803149606299 + 3.1, 10),), enemy=True)
    assert s.mission_setup is not None
    marker = replace(s.mission_setup.objective_markers[0], x_inches=14, y_inches=10)
    s.mission_setup = replace(s.mission_setup, objective_markers=(marker,))
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    foe = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(10, 30),))
    add_native(s, foe, (Pose.at(13, 30),), enemy=True)
    checkpoint(s, FightPhaseStepKind.CONSOLIDATE)
    session = session_for(section12_definitions, s)
    r = begin(session)
    before = s.battlefield_state
    assert (
        MovementProposalRequest.from_decision_request_payload(r.payload).unit_instance_id
        == u.unit_instance_id
    )
    dx = 1.25 if failure == "engaged_after" else -2 if failure == "outside_range" else 0.25
    result = submit_move(
        session,
        objective="absent" if failure == "wrong_objective" else marker.objective_marker_id,
        mode=ConsolidationModeKind.OBJECTIVE,
        witness=paths(s, (u.unit_instance_id,), dx),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        objective=marker.objective_marker_id,
        mode=ConsolidationModeKind.OBJECTIVE,
        witness=paths(s, (u.unit_instance_id,), 0.25),
        identity="legal-objective",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
