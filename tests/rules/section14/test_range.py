"""Core14 range: terrain membership differs from the fallback marker cylinder."""

import math
from dataclasses import replace

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry
from tests.support.section13_fixtures import feature
from tests.support.section14_fixtures import context, objective_state
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.objectives import Objective, ObjectiveMarker
from warhammer40k_core.engine.objective_control import resolve_objective_control
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("z", [0, 5, 5.001, 6, 12])
def test_terrain_membership_has_no_marker_vertical_cap(
    section14_definitions: Section02Definitions, z: float
) -> None:
    # Core14.02 / FAQ34: a supported upper storey remains in the terrain area.
    # This is a measurement checkpoint, not a deployment/prior ascent claim.
    state, unit, _ = objective_state(section14_definitions, z=z)
    floor = feature(x=10, width=8, depth=8, floor=True, height=max(z, 0.125))
    model = geometry(unit, (Pose.at(10, 10, z),))[0]
    terrain = ObjectiveGeometry.from_terrain(
        objective_id="s14:terrain",
        footprint_polygons=(((6.0, 6.0), (14.0, 6.0), (14.0, 14.0), (6.0, 14.0)),),
    )
    distance = measure_model_to_objective(model=model, objective=terrain)
    assert distance.horizontal_distance_inches == 0
    assert distance.vertical_gap_inches == z
    record = resolve_objective_control(
        replace(
            context(state),
            objective_markers=(),
            terrain_objectives=(Objective.terrain("s14:terrain", "Terrain", floor.feature_id),),
            terrain_features=(floor,),
        )
    )
    result = record.results[0]
    assert result.controlled_by_player_id == "owner"
    assert {c.model_instance_id for c in result.contributors} == set(unit.own_model_ids())
    assert (
        result.scores[0].score
        == unit.own_models[0].characteristic(Characteristic.OBJECTIVE_CONTROL).final
    )
    assert distance.within_control_range


@pytest.mark.parametrize("z", [0, 6, 12])
def test_linked_terrain_upper_storey_scores_at_the_real_consumer(
    section14_definitions: Section02Definitions, z: float
) -> None:
    from tests.support.section13_fixtures import area
    from warhammer40k_core.core.missions import ObjectiveMarkerRole, ObjectiveTerrainAreaDefinition

    state, unit, _ = objective_state(section14_definitions, z=z)
    terrain = area(x=10, width=8, depth=8)
    marker = ObjectiveMarker("s14:objective", "Objective", 10, 10)
    definition = ObjectiveTerrainAreaDefinition(
        marker.objective_marker_id,
        ObjectiveMarkerRole.CENTRAL,
        (terrain.terrain_area_id,),
        "constructed:s14:mission-link",
    )
    record = resolve_objective_control(
        replace(
            context(state),
            objective_markers=(),
            objective_terrain_areas=(definition,),
            objective_terrain_area_markers=(marker,),
            terrain_areas=(terrain,),
        )
    )
    result = record.results[0]
    assert result.controlled_by_player_id == "owner"
    assert len(result.contributors) == len(unit.own_models)
    assert result.contributors[0].vertical_gap_inches == z


@pytest.mark.parametrize(("z", "expected"), [(5, True), (5.001, False), (6, False)])
def test_fallback_marker_keeps_five_inch_vertical_limit(
    section14_definitions: Section02Definitions, z: float, expected: bool
) -> None:
    state, _, _ = objective_state(section14_definitions, z=z)
    result = resolve_objective_control(
        context(state, ObjectiveMarker("s14:marker", "Marker", 10, 10))
    )
    assert (result.results[0].controlled_by_player_id == "owner") is expected


@pytest.mark.parametrize(("offset", "expected"), [(0, True), (0.001, False)])
def test_marker_horizontal_range_measures_closest_edges_inclusively(
    section14_definitions: Section02Definitions, offset: float, expected: bool
) -> None:
    from tests.support.section03_fixtures import axis_endpoint_within_range

    marker = ObjectiveMarker("s14:objective", "Objective", 10, 10)
    unit = section14_definitions.unit("000004078")
    model = geometry(unit, (Pose.at(10, 10),))[0]
    radius = model.base.max_radius()
    x = axis_endpoint_within_range(10, radius, marker.marker_diameter_inches / 2, 3) + offset
    state, _, _ = objective_state(section14_definitions, x=x)
    result = resolve_objective_control(context(state, marker)).results[0]
    assert (result.controlled_by_player_id == "owner") is expected
    assert marker.marker_diameter_mm == 40
    assert marker.is_flat
    assert not marker.blocks_movement
    assert not marker.blocks_placement
    if expected:
        assert math.isclose(
            result.contributors[0].horizontal_distance_inches, 3, rel_tol=0, abs_tol=1e-12
        )


@pytest.mark.parametrize(("x", "expected"), [(9.5, True), (9.499, False), (7, False), (12, True)])
@pytest.mark.parametrize("z", [0, 12])
def test_terrain_requires_actual_membership_without_three_inch_halo(
    section14_definitions: Section02Definitions, x: float, z: float, expected: bool
) -> None:
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    # Exactly representable analytic contract isolates membership from a native
    # millimetre base's binary boundary; no native geometry/admission is claimed.
    model = Model("constructed:s14:boundary", Pose.at(x, 10, z), CircularBase(0.5), ModelVolume(1))
    terrain = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(((10.0, 8.0), (14.0, 8.0), (14.0, 12.0), (10.0, 12.0)),),
    )
    result = measure_model_to_objective(model=model, objective=terrain)
    assert result.within_control_range is expected
    if x == 9.5:
        assert result.horizontal_distance_inches == 0
    if not expected:
        assert result.horizontal_distance_inches > 0


def test_sources_resolve_point_on_terrain_and_keep_unmatched_forty_mm_marker() -> None:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.objective_control_sources import resolve_objective_control_sources

    terrain = feature(x=10, width=8, depth=8)
    inside = ObjectiveMarker("inside", "Inside", 10, 10)
    outside = ObjectiveMarker("outside", "Outside", 20, 10)
    markers, objectives, linked = resolve_objective_control_sources(
        objective_markers=(inside, outside),
        terrain_features=(terrain,),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(),
        explicit_terrain_objectives=(),
        objective_terrain_areas=(),
    )
    assert markers == (outside,)
    assert not linked
    assert objectives == (Objective.terrain("inside", "Inside", terrain.feature_id),)
    assert markers[0].x_inches == outside.x_inches
    assert markers[0].y_inches == outside.y_inches
    assert markers[0].marker_diameter_mm == 40


def test_terrain_concavity_and_separate_area_parts_do_not_fill_their_gap() -> None:
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.volume import Model, ModelVolume

    terrain = ObjectiveGeometry.from_terrain(
        objective_id="terrain",
        footprint_polygons=(
            ((0.0, 0.0), (4.0, 0.0), (4.0, 1.0), (1.0, 1.0), (1.0, 4.0), (0.0, 4.0)),
            ((8.0, 0.0), (10.0, 0.0), (10.0, 4.0), (8.0, 4.0)),
        ),
    )
    model = Model("constructed:s14:concavity", Pose.at(3, 3, 12), CircularBase(0.5), ModelVolume(1))
    assert not measure_model_to_objective(model=model, objective=terrain).within_control_range
    assert not measure_model_to_objective(
        model=replace(model, pose=Pose.at(6, 3)), objective=terrain
    ).within_control_range
    assert measure_model_to_objective(
        model=replace(model, pose=Pose.at(8, 3, 12)), objective=terrain
    ).within_control_range
