"""Exact capability shape for a led unit ranged Cover grant."""

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)

LEADING_COVER_TEMPLATE_ID = "catalog-ir:conditional-leading-ranged-cover"
LEADING_COVER_CONSUMER_ID = "catalog-ir:leading-ranged-cover"


def clause_is_leading_cover(clause: RuleClause) -> bool:
    return (
        clause.is_supported
        and clause.template_id == LEADING_COVER_TEMPLATE_ID
        and clause.trigger is None
        and clause.target is not None
        and clause.target.kind is RuleTargetKind.THIS_UNIT
        and not clause.target.parameters
        and len(clause.conditions) == 1
        and clause.conditions[0].kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(clause.conditions[0].parameters)
        == {"relationship": "this_model_leading_unit"}
        and len(clause.effects) == 1
        and clause.effects[0].kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
        and parameter_payload(clause.effects[0].parameters)
        == {"attack_kind": "ranged", "operation": "grant", "status": "benefit_of_cover"}
        and clause.duration is not None
        and clause.duration.kind is RuleDurationKind.WHILE_CONDITION_TRUE
        and not clause.duration.parameters
    )
