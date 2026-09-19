"""Source-neutral Surge target, eligibility and mandatory endpoint authority."""

from __future__ import annotations

from dataclasses import replace
from math import isclose
from typing import TYPE_CHECKING

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.phase_movement_history import current_unit_moves
from warhammer40k_core.engine.physical_engagement import (
    physical_geometry_models_for_rules_unit,
    scenario_physical_enemy_rules_unit_ids,
    scenario_physically_engaged_enemy_rules_unit_ids,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id, rules_unit_view_from_armies
from warhammer40k_core.geometry.movement_reachability import (
    MovementGoal,
    MovementReachabilityQuery,
    MovementReachabilityStatus,
    movement_reachability,
)
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_surge_2026_09 import (
    SURGE_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def closest_surge_targets(
    *, scenario: BattlefieldScenario, unit_instance_id: str
) -> tuple[str, ...]:
    view = rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=unit_instance_id)
    source = physical_geometry_models_for_rules_unit(
        scenario=scenario, unit_instance_id=view.unit_instance_id
    )
    distances: dict[str, float] = {}
    for enemy_id in scenario_physical_enemy_rules_unit_ids(
        scenario=scenario, unit_instance_id=view.unit_instance_id
    ):
        enemy = rules_unit_view_from_armies(armies=scenario.armies, unit_instance_id=enemy_id)
        if "AIRCRAFT" in enemy.keywords and "FLY" not in view.keywords:
            continue
        targets = physical_geometry_models_for_rules_unit(
            scenario=scenario, unit_instance_id=enemy_id
        )
        if source and targets:
            distances[enemy_id] = min(
                model.range_to(target) for model in source for target in targets
            )
    if not distances:
        return ()
    closest = min(distances.values())
    return tuple(
        sorted(
            key
            for key, distance in distances.items()
            if isclose(distance, closest, rel_tol=0.0, abs_tol=1e-9)
        )
    )


def surge_ineligibility(state: GameState, unit_instance_id: str) -> str | None:
    from warhammer40k_core.engine.battlefield_presence import rules_unit_has_placed_alive_model

    view = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if not rules_unit_has_placed_alive_model(state=state, rules_unit=view):
        return "surge_source_not_on_battlefield"
    if {view.unit_instance_id, *view.component_unit_instance_ids}.intersection(
        state.battle_shocked_unit_ids
    ):
        return "battle_shocked_surge_forbidden"
    if current_unit_moves(state, view.unit_instance_id):
        return "surge_prior_move_this_phase"
    scenario = battlefield_scenario_for_state(state=state)
    if scenario_physically_engaged_enemy_rules_unit_ids(
        scenario=scenario,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_instance_id=view.unit_instance_id,
    ):
        return "engagement_range_surge_forbidden"
    if not closest_surge_targets(scenario=scenario, unit_instance_id=view.unit_instance_id):
        return "surge_has_no_target"
    return None


def validate_surge_target(
    *, scenario: BattlefieldScenario, unit_instance_id: str, target_id: str | None
) -> str:
    targets = closest_surge_targets(scenario=scenario, unit_instance_id=unit_instance_id)
    if target_id is None and len(targets) == 1:
        return targets[0]
    if target_id not in targets:
        raise GameLifecycleError(
            "Surge requires a committed closest enemy target; ties require a finite choice."
        )
    assert target_id is not None
    return target_id


def surge_endpoint_evidence(
    *,
    query: MovementReachabilityQuery,
    endpoint: Model,
    target_id: str,
    component_unit_instance_id: str,
    ruleset: RulesetDescriptor,
) -> tuple[dict[str, JsonValue], str | None]:
    """Never treat the bounded search's failure as proof of maximal approach."""
    source = query.path_context.moving_model
    targets = query.goal.models
    budget = query.path_context.movement_distance_budget_inches
    if budget is None or not targets:
        raise GameLifecycleError("Surge endpoint query requires targets and a movement budget.")
    distance = min(endpoint.range_to(target) for target in targets)
    row: dict[str, JsonValue] = {
        "source_rule_id": SURGE_SOURCE_ID,
        "model_instance_id": source.model_id,
        "component_unit_instance_id": component_unit_instance_id,
        "target_unit_instance_id": target_id,
        "distance_before_inches": min(source.range_to(target) for target in targets),
        "distance_after_inches": distance,
        "engagement_status": "not_evaluated",
        "approach_status": "not_evaluated",
        "alternative_witness": None,
    }
    if any(goal.contains(endpoint) for goal in query.forbidden_goals):
        return row, "surge_non_target_engagement"
    if query.goal.contains(endpoint):
        row["engagement_status"] = "satisfied"
        row["approach_status"] = "not_required"
        return row, None
    engagement = movement_reachability(query)
    row["engagement_status"] = engagement.status.value
    if engagement.witness is not None:
        row["alternative_witness"] = validate_json_value(engagement.witness.to_payload())
        return row, "surge_engagement_not_reached"
    if engagement.status is MovementReachabilityStatus.UNRESOLVED:
        return row, "surge_reachability_unresolved"
    # A containing disk and the translation budget give a global lower bound,
    # valid for every path, rotation, obstacle and coherency constraint. A legal
    # submitted endpoint meeting that bound proves optimality directly.
    contact = MovementGoal(models=targets, range_inches=0.0)
    lower = max(0.0, contact.distance_lower_bound(source, ignores_vertical_distance=False) - budget)
    row["distance_lower_bound_inches"] = lower
    if distance <= lower + 1e-8:
        row["approach_status"] = "optimal_bound"
        return row, None
    better = movement_reachability(
        replace(
            query,
            goal=MovementGoal(models=targets, range_inches=distance),
            maximum_target_range_inches=distance,
        )
    )
    row["approach_status"] = better.status.value
    if better.witness is not None:
        row["alternative_witness"] = validate_json_value(better.witness.to_payload())
        return row, "surge_maximum_approach_not_reached"
    return row, "surge_reachability_unresolved"
