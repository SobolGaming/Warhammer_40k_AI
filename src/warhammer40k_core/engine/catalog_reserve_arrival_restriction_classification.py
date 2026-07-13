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

CATALOG_IR_RESERVE_ARRIVAL_RESTRICTION_CONSUMER_ID = "catalog-ir:reserve-arrival-restriction"


def clause_is_reserve_arrival_restriction(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Reserve-arrival restriction classifier requires RuleClause.")
    if not clause.is_supported or clause.trigger is None:
        return False
    if clause.trigger.kind is not RuleTriggerKind.SETUP:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    trigger_parameters = parameter_payload(clause.trigger.parameters)
    target_parameters = parameter_payload(clause.target.parameters)
    if (
        trigger_parameters.get("setup_source") != "reserves"
        or trigger_parameters.get("subject") != "enemy_unit"
        or target_parameters.get("allegiance") != "enemy"
        or target_parameters.get("setup_source") != "reserves"
    ):
        return False
    if clause.duration is not None or len(clause.conditions) != 1 or len(clause.effects) != 1:
        return False
    effect = clause.effects[0]
    effect_parameters = parameter_payload(effect.parameters)
    return (
        effect.kind is RuleEffectKind.PLACEMENT_RESTRICTION
        and effect_parameters.get("allowed") is False
        and effect_parameters.get("placement_source") == "reserves"
        and _restriction_distance_inches_or_none(clause) is not None
    )


def reserve_arrival_restriction_distance_inches(clause: RuleClause) -> float:
    if not clause_is_reserve_arrival_restriction(clause):
        raise GameLifecycleError("RuleClause is not a reserve-arrival restriction.")
    distance = _restriction_distance_inches_or_none(clause)
    if distance is None:
        raise GameLifecycleError("Reserve-arrival restriction distance is missing.")
    return distance


def _restriction_distance_inches_or_none(clause: RuleClause) -> float | None:
    matching = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    if len(matching) != 1:
        return None
    parameters = parameter_payload(matching[0].parameters)
    if (
        parameters.get("predicate") != "within"
        or parameters.get("range_kind") != "numeric_range"
        or parameters.get("object_kind") != "model"
        or parameters.get("object_reference") != "this_model"
    ):
        return None
    raw_distance = parameters.get("distance_inches")
    if not isinstance(raw_distance, int | float) or type(raw_distance) is bool:
        return None
    distance = float(raw_distance)
    return distance if distance > 0 else None
