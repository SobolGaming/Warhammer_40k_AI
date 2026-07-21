from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

_ATTACK_ALLOCATED_TO_MODEL_RE = re.compile(
    r"\beach\s+time\s+an?\s+attack\s+is\s+allocated\s+to\s+"
    r"(?P<target>(?:the\s+)?bearer|this\s+model)\b",
    re.IGNORECASE,
)


def allocated_attack_clause_split_offsets(
    text: str,
) -> tuple[tuple[int, int], tuple[int, int]] | None:
    match = _ATTACK_ALLOCATED_TO_MODEL_RE.search(text)
    if match is None or match.start() == 0:
        return None
    conjunction = re.search(r"\band\s*$", text[: match.start()], re.IGNORECASE)
    if conjunction is None:
        return None
    passive_end = conjunction.start()
    while passive_end > 0 and text[passive_end - 1].isspace():
        passive_end -= 1
    return ((0, passive_end), (match.start(), len(text)))


def parse_allocated_attack_trigger(clause_span: TextSpan) -> RuleTrigger | None:
    match = _ATTACK_ALLOCATED_TO_MODEL_RE.search(clause_span.text)
    if match is None:
        return None
    source_span = TextSpan(
        text=clause_span.text[match.start() : match.end()],
        start=clause_span.start + match.start(),
        end=clause_span.start + match.end(),
    )
    return RuleTrigger(
        kind=RuleTriggerKind.TIMING_WINDOW,
        source_span=source_span,
        parameters=parameters_from_pairs(
            (
                ("edge", "during"),
                ("subject", "incoming_attack"),
                ("timing_window", "attack_allocated"),
            )
        ),
    )
