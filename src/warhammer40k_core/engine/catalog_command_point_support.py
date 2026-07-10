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

CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID = "catalog-ir:command-point-gain"
CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID = "catalog-ir:stratagem-cost-modifier"


def command_point_consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    _validate_clause(clause)
    consumer_ids: list[str] = []
    if clause_is_supported_command_point_gain(clause):
        consumer_ids.append(CATALOG_IR_COMMAND_POINT_GAIN_CONSUMER_ID)
    if clause_is_supported_stratagem_cost_modifier(clause):
        consumer_ids.append(CATALOG_IR_STRATAGEM_COST_MODIFIER_CONSUMER_ID)
    return tuple(consumer_ids)


def clause_is_supported_command_point_gain(clause: RuleClause) -> bool:
    _validate_clause(clause)
    if not clause.is_supported or not _has_source_player_target(clause):
        return False
    if not _has_single_command_point_effect(clause, operation="gain"):
        return False
    return clause_is_supported_destroyed_unit_command_point_gain(
        clause
    ) or clause_is_supported_phase_command_point_gain(clause)


def clause_is_supported_destroyed_unit_command_point_gain(clause: RuleClause) -> bool:
    _validate_clause(clause)
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.UNIT_DESTROYED:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if trigger_parameters != {
        "actor": "this_model",
        "destroyed_allegiance": "enemy",
        "destroyed_unit_kind": "unit",
    }:
        return False
    if not _has_target_constraint(
        clause,
        relationship="this_model_destroyed_unit",
        gate_subject="destroyed_unit",
    ):
        return False
    return any(_is_destroyed_unit_keyword_gate(condition) for condition in clause.conditions)


def clause_is_supported_phase_end_leadership_command_point_gain(
    clause: RuleClause,
) -> bool:
    if not clause_is_supported_phase_command_point_gain(clause):
        return False
    trigger = clause.trigger
    if trigger is None or parameter_payload(trigger.parameters).get("edge") != "end":
        return False
    dice_gates = _dice_roll_gates(clause)
    return len(dice_gates) == 1 and _is_supported_leadership_gate(dice_gates[0])


def clause_is_supported_phase_command_point_gain(clause: RuleClause) -> bool:
    _validate_clause(clause)
    if not clause.is_supported or not _has_source_player_target(clause):
        return False
    if not _has_single_command_point_effect(clause, operation="gain"):
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    if (
        trigger_parameters.get("edge") not in {"start", "end"}
        or trigger_parameters.get("owner") != "active_player"
        or trigger_parameters.get("phase")
        not in {"command", "movement", "shooting", "charge", "fight"}
    ):
        return False
    if any(
        condition.kind
        not in {RuleConditionKind.TARGET_CONSTRAINT, RuleConditionKind.DICE_ROLL_GATE}
        for condition in clause.conditions
    ):
        return False
    target_constraints = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.TARGET_CONSTRAINT
    )
    if len(target_constraints) > 1:
        return False
    if target_constraints and not _has_target_constraint(
        clause,
        relationship="source_model_on_battlefield",
        gate_subject="source_model",
    ):
        return False
    dice_gates = _dice_roll_gates(clause)
    if len(dice_gates) > 1:
        return False
    return not dice_gates or _is_supported_phase_gain_gate(dice_gates[0])


def _dice_roll_gates(clause: RuleClause) -> tuple[RuleCondition, ...]:
    return tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.DICE_ROLL_GATE
    )


def _is_supported_phase_gain_gate(condition: RuleCondition) -> bool:
    return _is_supported_leadership_gate(condition) or _is_supported_fixed_roll_gate(condition)


def _is_supported_leadership_gate(condition: RuleCondition) -> bool:
    return parameter_payload(condition.parameters) == {
        "comparison": "greater_or_equal",
        "roll_count": 2,
        "roll_expression": "2D6",
        "roll_type": "leadership",
        "success_threshold_source": "target_leadership",
        "test_target": "this_model",
    }


def _is_supported_fixed_roll_gate(condition: RuleCondition) -> bool:
    parameters = parameter_payload(condition.parameters)
    roll_count = parameters.get("roll_count")
    threshold = parameters.get("success_threshold")
    expression = parameters.get("roll_expression")
    return (
        parameters.get("comparison") == "greater_or_equal"
        and type(roll_count) is int
        and roll_count > 0
        and expression == ("D6" if roll_count == 1 else f"{roll_count}D6")
        and parameters.get("roll_type") == "command_point_gain"
        and type(threshold) is int
        and threshold > 0
    )


