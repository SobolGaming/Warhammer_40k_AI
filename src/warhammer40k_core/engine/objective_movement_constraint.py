"""Source-backed objective approach, distinct from Objective Consolidation's closer fallback."""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import isfinite
from typing import TYPE_CHECKING, TypedDict, cast

from warhammer40k_core.core.objectives import ObjectiveMarker, ObjectiveMarkerPayload
from warhammer40k_core.engine.battlefield_state import ModelPlacement, geometry_model_for_placement
from warhammer40k_core.engine.decision_request import DecisionOption
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_model_to_objective,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.pathing import PathValidationContext, TerrainPathLegalityContext
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
    from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
    from warhammer40k_core.engine.charge_movement_source import ChargePlacement

OBJECTIVE_APPROACH_SOURCE_ID = "rule:01:01.04.03:1"
OBJECTIVE_APPROACH_CHOICE_KEY = "objective_approach_id"


class ObjectiveMovementConstraintPayload(TypedDict):
    source_rule_id: str
    objectives: list[dict[str, JsonValue]]
    movement_budgets: dict[str, float]


@dataclass(frozen=True, slots=True)
class ObjectiveMovementConstraint:
    """Frozen eligible objectives; one finite choice commits the unit's objective."""

    objectives: tuple[ObjectiveGeometry, ...]
    source_rule_id: str = OBJECTIVE_APPROACH_SOURCE_ID
    movement_budgets: tuple[tuple[str, float], ...] = ()

    def __post_init__(self) -> None:
        if self.source_rule_id != OBJECTIVE_APPROACH_SOURCE_ID:
            raise GameLifecycleError("Objective approach definition source drift.")
        if (
            type(self.objectives) is not tuple
            or not self.objectives
            or any(type(item) is not ObjectiveGeometry for item in self.objectives)
            or len({item.objective_id for item in self.objectives}) != len(self.objectives)
        ):
            raise GameLifecycleError("Objective approach requires unique typed objective geometry.")

        if type(self.movement_budgets) is not tuple or any(
            type(row) is not tuple or len(row) != 2 for row in self.movement_budgets
        ):
            raise GameLifecycleError("Objective approach movement budgets are malformed.")
        if any(
            type(key) is not str
            or not key.strip()
            or type(value) not in {int, float}
            or not isfinite(value)
            or value < 0
            for key, value in self.movement_budgets
        ) or len(dict(self.movement_budgets)) != len(self.movement_budgets):
            raise GameLifecycleError("Objective approach movement budgets are malformed.")

    def to_payload(self) -> ObjectiveMovementConstraintPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "movement_budgets": dict(self.movement_budgets),
            "objectives": [
                {
                    "objective_id": item.objective_id,
                    "marker": None
                    if item.marker is None
                    else validate_json_value(item.marker.to_payload()),
                    "footprint_polygons": [
                        [{"x": p[0], "y": p[1]} for p in polygon]
                        for polygon in item.footprint_polygons
                    ],
                }
                for item in self.objectives
            ],
        }

    @classmethod
    def from_payload(
        cls, payload: ObjectiveMovementConstraintPayload
    ) -> ObjectiveMovementConstraint:
        if (
            set(payload) != {"source_rule_id", "objectives", "movement_budgets"}
            or type(payload["objectives"]) is not list
        ):
            raise GameLifecycleError("Objective approach payload schema drift.")
        items: list[ObjectiveGeometry] = []
        for row in payload["objectives"]:
            if type(row) is not dict or set(row) != {
                "objective_id",
                "marker",
                "footprint_polygons",
            }:
                raise GameLifecycleError("Objective approach geometry schema drift.")
            polygons = row["footprint_polygons"]
            if not isinstance(polygons, list) or not isinstance(row["objective_id"], str):
                raise GameLifecycleError("Objective approach geometry is malformed.")
            points: list[tuple[tuple[float, float], ...]] = []
            for polygon in polygons:
                if not isinstance(polygon, list):
                    raise GameLifecycleError("Objective approach polygon is malformed.")
                vertices: list[tuple[float, float]] = []
                for point in polygon:
                    if not isinstance(point, dict) or set(point) != {"x", "y"}:
                        raise GameLifecycleError("Objective approach vertex is malformed.")
                    if type(point["x"]) not in {int, float} or type(point["y"]) not in {int, float}:
                        raise GameLifecycleError(
                            "Objective approach vertex coordinates are malformed."
                        )
                    vertices.append((cast(float, point["x"]), cast(float, point["y"])))
                points.append(tuple(vertices))
            marker = row["marker"]
            if marker is not None and not isinstance(marker, dict):
                raise GameLifecycleError("Objective approach marker is malformed.")
            items.append(
                ObjectiveGeometry(
                    objective_id=row["objective_id"],
                    marker=None
                    if marker is None
                    else ObjectiveMarker.from_payload(cast(ObjectiveMarkerPayload, marker)),
                    footprint_polygons=tuple(points),
                )
            )
        if type(payload["movement_budgets"]) is not dict:
            raise GameLifecycleError("Objective approach budgets must be an object.")
        return cls(
            objectives=tuple(items),
            source_rule_id=payload["source_rule_id"],
            movement_budgets=tuple(payload["movement_budgets"].items()),
        )

    def objective(self, selected_id: str | None) -> ObjectiveGeometry:
        if selected_id is None and len(self.objectives) == 1:
            return self.objectives[0]
        for item in self.objectives:
            if item.objective_id == selected_id:
                return item
        raise GameLifecycleError(
            "Objective approach requires its committed finite objective choice."
        )


