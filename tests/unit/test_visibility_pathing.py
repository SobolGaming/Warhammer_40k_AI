from __future__ import annotations

import json

import pytest

from warhammer40k_core.core.attached_unit import AttachedUnit
from warhammer40k_core.core.unit import Unit, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.collision import CollisionSet
from warhammer40k_core.geometry.movement_envelope import MovementEnvelope
from warhammer40k_core.geometry.pathing import (
    PathFailureReason,
    PathQuery,
    PathResult,
    PathWitness,
)
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import ObstacleVolume, TerrainVolume
from warhammer40k_core.geometry.visibility import VisibilityQuery, VisibilityResult
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _model(model_id: str, x: float, y: float, z: float = 0.0) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x=x, y=y, z=z),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _unit(unit_id: str, *model_ids: str) -> Unit:
    return Unit(
        unit_id=unit_id,
        name=unit_id.title(),
        own_models=tuple(
            UnitMember.ready(model_id=model_id, name=model_id.title()) for model_id in model_ids
        ),
    )


def _query_for_single_model(
    witness: PathWitness,
    collision_set: CollisionSet | None = None,
    envelope: MovementEnvelope | None = None,
) -> PathQuery:
    model = _model("mover-1", 0.0, 0.0)
    unit_group = UnitGroup.single(_unit("movers", "mover-1"))
    return PathQuery(
        unit_group=unit_group,
        spatial_index=SpatialIndex.empty().with_model(model),
        witness=witness,
        movement_envelope=(
            MovementEnvelope(max_distance_inches=10.0) if envelope is None else envelope
        ),
        collision_set=CollisionSet.empty() if collision_set is None else collision_set,
    )


def _single_model_witness(*poses: Pose) -> PathWitness:
    return PathWitness.for_paths((("mover-1", poses),))


def test_visibility_uses_staged_rays_and_early_exits_on_clear_ray() -> None:
    wall = ObstacleVolume(
        terrain_id="wall",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )
    query = VisibilityQuery(
        rays=(
            (Point3(-3.0, 0.0, 1.0), Point3(3.0, 0.0, 1.0)),
            (Point3(-3.0, 3.0, 1.0), Point3(3.0, 3.0, 1.0)),
        ),
        static_terrain=(wall,),
    )

    result = query.resolve()

    assert result.has_line_of_sight
    assert result.checked_ray_count == 2
    assert result.clear_ray_index == 1
    assert result.blocking_terrain_ids == ()
    assert result.checked_terrain_ids == ("wall",)
    assert result.metrics.terrain_candidate_count == 1
    assert result.metrics.exact_terrain_check_count == 1


def test_visibility_reports_deterministic_blockers_when_all_rays_are_blocked() -> None:
    wall_b = ObstacleVolume(
        terrain_id="wall-b",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )
    wall_a = ObstacleVolume(
        terrain_id="wall-a",
        bottom_center=Point3(1.5, 0.0, 0.0),
        width=1.0,
        depth=4.0,
        height=3.0,
    )
    model_blocker = _model("blocker", -1.5, 0.0)
    query = VisibilityQuery(
        rays=((Point3(-3.0, 0.0, 1.0), Point3(3.0, 0.0, 1.0)),),
        static_terrain=(wall_b, wall_a),
        dynamic_model_blockers=(model_blocker,),
    )

    result = query.resolve()

    assert not result.has_line_of_sight
    assert result.checked_ray_count == 1
    assert result.blocking_terrain_ids == ("wall-a", "wall-b")
    assert result.blocking_model_ids == ("blocker",)
    assert result.checked_terrain_ids == ("wall-a", "wall-b")
    assert result.checked_model_ids == ("blocker",)


