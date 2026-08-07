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
    RuleTriggerPayload,
)
from warhammer40k_core.rules.rule_templates import REROLL_PERMISSION_TEMPLATE_ID

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

MERCURIAL_HOST_DETACHMENT_RULE_DESCRIPTOR_ID = "phase17e:emperors-children:mercurial-host:rule"
QUICKSILVER_GRACE_SOURCE_ROW_ID = "emperors-children:mercurial-host:rule"
QUICKSILVER_GRACE_SOURCE_RULE_ID = (
    f"{SOURCE_PACKAGE_ID}:phase17e:{QUICKSILVER_GRACE_SOURCE_ROW_ID}:source-text"
)
EMPERORS_CHILDREN_FACTION_KEYWORD = "EMPEROR'S CHILDREN"


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


def _quicksilver_grace_payload() -> RuleIRPayload:
    normalized_text = (
        "You can re-roll Advance rolls made for Emperor's Children units from your army."
    )
    source_text = "re-roll Advance rolls made for Emperor's Children units from your army"
    clauses = (
        cast(
            RuleClausePayload,
            {
                "clause_id": f"{QUICKSILVER_GRACE_SOURCE_RULE_ID}:effect:001",
                "template_id": REROLL_PERMISSION_TEMPLATE_ID,
                "source_span": _span(normalized_text, source_text),
                "trigger": _dice_roll_trigger(normalized_text),
                "conditions": [],
                "target": _target(normalized_text),
                "effects": [_reroll_effect(normalized_text)],
                "duration": _permanent_duration(normalized_text),
                "unsupported_reason": None,
                "diagnostics": [],
            },
        ),
    )
    return RuleIR(
        rule_id=QUICKSILVER_GRACE_SOURCE_RULE_ID,
        source_id=QUICKSILVER_GRACE_SOURCE_RULE_ID,
        normalized_text=normalized_text,
        parser_version="phase17c-rule-parser-v1",
        schema_version="phase17c-rule-ir-v1",
        clauses=tuple(RuleClause.from_payload(clause) for clause in clauses),
        diagnostics=(),
    ).to_payload()


def _dice_roll_trigger(normalized_text: str) -> RuleTriggerPayload:
    trigger_text = "Advance rolls made for Emperor's Children units from your army"
    return cast(
        RuleTriggerPayload,
        {
            "kind": "dice_roll",
            "source_span": _span(normalized_text, trigger_text),
            "parameters": [_parameter("roll_type", "advance")],
        },
    )


def _target(normalized_text: str) -> RuleTargetSpecPayload:
    target_text = "Emperor's Children units from your army"
    return cast(
        RuleTargetSpecPayload,
        {
            "kind": "this_unit",
            "source_span": _span(normalized_text, target_text),
            "parameters": [],
        },
    )


def _reroll_effect(normalized_text: str) -> RuleEffectSpecPayload:
    effect_text = "re-roll Advance rolls"
    return cast(
        RuleEffectSpecPayload,
        {
            "kind": "reroll_permission",
            "source_span": _span(normalized_text, effect_text),
            "parameters": [
                _parameter("roll_type", "advance_roll"),
                _parameter("timing_window", "after_advance_roll"),
                _parameter("required_faction_keyword", EMPERORS_CHILDREN_FACTION_KEYWORD),
            ],
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


def _coverage_payloads() -> Mapping[str, RuleIRPayload]:
    return MappingProxyType(
        {
            MERCURIAL_HOST_DETACHMENT_RULE_DESCRIPTOR_ID: _quicksilver_grace_payload(),
        }
    )


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = _coverage_payloads()
