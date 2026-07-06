from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType
from typing import cast

from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleClausePayload,
    RuleConditionPayload,
    RuleDurationPayload,
    RuleEffectSpecPayload,
    RuleIR,
    RuleIRPayload,
    RuleParameterPayload,
    RuleTargetSpecPayload,
)
from warhammer40k_core.rules.rule_templates import (
    GRANT_ABILITY_TEMPLATE_ID,
    KEYWORD_GATE_TEMPLATE_ID,
)

SOURCE_PACKAGE_ID = "gw-11e-phase17e-faction-coverage-2026-27"

ANHRATHE_KEYWORD = "ANHRATHE"
CHARACTER_KEYWORD = "CHARACTER"
INFANTRY_KEYWORD = "INFANTRY"

ARCHRAIDER_ENHANCEMENT_ID = "archraider"
ARCHRAIDER_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:archraider"
ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{ARCHRAIDER_SOURCE_ROW_ID}"
ARCHRAIDER_SOURCE_RULE_ID = f"phase17f:{ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID}"
ARCHRAIDER_MARKER_ABILITY = "aeldari:corsair-coterie:archraider:marker"

INFAMY_ENHANCEMENT_ID = "infamy"
INFAMY_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:infamy"
INFAMY_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{INFAMY_SOURCE_ROW_ID}"
INFAMY_SOURCE_RULE_ID = f"phase17f:{INFAMY_ENHANCEMENT_DESCRIPTOR_ID}"
INFAMY_MARKER_ABILITY = "aeldari:corsair-coterie:infamy:marker"
INFAMY_OBJECTIVE_CONTROL_ABILITY = "aeldari:corsair-coterie:infamy:objective-control"

VOIDSTONE_ENHANCEMENT_ID = "voidstone"
VOIDSTONE_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:voidstone"
VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{VOIDSTONE_SOURCE_ROW_ID}"
VOIDSTONE_SOURCE_RULE_ID = f"phase17f:{VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID}"
VOIDSTONE_MARKER_ABILITY = "aeldari:corsair-coterie:voidstone:marker"

WEBWAY_PATHSTONE_ENHANCEMENT_ID = "webway-pathstone"
WEBWAY_PATHSTONE_SOURCE_ROW_ID = "enhancement:aeldari:corsair-coterie:webway-pathstone"
WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID = f"phase17e:{WEBWAY_PATHSTONE_SOURCE_ROW_ID}"
WEBWAY_PATHSTONE_SOURCE_RULE_ID = f"phase17f:{WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID}"
WEBWAY_PATHSTONE_MARKER_ABILITY = "aeldari:corsair-coterie:webway-pathstone:marker"
WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY = "aeldari:corsair-coterie:webway-pathstone:deep-strike"
WEBWAY_PATHSTONE_RESERVES_ABILITY = "aeldari:corsair-coterie:webway-pathstone:reserves"


class AeldariCorsairCoterieIrSupportError(ValueError):
    """Raised when static Corsair Coterie RuleIR metadata is inconsistent."""


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


def _archraider_payload() -> RuleIRPayload:
    normalized_text = "ANHRATHE CHARACTER bearer gains the Archraider marker for Lord of Deceit."
    return _enhancement_payload(
        source_row_id=ARCHRAIDER_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE CHARACTER",
        required_keyword_sequence=(ANHRATHE_KEYWORD, CHARACTER_KEYWORD),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Archraider marker",
                effect_text="gains the Archraider marker",
                ability=ARCHRAIDER_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
        ),
    )


def _infamy_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE bearer gains the Infamy marker and reduces Objective Control by 1 "
        "for enemy units within 3 inches."
    )
    return _enhancement_payload(
        source_row_id=INFAMY_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE",
        required_keyword_sequence=(ANHRATHE_KEYWORD,),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Infamy marker",
                effect_text="gains the Infamy marker",
                ability=INFAMY_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="reduces Objective Control by 1 for enemy units within 3 inches",
                effect_text="reduces Objective Control by 1",
                ability=INFAMY_OBJECTIVE_CONTROL_ABILITY,
                hook_family="objective_control_modifier",
                extra_parameters=(_parameter("objective_control_delta", -1),),
            ),
        ),
    )


def _voidstone_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE INFANTRY bearer gains the Voidstone marker for a 5+ invulnerable save."
    )
    return _enhancement_payload(
        source_row_id=VOIDSTONE_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE INFANTRY",
        required_keyword_sequence=(ANHRATHE_KEYWORD, INFANTRY_KEYWORD),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Voidstone marker",
                effect_text="gains the Voidstone marker",
                ability=VOIDSTONE_MARKER_ABILITY,
                hook_family="enhancement_effect",
                extra_parameters=(_parameter("invulnerable_save_target", 5),),
            ),
        ),
    )


