"""Necessary path bounds for source-directed objectives behind blocked walls.

A continuous path crossing a wall's centre plane must pass one of its four
edges. Reflection across each edge gives a lower bound on the travelled distance.
The wall thickness, base radius, climbing contact and other obstacles are relaxed;
these conditions exclude impossible paths and never grant a playable witness.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.geometry.placement_predicates import rational
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    classified_feature_transit_permission,
)
from warhammer40k_core.geometry.visibility_algebra import Formula, RealTerm, both, either, term
from warhammer40k_core.geometry.visibility_shapes import rational_rotation

if TYPE_CHECKING:
    from warhammer40k_core.geometry.movement_reachability import MovementReachabilityQuery


def _through_forbidden(query: MovementReachabilityQuery, feature: TerrainFeatureDefinition) -> bool:
    context = query.terrain_context
    # MOBILE permission depends on elevation across the full touching path.
    # Relax that case rather than assuming the submitted path applies to a rival.
    if "MOBILE" in context.movement_keywords:
        return False
    classified = classified_feature_transit_permission(
        feature, context.movement_keywords, (context.moving_model.pose,)
    )
    if classified is not None:
        return not classified
    policy = context.terrain_movement_policy
    feature_policy = policy.policy_for_feature_kind(feature.feature_kind)
    return (
        policy.requires_permission_to_move_through_features
        and not feature_policy.can_move_through
        and not (
            set(context.movement_keywords) & set(feature_policy.through_terrain_allowed_keywords)
        )
    )


def objective_path_bounds(
    query: MovementReachabilityQuery, x: RealTerm, y: RealTerm, z: float
) -> Formula:
    context = query.terrain_context
    source = query.path_context.moving_model
    budget = query.path_context.movement_distance_budget_inches
    if budget is None or query.path_context.ignores_vertical_distance or context.has_fly:
        return both()
    origin = source.pose.position
    constraints: list[Formula] = []
    for feature in context.terrain_features:
        if not _through_forbidden(query, feature):
            continue
        policy = context.terrain_movement_policy
        feature_policy = policy.policy_for_feature_kind(feature.feature_kind)
        for wall in feature.wall_volumes():
            free_height = feature_policy.freely_moved_over_height_inches
            if free_height is None:
                free_height = policy.freely_traversable_height_threshold_inches
            free_height = max(free_height, context.terrain_as_if_absent_height_inches or 0)
            if wall.height <= free_height:
                continue
            horizontal_height = context.horizontal_terrain_transit_height_inches
            if horizontal_height is not None and wall.top_z_inches() <= horizontal_height:
                continue
            c, s = rational_rotation(wall.rotation_degrees)
            determinant = c * c + s * s
            cx, cy = rational(wall.bottom_center.x), rational(wall.bottom_center.y)
            dx, dy = rational(origin.x) - cx, rational(origin.y) - cy
            # Use the same rational axes as physical wall geometry. Their
            # determinant is retained, rather than assuming rounded trig is unit.
            start = (c * dx + s * dy, c * dy - s * dx, rational(origin.z))
            end = ((x - cx) * c + (y - cy) * s, (y - cy) * c - (x - cx) * s, term(rational(z)))
            axis = 0 if wall.width <= wall.depth else 1
            extent = wall.depth if axis == 0 else wall.width
            half_extent = rational(extent) * determinant / 2
            slack = rational(1e-9) * (determinant if determinant > 1 else rational(1))
            # The centre point of the physical base column must avoid the wall.
            # Relax its radius and collision tolerance, retaining every legal path.
            edges = (
                (1 - axis, -half_extent + slack, False),
                (1 - axis, half_extent - slack, True),
                (2, rational(wall.bottom_center.z - source.volume.height + 1e-9), False),
                (2, rational(wall.top_z_inches() - 1e-9), True),
            )
            if any((start[a] >= b if upper else start[a] <= b) for a, b, upper in edges):
                continue
            if start[axis] == 0:
                continue
            bypasses: list[Formula] = []
            for a, boundary, upper in edges:
                reflected = list(start)
                reflected[a] = 2 * boundary - start[a]
                squared = (
                    (end[0] - reflected[0]) ** 2
                    + (end[1] - reflected[1]) ** 2
                    + (end[2] - reflected[2]) ** 2 * determinant
                )
                outside = end[a].ge(boundary) if upper else end[a].le(boundary)
                bypasses.append(
                    either(outside, squared.le(rational(budget + 1e-8) ** 2 * determinant))
                )
            same_side = end[axis].le(0) if start[axis] < 0 else end[axis].ge(0)
            constraints.append(either(same_side, *bypasses))
    return both(*constraints)
