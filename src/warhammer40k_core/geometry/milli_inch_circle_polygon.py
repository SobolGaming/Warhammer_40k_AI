"""Staged exact queries between canonical closed disks and filled simple rings."""

from __future__ import annotations

from fractions import Fraction
from math import isqrt
from typing import cast

from warhammer40k_core.geometry.milli_inch_circle import CanonicalCircle, CanonicalCircleError
from warhammer40k_core.geometry.milli_inch_polygon import CanonicalPolygon, CanonicalPolygonError
from warhammer40k_core.geometry.milli_inch_polygon_pairs import (
    PolygonRelation,
    _edges,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.geometry.milli_inch_polygon_queries import (
    PolygonPointLocation,
    _point_location,  # pyright: ignore[reportPrivateUsage]
    _squared_segment_distance,  # pyright: ignore[reportPrivateUsage]
)


def circle_polygon_relation(circle: CanonicalCircle, polygon: CanonicalPolygon) -> PolygonRelation:
    """Distinguish separation, boundary-only contact and interior overlap."""
    squared_ticks = _squared_center_distance(circle, polygon)
    squared_diameter = circle.diameter_ticks**2
    if 4 * squared_ticks > squared_diameter:
        return PolygonRelation.SEPARATED
    if 4 * squared_ticks == squared_diameter:
        return PolygonRelation.CONTACT
    return PolygonRelation.INTERIOR_OVERLAP


def circle_polygon_distance_ticks(circle: CanonicalCircle, polygon: CanonicalPolygon) -> int:
    """Round the nonnegative surface gap once, after subtracting the exact radius."""
    squared_ticks = _squared_center_distance(circle, polygon)
    # In doubled tick units, the radius is the integer diameter. Taking
    # floor(sqrt(4 * squared_ticks)) gives the floor needed for the gap
    # without rounding the center distance or representing its square root.
    numerator = 4 * squared_ticks.numerator
    denominator = squared_ticks.denominator
    lower = (isqrt(numerator // denominator) - circle.diameter_ticks) // 2
    if lower < 0:
        return 0
    midpoint = circle.diameter_ticks + 2 * lower + 1
    return lower + int(numerator >= midpoint**2 * denominator)


def _squared_center_distance(circle: CanonicalCircle, polygon: CanonicalPolygon) -> Fraction:
    if not isinstance(cast(object, circle), CanonicalCircle):
        raise CanonicalCircleError("Circle-polygon queries require a canonical circle.")
    if not isinstance(cast(object, polygon), CanonicalPolygon):
        raise CanonicalPolygonError("Circle-polygon queries require a canonical polygon.")
    center = circle.center
    if _point_location(polygon, center) != PolygonPointLocation.EXTERIOR:
        return Fraction(0)
    return min(_squared_segment_distance(start, end, center) for start, end in _edges(polygon))
