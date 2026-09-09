"""Exact witnesses searched from scene geometry; failed searches prove nothing.

Candidate selection may use rounded directions, but every candidate is rebuilt
on the exact model domain and its complete geometric claim is checked exactly.
The complete algebraic predicate handles queries that this finite search cannot
certify. Target membership and self-visible facing are mandatory before a hidden
point can certify failure of full visibility.
"""

from __future__ import annotations

import math
from collections.abc import Iterator
from fractions import Fraction
from itertools import pairwise, product

from warhammer40k_core.geometry.visibility_certificates import (
    Bounds,
    Box,
    all_box_corridors_blocked_by_circle,
    all_box_corridors_blocked_by_plane,
)
from warhammer40k_core.geometry.visibility_exact import (
    RationalEllipse,
    RationalPoint2,
    RationalPoint3,
    VisibilityPrism,
    rational_sqrt_bounds,
)
from warhammer40k_core.geometry.visibility_formulas import ModelDomain


def local_point(domain: ModelDomain, point: RationalPoint3) -> RationalPoint2:
    x, y = point[0] - domain.center[0], point[1] - domain.center[1]
    a, b = domain.axes
    det = a[0] * b[1] - a[1] * b[0]
    return ((b[1] * x - b[0] * y) / det, (-a[1] * x + a[0] * y) / det)


def _normal(domain: ModelDomain, u: Fraction, v: Fraction) -> RationalPoint2:
    a, b = domain.axes
    det = a[0] * b[1] - a[1] * b[0]
    return ((b[1] * u - a[1] * v) / det, (-b[0] * u + a[0] * v) / det)


def point_in_model(domain: ModelDomain, point: RationalPoint3) -> bool:
    if not domain.lower <= point[2] <= domain.upper:
        return False
    u, v = local_point(domain, point)
    return u * u + v * v <= 1 if domain.curved else abs(u) <= 1 and abs(v) <= 1


def _support_faces(
    observer: ModelDomain, point: RationalPoint3, normal: RationalPoint2, *, tangent: bool
) -> bool:
    if not observer.curved:
        for x, y in observer.vertices():
            distance = normal[0] * (x - point[0]) + normal[1] * (y - point[1])
            if distance > 0 or (tangent and distance == 0 and (x != point[0] or y != point[1])):
                return True
        return False
    a, b = observer.axes
    first = normal[0] * a[0] + normal[1] * a[1]
    second = normal[0] * b[0] + normal[1] * b[1]
    square = first * first + second * second
    delta = normal[0] * (point[0] - observer.center[0]) + normal[1] * (
        point[1] - observer.center[1]
    )
    if delta < 0 or square > delta * delta:
        return True
    if not tangent or delta <= 0 or square != delta * delta:
        return False
    support = (
        observer.center[0] + (first * a[0] + second * b[0]) / delta,
        observer.center[1] + (first * a[1] + second * b[1]) / delta,
    )
    return support != point[:2]


def point_has_self_visible_origin(
    observer: ModelDomain, target: ModelDomain, point: RationalPoint3
) -> bool:
    if not point_in_model(target, point):
        return False
    if (point[2] == target.lower and observer.lower < target.lower) or (
        point[2] == target.upper and observer.upper > target.upper
    ):
        return True
    u, v = local_point(target, point)
    if target.curved:
        return u * u + v * v == 1 and _support_faces(
            observer, point, _normal(target, u, v), tangent=True
        )
    return any(
        _support_faces(
            observer,
            point,
            _normal(target, Fraction(sign if axis == 0 else 0), Fraction(sign if axis == 1 else 0)),
            tangent=False,
        )
        for axis, coordinate in ((0, u), (1, v))
        for sign in (-1, 1)
        if coordinate == sign
    )


