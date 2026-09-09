from __future__ import annotations

import json
import math
from dataclasses import replace
from fractions import Fraction
from typing import cast

import pytest

from warhammer40k_core.core.attached_unit import AttachedUnit
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.unit import Unit, UnitMember
from warhammer40k_core.core.unit_group import UnitGroup
from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.collision import CollisionSet
from warhammer40k_core.geometry.movement_envelope import MovementEnvelope
from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import (
    PathFailureReason,
    PathQuery,
    PathResult,
    PathWitness,
)
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import ObstacleVolume, TerrainVolume
from warhammer40k_core.geometry.visibility_certificates import (
    all_corridors_blocked_by_plane,
    corridors_clear_by_enclosure,
    full_visibility_by_observer_caps,
)
from warhammer40k_core.geometry.visibility_corridor import (
    line_of_sight_corridor_bounds,
    line_of_sight_corridor_intersects_polygon,
    line_of_sight_corridor_intersects_polygon_union,
)
from warhammer40k_core.geometry.visibility_query import VisibilityQuery, VisibilityResult
from warhammer40k_core.geometry.visibility_shapes import (
    model_visibility_prism,
    terrain_visibility_prism,
)
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
            _movement_envelope(max_distance_inches=10.0) if envelope is None else envelope
        ),
        collision_set=CollisionSet.empty() if collision_set is None else collision_set,
    )


def _movement_envelope(
    *,
    max_distance_inches: float,
    sample_interval_inches: float = 1.0,
    required_coherency_neighbors: int | None = None,
) -> MovementEnvelope:
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
        sample_interval_inches=sample_interval_inches,
        required_coherency_neighbors=(
            coherency_policy.required_neighbors_small_unit
            if required_coherency_neighbors is None
            else required_coherency_neighbors
        ),
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


def test_p06c_sloped_corridor_height_is_evaluated_inside_flat_endpoint_strip() -> None:
    # In the strip's plane z=x, every obstacle point has x>=4 and z<=3.99.
    # Expanding the obstacle longitudinally before testing height invents a hit.
    obstacle = ObstacleVolume("slope", Point3(5, 0.015, 0), 2, 0.01, 3.99)
    result = VisibilityQuery.from_segment(
        Point3(0, 0, 0), Point3(10, 0, 10), static_terrain=(obstacle,)
    ).resolve()
    assert result.has_line_of_sight


def test_p06c_circular_blocker_keeps_analytic_arc_between_polygon_vertices() -> None:
    # The inscribed 256-gon loses radius at its chord midpoint. Place a horizontal
    # strip so its near edge cuts the real arc above that chord.
    from math import cos, pi, sin

    angle = pi / 256
    blocker = _model("circle", 0, 0)
    radius = 0.5
    half_width = 1 / 50.8
    normal = (cos(angle), sin(angle))
    tangent = (-normal[1], normal[0])
    offset = radius * (1 + cos(angle)) / 2 + half_width
    endpoints = tuple(
        Point3(offset * normal[0] + sign * tangent[0], offset * normal[1] + sign * tangent[1], 1)
        for sign in (-1, 1)
    )
    result = VisibilityQuery.from_segment(
        endpoints[0], endpoints[1], dynamic_model_blockers=(blocker,)
    ).resolve()
    assert not result.has_line_of_sight


@pytest.mark.parametrize(
    ("base", "x", "y", "expected"),
    [
        (CircularBase(0.5), 0.51, 0, True),
        (CircularBase(0.5), 0.53, 0, False),
        (OvalBase(2, 1), 1.01, 0, True),
        (OvalBase(2, 1), 1.03, 0, False),
        (OvalBase(2, 1), 0.71, 0.36, True),
        (OvalBase(2, 1), 0.75, 0.38, False),
        (RectangularBase(1, 1), 0.51, 0.51, True),
        (RectangularBase(1, 1), 0.516, 0.516, False),
    ],
)
def test_p06c_vertical_corridor_is_a_disk_for_every_supported_base(
    base: BaseShape,
    x: float,
    y: float,
    expected: bool,
) -> None:
    blocker = replace(_model("vertical-blocker", 0, 0), base=base)
    result = VisibilityQuery.from_segment(
        Point3(x, y, -1), Point3(x, y, 3), dynamic_model_blockers=(blocker,)
    ).resolve()
    assert result.has_line_of_sight is not expected
    reverse = VisibilityQuery.from_segment(
        Point3(x, y, 3), Point3(x, y, -1), dynamic_model_blockers=(blocker,)
    ).resolve()
    assert reverse == result


def test_p06c_corridor_float_bounds_enclose_the_exact_width() -> None:
    # VEX-02: subtracting the old rounded half-width used to yield max_y=0.
    rounded_radius = 1 / 50.8
    bounds = line_of_sight_corridor_bounds(
        Point3(-1, -rounded_radius, 0),
        Point3(1, -rounded_radius, 0),
    )
    assert Fraction(bounds[3]) >= Fraction(5, 254) - Fraction(rounded_radius) > 0


def test_p06c_continuous_certificates_preserve_alternative_observer_origins() -> None:
    observer = model_visibility_prism(replace(_model("observer", -3, 0), volume=ModelVolume(4)))
    target = model_visibility_prism(replace(_model("target", 3, 0), volume=ModelVolume(4)))
    low = terrain_visibility_prism(ObstacleVolume("low", Point3(0, 0, 0), 0.5, 4, 1))
    tall = terrain_visibility_prism(ObstacleVolume("tall", Point3(0, 0, 0), 0.5, 4, 5))

    assert corridors_clear_by_enclosure(observer, target, ())
    assert not corridors_clear_by_enclosure(observer, target, (low,))
    assert full_visibility_by_observer_caps(observer, target, (low,))
    assert not all_corridors_blocked_by_plane(observer, target, (low,))
    assert not full_visibility_by_observer_caps(observer, target, (tall,))
    assert all_corridors_blocked_by_plane(observer, target, (tall,))


