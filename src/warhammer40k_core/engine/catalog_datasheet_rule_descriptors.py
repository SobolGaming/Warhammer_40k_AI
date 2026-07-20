from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CONDITIONAL_OBJECTIVE_HIT_REROLL_TEMPLATE_ID = "phase17c:conditional-objective-hit-reroll"
PASSIVE_MODEL_CHARACTERISTIC_SET_TEMPLATE_ID = "phase17c:passive-model-characteristic-set"
FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_TEMPLATE_ID = "phase17c:first-failed-save-damage-replacement"
CONDITIONAL_MODEL_FIGHT_ON_DEATH_TEMPLATE_ID = "phase17c:conditional-model-fight-on-death"
CONDITIONAL_RANGED_INVULNERABLE_SAVE_TEMPLATE_ID = "phase17c:conditional-ranged-invulnerable-save"
CONDITIONAL_RANGED_ATTACK_FULL_REROLLS_TEMPLATE_ID = (
    "phase17l:conditional-ranged-attack-full-rerolls"
)
OPTIONAL_NORMAL_MOVE_GRANT_TEMPLATE_ID = (
    "phase17l:optional-normal-move-characteristic-set-and-phase-end-risk"
)
EXACT_DATASHEET_RUNTIME_TEMPLATE_IDS = frozenset(
    {
        CONDITIONAL_OBJECTIVE_HIT_REROLL_TEMPLATE_ID,
        PASSIVE_MODEL_CHARACTERISTIC_SET_TEMPLATE_ID,
        FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_TEMPLATE_ID,
        CONDITIONAL_MODEL_FIGHT_ON_DEATH_TEMPLATE_ID,
        CONDITIONAL_RANGED_INVULNERABLE_SAVE_TEMPLATE_ID,
        CONDITIONAL_RANGED_ATTACK_FULL_REROLLS_TEMPLATE_ID,
        OPTIONAL_NORMAL_MOVE_GRANT_TEMPLATE_ID,
    }
)


@dataclass(frozen=True, slots=True)
class CatalogInvulnerableSaveDescriptor:
    target_number: int


@dataclass(frozen=True, slots=True)
class CatalogPassiveHitRerollDescriptor:
    reroll_unmodified_value: int
    full_reroll_if_target_within_objective_range: bool


@dataclass(frozen=True, slots=True)
class CatalogFirstFailedSaveDamageReplacementDescriptor:
    replacement_damage: int


@dataclass(frozen=True, slots=True)
class CatalogConditionalProximityEffectsDescriptor:
    distance_inches: float
    required_keyword_sequence: tuple[str, ...]
    characteristic: Characteristic
    characteristic_value: int
    hit_roll_delta: int | None
    weapon_characteristic_deltas: tuple[tuple[Characteristic, int], ...] = ()


@dataclass(frozen=True, slots=True)
class CatalogFightOnDeathDescriptor:
    trigger_roll_threshold: int
    trigger_roll_type: str
    requires_destroyed_by_melee_attack: bool
    requires_not_fought_this_phase: bool


@dataclass(frozen=True, slots=True)
class CatalogConditionalInvulnerableSaveDescriptor:
    target_number: int
    attack_kind: str


@dataclass(frozen=True, slots=True)
class CatalogConditionalAttackRerollDescriptor:
    attack_kind: str
    phase: str
    required_target_keywords: tuple[str, ...]
    roll_types: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class CatalogMovementActionGrantDescriptor:
    movement_action: str
    movement_characteristic: int
    charge_forbidden: bool
    phase_end_roll_success_value: int
    mortal_wounds_per_success: int


CatalogDatasheetRuntimeDescriptor = (
    CatalogInvulnerableSaveDescriptor
    | CatalogPassiveHitRerollDescriptor
    | CatalogFirstFailedSaveDamageReplacementDescriptor
    | CatalogConditionalProximityEffectsDescriptor
    | CatalogFightOnDeathDescriptor
    | CatalogConditionalInvulnerableSaveDescriptor
    | CatalogConditionalAttackRerollDescriptor
    | CatalogMovementActionGrantDescriptor
)


