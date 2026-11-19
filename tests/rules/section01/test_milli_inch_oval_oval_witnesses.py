from __future__ import annotations

from fractions import Fraction

import pytest

from warhammer40k_core.geometry.base import OvalBase
from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval
from warhammer40k_core.geometry.milli_inch_oval_oval import oval_oval_relation
from warhammer40k_core.geometry.milli_inch_oval_oval_distance import oval_oval_distance_ticks
from warhammer40k_core.geometry.pose import Facing, Point3, Pose
from warhammer40k_core.geometry.visibility_algebra import RealTerm, both, decide, variable


def _ellipse_level(oval: CanonicalOval, x: RealTerm, y: RealTerm) -> RealTerm:
    """Write the ellipse equation directly in its rotated frame."""
    dx, dy = x - oval.center[0], y - oval.center[1]
    match oval.facing_degrees:
        case 0:
            major, minor, factor = dx, dy, 4
        case 45:
            major, minor, factor = dx + dy, dy - dx, 2
        case _:
            raise AssertionError("Expected an untransformed witness facing")
    return major**2 * Fraction(factor, oval.length_ticks**2) + minor**2 * Fraction(
        factor, oval.width_ticks**2
    )


def _quarter_turn(oval: CanonicalOval) -> CanonicalOval:
    x, y = oval.center
    return CanonicalOval(
        (7 - y, -4 + x), oval.length_ticks, oval.width_ticks, oval.facing_degrees + 90
    )


def _assert_oval_pair(
    first: CanonicalOval, second: CanonicalOval, relation: CircleRelation, ticks: int
) -> None:
    for a, b in ((first, second), (_quarter_turn(first), _quarter_turn(second))):
        for left, right in ((a, b), (b, a)):
            assert oval_oval_relation(left, right) is relation
            assert oval_oval_distance_ticks(left, right) == ticks


type RationalPoint = tuple[Fraction, Fraction]


def _prove_gap_bin(
    first: CanonicalOval,
    second: CanonicalOval,
    normal: tuple[int, int],
    first_radius: Fraction,
    second_radius: Fraction,
    points: tuple[RationalPoint, RationalPoint],
    ticks: int,
) -> tuple[Fraction, Fraction]:
    x, y = variable("x"), variable("y")
    nx, ny = normal
    # The first center is the origin. Rule out any point crossing either
    # supplied support line, using the filled ellipse equations directly.
    second_min = nx * second.center[0] + ny * second.center[1] - second_radius
    projection = x * nx + y * ny
    assert not decide(
        both(_ellipse_level(first, x, y).le(1), projection.gt(first_radius)), ("x", "y")
    )
    assert not decide(
        both(_ellipse_level(second, x, y).le(1), projection.lt(second_min)), ("x", "y")
    )
    clearance = second_min - first_radius
    assert clearance > 0
    lower_squared = clearance**2 / (nx**2 + ny**2)
    if ticks > 0:
        assert lower_squared >= Fraction(2 * ticks - 1, 2) ** 2

    # A concrete pair in the closed ellipses gives an upper bound. Checking
    # feasibility by substitution avoids a four-variable nonlinear search.
    for oval, (px, py) in zip((first, second), points, strict=True):
        level = _ellipse_level(oval, RealTerm.number(px), RealTerm.number(py)).constant
        assert level is not None
        assert level <= 1
    (ax, ay), (bx, by) = points
    upper_squared = (bx - ax) ** 2 + (by - ay) ** 2
    assert upper_squared < Fraction(2 * ticks + 1, 2) ** 2
    return lower_squared, upper_squared


@pytest.mark.parametrize(
    ("center", "relation", "ticks"),
    [
        pytest.param((10, 9), CircleRelation.INTERIOR_OVERLAP, 0, id="overlap"),
        pytest.param((10, 10), CircleRelation.EXTERNAL_CONTACT, 0, id="tangent"),
        pytest.param((10, 11), CircleRelation.SEPARATED, 1, id="separated"),
        pytest.param((11, 10), CircleRelation.SEPARATED, 0, id="separated-rounds-to-zero"),
    ],
)
def test_symbolic_oval_pair_topology(
    center: tuple[int, int], relation: CircleRelation, ticks: int
) -> None:
    first = CanonicalOval((0, 0), 9, 2)
    second = CanonicalOval(center, 23, 17, 45)
    x, y = variable("x"), variable("y")
    a, b = _ellipse_level(first, x, y), _ellipse_level(second, x, y)
    assert decide(both(a.le(1), b.le(1)), ("x", "y")) is (relation is not CircleRelation.SEPARATED)
    assert decide(both(a.lt(1), b.lt(1)), ("x", "y")) is (
        relation is CircleRelation.INTERIOR_OVERLAP
    )
    if relation is CircleRelation.SEPARATED:
        points = (
            ((Fraction(31, 8), Fraction(1, 2)), (Fraction(67, 16), Fraction(7, 8)))
            if ticks == 0
            else ((Fraction(135, 34), Fraction(8, 17)), (Fraction(135, 34), Fraction(25, 17)))
        )
        _prove_gap_bin(first, second, (5, 12), Fraction(51, 2), Fraction(289, 2), points, ticks)
    _assert_oval_pair(first, second, relation, ticks)

    # Check coarse agreement with polygon footprints away from tangency and
    # sub-half-tick separation. The exact constraints above are the oracle.
    if center in ((10, 9), (10, 11)):
        a_base, b_base = OvalBase(0.009, 0.002), OvalBase(0.023, 0.017)
        origin = Pose(Point3.origin())
        other = Pose(Point3(center[0] / 1000, center[1] / 1000, 0), Facing(45))
        assert a_base.overlaps(origin, b_base, other) is (
            relation is CircleRelation.INTERIOR_OVERLAP
        )


@pytest.mark.parametrize(
    ("y", "ticks"),
    [
        pytest.param(19, 2, id="below"),
        pytest.param(20, 3, id="tie"),
        pytest.param(21, 3, id="above"),
    ],
)
def test_symbolic_oval_pair_rounds_across_off_axis_midpoint(y: int, ticks: int) -> None:
    first = CanonicalOval((0, 0), 14, 10)
    second = CanonicalOval((21, y), 41, 7, 45)
    # The second point is its center minus its support offset in (3, 4).
    points = (
        (Fraction(147, 29), Fraction(100, 29)),
        (21 - Fraction(837, 58), y - Fraction(422, 29)),
    )
    lower, upper = _prove_gap_bin(
        first, second, (3, 4), Fraction(29), Fraction(203, 2), points, ticks
    )
    if y == 20:
        assert lower == upper == Fraction(25, 4)
    _assert_oval_pair(first, second, CircleRelation.SEPARATED, ticks)
