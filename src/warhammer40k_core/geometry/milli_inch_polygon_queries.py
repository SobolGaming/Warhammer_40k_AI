"""Inactive exact point queries against canonical closed, filled simple polygons.

Query points are signed 64-bit integer milli-inch pairs, never implicitly snapped.
Topology remains independent of rounded measurement; a zero distance can describe
an exterior point. No gameplay, contact-placement or backend admission is implied.
"""

from __future__ import annotations

from enum import StrEnum
from fractions import Fraction
from typing import cast

from warhammer40k_core.geometry.milli_inch import TICKS_PER_INCH, squared_inches_to_ticks
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    CanonicalPolygon,
    CanonicalPolygonError,
    ExactVertex,
    TickVertex,
)


class PolygonPointLocation(StrEnum):
    EXTERIOR = "exterior"
    BOUNDARY = "boundary"
    INTERIOR = "interior"


def polygon_point_location(polygon: CanonicalPolygon, point: TickVertex) -> PolygonPointLocation:
    """Classify a canonical point exactly, including edges and reflex vertices."""
    _validate_query(polygon, point)
    return _point_location(polygon, point)


def polygon_point_distance_ticks(polygon: CanonicalPolygon, point: TickVertex) -> int:
    """Round distance to the closed filled polygon once; interior/boundary is zero.

    Exterior distance is the minimum exact rational squared segment distance.
    Projection parameters, projected coordinates and individual edge distances
    are never snapped. The shared squared-length boundary handles irrational roots.
    """
    _validate_query(polygon, point)
    if _point_location(polygon, point) != PolygonPointLocation.EXTERIOR:
        return 0
    squared_ticks = min(
        _squared_segment_distance(a, b, point)
        for a, b in zip(polygon.vertices, (*polygon.vertices[1:], polygon.vertices[0]), strict=True)
    )
    return squared_inches_to_ticks(squared_ticks / TICKS_PER_INCH**2)


def _validate_query(polygon: CanonicalPolygon, point: TickVertex) -> None:
    if not isinstance(cast(object, polygon), CanonicalPolygon):
        raise CanonicalPolygonError("Point queries require a canonical polygon.")
    if (
        type(point) is not tuple
        or len(point) != 2
        or any(type(coordinate) is not int for coordinate in point)
    ):
        raise CanonicalPolygonError("A query point requires an immutable integer tick pair.")
    if any(not MIN_COORDINATE_TICKS <= coordinate <= MAX_COORDINATE_TICKS for coordinate in point):
        raise CanonicalPolygonError("Query coordinates must fit signed 64-bit ticks.")


def _point_location(
    polygon: CanonicalPolygon, point: TickVertex | ExactVertex
) -> PolygonPointLocation:
    inside = False
    for a, b in zip(polygon.vertices, (*polygon.vertices[1:], polygon.vertices[0]), strict=True):
        cross = (b[0] - a[0]) * (point[1] - a[1]) - (b[1] - a[1]) * (point[0] - a[0])
        if (
            cross == 0
            and min(a[0], b[0]) <= point[0] <= max(a[0], b[0])
            and min(a[1], b[1]) <= point[1] <= max(a[1], b[1])
        ):
            return PolygonPointLocation.BOUNDARY
        # Half-open vertical intervals count a shared vertex exactly once. The
        # cross sign tests whether the horizontal ray meets this edge to its right.
        if (a[1] > point[1]) != (b[1] > point[1]) and (cross > 0) == (b[1] > a[1]):
            inside = not inside
    return PolygonPointLocation.INTERIOR if inside else PolygonPointLocation.EXTERIOR


def _squared_segment_distance(a: TickVertex, b: TickVertex, point: TickVertex) -> Fraction:
    dx, dy = b[0] - a[0], b[1] - a[1]
    px, py = point[0] - a[0], point[1] - a[1]
    projection = px * dx + py * dy
    squared_length = dx * dx + dy * dy
    if projection <= 0:
        return Fraction(px * px + py * py)
    if projection >= squared_length:
        return Fraction((point[0] - b[0]) ** 2 + (point[1] - b[1]) ** 2)
    return Fraction((dx * py - dy * px) ** 2, squared_length)