def clause_uses_exact_datasheet_runtime_template(clause: RuleClause) -> bool:
    return clause.template_id in EXACT_DATASHEET_RUNTIME_TEMPLATE_IDS


def exact_datasheet_runtime_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogDatasheetRuntimeDescriptor | None:
    if clause.template_id == CONDITIONAL_OBJECTIVE_HIT_REROLL_TEMPLATE_ID:
        return passive_hit_reroll_descriptor_for_clause(clause)
    if clause.template_id == PASSIVE_MODEL_CHARACTERISTIC_SET_TEMPLATE_ID:
        return invulnerable_save_descriptor_for_clause(clause)
    if clause.template_id == FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_TEMPLATE_ID:
        return first_failed_save_damage_replacement_descriptor_for_clause(clause)
    if clause.template_id == CONDITIONAL_MODEL_FIGHT_ON_DEATH_TEMPLATE_ID:
        return fight_on_death_descriptor_for_clause(clause)
    if clause.template_id == CONDITIONAL_RANGED_INVULNERABLE_SAVE_TEMPLATE_ID:
        return conditional_invulnerable_save_descriptor_for_clause(clause)
    if clause.template_id == CONDITIONAL_RANGED_ATTACK_FULL_REROLLS_TEMPLATE_ID:
        return conditional_attack_reroll_descriptor_for_clause(clause)
    if clause.template_id == OPTIONAL_NORMAL_MOVE_GRANT_TEMPLATE_ID:
        return movement_action_grant_descriptor_for_clause(clause)
    proximity = conditional_proximity_effects_descriptor_for_clause(clause)
    if proximity is not None:
        return proximity
    return None


def movement_action_grant_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogMovementActionGrantDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != OPTIONAL_NORMAL_MOVE_GRANT_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.UNIT_SELECTED
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.conditions
        or clause.duration is None
        or len(clause.effects) != 3
    ):
        return None
    trigger = parameter_payload(clause.trigger.parameters)
    duration = parameter_payload(clause.duration.parameters)
    movement_effect, charge_effect, mortal_effect = clause.effects
    movement_parameters = parameter_payload(movement_effect.parameters)
    charge_parameters = parameter_payload(charge_effect.parameters)
    mortal_parameters = parameter_payload(mortal_effect.parameters)
    if (
        trigger
        != {
            "action": "normal_move",
            "owner": "active_player",
            "optional": True,
            "phase": "movement",
            "subject": "this_unit",
            "timing_window": "selected_to_make_movement_action",
        }
        or clause.duration.kind.value != "until_timing_endpoint"
        or duration != {"endpoint": "turn"}
        or movement_effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
        or movement_parameters
        != {
            "characteristic": "movement",
            "target_scope": "models_in_this_unit",
            "value": 24,
        }
        or charge_effect.kind is not RuleEffectKind.GRANT_ABILITY
        or charge_parameters != {"ability": "charge_forbidden", "target_scope": "this_unit"}
        or mortal_effect.kind is not RuleEffectKind.INFLICT_MORTAL_WOUNDS
        or mortal_parameters
        != {
            "damage_kind": "mortal_wounds",
            "mortal_wounds_expression": "1",
            "roll_count_scope": "each_model_in_this_unit_at_phase_end",
            "roll_expression": "D6",
            "success_values": ("1",),
            "target_scope": "this_unit",
            "timing_window": "end_of_phase",
        }
    ):
        return None
    return CatalogMovementActionGrantDescriptor(
        movement_action="normal_move",
        movement_characteristic=24,
        charge_forbidden=True,
        phase_end_roll_success_value=1,
        mortal_wounds_per_success=1,
    )


