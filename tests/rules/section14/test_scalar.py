"""Closest physical point contracts, separate from the adopted marker point convention."""

import math
from dataclasses import replace

import pytest

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    ObjectiveModelDistance,
    measure_model_to_objective,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def declared_frame(bottom: float) -> Model:
    """Supported typed geometry contract; no native FRAME admission claim."""
    return Model(
        "constructed:s14:scalar",
        Pose.at(15, 10),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(
            ModelBodyPart("arm", CircularBase(0.5), -5, 0, bottom, 1, "constructed:s14:scalar-arm"),
        ),
        measures_every_part=True,
    )


@pytest.mark.parametrize("scalar", [-1, float("inf"), float("nan")])
def test_scalar_distance_rejects_invalid_required_evidence(scalar: float) -> None:
    with pytest.raises((GameLifecycleError, GeometryError), match=r"non-negative|finite"):
        ObjectiveModelDistance(
            horizontal_distance_inches=0,
            vertical_gap_inches=0,
            within_control_range=True,
            closest_distance_inches=scalar,
        )


@pytest.mark.parametrize(
    ("right", "bottom", "expected"),
    [
        (11, 6, 3.5),
        (9.25, 6, 5.25),
        (9.25, 2, math.hypot(0.25, 2)),
    ],
)
def test_terrain_closest_distance_uses_one_physical_part(
    right: float,
    bottom: float,
    expected: float,
) -> None:
    objective = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(((8.0, 9.0), (right, 9.0), (right, 11.0), (8.0, 11.0)),),
    )
    frame = declared_frame(bottom)
    result = measure_model_to_objective(model=frame, objective=objective)
    # Range membership still uses horizontal area occupancy. A physical distance
    # cannot combine the arm's horizontal gap with the base's vertical gap.
    assert result.within_control_range is (right == 11)
    assert result.vertical_gap_inches == 0
    assert result.horizontal_distance_inches == max(0, 9.5 - right)
    assert math.isclose(result.closest_distance_inches, expected, rel_tol=0, abs_tol=1e-12)
    assert math.isclose(
        result.closest_distance_inches,
        min(
            measure_model_to_objective(model=p, objective=objective).closest_distance_inches
            for p in frame.rules_distance_subjects()
        ),
        rel_tol=0,
        abs_tol=1e-12,
    )
    ordinary = measure_model_to_objective(
        model=replace(frame, measures_every_part=False), objective=objective
    )
    assert ordinary.closest_distance_inches == 14.5 - right


def test_marker_closest_distance_does_not_combine_different_parts() -> None:
    marker = ObjectiveMarker("marker", "Marker", 10, 10)
    result = measure_model_to_objective(
        model=declared_frame(6), objective=ObjectiveGeometry.from_marker(marker)
    )
    expected = 5 - 0.5 - marker.marker_diameter_inches / 2
    assert result.horizontal_distance_inches == 0
    assert result.vertical_gap_inches == 0
    assert math.isclose(result.closest_distance_inches, expected, rel_tol=0, abs_tol=1e-12)
    # No marker-admission verdict is asserted here. The adopted marker convention
    # is asserted separately.


def test_physical_distance_reaches_objective_endpoint_evidence() -> None:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.objective_movement_constraint import (
        objective_endpoint_evidence,
        objective_goal,
    )
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery
    from warhammer40k_core.geometry.pathing import (
        PathValidationContext,
        PathWitness,
        TerrainPathLegalityContext,
    )

    source = declared_frame(6)
    endpoint = replace(source, pose=Pose.at(14.75, 10))
    objective = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(((8.0, 9.0), (11.0, 9.0), (11.0, 11.0), (8.0, 11.0)),),
    )
    witness = PathWitness.for_paths(((source.model_id, (source.pose, endpoint.pose)),))
    path = PathValidationContext(
        moving_model=source,
        witness=witness,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        enemy_engagement_horizontal_inches=1,
        enemy_engagement_vertical_inches=5,
        movement_distance_budget_inches=0.25,
    )
    terrain = TerrainPathLegalityContext(
        moving_model=source,
        witness=witness,
        terrain=(),
        terrain_movement_policy=RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy,
    )
    query = MovementReachabilityQuery(
        path_context=path, terrain_context=terrain, goal=objective_goal(objective)
    )
    assert path.validate().is_valid
    assert terrain.validate().is_valid
    row, rejection = objective_endpoint_evidence(
        query=query, endpoint=endpoint, objective=objective
    )
    assert rejection is None
    assert row["range_status"] == "satisfied"
    assert row["distance_before_inches"] == 3.5
    assert row["distance_after_inches"] == 3.25
