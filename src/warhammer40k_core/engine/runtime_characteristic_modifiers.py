from __future__ import annotations

from collections.abc import Iterable
from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierOperation,
    ModifierStack,
    ModifierTerm,
    resolve_characteristic_value,
)
from warhammer40k_core.engine.effects import GENERIC_RULE_EFFECT_KIND
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.runtime_modifiers import (
        ObjectiveControlModifierBinding,
        ObjectiveControlModifierContext,
        UnitCharacteristicModifierBinding,
        UnitCharacteristicModifierContext,
    )


def bind_characteristic_terms(
    *,
    modifier_id: str,
    source_id: str,
    characteristic: Characteristic,
    terms: tuple[ModifierTerm, ...],
) -> tuple[Modifier, ...]:
    if type(terms) is not tuple or any(type(term) is not ModifierTerm for term in terms):
        raise GameLifecycleError("Characteristic handlers must return typed modifier terms.")
    return tuple(
        term.bind(
            modifier_id=modifier_id if index == 0 else f"{modifier_id}:operation:{index}",
            source_id=source_id,
            characteristic=characteristic,
        )
        for index, term in enumerate(terms)
    )


def runtime_characteristic_operations(
    *,
    context: UnitCharacteristicModifierContext,
    bindings: Iterable[UnitCharacteristicModifierBinding] = (),
) -> tuple[Modifier, ...]:
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_rule_characteristic_operations,
    )
    from warhammer40k_core.engine.runtime_modifiers import UnitCharacteristicModifierContext

    if type(context) is not UnitCharacteristicModifierContext:
        raise GameLifecycleError("Unit characteristic modifiers require a context.")
    modifiers = [
        modifier
        for binding in bindings
        for modifier in bind_characteristic_terms(
            modifier_id=binding.modifier_id,
            source_id=binding.source_id,
            characteristic=context.characteristic,
            terms=binding.handler(context),
        )
    ]
    modifiers.extend(
        generic_rule_characteristic_operations(
            state=context.state,
            unit_instance_id=context.unit_instance_id,
            characteristic=context.characteristic,
            model_instance_id=context.model_instance_id,
        )
    )
    return tuple(modifiers)


def resolve_runtime_characteristic(
    *,
    context: UnitCharacteristicModifierContext,
    bindings: Iterable[UnitCharacteristicModifierBinding] = (),
    selected_modifiers: tuple[Modifier, ...] | None = None,
) -> CharacteristicValue:
    modifiers = _selected_operations(
        runtime_characteristic_operations(context=context, bindings=bindings), selected_modifiers
    )
    resolved = ModifierStack(
        characteristic=context.characteristic,
        raw_value=context.current_value,
        modifiers=tuple(modifiers),
        target_id=context.unit_instance_id,
    ).resolve()
    if not resolved.is_numeric:
        raise GameLifecycleError(
            "Unit characteristic numeric consumption cannot use a symbolic replacement."
        )
    return resolved


def runtime_objective_control_operations(
    *,
    context: ObjectiveControlModifierContext,
    value: CharacteristicValue,
    bindings: Iterable[ObjectiveControlModifierBinding] = (),
) -> tuple[Modifier, ...]:
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        generic_rule_characteristic_operations,
    )
    from warhammer40k_core.engine.runtime_modifiers import ObjectiveControlModifierContext

    if type(context) is not ObjectiveControlModifierContext:
        raise GameLifecycleError("Objective Control modifiers require a context.")
    if (
        type(value) is not CharacteristicValue
        or value.characteristic is not Characteristic.OBJECTIVE_CONTROL
    ):
        raise GameLifecycleError("Objective Control resolution requires its typed characteristic.")
    if value.final != context.current_objective_control:
        raise GameLifecycleError("Objective Control characteristic context drifted.")
    modifiers: list[Modifier] = []
    for binding in bindings:
        operations = bind_characteristic_terms(
            modifier_id=binding.modifier_id,
            source_id=binding.source_id,
            characteristic=Characteristic.OBJECTIVE_CONTROL,
            terms=binding.handler(context),
        )
        modifiers.extend(operations)
    # Other effect families cannot supply generic characteristic operations.
    # Avoid rebuilding attached-unit applicability when no generic rules exist.
    if any(
        isinstance(effect.effect_payload, dict)
        and effect.effect_payload.get("effect_kind") == GENERIC_RULE_EFFECT_KIND
        for effect in context.state.persisting_effects
    ):
        modifiers.extend(
            generic_rule_characteristic_operations(
                state=context.state,
                unit_instance_id=context.unit_instance_id,
                characteristic=Characteristic.OBJECTIVE_CONTROL,
                model_instance_id=context.model_instance_id,
            )
        )
    return tuple(modifiers)


def resolve_runtime_objective_control(
    *,
    context: ObjectiveControlModifierContext,
    value: CharacteristicValue,
    bindings: Iterable[ObjectiveControlModifierBinding] = (),
    selected_modifiers: tuple[Modifier, ...] | None = None,
) -> CharacteristicValue:
    binding_tuple = tuple(bindings)
    modifiers = _selected_operations(
        runtime_objective_control_operations(context=context, value=value, bindings=binding_tuple),
        selected_modifiers,
    )
    if not modifiers:
        return value
    if value.modifier_trace is not None:
        from warhammer40k_core.core.profile_modifier_trace import CharacteristicModifierTrace

        trace = value.modifier_trace
        return CharacteristicModifierTrace(
            characteristic=trace.characteristic,
            source_value=trace.source_value,
            modifiers=(*trace.modifiers, *modifiers),
            bounded=trace.bounded,
            ignored_modifier_ids=trace.ignored_modifier_ids,
        ).value()
    origin_ids = {
        operation.modifier_id: binding.modifier_id
        for operation in modifiers
        for binding in binding_tuple
        if operation.modifier_id == binding.modifier_id
        or operation.modifier_id.startswith(f"{binding.modifier_id}:operation:")
    }
    resolved = resolve_characteristic_value(
        replace(value, raw=value.final),
        modifiers,
        target_id=context.model_instance_id,
    )
    has_replacement = any(
        modifier.operation
        in {ModifierOperation.SET, ModifierOperation.SET_DASH, ModifierOperation.SET_STAR}
        and modifier.modifier_id in resolved.applied_modifier_ids
        for modifier in modifiers
    )
    return replace(
        resolved,
        raw=value.raw if resolved.is_numeric else 0,
        base=resolved.base if has_replacement else value.base,
        applied_modifier_ids=tuple(
            sorted(
                {
                    *value.applied_modifier_ids,
                    *(
                        origin_ids.get(identifier, identifier)
                        for identifier in resolved.applied_modifier_ids
                    ),
                }
            )
        ),
    )


def _selected_operations(
    available: tuple[Modifier, ...], selected: tuple[Modifier, ...] | None
) -> tuple[Modifier, ...]:
    if selected is None:
        return available
    if (
        type(selected) is not tuple
        or tuple(item for item in available if item in selected) != selected
    ):
        raise GameLifecycleError("Selected characteristic operations differ from source inventory.")
    return selected