def test_p06c_plane_certificate_proves_a_hidden_facing_part_over_all_origins() -> None:
    observer = model_visibility_prism(replace(_model("observer", -3, 0), base=CircularBase(0.001)))
    target = model_visibility_prism(_model("target", 3, 0))
    blocker = terrain_visibility_prism(ObstacleVolume("post", Point3(2.4, 0.15, 0), 0.1, 0.1, 3))
    u = Fraction(1, 5)
    # Rational circle parameterization gives an exact facing-surface point.
    hidden = (
        Fraction(3) - Fraction(1, 2) * (1 - u * u) / (1 + u * u),
        u / (1 + u * u),
        Fraction(1),
    )
    clear = (Fraction(5, 2), Fraction(0), Fraction(1))
    assert not all_corridors_blocked_by_plane(observer, target, (blocker,))
    assert all_corridors_blocked_by_plane(observer, target, (blocker,), target_point=hidden)
    assert not all_corridors_blocked_by_plane(observer, target, (blocker,), target_point=clear)


def test_p06c_cross_section_proof_does_not_cover_a_disjoint_zero_height_domain() -> None:
    observer = model_visibility_prism(_model("observer", -3, 0))
    target = model_visibility_prism(_model("target", 3, 0))
    wall = terrain_visibility_prism(ObstacleVolume("below", Point3(0, 0, 0), 0.5, 4, 2))
    top_origin = replace(observer, lower=Fraction(3), upper=Fraction(3))
    top_target = replace(target, lower=Fraction(3), upper=Fraction(3))
    assert not all_corridors_blocked_by_plane(top_origin, top_target, (wall,))


@pytest.mark.parametrize(
    ("kind", "visible", "full"),
    [
        ("clear", True, True),
        ("blocked", False, False),
        ("opening", True, False),
        ("partial", True, False),
        ("low", True, True),
    ],
)
def test_p06c_continuous_predicates_and_evidence_round_trip(
    kind: str, visible: bool, full: bool
) -> None:
    from warhammer40k_core.geometry.continuous_visibility import (
        ContinuousVisibilityEvidence,
        resolve_visibility_pair,
        resolve_visibility_pair_uncached,
    )

    origin = _model("observer", -3, 0)
    destination = _model("target", 3, 0)
    walls: tuple[TerrainVolume, ...] = ()
    if kind == "blocked":
        walls = (ObstacleVolume("solid", Point3(0, 0, 0), 0.1, 8, 3),)
    elif kind == "opening":
        # 0.1in opening > 1mm, with a clear corridor at y=.15.
        walls = (
            ObstacleVolume("lower", Point3(0, -1.95, 0), 0.1, 4.1, 3),
            ObstacleVolume("upper", Point3(0, 2.1, 0), 0.1, 3.8, 3),
        )
    elif kind == "partial":
        origin = replace(origin, base=CircularBase(0.001))
        walls = (ObstacleVolume("post", Point3(2.4, 0.15, 0), 0.1, 0.1, 3),)
    elif kind == "low":
        origin = replace(origin, volume=ModelVolume(4))
        destination = replace(destination, volume=ModelVolume(4))
        walls = (ObstacleVolume("low", Point3(0, 0, 0), 0.5, 4, 1),)
    observer, target = model_visibility_prism(origin), model_visibility_prism(destination)
    blockers = tuple(terrain_visibility_prism(wall) for wall in walls)
    result = resolve_visibility_pair_uncached(observer, target, blockers, blockers)
    assert (result.model_visible, result.model_fully_visible) == (visible, full)
    assert resolve_visibility_pair(observer, target, blockers, blockers) == result
    payload = json.loads(json.dumps(result.to_payload(), sort_keys=True))
    assert ContinuousVisibilityEvidence.from_payload(payload) == result
    payload["model_visible"] = not visible
    with pytest.raises(GeometryError):
        ContinuousVisibilityEvidence.from_payload(payload)


def test_p06c_self_visible_domain_excludes_vertical_only_tangent_support() -> None:
    from warhammer40k_core.geometry.visibility_algebra import decide, term
    from warhammer40k_core.geometry.visibility_formulas import (
        ModelDomain,
        _side_facing,  # pyright: ignore[reportPrivateUsage]
    )
    from warhammer40k_core.geometry.visibility_witnesses import point_has_self_visible_origin

    origin = replace(
        _model("observer", 0.5, 0),
        base=OvalBase(2, 1),
        pose=Pose.at(0.5, 0, facing_degrees=90),
        volume=ModelVolume(1),
    )
    destination = replace(_model("target", 0, 0, 2), base=CircularBase(1), volume=ModelVolume(1))
    observer = ModelDomain.from_prism(model_visibility_prism(origin))
    target = ModelDomain.from_prism(model_visibility_prism(destination))
    point = (Fraction(1), Fraction(0), Fraction(5, 2))
    assert not point_has_self_visible_origin(observer, target, point)
    assert not decide(
        _side_facing(
            observer, target, term(1), term(0), term(1), (term(1), term(0), term(Fraction(5, 2)))
        )
    )
    # Translating the observer along the tangent supplies a displaced origin.
    observer = replace(observer, center=(Fraction(1, 2), Fraction(1)))
    assert point_has_self_visible_origin(observer, target, point)
    assert decide(
        _side_facing(
            observer, target, term(1), term(0), term(1), (term(1), term(0), term(Fraction(5, 2)))
        )
    )


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("algorithm_id", "sampled:legacy"),
        ("input_fingerprint", "x" * 64),
        ("model_visible", 1),
        ("model_fully_visible", 1),
        ("visibility_proof", []),
        ("full_visibility_proof", {}),
        ("checked_witness_count", True),
        ("clear_corridor", [["0/1", "0/1", "0/1"]]),
        ("extra", "not allowed"),
    ],
)
def test_p06c_evidence_payload_rejects_malformed_identity_and_proofs(
    field: str, value: object
) -> None:
    from warhammer40k_core.geometry.continuous_visibility import ContinuousVisibilityEvidence

    valid = ContinuousVisibilityEvidence("a" * 64, True, True, "clear_enclosure", "clear_enclosure")
    payload = json.loads(json.dumps(valid.to_payload()))
    payload[field] = value
    with pytest.raises(GeometryError):
        ContinuousVisibilityEvidence.from_payload(payload)
    payload = json.loads(json.dumps(valid.to_payload()))
    del payload["algorithm_id"]
    with pytest.raises(GeometryError, match="fields"):
        ContinuousVisibilityEvidence.from_payload(payload)


