from __future__ import annotations

from math import isqrt
from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch_circle import (
    CanonicalCircle,
    CanonicalCircleError,
    CircleRelation,
)
from warhammer40k_core.geometry.milli_inch_circle_oval import (
    circle_oval_distance_ticks,
    circle_oval_relation,
)
from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval, CanonicalOvalError


@pytest.mark.parametrize(
    ("x", "diameter", "relation", "gap"),
    [
        (5, 1, CircleRelation.INTERIOR_OVERLAP, 0),
        (6, 1, CircleRelation.EXTERNAL_CONTACT, 0),
        (7, 1, CircleRelation.SEPARATED, 1),
        (7, 2, CircleRelation.SEPARATED, 1),
    ],
)
def test_circle_oval_axis_contact_preserves_half_tick_radii(
    x: int, diameter: int, relation: CircleRelation, gap: int
) -> None:
    oval = CanonicalOval((0, 0), 11, 7)
    circle = CanonicalCircle((x, 0), diameter)
    assert circle_oval_relation(circle, oval) is relation
    assert circle_oval_distance_ticks(circle, oval) == gap


@pytest.mark.parametrize(
    ("axes", "facing", "center"),
    [
        ((160, 90), 0, (67, 31)),
        ((160, 90), 90, (-31, 67)),
        ((28, 4), 45, (12, 3)),
        ((28, 4), 135, (12, -3)),
    ],
)
def test_circle_oval_certifies_off_axis_tangency(
    axes: tuple[int, int], facing: int, center: tuple[int, int]
) -> None:
    # At zero degrees (64, 27) has outward unit normal (3/5, 4/5).
    # At 45 degrees (8, 6) has outward unit normal (4/5, -3/5).
    # The circle centers are five ticks along those normals or their transforms.
    oval = CanonicalOval((0, 0), *axes, facing)
    tangent = CanonicalCircle(center, 10)
    assert circle_oval_relation(tangent, oval) is CircleRelation.EXTERNAL_CONTACT
    assert circle_oval_distance_ticks(tangent, oval) == 0

    separated = CanonicalCircle(center, 9)
    assert circle_oval_relation(separated, oval) is CircleRelation.SEPARATED
    assert circle_oval_distance_ticks(separated, oval) == 1  # Exactly half a tick.

    overlapping = CanonicalCircle(center, 11)
    assert circle_oval_relation(overlapping, oval) is CircleRelation.INTERIOR_OVERLAP
    assert circle_oval_distance_ticks(overlapping, oval) == 0


@pytest.mark.parametrize("facing", [45, 135])
def test_circle_oval_diagonal_rounding_preserves_exact_separation(facing: int) -> None:
    # At 45 degrees the outward normal at (4, 1) is (4, -1).
    # Reflection gives the same center distance sqrt(17) at 135 degrees.
    oval = CanonicalOval((0, 0), 10, 6, facing)
    separated = CanonicalCircle((8, 0), 8)
    assert circle_oval_relation(separated, oval) is CircleRelation.SEPARATED
    assert circle_oval_distance_ticks(separated, oval) == 0

    odd = CanonicalCircle((8, 0), 7)
    assert circle_oval_distance_ticks(odd, oval) == 1  # sqrt(17) - 3.5
    assert circle_oval_relation(CanonicalCircle((8, 0), 9), oval) is (
        CircleRelation.INTERIOR_OVERLAP
    )


@pytest.mark.parametrize(
    ("facing", "center", "boundary"),
    [(45, (1, 1), (5, 2)), (135, (1, -1), (5, -2))],
)
def test_circle_oval_containment_and_center_on_boundary(
    facing: int, center: tuple[int, int], boundary: tuple[int, int]
) -> None:
    oval = CanonicalOval(center, 10, 6, facing)
    for circle in (
        CanonicalCircle(center, 1),
        CanonicalCircle(center, 6),  # Internally tangent to the oval.
        CanonicalCircle((0, 0), 100),
        CanonicalCircle(boundary, 1),
    ):
        assert circle_oval_relation(circle, oval) is CircleRelation.INTERIOR_OVERLAP
        assert circle_oval_distance_ticks(circle, oval) == 0


def test_circle_oval_midpoint_both_sides_at_large_scale() -> None:
    # For the three offsets, the squared center distances are n² - 1, n², n² + 1.
    k = 2**30
    n = 2 * k**2 + 1
    oval = CanonicalOval((0, 0), 2, 2, 135)
    diameter = 2 * n - 3
    for center, gap in (((n - 1, 2 * k), 0), ((n, 0), 1), ((n, 1), 1)):
        circle = CanonicalCircle(center, diameter)
        assert circle_oval_relation(circle, oval) is CircleRelation.SEPARATED
        assert circle_oval_distance_ticks(circle, oval) == gap


@pytest.mark.parametrize("sign", [-1, 1])
def test_circle_oval_accepts_both_coordinate_extremes(sign: int) -> None:
    minimum, maximum = -(2**63), 2**63 - 1
    start, end = (minimum, maximum) if sign > 0 else (maximum, minimum)
    oval = CanonicalOval((start, start), maximum, maximum - 2, 45)
    circle = CanonicalCircle((end, end), maximum)
    # The center displacement is along the major axis. The radii sum to maximum.
    distance_squared = 2 * (end - start) ** 2
    gap_floor = isqrt(distance_squared) - maximum
    doubled_midpoint = 2 * (maximum + gap_floor) + 1
    assert circle_oval_relation(circle, oval) is CircleRelation.SEPARATED
    assert circle_oval_distance_ticks(circle, oval) == gap_floor + int(
        4 * distance_squared >= doubled_midpoint**2
    )


@pytest.mark.parametrize("query", [circle_oval_relation, circle_oval_distance_ticks])
def test_circle_oval_queries_reject_noncanonical_operands(query: Any) -> None:
    with pytest.raises(CanonicalCircleError):
        query(object(), CanonicalOval((0, 0), 10, 6))
    with pytest.raises(CanonicalOvalError):
        query(CanonicalCircle((0, 0), 3), object())
