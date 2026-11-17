"""Inactive exact topology and distance for canonical closed filled simple rings.

No epsilon, backend, implicit snapping or gameplay admission is used. Interior
overlap includes containment and coincidence; boundary-only intersection is contact.
"""

from __future__ import annotations

from enum import StrEnum
from fractions import Fraction
from itertools import pairwise
from typing import cast

from warhammer40k_core.geometry.milli_inch import TICKS_PER_INCH, squared_inches_to_ticks
from warhammer40k_core.geometry.milli_inch_polygon import (
    CanonicalPolygon,
    CanonicalPolygonError,
    ExactVertex,
    TickVertex,
)
from warhammer40k_core.geometry.milli_inch_polygon_queries import (
    PolygonPointLocation,
    _point_location,  # pyright: ignore[reportPrivateUsage]
    _squared_segment_distance,  # pyright: ignore[reportPrivateUsage]
)


class PolygonRelation(StrEnum):
    SEPARATED = "separated"
    CONTACT = "contact"
    INTERIOR_OVERLAP = "interior_overlap"


def polygon_polygon_relation(first: CanonicalPolygon, second: CanonicalPolygon) -> PolygonRelation:
    """Classify filled sets exactly, independently of any rounded measurement."""
    _validate_pair(first, second)
    contact = False
    for polygon, other in ((first, second), (second, first)):
        for a, b in _edges(polygon):
            # If no proper crossing exists, every change of point location on
            # this edge occurs at a foreign vertex. Split there before sampling;
            # a single midpoint can miss intervals inside a concave ring.
            split = {a, b}
            for c, d in _edges(other):
                ac, ad = _cross(a, b, c), _cross(a, b, d)
                ca, cb = _cross(c, d, a), _cross(c, d, b)
                if ac * ad < 0 and ca * cb < 0:
                    return PolygonRelation.INTERIOR_OVERLAP
                for point, side in ((c, ac), (d, ad)):
                    if side == 0 and _between(a, b, point):
                        split.add(point)
                        contact = True
                if ac == ad == 0 and _positive_overlap(a, b, c, d):
                    contact = True
                    direction = (b[0] - a[0]) * (d[0] - c[0]) + (b[1] - a[1]) * (d[1] - c[1])
                    # A simple ring's interior is on its winding side. A shared
                    # open edge has overlapping interiors iff those sides agree.
                    same_winding = (_area(polygon) > 0) == (_area(other) > 0)
                    if same_winding == (direction > 0):
                        return PolygonRelation.INTERIOR_OVERLAP
            ordered = sorted(split)
            for start, end in pairwise(ordered):
                midpoint: ExactVertex = (
                    Fraction(start[0] + end[0], 2),
                    Fraction(start[1] + end[1], 2),
                )
                if _point_location(other, midpoint) == PolygonPointLocation.INTERIOR:
                    return PolygonRelation.INTERIOR_OVERLAP
    return PolygonRelation.CONTACT if contact else PolygonRelation.SEPARATED


def polygon_polygon_distance_ticks(first: CanonicalPolygon, second: CanonicalPolygon) -> int:
    """Round the minimum gap once; zero does not establish contact or overlap.

    Disjoint planar segments attain their minimum at an endpoint projection.
    Select the exact rational squared minimum before the sole length rounding.
    """
    if polygon_polygon_relation(first, second) != PolygonRelation.SEPARATED:
        return 0
    squared_ticks = min(
        min(
            _squared_segment_distance(a, b, c),
            _squared_segment_distance(a, b, d),
            _squared_segment_distance(c, d, a),
            _squared_segment_distance(c, d, b),
        )
        for a, b in _edges(first)
        for c, d in _edges(second)
    )
    return squared_inches_to_ticks(squared_ticks / TICKS_PER_INCH**2)


def _validate_pair(first: CanonicalPolygon, second: CanonicalPolygon) -> None:
    if any(not isinstance(cast(object, polygon), CanonicalPolygon) for polygon in (first, second)):
        raise CanonicalPolygonError("Pair queries require two canonical polygon objects.")


def _edges(polygon: CanonicalPolygon) -> tuple[tuple[TickVertex, TickVertex], ...]:
    vertices = polygon.vertices
    return tuple(zip(vertices, (*vertices[1:], vertices[0]), strict=True))


def _cross(a: TickVertex, b: TickVertex, point: TickVertex) -> int:
    return (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])


def _between(a: TickVertex, b: TickVertex, point: TickVertex) -> bool:
    return min(a[0], b[0]) <= point[0] <= max(a[0], b[0]) and min(a[1], b[1]) <= point[1] <= max(
        a[1], b[1]
    )


def _positive_overlap(a: TickVertex, b: TickVertex, c: TickVertex, d: TickVertex) -> bool:
    axis = 0 if a[0] != b[0] else 1
    return max(min(a[axis], b[axis]), min(c[axis], d[axis])) < min(
        max(a[axis], b[axis]), max(c[axis], d[axis])
    )


def _area(polygon: CanonicalPolygon) -> int:
    return sum(a[0] * b[1] - a[1] * b[0] for a, b in _edges(polygon))