@pytest.mark.parametrize("coordinate", ["0", "2/2", "1/0", "nan", 0, None])
def test_p06c_evidence_requires_canonical_exact_coordinates(coordinate: object) -> None:
    from warhammer40k_core.geometry.continuous_visibility import ContinuousVisibilityEvidence

    point = (Fraction(0), Fraction(0), Fraction(1))
    valid = ContinuousVisibilityEvidence(
        "a" * 64,
        True,
        False,
        "clear_corridor",
        "hidden_target_part",
        clear_corridor=(point, point),
        hidden_target_part=point,
    )
    payload = json.loads(json.dumps(valid.to_payload()))
    payload["hidden_target_part"][0] = coordinate
    with pytest.raises(GeometryError):
        ContinuousVisibilityEvidence.from_payload(payload)
    with pytest.raises(GeometryError, match="exact rational"):
        replace(
            valid, hidden_target_part=cast(tuple[Fraction, Fraction, Fraction], (0.0, 0.0, 1.0))
        )


def test_p06c_prisms_reject_invalid_geometry_before_broad_phase_can_hide_it() -> None:
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse, RationalPolygon

    circle = model_visibility_prism(_model("circle", 0, 0))
    with pytest.raises(ValueError, match="enclose"):
        replace(circle, bounds=(Fraction(0), Fraction(0), Fraction(0), Fraction(0)))
    with pytest.raises(ValueError, match="ordered rational"):
        replace(circle, upper=Fraction(-1))
    with pytest.raises(ValueError, match="independent axes"):
        RationalEllipse(
            (Fraction(0), Fraction(0)), (Fraction(1), Fraction(0)), (Fraction(2), Fraction(0))
        )
    with pytest.raises(ValueError, match="nondegenerate"):
        replace(circle, footprint=cast(RationalPolygon, []))
    with pytest.raises(ValueError, match="immutable exact rational"):
        replace(circle, footprint=cast(RationalPolygon, ((0.0, 0.0), (1.0, 0.0), (1.0, 1.0))))


def test_p06c_hidden_part_proof_includes_only_self_valid_origins_and_all_caps() -> None:
    from warhammer40k_core.geometry.visibility_formulas import ModelDomain
    from warhammer40k_core.geometry.visibility_witnesses import (
        point_has_self_visible_origin,
        self_visible_corridors_blocked,
    )

    observer = model_visibility_prism(_model("observer", -3, 0))
    target = model_visibility_prism(_model("target", 3, 0))
    domain = ModelDomain.from_prism(target)
    blocker = model_visibility_prism(_model("blocker", 0, 0.5))
    point = (Fraction(3), Fraction(1, 2), Fraction(2))
    assert point_has_self_visible_origin(ModelDomain.from_prism(observer), domain, point)
    assert not all_corridors_blocked_by_plane(observer, target, (blocker,), target_point=point)
    assert self_visible_corridors_blocked(observer, domain, point, (blocker,))
    # A taller observer can see this top-edge point through the top cap. The
    # side-only enclosure cannot be used to claim that the union is blocked.
    higher = replace(observer, upper=Fraction(4))
    assert not self_visible_corridors_blocked(higher, domain, point, (blocker,))


@pytest.mark.parametrize(
    ("first", "last", "bounds", "height", "blocked"),
    [
        ((0, 0, 0), (1, 1, 1), (".0005", "-.018", ".0015", "-.017"), ("0", "1"), False),
        ((-1, -1, 0), (1, 1, 2), ("-.001", ".015", ".001", ".016"), (".999", "1.001"), False),
        ((-1, -1, 0), (1, 1, 2), ("-.001", ".015", ".001", ".016"), ("0", "2"), True),
    ],
)
def test_p06c_width_certificate_preserves_flat_caps_and_sloped_height(
    first: tuple[int, int, int],
    last: tuple[int, int, int],
    bounds: tuple[str, str, str, str],
    height: tuple[str, str],
    blocked: bool,
) -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        all_box_corridors_blocked_by_plane,
    )
    from warhammer40k_core.geometry.visibility_exact import VisibilityPrism

    a = (Fraction(first[0]), Fraction(first[1]), Fraction(first[2]))
    b = (Fraction(last[0]), Fraction(last[1]), Fraction(last[2]))
    x0, y0, x1, y1 = map(Fraction, bounds)
    z0, z1 = map(Fraction, height)
    prism = VisibilityPrism(((x0, y0), (x1, y0), (x1, y1), (x0, y1)), z0, z1, (x0, y0, x1, y1))
    for start, end in ((a, b), (b, a)):
        first_box = ((start[0], start[1], start[0], start[1]), start[2], start[2])
        last_box = ((end[0], end[1], end[0], end[1]), end[2], end[2])
        assert all_box_corridors_blocked_by_plane(first_box, last_box, (prism,)) is blocked
        assert prism.intersects_corridor(start, end) is blocked


def test_p06c_planar_line_reduction_certifies_oblique_circular_obstruction() -> None:
    from warhammer40k_core.geometry.visibility_certificates import all_corridors_blocked_by_circle
    from warhammer40k_core.geometry.visibility_planar import (
        decide_planar_any,
        planar_line_reduction_applies,
    )

    observer = model_visibility_prism(_model("observer", -3, 0))
    target = model_visibility_prism(_model("target", 4.25, 1.25))
    blocker = model_visibility_prism(_model("blocker", 0, 0.5))
    assert planar_line_reduction_applies(observer, target, (blocker,))
    assert all_corridors_blocked_by_circle(observer, target, (blocker,))
    assert not decide_planar_any(observer, target, (blocker,))
    # Shortening the blocker opens vertical sightlines and invalidates the
    # planar reduction; it must not silently apply the infinite-height answer.
    low = replace(blocker, upper=Fraction(1))
    assert not planar_line_reduction_applies(observer, target, (low,))
    with pytest.raises(ValueError, match="preconditions"):
        decide_planar_any(observer, target, (low,))
    side = model_visibility_prism(_model("side", 0, 2))
    assert decide_planar_any(observer, target, (side,))


