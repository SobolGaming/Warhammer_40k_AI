"""Staged exact topology between filled canonical ellipses and simple rings."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.geometry.milli_inch_oval import (
    CanonicalOval,
    CanonicalOvalError,
    _ellipse_coefficients,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.geometry.milli_inch_polygon import (
    CanonicalPolygon,
    CanonicalPolygonError,
    TickVertex,
)
from warhammer40k_core.geometry.milli_inch_polygon_pairs import (
    PolygonRelation,
    _edges,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.geometry.milli_inch_polygon_queries import (
    PolygonPointLocation,
    polygon_point_location,
)


def oval_polygon_relation(oval: CanonicalOval, polygon: CanonicalPolygon) -> PolygonRelation:
    """Classify separation, boundary-only contact, or shared interior exactly."""
    if not isinstance(cast(object, oval), CanonicalOval):
        raise CanonicalOvalError("Oval-polygon queries require a canonical oval.")
    if not isinstance(cast(object, polygon), CanonicalPolygon):
        raise CanonicalPolygonError("Oval-polygon queries require a canonical polygon.")

    # A neighborhood of the oval center is inside the oval, even when the
    # center lies on the polygon boundary. For an exterior center, any shared
    # interior would give a segment from the center crossing a polygon edge
    # inside the open oval, by convexity of the ellipse.
    if polygon_point_location(polygon, oval.center) is not PolygonPointLocation.EXTERIOR:
        return PolygonRelation.INTERIOR_OVERLAP

    coefficients = _ellipse_coefficients(oval)
    contact = False
    for start, end in _edges(polygon):
        residual = _edge_minimum_residual(start, end, oval.center, coefficients)
        if residual < 0:
            return PolygonRelation.INTERIOR_OVERLAP
        if residual == 0:
            contact = True
    return PolygonRelation.CONTACT if contact else PolygonRelation.SEPARATED


def _edge_minimum_residual(
    start: TickVertex,
    end: TickVertex,
    center: TickVertex,
    coefficients: tuple[int, int, int, int],
) -> int:
    """Return the signed numerator of the minimum ellipse residual on the edge."""
    xx, xy, yy, bound = coefficients
    x, y = start[0] - center[0], start[1] - center[1]
    dx, dy = end[0] - start[0], end[1] - start[1]
    # Substitution of (x, y) + t * (dx, dy) gives a*t² + b*t + c.
    # Nonzero canonical edges and positive ellipse axes imply a > 0.
    a = xx * dx**2 + xy * dx * dy + yy * dy**2
    b = 2 * xx * x * dx + xy * (x * dy + y * dx) + 2 * yy * y * dy
    c = xx * x**2 + xy * x * y + yy * y**2 - bound
    if b >= 0:
        return c
    if -b >= 2 * a:
        return a + b + c
    # At t = -b/(2*a) the denominator 4*a is positive, so only the numerator matters.
    return 4 * a * c - b**2
