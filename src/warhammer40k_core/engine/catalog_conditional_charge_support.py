from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID = "catalog-ir:stratagem-phase-use-exception"
CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID = (
    "catalog-ir:friendly-engaged-anchor-charge-reroll"
)

STRATAGEM_PHASE_USE_EXCEPTION_ABILITY = "stratagem_phase_use_exception"
FRIENDLY_ENGAGED_ANCHOR_CHARGE_ABILITY = "charge_reroll_with_friendly_engaged_keyword_anchor"


@dataclass(frozen=True, slots=True)
class StratagemPhaseUseExceptionSemantic:
    stratagem_id: str
    frequency_scope: str
    bypass_same_stratagem_per_phase: bool
    does_not_block_other_units: bool


@dataclass(frozen=True, slots=True)
class FriendlyEngagedAnchorChargeSemantic:
    anchor_keyword: str
    maximum_anchor_distance_inches: float
    roll_type: str
    component_selection_policy: str
    selection_policy: str
    required_charge_end_relationship: str
    optional: bool


def registered_consumer_ids() -> tuple[str, ...]:
    return (
        CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,
        CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID,
    )


def consumer_ids_for_clause(clause: RuleClause) -> tuple[str, ...]:
    _validate_clause(clause)
    consumer_ids: list[str] = []
    if clause_is_stratagem_phase_use_exception(clause):
        consumer_ids.append(CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID)
    if clause_is_friendly_engaged_anchor_charge_reroll(clause):
        consumer_ids.append(CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID)
    return tuple(consumer_ids)


def consumer_ids_for_effect(effect: RuleEffectSpec) -> tuple[str, ...]:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Conditional Charge RuleIR support requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return ()
    ability = parameter_payload(effect.parameters).get("ability")
    if ability == STRATAGEM_PHASE_USE_EXCEPTION_ABILITY:
        return (CATALOG_IR_STRATAGEM_PHASE_USE_EXCEPTION_CONSUMER_ID,)
    if ability == FRIENDLY_ENGAGED_ANCHOR_CHARGE_ABILITY:
        return (CATALOG_IR_FRIENDLY_ENGAGED_ANCHOR_CHARGE_CONSUMER_ID,)
    return ()


def clause_is_stratagem_phase_use_exception(clause: RuleClause) -> bool:
    _validate_clause(clause)
    if not clause.is_supported or clause.duration is not None:
        return False
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.UNIT_SELECTED:
        return False
    if parameter_payload(clause.trigger.parameters) != {
        "selected_unit_allegiance": "friendly",
        "selection": "stratagem_target",
        "source_relationship": "stratagem_targets_source_unit",
        "stratagem_user": "source_player",
        "timing_window": "after_unit_selected_as_stratagem_target",
        "usage_scope": "source_model",
    }:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.STRATAGEM_USE:
        return False
    if parameter_payload(clause.target.parameters):
        return False
    if len(clause.conditions) != 1 or not _is_source_stratagem_target_constraint(
        clause.conditions[0]
    ):
        return False
    if len(clause.effects) != 1:
        return False
    return _phase_use_exception_semantic_or_none(clause.effects[0]) is not None


def stratagem_phase_use_exception_semantic(
    clause: RuleClause,
) -> StratagemPhaseUseExceptionSemantic:
    if not clause_is_stratagem_phase_use_exception(clause):
        raise GameLifecycleError("RuleIR clause is not a Stratagem phase-use exception.")
    semantic = _phase_use_exception_semantic_or_none(clause.effects[0])
    if semantic is None:
        raise GameLifecycleError("Stratagem phase-use exception effect drift.")
    return semantic


def clause_is_friendly_engaged_anchor_charge_reroll(clause: RuleClause) -> bool:
    _validate_clause(clause)
    if not clause.is_supported:
        return False
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.UNIT_SELECTED:
        return False
    if parameter_payload(clause.trigger.parameters) != {
        "selection": "charging_unit",
        "source_relationship": "source_unit_declares_charge",
        "timing_window": "after_charging_unit_selected_before_charge_roll",
    }:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.THIS_UNIT:
        return False
    if parameter_payload(clause.target.parameters):
        return False
    if (
        clause.duration is None
        or clause.duration.kind is not RuleDurationKind.UNTIL_TIMING_ENDPOINT
        or parameter_payload(clause.duration.parameters) != {"endpoint": "phase"}
    ):
        return False
    if len(clause.effects) != 1 or _charge_semantic_from_effect_or_none(clause.effects[0]) is None:
        return False
    return _charge_condition_semantic_or_none(clause.conditions) is not None


def friendly_engaged_anchor_charge_semantic(
    clause: RuleClause,
) -> FriendlyEngagedAnchorChargeSemantic:
    if not clause_is_friendly_engaged_anchor_charge_reroll(clause):
        raise GameLifecycleError("RuleIR clause is not a friendly-engaged-anchor Charge reroll.")
    condition_semantic = _charge_condition_semantic_or_none(clause.conditions)
    effect_semantic = _charge_semantic_from_effect_or_none(clause.effects[0])
    if condition_semantic is None or effect_semantic is None:
        raise GameLifecycleError("Friendly-engaged-anchor Charge semantic drift.")
    anchor_keyword, maximum_distance = condition_semantic
    return FriendlyEngagedAnchorChargeSemantic(
        anchor_keyword=anchor_keyword,
        maximum_anchor_distance_inches=maximum_distance,
        roll_type=effect_semantic.roll_type,
        component_selection_policy=effect_semantic.component_selection_policy,
        selection_policy=effect_semantic.selection_policy,
        required_charge_end_relationship=effect_semantic.required_charge_end_relationship,
        optional=effect_semantic.optional,
    )


