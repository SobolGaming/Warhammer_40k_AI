"""Continuous physical-footprint predicates shared by collisions and certificates."""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.base import BaseShape, CircularBase
from warhammer40k_core.geometry.placement_predicates import Footprint, PlacementPredicates, rational
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.visibility_algebra import Formula, both, decide, term


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
