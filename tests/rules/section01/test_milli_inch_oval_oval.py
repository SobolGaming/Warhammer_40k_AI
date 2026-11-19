from __future__ import annotations

from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval, CanonicalOvalError
from warhammer40k_core.geometry.milli_inch_oval_oval import oval_oval_relation


@pytest.mark.parametrize(
    ("first_facing", "second_facing", "contact_center"),
    [
        (0, 0, (105, 0)),
        (0, 45, (85, 48)),
        (0, 90, (45, 0)),
        (0, 135, (85, -48)),
        (45, 45, (75, 72)),
        (45, 90, (35, 24)),
        (45, 135, (75, -24)),
        (90, 90, (15, 0)),
        (90, 135, (55, -48)),
        (135, 135, (75, -72)),
    ],
)
def test_oval_pair_classifies_contact_for_every_facing_pair(
    first_facing: int, second_facing: int, contact_center: tuple[int, int]
) -> None:
    # The rightmost points of the first oval relative to its center are
    # (35, 0), (25, 24), (5, 0), and (25, -24) at the four respective facings.
    # The second oval has twice the axes. At contact its leftmost point
    # coincides with the first oval's rightmost point on the same support line.
    first = CanonicalOval((0, 0), 70, 10, first_facing)
    x, y = contact_center
    for shift, expected in (
        (-1, CircleRelation.INTERIOR_OVERLAP),
        (0, CircleRelation.EXTERNAL_CONTACT),
        (1, CircleRelation.SEPARATED),
    ):
        second = CanonicalOval((x + shift, y), 140, 20, second_facing)
        assert oval_oval_relation(first, second) is expected
        assert oval_oval_relation(second, first) is expected


def test_oval_pair_preserves_odd_axes_at_mixed_facings() -> None:
    first = CanonicalOval((0, 0), 11, 5)
    # The first major radius and second minor radius are both half-integral.
    for x, expected in (
        (7, CircleRelation.INTERIOR_OVERLAP),
        (8, CircleRelation.EXTERNAL_CONTACT),
        (9, CircleRelation.SEPARATED),
    ):
        second = CanonicalOval((x, 0), 9, 5, 90)
        assert oval_oval_relation(first, second) is expected
        assert oval_oval_relation(second, first) is expected


@pytest.mark.parametrize("x", [32, -32])
def test_oval_pair_classifies_off_axis_contact(x: int) -> None:
    # (x, 9) lies on the first ellipse. Both contact points have the same
    # outward normal up to reversal because the two ellipses are homothetic.
    y = 9
    first = CanonicalOval((0, 0), 80, 30)
    for scale, expected in (
        (1, CircleRelation.INTERIOR_OVERLAP),
        (3, CircleRelation.EXTERNAL_CONTACT),
        (4, CircleRelation.SEPARATED),
    ):
        second = CanonicalOval((scale * x, scale * y), 160, 60)
        assert oval_oval_relation(first, second) is expected
        assert oval_oval_relation(second, first) is expected


@pytest.mark.parametrize(
    ("center", "length", "width", "facing"),
    [
        ((2, 1), 5, 3, 135),  # Strict containment.
        ((4, 0), 12, 6, 0),  # Internal tangency of homothetic ovals.
        ((0, 0), 20, 10, 180),  # Coincidence gives a triple negative root.
        ((0, 0), 20, 10, 90),  # Shared center, distinct real negative roots.
        ((11, 0), 20, 10, 0),  # Shared interior with both centers outside the other oval.
    ],
)
def test_oval_pair_shared_interior(
    center: tuple[int, int], length: int, width: int, facing: int
) -> None:
    first = CanonicalOval((0, 0), 20, 10)
    second = CanonicalOval(center, length, width, facing)
    assert oval_oval_relation(first, second) is CircleRelation.INTERIOR_OVERLAP
    assert oval_oval_relation(second, first) is CircleRelation.INTERIOR_OVERLAP


@pytest.mark.parametrize(
    ("along", "across", "expected"),
    [
        (0, 0, CircleRelation.EXTERNAL_CONTACT),
        (0, 1, CircleRelation.SEPARATED),
        (-1, 1, CircleRelation.INTERIOR_OVERLAP),
    ],
)
def test_oval_pair_resolves_near_contact_at_large_coordinates(
    along: int, across: int, expected: CircleRelation
) -> None:
    # At the full axis separation their vertical support lines coincide.
    # A transverse one-tick displacement moves the support points apart.
    length = 2**63 - 2
    origin = -(2**62)
    first = CanonicalOval((origin, origin), length, length - 2)
    second = CanonicalOval((origin + length + along, origin + across), length, length - 2)
    assert oval_oval_relation(first, second) is expected
    assert oval_oval_relation(second, first) is expected


def test_oval_pair_accepts_extreme_coordinate_differences() -> None:
    low, high = -(2**63), 2**63 - 1
    first = CanonicalOval((low, high), high, 1, 45)
    second = CanonicalOval((high, low), high, 1, 135)
    assert oval_oval_relation(first, second) is CircleRelation.SEPARATED
    assert oval_oval_relation(second, first) is CircleRelation.SEPARATED


@pytest.mark.parametrize("bad_first", [False, True])
def test_oval_pair_rejects_noncanonical_operands(bad_first: bool) -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    invalid: Any = object()
    with pytest.raises(CanonicalOvalError, match="canonical ovals"):
        oval_oval_relation(invalid, oval) if bad_first else oval_oval_relation(oval, invalid)