def conditional_attack_reroll_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalAttackRerollDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != CONDITIONAL_RANGED_ATTACK_FULL_REROLLS_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 1
        or len(clause.effects) != 3
    ):
        return None
    trigger = parameter_payload(clause.trigger.parameters)
    roll_types = trigger.get("roll_types")
    condition = clause.conditions[0]
    condition_parameters = parameter_payload(condition.parameters)
    required_keywords = condition_parameters.get("required_keywords")
    if (
        trigger.get("attack_kind") != "ranged"
        or trigger.get("owner") != "active_player"
        or trigger.get("phase") != "shooting"
        or trigger.get("subject") != "this_unit"
        or roll_types != ("hit", "wound", "damage")
        or condition.kind is not RuleConditionKind.KEYWORD_GATE
        or condition_parameters.get("gate_subject") != "target_unit"
        or condition_parameters.get("keyword_match") != "any"
        or required_keywords != ("MONSTER", "VEHICLE")
    ):
        return None
    effect_roll_types: list[str] = []
    for effect in clause.effects:
        parameters = parameter_payload(effect.parameters)
        roll_type = parameters.get("roll_type")
        if (
            effect.kind is not RuleEffectKind.REROLL_PERMISSION
            or parameters.get("selection") != "whole_roll"
            or roll_type not in {"hit_roll", "wound_roll", "damage_roll"}
            or set(parameters) != {"roll_type", "selection"}
        ):
            return None
        effect_roll_types.append(str(roll_type))
    if tuple(effect_roll_types) != ("hit_roll", "wound_roll", "damage_roll"):
        return None
    return CatalogConditionalAttackRerollDescriptor(
        attack_kind="ranged",
        phase="shooting",
        required_target_keywords=("MONSTER", "VEHICLE"),
        roll_types=tuple(effect_roll_types),
    )


def conditional_proximity_effects_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalProximityEffectsDescriptor | None:
    descriptor = _unit_proximity_roll_descriptor_for_clause(clause)
    if descriptor is not None:
        return descriptor
    return _model_proximity_weapon_descriptor_for_clause(clause)


def _unit_proximity_roll_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalProximityEffectsDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != "phase17c:characteristic-set"
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or parameter_payload(clause.trigger.parameters) != {"roll_type": "hit"}
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 1
        or len(clause.effects) != 2
    ):
        return None
    condition = clause.conditions[0]
    condition_parameters = parameter_payload(condition.parameters)
    required_keywords = condition_parameters.get("required_keyword_sequence")
    distance = condition_parameters.get("distance_inches")
    if (
        condition.kind is not RuleConditionKind.DISTANCE_PREDICATE
        or condition_parameters.get("predicate") != "within"
        or condition_parameters.get("negated") is not False
        or condition_parameters.get("object_allegiance") != "friendly"
        or condition_parameters.get("object_kind") != "model"
        or condition_parameters.get("object_quantity") != "one_or_more"
        or condition_parameters.get("subject") != "this_unit"
        or not isinstance(distance, int | float)
        or type(distance) is bool
        or distance <= 0
        or not isinstance(required_keywords, tuple)
        or not required_keywords
        or not all(type(keyword) is str and bool(keyword) for keyword in required_keywords)
    ):
        return None
    characteristic_effect, hit_effect = clause.effects
    characteristic_parameters = parameter_payload(characteristic_effect.parameters)
    hit_parameters = parameter_payload(hit_effect.parameters)
    raw_value = characteristic_parameters.get("value")
    hit_roll_delta = hit_parameters.get("delta")
    if (
        characteristic_effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
        or characteristic_parameters.get("characteristic") != Characteristic.LEADERSHIP.value
        or type(raw_value) is not str
        or not raw_value.endswith("+")
        or not raw_value[:-1].isdigit()
        or hit_effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL
        or hit_parameters.get("roll_type") != "hit"
        or type(hit_roll_delta) is not int
    ):
        return None
    value = int(raw_value[:-1])
    if not 2 <= value <= 8:
        return None
    return CatalogConditionalProximityEffectsDescriptor(
        distance_inches=float(distance),
        required_keyword_sequence=required_keywords,
        characteristic=Characteristic.LEADERSHIP,
        characteristic_value=value,
        hit_roll_delta=hit_roll_delta,
    )


