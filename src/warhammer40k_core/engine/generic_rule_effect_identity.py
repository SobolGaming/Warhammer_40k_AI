from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.rule_ir import RuleClause, RuleIR

if TYPE_CHECKING:
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext


def generic_rule_persisting_effect_id(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    effect_index: int,
    context: RuleExecutionContext,
    target_unit_instance_ids: tuple[str, ...],
) -> str:
    """Identify one recorded activation's bound effect slot, independently of live state."""

    from warhammer40k_core.engine.rule_execution import RuleExecutionContext

    if type(rule_ir) is not RuleIR or type(clause) is not RuleClause:
        raise GameLifecycleError("Generic RuleIR effect identity requires typed source IR.")
    if clause not in rule_ir.clauses:
        raise GameLifecycleError("Generic RuleIR effect identity requires a loaded source clause.")
    if type(effect_index) is not int or not 0 <= effect_index < len(clause.effects):
        raise GameLifecycleError("Generic RuleIR effect identity requires a valid effect slot.")
    if type(context) is not RuleExecutionContext:
        raise GameLifecycleError("Generic RuleIR effect identity requires RuleExecutionContext.")
    if type(target_unit_instance_ids) is not tuple or any(
        type(unit_id) is not str or not unit_id.strip() for unit_id in target_unit_instance_ids
    ):
        raise GameLifecycleError("Generic RuleIR effect identity target inventory is invalid.")
    if len(set(target_unit_instance_ids)) != len(target_unit_instance_ids):
        raise GameLifecycleError("Generic RuleIR effect identity target inventory is duplicated.")
    identity = {
        "rule_ir_hash": rule_ir.ir_hash(),
        "clause_id": clause.clause_id,
        "effect_index": effect_index,
        "context": {
            key: value
            for key, value in context.to_payload().items()
            if key != "record_persisting_effects"
        },
        "target_unit_instance_ids": sorted(target_unit_instance_ids),
    }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    return f"rule-effect:activation-v1:sha256:{hashlib.sha256(canonical).hexdigest()}"


__all__ = ("generic_rule_persisting_effect_id",)
