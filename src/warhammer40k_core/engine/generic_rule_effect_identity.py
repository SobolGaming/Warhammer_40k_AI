from __future__ import annotations

import hashlib
import json

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_frequency import optional_ability_frequency_condition
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectSpec, RuleIR


def generic_rule_persisting_effect_id(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec,
    source_unit_instance_id: str | None,
    source_model_instance_id: str | None,
    target_unit_instance_ids: tuple[str, ...],
) -> str:
    """Return the deterministic identity used by generic RuleIR persisted effects."""

    if type(rule_ir) is not RuleIR or type(clause) is not RuleClause:
        raise GameLifecycleError("Generic RuleIR effect identity requires typed source IR.")
    if type(effect) is not RuleEffectSpec or effect not in clause.effects:
        raise GameLifecycleError("Generic RuleIR effect identity requires a source clause effect.")
    if type(target_unit_instance_ids) is not tuple or any(
        type(unit_id) is not str or not unit_id.strip() for unit_id in target_unit_instance_ids
    ):
        raise GameLifecycleError("Generic RuleIR effect identity target inventory is invalid.")
    identity: object = effect.to_payload()
    if optional_ability_frequency_condition(clause) is not None:
        identity = {
            "effect": effect.to_payload(),
            "source_model_instance_id": source_model_instance_id,
            "source_unit_instance_id": source_unit_instance_id,
            "target_unit_instance_ids": list(target_unit_instance_ids),
        }
    canonical = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    effect_suffix = hashlib.sha256(canonical).hexdigest()[:8]
    return (
        f"rule-effect:{rule_ir.ir_hash()[:16]}:"
        f"{clause.clause_id.rsplit(':', 1)[-1]}:{effect_suffix}"
    )


__all__ = ("generic_rule_persisting_effect_id",)
