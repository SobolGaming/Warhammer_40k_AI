from __future__ import annotations

from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.engine.advance_eligibility_hooks import (
    AdvanceEligibilityContext,
    AdvanceEligibilityGrant,
)
from warhammer40k_core.engine.advance_hooks import AdvanceMoveContext, AdvanceMoveGrant
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.generic_rule_ability_effects import (
    generic_rule_ability_effects_for_unit,
    generic_rule_ability_source_context_payload,
    generic_rule_ability_unit_for_player_context,
    generic_rule_advance_context_unit_id,
    generic_rule_advance_move_context_unit_id,
)
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleAdvanceEligibilityAbility,
    GenericRuleStratagemCostModifierAbility,
)
from warhammer40k_core.engine.generic_rule_advance_move_abilities import (
    GenericRuleAdvanceMoveAbility,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.ranged_weapon_keyword_effects import (
    ranged_weapon_keyword_grant_payload,
)
from warhammer40k_core.engine.stratagem_cost_modifiers import StratagemCostModifierContext
from warhammer40k_core.engine.stratagems_model import (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    CORE_HEROIC_INTERVENTION_HANDLER_ID,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_warptide_ir_support_2026_27 as warptide_ir,
)

_SOUL_HUNGRY_HANDLER_IDS = (
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    CORE_HEROIC_INTERVENTION_HANDLER_ID,
)
_SOUL_HUNGRY_STRATAGEM_IDS = (
    "core:fire-overwatch",
    "core:heroic-intervention",
    "fire-overwatch",
    "heroic-intervention",
)


def warptide_advance_move_abilities() -> tuple[GenericRuleAdvanceMoveAbility, ...]:
    return (
        GenericRuleAdvanceMoveAbility(
            ability_id=warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
            coverage_descriptor_id=warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
            hook_id_builder=_warptide_advance_move_hook_id,
            target_unit_id_builder=generic_rule_advance_move_context_unit_id,
            context_predicate=_warptide_advance_move_context_predicate,
            grant_builder=_warptide_advance_move_grant,
        ),
    )


def warptide_advance_eligibility_abilities() -> tuple[GenericRuleAdvanceEligibilityAbility, ...]:
    return (
        GenericRuleAdvanceEligibilityAbility(
            ability_id=warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
            coverage_descriptor_id=warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID,
            source_rule_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
            hook_id_builder=_warptide_advance_eligibility_hook_id,
            target_unit_id_builder=generic_rule_advance_context_unit_id,
            context_predicate=_warptide_advance_eligibility_context_predicate,
            grant_builder=_warptide_advance_eligibility_grant,
        ),
    )


def warptide_stratagem_cost_modifier_abilities() -> tuple[
    GenericRuleStratagemCostModifierAbility, ...
]:
    return (
        GenericRuleStratagemCostModifierAbility(
            ability_id=warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,
            coverage_descriptor_id=warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID,
            source_rule_id=warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_SOURCE_RULE_ID,
            modifier_id_builder=_warptide_soul_hungry_cost_modifier_id,
            context_predicate=_warptide_soul_hungry_cost_context_predicate,
            modifier_builder=_warptide_soul_hungry_cost_modifier,
        ),
    )


def _warptide_advance_move_context_predicate(
    context: AdvanceMoveContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if type(context) is not AdvanceMoveContext:
        raise GameLifecycleError("Warptide Shudderblink advance move requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide Shudderblink advance move requires source.")
    if not matching_effects:
        return False
    if context.movement_phase_action != "advance":
        return False
    return (
        generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is not None
    )


def _warptide_advance_move_grant(
    context: AdvanceMoveContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> AdvanceMoveGrant:
    return AdvanceMoveGrant(
        hook_id=_warptide_advance_move_hook_id(source),
        source_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
        label="Shudderblink Assault",
        granted_ranged_weapon_keywords=(WeaponKeyword.ASSAULT.value,),
        automatic=True,
        replay_payload=_warptide_replay_payload(
            source=source,
            matching_effects=matching_effects,
            effect_kind="shudderblink_assault_after_advance",
            extra_context={
                "unit_instance_id": context.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
                "granted_ranged_weapon_keyword": WeaponKeyword.ASSAULT.value,
            },
        ),
        unit_effect_payload=ranged_weapon_keyword_grant_payload(
            granted_keywords=(WeaponKeyword.ASSAULT,),
            source_movement_request_id=context.movement_request_id,
            source_movement_result_id=context.movement_result_id,
        ),
        unit_effect_expiration="end_turn",
    )


def _warptide_advance_eligibility_context_predicate(
    context: AdvanceEligibilityContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> bool:
    if type(context) is not AdvanceEligibilityContext:
        raise GameLifecycleError("Warptide Shudderblink advance eligibility requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide Shudderblink advance eligibility requires source.")
    if not matching_effects:
        return False
    return (
        generic_rule_ability_unit_for_player_context(
            state=context.state,
            player_id=context.player_id,
            unit_instance_id=context.unit_instance_id,
            source=source,
        )
        is not None
    )


def _warptide_advance_eligibility_grant(
    context: AdvanceEligibilityContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> AdvanceEligibilityGrant:
    return AdvanceEligibilityGrant(
        hook_id=_warptide_advance_eligibility_hook_id(source),
        source_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
        can_shoot=True,
        can_declare_charge=True,
        replay_payload=_warptide_replay_payload(
            source=source,
            matching_effects=matching_effects,
            effect_kind="shudderblink_advance_eligibility",
            extra_context={
                "unit_instance_id": context.unit_instance_id,
                "movement_request_id": context.movement_request_id,
                "movement_result_id": context.movement_result_id,
                "can_shoot_after_advance": True,
                "can_declare_charge_after_advance": True,
            },
        ),
    )


def _warptide_soul_hungry_cost_context_predicate(
    context: StratagemCostModifierContext,
    source: GenericRuleAbilitySource,
) -> bool:
    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Warptide Soul-hungry Slaughterers requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide Soul-hungry Slaughterers requires source.")
    if context.definition.handler_id not in _SOUL_HUNGRY_HANDLER_IDS and (
        context.definition.stratagem_id not in _SOUL_HUNGRY_STRATAGEM_IDS
    ):
        return False
    target_unit_id = _target_binding_unit_id_or_none(context)
    if target_unit_id is None:
        return False
    if _unit_owner_or_none(context, unit_instance_id=target_unit_id) != (
        context.eligibility_context.player_id
    ):
        return False
    return bool(
        generic_rule_ability_effects_for_unit(
            state=context.state,
            source=source,
            unit_instance_id=target_unit_id,
            ability=warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,
        )
    )


def _warptide_soul_hungry_cost_modifier(
    context: StratagemCostModifierContext,
    source: GenericRuleAbilitySource,
) -> int:
    if type(context) is not StratagemCostModifierContext:
        raise GameLifecycleError("Warptide Soul-hungry Slaughterers requires context.")
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide Soul-hungry Slaughterers requires source.")
    return max(0, context.current_command_point_cost - 1)


def _warptide_advance_move_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide advance move hook ID requires source.")
    return warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID


def _warptide_advance_eligibility_hook_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide advance eligibility hook ID requires source.")
    return warptide_ir.SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID


def _warptide_soul_hungry_cost_modifier_id(source: GenericRuleAbilitySource) -> str:
    if type(source) is not GenericRuleAbilitySource:
        raise GameLifecycleError("Warptide cost modifier ID requires source.")
    return warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_MODIFIER_ID


def _target_binding_unit_id_or_none(context: StratagemCostModifierContext) -> str | None:
    target_binding = context.target_binding
    if target_binding is None:
        return None
    return target_binding.target_unit_instance_id


def _unit_owner_or_none(
    context: StratagemCostModifierContext,
    *,
    unit_instance_id: str,
) -> str | None:
    for army in context.state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == unit_instance_id:
                return army.player_id
    return None


def _warptide_replay_payload(
    *,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
    effect_kind: str,
    extra_context: dict[str, JsonValue],
) -> JsonValue:
    return generic_rule_ability_source_context_payload(
        source=source,
        matching_effects=matching_effects,
        source_rule_id=warptide_ir.WARPTIDE_SOURCE_RULE_ID,
        extra_context={
            "effect_kind": effect_kind,
            "detachment_id": warptide_ir.WARPTIDE_DETACHMENT_ID,
            "required_faction_keyword": warptide_ir.LEGIONES_DAEMONICA_KEYWORD,
            "required_keyword": warptide_ir.BATTLELINE_KEYWORD,
            **extra_context,
        },
    )
