from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import CharacteristicValue
from warhammer40k_core.engine.generic_rule_objective_control import (
    generic_rule_objective_control_trace,
)
from warhammer40k_core.engine.objective_control import model_objective_control_characteristic
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.unit_factory import ModelInstance

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def resolve_checkpoint_objective_control(
    *,
    state: GameState,
    unit_instance_id: str,
    model: ModelInstance,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> CharacteristicValue:
    source = model_objective_control_characteristic(model, battle_shocked=False)
    context = ObjectiveControlModifierContext(
        state=state,
        unit_instance_id=unit_instance_id,
        model_instance_id=model.model_instance_id,
        base_objective_control=source.final,
        current_objective_control=source.final,
    )
    runtime_value, runtime_ids = runtime_modifier_registry.objective_control_binding_trace(context)
    resolved_value, effect_ids = generic_rule_objective_control_trace(
        replace(context, current_objective_control=runtime_value)
    )
    return replace(
        source,
        final=resolved_value,
        applied_modifier_ids=tuple(
            sorted({*source.applied_modifier_ids, *runtime_ids, *effect_ids})
        ),
    )


__all__ = ("resolve_checkpoint_objective_control",)
