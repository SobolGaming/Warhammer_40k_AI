"""Terrain range must remain consistent in mandatory endpoint consumers."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.objective_movement_constraint import objective_goal
from warhammer40k_core.geometry.movement_query_payloads import goal_from_payload, goal_payload
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("z", [0, 6, 12])
def test_native_terrain_goal_range_agrees_with_control_owner_and_serializes(
    section14_definitions: Section02Definitions, z: float
) -> None:
    unit = section14_definitions.unit("000004078")
    model = geometry(unit, (Pose.at(10, 10, z),))[0]
    terrain = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(((6.0, 6.0), (14.0, 6.0), (14.0, 14.0), (6.0, 14.0)),),
    )
    goal = objective_goal(terrain)
    assert measure_model_to_objective(model=model, objective=terrain).within_control_range
    assert goal.contains(model)
    assert goal.distance_lower_bound(model) == 0
    assert goal_from_payload(goal_payload(goal)) == goal
    marker = objective_goal(
        ObjectiveGeometry.from_marker(ObjectiveMarker("marker", "Marker", 10, 10))
    )
    assert marker.contains(model) is (z <= 5)


def test_terrain_goal_has_a_validated_upper_floor_witness_and_keeps_finite_polygon_guard(
    section14_definitions: Section02Definitions,
) -> None:
    from tests.support.section13_fixtures import feature
    from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
    from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
    from warhammer40k_core.engine.movement_legality import MovementLegalityContext
    from warhammer40k_core.geometry.movement_reachability import (
        MovementGoal,
        MovementReachabilityQuery,
        MovementReachabilityStatus,
        movement_reachability,
    )
    from warhammer40k_core.geometry.pathing import PathWitness

    unit = section14_definitions.unit("000004078")
    model = geometry(unit, (Pose.at(10, 10, 12),))[0]
    terrain = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(((6.0, 6.0), (14.0, 6.0), (14.0, 14.0), (6.0, 14.0)),),
    )
    goal = objective_goal(terrain)
    floor = feature(x=10, y=10, width=8, depth=8, height=12, floor=True)
    path = PathWitness.for_paths(((model.model_id, (model.pose, model.pose)),))
    legality = MovementLegalityContext.from_keywords(
        keywords=unit.keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action="normal_move",
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )
    query = MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=model,
            witness=path,
            battlefield_width_inches=60,
            battlefield_depth_inches=44,
            friendly_models=(),
            enemy_models=(),
            terrain=(),
            movement_distance_budget_inches=0,
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=model, witness=path, terrain=(), terrain_features=(floor,)
        ),
        goal=goal,
    )
    assert query.path_context.validate().is_valid
    assert query.terrain_context.validate().is_valid
    result = movement_reachability(query)
    assert result.status is MovementReachabilityStatus.REACHABLE
    assert result.witness is not None
    assert not MovementGoal(polygons=terrain.footprint_polygons, vertical_inches=5).contains(model)
    assert goal.distance_lower_bound(model) == 0
    assert (
        MovementGoal(polygons=terrain.footprint_polygons, vertical_inches=5).distance_lower_bound(
            model
        )
        == 7
    )


@pytest.mark.parametrize("invalid", [None, 1, "true"])
def test_goal_height_permission_rejects_non_boolean_payload(invalid: object) -> None:
    from typing import cast

    from warhammer40k_core.geometry.movement_query_payloads import MovementGoalPayload
    from warhammer40k_core.geometry.pose import GeometryError

    goal = objective_goal(
        ObjectiveGeometry.from_terrain(
            objective_id="terrain",
            footprint_polygons=(((6.0, 6.0), (14.0, 6.0), (14.0, 14.0), (6.0, 14.0)),),
        )
    )
    payload = dict(goal_payload(goal))
    payload["ignore_polygon_height"] = invalid
    with pytest.raises(GeometryError, match="must be a bool"):
        goal_from_payload(cast(MovementGoalPayload, payload))


def test_marker_cannot_gain_polygon_height_permission() -> None:
    from dataclasses import replace

    from warhammer40k_core.geometry.pose import GeometryError

    marker = objective_goal(
        ObjectiveGeometry.from_marker(ObjectiveMarker("marker", "Marker", 10, 10))
    )
    with pytest.raises(GeometryError, match="polygon membership"):
        replace(marker, ignore_polygon_height=True)
