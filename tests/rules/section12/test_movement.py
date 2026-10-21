"""12.03/12.08: real public path, target, ownership and endpoint consumers."""

from __future__ import annotations

from typing import cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section12_fixtures import (
    LORD,
    add_native,
    begin,
    checkpoint,
    engaged_case,
    events,
    move_payload,
    paths,
    session_for,
    submit_move,
)
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind, FightPhaseStepKind
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import MovementProposalRequest, ProposalKind
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose

KINDS = (ProposalKind.PILE_IN, ProposalKind.CONSOLIDATE)


def _case(
    d: Section02Definitions, kind: ProposalKind, *, gap: float = 1.5
) -> tuple[LocalGameSession, GameState, UnitInstance, UnitInstance]:
    s, u, e = engaged_case(d, gap=gap)
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
    )
    session = session_for(d, s)
    r = begin(session)
    assert (
        MovementProposalRequest.from_decision_request_payload(r.payload).unit_instance_id
        == u.unit_instance_id
    )
    return session, s, u, e


def _mode(kind: ProposalKind) -> ConsolidationModeKind | None:
    return ConsolidationModeKind.ONGOING if kind is ProposalKind.CONSOLIDATE else None


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "failure",
    [
        "away",
        "equal",
        "detour",
        "missing_target",
        "friendly_target",
        "unknown_target",
        "duplicate_target",
        "missing_witness",
    ],
)
def test_public_movement_rejects_bad_choice_without_displacement_and_continues(
    section12_definitions: Section02Definitions, kind: ProposalKind, failure: str
) -> None:
    session, s, u, e = _case(section12_definitions, kind)
    assert s.battlefield_state is not None
    before = s.battlefield_state.to_payload()
    r = pending(session)
    target: tuple[str, ...] = (e.unit_instance_id,)
    witness: PathWitness | None = paths(s, (u.unit_instance_id,), 0.25)
    if failure == "away":
        witness = paths(s, (u.unit_instance_id,), -0.1)
    if failure == "equal":
        from math import cos, sin

        distance = 1.574803149606299 + 1.5
        witness = paths(s, (u.unit_instance_id,), distance * (1 - cos(0.1)), distance * sin(0.1))
    if failure == "detour":
        p = s.battlefield_state.unit_placement_by_id(u.unit_instance_id).model_placements[0]
        witness = PathWitness.for_paths(
            ((p.model_instance_id, (p.pose, Pose.at(9, 12), Pose.at(10.25, 10))),)
        )
    if failure == "missing_target":
        target = ()
    if failure == "friendly_target":
        target = (u.unit_instance_id,)
    if failure == "unknown_target":
        target = ("enemy:absent",)
    if failure == "duplicate_target":
        target = (e.unit_instance_id, e.unit_instance_id)
    if failure == "missing_witness":
        witness = None
    payload = cast(
        dict[str, JsonValue], move_payload(r, targets=target, witness=witness, mode=_mode(kind))
    )
    # Missing targets plus witness is malformed, not the legal no-move schema.
    result = session.submit_parameterized_payload(
        request_id=r.request_id, result_id="invalid", payload=payload
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state.to_payload() == before
    assert not events(session, "fight_movement_completed")
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        witness=paths(s, (u.unit_instance_id,), 0.25),
        mode=_mode(kind),
        identity="retry",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    completed = events(session, "fight_movement_completed")
    assert len(completed) == 1
    assert cast(str, completed[0]["unit_instance_id"]) == u.unit_instance_id
    assert s.battlefield_state.to_payload() != before
    assert not events(session, "forced_fight_activation_queue_started")


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize(
    "drift", ["request", "unit", "inventory", "start", "endpoint_only", "malformed_mode"]
)
def test_schema_and_current_physical_authority_reject_before_commit(
    section12_definitions: Section02Definitions, kind: ProposalKind, drift: str
) -> None:
    session, s, u, e = _case(section12_definitions, kind)
    r = pending(session)
    before = s.battlefield_state
    witness = paths(s, (u.unit_instance_id,), 0.25)
    if drift == "inventory":
        witness = PathWitness.for_paths((("not-selected-model", witness.model_paths[0][1]),))
    if drift == "start":
        witness = PathWitness.for_paths(
            ((u.own_model_ids()[0], (Pose.at(9, 10), Pose.at(10.25, 10))),)
        )
    payload = cast(
        dict[str, JsonValue],
        move_payload(r, targets=(e.unit_instance_id,), witness=witness, mode=_mode(kind)),
    )
    if drift == "request":
        payload["proposal_request_id"] = "stale-request"
    if drift == "unit":
        payload["unit_instance_id"] = e.unit_instance_id
    if drift == "malformed_mode":
        payload["movement_mode"] = "normal"
    if drift == "endpoint_only":
        raw_witness = cast(dict[str, JsonValue], payload["witness"])
        raw_paths = cast(list[dict[str, JsonValue]], raw_witness["model_paths"])
        raw_paths[0]["poses"] = cast(list[JsonValue], raw_paths[0]["poses"])[1:]
    count = len(session.lifecycle.decision_controller.records)
    result = session.submit_parameterized_payload(
        request_id=r.request_id, result_id="authority-invalid", payload=payload
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    assert len(session.lifecycle.decision_controller.records) == count
    assert pending(session).request_id == r.request_id
    result = submit_move(session, identity="legal-decline")
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("moving", [False, True])
def test_enemy_base_contact_pins_models_but_does_not_require_movement(
    section12_definitions: Section02Definitions, kind: ProposalKind, moving: bool
) -> None:
    session, s, u, e = _case(section12_definitions, kind, gap=0)
    before = s.battlefield_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        witness=paths(s, (u.unit_instance_id,), 0, 0.1 if moving else 0),
        mode=_mode(kind),
    )
    assert (result.status_kind is LifecycleStatusKind.INVALID) == moving, result.to_payload()
    assert s.battlefield_state == before
    if moving:
        result = submit_move(session, identity="decline")
        assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


@pytest.mark.parametrize("kind", KINDS)
def test_every_engaged_target_is_mandatory_and_each_initial_engagement_survives(
    section12_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    s, u, e = engaged_case(section12_definitions, gap=0.5)
    left = section12_definitions.unit(LORD, army_id="enemy", identity="left")
    add_native(s, left, (Pose.at(10 - 1.574803149606299 - 1.9, 10),), enemy=True)
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
    )
    session = session_for(section12_definitions, s)
    begin(session)
    before = s.battlefield_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        witness=paths(s, (u.unit_instance_id,), 0.25),
        mode=_mode(kind),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id, left.unit_instance_id),
        witness=paths(s, (u.unit_instance_id,), 0.25),
        mode=_mode(kind),
        identity="break-left",
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id, left.unit_instance_id),
        witness=paths(s, (u.unit_instance_id,), 0.05),
        mode=_mode(kind),
        identity="keep-both",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    endpoint = cast(
        dict[str, JsonValue], events(session, "fight_movement_completed")[0]["resolution"]
    )
    assert set(
        cast(
            list[str],
            cast(dict[str, JsonValue], endpoint["endpoint_witness"])["engaged_after_unit_ids"],
        )
    ) == {e.unit_instance_id, left.unit_instance_id}


