"""Sufficient continuous-domain certificates, never sampled negative answers.

Failure to find a certificate means unresolved; the complete predicate must then
use another proof or real-algebraic decision. Every successful certificate checks
closed domains using exact rational comparisons.
"""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from functools import lru_cache
from itertools import pairwise, product

from warhammer40k_core.geometry.visibility_exact import (
    CORRIDOR_RADIUS,
    RationalEllipse,
    RationalPoint2,
    RationalPoint3,
    VisibilityPrism,
    convex_polygon_parts,
    footprint_intersects_polygon,
    rational_sqrt_bounds,
)

type Bounds = tuple[Fraction, Fraction, Fraction, Fraction]
type Box = tuple[Bounds, Fraction, Fraction]


def _box(prism: VisibilityPrism) -> Box:
    return (prism.bounds, prism.lower, prism.upper)


def _vertices(box: Box) -> tuple[RationalPoint3, ...]:
    (x0, y0, x1, y1), z0, z1 = box
    return tuple(sorted(set(product((x0, x1), (y0, y1), (z0, z1)))))


def _prism_support(prism: VisibilityPrism, normal: RationalPoint3) -> tuple[Fraction, Fraction]:
    """Return exact support as rational + sqrt(nonnegative rational)."""
    vertical = max(normal[2] * prism.lower, normal[2] * prism.upper)
    footprint = prism.footprint
    if isinstance(footprint, RationalEllipse):
        a, b = footprint.first_axis, footprint.second_axis
        center = normal[0] * footprint.center[0] + normal[1] * footprint.center[1]
        square = (normal[0] * a[0] + normal[1] * a[1]) ** 2 + (
            normal[0] * b[0] + normal[1] * b[1]
        ) ** 2
        return center + vertical, square
    return max(normal[0] * x + normal[1] * y for x, y in footprint) + vertical, Fraction(0)


def _cross(a: RationalPoint2, b: RationalPoint2, c: RationalPoint2) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


def _hull(points: tuple[RationalPoint2, ...]) -> tuple[RationalPoint2, ...]:
    ordered = sorted(set(points))
    if len(ordered) <= 2:
        return tuple(ordered)
    parts: list[list[RationalPoint2]] = []
    for sequence in (ordered, list(reversed(ordered))):
        side: list[RationalPoint2] = []
        for point in sequence:
            while len(side) >= 2 and _cross(side[-2], side[-1], point) <= 0:
                side.pop()
            side.append(point)
        parts.append(side[:-1])
    return tuple(parts[0] + parts[1])


@lru_cache(maxsize=4096)
def _candidate_planes(first: Box, second: Box) -> tuple[RationalPoint3, ...]:
    points = (*_vertices(first), *_vertices(second))
    normals: set[RationalPoint3] = {
        (Fraction(1), Fraction(0), Fraction(0)),
        (Fraction(0), Fraction(1), Fraction(0)),
        (Fraction(0), Fraction(0), Fraction(1)),
    }
    for i, j in ((0, 1), (0, 2), (1, 2)):
        hull = _hull(tuple((point[i], point[j]) for point in points))
        for a, b in zip(hull, (*hull[1:], hull[0]), strict=True):
            normal = [Fraction(0)] * 3
            normal[i], normal[j] = b[1] - a[1], a[0] - b[0]
            if any(normal):
                normals.add((normal[0], normal[1], normal[2]))
    return tuple(sorted(normals))


