from __future__ import annotations

from warhammer40k_core.rules.post_shoot_charge_target_parser import (
    compile_post_shoot_charge_target_clauses,
)
from warhammer40k_core.rules.rule_ir import RuleClause
from warhammer40k_core.rules.selected_to_fight_risk_parser import (
    compile_selected_to_fight_risk_clauses,
)


def compile_specialized_rule_clauses(
    *,
    source_id: str,
    normalized_text: str,
) -> tuple[RuleClause, ...] | None:
    compiled = compile_post_shoot_charge_target_clauses(
        source_id=source_id,
        normalized_text=normalized_text,
    )
    if compiled is not None:
        return compiled
    return compile_selected_to_fight_risk_clauses(
        source_id=source_id,
        normalized_text=normalized_text,
    )