@pytest.mark.parametrize("kind", KINDS)
def test_must_approach_initially_closest_selected_target_not_just_any_target(
    section12_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    s, u, e = engaged_case(section12_definitions, gap=1.5)
    left = section12_definitions.unit(LORD, army_id="enemy", identity="closer")
    add_native(s, left, (Pose.at(10 - 1.574803149606299 - 0.5, 10),), enemy=True)
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
    )
    session = session_for(section12_definitions, s)
    begin(session)
    before = s.battlefield_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id, left.unit_instance_id),
        witness=paths(s, (u.unit_instance_id,), 0.1),
        mode=_mode(kind),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(
        session,
        targets=(e.unit_instance_id, left.unit_instance_id),
        witness=paths(s, (u.unit_instance_id,), -0.1),
        mode=_mode(kind),
        identity="closest",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()


@pytest.mark.parametrize("kind", KINDS)
def test_native_fight_path_obeys_real_solid_terrain_and_retries(
    section12_definitions: Section02Definitions, kind: ProposalKind
) -> None:
    from dataclasses import replace

    from tests.support.section12_fixtures import SPAWN
    from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
    from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
    from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition

    s, u, e = engaged_case(section12_definitions, datasheet=SPAWN)
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=11.2,
        center_y_inches=10,
        width_inches=0.1,
        depth_inches=1,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        "constructed-fight-wall",
        TerrainFeatureKind.SEALED_BUILDINGS,
        11.2,
        10,
        0.1,
        1,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 11.2, 10, 0, 0.1, 1, 5),),
    )
    assert s.battlefield_state is not None
    assert s.mission_setup is not None
    s.mission_setup = replace(s.mission_setup, terrain_features=(feature,))
    s.replace_battlefield_state(replace(s.battlefield_state, terrain_features=(feature,)))
    checkpoint(
        s,
        FightPhaseStepKind.PILE_IN
        if kind is ProposalKind.PILE_IN
        else FightPhaseStepKind.CONSOLIDATE,
    )
    session = session_for(section12_definitions, s)
    begin(session)
    before = s.battlefield_state
    result = submit_move(
        session,
        targets=(e.unit_instance_id,),
        mode=_mode(kind),
        witness=paths(s, (u.unit_instance_id,), 0.3),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
    result = submit_move(session, identity="legal-no-move")
    assert result.status_kind is not LifecycleStatusKind.INVALID, result.to_payload()
    assert s.battlefield_state == before
