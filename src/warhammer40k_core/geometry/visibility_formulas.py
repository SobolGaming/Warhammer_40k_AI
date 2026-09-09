"""Complete continuous visibility formulas over the prepared analytic geometry.

Side surfaces use two rational ellipse charts or four rectangle faces. A target
part is facing iff a self-clear origin actually exists, including displaced
tangents and excluding an occluded vertical generator. Positive-denominator
scaling keeps every corridor constraint polynomial. No endpoint sampling decides
the quantified predicates.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from fractions import Fraction
from itertools import product

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
from warhammer40k_core.geometry.visibility_exact import (
    CORRIDOR_RADIUS,
    RationalEllipse,
    RationalPoint2,
    VisibilityPrism,
    convex_polygon_parts,
)

type Point = tuple[RealTerm, RealTerm, RealTerm]
type Vector2 = tuple[RealTerm, RealTerm]


def _dot(a: tuple[RealTerm, ...], b: tuple[RealTerm, ...]) -> RealTerm:
    result = term(0)
    for x, y in zip(a, b, strict=True):
        result = result + x * y
    return result


def _sub(a: Point, b: Point) -> Point:
    return (a[0] - b[0], a[1] - b[1], a[2] - b[2])


def _cross(a: Point, b: Point) -> Point:
    return (a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0])


def _scale(a: Point, scale: RealTerm) -> Point:
    return (a[0] * scale, a[1] * scale, a[2] * scale)


@dataclass(frozen=True, slots=True)
class ModelDomain:
    center: RationalPoint2
    axes: tuple[RationalPoint2, RationalPoint2]
    lower: Fraction
    upper: Fraction
    curved: bool

    @classmethod
    def from_prism(cls, prism: VisibilityPrism) -> ModelDomain:
        footprint = prism.footprint
        if isinstance(footprint, RationalEllipse):
            return cls(
                footprint.center,
                (footprint.first_axis, footprint.second_axis),
                prism.lower,
                prism.upper,
                True,
            )
        if len(footprint) != 4:
            raise ValueError("A model domain requires an ellipse or rectangle.")
        a, b, c, d = footprint
        if a[0] + c[0] != b[0] + d[0] or a[1] + c[1] != b[1] + d[1]:
            raise ValueError("A rectangular model must have parallelogram geometry.")
        return cls(
            ((a[0] + c[0]) / 2, (a[1] + c[1]) / 2),
            (((b[0] - a[0]) / 2, (b[1] - a[1]) / 2), ((d[0] - a[0]) / 2, (d[1] - a[1]) / 2)),
            prism.lower,
            prism.upper,
            False,
        )

    def local(self, point: Point) -> Vector2:
        x, y = point[0] - self.center[0], point[1] - self.center[1]
        a, b = self.axes
        determinant = a[0] * b[1] - a[1] * b[0]
        return (
            x * (b[1] / determinant) - y * (b[0] / determinant),
            y * (a[0] / determinant) - x * (a[1] / determinant),
        )

    def normal(self, u: RealTerm, v: RealTerm) -> Vector2:
        a, b = self.axes
        determinant = a[0] * b[1] - a[1] * b[0]
        return (
            u * (b[1] / determinant) - v * (a[1] / determinant),
            v * (a[0] / determinant) - u * (b[0] / determinant),
        )

    def world(self, u: RealTerm, v: RealTerm, z: RealTerm, denominator: RealTerm) -> Point:
        a, b = self.axes
        return (
            denominator * self.center[0] + u * a[0] + v * b[0],
            denominator * self.center[1] + u * a[1] + v * b[1],
            z * denominator,
        )

    def member(self, point: Point) -> Formula:
        u, v = self.local(point)
        footprint = (
            (u * u + v * v).le(1) if self.curved else both(u.ge(-1), u.le(1), v.ge(-1), v.le(1))
        )
        return both(footprint, point[2].ge(self.lower), point[2].le(self.upper))

    def vertices(self) -> tuple[RationalPoint2, ...]:
        a, b = self.axes
        return tuple(
            (self.center[0] + i * a[0] + j * b[0], self.center[1] + i * a[1] + j * b[1])
            for i, j in product((-1, 1), repeat=2)
        )


def _self_visible(
    domain: ModelDomain, origin: Point, target: Point, u: RealTerm, v: RealTerm, d: RealTerm
) -> Formula:
    difference = _sub(origin, target)
    active: list[Formula] = [
        both(target[2].eq(d * domain.lower), origin[2].lt(d * domain.lower)),
        both(target[2].eq(d * domain.upper), origin[2].gt(d * domain.upper)),
    ]
    if domain.curved:
        normal = domain.normal(u, v)
        facing = _dot(normal, difference[:2])
        nonvertical = (difference[0] ** 2 + difference[1] ** 2).gt(0)
        active.append(
            both((u * u + v * v).eq(d * d), either(facing.gt(0), both(facing.eq(0), nonvertical)))
        )
    else:
        for axis, coordinate in ((0, u), (1, v)):
            for sign in (-1, 1):
                normal = domain.normal(
                    term(sign if axis == 0 else 0), term(sign if axis == 1 else 0)
                )
                active.append(both(coordinate.eq(d * sign), _dot(normal, difference[:2]).gt(0)))
    return either(*active)


def _side_facing(
    observer: ModelDomain,
    target: ModelDomain,
    u: RealTerm,
    v: RealTerm,
    d: RealTerm,
    target_scaled: Point,
) -> Formula:
    normal = target.normal(u, v)
    if not observer.curved:
        return either(
            *(
                both(
                    (_dot(normal, (term(x - target.center[0]), term(y - target.center[1]))) - d).ge(
                        0
                    ),
                    either(
                        negate((d * x).eq(target_scaled[0])), negate((d * y).eq(target_scaled[1]))
                    ),
                )
                for x, y in observer.vertices()
            )
        )
    delta = (
        _dot(
            normal,
            (
                term(target.center[0] - observer.center[0]),
                term(target.center[1] - observer.center[1]),
            ),
        )
        + d
    )
    a, b = observer.axes
    first, second = _dot(normal, tuple(map(term, a))), _dot(normal, tuple(map(term, b)))
    square = first * first + second * second
    difference = square - delta * delta
    support_x = delta * observer.center[0] + first * a[0] + second * b[0]
    support_y = delta * observer.center[1] + first * a[1] + second * b[1]
    displaced = either(
        negate((d * support_x).eq(delta * target_scaled[0])),
        negate((d * support_y).eq(delta * target_scaled[1])),
    )
    return either(delta.lt(0), difference.gt(0), both(delta.gt(0), difference.eq(0), displaced))


def _poly_clear(
    origin: Point, target: Point, blocker: VisibilityPrism, scale: RealTerm, *, planar: bool
) -> Formula:
    footprint = blocker.footprint
    if isinstance(footprint, RationalEllipse):
        raise TypeError("Polygon separation requires a polygon.")
    d = _sub(target, origin)
    lateral = (-d[1], d[0], term(0))
    length2 = d[0] ** 2 + d[1] ** 2
    edges: list[Point] = [
        (term(b[0] - a[0]), term(b[1] - a[1]), term(0))
        for a, b in zip(footprint, (*footprint[1:], footprint[0]), strict=True)
    ]
    vertical = (term(0), term(0), term(1))
    axes = [_cross(edge, vertical) for edge in edges]
    heights: tuple[Fraction, ...]
    if planar:
        axes.extend((d, lateral))
        heights = (blocker.lower,)
    else:
        axes.extend((vertical, _cross(d, lateral)))
        axes.extend(_cross(a, b) for a in (d, lateral) for b in (*edges, vertical))
        heights = (blocker.lower, blocker.upper)
    vertices = tuple((scale * x, scale * y, scale * z) for (x, y), z in product(footprint, heights))
    radius2 = (scale * CORRIDOR_RADIUS) ** 2
    alternatives: list[Formula] = []
    for axis in axes:
        width2 = radius2 * (_dot(axis, lateral) ** 2)
        for sign in (-1, 1):
            constraints: list[Formula] = []
            for endpoint, vertex in product((origin, target), vertices):
                distance = _dot(axis, _sub(vertex, endpoint)) * sign
                constraints.append(both(distance.gt(0), (distance * distance * length2).gt(width2)))
            alternatives.append(both(*constraints))
    return either(*alternatives)


def _curve_clear(
    origin: Point,
    target: Point,
    blocker: VisibilityPrism,
    scale: RealTerm,
    name: str,
    *,
    planar: bool,
) -> tuple[Formula, tuple[str, ...]]:
    footprint = blocker.footprint
    if not isinstance(footprint, RationalEllipse):
        raise TypeError("Ellipse separation requires an ellipse.")
    a, b = footprint.first_axis, footprint.second_axis
    if planar and a[1] == b[0] == 0 and a[0] == b[1] and a[0] > 0:
        return _planar_circle_clear(origin, target, footprint, scale), ()
    names: tuple[str, ...] = (
        (f"{name}_nx", f"{name}_ny") if planar else (f"{name}_nx", f"{name}_ny", f"{name}_nz")
    )
    normal = (variable(names[0]), variable(names[1]), term(0) if planar else variable(f"{name}_nz"))
    d = _sub(target, origin)
    lateral = (-d[1], d[0], term(0))
    length2 = d[0] ** 2 + d[1] ** 2
    first = _dot(normal[:2], tuple(scale * value for value in footprint.first_axis))
    second = _dot(normal[:2], tuple(scale * value for value in footprint.second_axis))
    support2 = first * first + second * second
    width2 = (scale * CORRIDOR_RADIUS) ** 2 * (_dot(normal, lateral) ** 2)
    constraints: list[Formula] = []
    for endpoint, z in product((origin, target), (blocker.lower, blocker.upper)):
        center = (scale * footprint.center[0], scale * footprint.center[1], scale * z)
        distance = _dot(normal, _sub(endpoint, center))
        difference = (distance * distance - support2) * length2 - width2
        constraints.append(
            both(
                distance.gt(0),
                difference.gt(0),
                (difference * difference).gt(support2 * width2 * length2 * 4),
            )
        )
    return both(*constraints), names


def _planar_circle_clear(
    origin: Point, target: Point, circle: RationalEllipse, scale: RealTerm
) -> Formula:
    """Exact point-to-flat-rectangle distance without auxiliary separating normals."""
    d = _sub(target, origin)
    q = (scale * circle.center[0] - origin[0], scale * circle.center[1] - origin[1])
    length2 = d[0] ** 2 + d[1] ** 2
    projection = q[0] * d[0] + q[1] * d[1]
    perpendicular2 = (d[0] * q[1] - d[1] * q[0]) ** 2
    radius, width = scale * circle.first_axis[0], scale * CORRIDOR_RADIUS
    width2, radius2 = width * width, radius * radius
    alternatives = [
        both(
            projection.ge(0),
            projection.le(length2),
            perpendicular2.gt((radius + width) ** 2 * length2),
        )
    ]
    for endpoint, guard, axial in (
        (origin, projection.le(0), projection),
        (target, projection.ge(length2), projection - length2),
    ):
        distance2 = (scale * circle.center[0] - endpoint[0]) ** 2 + (
            scale * circle.center[1] - endpoint[1]
        ) ** 2
        excess = distance2 + width2 - radius2
        alternatives.append(
            both(
                guard,
                either(
                    both(
                        perpendicular2.le(width2 * length2), (axial * axial).gt(radius2 * length2)
                    ),
                    both(
                        perpendicular2.ge(width2 * length2),
                        excess.gt(0),
                        (excess * excess * length2).gt(width2 * perpendicular2 * 4),
                    ),
                ),
            )
        )
    return either(*alternatives)


def _clear(
    origin: Point,
    target: Point,
    blockers: tuple[VisibilityPrism, ...],
    scale: RealTerm,
    *,
    planar: bool,
) -> tuple[Formula, tuple[str, ...]]:
    horizontal_length2 = (origin[0] - target[0]) ** 2 + (origin[1] - target[1]) ** 2
    constraints = [horizontal_length2.gt(0)]
    variables: list[str] = []
    for index, blocker in enumerate(blockers):
        if isinstance(blocker.footprint, RationalEllipse):
            clear, names = _curve_clear(
                origin, target, blocker, scale, f"blocker{index}", planar=planar
            )
            variables.extend(names)
        else:
            clear = both(
                *(
                    _poly_clear(
                        origin, target, replace(blocker, footprint=part), scale, planar=planar
                    )
                    for part in convex_polygon_parts(blocker.footprint)
                )
            )
        constraints.append(clear)
    return both(*constraints), tuple(variables)


def _planar(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    return (
        observer.lower == target.lower
        and observer.upper == target.upper
        and all(
            blocker.lower <= observer.lower and blocker.upper >= observer.upper
            for blocker in blockers
        )
    )


def _origin(observer: ModelDomain, planar: bool) -> tuple[Point, tuple[str, ...]]:
    names = ("ox", "oy") if planar else ("ox", "oy", "oz")
    return (
        variable("ox"),
        variable("oy"),
        term((observer.lower + observer.upper) / 2) if planar else variable("oz"),
    ), names


def any_visibility_formula(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> tuple[Formula, tuple[str, ...]]:
    planar = _planar(observer, target, blockers)
    origin, names = _origin(observer, planar)
    target_names = ("tx", "ty") if planar else ("tx", "ty", "tz")
    destination = (
        variable("tx"),
        variable("ty"),
        term((target.lower + target.upper) / 2) if planar else variable("tz"),
    )
    clear, auxiliaries = _clear(origin, destination, blockers, term(1), planar=planar)
    return both(observer.member(origin), target.member(destination), clear), (
        *names,
        *target_names,
        *auxiliaries,
    )


@dataclass(frozen=True, slots=True)
class TargetPatch:
    parameters: tuple[str, ...]
    domain: Formula
    point: Point
    u: RealTerm
    v: RealTerm
    scale: RealTerm
    planar: bool


def target_visibility_patches(
    observer: ModelDomain, target: ModelDomain, *, planar: bool
) -> tuple[TargetPatch, ...]:
    p, z = variable("p"), term((target.lower + target.upper) / 2) if planar else variable("z")
    domain = both(p.ge(-1), p.le(1), z.ge(target.lower), z.le(target.upper))
    target_names = ("p",) if planar else ("p", "z")
    result: list[TargetPatch] = []
    sides = (
        tuple((((term(1) - p * p) * sign), p * 2, term(1) + p * p) for sign in (-1, 1))
        if target.curved
        else tuple(
            (term(sign) if axis == 0 else p, p if axis == 0 else term(sign), term(1))
            for axis, sign in product((0, 1), (-1, 1))
        )
    )
    for u, v, denominator in sides:
        destination = target.world(u, v, z, denominator)
        if target.curved:
            facing = _side_facing(observer, target, u, v, denominator, destination)
        else:
            normal = target.normal(
                u if u.constant is not None else term(0), v if v.constant is not None else term(0)
            )
            center = (term(target.center[0]), term(target.center[1]))
            # A flat face belongs to F only if an origin is strictly outside it.
            if observer.curved:
                offset = (
                    _dot(
                        normal,
                        (
                            term(observer.center[0]) - center[0],
                            term(observer.center[1]) - center[1],
                        ),
                    )
                    - 1
                )
                square = (
                    _dot(normal, tuple(map(term, observer.axes[0]))) ** 2
                    + _dot(normal, tuple(map(term, observer.axes[1]))) ** 2
                )
                facing = either(offset.gt(0), square.gt(offset * offset))
            else:
                facing = either(
                    *(
                        (_dot(normal, (term(x) - center[0], term(y) - center[1])) - 1).gt(0)
                        for x, y in observer.vertices()
                    )
                )
        result.append(
            TargetPatch(target_names, both(domain, facing), destination, u, v, denominator, planar)
        )
    for height, enabled in (
        (target.lower, observer.lower < target.lower),
        (target.upper, observer.upper > target.upper),
    ):
        if not enabled:
            continue
        u, v = variable("u"), variable("v")
        destination = target.world(u, v, term(height), term(1))
        cap_domain = (
            (u * u + v * v).le(1) if target.curved else both(u.ge(-1), u.le(1), v.ge(-1), v.le(1))
        )
        result.append(TargetPatch(("u", "v"), cap_domain, destination, u, v, term(1), False))
    return tuple(result)


def _part_visibility_condition(
    observer: ModelDomain,
    target: ModelDomain,
    patch: TargetPatch,
    blockers: tuple[VisibilityPrism, ...],
) -> tuple[Formula, tuple[str, ...]]:
    origin, names = _origin(observer, patch.planar)
    scaled_origin = _scale(origin, patch.scale)
    clear, auxiliaries = _clear(
        scaled_origin, patch.point, blockers, patch.scale, planar=patch.planar
    )
    return (
        both(
            observer.member(origin),
            _self_visible(target, scaled_origin, patch.point, patch.u, patch.v, patch.scale),
            clear,
        ),
        (*names, *auxiliaries),
    )


def _part_visible(
    observer: ModelDomain,
    target: ModelDomain,
    patch: TargetPatch,
    blockers: tuple[VisibilityPrism, ...],
) -> Formula:
    condition, names = _part_visibility_condition(observer, target, patch, blockers)
    return quantified("exists", names, condition)


def full_visibility_formulas(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> tuple[Formula, ...]:
    return tuple(
        quantified(
            "forall",
            patch.parameters,
            implies(patch.domain, _part_visible(observer, target, patch, blockers)),
        )
        for patch in target_visibility_patches(
            observer, target, planar=_planar(observer, target, blockers)
        )
    )


def decide_target_part_visible(
    observer: ModelDomain,
    target: ModelDomain,
    point: tuple[Fraction, Fraction, Fraction],
    blockers: tuple[VisibilityPrism, ...],
) -> bool:
    destination = (term(point[0]), term(point[1]), term(point[2]))
    u, v = target.local(destination)
    patch = TargetPatch(
        (),
        target.member(destination),
        destination,
        u,
        v,
        term(1),
        _planar(observer, target, blockers),
    )
    condition, names = _part_visibility_condition(observer, target, patch, blockers)
    return decide(both(patch.domain, condition), names)


def decide_same_part_counterfactual(
    observer: ModelDomain,
    target: ModelDomain,
    blockers: tuple[VisibilityPrism, ...],
    remaining: tuple[VisibilityPrism, ...],
) -> bool:
    # Both subqueries use the same target variables, with independently scoped
    # origin/clearance variables. Another hidden target part is irrelevant.
    return any(
        decide(
            quantified(
                "exists",
                patch.parameters,
                both(
                    patch.domain,
                    negate(_part_visible(observer, target, patch, blockers)),
                    _part_visible(observer, target, patch, remaining),
                ),
            )
        )
        for patch in target_visibility_patches(
            observer, target, planar=_planar(observer, target, blockers)
        )
    )


def decide_any(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    formula, names = any_visibility_formula(observer, target, blockers)
    return decide(formula, names)


def decide_full(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    return all(decide(formula) for formula in full_visibility_formulas(observer, target, blockers))
