"""Exact circular-passenger existence for Emergency Disembark set-up.

Coordinates are rationalized from their decimal representation. A negative
answer requires an unsatisfiability proof over all translations. Sampling,
congestion heuristics, and proposed orientations are never such proof.
Non-circular bases raise rather than approximating a rules answer. Contact
counts as overlap, so legal set-up is an open set; closeness uses the source
tolerance instead of an open-set strictly-closer query.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    term,
    variable,
)


@dataclass(frozen=True, slots=True)
class CircleObstacle:
    x: Fraction
    y: Fraction
    radius: Fraction


@dataclass(frozen=True, slots=True)
class AxisAlignedRectObstacle:
    min_x: Fraction
    max_x: Fraction
    min_y: Fraction
    max_y: Fraction

    def __post_init__(self) -> None:
        if self.max_x <= self.min_x or self.max_y <= self.min_y:
            raise GeometryError("Emergency Disembark wall obstacle requires a positive rectangle.")


@dataclass(frozen=True, slots=True)
class CircularEmergencyPoseQuery:
    transport_x: Fraction
    transport_y: Fraction
    transport_radius: Fraction
    passenger_radius: Fraction
    containment_center_limit: Fraction
    battlefield_width: Fraction
    battlefield_depth: Fraction
    overlap_obstacles: tuple[CircleObstacle, ...]
    unengaged_obstacles: tuple[tuple[CircleObstacle, Fraction], ...]
    require_unengaged: bool
    closer_than_center: Fraction | None
    neighbor_obstacles: tuple[tuple[CircleObstacle, Fraction], ...]
    span_obstacles: tuple[tuple[CircleObstacle, Fraction], ...]
    rect_obstacles: tuple[AxisAlignedRectObstacle, ...] = ()


@lru_cache(maxsize=512)
def circular_emergency_pose_exists(query: CircularEmergencyPoseQuery) -> bool:
    if type(query) is not CircularEmergencyPoseQuery:
        raise GeometryError("Emergency Disembark fit requires CircularEmergencyPoseQuery.")
    passenger = query.passenger_radius
    if passenger <= 0 or query.transport_radius <= 0:
        raise GeometryError("Emergency Disembark fit requires positive radii.")
    if query.battlefield_width < 2 * passenger or query.battlefield_depth < 2 * passenger:
        return False
    overlap_limit = query.transport_radius + passenger
    if query.containment_center_limit <= overlap_limit:
        return False
    if query.closer_than_center is not None and query.closer_than_center <= overlap_limit:
        return False
    x, y = variable("x"), variable("y")
    tx, ty = term(query.transport_x), term(query.transport_y)
    center_squared = (x - tx) ** 2 + (y - ty) ** 2
    constraints: list[Formula] = [
        x.ge(passenger),
        y.ge(passenger),
        x.le(query.battlefield_width - passenger),
        y.le(query.battlefield_depth - passenger),
        center_squared.le(query.containment_center_limit**2),
        center_squared.gt(overlap_limit**2),
    ]
    if query.closer_than_center is not None:
        constraints.append(center_squared.lt(query.closer_than_center**2))
    for obstacle in query.overlap_obstacles:
        constraints.append(
            ((x - obstacle.x) ** 2 + (y - obstacle.y) ** 2).gt((passenger + obstacle.radius) ** 2)
        )
    for rect in query.rect_obstacles:
        constraints.append(_circle_strictly_outside_rect(x, y, passenger, rect))
    if query.require_unengaged:
        for obstacle, engagement in query.unengaged_obstacles:
            constraints.append(
                ((x - obstacle.x) ** 2 + (y - obstacle.y) ** 2).gt(
                    (passenger + obstacle.radius + engagement) ** 2
                )
            )
    if query.neighbor_obstacles:
        constraints.append(
            either(
                *(
                    ((x - obstacle.x) ** 2 + (y - obstacle.y) ** 2).le(
                        (passenger + obstacle.radius + distance) ** 2
                    )
                    for obstacle, distance in query.neighbor_obstacles
                )
            )
        )
    for obstacle, distance in query.span_obstacles:
        constraints.append(
            ((x - obstacle.x) ** 2 + (y - obstacle.y) ** 2).le(
                (passenger + obstacle.radius + distance) ** 2
            )
        )
    return decide(both(*constraints), ("x", "y"))


def _circle_strictly_outside_rect(
    x: RealTerm,
    y: RealTerm,
    radius: Fraction,
    rect: AxisAlignedRectObstacle,
) -> Formula:
    # Exact open Minkowski complement: two side strips plus four corner disks.
    return both(
        either(
            x.lt(rect.min_x - radius),
            x.gt(rect.max_x + radius),
            y.lt(rect.min_y),
            y.gt(rect.max_y),
        ),
        either(
            y.lt(rect.min_y - radius),
            y.gt(rect.max_y + radius),
            x.lt(rect.min_x),
            x.gt(rect.max_x),
        ),
        *(
            ((x - corner_x) ** 2 + (y - corner_y) ** 2).gt(radius**2)
            for corner_x, corner_y in (
                (rect.min_x, rect.min_y),
                (rect.min_x, rect.max_y),
                (rect.max_x, rect.min_y),
                (rect.max_x, rect.max_y),
            )
        ),
    )
