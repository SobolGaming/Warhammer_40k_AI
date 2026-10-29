"""03.01 geometry contracts: explicit sizes, never claimed to be native units."""

import math

import pytest

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.movement_envelope import MovementDistanceWitness
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.shapely_backend import footprint_for_base
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    "base",
    [CircularBase(radius=0.5), OvalBase(length=3, width=1), RectangularBase(length=4, width=2)],
)
@pytest.mark.parametrize(("budget", "valid"), [(5.99, False), (6, True), (6.01, True)])
def test_segments_sum_same_point_horizontal_distance_with_free_rotations(
    base: CircularBase | OvalBase | RectangularBase, budget: float, valid: bool
) -> None:
    model = Model("contract", Pose.at(10, 10), base, ModelVolume(3))
    poses = (
        model.pose,
        Pose.at(13, 10),
        Pose.at(13, 10, facing_degrees=90),
        Pose.at(13, 13, facing_degrees=90),
        Pose.at(13, 13, facing_degrees=270),
    )
    distance = MovementDistanceWitness.for_model_path(
        model=model, poses=poses, max_distance_inches=budget
    )
    assert distance.total_distance_inches == 6
    assert distance.straight_line_distance_inches == 6
    assert distance.budget is not None
    assert distance.budget.is_within_budget is valid
    assert len(distance.rotation_events) == 2
    result = PathValidationContext(
        moving_model=model,
        witness=PathWitness.for_paths(((model.model_id, poses),)),
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        enemy_engagement_horizontal_inches=2,
        enemy_engagement_vertical_inches=5,
        movement_distance_budget_inches=budget,
    ).validate()
    assert result.is_valid is valid
    if not valid:
        assert result.violations[0].violation_code == "movement_distance_exceeded"


@pytest.mark.parametrize(
    ("angle", "bounds"), [(0, (8, 9, 12, 11)), (90, (9, 8, 11, 12)), (180, (8, 9, 12, 11))]
)
def test_baseless_rectangular_contract_rotates_about_central_axis_upright(
    angle: float, bounds: tuple[int, int, int, int]
) -> None:
    # The geometry evaluator receives the hull as its rules footprint for a baseless FRAME.
    model = Model(
        "constructed-baseless-frame",
        Pose.at(10, 10),
        RectangularBase(length=4, width=2),
        ModelVolume(3),
        measures_every_part=True,
    )
    rotated = Pose.at(10, 10, facing_degrees=angle)
    assert all(
        math.isclose(a, b, rel_tol=0, abs_tol=1e-9)
        for a, b in zip(footprint_for_base(model.base, rotated).bounds, bounds, strict=True)
    )
    assert rotated.position == model.pose.position
    assert model.volume.vertical_interval(rotated) == (0, 3)
    distance = MovementDistanceWitness.for_model_path(
        model=model, poses=(model.pose, rotated), max_distance_inches=0
    )
    assert distance.total_distance_inches == 0
