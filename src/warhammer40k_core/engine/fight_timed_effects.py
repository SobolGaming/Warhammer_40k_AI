from __future__ import annotations

from warhammer40k_core.engine.fight_unit_selected_hooks import FightUnitSelectedTimedEffect
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    generic_rule_effect_payload,
)
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectSpec, RuleIR


def end_phase_rule_effect(
    *,
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec,
    context: RuleExecutionContext,
    target_unit_instance_ids: tuple[str, ...],
) -> FightUnitSelectedTimedEffect:
    return FightUnitSelectedTimedEffect(
        effect_payload=generic_rule_effect_payload(
            rule_ir=rule_ir,
            clause=clause,
            effect=effect,
            context=context,
            target_unit_instance_ids=target_unit_instance_ids,
        ),
        expiration="end_phase",
    )


__all__ = ("end_phase_rule_effect",)
