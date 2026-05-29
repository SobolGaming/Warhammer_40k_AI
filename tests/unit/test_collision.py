from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.collision import CollisionSet, CollisionSetPayload
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _model(model_id: str, x: float, y: float, z: float = 0.0) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _terrain(terrain_id: str, x: float, y: float, z: float = 0.0) -> TerrainVolume:
    return TerrainVolume(
        terrain_id=terrain_id,
        bottom_center=Point3(x, y, z),
        width=1.0,
        depth=1.0,
        height=2.0,
    )


def test_collision_set_orders_blockers_and_filters_queries_by_geometry() -> None:
    mover = _model("mover", 0.0, 0.0)
    overlapping_b = _model("blocker-b", 0.25, 0.0)
    overlapping_a = _model("blocker-a", 0.5, 0.0)
    elevated = _model("blocker-elevated", 0.0, 0.0, z=4.0)
    far_terrain = _terrain("terrain-a", 10.0, 0.0)
    colliding_terrain = _terrain("terrain-b", 0.0, 0.0)
    enemy_b = _model("enemy-b", 1.25, 0.0)
    enemy_a = _model("enemy-a", 1.1, 0.0)
    far_enemy = _model("enemy-far", 10.0, 0.0)

    collision_set = CollisionSet(
        model_blockers=(overlapping_b, elevated, overlapping_a),
        terrain_blockers=(colliding_terrain, far_terrain),
        engagement_blockers=(enemy_b, far_enemy, enemy_a),
    )

    assert tuple(model.model_id for model in collision_set.model_blockers) == (
        "blocker-a",
        "blocker-b",
        "blocker-elevated",
    )
    assert tuple(terrain.terrain_id for terrain in collision_set.terrain_blockers) == (
        "terrain-a",
        "terrain-b",
    )
    assert tuple(model.model_id for model in collision_set.engagement_blockers) == (
        "enemy-a",
        "enemy-b",
        "enemy-far",
    )
    assert collision_set.colliding_model_ids(mover) == ("blocker-a", "blocker-b")
    assert collision_set.colliding_terrain_ids(mover) == ("terrain-b",)
    assert collision_set.engagement_model_ids(
        mover,
        horizontal_inches=1.0,
        vertical_inches=5.0,
    ) == ("enemy-a", "enemy-b")


def test_collision_queries_report_broadphase_rejections_before_exact_checks() -> None:
    mover = _model("mover", 0.0, 0.0)
    overlapping = _model("overlap", 0.5, 0.0)
    far_model = _model("far-model", 20.0, 0.0)
    colliding_terrain = _terrain("colliding-terrain", 0.0, 0.0)
    far_terrain = _terrain("far-terrain", 20.0, 0.0)
    near_enemy = _model("near-enemy", 1.25, 0.0)
    far_enemy = _model("far-enemy", 20.0, 0.0)
    collision_set = CollisionSet(
        model_blockers=(far_model, overlapping),
        terrain_blockers=(far_terrain, colliding_terrain),
        engagement_blockers=(far_enemy, near_enemy),
    )

    model_result = collision_set.model_collision_query(mover)
    terrain_result = collision_set.terrain_collision_query(mover)
    engagement_result = collision_set.engagement_query(
        mover,
        horizontal_inches=1.0,
        vertical_inches=5.0,
    )

    assert model_result.blocker_ids == ("overlap",)
    assert model_result.broadphase_check_count == 2
    assert model_result.exact_check_count == 1
    assert model_result.broadphase_rejection_count == 1
    assert terrain_result.blocker_ids == ("colliding-terrain",)
    assert terrain_result.broadphase_check_count == 2
    assert terrain_result.exact_check_count == 1
    assert terrain_result.broadphase_rejection_count == 1
    assert engagement_result.blocker_ids == ("near-enemy",)
    assert engagement_result.broadphase_check_count == 2
    assert engagement_result.exact_check_count == 1
    assert engagement_result.broadphase_rejection_count == 1


def test_collision_set_from_spatial_index_excludes_movers_and_selects_engagement() -> None:
    mover = _model("mover", 0.0, 0.0)
    support = _model("support", 3.0, 0.0)
    enemy = _model("enemy", 1.0, 0.0)
    terrain = _terrain("wall", 2.0, 0.0)
    spatial_index = (
        SpatialIndex.empty()
        .with_model(enemy)
        .with_model(mover)
        .with_model(support)
        .with_terrain(terrain)
    )

    collision_set = CollisionSet.from_spatial_index(
        spatial_index,
        moving_model_ids=(" mover ",),
        engagement_model_ids=("enemy",),
    )

    assert tuple(model.model_id for model in collision_set.model_blockers) == ("enemy", "support")
    assert tuple(terrain.terrain_id for terrain in collision_set.terrain_blockers) == ("wall",)
    assert tuple(model.model_id for model in collision_set.engagement_blockers) == ("enemy",)


