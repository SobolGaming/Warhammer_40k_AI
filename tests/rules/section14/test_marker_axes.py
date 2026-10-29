"""User-adopted marker cylinder; constructed FRAME contracts, no admission claim."""

import math
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import axis_endpoint_within_range, native_state
from tests.support.section14_fixtures import context
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.objective_control import resolve_objective_control
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.objective_movement_constraint import (
    objective_endpoint_evidence,
    objective_goal,
)
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


def declared_frame(marker: ObjectiveMarker, horizontal: float = 0, vertical: float = 6) -> Model:
    """Two declared physical prisms; source permission/history is not constructed."""
    arm_x = (
        marker.x_inches
        if horizontal == 0
        else axis_endpoint_within_range(
            marker.x_inches, marker.marker_diameter_inches / 2, 0.5, horizontal
        )
    )
    return Model(
        "constructed:s18:frame",
        Pose.at(marker.x_inches + 5, marker.y_inches),
        CircularBase(0.5),
        ModelVolume(1),
        body_parts=(
            ModelBodyPart(
                "arm",
                CircularBase(0.5),
                arm_x - marker.x_inches - 5,
                0,
                vertical,
                1,
                "constructed:s18:arm",
            ),
        ),
        measures_every_part=True,
    )


@pytest.mark.parametrize(("x", "y"), [(10, 10), (11.25, 9.5), (8, 13)])
def test_user_convention_does_not_borrow_marker_axes_from_different_parts(
    x: float, y: float
) -> None:
    marker = ObjectiveMarker("marker", "Marker", x, y)
    model = declared_frame(marker)
    objective = ObjectiveGeometry.from_marker(marker)
    measured = measure_model_to_objective(model=model, objective=objective)
    geometric = DistanceMeasurementContext.from_objective_marker_to_model(
        marker_id=marker.objective_marker_id,
        marker_pose=Pose.at(x, y),
        model=model,
        marker_diameter_inches=marker.marker_diameter_inches,
    )
    assert not geometric.within_axis_limits(3, 5)
    assert not objective_goal(objective).contains(model)
    assert measured.horizontal_distance_inches == 0
    assert measured.vertical_gap_inches == 0
    assert math.isclose(
        measured.closest_distance_inches, 5 - 0.5 - marker.marker_diameter_inches / 2, abs_tol=1e-12
    )
    assert not measured.within_control_range


@pytest.mark.parametrize(
    ("horizontal", "vertical", "expected"),
    [
        (2.5, 5, True),
        (2.5, 5.00001, False),
        (3.1, 4, False),
        (3, 4, True),
    ],
)
def test_compound_marker_keeps_inclusive_limits_and_exterior_rejection(
    horizontal: float,
    vertical: float,
    expected: bool,
) -> None:
    marker = ObjectiveMarker("marker", "Marker", 10, 10)
    model = declared_frame(marker, horizontal, vertical)
    objective = ObjectiveGeometry.from_marker(marker)
    result = measure_model_to_objective(model=model, objective=objective)
    assert result.within_control_range is expected
    assert objective_goal(objective).contains(model) is expected


def test_same_point_is_not_only_the_euclidean_nearest_point() -> None:
    marker = ObjectiveMarker("marker", "Marker", 10, 10)
    model = declared_frame(marker, 2.5, 5)
    objective = ObjectiveGeometry.from_marker(marker)
    parts = tuple(
        measure_model_to_objective(model=p, objective=objective)
        for p in model.rules_distance_subjects()
    )
    result = measure_model_to_objective(model=model, objective=objective)
    assert not parts[0].within_control_range
    assert parts[1].within_control_range
    assert parts[0].closest_distance_inches < parts[1].closest_distance_inches
    assert result.closest_distance_inches == parts[0].closest_distance_inches
    assert result.within_control_range


