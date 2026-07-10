from __future__ import annotations

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.rule_frequency import optional_ability_frequency_condition
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)


def clause_has_optional_once_per_battle_activation(clause: RuleClause) -> bool:
    return optional_ability_frequency_condition(clause) is not None


def clause_has_unconsumed_once_per_battle_activation(clause: RuleClause) -> bool:
    return clause_has_optional_once_per_battle_activation(
        clause
    ) and not clause_is_runtime_once_per_battle_activation(clause)


def clause_is_runtime_once_per_battle_activation(clause: RuleClause) -> bool:
    return clause_is_fight_start_once_per_battle_activation(
        clause
    ) or clause_is_any_phase_start_once_per_battle_activation(clause)


def clause_is_any_phase_start_once_per_battle_activation(clause: RuleClause) -> bool:
    return _clause_is_phase_start_once_per_battle_activation(clause, phase="any")


def clause_is_fight_start_once_per_battle_activation(clause: RuleClause) -> bool:
    return _clause_is_phase_start_once_per_battle_activation(clause, phase=BattlePhase.FIGHT.value)


def _clause_is_phase_start_once_per_battle_activation(clause: RuleClause, *, phase: str) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog once-per-battle classification requires RuleClause.")
    if not clause.is_supported or not clause.effects:
        return False
    condition = optional_ability_frequency_condition(clause)
    if condition is None or clause.trigger is None or clause.target is None:
        return False
    if clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger = parameter_payload(clause.trigger.parameters)
    if trigger.get("edge") != "start" or trigger.get("phase") != phase:
        return False
    usage_subject = parameter_payload(condition.parameters).get("usage_subject")
    if usage_subject in {"this_model", "bearer"}:
        return clause.target.kind is RuleTargetKind.THIS_MODEL
    if usage_subject == "this_unit":
        return clause.target.kind is RuleTargetKind.THIS_UNIT
    raise GameLifecycleError("Catalog once-per-battle usage_subject is unsupported.")
