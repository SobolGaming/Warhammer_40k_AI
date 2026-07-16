from __future__ import annotations

from warhammer40k_core.rules.movement_end_reactive_parser import (
    MovementEndReactiveClauseText,
    compile_movement_end_reactive_normal_move_clause,
)
from warhammer40k_core.rules.rule_ir import RuleClause
from warhammer40k_core.rules.setup_reactive_parser import (
    compile_setup_reactive_shoot_charge_clause,
)


def compile_triggered_action_clause(
    *,
    source_id: str,
    clause_index: int,
    clause_text: MovementEndReactiveClauseText,
) -> RuleClause | None:
    movement_end_clause = compile_movement_end_reactive_normal_move_clause(
        source_id=source_id,
        clause_index=clause_index,
        clause_text=clause_text,
    )
    if movement_end_clause is not None:
        return movement_end_clause
    return compile_setup_reactive_shoot_charge_clause(
        source_id=source_id,
        clause_index=clause_index,
        clause_text=clause_text,
    )
