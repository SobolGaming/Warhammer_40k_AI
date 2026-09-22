"""Sufficient continuous proofs that terrain excludes every mandatory endpoint.

The formula deliberately contains *more* endpoints than the rules permit: a
translation ball, enclosing target footprints, and small disks strictly inside
the moving base and terrain walls. Unsatisfiability therefore proves exclusion
for every facing and path. Satisfiability says nothing about path feasibility.
Neither a navigation miss nor a solver failure is an impossibility certificate.
"""

from __future__ import annotations

from fractions import Fraction
from typing import TYPE_CHECKING

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.placement_predicates import rational
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainVolume
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    variable,
)
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.geometry.movement_reachability import MovementGoal

_SLACK = Fraction(1, 100_000_000)


def endpoint_excluded_by_terrain(
    *,
    source: Model,
    goal: MovementGoal,
    budget: float,
    ignores_vertical_distance: bool,
    terrain: tuple[TerrainVolume, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> bool:
    """Return only a proved negative; False means this certificate is inconclusive.

    Only feature-owned walls actually checked by TerrainPathLegalityContext enter
    the proof. Floors/support surfaces, raw unclassified volumes, coherency and
    other models are relaxed away. This is a sufficient certificate, not a complete
    motion planner or an endpoint-only replacement for PathWitness validation.
    """
    walls = tuple(
        wall
        for feature in terrain_features
        for wall in feature.wall_volumes()
        if wall in terrain
        # The endpoint authority permits contact with a matching support-surface
        # identity. Relax such walls away rather than contradict that permission.
        and wall.terrain_id
        not in {f"{feature.feature_id}:{floor.floor_id}" for floor in feature.floors}
        and source.pose.position.distance_2d_to(wall.bottom_center)
        <= budget + source.base.max_radius() + wall.width + wall.depth
    )
    if not walls:
        return False
    x, y, z = (variable(name) for name in ("endpoint_x", "endpoint_y", "endpoint_z"))
    position = source.pose.position
    distance = (x - rational(position.x)) ** 2 + (y - rational(position.y)) ** 2
    if not ignores_vertical_distance:
        distance = distance + (z - rational(position.z)) ** 2
    constraints = [
        distance.le((rational(budget) + _SLACK) ** 2),
        _goal_region(source, goal, x, y, z),
    ]
    # Half the analytic inradius is strictly inside every supported footprint,
    # including the polygonal circle/ellipse used by the collision authority.
    # Circumscribed goal disks cover every continuous rotation, not sampled ones.
    base = source.base
    if isinstance(base, CircularBase):
        inner = rational(base.radius) / 2
    elif isinstance(base, (OvalBase, RectangularBase)):
        inner = rational(min(base.length, base.width)) / 4
    else:
        raise GeometryError("Endpoint proof requires a supported base shape.")
    for wall in walls:
        radius = inner + rational(min(wall.width, wall.depth)) / 4 - _SLACK
        if radius <= 0:
            continue
        constraints.append(
            either(
                (
                    (x - rational(wall.bottom_center.x)) ** 2
                    + (y - rational(wall.bottom_center.y)) ** 2
                ).ge(radius**2),
                z.ge(rational(wall.top_z_inches()) - _SLACK),
                (z + rational(source.volume.height)).le(rational(wall.bottom_center.z) + _SLACK),
            )
        )
    return not decide(both(*constraints), ("endpoint_x", "endpoint_y", "endpoint_z"))


def _goal_region(
    source: Model, goal: MovementGoal, x: RealTerm, y: RealTerm, z: RealTerm
) -> Formula:
    radius = rational(source.base.max_radius()) + _SLACK
    height = rational(source.volume.height)
    horizontal = rational(
        goal.horizontal_inches if goal.range_inches is None else goal.range_inches
    )
    vertical = rational(goal.vertical_inches if goal.range_inches is None else goal.range_inches)

    def region(cx: float, cy: float, extent: Fraction, bottom: float, top: float) -> Formula:
        return both(
            ((x - rational(cx)) ** 2 + (y - rational(cy)) ** 2).le(
                (radius + extent + horizontal) ** 2
            ),
            z.le(rational(top) + vertical + _SLACK),
            (z + height).ge(rational(bottom) - vertical - _SLACK),
        )

    if goal.models:
        return either(
            *(
                region(
                    target.pose.position.x,
                    target.pose.position.y,
                    rational(target.base.max_radius()),
                    *target.volume.vertical_interval(target.pose),
                )
                for target in goal.models
            )
        )
    if goal.disk is not None:
        pose, base = goal.disk
        return region(
            pose.position.x,
            pose.position.y,
            rational(base.radius),
            pose.position.z,
            pose.position.z,
        )
    return both(
        z.le(rational(goal.z_inches) + vertical + _SLACK),
        (z + height).ge(rational(goal.z_inches) - vertical - _SLACK),
        either(
            *(
                both(
                    x.ge(rational(min(point[0] for point in polygon)) - radius - horizontal),
                    x.le(rational(max(point[0] for point in polygon)) + radius + horizontal),
                    y.ge(rational(min(point[1] for point in polygon)) - radius - horizontal),
                    y.le(rational(max(point[1] for point in polygon)) + radius + horizontal),
                )
                for polygon in goal.polygons
            )
        ),
    )
