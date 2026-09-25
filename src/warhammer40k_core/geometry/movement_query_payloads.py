"""Closed, replay-safe payloads for a witnessed endpoint feasibility query."""

from __future__ import annotations

from typing import TypedDict, cast

from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.movement_reachability import MovementGoal, MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathValidationContextPayload,
    TerrainPathLegalityContext,
    TerrainPathLegalityContextPayload,
)
from warhammer40k_core.geometry.pose import GeometryError, Pose, PosePayload
from warhammer40k_core.geometry.volume import Model, ModelPayload


class MovementGoalPayload(TypedDict):
    models: list[ModelPayload]
    disk_pose: PosePayload | None
    disk_radius: float | None
    polygons: list[list[list[float]]]
    horizontal_inches: float
    vertical_inches: float
    z_inches: float
    range_inches: float | None


class MovementQueryPayload(TypedDict):
    path_context: PathValidationContextPayload
    terrain_context: TerrainPathLegalityContextPayload
    goal: MovementGoalPayload
    required_if_reachable_goals: list[MovementGoalPayload]
    required_goals: list[MovementGoalPayload]
    forbidden_goals: list[MovementGoalPayload]
    coherent_models: list[ModelPayload]
    coherency_horizontal_inches: float
    coherency_vertical_inches: float
    maximum_target_range_inches: float | None
    coherency_neighbor_count: int
    coherency_max_span_inches: float | None
    coherency_all_models_distance_inches: float | None
    closer_target_groups: list[list[ModelPayload]]


def goal_payload(goal: MovementGoal) -> MovementGoalPayload:
    return {
        "models": [m.to_payload() for m in goal.models],
        "disk_pose": None if goal.disk is None else goal.disk[0].to_payload(),
        "disk_radius": None if goal.disk is None else goal.disk[1].radius,
        "polygons": [[list(point) for point in polygon] for polygon in goal.polygons],
        "horizontal_inches": goal.horizontal_inches,
        "vertical_inches": goal.vertical_inches,
        "z_inches": goal.z_inches,
        "range_inches": goal.range_inches,
    }


def goal_from_payload(raw: MovementGoalPayload) -> MovementGoal:
    if frozenset(raw) != MovementGoalPayload.__required_keys__:
        raise GeometryError("Movement goal evidence fields drifted.")
    if (raw["disk_pose"] is None) != (raw["disk_radius"] is None):
        raise GeometryError("Movement goal disk evidence is incomplete.")
    if any(len(point) != 2 for poly in raw["polygons"] for point in poly):
        raise GeometryError("Movement goal polygon evidence is invalid.")
    return MovementGoal(
        models=tuple(Model.from_payload(m) for m in raw["models"]),
        disk=None
        if raw["disk_pose"] is None
        else (Pose.from_payload(raw["disk_pose"]), CircularBase(cast(float, raw["disk_radius"]))),
        polygons=tuple(tuple((p[0], p[1]) for p in poly) for poly in raw["polygons"]),
        horizontal_inches=raw["horizontal_inches"],
        vertical_inches=raw["vertical_inches"],
        z_inches=raw["z_inches"],
        range_inches=raw["range_inches"],
    )


def query_payload(query: MovementReachabilityQuery) -> MovementQueryPayload:
    return {
        "path_context": query.path_context.to_payload(),
        "terrain_context": query.terrain_context.to_payload(),
        "goal": goal_payload(query.goal),
        "required_goals": [goal_payload(g) for g in query.required_goals],
        "required_if_reachable_goals": [goal_payload(g) for g in query.required_if_reachable_goals],
        "forbidden_goals": [goal_payload(g) for g in query.forbidden_goals],
        "coherent_models": [m.to_payload() for m in query.coherent_models],
        "coherency_horizontal_inches": query.coherency_horizontal_inches,
        "coherency_vertical_inches": query.coherency_vertical_inches,
        "maximum_target_range_inches": query.maximum_target_range_inches,
        "coherency_neighbor_count": query.coherency_neighbor_count,
        "coherency_max_span_inches": query.coherency_max_span_inches,
        "coherency_all_models_distance_inches": query.coherency_all_models_distance_inches,
        "closer_target_groups": [
            [m.to_payload() for m in group] for group in query.closer_target_groups
        ],
    }


def query_from_payload(raw: MovementQueryPayload) -> MovementReachabilityQuery:
    if frozenset(raw) != MovementQueryPayload.__required_keys__:
        raise GeometryError("Movement query evidence fields drifted.")
    query = MovementReachabilityQuery(
        path_context=PathValidationContext.from_payload(raw["path_context"]),
        terrain_context=TerrainPathLegalityContext.from_payload(raw["terrain_context"]),
        goal=goal_from_payload(raw["goal"]),
        required_goals=tuple(goal_from_payload(g) for g in raw["required_goals"]),
        required_if_reachable_goals=tuple(
            goal_from_payload(g) for g in raw["required_if_reachable_goals"]
        ),
        forbidden_goals=tuple(goal_from_payload(g) for g in raw["forbidden_goals"]),
        coherent_models=tuple(Model.from_payload(m) for m in raw["coherent_models"]),
        coherency_horizontal_inches=raw["coherency_horizontal_inches"],
        coherency_vertical_inches=raw["coherency_vertical_inches"],
        maximum_target_range_inches=raw["maximum_target_range_inches"],
        coherency_neighbor_count=raw["coherency_neighbor_count"],
        coherency_max_span_inches=raw["coherency_max_span_inches"],
        coherency_all_models_distance_inches=raw["coherency_all_models_distance_inches"],
        closer_target_groups=tuple(
            tuple(Model.from_payload(m) for m in group) for group in raw["closer_target_groups"]
        ),
    )
    if query_payload(query) != raw:
        raise GeometryError("Movement query nested payload fields drifted.")
    return query
