from __future__ import annotations

from collections.abc import Callable
from typing import Protocol, TypeVar

import pytest

from warhammer40k_core.core.attached_unit import AttachedUnit
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.unit import Unit, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.collision import CollisionSet
from warhammer40k_core.geometry.movement_envelope import MovementEnvelope
from warhammer40k_core.geometry.pathing import PathQuery, PathWitness
from warhammer40k_core.geometry.pose import Facing, Point3, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import ObstacleVolume, TerrainVolume
from warhammer40k_core.geometry.visibility import VisibilityQuery
from warhammer40k_core.geometry.volume import Model, ModelVolume

pytestmark = pytest.mark.benchmark

_T = TypeVar("_T")


class BenchmarkFixture(Protocol):
    def __call__(self, function_to_benchmark: Callable[[], _T]) -> _T: ...


def test_benchmark_visibility_early_clear_ray(benchmark: BenchmarkFixture) -> None:
    query = VisibilityQuery(
        rays=(
            (Point3(-24.0, 0.0, 1.0), Point3(24.0, 0.0, 1.0)),
            (Point3(-24.0, 12.0, 1.0), Point3(24.0, 12.0, 1.0)),
            (Point3(-24.0, -12.0, 1.0), Point3(24.0, -12.0, 1.0)),
        ),
        static_terrain=_wall_line(count=40, y=0.0, depth=2.0),
        dynamic_model_blockers=_model_line(prefix="blocker", count=40, y=0.0),
    )

    result = benchmark(query.resolve)

    assert result.has_line_of_sight
    assert result.checked_ray_count == 2
    assert result.metrics.terrain_candidate_count > 0
    assert result.metrics.model_candidate_count > 0


def test_benchmark_visibility_all_blocked(benchmark: BenchmarkFixture) -> None:
    query = VisibilityQuery(
        rays=(
            (Point3(-24.0, 0.0, 1.0), Point3(24.0, 0.0, 1.0)),
            (Point3(-24.0, 4.0, 1.0), Point3(24.0, 4.0, 1.0)),
            (Point3(-24.0, -4.0, 1.0), Point3(24.0, -4.0, 1.0)),
        ),
        static_terrain=_wall_line(count=40, y=0.0, depth=10.0),
        dynamic_model_blockers=_model_line(prefix="blocker", count=40, y=0.0),
    )

    result = benchmark(query.resolve)

    assert not result.has_line_of_sight
    assert result.checked_ray_count == 3
    assert result.metrics.exact_terrain_check_count >= 120


def test_benchmark_path_query_one_model_no_blockers(benchmark: BenchmarkFixture) -> None:
    query = _path_query_for_group(model_count=1)

    result = benchmark(query.evaluate)

    assert result.is_valid
    assert result.metrics.sampled_pose_count > 0
    assert result.metrics.model_collision_check_count == 0


def test_benchmark_path_query_five_model_group_no_blockers(benchmark: BenchmarkFixture) -> None:
    query = _path_query_for_group(model_count=5)

    result = benchmark(query.evaluate)

    assert result.is_valid
    assert result.metrics.sampled_pose_count >= 25


def test_benchmark_path_query_five_model_group_with_model_blockers(
    benchmark: BenchmarkFixture,
) -> None:
    blockers = tuple(_model(f"blocker-{index}", 20.0 + index, 20.0) for index in range(40))
    query = _path_query_for_group(
        model_count=5,
        collision_set=CollisionSet(model_blockers=blockers),
    )

    result = benchmark(query.evaluate)

    assert result.is_valid
    assert result.metrics.model_collision_broadphase_check_count == 0
    assert result.metrics.model_collision_check_count == 0


def test_benchmark_path_query_five_model_group_with_terrain_blockers(
    benchmark: BenchmarkFixture,
) -> None:
    terrain = tuple(
        TerrainVolume(
            terrain_id=f"terrain-{index}",
            bottom_center=Point3(20.0 + index, 20.0, 0.0),
            width=1.0,
            depth=1.0,
            height=3.0,
        )
        for index in range(40)
    )
    query = _path_query_for_group(
        model_count=5,
        collision_set=CollisionSet(terrain_blockers=terrain),
    )

    result = benchmark(query.evaluate)

    assert result.is_valid
    assert result.metrics.terrain_collision_broadphase_check_count == 0
    assert result.metrics.terrain_collision_check_count == 0


def test_benchmark_path_query_attached_group_validation(benchmark: BenchmarkFixture) -> None:
    query = _attached_group_path_query()

    result = benchmark(query.evaluate)

    assert result.is_valid
    assert result.metrics.sampled_pose_count >= 25


def test_benchmark_shapely_circular_base_footprint(benchmark: BenchmarkFixture) -> None:
    footprint = benchmark(
        lambda: shapely_backend.footprint_for_base(CircularBase(0.5), Pose.at(0.0, 0.0))
    )

    assert not footprint.is_empty


def test_benchmark_shapely_oval_base_footprint(benchmark: BenchmarkFixture) -> None:
    footprint = benchmark(
        lambda: shapely_backend.footprint_for_base(
            OvalBase(length=3.5, width=1.5),
            Pose(position=Point3(0.0, 0.0, 0.0), facing=Facing(30.0)),
        )
    )

    assert not footprint.is_empty


def test_benchmark_shapely_rectangular_base_footprint(benchmark: BenchmarkFixture) -> None:
    footprint = benchmark(
        lambda: shapely_backend.footprint_for_base(
            RectangularBase(length=3.5, width=1.5),
            Pose(position=Point3(0.0, 0.0, 0.0), facing=Facing(30.0)),
        )
    )

    assert not footprint.is_empty


