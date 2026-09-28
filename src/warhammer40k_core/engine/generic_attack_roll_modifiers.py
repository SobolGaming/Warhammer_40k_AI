"""Source-preserving generic attack roll contributions."""

from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.core.modifiers import RollModifier
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.generic_rule_effect_targets import GenericAttackEffect
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import (
    DamageRollModifierContext,
    WoundRollModifierContext,
)
from warhammer40k_core.rules.rule_ir import RuleEffectKind


def generic_wound_roll_modifiers(context: WoundRollModifierContext) -> tuple[RollModifier, ...]:
    # Extracted provider implementation shares its owning module's parameter decoder.
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        _required_int_parameter,  # pyright: ignore[reportPrivateUsage]
    )

    if type(context) is not WoundRollModifierContext:
        raise GameLifecycleError("Generic wound roll hooks require WoundRollModifierContext.")
    return _dice_roll_modifiers_for_attack(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        attack_strength=context.strength,
        target_toughness=context.toughness,
        expected_roll_type="wound",
        legacy_attacker_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            >= 0
        ),
        legacy_target_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            <= 0
        ),
    )


def generic_damage_roll_modifiers(context: DamageRollModifierContext) -> tuple[RollModifier, ...]:
    # Extracted provider implementation shares its owning module's parameter decoder.
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        _required_int_parameter,  # pyright: ignore[reportPrivateUsage]
    )

    if type(context) is not DamageRollModifierContext:
        raise GameLifecycleError("Generic damage roll hooks require DamageRollModifierContext.")
    return _dice_roll_modifiers_for_attack(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        expected_roll_type="damage",
        legacy_attacker_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            >= 0
        ),
        legacy_target_role_allowed=lambda effect: (
            _required_int_parameter(
                effect.parameters,
                key="delta",
            )
            <= 0
        ),
    )


def _dice_roll_modifiers_for_attack(
    *,
    state: object,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None,
    target_unit_instance_id: str,
    source_phase: object,
    expected_roll_type: str,
    legacy_attacker_role_allowed: Callable[[GenericAttackEffect], bool],
    legacy_target_role_allowed: Callable[[GenericAttackEffect], bool],
    weapon_profile: WeaponProfile | None = None,
    attack_strength: int | None = None,
    target_toughness: int | None = None,
) -> tuple[RollModifier, ...]:
    # Match the shared internal provider gates, as Hit/Critical Wound providers do.
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        _matching_generic_attack_effects,  # pyright: ignore[reportPrivateUsage]
        _required_int_parameter,  # pyright: ignore[reportPrivateUsage]
        _roll_type_matches,  # pyright: ignore[reportPrivateUsage]
    )

    modifiers: list[RollModifier] = []
    for effect in _matching_generic_attack_effects(
        state=state,
        attacking_unit_instance_id=attacking_unit_instance_id,
        attacker_model_instance_id=attacker_model_instance_id,
        target_unit_instance_id=target_unit_instance_id,
        source_phase=source_phase,
        attack_strength=attack_strength,
        target_toughness=target_toughness,
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        legacy_attacker_role_allowed=legacy_attacker_role_allowed,
        legacy_target_role_allowed=legacy_target_role_allowed,
        weapon_profile=weapon_profile,
    ):
        if not _roll_type_matches(effect.parameters, expected=expected_roll_type):
            continue
        modifiers.append(
            RollModifier(
                modifier_id=f"{effect.persisting_effect.effect_id}:{expected_roll_type}:{effect.effect_index}",
                source_id=effect.source_id,
                operand=_required_int_parameter(effect.parameters, key="delta"),
            )
        )
    return tuple(modifiers)
