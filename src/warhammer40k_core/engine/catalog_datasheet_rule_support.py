from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.weapon_profiles import WeaponProfileError, weapon_keyword_from_token
from warhammer40k_core.engine.catalog_datasheet_rule_descriptors import (
    clause_uses_exact_datasheet_runtime_template,
    conditional_attack_reroll_descriptor_for_clause,
    conditional_invulnerable_save_descriptor_for_clause,
    conditional_leader_ability_grant_descriptor_for_clause,
    conditional_leading_roll_reroll_descriptor_for_clause,
    conditional_proximity_effects_descriptor_for_clause,
    exact_datasheet_runtime_descriptor_for_clause,
    faction_resource_refund_roll_descriptor_for_clause,
    fight_on_death_descriptor_for_clause,
    first_failed_save_damage_replacement_descriptor_for_clause,
    invulnerable_save_descriptor_for_clause,
    movement_action_grant_descriptor_for_clause,
    passive_hit_reroll_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_datasheet_rule_extensions import (
    charge_after_movement_actions_descriptor_for_clause,
    clause_uses_exact_extended_datasheet_template,
    command_restoration_descriptor_for_clause,
    conditional_leading_charge_after_movement_action_descriptor_for_clause,
    conditional_leading_fixed_advance_descriptor_for_clause,
    conditional_leading_weapon_range_descriptor_for_clause,
    extended_datasheet_descriptor_for_clause,
    movement_target_pair_descriptor_for_clause,
)
from warhammer40k_core.engine.catalog_tracked_target_selection_descriptors import (
    clause_has_invalid_exact_tracked_target_selection_shape,
)
from warhammer40k_core.engine.catalog_tracked_target_weapon_grants import (
    clause_has_invalid_exact_tracked_target_weapon_grant_shape,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_MUSTERING_SELECTION_CONSUMER_ID = "army-mustering:required-datasheet-option"
CATALOG_IR_CONDITIONAL_LONE_OPERATIVE_CONSUMER_ID = "catalog-ir:conditional-ability:lone-operative"
CATALOG_IR_STEALTH_AURA_CONSUMER_ID = "catalog-ir:aura-ability:stealth"
CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID = "catalog-ir:granted-ability:stealth"
CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID = (
    "catalog-ir:fight-selected-weapon-ability-choice"
)
CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID = "catalog-ir:weapon-keyword-grant"
CATALOG_IR_LEADING_UNIT_WOUND_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:wound-roll-modifier"
CATALOG_IR_LEADING_UNIT_HIT_ROLL_MODIFIER_CONSUMER_ID = "catalog-ir:hit-roll-modifier"
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
CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID = "catalog-ir:fight-on-death-source"
CATALOG_IR_LEADERSHIP_CHARACTERISTIC_QUERY_CONSUMER_ID = (
    "catalog-ir:leadership-characteristic-query"
)
CATALOG_IR_BALLISTIC_SKILL_CHARACTERISTIC_MODIFIER_CONSUMER_ID = (
    "catalog-ir:ballistic-skill-characteristic-modifier"
)
CATALOG_IR_WEAPON_SKILL_CHARACTERISTIC_MODIFIER_CONSUMER_ID = (
    "catalog-ir:weapon-skill-characteristic-modifier"
)
CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID = "catalog-ir:hit-roll-reroll"
CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID = "catalog-ir:wound-roll-reroll"
CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID = "catalog-ir:damage-roll-reroll"
CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID = "catalog-ir:movement-action-grant"
CATALOG_IR_AGILE_MANOEUVRE_ROLL_REROLL_CONSUMER_ID = "catalog-ir:agile-manoeuvre-roll-reroll"
CATALOG_IR_FACTION_RESOURCE_REFUND_ROLL_CONSUMER_ID = "catalog-ir:faction-resource-refund-roll"
CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID = "catalog-ir:conditional-leading-fixed-advance"
CATALOG_IR_WEAPON_RANGE_MODIFIER_CONSUMER_ID = (
    "catalog-ir:conditional-leading-weapon-range-modifier"
)
CATALOG_IR_CHARGE_AFTER_MOVEMENT_ACTION_CONSUMER_ID = (
    "catalog-ir:conditional-leading-charge-after-movement-action"
)
CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID = "catalog-ir:movement-friendly-enemy-target-pair"
CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID = "catalog-ir:command-restoration"
CATALOG_IR_CLAUSE_WIDE_COMPOUND_CONSUMER_IDS = (
    CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
    CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
    CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID,
    CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
)
CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS = MappingProxyType(
    {
        "fights_first": "catalog-ir:conditional-leading-ability:fights-first",
        "infiltrators": "catalog-ir:conditional-leading-ability:infiltrators",
        "scouts": "catalog-ir:conditional-leading-ability:scouts",
        "stealth": "catalog-ir:conditional-leading-ability:stealth",
    }
)


def consumer_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Datasheet RuleIR support requires RuleEffectSpec.")
    parameters = parameter_payload(effect.parameters)
    if effect.kind is RuleEffectKind.REROLL_PERMISSION and parameters == {
        "roll_type": "agile_manoeuvre_roll",
        "selection": "whole_roll",
    }:
        return (CATALOG_IR_AGILE_MANOEUVRE_ROLL_REROLL_CONSUMER_ID,)
    if effect.kind is RuleEffectKind.MODIFY_FACTION_RESOURCE and parameters == {
        "amount": 1,
        "operation": "gain",
        "resource_kind": "battle_focus_token",
        "roll_expression": "D6",
        "success_threshold": 3,
    }:
        return (CATALOG_IR_FACTION_RESOURCE_REFUND_ROLL_CONSUMER_ID,)
    return ()


def clause_has_invalid_exact_datasheet_runtime_shape(clause: RuleClause) -> bool:
    return (
        (
            clause_uses_exact_datasheet_runtime_template(clause)
            and exact_datasheet_runtime_descriptor_for_clause(clause) is None
        )
        or (
            clause_uses_exact_extended_datasheet_template(clause)
            and extended_datasheet_descriptor_for_clause(clause) is None
        )
        or clause_has_invalid_exact_tracked_target_weapon_grant_shape(clause)
        or clause_has_invalid_exact_tracked_target_selection_shape(clause)
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
    if conditional_attack_reroll_descriptor_for_clause(clause) is not None:
        consumer_ids.update(
            {
                CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
                CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
                CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
            }
        )
    if movement_action_grant_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID)
    conditional_leader_grant = conditional_leader_ability_grant_descriptor_for_clause(clause)
    if conditional_leader_grant is not None:
        consumer_ids.add(
            CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS[conditional_leader_grant.ability]
        )
    if conditional_leading_roll_reroll_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_AGILE_MANOEUVRE_ROLL_REROLL_CONSUMER_ID)
    if faction_resource_refund_roll_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_FACTION_RESOURCE_REFUND_ROLL_CONSUMER_ID)
    if conditional_leading_fixed_advance_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID)
    if conditional_leading_weapon_range_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_WEAPON_RANGE_MODIFIER_CONSUMER_ID)
    if conditional_leading_charge_after_movement_action_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_CHARGE_AFTER_MOVEMENT_ACTION_CONSUMER_ID)
    if movement_target_pair_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID)
    if command_restoration_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID)
    if charge_after_movement_actions_descriptor_for_clause(clause) is not None:
        for effect in clause.effects:
            ability = parameter_payload(effect.parameters).get("ability")
            if ability == "can_advance_and_charge":
                consumer_ids.add("catalog-ir:can-advance-and-charge")
            elif ability == "can_fall_back_and_charge":
                consumer_ids.add("catalog-ir:can-fallback-and-charge")
    if clause_is_first_failed_save_damage_replacement(clause):
        consumer_ids.add(CATALOG_IR_FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_CONSUMER_ID)
    if conditional_invulnerable_save_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID)
    proximity_descriptor = conditional_proximity_effects_descriptor_for_clause(clause)
    if proximity_descriptor is not None:
        consumer_ids.add(CATALOG_IR_LEADERSHIP_CHARACTERISTIC_QUERY_CONSUMER_ID)
        if proximity_descriptor.hit_roll_delta is not None:
            consumer_ids.add(CATALOG_IR_LEADING_UNIT_HIT_ROLL_MODIFIER_CONSUMER_ID)
        for characteristic, _delta in proximity_descriptor.weapon_characteristic_deltas:
            token = characteristic.value.replace("_", "-")
            consumer_ids.add(f"catalog-ir:{token}-characteristic-modifier")
    if fight_on_death_descriptor_for_clause(clause) is not None:
        consumer_ids.add(CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID)
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
    if clause_is_leading_unit_hit_roll_modifier(clause):
        consumer_ids.add(CATALOG_IR_LEADING_UNIT_HIT_ROLL_MODIFIER_CONSUMER_ID)
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
                CATALOG_IR_GRANTED_STEALTH_CONSUMER_ID,
                CATALOG_IR_FIGHT_SELECTED_WEAPON_ABILITY_CHOICE_CONSUMER_ID,
                CATALOG_IR_WEAPON_KEYWORD_GRANT_CONSUMER_ID,
                CATALOG_IR_LEADING_UNIT_WOUND_ROLL_MODIFIER_CONSUMER_ID,
                CATALOG_IR_LEADING_UNIT_HIT_ROLL_MODIFIER_CONSUMER_ID,
                CATALOG_IR_FIGHT_ACTIVATION_MOVEMENT_DISTANCE_CONSUMER_ID,
                CATALOG_IR_INVULNERABLE_SAVE_CHARACTERISTIC_QUERY_CONSUMER_ID,
                CATALOG_IR_PASSIVE_HIT_REROLL_CONSUMER_ID,
                CATALOG_IR_FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_CONSUMER_ID,
                CATALOG_IR_FIGHT_ON_DEATH_SOURCE_CONSUMER_ID,
                CATALOG_IR_LEADERSHIP_CHARACTERISTIC_QUERY_CONSUMER_ID,
                CATALOG_IR_BALLISTIC_SKILL_CHARACTERISTIC_MODIFIER_CONSUMER_ID,
                CATALOG_IR_WEAPON_SKILL_CHARACTERISTIC_MODIFIER_CONSUMER_ID,
                CATALOG_IR_HIT_ROLL_REROLL_CONSUMER_ID,
                CATALOG_IR_WOUND_ROLL_REROLL_CONSUMER_ID,
                CATALOG_IR_DAMAGE_ROLL_REROLL_CONSUMER_ID,
                CATALOG_IR_MOVEMENT_ACTION_GRANT_CONSUMER_ID,
                CATALOG_IR_AGILE_MANOEUVRE_ROLL_REROLL_CONSUMER_ID,
                CATALOG_IR_FACTION_RESOURCE_REFUND_ROLL_CONSUMER_ID,
                CATALOG_IR_FIXED_ADVANCE_CONSUMER_ID,
                CATALOG_IR_WEAPON_RANGE_MODIFIER_CONSUMER_ID,
                CATALOG_IR_CHARGE_AFTER_MOVEMENT_ACTION_CONSUMER_ID,
                CATALOG_IR_MOVEMENT_TARGET_PAIR_CONSUMER_ID,
                CATALOG_IR_COMMAND_RESTORATION_CONSUMER_ID,
                *CATALOG_IR_CONDITIONAL_LEADER_ABILITY_CONSUMER_IDS.values(),
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
    return invulnerable_save_descriptor_for_clause(clause) is not None


