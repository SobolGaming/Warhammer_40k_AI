"""Continuous physical-footprint predicates shared by collisions and certificates."""

from __future__ import annotations

from dataclasses import replace
from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.base import BaseShape, CircularBase
from warhammer40k_core.geometry.exact_contact import ExactDisk
from warhammer40k_core.geometry.exact_coordinate import rational_coordinate
from warhammer40k_core.geometry.exact_path import ExactDiskSweep
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import GeometryError, Pose
from warhammer40k_core.geometry.visibility_algebra import Formula, RealTerm, both, decide, term


def nonoverlapping(predicates: PlacementPredicates, first: Footprint, second: Footprint) -> Formula:
    if first.kind == second.kind == "circle":
        return ((first.x - second.x) ** 2 + (first.y - second.y) ** 2).ge(
            (first.a + second.a - Fraction(1, 1_000_000_000)) ** 2
        )
    nx, ny, a, b = (predicates.scalar() for _ in range(4))
    return both(
        (nx * nx + ny * ny).eq(1),
        first.support_at_most(nx, ny, a),
        second.support_at_most(nx, ny, b),
        ((second.x - first.x) * nx + (second.y - first.y) * ny).ge(
            a + b - Fraction(1, 1_000_000_000)
        ),
    )


@lru_cache(maxsize=4096)
def physical_footprints_overlap(
    first: BaseShape, first_pose: Pose, second: BaseShape, second_pose: Pose
) -> bool:
    if type(first) is CircularBase and type(second) is CircularBase:
        return first_pose.distance_2d_to(second_pose) < first.radius + second.radius - 1e-9
    predicates = PlacementPredicates(prefix="physical_separation")
    return not decide(
        nonoverlapping(
            predicates, Footprint.fixed(first, first_pose), Footprint.fixed(second, second_pose)
        ),
        tuple(predicates.names),
    )


def translated_footprint_crosses(
    first: BaseShape, start: Pose, end: Pose, second: BaseShape, obstacle: Pose
) -> bool:
    """Strict interior intersection over one continuous projected translation."""
    if type(first) is not CircularBase and start.facing != end.facing:
        raise GeometryError("A translated footprint requires fixed facing.")
    reach = first.max_radius() + second.max_radius()
    if (
        obstacle.position.x < min(start.position.x, end.position.x) - reach
        or obstacle.position.x > max(start.position.x, end.position.x) + reach
        or obstacle.position.y < min(start.position.y, end.position.y) - reach
        or obstacle.position.y > max(start.position.y, end.position.y) + reach
    ):
        return False
    if type(first) is CircularBase and type(second) is CircularBase:
        radius_sum = rational(first.radius) + rational(second.radius) - Fraction(1, 1_000_000_000)
        if radius_sum <= 0:
            return False
        # Normalize by the actual combined radius to use the exact sweep without
        # snapping a native pose or catalog base to a milli-inch grid.
        origin_x, origin_y = rational(obstacle.position.x), rational(obstacle.position.y)

        def normalized(pose: Pose) -> ExactDisk:
            return ExactDisk(
                (
                    rational_coordinate((rational(pose.position.x) - origin_x) / radius_sum),
                    rational_coordinate((rational(pose.position.y) - origin_y) / radius_sum),
                ),
                1000,
            )

        return not ExactDiskSweep(normalized(start), normalized(end)).clears(normalized(obstacle))
    predicates = PlacementPredicates(prefix="translated_overlap")
    t, x, y = (predicates.scalar() for _ in range(3))
    initial = Footprint.fixed(first, start)
    translated = replace(
        initial,
        x=initial.x + t * (rational(end.position.x) - rational(start.position.x)),
        y=initial.y + t * (rational(end.position.y) - rational(start.position.y)),
    )
    stationary = Footprint.fixed(second, obstacle)
    return decide(
        both(t.ge(0), t.le(1), _interior(translated, x, y), _interior(stationary, x, y)),
        tuple(predicates.names),
    )


def _interior(shape: Footprint, x: RealTerm, y: RealTerm) -> Formula:
    u, v = shape.local(x, y)
    if shape.kind == "rectangle":
        return both(u.gt(-shape.a), u.lt(shape.a), v.gt(-shape.b), v.lt(shape.b))
    return ((u * shape.b) ** 2 + (v * shape.a) ** 2).lt((shape.a * shape.b) ** 2)


@lru_cache(maxsize=4096)
def physical_footprints_within(
    first: BaseShape, first_pose: Pose, second: BaseShape, second_pose: Pose, distance: float
) -> bool:
    predicates = PlacementPredicates(prefix="physical_proximity")
    return decide(
        predicates.near(
            Footprint.fixed(first, first_pose),
            Footprint.fixed(second, second_pose),
            term(rational(distance)),
        ),
        tuple(predicates.names),
    )