def objective_approach_options(
    *, constraint: ObjectiveMovementConstraint, options: tuple[DecisionOption, ...]
) -> tuple[DecisionOption, ...]:
    variants: list[DecisionOption] = []
    for option in options:
        if not isinstance(option.payload, dict) or option.payload.get("declined"):
            variants.append(option)
            continue
        for objective in constraint.objectives:
            variants.append(
                replace(
                    option,
                    option_id=f"{option.option_id}:objective:{objective.objective_id}",
                    label=f"{option.label} towards {objective.objective_id}",
                    payload={
                        **option.payload,
                        OBJECTIVE_APPROACH_CHOICE_KEY: objective.objective_id,
                    },
                )
            )
    return tuple(variants)


def objective_approach_choice(
    payload: JsonValue, constraint: ObjectiveMovementConstraint | None
) -> str | None:
    if constraint is None:
        return None
    if not isinstance(payload, dict):
        raise GameLifecycleError("Objective approach choice requires an object.")
    selected = payload.get(OBJECTIVE_APPROACH_CHOICE_KEY)
    if not isinstance(selected, str):
        raise GameLifecycleError("Objective approach choice requires an objective identity.")
    return constraint.objective(selected).objective_id


def objective_approach_context(
    payload: JsonValue, constraint: ObjectiveMovementConstraint | None
) -> dict[str, JsonValue]:
    selected = objective_approach_choice(payload, constraint)
    return {} if selected is None else {OBJECTIVE_APPROACH_CHOICE_KEY: selected}


def objective_goal(objective: ObjectiveGeometry) -> MovementGoal:
    marker = objective.marker
    if marker is None:
        return MovementGoal(polygons=objective.footprint_polygons, vertical_inches=5.0)
    return MovementGoal(
        disk=(
            Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
            CircularBase(radius=marker.marker_diameter_inches / 2),
        ),
        horizontal_inches=marker.control_horizontal_inches,
        vertical_inches=marker.control_vertical_inches,
    )


