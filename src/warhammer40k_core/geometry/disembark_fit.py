"""Size-only fit beside a convex Transport footprint, over all poses.

The exception is not a way around terrain, enemies or other passengers. The
question is whether the base can fit in the Transport's closed distance band
without overlapping its interior. Contact counts as a fit. Exact sufficient
certificates handle common bases; the remaining cases use real quantification.
An unresolved calculation raises rather than authorizing exceptional placement.
"""

from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.base import BaseShape, CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import GeometryError, validate_finite_number
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


def _axes(base: BaseShape) -> tuple[Fraction, Fraction]:
    if type(base) is CircularBase:
        return Fraction(str(base.radius)), Fraction(str(base.radius))
    if isinstance(base, OvalBase | RectangularBase):
        return Fraction(str(base.length)) / 2, Fraction(str(base.width)) / 2
    raise GeometryError("Disembark fit requires an analytic convex base or hull.")


def _inside(base: BaseShape, x: RealTerm, y: RealTerm, *, interior: bool = False) -> Formula:
    a, b = _axes(base)
    if type(base) is RectangularBase:
        values = (x + a, term(a) - x, y + b, term(b) - y)
        return both(*(v.gt(0) if interior else v.ge(0) for v in values))
    value = (x * b) ** 2 + (y * a) ** 2
    return value.lt((a * b) ** 2) if interior else value.le((a * b) ** 2)


def _within(base: BaseShape, x: RealTerm, y: RealTerm, distance: Fraction) -> Formula:
    a, b = _axes(base)
    if type(base) is CircularBase:
        return (x * x + y * y).le((a + distance) ** 2)
    if type(base) is RectangularBase:
        # Exact rounded rectangle: two closed strips and the four corner disks.
        return either(
            both(x.ge(-a), x.le(a), y.ge(-b - distance), y.le(b + distance)),
            both(y.ge(-b), y.le(b), x.ge(-a - distance), x.le(a + distance)),
            *(
                ((x - i * a) ** 2 + (y - j * b) ** 2).le(distance**2)
                for i in (-1, 1)
                for j in (-1, 1)
            ),
        )
    q, r = variable("q"), variable("r")
    return quantified(
        "exists",
        ("q", "r"),
        both(_inside(base, q, r), ((x - q) ** 2 + (y - r) ** 2).le(distance**2)),
    )


def _ellipse_circle_fit(a: Fraction, b: Fraction, radius: Fraction, distance: Fraction) -> bool:
    # S-lemma on the unit disk eliminates both universal ellipse predicates.
    # f(z) >= 0 on 1-|z|² >= 0 iff f-lambda*(1-|z|²) is globally nonnegative
    # for some lambda >= 0. Strict disk feasibility holds, including tangencies.
    x, y, lo, hi = (variable(n) for n in ("x", "y", "lo", "hi"))

    def positive_matrix(d1: RealTerm, d2: RealTerm, d3: RealTerm) -> Formula:
        p, q = x * a, y * b
        return both(
            d1.ge(0),
            d2.ge(0),
            d3.ge(0),
            (d1 * d3 - p * p).ge(0),
            (d2 * d3 - q * q).ge(0),
            (d1 * d2 * d3 - d2 * p * p - d1 * q * q).ge(0),
        )

    return decide(
        both(
            lo.ge(0),
            hi.ge(0),
            positive_matrix(lo + a * a, lo + b * b, x * x + y * y - radius * radius - lo),
            positive_matrix(
                hi - a * a, hi - b * b, term((radius + distance) ** 2) - x * x - y * y - hi
            ),
        ),
        ("x", "y", "lo", "hi"),
    )


def _tangent_circle_contains(base: BaseShape, radius: Fraction, distance: Fraction) -> bool:
    """Sufficient explicit pose: long axis parallel to a supporting tangent."""
    a, b = sorted(_axes(base), reverse=True)
    offset = radius + b
    if type(base) is RectangularBase:
        farthest_squared = a * a + (offset + b) ** 2
    elif a == b:
        farthest_squared = (offset + b) ** 2
    else:
        t = min(Fraction(1), b * offset / (a * a - b * b))
        farthest_squared = a * a + offset * offset + 2 * b * offset * t + (b * b - a * a) * t * t
    return farthest_squared <= (radius + distance) ** 2


