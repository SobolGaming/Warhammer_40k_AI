from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

STRATAGEM_COST_EFFECT_RE = re.compile(
    r"\b(?P<verb>increase|reduce)\s+(?:the\s+)?(?:CP\s+)?cost\s+of\s+"
    r"(?:(?:the|that)\s+)?(?:use|usage)\s+of\s+(?:that|the)\s+Stratagem\s+"
    r"by\s+(?P<value>\d+)\s*CP\b",
    re.IGNORECASE,
)
STRATAGEM_COST_EFFECT_CONTINUATION_RE = re.compile(
    rf"^\s*(?:if\s+(?:it\s+does|you\s+do),\s*)?(?:{STRATAGEM_COST_EFFECT_RE.pattern})",
    re.IGNORECASE,
)
STRATAGEM_COST_TRIGGER_RE = re.compile(
    r"\b(?:when|each\s+time)\s+(?P<trigger>"
    r"your\s+opponent\s+targets\s+a\s+unit\s+from\s+their\s+army"
    r"(?:\s+within\s+\d+(?:\.\d+)?\"\s+of\s+"
    r"(?:this\s+model|(?:the\s+)?bearer))?\s+with\s+a\s+Stratagem"
    r"|(?P<source_target>its\s+unit|this\s+model(?:'s\s+unit)?|"
    r"a\s+friendly\s+.+?\s+unit(?:\s+within\s+\d+(?:\.\d+)?\"\s+of\s+"
    r"(?:this|that)\s+model)?)\s+is\s+targeted\s+with\s+a\s+Stratagem"
    r"|you\s+target\s+(?P<direct_source_target>this\s+model(?:'s\s+unit)?|"
    r"(?:the\s+)?bearer's\s+unit)\s+with\s+a\s+Stratagem"
    r")\b",
    re.IGNORECASE,
)
STRATAGEM_COST_POST_TRIGGER_RANGE_RE = re.compile(
    r"\bif\s+that\s+unit\s+is\s+within\s+\d+(?:\.\d+)?\"\s+of\s+"
    r"(?:this\s+model|(?:the\s+)?bearer)\b",
    re.IGNORECASE,
)
_COMMAND_POINT_LEDGER_RE = re.compile(
    r"\b(?:you\s+)?(?P<verb>gain|add|refund|spend|lose|remove)\s+(?P<value>\d+)\s*"
    r"(?:CP|Command Points?|Command point)\b",
    re.IGNORECASE,
)
_SOURCE_MODEL_ON_BATTLEFIELD_RE = re.compile(
    r"\bif\s+this\s+model\s+is\s+on\s+the\s+battlefield\b",
    re.IGNORECASE,
)
LEADERSHIP_TEST_RE = re.compile(
    r"\b(?:take|takes)\s+a\s+Leadership\s+test\b",
    re.IGNORECASE,
)
LEADERSHIP_TEST_PASSED_CONTINUATION_RE = re.compile(
    r"^\s*if\s+(?:that|the)\s+test\s+is\s+passed\b",
    re.IGNORECASE,
)
_LEADERSHIP_TEST_PASSED_RE = re.compile(
    r"\b(?:take|takes)\s+a\s+Leadership\s+test"
    r"(?:\s+for\s+(?P<target>this\s+model|this\s+unit|the\s+bearer|bearer))?\s*"
    r"[;,]?\s*if\s+(?:that|the)\s+test\s+is\s+passed\b",
    re.IGNORECASE,
)
_FIXED_COMMAND_POINT_ROLL_GATE_RE = re.compile(
    r"\broll\s+(?:(?P<word_quantity>one)\s+)?(?P<quantity>\d+)?D6\s*:\s*"
    r"on\s+a\s+(?P<threshold>\d+)\+",
    re.IGNORECASE,
)
_OPTIONAL_COST_USE_RE = re.compile(
    r"\b(?:can\s+use\s+(?:this\s+(?:ability|Enhancement)|it)|"
    r"may\s+(?:increase|reduce)|"
    r"can\s+(?:increase|reduce))\b",
    re.IGNORECASE,
)
_NON_CUMULATIVE_COST_INCREASE_RE = re.compile(
    r"\(?(?:this\s+is\s+)?not\s+cumulative\s+with\s+any\s+other\s+rules?\s+that\s+"
    r"(?:would\s+)?increase\s+the\s+CP\s+cost"
    r"(?:\s+of\s+(?:that|the)\s+Stratagem)?\)?",
    re.IGNORECASE,
)