def _model_proximity_weapon_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalProximityEffectsDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != "phase17c:characteristic-set"
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 1
        or len(clause.effects) != 3
    ):
        return None
    condition = clause.conditions[0]
    condition_parameters = parameter_payload(condition.parameters)
    required_keywords = condition_parameters.get("required_keyword_sequence")
    distance = condition_parameters.get("distance_inches")
    if (
        condition.kind is not RuleConditionKind.DISTANCE_PREDICATE
        or condition_parameters.get("predicate") != "within"
        or condition_parameters.get("negated") is not False
        or condition_parameters.get("object_allegiance") != "friendly"
        or condition_parameters.get("object_kind") != "model"
        or condition_parameters.get("object_quantity") != "one_or_more"
        or condition_parameters.get("subject") != "this_model"
        or not isinstance(distance, int | float)
        or type(distance) is bool
        or distance <= 0
        or not isinstance(required_keywords, tuple)
        or not required_keywords
        or not all(type(keyword) is str and bool(keyword) for keyword in required_keywords)
    ):
        return None
    weapon_deltas: list[tuple[Characteristic, int]] = []
    characteristic_value: int | None = None
    for effect in clause.effects:
        parameters = parameter_payload(effect.parameters)
        if effect.kind is RuleEffectKind.MODIFY_CHARACTERISTIC:
            characteristic_token = parameters.get("characteristic")
            delta = parameters.get("delta")
            if (
                parameters.get("target_scope") != "weapons_equipped_by_this_model"
                or characteristic_token
                not in {
                    Characteristic.BALLISTIC_SKILL.value,
                    Characteristic.WEAPON_SKILL.value,
                }
                or type(delta) is not int
                or delta == 0
            ):
                return None
            weapon_deltas.append((Characteristic(str(characteristic_token)), delta))
            continue
        raw_value = parameters.get("value")
        if (
            effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
            or parameters.get("characteristic") != Characteristic.LEADERSHIP.value
            or type(raw_value) is not str
            or not raw_value.endswith("+")
            or not raw_value[:-1].isdigit()
        ):
            return None
        characteristic_value = int(raw_value[:-1])
    if (
        characteristic_value is None
        or not 2 <= characteristic_value <= 8
        or tuple(characteristic for characteristic, _delta in weapon_deltas)
        != (Characteristic.BALLISTIC_SKILL, Characteristic.WEAPON_SKILL)
    ):
        return None
    return CatalogConditionalProximityEffectsDescriptor(
        distance_inches=float(distance),
        required_keyword_sequence=required_keywords,
        characteristic=Characteristic.LEADERSHIP,
        characteristic_value=characteristic_value,
        hit_roll_delta=None,
        weapon_characteristic_deltas=tuple(weapon_deltas),
    )


def fight_on_death_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogFightOnDeathDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != CONDITIONAL_MODEL_FIGHT_ON_DEATH_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.MODEL_DESTROYED
        or parameter_payload(clause.trigger.parameters)
        != {
            "destroyed_target": "this_model",
            "timing_window": "after_attacking_unit_finished_attacks",
        }
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 2
        or len(clause.effects) != 1
    ):
        return None
    conditions = {
        tuple(sorted(parameter_payload(condition.parameters).items()))
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.TARGET_CONSTRAINT
    }
    if conditions != {
        (
            ("attack_kind", "melee"),
            ("gate_subject", "destroyed_model"),
            ("relationship", "destroyed_by_attack"),
        ),
        (
            ("gate_subject", "destroyed_model"),
            ("relationship", "has_not_fought_this_phase"),
        ),
    }:
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    threshold = parameters.get("trigger_roll_threshold")
    roll_type = parameters.get("trigger_roll_type")
    if (
        effect.kind is not RuleEffectKind.GRANT_ABILITY
        or parameters.get("ability") != "fight_on_death"
        or parameters.get("optional") is not True
        or type(threshold) is not int
        or not 2 <= threshold <= 6
        or type(roll_type) is not str
        or not roll_type
    ):
        return None
    return CatalogFightOnDeathDescriptor(
        trigger_roll_threshold=threshold,
        trigger_roll_type=roll_type,
        requires_destroyed_by_melee_attack=True,
        requires_not_fought_this_phase=True,
    )