def test_p06c_parallel_top_origins_certify_the_stalled_tau_query() -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_parallel_circle_corridors,
    )

    observer_model = replace(
        _model("observer", 10, 28),
        base=CircularBase(0.6299212598425197),
        volume=ModelVolume(1.7637795275590549),
    )
    observer = model_visibility_prism(observer_model)
    target = model_visibility_prism(replace(observer_model, pose=Pose.at(20, 10)))
    blockers = tuple(
        model_visibility_prism(
            replace(observer_model, pose=Pose.at(x, 24), volume=ModelVolume(1.2598425196850394))
        )
        for x in (11, 12, 13)
    )
    assert full_visibility_by_parallel_circle_corridors(observer, target, blockers)


def test_p06c_parallel_top_origin_proof_requires_the_midpoint_guard() -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_parallel_circle_corridors,
    )
    from warhammer40k_core.geometry.visibility_footprints import polygon_visibility_prism
    from warhammer40k_core.geometry.visibility_formulas import ModelDomain
    from warhammer40k_core.geometry.visibility_witnesses import self_visible_corridors_blocked

    observer = model_visibility_prism(_model("observer", 0, 0))
    target = model_visibility_prism(_model("target", 10, 0))
    wall = polygon_visibility_prism(
        ((7.99, -1.0), (8.01, -1.0), (8.01, 1.0), (7.99, 1.0)),
        Fraction(0),
        Fraction(9, 25),
    )
    # Below the centre-to-centre sloped plane, but beyond its valid midpoint.
    # The facing bottom point is blocked even from the highest possible origin.
    assert not full_visibility_by_parallel_circle_corridors(observer, target, (wall,))
    assert self_visible_corridors_blocked(
        observer,
        ModelDomain.from_prism(target),
        (Fraction(19, 2), Fraction(0), Fraction(0)),
        (wall,),
    )


@pytest.mark.stubbed
@pytest.mark.parametrize("endpoint", ["observer", "target"])
@pytest.mark.parametrize("base", [CircularBase(0.5), OvalBase(2, 1), RectangularBase(2, 1)])
def test_p06c_endpoint_containment_finishes_without_quantified_solving(
    monkeypatch: pytest.MonkeyPatch, endpoint: str, base: BaseShape
) -> None:
    from warhammer40k_core.geometry import continuous_visibility

    def reject_quantified_solver(*args: object, **kwargs: object) -> bool:
        raise AssertionError("Exact endpoint containment must not invoke the quantified solver.")

    monkeypatch.setattr(continuous_visibility, "decide_any", reject_quantified_solver)
    monkeypatch.setattr(continuous_visibility, "decide_full", reject_quantified_solver)
    observer = model_visibility_prism(replace(_model("observer", 0, 0), base=base))
    target = model_visibility_prism(replace(_model("target", 8, 0), base=base))
    blocker = observer if endpoint == "observer" else target
    evidence = continuous_visibility.resolve_visibility_pair_uncached(
        observer, target, (blocker,), (blocker,)
    )
    assert not evidence.model_visible
    assert not evidence.model_fully_visible
    assert continuous_visibility.ContinuousVisibilityEvidence.from_payload(
        evidence.to_payload()
    ) == (evidence)


@pytest.mark.stubbed
@pytest.mark.parametrize(
    ("source_x", "target_x", "blocker_x", "radius"),
    [(10.0, 11.0, 12.0, 1.1811023622047243), (10.0, 32.0, 32.26, 0.6299212598425197)],
)
def test_p06c_rear_blockers_finish_without_quantified_solving(
    monkeypatch: pytest.MonkeyPatch,
    source_x: float,
    target_x: float,
    blocker_x: float,
    radius: float,
) -> None:
    from warhammer40k_core.geometry import continuous_visibility

    def reject_quantified_solver(*args: object, **kwargs: object) -> bool:
        raise AssertionError("Separated rear blocker must not invoke the quantified solver.")

    monkeypatch.setattr(continuous_visibility, "decide_full", reject_quantified_solver)
    prisms = tuple(
        model_visibility_prism(replace(_model("model", x, 20), base=CircularBase(radius)))
        for x in (source_x, target_x, blocker_x)
    )
    evidence = continuous_visibility.resolve_visibility_pair_uncached(
        prisms[0], prisms[1], (prisms[2],), (prisms[2],)
    )
    assert evidence.model_visible
    assert evidence.model_fully_visible


@pytest.mark.parametrize("offset", [Fraction(-1, 1000), Fraction(0), Fraction(1, 1000)])
@pytest.mark.parametrize(
    "direction", [(Fraction(1), Fraction(0)), (Fraction(3, 5), Fraction(4, 5))]
)
def test_p06c_rear_circle_proof_retains_flat_cap_contact(
    offset: Fraction, direction: tuple[Fraction, Fraction]
) -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_circle_separation,
    )
    from warhammer40k_core.geometry.visibility_exact import (
        CORRIDOR_RADIUS,
        RationalEllipse,
        VisibilityPrism,
    )

    def circle(x: Fraction, y: Fraction, radius: Fraction) -> VisibilityPrism:
        return VisibilityPrism(
            RationalEllipse((x, y), (radius, Fraction(0)), (Fraction(0), radius)),
            Fraction(0),
            Fraction(2),
            (x - radius, y - radius, x + radius, y + radius),
        )

    radius = Fraction(3, 5) + CORRIDOR_RADIUS
    ux, uy = direction
    observer = circle(Fraction(0), Fraction(0), radius)
    target = circle(ux, uy, radius)
    blocker = circle(ux * Fraction(9, 5), uy * Fraction(9, 5), Fraction(1) + offset)
    assert full_visibility_by_rear_circle_separation(observer, target, (blocker,)) is (offset < 0)
    start = (-uy * radius, ux * radius, Fraction(1))
    end = (ux - uy * radius, uy + ux * radius, Fraction(1))
    assert blocker.intersects_corridor(start, end) is (offset >= 0)


