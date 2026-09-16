"""Per-model Surge obligations using shared full-path feasibility queries."""

from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    ModelPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.charge_movement_source import ChargePlacement
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
    scenario_physical_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.surge_movement import surge_endpoint_evidence
from warhammer40k_core.geometry.movement_reachability import MovementGoal, MovementReachabilityQuery
from warhammer40k_core.geometry.pathing import PathValidationContext, TerrainPathLegalityContext
from warhammer40k_core.geometry.volume import Model


def validate_surge_endpoints(
    *,
    scenario: BattlefieldScenario,
    ruleset: RulesetDescriptor,
    unit_instance_id: str,
    target_id: str,
    attempted: ChargePlacement,
    contexts: tuple[tuple[ModelPlacement, PathValidationContext, TerrainPathLegalityContext], ...],
) -> tuple[list[JsonValue], tuple[str, ...]]:
    endpoints = {
        model.model_instance_id: geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model), placement=model
        )
        for model in attempted.model_placements
        if scenario.model_instance_for_placement(model).is_alive
    }
    targets = physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=target_id)
    engagement = ruleset.engagement_policy

    def goal(models: tuple[Model, ...]) -> MovementGoal:
        return MovementGoal(
            models=models,
            horizontal_inches=engagement.horizontal_inches,
            vertical_inches=engagement.vertical_inches,
        )

    forbidden = tuple(
        goal(physical_geometry_models_for_rules_unit(scenario=scenario, unit_instance_id=enemy))
        for enemy in scenario_physical_enemy_rules_unit_ids(
            scenario=scenario, unit_instance_id=unit_instance_id
        )
        if enemy != target_id
    )
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
            goal=goal(targets),
            forbidden_goals=forbidden,
            coherent_models=tuple(
                model for key, model in endpoints.items() if key != placement.model_instance_id
            ),
            coherency_neighbor_count=1 if neighbors is None else neighbors,
            coherency_horizontal_inches=(
                0.0 if policy.max_horizontal_inches is None else policy.max_horizontal_inches
            ),
            coherency_vertical_inches=(
                0.0 if policy.max_vertical_inches is None else policy.max_vertical_inches
            ),
            coherency_max_span_inches=policy.max_unit_span_inches,
            coherency_all_models_distance_inches=policy.max_all_models_distance_inches,
        )
        row, code = surge_endpoint_evidence(
            query=query,
            endpoint=endpoints[placement.model_instance_id],
            target_id=target_id,
            component_unit_instance_id=placement.unit_instance_id,
            ruleset=ruleset,
        )
        rows.append(row)
        if code is not None:
            codes.append(code)
    return rows, tuple(dict.fromkeys(codes))
