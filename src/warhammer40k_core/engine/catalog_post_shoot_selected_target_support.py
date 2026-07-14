from __future__ import annotations

from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    clause_has_immediate_selected_target_effect as _clause_has_immediate_selected_target_effect,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    effect_is_immediate_selected_target_battle_shock as _effect_is_immediate_battle_shock,
)
from warhammer40k_core.engine.catalog_selected_target_pair_support import (
    selected_target_effect_attack_role,
    selected_target_effect_clause_is_supported,
    selected_target_selection_clause_binds_source_model,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectSpec,
    RuleTargetKind,
)


def post_shoot_selected_target_effect_clauses_after(
    clauses: tuple[RuleClause, ...],
    selection_index: int,
) -> tuple[RuleClause, ...]:
    if type(clauses) is not tuple or any(type(clause) is not RuleClause for clause in clauses):
        raise GameLifecycleError("Post-shoot selected-target discovery requires RuleClause values.")
    if type(selection_index) is not int or not 0 <= selection_index < len(clauses):
        raise GameLifecycleError("Post-shoot selected-target selection_index is invalid.")
    selection_clause = clauses[selection_index]
    selected: list[RuleClause] = []
    for clause in clauses[selection_index + 1 :]:
        if clause.template_id == "phase17c:selected-target-constraint":
            break
        if post_shoot_selected_target_pair_is_supported(
            selection_clause=selection_clause,
            effect_clause=clause,
        ):
            selected.append(clause)
    return tuple(selected)


def post_shoot_selected_target_pair_is_supported(
    *,
    selection_clause: RuleClause,
    effect_clause: RuleClause,
) -> bool:
    if type(selection_clause) is not RuleClause or type(effect_clause) is not RuleClause:
        raise GameLifecycleError(
            "Post-shoot selected-target pair support requires RuleClause values."
        )
    if not post_shoot_selected_target_effect_clause_is_supported(effect_clause):
        return False
    return (
        effect_clause.target is None
        or effect_clause.target.kind is not RuleTargetKind.THIS_MODEL
        or post_shoot_selection_clause_binds_source_model(selection_clause)
    )


def post_shoot_selection_clause_binds_source_model(clause: RuleClause) -> bool:
    return selected_target_selection_clause_binds_source_model(clause)


def post_shoot_selected_target_effect_clause_is_supported(clause: RuleClause) -> bool:
    if type(clause) is not RuleClause:
        raise GameLifecycleError("Post-shoot selected-target support requires RuleClause.")
    return selected_target_effect_clause_is_supported(clause)


def post_shoot_selected_target_effect_attack_role(
    *,
    clause: RuleClause,
    effect: RuleEffectSpec,
) -> str:
    return selected_target_effect_attack_role(clause=clause, effect=effect)


def clause_has_immediate_selected_target_effect(clause: RuleClause) -> bool:
    return _clause_has_immediate_selected_target_effect(clause)


def effect_is_immediate_selected_target_battle_shock(effect: RuleEffectSpec) -> bool:
    return _effect_is_immediate_battle_shock(effect)
