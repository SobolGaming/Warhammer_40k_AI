from __future__ import annotations

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.generic_rule_attack_hooks import (
    generic_rule_unit_characteristic_modifiers,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import ObjectiveControlModifierContext


def generic_rule_modified_objective_control(
    context: ObjectiveControlModifierContext,
) -> int:
    return generic_rule_objective_control_trace(context)[0]


apply_generic_oc = generic_rule_modified_objective_control


def generic_rule_objective_control_trace(
    context: ObjectiveControlModifierContext,
) -> tuple[int, tuple[str, ...]]:
    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError(
            "Generic Objective Control hooks require ObjectiveControlModifierContext."
        )
    current = context.current_objective_control
    applied_effect_ids: list[str] = []
    for effect_id, delta in generic_rule_unit_characteristic_modifiers(
        state=context.state,
        unit_instance_id=context.unit_instance_id,
        characteristic=Characteristic.OBJECTIVE_CONTROL,
    ):
        modified = max(0, current + delta)
        if modified != current:
            applied_effect_ids.append(effect_id)
        current = modified
    return current, tuple(applied_effect_ids)


__all__ = (
    "apply_generic_oc",
    "generic_rule_modified_objective_control",
    "generic_rule_objective_control_trace",
)
