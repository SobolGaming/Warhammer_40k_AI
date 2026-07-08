from __future__ import annotations

import re
from typing import Protocol

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIRError,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)
from warhammer40k_core.rules.rule_templates import OUT_OF_PHASE_ACTION_TEMPLATE_ID


class SetupReactiveClauseText(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def span(self) -> TextSpan: ...

    @property
    def start(self) -> int: ...


_SETUP_REACTIVE_SHOOT_CHARGE_RE = re.compile(
    r"(?P<trigger>\bat\s+the\s+end\s+of\s+your\s+opponent's\s+Movement\s+phase),\s+"
    r"you\s+can\s+(?P<select>select\s+one\s+enemy\s+unit\s+that\s+was\s+set\s+up\s+"
    r"on\s+the\s+battlefield\s+within\s+(?P<distance>\d+(?:\.\d+)?)\"\s+of\s+"
    r"this\s+model);\s+"
    r"(?P<source>this\s+model)\s+can\s+then\s+either\s*:\s*"
    r"(?:\u25a0|-)?\s*(?P<shoot>Shoot\s+at\s+that\s+unit,\s+but\s+only\s+if\s+it\s+"
    r"is\s+an\s+eligible\s+target)\.\s*"
    r"(?:\u25a0|-)?\s*(?P<charge>Declare\s+a\s+charge(?:\s+against\s+that\s+unit)?"
    r"(?:\.\s*This\s+unit\s+must\s+end\s+that\s+charge\s+move\s+engaged\s+with\s+"
    r"the\s+enemy\s+unit\s+you\s+selected)?\s*"
    r"\(note\s+that\s+even\s+if\s+this\s+charge\s+is\s+successful,\s+this\s+"
    r"(?:model|unit)\s+does\s+not\s+receive\s+any\s+Charge\s+bonus\s+this\s+turn\))"
    r"\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def compile_setup_reactive_shoot_charge_clause(
    *,
    source_id: str,
    clause_index: int,
    clause_text: SetupReactiveClauseText,
) -> RuleClause | None:
    match = _SETUP_REACTIVE_SHOOT_CHARGE_RE.search(clause_text.text)
    if match is None:
        return None
    distance_inches = _numeric_distance_inches(match.group("distance"))
    clause_id = f"{source_id}:clause:{clause_index:03d}"
    return RuleClause(
        clause_id=clause_id,
        source_span=clause_text.span,
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_group(clause_text, match, "trigger"),
            parameters=parameters_from_pairs(
                (
                    ("edge", "end"),
                    ("owner", "opponent"),
                    ("phase", "movement"),
                    ("timing_window", "end_opponent_movement_phase"),
                )
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_group(clause_text, match, "select"),
                parameters=parameters_from_pairs(
                    (
                        ("relationship", "selected_unit_set_up_on_battlefield_this_phase"),
                        ("gate_subject", "selected_unit"),
                    )
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span_from_group(clause_text, match, "select"),
                parameters=parameters_from_pairs(
                    (
                        ("predicate", "within"),
                        ("distance_inches", distance_inches),
                        ("qualifier", None),
                        ("range_kind", "numeric_range"),
                        ("object_kind", "model"),
                        ("object_reference", "this"),
                        ("subject", "selected_unit"),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.ENEMY_UNIT,
            source_span=_span_from_group(clause_text, match, "select"),
            parameters=parameters_from_pairs((("allegiance", "enemy"),)),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.OUT_OF_PHASE_ACTION,
                source_span=_span_from_group(clause_text, match, "shoot"),
                parameters=parameters_from_pairs(
                    (
                        ("action_group", "setup_reactive_shoot_charge"),
                        ("action", "shoot"),
                        ("action_source", "this_model"),
                        ("target_reference", "selected_unit"),
                        ("eligible_target_required", True),
                    )
                ),
            ),
            RuleEffectSpec(
                kind=RuleEffectKind.OUT_OF_PHASE_ACTION,
                source_span=_span_from_group(clause_text, match, "charge"),
                parameters=parameters_from_pairs(
                    (
                        ("action_group", "setup_reactive_shoot_charge"),
                        ("action", "charge"),
                        ("action_source", "this_model"),
                        ("target_reference", "selected_unit"),
                        ("must_end_engaged_with_selected_unit", True),
                        ("suppress_charge_bonus", True),
                        ("suppressed_charge_bonus", "fights_first"),
                    )
                ),
            ),
        ),
        template_id=OUT_OF_PHASE_ACTION_TEMPLATE_ID,
    )


def _span_from_group(
    clause_text: SetupReactiveClauseText,
    match: re.Match[str],
    group_name: str,
) -> TextSpan:
    group_start = match.start(group_name)
    group_end = match.end(group_name)
    if group_start < 0 or group_end < group_start:
        raise RuleIRError(f"Rule parser regex group is missing: {group_name}.")
    start = clause_text.start + group_start
    end = clause_text.start + group_end
    return TextSpan(text=clause_text.span.text[group_start:group_end], start=start, end=end)


def _numeric_distance_inches(value: str) -> RuleParameterValue:
    if "." in value:
        return float(value)
    return int(value)
