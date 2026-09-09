"""Exact two-variable line-space reduction for separated planar circular models.

Circular blockers need their centers to project between every endpoint pair;
other blockers require the same for their entire footprint. With common model
heights and full-height blockers this makes infinite-strip clearance equivalent
to finite flat-strip clearance. Other scenes retain the complete endpoint formulas.
"""

from __future__ import annotations

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
from warhammer40k_core.geometry.visibility_certificates import (
    center_projects_between_boxes,
    circle_radius,
)
from warhammer40k_core.geometry.visibility_exact import (
    CORRIDOR_RADIUS,
    RationalEllipse,
    VisibilityPrism,
)
from warhammer40k_core.geometry.visibility_formulas import ModelDomain, target_visibility_patches


def planar_line_reduction_applies(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    if observer.lower != target.lower or observer.upper != target.upper:
        return False
    if circle_radius(observer) is None or circle_radius(target) is None:
        return False
    if not any(
        observer.bounds[axis + 2] < target.bounds[axis]
        or target.bounds[axis + 2] < observer.bounds[axis]
        for axis in (0, 1)
    ):
        return False
    for blocker in blockers:
        if blocker.lower > observer.lower or blocker.upper < observer.upper:
            return False
        footprint = blocker.footprint
        if isinstance(footprint, RationalEllipse):
            points = (
                (footprint.center,)
                if circle_radius(blocker) is not None
                else tuple(
                    product(
                        (blocker.bounds[0], blocker.bounds[2]),
                        (blocker.bounds[1], blocker.bounds[3]),
                    )
                )
            )
        else:
            points = footprint
        if not all(
            center_projects_between_boxes(point, observer.bounds, target.bounds) for point in points
        ):
            return False
    return True


def _line_clear(
    nx: RealTerm,
    ny: RealTerm,
    denominator: RealTerm,
    offset: RealTerm,
    scale: RealTerm,
    blockers: tuple[VisibilityPrism, ...],
) -> Formula:
    width = denominator * scale * CORRIDOR_RADIUS
    constraints: list[Formula] = []
    for blocker in blockers:
        footprint, radius = blocker.footprint, circle_radius(blocker)
        if isinstance(footprint, RationalEllipse):
            distance = scale * (nx * footprint.center[0] + ny * footprint.center[1]) - offset
            if radius is not None:
                clearance = denominator * scale * (radius + CORRIDOR_RADIUS)
                constraints.append(either(distance.gt(clearance), distance.lt(-clearance)))
            else:
                a, b = footprint.first_axis, footprint.second_axis
                square = (
                    scale * scale * ((nx * a[0] + ny * a[1]) ** 2 + (nx * b[0] + ny * b[1]) ** 2)
                )
                constraints.append(
                    either(
                        *(
                            both(margin.gt(0), (margin * margin).gt(square))
                            for margin in (distance - width, -distance - width)
                        )
                    )
                )
        else:
            distances = tuple(scale * (nx * x + ny * y) - offset for x, y in footprint)
            constraints.append(
                either(
                    both(*(distance.gt(width) for distance in distances)),
                    both(*(distance.lt(-width) for distance in distances)),
                )
            )
    return both(*constraints)


def decide_planar_any(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    if not planar_line_reduction_applies(observer, target, blockers):
        raise ValueError("Planar line-space reduction preconditions are not satisfied.")
    # Unoriented lines need only the half-circle nx>=0; p=-1..1 covers it.
    p, h = variable("p"), variable("h")
    nx, ny, denominator = term(1) - p * p, p * 2, term(1) + p * p
    constraints = [p.ge(-1), p.le(1)]
    for prism in (observer, target):
        footprint, radius = prism.footprint, circle_radius(prism)
        assert isinstance(footprint, RationalEllipse)
        assert radius is not None
        distance = nx * footprint.center[0] + ny * footprint.center[1] - h
        constraints.extend((distance.ge(-denominator * radius), distance.le(denominator * radius)))
    constraints.append(_line_clear(nx, ny, denominator, h, term(1), blockers))
    return decide(both(*constraints), ("p", "h"))


def decide_planar_full(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    if not planar_line_reduction_applies(observer, target, blockers):
        raise ValueError("Planar line-space reduction preconditions are not satisfied.")
    source, destination = ModelDomain.from_prism(observer), ModelDomain.from_prism(target)
    radius = circle_radius(observer)
    assert radius is not None
    q = variable("q")
    nx, ny, length = term(1) - q * q, q * 2, term(1) + q * q
    for patch in target_visibility_patches(source, destination, planar=True):
        px, py = patch.point[:2]
        dx, dy = patch.scale * source.center[0] - px, patch.scale * source.center[1] - py
        distance = nx * dx + ny * dy
        projection = -ny * dx + nx * dy
        chord_square = (patch.scale * length * radius) ** 2 - distance * distance
        normal = destination.normal(patch.u, patch.v)
        outward = -normal[0] * ny + normal[1] * nx
        # The observer-circle chord must contain an origin on the outward
        # half-line. On a target tangent, any displaced chord point is self-clear.
        self_clear = either(
            both(outward.gt(0), either(projection.gt(0), chord_square.gt(projection * projection))),
            both(outward.lt(0), either(projection.lt(0), chord_square.gt(projection * projection))),
            both(outward.eq(0), either(negate(projection.eq(0)), chord_square.gt(0))),
        )
        visible = quantified(
            "exists",
            ("q",),
            both(
                q.ge(-1),
                q.le(1),
                chord_square.ge(0),
                self_clear,
                _line_clear(nx, ny, length, nx * px + ny * py, patch.scale, blockers),
            ),
        )
        if not decide(quantified("forall", patch.parameters, implies(patch.domain, visible))):
            return False
    return True