def _tangent_polygon_certificate(base: BaseShape, transport: BaseShape, distance: Fraction) -> bool:
    """Enclose cargo by tangents and inscribe the Transport by rational chords.

    This only proves a positive fit. Every vertex of the cargo enclosure must
    lie within distance of a Transport chord; convexity proves containment of
    the entire analytic cargo. A failed certificate proves nothing.
    """
    a, b = sorted(_axes(base), reverse=True)
    ta, tb = sorted(_axes(transport), reverse=True)
    quadrant = tuple(
        ((1 - t * t) / (1 + t * t), 2 * t / (1 + t * t))
        for t in (Fraction(0), Fraction(1, 4), Fraction(1, 2), Fraction(3, 4), Fraction(1))
    )
    directions = (
        *quadrant,
        *((-x, y) for x, y in reversed(quadrant[:-1])),
        *((-x, -y) for x, y in quadrant[1:]),
        *((x, -y) for x, y in reversed(quadrant[1:-1])),
    )
    cargo: tuple[tuple[Fraction, Fraction], ...]
    if type(base) is RectangularBase:
        cargo = ((-a, tb), (a, tb), (a, tb + 2 * b), (-a, tb + 2 * b))
    else:
        vertices: list[tuple[Fraction, Fraction]] = []
        for (c, s), (d, t) in zip(directions, (*directions[1:], directions[0]), strict=True):
            det = c * t - s * d
            vertices.append((a * (t - s) / det, tb + b + b * (c - d) / det))
        cargo = tuple(vertices)
    hull = (
        ((-ta, -tb), (ta, -tb), (ta, tb), (-ta, tb))
        if type(transport) is RectangularBase
        else tuple((ta * x, tb * y) for x, y in directions)
    )

    def within_chord(
        p: tuple[Fraction, Fraction], q: tuple[Fraction, Fraction], r: tuple[Fraction, Fraction]
    ) -> bool:
        dx, dy = r[0] - q[0], r[1] - q[1]
        px, py = p[0] - q[0], p[1] - q[1]
        length = dx * dx + dy * dy
        projection = px * dx + py * dy
        if projection < 0:
            return px * px + py * py <= distance * distance
        if projection > length:
            return (p[0] - r[0]) ** 2 + (p[1] - r[1]) ** 2 <= distance * distance
        return (px * dy - py * dx) ** 2 <= distance * distance * length

    return all(
        any(within_chord(p, q, r) for q, r in zip(hull, (*hull[1:], hull[0]), strict=True))
        for p in cargo
    )


@lru_cache(maxsize=512)
def base_fits_disembark_distance(
    base: BaseShape, transport: BaseShape, distance_inches: float
) -> bool:
    distance_value = validate_finite_number("disembark distance", distance_inches)
    if distance_value <= 0:
        raise GeometryError("Disembark distance must be positive.")
    distance = Fraction(str(distance_value))
    a, b = _axes(base)
    ta, tb = _axes(transport)
    # Any disjoint pair of convex bodies has a separating support line. The
    # cargo's width normal to that line must fit inside the distance band.
    if 2 * min(a, b) > distance:
        return False
    # A circle tangent at a Transport support point fits iff its diameter fits.
    # More generally, diameter <= distance proves a tangent placement exists.
    diameter_squared = 4 * (a * a + b * b if type(base) is RectangularBase else max(a, b) ** 2)
    if diameter_squared <= distance**2:
        return True
    # The band cannot contain a diameter longer than its own diameter.
    transport_radius_squared = (
        ta * ta + tb * tb if type(transport) is RectangularBase else max(ta, tb) ** 2
    )
    excess = diameter_squared / 4 - transport_radius_squared - distance**2
    if excess > 0 and excess**2 > 4 * transport_radius_squared * distance**2:
        return False
    # The base's bounding rectangle fits along a straight Transport side.
    if type(transport) is RectangularBase and (
        (2 * a <= distance and b <= max(ta, tb)) or (2 * b <= distance and a <= max(ta, tb))
    ):
        return True
    # Every supported Transport contains a centered disk of its minor radius;
    # placement beyond its minor-axis support is also outside the full hull.
    if _tangent_circle_contains(base, min(ta, tb), distance):
        return True
    if type(transport) is CircularBase and type(base) is OvalBase:
        return _ellipse_circle_fit(a, b, ta, distance)
    if _tangent_polygon_certificate(base, transport, distance):
        return True
    x, y, c, s = (variable(n) for n in ("x", "y", "c", "s"))
    names: tuple[str, ...] = ("x", "y", "c", "s")
    rotation = (c * c + s * s).eq(1)
    if type(transport) is CircularBase:
        # Rotational symmetry lets us fix the cargo orientation, not its centre.
        c, s = term(1), term(0)
        rotation = c.eq(1)
        names = ("x", "y")
    u, v = variable("u"), variable("v")
    px, py = x + c * u - s * v, y + s * u + c * v
    return decide(
        both(
            rotation,
            quantified(
                "forall",
                ("u", "v"),
                implies(
                    _inside(base, u, v),
                    both(
                        negate(_inside(transport, px, py, interior=True)),
                        _within(transport, px, py, distance),
                    ),
                ),
            ),
        ),
        names,
    )