def test_p06c_rear_circle_proof_rejects_inapplicable_geometry() -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_circle_separation,
    )

    observer = model_visibility_prism(_model("observer", 0, 0))
    target = model_visibility_prism(_model("target", 1, 0))
    rear = model_visibility_prism(_model("rear", 2, 0))
    assert full_visibility_by_rear_circle_separation(observer, target, (rear,))
    assert not full_visibility_by_rear_circle_separation(observer, observer, (rear,))
    for other in (
        replace(target, upper=Fraction(3)),
        model_visibility_prism(replace(_model("unequal", 1, 0), base=CircularBase(0.75))),
        model_visibility_prism(replace(_model("box", 1, 0), base=RectangularBase(1, 1))),
    ):
        assert not full_visibility_by_rear_circle_separation(observer, other, (rear,))
    for blocker in (
        observer,
        model_visibility_prism(_model("off-axis", 2, 0.1)),
        model_visibility_prism(replace(_model("box", 2, 0), base=RectangularBase(1, 1))),
    ):
        assert not full_visibility_by_rear_circle_separation(observer, target, (blocker,))
    assert full_visibility_by_rear_circle_separation(
        observer, target, (replace(rear, lower=Fraction(3), upper=Fraction(4)),)
    )


@pytest.mark.parametrize("elevation", [0, 5])
@pytest.mark.parametrize("offset", [Fraction(-1, 1000), Fraction(0), Fraction(1, 1000)])
def test_p06c_parallel_top_origin_proof_preserves_exact_contact(
    elevation: int, offset: Fraction
) -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_parallel_circle_corridors,
    )
    from warhammer40k_core.geometry.visibility_footprints import polygon_visibility_prism
    from warhammer40k_core.geometry.visibility_formulas import ModelDomain
    from warhammer40k_core.geometry.visibility_witnesses import self_visible_corridors_blocked

    observer = model_visibility_prism(_model("observer", 0, 0, elevation))
    target = model_visibility_prism(_model("target", 10, 0, elevation))
    wall = polygon_visibility_prism(
        ((3.75, 0.375), (4.0, 0.375), (4.0, 0.625), (3.75, 0.625)),
        Fraction(elevation),
        Fraction(elevation) + Fraction(6, 5) + offset,
    )
    assert full_visibility_by_parallel_circle_corridors(observer, target, (wall,)) is (offset < 0)
    if offset >= 0:
        assert self_visible_corridors_blocked(
            observer,
            ModelDomain.from_prism(target),
            (Fraction(10), Fraction(1, 2), Fraction(elevation)),
            (wall,),
        )


@pytest.mark.parametrize("endpoint", ["observer", "target"])
def test_p06c_endpoint_containment_requires_the_entire_endpoint_volume(endpoint: str) -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        all_corridors_blocked_by_endpoint_containment,
    )

    observer = model_visibility_prism(_model("observer", 0, 0))
    target = model_visibility_prism(_model("target", 8, 0))
    source = observer if endpoint == "observer" else target
    for blocker in (replace(source, lower=Fraction(1)), replace(source, upper=Fraction(1))):
        assert not all_corridors_blocked_by_endpoint_containment(observer, target, (blocker,))
    displaced = model_visibility_prism(_model("displaced", 4, 0))
    assert not all_corridors_blocked_by_endpoint_containment(observer, target, (displaced,))
    expanded = replace(source, lower=Fraction(-1), upper=Fraction(3))
    assert all_corridors_blocked_by_endpoint_containment(observer, target, (expanded,))


@pytest.mark.parametrize("radius", [Fraction(2, 5), Fraction(12, 25)])
def test_p06c_planar_visibility_keeps_nonparallel_lines(radius: Fraction) -> None:
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse, VisibilityPrism
    from warhammer40k_core.geometry.visibility_planar import decide_planar_any

    observer = model_visibility_prism(_model("observer", -3, 0))
    target = model_visibility_prism(_model("target", 3, 0))
    blockers = tuple(
        VisibilityPrism(
            RationalEllipse((x, y), (radius, Fraction(0)), (Fraction(0), radius)),
            Fraction(0),
            Fraction(2),
            (x - radius, y - radius, x + radius, y + radius),
        )
        for x, y in [(Fraction(-1), Fraction(3, 10)), (Fraction(1), Fraction(-3, 10))]
    )
    # Every horizontal line is blocked. At radius .4 the tilted line y=x/6
    # passes between the posts; their strip-expanded intervals overlap at .48.
    assert decide_planar_any(observer, target, blockers) is (radius == Fraction(2, 5))


@pytest.mark.parametrize("offset", [Fraction(-1, 10**30), Fraction(0), Fraction(1, 10**30)])
def test_p06c_circle_enclosure_retains_exact_strip_tangency(offset: Fraction) -> None:
    from warhammer40k_core.geometry.visibility_certificates import all_corridors_blocked_by_circle
    from warhammer40k_core.geometry.visibility_exact import (
        CORRIDOR_RADIUS,
        RationalEllipse,
        VisibilityPrism,
    )
    from warhammer40k_core.geometry.visibility_planar import decide_planar_any

    observer = model_visibility_prism(_model("observer", -3, 0))
    target = model_visibility_prism(_model("target", 3, 0))
    radius = Fraction(1, 2) - CORRIDOR_RADIUS + offset
    blocker = VisibilityPrism(
        RationalEllipse((Fraction(0), Fraction(0)), (radius, Fraction(0)), (Fraction(0), radius)),
        Fraction(0),
        Fraction(2),
        (-radius, -radius, radius, radius),
    )
    assert all_corridors_blocked_by_circle(observer, target, (blocker,)) is (offset >= 0)
    assert decide_planar_any(observer, target, (blocker,)) is (offset < 0)


