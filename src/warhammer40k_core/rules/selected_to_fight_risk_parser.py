from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
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

_SELECTED_TO_FIGHT_RISK_RE = re.compile(
    r"\A(?P<activation>Each\s+time\s+this\s+unit\s+is\s+selected\s+to\s+fight,\s+"
    r"it\s+can\s+[^.]+\.)\s+"
    r"(?P<benefit>If\s+it\s+does,\s+until\s+the\s+end\s+of\s+the\s+phase,\s+"
    r"each\s+time\s+a\s+model\s+in\s+this\s+unit\s+makes\s+an\s+attack,\s+"
    r"an\s+unmodified\s+Wound\s+roll\s+of\s+(?P<threshold>[2-6])\+\s+scores\s+"
    r"a\s+Critical\s+Wound\.)\s+"
    r"(?P<risk>At\s+the\s+end\s+of\s+the\s+Fight\s+phase,\s+if\s+this\s+unit\s+"
    r"[^.]+?\s+this\s+phase\s+and\s+no\s+enemy\s+models\s+were\s+destroyed\s+by\s+"
    r"attacks\s+made\s+by\s+models\s+in\s+this\s+unit\s+this\s+phase,\s+one\s+model\s+"
    r"in\s+this\s+unit\s+is\s+destroyed\.)\Z",
    re.IGNORECASE,
)


def compile_selected_to_fight_risk_clauses(
    *,
    source_id: str,
    normalized_text: str,
) -> tuple[RuleClause, ...] | None:
    """Compile an optional Fight activation with a failed-kill model-destruction risk."""
    match = _SELECTED_TO_FIGHT_RISK_RE.fullmatch(normalized_text)
    if match is None:
        return None
    activation_span = _combined_span(normalized_text, match, "activation", "benefit")
    benefit_span = _span(normalized_text, match, "benefit")
    risk_span = _span(normalized_text, match, "risk")
    threshold = int(match.group("threshold"))
    return (
        RuleClause(
            clause_id=f"{source_id}:clause:1",
            template_id="phase17c:contextual-status",
            source_span=activation_span,
            trigger=RuleTrigger(
                kind=RuleTriggerKind.UNIT_SELECTED,
                source_span=_span(normalized_text, match, "activation"),
                parameters=parameters_from_pairs(
                    (
                        ("phase", "fight"),
                        ("timing_window", "selected_to_fight"),
                        ("optional", True),
                    )
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT,
                source_span=activation_span,
            ),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                    source_span=benefit_span,
                    parameters=parameters_from_pairs(
                        (
                            ("status", "critical_wound_threshold"),
                            ("roll_type", "wound"),
                            ("attack_role", "attacker"),
                            ("critical_threshold", threshold),
                        )
                    ),
                ),
            ),
            duration=RuleDuration(
                kind=RuleDurationKind.UNTIL_TIMING_ENDPOINT,
                source_span=benefit_span,
                parameters=parameters_from_pairs((("endpoint", "phase"), ("boundary", "end"))),
            ),
        ),
        RuleClause(
            clause_id=f"{source_id}:clause:2",
            template_id="phase17c:timing-window",
            source_span=risk_span,
            trigger=RuleTrigger(
                kind=RuleTriggerKind.TIMING_WINDOW,
                source_span=risk_span,
                parameters=parameters_from_pairs((("edge", "end"), ("phase", "fight"))),
            ),
            conditions=(
                RuleCondition(
                    kind=RuleConditionKind.TARGET_CONSTRAINT,
                    source_span=risk_span,
                    parameters=parameters_from_pairs(
                        (("constraint", "source_effect_activated_this_phase"),)
                    ),
                ),
                RuleCondition(
                    kind=RuleConditionKind.TARGET_CONSTRAINT,
                    source_span=risk_span,
                    parameters=parameters_from_pairs(
                        (
                            (
                                "constraint",
                                "no_enemy_model_destroyed_by_this_unit_attacks_this_phase",
                            ),
                        )
                    ),
                ),
            ),
            target=RuleTargetSpec(
                kind=RuleTargetKind.THIS_UNIT,
                source_span=risk_span,
            ),
            effects=(
                RuleEffectSpec(
                    kind=RuleEffectKind.DESTROY_MODEL,
                    source_span=risk_span,
                    parameters=parameters_from_pairs(
                        (
                            ("destroy_count", 1),
                            ("selection_policy", "controlling_player"),
                            ("target_scope", "one_model_in_this_unit"),
                        )
                    ),
                ),
            ),
            duration=RuleDuration(
                kind=RuleDurationKind.IMMEDIATE,
                source_span=risk_span,
            ),
        ),
    )


def _span(text: str, match: re.Match[str], group: str) -> TextSpan:
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
