"""Generic save operations preserve their individual source identities."""

from __future__ import annotations

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.generic_rule_effect_targets import GenericAttackEffect
from warhammer40k_core.engine.generic_rule_save_modifiers import (
    generic_rule_save_option_with_roll_modifier,
    generic_rule_save_options_with_invulnerable_save,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.runtime_modifiers import SaveOptionModifierContext
from warhammer40k_core.engine.saves import SaveOption, save_option_with_armor_penetration_modifier
from warhammer40k_core.rules.rule_ir import RuleEffectKind, RuleTargetKind


def generic_rule_modified_save_options(
    context: SaveOptionModifierContext,
) -> tuple[SaveOption, ...]:
    # Extracted save provider retains the same internal gates and parameter decoders.
    from warhammer40k_core.engine.generic_rule_attack_hooks import (
        _characteristic_parameter,  # pyright: ignore[reportPrivateUsage]
        _matching_generic_attack_effects,  # pyright: ignore[reportPrivateUsage]
        _required_int_parameter,  # pyright: ignore[reportPrivateUsage]
        _roll_type_matches,  # pyright: ignore[reportPrivateUsage]
        generic_rule_matching_unit_effects,
        generic_rule_modifier_source_id,
    )

    if type(context) is not SaveOptionModifierContext:
        raise GameLifecycleError("Generic save hooks require SaveOptionModifierContext.")
    if (
        context.attacking_unit_instance_id is None
        or context.attacker_model_instance_id is None
        or context.weapon_profile is None
        or context.source_phase is None
    ):
        return context.save_options
    current = context.save_options
    for effect in generic_rule_matching_unit_effects(
        state=context.state,
        unit_instance_id=context.target_unit_instance_id,
        effect_kind=RuleEffectKind.SET_CHARACTERISTIC,
    ):
        if _characteristic_parameter(effect.parameters) is not Characteristic.INVULNERABLE_SAVE:
            continue
        if context.allocated_model_instance_id is None:
            if not _generic_this_model_effect_targets_only_alive_model(
                state=context.state,
                effect=effect,
                unit_instance_id=context.target_unit_instance_id,
            ):
                continue
        elif effect.source_model_instance_id != context.allocated_model_instance_id:
            continue
        current = generic_rule_save_options_with_invulnerable_save(
            current,
            target_number=_required_int_parameter(effect.parameters, key="value"),
            source_id=generic_rule_modifier_source_id(effect),
        )
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        effect_kind=RuleEffectKind.MODIFY_DICE_ROLL,
        legacy_attacker_role_allowed=lambda candidate: (
            _required_int_parameter(
                candidate.parameters,
                key="delta",
            )
            <= 0
        ),
        legacy_target_role_allowed=lambda candidate: (
            _required_int_parameter(
                candidate.parameters,
                key="delta",
            )
            >= 0
        ),
    ):
        if not _roll_type_matches(effect.parameters, expected="save"):
            continue
        delta = _required_int_parameter(effect.parameters, key="delta")
        source_id = generic_rule_modifier_source_id(effect)
        current = tuple(
            generic_rule_save_option_with_roll_modifier(
                option,
                delta,
                source_id,
                modifier_id=f"{effect.persisting_effect.effect_id}:save:{effect.effect_index}",
            )
            for option in current
        )
    for effect in _matching_generic_attack_effects(
        state=context.state,
        attacking_unit_instance_id=context.attacking_unit_instance_id,
        attacker_model_instance_id=context.attacker_model_instance_id,
        target_unit_instance_id=context.target_unit_instance_id,
        source_phase=context.source_phase,
        weapon_profile=context.weapon_profile,
        effect_kind=RuleEffectKind.MODIFY_CHARACTERISTIC,
        legacy_attacker_role_allowed=lambda _candidate: False,
        legacy_target_role_allowed=lambda _candidate: False,
    ):
        if _characteristic_parameter(effect.parameters) is not Characteristic.ARMOR_PENETRATION:
            continue
        delta = _required_int_parameter(effect.parameters, key="delta")
        source_id = generic_rule_modifier_source_id(effect)
        current = tuple(
            save_option_with_armor_penetration_modifier(
                option,
                delta=delta,
                source_rule_id=source_id,
                modifier_id=f"{effect.persisting_effect.effect_id}:armor-penetration:{effect.effect_index}",
            )
            for option in current
        )
    return current


def _generic_this_model_effect_targets_only_alive_model(
    *, state: object, effect: GenericAttackEffect, unit_instance_id: str
) -> bool:
    if effect.target_kind is not RuleTargetKind.THIS_MODEL:
        return True
    source_model_id = effect.source_model_instance_id
    if source_model_id is None:
        raise GameLifecycleError("Generic THIS_MODEL save effect requires source model.")
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id

    if type(state) is not GameState:
        raise GameLifecycleError("Generic THIS_MODEL save effect requires GameState.")
    alive_ids = tuple(
        model.model_instance_id
        for model in rules_unit_view_by_id(
            state=state, unit_instance_id=unit_instance_id
        ).alive_models()
    )
    return alive_ids == (source_model_id,)
