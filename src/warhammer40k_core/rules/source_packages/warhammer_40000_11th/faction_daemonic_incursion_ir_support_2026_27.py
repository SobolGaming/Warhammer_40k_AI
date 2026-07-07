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

DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:chaos-daemons:daemonic-incursion:rule"
DAEMONIC_INCURSION_SOURCE_RULE_ID = "phase17f:phase17e:chaos-daemons:daemonic-incursion:rule"
DAEMONIC_INCURSION_DETACHMENT_ID = "daemonic-incursion"
CHAOS_DAEMONS_FACTION_ID = "chaos-daemons"
WARP_RIFTS_HOOK_ID = "warhammer_40000_11th:chaos_daemons:detachment:daemonic_incursion:warp_rifts"
WARP_RIFTS_DEEP_STRIKE_DISTANCE_ABILITY = (
    "chaos-daemons:daemonic-incursion:warp-rifts:deep-strike-distance"
)
LEGIONES_DAEMONICA_KEYWORD = "LEGIONES DAEMONICA"
WARP_RIFTS_PLACEMENT_KIND = "deep_strike"
WARP_RIFTS_HOOK_FAMILY = "reserve_arrival_distance"
WARP_RIFTS_CONDITION_FAMILY = "shadow_of_chaos_or_matching_greater_daemon_anchor"
WARP_RIFTS_ENEMY_DISTANCE_INCHES = 6.0


class DaemonicIncursionIrSupportError(ValueError):
    """Raised when static Daemonic Incursion RuleIR support metadata is inconsistent."""


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
    source_row_id = "chaos-daemons:daemonic-incursion:rule"
    source_text = (
        "LEGIONES DAEMONICA Deep Strike units can be set up more than 6 inches "
        "horizontally away from enemy models if wholly within Shadow of Chaos or wholly "
        "within 6 inches of a matching named Greater Daemon anchor."
    )
    normalized_text = source_text
    return _coverage_payload(
        source_row_id,
        normalized_text,
        (
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, "effect:001"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text="can be set up more than 6 inches horizontally away from enemy models",
            ),
        ),
    )


def _coverage_payload(
    source_row_id: str,
    normalized_text: str,
    clauses: tuple[RuleClausePayload, ...],
) -> RuleIRPayload:
    source_id = f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text"
    return RuleIR(
        rule_id=source_id,
        source_id=source_id,
        normalized_text=normalized_text,
        parser_version="phase17c-rule-parser-v1",
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
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": GRANT_ABILITY_TEMPLATE_ID,
            "source_span": _span(normalized_text, source_text),
            "trigger": None,
            "conditions": [],
            "target": _target("this_unit", normalized_text, source_text),
            "effects": [
                _effect(
                    "grant_ability",
                    normalized_text,
                    effect_text,
                    (
                        _parameter("ability", WARP_RIFTS_DEEP_STRIKE_DISTANCE_ABILITY),
                        _parameter("hook_family", WARP_RIFTS_HOOK_FAMILY),
                        _parameter("placement_kind", WARP_RIFTS_PLACEMENT_KIND),
                        _parameter(
                            "enemy_horizontal_distance_inches",
                            WARP_RIFTS_ENEMY_DISTANCE_INCHES,
                        ),
                        _parameter("required_faction_keyword", LEGIONES_DAEMONICA_KEYWORD),
                        _parameter("condition_family", WARP_RIFTS_CONDITION_FAMILY),
                    ),
                ),
            ],
            "duration": _permanent_duration(normalized_text),
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
            DAEMONIC_INCURSION_DETACHMENT_RULE_DESCRIPTOR_ID: _detachment_rule_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
