from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rule_aura_resolution import aura_affected_unit_ids
from warhammer40k_core.engine.rule_execution_validation import json_object as _json_object
from warhammer40k_core.rules.rule_ir import RuleClause, RuleEffectSpec, RuleIR
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.core_aura_psychic_2026_09 import (
    AURA_SOURCE_ID,
)

if TYPE_CHECKING:
    from warhammer40k_core.engine.rule_execution import RuleExecutionContext, RuleExecutionResult


def aura_handler(
    rule_ir: RuleIR,
    clause: RuleClause,
    effect: RuleEffectSpec | None,
    context: RuleExecutionContext,
) -> RuleExecutionResult:
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionResult,
        emit_rule_execution_event,
        require_execution_state,
        rule_effect_payload,
        rule_execution_event_id,
    )

    if effect is not None:
        raise GameLifecycleError("Aura handler does not accept a single effect.")
    source_unit_instance_id = context.source_unit_instance_id
    if source_unit_instance_id is None:
        raise GameLifecycleError("Aura evaluation requires source_unit_instance_id.")
    affected_unit_ids = aura_affected_unit_ids(
        clause=clause,
        state=require_execution_state(context),
        source_unit_instance_id=source_unit_instance_id,
        source_model_instance_id=context.source_model_instance_id,
    )
    aura_payload = _json_object(
        {
            "rule_id": rule_ir.rule_id,
            "source_id": rule_ir.source_id,
            "clause_id": clause.clause_id,
            "core_rule_source_id": AURA_SOURCE_ID,
            "source_unit_instance_id": context.source_unit_instance_id,
            "affected_unit_instance_ids": list(affected_unit_ids),
            "conditions": [condition.to_payload() for condition in clause.conditions],
        }
    )
    effect_payloads = tuple(
        rule_effect_payload(
            rule_ir=rule_ir,
            clause=clause,
            effect=effect_spec,
            context=context,
            target_unit_instance_ids=affected_unit_ids,
        )
        for effect_spec in clause.effects
    )
    event = emit_rule_execution_event(
        context=context,
        event_type="rule_execution_aura_evaluated",
        payload=aura_payload,
        fallback_id=rule_execution_event_id(rule_ir, clause, None, "aura"),
    )
    return RuleExecutionResult.applied(
        rule_ir,
        applied_clause_ids=(clause.clause_id,),
        effect_payloads=effect_payloads,
        aura_evaluations=(aura_payload,),
        event_records=(event,),
    )
