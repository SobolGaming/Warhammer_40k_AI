from __future__ import annotations

import pytest

from warhammer40k_core.geometry.milli_inch_circle import CanonicalCircle, CanonicalCircleError
from warhammer40k_core.geometry.milli_inch_circle_polygon import (
    circle_polygon_distance_ticks,
    circle_polygon_relation,
)
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    CanonicalPolygon,
    CanonicalPolygonError,
)
from warhammer40k_core.geometry.milli_inch_polygon_pairs import PolygonRelation


@pytest.mark.parametrize(
    ("center", "diameter", "relation", "distance"),
    [
        ((8, 2), 2, PolygonRelation.SEPARATED, 3),
        ((6, 2), 3, PolygonRelation.SEPARATED, 1),
        ((6, 2), 4, PolygonRelation.CONTACT, 0),
        ((7, 8), 10, PolygonRelation.CONTACT, 0),
        ((5, 5), 2, PolygonRelation.SEPARATED, 0),
        ((6, 2), 5, PolygonRelation.INTERIOR_OVERLAP, 0),
        ((4, 2), 1, PolygonRelation.INTERIOR_OVERLAP, 0),
        ((2, 2), 1, PolygonRelation.INTERIOR_OVERLAP, 0),
        ((7, 8), 24, PolygonRelation.INTERIOR_OVERLAP, 0),
    ],
)
def test_circle_polygon_topology_and_surface_gap(
    center: tuple[int, int], diameter: int, relation: PolygonRelation, distance: int
) -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 0), (4, 4), (0, 4)))
    circle = CanonicalCircle(center, diameter)
    assert circle_polygon_relation(circle, polygon) == relation
    assert circle_polygon_distance_ticks(circle, polygon) == distance


def test_circle_polygon_concavity_is_independent_of_ring_order() -> None:
    ring = ((0, 0), (6, 0), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6))
    for vertices in (ring, tuple(reversed(ring)), (*ring[1:], ring[0])):
        polygon = CanonicalPolygon(vertices)
        for diameter, relation, gap in (
            (1, PolygonRelation.SEPARATED, 1),
            (2, PolygonRelation.CONTACT, 0),
            (3, PolygonRelation.INTERIOR_OVERLAP, 0),
        ):
            circle = CanonicalCircle((3, 4), diameter)
            assert circle_polygon_relation(circle, polygon) == relation
            assert circle_polygon_distance_ticks(circle, polygon) == gap


def test_circle_polygon_gap_uses_exact_projection_before_subtracting_radius() -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 3), (0, 4)))
    # The off-grid perpendicular projection gives 3/5 ticks to the center.
    # After subtracting the half-tick radius the positive gap rounds to zero.
    circle = CanonicalCircle((1, 0), 1)
    assert circle_polygon_relation(circle, polygon) == PolygonRelation.SEPARATED
    assert circle_polygon_distance_ticks(circle, polygon) == 0


def test_circle_polygon_gap_preserves_exact_rounding_at_large_coordinates() -> None:
    polygon = CanonicalPolygon(((-1, 0), (0, -1), (0, 0)))
    k = 10**8
    n = k**2 // 2 + 1
    # With a half-tick radius, center distances sqrt(n� - 1) and sqrt(n� + 1)
    # lie on opposite sides of the gap's n - 1/2 rounding boundary.
    assert circle_polygon_distance_ticks(CanonicalCircle((n - 1, k), 1), polygon) == n - 1
    assert circle_polygon_distance_ticks(CanonicalCircle((n, 1), 1), polygon) == n
    extreme = CanonicalPolygon(
        ((MIN_COORDINATE_TICKS, 0), (MIN_COORDINATE_TICKS + 1, 0), (MIN_COORDINATE_TICKS, 1))
    )
    assert (
        circle_polygon_distance_ticks(CanonicalCircle((MAX_COORDINATE_TICKS, 0), 1), extreme)
        == 2**64 - 2
    )


def test_circle_polygon_queries_require_canonical_inputs() -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 0), (0, 4)))
    circle = CanonicalCircle((0, 0), 1)
    for query in (circle_polygon_relation, circle_polygon_distance_ticks):
        with pytest.raises(CanonicalCircleError, match="canonical circle"):
            query(circle.to_payload(), polygon)  # type: ignore[arg-type]
        with pytest.raises(CanonicalPolygonError, match="canonical polygon"):
            query(circle, polygon.to_payload())  # type: ignore[arg-type]
