"""Engine-owned Leadership evaluation before a model or rules-unit test."""

from __future__ import annotations

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.battle_shock import battle_shock_leadership_target_for_rules_unit
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.random_profile_evaluation import evaluate_unit_profile_characteristics
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    RuntimeModifierRegistry,
    UnitCharacteristicModifierContext,
)
from warhammer40k_core.engine.unit_factory import ModelInstance


def evaluate_leadership_test_target(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    scope_id: str,
    model_instance_id: str | None,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> int:
    evaluate_unit_profile_characteristics(
        state=state,
        decisions=decisions,
        unit_instance_id=unit_instance_id,
        scope_id=scope_id,
        characteristics=(Characteristic.LEADERSHIP,),
        model_instance_ids=None if model_instance_id is None else (model_instance_id,),
    )
    unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    if model_instance_id is None:
        return battle_shock_leadership_target_for_rules_unit(
            unit,
            current_model_ids=tuple(model.model_instance_id for model in unit.alive_models()),
            ability_index=ability_index,
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    source = leadership_for_model(unit.model_by_id(model_instance_id))
    return runtime_modifier_registry.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=unit_instance_id,
            characteristic=Characteristic.LEADERSHIP,
            base_value=source,
            current_value=source,
        )
    )


def leadership_for_model(model: ModelInstance) -> int:
    for value in model.characteristics:
        if value.characteristic is Characteristic.LEADERSHIP:
            return value.final
    raise GameLifecycleError("Test source model is missing Leadership.")