def clause_is_passive_hit_reroll(clause: RuleClause) -> bool:
    return passive_hit_reroll_descriptor_for_clause(clause) is not None


def clause_is_first_failed_save_damage_replacement(clause: RuleClause) -> bool:
    return first_failed_save_damage_replacement_descriptor_for_clause(clause) is not None


def clause_is_conditional_lone_operative(clause: RuleClause) -> bool:
    if not _is_while_condition_ability_grant(clause, ability="lone_operative"):
        return False
    return any(
        condition.kind is RuleConditionKind.DISTANCE_PREDICATE
        and parameter_payload(condition.parameters).get("predicate") == "within"
        and parameter_payload(condition.parameters).get("object_kind") == "unit"
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


def clause_is_granted_stealth_effect(clause: RuleClause) -> bool:
    conditional = conditional_leader_ability_grant_descriptor_for_clause(clause)
    if conditional is not None:
        return conditional.ability == "stealth"
    return (
        clause.is_supported
        and clause.target is not None
        and clause.target.kind in {RuleTargetKind.SELECTED_TARGET, RuleTargetKind.SELECTED_UNIT}
        and clause.duration is not None
        and len(clause.effects) == 1
        and clause.effects[0].kind is RuleEffectKind.GRANT_ABILITY
        and parameter_payload(clause.effects[0].parameters).get("ability") == "stealth"
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
    return _clause_is_leading_unit_roll_modifier(clause, roll_tokens={"wound", "wound_roll"})


def clause_is_leading_unit_hit_roll_modifier(clause: RuleClause) -> bool:
    return _clause_is_leading_unit_roll_modifier(clause, roll_tokens={"hit", "hit_roll"})


def _clause_is_leading_unit_roll_modifier(
    clause: RuleClause,
    *,
    roll_tokens: set[str],
) -> bool:
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
    if trigger_parameters.get("roll_type") not in roll_tokens:
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
        parameters.get("roll_type") in roll_tokens
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
