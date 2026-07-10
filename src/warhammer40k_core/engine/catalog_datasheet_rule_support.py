from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.weapon_profiles import WeaponProfileError, weapon_keyword_from_token
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID = "army-mustering:required-datasheet-option"
CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID = "catalog-ir:conditional-ability:lone-operative"
CATALOG_IR_STEALTH_AURA_CONSUMER_ID = "catalog-ir:aura-ability:stealth"
CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID = (
    "catalog-ir:fight-selected-weapon-ability-choice"
)
CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID = "catalog-ir:weapon-keyword-grant"


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Datasheet RuleIR support requires RuleClause.")
    consumer_ids: set[str] = set()
    if clause_is_mustering_selection(clause):
        consumer_ids.add(CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID)
    if clause_is_conditional_lone_operative(clause):
        consumer_ids.add(CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID)
    if clause_is_stealth_aura(clause):
        consumer_ids.add(CATALOG_IR_STEALTH_AURA_CONSUMER_ID)
    if clause_is_passive_characteristic_modifier(clause):
        characteristic = Characteristic(
            _required_string(parameter_payload(clause.effects[0].parameters), "characteristic")
        )
        consumer_ids.add(f"catalog-ir:{characteristic.value}-characteristic-modifier")
    if clause_is_fight_selected_weapon_ability_choice(clause):
        consumer_ids.add(CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID)
        consumer_ids.add(CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID)
        for effect in clause.effects:
            ability = weapon_keyword_from_token(
                _required_string(parameter_payload(effect.parameters), "weapon_ability")
            )
            token = ability.value.lower().replace("_", "-").replace(" ", "-")
            consumer_ids.add(f"catalog-ir:weapon-keyword-grant:{token}")
    return tuple(sorted(consumer_ids))


def registered_consumer_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID,
                CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
                CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
            }
        )
    )


def clause_is_mustering_selection(clause: RuleClause) -> bool:
    if not clause.is_supported or clause.trigger is None or clause.target is None:
        return False
    if clause.trigger.kind is not RuleTriggerKind.SETUP:
        return False
    if parameter_payload(clause.trigger.parameters).get("timing_window") != "army_mustering":
        return False
    if clause.target.kind is not RuleTargetKind.THIS_MODEL or len(clause.effects) != 1:
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.MUSTERING_SELECTION:
        return False
    parameters = parameter_payload(effect.parameters)
    options = parameters.get("selection_option_ids")
    return (
        parameters.get("required") is True
        and type(options) is tuple
        and bool(options)
        and all(type(option) is str and bool(option) for option in options)
    )


def clause_is_passive_characteristic_modifier(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.WHILE_CONDITION_TRUE
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.MODIFY_CHARACTERISTIC:
        return False
    parameters = parameter_payload(effect.parameters)
    try:
        characteristic = Characteristic(_required_string(parameters, "characteristic"))
    except ValueError:
        return False
    if characteristic not in {
        Characteristic.ATTACKS,
        Characteristic.MOVEMENT,
        Characteristic.STRENGTH,
        Characteristic.TOUGHNESS,
    }:
        return False
    if type(parameters.get("delta")) is not int:
        return False
    return any(
        condition.kind is RuleConditionKind.KEYWORD_GATE
        and type(parameter_payload(condition.parameters).get("required_keyword")) is str
        for condition in clause.conditions
    )


def clause_is_conditional_lone_operative(clause: RuleClause) -> bool:
    if not _is_while_condition_ability_grant(clause, ability="lone_operative"):
        return False
    return any(
        condition.kind is RuleConditionKind.DISTANCE_PREDICATE
        and parameter_payload(condition.parameters).get("predicate") == "within"
        and type(parameter_payload(condition.parameters).get("distance_inches")) in {int, float}
        and parameter_payload(condition.parameters).get("allegiance") == "friendly"
        and type(parameter_payload(condition.parameters).get("required_keyword_sequence")) is tuple
        for condition in clause.conditions
    )


def clause_is_stealth_aura(clause: RuleClause) -> bool:
    if not _is_while_condition_ability_grant(clause, ability="stealth"):
        return False
    return (
        clause.template_id is not None
        and clause.target is not None
        and clause.target.kind is RuleTargetKind.AURA_UNITS
        and parameter_payload(clause.target.parameters).get("allegiance") == "friendly"
        and any(condition.kind is RuleConditionKind.AURA for condition in clause.conditions)
    )


def clause_is_fight_selected_weapon_ability_choice(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.UNIT_SELECTED
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or len(clause.effects) < 2
    ):
        return False
    trigger = parameter_payload(clause.trigger.parameters)
    duration = parameter_payload(clause.duration.parameters)
    if trigger.get("phase") != "fight" or trigger.get("timing_window") != "selected_to_fight":
        return False
    if duration.get("endpoint") != "phase" or duration.get("boundary") != "end":
        return False
    groups: set[str] = set()
    option_ids: set[str] = set()
    for effect in clause.effects:
        if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
            return False
        parameters = parameter_payload(effect.parameters)
        if parameters.get("selection_kind") != "select_one":
            return False
        group_id = parameters.get("selection_group_id")
        option_id = parameters.get("selection_option_id")
        if type(group_id) is not str or type(option_id) is not str:
            return False
        groups.add(group_id)
        option_ids.add(option_id)
        try:
            weapon_keyword_from_token(_required_string(parameters, "weapon_ability"))
        except WeaponProfileError:
            return False
    return len(groups) == 1 and len(option_ids) == len(clause.effects)


def _is_while_condition_ability_grant(clause: RuleClause, *, ability: str) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.target is None
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.WHILE_CONDITION_TRUE
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    return (
        effect.kind is RuleEffectKind.GRANT_ABILITY
        and parameter_payload(effect.parameters).get("ability") == ability
    )


def _required_string(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value:
        raise GameLifecycleError(f"Datasheet RuleIR {key} must be a non-empty string.")
    return value
