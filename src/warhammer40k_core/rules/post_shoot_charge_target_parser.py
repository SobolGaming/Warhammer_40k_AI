from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

_POST_SHOOT_CHARGE_TARGET_RE = re.compile(
    r"\A(?P<trigger>In\s+your\s+Shooting\s+phase,\s+after\s+this\s+unit\s+has\s+shot,\s+"
    r"you\s+can\s+use\s+this\s+ability\.)\s+"
    r"(?P<selection>If\s+you\s+do,\s+select\s+one\s+enemy\s+unit\s+hit\s+by\s+those\s+"
    r"ranged\s+attacks\.)\s+"
    r"(?P<effect>Until\s+the\s+end\s+of\s+the\s+turn,\s+when\s+this\s+unit\s+declares\s+"
    r"a\s+charge:\s*\n-\s+This\s+unit\s+can\s+re-roll\s+that\s+charge\s+roll\.\s*\n"
    r"-\s+This\s+unit\s+must\s+end\s+that\s+charge\s+move\s+engaged\s+with\s+that\s+"
    r"enemy\s+unit\.)\Z",
    re.IGNORECASE,
)


def compile_post_shoot_charge_target_clauses(
    *,
    source_id: str,
    normalized_text: str,
) -> tuple[RuleClause, ...] | None:
    """Compile an optional hit-target mark used by a later Charge declaration."""
    match = _POST_SHOOT_CHARGE_TARGET_RE.fullmatch(normalized_text)
    if match is None:
        return None
    trigger_span = _span(match, "trigger")
    selection_span = _span(match, "selection")
    effect_span = _span(match, "effect")
    return (
        RuleClause(
            clause_id=f"{source_id}:clause:1",
            template_id="phase17c:selected-target-constraint",
            source_span=_combined_span(normalized_text, match, "trigger", "selection"),
            trigger=RuleTrigger(
                kind=RuleTriggerKind.TIMING_WINDOW,
                source_span=trigger_span,
                parameters=parameters_from_pairs(
                    (
                        ("edge", "after"),
                        ("optional", True),
                        ("owner", "active_player"),
                        ("phase", "shooting"),
                        ("subject", "this_unit"),
                        ("target_relationship", "hit_by_those_attacks"),
                        ("timing_window", "just_after_friendly_unit_has_shot"),
                    )
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.ENEMY_UNIT,
                source_span=selection_span,
                parameters=parameters_from_pairs(
                    (
                        ("allegiance", "enemy"),
                        ("target_relationship", "hit_by_those_attacks"),
                    )
                ),
            ),
        ),
        RuleClause(
            clause_id=f"{source_id}:clause:2",
            template_id="phase17c:post-shoot-selected-target-charge",
            source_span=effect_span,
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT,
                source_span=effect_span,
            ),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.REROLL_PERMISSION,
                    source_span=effect_span,
                    parameters=parameters_from_pairs(
                        (
                            ("must_end_charge_move_engaged_with_selected_unit", True),
                            ("roll_type", "charge"),
                            ("target_reference", "selected_unit"),
                        )
                    ),
                ),
            ),
            duration=RuleDuration(
                kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                source_span=effect_span,
                parameters=parameters_from_pairs((("boundary", "end"), ("endpoint", "turn"))),
            ),
        ),
    )


def _span(match: re.Match[str], group: str) -> TextSpan:
    return TextSpan(
        text=match.group(group),
        start=match.start(group),
        end=match.end(group),
    )


def _combined_span(
    text: str,
    match: re.Match[str],
    start_group: str,
    end_group: str,
) -> TextSpan:
    start = match.start(start_group)
    end = match.end(end_group)
    return TextSpan(text=text[start:end], start=start, end=end)
