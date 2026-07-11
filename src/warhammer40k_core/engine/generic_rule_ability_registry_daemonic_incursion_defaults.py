from __future__ import annotations

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.attack_sequence_completion_hooks import (
    AttackSequenceCompletedContext,
)
from warhammer40k_core.engine.enhancement_effects import EnhancementEffectContext
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleAttackSequenceCompletedAbility,
    GenericRuleEnhancementEffectAbility,
    GenericRuleReserveArrivalDistanceAbility,
    GenericRuleWeaponProfileModifierAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.reserve_arrival_hooks import (
    ReserveArrivalDistanceContext,
    ReserveArrivalDistanceGrant,
)
from warhammer40k_core.engine.runtime_modifiers import WeaponProfileModifierContext
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_daemonic_incursion_ir_support_2026_27 as daemonic_incursion_ir,
)


def _daemonic_incursion_warp_rifts_context_predicate(
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not ReserveArrivalDistanceContext:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival distance requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival distance requires source.")
    return (
        source.record.coverage_descriptor_id
        == daemonic_incursion_ir.DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID
    )


def _daemonic_incursion_warp_rifts_grants(
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource,
) -> tuple[ReserveArrivalDistanceGrant, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival grants require source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        rule,
    )

    return rule.warp_rifts_distance_grants(context, source=source)


def _daemonic_incursion_warp_rifts_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion reserve-arrival hook ID requires source.")
    return _validate_identifier(
        "generic Daemonic Incursion Warp Rifts hook_id",
        daemonic_incursion_ir.WARP_RIFTS_HOOK_ID,
    )


def _daemonic_incursion_denizens_context_predicate(
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not ReserveArrivalDistanceContext:
        raise GameLifecycleError("Daemonic Incursion Denizens distance requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Denizens distance requires source.")
    return (
        source.record.coverage_descriptor_id
        == daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID
    )


def _daemonic_incursion_denizens_grants(
    context: ReserveArrivalDistanceContext,
    source: GenericRuleAbilitySource,
) -> tuple[ReserveArrivalDistanceGrant, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Denizens grants require source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        rule,
    )

    return rule.denizens_of_the_warp_distance_grants(context, source=source)


def _daemonic_incursion_denizens_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Denizens hook ID requires source.")
    return _validate_identifier(
        "generic Daemonic Incursion Denizens hook_id",
        daemonic_incursion_ir.DENIZENS_OF_THE_WARP_HOOK_ID,
    )


def _daemonic_incursion_argath_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion A'rgath modifier ID requires source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return _validate_identifier(
        "generic Daemonic Incursion A'rgath modifier_id",
        enhancements.ARGATH_WEAPON_PROFILE_MODIFIER_ID,
    )


def _daemonic_incursion_everstave_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Everstave modifier ID requires source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return _validate_identifier(
        "generic Daemonic Incursion Everstave modifier_id",
        enhancements.EVERSTAVE_WEAPON_PROFILE_MODIFIER_ID,
    )


def _daemonic_incursion_soulstealer_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Soulstealer hook ID requires source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return _validate_identifier(
        "generic Daemonic Incursion Soulstealer hook_id",
        enhancements.SOULSTEALER_HOOK_ID,
    )


def _daemonic_incursion_endless_gift_effect_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Endless Gift effect ID requires source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return _validate_identifier(
        "generic Daemonic Incursion Endless Gift effect_id",
        enhancements.ENDLESS_GIFT_EFFECT_ID,
    )


def _daemonic_incursion_argath_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return enhancements.argath_weapon_profile_modifier(context)


def _daemonic_incursion_everstave_weapon_profile_modifier(
    context: WeaponProfileModifierContext,
) -> WeaponProfile:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return enhancements.everstave_weapon_profile_modifier(context)


def _daemonic_incursion_soulstealer_attack_sequence_completed(
    context: AttackSequenceCompletedContext,
) -> None:
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return enhancements.resolve_soulstealer_attack_sequence_completion(context)


def _daemonic_incursion_endless_gift_context_predicate(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not EnhancementEffectContext:
        raise GameLifecycleError("Daemonic Incursion Endless Gift effect requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Endless Gift effect requires source.")
    return (
        source.record.coverage_descriptor_id
        == daemonic_incursion_ir.ENDLESS_GIFT_ENHANCEMENT_DESCRIPTOR_ID
        and context.assignment.enhancement_id == daemonic_incursion_ir.ENDLESS_GIFT_ENHANCEMENT_ID
    )


def _daemonic_incursion_endless_gift_effect(
    context: EnhancementEffectContext,
    source: GenericRuleAbilitySource,
) -> tuple[object, ...]:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Daemonic Incursion Endless Gift effect requires source.")
    from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_daemons.detachments.daemonic_incursion import (  # noqa: E501
        enhancements,
    )

    return enhancements.endless_gift_effect(context)


def daemonic_incursion_weapon_profile_modifier_abilities() -> tuple[
    GenericRuleWeaponProfileModifierAbility,
    ...,
]:
    return (
        GenericRuleWeaponProfileModifierAbility(
            ability_ids_value=(daemonic_incursion_ir.ARGATH_MELEE_WEAPON_PROFILE_ABILITY,),
            coverage_descriptor_id=daemonic_incursion_ir.ARGATH_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=daemonic_incursion_ir.ARGATH_SOURCE_RULE_ID,
            modifier_id_builder=_daemonic_incursion_argath_modifier_id,
            handler=_daemonic_incursion_argath_weapon_profile_modifier,
        ),
        GenericRuleWeaponProfileModifierAbility(
            ability_ids_value=(daemonic_incursion_ir.EVERSTAVE_RANGED_WEAPON_PROFILE_ABILITY,),
            coverage_descriptor_id=daemonic_incursion_ir.EVERSTAVE_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=daemonic_incursion_ir.EVERSTAVE_SOURCE_RULE_ID,
            modifier_id_builder=_daemonic_incursion_everstave_modifier_id,
            handler=_daemonic_incursion_everstave_weapon_profile_modifier,
        ),
    )


def daemonic_incursion_attack_sequence_completed_abilities() -> tuple[
    GenericRuleAttackSequenceCompletedAbility,
    ...,
]:
    return (
        GenericRuleAttackSequenceCompletedAbility(
            ability_ids_value=(daemonic_incursion_ir.SOULSTEALER_MODEL_DESTROYED_HEAL_ABILITY,),
            coverage_descriptor_id=daemonic_incursion_ir.SOULSTEALER_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=daemonic_incursion_ir.SOULSTEALER_SOURCE_RULE_ID,
            hook_id_builder=_daemonic_incursion_soulstealer_hook_id,
            handler=_daemonic_incursion_soulstealer_attack_sequence_completed,
        ),
    )


def daemonic_incursion_enhancement_effect_abilities() -> tuple[
    GenericRuleEnhancementEffectAbility,
    ...,
]:
    return (
        GenericRuleEnhancementEffectAbility(
            ability_id=daemonic_incursion_ir.ENDLESS_GIFT_FEEL_NO_PAIN_ABILITY,
            coverage_descriptor_id=daemonic_incursion_ir.ENDLESS_GIFT_ENHANCEMENT_DESCRIPTOR_ID,
            source_rule_id=daemonic_incursion_ir.ENDLESS_GIFT_SOURCE_RULE_ID,
            enhancement_id=daemonic_incursion_ir.ENDLESS_GIFT_ENHANCEMENT_ID,
            effect_id_builder=_daemonic_incursion_endless_gift_effect_id,
            context_predicate=_daemonic_incursion_endless_gift_context_predicate,
            effect_builder=_daemonic_incursion_endless_gift_effect,
        ),
    )


daemonic_incursion_reserve_arrival_distance_abilities = (
    GenericRuleReserveArrivalDistanceAbility(
        ability_id=daemonic_incursion_ir.WARP_RIFTS_DEEP_STRIKE_DISTANCE_ABILITY,
        coverage_descriptor_id=(
            daemonic_incursion_ir.DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID
        ),
        source_rule_id=daemonic_incursion_ir.DAEMONIC_INCURSION_SOURCE_RULE_ID,
        hook_id_builder=_daemonic_incursion_warp_rifts_hook_id,
        context_predicate=_daemonic_incursion_warp_rifts_context_predicate,
        grant_builder=_daemonic_incursion_warp_rifts_grants,
    ),
    GenericRuleReserveArrivalDistanceAbility(
        ability_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DEEP_STRIKE_DISTANCE_ABILITY,
        coverage_descriptor_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_DESCRIPTOR_ID,
        source_rule_id=daemonic_incursion_ir.DENIZENS_OF_THE_WARP_SOURCE_RULE_ID,
        hook_id_builder=_daemonic_incursion_denizens_hook_id,
        context_predicate=_daemonic_incursion_denizens_context_predicate,
        grant_builder=_daemonic_incursion_denizens_grants,
    ),
)


_validate_identifier = IdentifierValidator(GameLifecycleError)
