"""Exact finite disk containment in convex setup regions with cutouts."""

from __future__ import annotations

from fractions import Fraction

from warhammer40k_core.geometry.visibility_algebra import Formula, RealTerm, both, either, term
from warhammer40k_core.geometry.visibility_exact import RationalPolygon, convex_polygon_parts

type Polygon = tuple[tuple[float, float], ...]
type Circle = tuple[float, float, float]


def circle_outside_convex_polygon(
    x: RealTerm, y: RealTerm, radius: Fraction, polygon: RationalPolygon
) -> Formula:
    """Closest points lie on an edge or in a vertex's outward normal cone."""
    alternatives: list[Formula] = []
    for index, p in enumerate(polygon):
        previous, following = polygon[index - 1], polygon[(index + 1) % len(polygon)]
        px, py = x - p[0], y - p[1]
        dx, dy = following[0] - p[0], following[1] - p[1]
        margin = term(dx) * py - term(dy) * px
        alternatives.append(
            both(margin.le(0), (margin * margin).ge(radius * radius * (dx * dx + dy * dy)))
        )
        alternatives.append(
            both(
                (px * (previous[0] - p[0]) + py * (previous[1] - p[1])).le(0),
                (px * dx + py * dy).le(0),
                (px * px + py * py).ge(radius * radius),
            )
        )
    return either(*alternatives)


def circle_containment(
    x: RealTerm,
    y: RealTerm,
    radius: Fraction,
    polygons: tuple[Polygon, ...],
    holes: tuple[Polygon, ...],
    circles: tuple[Circle, ...],
) -> Formula | None:
    if len(polygons) != 1:
        return None
    outer = tuple((Fraction(str(px)), Fraction(str(py))) for px, py in polygons[0])
    parts = convex_polygon_parts(outer)
    if len(parts) != 1:
        return None
    constraints: list[Formula] = []
    for p, q in zip(parts[0], (*parts[0][1:], parts[0][0]), strict=True):
        dx, dy = q[0] - p[0], q[1] - p[1]
        margin = term(dx) * (y - p[1]) - term(dy) * (x - p[0])
        constraints.append(
            both(margin.ge(0), (margin * margin).ge(radius * radius * (dx * dx + dy * dy)))
        )
    for hole in holes:
        rational = tuple((Fraction(str(px)), Fraction(str(py))) for px, py in hole)
        constraints.extend(
            circle_outside_convex_polygon(x, y, radius, part)
            for part in convex_polygon_parts(rational)
        )
    constraints.extend(
        ((x - Fraction(str(hx))) ** 2 + (y - Fraction(str(hy))) ** 2).ge(
            (radius + Fraction(str(hr))) ** 2
        )
        for hx, hy, hr in circles
    )
    return both(*constraints)
