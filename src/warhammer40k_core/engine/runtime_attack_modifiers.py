"""Registered attack operations retain their provider identities until resolution."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.allocated_attack_damage_modifiers import (
        AllocatedAttackDamageModifierBinding,
        AllocatedAttackDamageModifierContext,
    )
    from warhammer40k_core.engine.runtime_modifiers import (
        DamageRollModifierBinding,
        DamageRollModifierContext,
        WoundRollModifierBinding,
        WoundRollModifierContext,
    )


def registered_wound_roll_modifiers(
    context: WoundRollModifierContext, bindings: tuple[WoundRollModifierBinding, ...]
) -> tuple[RollModifier, ...]:
    from warhammer40k_core.engine.generic_attack_roll_modifiers import generic_wound_roll_modifiers

    return _validated_inventory(
        tuple(
            RollModifier(binding.modifier_id, value, source_id=binding.source_id)
            for binding in bindings
            if (value := _value(binding.handler(context), binding.modifier_id)) != 0
        )
        + generic_wound_roll_modifiers(context)
    )


def registered_damage_roll_modifiers(
    context: DamageRollModifierContext, bindings: tuple[DamageRollModifierBinding, ...]
) -> tuple[RollModifier, ...]:
    from warhammer40k_core.engine.generic_attack_roll_modifiers import generic_damage_roll_modifiers

    return _validated_inventory(
        tuple(
            RollModifier(binding.modifier_id, value, source_id=binding.source_id)
            for binding in bindings
            if (value := _value(binding.handler(context), binding.modifier_id)) != 0
        )
        + generic_damage_roll_modifiers(context)
    )


def registered_allocated_attack_damage_modifiers(
    context: AllocatedAttackDamageModifierContext,
    bindings: tuple[AllocatedAttackDamageModifierBinding, ...],
) -> tuple[RollModifier, ...]:
    return _validated_inventory(
        tuple(
            RollModifier(binding.modifier_id, value, source_id=binding.source_id)
            for binding in bindings
            if (value := _value(binding.handler(context), binding.modifier_id)) != 0
        )
    )


def _value(value: int, modifier_id: str) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{modifier_id} returned a non-integer attack modifier.")
    return value


def _validated_inventory(modifiers: tuple[RollModifier, ...]) -> tuple[RollModifier, ...]:
    if len({modifier.modifier_id for modifier in modifiers}) != len(modifiers):
        raise GameLifecycleError("Attack modifier identities must be unique.")
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))
