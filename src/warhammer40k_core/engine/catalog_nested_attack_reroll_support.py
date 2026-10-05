"""Exact structured support for the bounded nested attack-reroll shape."""

from __future__ import annotations

from warhammer40k_core.rules.nested_attack_reroll_parser import NESTED_ATTACK_REROLL_TEMPLATE_ID
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)


def nested_attack_reroll_clause_is_supported(clause: RuleClause) -> bool:
    if (
        not clause.is_supported
        or clause.template_id != NESTED_ATTACK_REROLL_TEMPLATE_ID
        or clause.trigger is not None
        or clause.duration is not None
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or len(clause.conditions) != 1
        or len(clause.effects) != 1
    ):
        return False
    parent = clause.conditions[0]
    effect = clause.effects[0]
    parameters = parameter_payload(effect.parameters)
    value = parameters.get("reroll_unmodified_value")
    return (
        parent.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(parent.parameters)
        == {"gate_subject": "attack_target", "target_constraint": "closest_eligible"}
        and effect.kind is RuleEffectKind.REROLL_PERMISSION
        and type(value) is int
        and 1 <= value <= 6
        and parameters
        == {
            "attack_kind": "ranged",
            "roll_type": "hit",
            "reroll_unmodified_value": value,
            "full_reroll_if_target_within_opponent_controlled_objective_range": True,
        }
        and parameters["full_reroll_if_target_within_opponent_controlled_objective_range"] is True
    )


def nested_attack_reroll_clause_has_invalid_shape(clause: RuleClause) -> bool:
    return (
        clause.template_id == NESTED_ATTACK_REROLL_TEMPLATE_ID
        and not nested_attack_reroll_clause_is_supported(clause)
    )