def clause_is_supported_stratagem_cost_modifier(clause: RuleClause) -> bool:
    _validate_clause(clause)
    if not clause.is_supported:
        return False
    trigger = clause.trigger
    if trigger is None or trigger.kind is not RuleTriggerKind.UNIT_SELECTED:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.STRATAGEM_USE:
        return False
    trigger_parameters = parameter_payload(trigger.parameters)
    stratagem_user = trigger_parameters.get("stratagem_user")
    relationship = trigger_parameters.get("source_relationship")
    allegiance = trigger_parameters.get("selected_unit_allegiance")
    usage_scope = trigger_parameters.get("usage_scope")
    if (
        trigger_parameters.get("selection") != "stratagem_target"
        or trigger_parameters.get("timing_window") != "after_unit_selected_as_stratagem_target"
        or stratagem_user not in {"source_player", "opponent"}
        or relationship
        not in {
            "stratagem_targets_source_unit",
            "stratagem_targets_unit_within_source_model_range",
        }
        or allegiance != ("friendly" if stratagem_user == "source_player" else "enemy")
        or usage_scope not in {"army_ability", "source_model"}
    ):
        return False
    if not _has_target_constraint(
        clause,
        relationship=str(relationship),
        gate_subject="stratagem_target",
        selected_unit_allegiance=str(allegiance),
    ):
        return False
    if relationship == "stratagem_targets_unit_within_source_model_range" and not any(
        _is_supported_numeric_distance(condition) for condition in clause.conditions
    ):
        return False
    effects = _command_point_effects(clause)
    if len(effects) != 1:
        return False
    parameters = parameter_payload(effects[0].parameters)
    delta = parameters.get("delta")
    if type(delta) is not int or delta == 0:
        return False
    if parameters.get("affected_player") != stratagem_user:
        return False
    if delta > 0 and stratagem_user != "opponent":
        return False
    if delta < 0 and stratagem_user != "source_player":
        return False
    return (
        parameters.get("operation") == "modify_stratagem_cost"
        and parameters.get("application_scope") == "current_stratagem_use"
        and parameters.get("minimum_cost") == 0
        and type(parameters.get("optional")) is bool
        and parameters.get("stacking") in {"cumulative", "non_cumulative_cost_increase"}
        and _has_supported_cost_frequency(clause)
    )


def command_point_effect(clause: RuleClause) -> RuleEffectSpec:
    _validate_clause(clause)
    effects = _command_point_effects(clause)
    if len(effects) != 1:
        raise GameLifecycleError("Command-point RuleIR clause requires exactly one CP effect.")
    return effects[0]


def command_point_effect_parameters(clause: RuleClause) -> Mapping[str, object]:
    return parameter_payload(command_point_effect(clause).parameters)


def _has_source_player_target(clause: RuleClause) -> bool:
    if clause.target is None or clause.target.kind is not RuleTargetKind.PLAYER:
        return False
    return parameter_payload(clause.target.parameters).get("relationship") == "source_player"


def _has_single_command_point_effect(clause: RuleClause, *, operation: str) -> bool:
    effects = _command_point_effects(clause)
    if len(effects) != 1:
        return False
    parameters = parameter_payload(effects[0].parameters)
    delta = parameters.get("delta")
    return (
        parameters.get("operation") == operation
        and parameters.get("affected_player") == "source_player"
        and type(delta) is int
        and delta > 0
    )


def _command_point_effects(clause: RuleClause) -> tuple[RuleEffectSpec, ...]:
    return tuple(
        effect for effect in clause.effects if effect.kind is RuleEffectKind.MODIFY_COMMAND_POINTS
    )


def _has_target_constraint(
    clause: RuleClause,
    *,
    relationship: str,
    gate_subject: str,
    selected_unit_allegiance: str | None = None,
) -> bool:
    for condition in clause.conditions:
        if condition.kind is not RuleConditionKind.TARGET_CONSTRAINT:
            continue
        parameters = parameter_payload(condition.parameters)
        if (
            parameters.get("relationship") == relationship
            and parameters.get("gate_subject") == gate_subject
            and (
                selected_unit_allegiance is None
                or parameters.get("selected_unit_allegiance") == selected_unit_allegiance
            )
        ):
            return True
    return False


def _is_destroyed_unit_keyword_gate(condition: RuleCondition) -> bool:
    if condition.kind is not RuleConditionKind.KEYWORD_GATE:
        return False
    parameters = parameter_payload(condition.parameters)
    keywords = parameters.get("required_keyword_any")
    return (
        parameters.get("gate_subject") == "destroyed_unit"
        and type(keywords) is tuple
        and bool(keywords)
    )


def _is_supported_numeric_distance(condition: RuleCondition) -> bool:
    if condition.kind is not RuleConditionKind.DISTANCE_PREDICATE:
        return False
    parameters = parameter_payload(condition.parameters)
    distance = parameters.get("distance_inches")
    return (
        parameters.get("range_kind") == "numeric_range"
        and parameters.get("negated") is False
        and isinstance(distance, int | float)
        and type(distance) is not bool
        and float(distance) > 0
    )


def _has_supported_cost_frequency(clause: RuleClause) -> bool:
    frequencies = tuple(
        condition
        for condition in clause.conditions
        if condition.kind is RuleConditionKind.FREQUENCY_LIMIT
    )
    if len(frequencies) > 1:
        return False
    if not frequencies:
        return True
    return parameter_payload(frequencies[0].parameters).get("scope") in {
        "phase",
        "turn",
        "battle round",
        "battle",
    }


def _validate_clause(clause: object) -> RuleClause:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Command-point RuleIR support requires RuleClause.")
    return clause
