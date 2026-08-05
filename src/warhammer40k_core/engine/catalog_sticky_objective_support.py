from __future__ import annotations

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

COMMAND_END_STICKY_OBJECTIVE_TEMPLATE_ID = "phase17n:command-end-sticky-objective-control"
CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID = (
    "catalog-ir:command-end-sticky-objective-control"
)


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if clause_is_command_end_sticky_objective_control(clause):
        return (CATALOG_IR_COMMAND_END_STICKY_OBJECTIVE_CONSUMER_ID,)
    return ()


def clause_has_invalid_exact_shape(clause: RuleClause) -> bool:
    return (
        clause.template_id == COMMAND_END_STICKY_OBJECTIVE_TEMPLATE_ID
        and not clause_is_command_end_sticky_objective_control(clause)
    )


def clause_is_command_end_sticky_objective_control(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Sticky-objective RuleIR support requires RuleClause.")
    if (
        not clause.is_supported
        or clause.template_id != COMMAND_END_STICKY_OBJECTIVE_TEMPLATE_ID
        or clause.trigger is None
        or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW
        or parameter_payload(clause.trigger.parameters)
        != {
            "edge": "end",
            "owner": "active_player",
            "phase": "command",
            "subject": "this_unit",
        }
        or clause.target is None
        or clause.target.kind is not RuleTargetKind.THIS_UNIT
        or clause.target.parameters
        or clause.duration is not None
        or len(clause.conditions) != 1
        or len(clause.effects) != 1
    ):
        return False
    condition = clause.conditions[0]
    effect = clause.effects[0]
    return (
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters)
        == {
            "gate_subject": "source_unit",
            "relationship": "source_unit_within_controlled_objective",
        }
        and effect.kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
        and parameter_payload(effect.parameters)
        == {
            "objective_scope": "controlled_objective_within_source_unit_range",
            "retention_end_condition": ("opponent_level_of_control_greater_than_source_player"),
            "status": "sticky_objective_control",
        }
    )
