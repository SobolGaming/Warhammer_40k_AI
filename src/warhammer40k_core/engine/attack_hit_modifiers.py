"""Source-preserving hit contributions shared by ordinary and Psychic attacks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.runtime_modifiers import (
        HitRollModifierBinding,
        HitRollModifierContext,
    )


def declaration_hit_modifiers(rule_ids: tuple[str, ...]) -> tuple[RollModifier, ...]:
    from warhammer40k_core.engine.shooting_targets import (
        BIG_GUNS_NEVER_TIRE_RULE_ID,
        FORTIFICATION_ENGAGEMENT_RULE_ID,
        STEALTH_RULE_ID,
    )
    from warhammer40k_core.engine.weapon_abilities import (
        INDIRECT_FIRE_NO_VISIBLE_RULE_ID,
        heavy_rule_id,
    )

    values = {
        INDIRECT_FIRE_NO_VISIBLE_RULE_ID: -1,
        STEALTH_RULE_ID: -1,
        BIG_GUNS_NEVER_TIRE_RULE_ID: -1,
        FORTIFICATION_ENGAGEMENT_RULE_ID: -1,
        heavy_rule_id(): 1,
    }
    return tuple(
        RollModifier(modifier_id=f"declaration:{source_id}", source_id=source_id, operand=value)
        for source_id, value in sorted(values.items())
        if source_id in rule_ids
    )


def registered_hit_roll_modifiers(
    context: HitRollModifierContext, bindings: tuple[HitRollModifierBinding, ...]
) -> tuple[RollModifier, ...]:
    from warhammer40k_core.engine.generic_rule_attack_hooks import generic_hit_roll_modifiers

    modifiers: list[RollModifier] = []
    for binding in bindings:
        value = binding.handler(context)
        if type(value) is not int:
            raise GameLifecycleError(f"{binding.modifier_id} returned a non-integer hit modifier.")
        if value:
            modifiers.append(RollModifier(binding.modifier_id, value, source_id=binding.source_id))
    modifiers.extend(generic_hit_roll_modifiers(context))
    if len({modifier.modifier_id for modifier in modifiers}) != len(modifiers):
        raise GameLifecycleError("Hit modifier identities must be unique.")
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))