def test_benchmark_shapely_terrain_footprint(benchmark: BenchmarkFixture) -> None:
    terrain = TerrainVolume("ruin", Point3(0.0, 0.0, 0.0), 6.0, 4.0, 3.0)

    footprint = benchmark(lambda: shapely_backend.footprint_for_terrain(terrain))

    assert not footprint.is_empty


def test_benchmark_collision_set_model_query(benchmark: BenchmarkFixture) -> None:
    mover = _model("mover", 0.0, 0.0)
    blockers = (_model("overlap", 0.5, 0.0), *_model_line("blocker", count=40, y=20.0))
    collision_set = CollisionSet(model_blockers=blockers)

    result = benchmark(lambda: collision_set.colliding_model_ids(mover))

    assert result == ("overlap",)


def test_benchmark_collision_set_terrain_query(benchmark: BenchmarkFixture) -> None:
    mover = _model("mover", 0.0, 0.0)
    terrain = (
        TerrainVolume("overlap", Point3(0.0, 0.0, 0.0), 1.0, 1.0, 3.0),
        *tuple(
            TerrainVolume(f"terrain-{index}", Point3(20.0 + index, 20.0, 0.0), 1.0, 1.0, 3.0)
            for index in range(40)
        ),
    )
    collision_set = CollisionSet(terrain_blockers=terrain)

    result = benchmark(lambda: collision_set.colliding_terrain_ids(mover))

    assert result == ("overlap",)


def test_benchmark_collision_set_engagement_query(benchmark: BenchmarkFixture) -> None:
    mover = _model("mover", 0.0, 0.0)
    blockers = (_model("enemy", 1.5, 0.0), *_model_line("blocker", count=40, y=20.0))
    collision_set = CollisionSet(engagement_blockers=blockers)

    result = benchmark(
        lambda: collision_set.engagement_model_ids(
            mover,
            horizontal_inches=1.0,
            vertical_inches=5.0,
        )
    )

    assert result == ("enemy",)


def _model(
    model_id: str,
    x: float,
    y: float,
    z: float = 0.0,
    base: BaseShape | None = None,
) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=0.5) if base is None else base,
        volume=ModelVolume(height=2.0),
    )


def _model_line(prefix: str, count: int, y: float) -> tuple[Model, ...]:
    return tuple(_model(f"{prefix}-{index}", -20.0 + index, y) for index in range(count))


def _wall_line(count: int, y: float, depth: float) -> tuple[ObstacleVolume, ...]:
    return tuple(
        ObstacleVolume(
            terrain_id=f"wall-{index}",
            bottom_center=Point3(-20.0 + index, y, 0.0),
            width=0.5,
            depth=depth,
            height=3.0,
        )
        for index in range(count)
    )


def _unit(unit_id: str, *model_ids: str) -> Unit:
    return Unit(
        unit_id=unit_id,
        name=unit_id.title(),
        own_models=tuple(
            UnitMember.ready(model_id=model_id, name=model_id.title()) for model_id in model_ids
        ),
    )


def _path_query_for_group(
    model_count: int,
    collision_set: CollisionSet | None = None,
) -> PathQuery:
    model_ids = tuple(f"mover-{index}" for index in range(model_count))
    models = tuple(_model(model_id, 0.0, index * 1.25) for index, model_id in enumerate(model_ids))
    witness = PathWitness.for_paths(
        tuple(
            (
                model_id,
                (
                    Pose.at(0.0, index * 1.25),
                    Pose.at(2.0, index * 1.25),
                    Pose.at(4.0, index * 1.25),
                ),
            )
            for index, model_id in enumerate(model_ids)
        )
    )
    index = SpatialIndex(models=models)
    return PathQuery(
        unit_group=UnitGroup.single(_unit("movers", *model_ids)),
        spatial_index=index,
        witness=witness,
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty() if collision_set is None else collision_set,
    )


def _attached_group_path_query() -> PathQuery:
    bodyguard_ids = ("bodyguard-0", "bodyguard-1", "bodyguard-2")
    leader_ids = ("leader-0", "leader-1")
    model_ids = (*bodyguard_ids, *leader_ids)
    models = tuple(_model(model_id, 0.0, index * 1.25) for index, model_id in enumerate(model_ids))
    witness = PathWitness.for_paths(
        tuple(
            (
                model_id,
                (
                    Pose.at(0.0, index * 1.25),
                    Pose.at(2.0, index * 1.25),
                    Pose.at(4.0, index * 1.25),
                ),
            )
            for index, model_id in enumerate(model_ids)
        )
    )
    attached = AttachedUnit(
        attached_unit_id="joined",
        bodyguard=_unit("bodyguard", *bodyguard_ids),
        leaders=(_unit("leader-0", "leader-0"), _unit("leader-1", "leader-1")),
    )
    return PathQuery(
        unit_group=UnitGroup.attached(attached),
        spatial_index=SpatialIndex(models=models),
        witness=witness,
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    )


def _movement_envelope(*, max_distance_inches: float) -> MovementEnvelope:
    descriptor = RulesetDescriptor.warhammer_40000_eleventh()
    coherency_policy = descriptor.coherency_policy
    assert coherency_policy.max_horizontal_inches is not None
    assert coherency_policy.max_vertical_inches is not None
    assert coherency_policy.required_neighbors_small_unit is not None
    return MovementEnvelope(
        max_distance_inches=max_distance_inches,
        coherency_horizontal_inches=coherency_policy.max_horizontal_inches,
        coherency_vertical_inches=coherency_policy.max_vertical_inches,
        engagement_horizontal_inches=descriptor.engagement_policy.horizontal_inches,
        engagement_vertical_inches=descriptor.engagement_policy.vertical_inches,
        required_coherency_neighbors=coherency_policy.required_neighbors_small_unit,
    )
