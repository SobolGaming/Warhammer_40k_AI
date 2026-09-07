from __future__ import annotations

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_characteristic_modifiers import (
    resolve_runtime_objective_control,
)
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
    resolved = resolve_runtime_objective_control(
        context=context,
        value=CharacteristicValue.from_raw(
            Characteristic.OBJECTIVE_CONTROL, context.current_objective_control
        ),
    )
    return resolved.final, resolved.applied_modifier_ids


__all__ = (
    "apply_generic_oc",
    "generic_rule_modified_objective_control",
    "generic_rule_objective_control_trace",
)
