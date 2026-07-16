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
EXACT_DATASHEET_RUNTIME_TEMPLATE_IDS = frozenset(
    {
        CONDITIONAL_OBJECTIVE_HIT_REROLL_TEMPLATE_ID,
        PASSIVE_MODEL_CHARACTERISTIC_SET_TEMPLATE_ID,
        FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_TEMPLATE_ID,
        CONDITIONAL_MODEL_FIGHT_ON_DEATH_TEMPLATE_ID,
        CONDITIONAL_RANGED_INVULNERABLE_SAVE_TEMPLATE_ID,
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
    hit_roll_delta: int


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


CatalogDatasheetRuntimeDescriptor = (
    CatalogInvulnerableSaveDescriptor
    | CatalogPassiveHitRerollDescriptor
    | CatalogFirstFailedSaveDamageReplacementDescriptor
    | CatalogConditionalProximityEffectsDescriptor
    | CatalogFightOnDeathDescriptor
    | CatalogConditionalInvulnerableSaveDescriptor
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
    proximity = conditional_proximity_effects_descriptor_for_clause(clause)
    if proximity is not None:
        return proximity
    return None


def conditional_proximity_effects_descriptor_for_clause(
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