def parse_command_point_trigger(clause_span: TextSpan) -> RuleTrigger | None:
    match = STRATAGEM_COST_TRIGGER_RE.search(clause_span.text)
    if match is None:
        return None
    opponent_use = _trigger_is_opponent_use(match)
    relationship = _stratagem_target_relationship(match, clause_span.text)
    return RuleTrigger(
        kind=RuleTriggerKind.UNIT_SELECTED,
        source_span=_span_from_match(clause_span, match),
        parameters=parameters_from_pairs(
            (
                ("selected_unit_allegiance", "enemy" if opponent_use else "friendly"),
                ("selection", "stratagem_target"),
                ("source_relationship", relationship),
                ("stratagem_user", "opponent" if opponent_use else "source_player"),
                ("timing_window", "after_unit_selected_as_stratagem_target"),
                ("usage_scope", _stratagem_cost_usage_scope(clause_span.text)),
            )
        ),
    )


def parse_command_point_conditions(clause_span: TextSpan) -> tuple[RuleCondition, ...]:
    if not has_command_point_effect(clause_span.text):
        return ()
    conditions: list[RuleCondition] = []
    trigger_match = STRATAGEM_COST_TRIGGER_RE.search(clause_span.text)
    if trigger_match is not None:
        opponent_use = _trigger_is_opponent_use(trigger_match)
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_stratagem_cost_relationship_span(
                    clause_span,
                    trigger_match=trigger_match,
                ),
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "stratagem_target"),
                        (
                            "relationship",
                            _stratagem_target_relationship(trigger_match, clause_span.text),
                        ),
                        (
                            "selected_unit_allegiance",
                            "enemy" if opponent_use else "friendly",
                        ),
                    )
                ),
            )
        )
    for match in _SOURCE_MODEL_ON_BATTLEFIELD_RE.finditer(clause_span.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("gate_subject", "source_model"),
                        ("relationship", "source_model_on_battlefield"),
                    )
                ),
            )
        )
    for match in _LEADERSHIP_TEST_PASSED_RE.finditer(clause_span.text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.DICE_ROLL_GATE,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("comparison", "greater_or_equal"),
                        ("roll_count", 2),
                        ("roll_expression", "2D6"),
                        ("roll_type", "leadership"),
                        ("success_threshold_source", "target_leadership"),
                        ("test_target", _leadership_test_target(match)),
                    )
                ),
            )
        )
    for match in _FIXED_COMMAND_POINT_ROLL_GATE_RE.finditer(clause_span.text):
        quantity_token = match.group("quantity")
        quantity = 1 if quantity_token is None else int(quantity_token)
        expression = "D6" if quantity == 1 else f"{quantity}D6"
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.DICE_ROLL_GATE,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("comparison", "greater_or_equal"),
                        ("roll_count", quantity),
                        ("roll_expression", expression),
                        ("roll_type", "command_point_gain"),
                        ("success_threshold", int(match.group("threshold"))),
                    )
                ),
            )
        )
    return tuple(conditions)


def parse_command_point_effects(clause_span: TextSpan) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in STRATAGEM_COST_EFFECT_RE.finditer(clause_span.text):
        verb = match.group("verb").lower()
        value = int(match.group("value"))
        delta = value if verb == "increase" else -value
        non_cumulative_match = _NON_CUMULATIVE_COST_INCREASE_RE.search(clause_span.text)
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                source_span=_combined_span(
                    clause_span,
                    first=match,
                    second=non_cumulative_match,
                ),
                parameters=parameters_from_pairs(
                    (
                        ("affected_player", "opponent" if delta > 0 else "source_player"),
                        ("application_scope", "current_stratagem_use"),
                        ("delta", delta),
                        ("minimum_cost", 0),
                        ("operation", "modify_stratagem_cost"),
                        ("optional", _OPTIONAL_COST_USE_RE.search(clause_span.text) is not None),
                        (
                            "stacking",
                            (
                                "non_cumulative_cost_increase"
                                if non_cumulative_match is not None
                                else "cumulative"
                            ),
                        ),
                    )
                ),
            )
        )
    for match in _COMMAND_POINT_LEDGER_RE.finditer(clause_span.text):
        verb = match.group("verb").lower()
        value = int(match.group("value"))
        operation = _ledger_operation(verb)
        delta = -value if operation == "spend" else value
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.MODIFY_COMMAND_POINTS,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("affected_player", "source_player"),
                        ("delta", delta),
                        ("operation", operation),
                    )
                ),
            )
        )
    return tuple(effects)


