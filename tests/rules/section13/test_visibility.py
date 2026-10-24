"""13.01/02/08/10/11 and FAQ34: direct physical visibility consumers."""

from dataclasses import replace

import pytest

from tests.support.section13_fixtures import area, feature, tiny, visibility, window
from warhammer40k_core.engine.shooting_terrain_visibility import (
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry.terrain_area_visibility import model_intersects_terrain_area
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification as C


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