def _phase_use_exception_semantic_or_none(
    effect: RuleEffectSpec,
) -> StratagemPhaseUseExceptionSemantic | None:
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return None
    parameters = parameter_payload(effect.parameters)
    stratagem_id = parameters.get("stratagem_id")
    if type(stratagem_id) is not str or not stratagem_id.strip():
        return None
    expected = {
        "ability": STRATAGEM_PHASE_USE_EXCEPTION_ABILITY,
        "bypass_same_stratagem_per_phase": True,
        "does_not_block_other_units": True,
        "frequency_scope": "phase_per_unit",
        "stratagem_id": stratagem_id,
    }
    if parameters != expected:
        return None
    return StratagemPhaseUseExceptionSemantic(
        stratagem_id=stratagem_id,
        frequency_scope="phase_per_unit",
        bypass_same_stratagem_per_phase=True,
        does_not_block_other_units=True,
    )


def _charge_semantic_from_effect_or_none(
    effect: RuleEffectSpec,
) -> FriendlyEngagedAnchorChargeSemantic | None:
    if effect.kind is not RuleEffectKind.GRANT_ABILITY:
        return None
    parameters = parameter_payload(effect.parameters)
    expected = {
        "ability": FRIENDLY_ENGAGED_ANCHOR_CHARGE_ABILITY,
        "component_selection_policy": "whole_roll",
        "optional": True,
        "required_charge_end_relationship": "enemy_engaged_with_selected_anchor",
        "roll_type": "charge_roll",
        "selection_policy": "anchor_and_enemy_pair",
    }
    if parameters != expected:
        return None
    return FriendlyEngagedAnchorChargeSemantic(
        anchor_keyword="",
        maximum_anchor_distance_inches=0.0,
        roll_type="charge_roll",
        component_selection_policy="whole_roll",
        selection_policy="anchor_and_enemy_pair",
        required_charge_end_relationship="enemy_engaged_with_selected_anchor",
        optional=True,
    )


def _charge_condition_semantic_or_none(
    conditions: tuple[RuleCondition, ...],
) -> tuple[str, float] | None:
    if len(conditions) != 4:
        return None
    anchor_constraint = _single_condition(
        conditions,
        kind=RuleConditionKind.TARGET_CONSTRAINT,
        parameters={
            "exclude_source_unit": True,
            "gate_subject": "friendly_anchor",
            "relationship": "friendly_engaged_keyword_unit",
        },
    )
    enemy_constraint = _single_condition(
        conditions,
        kind=RuleConditionKind.TARGET_CONSTRAINT,
        parameters={
            "gate_subject": "required_enemy",
            "relationship": "enemy_engaged_with_selected_friendly_anchor",
        },
    )
    if anchor_constraint is None or enemy_constraint is None:
        return None
    keyword_conditions = tuple(
        condition for condition in conditions if condition.kind is RuleConditionKind.KEYWORD_GATE
    )
    if len(keyword_conditions) != 1:
        return None
    keyword_parameters = parameter_payload(keyword_conditions[0].parameters)
    anchor_keyword = keyword_parameters.get("required_keyword")
    if (
        keyword_parameters
        != {
            "gate_subject": "friendly_anchor",
            "required_keyword": anchor_keyword,
        }
        or type(anchor_keyword) is not str
        or not anchor_keyword.strip()
    ):
        return None
    distance_conditions = tuple(
        condition
        for condition in conditions
        if condition.kind is RuleConditionKind.DISTANCE_PREDICATE
    )
    if len(distance_conditions) != 1:
        return None
    distance_parameters = parameter_payload(distance_conditions[0].parameters)
    distance = distance_parameters.get("distance_inches")
    if (
        not isinstance(distance, int | float)
        or type(distance) is bool
        or float(distance) <= 0
        or distance_parameters
        != {
            "distance_inches": distance,
            "first_subject": "source_unit",
            "negated": False,
            "range_kind": "numeric_range",
            "second_subject": "friendly_anchor",
        }
    ):
        return None
    return anchor_keyword, float(distance)


def _single_condition(
    conditions: tuple[RuleCondition, ...],
    *,
    kind: RuleConditionKind,
    parameters: dict[str, object],
) -> RuleCondition | None:
    matches = tuple(
        condition
        for condition in conditions
        if condition.kind is kind and parameter_payload(condition.parameters) == parameters
    )
    return matches[0] if len(matches) == 1 else None


def _is_source_stratagem_target_constraint(condition: RuleCondition) -> bool:
    return condition.kind is RuleConditionKind.TARGET_CONSTRAINT and parameter_payload(
        condition.parameters
    ) == {
        "gate_subject": "stratagem_target",
        "relationship": "stratagem_targets_source_unit",
        "selected_unit_allegiance": "friendly",
    }


def _validate_clause(clause: object) -> RuleClause:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Conditional Charge RuleIR support requires RuleClause.")
    return clause