@pytest.mark.parametrize(
    ("base", "y", "fully_visible"),
    [
        (CircularBase(0.1), 0.0, True),
        (RectangularBase(0.1, 2), 0.0, False),
        (OvalBase(0.4, 0.2), 1.0, True),
    ],
)
def test_p06c_planar_full_uses_each_targets_own_self_valid_origin(
    base: BaseShape, y: float, fully_visible: bool
) -> None:
    from warhammer40k_core.geometry.continuous_visibility import resolve_visibility_pair_uncached
    from warhammer40k_core.geometry.visibility_planar import decide_planar_full

    observer = model_visibility_prism(_model("observer", -3, 0))
    target = model_visibility_prism(_model("target", 3, 0))
    blocker = model_visibility_prism(replace(_model("blocker", 0, y), base=base))
    if isinstance(base, OvalBase):
        # This off-axis analytic ellipse is separated from the complete corridor
        # enclosure. Exercise the production authority's proof before quantifier
        # elimination; an unbounded raw-solver run is not the gameplay path.
        result = resolve_visibility_pair_uncached(observer, target, (blocker,), (blocker,))
        assert result.model_fully_visible is fully_visible
    else:
        assert decide_planar_full(observer, target, (blocker,)) is fully_visible


def test_p06c_analytic_footprint_union_containment_preserves_holes_and_shared_edges() -> None:
    from warhammer40k_core.geometry.visibility_footprints import (
        model_within_visibility_polygons,
        visibility_polygon_within_union,
    )

    model = _model("circle", 0, 0)
    left = ((-1.0, -1.0), (0.0, -1.0), (0.0, 1.0), (-1.0, 1.0))
    right = ((0.0, -1.0), (1.0, -1.0), (1.0, 1.0), (0.0, 1.0))
    assert model_within_visibility_polygons(model, (left, right))
    frame = (
        ((-1.0, -1.0), (-0.1, -1.0), (-0.1, 1.0), (-1.0, 1.0)),
        ((0.1, -1.0), (1.0, -1.0), (1.0, 1.0), (0.1, 1.0)),
        ((-1.0, 0.1), (1.0, 0.1), (1.0, 1.0), (-1.0, 1.0)),
        ((-1.0, -1.0), (1.0, -1.0), (1.0, -0.1), (-1.0, -0.1)),
    )
    # The circle boundary is covered; its central disk is outside the union.
    assert not model_within_visibility_polygons(model, frame)
    middle = ((-0.5, -0.5), (0.5, -0.5), (0.5, 0.5), (-0.5, 0.5))
    assert visibility_polygon_within_union(middle, (left, right))
    assert not visibility_polygon_within_union(middle, frame)


@pytest.mark.parametrize("shape", [CircularBase(0.5), OvalBase(2, 0.4), RectangularBase(1, 0.5)])
@pytest.mark.parametrize("y", [0.0, 2.0])
@pytest.mark.parametrize("scale", [Fraction(1), Fraction(5, 4)])
def test_p06c_polynomial_clearance_matches_analytic_primitives(
    shape: BaseShape, y: float, scale: Fraction
) -> None:
    from warhammer40k_core.geometry.visibility_algebra import decide, term
    from warhammer40k_core.geometry.visibility_formulas import (
        _clear,  # pyright: ignore[reportPrivateUsage]
    )

    blocker = model_visibility_prism(
        replace(_model("blocker", 0, 0), base=shape, pose=Pose.at(0, 0, facing_degrees=31))
    )
    first = (Fraction(-3), Fraction(y), Fraction(0))
    last = (Fraction(3), Fraction(y), Fraction(3))
    formula, names = _clear(
        (term(first[0] * scale), term(first[1] * scale), term(first[2] * scale)),
        (term(last[0] * scale), term(last[1] * scale), term(last[2] * scale)),
        (blocker,),
        term(scale),
        planar=False,
    )
    assert decide(formula, names) is (not blocker.intersects_corridor(first, last))


@pytest.mark.parametrize(
    "invalid",
    [
        (),
        ((0, 0), (1, 1)),
        ((0, 0), (1, 0), (2, 0)),
        ((0, 0), (1, 0), (1, 1), (0, 0)),
        ((0, 0), (1, 1), (0, 1), (1, 0)),
        ((False, 0), (1, 0), (1, 1)),
        ((math.nan, 0), (1, 0), (1, 1)),
    ],
)
def test_p06c_corridor_polygon_validation_remains_eager(invalid: object) -> None:
    # VEX-01: a successful earlier union member must not conceal invalid data.
    start, end = Point3(-2, 0, 1), Point3(2, 0, 1)
    malformed = cast(tuple[tuple[float, float], ...], invalid)
    with pytest.raises(GeometryError):
        line_of_sight_corridor_intersects_polygon(start, end, malformed)
    valid = ((-1.0, -1.0), (1.0, -1.0), (1.0, 1.0), (-1.0, 1.0))
    with pytest.raises(GeometryError):
        line_of_sight_corridor_intersects_polygon_union(start, end, (valid, malformed))
    with pytest.raises(GeometryError):
        line_of_sight_corridor_intersects_polygon_union(start, end, ())


def test_p06a_visibility_uses_one_millimeter_corridor_for_terrain_and_model_hulls() -> None:
    terrain_near_miss = ObstacleVolume(
        terrain_id="terrain-near-miss",
        bottom_center=Point3(0.0, 0.015, 0.0),
        width=1.0,
        depth=0.01,
        height=3.0,
    )
    model_near_miss = _model("model-near-miss", 0.0, 0.51)
    centerline = (Point3(-3.0, 0.0, 1.0), Point3(3.0, 0.0, 1.0))

    terrain_result = VisibilityQuery.from_segment(
        *centerline,
        static_terrain=(terrain_near_miss,),
    ).resolve()
    model_result = VisibilityQuery.from_segment(
        *centerline,
        dynamic_model_blockers=(model_near_miss,),
    ).resolve()

    assert not terrain_result.has_line_of_sight
    assert terrain_result.blocking_terrain_ids == ("terrain-near-miss",)
    assert not model_result.has_line_of_sight
    assert model_result.blocking_model_ids == ("model-near-miss",)


def test_p06a_visibility_corridor_preserves_2_5d_height_and_half_width_boundary() -> None:
    horizontally_clear = ObstacleVolume(
        terrain_id="outside-half-width",
        bottom_center=Point3(0.0, 0.026, 0.0),
        width=1.0,
        depth=0.01,
        height=3.0,
    )
    vertically_clear = ObstacleVolume(
        terrain_id="below-corridor",
        bottom_center=Point3(0.0, 0.015, 0.0),
        width=1.0,
        depth=0.01,
        height=3.0,
    )

    assert (
        VisibilityQuery.from_segment(
            Point3(-3.0, 0.0, 1.0),
            Point3(3.0, 0.0, 1.0),
            static_terrain=(horizontally_clear,),
        )
        .resolve()
        .has_line_of_sight
    )
    assert (
        VisibilityQuery.from_segment(
            Point3(-3.0, 0.0, 4.0),
            Point3(3.0, 0.0, 4.0),
            static_terrain=(vertically_clear,),
        )
        .resolve()
        .has_line_of_sight
    )


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


