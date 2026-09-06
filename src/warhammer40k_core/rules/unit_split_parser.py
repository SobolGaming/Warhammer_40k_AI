"""Compile the source-backed pre-battle partition wording at the data boundary."""

from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

_PREBATTLE_SPLIT = re.compile(
    r"At the start of the Declare Battle Formations step, before any units have been set up, "
    r"this unit can be split into two units, each containing (?P<count>five|[1-9][0-9]*) models\.",
    re.IGNORECASE,
)


def compile_prebattle_split_clauses(
    *, source_id: str, normalized_text: str
) -> tuple[RuleClause, ...] | None:
    match = _PREBATTLE_SPLIT.fullmatch(normalized_text)
    if match is None:
        return None
    count_token = match.group("count")
    count = 5 if count_token.lower() == "five" else int(count_token)
    span = TextSpan(normalized_text, 0, len(normalized_text))
    return (
        RuleClause(
            clause_id=f"{source_id}:clause:1",
            source_span=span,
            trigger=RuleTrigger(
                RuleTriggerKind.SETUP,
                span,
                parameters_from_pairs(
                    (("timing_window", "declare_battle_formations"), ("edge", "before"))
                ),
            ),
            target=RuleTargetSpec(RuleTargetKind.THIS_UNIT, span),
            effects=(
                RuleEffectSpec(
                    RuleEffectKind.SPLIT_UNIT,
                    span,
                    parameters_from_pairs(
                        (("first_strength", count), ("second_strength", count), ("optional", True))
                    ),
                ),
            ),
        ),
    )
