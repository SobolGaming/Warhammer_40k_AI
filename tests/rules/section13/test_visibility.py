"""13.01/02/08/10/11 and FAQ34: direct physical visibility consumers."""

from dataclasses import replace

import pytest

from tests.support.section13_fixtures import area, feature, tiny, visibility, window
from warhammer40k_core.core.visibility import (
    BenefitOfCoverResult,
    LineOfSightWitness,
    VisibilityBlockerKind,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry import visibility_occlusion
from warhammer40k_core.geometry.base import RectangularBase
from warhammer40k_core.geometry.continuous_visibility import (
    ContinuousVisibilityEvidence,
    resolve_visibility_pair,
)
from warhammer40k_core.geometry.physical_visibility import physical_model_visibility_prisms
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain_area_visibility import model_intersects_terrain_area
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification as C
from warhammer40k_core.geometry.visibility_exact import VisibilityPrism
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize("z", [0, 10])
def test_agreed_boundary_membership_projects_at_every_elevation(z: float) -> None:
    a = area(x=14, width=4, depth=4)
    (logical,) = terrain_visibility_areas_from_placements((a,))
    assert model_intersects_terrain_area(tiny(x=14, z=z), logical)
    assert model_intersects_terrain_area(tiny(x=16.24, z=z), logical)
    assert not model_intersects_terrain_area(tiny(x=16.26, z=z), logical)
    assert logical.footprint_polygons == (((12, 8), (16, 8), (16, 12), (12, 12)),)


def test_multiple_declared_physical_members_keep_exact_boundary_and_mixed_categories() -> None:
    left = area(identity="s13:left", logical="s13:logical", x=13, width=2, classification=C.LIGHT)
    right = area(identity="s13:right", logical="s13:logical", x=15, width=2, classification=C.DENSE)
    (logical,) = terrain_visibility_areas_from_placements((left, right))
    assert logical.member_terrain_area_ids == ("s13:left", "s13:right")
    assert logical.classification is C.MIXED
    assert model_intersects_terrain_area(tiny(x=12), logical)
    assert not model_intersects_terrain_area(tiny(x=17), logical)
    observer, target = tiny("observer", x=8), tiny("target", x=20)
    context = visibility(observer, (target,), areas=(left, right))
    assert not context.resolve_line_of_sight().unit_visible
    # Remove the dense member: the remaining explicit light member still obscures.
    assert (
        not visibility(
            observer,
            (target,),
            areas=(replace(left, logical_terrain_area_id=left.terrain_area_id),),
        )
        .resolve_line_of_sight()
        .unit_visible
    )


@pytest.mark.parametrize("classification", [C.EXPOSED, C.LIGHT, C.DENSE])
@pytest.mark.parametrize(
    ("observer_x", "target_x", "crossing"),
    [(8, 20, True), (14, 20, False), (8, 14, False), (13, 15, False), (8, 8.5, False)],
)
def test_obscuring_requires_crossing_and_excludes_either_occupied_area(
    classification: C, observer_x: float, target_x: float, crossing: bool
) -> None:
    context = visibility(
        tiny("o", x=observer_x),
        (tiny("t", x=target_x),),
        areas=(area(x=14, width=4, classification=classification),),
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible is (not crossing or classification is C.EXPOSED)
    assert context.resolve_line_of_sight_uncached() == witness


def test_one_open_sightline_prevents_obscuring_from_blocking_visibility() -> None:
    context = visibility(
        tiny("o", x=8), (tiny("t", x=20),), areas=(area(x=14, y=10.2, width=2, depth=0.2),)
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert context.benefit_of_cover(witness).has_benefit


@pytest.mark.parametrize("keyword", ["INFANTRY", "BEAST", "SWARM", "VEHICLE", "MONSTER", "MOBILE"])
@pytest.mark.parametrize("classification", [C.EXPOSED, C.LIGHT, C.DENSE])
def test_cover_occupancy_is_per_model_keyword_and_independent_of_category(
    keyword: str, classification: C
) -> None:
    context = visibility(
        tiny("o", x=8),
        (tiny("t", x=20),),
        keywords=(keyword,),
        areas=(area(classification=classification),),
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_fully_visible
    cover = context.benefit_of_cover(witness)
    assert cover.has_benefit is (keyword in {"INFANTRY", "BEAST", "SWARM"})


@pytest.mark.parametrize("second_inside", [False, True])
def test_cover_requires_every_target_model_to_have_its_own_source(second_inside: bool) -> None:
    targets = (tiny("inside", x=20), tiny("other", x=20, y=12 if second_inside else 20))
    context = visibility(tiny("o", x=8), targets, areas=(area(),))
    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)
    assert cover.has_benefit is second_inside
    assert witness.unit_visible


def test_different_models_can_satisfy_different_cover_conditions() -> None:
    # One infantry occupies the area; the other is partially screened by a Light wall.
    context = visibility(
        tiny("o", x=8),
        (tiny("in-area", x=20), tiny("screened", x=20, y=14)),
        areas=(area(x=20, width=2, depth=2),),
        features=(feature(C.LIGHT, x=16, y=12.6, width=0.25, depth=0.3, height=4),),
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible
    assert context.benefit_of_cover(witness).has_benefit


@pytest.mark.parametrize("classification", [C.LIGHT, C.DENSE])
def test_partial_intervening_feature_grants_cover_to_vehicle_without_occupancy(
    classification: C,
) -> None:
    context = visibility(
        tiny("o", x=8),
        (tiny("t", x=20),),
        keywords=("VEHICLE",),
        features=(feature(classification, x=14, y=10.2, width=0.25, depth=0.2),),
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert context.benefit_of_cover(witness).has_benefit
    clear = replace(context, terrain_features=(), terrain_volumes=())
    assert clear.resolve_line_of_sight().unit_fully_visible
    assert not clear.benefit_of_cover(clear.resolve_line_of_sight()).has_benefit


@pytest.mark.parametrize("classification", [C.LIGHT, C.DENSE])
@pytest.mark.parametrize(("z", "visible"), [(1.25, False), (2.5, False), (3.01, True)])
def test_solid_enclosed_window_has_three_inch_boundary(
    classification: C, z: float, visible: bool
) -> None:
    context = visibility(
        tiny("o", x=10, z=z),
        (tiny("t", x=18, z=z),),
        features=(window(classification=classification),),
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible is (visible or classification is C.LIGHT)
    assert context.resolve_line_of_sight_uncached() == witness


def test_solid_does_not_fill_unenclosed_wall_end_or_area_interior() -> None:
    f = window()
    open_end = replace(f, walls=tuple(w for w in f.walls if w.wall_id != "right"))
    context = visibility(tiny("o", x=10, z=1.25), (tiny("t", x=18, z=1.25),), features=(open_end,))
    assert context.resolve_line_of_sight().unit_visible
    # Two models inside the footprint but on the same side of its wall see each other.
    interior = visibility(tiny("o", x=12, z=1.25), (tiny("t", x=13, z=1.25),), features=(f,))
    assert interior.resolve_line_of_sight().unit_visible


@pytest.mark.parametrize("z", [0, 10])
def test_faq34_constructed_frame_body_overhang_controls_area_membership(z: float) -> None:
    from warhammer40k_core.geometry.base import CircularBase
    from warhammer40k_core.geometry.model_body import ModelBodyPart

    model = tiny("constructed:s13:frame", x=14, z=z)
    frame = replace(
        model,
        measures_every_part=True,
        body_parts=(
            ModelBodyPart("body", CircularBase(1), 0, 3, 0, 1, "constructed:s13:overhang"),
        ),
    )
    (a,) = terrain_visibility_areas_from_placements((area(x=14, y=15, width=2, depth=2),))
    assert model_intersects_terrain_area(frame, a)
    assert not model_intersects_terrain_area(replace(frame, measures_every_part=False), a)


def test_one_agreed_area_can_contain_features_with_different_movement_categories() -> None:
    from tests.support.section13_fixtures import transit
    from warhammer40k_core.geometry.pose import Pose

    dense = feature(C.DENSE, x=13, y=8, width=1, depth=2, identity="s13:dense-member")
    light = feature(C.LIGHT, x=17, y=12, width=1, depth=2, identity="s13:light-member")
    declared = area(x=15, y=10, width=12, depth=8, classification=C.MIXED)
    (boundary,) = terrain_visibility_areas_from_placements((declared,))
    assert model_intersects_terrain_area(tiny(x=13, y=8), boundary)
    assert model_intersects_terrain_area(tiny(x=17, y=12), boundary)
    for y, accepted in ((8, False), (12, True)):
        mover = tiny(x=10, y=y)
        result = transit(
            mover, (mover.pose, Pose.at(20, y)), keywords=("VEHICLE",), features=(dense, light)
        )
        assert result.is_valid is accepted, result.to_payload()
    # The same declared area does not make its Dense physical feature Light.
    assert dense.classification is C.DENSE
    assert light.classification is C.LIGHT


@pytest.mark.parametrize(
    ("terrain_height", "model_bottom", "model_height", "grants_cover"),
    [(4.0, 0.0, 4.0, True), (1.0, 1.0, 3.0, True), (1.0, 0.0, 4.0, False)],
    ids=["independent", "joint-only", "incidental"],
)
def test_cover_attribution_preserves_causal_sources(
    terrain_height: float, model_bottom: float, model_height: float, grants_cover: bool
) -> None:
    # The low wall and the intervening model either complete one blocker
    # together or leave terrain incidental to the model's own obstruction.
    terrain = feature(C.LIGHT, x=-1, y=1, height=terrain_height, width=0.1, depth=2)
    blocker = Model(
        "other-model",
        Pose.at(-1, 1, model_bottom),
        RectangularBase(0.1, 2),
        ModelVolume(model_height),
    )
    target = replace(tiny("target", x=3, y=0), volume=ModelVolume(4))
    context = replace(
        visibility(
            replace(tiny("observer", x=-3, y=0), volume=ModelVolume(4)),
            (target,),
            features=(terrain,),
        ),
        dynamic_model_blockers=(blocker,),
    )
    witness = context.resolve_line_of_sight()
    assert witness.unit_visible
    assert not witness.unit_fully_visible
    assert context.resolve_line_of_sight_uncached().to_payload() == witness.to_payload()
    assert LineOfSightWitness.from_payload(witness.to_payload()) == witness
    sources = tuple(
        row
        for row in witness.all_blocker_records()
        if row.blocker_kind is VisibilityBlockerKind.TERRAIN_VOLUME
    )
    assert tuple(row.terrain_feature_id for row in sources) == (terrain.feature_id,)
    assert (
        context.not_fully_visible_because_of(
            witness, target_model_id=target.model_id, sources=sources
        )
        is grants_cover
    )

    cover = context.benefit_of_cover(witness)
    assert cover.has_benefit is grants_cover
    assert cover.source_feature_ids == ((terrain.feature_id,) if grants_cover else ())
    assert cover.source_terrain_area_ids == ()
    assert BenefitOfCoverResult.from_payload(cover.to_payload()) == cover

    terrain_context = replace(context, dynamic_model_blockers=())
    terrain_only = terrain_context.resolve_line_of_sight()
    assert terrain_only.unit_visible
    assert terrain_only.unit_fully_visible is (terrain_height == 1)
    terrain_cover = terrain_context.benefit_of_cover(terrain_only)
    assert terrain_cover.has_benefit is (terrain_height == 4)
    assert terrain_cover.source_feature_ids == (
        (terrain.feature_id,) if terrain_height == 4 else ()
    )

    # The intervening model still hides some part after removing terrain.
    # The joint result concerns the particular part that terrain helps hide.
    model_context = replace(context, terrain_features=(), terrain_volumes=())
    model_only = model_context.resolve_line_of_sight()
    assert model_only.unit_visible
    assert not model_only.unit_fully_visible
    assert {row.blocker_kind for row in model_only.all_blocker_records()} == {
        VisibilityBlockerKind.MODEL
    }
    assert not model_context.benefit_of_cover(model_only).has_benefit


def _rectangular_cover_prism(identity: str, *, x: float, size: float) -> VisibilityPrism:
    (prism,) = physical_model_visibility_prisms(
        Model(identity, Pose.at(x, 0), RectangularBase(size, size), ModelVolume(1))
    )
    return prism


def test_cover_attribution_preserves_a_contained_observer() -> None:
    observer = _rectangular_cover_prism("observer", x=0, size=1)
    target = _rectangular_cover_prism("target", x=0, size=4)
    selected = (_rectangular_cover_prism("wall", x=0, size=2),)

    # With no facing target patch, full-mask visibility can be vacuously true
    # even though the wall blocks every actual ray from the observer.
    assert resolve_visibility_pair(observer, target, (), selected).model_fully_visible
    both_masks = resolve_visibility_pair(observer, target, selected, selected)
    assert not both_masks.model_visible
    assert not both_masks.model_fully_visible
    assert visibility_occlusion.source_group_obscures(observer, target, selected, ())


@pytest.mark.parametrize(
    ("target_x", "separated"), [(3, True), (2, False)], ids=["separated", "touching"]
)
def test_cover_attribution_chooses_exact_visibility_masks(
    monkeypatch: pytest.MonkeyPatch, target_x: float, separated: bool
) -> None:
    observer = _rectangular_cover_prism("observer", x=0, size=2)
    target = _rectangular_cover_prism("target", x=target_x, size=2)
    selected = (_rectangular_cover_prism("wall", x=0, size=2),)
    masks: list[tuple[tuple[VisibilityPrism, ...], tuple[VisibilityPrism, ...]]] = []

    def record_masks(
        origin: VisibilityPrism,
        destination: VisibilityPrism,
        any_blockers: tuple[VisibilityPrism, ...],
        full_blockers: tuple[VisibilityPrism, ...],
    ) -> ContinuousVisibilityEvidence:
        masks.append((any_blockers, full_blockers))
        return resolve_visibility_pair(origin, destination, any_blockers, full_blockers)

    # Observe the masks while executing the real exact resolver in both cases.
    monkeypatch.setattr(visibility_occlusion, "resolve_visibility_pair", record_masks)
    assert visibility_occlusion.source_group_obscures.__wrapped__(observer, target, selected, ())
    assert masks == [((), selected) if separated else (selected, selected)]