def test_visibility_broad_phase_skips_far_static_terrain_candidates() -> None:
    near_wall = ObstacleVolume("near-wall", Point3(0.0, 0.0, 0.0), 1.0, 4.0, 3.0)
    far_wall = ObstacleVolume("far-wall", Point3(50.0, 0.0, 0.0), 1.0, 4.0, 3.0)
    query = VisibilityQuery.from_segment(
        Point3(-3.0, 0.0, 1.0),
        Point3(3.0, 0.0, 1.0),
        static_terrain=(far_wall, near_wall),
    )

    result = query.resolve()

    assert not result.has_line_of_sight
    assert result.blocking_terrain_ids == ("near-wall",)
    assert result.checked_terrain_ids == ("near-wall",)


def test_visibility_dynamic_model_blocker_uses_2_5d_volume() -> None:
    blocker = _model("blocker", 0.0, 0.0)
    blocked = VisibilityQuery.from_segment(
        Point3(-3.0, 0.0, 1.0),
        Point3(3.0, 0.0, 1.0),
        dynamic_model_blockers=(blocker,),
    ).resolve()
    clear_above = VisibilityQuery.from_segment(
        Point3(-3.0, 0.0, 5.0),
        Point3(3.0, 0.0, 5.0),
        dynamic_model_blockers=(blocker,),
    ).resolve()

    assert not blocked.has_line_of_sight
    assert blocked.blocking_model_ids == ("blocker",)
    assert blocked.metrics.model_candidate_count == 1
    assert blocked.metrics.exact_model_check_count == 1
    assert clear_above.has_line_of_sight


def test_visibility_payloads_round_trip_without_object_reprs() -> None:
    query = VisibilityQuery.from_segment(
        Point3(-3.0, 0.0, 1.0),
        Point3(3.0, 0.0, 1.0),
        dynamic_model_blockers=(_model("blocker", 0.0, 0.0),),
    )
    result = query.resolve()

    for payload, loader in (
        (query.to_payload(), VisibilityQuery.from_payload),
        (result.to_payload(), VisibilityResult.from_payload),
    ):
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob
        assert loader(json.loads(blob)).to_payload() == payload


def test_path_query_rejects_endpoint_only_movement_witness() -> None:
    query = _query_for_single_model(_single_model_witness(Pose.at(0.0, 0.0), Pose.at(4.0, 0.0)))

    result = query.evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.ENDPOINT_ONLY_PATH


@pytest.mark.parametrize(
    "poses",
    [
        (Pose.at(0.0, 0.0), Pose.at(4.0, 0.0), Pose.at(4.0, 0.0)),
        (Pose.at(0.0, 0.0), Pose.at(0.0, 0.0), Pose.at(4.0, 0.0)),
    ],
)
def test_path_query_rejects_degenerate_endpoint_only_witnesses(
    poses: tuple[Pose, ...],
) -> None:
    result = _query_for_single_model(_single_model_witness(*poses)).evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.ENDPOINT_ONLY_PATH


def test_path_query_checks_model_collision_along_witness_path() -> None:
    blocker = _model("blocker", 2.0, 0.0)
    query = _query_for_single_model(
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(2.0, 0.0), Pose.at(4.0, 0.0)),
        collision_set=CollisionSet(model_blockers=(blocker,)),
    )

    result = query.evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.MODEL_COLLISION
    assert result.failure.blocker_id == "blocker"
    assert result.metrics.model_collision_check_count > 0
    assert result.metrics.model_collision_broadphase_check_count >= (
        result.metrics.model_collision_check_count
    )


def test_path_query_checks_terrain_collision_along_witness_path() -> None:
    terrain = TerrainVolume(
        terrain_id="ruin",
        bottom_center=Point3(2.0, 0.0, 0.0),
        width=1.0,
        depth=2.0,
        height=3.0,
    )
    query = _query_for_single_model(
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(2.0, 0.0), Pose.at(4.0, 0.0)),
        collision_set=CollisionSet(terrain_blockers=(terrain,)),
    )

    result = query.evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.TERRAIN_COLLISION
    assert result.failure.blocker_id == "ruin"


def test_path_query_checks_engagement_range_along_witness_path() -> None:
    enemy = _model("enemy", 2.0, 0.0)
    query = _query_for_single_model(
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(1.2, 0.0), Pose.at(4.0, 0.0)),
        collision_set=CollisionSet(engagement_blockers=(enemy,)),
    )

    result = query.evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.ENGAGEMENT_RANGE
    assert result.failure.blocker_id == "enemy"


