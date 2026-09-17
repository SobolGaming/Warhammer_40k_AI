"""Existence of a translated/rotated analytic base wholly inside a setup region.

Coordinates are rationalized from their decimal representation. A negative answer
requires an unsatisfiability proof over *all* translations and orientations; failed
sampling, terrain congestion and the proposed orientation are never such proof.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    implies,
    negate,
    quantified,
    term,
    variable,
)
from warhammer40k_core.geometry.visibility_exact import RationalPolygon, convex_polygon_parts

type Polygon = tuple[tuple[float, float], ...]
type Circle = tuple[float, float, float]
type Region = tuple[tuple[Polygon, ...], tuple[Polygon, ...], tuple[Circle, ...]]


def _rational_polygon(polygon: Polygon) -> RationalPolygon:
    return tuple((Fraction(str(x)), Fraction(str(y))) for x, y in polygon)


def _inside(x: RealTerm, y: RealTerm, polygon: RationalPolygon, *, strict: bool = False) -> Formula:
    def halfplanes(part: RationalPolygon) -> Formula:
        values = tuple(
            (term(b[0] - a[0]) * (y - a[1]) - term(b[1] - a[1]) * (x - a[0]))
            for a, b in zip(part, (*part[1:], part[0]), strict=True)
        )
        return both(*(v.gt(0) if strict else v.ge(0) for v in values))

    # Cutout interior excludes its outside boundary, not internal triangulation seams.
    if strict:
        boundary = either(
            *(
                both(
                    (term(b[0] - a[0]) * (y - a[1]) - term(b[1] - a[1]) * (x - a[0])).eq(0),
                    x.ge(min(a[0], b[0])),
                    x.le(max(a[0], b[0])),
                    y.ge(min(a[1], b[1])),
                    y.le(max(a[1], b[1])),
                )
                for a, b in zip(polygon, (*polygon[1:], polygon[0]), strict=True)
            )
        )
        return both(_inside(x, y, polygon), negate(boundary))
    return either(*(halfplanes(part) for part in convex_polygon_parts(polygon)))


def _region_membership(x: RealTerm, y: RealTerm, region: Region) -> Formula:
    polygons, holes, circles = region
    return both(
        either(*(_inside(x, y, _rational_polygon(p)) for p in polygons)),
        *(negate(_inside(x, y, _rational_polygon(p), strict=True)) for p in holes),
        *(
            ((x - Fraction(str(hx))) ** 2 + (y - Fraction(str(hy))) ** 2).ge(
                Fraction(str(radius)) ** 2
            )
            for hx, hy, radius in circles
        ),
    )


def _irredundant_regions(regions: tuple[Region, ...]) -> tuple[Region, ...]:
    retained = list(dict.fromkeys(regions))
    if len(retained) == 1:
        return tuple(retained)
    x, y = variable("x"), variable("y")
    membership = {region: _region_membership(x, y, region) for region in retained}
    # Prefer removing cutout/decomposed representations. Containment is proved
    # over actual sets, including coverage by multiple remaining regions. Tuple
    # equality cannot recognize equivalent decompositions or scoped cutouts.
    for region in sorted(
        retained, key=lambda row: (len(row[1]) + len(row[2]), len(row[0])), reverse=True
    ):
        if len(retained) == 1:
            break
        others = either(*(membership[other] for other in retained if other != region))
        if not decide(both(membership[region], negate(others)), ("x", "y")):
            retained.remove(region)
    return tuple(retained)


@lru_cache(maxsize=512)
def base_fits_region(
    base: BaseShape,
    polygons: tuple[Polygon, ...],
    polygon_cutouts: tuple[Polygon, ...] = (),
    circle_cutouts: tuple[Circle, ...] = (),
) -> bool:
    return base_fits_regions(base, ((polygons, polygon_cutouts, circle_cutouts),))


@lru_cache(maxsize=512)
def base_fits_regions(base: BaseShape, setup_regions: tuple[Region, ...]) -> bool:
    if not setup_regions or any(not region[0] for region in setup_regions):
        raise GeometryError("Setup fit requires nonempty polygon regions.")
    # Redundant nonlinear branches change nlqsat's result at tangency in the
    # pinned solver. Exact quantifier-free containment proofs remove them before
    # constructing the quantified fit formula; unresolved proofs still raise.
    setup_regions = _irredundant_regions(setup_regions)
    polygons, polygon_cutouts, circle_cutouts = setup_regions[0]
    if not polygons:
        raise GeometryError("Setup fit requires at least one polygon.")
    if type(base) is CircularBase:
        a = b = Fraction(str(base.radius))
    elif isinstance(base, OvalBase | RectangularBase):
        a, b = Fraction(str(base.length)) / 2, Fraction(str(base.width)) / 2
    else:
        raise GeometryError("Unsupported analytic setup base.")
    regions = tuple(_rational_polygon(p) for p in polygons)
    holes = tuple(_rational_polygon(p) for p in polygon_cutouts)
    circles = tuple(tuple(Fraction(str(v)) for v in circle) for circle in circle_cutouts)
    x, y, c, s = (variable(n) for n in ("x", "y", "c", "s"))
    orientation = (c * c + s * s).eq(1)
    names: tuple[str, ...] = ("x", "y", "c", "s")
    if type(base) is CircularBase:
        c, s = term(1), term(0)
        orientation = c.eq(1)
        names = ("x", "y")
    # Convex regions have an exact finite support-function formulation. Circle
    # cutouts against circular bases also have a finite separating condition.
    parts = convex_polygon_parts(regions[0]) if len(regions) == 1 else ()
    if (
        len(setup_regions) == 1
        and len(parts) == 1
        and not holes
        and (not circles or type(base) is CircularBase)
    ):
        constraints = [orientation]
        part = parts[0]
        for p, q in zip(part, (*part[1:], part[0]), strict=True):
            dx, dy = q[0] - p[0], q[1] - p[1]
            margin = term(dx) * (y - p[1]) - term(dy) * (x - p[0])
            u = (term(dx) * s - term(dy) * c) * a
            v = (term(dx) * c + term(dy) * s) * b
            if type(base) is RectangularBase:
                constraints.extend(margin.ge(u * i + v * j) for i in (-1, 1) for j in (-1, 1))
            else:
                constraints.extend((margin.ge(0), (margin * margin).ge(u * u + v * v)))
        constraints.extend(
            ((x - hx) ** 2 + (y - hy) ** 2).ge((a + radius) ** 2) for hx, hy, radius in circles
        )
        return decide(both(*constraints), names)
    u, v = variable("u"), variable("v")
    px, py = x + c * u - s * v, y + s * u + c * v
    in_base = (
        both(u.ge(-a), u.le(a), v.ge(-b), v.le(b))
        if type(base) is RectangularBase
        else ((u * b) ** 2 + (v * a) ** 2).le((a * b) ** 2)
    )
    in_region = either(*(_region_membership(px, py, region) for region in setup_regions))
    return decide(
        both(orientation, quantified("forall", ("u", "v"), implies(in_base, in_region))), names
    )
