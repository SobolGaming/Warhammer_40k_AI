from __future__ import annotations

from typing import cast

from warhammer40k_core.engine.catalog_post_shoot_selected_target_support import (
    post_shoot_selected_target_effect_clauses_after,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    clause_is_fight_start_selected_target_selection,
    clause_is_shooting_start_selected_target_selection,
    fight_start_selected_target_effect_clauses_after,
    shooting_start_selected_target_effect_clauses_after,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleIR,
    RuleParameterValue,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID = "catalog-ir:selected-target-effect"
CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID = "catalog-ir:post-shoot-hit-target-effect"
CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID = (
    "catalog-ir:shooting-start-selected-target-effect"
)

_POST_SHOOT_TRIGGER_KEYS = frozenset(
    {
        "edge",
        "owner",
        "phase",
        "subject",
        "target_relationship",
        "timing_window",
    }
)
_POST_SHOOT_FILTERED_TRIGGER_KEYS = _POST_SHOOT_TRIGGER_KEYS | {
    "attacker_model_reference",
    "weapon_names",
}


def rule_has_fight_start_selected_target_effect(rule_ir: RuleIR) -> bool:
    return bool(fight_start_selected_target_effect_clause_ids(rule_ir))


def fight_start_selected_target_effect_clause_ids(rule_ir: RuleIR) -> tuple[str, ...]:
    clause_ids: set[str] = set()
    for index, clause in enumerate(rule_ir.clauses):
        if not clause_is_fight_start_selected_target_selection(clause):
            continue
        clause_ids.update(
            effect_clause.clause_id
            for effect_clause in fight_start_selected_target_effect_clauses_after(
                rule_ir.clauses,
                index,
            )
        )
    return tuple(sorted(clause_ids))


def rule_has_post_shoot_hit_target_effect(rule_ir: RuleIR) -> bool:
    return bool(post_shoot_hit_target_effect_clause_ids(rule_ir))


def post_shoot_hit_target_effect_clause_ids(rule_ir: RuleIR) -> tuple[str, ...]:
    clause_ids: set[str] = set()
    for index, clause in enumerate(rule_ir.clauses):
        if not clause_is_post_shoot_hit_target_selection(clause):
            continue
        clause_ids.update(
            effect_clause.clause_id
            for effect_clause in post_shoot_selected_target_effect_clauses_after(
                rule_ir.clauses,
                index,
            )
        )
    return tuple(sorted(clause_ids))


def rule_has_shooting_start_selected_target_effect(rule_ir: RuleIR) -> bool:
    return bool(shooting_start_selected_target_effect_clause_ids(rule_ir))


def shooting_start_selected_target_effect_clause_ids(rule_ir: RuleIR) -> tuple[str, ...]:
    clause_ids: set[str] = set()
    for index, clause in enumerate(rule_ir.clauses):
        if not clause_is_shooting_start_selected_target_selection(clause):
            continue
        clause_ids.update(
            effect_clause.clause_id
            for effect_clause in shooting_start_selected_target_effect_clauses_after(
                rule_ir.clauses,
                index,
            )
        )
    return tuple(sorted(clause_ids))


def contextual_consumers_for_clause(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
) -> tuple[str, ...]:
    if type(rule_ir) is not RuleIR or type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog contextual consumer classification requires RuleIR.")
    if clause not in rule_ir.clauses:
        raise GameLifecycleError("Catalog contextual consumer clause is not in RuleIR.")
    consumer_ids: set[str] = set()
    if clause.clause_id in fight_start_selected_target_effect_clause_ids(rule_ir):
        consumer_ids.add(CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID)
    if clause.clause_id in post_shoot_hit_target_effect_clause_ids(rule_ir):
        consumer_ids.add(CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID)
    if clause.clause_id in shooting_start_selected_target_effect_clause_ids(rule_ir):
        consumer_ids.add(CATALOG_IR_SHOOTING_START_SELECTED_TARGET_EFFECT_CONSUMER_ID)
    return tuple(sorted(consumer_ids))


def clause_is_post_shoot_hit_target_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog post-shoot matcher requires RuleClause.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(clause.trigger.parameters)
    target_parameters = parameter_payload(clause.target.parameters)
    return (
        clause.is_supported
        and clause.template_id == "phase17c:selected-target-constraint"
        and not clause.conditions
        and not clause.effects
        and clause.duration is None
        and _post_shoot_trigger_parameters_are_supported(parameters)
        and parameters.get("timing_window") == "just_after_friendly_unit_has_shot"
        and parameters.get("target_relationship") == "hit_by_those_attacks"
        and parameters.get("owner") == "active_player"
        and parameters.get("phase") == BattlePhase.SHOOTING.value
        and parameters.get("edge") == "after"
        and set(target_parameters) == {"allegiance", "target_relationship"}
        and target_parameters.get("allegiance") == "enemy"
        and target_parameters.get("target_relationship") == "hit_by_those_attacks"
    )


def _post_shoot_trigger_parameters_are_supported(
    parameters: dict[str, RuleParameterValue],
) -> bool:
    parameter_keys = frozenset(parameters)
    if parameter_keys == _POST_SHOOT_TRIGGER_KEYS:
        return parameters.get("subject") in {"this_model", "this_unit"}
    return (
        parameter_keys == _POST_SHOOT_FILTERED_TRIGGER_KEYS
        and parameters.get("subject") == "this_model"
        and parameters.get("attacker_model_reference") == "this_model"
        and _valid_weapon_names(parameters.get("weapon_names"))
    )


def _valid_weapon_names(value: object) -> bool:
    if type(value) is not tuple or not value:
        return False
    return all(type(name) is str and bool(name.strip()) for name in cast(tuple[object, ...], value))
