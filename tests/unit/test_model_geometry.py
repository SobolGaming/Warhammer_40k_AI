from __future__ import annotations

import math
from typing import cast

import pytest

from warhammer40k_core.geometry.base import (
    BaseShape,
    CircularBase,
    OvalBase,
    base_distance,
    bases_overlap,
)
from warhammer40k_core.geometry.pose import Facing, GeometryError, Point3, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import ObstacleVolume, TerrainVolume
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _model(model_id: str, x: float, y: float, z: float = 0.0) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def test_base_overlap_and_distance_are_deterministic() -> None:
    first = CircularBase(radius=1.0)
    second = CircularBase(radius=1.0)
    first_pose = Pose.at(0.0, 0.0)
    overlapping_pose = Pose.at(1.5, 0.0)
    separated_pose = Pose.at(3.0, 0.0)

    assert bases_overlap(first, first_pose, second, overlapping_pose)
    assert math.isclose(base_distance(first, first_pose, second, separated_pose), 1.0)
    assert not bases_overlap(first, first_pose, second, separated_pose)


def test_oval_base_uses_pose_facing_for_footprint_radius() -> None:
    oval = OvalBase(length=4.0, width=2.0)

    assert math.isclose(oval.radius_at_angle(0.0, Facing(0.0)), 2.0)
    assert math.isclose(oval.radius_at_angle(90.0, Facing(0.0)), 1.0)
    assert math.isclose(oval.radius_at_angle(90.0, Facing(90.0)), 2.0)


def test_model_has_stable_identity_and_requires_geometry() -> None:
    model = _model("intercessor-1", 0.0, 0.0)
    index = SpatialIndex.empty().with_model(model)

    assert model.stable_identity() == "model:intercessor-1"
    assert index.models == (model,)

    with pytest.raises(GeometryError):
        Model(
            model_id="model:intercessor-2",
            pose=Pose.at(0.0, 0.0),
            base=CircularBase(radius=0.5),
            volume=ModelVolume(height=2.0),
        )
    with pytest.raises(GeometryError):
        Model(
            model_id="missing-base",
            pose=Pose.at(0.0, 0.0),
            base=cast(BaseShape, None),
            volume=ModelVolume(height=2.0),
        )
    with pytest.raises(GeometryError):
        SpatialIndex.empty().with_model(cast(Model, "not-a-model"))


def test_model_range_and_engagement_use_2_5d_volume_distance() -> None:
    first = _model("first", 0.0, 0.0)
    second = _model("second", 2.0, 0.0)
    elevated = _model("elevated", 0.0, 0.0, z=8.0)

    assert math.isclose(first.base_distance_to(second), 1.0)
    assert math.isclose(first.range_to(second), 1.0)
    assert first.is_within_engagement_range(second)
    assert math.isclose(first.range_to(elevated), 6.0)
    assert not first.is_within_engagement_range(elevated)


def test_terrain_volume_intersects_model_footprints_and_height() -> None:
    terrain = TerrainVolume(
        terrain_id="ruin-floor",
        center=Point3(0.0, 0.0, 0.0),
        width=2.0,
        depth=2.0,
        height=3.0,
    )

    assert terrain.stable_identity() == "terrain:ruin-floor"
    assert terrain.intersects_model(_model("touching", 1.5, 0.0))
    assert not terrain.intersects_model(_model("clear", 3.0, 0.0))
    assert not terrain.intersects_model(_model("above", 0.0, 0.0, z=4.0))


def test_line_of_sight_segment_blocking_uses_obstacle_volume() -> None:
    wall = ObstacleVolume(
        terrain_id="wall",
        center=Point3(0.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )
    index = SpatialIndex.empty().with_terrain(wall)

    assert wall.blocks_line_segment(Point3(-3.0, 0.0, 1.0), Point3(3.0, 0.0, 1.0))
    assert not wall.blocks_line_segment(Point3(-3.0, 3.0, 1.0), Point3(3.0, 3.0, 1.0))
    assert not wall.blocks_line_segment(Point3(-3.0, 0.0, 5.0), Point3(3.0, 0.0, 5.0))
    assert index.line_of_sight_blockers(Point3(-3.0, 0.0, 1.0), Point3(3.0, 0.0, 1.0)) == (wall,)
    assert not index.has_clear_line_of_sight(Point3(-3.0, 0.0, 1.0), Point3(3.0, 0.0, 1.0))
    assert index.has_clear_line_of_sight(Point3(-3.0, 3.0, 1.0), Point3(3.0, 3.0, 1.0))


def test_spatial_index_orders_entries_and_rejects_duplicates() -> None:
    second = _model("second", 3.0, 0.0)
    first = _model("first", 0.0, 0.0)
    wall_b = ObstacleVolume("wall-b", Point3(3.0, 0.0, 0.0), 1.0, 1.0, 2.0)
    wall_a = ObstacleVolume("wall-a", Point3(0.0, 0.0, 0.0), 1.0, 1.0, 2.0)

    index = (
        SpatialIndex.empty()
        .with_model(second)
        .with_model(first)
        .with_terrain(wall_b)
        .with_terrain(wall_a)
    )

    assert tuple(model.model_id for model in index.models) == ("first", "second")
    assert tuple(volume.terrain_id for volume in index.terrain) == ("wall-a", "wall-b")
    assert index.generation == 4

    with pytest.raises(GeometryError):
        index.with_model(_model("first", 6.0, 0.0))
    with pytest.raises(GeometryError):
        index.with_terrain(ObstacleVolume("wall-a", Point3(6.0, 0.0, 0.0), 1.0, 1.0, 2.0))
