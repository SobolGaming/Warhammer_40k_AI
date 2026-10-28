"""V963-VISIBILITY: body endpoints and clipped origins share one exact authority."""

from fractions import Fraction

from warhammer40k_core.geometry.physical_visibility import (
    BattlefieldVisibilityBounds,
    resolve_physical_visibility,
)
from warhammer40k_core.geometry.physical_visibility_formulas import (
    decide_physical_counterfactual,
    part_visible,
    physical_corridor_clear_condition,
)
from warhammer40k_core.geometry.visibility_algebra import decide, term
from warhammer40k_core.geometry.visibility_exact import RationalEllipse, VisibilityPrism
from warhammer40k_core.geometry.visibility_formulas import ModelDomain, TargetPatch


def _box(x0: int, y0: int, x1: int, y1: int) -> VisibilityPrism:
    bounds = (Fraction(x0), Fraction(y0), Fraction(x1), Fraction(y1))
    return VisibilityPrism(
        (
            (bounds[0], bounds[1]),
            (bounds[2], bounds[1]),
            (bounds[2], bounds[3]),
            (bounds[0], bounds[3]),
        ),
        Fraction(0),
        Fraction(2),
        bounds,
    )


def test_body_overhang_is_an_incoming_endpoint_but_not_an_outgoing_origin() -> None:
    body, opponent = _box(1, -2, 3, 2), _box(8, 1, 10, 3)
    wall = _box(5, 0, 6, 10)
    field = BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(12), Fraction(10))
    incoming = resolve_physical_visibility((opponent,), (body,), (wall,), (wall,), field)
    outgoing = resolve_physical_visibility((body,), (opponent,), (wall,), (wall,), field)
    assert incoming.model_visible
    assert not incoming.model_fully_visible
    assert incoming.clear_corridor is not None
    assert incoming.clear_corridor[1][1] < 0
    assert not outgoing.model_visible
    assert not outgoing.model_fully_visible
    assert resolve_physical_visibility((body,), (opponent,), (), (), field).model_fully_visible


def test_complete_physical_input_and_clipping_have_distinct_fingerprints() -> None:
    body, opponent = _box(1, -2, 3, 2), _box(8, 1, 10, 3)
    field = BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(12), Fraction(10))
    unbounded = resolve_physical_visibility((body,), (opponent,), (), (), None)
    bounded = resolve_physical_visibility((body,), (opponent,), (), (), field)
    assert unbounded.model_visible
    assert bounded.model_visible
    assert unbounded.input_fingerprint != bounded.input_fingerprint
    assert (
        resolve_physical_visibility(
            (body, _box(1, 0, 2, 1)), (opponent,), (), (), field
        ).input_fingerprint
        != bounded.input_fingerprint
    )


def test_disconnected_physical_parts_are_a_union_without_a_filled_gap() -> None:
    left, right, target = _box(1, 1, 2, 2), _box(1, 8, 2, 9), _box(9, 4, 10, 6)
    lower, upper = _box(4, 0, 5, 4), _box(4, 6, 5, 10)
    field = BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(12), Fraction(10))
    evidence = resolve_physical_visibility(
        (left, right), (target,), (lower, upper), (lower, upper), field
    )
    assert not evidence.model_visible


def test_parts_combine_inside_each_target_point_existential() -> None:
    lower, upper, target = _box(1, 0, 2, 2), _box(1, 8, 2, 10), _box(9, 4, 10, 6)
    screen = _box(5, 4, 6, 6)
    field = BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(12), Fraction(10))
    evidence = resolve_physical_visibility((lower, upper), (target,), (screen,), (screen,), field)
    assert evidence.model_visible
    assert evidence.model_fully_visible


def test_closed_boundary_line_and_point_origins_remain_usable() -> None:
    field = BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(12), Fraction(10))
    target = _box(5, 1, 6, 2)
    for origin in (_box(-2, 1, 0, 3), _box(-2, -2, 0, 0)):
        evidence = resolve_physical_visibility((origin,), (target,), (), (), field)
        assert evidence.model_visible
        assert evidence.model_fully_visible
        assert evidence.clear_corridor is not None
        assert field.contains(evidence.clear_corridor[0])
    assert not resolve_physical_visibility(
        (_box(-3, -3, -1, -1),), (target,), (), (), field
    ).model_visible


