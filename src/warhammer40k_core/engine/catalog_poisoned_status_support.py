from __future__ import annotations

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    parameter_payload,
)

CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID = "catalog-ir:poisoned-command-mortal-wounds"
POISONED_STATUS_TEMPLATE_ID = "phase17k:persistent-selected-target-status"


def clause_is_poisoned_command_mortal_wounds_status(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog poisoned status classifier requires RuleClause.")
    return (
        clause.is_supported
        and clause.template_id == POISONED_STATUS_TEMPLATE_ID
        and clause.trigger is None
        and not clause.conditions
        and clause.target is not None
        and clause.target.kind in {RuleTargetKind.SELECTED_TARGET, RuleTargetKind.SELECTED_UNIT}
        and not clause.target.parameters
        and clause.duration is not None
        and clause.duration.kind is RuleDurationKind.PERMANENT
        and len(clause.effects) == 1
        and clause.effects[0].kind is RuleEffectKind.SET_CONTEXTUAL_STATUS
        and parameter_payload(clause.effects[0].parameters)
        == {
            "command_phase_mortal_wounds": "D3",
            "command_phase_roll_threshold": 4,
            "command_phase_timing": "start_each_players_command_phase",
            "status": "poisoned",
        }
    )


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if clause_is_poisoned_command_mortal_wounds_status(clause):
        return (CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,)
    return ()


def registered_consumer_ids() -> tuple[str, ...]:
    return (CATALOG_IR_POISONED_COMMAND_MORTAL_WOUNDS_CONSUMER_ID,)
