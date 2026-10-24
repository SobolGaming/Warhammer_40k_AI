"""17.02: closest physical parts, explicit hull rotation and local FRAME FAQs."""

import json
from dataclasses import replace
from fractions import Fraction

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import geometry
from tests.support.section17_fixtures import LORD, frame_unit, native_mission
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry.base import CircularBase, RectangularBase
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.physical_model import physical_prisms
from warhammer40k_core.geometry.physical_visibility_formulas import decide_physical_any
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain_area_visibility import model_intersects_terrain_area
from warhammer40k_core.geometry.visibility_formulas import ModelDomain
from warhammer40k_core.geometry.visibility_shapes import model_visibility_prism
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("frame", [False, True])
@pytest.mark.parametrize("reverse", [False, True])
def test_keyword_controls_measurement_from_and_to_identical_physical_body(
    section17_definitions: Section02Definitions,
    frame: bool,
    reverse: bool,
) -> None:
    d = section17_definitions
    subject = geometry(frame_unit(d, framed=frame), (Pose.at(10, 10),))[0]
    other = geometry(d.unit(LORD, identity="other"), (Pose.at(14.5, 10),))[0]
    source, target = (other, subject) if reverse else (subject, other)
    context = DistanceMeasurementContext.from_models(source, target)
    assert subject.measures_every_part is frame
    assert (context.closest_distance_inches() <= 1) is frame
    assert source.range_to(target) < 1 if frame else source.range_to(target) > 2
    restored = DistanceMeasurementContext.from_payload(json.loads(json.dumps(context.to_payload())))
    assert restored.to_payload() == context.to_payload()
    assert (restored.closest_distance_inches() <= 1) is frame


def test_every_part_whole_distance_includes_a_remote_overhang(
    section17_definitions: Section02Definitions,
) -> None:
    d = section17_definitions
    frame = geometry(frame_unit(d), (Pose.at(10, 10),))[0]
    ordinary = replace(frame, measures_every_part=False)
    source = geometry(d.unit(LORD, identity="source"), (Pose.at(8, 10),))[0]
    assert DistanceMeasurementContext.from_models(source, ordinary).target_wholly_within_distance(4)
    assert not DistanceMeasurementContext.from_models(source, frame).target_wholly_within_distance(
        4
    )
    assert DistanceMeasurementContext.from_models(source, frame).target_wholly_within_distance(6)


@pytest.mark.parametrize("height", [0, 12])
def test_faq34_frame_overhang_is_in_source_terrain_area_at_any_height(
    section17_definitions: Section02Definitions,
    height: float,
) -> None:
    mission = native_mission()
    logical = terrain_visibility_areas_from_placements(mission.terrain_areas)[0]
    # Place only the overhang in the actual source polygon. Translation is an
    # explicit boundary premise; this does not play a climb or deployment.
    xs = [x for polygon in logical.footprint_polygons for x, _ in polygon]
    ys = [y for polygon in logical.footprint_polygons for _, y in polygon]
    x, y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    original = geometry(frame_unit(section17_definitions), (Pose.at(x - 12, y, height),))[0]
    frame = replace(original, body_parts=(replace(original.body_parts[0], offset_x_inches=12),))
    assert model_intersects_terrain_area(frame, logical)
    assert not model_intersects_terrain_area(replace(frame, measures_every_part=False), logical)


