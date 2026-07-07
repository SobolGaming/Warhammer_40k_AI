from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleDuration,
    RuleDurationKind,
    parameters_from_pairs,
)

_UNTIL_NEXT_PHASE_RE = re.compile(
    r"\buntil\s+(?:(?:the\s+)?(?P<boundary>start|end)\s+of\s+)?"
    r"(?P<owner>your|opponent's)\s+next\s+"
    r"(?P<phase>Command|Movement|Shooting|Charge|Fight)\s+phase\b",
    re.IGNORECASE,
)
_UNTIL_NEXT_TURN_RE = re.compile(
    r"\buntil\s+(?:(?:the\s+)?(?P<boundary>start|end)\s+of\s+)?"
    r"(?P<owner>your|opponent's)\s+next\s+turn\b",
    re.IGNORECASE,
)
_UNTIL_RE = re.compile(
    r"\buntil\s+(?:the\s+)?end\s+of\s+(?:the\s+|this\s+|that\s+|your\s+|opponent's\s+)?"
    r"(?P<endpoint>phase|turn|battle round|battle)\b",
    re.IGNORECASE,
)
_AURA_RE = re.compile(r"(?:\bAura\b|^\s*Aura\s*:)", re.IGNORECASE)


def parse_rule_duration(*, text: str, span: TextSpan) -> RuleDuration | None:
    next_phase_match = _UNTIL_NEXT_PHASE_RE.search(text)
    if next_phase_match is not None:
        boundary = next_phase_match.group("boundary")
        boundary_token = "start" if boundary is None else boundary.lower()
        return RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span_from_match(span=span, match=next_phase_match),
            parameters=parameters_from_pairs(
                (
                    ("endpoint", "phase"),
                    ("boundary", boundary_token),
                    ("relative", "next"),
                    ("owner", _duration_owner(next_phase_match.group("owner"))),
                    ("phase", _lower_group(next_phase_match, "phase")),
                )
            ),
        )

    next_turn_match = _UNTIL_NEXT_TURN_RE.search(text)
    if next_turn_match is not None:
        boundary = next_turn_match.group("boundary")
        boundary_token = "start" if boundary is None else boundary.lower()
        return RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span_from_match(span=span, match=next_turn_match),
            parameters=parameters_from_pairs(
                (
                    ("endpoint", "turn"),
                    ("boundary", boundary_token),
                    ("relative", "next"),
                    ("owner", _duration_owner(next_turn_match.group("owner"))),
                )
            ),
        )

    match = _UNTIL_RE.search(text)
    if match is not None:
        return RuleDuration(
            kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            source_span=_span_from_match(span=span, match=match),
            parameters=parameters_from_pairs(
                (("endpoint", _endpoint_token(match.group("endpoint"))),)
            ),
        )

    if _AURA_RE.search(text) is not None and "while" in text.lower():
        return RuleDuration(
            kind=RuleDurationKind.WHILE_CONDITION_TRUE,
            source_span=span,
            parameters=parameters_from_pairs((("condition", "aura"),)),
        )
    return None


def _duration_owner(owner_text: str) -> str:
    if owner_text.lower() == "your":
        return "self"
    return "opponent"


def _span_from_match(*, span: TextSpan, match: re.Match[str]) -> TextSpan:
    start = span.start + match.start()
    end = span.start + match.end()
    return TextSpan(text=span.text[start - span.start : end - span.start], start=start, end=end)


def _lower_group(match: re.Match[str], group_name: str) -> str:
    return match.group(group_name).lower()


def _endpoint_token(endpoint: str) -> str:
    normalized = endpoint.lower()
    if normalized == "battle round":
        return "battle_round"
    return normalized