def corridors_clear_by_enclosure(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    blockers: tuple[VisibilityPrism, ...],
) -> bool:
    """Prove every observer/target corridor avoids every blocker via separating planes.

    The hull of both endpoint prisms, expanded by a horizontal radius-r disk,
    encloses every strip. For a candidate plane, sqrt(nx²+ny²)*r is its exact
    support increment. The blocker
    support is computed over its actual analytic footprint. Only strict
    separation passes; squared positive inequalities preserve tangent contact.
    """
    if not blockers:
        return True
    x0 = min(observer.bounds[0], target.bounds[0]) - CORRIDOR_RADIUS
    y0 = min(observer.bounds[1], target.bounds[1]) - CORRIDOR_RADIUS
    x1 = max(observer.bounds[2], target.bounds[2]) + CORRIDOR_RADIUS
    y1 = max(observer.bounds[3], target.bounds[3]) + CORRIDOR_RADIUS
    z0, z1 = min(observer.lower, target.lower), max(observer.upper, target.upper)
    remaining = tuple(
        b
        for b in blockers
        if (
            b.bounds[0] <= x1
            and b.bounds[2] >= x0
            and b.bounds[1] <= y1
            and b.bounds[3] >= y0
            and b.lower <= z1
            and b.upper >= z0
        )
    )
    if not remaining:
        return True
    first, second = _box(observer), _box(target)
    planes = _candidate_planes(first, second)
    for blocker in remaining:
        clear = False
        for plane, sign in product(planes, (-1, 1)):
            normal = (sign * plane[0], sign * plane[1], sign * plane[2])
            opposite = (-normal[0], -normal[1], -normal[2])
            base, support2 = _prism_support(blocker, opposite)
            width2 = CORRIDOR_RADIUS * CORRIDOR_RADIUS * (normal[0] ** 2 + normal[1] ** 2)
            expansion = rational_sqrt_bounds(support2)[1] + rational_sqrt_bounds(width2)[1]
            if all(
                -base - endpoint_base > expansion + rational_sqrt_bounds(endpoint_square)[1]
                for endpoint_base, endpoint_square in (
                    _prism_support(observer, normal),
                    _prism_support(target, normal),
                )
            ):
                clear = True
                break
        if not clear:
            return False
    return True


def full_visibility_by_observer_caps(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    blockers: tuple[VisibilityPrism, ...],
) -> bool:
    """Cover all facing patches using the observer's complete top/bottom faces.

    A vertical target side's outward normal has zero Z component, so moving a
    valid viewing origin vertically to the observer top preserves facing. Top
    target faces can also use that top. If any observer point is below the target,
    the bottom-origin face is checked separately for the target bottom cap. Each
    check encloses ALL XY origins, avoiding a fixed-origin self-occlusion error.
    """
    top = replace(observer, lower=observer.upper)
    bottom = replace(observer, upper=observer.lower)
    return (
        corridors_clear_by_enclosure(top, target, blockers)
        and (
            observer.lower >= target.lower
            or corridors_clear_by_enclosure(bottom, replace(target, upper=target.lower), blockers)
        )
    ) or (
        corridors_clear_by_enclosure(bottom, target, blockers)
        and (
            observer.upper <= target.upper
            or corridors_clear_by_enclosure(top, replace(target, lower=target.upper), blockers)
        )
    )


def _inner_sqrt(value: Fraction) -> Fraction:
    return rational_sqrt_bounds(value)[0]


