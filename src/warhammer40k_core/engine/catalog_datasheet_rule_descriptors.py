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
EXACT_DATASHEET_RUNTIME_TEMPLATE_IDS = frozenset(
    {
        CONDITIONAL_OBJECTIVE_HIT_REROLL_TEMPLATE_ID,
        PASSIVE_MODEL_CHARACTERISTIC_SET_TEMPLATE_ID,
        FIRST_FAILED_SAVE_DAMAGE_REPLACEMENT_TEMPLATE_ID,
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


CatalogDatasheetRuntimeDescriptor = (
    CatalogInvulnerableSaveDescriptor
    | CatalogPassiveHitRerollDescriptor
    | CatalogFirstFailedSaveDamageReplacementDescriptor
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
    return None


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
