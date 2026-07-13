from __future__ import annotations

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleConditionKind,
    RuleDurationKind,
    RuleEffectKind,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

_SUPPORTED_EFFECT_KINDS = frozenset(
    {
        RuleEffectKind.GRANT_WEAPON_ABILITY,
        RuleEffectKind.MODIFY_CHARACTERISTIC,
        RuleEffectKind.MODIFY_DICE_ROLL,
        RuleEffectKind.REROLL_PERMISSION,
        RuleEffectKind.SET_CONTEXTUAL_STATUS,
    }
)
_SUPPORTED_EFFECT_TARGET_KINDS = frozenset(
    {
        RuleTargetKind.ENEMY_UNIT,
        RuleTargetKind.FRIENDLY_UNIT,
        RuleTargetKind.SELECTED_TARGET,
        RuleTargetKind.SELECTED_UNIT,
        RuleTargetKind.THIS_MODEL,
        RuleTargetKind.THIS_UNIT,
    }
)
_SUPPORTED_DURATION_ENDPOINTS = frozenset({"phase", "turn", "battle_round", "battle"})


def clause_is_fight_start_selected_target_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target classifier requires RuleClause.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(clause.trigger.parameters)
    return (
        clause.template_id == "phase17c:selected-target-constraint"
        and parameters.get("edge") == "start"
        and parameters.get("phase") == BattlePhase.FIGHT.value
        and not clause.effects
        and clause.duration is None
    )


def fight_start_selected_target_effect_clauses_after(
    clauses: tuple[RuleClause, ...],
    selection_index: int,
) -> tuple[RuleClause, ...]:
    if type(clauses) is not tuple or any(type(clause) is not RuleClause for clause in clauses):
        raise GameLifecycleError(
            "Fight-start selected-target discovery requires RuleClause values."
        )
    if type(selection_index) is not int or not 0 <= selection_index < len(clauses):
        raise GameLifecycleError("Fight-start selected-target selection_index is invalid.")
    selection_clause = clauses[selection_index]
    selected: list[RuleClause] = []
    for clause in clauses[selection_index + 1 :]:
        if clause.template_id == "phase17c:selected-target-constraint":
            break
        if fight_start_selected_target_pair_is_supported(
            selection_clause=selection_clause,
            effect_clause=clause,
        ):
            selected.append(clause)
    return tuple(selected)


def fight_start_selected_target_pair_is_supported(
    *,
    selection_clause: RuleClause,
    effect_clause: RuleClause,
) -> bool:
    if type(selection_clause) is not RuleClause or type(effect_clause) is not RuleClause:
        raise GameLifecycleError(
            "Fight-start selected-target pair support requires RuleClause values."
        )
    return (
        clause_is_fight_start_selected_target_selection(selection_clause)
        and _fight_start_effect_clause_is_supported(effect_clause)
        and (
            not selected_target_effect_clause_has_this_model_semantics(effect_clause)
            or (
                effect_clause.target is not None
                and effect_clause.target.kind is RuleTargetKind.THIS_MODEL
            )
        )
    )


def selected_target_pair_requires_source_model(
    *,
    selection_clause: RuleClause,
    effect_clauses: tuple[RuleClause, ...],
) -> bool:
    if type(selection_clause) is not RuleClause:
        raise GameLifecycleError("Selected-target model-scope resolution requires RuleClause.")
    if type(effect_clauses) is not tuple or any(
        type(clause) is not RuleClause for clause in effect_clauses
    ):
        raise GameLifecycleError(
            "Selected-target model-scope resolution requires effect RuleClause values."
        )
    return selected_target_selection_clause_binds_source_model(selection_clause) or any(
        selected_target_effect_clause_has_this_model_semantics(clause) for clause in effect_clauses
    )


def selected_target_selection_clause_binds_source_model(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target source-model binding requires RuleClause.")
    if clause.trigger is not None:
        trigger_parameters = parameter_payload(clause.trigger.parameters)
        if (
            trigger_parameters.get("subject") == "this_model"
            or trigger_parameters.get("attacker_model_reference") == "this_model"
        ):
            return True
    return any(
        condition.kind is RuleConditionKind.DISTANCE_PREDICATE
        and parameter_payload(condition.parameters).get("object_kind") == "model"
        and parameter_payload(condition.parameters).get("object_reference") == "this"
        for condition in clause.conditions
    )


def selected_target_effect_clause_has_this_model_semantics(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Selected-target model-scope resolution requires RuleClause.")
    if clause.target is not None and clause.target.kind is RuleTargetKind.THIS_MODEL:
        return True
    if clause.trigger is not None:
        parameters = parameter_payload(clause.trigger.parameters)
        if parameters.get("actor") == "this_model":
            return True
    return any(
        condition.kind is RuleConditionKind.TARGET_CONSTRAINT
        and parameter_payload(condition.parameters).get("relationship") == "this_model_makes_attack"
        for condition in clause.conditions
    )


def _fight_start_effect_clause_is_supported(clause: RuleClause) -> bool:
    return (
        clause.is_supported
        and clause.target is not None
        and clause.target.kind in _SUPPORTED_EFFECT_TARGET_KINDS
        and _duration_is_supported(clause)
        and bool(clause.effects)
        and all(effect.kind in _SUPPORTED_EFFECT_KINDS for effect in clause.effects)
    )


def _duration_is_supported(clause: RuleClause) -> bool:
    duration = clause.duration
    if duration is None:
        return False
    parameters = parameter_payload(duration.parameters)
    if duration.kind is RuleDurationKind.PERMANENT:
        return not parameters
    return (
        duration.kind is RuleDurationKind.UNTIL_TIMING_ENDPOINT
        and frozenset(parameters) == frozenset({"endpoint"})
        and parameters.get("endpoint") in _SUPPORTED_DURATION_ENDPOINTS
    )
