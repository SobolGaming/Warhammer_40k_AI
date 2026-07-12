from __future__ import annotations

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID = (
    "catalog-ir:unit-move-completed-battle-shock"
)


def registered_hook_ids() -> tuple[str, ...]:
    return (CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,)


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    if clause_is_supported_unit_move_completed_battle_shock(clause):
        return (CATALOG_IR_UNIT_MOVE_COMPLETED_BATTLE_SHOCK_CONSUMER_ID,)
    return ()


def clause_is_supported_unit_move_completed_battle_shock(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog rule consumer requires RuleClause values.")
    if not clause.is_supported:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if (
        trigger_parameters.get("edge") != "after"
        or trigger_parameters.get("phase") != BattlePhase.CHARGE.value
        or trigger_parameters.get("timing_window") != "charge_move_end"
        or trigger_parameters.get("subject") != "this_unit"
    ):
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    if not _clause_has_enemy_unit_engagement_range_of_this_unit_target(clause):
        return False
    return (
        len(clause.effects) == 1
        and sum(
            1
            for effect in clause.effects
            if effect_is_supported_unit_move_completed_battle_shock(effect)
        )
        == 1
    )


def effect_is_supported_unit_move_completed_battle_shock(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog rule consumer requires RuleEffectSpec values.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("rules_context") == "battle_shock"
        and parameters.get("status") == "force_battle_shock_test"
        and parameters.get("required") is True
        and parameters.get("target_scope") == "enemy_units_within_engagement_range"
        and parameters.get("range_anchor") == "this_unit"
    )


def _clause_has_enemy_unit_engagement_range_of_this_unit_target(clause: RuleClause) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("predicate") == "within_engagement_range"
            and parameters.get("range_kind") == "engagement_range"
            and parameters.get("negated") is False
            and parameters.get("object_kind") == "unit"
            and parameters.get("object_reference") in {"this", "that"}
        ):
            return True
    return False
