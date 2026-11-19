"""Staged exact topology and distance between filled canonical ellipses and simple rings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.geometry.milli_inch_oval import (
    CanonicalOval,
    CanonicalOvalError,
    _doubled_local_squares,  # pyright: ignore[reportPrivateUsage]
    _ellipse_coefficients,  # pyright: ignore[reportPrivateUsage]
    _oval_point_below_midpoint,  # pyright: ignore[reportPrivateUsage]
    _round_distance_ticks,  # pyright: ignore[reportPrivateUsage]
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


def oval_polygon_distance_ticks(oval: CanonicalOval, polygon: CanonicalPolygon) -> int:
    """Round the Euclidean surface gap once, with exact half ticks rounding up."""
    if oval_polygon_relation(oval, polygon) is not PolygonRelation.SEPARATED:
        return 0

    center_x, center_y = oval.center
    offsets = tuple((x - center_x, y - center_y) for x, y in polygon.vertices)
    upper_bound = min(abs(x) + abs(y) for x, y in offsets)
    axes = oval.length_ticks**2, oval.width_ticks**2
    local_squares = tuple(_doubled_local_squares(oval, offset) for offset in offsets)
    xx, xy, yy, _ = _ellipse_coefficients(oval)
    projections = tuple(
        projection
        for start, end in zip(offsets, (*offsets[1:], offsets[0]), strict=True)
        if (projection := _edge_projection(start, end, (xx, xy, yy))) is not None
    )

    # Separation puts a closest polygon point on its boundary. At an interior
    # edge minimum the separation vector is perpendicular to the edge and
    # exposes the corresponding ellipse support point. Edge endpoints supply
    # every remaining candidate. Compare the minimum to each midpoint directly.
    def below_midpoint(midpoint: int) -> bool:
        return any(projection.below_midpoint(midpoint) for projection in projections) or any(
            _oval_point_below_midpoint(axes, squares, midpoint) for squares in local_squares
        )

    return _round_distance_ticks(upper_bound, below_midpoint)


@dataclass(frozen=True, slots=True)
class _EdgeProjection:
    line_offset: int
    edge_length_squared: int
    support_squared_numerator: int

    def below_midpoint(self, midpoint: int) -> bool:
        # gap = (line_offset - sqrt(support_squared_numerator/32)) / |edge|.
        # Test sqrt(q) + sqrt(8*m²*|edge|²) > sqrt(32)*line_offset.
        q = self.support_squared_numerator
        midpoint_squared = 8 * midpoint**2 * self.edge_length_squared
        residual = 32 * self.line_offset**2 - q - midpoint_squared
        return residual < 0 or residual**2 < 4 * q * midpoint_squared


def _edge_projection(
    start: TickVertex, end: TickVertex, coefficients: tuple[int, int, int]
) -> _EdgeProjection | None:
    """Return a line minimum whose ellipse support projects onto the closed edge."""
    x, y = start
    dx, dy = end[0] - x, end[1] - y
    nx, ny = -dy, dx
    line_offset = nx * x + ny * y
    if line_offset < 0:
        nx, ny, line_offset = -nx, -ny, -line_offset

    # For M = [[2*xx, xy], [xy, 2*yy]], det(M) = 64*bound in every
    # facing. The ellipse shape matrix is 2*bound*M^-1 = adj(M)/32.
    xx, xy, yy = coefficients
    wx, wy = 2 * yy * nx - xy * ny, 2 * xx * ny - xy * nx
    q = nx * wx + ny * wy
    if 32 * line_offset**2 <= q:
        # A crossing or tangent infinite line cannot give an interior minimum
        # on a separated segment. The endpoint tests cover its closest point.
        return None

    # The support point is (wx, wy)/sqrt(32*q). Moving from it along the
    # normal leaves its dot product with the edge direction unchanged.
    support_dot = dx * wx + dy * wy
    start_dot = dx * x + dy * y
    length_squared = dx**2 + dy**2
    if _at_most_scaled_root(-support_dot, -start_dot, 32 * q) and _at_most_scaled_root(
        support_dot, start_dot + length_squared, 32 * q
    ):
        return _EdgeProjection(line_offset, length_squared, q)
    return None


def _at_most_scaled_root(value: int, scale: int, radicand: int) -> bool:
    """Test value <= scale*sqrt(radicand), retaining the signs before squaring."""
    if value < 0:
        return scale >= 0 or value**2 >= scale**2 * radicand
    return scale >= 0 and value**2 <= scale**2 * radicand


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
