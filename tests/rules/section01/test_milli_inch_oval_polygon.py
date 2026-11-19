from __future__ import annotations

import pytest

from warhammer40k_core.geometry.milli_inch_oval import CanonicalOval, CanonicalOvalError
from warhammer40k_core.geometry.milli_inch_oval_polygon import oval_polygon_relation
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    CanonicalPolygon,
    CanonicalPolygonError,
    TickVertex,
)
from warhammer40k_core.geometry.milli_inch_polygon_pairs import PolygonRelation


@pytest.mark.parametrize(
    ("vertices", "expected"),
    [
        (((6, -4), (8, -4), (8, 4), (6, 4)), PolygonRelation.SEPARATED),
        (((5, -4), (7, -4), (7, 4), (5, 4)), PolygonRelation.CONTACT),
        (((4, -4), (7, -4), (7, 4), (4, 4)), PolygonRelation.INTERIOR_OVERLAP),
        (((5, 0), (7, -2), (7, 2)), PolygonRelation.CONTACT),
        (((5, 1), (7, 2), (7, 3)), PolygonRelation.SEPARATED),
        (((-8, -8), (8, -8), (8, 8), (-8, 8)), PolygonRelation.INTERIOR_OVERLAP),
        (((2, 0), (3, 0), (2, 1)), PolygonRelation.INTERIOR_OVERLAP),
        (((0, 0), (7, -5), (7, 5)), PolygonRelation.INTERIOR_OVERLAP),
    ],
)
def test_oval_polygon_relation(vertices: tuple[TickVertex, ...], expected: PolygonRelation) -> None:
    assert (
        oval_polygon_relation(CanonicalOval((0, 0), 10, 6), CanonicalPolygon(vertices)) is expected
    )


def test_oval_polygon_contact_at_an_off_grid_point() -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    # 4x + 5y = 25 supports this ellipse at (4, 9/5).
    polygon = CanonicalPolygon(((0, 5), (5, 1), (5, 5)))
    assert oval_polygon_relation(oval, polygon) is PolygonRelation.CONTACT


@pytest.mark.parametrize("facing", [45, 135])
@pytest.mark.parametrize(
    ("shift", "expected"),
    [
        (1, PolygonRelation.SEPARATED),
        (0, PolygonRelation.CONTACT),
        (-1, PolygonRelation.INTERIOR_OVERLAP),
    ],
)
def test_oval_polygon_uses_euclidean_diagonal_facing(
    facing: int, shift: int, expected: PolygonRelation
) -> None:
    # (4, 1) has normal (4, -1) at 45 degrees. Reflect the tangent for 135 degrees.
    vertices = ((3, -3), (5, 5), (7, -3))
    reflection = 1 if facing == 45 else -1
    polygon = CanonicalPolygon(tuple((x + shift, reflection * y) for x, y in vertices))
    assert oval_polygon_relation(CanonicalOval((0, 0), 10, 6, facing), polygon) is expected


def test_oval_polygon_concave_notch_and_ring_order() -> None:
    ring = ((0, 0), (12, 0), (12, 12), (9, 12), (9, 3), (3, 3), (3, 12), (0, 12))
    for vertices in (ring, ring[::-1], (*ring[3:], *ring[:3])):
        polygon = CanonicalPolygon(vertices)
        for width, expected in (
            (5, PolygonRelation.SEPARATED),
            (6, PolygonRelation.CONTACT),
            (7, PolygonRelation.INTERIOR_OVERLAP),
        ):
            assert oval_polygon_relation(CanonicalOval((6, 8), 9, width, 90), polygon) is expected


def test_oval_polygon_preserves_signed_tick_limits_and_thin_differences() -> None:
    radius = 10**18
    center_x = MAX_COORDINATE_TICKS - radius - 1
    oval = CanonicalOval((center_x, 0), 2 * radius, 2 * radius - 2)
    edge_x = center_x + radius
    for point, expected in (
        ((edge_x, 1), PolygonRelation.SEPARATED),
        ((edge_x, 0), PolygonRelation.CONTACT),
        ((edge_x - 1, 1), PolygonRelation.INTERIOR_OVERLAP),
    ):
        polygon = CanonicalPolygon((point, (MAX_COORDINATE_TICKS, 0), (edge_x, 2)))
        assert oval_polygon_relation(oval, polygon) is expected
    minimum = MIN_COORDINATE_TICKS
    opposite = CanonicalPolygon(((minimum, 0), (minimum + 1, 0), (minimum, 1)))
    assert oval_polygon_relation(oval, opposite) is PolygonRelation.SEPARATED


def test_oval_polygon_relation_requires_canonical_shapes() -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    polygon = CanonicalPolygon(((0, 0), (2, 0), (0, 2)))
    with pytest.raises(CanonicalOvalError, match="canonical oval"):
        oval_polygon_relation(object(), polygon)  # type: ignore[arg-type]
    with pytest.raises(CanonicalPolygonError, match="canonical polygon"):
        oval_polygon_relation(oval, polygon.to_payload())  # type: ignore[arg-type]
