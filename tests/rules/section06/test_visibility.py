"""06.01 and FAQ53: physical native geometry plus labelled millimetre contracts."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import LORD_EXULTANT, MAULERFIEND, Section02Definitions
from tests.support.section03_fixtures import geometry
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.visibility import TerrainVisibilityContext, VisibilityQuery
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose
from warhammer40k_core.geometry.terrain import (
    ObstacleVolume,
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.visibility_exact import VisibilityPrism


@pytest.mark.parametrize(("edge", "clear"), [(0.49 / 25.4, False), (0.51 / 25.4, True)])
@pytest.mark.parametrize("height", [1.0, 4.0])
def test_one_millimetre_corridor_and_vertical_clearance(
    edge: float, clear: bool, height: float
) -> None:
    # Constructed submillimetre terrain, at real production segment evaluator.
    wall = ObstacleVolume(
        terrain_id="s06:edge", bottom_center=Point3(0, edge + 0.05, 0), width=1, depth=0.1, height=3
    )
    result = VisibilityQuery.from_segment(
        Point3(-3, 0, height), Point3(3, 0, height), static_terrain=(wall,)
    ).resolve()
    assert result.has_line_of_sight is (clear or height > 3)


@pytest.mark.parametrize(
    ("height", "visible", "fully"),
    [(0.0, True, True), (1.0, True, True), (3.0, True, False), (8.0, False, False)],
)
def test_any_model_part_and_every_facing_part_native_geometry(
    section06_definitions: Section02Definitions,
    height: float,
    visible: bool,
    fully: bool,
) -> None:
    d = section06_definitions
    observer_unit = d.unit(MAULERFIEND)
    target_unit = d.unit(LORD_EXULTANT, identity="target")
    observer = geometry(observer_unit, (Pose.at(10, 10),))[0]
    target = geometry(target_unit, (Pose.at(20, 10),))[0]
    walls = (
        ()
        if height == 0
        else (
            ObstacleVolume(
                terrain_id="s06:wall",
                bottom_center=Point3(15, 10, 0),
                width=0.2,
                depth=20,
                height=height,
            ),
        )
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s06:parts",
        observer_model=observer,
        target_models=(target,),
        target_model_keywords=((target.model_id, target_unit.own_models[0].keywords),),
        terrain_volumes=walls,
        observer_keywords=observer_unit.own_models[0].keywords,
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible is visible
    assert witness.unit_fully_visible is fully
    assert witness.visible_model_ids == ((target.model_id,) if visible else ())
    if height == 1:
        # Base-level sight is blocked; native upper-body origins see every facing part.
        assert (
            not VisibilityQuery.from_segment(
                Point3(10, 10, 0), Point3(20, 10, 0), static_terrain=walls
            )
            .resolve()
            .has_line_of_sight
        )
        assert witness.unit_fully_visible
    changed = replace(context, target_models=(replace(target, pose=Pose.at(22, 10)),))
    with pytest.raises(GeometryError, match=r"geometry|evidence"):
        changed.benefit_of_cover(witness)


@pytest.mark.parametrize("blocked", [0, 1, 2])
def test_unit_visible_any_and_fully_visible_all_native_members(
    section06_definitions: Section02Definitions, blocked: int
) -> None:
    d = section06_definitions
    observer = geometry(d.unit(LORD_EXULTANT), (Pose.at(10, 10),))[0]
    unit = d.unit()
    # Two surviving physical native models are a casualty-state contract.
    unit = replace(unit, own_models=unit.own_models[:2])
    targets = geometry(unit, (Pose.at(20, 10), Pose.at(20, 20)))
    walls = tuple(
        ObstacleVolume(
            terrain_id=f"s06:enclose-{i}",
            bottom_center=Point3(20, 10 + 10 * i, 0),
            width=3,
            depth=3,
            height=8,
        )
        for i in range(blocked)
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s06:unit",
        observer_model=observer,
        target_models=targets,
        target_model_keywords=tuple(
            (m.model_id, unit.own_models[i].keywords) for i, m in enumerate(targets)
        ),
        terrain_volumes=walls,
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible is (blocked < 2)
    assert witness.unit_fully_visible is (blocked == 0)
    assert set(witness.visible_model_ids) == {m.model_id for m in targets[blocked:]}


def test_ruins_rules_footprint_can_block_without_physical_wall(
    section06_definitions: Section02Definitions,
) -> None:
    d = section06_definitions
    observer = geometry(d.unit(LORD_EXULTANT), (Pose.at(10, 10),))[0]
    target = geometry(d.unit(LORD_EXULTANT, identity="target"), (Pose.at(20, 10),))[0]
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=15,
        center_y_inches=10,
        width_inches=4,
        depth_inches=6,
        display_template_id="s06:ruin",
    )
    ruin = TerrainFeatureDefinition(
        feature_id="s06:ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=15,
        footprint_center_y_inches=10,
        footprint_width_inches=4,
        footprint_depth_inches=6,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        source_id="constructed:s06:ruin",
        walls=(
            TerrainWallDefinition(
                wall_id="off-axis",
                center_x_inches=15,
                center_y_inches=12.8,
                bottom_z_inches=0,
                width_inches=1,
                depth_inches=0.1,
                height_inches=3,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="floor",
                center_x_inches=15,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=4,
                depth_inches=6,
                thickness_inches=0.1,
            ),
        ),
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        los_cache_key="s06:ruin",
        observer_model=observer,
        target_models=(target,),
        target_model_keywords=((target.model_id, ()),),
        terrain_features=(ruin,),
    )
    assert (
        VisibilityQuery.from_segment(
            Point3(10, 10, 1), Point3(20, 10, 1), static_terrain=ruin.terrain_volumes()
        )
        .resolve()
        .has_line_of_sight
    )
    assert not context.resolve_line_of_sight().unit_visible
    assert (
        replace(context, terrain_features=(), terrain_volumes=())
        .resolve_line_of_sight()
        .unit_fully_visible
    )


@pytest.mark.parametrize(("observer_radius", "target_radius"), [(1, 1), (1, 2), (2, 1)])
@pytest.mark.parametrize("offset", [-1, 0, 1])
def test_rear_plane_certificate_preserves_strict_rational_boundary(
    observer_radius: int, target_radius: int, offset: int
) -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_plane_separation,
    )
    from warhammer40k_core.geometry.visibility_exact import (
        CORRIDOR_RADIUS,
        RationalEllipse,
        VisibilityPrism,
    )

    observer = VisibilityPrism(
        RationalEllipse((F(0), F(0)), (F(observer_radius), F(0)), (F(0), F(observer_radius))),
        F(0),
        F(1),
        (F(-observer_radius), F(-observer_radius), F(observer_radius), F(observer_radius)),
    )
    target = VisibilityPrism(
        RationalEllipse((F(10), F(0)), (F(target_radius), F(0)), (F(0), F(target_radius))),
        F(0),
        F(2),
        (F(10 - target_radius), F(-target_radius), F(10 + target_radius), F(target_radius)),
    )
    boundary = F(10) + F(target_radius * (observer_radius - target_radius), 10) + CORRIDOR_RADIUS
    left = boundary + F(offset, 10**9)
    blocker = VisibilityPrism(
        ((left, F(-3)), (left + 1, F(-3)), (left + 1, F(3)), (left, F(3))),
        F(0),
        F(2),
        (left, F(-3), left + 1, F(3)),
    )
    assert full_visibility_by_rear_plane_separation(observer, target, (blocker,)) is (offset > 0)


@pytest.mark.parametrize(
    "invalid_scope", ["upper-cap", "lower-cap", "overlap", "coincident", "tangent", "flat"]
)
def test_rear_plane_certificate_declines_unproved_scope(invalid_scope: str) -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_plane_separation,
    )
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse, VisibilityPrism

    observer = VisibilityPrism(
        RationalEllipse((F(0), F(0)), (F(1), F(0)), (F(0), F(1))),
        F(0),
        F(1),
        (F(-1), F(-1), F(1), F(1)),
    )
    target = VisibilityPrism(
        RationalEllipse((F(10), F(0)), (F(2), F(0)), (F(0), F(2))),
        F(0),
        F(2),
        (F(8), F(-2), F(12), F(2)),
    )
    if invalid_scope == "upper-cap":
        observer = replace(observer, upper=F(3))
    elif invalid_scope == "lower-cap":
        observer = replace(observer, lower=F(-1))
    elif invalid_scope in {"overlap", "coincident", "tangent"}:
        assert isinstance(target.footprint, RationalEllipse)
        x = F({"overlap": 2, "coincident": 0, "tangent": 3}[invalid_scope])
        target = replace(
            target,
            footprint=replace(target.footprint, center=(x, F(0))),
            bounds=(x - 2, F(-2), x + 2, F(2)),
        )
    else:
        target = replace(
            target, footprint=((F(9), F(-1)), (F(11), F(-1)), (F(11), F(1)), (F(9), F(1)))
        )
    assert not full_visibility_by_rear_plane_separation(observer, target, ())


def _retained_visibility_domains(
    case: str,
) -> tuple[VisibilityPrism, VisibilityPrism, tuple[VisibilityPrism, ...]]:
    import json
    from fractions import Fraction as F
    from pathlib import Path
    from typing import Any, cast

    from warhammer40k_core.geometry.visibility_exact import RationalEllipse, RationalPolygon

    fixture = Path(__file__).resolve().parents[2] / "fixtures/sorcerer_visibility_domains.json"
    row: dict[str, Any] = json.loads(fixture.read_text())["cases"][case]

    def point(values: list[str]) -> tuple[F, F]:
        return F(values[0]), F(values[1])

    def prism(raw: dict[str, Any]) -> VisibilityPrism:
        source = raw["footprint"]
        footprint: RationalEllipse | RationalPolygon
        if isinstance(source, dict):
            source = cast(dict[str, list[str]], source)
            footprint = RationalEllipse(
                point(source["center"]), point(source["first_axis"]), point(source["second_axis"])
            )
        else:
            footprint = tuple(point(p) for p in source)
        bounds = raw["bounds"]
        return VisibilityPrism(
            footprint,
            F(raw["lower"]),
            F(raw["upper"]),
            (F(bounds[0]), F(bounds[1]), F(bounds[2]), F(bounds[3])),
        )

    return prism(row["observer"]), prism(row["target"]), tuple(prism(b) for b in row["blockers"])


def test_rear_plane_certifies_retained_diagonal_concave_blocker() -> None:
    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_plane_separation,
    )

    observer, target, blockers = _retained_visibility_domains("original")
    assert full_visibility_by_rear_plane_separation(observer, target, blockers)


def test_unequal_circle_candidates_prove_retained_hidden_part_and_clear_gap() -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.continuous_visibility import resolve_visibility_pair_uncached
    from warhammer40k_core.geometry.visibility_formulas import (
        ModelDomain,
        decide_target_part_visible,
    )
    from warhammer40k_core.geometry.visibility_witnesses import (
        point_has_self_visible_origin,
        point_in_model,
        self_visible_corridors_blocked,
        target_part_candidates,
    )

    observer, target, blockers = _retained_visibility_domains("continuation")
    origin, destination = ModelDomain.from_prism(observer), ModelDomain.from_prism(target)
    witnesses = tuple(
        p
        for p in target_part_candidates(origin, destination, blockers)
        if point_has_self_visible_origin(origin, destination, p)
        and self_visible_corridors_blocked(observer, destination, p, blockers)
    )
    assert witnesses
    # Completed original existential NRA predicates independently check this
    # actual generated point. The full historical forall/exists stall remains
    # retained; these are not a claimed completed whole-query comparison.
    assert not decide_target_part_visible(origin, destination, witnesses[0], blockers)
    assert decide_target_part_visible(origin, destination, witnesses[0], blockers[:1])
    assert all(point_in_model(destination, p) for p in witnesses)
    result = resolve_visibility_pair_uncached(observer, target, blockers, blockers)
    assert result.model_visible
    assert not result.model_fully_visible
    assert result.full_visibility_proof == "hidden_target_part"
    assert result.hidden_target_part in witnesses
    # Removing the near-observer blocker removes the hidden-part proof. This is
    # an adjacent control; the original native scene remains unchanged elsewhere.
    assert not self_visible_corridors_blocked(observer, destination, witnesses[0], blockers[:1])
    clear = resolve_visibility_pair_uncached(observer, target, blockers[:1], blockers[:1])
    assert clear.model_visible
    assert clear.model_fully_visible
    invalid_facing = (destination.center[0] + destination.axes[0][0], destination.center[1], F(0))
    assert point_in_model(destination, invalid_facing)
    assert not point_has_self_visible_origin(origin, destination, invalid_facing)


@pytest.mark.parametrize("scope", ["equal", "ellipse", "flat", "coincident", "contained"])
def test_unequal_circle_search_retains_fallback_for_other_domains(scope: str) -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_formulas import ModelDomain
    from warhammer40k_core.geometry.visibility_witnesses import (
        target_part_candidates,
        unequal_circle_tangent_candidates,
    )

    first, last, _ = _retained_visibility_domains("continuation")
    observer, target = ModelDomain.from_prism(first), ModelDomain.from_prism(last)
    if scope == "equal":
        observer = replace(observer, axes=target.axes)
    elif scope == "ellipse":
        target = replace(target, axes=((F(1), F(0)), (F(0), F(2))))
    elif scope == "flat":
        target = replace(target, curved=False)
    elif scope == "coincident":
        observer = replace(observer, center=target.center)
    else:
        observer = replace(observer, center=(target.center[0] + F(1, 100), target.center[1]))
    assert not unequal_circle_tangent_candidates(observer, target)
    assert target_part_candidates(observer, target, ())


@pytest.mark.parametrize("height", ["below", "lower-contact", "upper-contact", "above"])
def test_rear_plane_requires_strict_vertical_disjointness(height: str) -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_plane_separation,
    )

    observer, target, blockers = _retained_visibility_domains("continuation")
    front = blockers[1]
    if height in {"below", "lower-contact"}:
        upper = target.lower - (F(1, 10**9) if height == "below" else 0)
        front = replace(front, lower=upper - 1, upper=upper)
    else:
        lower = target.upper + (F(1, 10**9) if height == "above" else 0)
        front = replace(front, lower=lower, upper=lower + 1)
    assert full_visibility_by_rear_plane_separation(observer, target, (blockers[0], front)) is (
        height in {"below", "above"}
    )


def test_rear_plane_analytic_ellipse_support_and_multiple_blockers() -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_plane_separation,
    )
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse

    observer, target, blockers = _retained_visibility_domains("original")
    ellipse = VisibilityPrism(
        RationalEllipse((F(40), F(10)), (F(1), F(1)), (F(-2), F(2))),
        F(0),
        target.upper,
        (F(37), F(7), F(43), F(13)),
    )
    assert full_visibility_by_rear_plane_separation(observer, target, (*blockers, ellipse))
    assert isinstance(ellipse.footprint, RationalEllipse)
    front = replace(
        ellipse,
        footprint=replace(ellipse.footprint, center=(F(20), F(4))),
        bounds=(F(17), F(1), F(23), F(7)),
    )
    assert not full_visibility_by_rear_plane_separation(observer, target, (*blockers, front))


def test_rear_plane_full_proof_does_not_hide_a_different_any_visibility_blocker() -> None:
    from warhammer40k_core.geometry.continuous_visibility import resolve_visibility_pair_uncached

    observer, target, blockers = _retained_visibility_domains("original")
    result = resolve_visibility_pair_uncached(observer, target, (target,), blockers)
    assert not result.model_visible
    assert not result.model_fully_visible


def test_rear_plane_empty_scene_agrees_with_complete_quantified_reference() -> None:
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_certificates import (
        full_visibility_by_rear_plane_separation,
    )
    from warhammer40k_core.geometry.visibility_exact import RationalEllipse
    from warhammer40k_core.geometry.visibility_formulas import ModelDomain, decide_full

    observer = VisibilityPrism(
        RationalEllipse((F(0), F(0)), (F(1), F(0)), (F(0), F(1))),
        F(0),
        F(1),
        (F(-1), F(-1), F(1), F(1)),
    )
    target = VisibilityPrism(
        RationalEllipse((F(10), F(0)), (F(1), F(0)), (F(0), F(1))),
        F(0),
        F(1),
        (F(9), F(-1), F(11), F(1)),
    )
    assert full_visibility_by_rear_plane_separation(observer, target, ())
    assert decide_full(ModelDomain.from_prism(observer), ModelDomain.from_prism(target), ())


@pytest.mark.parametrize("shape", ["ellipse", "flat"])
@pytest.mark.parametrize("offset_sign", [-1, 0, 1])
def test_exact_corridor_contact_survives_rear_proof_search(shape: str, offset_sign: int) -> None:
    # Narrow active port of the quarantined test_visibility_pathing.py exact
    # strip-tangency concept; the legacy module and its admission remain intact.
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_exact import CORRIDOR_RADIUS, RationalEllipse

    edge = CORRIDOR_RADIUS + F(offset_sign, 10**30)
    if shape == "ellipse":
        obstacle = VisibilityPrism(
            RationalEllipse((F(0), edge + 2), (F(1), F(0)), (F(0), F(2))),
            F(0),
            F(2),
            (F(-1), edge, F(1), edge + 4),
        )
    else:
        obstacle = VisibilityPrism(
            ((F(-1), edge), (F(1), edge), (F(1), edge + 1), (F(-1), edge + 1)),
            F(0),
            F(2),
            (F(-1), edge, F(1), edge + 1),
        )
    assert obstacle.intersects_corridor((F(-3), F(0), F(1)), (F(3), F(0), F(1))) is (
        offset_sign <= 0
    )


@pytest.mark.parametrize("displaced", [False, True])
def test_facing_witness_requires_a_horizontal_origin_at_exact_tangency(displaced: bool) -> None:
    # Port the relevant vertical-only tangent-support invariant with real exact
    # prisms and the public complete target-part predicate, without private hooks.
    from fractions import Fraction as F

    from warhammer40k_core.geometry.visibility_exact import RationalEllipse
    from warhammer40k_core.geometry.visibility_formulas import (
        ModelDomain,
        decide_target_part_visible,
    )
    from warhammer40k_core.geometry.visibility_witnesses import point_has_self_visible_origin

    y = F(1 if displaced else 0)
    observer = VisibilityPrism(
        RationalEllipse((F(1, 2), y), (F(1, 2), F(0)), (F(0), F(1))),
        F(0),
        F(1),
        (F(0), y - 1, F(1), y + 1),
    )
    target = VisibilityPrism(
        RationalEllipse((F(0), F(0)), (F(1), F(0)), (F(0), F(1))),
        F(2),
        F(3),
        (F(-1), F(-1), F(1), F(1)),
    )
    origin, destination = ModelDomain.from_prism(observer), ModelDomain.from_prism(target)
    point = (F(1), F(0), F(5, 2))
    assert point_has_self_visible_origin(origin, destination, point) is displaced
    assert decide_target_part_visible(origin, destination, point, ()) is displaced
