"""11.04 each-model, attached ownership and mandatory coherency."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section11_attached import attached_case
from tests.support.section11_fixtures import (
    SERPENT,
    begin,
    choose,
    events,
    modifier,
    propose,
    resolution,
    roll,
    select,
    session_for,
    state_case,
    targets,
    witness,
)
from warhammer40k_core.engine.fights_first import FightsFirstRegistry, fights_first_model_inventory
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("stationary_component", ["body", "leader"])
def test_every_attached_physical_model_must_approach_a_target(
    section11_definitions: Section02Definitions,
    stationary_component: str,
) -> None:
    state, body, leader, enemy, formation = attached_case(section11_definitions)
    path = PathWitness.for_paths(
        tuple(
            (
                u.own_model_ids()[0],
                (Pose.at(10, y), Pose.at(10 if stationary_component == name else 14.5, y)),
            )
            for name, u, y in [("body", body, 10), ("leader", leader, 12.5)]
        )
    )
    result = resolution(state, formation.attached_unit_instance_id, (enemy.unit_instance_id,), path)
    assert not result.is_valid
    assert result.endpoint_violation_code == "charge_not_closer_to_target"
    rows = result.endpoint_witness.model_endpoints
    assert {r.model_instance_id for r in rows} == {*body.own_model_ids(), *leader.own_model_ids()}
    assert {r.component_unit_instance_id for r in rows} == {
        body.unit_instance_id,
        leader.unit_instance_id,
    }
    assert [r.model_instance_id for r in rows if not r.ended_closer] == (
        list(body.own_model_ids())
        if stationary_component == "body"
        else list(leader.own_model_ids())
    )


def test_approach_requirements_cannot_excuse_incoherent_attached_endpoint(
    section11_definitions: Section02Definitions,
) -> None:
    state, body, leader, enemy, formation = attached_case(section11_definitions)
    path = PathWitness.for_paths(
        (
            (body.own_model_ids()[0], (Pose.at(10, 10), Pose.at(14.5, 10))),
            (leader.own_model_ids()[0], (Pose.at(10, 12.5), Pose.at(13, 16))),
        )
    )
    result = resolution(state, formation.attached_unit_instance_id, (enemy.unit_instance_id,), path)
    assert not result.is_valid
    assert not result.coherency_result.is_coherent
    assert all(r.ended_closer for r in result.endpoint_witness.model_endpoints)


def test_canonical_attachment_public_reject_retry_moves_all_physical_owners_and_grants_bonus(
    section11_definitions: Section02Definitions,
) -> None:
    state, body, leader, enemy, formation = attached_case(section11_definitions)
    canonical = formation.attached_unit_instance_id
    modifier(state, canonical, 12)
    session = session_for(section11_definitions, state)
    request = begin(session)
    options = {o.option_id for o in request.options}
    assert canonical in options
    assert body.unit_instance_id not in options
    assert leader.unit_instance_id not in options
    choose(session, canonical)
    targets(session, (enemy.unit_instance_id,))
    before = state.battlefield_state
    incomplete = PathWitness.for_paths(
        ((body.own_model_ids()[0], (Pose.at(10, 10), Pose.at(14.5, 10))),)
    )
    status = propose(
        session, canonical, (enemy.unit_instance_id,), incomplete, result_id="missing-leader"
    )
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert not events(session, "charge_move_completed")
    status = propose(session, canonical, (enemy.unit_instance_id,), witness(state, canonical, 4.5))
    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert len(events(session, "charge_move_completed")) == 1
    assert state.battlefield_state is not None
    for unit in (body, leader):
        placed = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
        assert placed.model_placements[0].pose.position.x == 14.5
        assert placed.model_placements[0].model_instance_id == unit.own_model_ids()[0]
        assert placed.model_placements[0].unit_instance_id == unit.unit_instance_id
    view = rules_unit_view_by_id(state=state, unit_instance_id=canonical)
    present, grants = fights_first_model_inventory(state=state, view=view)
    assert set(present) == {*body.own_model_ids(), *leader.own_model_ids()}
    assert {
        m
        for source, ids in grants
        if source.effect_kind == "charge_grants_fights_first"
        for m in ids
    } == set(present)
    assert FightsFirstRegistry.from_state(state).charged_unit_ids() == (canonical,)
    assert pending(session).decision_type == "select_charging_unit"
    assert canonical not in {o.option_id for o in pending(session).options}


@pytest.mark.parametrize("skies", [False, True])
def test_native_flying_choice_precedes_charge_roll_and_penalizes_current_target_budget(
    section11_definitions: Section02Definitions,
    skies: bool,
) -> None:
    state, unit, enemy = state_case(section11_definitions, datasheet=SERPENT, gap=3)
    modifier(state, unit.unit_instance_id, 6)
    session = session_for(section11_definitions, state)
    request = select(session, unit, skies=skies)
    assert request.decision_type == "select_charge_targets"
    result = roll(session)
    assert result.request.take_to_the_skies is skies
    assert result.movement_budget.maximum_distance_inches == result.value - (2 if skies else 0)
    assert abs(result.reachable_target_distances_inches[enemy.unit_instance_id] - 3) < 1e-12
    records = session.lifecycle.decision_controller.records
    assert isinstance(records[0].result.payload, dict)
    assert records[0].result.payload["take_to_the_skies"] is skies


def test_two_cases_share_definitions_but_not_decisions_damage_or_physical_state(
    section11_definitions: Section02Definitions,
) -> None:
    ls, lu, _ = state_case(section11_definitions)
    rs, ru, _ = state_case(section11_definitions)
    left, right = session_for(section11_definitions, ls), session_for(section11_definitions, rs)
    before = right.lifecycle.to_payload()
    select(left, lu)
    from warhammer40k_core.engine.damage_allocation import DamageKind, apply_damage_to_model

    apply_damage_to_model(
        state=ls,
        target_unit_instance_id=lu.unit_instance_id,
        model_instance_id=lu.own_model_ids()[0],
        damage=1,
        damage_kind=DamageKind.NORMAL,
    )
    assert right.lifecycle.to_payload() == before
    assert lu is not ru
    assert lu.own_models[0] is not ru.own_models[0]
    assert ls.battlefield_state is not rs.battlefield_state
    assert left.lifecycle.decision_controller is not right.lifecycle.decision_controller
    assert ru.own_models[0].current_wounds == ru.own_models[0].initial_wounds


def test_an_engaged_member_cannot_satisfy_another_members_reachable_obligations(
    section11_definitions: Section02Definitions,
) -> None:
    state, body, leader, enemy, formation = attached_case(section11_definitions)
    path = PathWitness.for_paths(
        (
            (body.own_model_ids()[0], (Pose.at(10, 10), Pose.at(14.5, 10))),
            (leader.own_model_ids()[0], (Pose.at(10, 12.5), Pose.at(12.5, 12.5))),
        )
    )
    result = resolution(state, formation.attached_unit_instance_id, (enemy.unit_instance_id,), path)
    assert not result.is_valid
    row = next(
        r
        for r in result.endpoint_witness.model_endpoints
        if r.component_unit_instance_id == leader.unit_instance_id
    )
    assert row.ended_closer
    assert row.engaged_target_unit_instance_ids == ()
    assert row.preferred_reachability.status == "reachable"
    assert row.engagement_reachability.status == "reachable"
    assert row.engagement_reachability.alternative_witness is not None
