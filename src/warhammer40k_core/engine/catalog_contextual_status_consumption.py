from __future__ import annotations

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    parameter_payload,
)

CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID = "catalog-ir:hit-roll-reroll"
CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID = "catalog-ir:wound-roll-reroll"
CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID = "catalog-ir:shadow-of-chaos-aura"
CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID = "catalog-ir:shadow-form-choice"
CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID = (
    "catalog-ir:shooting-target-range-restriction"
)
CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID = "catalog-ir:battle-shock-forced-test"
CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID = "catalog-ir:battle-shock-failed-heal"
CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID = "catalog-ir:battle-shock-reroll"
CATALOG_IR_FORTIFICATION_COVER_CONSUMER_ID = "catalog-ir:fortification-cover"
CATALOG_IR_FORTIFICATION_TARGET_PERMISSION_CONSUMER_ID = (
    "catalog-ir:fortification-target-permission"
)
CATALOG_IR_FORTIFICATION_DESPERATE_ESCAPE_CONSUMER_ID = "catalog-ir:fortification-desperate-escape"

_RULE_EFFECT_SPEC_ERROR = "Catalog contextual status consumer requires RuleEffectSpec values."
_HIT_REROLL_ROLL_TYPES = frozenset({"hit", "hit_roll", "attack_sequence_hit"})
_WOUND_REROLL_ROLL_TYPES = frozenset({"wound", "wound_roll", "attack_sequence_wound"})
_BATTLE_SHOCK_REROLL_ROLL_TYPES = frozenset(
    {"battle_shock", "battle_shock_roll", "battle_shock_test"}
)


def registered_hook_ids() -> tuple[str, ...]:
    return (
        CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,
        CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,
        CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,
        CATALOG_IR_FORTIFICATION_COVER_CONSUMER_ID,
        CATALOG_IR_FORTIFICATION_DESPERATE_ESCAPE_CONSUMER_ID,
        CATALOG_IR_FORTIFICATION_TARGET_PERMISSION_CONSUMER_ID,
        CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,
        CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,
        CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,
    )


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog contextual status consumer requires RuleClause values.")
    consumer_ids: set[str] = set()
    if _clause_targets_shadow_of_chaos_aura(clause):
        consumer_ids.add(CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID)
    if _clause_is_shadow_form_choice(clause):
        consumer_ids.add(CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID)
    if _clause_is_shooting_target_range_restriction(clause):
        consumer_ids.add(CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID)
    if _clause_is_battle_shock_forced_test(clause):
        consumer_ids.add(CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID)
    if _clause_is_battle_shock_failed_heal(clause):
        consumer_ids.add(CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID)
    if _clause_is_battle_shock_reroll(clause):
        consumer_ids.add(CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID)
    if _clause_is_fortification_cover(clause):
        consumer_ids.add(CATALOG_IR_FORTIFICATION_COVER_CONSUMER_ID)
    if _clause_is_fortification_target_permission(clause):
        consumer_ids.add(CATALOG_IR_FORTIFICATION_TARGET_PERMISSION_CONSUMER_ID)
    if _clause_is_fortification_desperate_escape(clause):
        consumer_ids.add(CATALOG_IR_FORTIFICATION_DESPERATE_ESCAPE_CONSUMER_ID)
    consumer_ids.update(aura_attack_roll_reroll_consumer_ids_for_clause(clause))
    return tuple(sorted(consumer_ids))


def hook_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if _effect_is_shadow_of_chaos_status(effect):
        return (CATALOG_IR_SHADOW_OF_CHAOS_AURA_CONSUMER_ID,)
    if _effect_is_shadow_form_choice(effect):
        return (CATALOG_IR_SHADOW_FORM_CHOICE_CONSUMER_ID,)
    if _effect_is_shooting_target_range_restriction(effect):
        return (CATALOG_IR_SHOOTING_TARGET_RANGE_RESTRICTION_CONSUMER_ID,)
    if _effect_is_battle_shock_forced_test(effect):
        return (CATALOG_IR_BATTLE_SHOCK_FORCED_TEST_CONSUMER_ID,)
    if _effect_is_battle_shock_failed_heal(effect):
        return (CATALOG_IR_BATTLE_SHOCK_FAILED_HEAL_CONSUMER_ID,)
    if _effect_is_battle_shock_reroll(effect):
        return (CATALOG_IR_BATTLE_SHOCK_REROLL_CONSUMER_ID,)
    if _effect_is_fortification_cover(effect):
        return (CATALOG_IR_FORTIFICATION_COVER_CONSUMER_ID,)
    if _effect_is_fortification_target_permission(effect):
        return (CATALOG_IR_FORTIFICATION_TARGET_PERMISSION_CONSUMER_ID,)
    if _effect_is_fortification_desperate_escape(effect):
        return (CATALOG_IR_FORTIFICATION_DESPERATE_ESCAPE_CONSUMER_ID,)
    return ()


