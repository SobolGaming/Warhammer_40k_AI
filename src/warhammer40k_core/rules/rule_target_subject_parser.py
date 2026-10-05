"""Source-bound target subjects, including the Core default unit noun."""

from __future__ import annotations

import re
from dataclasses import replace

from warhammer40k_core.rules.rule_ir import (
    RuleParameter,
    RuleTrigger,
    parameter_payload,
)

_EXPLICIT_TARGET_RE = re.compile(
    r"\b(?:select\s+)?(?:one\s+)?(?:new\s+)?(?P<allegiance>friendly|enemy)\s+"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?P<subject_noun>model|unit)\b",
    re.IGNORECASE,
)


def target_subject_matches(
    text: str, *, source_keyword_sequence_parts: tuple[str, ...]
) -> tuple[re.Match[str], ...]:
    """Preserve explicit subjects; infer only source-known selected keyword units.

    Raw text and literal spans remain intact. The source vocabulary bounds omitted
    subjects so unrelated prose cannot become a supported target. This performs
    no singular/plural aliasing and never changes an explicit model/unit form.
    """
    explicit = tuple(_EXPLICIT_TARGET_RE.finditer(text))
    keyword_pattern = "|".join(
        re.escape(keyword).replace(r"\ ", r"\s+")
        for keyword in sorted(source_keyword_sequence_parts, key=len, reverse=True)
    )
    implicit_re = re.compile(
        r"\bselect\s+one\s+(?P<allegiance>friendly|enemy)\s+"
        rf"(?P<keyword>(?:{keyword_pattern})(?:\s+(?:{keyword_pattern}))*)"
        r"(?=\s+(?:within|from\s+your\s+army|visible)\b|\s*[,.;]|\s*$)",
        re.IGNORECASE,
    )
    implicit = tuple(
        match
        for match in implicit_re.finditer(text)
        if not any(start.start() <= match.start() < start.end() for start in explicit)
    )
    return tuple(sorted((*explicit, *implicit), key=lambda match: match.start()))


def first_target_subject_match(
    text: str, *, source_keyword_sequence_parts: tuple[str, ...]
) -> re.Match[str] | None:
    matches = target_subject_matches(
        text, source_keyword_sequence_parts=source_keyword_sequence_parts
    )
    return matches[0] if matches else None


def selection_trigger_with_subject(
    trigger: RuleTrigger | None,
    *,
    template_id: str | None,
    text: str,
    source_keyword_sequence_parts: tuple[str, ...],
) -> RuleTrigger | None:
    """Retain explicit model evidence before the unit-only ordinary selector.

    Older target IR uses a unit kind for either explicit noun. Preserve that
    representation while preventing new unit execution from erasing the noun.
    This is normalization at the source boundary, not runtime text discovery.
    """
    if (
        trigger is None
        or template_id != "phase17c:selected-target-constraint"
        or parameter_payload(trigger.parameters)
        != {"edge": "start", "owner": "opponent", "phase": "shooting"}
    ):
        return trigger
    match = first_target_subject_match(
        text, source_keyword_sequence_parts=source_keyword_sequence_parts
    )
    noun = None if match is None else match.groupdict().get("subject_noun")
    if noun is None or noun.casefold() != "model":
        return trigger
    return replace(
        trigger, parameters=(*trigger.parameters, RuleParameter("subject", "selected_model"))
    )