def command_point_target(clause_span: TextSpan) -> RuleTargetSpec | None:
    cost_match = STRATAGEM_COST_EFFECT_RE.search(clause_span.text)
    if cost_match is not None:
        return RuleTargetSpec(
            kind=RuleTargetKind.STRATAGEM_USE,
            source_span=_span_from_match(clause_span, cost_match),
        )
    ledger_match = _COMMAND_POINT_LEDGER_RE.search(clause_span.text)
    if ledger_match is None:
        return None
    return RuleTargetSpec(
        kind=RuleTargetKind.PLAYER,
        source_span=_span_from_match(clause_span, ledger_match),
        parameters=parameters_from_pairs((("relationship", "source_player"),)),
    )


def has_command_point_effect(text: str) -> bool:
    return (
        STRATAGEM_COST_EFFECT_RE.search(text) is not None
        or _COMMAND_POINT_LEDGER_RE.search(text) is not None
    )


def command_point_frequency_span_end(text: str, *, fallback_end: int) -> int:
    if _OPTIONAL_COST_USE_RE.search(text) is None:
        return fallback_end
    effect_match = STRATAGEM_COST_EFFECT_RE.search(text)
    if effect_match is None:
        return fallback_end
    return effect_match.start()


def _trigger_is_opponent_use(match: re.Match[str]) -> bool:
    return match.group("source_target") is None and match.group("direct_source_target") is None


def _stratagem_target_relationship(match: re.Match[str], clause_text: str) -> str:
    trigger_text = match.group("trigger").lower()
    if (
        "within" in trigger_text
        or STRATAGEM_COST_POST_TRIGGER_RANGE_RE.search(clause_text) is not None
    ):
        return "stratagem_targets_unit_within_source_model_range"
    return "stratagem_targets_source_unit"


def _stratagem_cost_relationship_span(
    clause_span: TextSpan,
    *,
    trigger_match: re.Match[str],
) -> TextSpan:
    range_match = STRATAGEM_COST_POST_TRIGGER_RANGE_RE.search(clause_span.text)
    if range_match is not None:
        return _span_from_match(clause_span, range_match)
    return _span_from_match(clause_span, trigger_match)


def _stratagem_cost_usage_scope(text: str) -> str:
    if (
        re.search(
            r"\bone\s+unit\s+from\s+your\s+army\s+with\s+this\s+ability\b",
            text,
            re.IGNORECASE,
        )
        is not None
    ):
        return "army_ability"
    return "source_model"


def _leadership_test_target(match: re.Match[str]) -> str:
    target = match.group("target")
    if target is None:
        return "this_model"
    token = " ".join(target.lower().split())
    if token == "this model":
        return "this_model"
    if token == "this unit":
        return "this_unit"
    return "bearer"


def _ledger_operation(verb: str) -> str:
    if verb in {"gain", "add"}:
        return "gain"
    if verb == "refund":
        return "refund"
    return "spend"


def _span_from_match(span: TextSpan, match: re.Match[str]) -> TextSpan:
    return TextSpan(
        text=match.group(0),
        start=span.start + match.start(),
        end=span.start + match.end(),
    )


def _combined_span(
    span: TextSpan,
    *,
    first: re.Match[str],
    second: re.Match[str] | None,
) -> TextSpan:
    start = first.start() if second is None else min(first.start(), second.start())
    end = first.end() if second is None else max(first.end(), second.end())
    return TextSpan(
        text=span.text[start:end],
        start=span.start + start,
        end=span.start + end,
    )
