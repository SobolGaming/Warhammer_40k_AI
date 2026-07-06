from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleDurationPayload,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetSpecPayload,
)
from warhammer40k_core.rules.rule_templates import GRANT_ABILITY_TEMPLATE_ID

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:blood-legion:rule"
BLOOD_LEGION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:blood-legion:rule"
BLOOD_LEGION_DETACHMENT_ID = "blood-legion"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
MURDERCALL_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:murdercall"
BLOOD_TAINTED_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:blood_legion:blood_tainted"
LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
KHORNE_KEYWORD = "KHORNE"
AIRCRAFT_KEYWORD = "AIRCRAFT"
MURDERCALL_RANGE_INCHES = 8.0
MURDERCALL_SURGE_ABILITY = "blood_legion_murdercall_surge"
BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY = "blood_legion_blood_tainted_sticky_objective"


class BloodLegionIrSupportError(ValueError):
    """Raised when static Blood Legion RuleIR support metadata is inconsistent."""


def coverage_rule_ir_payload_by_descriptor_id(
    coverage_descriptor_id: str,
) -> RuleIRPayload | None:
    return _COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID.get(coverage_descriptor_id)


def coverage_rule_ir_hash_by_descriptor_id(coverage_descriptor_id: str) -> str | None:
    payload = coverage_rule_ir_payload_by_descriptor_id(coverage_descriptor_id)
    if payload is None:
        return None
    return payload["ir_hash"]


def supported_coverage_descriptor_ids() -> tuple[str, ...]:
    return tuple(sorted(_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID))


def _detachment_rule_payload() -> RuleIRPayload:
    source_row_id = "chaos-daemons:blood-legion:rule"
    murdercall_text = (
        "Legiones Daemonica Khorne units have the Murdercall surge ability after enemy "
        "movement within 8 inches."
    )
    blood_tainted_text = (
        "Legiones Daemonica Khorne units have the Blood Tainted sticky objective control "
        "ability after destroying enemy units on objectives."
    )
    normalized_text = f"{murdercall_text} {blood_tainted_text}"
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=murdercall_text,
                effect_text="have the Murdercall surge ability",
                ability=MURDERCALL_SURGE_ABILITY,
                extra_parameters=(
                    _parameter("hook_family", "movement_end_surge"),
                    _parameter("range_inches", MURDERCALL_RANGE_INCHES),
                ),
            ),
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:002"),
                normalized_text=normalized_text,
                source_text=blood_tainted_text,
                effect_text="have the Blood Tainted sticky objective control ability",
                ability=BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,
                extra_parameters=(_parameter("hook_family", "phase_end_objective_control"),),
            ),
        ),
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return _payload(
        source_id,
        source_id,
        normalized_text,
        clauses,
        "phase17c-rule-parser-v1",
    )


def _payload(
    rule_id: str,
    source_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
    parser_version: str,
) -> RuleIRPayload:
    return RuleIR(
        rule_id=rule_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version=parser_version,
        schema_version="phase17c-rule-ir-v1",
        clauses=tuple(RuleClause.from_payload(clause) for clause in clauses),
        diagnostics=(),
    ).to_payload()


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    extra_parameters: tuple[RuleParameterPayload, ...],
) -> RuleClausePayload:
    return _effect_clause(
        clause_id=clause_id,
        template_id=GRANT_ABILITY_TEMPLATE_ID,
        normalized_text=normalized_text,
        source_text=source_text,
        target=_target("this_unit", normalized_text, source_text),
        effects=(
            _effect(
                "grant_ability",
                normalized_text,
                effect_text,
                (
                    _parameter("ability", ability),
                    _parameter(
                        "required_faction_keyword_sequence",
                        (LEGIONES_DAEMONICA_KEYWORD,),
                    ),
                    _parameter("required_keyword_sequence", (KHORNE_KEYWORD,)),
                    *extra_parameters,
                ),
            ),
        ),
        duration=_permanent_duration(normalized_text),
    )


def _effect_clause(
    *,
    clause_id: str,
    template_id: str,
    normalized_text: str,
    source_text: str,
    target: RuleTargetSpecPayload | None,
    effects: tuple[RuleEffectSpecPayload, ...],
    duration: RuleDurationPayload | None,
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": template_id,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [],
            "target": target,
            "effects": list(effects),
            "duration": duration,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _effect(
    kind: str,
    normalized_text: str,
    source_text: str,
    parameters: tuple[RuleParameterPayload, ...],
) -> RuleEffectSpecPayload:
    return cast(
        RuleEffectSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": list(parameters),
        },
    )


def _target(
    kind: str,
    normalized_text: str,
    source_text: str,
) -> RuleTargetSpecPayload:
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": kind,
            "source_span": _span(normalized_text, source_text),
            "parameters": [],
        },
    )


def _permanent_duration(normalized_text: str) -> RuleDurationPayload:
    return cast(
        RuleDurationPayload,
        {
            "kind": "permanent",
            "source_span": _span(normalized_text, normalized_text),
            "parameters": [],
        },
    )


def _parameter(key: str, value: object) -> RuleParameterPayload:
    return cast(RuleParameterPayload, {"key": key, "value": value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text:{suffix}"


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