def _webway_pathstone_payload() -> RuleIRPayload:
    normalized_text = (
        "ANHRATHE bearer gains the Webway Pathstone marker, gains Deep Strike, and can "
        "enter Strategic Reserves at the end of the Fight phase in the opponent's turn."
    )
    return _enhancement_payload(
        source_row_id=WEBWAY_PATHSTONE_SOURCE_ROW_ID,
        normalized_text=normalized_text,
        keyword_text="ANHRATHE",
        required_keyword_sequence=(ANHRATHE_KEYWORD,),
        ability_clauses=(
            _ability_clause_spec(
                source_text="gains the Webway Pathstone marker",
                effect_text="gains the Webway Pathstone marker",
                ability=WEBWAY_PATHSTONE_MARKER_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="gains Deep Strike",
                effect_text="gains Deep Strike",
                ability=WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY,
                hook_family="enhancement_effect",
            ),
            _ability_clause_spec(
                source_text="can enter Strategic Reserves at the end of the Fight phase",
                effect_text="can enter Strategic Reserves at the end of the Fight phase",
                ability=WEBWAY_PATHSTONE_RESERVES_ABILITY,
                hook_family="turn_end",
            ),
        ),
    )


def _ability_clause_spec(
    *,
    source_text: str,
    effect_text: str,
    ability: str,
    hook_family: str,
    extra_parameters: tuple[RuleParameterPayload, ...] = (),
) -> tuple[str, str, str, str, tuple[RuleParameterPayload, ...]]:
    return source_text, effect_text, ability, hook_family, extra_parameters


def _enhancement_payload(
    *,
    source_row_id: str,
    normalized_text: str,
    keyword_text: str,
    required_keyword_sequence: tuple[str, ...],
    ability_clauses: tuple[tuple[str, str, str, str, tuple[RuleParameterPayload, ...]], ...],
) -> RuleIRPayload:
    clauses: list[RuleClausePayload] = [
        _keyword_gate_clause(
            clause_id=_coverage_clause_id(source_row_id, "gate:001"),
            normalized_text=normalized_text,
            keyword_text=keyword_text,
            required_keyword_sequence=required_keyword_sequence,
        )
    ]
    for index, (source_text, effect_text, ability, hook_family, extra_parameters) in enumerate(
        ability_clauses,
        start=1,
    ):
        clauses.append(
            _ability_clause(
                clause_id=_coverage_clause_id(source_row_id, f"effect:{index:03d}"),
                normalized_text=normalized_text,
                source_text=source_text,
                effect_text=effect_text,
                ability=ability,
                required_keyword_sequence=required_keyword_sequence,
                extra_parameters=(
                    _parameter("hook_family", hook_family),
                    *extra_parameters,
                ),
            )
        )
    return _coverage_payload(source_row_id, normalized_text, tuple(clauses))


def _keyword_gate_clause(
    *,
    clause_id: str,
    normalized_text: str,
    keyword_text: str,
    required_keyword_sequence: tuple[str, ...],
) -> RuleClausePayload:
    return cast(
        RuleClausePayload,
        {
            "clause_id": clause_id,
            "template_id": KEYWORD_GATE_TEMPLATE_ID,
            "source_span": _span(normalized_text, keyword_text),
            "trigger": None,
            "conditions": [
                _keyword_gate_condition(
                    normalized_text=normalized_text,
                    keyword_text=keyword_text,
                    required_keyword_sequence=required_keyword_sequence,
                )
            ],
            "target": None,
            "effects": [],
            "duration": None,
            "unsupported_reason": None,
            "diagnostics": [],
        },
    )


def _keyword_gate_condition(
    *,
    normalized_text: str,
    keyword_text: str,
    required_keyword_sequence: tuple[str, ...],
) -> RuleConditionPayload:
    return cast(
        RuleConditionPayload,
        {
            "kind": "keyword_gate",
            "source_span": _span(normalized_text, keyword_text),
            "parameters": [_parameter("required_keyword_sequence", required_keyword_sequence)],
        },
    )


def _ability_clause(
    *,
    clause_id: str,
    normalized_text: str,
    source_text: str,
    effect_text: str,
    ability: str,
    required_keyword_sequence: tuple[str, ...],
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
                    _parameter("required_keyword_sequence", required_keyword_sequence),
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


def _coverage_clause_id(source_row_id: str, suffix: str) -> str:
    return f"{SOURCE_PACKAGE_ID}:phase17e:{source_row_id}:source-text:{suffix}"


def _parameter(
    key: str,
    value: str | int | float | bool | None | tuple[str, ...],
) -> RuleParameterPayload:
    payload_value = list(value) if type(value) is tuple else value
    return cast(RuleParameterPayload, {"key": key, "value": payload_value})


def _span(normalized_text: str, source_text: str) -> dict[str, str | int]:
    start = normalized_text.index(source_text)
    return {"text": source_text, "start": start, "end": start + len(source_text)}


def _payload_rows() -> Mapping[str, RuleIRPayload]:
    return {
        ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID: _archraider_payload(),
        INFAMY_ENHANCEMENT_DESCRIPTOR_ID: _infamy_payload(),
        VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID: _voidstone_payload(),
        WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID: _webway_pathstone_payload(),
    }


_COVERAGE_RULE_IR_PAYLOADS_BY_DESCRIPTOR_ID = MappingProxyType(_payload_rows())
