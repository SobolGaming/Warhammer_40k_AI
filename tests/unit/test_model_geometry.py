from __future__ import annotations

import json
import math
from typing import cast

import pytest

from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZoneCircleCutout,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import (
    BaseShape,
    BaseShapePayload,
    CircularBase,
    OvalBase,
    RectangularBase,
    base_distance,
    base_shape_from_payload,
    bases_overlap,
)
from warhammer40k_core.geometry.pose import Facing, GeometryError, Point3, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex, SpatialIndexPayload
from warhammer40k_core.geometry.terrain import (
    ObstacleVolume,
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload, ModelVolume


def _model(model_id: str, x: float, y: float, z: float = 0.0) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _engagement_horizontal_inches() -> float:
    return RulesetDescriptor.warhammer_40000_eleventh().engagement_policy.horizontal_inches


def _engagement_vertical_inches() -> float:
    return RulesetDescriptor.warhammer_40000_eleventh().engagement_policy.vertical_inches


def test_base_overlap_and_distance_are_deterministic() -> None:
    first = CircularBase(radius=1.0)
    second = CircularBase(radius=1.0)
    first_pose = Pose.at(0.0, 0.0)
    overlapping_pose = Pose.at(1.5, 0.0)
    separated_pose = Pose.at(3.0, 0.0)

    assert bases_overlap(first, first_pose, second, overlapping_pose)
    assert math.isclose(base_distance(first, first_pose, second, separated_pose), 1.0)
    assert not bases_overlap(first, first_pose, second, separated_pose)


def test_deployment_zone_footprint_intersection_uses_shape_not_bounds() -> None:
    triangular_zone = DeploymentZone(
        deployment_zone_id="triangle",
        player_id="player-a",
        shape=DeploymentZoneShape(
            polygons=(
                DeploymentZonePolygon(
                    vertices=(
                        DeploymentZonePoint(0.0, 0.0),
                        DeploymentZonePoint(10.0, 0.0),
                        DeploymentZonePoint(0.0, 10.0),
                    )
                ),
            )
        ),
    )
    cutout_zone = DeploymentZone(
        deployment_zone_id="cutout",
        player_id="player-a",
        shape=DeploymentZoneShape(
            polygons=DeploymentZoneShape.rectangle(
                min_x=0.0,
                min_y=0.0,
                max_x=12.0,
                max_y=12.0,
            ).polygons,
            cutouts=(DeploymentZoneCircleCutout(center_x=12.0, center_y=12.0, radius=4.0),),
        ),
    )
    base = CircularBase(radius=0.25)

    assert not shapely_backend.base_footprint_intersects_deployment_zone(
        base,
        Pose.at(9.0, 9.0),
        triangular_zone,
    )
    assert shapely_backend.base_footprint_intersects_deployment_zone(
        base,
        Pose.at(2.0, 2.0),
        triangular_zone,
    )
    assert not shapely_backend.base_footprint_intersects_deployment_zone(
        base,
        Pose.at(10.0, 10.0),
        cutout_zone,
    )


def test_circular_base_edge_contact_has_zero_distance_and_overlaps() -> None:
    first = CircularBase(radius=1.0)
    second = CircularBase(radius=0.5)
    first_pose = Pose.at(0.0, 0.0)
    touching_pose = Pose.at(1.5, 0.0)

    assert math.isclose(base_distance(first, first_pose, second, touching_pose), 0.0)
    assert bases_overlap(first, first_pose, second, touching_pose)


def test_oval_base_distance_and_overlap_use_exact_footprints() -> None:
    first = OvalBase(length=4.0, width=1.0)
    second = OvalBase(length=4.0, width=1.0)
    first_pose = Pose.at(0.0, 0.0)
    separated_pose = Pose.at(0.0, 1.2)

    assert math.isclose(base_distance(first, first_pose, second, separated_pose), 0.2)
    assert not bases_overlap(first, first_pose, second, separated_pose)


def test_oval_base_uses_pose_facing_for_footprint_radius() -> None:
    oval = OvalBase(length=4.0, width=2.0)

    assert math.isclose(oval.radius_at_angle(0.0, Facing(0.0)), 2.0)
    assert math.isclose(oval.radius_at_angle(90.0, Facing(0.0)), 1.0)
    assert math.isclose(oval.radius_at_angle(90.0, Facing(90.0)), 2.0)


def test_rectangular_base_validates_and_uses_facing_for_footprint_radius() -> None:
    rectangle = RectangularBase(length=2.0, width=4.0)

    assert math.isclose(rectangle.radius_at_angle(0.0, Facing(0.0)), 1.0)
    assert math.isclose(rectangle.radius_at_angle(90.0, Facing(0.0)), 2.0)
    assert math.isclose(rectangle.radius_at_angle(0.0, Facing(90.0)), 2.0)

    with pytest.raises(GeometryError):
        RectangularBase(length=0.0, width=1.0)
    with pytest.raises(GeometryError):
        RectangularBase(length=1.0, width=0.0)
    with pytest.raises(GeometryError):
        RectangularBase(length=float("inf"), width=1.0)


def test_rectangular_base_payload_round_trips_without_object_reprs() -> None:
    rectangle = RectangularBase(length=2.0, width=4.0)
    blob = json.dumps(rectangle.to_payload(), sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert "POLYGON" not in blob
    assert (
        base_shape_from_payload(cast(BaseShapePayload, json.loads(blob))).to_payload()
        == rectangle.to_payload()
    )


def test_rectangular_base_distance_uses_exact_footprints() -> None:
    rectangle = RectangularBase(length=2.0, width=1.0)
    circle = CircularBase(radius=0.5)

    assert math.isclose(
        base_distance(rectangle, Pose.at(0.0, 0.0), circle, Pose.at(2.0, 0.0)),
        0.5,
    )
    assert math.isclose(
        base_distance(
            rectangle,
            Pose.at(0.0, 0.0, facing_degrees=90.0),
            circle,
            Pose.at(1.2, 0.0),
        ),
        0.2,
    )


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
    second = _model("second", 3.0, 0.0)
    elevated = _model("elevated", 0.0, 0.0, z=8.0)

    assert math.isclose(first.base_distance_to(second), 2.0)
    assert math.isclose(first.range_to(second), 2.0)
    assert first.is_within_engagement_range(
        second,
        horizontal_inches=_engagement_horizontal_inches(),
        vertical_inches=_engagement_vertical_inches(),
    )
    assert math.isclose(first.range_to(elevated), 6.0)
    assert not first.is_within_engagement_range(
        elevated,
        horizontal_inches=_engagement_horizontal_inches(),
        vertical_inches=_engagement_vertical_inches(),
    )


def test_terrain_volume_intersects_model_footprints_and_height() -> None:
    terrain = TerrainVolume(
        terrain_id="ruin-floor",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=2.0,
        depth=2.0,
        height=3.0,
    )

    assert terrain.stable_identity() == "terrain:ruin-floor"
    assert terrain.intersects_model(_model("touching", 1.5, 0.0))
    assert not terrain.intersects_model(_model("clear", 3.0, 0.0))
    assert not terrain.intersects_model(_model("above", 0.0, 0.0, z=4.0))


def test_terrain_intersection_uses_exact_model_footprint() -> None:
    terrain = TerrainVolume(
        terrain_id="ruin-floor",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=2.0,
        depth=2.0,
        height=3.0,
    )
    oval_model = Model(
        model_id="oval-clear",
        pose=Pose.at(0.0, 1.6),
        base=OvalBase(length=4.0, width=1.0),
        volume=ModelVolume(height=2.0),
    )

    assert not terrain.intersects_model(oval_model)


def test_line_of_sight_segment_blocking_uses_obstacle_volume() -> None:
    wall = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(0.0, 0.0, 0.0),
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


def test_los_segment_crossing_footprint_above_obstacle_does_not_block() -> None:
    wall = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(-8.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )

    assert not wall.blocks_line_segment(
        Point3(-10.0, 0.0, 10.0),
        Point3(10.0, 0.0, 0.0),
    )


def test_los_segment_crossing_footprint_at_obstacle_height_blocks() -> None:
    wall = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(-8.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )

    assert wall.blocks_line_segment(
        Point3(-10.0, 0.0, 2.0),
        Point3(10.0, 0.0, 2.0),
    )


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


def test_model_geometry_payloads_round_trip_without_object_reprs() -> None:
    model = Model(
        model_id="outrider-1",
        pose=Pose.at(2.0, 3.0, z=1.0, facing_degrees=45.0),
        base=OvalBase(length=3.5, width=1.5),
        volume=ModelVolume(height=2.25),
    )
    blob = json.dumps(model.to_payload(), sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert "POLYGON" not in blob
    assert (
        Model.from_payload(cast(ModelPayload, json.loads(blob))).to_payload() == model.to_payload()
    )


def test_terrain_payloads_round_trip_without_object_reprs() -> None:
    terrain = TerrainVolume(
        terrain_id="ruin-floor",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=6.0,
        depth=4.0,
        height=2.0,
    )
    obstacle = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )
    for volume in (terrain, obstacle):
        blob = json.dumps(volume.to_payload(), sort_keys=True)

        assert "<" not in blob
        assert "object at 0x" not in blob
        assert "POLYGON" not in blob
        assert (
            terrain_volume_from_payload(cast(TerrainVolumePayload, json.loads(blob))).to_payload()
            == volume.to_payload()
        )

    obstacle_blob = json.dumps(obstacle.to_payload(), sort_keys=True)
    assert (
        ObstacleVolume.from_payload(
            cast(TerrainVolumePayload, json.loads(obstacle_blob))
        ).to_payload()
        == obstacle.to_payload()
    )


def test_spatial_index_payload_round_trips_without_object_reprs() -> None:
    model = _model("intercessor-1", 0.0, 0.0)
    obstacle = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(3.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )
    index = SpatialIndex.empty().with_model(model).with_terrain(obstacle)
    blob = json.dumps(index.to_payload(), sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert "POLYGON" not in blob
    assert (
        SpatialIndex.from_payload(cast(SpatialIndexPayload, json.loads(blob))).to_payload()
        == index.to_payload()
    )