def test_path_query_accepts_two_pose_straight_movement_witness() -> None:
    start = Pose.at(0.0, 0.0)
    end = Pose.at(4.0, 0.0)
    witness = PathWitness.for_straight_line_endpoints((("mover-1", start, end),))
    query = _query_for_single_model(witness)

    result = query.evaluate()

    assert witness.poses_for_model("mover-1") == (start, end)
    assert result.is_valid
    assert result.metrics.sampled_pose_count == 5


def test_path_query_accepts_explicit_zero_displacement_no_op_witness() -> None:
    query = _query_for_single_model(_single_model_witness(Pose.at(0.0, 0.0), Pose.at(0.0, 0.0)))

    result = query.evaluate()

    assert result.is_valid
    assert result.metrics.sampled_pose_count == 2


def test_path_query_accepts_stationary_model_in_group_witness() -> None:
    first = _model("mover-1", 0.0, 0.0)
    second = _model("mover-2", 2.0, 0.0)
    unit_group = UnitGroup.single(_unit("movers", "mover-1", "mover-2"))
    witness = PathWitness.for_paths(
        (
            ("mover-1", (Pose.at(0.0, 0.0), Pose.at(0.25, 0.0), Pose.at(0.5, 0.0))),
            ("mover-2", (Pose.at(2.0, 0.0), Pose.at(2.0, 0.0))),
        )
    )

    result = PathQuery(
        unit_group=unit_group,
        spatial_index=SpatialIndex.empty().with_model(first).with_model(second),
        witness=witness,
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert result.is_valid
    assert result.metrics.sampled_pose_count == 5


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
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(4.0, 0.0)),
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
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(4.0, 0.0)),
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
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(4.0, 0.0)),
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
        movement_envelope=_movement_envelope(max_distance_inches=20.0),
        collision_set=CollisionSet.empty(),
    )

    result = query.evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.COHERENCY


def test_movement_envelope_can_require_two_coherency_neighbors() -> None:
    envelope = _movement_envelope(max_distance_inches=10.0, required_coherency_neighbors=2)
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
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()
    complete_result = PathQuery(
        unit_group=group,
        spatial_index=index,
        witness=complete,
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
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
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
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
        movement_envelope=_movement_envelope(max_distance_inches=10.0),
        collision_set=CollisionSet.empty(),
    ).evaluate()

    assert not result.is_valid
    assert result.failure is not None
    assert result.failure.reason is PathFailureReason.SELF_COLLISION
    assert result.failure.model_id == "mover-1"
    assert result.failure.blocker_id == "mover-2"


def test_pathing_payloads_round_trip_without_object_reprs() -> None:
    witness = _single_model_witness(Pose.at(0.0, 0.0), Pose.at(1.0, 0.0), Pose.at(2.0, 0.0))
    envelope = _movement_envelope(
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
        _single_model_witness(Pose.at(0.0, 0.0), Pose.at(4.0, 0.0), Pose.at(4.0, 0.0))
    ).evaluate()
    payload = result.to_payload()
    payload["is_valid"] = True

    with pytest.raises(GeometryError, match="Valid PathResult payload"):
        PathResult.from_payload(payload)


def _mandatory_endpoint_query(
    *, target_x: float = 6.0, budget: float = 3.0
) -> MovementReachabilityQuery:
    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
    from warhammer40k_core.engine.movement_legality import MovementLegalityContext
    from warhammer40k_core.geometry.movement_reachability import (
        MovementGoal,
        MovementReachabilityQuery,
    )

    moving = _model("reachability:mover", 2.0, 2.0)
    target = _model("reachability:target", target_x, 2.0)
    witness = PathWitness.for_paths(((moving.model_id, (moving.pose, moving.pose)),))
    legality = MovementLegalityContext.from_keywords(
        keywords=("INFANTRY",),
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.CONSOLIDATE,
        movement_phase_action=None,
        displacement_kind=ModelDisplacementKind.CONSOLIDATE,
    )
    return MovementReachabilityQuery(
        path_context=legality.to_path_validation_context(
            moving_model=moving,
            witness=witness,
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            friendly_models=(),
            enemy_models=(target,),
            terrain=(),
            movement_distance_budget_inches=budget,
        ),
        terrain_context=legality.to_terrain_path_legality_context(
            moving_model=moving, witness=witness, terrain=(), terrain_features=()
        ),
        goal=MovementGoal(models=(target,), horizontal_inches=1.0, vertical_inches=5.0),
    )


def test_mandatory_endpoint_search_returns_validated_paths_and_bounded_cached_answers() -> None:
    from warhammer40k_core.geometry.movement_reachability import (
        MovementReachabilityStatus,
        clear_movement_reachability_cache,
        movement_reachability,
        movement_reachability_cache_info,
    )

    clear_movement_reachability_cache()
    query = _mandatory_endpoint_query()
    result = movement_reachability(query)
    assert result.status is MovementReachabilityStatus.REACHABLE
    assert result.witness is not None
    assert replace(query.path_context, witness=result.witness).validate().is_valid
    assert replace(query.terrain_context, witness=result.witness).validate().is_valid
    assert len(result.witness.poses_for_model(query.path_context.moving_model.model_id)) >= 3
    for _ in range(32):
        assert movement_reachability(_mandatory_endpoint_query()) is result
    assert movement_reachability_cache_info() == (32, 1, 512, 1)
    far = movement_reachability(_mandatory_endpoint_query(target_x=10.0))
    assert far.status is MovementReachabilityStatus.UNREACHABLE
    assert far.witness is None
    assert far.explored_nodes == 0
    short = movement_reachability(_mandatory_endpoint_query(budget=1.0))
    assert short.status is MovementReachabilityStatus.UNREACHABLE
    assert movement_reachability_cache_info()[1] == 3
    for index in range(513):
        movement_reachability(_mandatory_endpoint_query(target_x=20.0 + index))
    assert movement_reachability_cache_info()[3] == 512