def test_collision_set_prunes_x_disjoint_model_blockers_before_broadphase() -> None:
    mover = _model("mover", 0.0, 0.0)
    near_x_far_y = _model("near-x-far-y", 0.0, 20.0)
    far_x = _model("far-x", 20.0, 0.0)
    collision_set = CollisionSet(model_blockers=(near_x_far_y, far_x))

    result = collision_set.model_collision_query(mover)

    assert result.blocker_ids == ()
    assert result.broadphase_check_count == 1
    assert result.exact_check_count == 0


def test_collision_set_prunes_x_disjoint_terrain_blockers_before_broadphase() -> None:
    mover = _model("mover", 0.0, 0.0)
    near_x_far_y = TerrainVolume(
        terrain_id="near-x-far-y",
        bottom_center=Point3(0.0, 20.0, 0.0),
        width=1.0,
        depth=1.0,
        height=3.0,
    )
    far_x = TerrainVolume(
        terrain_id="far-x",
        bottom_center=Point3(20.0, 0.0, 0.0),
        width=1.0,
        depth=1.0,
        height=3.0,
    )
    collision_set = CollisionSet(terrain_blockers=(near_x_far_y, far_x))

    result = collision_set.terrain_collision_query(mover)

    assert result.blocker_ids == ()
    assert result.broadphase_check_count == 1
    assert result.exact_check_count == 0


def test_path_query_checks_coherency_after_group_movement() -> None:
    first = _model("mover-1", 0.0, 0.0)
    second = _model("mover-2", 1.0, 0.0)
    unit_group = UnitGroup.single(_unit("movers", "mover-1", "mover-2"))
    witness = PathWitness.for_paths(
        (
            ("mover-1", (Pose.at(0.0, 0.0), Pose.at(0.5, 0.0), Pose.at(0.0, 0.0))),
            ("mover-2", (Pose.at(1.0, 0.0), Pose.at(5.0, 0.0), Pose.at(10.0, 0.0))),
        )
    )
    query = PathQuery(
        unit_group=unit_group,
        spatial_index=SpatialIndex.empty().with_model(first).with_model(second),
        witness=witness,
        movement_envelope=MovementEnvelope(max_distance_inches=20.0),
        collision_set=CollisionSet.empty(),
    )

    result = query.evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.COHERENCY


def test_movement_envelope_can_require_two_coherency_neighbors() -> None:
    envelope = MovementEnvelope(max_distance_inches=10.0, required_coherency_neighbors=2)
    coherent = (_model("first", 0.0, 0.0), _model("second", 1.5, 0.0), _model("third", 0.0, 1.5))
    incoherent = (
        _model("first", 0.0, 0.0),
        _model("second", 1.5, 0.0),
        _model("third", 4.0, 0.0),
    )

    assert envelope.models_are_coherent(coherent)
    assert not envelope.models_are_coherent(incoherent)


