from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

_SUPPORTED_ATTACK_ROLL_TYPES = frozenset({"hit", "wound"})


def clause_effect_is_supported_this_model_attack_roll_modifier(
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog attack condition requires RuleClause values.")
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog attack condition requires RuleEffectSpec values.")
    if (
        not clause.is_supported
        or clause.duration is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_MODEL
        or parameter_payload(clause.target.parameters)
        or effect.kind is not RuleEffectKind.MODIFY_DICE_ROLL
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or len(clause.effects) != 1
        or clause.effects[0] != effect
    ):
        return False
    effect_parameters = parameter_payload(effect.parameters)
    roll_type = effect_parameters.get("roll_type")
    if type(roll_type) is not str or roll_type not in _SUPPORTED_ATTACK_ROLL_TYPES:
        return False
    if set(effect_parameters) != {"delta", "roll_type"}:
        return False
    if type(effect_parameters.get("delta")) is not int:
        return False
    if not _trigger_parameters_are_supported(
        parameters=parameter_payload(clause.trigger.parameters),
        roll_type=roll_type,
    ):
        return False
    return bool(clause.conditions) and all(
        condition_is_supported_this_model_attack_strength_gate(condition)
        for condition in clause.conditions
    )


def condition_is_supported_this_model_attack_strength_gate(
    condition: RuleCondition,
) -> bool:
    if type(condition) is not RuleCondition:
        raise GameLifecycleError("Catalog attack condition requires RuleCondition values.")
    if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
        return False
    parameters = parameter_payload(condition.parameters)
    if parameters.get("relationship") != "this_model_makes_attack":
        return False
    if parameters == {
        "gate_subject": "attack_target",
        "relationship": "this_model_makes_attack",
        "target_allegiance": "enemy",
        "target_constraint": "target_not_below_half_strength",
    }:
        return True
    return parameters in (
        {
            "gate_subject": "source_unit",
            "relationship": "this_model_makes_attack",
            "target_constraint": "source_unit_below_starting_strength",
        },
        {
            "gate_subject": "source_unit",
            "relationship": "this_model_makes_attack",
            "target_constraint": "source_unit_below_half_strength",
        },
    )


def _trigger_parameters_are_supported(
    *,
    parameters: Mapping[str, object],
    roll_type: str,
) -> bool:
    if parameters == {"roll_type": roll_type}:
        return True
    return parameters == {
        "actor": "this_model",
        "roll_type": roll_type,
        "target_allegiance": "enemy",
        "timing_window": f"attack_sequence.{roll_type}",
    }
