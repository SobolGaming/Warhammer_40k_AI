"""Compose the retained instruction through the existing generic Stratagem and move owners."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.movement_budget_modifiers import (
    MovementBudgetModifierContext,
    model_movement_characteristic,
)
from warhammer40k_core.engine.objective_geometry import (
    ObjectiveGeometry,
    measure_rules_unit_to_objective,
)
from warhammer40k_core.engine.objective_geometry_sources import mission_objective_geometries
from warhammer40k_core.engine.objective_movement_constraint import ObjectiveMovementConstraint
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.rules.rule_ir import parameter_payload
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_objective_movement_consumer_2026_10 as source,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
    from warhammer40k_core.engine.stratagems import StratagemCatalogRecord


def objective_movement_consumer_record(record: StratagemCatalogRecord) -> StratagemCatalogRecord:
    if record.definition.source_id != source.SOURCE_ID:
        return record
    return replace(
        record,
        definition=replace(
            record.definition,
            target_spec=replace(
                record.definition.target_spec, required_keywords=(source.REQUIRED_NAME_KEYWORD,)
            ),
            effect_payload={
                "rule_ir": validate_json_value(source.RULE_IR.to_payload()),
                "requires_opponent_turn": True,
                "target_forbidden_if_within_engagement_range": True,
                "requires_objective_marker": True,
            },
        ),
    )


def objective_constraint_for_effect(
    *,
    state: GameState,
    unit_instance_id: str,
    effect_payload: dict[str, JsonValue],
    runtime_modifiers: RuntimeModifierRegistry | None,
) -> ObjectiveMovementConstraint | None:
    raw_effect = effect_payload.get("effect")
    if not isinstance(raw_effect, dict):
        raise GameLifecycleError("Objective move requires a structured RuleIR effect.")
    from typing import cast

    from warhammer40k_core.rules.rule_ir import RuleEffectSpec, RuleEffectSpecPayload

    parameters = parameter_payload(
        RuleEffectSpec.from_payload(cast(RuleEffectSpecPayload, raw_effect)).parameters
    )
    if parameters.get("endpoint_constraint") is None:
        return None
    if (
        parameters.get("endpoint_constraint") != "closest_legal_objective"
        or parameters.get("objective_selection") != "closest_marker"
        or parameters.get("distance_kind") != "normal_move_characteristic"
        or runtime_modifiers is None
    ):
        raise GameLifecycleError("Objective Normal move constraint semantics are incomplete.")
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    scenario = battlefield_scenario_for_state(state=state)
    distances: list[tuple[float, ObjectiveGeometry]] = []
    for objective in mission_objective_geometries(state):
        if objective.marker is None:
            continue
        measurements = measure_rules_unit_to_objective(
            scenario=scenario, rules_unit=unit, objective=objective
        )
        if measurements:
            distances.append(
                (min(row.distance.closest_distance_inches for row in measurements), objective)
            )
    if not distances:
        raise GameLifecycleError("Objective Normal move requires a placed unit and mission marker.")
    minimum = min(distance for distance, _ in distances)
    budgets = tuple(
        (
            model.model_instance_id,
            runtime_modifiers.modified_movement_inches(
                MovementBudgetModifierContext(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_instance_id,
                    movement=model_movement_characteristic(model),
                )
            ),
        )
        for model in unit.alive_models()
        if state.battlefield_state is not None
        and state.battlefield_state.model_placement_or_none(model.model_instance_id) is not None
    )
    if not budgets:
        raise GameLifecycleError("Objective Normal move requires physical model budgets.")
    return ObjectiveMovementConstraint(
        objectives=tuple(
            objective for distance, objective in distances if distance <= minimum + 1e-9
        ),
        movement_budgets=budgets,
    )