def _half_plane_bounds(
    bounds: Bounds, point: RationalPoint3, normal: RationalPoint2
) -> Bounds | None:
    x0, y0, x1, y1 = bounds
    corners = ((x0, y0), (x1, y0), (x1, y1), (x0, y1))
    clipped: list[RationalPoint2] = []
    for a, b in zip(corners, (*corners[1:], corners[0]), strict=True):
        da = normal[0] * (a[0] - point[0]) + normal[1] * (a[1] - point[1])
        db = normal[0] * (b[0] - point[0]) + normal[1] * (b[1] - point[1])
        if da >= 0:
            clipped.append(a)
        if (da < 0 < db) or (db < 0 < da):
            t = da / (da - db)
            clipped.append((a[0] + t * (b[0] - a[0]), a[1] + t * (b[1] - a[1])))
    if not clipped:
        return None
    return (
        min(x for x, _ in clipped),
        min(y for _, y in clipped),
        max(x for x, _ in clipped),
        max(y for _, y in clipped),
    )


def _outer_sqrt(value: Fraction) -> Fraction:
    return rational_sqrt_bounds(value)[1]


def _ellipse_half_plane_bounds(
    ellipse: RationalEllipse, point: RationalPoint3, normal: RationalPoint2
) -> Bounds | None:
    """Conservative rational enclosure of an exact ellipse/half-plane cap.

    Coordinate extrema are either the whole ellipse's support point or an
    endpoint of its exact line-section chord. Outward square-root bounds only
    enlarge this proof domain; the authoritative ellipse remains analytic.
    """
    a, b, center = ellipse.first_axis, ellipse.second_axis, ellipse.center
    m = (normal[0] * a[0] + normal[1] * a[1], normal[0] * b[0] + normal[1] * b[1])
    square = m[0] * m[0] + m[1] * m[1]
    delta = normal[0] * (point[0] - center[0]) + normal[1] * (point[1] - center[1])
    if delta > 0 and delta * delta > square:
        return None
    unrestricted = delta <= 0 and delta * delta >= square
    bounds: list[Fraction] = []
    for sign, axis in product((-1, 1), (0, 1)):
        coordinate_square = a[axis] ** 2 + b[axis] ** 2
        covariance = a[axis] * m[0] + b[axis] * m[1]
        k = sign * covariance
        supported = (
            k >= 0 and k * k >= delta * delta * coordinate_square
            if delta >= 0
            else k >= 0 or k * k <= delta * delta * coordinate_square
        )
        if unrestricted or supported:
            bound = center[axis] + sign * _outer_sqrt(coordinate_square)
        else:
            chord_center = center[axis] + delta * covariance / square
            extent = (
                abs(a[axis] * m[1] - b[axis] * m[0]) * _outer_sqrt(square - delta * delta) / square
            )
            bound = chord_center + sign * extent
        bounds.append(bound)
    return (bounds[0], bounds[1], bounds[2], bounds[3])


def self_visible_corridors_blocked(
    observer: VisibilityPrism,
    target: ModelDomain,
    point: RationalPoint3,
    blockers: tuple[VisibilityPrism, ...],
) -> bool:
    """Prove a target point hidden using all self-valid origin domains.

    Each active target face contributes an outside half-space. Clipping the
    observer's enclosing box by its closed half-space over-encloses that patch's
    valid origins, including every curved tangent. All such enclosures must be
    blocked. Cap/side edges require their union, not just one normal.
    """
    # A closed blocker containing the endpoint intersects every corridor there,
    # independently of flat-cap orientation or the location of the observer.
    if any(blocker.contains_point(point) for blocker in blockers):
        return True
    boxes: list[Box] = []
    if point[2] == target.lower and observer.lower < target.lower:
        boxes.append((observer.bounds, observer.lower, min(observer.upper, target.lower)))
    if point[2] == target.upper and observer.upper > target.upper:
        boxes.append((observer.bounds, max(observer.lower, target.upper), observer.upper))
    u, v = local_point(target, point)
    normals: list[RationalPoint2] = []
    if target.curved and u * u + v * v == 1:
        normals.append(_normal(target, u, v))
    elif not target.curved:
        normals.extend(
            _normal(target, Fraction(sign if axis == 0 else 0), Fraction(sign if axis == 1 else 0))
            for axis, coordinate in ((0, u), (1, v))
            for sign in (-1, 1)
            if coordinate == sign
        )
    for normal in normals:
        bounds = (
            _ellipse_half_plane_bounds(observer.footprint, point, normal)
            if isinstance(observer.footprint, RationalEllipse)
            else _half_plane_bounds(observer.bounds, point, normal)
        )
        if bounds is not None:
            boxes.append((bounds, observer.lower, observer.upper))
    destination = ((point[0], point[1], point[0], point[1]), point[2], point[2])
    return bool(boxes) and all(
        (
            all_box_corridors_blocked_by_circle(box, destination, blockers)
            or all_box_corridors_blocked_by_plane(box, destination, blockers)
        )
        for box in boxes
    )


