# pyright: reportPrivateUsage=false
"""Order 100: based FRAME models are measured from every part."""

from __future__ import annotations

import json
from dataclasses import replace

from tests.order85_overhang_helpers import overhang_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import geometry_model_for_placement
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.transport_disembark_geometry import (
    _model_wholly_within_any_transport_model,
)
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.measurement import (
    OBJECTIVE_MARKER_DIAMETER_INCHES,
    DistanceMeasurementContext,
    objective_marker_controls_model,
)
from warhammer40k_core.geometry.movement_reachability import MovementGoal
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain_area_visibility import (
    TerrainVisibilityArea,
    model_intersects_terrain_area,
)
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model


def _session(*, frame: bool) -> LocalGameSession:
    return overhang_session(start_y=8, enemy_keywords=("FRAME",) if frame else ())


def _pair(session: LocalGameSession) -> tuple[Model, Model]:
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    source = state.army_definitions[0].units[0]
    target = state.army_definitions[1].units[0]
    battlefield = state.battlefield_state
    return (
        geometry_model_for_placement(
            model=source.own_models[0],
            placement=battlefield.unit_placement_by_id(source.unit_instance_id).model_placements[0],
        ),
        geometry_model_for_placement(
            model=target.own_models[0],
            placement=battlefield.unit_placement_by_id(target.unit_instance_id).model_placements[0],
        ),
    )


def _terrain_strip() -> TerrainVisibilityArea:
    return TerrainVisibilityArea(
        "frame-area",
        ("frame-area",),
        TerrainAreaClassification.LIGHT,
        (((9.5, 10.25), (10.5, 10.25), (10.5, 10.75), (9.5, 10.75)),),
    )


def test_based_frame_wholly_within_includes_every_part() -> None:
    source, frame = _pair(_session(frame=True))
    _source, support_only = _pair(_session(frame=False))
    context = DistanceMeasurementContext.from_models(source, frame)
    support_context = DistanceMeasurementContext.from_models(source, support_only)

    assert frame.measures_every_part is True
    assert support_only.measures_every_part is False
    assert frame.body_parts[0].base.max_radius() > frame.base.max_radius()
    assert context.target_wholly_within_distance(8.5) is False
    assert support_context.target_wholly_within_distance(8.5) is True
    assert context.target_wholly_within_distance(12) is True
    assert (
        _model_wholly_within_any_transport_model(
            frame, transport_models=(source,), distance_inches=8.5
        )
        is False
    )


def test_based_frame_engagement_and_movement_use_the_body() -> None:
    session = _session(frame=True)
    state = session.lifecycle.state
    assert state is not None
    source, frame = _pair(session)
    plain = _session(frame=False)
    plain_state = plain.lifecycle.state
    assert plain_state is not None
    plain_source, support_only = _pair(plain)
    goal = MovementGoal(models=(source,), horizontal_inches=2.0, vertical_inches=5.0)

    assert source.base_distance_to(frame) > 2
    assert frame.rules_horizontal_distance_to(source) <= 2
    assert plain_source.range_to(support_only) == plain_source.base_distance_to(support_only)
    assert (
        unit_within_enemy_engagement_range(
            state=state, unit_instance_id=state.army_definitions[0].units[0].unit_instance_id
        )
        is True
    )
    assert (
        unit_within_enemy_engagement_range(
            state=plain_state,
            unit_instance_id=plain_state.army_definitions[0].units[0].unit_instance_id,
        )
        is False
    )
    assert goal.contains(frame) is True
    assert goal.contains(support_only) is False


def test_based_frame_terrain_and_objective_membership_use_the_body() -> None:
    _source, frame = _pair(_session(frame=True))
    area = _terrain_strip()
    support_only = replace(frame, measures_every_part=False)
    elevated = replace(frame, pose=Pose.at(frame.pose.position.x, frame.pose.position.y, 10))
    marker_radius = OBJECTIVE_MARKER_DIAMETER_INCHES / 2
    center_distance = frame.base.max_radius() + marker_radius + 3.2
    marker = Pose.at(frame.pose.position.x, frame.pose.position.y - center_distance)

    assert model_intersects_terrain_area(frame, area) is True
    assert model_intersects_terrain_area(support_only, area) is False
    assert model_intersects_terrain_area(elevated, area) is True
    assert objective_marker_controls_model(marker, frame) is True
    assert objective_marker_controls_model(marker, support_only) is False


def test_based_frame_engagement_restores_for_both_viewers_and_replays() -> None:
    session = _session(frame=True)
    state = session.lifecycle.state
    assert state is not None
    source_id = state.army_definitions[0].units[0].unit_instance_id
    checkpoint = json.loads(json.dumps(session.to_persistence_payload()))
    restored = LocalGameSession.from_persistence_payload(checkpoint)
    restored_state = restored.lifecycle.state
    assert restored_state is not None

    assert unit_within_enemy_engagement_range(state=state, unit_instance_id=source_id) is True
    assert (
        unit_within_enemy_engagement_range(state=restored_state, unit_instance_id=source_id) is True
    )
    assert restored.to_persistence_payload() == checkpoint
    assert restored.view(viewer_player_id="player-a") == session.view(viewer_player_id="player-a")
    assert restored.view(viewer_player_id="player-b") == session.view(viewer_player_id="player-b")
    assert restored.events_since(
        EventStreamCursor(), viewer_player_id="player-a"
    ) == session.events_since(EventStreamCursor(), viewer_player_id="player-a")
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order100")).run()
    assert replay.status is ReplayRunStatus.REPRODUCED
