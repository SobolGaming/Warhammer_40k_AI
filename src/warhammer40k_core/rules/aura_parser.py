"""Normalize Aura scope at the source boundary."""

from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import RuleCondition, RuleConditionKind, parameters_from_pairs
from warhammer40k_core.rules.rule_parser_selected_target_extensions import (
    shadow_of_chaos_area_match,
)

AURA_TAG_RE = re.compile(r"(?:\bAura\b|^\s*Aura\s*:)", re.IGNORECASE)
_EXCLUDE_UNIT_RE = re.compile(
    r"\b(?:an)?other friendly(?: [A-Z][A-Z0-9'-]*){0,5} units?\b|\bexcluding this unit\b",
    re.IGNORECASE,
)


def aura_excludes_source_unit(text: str) -> bool:
    return _EXCLUDE_UNIT_RE.search(text) is not None


def parse_aura_conditions(span: TextSpan) -> tuple[RuleCondition, ...]:
    match = AURA_TAG_RE.search(span.text)
    if match is None:
        match = shadow_of_chaos_area_match(span.text)
    if match is None:
        return ()
    return (
        RuleCondition(
            kind=RuleConditionKind.AURA,
            source_span=TextSpan(
                text=match.group(), start=span.start + match.start(), end=span.start + match.end()
            ),
            parameters=parameters_from_pairs((("source", "aura"),)),
        ),
    )
