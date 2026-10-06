"""Existence of a translated/rotated analytic base wholly inside a setup region.

Coordinates are rationalized from their decimal representation. A negative answer
requires an unsatisfiability proof over *all* translations and orientations; failed
sampling, terrain congestion and the proposed orientation are never such proof.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.model_body import ModelBodyPart
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.setup_circle_fit import circle_containment
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
from warhammer40k_core.geometry.volume import Model

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


def _shape_containment(
    base: BaseShape,
    x: RealTerm,
    y: RealTerm,
    c: RealTerm,
    s: RealTerm,
    regions: tuple[Region, ...],
) -> Formula:
    if isinstance(base, CircularBase):
        a = b = Fraction(str(base.radius))
        c, s = term(1), term(0)
    elif isinstance(base, OvalBase | RectangularBase):
        a, b = Fraction(str(base.length)) / 2, Fraction(str(base.width)) / 2
    else:
        raise GeometryError("Unsupported whole-model setup shape.")
    polygons, holes, circles = regions[0]
    if isinstance(base, CircularBase) and len(regions) == 1:
        finite = circle_containment(x, y, a, polygons, holes, circles)
        if finite is not None:
            return finite
    parts = convex_polygon_parts(_rational_polygon(polygons[0])) if len(polygons) == 1 else ()
    if len(regions) == 1 and len(parts) == 1 and not holes and not circles:
        constraints: list[Formula] = []
        for p, q in zip(parts[0], (*parts[0][1:], parts[0][0]), strict=True):
            dx, dy = q[0] - p[0], q[1] - p[1]
            margin = term(dx) * (y - p[1]) - term(dy) * (x - p[0])
            u = (term(dx) * s - term(dy) * c) * a
            v = (term(dx) * c + term(dy) * s) * b
            if isinstance(base, RectangularBase):
                constraints.extend(margin.ge(u * i + v * j) for i in (-1, 1) for j in (-1, 1))
            else:
                constraints.extend((margin.ge(0), (margin * margin).ge(u * u + v * v)))
        return both(*constraints)
    u, v = variable("u"), variable("v")
    in_shape = (
        both(u.ge(-a), u.le(a), v.ge(-b), v.le(b))
        if isinstance(base, RectangularBase)
        else ((u * b) ** 2 + (v * a) ** 2).le((a * b) ** 2)
    )
    return quantified(
        "forall",
        ("u", "v"),
        implies(
            in_shape,
            either(
                *(
                    _region_membership(x + c * u - s * v, y + s * u + c * v, region)
                    for region in regions
                )
            ),
        ),
    )


@lru_cache(maxsize=512)
def _fit(
    base: BaseShape,
    body: tuple[ModelBodyPart, ...],
    regions: tuple[Region, ...],
    base_regions: tuple[Region, ...],
    base_contact: tuple[float, float, float] | None,
) -> bool:
    if not body and regions == base_regions and base_contact is None:
        return base_fits_regions(base, regions)
    regions = _irredundant_regions(regions)
    base_regions = _irredundant_regions(base_regions)
    x, y, c, s = (variable(name) for name in ("x", "y", "c", "s"))
    names: tuple[str, ...] = ("x", "y", "c", "s")
    orientation = (c * c + s * s).eq(1)
    if isinstance(base, CircularBase) and all(
        isinstance(part.base, CircularBase) and part.offset_x_inches == part.offset_y_inches == 0
        for part in body
    ):
        c, s = term(1), term(0)
        names = ("x", "y")
        orientation = c.eq(1)
    constraints = [orientation, _shape_containment(base, x, y, c, s, base_regions)]
    constraints.append(_shape_containment(base, x, y, c, s, regions))
    if base_contact is not None:
        nx, ny, bound = (Fraction(str(value)) for value in base_contact)
        if isinstance(base, CircularBase):
            constraints.append((term(bound) - x * nx - y * ny).eq(Fraction(str(base.radius))))
        elif isinstance(base, OvalBase | RectangularBase):
            margin = term(bound) - x * nx - y * ny
            u = (c * nx + s * ny) * (Fraction(str(base.length)) / 2)
            v = (-s * nx + c * ny) * (Fraction(str(base.width)) / 2)
            if isinstance(base, RectangularBase):
                supports = tuple(u * i + v * j for i in (-1, 1) for j in (-1, 1))
                constraints.extend(margin.ge(support) for support in supports)
                constraints.append(either(*(margin.eq(support) for support in supports)))
            else:
                constraints.extend((margin.ge(0), (margin * margin).eq(u * u + v * v)))
        else:
            raise GeometryError("Unsupported whole-model setup contact shape.")
    for part in body:
        ox, oy = Fraction(str(part.offset_x_inches)), Fraction(str(part.offset_y_inches))
        constraints.append(
            _shape_containment(
                part.base,
                x + c * ox - s * oy,
                y + s * ox + c * oy,
                c,
                s,
                regions,
            )
        )
    return decide(both(*constraints), names)


def model_fits_regions(
    model: Model,
    regions: tuple[Region, ...],
    *,
    base_regions: tuple[Region, ...] | None = None,
    base_contact: tuple[float, float, float] | None = None,
) -> bool:
    required_base_regions = regions if base_regions is None else base_regions
    if (
        not regions
        or not required_base_regions
        or any(not region[0] for region in (*regions, *required_base_regions))
    ):
        raise GeometryError("Whole-model setup fit requires nonempty regions.")
    return _fit(model.base, model.body_parts, regions, required_base_regions, base_contact)


def model_wholly_within_regions(model: Model, regions: tuple[Region, ...]) -> bool:
    """Check the actual pose with the same analytic containment predicates."""
    import math

    if not regions or any(not region[0] for region in regions):
        raise GeometryError("Whole-model setup containment requires nonempty regions.")
    x, y = term(Fraction(str(model.pose.position.x))), term(Fraction(str(model.pose.position.y)))
    degrees = model.pose.facing.degrees % 360
    cardinal = {0.0: (1, 0), 90.0: (0, 1), 180.0: (-1, 0), 270.0: (0, -1)}
    if degrees in cardinal:
        cosine, sine = cardinal[degrees]
        c, s = term(cosine), term(sine)
    else:
        angle = math.radians(degrees)
        c, s = term(Fraction(str(math.cos(angle)))), term(Fraction(str(math.sin(angle))))
    constraints = [_shape_containment(model.base, x, y, c, s, regions)]
    for part in model.body_parts:
        ox, oy = Fraction(str(part.offset_x_inches)), Fraction(str(part.offset_y_inches))
        constraints.append(
            _shape_containment(
                part.base,
                x + c * ox - s * oy,
                y + s * ox + c * oy,
                c,
                s,
                regions,
            )
        )
    return decide(both(*constraints), ())