def aura_attack_roll_reroll_consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog contextual status consumer requires RuleClause values.")
    if clause.target is None or clause.target.kind is not RuleTargetKind.AURA_UNITS:
        return ()
    consumer_ids = {
        consumer_id
        for effect in clause.effects
        if (consumer_id := _attack_roll_reroll_consumer_id_for_effect(effect)) is not None
    }
    return tuple(sorted(consumer_ids))


def _clause_targets_shadow_of_chaos_aura(clause: RuleClause) -> bool:
    return (
        clause.target is not None
        and clause.target.kind is RuleTargetKind.AURA_UNITS
        and any(condition.kind is RuleConditionKind.AURA for condition in clause.conditions)
        and any(_effect_is_shadow_of_chaos_status(effect) for effect in clause.effects)
    )


def _effect_is_shadow_of_chaos_status(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "within_shadow_of_chaos"
        and parameters.get("rules_context") == "shadow_of_chaos"
        and parameters.get("owner") == "your_army"
    )


def _clause_is_shadow_form_choice(clause: RuleClause) -> bool:
    return (
        clause.target is not None
        and clause.target.kind is RuleTargetKind.THIS_UNIT
        and any(_effect_is_shadow_form_choice(effect) for effect in clause.effects)
    )


def _effect_is_shadow_form_choice(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    selectable_source_ids = parameters.get("selectable_source_ids")
    return (
        parameters.get("status") == "catalog_shadow_form_selection"
        and parameters.get("rules_context") == "shadow_form"
        and type(selectable_source_ids) is tuple
        and all(type(source_id) is str for source_id in selectable_source_ids)
        and bool(selectable_source_ids)
    )


def _clause_is_shooting_target_range_restriction(clause: RuleClause) -> bool:
    return any(_effect_is_shooting_target_range_restriction(effect) for effect in clause.effects)


def _effect_is_shooting_target_range_restriction(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    max_range = parameters.get("targeting_max_range_inches")
    return (
        parameters.get("status") == "shooting_target_range_restriction"
        and isinstance(max_range, int | float)
        and type(max_range) is not bool
        and float(max_range) > 0.0
    )


def _clause_is_battle_shock_forced_test(clause: RuleClause) -> bool:
    return any(_effect_is_battle_shock_forced_test(effect) for effect in clause.effects)


def _effect_is_battle_shock_forced_test(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "battle_shock_forced_below_starting_strength"
        and parameters.get("rules_context") == "battle_shock"
        and parameters.get("force_battle_shock_below_starting_strength") is True
    )


def _clause_is_battle_shock_failed_heal(clause: RuleClause) -> bool:
    return any(_effect_is_battle_shock_failed_heal(effect) for effect in clause.effects)


def _effect_is_battle_shock_failed_heal(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.RESTORE_LOST_WOUNDS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("amount") == "D3"
        and parameters.get("trigger") == "target_failed_battle_shock"
        and parameters.get("source_reference") == "aura_source"
    )


def _clause_is_battle_shock_reroll(clause: RuleClause) -> bool:
    return any(_effect_is_battle_shock_reroll(effect) for effect in clause.effects)


def _effect_is_battle_shock_reroll(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    roll_type = parameters.get("roll_type")
    return type(roll_type) is str and _lookup_token(roll_type) in _BATTLE_SHOCK_REROLL_ROLL_TYPES


def _clause_is_fortification_cover(clause: RuleClause) -> bool:
    return any(_effect_is_fortification_cover(effect) for effect in clause.effects)


def _effect_is_fortification_cover(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "benefit_of_cover"
        and parameters.get("rules_context") == "ranged_attack_allocation"
        and parameters.get("source_reference") == "this_fortification"
    )


def _clause_is_fortification_target_permission(clause: RuleClause) -> bool:
    return any(_effect_is_fortification_target_permission(effect) for effect in clause.effects)


def _effect_is_fortification_target_permission(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status") == "fortification_engagement_ranged_target_permission"
        and parameters.get("rules_context") == "shooting_target_selection"
    )


def _clause_is_fortification_desperate_escape(clause: RuleClause) -> bool:
    return any(_effect_is_fortification_desperate_escape(effect) for effect in clause.effects)


def _effect_is_fortification_desperate_escape(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("status")
        == "fortification_engagement_battle_shocked_desperate_escape_exception"
        and parameters.get("rules_context") == "fall_back_desperate_escape"
        and parameters.get("overflight_exception") is True
    )


def _attack_roll_reroll_consumer_id_for_effect(effect: RuleEffectSpec) -> str | None:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError(_RULE_EFFECT_SPEC_ERROR)
    if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
        return None
    parameters = parameter_payload(effect.parameters)
    if parameters.get("target_reference") == "tracked_target":
        return None
    if parameters.get("attack_role") != "attacker":
        return None
    roll_type = parameters.get("roll_type")
    if type(roll_type) is not str:
        return None
    token = _lookup_token(roll_type)
    if token in _HIT_REROLL_ROLL_TYPES:
        return CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID
    if token in _WOUND_REROLL_ROLL_TYPES:
        return CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID
    return None


def _lookup_token(value: str) -> str:
    return "_".join(value.casefold().replace(".", "_").replace("-", "_").split())
