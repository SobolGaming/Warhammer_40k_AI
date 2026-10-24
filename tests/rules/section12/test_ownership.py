"""Native attachment, immutable definition and fresh mutable graph consumers."""

from __future__ import annotations

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import weapon_rows
from tests.support.section12_attached import attached_case
from tests.support.section12_fixtures import (
    begin,
    checkpoint,
    declare,
    engaged_case,
    events,
    finish_activation,
    move_payload,
    paths,
    select_fight,
    session_for,
    submit_move,
)
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, FightPhaseStepKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
def test_each_moved_attached_model_must_engage_if_able_and_legal_retry_moves_all_owners(
    section12_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    s, u, leader, e, f = attached_case(section12_definitions)
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
        engaged_ids=(f.attached_unit_instance_id, e.unit_instance_id),
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    assert (
        MovementProposalRequest.from_decision_request_payload(r.payload).unit_instance_id
        == f.attached_unit_instance_id
    )
    before = s.battlefield_state
    mode = ConsolidationModeKind.ONGOING if kind is ProposalKind.CONSOLIDATE else None
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=mode,
        witness=paths(s, (u.unit_instance_id, leader.unit_instance_id), 0.05),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=mode,
        witness=paths(s, (u.unit_instance_id, leader.unit_instance_id), 0.6),
        identity="all-models-engage",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    completed = events(session, "fight_movement_completed")
    assert len(completed) == 1
    assert cast(str, completed[0]["unit_instance_id"]) == f.attached_unit_instance_id
    resolution = cast(dict[str, JsonValue], completed[0]["resolution"])
    assert set(cast(list[str], resolution["component_unit_instance_ids"])) == {
        u.unit_instance_id,
        leader.unit_instance_id,
    }
    transition = cast(dict[str, JsonValue], completed[0]["transition_batch"])
    assert {
        cast(str, x["model_instance_id"])
        for x in cast(list[dict[str, JsonValue]], transition["displacements"])
    } == set(u.own_model_ids() + leader.own_model_ids())


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
@pytest.mark.parametrize("bad", ["omitted_owner", "incoherent", "component_alias"])
def test_attached_group_authority_and_coherency_cannot_be_excused_by_approach(
    section12_definitions: Section02Definitions, kind: ProposalKind, bad: str
) -> None:
    s, u, leader, e, f = attached_case(section12_definitions)
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
        engaged_ids=(f.attached_unit_instance_id, e.unit_instance_id),
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    before = s.battlefield_state
    witness = paths(s, (u.unit_instance_id, leader.unit_instance_id), 0.6)
    if bad == "omitted_owner":
        witness = paths(s, (u.unit_instance_id,), 0.6)
    if bad == "incoherent":
        witness = PathWitness.for_paths(
            (
                (u.own_model_ids()[0], (Pose.at(10, 10), Pose.at(10.6, 10))),
                (leader.own_model_ids()[0], (Pose.at(10, 12.5), Pose.at(10.6, 15.3))),
            )
        )
    payload = cast(
        dict[str, JsonValue],
        move_payload(
            r,
            targets=(e.unit_instance_id,),
            witness=witness,
            mode=ConsolidationModeKind.ONGOING if kind is ProposalKind.CONSOLIDATE else None,
        ),
    )
    if bad == "component_alias":
        payload["unit_instance_id"] = leader.unit_instance_id
    result = session.submit_parameterized_payload(
        request_id=r.request_id, result_id="bad-attachment", payload=payload
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(session, identity="decline")
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


@pytest.mark.parametrize("actor", ["owner", "opponent"])
def test_attached_fight_selection_is_one_canonical_unit_and_weapons_keep_physical_owners(
    section12_definitions: Section02Definitions, actor: str
) -> None:
    s, u, leader, e, f = attached_case(section12_definitions)
    s.active_player_id = actor
    checkpoint(
        s, FightPhaseStepKind.FIGHT, engaged_ids=(f.attached_unit_instance_id, e.unit_instance_id)
    )
    session = session_for(section12_definitions, s)
    r = begin(session)
    if actor == "opponent":
        select_fight(session, e.unit_instance_id)
        declare(session)
        finish_activation(session)
        r = begin(session)
    assert r.actor_id == "owner"
    assert {
        cast(str, cast(dict[str, JsonValue], o.payload)["unit_instance_id"]) for o in r.options
    } == {f.attached_unit_instance_id}
    r = select_fight(session, f.attached_unit_instance_id)
    rows = weapon_rows(r)
    assert {cast(str, row["model_instance_id"]) for row in rows} == set(
        u.own_model_ids() + leader.own_model_ids()
    )
    assert len({cast(str, row["weapon_instance_id"]) for row in rows}) == len(rows)
    result = declare(session)
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    finish_activation(session)
    assert (
        cast(
            str,
            cast(
                dict[str, JsonValue],
                events(session, "fight_activation_selected")[-1]["activation_selection"],
            )["unit_instance_id"],
        )
        == f.attached_unit_instance_id
    )


def test_native_definitions_reused_but_health_effects_placement_and_decisions_are_fresh(
    section12_definitions: Section02Definitions,
) -> None:
    s, u, e = engaged_case(section12_definitions)
    other, v, f = engaged_case(section12_definitions)
    assert u == v
    assert u is not v
    assert u.own_models[0] is not v.own_models[0]
    assert s.army_definitions is not other.army_definitions
    assert s.starting_strength_records is not other.starting_strength_records
    assert s.persisting_effects is not other.persisting_effects
    assert s.battlefield_state == other.battlefield_state
    assert s.battlefield_state is not other.battlefield_state
    checkpoint(s, FightPhaseStepKind.PILE_IN)
    session = session_for(section12_definitions, s)
    begin(session)
    result = submit_move(
        session, targets=(e.unit_instance_id,), witness=paths(s, (u.unit_instance_id,), 0.25)
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state != other.battlefield_state
    assert not other.persisting_effects
    assert other.fight_phase_state is None
    assert f == e


@pytest.mark.parametrize("kind", [ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE])
def test_unreachable_attached_member_may_approach_without_breaking_coherency(
    section12_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    from tests.support.section12_fixtures import set_pose

    s, u, leader, e, f = attached_case(section12_definitions)
    set_pose(s, leader, (Pose.at(6.45, 10),))
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
        engaged_ids=(f.attached_unit_instance_id, e.unit_instance_id),
    )
    session = session_for(section12_definitions, s)
    begin(session)
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=ConsolidationModeKind.ONGOING if kind is ProposalKind.CONSOLIDATE else None,
        witness=paths(s, (u.unit_instance_id, leader.unit_instance_id), 0.1),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert len(events(session, "fight_movement_completed")) == 1


def test_objective_consolidation_per_model_reachability_is_not_satisfied_by_another_member(
    section12_definitions: Section02Definitions,
) -> None:
    from dataclasses import replace

    from tests.support.section12_fixtures import LORD, add_native, set_pose

    s, u, leader, e, f = attached_case(section12_definitions)
    set_pose(s, e, (Pose.at(30, 10),), enemy=True)
    assert s.mission_setup is not None
    marker = replace(s.mission_setup.objective_markers[0], x_inches=14, y_inches=10)
    s.mission_setup = replace(s.mission_setup, objective_markers=(marker,))
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    foe = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(10, 30),))
    add_native(s, foe, (Pose.at(13, 30),), enemy=True)
    checkpoint(
        s,
        FightPhaseStepKind.CONSOLIDATE,
        engaged_ids=(
            f.attached_unit_instance_id,
            e.unit_instance_id,
            spare.unit_instance_id,
            foe.unit_instance_id,
        ),
    )
    session = session_for(section12_definitions, s)
    begin(session)
    before = s.battlefield_state
    result = submit_move(
        session,
        objective=marker.objective_marker_id,
        mode=ConsolidationModeKind.OBJECTIVE,
        witness=paths(s, (u.unit_instance_id, leader.unit_instance_id), 0.05),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        objective=marker.objective_marker_id,
        mode=ConsolidationModeKind.OBJECTIVE,
        witness=paths(s, (u.unit_instance_id, leader.unit_instance_id), 0.6),
        identity="both-in-range",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


@pytest.mark.parametrize("scene", ["unobstructed", "blocked", "blocked_decline"])
def test_objective_member_unable_to_reach_range_may_move_closer_behind_solid_wall(
    section12_definitions: Section02Definitions,
    scene: str,
) -> None:
    from dataclasses import replace

    from tests.support.section12_fixtures import LORD, add_native, set_pose
    from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
    from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
    from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

    s, u, leader, e, f = attached_case(section12_definitions)
    set_pose(s, u, (Pose.at(12, 10),))
    set_pose(s, e, (Pose.at(30, 10),), enemy=True)
    assert s.mission_setup is not None
    marker = replace(s.mission_setup.objective_markers[0], x_inches=16, y_inches=10)
    s.mission_setup = replace(s.mission_setup, objective_markers=(marker,))
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=11.15,
        center_y_inches=19.5,
        width_inches=0.1,
        depth_inches=21,
        display_template_id=None,
    )
    wall = TerrainFeatureDefinition(
        "constructed-objective-wall",
        TerrainFeatureKind.SEALED_BUILDINGS,
        11.15,
        19.5,
        0.1,
        21,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 11.15, 19.5, 0, 0.1, 21, 8),),
    )
    assert s.battlefield_state is not None
    if scene != "unobstructed":
        s.mission_setup = replace(s.mission_setup, terrain_features=(wall,))
        s.replace_battlefield_state(replace(s.battlefield_state, terrain_features=(wall,)))
    spare = section12_definitions.unit(LORD, identity="z-sentinel")
    foe = section12_definitions.unit(LORD, identity="z-sentinel", army_id="enemy")
    add_native(s, spare, (Pose.at(40, 30),))
    add_native(s, foe, (Pose.at(43, 30),), enemy=True)
    checkpoint(
        s,
        FightPhaseStepKind.CONSOLIDATE,
        engaged_ids=(
            f.attached_unit_instance_id,
            e.unit_instance_id,
            spare.unit_instance_id,
            foe.unit_instance_id,
        ),
    )
    session = session_for(section12_definitions, s)
    begin(session)
    witness = PathWitness.for_paths(
        (
            (u.own_model_ids()[0], (Pose.at(12, 10), Pose.at(12.1, 10))),
            (leader.own_model_ids()[0], (Pose.at(10, 12.5), Pose.at(10.1, 12.5))),
        )
    )
    result = submit_move(
        session,
        objective=marker.objective_marker_id if scene != "blocked_decline" else None,
        mode=ConsolidationModeKind.OBJECTIVE,
        witness=witness if scene != "blocked_decline" else None,
    )
    assert (result.status_kind is not LifecycleStatusKind.INVALID) == (scene != "unobstructed"), (
        result.to_payload()
    )
    assert len(events(session, "fight_movement_completed")) == int(scene != "unobstructed")