def validate_objective_approach_endpoints(
    *,
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    constraint: ObjectiveMovementConstraint,
    selected_id: str | None,
    attempted: ChargePlacement,
    contexts: tuple[tuple[ModelPlacement, PathValidationContext, TerrainPathLegalityContext], ...],
) -> tuple[list[JsonValue], tuple[str, ...]]:
    objective = constraint.objective(selected_id)
    endpoints = {
        row.model_instance_id: geometry_model_for_placement(
            model=scenario.model_instance_for_placement(row), placement=row
        )
        for row in attempted.model_placements
        if scenario.model_instance_for_placement(row).is_alive
    }
    policy = ruleset.coherency_policy
    neighbors = policy.required_neighbors_small_unit
    if (
        policy.large_unit_model_count_threshold is not None
        and len(endpoints) >= policy.large_unit_model_count_threshold
    ):
        neighbors = policy.required_neighbors_large_unit
    rows: list[JsonValue] = []
    codes: list[str] = []
    for placement, path_context, terrain_context in contexts:
        query = MovementReachabilityQuery(
            path_context=path_context,
            terrain_context=terrain_context,
            goal=objective_goal(objective),
            coherent_models=tuple(
                model for key, model in endpoints.items() if key != placement.model_instance_id
            ),
            coherency_neighbor_count=1 if neighbors is None else neighbors,
            coherency_horizontal_inches=0.0
            if policy.max_horizontal_inches is None
            else policy.max_horizontal_inches,
            coherency_vertical_inches=0.0
            if policy.max_vertical_inches is None
            else policy.max_vertical_inches,
            coherency_max_span_inches=policy.max_unit_span_inches,
            coherency_all_models_distance_inches=policy.max_all_models_distance_inches,
            prove_coherent_endpoint_exclusion=True,
        )
        row, code = objective_endpoint_evidence(
            query=query, endpoint=endpoints[placement.model_instance_id], objective=objective
        )
        rows.append(row)
        if code is not None:
            codes.append(code)
    return rows, tuple(dict.fromkeys(codes))


def objective_endpoint_evidence(
    *,
    query: MovementReachabilityQuery,
    endpoint: Model,
    objective: ObjectiveGeometry,
) -> tuple[dict[str, JsonValue], str | None]:
    source = query.path_context.moving_model
    distance = measure_model_to_objective(model=endpoint, objective=objective)
    before = measure_model_to_objective(model=source, objective=objective)
    row: dict[str, JsonValue] = {
        "source_rule_id": OBJECTIVE_APPROACH_SOURCE_ID,
        "model_instance_id": source.model_id,
        "objective_id": objective.objective_id,
        "distance_before_inches": before.closest_distance_inches,
        "distance_after_inches": distance.closest_distance_inches,
        "range_status": "satisfied" if distance.within_control_range else "not_evaluated",
        "approach_status": "not_required",
        "alternative_witness": None,
    }
    if distance.within_control_range:
        return row, None
    if before.within_control_range:
        row["range_status"] = "already_in_range"
        return row, "objective_approach_range_not_reached"
    reachable = movement_reachability(query)
    row["range_status"] = reachable.status.value
    if reachable.witness is not None:
        row["alternative_witness"] = validate_json_value(reachable.witness.to_payload())
        return row, "objective_approach_range_not_reached"
    if reachable.status is MovementReachabilityStatus.UNRESOLVED:
        return row, "objective_approach_unresolved"
    budget = query.path_context.movement_distance_budget_inches
    if budget is None:
        raise GameLifecycleError("Objective approach requires a movement budget.")
    physical_goal = replace(query.goal, horizontal_inches=0.0, vertical_inches=0.0)
    lower = (
        before.closest_distance_inches
        if query.path_context.pose_is_fixed
        else max(
            0.0,
            physical_goal.distance_lower_bound(
                source, ignores_vertical_distance=query.path_context.ignores_vertical_distance
            )
            - budget,
        )
    )
    row["distance_lower_bound_inches"] = lower
    if distance.closest_distance_inches <= lower + 1e-8:
        row["approach_status"] = "optimal_bound"
        return row, None
    # A witnessed alternative is a rejection. Search exhaustion never certifies optimality.
    better = movement_reachability(
        replace(
            query,
            goal=replace(
                physical_goal,
                spatial_region_range_inches=max(0.0, distance.closest_distance_inches - 1e-8),
                horizontal_inches=max(0.0, distance.closest_distance_inches - 1e-8),
                vertical_inches=max(0.0, distance.closest_distance_inches - 1e-8),
            ),
        )
    )
    row["approach_status"] = better.status.value
    if better.witness is not None:
        row["alternative_witness"] = validate_json_value(better.witness.to_payload())
        return row, "objective_approach_closest_endpoint_not_reached"
    if better.status in {
        MovementReachabilityStatus.UNREACHABLE,
        MovementReachabilityStatus.ENDPOINT_UNREACHABLE,
    }:
        return row, None
    return row, "objective_approach_unresolved"
