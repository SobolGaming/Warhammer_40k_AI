"""SF21-R001: finite declaration must reach real dense terrain transit authority."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state
from tests.support.section03_session import movement_session
from tests.support.section09_fixtures import add_unit, attach_mission, begin, events, propose
from tests.support.section21_fixtures import LORD, SERPENT
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalPayload,
    MovementProposalRequest,
)
from warhammer40k_core.engine.phase import LifecycleStatus, LifecycleStatusKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification


@pytest.mark.parametrize("skies", [False, True])
def test_native_public_flight_crosses_dense_wall_after_explicit_declaration(
    section21_definitions: Section02Definitions, skies: bool
) -> None:
    d = section21_definitions
    unit = d.unit(SERPENT)
    state = native_state(
        d,
        unit,
        (Pose.at(10, 10),),
        enemy=d.unit(LORD, army_id="enemy", identity="observer"),
        enemy_poses=(Pose.at(35, 30),),
    )
    attach_mission(state)
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(10, 35),))
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=16,
        center_y_inches=10,
        width_inches=0.5,
        depth_inches=8,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        "s21:dense-wall",
        TerrainFeatureKind.SEALED_BUILDINGS,
        16,
        10,
        0.5,
        8,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 16, 10, 0, 0.5, 8, 12),),
        classification=TerrainAreaClassification.DENSE,
    )
    assert state.battlefield_state is not None
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        deployment_map_id="constructed:s21:deployment",
        terrain_layout_id="constructed:s21:dense-wall",
        terrain_features=(feature,),
        battlefield_regions=(),
    )
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(feature,)))
    session = movement_session(d, state)
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:wall-unit", option_id=unit.unit_instance_id
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:wall-mode",
        option_id="normal_move:fly_take_to_skies" if skies else "normal_move",
    )
    assert status.decision_request is not None
    request = status.decision_request
    assert request is not None
    before = state.battlefield_state
    status = propose(session, request, unit, (Pose.at(22, 10),))
    assert (status.status_kind is not LifecycleStatusKind.INVALID) is skies, status.to_payload()
    if skies:
        assert state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements[
            0
        ].pose == Pose.at(22, 10)
        assert len(events(session, "movement_activation_completed")) == 1
    else:
        assert state.battlefield_state == before
        assert not events(session, "movement_activation_completed")


def _floor_scene(
    d: Section02Definitions, classification: TerrainAreaClassification, *, skies: bool
) -> tuple[LocalGameSession, GameState, UnitInstance, DecisionRequest]:
    unit = d.unit(SERPENT)
    state = native_state(
        d,
        unit,
        (Pose.at(10, 10),),
        enemy=d.unit(LORD, army_id="enemy", identity="observer"),
        enemy_poses=(Pose.at(35, 30),),
    )
    attach_mission(state)
    add_unit(state, d.unit(LORD, identity="spare"), (Pose.at(10, 35),))
    # Ground controls total exactly native M14 (6 horizontal + 8 vertical),
    # isolating floor permission from an over-budget path. Selected flight uses
    # the independent review's 12-horizontal/16-vertical path and M12 budget.
    center, width, height = (16, 6, 5) if skies else (13, 1, 3)
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center,
        center_y_inches=10,
        width_inches=width,
        depth_inches=8,
        display_template_id=None,
    )
    feature = TerrainFeatureDefinition(
        "s21:floor",
        TerrainFeatureKind.SEALED_BUILDINGS,
        center,
        10,
        width,
        8,
        display.footprint_polygon,
        display,
        floors=(TerrainFloorDefinition("floor", center, 10, height, width, 8, 0.1),),
        classification=classification,
    )
    assert state.mission_setup is not None
    assert state.battlefield_state is not None
    state.mission_setup = replace(
        state.mission_setup,
        deployment_map_id="constructed:s21:deployment",
        terrain_layout_id="constructed:s21:floor",
        terrain_features=(feature,),
        battlefield_regions=(),
    )
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=(feature,)))
    session = movement_session(d, state)
    request = begin(session)
    status = session.submit_option(
        request_id=request.request_id, result_id="s21:floor-unit", option_id=unit.unit_instance_id
    )
    assert status.decision_request is not None
    request = status.decision_request
    status = session.submit_option(
        request_id=request.request_id,
        result_id="s21:floor-mode",
        option_id="normal_move:fly_take_to_skies" if skies else "normal_move",
    )
    assert status.decision_request is not None
    return session, state, unit, status.decision_request


def _floor_path(*, skies: bool, descend: bool) -> tuple[Pose, ...]:
    center, end, top = (16, 22, 8) if skies else (13, 16, 4)
    if descend:
        return (
            Pose.at(10, 10),
            Pose.at(10, 10, top),
            Pose.at(center, 10, top),
            Pose.at(center, 10),
            Pose.at(end, 10),
        )
    return (
        Pose.at(10, 10),
        Pose.at(center, 10),
        Pose.at(center, 10, top),
        Pose.at(end, 10, top),
        Pose.at(end, 10),
    )


def _submit_floor_path(
    session: LocalGameSession,
    unit: UnitInstance,
    request: DecisionRequest,
    path: tuple[Pose, ...],
    *,
    skies: bool,
) -> LifecycleStatus:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    return session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="s21:floor-path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=unit.unit_instance_id,
                movement_phase_action="normal_move",
                movement_mode="fly_take_to_skies" if skies else "normal",
                witness=PathWitness.for_paths(((unit.own_model_ids()[0], path),)),
            ).to_payload()
        ),
    )


@pytest.mark.parametrize(
    "classification",
    [
        TerrainAreaClassification.UNKNOWN,
        TerrainAreaClassification.DENSE,
        TerrainAreaClassification.MIXED,
    ],
)
@pytest.mark.parametrize("descend", [False, True])
def test_native_selected_flight_crosses_floor_in_both_vertical_directions(
    section21_definitions: Section02Definitions,
    classification: TerrainAreaClassification,
    descend: bool,
) -> None:
    session, state, unit, request = _floor_scene(section21_definitions, classification, skies=True)
    status = _submit_floor_path(
        session, unit, request, _floor_path(skies=True, descend=descend), skies=True
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID, status.to_payload()
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_by_id(unit.unit_instance_id).model_placements[
        0
    ].pose == Pose.at(22, 10)
    assert len(state.model_movement_history) == 1
    assert state.model_movement_history[0].distance_inches == 12
    assert len(events(session, "movement_activation_completed")) == 1


@pytest.mark.parametrize(
    "classification", [TerrainAreaClassification.DENSE, TerrainAreaClassification.MIXED]
)
@pytest.mark.parametrize("descend", [False, True])
def test_intrinsic_fly_without_selection_keeps_dense_floor_restriction(
    section21_definitions: Section02Definitions,
    classification: TerrainAreaClassification,
    descend: bool,
) -> None:
    session, state, unit, request = _floor_scene(section21_definitions, classification, skies=False)
    before = state.battlefield_state
    status = _submit_floor_path(
        session, unit, request, _floor_path(skies=False, descend=descend), skies=False
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert "dense_floor_transit_forbidden" in str(status.to_payload())
    assert state.battlefield_state == before
    assert not state.model_movement_history
    assert not events(session, "movement_activation_completed")


@pytest.mark.parametrize(
    "classification", [TerrainAreaClassification.DENSE, TerrainAreaClassification.MIXED]
)
@pytest.mark.parametrize("endpoint", [Pose.at(16, 10, 5.05), Pose.at(22, 10, 8)])
def test_selected_vertical_floor_transit_keeps_body_and_support_endpoint_checks(
    section21_definitions: Section02Definitions,
    classification: TerrainAreaClassification,
    endpoint: Pose,
) -> None:
    session, state, unit, request = _floor_scene(section21_definitions, classification, skies=True)
    before = state.battlefield_state
    status = _submit_floor_path(
        session,
        unit,
        request,
        (Pose.at(10, 10), Pose.at(16, 10), Pose.at(16, 10, 8), endpoint),
        skies=True,
    )
    assert status.status_kind is LifecycleStatusKind.INVALID, status.to_payload()
    assert "model_cannot_be_placed_at_endpoint" in str(status.to_payload())
    assert state.battlefield_state == before
    assert not state.model_movement_history
    assert not events(session, "movement_activation_completed")
