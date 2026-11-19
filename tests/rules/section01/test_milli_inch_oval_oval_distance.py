from __future__ import annotations

from math import isqrt
from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval, CanonicalOvalError
from warhammer40k_core.geometry.milli_inch_oval_oval import oval_oval_relation
from warhammer40k_core.geometry.milli_inch_oval_oval_distance import oval_oval_distance_ticks


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
def test_oval_pair_measures_gap_for_every_facing_pair(
    first_facing: int, second_facing: int, contact_center: tuple[int, int]
) -> None:
    # The rightmost points of the first oval relative to its center are
    # (35, 0), (25, 24), (5, 0), and (25, -24) at the four respective facings.
    # The second oval has twice the axes. At contact its leftmost point
    # coincides with the first oval's rightmost point on the same support line.
    first = CanonicalOval((0, 0), 70, 10, first_facing)
    x, y = contact_center
    for shift in (-1, 0, 1):
        second = CanonicalOval((x + shift, y), 140, 20, second_facing)
        assert oval_oval_distance_ticks(first, second) == max(0, shift)
        assert oval_oval_distance_ticks(second, first) == max(0, shift)


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
    assert oval_oval_distance_ticks(first, second) == 0
    assert oval_oval_distance_ticks(second, first) == 0


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
    # For the separated case the two right/left support points differ by one
    # transverse tick. Points on the boundaries with the same y instead give
    # a horizontal pair whose gap is strictly between zero and half a tick.
    assert oval_oval_distance_ticks(first, second) == 0
    assert oval_oval_distance_ticks(second, first) == 0


def test_oval_pair_accepts_extreme_coordinate_differences() -> None:
    low, high = -(2**63), 2**63 - 1
    first = CanonicalOval((low, high), high, 1, 45)
    second = CanonicalOval((high, low), high, 1, 135)
    assert oval_oval_relation(first, second) is CircleRelation.SEPARATED
    assert oval_oval_relation(second, first) is CircleRelation.SEPARATED
    # The separation vector lies on a principal axis of each oval. Their
    # opposing support points lie on the center line, giving the exact gap.
    expected = (isqrt(8 * (high - low) ** 2) + 1) // 2 - (high + 1) // 2
    assert oval_oval_distance_ticks(first, second) == expected
    assert oval_oval_distance_ticks(second, first) == expected


@pytest.mark.parametrize(
    ("center", "expected"),
    [((64, 117), 2), ((64, 118), 3), ((65, 118), 3), ((67, 122), 8)],
)
def test_oval_pair_rounds_off_axis_gap_at_mixed_facings(
    center: tuple[int, int], expected: int
) -> None:
    first = CanonicalOval((0, 0), 85, 34)
    second = CanonicalOval(center, 234, 130, 90)
    # With unit outward normal (3/5, 4/5), the support offsets toward the
    # other oval are (75/2, 8) and -(25, 108). Projecting the difference
    # of the support points onto that normal gives a lower bound, while the
    # length of the difference gives an upper bound. Both certify the same
    # bin. At (64, 118) the difference is exactly 2.5 times the unit normal.
    assert oval_oval_relation(first, second) is CircleRelation.SEPARATED
    assert oval_oval_distance_ticks(first, second) == expected
    assert oval_oval_distance_ticks(second, first) == expected


@pytest.mark.parametrize(("steps", "expected"), [(49, 1), (50, 0)])
def test_oval_pair_resolves_a_pell_offset_from_half_a_tick(steps: int, expected: int) -> None:
    # p + k*sqrt(2) = (1 + sqrt(2))**steps gives p² - 2k² = (-1)**steps.
    # Along the diagonal, the gap is 1/2 + k*sqrt(2) - p. The Pell equation
    # places it just above or below the tie, even at scales where floats
    # cannot distinguish the centers' distance from the radii sum.
    p, k = 1, 0
    for _ in range(steps):
        p, k = p + 2 * k, p + k
    first = CanonicalOval((0, 0), p, 1, 45)
    second = CanonicalOval((k, k), p, p - 1, 135)
    assert oval_oval_relation(first, second) is CircleRelation.SEPARATED
    assert oval_oval_distance_ticks(first, second) == expected
    assert oval_oval_distance_ticks(second, first) == expected


@pytest.mark.parametrize("bad_first", [False, True])
def test_oval_pair_distance_rejects_noncanonical_operands(bad_first: bool) -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    invalid: Any = object()
    with pytest.raises(CanonicalOvalError, match="canonical ovals"):
        oval_oval_distance_ticks(invalid, oval) if bad_first else oval_oval_distance_ticks(
            oval, invalid
        )
