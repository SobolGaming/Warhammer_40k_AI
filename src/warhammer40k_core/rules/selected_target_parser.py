from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_keyword_sequences import keyword_sequence_parameter_pairs

_SELECTED_TARGET_RE = re.compile(
    r"\b(?:select\s+)?(?:one\s+)?(?:(?P<allegiance>friendly|enemy)\s+)?"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"unit\b(?:\s+\([^)]*\))?(?:\s+from\s+your\s+army)?(?:\s+\([^)]*\))?\s+"
    r"(?:that\s+)?was\s+selected\s+as\s+(?:the\s+)?target\b"
    r"(?:\s+of\s+one\s+or\s+more(?:\s+of\s+the\s+attacking\s+unit'?s)?\s+attacks?)?",
    re.IGNORECASE,
)


def selected_target_spec_from_text(
    *,
    text: str,
    source_start: int,
    source_keyword_sequence_parts: tuple[str, ...],
) -> RuleTargetSpec | None:
    match = _SELECTED_TARGET_RE.search(text)
    if match is None:
        return None
    allegiance = match.group("allegiance")
    selected_target_pairs: list[tuple[str, RuleParameterValue]] = [
        ("allegiance", "friendly" if allegiance is None else allegiance.lower()),
        ("source_context", "selected_target"),
    ]
    keyword_text = match.group("keyword")
    if keyword_text is not None and not is_structural_target_keyword(keyword_text):
        selected_target_pairs.extend(
            keyword_sequence_parameter_pairs(
                keyword_text,
                source_keyword_sequence_parts=source_keyword_sequence_parts,
            )
        )
    return RuleTargetSpec(
        kind=RuleTargetKind.SELECTED_TARGET,
        source_span=TextSpan(
            text=text[match.start() : match.end()],
            start=source_start + match.start(),
            end=source_start + match.end(),
        ),
        parameters=parameters_from_pairs(tuple(selected_target_pairs)),
    )


def is_structural_target_keyword(value: str) -> bool:
    token = " ".join(value.lower().split())
    return (
        " within " in f" {token} "
        or " engagement range" in token
        or " objective marker range" in token
        or " objective range" in token
        or " hit by " in f" {token} "
    )
