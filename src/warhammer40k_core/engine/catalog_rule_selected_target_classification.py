from __future__ import annotations

from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
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
    for index, clause in enumerate(rule_ir.clauses):
        if not _clause_is_fight_start_selected_target_selection(clause):
            continue
        if _selected_target_effect_clauses_after(rule_ir.clauses, index):
            return True
    return False


def rule_has_post_shoot_hit_target_effect(rule_ir: RuleIR) -> bool:
    for index, clause in enumerate(rule_ir.clauses):
        if not _clause_is_post_shoot_hit_target_effect_selection(clause):
            continue
        if _selected_target_effect_clauses_after(rule_ir.clauses, index):
            return True
    return False


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
) -> tuple[RuleClause, ...]:
    selected: list[RuleClause] = []
    for clause in clauses[selection_index + 1 :]:
        if clause.template_id == "phase17c:selected-target-constraint":
            break
        if clause.duration is None or not clause.effects:
            continue
        if any(effect.kind in _SELECTED_TARGET_EFFECT_KINDS for effect in clause.effects):
            selected.append(clause)
    return tuple(selected)
