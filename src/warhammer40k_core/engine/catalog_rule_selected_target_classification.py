from __future__ import annotations

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTriggerKind,
    parameter_payload,
)

CATALOG_IR_SELECTED_TARGET_EFFECT_CONSUMER_ID = "catalog-ir:selected-target-effect"
CATALOG_IR_POST_SHOOT_HIT_TARGET_EFFECT_CONSUMER_ID = "catalog-ir:post-shoot-hit-target-effect"

_SELECTED_TARGET_EFFECT_KINDS = frozenset(
    (
        RuleEffectKind.GRANT_WEAPON_ABILITY,
        RuleEffectKind.MODIFY_CHARACTERISTIC,
        RuleEffectKind.MODIFY_DICE_ROLL,
        RuleEffectKind.REROLL_PERMISSION,
        RuleEffectKind.SET_CONTEXTUAL_STATUS,
    )
)


def rule_has_fight_start_selected_target_effect(rule_ir: RuleIR) -> bool:
    return bool(fight_start_selected_target_effect_clause_ids(rule_ir))


def fight_start_selected_target_effect_clause_ids(rule_ir: RuleIR) -> tuple[str, ...]:
    clause_ids: set[str] = set()
    for index, clause in enumerate(rule_ir.clauses):
        if not _clause_is_fight_start_selected_target_selection(clause):
            continue
        clause_ids.update(
            effect_clause.clause_id
            for effect_clause in _selected_target_effect_clauses_after(
                rule_ir.clauses,
                index,
                include_immediate_effects=False,
            )
        )
    return tuple(sorted(clause_ids))


def rule_has_post_shoot_hit_target_effect(rule_ir: RuleIR) -> bool:
    return bool(post_shoot_hit_target_effect_clause_ids(rule_ir))


def post_shoot_hit_target_effect_clause_ids(rule_ir: RuleIR) -> tuple[str, ...]:
    clause_ids: set[str] = set()
    for index, clause in enumerate(rule_ir.clauses):
        if not _clause_is_post_shoot_hit_target_effect_selection(clause):
            continue
        clause_ids.update(
            effect_clause.clause_id
            for effect_clause in _selected_target_effect_clauses_after(
                rule_ir.clauses,
                index,
                include_immediate_effects=True,
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
    return tuple(sorted(consumer_ids))


def _clause_is_fight_start_selected_target_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target classifier requires RuleClause.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(clause.trigger.parameters)
    return (
        parameters.get("edge") == "start"
        and parameters.get("phase") == BattlePhase.FIGHT.value
        and not clause.effects
    )


def _clause_is_post_shoot_hit_target_effect_selection(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target classifier requires RuleClause.")
    if clause.trigger is None or clause.trigger.kind is not RuleTriggerKind.TIMING_WINDOW:
        return False
    if clause.target is None or clause.target.kind is not RuleTargetKind.ENEMY_UNIT:
        return False
    parameters = parameter_payload(clause.trigger.parameters)
    target_parameters = parameter_payload(clause.target.parameters)
    return (
        parameters.get("timing_window") == "just_after_friendly_unit_has_shot"
        and parameters.get("target_relationship") == "hit_by_those_attacks"
        and target_parameters.get("target_relationship") == "hit_by_those_attacks"
        and not clause.effects
    )


def _selected_target_effect_clauses_after(
    clauses: tuple[RuleClause, ...],
    selection_index: int,
    *,
    include_immediate_effects: bool,
) -> tuple[RuleClause, ...]:
    selected: list[RuleClause] = []
    for clause in clauses[selection_index + 1 :]:
        if clause.template_id == "phase17c:selected-target-constraint":
            break
        if not clause.effects:
            continue
        if clause.duration is None and not (
            include_immediate_effects and _clause_has_immediate_selected_target_effect(clause)
        ):
            continue
        if any(effect.kind in _SELECTED_TARGET_EFFECT_KINDS for effect in clause.effects):
            selected.append(clause)
    return tuple(selected)


def _clause_has_immediate_selected_target_effect(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Catalog selected-target classifier requires RuleClause.")
    if clause.duration is not None or clause.target is None:
        return False
    if clause.target.kind not in {RuleTargetKind.SELECTED_UNIT, RuleTargetKind.SELECTED_TARGET}:
        return False
    return any(
        _effect_is_immediate_selected_target_battle_shock(effect) for effect in clause.effects
    )


def _effect_is_immediate_selected_target_battle_shock(effect: RuleEffectSpec) -> bool:
    if type(effect) is not RuleEffectSpec:
        raise GameLifecycleError("Catalog selected-target classifier requires RuleEffectSpec.")
    if effect.kind is not RuleEffectKind.SET_CONTEXTUAL_STATUS:
        return False
    parameters = parameter_payload(effect.parameters)
    return (
        parameters.get("rules_context") == "battle_shock"
        and parameters.get("status") == "force_battle_shock_test"
        and parameters.get("required") is True
        and parameters.get("target_scope") == "selected_unit"
    )