def test_equivalent_rectangular_parts_keep_one_representative() -> None:
    first, target = _box(1, 1, 2, 2), _box(5, 1, 6, 2)
    assert type(first.footprint) is tuple
    equivalent = VisibilityPrism(
        (*first.footprint[1:], first.footprint[0]), first.lower, first.upper, first.bounds
    )
    assert equivalent != first
    evidence = resolve_physical_visibility((first, equivalent), (target,), (), (), None)
    assert evidence.model_visible
    assert evidence.model_fully_visible


def test_clipping_keeps_the_exact_ellipse_instead_of_its_enclosing_box() -> None:
    circle = VisibilityPrism(
        RationalEllipse(
            (Fraction(1), Fraction(-2)), (Fraction(2), Fraction(0)), (Fraction(0), Fraction(2))
        ),
        Fraction(0),
        Fraction(2),
        (Fraction(-1), Fraction(-4), Fraction(3), Fraction(0)),
    )
    field = BattlefieldVisibilityBounds(Fraction(0), Fraction(0), Fraction(12), Fraction(10))
    target, wall = _box(5, 0, 6, 1), _box(3, 0, 4, 10)
    # The only allowed XY origin is the exact tangent (1,0), not the entire
    # bounding-box edge. Closed one-millimeter wall contact blocks its corridor.
    assert resolve_physical_visibility((circle,), (target,), (), (), field).model_visible
    assert not resolve_physical_visibility(
        (circle,), (target,), (wall,), (wall,), field
    ).model_visible


def test_vertical_corridor_uses_the_exact_closed_disk_and_height_interval() -> None:
    start, end = (term(0), term(0), term(0)), (term(0), term(0), term(5))
    blocking = VisibilityPrism(
        _box(-1, -1, 1, 1).footprint,
        Fraction(2),
        Fraction(3),
        (Fraction(-1), Fraction(-1), Fraction(1), Fraction(1)),
    )
    outside_height = VisibilityPrism(blocking.footprint, Fraction(6), Fraction(7), blocking.bounds)
    for blocker, expected in ((blocking, False), (outside_height, True), (_box(2, 2, 3, 3), True)):
        condition, auxiliary = physical_corridor_clear_condition(
            start, end, (blocker,), term(1), planar=False
        )
        assert decide(condition, auxiliary) is expected


def test_union_self_surface_hides_nearer_parts_touching_seams_and_buried_faces() -> None:
    observer = ModelDomain.from_prism(_box(0, 1, 1, 2))
    for far, other in (
        (_box(8, 1, 9, 2), _box(4, 1, 5, 2)),
        (_box(5, 1, 6, 2), _box(4, 1, 5, 2)),
        (_box(8, 1, 9, 2), _box(7, 0, 10, 3)),
    ):
        destination = ModelDomain.from_prism(far)
        point = (term(far.bounds[0]), term(Fraction(3, 2)), term(1))
        patch = TargetPatch((), destination.member(point), point, term(-1), term(0), term(1), False)
        assert decide(part_visible((observer,), (destination,), None, 0, patch, ()))
        assert not decide(
            part_visible(
                (observer,), (destination, ModelDomain.from_prism(other)), None, 0, patch, ()
            )
        )


def test_cover_counterfactual_requires_the_same_newly_revealed_target_part() -> None:
    observers = tuple(ModelDomain.from_prism(p) for p in (_box(0, 0, 1, 4), _box(0, 6, 1, 10)))
    targets = (ModelDomain.from_prism(_box(9, 4, 10, 6)),)
    lower, upper = _box(5, 0, 6, 5), _box(5, 5, 6, 10)
    unrelated = _box(5, 4, 6, 6)
    assert decide_physical_counterfactual(observers, targets, (lower, upper), (lower,), None)
    # Removing a middle screen cannot reveal a part already hidden by the lower
    # wall. A different hidden part is not evidence of this screen's causality.
    assert not decide_physical_counterfactual(
        observers, targets, (lower, unrelated), (lower,), None
    )
