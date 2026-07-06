from __future__ import annotations

from typing import Protocol, cast

from warhammer40k_core.engine.enhancement_effects import EnhancementEffectContext
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleEnhancementEffectAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_aeldari_path_of_the_outcast_ir_support_2026_27 as path_outcast_ir,
)


class _PathOfTheOutcastEnhancementsModule(Protocol):
    CAMOUFLAGED_SNIPERS_EFFECT_ID: str
    ASSASSINS_EYE_EFFECT_ID: str

    def camouflaged_snipers_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...

    def assassins_eye_effect(
        self,
        context: EnhancementEffectContext,
    ) -> tuple[object, ...]: ...


def aeldari_path_of_the_outcast_enhancement_effect_abilities() -> tuple[
    GenericRuleEnhancementEffectAbility, ...
]:
    return (
        GenericRuleEnhancementEffectAbility(
            ability_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_KEEP_HIDDEN_ABILITY,
            coverage_descriptor_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_SOURCE_RULE_ID,
            enhancement_id=path_outcast_ir.CAMOUFLAGED_SNIPERS_ENHANCEMENT_ID,
            effect_id_builder=_camouflaged_snipers_effect_id,
            context_predicate=_enhancement_context_predicate,
            effect_builder=_camouflaged_snipers_effect,
        ),
        GenericRuleEnhancementEffectAbility(
            ability_id=path_outcast_ir.ASSASSINS_EYE_CHARACTER_AP_BONUS_ABILITY,
            coverage_descriptor_id=path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=path_outcast_ir.ASSASSINS_EYE_SOURCE_RULE_ID,
            enhancement_id=path_outcast_ir.ASSASSINS_EYE_ENHANCEMENT_ID,
            effect_id_builder=_assassins_eye_effect_id,
            context_predicate=_enhancement_context_predicate,
            effect_builder=_assassins_eye_effect,
        ),
    )


def _path_of_the_outcast_enhancements() -> _PathOfTheOutcastEnhancementsModule:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.aeldari.detachments.path_of_the_outcast import (  # noqa: E501
        enhancements,
    )

    return cast(_PathOfTheOutcastEnhancementsModule, enhancements)


def _enhancement_context_predicate(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Path of the Outcast enhancement effect requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Path of the Outcast enhancement effect requires source.")
    return True


def _camouflaged_snipers_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Camouflaged Snipers effect ID requires source.")
    return _path_of_the_outcast_enhancements().CAMOUFLAGED_SNIPERS_EFFECT_ID


def _camouflaged_snipers_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Camouflaged Snipers effect requires source.")
    return _path_of_the_outcast_enhancements().camouflaged_snipers_effect(context)


def _assassins_eye_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Assassins Eye effect ID requires source.")
    return _path_of_the_outcast_enhancements().ASSASSINS_EYE_EFFECT_ID


def _assassins_eye_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Assassins Eye effect requires source.")
    return _path_of_the_outcast_enhancements().assassins_eye_effect(context)
