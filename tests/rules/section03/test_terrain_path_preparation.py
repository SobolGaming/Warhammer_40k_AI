"""Validation-local terrain footprints: differential legality and input isolation."""

import math
from dataclasses import replace

import pytest

from warhammer40k_core.core.ruleset_descriptor import (
    MovementMode,
    RulesetDescriptor,
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainVolume,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume


def _preparation_legality() -> MovementLegalityContext:
    return MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )


def _preparation_context(
    legality: MovementLegalityContext,
    *,
    moving_model: Model,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    end_pose: Pose,
) -> TerrainPathLegalityContext:
    return legality.to_terrain_path_legality_context(
        moving_model=moving_model,
        witness=PathWitness.for_paths(((moving_model.model_id, (moving_model.pose, end_pose)),)),
        terrain=(),
        terrain_features=terrain_features,
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    )


def _preparation_wall() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=3,
        center_y_inches=1,
        width_inches=6,
        depth_inches=6,
        display_template_id=None,
    )
    return TerrainFeatureDefinition(
        "preparation-wall",
        TerrainFeatureKind.RUINS,
        3,
        1,
        6,
        6,
        display.footprint_polygon,
        display,
        walls=(TerrainWallDefinition("wall", 3, 1, 0, 1, 1, 3),),
        floors=(TerrainFloorDefinition("floor", 3, 1, 0, 6, 6, 0.12),),
    )


@pytest.mark.parametrize("base", [CircularBase(0.5), OvalBase(2, 1), RectangularBase(2, 1)])
@pytest.mark.parametrize("rotation", [0, 15, 90, 179])
def test_prepared_terrain_samples_match_direct_intersections(
    base: BaseShape, rotation: int
) -> None:
    from warhammer40k_core.geometry.terrain_path_preparation import TerrainPathFootprints

    poses = tuple(
        Pose.at(x, y, z, facing_degrees=facing)
        for x, y, z, facing in (
            (0, 0, 0, 0),
            (1, 1, 0, 15),
            (2, 1, 0, 90),
            (1, 1, 3, 15),
            (1, 1, 0, 15),
            (100, 100, 0, 0),
        )
    )
    prepared = TerrainPathFootprints(base, poses)
    for center_x in (0.5, 1, 1.5, math.nextafter(1.5, math.inf), 3, 1000):
        terrain = TerrainVolume(
            terrain_id="probe",
            bottom_center=Point3(center_x, 0, 0),
            width=1,
            depth=1,
            height=2,
            rotation_degrees=rotation,
        )
        footprint = shapely_backend.footprint_for_terrain(terrain)
        expected = tuple(
            pose
            for pose in poses
            if footprint.intersects(shapely_backend.footprint_for_base(base, pose))
        )
        assert prepared.touching_poses(terrain) == expected
        assert prepared.touching_poses(terrain) == expected


def test_prepared_terrain_builds_each_sample_once_and_keeps_boundary_contact(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from warhammer40k_core.geometry.terrain_path_preparation import TerrainPathFootprints

    calls: list[Pose] = []
    original = shapely_backend.footprint_for_base

    def counted(base: BaseShape, pose: Pose) -> shapely_backend.FootprintGeometry:
        calls.append(pose)
        return original(base, pose)

    monkeypatch.setattr(shapely_backend, "footprint_for_base", counted)
    poses = (Pose.at(0, 0), Pose.at(1, 0), Pose.at(2, 0))
    prepared = TerrainPathFootprints(CircularBase(0.5), poses)
    assert calls == []
    tangent = TerrainVolume(
        terrain_id="tangent",
        bottom_center=Point3(1, 1, 0),
        width=1,
        depth=1,
        height=1,
    )
    assert prepared.touching_poses(tangent) == (poses[1],)
    for i in range(8):
        distant = replace(tangent, bottom_center=Point3(100 + i, 100, 0))
        assert prepared.touching_poses(distant) == ()
    assert calls == list(poses)
    # A separate validation owns fresh preparation even with identical identifiers.
    other = TerrainPathFootprints(CircularBase(1), poses)
    assert other.touching_poses(tangent) != prepared.touching_poses(tangent)
    assert calls == [*poses, *poses]


def test_terrain_preparation_preserves_complete_results_and_context_isolation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from warhammer40k_core.geometry.terrain_path_preparation import TerrainPathFootprints

    mover = Model("mover", Pose.at(1, 1), CircularBase(0.5), ModelVolume(2))
    wall = _preparation_wall()
    original = _preparation_context(
        _preparation_legality(),
        moving_model=mover,
        terrain_features=(wall,),
        end_pose=Pose.at(5, 1),
    )
    shifted = replace(mover, pose=Pose.at(1, 8), base=OvalBase(2, 1))
    contexts = (
        original,
        replace(original, can_transit_all_terrain=True),
        replace(original, movement_keywords=("VEHICLE",), can_traverse_ruins_walls=False),
        replace(
            original,
            witness=PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(3, 1))),)),
        ),
        replace(
            original,
            witness=PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(5, 1, 2))),)),
        ),
        replace(
            original, witness=PathWitness.for_paths(((mover.model_id, (mover.pose, mover.pose)),))
        ),
        _preparation_context(
            _preparation_legality(),
            moving_model=shifted,
            terrain_features=(wall,),
            end_pose=Pose.at(5, 8),
        ),
        replace(original, terrain_features=()),
        TerrainPathLegalityContext.from_payload(original.to_payload()),
    )
    actual = tuple(context.validate().to_payload() for context in contexts)

    def direct(self: TerrainPathFootprints, terrain: TerrainVolume) -> tuple[Pose, ...]:
        footprint = shapely_backend.footprint_for_terrain(terrain)
        return tuple(
            pose
            for pose in self.sampled_path
            if footprint.intersects(shapely_backend.footprint_for_base(self.base, pose))
        )

    monkeypatch.setattr(TerrainPathFootprints, "touching_poses", direct)
    expected = tuple(context.validate().to_payload() for context in contexts)
    assert actual == expected
    assert actual[0]["is_valid"]
    assert not actual[2]["is_valid"]  # Permission changes still invalidate transit.
    assert not actual[3]["is_valid"]  # Endpoint inside terrain is never bypassed.
    assert not actual[4]["is_valid"]  # Unsupported elevated endpoint is still rejected.
    assert actual[0] == actual[-1]
