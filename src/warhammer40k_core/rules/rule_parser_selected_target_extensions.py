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
_BATTLE_SHOCK_TEST_REROLL_RE = re.compile(
    r"\beach\s+time\s+you\s+take\s+a\s+Battle-shock\s+test\s+for\s+"
    r"(?P<target>that\s+unit|this\s+unit|selected\s+unit|target\s+unit),\s+"
    r"you\s+can\s+re-roll\s+that\s+test\b",
    re.IGNORECASE,
)
_FORTIFICATION_COVER_RE = re.compile(
    r"\beach\s+time\s+a\s+ranged\s+attack\s+is\s+allocated\s+to\s+a\s+model,\s+"
    r"if\s+that\s+model\s+is\s+not\s+fully\s+visible\s+to\s+every\s+model\s+in\s+"
    r"the\s+attacking\s+unit\s+because\s+of\s+this\s+FORTIFICATION,\s+that\s+model\s+"
    r"has\s+the\s+Benefit\s+of\s+Cover\s+against\s+that\s+attack\b",
    re.IGNORECASE,
)
_FORTIFICATION_TARGET_PERMISSION_RE = re.compile(
    r"\bwhile\s+an\s+enemy\s+unit\s+is\s+only\s+within\s+Engagement\s+Range\s+of\s+"
    r"one\s+or\s+more\s+Fortifications\s+from\s+your\s+army:\s*-\s*"
    r"That\s+unit\s+can\s+still\s+be\s+selected\s+as\s+the\s+target\s+of\s+"
    r"ranged\s+attacks,\s+but\s+each\s+time\s+such\s+an\s+attack\s+is\s+made,\s+"
    r"unless\s+it\s+is\s+made\s+with\s+a\s+Pistol,\s+subtract\s+1\s+from\s+the\s+"
    r"Hit\s+roll\b",
    re.IGNORECASE,
)
_FORTIFICATION_DESPERATE_ESCAPE_RE = re.compile(
    r"\bModels\s+in\s+that\s+unit\s+do\s+not\s+need\s+to\s+take\s+"
    r"Desperate\s+Escape\s+tests\s+due\s+to\s+Falling\s+Back\s+while\s+"
    r"Battle-shocked,\s+except\s+for\s+those\s+that\s+will\s+move\s+over\s+"
    r"enemy\s+models\s+when\s+doing\s+so\b",
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


def parse_battle_shock_test_reroll_effects(
    *,
    text: str,
    source_span: TextSpan,
) -> tuple[RuleEffectSpec, ...]:
    return tuple(
        RuleEffectSpec(
            kind=RuleEffectKind.REROLL_PERMISSION,
            source_span=_span_from_match(source_span, match),
            parameters=parameters_from_pairs(
                (
                    ("roll_type", "battle_shock"),
                    ("target_reference", _subject_token(match.group("target"))),
                    ("timing_window", "battle_shock_test"),
                )
            ),
        )
        for match in _BATTLE_SHOCK_TEST_REROLL_RE.finditer(text)
    )


def parse_fortification_contextual_status_effects(
    *,
    text: str,
    source_span: TextSpan,
) -> tuple[RuleEffectSpec, ...]:
    effects: list[RuleEffectSpec] = []
    for match in _FORTIFICATION_COVER_RE.finditer(text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span_from_match(source_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("status", "benefit_of_cover"),
                        ("rules_context", "ranged_attack_allocation"),
                        ("source_reference", "this_fortification"),
                        (
                            "visibility_predicate",
                            "not_fully_visible_to_every_attacking_model_because_of_source",
                        ),
                    )
                ),
            )
        )
    for match in _FORTIFICATION_TARGET_PERMISSION_RE.finditer(text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span_from_match(source_span, match),
                parameters=parameters_from_pairs(
                    (
                        ("status", "fortification_engagement_ranged_target_permission"),
                        ("rules_context", "shooting_target_selection"),
                        ("source_reference", "friendly_fortifications"),
                    )
                ),
            )
        )
    for match in _FORTIFICATION_DESPERATE_ESCAPE_RE.finditer(text):
        effects.append(
            RuleEffectSpec(
                kind=RuleEffectKind.SET_CONTEXTUAL_STATUS,
                source_span=_span_from_match(source_span, match),
                parameters=parameters_from_pairs(
                    (
                        (
                            "status",
                            "fortification_engagement_battle_shocked_desperate_escape_exception",
                        ),
                        ("rules_context", "fall_back_desperate_escape"),
                        ("source_reference", "enemy_fortifications"),
                        ("overflight_exception", True),
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
