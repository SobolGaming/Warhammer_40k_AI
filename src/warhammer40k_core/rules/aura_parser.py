"""Normalize Aura scope at the source boundary."""

from __future__ import annotations

import re
from dataclasses import replace

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleParseDiagnostic,
    RuleUnsupportedReason,
    parameter_payload,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_keyword_sequences import is_known_source_keyword_sequence
from warhammer40k_core.rules.rule_parser_selected_target_extensions import (
    shadow_of_chaos_area_match,
)

_AURA_TAG_RE = re.compile(r"(?:\bAura\b|^\s*Aura\s*:)", re.IGNORECASE)
_EXCLUDE_UNIT_RE = re.compile(
    r"\b(?:an)?other friendly(?: [A-Z][A-Z0-9'-]*){0,5} units?\b|\bexcluding this unit\b",
    re.IGNORECASE,
)


_AURA_KEYWORD_SUBJECT_RE = re.compile(r"[A-Z][A-Z0-9_'-]*(?: [A-Z0-9_'-]+){0,4}", re.IGNORECASE)
_STEALTH_GRANT_AURA_RE = re.compile(
    r"(?:Aura:\s+)?(?P<condition>While) (?:a|another) friendly"
    r"(?: (?P<qualifier>.+?))? unit is within \d+(?:\.\d+)?\" of this "
    r"fortification, "
    r"(?P<grant>models in that unit have the (?:Stealth|\[Stealth\]) ability)\.?",
    re.IGNORECASE,
)


def unsupported_live_aura_clause(
    span: TextSpan, *, clause_id: str, source_keyword_sequence_parts: tuple[str, ...]
) -> RuleClause | None:
    match = _STEALTH_GRANT_AURA_RE.fullmatch(span.text)
    if match is None or (qualifier := match["qualifier"]) is None:
        return None
    matches_keyword_subject = _AURA_KEYWORD_SUBJECT_RE.fullmatch(qualifier) is not None
    if matches_keyword_subject and is_known_source_keyword_sequence(
        qualifier, source_keyword_sequence_parts=source_keyword_sequence_parts
    ):
        return None
    return RuleClause(
        clause_id=clause_id,
        source_span=span,
        unsupported_reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
        diagnostics=(
            RuleParseDiagnostic(
                reason=RuleUnsupportedReason.UNSUPPORTED_LANGUAGE,
                message="Fortification Stealth aura requires known conjunctive keywords.",
                source_span=TextSpan(
                    text=qualifier,
                    start=span.start + match.start("qualifier"),
                    end=span.start + match.end("qualifier"),
                ),
            ),
        ),
    )


def has_aura_scope(text: str) -> bool:
    return (
        _AURA_TAG_RE.search(text) is not None or _STEALTH_GRANT_AURA_RE.fullmatch(text) is not None
    )


def live_aura_distance_conditions(
    span: TextSpan, conditions: tuple[RuleCondition, ...]
) -> tuple[RuleCondition, ...]:
    if _STEALTH_GRANT_AURA_RE.fullmatch(span.text) is None:
        return conditions
    result: list[RuleCondition] = []
    for condition in conditions:
        parameters = parameter_payload(condition.parameters)
        if parameters.get("object_kind") == "fortification":
            # This Fortification is the rules unit providing the aura. Keep
            # the authored noun in the source span.
            parameters["object_kind"] = "unit"
            condition = replace(
                condition, parameters=parameters_from_pairs(tuple(parameters.items()))
            )
        result.append(condition)
    return tuple(result)


def parse_live_aura_ability_effects(span: TextSpan) -> tuple[RuleEffectSpec, ...]:
    match = _STEALTH_GRANT_AURA_RE.fullmatch(span.text)
    if match is None:
        return ()
    return (
        RuleEffectSpec(
            kind=RuleEffectKind.GRANT_ABILITY,
            source_span=TextSpan(
                text=match["grant"],
                start=span.start + match.start("grant"),
                end=span.start + match.end("grant"),
            ),
            parameters=parameters_from_pairs((("ability", "stealth"),)),
        ),
    )


def aura_excludes_source_unit(text: str) -> bool:
    return _EXCLUDE_UNIT_RE.search(text) is not None


def parse_aura_conditions(span: TextSpan) -> tuple[RuleCondition, ...]:
    match = _AURA_TAG_RE.search(span.text)
    if match is None:
        match = shadow_of_chaos_area_match(span.text)
    condition_group: int | str = 0
    if match is None:
        match = _STEALTH_GRANT_AURA_RE.fullmatch(span.text)
        condition_group = "condition"
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.AURA,
            source_span=TextSpan(
                text=match.group(condition_group),
                start=span.start + match.start(condition_group),
                end=span.start + match.end(condition_group),
            ),
            parameters=parameters_from_pairs((("source", "aura"),)),
        ),
    )