@pytest.mark.parametrize("z", [0, 12])
def test_frame_occupies_actual_companion_terrain_objective_using_body(
    section17_definitions: Section02Definitions,
    z: float,
) -> None:
    mission = native_mission()
    # Source Terrain Objective identity and polygon are primary, marker below is
    # a separately declared measurement kernel, never a mission substitution.
    area = mission.objective_terrain_areas[0]
    areas = terrain_visibility_areas_from_placements(mission.terrain_areas)
    polygons = tuple(
        p
        for logical in areas
        if set(logical.member_terrain_area_ids) & set(area.terrain_area_ids)
        for p in logical.footprint_polygons
    )
    objective = ObjectiveGeometry.from_terrain(
        objective_id=area.objective_marker_id, footprint_polygons=polygons
    )
    xs = [x for polygon in objective.footprint_polygons for x, _ in polygon]
    ys = [y for polygon in objective.footprint_polygons for _, y in polygon]
    x, y = (min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2
    subject = geometry(frame_unit(section17_definitions), (Pose.at(x - 12, y, z),))[0]
    subject = replace(subject, body_parts=(replace(subject.body_parts[0], offset_x_inches=12),))
    measured = measure_model_to_objective(model=subject, objective=objective)
    assert measured.horizontal_distance_inches == 0
    assert measured.within_control_range
    assert not measure_model_to_objective(
        model=replace(subject, measures_every_part=False), objective=objective
    ).within_control_range


def test_marker_axes_cannot_be_borrowed_from_different_frame_points(
    section17_definitions: Section02Definitions,
) -> None:
    frame = geometry(frame_unit(section17_definitions), (Pose.at(15, 10),))[0]
    # Base is too far horizontally; elevated arm is too high vertically.
    frame = replace(
        frame,
        body_parts=(
            ModelBodyPart("high-arm", CircularBase(0.5), -5, 0, 6, 1, "constructed:s17:axes"),
        ),
    )
    objective = ObjectiveGeometry.from_marker(ObjectiveMarker("s17:marker", "Marker", 10, 10))
    result = measure_model_to_objective(model=frame, objective=objective)
    assert result.horizontal_distance_inches == 0
    assert result.vertical_gap_inches == 0
    assert not result.within_control_range
    lowered = replace(frame, body_parts=(replace(frame.body_parts[0], bottom_inches=5),))
    assert measure_model_to_objective(model=lowered, objective=objective).within_control_range


@pytest.mark.parametrize("degrees", [45, 90, 180, 270])
def test_declared_baseless_hull_rotates_upright_about_its_center(
    section17_definitions: Section02Definitions,
    degrees: float,
) -> None:
    native = geometry(section17_definitions.unit(LORD), (Pose.at(15, 15),))[0]
    # Explicit hull geometry replaces the support-base contract in this kernel.
    # Pose exposes yaw only; no roll/pitch or native baseless provider is claimed.
    hull = replace(native, base=RectangularBase(4, 2), body_parts=(), measures_every_part=True)
    end = Pose.at(15, 15, facing_degrees=degrees)
    path = PathValidationContext(
        moving_model=hull,
        witness=PathWitness.for_paths(((hull.model_id, (hull.pose, end)),)),
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        movement_distance_budget_inches=0,
        enemy_engagement_horizontal_inches=2,
        enemy_engagement_vertical_inches=5,
    )
    assert path.validate().is_valid
    rotated = Model.from_payload(json.loads(json.dumps(replace(hull, pose=end).to_payload())))
    assert rotated.pose.position == hull.pose.position
    assert rotated.pose.facing.degrees == degrees
    assert rotated.volume == hull.volume


@pytest.mark.parametrize("frame", [False, True])
def test_faq53_visibility_uses_body_even_when_rules_distances_use_base(
    section17_definitions: Section02Definitions,
    frame: bool,
) -> None:
    d = section17_definitions
    target = geometry(frame_unit(d, framed=frame), (Pose.at(14, 10),))[0]
    # Declared rectangular physical geometry bounds this body/visibility kernel.
    target = replace(
        target,
        base=RectangularBase(1, 1),
        body_parts=(
            replace(
                target.body_parts[0],
                base=RectangularBase(1, 1),
                offset_x_inches=0,
                offset_y_inches=4,
            ),
        ),
    )
    observer = geometry(d.unit(LORD, identity="observer"), (Pose.at(8, 10),))[0]
    observer = replace(observer, base=RectangularBase(1, 1))
    # Wall occludes support-base body; offset arm offers a physical sightline.
    wall = Model("s17:wall", Pose.at(11, 10), RectangularBase(0.2, 2), ModelVolume(6))
    origins = (ModelDomain.from_prism(model_visibility_prism(observer)),)
    targets = tuple(
        ModelDomain.from_prism(model_visibility_prism(p)) for p in physical_prisms(target)
    )
    blockers = (model_visibility_prism(wall),)
    # This is the exact existential consumer used by the physical visibility
    # owner. FAQ53 needs any sightline, not the separate quantified cover/full-
    # visibility result. Both original visible/hidden controls remain mandatory.
    seen = decide_physical_any(origins, targets, blockers, None)
    hidden = decide_physical_any(origins, targets[:1], blockers, None)
    assert seen
    assert not hidden


def test_faq63_overhanging_origins_are_clipped_but_targets_remain_physical(
    section17_definitions: Section02Definitions,
) -> None:
    native = geometry(frame_unit(section17_definitions), (Pose.at(0, 5),))[0]
    # Minimal exact physical rectangles test the shared existential boundary;
    # native overhanging-model geometry/provider admission remains unclaimed.
    overhanging = replace(native, base=RectangularBase(4, 1), body_parts=())
    outside = replace(overhanging, pose=Pose.at(-4, 5))
    inside = replace(overhanging, pose=Pose.at(6, 5))
    bounds = (Fraction(0), Fraction(0), Fraction(60), Fraction(44))

    def domains(model: Model) -> tuple[ModelDomain, ...]:
        return (ModelDomain.from_prism(model_visibility_prism(model)),)

    assert decide_physical_any(domains(overhanging), domains(inside), (), bounds)
    assert not decide_physical_any(domains(outside), domains(inside), (), bounds)
    assert decide_physical_any(domains(inside), domains(outside), (), bounds)
