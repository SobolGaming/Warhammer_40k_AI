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


class MovementEndReactiveClauseText(Protocol):
    @property
    def text(self) -> str: ...

    @property
    def span(self) -> TextSpan: ...

    @property
    def start(self) -> int: ...


_MOVEMENT_END_REACTIVE_NORMAL_MOVE_RE = re.compile(
    r"^\s*(?P<trigger>In\s+your\s+opponent['\N{RIGHT SINGLE QUOTATION MARK}]s\s+"
    r"Movement\s+phase,\s+if\s+an\s+"
    r"enemy\s+unit\s+ends\s+a\s+move)\s+"
    r"(?P<trigger_distance>within\s+(?P<distance>\d+(?:\.\d+)?)\"\s+of\s+this\s+unit),\s+"
    r"(?P<engagement>if\s+this\s+unit\s+is\s+not\s+within\s+Engagement\s+Range\s+of\s+"
    r"one\s+or\s+more\s+enemy\s+units),\s+"
    r"(?P<effect>(?P<target>this\s+unit)\s+can\s+make\s+a\s+Normal\s+move\s+of\s+up\s+"
    r"to\s+(?P<quantity>\d*)D(?P<sides>\d+)\")\.?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def compile_movement_end_reactive_normal_move_clause(
    *,
    source_id: str,
    clause_index: int,
    clause_text: MovementEndReactiveClauseText,
) -> RuleClause | None:
    match = _MOVEMENT_END_REACTIVE_NORMAL_MOVE_RE.search(clause_text.text)
    if match is None:
        return None
    distance_inches = _numeric_value(match.group("distance"))
    quantity_text = match.group("quantity")
    dice_quantity = 1 if quantity_text == "" else int(quantity_text)
    dice_sides = int(match.group("sides"))
    clause_id = f"{source_id}:clause:{clause_index:03d}"
    return RuleClause(
        clause_id=clause_id,
        source_span=clause_text.span,
        trigger=RuleTrigger(
            kind=RuleTriggerKind.TIMING_WINDOW,
            source_span=_span_from_group(clause_text, match, "trigger"),
            parameters=parameters_from_pairs(
                (
                    ("edge", "after"),
                    ("owner", "opponent"),
                    ("phase", "movement"),
                    ("subject", "enemy_unit"),
                    ("timing_window", "enemy_unit_move_end"),
                )
            ),
        ),
        conditions=(
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span_from_group(clause_text, match, "trigger_distance"),
                parameters=parameters_from_pairs(
                    (
                        ("distance_inches", distance_inches),
                        ("object_kind", "unit"),
                        ("object_reference", "this"),
                        ("predicate", "within"),
                        ("qualifier", None),
                        ("range_kind", "numeric_range"),
                        ("subject", "enemy_unit"),
                    )
                ),
            ),
            RuleCondition(
                kind=RuleConditionKind.DISTANCE_PREDICATE,
                source_span=_span_from_group(clause_text, match, "engagement"),
                parameters=parameters_from_pairs(
                    (
                        ("distance_inches", None),
                        ("negated", True),
                        ("object_allegiance", "enemy"),
                        ("object_kind", "unit"),
                        ("object_quantity", "one_or_more"),
                        ("predicate", "within_engagement_range"),
                        ("qualifier", None),
                        ("range_kind", "engagement_range"),
                        ("subject", "this_unit"),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(
            kind=RuleTargetKind.THIS_UNIT,
            source_span=_span_from_group(clause_text, match, "target"),
        ),
        effects=(
            RuleEffectSpec(
                kind=RuleEffectKind.OUT_OF_PHASE_ACTION,
                source_span=_span_from_group(clause_text, match, "effect"),
                parameters=parameters_from_pairs(
                    (
                        ("action", "move"),
                        ("action_group", "movement_end_reactive_normal_move"),
                        ("distance_bonus", 0),
                        ("distance_dice_quantity", dice_quantity),
                        ("distance_dice_sides", dice_sides),
                        ("movement_kind", "triggered"),
                        ("movement_mode", "normal"),
                        ("optional", True),
                    )
                ),
            ),
        ),
        template_id=OUT_OF_PHASE_ACTION_TEMPLATE_ID,
    )


def _span_from_group(
    clause_text: MovementEndReactiveClauseText,
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


def _numeric_value(value: str) -> RuleParameterValue:
    if "." in value:
        return float(value)
    return int(value)