def conditional_invulnerable_save_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogConditionalInvulnerableSaveDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != CONDITIONAL_RANGED_INVULNERABLE_SAVE_TEMPLATE_ID
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 1
        or len(clause.effects) != 1
    ):
        return None
    condition = clause.conditions[0]
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT or parameter_payload(
        condition.parameters
    ) != {"attack_kind": "ranged", "gate_subject": "incoming_attack"}:
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    value = parameters.get("value")
    if (
        effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
        or parameters.get("characteristic") != Characteristic.INVULNERABLE_SAVE.value
        or type(value) is not int
        or not 2 <= value <= 6
    ):
        return None
    return CatalogConditionalInvulnerableSaveDescriptor(
        target_number=value,
        attack_kind="ranged",
    )


def invulnerable_save_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogInvulnerableSaveDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != PASSIVE_MODEL_CHARACTERISTIC_SET_TEMPLATE_ID
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or clause.target.parameters
        or clause.duration is not None
        or clause.conditions
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    value = parameters.get("value")
    if (
        effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
        or set(parameters) != {"characteristic", "value"}
        or parameters.get("characteristic") != Characteristic.INVULNERABLE_SAVE.value
        or type(value) is not int
        or not 2 <= value <= 6
    ):
        return None
    return CatalogInvulnerableSaveDescriptor(target_number=value)


def passive_hit_reroll_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogPassiveHitRerollDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != CONDITIONAL_OBJECTIVE_HIT_REROLL_TEMPLATE_ID
        or clause.trigger is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is not None
        or clause.conditions
        or len(clause.effects) != 1
    ):
        return None
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    reroll_value = parameters.get("reroll_unmodified_value")
    objective_upgrade = parameters.get("full_reroll_if_target_within_objective_range")
    if (
        effect.kind is not RuleEffectKind.REROLL_PERMISSION
        or set(parameters)
        != {
            "full_reroll_if_target_within_objective_range",
            "reroll_unmodified_value",
            "roll_type",
        }
        or parameters.get("roll_type") != "hit"
        or type(reroll_value) is not int
        or not 1 <= reroll_value <= 6
        or type(objective_upgrade) is not bool
    ):
        return None
    return CatalogPassiveHitRerollDescriptor(
        reroll_unmodified_value=reroll_value,
        full_reroll_if_target_within_objective_range=objective_upgrade,
    )


def first_failed_save_damage_replacement_descriptor_for_clause(
    clause: RuleClause,
) -> CatalogFirstFailedSaveDamageReplacementDescriptor | None:
    if (
        not clause.is_supported
        or clause.template_id != FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.effects) != 1
        or len(clause.conditions) != 1
    ):
        return None
    trigger = parameter_payload(clause.trigger.parameters)
    condition = clause.conditions[0]
    frequency = parameter_payload(condition.parameters)
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    if (
        trigger
        != {
            "outcome": "failed",
            "roll_type": "attack_sequence.save",
            "timing_window": "after_failed_saving_throw",
        }
        or condition.kind is not RuleConditionKind.FREQUENCY_LIMIT
        or frequency
        != {
            "activation_kind": "automatic_first_occurrence",
            "max_uses": 1,
            "scope": "turn",
            "usage_subject": "bearers_unit",
        }
        or effect.kind is not RuleEffectKind.SET_CHARACTERISTIC
        or parameters
        != {
            "attack_role": "defender",
            "characteristic": Characteristic.DAMAGE.value,
            "value": 0,
        }
    ):
        return None
    return CatalogFirstFailedSaveDamageReplacementDescriptor(replacement_damage=0)
