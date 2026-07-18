from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleEffectKind,
    RuleEffectSpec,
    parameters_from_pairs,
)

_RESOURCE_BACKED_DICE_ROLL_OVERRIDE_RE = re.compile(
    r"\bonce\s+per\s+battle\s+for\s+each\s+"
    r"(?P<resource_name>Aspect\s+Shrine\s+token)\s+this\s+unit\s+has,\s+"
    r"you\s+can\s+change\s+the\s+result\s+of\s+one\s+Hit\s+roll\s+or\s+one\s+"
    r"Wound\s+roll\s+made\s+for\s+a\s+model\s+in\s+this\s+unit\s+"
    r"\(excluding\s+(?P<excluded_keyword>CHARACTER)\s+models\)\s+to\s+an\s+"
    r"unmodified\s+(?P<replacement_value>[1-6])\b",
    re.IGNORECASE,
)


def dice_roll_override_effects(
    text: str,
    source_span: TextSpan,
) -> tuple[RuleEffectSpec, ...]:
    match = _RESOURCE_BACKED_DICE_ROLL_OVERRIDE_RE.search(text)
    if match is None:
        return ()
    return (
        RuleEffectSpec(
            kind=RuleEffectKind.OVERRIDE_DICE_ROLL_RESULT,
            source_span=source_span,
            parameters=parameters_from_pairs(
                (
                    ("roll_types", ("hit", "wound")),
                    ("replacement_value", int(match.group("replacement_value"))),
                    ("resource_kind", "aeldari:aspect-shrine-token"),
                    ("resource_cost", 1),
                    ("resource_scope", "source_unit"),
                    ("excluded_model_keywords", (match.group("excluded_keyword").upper(),)),
                )
            ),
        ),
    )