def test_collision_set_payload_round_trips_all_blocker_types_without_object_reprs() -> None:
    collision_set = CollisionSet(
        model_blockers=(_model("blocker", 2.0, 0.0),),
        terrain_blockers=(_terrain("wall", 4.0, 0.0),),
        engagement_blockers=(_model("enemy", 1.0, 0.0),),
    )
    payload = collision_set.to_payload()
    blob = json.dumps(payload, sort_keys=True)

    assert "<" not in blob
    assert "object at 0x" not in blob
    assert "POLYGON" not in blob
    assert (
        CollisionSet.from_payload(cast(CollisionSetPayload, json.loads(blob))).to_payload()
        == payload
    )


def test_collision_set_rejects_invalid_collections_and_blocker_types() -> None:
    model = _model("model", 0.0, 0.0)
    terrain = _terrain("terrain", 0.0, 0.0)

    with pytest.raises(GeometryError, match="model_blockers must be a tuple"):
        CollisionSet(model_blockers=cast(tuple[Model, ...], [model]))
    with pytest.raises(GeometryError, match="terrain_blockers must be a tuple"):
        CollisionSet(terrain_blockers=cast(tuple[TerrainVolume, ...], [terrain]))
    with pytest.raises(GeometryError, match="engagement_blockers must be a tuple"):
        CollisionSet(engagement_blockers=cast(tuple[Model, ...], [model]))
    with pytest.raises(GeometryError, match="model_blocker must be a Model"):
        CollisionSet(model_blockers=(cast(Model, "model"),))
    with pytest.raises(GeometryError, match="terrain_blocker must be a TerrainVolume"):
        CollisionSet(terrain_blockers=(cast(TerrainVolume, "terrain"),))
    with pytest.raises(GeometryError, match="engagement_blocker must be a Model"):
        CollisionSet(engagement_blockers=(cast(Model, "model"),))


def test_collision_set_rejects_duplicate_blocker_ids() -> None:
    model = _model("duplicate", 0.0, 0.0)
    terrain = _terrain("duplicate-terrain", 0.0, 0.0)

    with pytest.raises(GeometryError, match="model_blockers must not contain duplicate"):
        CollisionSet(model_blockers=(model, model))
    with pytest.raises(GeometryError, match="engagement_blockers must not contain duplicate"):
        CollisionSet(engagement_blockers=(model, model))
    with pytest.raises(GeometryError, match="terrain_blockers must not contain duplicate"):
        CollisionSet(terrain_blockers=(terrain, terrain))


def test_collision_set_rejects_invalid_spatial_index_inputs() -> None:
    spatial_index = SpatialIndex.empty().with_model(_model("mover", 0.0, 0.0))

    with pytest.raises(GeometryError, match="spatial_index must be a SpatialIndex"):
        CollisionSet.from_spatial_index(cast(SpatialIndex, "index"), moving_model_ids=())
    with pytest.raises(GeometryError, match="moving_model_ids must be a tuple"):
        CollisionSet.from_spatial_index(
            spatial_index,
            moving_model_ids=cast(tuple[str, ...], ["mover"]),
        )
    with pytest.raises(GeometryError, match="moving_model_ids values must be strings"):
        CollisionSet.from_spatial_index(
            spatial_index,
            moving_model_ids=cast(tuple[str, ...], (1,)),
        )
    with pytest.raises(GeometryError, match="moving_model_ids values must not be empty"):
        CollisionSet.from_spatial_index(spatial_index, moving_model_ids=(" ",))
    with pytest.raises(GeometryError, match="moving_model_ids must not contain duplicate"):
        CollisionSet.from_spatial_index(spatial_index, moving_model_ids=("mover", "mover"))
    with pytest.raises(GeometryError, match="engagement_model_ids must not contain duplicate"):
        CollisionSet.from_spatial_index(
            spatial_index,
            moving_model_ids=(),
            engagement_model_ids=("mover", "mover"),
        )


def test_collision_queries_reject_non_model_subjects() -> None:
    collision_set = CollisionSet.empty()

    with pytest.raises(GeometryError, match="model must be a Model"):
        collision_set.colliding_model_ids(cast(Model, "model"))
    with pytest.raises(GeometryError, match="model must be a Model"):
        collision_set.colliding_terrain_ids(cast(Model, "model"))
    with pytest.raises(GeometryError, match="model must be a Model"):
        collision_set.engagement_model_ids(
            cast(Model, "model"),
            horizontal_inches=1.0,
            vertical_inches=5.0,
        )