def test_mandatory_endpoint_search_routes_around_a_blocker_and_does_not_reuse_stale_geometry() -> (
    None
):
    from warhammer40k_core.geometry.movement_reachability import (
        MovementReachabilityStatus,
        clear_movement_reachability_cache,
        movement_reachability,
    )

    clear_movement_reachability_cache()
    query = _mandatory_endpoint_query(budget=5.0)
    direct = movement_reachability(query)
    blocker = _model("reachability:blocker", 4.0, 2.0)
    blocked = replace(
        query,
        path_context=replace(
            query.path_context, enemy_models=(*query.path_context.enemy_models, blocker)
        ),
    )
    result = movement_reachability(blocked)
    assert result.status is MovementReachabilityStatus.REACHABLE
    assert result.witness is not None
    assert result.witness != direct.witness
    assert replace(blocked.path_context, witness=result.witness).validate().is_valid
    assert replace(blocked.terrain_context, witness=result.witness).validate().is_valid
    assert result.explored_nodes > direct.explored_nodes


def test_mandatory_endpoint_search_never_treats_unresolved_search_as_impossible() -> None:
    from warhammer40k_core.geometry.movement_reachability import (
        MovementReachabilityStatus,
        movement_reachability,
    )

    query = _mandatory_endpoint_query()
    # No endpoint can both satisfy and avoid the same range. A route-search miss
    # alone is not proof, even when the contradiction looks obvious to a caller.
    result = movement_reachability(replace(query, forbidden_goals=(query.goal,)))
    assert result.witness is None
    assert result.status is MovementReachabilityStatus.UNRESOLVED


@pytest.mark.parametrize("base", [CircularBase(0.5), OvalBase(2.0, 1.0), RectangularBase(2.0, 1.0)])
@pytest.mark.parametrize("ignores_vertical", [False, True])
@pytest.mark.parametrize("goal_kind", ["model", "disk", "polygon"])
@pytest.mark.parametrize("target_x", [6.0, 12.0])
def test_mandatory_endpoint_distance_proofs_cover_all_bases_and_distance_policies(
    base: BaseShape, ignores_vertical: bool, goal_kind: str, target_x: float
) -> None:
    from warhammer40k_core.geometry.movement_reachability import (
        MovementGoal,
        MovementReachabilityStatus,
        movement_reachability,
    )

    query = _mandatory_endpoint_query(target_x=target_x)
    moving = replace(query.path_context.moving_model, base=base)
    goal = query.goal
    if goal_kind == "disk":
        goal = MovementGoal(
            disk=(Pose.at(target_x, 2.0), CircularBase(0.5)),
            horizontal_inches=1.0,
            vertical_inches=5.0,
        )
    elif goal_kind == "polygon":
        goal = MovementGoal(
            polygons=(
                (
                    (target_x - 0.5, 1.5),
                    (target_x + 0.5, 1.5),
                    (target_x + 0.5, 2.5),
                    (target_x - 0.5, 2.5),
                ),
            ),
            horizontal_inches=1.0,
            vertical_inches=5.0,
        )
    query = replace(
        query,
        goal=goal,
        path_context=replace(
            query.path_context, moving_model=moving, ignores_vertical_distance=ignores_vertical
        ),
        terrain_context=replace(query.terrain_context, moving_model=moving),
    )
    result = movement_reachability(query)
    if target_x == 12.0:
        assert result.status is MovementReachabilityStatus.UNREACHABLE
        assert result.explored_nodes == 0
        assert result.witness is None
    else:
        assert result.status is MovementReachabilityStatus.REACHABLE
        assert result.witness is not None
        assert replace(query.path_context, witness=result.witness).validate().is_valid
        assert replace(query.terrain_context, witness=result.witness).validate().is_valid


def test_mandatory_endpoint_horizontal_policy_does_not_charge_vertical_goal_distance() -> None:
    from warhammer40k_core.geometry.movement_reachability import movement_reachability

    query = _mandatory_endpoint_query(target_x=6.0)
    elevated = replace(query.goal.models[0], pose=Pose.at(6.0, 2.0, 30.0))
    goal = replace(query.goal, models=(elevated,))
    assert goal.distance_lower_bound(query.path_context.moving_model) > 3.0
    assert (
        goal.distance_lower_bound(query.path_context.moving_model, ignores_vertical_distance=True)
        <= 3.0
    )
    # Reaching the horizontal region is still possible; no false impossibility
    # certificate may bypass navigation/terrain validation for the height change.
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityStatus

    result = movement_reachability(
        replace(
            query,
            goal=goal,
            path_context=replace(query.path_context, ignores_vertical_distance=True),
        )
    )
    assert result.status is not MovementReachabilityStatus.UNREACHABLE


def test_mandatory_endpoint_witness_also_satisfies_strict_closer_constraint() -> None:
    from warhammer40k_core.geometry.movement_reachability import movement_reachability

    query = replace(_mandatory_endpoint_query(target_x=4.0), maximum_target_range_inches=0.5)
    result = movement_reachability(query)
    assert result.witness is not None
    source = query.path_context.moving_model
    final = replace(source, pose=result.witness.final_pose_for_model(source.model_id))
    assert final.range_to(query.goal.models[0]) < 0.5
    assert final.pose != source.pose


def test_mandatory_endpoint_witness_cannot_break_vertical_unit_span() -> None:
    from warhammer40k_core.geometry.movement_reachability import movement_reachability

    query = _mandatory_endpoint_query()
    peers = (_model("peer:low", 4.0, 2.0, 4.0), _model("peer:high", 6.0, 2.0, 8.0))
    query = replace(
        query,
        coherent_models=peers,
        coherency_max_span_inches=6.0,
        path_context=replace(query.path_context, friendly_models=peers),
    )
    # The chain has neighbors, but the ground model and upper peer exceed the
    # descriptor's vertical whole-unit span. That cannot prove a legal endpoint.
    assert movement_reachability(query).witness is None