def _world(domain: ModelDomain, u: Fraction, v: Fraction, z: Fraction) -> RationalPoint3:
    a, b = domain.axes
    return (domain.center[0] + a[0] * u + b[0] * v, domain.center[1] + a[1] * u + b[1] * v, z)


def target_part_candidates(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> tuple[RationalPoint3, ...]:
    # Extreme side parts often have a small self-visible origin domain and make
    # inexpensive occlusion witnesses. These are proof candidates, not samples
    # from which either quantified answer may be inferred.
    local_candidates: list[RationalPoint2] = [
        (Fraction(0), Fraction(-1)),
        (Fraction(0), Fraction(1)),
        (Fraction(-1), Fraction(0)),
        (Fraction(1), Fraction(0)),
    ]
    dx, dy = target.center[0] - observer.center[0], target.center[1] - observer.center[1]
    if target.curved and (dx or dy):
        for sign in (-1, 1):
            x, y = local_point(
                target, (target.center[0] - sign * dy, target.center[1] + sign * dx, target.lower)
            )
            scale = max(abs(x), abs(y))
            nx, ny = float(x / scale), float(y / scale)
            parameter = Fraction(ny / (math.hypot(nx, ny) + abs(nx))).limit_denominator(4096)
            for shift in map(Fraction, ("0", "-1/4096", "1/4096", "-1/65536", "1/65536")):
                u = parameter + shift
                d = 1 + u * u
                local_candidates.append(((1 if x >= 0 else -1) * (1 - u * u) / d, 2 * u / d))
    for blocker in blockers:
        bx = (blocker.bounds[0] + blocker.bounds[2]) / 2
        by = (blocker.bounds[1] + blocker.bounds[3]) / 2
        x, y = local_point(target, (bx, by, target.lower))
        if target.curved:
            # Only a proof-search direction is rounded. The rational chart below
            # lies exactly on the ellipse for every selected rational parameter.
            scale = max(abs(x), abs(y))
            if scale == 0:
                continue
            nx, ny = float(x / scale), float(y / scale)
            parameter = Fraction(ny / (math.hypot(nx, ny) + abs(nx))).limit_denominator(4096)
            d = 1 + parameter * parameter
            local_candidates.append(
                ((1 if x >= 0 else -1) * (1 - parameter * parameter) / d, 2 * parameter / d)
            )
        else:
            u, v = max(Fraction(-1), min(Fraction(1), x)), max(Fraction(-1), min(Fraction(1), y))
            local_candidates.extend(
                ((Fraction(-1), v), (Fraction(1), v), (u, Fraction(-1)), (u, Fraction(1)))
            )
    if target.curved:
        for sign, parameter in product(
            (-1, 1), map(Fraction, ("0", "-1/2", "1/2", "-1/5", "1/5", "-4/5", "4/5", "-1", "1"))
        ):
            d = 1 + parameter * parameter
            local_candidates.append((sign * (1 - parameter * parameter) / d, 2 * parameter / d))
    else:
        local_candidates.extend((u, v) for u, v in product(map(Fraction, (-1, 0, 1)), repeat=2))
    points = [
        _world(target, u, v, z)
        for u, v in dict.fromkeys(local_candidates)
        for z in (target.lower, (target.lower + target.upper) / 2, target.upper)
    ]
    points.extend(_world(target, Fraction(0), Fraction(0), z) for z in (target.lower, target.upper))
    return tuple(dict.fromkeys(points))


def positive_ray_candidates(
    observer: ModelDomain, target: ModelDomain, blockers: tuple[VisibilityPrism, ...]
) -> Iterator[tuple[RationalPoint3, RationalPoint3]]:
    dx, dy = target.center[0] - observer.center[0], target.center[1] - observer.center[1]
    length2 = dx * dx + dy * dy
    shifts: list[RationalPoint2] = [(Fraction(0), Fraction(0))]
    if length2:
        cuts = sorted(
            {
                dx * (y - observer.center[1]) - dy * (x - observer.center[0])
                for blocker in blockers
                for x, y in product(
                    (blocker.bounds[0], blocker.bounds[2]), (blocker.bounds[1], blocker.bounds[3])
                )
            }
        )
        offsets = sorted(
            {*cuts, *((a + b) / 2 for a, b in pairwise(cuts))},
            key=lambda offset: (abs(offset), offset),
        )
        shifts.extend((-dy * offset / length2, dx * offset / length2) for offset in offsets)
    seen: set[tuple[RationalPoint3, RationalPoint3]] = set()
    heights = (
        (observer.upper, target.upper),
        ((observer.lower + observer.upper) / 2, (target.lower + target.upper) / 2),
        (observer.upper, target.lower),
        (observer.lower, target.upper),
    )
    for sx, sy in dict.fromkeys(shifts):
        for oz, tz in heights:
            origin = (observer.center[0] + sx, observer.center[1] + sy, oz)
            destination = (target.center[0] + sx, target.center[1] + sy, tz)
            ray = (origin, destination)
            if (
                ray not in seen
                and point_in_model(observer, origin)
                and point_in_model(target, destination)
            ):
                seen.add(ray)
                yield ray
    # Endpoints may need different lateral offsets when a blocker overlaps one
    # model. These finite candidates can prove existence only; a miss continues
    # to the complete algebraic predicate and never proves invisibility/fullness.
    local_points = (
        (Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(-1)),
        (Fraction(0), Fraction(1)),
        (Fraction(-1), Fraction(0)),
        (Fraction(1), Fraction(0)),
    )
    for first, last in product(local_points, repeat=2):
        for oz, tz in heights:
            ray = (_world(observer, *first, oz), _world(target, *last, tz))
            if ray not in seen:
                seen.add(ray)
                yield ray
    if not length2:
        return
    for sign in (-1, 1):
        boundary: list[RationalPoint2] = []
        for domain in (observer, target):
            x, y = local_point(
                domain, (domain.center[0] - sign * dy, domain.center[1] + sign * dx, domain.lower)
            )
            if domain.curved:
                scale = max(abs(x), abs(y))
                nx, ny = float(x / scale), float(y / scale)
                p = Fraction(ny / (math.hypot(nx, ny) + abs(nx))).limit_denominator(65536)
                d = 1 + p * p
                boundary.append(((1 if x >= 0 else -1) * (1 - p * p) / d, 2 * p / d))
            else:
                scale = max(abs(x), abs(y))
                boundary.append((x / scale, y / scale))
        for oz, tz in heights:
            origin = _world(observer, *boundary[0], oz)
            destination = _world(target, *boundary[1], tz)
            ray = (origin, destination)
            if (
                ray not in seen
                and point_in_model(observer, origin)
                and point_in_model(target, destination)
            ):
                seen.add(ray)
                yield ray
