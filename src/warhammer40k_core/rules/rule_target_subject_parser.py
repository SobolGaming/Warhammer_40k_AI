"""Source-bound target subjects, including the Core default unit noun."""

from __future__ import annotations

import re

_EXPLICIT_TARGET_RE = re.compile(
    r"\b(?:select\s+)?(?:one\s+)?(?:new\s+)?(?P<allegiance>friendly|enemy)\s+"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"(?:model|unit)\b",
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