def test_support_base_can_supply_the_one_point_when_other_parts_cannot() -> None:
    marker = ObjectiveMarker("marker", "Marker", 10, 10)
    model = replace(declared_frame(marker), pose=Pose.at(10, 10))
    objective = ObjectiveGeometry.from_marker(marker)
    assert measure_model_to_objective(model=model, objective=objective).within_control_range
    assert objective_goal(objective).contains(model)


@pytest.mark.parametrize(("arm_bottom", "expected"), [(6, False), (5, True)])
def test_declared_frame_point_policy_reaches_actual_control_scoring(
    section14_definitions: Section02Definitions,
    arm_bottom: float,
    expected: bool,
) -> None:
    # Preserve every native ID, base, height and OC. Only the explicitly constructed
    # FRAME keyword/body supplement changes; no roster or body admission is proved.
    native = section14_definitions.unit("000004078")
    original = native.own_models[0]
    physical = replace(
        original,
        keyword_assignment=replace(
            original.keyword_assignment, keywords=(*original.keyword_assignment.keywords, "FRAME")
        ),
        geometry=replace(
            original.geometry,
            body_parts=(
                ModelBodyPart(
                    "arm", CircularBase(0.5), -5, 0, arm_bottom, 1, "constructed:s18:arm"
                ),
            ),
        ),
    )
    unit = replace(native, own_models=(physical,))
    assert physical.model_instance_id == original.model_instance_id
    assert physical.base_size == original.base_size
    assert replace(physical.geometry, body_parts=()) == original.geometry
    state = native_state(section14_definitions, unit, (Pose.at(15, 10),))
    before = state.to_payload()
    record = resolve_objective_control(context(state))
    result = record.results[0]
    owned = tuple(c for c in result.contributors if c.player_id == "owner")
    assert bool(owned) is expected
    assert result.controlled_by_player_id == ("owner" if expected else None)
    assert sum(s.score for s in result.scores if s.player_id == "owner") == (
        original.characteristic(Characteristic.OBJECTIVE_CONTROL).final if expected else 0
    )
    if expected:
        assert len(owned) == 1
        assert owned[0].model_instance_id == original.model_instance_id
        assert owned[0].unit_instance_id == unit.unit_instance_id
    assert state.to_payload() == before


@pytest.mark.parametrize("terrain", [True, False])
def test_terrain_primary_membership_and_marker_endpoint_evidence_remain_distinct(
    terrain: bool,
) -> None:
    marker = ObjectiveMarker("marker", "Marker", 10, 10)
    model = declared_frame(marker)
    objective = (
        ObjectiveGeometry.from_terrain(
            objective_id="terrain",
            footprint_polygons=(((8.0, 8.0), (12.0, 8.0), (12.0, 12.0), (8.0, 12.0)),),
        )
        if terrain
        else ObjectiveGeometry.from_marker(marker)
    )
    witness = PathWitness.for_paths(((model.model_id, (model.pose, model.pose)),))
    path = PathValidationContext(
        moving_model=model,
        witness=witness,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        enemy_engagement_horizontal_inches=1,
        enemy_engagement_vertical_inches=5,
        movement_distance_budget_inches=0,
        pose_is_fixed=True,
    )
    typed_terrain = TerrainPathLegalityContext(
        moving_model=model,
        witness=witness,
        terrain=(),
        terrain_movement_policy=RulesetDescriptor.warhammer_40000_eleventh().terrain_movement_policy,
    )
    query = MovementReachabilityQuery(
        path_context=path, terrain_context=typed_terrain, goal=objective_goal(objective)
    )
    assert path.validate().is_valid
    assert typed_terrain.validate().is_valid
    row, rejection = objective_endpoint_evidence(query=query, endpoint=model, objective=objective)
    assert rejection is None
    assert (row["range_status"] == "satisfied") is terrain
    if not terrain:
        assert row["range_status"] in {"unreachable", "endpoint_unreachable"}
        assert row["approach_status"] == "optimal_bound"
    assert (
        measure_model_to_objective(model=model, objective=objective).within_control_range is terrain
    )