def test_path_query_validates_attached_unit_group_together() -> None:
    bodyguard_model = _model("bodyguard-1", 0.0, 0.0)
    leader_model = _model("leader-1", 1.0, 0.0)
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="joined",
            bodyguard=_unit("bodyguard", "bodyguard-1"),
            leaders=(_unit("leader", "leader-1"),),
        )
    )
    index = SpatialIndex.empty().with_model(bodyguard_model).with_model(leader_model)
    incomplete = PathWitness.for_paths(
        (("bodyguard-1", (Pose.at(0.0, 0.0), Pose.at(0.25, 0.0), Pose.at(0.5, 0.0))),)
    )
    complete = PathWitness.for_paths(
        (
            ("bodyguard-1", (Pose.at(0.0, 0.0), Pose.at(0.25, 0.0), Pose.at(0.5, 0.0))),
            ("leader-1", (Pose.at(1.0, 0.0), Pose.at(1.5, 0.0), Pose.at(2.0, 0.0))),
        )
    )

    incomplete_result = PathQuery(
        unit_group=group,
        spatial_index=index,
        witness=incomplete,
        movement_envelope=MovementEnvelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()
    complete_result = PathQuery(
        unit_group=group,
        spatial_index=index,
        witness=complete,
        movement_envelope=MovementEnvelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert not incomplete_result.is_valid
    assert incomplete_result.failure is not None
    assert incomplete_result.failure.reason is PathFailureReason.GROUP_MISMATCH
    assert complete_result.is_valid
    assert complete_result.metrics.sampled_pose_count == 6


def test_path_query_accepts_attached_group_when_witness_order_differs_from_unit_order() -> None:
    bodyguard_model = _model("z-bodyguard-1", 0.0, 0.0)
    leader_model = _model("a-leader-1", 1.0, 0.0)
    group = UnitGroup.attached(
        AttachedUnit(
            attached_unit_id="joined",
            bodyguard=_unit("bodyguard", "z-bodyguard-1"),
            leaders=(_unit("leader", "a-leader-1"),),
        )
    )
    witness = PathWitness.for_paths(
        (
            ("z-bodyguard-1", (Pose.at(0.0, 0.0), Pose.at(0.25, 0.0), Pose.at(0.5, 0.0))),
            ("a-leader-1", (Pose.at(1.0, 0.0), Pose.at(1.5, 0.0), Pose.at(2.0, 0.0))),
        )
    )

    result = PathQuery(
        unit_group=group,
        spatial_index=SpatialIndex.empty().with_model(bodyguard_model).with_model(leader_model),
        witness=witness,
        movement_envelope=MovementEnvelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert result.is_valid


def test_path_query_rejects_final_overlap_between_moving_models() -> None:
    first = _model("mover-1", 0.0, 0.0)
    second = _model("mover-2", 2.0, 0.0)
    unit_group = UnitGroup.single(_unit("movers", "mover-1", "mover-2"))
    witness = PathWitness.for_paths(
        (
            ("mover-1", (Pose.at(0.0, 0.0), Pose.at(0.5, 0.0), Pose.at(1.0, 0.0))),
            ("mover-2", (Pose.at(2.0, 0.0), Pose.at(1.5, 0.0), Pose.at(1.0, 0.0))),
        )
    )

    result = PathQuery(
        unit_group=unit_group,
        spatial_index=SpatialIndex.empty().with_model(first).with_model(second),
        witness=witness,
        movement_envelope=MovementEnvelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.SELF_COLLISION
    assert result.failure.model_id == "mover-1"
    assert result.failure.blocker_id == "mover-2"


def test_pathing_payloads_round_trip_without_object_reprs() -> None:
    witness = _single_model_witness(Pose.at(0.0, 0.0), Pose.at(1.0, 0.0), Pose.at(2.0, 0.0))
    envelope = MovementEnvelope(
        max_distance_inches=10.0,
        sample_interval_inches=0.5,
        required_coherency_neighbors=1,
    )
    collision_set = CollisionSet(model_blockers=(_model("blocker", 10.0, 0.0),))
    query = _query_for_single_model(witness, collision_set=collision_set, envelope=envelope)
    result = query.evaluate()

    payloads = (
        (witness.to_payload(), PathWitness.from_payload),
        (envelope.to_payload(), MovementEnvelope.from_payload),
        (collision_set.to_payload(), CollisionSet.from_payload),
        (query.to_payload(), PathQuery.from_payload),
        (result.to_payload(), PathResult.from_payload),
    )

    for payload, loader in payloads:
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob
        assert loader(json.loads(blob)).to_payload() == payload


def test_explicit_path_result_payload_rejects_mismatched_validity() -> None:
    result = _query_for_single_model(
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(4.0, 0.0))
    ).evaluate()
    payload = result.to_payload()
    payload["is_valid"] = True

    with pytest.raises(GeometryError, match="Valid PathResult payload"):
        PathResult.from_payload(payload)
