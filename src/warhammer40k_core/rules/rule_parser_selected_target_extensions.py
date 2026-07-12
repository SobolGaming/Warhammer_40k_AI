from __future__ import annotations

import re

from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_ir import (
    RuleCondition,
    RuleConditionKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleParameterValue,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)

_SELECTED_TARGET_ATTACK_RE = re.compile(
    r"\beach\s+time\s+(?:a\s+)?(?!models?\s+in\b)"
    r"(?:(?P<allegiance>friendly|enemy)\s+)?"
    r"(?:(?P<keyword>[A-Z][A-Z0-9_'-]*(?:\s+[A-Z0-9_'-]+){0,5})\s+)?"
    r"unit\s+makes\s+(?:a|an)\s+"
    r"(?:(?P<attack_kind>melee|ranged)\s+)?attack\s+that\s+targets\s+"
    r"(?:that|selected|target)\s+unit\b",
    re.IGNORECASE,
)
_SELECTED_UNIT_BATTLE_SHOCK_TEST_RE = re.compile(
    r"\b(?P<target>that\s+unit|selected\s+unit|target\s+unit)\s+must\s+take\s+"
    r"a\s+Battle-shock\s+test\b",
    re.IGNORECASE,
)
_SHADOW_OF_CHAOS_AREA_RE = re.compile(
    r"\bthe\s+area\s+of\s+the\s+battlefield\s+within\s+(?P<distance>\d+(?:\.\d+)?)\"?\s+"
    r"of\s+this\s+Fortification\s+is\s+considered\s+to\s+be\s+within\s+your\s+"
    r"army's\s+Shadow\s+of\s+Chaos\b",
    re.IGNORECASE,
)
_VISIBLE_TO_RE = re.compile(
    r"\bvisible\s+to\s+(?P<observer>this\s+model|this\s+unit)\b",
    re.IGNORECASE,
)


def parse_selected_target_attack_trigger(
    *,
    text: str,
    source_span: TextSpan,
) -> RuleTrigger | None:
    match = _SELECTED_TARGET_ATTACK_RE.search(text)
    if match is None:
        return None
    return RuleTrigger(
        kind=RuleTriggerKind.DICE_ROLL,
        source_span=_span_from_match(source_span, match),
        parameters=parameters_from_pairs(_selected_target_attack_trigger_parameter_pairs(match)),
    )


def parse_selected_target_attack_conditions(
    *,
    text: str,
    source_span: TextSpan,
) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _SELECTED_TARGET_ATTACK_RE.finditer(text):
        pairs: list[tuple[str, RuleParameterValue]] = [
            ("gate_subject", "attack_target"),
            ("relationship", "attack_targets_selected_unit"),
            ("target_reference", "selected_unit"),
        ]
        attack_kind = match.group("attack_kind")
        if attack_kind is not None:
            pairs.append(("attack_kind", _lower_group(match, "attack_kind")))
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.TARGET_CONSTRAINT,
                source_span=_span_from_match(source_span, match),
                parameters=parameters_from_pairs(tuple(pairs)),
            )
        )
    return tuple(conditions)


def selected_target_attack_match_ranges(text: str) -> tuple[tuple[int, int], ...]:
    return tuple(
        (match.start(), match.end()) for match in _SELECTED_TARGET_ATTACK_RE.finditer(text)
    )


def parse_visibility_conditions(
    *,
    text: str,
    source_span: TextSpan,
) -> tuple[RuleCondition, ...]:
    conditions: list[RuleCondition] = []
    for match in _VISIBLE_TO_RE.finditer(text):
        conditions.append(
            RuleCondition(
                kind=RuleConditionKind.VISIBILITY_PREDICATE,
                source_span=_span_from_match(source_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("observer", _subject_token(match.group("observer"))),
                        ("predicate", "visible_to"),
                        ("target_reference", "selected_unit"),
                    )
                ),
            )
        )
    return tuple(conditions)


def shadow_of_chaos_area_match(text: str) -> re.Match[str] | None:
    return _SHADOW_OF_CHAOS_AREA_RE.search(text)


def parse_shadow_of_chaos_area_target(
    *,
    text: str,
    source_span: TextSpan,
) -> RuleTargetSpec | None:
    match = _SHADOW_OF_CHAOS_AREA_RE.search(text)
    if match is None:
        return None
    return RuleTargetSpec(
        kind=RuleTargetKind.AURA_UNITS,
        source_span=_span_from_match(source_span, match),
        parameters=parameters_from_pairs(
            (("eligible_target", "aura_units"), ("allegiance", "friendly"))
        ),
    )


def parse_shadow_of_chaos_area_effects(
    *,
    text: str,
    source_span: TextSpan,
) -> tuple[RuleEffectSpec, ...]:
    return tuple(
        RuleEffectSpec(
            kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
            source_span=_span_from_match(source_span, match),
            parameters=parameters_from_pairs(
                (
                    ("status", "within_shadow_of_chaos"),
                    ("rules_context", "shadow_of_chaos"),
                    ("owner", "your_army"),
                )
            ),
        )
        for match in _SHADOW_OF_CHAOS_AREA_RE.finditer(text)
    )


def parse_selected_unit_battle_shock_test_effects(
    *,
    text: str,
    source_span: TextSpan,
    existing_effects: tuple[RuleEffectSpec, ...],
) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _SELECTED_UNIT_BATTLE_SHOCK_TEST_RE.finditer(text):
        span = _span_from_match(source_span, match)
        if _span_matches_existing_effect(span=span, effects=existing_effects):
            continue
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=span,
                parameters=parameters_from_pairs(
                    (
                        ("status", "force_battle_shock_test"),
                        ("required", True),
                        ("rules_context", "battle_shock"),
                        ("reason", "forced_by_ability"),
                        ("target_scope", "selected_unit"),
                    )
                ),
            )
        )
    return tuple(effects)


def _selected_target_attack_trigger_parameter_pairs(
    match: re.Match[str],
) -> tuple[tuple[str, RuleParameterValue], ...]:
    pairs: list[tuple[str, RuleParameterValue]] = [
        ("actor", "selected_unit"),
        ("target_reference", "selected_unit"),
        ("timing_window", "attack_sequence.attack"),
    ]
    attack_kind = match.group("attack_kind")
    if attack_kind is not None:
        pairs.append(("attack_kind", _lower_group(match, "attack_kind")))
    return tuple(pairs)


def _span_from_match(source_span: TextSpan, match: re.Match[str]) -> TextSpan:
    return TextSpan(
        text=match.group(0),
        start=source_span.start + match.start(),
        end=source_span.start + match.end(),
    )


def _span_matches_existing_effect(
    *,
    span: TextSpan,
    effects: tuple[RuleEffectSpec, ...],
) -> bool:
    return any(
        span.start >= effect.source_span.start and span.end <= effect.source_span.end
        for effect in effects
    )


def _lower_group(match: re.Match[str], group_name: str) -> str:
    return match.group(group_name).lower().replace("-", "_")


def _subject_token(value: str) -> str:
    return value.lower().replace(" ", "_").replace("-", "_")
