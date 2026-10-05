"""Compile a stronger reroll branch with its enclosing target condition intact."""

from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)

NESTED_ATTACK_REROLL_TEMPLATE_ID = "core:nested-closest-objective-reroll"
_NESTED_REROLL_RE = re.compile(
    r"\A(?P<subject>This\s+unit)'s\s+ranged\s+attacks\s+"
    r"(?P<parent>that\s+target\s+the\s+closest\s+eligible\s+target)\s+can"
    r"(?:\s*:\s*-\s*|\s+)"
    r"(?P<base>re-roll\s+hit\s+rolls\s+of\s+(?P<value>[1-6]))\.\s*"
    r"(?:-\s*Or:\s*)?"
    r"(?P<inner>If\s+that\s+target\s+is\s+within\s+range\s+of\s+an?\s+"
    r"objective(?:\s+marker)?\s+your\s+opponent\s+controls),\s*"
    r"(?P<upgrade>re-roll\s+hit\s+rolls)(?:\s+instead)?\.\Z",
    re.IGNORECASE,
)


def compile_nested_attack_reroll_clauses(
    *, source_id: str, normalized_text: str
) -> tuple[RuleClause, ...] | None:
    match = _NESTED_REROLL_RE.fullmatch(normalized_text)
    if match is None:
        return None
    return (
        RuleClause(
            clause_id=f"{source_id}:clause:1",
            template_id=NESTED_ATTACK_REROLL_TEMPLATE_ID,
            source_span=TextSpan(text=normalized_text, start=0, end=len(normalized_text)),
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT, source_span=_span(match, "subject")
            ),
            conditions=(
                RuleCondition(
                    kind=RuleConditionKind.TARGET_CONSTRAINT,
                    source_span=_span(match, "parent"),
                    parameters=parameters_from_pairs(
                        (
                            ("gate_subject", "attack_target"),
                            ("target_constraint", "closest_eligible"),
                        )
                    ),
                ),
            ),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.REROLL_PERMISSION,
                    source_span=TextSpan(
                        text=normalized_text[match.start("base") : match.end("upgrade")],
                        start=match.start("base"),
                        end=match.end("upgrade"),
                    ),
                    parameters=parameters_from_pairs(
                        (
                            ("attack_kind", "ranged"),
                            ("roll_type", "hit"),
                            ("reroll_unmodified_value", int(match.group("value"))),
                            (
                                "full_reroll_if_target_within_opponent_controlled_objective_range",
                                True,
                            ),
                        )
                    ),
                ),
            ),
        ),
    )


def _span(match: re.Match[str], name: str) -> TextSpan:
    return TextSpan(text=match.group(name), start=match.start(name), end=match.end(name))
