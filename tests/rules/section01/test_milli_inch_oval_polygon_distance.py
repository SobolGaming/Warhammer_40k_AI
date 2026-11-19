from __future__ import annotations

import pytest

from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval, CanonicalOvalError
from warhammer40k_core.geometry.milli_inch_oval_polygon import (
    oval_polygon_distance_ticks,
    oval_polygon_relation,
)
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    CanonicalPolygon,
    CanonicalPolygonError,
    TickVertex,
)
from warhammer40k_core.geometry.milli_inch_polygon_pairs import PolygonRelation


@pytest.mark.parametrize(
    ("vertices", "relation"),
    [
        (((5, 1), (7, 2), (7, 3)), PolygonRelation.SEPARATED),
        (((0, 5), (5, 1), (5, 5)), PolygonRelation.CONTACT),
        (((4, -4), (7, -4), (7, 4), (4, 4)), PolygonRelation.INTERIOR_OVERLAP),
        (((-8, -8), (8, -8), (8, 8), (-8, 8)), PolygonRelation.INTERIOR_OVERLAP),
    ],
)
def test_oval_polygon_zero_gap_preserves_exact_topology(
    vertices: tuple[TickVertex, ...], relation: PolygonRelation
) -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    polygon = CanonicalPolygon(vertices)
    assert oval_polygon_relation(oval, polygon) is relation
    assert oval_polygon_distance_ticks(oval, polygon) == 0


def test_oval_polygon_oblique_projection_at_an_exact_half_tick() -> None:
    oval = CanonicalOval((0, 0), 5, 2)
    # The edge on 3x + 4y = 11 has normal length 5 and support 17/2.
    # Its interior projection is exactly (11 - 17/2)/5 = 1/2 tick away.
    polygon = CanonicalPolygon(((-3, 5), (5, -1), (5, 5)))
    assert oval_polygon_relation(oval, polygon) is PolygonRelation.SEPARATED
    assert oval_polygon_distance_ticks(oval, polygon) == 1


@pytest.mark.parametrize(("shift", "gap"), [(-1, 0), (1, 1)])
def test_oval_polygon_oblique_projection_on_each_side_of_a_near_tie(shift: int, gap: int) -> None:
    oval = CanonicalOval((0, 0), 11, 7)
    n = 10**18
    # On nx + y = 6n + shift the exact gap is near 1/2 + shift/n.
    # The deviation from that expression is less than 2/n**2.
    polygon = CanonicalPolygon(((7, shift - n), (5, shift + n), (9, shift + n)))
    assert oval_polygon_relation(oval, polygon) is PolygonRelation.SEPARATED
    assert oval_polygon_distance_ticks(oval, polygon) == gap


@pytest.mark.parametrize(("facing", "reflection"), [(45, 1), (135, -1)])
def test_oval_polygon_projection_uses_rotated_ellipse_support(facing: int, reflection: int) -> None:
    oval = CanonicalOval((0, 0), 10, 6, facing)
    # The outward normal at (4, 1) is (4, -1) at 45 degrees.
    # Shifting this tangent two ticks right gives 8/sqrt(17).
    vertices = ((5, -3), (7, 5), (9, -3))
    polygon = CanonicalPolygon(tuple((x, y * reflection) for x, y in vertices))
    assert oval_polygon_distance_ticks(oval, polygon) == 2


def test_oval_polygon_uses_vertices_when_line_projections_are_outside() -> None:
    oval = CanonicalOval((0, 0), 50, 30)
    # (24, 32) lies sqrt(481) outside the ellipse along the normal at (15, 12).
    # Both adjoining edges lead further away. The x=24 line intersects the oval.
    polygon = CanonicalPolygon(((24, 32), (26, 32), (24, 34)))
    assert oval_polygon_distance_ticks(oval, polygon) == 22


def test_oval_polygon_vertex_tie_and_almost_tie() -> None:
    radius = 10**18
    x = radius + 1
    oval = CanonicalOval((0, 0), 2 * radius + 1, 2 * radius - 1)
    for y in (0, 1):
        # The first vertex is exactly half a tick away at y=0. At y=1 the gap
        # is strictly larger, with its distance to (radius + 1/2, 0) as an upper bound.
        polygon = CanonicalPolygon(((x, y), (x + 2, y + 1), (x + 2, y + 2)))
        assert oval_polygon_relation(oval, polygon) is PolygonRelation.SEPARATED
        assert oval_polygon_distance_ticks(oval, polygon) == 1


def test_oval_polygon_gap_just_below_a_half_tick_with_large_axes() -> None:
    radius = 10**18
    oval = CanonicalOval((0, 0), 2 * radius + 3, 2 * radius - 1, 45)
    # Its x support exceeds radius + 1/2 by less than 1/radius.
    # Use a vertical edge spanning the support projection just below the next half tick.
    polygon = CanonicalPolygon(
        ((radius + 1, -3), (radius + 3, -3), (radius + 3, 3), (radius + 1, 3))
    )
    assert oval_polygon_relation(oval, polygon) is PolygonRelation.SEPARATED
    assert oval_polygon_distance_ticks(oval, polygon) == 0


def test_oval_polygon_gap_to_a_concave_notch_is_invariant_to_ring_order() -> None:
    oval = CanonicalOval((6, 8), 9, 4, 90)
    ring = ((0, 0), (14, 0), (14, 14), (11, 14), (11, 2), (3, 2), (3, 14), (0, 14))
    for vertices in (ring, ring[::-1], (*ring[3:], *ring[:3])):
        polygon = CanonicalPolygon(vertices)
        assert oval_polygon_relation(oval, polygon) is PolygonRelation.SEPARATED
        assert oval_polygon_distance_ticks(oval, polygon) == 1


def test_oval_polygon_gap_can_exceed_the_coordinate_bound() -> None:
    maximum, minimum = MAX_COORDINATE_TICKS, MIN_COORDINATE_TICKS
    oval = CanonicalOval((minimum, 0), 2, 1)
    polygon = CanonicalPolygon(((maximum - 1, minimum), (maximum, 0), (maximum - 1, maximum)))
    assert oval_polygon_relation(oval, polygon) is PolygonRelation.SEPARATED
    assert oval_polygon_distance_ticks(oval, polygon) == maximum - minimum - 2


def test_oval_polygon_gap_requires_canonical_shapes() -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    polygon = CanonicalPolygon(((0, 0), (2, 0), (0, 2)))
    with pytest.raises(CanonicalOvalError, match="canonical oval"):
        oval_polygon_distance_ticks(object(), polygon)  # type: ignore[arg-type]
    with pytest.raises(CanonicalPolygonError, match="canonical polygon"):
        oval_polygon_distance_ticks(oval, polygon.to_payload())  # type: ignore[arg-type]
