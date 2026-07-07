from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    RuleParameterValue,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_tokens

_HIT_SUCCESS_THRESHOLD_RE = re.compile(
    r"\b(?:(?P<proximity_prefix>for\s+each\s+of\s+those\s+attacks\s+that\s+targets\s+"
    r"an\s+enemy\s+unit\s+within\s+(?P<proximity_distance>\d+(?:\.\d+)?)\"\s+of\s+"
    r"one\s+or\s+more\s+(?P<proximity_keywords>[A-Z][A-Za-z0-9_ '-]+?)\s+units\s+"
    r"from\s+your\s+army,\s*)?)"
    r"(?P<score_subject>hits\s+are|a\s+hit\s+is)\s+scored\s+on\s+"
    r"(?:an?\s+)?unmodified\s+Hit\s+rolls?\s+of\s+(?P<threshold>[2-6])\+"
    r"(?:\s+when\s+resolving\s+that\s+Stratagem)?(?:\s+instead)?(?=\s*(?:\.|,|;|$))",
    re.IGNORECASE,
)
_FIRE_OVERWATCH_STRATAGEM_RE = re.compile(
    r"\bFire\s+Overwatch\s+Stratagem\b",
    re.IGNORECASE,
)


def has_hit_success_threshold(text: str) -> bool:
    return _HIT_SUCCESS_THRESHOLD_RE.search(text) is not None


def hit_success_threshold_effects(
    *,
    clause_text: str,
    clause_start: int,
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[RuleEffectSpec, ...]:
    return tuple(
        RuleEffectSpec(
            kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
            source_span=_span_from_match(
                clause_text=clause_text,
                clause_start=clause_start,
                match=match,
            ),
            parameters=parameters_from_pairs(
                _hit_success_threshold_parameter_pairs(
                    clause_text=clause_text,
                    match=match,
                    source_keyword_sequence_parts=source_keyword_sequence_parts,
                )
            ),
        )
        for match in _HIT_SUCCESS_THRESHOLD_RE.finditer(clause_text)
    )


def _hit_success_threshold_parameter_pairs(
    *,
    clause_text: str,
    match: re.Match[str],
    source_keyword_sequence_parts: tuple[str, ...],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("status", "minimum_unmodified_hit_success"),
        ("roll_type", "hit"),
        ("attack_role", "attacker"),
        ("minimum_unmodified_success", int(match.group("threshold"))),
    ]
    if _FIRE_OVERWATCH_STRATAGEM_RE.search(clause_text) is not None:
        pairs.append(("required_targeting_rule_id", "core:fire-overwatch"))
    if match.group("proximity_prefix") is not None:
        pairs.extend(
            (
                (
                    "target_proximity_distance_inches",
                    _distance_number(match.group("proximity_distance")),
                ),
                ("target_proximity_unit_allegiance", "friendly"),
                (
                    "target_proximity_required_keyword_sequence",
                    keyword_sequence_tokens(
                        match.group("proximity_keywords"),
                        source_keyword_sequence_parts=source_keyword_sequence_parts,
                    ),
                ),
            )
        )
    return tuple(pairs)


def _span_from_match(
    *,
    clause_text: str,
    clause_start: int,
    match: re.Match[str],
) -> TextSpan:
    return TextSpan(
        text=match.group(0),
        start=clause_start + match.start(),
        end=clause_start + match.end(),
    )


def _distance_number(value: str) -> int | float:
    if "." in value:
        return float(value)
    return int(value)
