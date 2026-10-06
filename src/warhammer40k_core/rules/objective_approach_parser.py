"""Bounded data-boundary compilation of a real objective-directed Normal move."""

from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTargetSpec,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_templates import GRANT_ABILITY_TEMPLATE_ID

_OBJECTIVE_NORMAL_MOVE = re.compile(
    r"\AYour unit can make a Normal move\. When doing so, your unit must end that move "
    r"as close as possible to the closest objective marker\.\Z",
    re.IGNORECASE,
)


def compile_objective_approach_clauses(
    *,
    source_id: str,
    normalized_text: str,
) -> tuple[RuleClause, ...] | None:
    if _OBJECTIVE_NORMAL_MOVE.fullmatch(normalized_text) is None:
        return None
    span = TextSpan(text=normalized_text, start=0, end=len(normalized_text))
    return (
        RuleClause(
            clause_id=f"{source_id}:clause:1",
            template_id=GRANT_ABILITY_TEMPLATE_ID,
            source_span=span,
            target=RuleTargetSpec(kind=RuleTargetKind.THIS_UNIT, source_span=span),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.GRANT_ABILITY,
                    source_span=span,
                    parameters=parameters_from_pairs(
                        (
                            ("ability", "triggered_normal_move"),
                            ("movement_kind", "triggered"),
                            ("movement_mode", "normal"),
                            ("distance_kind", "normal_move_characteristic"),
                            ("endpoint_constraint", "closest_legal_objective"),
                            ("objective_selection", "closest_marker"),
                            ("optional", True),
                            ("one_per_phase", False),
                        )
                    ),
                ),
            ),
        ),
    )
