from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    RuleParameterValue,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

_ROLL_TYPES = "Hit|Wound|Damage|Save|Leadership|Battle-shock|Desperate Escape|Advance|Charge"
_THIS_MODEL_ATTACK_TARGET_UNIT_RE = re.compile(
    r"\beach\s+time\s+this\s+model\s+makes\s+(?:a|an)\s+"
    r"(?:(?P<attack_kind>melee|ranged)\s+)?attack\s+that\s+targets\s+"
    r"(?:a|an)\s+(?P<allegiance>enemy|friendly)\s+unit"
    r"(?:\s+that\s+is\s+(?P<not_below_half>not\s+below\s+Half-strength))?\b",
    re.IGNORECASE,
)
_THIS_MODEL_ATTACK_TARGET_REFERENCE_RE = re.compile(
    r"\beach\s+time\s+this\s+model\s+makes\s+(?:a|an)\s+"
    r"(?:(?P<attack_kind>melee|ranged)\s+)?attack\s+that\s+targets\s+"
    r"(?:that|selected|target)\s+unit\b",
    re.IGNORECASE,
)
_ADD_ROLL_RE = re.compile(
    rf"\b(?P<verb>add|subtract)\s+(?P<value>\d+)\s+(?:to|from)\s+"
    rf"(?:(?:the|each\s+of\s+those|each\s+of\s+these)\s+)?"
    rf"(?P<roll>{_ROLL_TYPES})\s+(?:rolls?|tests?)\b",
    re.IGNORECASE,
)
_SIGNED_ROLL_RE = re.compile(
    rf"(?<![A-Za-z0-9_])(?P<sign>[+-])(?P<value>\d+)\s+to\s+"
    rf"(?:(?:the|each\s+of\s+those|each\s+of\s+these)\s+)?"
    rf"(?P<roll>{_ROLL_TYPES})\s+(?:rolls?|tests?)\b",
    re.IGNORECASE,
)
_REROLL_RE = re.compile(
    rf"\b(?:(?:you\s+)?can\s+)?(?:re-roll|reroll)\s+"
    rf"(?:the\s+)?(?P<roll>{_ROLL_TYPES})\s+roll\b",
    re.IGNORECASE,
)


def parse_this_model_attack_target_trigger(clause_span: TextSpan) -> RuleTrigger | None:
    match = _THIS_MODEL_ATTACK_TARGET_UNIT_RE.search(clause_span.text)
    if match is None:
        match = _THIS_MODEL_ATTACK_TARGET_REFERENCE_RE.search(clause_span.text)
    if match is None:
        return None
    return RuleTrigger(
        kind=RuleTriggerKind.DICE_ROLL,
        source_span=_span_from_match(clause_span, match),
        parameters=parameters_from_pairs(
            _attack_target_trigger_parameter_pairs(clause_span=clause_span, match=match)
        ),
    )


def parse_this_model_attack_target_conditions(
    clause_span: TextSpan,
) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _THIS_MODEL_ATTACK_TARGET_UNIT_RE.finditer(clause_span.text):
        pairs: list[tuple[str, RuleParameterValue]] = [
            ("relationship", "this_model_makes_attack"),
            ("gate_subject", "attack_target"),
            ("target_allegiance", _lower_group(match, "allegiance")),
        ]
        attack_kind = match.group("attack_kind")
        if attack_kind is not None:
            pairs.append(("attack_kind", _lower_group(match, "attack_kind")))
        if match.group("not_below_half") is not None:
            pairs.append(("target_constraint", "target_not_below_half_strength"))
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(tuple(pairs)),
            )
        )
    for match in _THIS_MODEL_ATTACK_TARGET_REFERENCE_RE.finditer(clause_span.text):
        reference_pairs: list[tuple[str, RuleParameterValue]] = [
            ("relationship", "this_model_makes_attack"),
            ("gate_subject", "attack_target"),
            ("target_reference", "selected_unit"),
        ]
        attack_kind = match.group("attack_kind")
        if attack_kind is not None:
            reference_pairs.append(("attack_kind", _lower_group(match, "attack_kind")))
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(clause_span, match),
                parameters=parameters_from_pairs(tuple(reference_pairs)),
            )
        )
    return tuple(conditions)


def this_model_attack_target_match_ranges(text: str) -> tuple[tuple[int, int], ...]:
    return (
        *tuple(
            (match.start(), match.end())
            for match in _THIS_MODEL_ATTACK_TARGET_UNIT_RE.finditer(text)
        ),
        *tuple(
            (match.start(), match.end())
            for match in _THIS_MODEL_ATTACK_TARGET_REFERENCE_RE.finditer(text)
        ),
    )


def has_this_model_attack_target(text: str) -> bool:
    return (
        _THIS_MODEL_ATTACK_TARGET_UNIT_RE.search(text) is not None
        or _THIS_MODEL_ATTACK_TARGET_REFERENCE_RE.search(text) is not None
    )


def _attack_target_trigger_parameter_pairs(
    *,
    clause_span: TextSpan,
    match: re.Match[str],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    roll_types = _roll_types_for_attack_language(clause_span.text)
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("actor", "this_model"),
    ]
    if "allegiance" in match.groupdict():
        pairs.append(("target_allegiance", _lower_group(match, "allegiance")))
    else:
        pairs.append(("target_reference", "selected_unit"))
    attack_kind = match.group("attack_kind")
    if attack_kind is not None:
        pairs.append(("attack_kind", _lower_group(match, "attack_kind")))
    if len(roll_types) == 1:
        roll_type = roll_types[0]
        pairs.extend(
            (
                ("roll_type", roll_type),
                ("timing_window", f"attack_sequence.{roll_type}"),
            )
        )
    elif roll_types:
        pairs.extend(
            (
                ("roll_types", roll_types),
                ("timing_window", "attack_sequence.roll"),
            )
        )
    else:
        pairs.append(("timing_window", "attack_sequence.attack"))
    return tuple(pairs)


def _roll_types_for_attack_language(text: str) -> tuple[str, ...]:
    roll_types: list[str] = []
    for match in _ADD_ROLL_RE.finditer(text):
        roll_types.append(_roll_type(match.group("roll")))
    for match in _SIGNED_ROLL_RE.finditer(text):
        roll_types.append(_roll_type(match.group("roll")))
    for match in _REROLL_RE.finditer(text):
        roll_types.append(_roll_type(match.group("roll")))
    return tuple(dict.fromkeys(roll_types))


def _span_from_match(clause_span: TextSpan, match: re.Match[str]) -> TextSpan:
    return TextSpan(
        text=match.group(0),
        start=clause_span.start + match.start(),
        end=clause_span.start + match.end(),
    )


def _lower_group(match: re.Match[str], name: str) -> str:
    return " ".join(match.group(name).lower().split())


def _roll_type(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")
