"""Typed selected-enemy critical-hit grant; all admission gates are inseparable."""

from __future__ import annotations

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)


def selected_target_hit_threshold_is_supported(clause: RuleClause) -> bool:
    if (
        clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.DICE_ROLL
        or parameter_payload(clause.trigger.parameters) != {"roll_type": "hit"}
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.FRIENDLY_UNIT
        or clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters) != {"endpoint": "turn"}
        or len(clause.effects) != 1
    ):
        return False
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    keyword = parameters.get("required_model_keyword")
    threshold = parameters.get("critical_threshold")
    if (
        effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS
        or set(parameters)
        != {"status", "roll_type", "attack_role", "critical_threshold", "required_model_keyword"}
        or parameters.get("status") != "critical_hit_threshold"
        or parameters.get("roll_type") != "hit"
        or parameters.get("attack_role") != "attacker"
        or type(threshold) is not int
        or not 2 <= threshold <= 6
        or type(keyword) is not str
        or not keyword
        or parameter_payload(clause.target.parameters)
        != {"allegiance": "friendly", "required_keyword": keyword}
    ):
        return False
    return (
        len(clause.conditions) == 2
        and all(
            (
                condition.kind is RuleConditionKind.KEYWORD_GATE
                and parameter_payload(condition.parameters) == {"required_keyword": keyword}
            )
            or (
                condition.kind is RuleConditionKind.TARGET_CONSTRAINT
                and parameter_payload(condition.parameters)
                == {
                    "gate_subject": "attack_target",
                    "relationship": "attack_targets_selected_unit",
                    "target_reference": "selected_unit",
                }
            )
            for condition in clause.conditions
        )
        and {condition.kind for condition in clause.conditions}
        == {RuleConditionKind.KEYWORD_GATE, RuleConditionKind.TARGET_CONSTRAINT}
    )
