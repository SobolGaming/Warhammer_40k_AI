from __future__ import annotations

import re

from warhammer40k_core.rules.command_point_parser import command_point_frequency_span_end
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    parameters_from_pairs,
)

OPTIONAL_ABILITY_ACTIVATION_RE = re.compile(
    r"\bonce\s+per\s+(?P<scope>battle),\s+.+?,\s+"
    r"(?P<subject>this\s+model|this\s+unit|the\s+bearer|bearer)\s+"
    r"can\s+use\s+this\s+ability\.",
    re.IGNORECASE,
)
OPTIONAL_ABILITY_EFFECT_CONTINUATION_RE = re.compile(
    r"^\s*(?:if|when)\s+it\s+does,",
    re.IGNORECASE,
)
_ONCE_PER_RE = re.compile(
    r"\bonce\s+per\s+(?P<scope>battle round|phase|turn|battle)\b",
    re.IGNORECASE,
)


def parse_frequency_conditions(clause_span: TextSpan) -> tuple[RuleCondition, ...]:
    activation_match = OPTIONAL_ABILITY_ACTIVATION_RE.search(clause_span.text)
    activation_range: tuple[int, int] | None = None
    conditions: list[RuleCondition] = []
    if activation_match is not None:
        continuation_match = OPTIONAL_ABILITY_EFFECT_CONTINUATION_RE.search(
            clause_span.text[activation_match.end() :]
        )
        if continuation_match is not None:
            activation_range = (
                activation_match.start(),
                activation_match.end() + continuation_match.end(),
            )
            conditions.append(
                RuleCondition(
                    kind=RuleConditionKind.FREQUENCY_LIMIT,
                    source_span=_span_from_range(clause_span, *activation_range),
                    parameters=parameters_from_pairs(
                        (
                            ("activation_kind", "optional_ability_use"),
                            ("max_uses", 1),
                            ("scope", activation_match.group("scope").lower()),
                            ("usage_subject", _usage_subject(activation_match.group("subject"))),
                        )
                    ),
                )
            )
    for match in _ONCE_PER_RE.finditer(clause_span.text):
        if activation_range is not None and _range_contains(activation_range, match.span()):
            continue
        span_end = command_point_frequency_span_end(
            clause_span.text,
            fallback_end=match.end(),
        )
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.FREQUENCY_LIMIT,
                source_span=_span_from_range(clause_span, match.start(), span_end),
                parameters=parameters_from_pairs((("scope", match.group("scope").lower()),)),
            )
        )
    return tuple(conditions)


def _usage_subject(value: str) -> str:
    normalized = " ".join(value.lower().split())
    if normalized == "this model":
        return "this_model"
    if normalized == "this unit":
        return "this_unit"
    return "bearer"


def _range_contains(outer: tuple[int, int], inner: tuple[int, int]) -> bool:
    return outer[0] <= inner[0] and inner[1] <= outer[1]


def _span_from_range(span: TextSpan, start: int, end: int) -> TextSpan:
    return TextSpan(
        text=span.text[start:end],
        start=span.start + start,
        end=span.start + end,
    )