def full_visibility_by_parallel_circle_corridors(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    """Enclose a self-valid parallel corridor for EVERY facing part of equal circles.

    With equal radii/heights and separated centers, the facing side is exactly
    the target semicircle toward the observer. Reflect each radial point's axial
    component to the observer's forward semicircle, retaining its lateral/Z
    coordinates. Raise every selected origin to the observer top; this preserves
    side facing. No target cap faces an equal-height observer. The resulting XY
    corridor is parallel to the center displacement, including displaced tangents.
    The rectangle below encloses that whole family including the corridor width.
    """
    radius = circle_radius(observer)
    if (
        radius is None
        or radius != circle_radius(target)
        or observer.lower != target.lower
        or observer.upper != target.upper
    ):
        return False
    assert isinstance(observer.footprint, RationalEllipse)
    assert isinstance(target.footprint, RationalEllipse)
    start, end = observer.footprint.center, target.footprint.center
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 <= 4 * radius * radius:
        return False
    factor = (radius + CORRIDOR_RADIUS) / rational_sqrt_bounds(length2)[0]
    vx, vy = -dy * factor, dx * factor
    enclosure = (
        (start[0] + vx, start[1] + vy),
        (end[0] + vx, end[1] + vy),
        (end[0] - vx, end[1] - vy),
        (start[0] - vx, start[1] - vy),
    )
    return all(
        blocker.upper < observer.lower
        or blocker.lower > observer.upper
        or not footprint_intersects_polygon(blocker.footprint, enclosure)
        or _below_parallel_top_origins(observer, blocker, dx, dy, length2, start)
        for blocker in blockers
    )


def _below_parallel_top_origins(
    observer: VisibilityPrism,
    blocker: VisibilityPrism,
    dx: Fraction,
    dy: Fraction,
    length2: Fraction,
    start: RationalPoint2,
) -> bool:
    """Separate a near-observer blocker from the entire raised corridor family.

    Let s be axial distance from the observer centre and a the reflected origin's
    axial offset. For s<=L/2, (L-a-s)/(L-2a) >= (L-s)/L, so every selected ray
    is at least H-(H-z0)*s/L high. Flat perpendicular offsets preserve s and z.
    Exact support tests require the WHOLE blocker before the midpoint and
    strictly below this plane. Failing either test proves nothing.
    """
    center_projection = dx * start[0] + dy * start[1]
    base, square = _prism_support(blocker, (dx, dy, Fraction(0)))
    midpoint_gap = center_projection + length2 / 2 - base
    if midpoint_gap < 0 or midpoint_gap * midpoint_gap < square:
        return False
    height = observer.upper - observer.lower
    base, square = _prism_support(blocker, (height * dx, height * dy, length2))
    gap = observer.upper * length2 + height * center_projection - base
    return gap > 0 and gap * gap > square


def all_corridors_blocked_by_endpoint_containment(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    """An identical footprint with covering heights contains every endpoint.

    The closed corridor always contains both endpoints. Exact footprint identity
    is a sufficient containment certificate for every supported shape; differing
    representations are left to the other complete predicates.
    """
    return any(
        blocker.footprint == endpoint.footprint
        and blocker.lower <= endpoint.lower
        and blocker.upper >= endpoint.upper
        for endpoint in (observer, target)
        for blocker in blockers
    )


def full_visibility_by_rear_circle_separation(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    """Certify the translated facing semicircle against collinear rear blockers.

    For equal circles and D=Ct-Co != 0, facing normals satisfy n·D<=0. Choose
    origin Co+R*n for target part Ct+R*n at the same Z. Their displacement -D
    is self-clear, including tangents, even if the circles overlap. A circular
    blocker whose centre is distance d>=0 beyond Ct has distance at least
    sqrt(d²+max(R-r,0)²) from every such flat corridor. In axial coordinates,
    w=-n·D/|D|>=0 makes the unclamped squared distance
    d²+(R-r)²+2*d*R*w+2*r*R*(1-sqrt(1-w²)); when lateral clearance clamps to
    zero, its axial distance is no smaller. Strict rational comparison retains
    contact; noncircular or noncollinear blockers leave the query unresolved.
    """
    radius = circle_radius(observer)
    if (
        radius is None
        or radius != circle_radius(target)
        or observer.lower != target.lower
        or observer.upper != target.upper
    ):
        return False
    assert isinstance(observer.footprint, RationalEllipse)
    assert isinstance(target.footprint, RationalEllipse)
    start, end = observer.footprint.center, target.footprint.center
    dx, dy = end[0] - start[0], end[1] - start[1]
    length2 = dx * dx + dy * dy
    if length2 == 0:
        return False
    lateral = max(radius - CORRIDOR_RADIUS, Fraction(0))
    for blocker in blockers:
        if blocker.upper < observer.lower or blocker.lower > observer.upper:
            continue
        blocker_radius = circle_radius(blocker)
        if blocker_radius is None:
            return False
        assert isinstance(blocker.footprint, RationalEllipse)
        bx, by = blocker.footprint.center[0] - end[0], blocker.footprint.center[1] - end[1]
        projection = bx * dx + by * dy
        if bx * dy != by * dx or projection < 0:
            return False
        if projection * projection + lateral * lateral * length2 <= blocker_radius**2 * length2:
            return False
    return True


def circle_radius(prism: VisibilityPrism) -> Fraction | None:
    footprint = prism.footprint
    if not isinstance(footprint, RationalEllipse):
        return None
    a, b = footprint.first_axis, footprint.second_axis
    if a[1] or b[0] or abs(a[0]) != abs(b[1]):
        return None
    return abs(a[0])


def center_projects_between_boxes(center: RationalPoint2, first: Bounds, second: Bounds) -> bool:
    for source, destination in ((first, second), (second, first)):
        lower = Fraction(0)
        for axis in (0, 1):
            offset = (center[axis] - source[axis + 2], center[axis] - source[axis])
            direction = (destination[axis] - source[axis + 2], destination[axis + 2] - source[axis])
            lower += min(a * b for a, b in product(offset, direction))
        if lower < 0:
            return False
    return True


def all_corridors_blocked_by_circle(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    """Prove a full-height circular blocker intercepts every corridor.

    The point at a fixed convex-combination parameter on every endpoint segment
    lies within the weighted endpoint radii of the corresponding center segment.
    Thus its distance to a blocker center is bounded by that radius plus the
    exact center-segment residual. If <= blocker radius+r, each line is within
    corridor contact distance. A separate interval-dot proof puts each closest
    point inside the flat caps, and full height covers its interpolated Z.
    """
    first_radius, last_radius = circle_radius(observer), circle_radius(target)
    if first_radius is None or last_radius is None:
        return False
    first, last = observer.footprint, target.footprint
    assert isinstance(first, RationalEllipse)
    assert isinstance(last, RationalEllipse)
    return _circle_enclosures_blocked(
        first.center, first_radius, last.center, last_radius, _box(observer), _box(target), blockers
    )


def all_box_corridors_blocked_by_circle(
    observer_box: Box, target_box: Box, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    def enclosure(box: Box) -> tuple[RationalPoint2, Fraction]:
        x0, y0, x1, y1 = box[0]
        return (
            ((x0 + x1) / 2, (y0 + y1) / 2),
            rational_sqrt_bounds(((x1 - x0) / 2) ** 2 + ((y1 - y0) / 2) ** 2)[1],
        )

    first, first_radius = enclosure(observer_box)
    last, last_radius = enclosure(target_box)
    return _circle_enclosures_blocked(
        first, first_radius, last, last_radius, observer_box, target_box, blockers
    )


def _circle_enclosures_blocked(
    first_center: RationalPoint2,
    first_radius: Fraction,
    last_center: RationalPoint2,
    last_radius: Fraction,
    observer_box: Box,
    target_box: Box,
    blockers: tuple[VisibilityPrism, ...],
) -> bool:
    dx, dy = last_center[0] - first_center[0], last_center[1] - first_center[1]
    length2 = dx * dx + dy * dy
    if not length2:
        return False
    for blocker in blockers:
        radius = circle_radius(blocker)
        if (
            radius is None
            or blocker.lower > min(observer_box[1], target_box[1])
            or blocker.upper < max(observer_box[2], target_box[2])
        ):
            continue
        footprint = blocker.footprint
        assert isinstance(footprint, RationalEllipse)
        bx, by = footprint.center[0] - first_center[0], footprint.center[1] - first_center[1]
        parameter = (bx * dx + by * dy) / length2
        if not 0 <= parameter <= 1:
            continue
        allowance = (
            radius + CORRIDOR_RADIUS - ((1 - parameter) * first_radius + parameter * last_radius)
        )
        distance2 = (bx - parameter * dx) ** 2 + (by - parameter * dy) ** 2
        if (
            allowance >= 0
            and distance2 <= allowance * allowance
            and center_projects_between_boxes(footprint.center, observer_box[0], target_box[0])
        ):
            return True
    return False


def _plane_rectangles(
    prism: VisibilityPrism, axis: int, coordinate: Fraction
) -> tuple[Bounds, ...]:
    """Certified cross-section rectangles for analytic ellipses and polygon unions.

    Ellipse sections use a rational LOWER square-root bound. Polygon sections
    are exact intervals through convex pieces. Failed enclosure proofs remain
    unresolved and never alter the complete analytic domain.
    """
    footprint = prism.footprint
    if isinstance(footprint, RationalEllipse):
        a, b = footprint.first_axis, footprint.second_axis
        qaa = a[axis] ** 2 + b[axis] ** 2
        qab = a[axis] * a[1 - axis] + b[axis] * b[1 - axis]
        qbb = a[1 - axis] ** 2 + b[1 - axis] ** 2
        offset = coordinate - footprint.center[axis]
        remainder = 1 - offset * offset / qaa
        if remainder < 0:
            return ()
        extent = _inner_sqrt((qbb - qab * qab / qaa) * remainder)
        center = footprint.center[1 - axis] + qab * offset / qaa
        return ((center - extent, prism.lower, center + extent, prism.upper),)
    result: list[Bounds] = []
    for part in convex_polygon_parts(footprint):
        cuts: list[Fraction] = []
        for first, last in zip(part, (*part[1:], part[0]), strict=True):
            if first[axis] == coordinate:
                cuts.append(first[1 - axis])
            if min(first[axis], last[axis]) < coordinate < max(first[axis], last[axis]):
                t = (coordinate - first[axis]) / (last[axis] - first[axis])
                cuts.append(first[1 - axis] + t * (last[1 - axis] - first[1 - axis]))
        if cuts:
            result.append((min(cuts), prism.lower, max(cuts), prism.upper))
    return tuple(result)


def _interval_covered(
    low: Fraction, high: Fraction, intervals: tuple[tuple[Fraction, Fraction], ...]
) -> bool:
    reached = low
    for start, end in sorted(intervals):
        if end < reached:
            continue
        if start > reached:
            return False
        reached = max(reached, end)
        if reached >= high:
            return True
    return False


def _rectangle_covered(target: Bounds, blockers: tuple[Bounds, ...]) -> bool:
    x0, y0, x1, y1 = target
    if _interval_covered(x0, x1, tuple((a, c) for a, b, c, d in blockers if b <= y0 and d >= y1)):
        return True
    cuts = sorted({x0, x1, *(x for box in blockers for x in (box[0], box[2]) if x0 < x < x1)})
    probes = (*cuts, *((a + b) / 2 for a, b in pairwise(cuts)))
    return all(
        _interval_covered(y0, y1, tuple((b, d) for a, b, c, d in blockers if a <= x <= c))
        for x in probes
    )


def _projection_bounds(first: Box, second: Box, axis: int, coordinate: Fraction) -> Bounds | None:
    first_points, second_points = _vertices(first), _vertices(second)
    first_min, first_max = min(p[axis] for p in first_points), max(p[axis] for p in first_points)
    second_min, second_max = (
        min(p[axis] for p in second_points),
        max(p[axis] for p in second_points),
    )
    if not (first_max < coordinate < second_min or second_max < coordinate < first_min):
        return None
    projected: list[RationalPoint2] = []
    for a, b in product(first_points, second_points):
        parameter = (coordinate - a[axis]) / (b[axis] - a[axis])
        projected.append(
            (
                a[1 - axis] + parameter * (b[1 - axis] - a[1 - axis]),
                a[2] + parameter * (b[2] - a[2]),
            )
        )
    return (
        min(x for x, _ in projected),
        min(y for _, y in projected),
        max(x for x, _ in projected),
        max(y for _, y in projected),
    )


def all_corridors_blocked_by_plane(
    observer: VisibilityPrism,
    target: VisibilityPrism,
    blockers: tuple[VisibilityPrism, ...],
    *,
    target_point: RationalPoint3 | None = None,
) -> bool:
    """Prove all centerlines hit a covered cross-section between the domains.

    Perspective projection of convex endpoint boxes onto a strictly separating
    plane is contained in the convex hull of their vertex-pair intersections.
    Its bounding rectangle is therefore conservative. Covering that rectangle
    with exact blocker sections blocks every 1mm corridor (including its center).
    """
    target_box = (
        _box(target)
        if target_point is None
        else (
            (target_point[0], target_point[1], target_point[0], target_point[1]),
            target_point[2],
            target_point[2],
        )
    )
    return all_box_corridors_blocked_by_plane(_box(observer), target_box, blockers)


def all_box_corridors_blocked_by_plane(
    observer_box: Box, target_box: Box, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    """Certify every corridor between two closed bounding boxes as blocked.

    Callers must establish that the boxes enclose the endpoint domains they claim
    to certify. This also supports half-space enclosures of self-visible origins.
    """
    for axis in (0, 1):
        coordinates = sorted(
            {
                value
                for b in blockers
                for value in (
                    ((b.bounds[axis] + b.bounds[axis + 2]) / 2,)
                    if isinstance(b.footprint, RationalEllipse)
                    else tuple(point[axis] for point in b.footprint)
                )
            }
        )
        for coordinate in coordinates:
            projection = _projection_bounds(observer_box, target_box, axis, coordinate)
            if projection is None:
                continue
            rectangles = tuple(
                rectangle for b in blockers for rectangle in _plane_rectangles(b, axis, coordinate)
            )
            # A strip cut by an X/Y plane has transverse half-width at least r.
            # Moving that transverse coordinate by <=r changes the segment's
            # longitudinal coordinate by <=r; endpoint margins >r keep the
            # adjusted point inside both flat caps. Its Z remains between the
            # endpoint heights, so only sections spanning that entire interval
            # may use this width certificate. Partial-height sections retain
            # the centerline-only proof above.
            margin = min(
                abs(coordinate - bound)
                for box in (observer_box, target_box)
                for bound in (box[0][axis], box[0][axis + 2])
            )
            if margin > CORRIDOR_RADIUS:
                z0, z1 = min(observer_box[1], target_box[1]), max(observer_box[2], target_box[2])
                rectangles = tuple(
                    (a - CORRIDOR_RADIUS, b, c + CORRIDOR_RADIUS, d)
                    if b <= z0 and d >= z1
                    else (a, b, c, d)
                    for a, b, c, d in rectangles
                )
            if _rectangle_covered(projection, rectangles):
                return True
    return False
