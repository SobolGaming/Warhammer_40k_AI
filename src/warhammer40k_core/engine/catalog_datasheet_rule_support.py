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
CATALOG_IR_LEADING_UNIT_WOUND_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:wound-roll-modifier"
CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID = (
    "catalog-ir:fight-activation-movement-distance"
)
CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID = (
    "catalog-ir:invulnerable-save-characteristic-query"
)
CATALOG_IR_PASSIVE_HIT_REROLL_CONSUMER_ID = "catalog-ir:passive-hit-reroll"
CATALOG_IR_FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_CONSUMER_ID = (
    "catalog-ir:first-failed-save-damage-replacement"
)


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
    if clause_is_passive_invulnerable_save_set(clause):
        consumer_ids.add(CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID)
    if clause_is_passive_hit_reroll(clause):
        consumer_ids.add(CATALOG_IR_PASSIVE_HIT_REROLL_CONSUMER_ID)
    if clause_is_first_failed_save_damage_replacement(clause):
        consumer_ids.add(CATALOG_IR_FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_CONSUMER_ID)
    if clause_is_fight_selected_weapon_ability_choice(clause):
        consumer_ids.add(CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID)
        consumer_ids.add(CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID)
        for effect in clause.effects:
            ability = weapon_keyword_from_token(
                _required_string(parameter_payload(effect.parameters), "weapon_ability")
            )
            token = ability.value.lower().replace("_", "-").replace(" ", "-")
            consumer_ids.add(f"catalog-ir:weapon-keyword-grant:{token}")
    if clause_is_charge_end_leading_unit_weapon_ability_grant(clause):
        consumer_ids.add(CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID)
        for effect in clause.effects:
            ability = weapon_keyword_from_token(
                _required_string(parameter_payload(effect.parameters), "weapon_ability")
            )
            token = ability.value.lower().replace("_", "-").replace(" ", "-")
            consumer_ids.add(f"catalog-ir:weapon-keyword-grant:{token}")
    if clause_is_leading_unit_wound_roll_modifier(clause):
        consumer_ids.add(CATALOG_IR_LEADING_UNIT_WOUND_ROLL_MODIFIER_CONSUMER_ID)
    if clause_is_consolidation_move_distance_modifier(clause):
        consumer_ids.add(CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID)
    return tuple(sorted(consumer_ids))


def registered_consumer_ids() -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID,
                CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID,
                CATALOG_IR_STEALTH_AURA_CONSUMER_ID,
                CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
                CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
                CATALOG_IR_LEADING_UNIT_WOUND_ROLL_MODIFIER_CONSUMER_ID,
                CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
                CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID,
                CATALOG_IR_PASSIVE_HIT_REROLL_CONSUMER_ID,
                CATALOG_IR_FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_CONSUMER_ID,
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


def clause_is_passive_invulnerable_save_set(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.duration is not None
        or clause.conditions
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.SET_CHARACTERISTIC:
        return False
    parameters = parameter_payload(effect.parameters)
    value = parameters.get("value")
    return (
        parameters.get("characteristic") == Characteristic.INVULNERABLE_SAVE.value
        and type(value) is int
        and 2 <= value <= 6
    )


def clause_is_passive_hit_reroll(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.duration is not None
        or clause.conditions
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.REROLL_PERMISSION:
        return False
    parameters = parameter_payload(effect.parameters)
    reroll_value = parameters.get("reroll_unmodified_value")
    objective_upgrade = parameters.get("full_reroll_if_target_within_objective_range")
    return (
        parameters.get("roll_type") == "hit"
        and type(reroll_value) is int
        and 1 <= reroll_value <= 6
        and (objective_upgrade is None or type(objective_upgrade) is bool)
    )


def clause_is_first_failed_save_damage_replacement(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.duration is not None
        or len(clause.effects) != 1
        or len(clause.conditions) != 1
    ):
        return False
    trigger = parameter_payload(clause.trigger.parameters)
    if (
        trigger.get("roll_type") != "attack_sequence.save"
        or trigger.get("outcome") != "failed"
        or trigger.get("timing_window") != "after_failed_saving_throw"
    ):
        return False
    condition = clause.conditions[0]
    if condition.kind is not RuleConditionKind.FREQUENCY_LIMIT:
        return False
    frequency = parameter_payload(condition.parameters)
    if (
        frequency.get("scope") != "turn"
        or frequency.get("max_uses") != 1
        or frequency.get("activation_kind") != "automatic_first_occurrence"
        or frequency.get("usage_subject") != "bearers_unit"
    ):
        return False
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    return (
        effect.kind is RuleEffectKind.SET_CHARACTERISTIC
        and parameters.get("characteristic") == Characteristic.DAMAGE.value
        and parameters.get("attack_role") == "defender"
        and parameters.get("value") == 0
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


def clause_is_leading_unit_wound_roll_modifier(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.SELECTED_UNIT
        or len(clause.effects) != 1
    ):
        return False
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    if trigger_parameters.get("roll_type") not in {"wound", "wound_roll"}:
        return False
    if not any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship") == "this_model_leading_unit"
        for condition in clause.conditions
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("roll_type") in {"wound", "wound_roll"}
        and parameters.get("attack_role") == "attacker"
        and type(parameters.get("delta")) is int
    )


def clause_is_consolidation_move_distance_modifier(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or len(clause.effects) != 1
    ):
        return False
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    if (
        trigger_parameters.get("edge") != "during"
        or trigger_parameters.get("phase") != "fight"
        or trigger_parameters.get("timing_window") != "consolidate_move"
        or trigger_parameters.get("subject") != "this_unit"
        or trigger_parameters.get("movement_mode") != "consolidate"
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.MODIFY_MOVE_DISTANCE:
        return False
    parameters = parameter_payload(effect.parameters)
    distance = parameters.get("distance_inches")
    replaced = parameters.get("replaced_distance_inches")
    return (
        parameters.get("movement_mode") == "consolidate"
        and parameters.get("operation") == "set_maximum"
        and _is_positive_number(distance)
        and _is_positive_number(replaced)
    )


def clause_is_charge_end_leading_unit_weapon_ability_grant(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.SELECTED_UNIT
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or len(clause.effects) != 1
    ):
        return False
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    duration_parameters = parameter_payload(clause.duration.parameters)
    if (
        trigger_parameters.get("edge") != "after"
        or trigger_parameters.get("phase") != "charge"
        or trigger_parameters.get("timing_window") != "charge_move_end"
        or trigger_parameters.get("subject") != "that_unit"
        or duration_parameters.get("endpoint") != "turn"
        or duration_parameters.get("boundary", "end") != "end"
    ):
        return False
    if not any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship") == "this_model_leading_unit"
        for condition in clause.conditions
    ):
        return False
    effect = clause.effects[0]
    if effect.kind is not RuleEffectKind.GRANT_WEAPON_ABILITY:
        return False
    parameters = parameter_payload(effect.parameters)
    if parameters.get("target_scope") != "models_in_selected_unit":
        return False
    if not (
        type(parameters.get("weapon_name")) is str
        or type(parameters.get("weapon_names")) is tuple
        or parameters.get("weapon_scope") in {"all", "melee", "ranged"}
    ):
        return False
    try:
        weapon_keyword_from_token(_required_string(parameters, "weapon_ability"))
    except WeaponProfileError:
        return False
    return True


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


def _is_positive_number(value: object) -> bool:
    if type(value) is int:
        return value > 0
    if type(value) is float:
        return value > 0
    return False
