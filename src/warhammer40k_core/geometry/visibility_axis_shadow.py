"""Exact exclusions for corridors crossing an axis between separated footprints."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from itertools import pairwise

from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    variable,
)
from warhammer40k_core.geometry.visibility_exact import (
    CORRIDOR_RADIUS,
    RationalEllipse,
    RationalPoint2,
    RationalPolygon,
    VisibilityPrism,
    convex_polygon_parts,
)


def _clip_at(polygon: RationalPolygon, axis: int, cut: Fraction, direction: int) -> RationalPolygon:
    if not polygon:
        return ()
    clipped: list[RationalPoint2] = []
    for first, last in pairwise((*polygon, polygon[0])):
        first_inside = (first[axis] - cut) * direction >= 0
        last_inside = (last[axis] - cut) * direction >= 0
        if first_inside:
            clipped.append(first)
        if first_inside != last_inside:
            portion = (cut - first[axis]) / (last[axis] - first[axis])
            clipped.append(
                (
                    first[0] + portion * (last[0] - first[0]),
                    first[1] + portion * (last[1] - first[1]),
                )
            )
    return tuple(dict.fromkeys(clipped))


def _joined_height_intervals(blockers: tuple[VisibilityPrism, ...]) -> tuple[VisibilityPrism, ...]:
    by_footprint: dict[RationalEllipse | RationalPolygon, list[VisibilityPrism]] = {}
    for blocker in blockers:
        by_footprint.setdefault(blocker.footprint, []).append(blocker)
    result: list[VisibilityPrism] = []
    for pieces in by_footprint.values():
        first, *remaining = sorted(pieces, key=lambda blocker: blocker.lower)
        for piece in remaining:
            if first.upper < piece.lower:
                result.append(first)
                first = piece
            else:
                first = replace(first, upper=max(first.upper, piece.upper))
        result.append(first)
    return tuple(result)


def _ellipse_line_offset(
    ellipse: RationalEllipse, axis: int, slope: RealTerm, offset: RealTerm
) -> tuple[RealTerm, RealTerm]:
    across = 1 - axis
    distance = slope * ellipse.center[axis] + offset - ellipse.center[across]
    support_square = (slope * ellipse.first_axis[axis] - ellipse.first_axis[across]) ** 2 + (
        slope * ellipse.second_axis[axis] - ellipse.second_axis[across]
    ) ** 2
    return distance, support_square


def _axis_shadow_clauses(
    left: VisibilityPrism,
    right: VisibilityPrism,
    blockers: tuple[VisibilityPrism, ...],
    axis: int,
    slope: RealTerm,
    offset: RealTerm,
) -> tuple[Formula, ...]:
    radius = CORRIDOR_RADIUS
    start, stop = left.bounds[axis + 2] + radius, right.bounds[axis] - radius
    if start >= stop:
        return ()
    # At a fixed axis coordinate the corridor contains the transverse centerline
    # coordinate +/- radius. The corresponding centerline points are within one
    # radius along the axis. Bound their heights using the extreme endpoint pair
    # that puts the convex combination closest to the higher cap.
    lower = min(left.lower, right.lower)
    if left.upper <= right.upper:
        first, last = left.bounds[axis], right.bounds[axis]
        shift = radius
    else:
        first, last = left.bounds[axis + 2], right.bounds[axis + 2]
        shift = -radius
    height_slope = (right.upper - left.upper) / (last - first)
    exclusions: list[Formula] = []
    for blocker in blockers:
        if blocker.lower > lower:
            continue
        lo, hi = start, stop
        if height_slope > 0:
            hi = min(hi, first - shift + (blocker.upper - left.upper) / height_slope)
        elif height_slope < 0:
            lo = max(lo, first - shift + (blocker.upper - left.upper) / height_slope)
        elif blocker.upper < left.upper:
            continue
        if lo > hi:
            continue

        footprint = blocker.footprint
        if isinstance(footprint, RationalEllipse):
            if lo <= blocker.bounds[axis] and blocker.bounds[axis + 2] <= hi:
                distance, support_square = _ellipse_line_offset(footprint, axis, slope, offset)
                exclusions.append(
                    either(
                        *(
                            both(margin.gt(0), (margin * margin).gt(support_square))
                            for margin in (distance - radius, -distance - radius)
                        )
                    )
                )
            continue
        for part in convex_polygon_parts(footprint):
            clipped = _clip_at(_clip_at(part, axis, lo, 1), axis, hi, -1)
            if clipped:
                distances = tuple(slope * p[axis] + offset - p[1 - axis] for p in clipped)
                exclusions.append(
                    either(
                        both(*(distance.gt(radius) for distance in distances)),
                        both(*(distance.lt(-radius) for distance in distances)),
                    )
                )
    return tuple(exclusions)


def all_corridors_blocked_by_axis_shadow(
    observer: VisibilityPrism, target: VisibilityPrism, blockers: tuple[VisibilityPrism, ...]
) -> bool:
    """Prove impossibility with a necessary condition on each projected centerline.

    Only regions guaranteed inside the corridor's possible height interval
    contribute to the proof. A feasible projected line leaves the complete
    three-dimensional query to the existing exact solver.
    """
    source, destination = observer.footprint, target.footprint
    if not isinstance(source, RationalEllipse) or not isinstance(destination, RationalEllipse):
        return False
    joined = _joined_height_intervals(blockers)
    slope, offset = variable("slope"), variable("offset")
    axes = sorted(
        (0, 1),
        key=lambda axis: abs(source.center[axis] - destination.center[axis]),
        reverse=True,
    )
    for axis in axes:
        left, right = sorted((observer, target), key=lambda prism: prism.bounds[axis])
        exclusions = _axis_shadow_clauses(left, right, joined, axis, slope, offset)
        if not exclusions:
            continue
        domains = tuple(
            _ellipse_line_offset(ellipse, axis, slope, offset) for ellipse in (source, destination)
        )
        possible = both(
            *((distance * distance).le(support) for distance, support in domains), *exclusions
        )
        if not decide(possible, ("slope", "offset")):
            return True
    return False
