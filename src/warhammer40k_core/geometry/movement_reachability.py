"""Deterministic, bounded-cache reachability for mandatory movement endpoints.

Queries own immutable geometry and policy values, never a mutable game or an entity-ID-only
cache key. Every successful answer contains a path validated by the ordinary path owners.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, replace
from enum import StrEnum
from functools import lru_cache
from itertools import pairwise

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import CircularBase, base_distance
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathWitness,
    TerrainPathLegalityContext,
)
from warhammer40k_core.geometry.polygons import Point2D, triangulate_polygon
from warhammer40k_core.geometry.pose import GeometryError, Pose, validate_finite_number
from warhammer40k_core.geometry.volume import Model

_EPSILON = 1e-8


@dataclass(frozen=True, slots=True)
class MovementGoal:
    """Union of model ranges or polygon ranges, with explicit vertical geometry."""

    models: tuple[Model, ...] = ()
    disk: tuple[Pose, CircularBase] | None = None
    polygons: tuple[tuple[Point2D, ...], ...] = ()
    horizontal_inches: float = 0.0
    vertical_inches: float = 0.0
    z_inches: float = 0.0

    def __post_init__(self) -> None:
        if sum((bool(self.models), bool(self.polygons), self.disk is not None)) != 1:
            raise GeometryError("Movement goal requires exactly one kind of target geometry.")
        for value in (self.horizontal_inches, self.vertical_inches):
            if validate_finite_number("movement goal range", value) < 0:
                raise GeometryError("Movement goal ranges must be non-negative.")
        validate_finite_number("movement goal z", self.z_inches)
        for polygon in self.polygons:
            triangulate_polygon(polygon)

    def contains(self, model: Model) -> bool:
        if self.models:
            return any(
                model.is_within_engagement_range(
                    target,
                    horizontal_inches=self.horizontal_inches,
                    vertical_inches=self.vertical_inches,
                )
                for target in self.models
            )
        bottom, top = model.volume.vertical_interval(model.pose)
        if self.disk is not None:
            pose, base = self.disk
            gap = max(bottom - pose.position.z, pose.position.z - top, 0.0)
            return (
                gap <= self.vertical_inches
                and base_distance(model.base, model.pose, base, pose) <= self.horizontal_inches
            )
        gap = max(bottom - self.z_inches, self.z_inches - top, 0.0)
        return gap <= self.vertical_inches and any(
            shapely_backend.base_footprint_distance_to_polygon(model.base, model.pose, polygon)
            <= self.horizontal_inches
            for polygon in self.polygons
        )

    def distance_lower_bound(
        self, model: Model, *, ignores_vertical_distance: bool = False
    ) -> float:
        # Every orientation fits inside this disk. Its distance to the target
        # region cannot exceed the translation needed by any rotated footprint.
        radius = model.base.max_radius()
        if self.models:
            return min(
                math.hypot(
                    max(
                        0.0,
                        model.pose.distance_2d_to(target.pose)
                        - radius
                        - target.base.max_radius()
                        - self.horizontal_inches,
                    ),
                    0.0
                    if ignores_vertical_distance
                    else max(
                        0.0,
                        model.volume.vertical_gap_to(model.pose, target.volume, target.pose)
                        - self.vertical_inches,
                    ),
                )
                for target in self.models
            )
        bottom, top = model.volume.vertical_interval(model.pose)
        if self.disk is not None:
            pose, base = self.disk
            return math.hypot(
                max(
                    0.0,
                    model.pose.distance_2d_to(pose) - radius - base.radius - self.horizontal_inches,
                ),
                0.0
                if ignores_vertical_distance
                else max(
                    0.0,
                    bottom - pose.position.z - self.vertical_inches,
                    pose.position.z - top - self.vertical_inches,
                ),
            )
        return math.hypot(
            max(
                0.0,
                min(
                    shapely_backend.point_distance_to_polygon(
                        model.pose.position.x,
                        model.pose.position.y,
                        polygon,
                    )
                    for polygon in self.polygons
                )
                - radius
                - self.horizontal_inches,
            ),
            0.0
            if ignores_vertical_distance
            else max(
                0.0,
                bottom - self.z_inches - self.vertical_inches,
                self.z_inches - top - self.vertical_inches,
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementReachabilityQuery:
    path_context: PathValidationContext
    terrain_context: TerrainPathLegalityContext
    goal: MovementGoal
    required_goals: tuple[MovementGoal, ...] = ()
    forbidden_goals: tuple[MovementGoal, ...] = ()
    coherent_models: tuple[Model, ...] = ()
    coherency_horizontal_inches: float = 2.0
    coherency_vertical_inches: float = 5.0
    maximum_target_range_inches: float | None = None
    coherency_neighbor_count: int = 1
    coherency_max_span_inches: float | None = None
    coherency_all_models_distance_inches: float | None = None

    def __post_init__(self) -> None:
        if self.path_context.moving_model != self.terrain_context.moving_model:
            raise GeometryError("Reachability path and terrain source geometry must agree.")
        if self.path_context.movement_distance_budget_inches is None:
            raise GeometryError("Reachability requires an explicit movement budget.")
        if self.maximum_target_range_inches is not None and (
            not self.goal.models
            or validate_finite_number("reachability target range", self.maximum_target_range_inches)
            < 0
        ):
            raise GeometryError("Target range constraint requires models and nonnegative range.")
        if self.coherency_neighbor_count < 1:
            raise GeometryError("Reachability coherency requires positive neighbor count.")
        if any(
            model.model_id == self.path_context.moving_model.model_id
            for model in self.coherent_models
        ):
            raise GeometryError("Reachability peers must exclude the moving model.")


class MovementReachabilityStatus(StrEnum):
    REACHABLE = "reachable"
    UNREACHABLE = "unreachable"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class MovementReachabilityResult:
    witness: PathWitness | None
    explored_nodes: int
    status: MovementReachabilityStatus

    @property
    def reachable(self) -> bool:
        return self.witness is not None


def movement_reachability(query: MovementReachabilityQuery) -> MovementReachabilityResult:
    if type(query) is not MovementReachabilityQuery:
        raise GeometryError("Movement reachability requires a typed immutable query.")
    return _cached_reachability(query)


def movement_reachability_cache_info() -> tuple[int, int, int, int]:
    info = _cached_reachability.cache_info()
    return info.hits, info.misses, info.maxsize or 0, info.currsize


def clear_movement_reachability_cache() -> None:
    _cached_reachability.cache_clear()


@lru_cache(maxsize=512)
def _cached_reachability(query: MovementReachabilityQuery) -> MovementReachabilityResult:
    source = query.path_context.moving_model
    budget = query.path_context.movement_distance_budget_inches
    if budget is None:
        raise GeometryError("Reachability budget is absent.")
    if _endpoint_satisfies(query, source):
        stationary = _validated_witness(query, (source.pose, source.pose))
        if stationary is not None:
            return MovementReachabilityResult(stationary, 0, MovementReachabilityStatus.REACHABLE)
    if (
        query.goal.distance_lower_bound(
            source, ignores_vertical_distance=query.path_context.ignores_vertical_distance
        )
        > budget + _EPSILON
    ):
        return MovementReachabilityResult(None, 0, MovementReachabilityStatus.UNREACHABLE)
    # Direct paths are overwhelmingly the common headless case. Route construction is lazy.
    targets = _goal_poses(query, source.pose)
    for target in targets:
        poses = _segment(source.pose, target)
        witness = _validated_witness(query, poses)
        if witness is not None and _endpoint_satisfies(query, replace(source, pose=target)):
            return MovementReachabilityResult(witness, 1, MovementReachabilityStatus.REACHABLE)
    nodes = _navigation_poses(query)
    start = source.pose
    queue: list[tuple[float, float, int, tuple[Pose, ...]]] = [(0.0, 0.0, -1, (start,))]
    best: dict[int, float] = {-1: 0.0}
    explored = 0
    while queue and explored < 128:
        _estimate, distance, index, path = heapq.heappop(queue)
        if distance != best[index]:
            continue
        explored += 1
        current = path[-1]
        for target in _goal_poses(query, current):
            full = (*path[:-1], *_segment(current, target))
            if _path_length(query, full) > budget + _EPSILON:
                continue
            witness = _validated_witness(query, full)
            if witness is not None and _endpoint_satisfies(query, replace(source, pose=target)):
                return MovementReachabilityResult(
                    witness, explored, MovementReachabilityStatus.REACHABLE
                )
        for next_index, node in enumerate(nodes):
            if node == current:
                continue
            new_distance = distance + _distance(query, current, node)
            if new_distance > budget + _EPSILON or new_distance >= best.get(next_index, math.inf):
                continue
            lower = query.goal.distance_lower_bound(
                replace(source, pose=node),
                ignores_vertical_distance=query.path_context.ignores_vertical_distance,
            )
            if new_distance + lower > budget + _EPSILON:
                continue
            full = (*path[:-1], *_segment(current, node))
            if _validated_witness(query, full) is None:
                continue
            best[next_index] = new_distance
            heapq.heappush(queue, (new_distance + lower, new_distance, next_index, full))
    # Exhausting a navigation graph is not an impossibility proof. Never grant an
    # "if possible" exemption on the strength of a heuristic search failure.
    return MovementReachabilityResult(None, explored, MovementReachabilityStatus.UNRESOLVED)


def _goal_satisfied(query: MovementReachabilityQuery, model: Model) -> bool:
    return query.goal.contains(model) and (
        query.maximum_target_range_inches is None
        or min(model.range_to(target) for target in query.goal.models)
        < query.maximum_target_range_inches
    )


def _endpoint_satisfies(query: MovementReachabilityQuery, model: Model) -> bool:
    if not _goal_satisfied(query, model) or any(
        not goal.contains(model) for goal in query.required_goals
    ):
        return False
    if any(goal.contains(model) for goal in query.forbidden_goals):
        return False
    if not query.coherent_models:
        return True
    models = (*query.coherent_models, model)
    if query.coherency_all_models_distance_inches is not None:
        return all(
            first.range_to(second) <= query.coherency_all_models_distance_inches
            for first in models
            for second in models
        )
    adjacent = {
        item.model_id: {
            other.model_id
            for other in models
            if other.model_id != item.model_id
            and item.is_within_engagement_range(
                other,
                horizontal_inches=query.coherency_horizontal_inches,
                vertical_inches=query.coherency_vertical_inches,
            )
        }
        for item in models
    }
    if any(len(neighbors) < query.coherency_neighbor_count for neighbors in adjacent.values()):
        return False
    seen: set[str] = set()
    pending = [model.model_id]
    while pending:
        current = pending.pop()
        if current in seen:
            continue
        seen.add(current)
        pending.extend(sorted(adjacent[current] - seen))
    if len(seen) != len(models):
        return False
    span = query.coherency_max_span_inches
    return span is None or all(
        first.is_within_engagement_range(
            second, horizontal_inches=span, vertical_inches=query.coherency_vertical_inches
        )
        for first in models
        for second in models
    )


def _validated_witness(
    query: MovementReachabilityQuery, poses: tuple[Pose, ...]
) -> PathWitness | None:
    witness = PathWitness.for_paths(((query.path_context.moving_model.model_id, poses),))
    if not replace(query.path_context, witness=witness).validate().is_valid:
        return None
    if not replace(query.terrain_context, witness=witness).validate().is_valid:
        return None
    return witness


def _distance(query: MovementReachabilityQuery, first: Pose, second: Pose) -> float:
    return (
        first.distance_2d_to(second)
        if query.path_context.ignores_vertical_distance
        else first.distance_3d_to(second)
    )


def _path_length(query: MovementReachabilityQuery, poses: tuple[Pose, ...]) -> float:
    return sum(_distance(query, first, second) for first, second in pairwise(poses))


def _segment(first: Pose, last: Pose) -> tuple[Pose, ...]:
    if first == last:
        return (first, first)
    return (
        first,
        Pose.at(
            (first.position.x + last.position.x) / 2,
            (first.position.y + last.position.y) / 2,
            (first.position.z + last.position.z) / 2,
            facing_degrees=(first.facing.degrees + last.facing.degrees) / 2,
        ),
        last,
    )


def _goal_poses(query: MovementReachabilityQuery, origin: Pose) -> tuple[Pose, ...]:
    source = query.path_context.moving_model
    targets: list[tuple[float, float, float]] = []
    if query.goal.disk is not None:
        pose, _base = query.goal.disk
        targets.append((pose.position.x, pose.position.y, origin.position.z))
    for model in query.goal.models:
        targets.append((model.pose.position.x, model.pose.position.y, origin.position.z))
    for polygon in query.goal.polygons:
        for first, second in zip(polygon, (*polygon[1:], polygon[0]), strict=True):
            dx, dy = second[0] - first[0], second[1] - first[1]
            length = dx * dx + dy * dy
            t = max(
                0.0,
                min(
                    1.0,
                    ((origin.position.x - first[0]) * dx + (origin.position.y - first[1]) * dy)
                    / length,
                ),
            )
            targets.append((first[0] + t * dx, first[1] + t * dy, origin.position.z))
    candidates: set[Pose] = set()
    for x, y, z in targets:
        target = Pose.at(x, y, z, facing_degrees=origin.facing.degrees)
        if not _goal_satisfied(query, replace(source, pose=target)):
            continue
        if _goal_satisfied(query, replace(source, pose=origin)):
            candidates.add(origin)
            continue
        low, high = 0.0, 1.0
        for _ in range(48):
            t = (low + high) / 2
            candidate = Pose.at(
                origin.position.x + t * (x - origin.position.x),
                origin.position.y + t * (y - origin.position.y),
                z,
                facing_degrees=origin.facing.degrees,
            )
            if _goal_satisfied(query, replace(source, pose=candidate)):
                high = t
            else:
                low = t
        # Keep the endpoint on the legal side of the goal boundary.
        t = min(1.0, high + _EPSILON)
        candidates.add(
            Pose.at(
                origin.position.x + t * (x - origin.position.x),
                origin.position.y + t * (y - origin.position.y),
                z,
                facing_degrees=origin.facing.degrees,
            )
        )
    return tuple(
        sorted(
            candidates,
            key=lambda pose: (
                _distance(query, origin, pose),
                pose.position.x,
                pose.position.y,
                pose.position.z,
                pose.facing.degrees,
            ),
        )
    )


def _navigation_poses(query: MovementReachabilityQuery) -> tuple[Pose, ...]:
    source = query.path_context.moving_model
    budget = query.path_context.movement_distance_budget_inches
    if budget is None:
        raise GeometryError("Reachability budget is absent.")
    radius = source.base.max_radius() + _EPSILON
    points: set[Point2D] = {(source.pose.position.x, source.pose.position.y)}
    heights = {source.pose.position.z, 0.0}
    facings = {source.pose.facing.degrees}
    if not isinstance(source.base, CircularBase):
        facings.update(float(angle) for angle in range(0, 360, 15))
    for model in (*query.path_context.friendly_models, *query.path_context.enemy_models):
        if source.pose.distance_2d_to(model.pose) > budget + radius + model.base.max_radius():
            continue
        extent = radius + model.base.max_radius()
        # Circumscribed perimeter nodes never place the moving base inside the blocker.
        extent /= math.cos(math.pi / 32)
        for angle in range(32):
            theta = angle * math.tau / 32
            points.add(
                (
                    model.pose.position.x + extent * math.cos(theta),
                    model.pose.position.y + extent * math.sin(theta),
                )
            )
    for feature in query.terrain_context.terrain_features:
        polygon = feature.rules_footprint_points()
        for surface in feature.support_surfaces(no_overhang_required=False):
            heights.add(surface.z_inches)
        _add_polygon_routing_points(points, polygon, radius)
    for terrain in query.terrain_context.terrain:
        heights.add(terrain.bottom_center.z + terrain.height)
        min_x, min_y, max_x, max_y = shapely_backend.footprint_for_terrain(terrain).bounds
        _add_polygon_routing_points(
            points, ((min_x, min_y), (max_x, min_y), (max_x, max_y), (min_x, max_y)), radius
        )
    return tuple(
        sorted(
            (
                Pose.at(x, y, z, facing_degrees=facing)
                for x, y in points
                for z in heights
                for facing in facings
                if math.hypot(x - source.pose.position.x, y - source.pose.position.y)
                <= budget + _EPSILON
                and (
                    query.path_context.ignores_vertical_distance
                    or abs(z - source.pose.position.z) <= budget + _EPSILON
                )
            ),
            key=lambda pose: (
                pose.position.x,
                pose.position.y,
                pose.position.z,
                pose.facing.degrees,
            ),
        )
    )


def _add_polygon_routing_points(
    points: set[Point2D], polygon: tuple[Point2D, ...], radius: float
) -> None:
    for x, y in polygon:
        for dx, dy in ((-1, -1), (-1, 1), (1, -1), (1, 1)):
            points.add((x + dx * radius, y + dy * radius))
