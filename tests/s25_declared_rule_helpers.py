"""Explicit synthetic catalog source text compiled before native game startup."""

from typing import cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.parsed_tokens import TextSpan
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleCondition,
    RuleConditionKind,
    RuleDuration,
    RuleDurationKind,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleTargetKind,
    RuleTargetSpec,
    RuleTrigger,
    RuleTriggerKind,
    parameters_from_pairs,
)
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    datasheet_keyword_lexicon_2026_06_14,
)


def declared_uniform_hit_ability() -> DatasheetAbilityDescriptor:
    text = (
        "Each time this model makes an attack that targets an enemy unit that is not "
        "below Half-strength, add 1 to the Hit roll."
    )
    source_id = "analytical:s25-declared-uniform-own-hit"
    compiled = compile_rule_source_text(
        RuleSourceText.from_raw(
            objective_scope=ObjectiveRuleScope.CORE_RULES,
            source_id=source_id,
            raw_text=text,
        ),
        source_keyword_sequence_parts=datasheet_keyword_lexicon_2026_06_14.canonical_datasheet_keyword_sequence_parts(),
    )
    assert compiled.rule_ir.is_supported
    return DatasheetAbilityDescriptor(
        ability_id="s25-declared-uniform-own-hit",
        name="S25 declared own-model Hit control",
        source_id=source_id,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, compiled.rule_ir.to_payload()),
    )


def declared_own_ignore_ability() -> DatasheetAbilityDescriptor:
    """Synthetic supported catalog IR declared at muster, never an injected effect."""
    text = "S25 analytical source: this model may ignore any or all Hit-roll modifiers."
    source = "analytical:s25-declared-own-ignore"
    span = TextSpan(text, 0, len(text))
    clause = RuleClause(
        source + ":clause",
        span,
        target=RuleTargetSpec(RuleTargetKind.THIS_MODEL, span),
        effects=(
            RuleEffectSpec(
                RuleEffectKind.GRANT_ABILITY,
                span,
                parameters_from_pairs(
                    (
                        ("ability", "modifier_ignore_permission"),
                        ("selection", "any_or_all"),
                        ("modifier_kinds", ("hit_roll",)),
                    )
                ),
            ),
        ),
        duration=RuleDuration(RuleDurationKind.WHILE_CONDITION_TRUE, span),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-declared-own-ignore",
        name="S25 declared own-model ignore control",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )


def declared_activated_reroll_ability() -> DatasheetAbilityDescriptor:
    """Synthetic supported IR with real optional per-model phase-start activation."""
    text = "S25 analytical source: once per battle at phase start, this model may reroll Hits."
    source = "analytical:s25-declared-own-reroll"
    span = TextSpan(text, 0, len(text))
    clause = RuleClause(
        source + ":clause",
        span,
        trigger=RuleTrigger(
            RuleTriggerKind.TIMING_WINDOW,
            span,
            parameters_from_pairs((("edge", "start"), ("phase", "any"))),
        ),
        conditions=(
            RuleCondition(
                RuleConditionKind.FREQUENCY_LIMIT,
                span,
                parameters_from_pairs(
                    (
                        ("activation_kind", "optional_ability_use"),
                        ("max_uses", 1),
                        ("scope", "battle"),
                        ("usage_subject", "this_model"),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(RuleTargetKind.THIS_MODEL, span),
        effects=(
            RuleEffectSpec(
                RuleEffectKind.REROLL_PERMISSION,
                span,
                parameters_from_pairs((("roll_type", "hit"), ("selection", "whole_roll"))),
            ),
        ),
        duration=RuleDuration(
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            span,
            parameters_from_pairs((("endpoint", "phase"),)),
        ),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-declared-own-reroll",
        name="S25 declared per-model activated reroll",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )


def declared_activated_variant_ability(kind: str) -> DatasheetAbilityDescriptor:
    """Additional explicit synthetic IR, through the same real public activation owner."""
    assert kind in {"ignore", "strength", "strength-pair", "skill", "random-skill"}
    text = (
        "S25 analytical source: once per battle at phase start, "
        "this model may ignore Hit modifiers."
        if kind == "ignore"
        else "S25 analytical source: once per battle at phase start, "
        "add 1 to this model's ranged Strength."
        if kind == "strength"
        else "S25 analytical source: once per battle at phase start, "
        "add 1 to this model's ranged Ballistic Skill."
        if kind in {"skill", "random-skill"}
        else "S25 analytical source: once per battle at phase start, "
        "add 1 and then 2 to this model's ranged Strength."
    )
    source = "analytical:s25-declared-activated-" + kind
    span = TextSpan(text, 0, len(text))
    effects = (
        (
            RuleEffectSpec(
                RuleEffectKind.GRANT_ABILITY,
                span,
                parameters_from_pairs(
                    (
                        ("ability", "modifier_ignore_permission"),
                        ("selection", "any_or_all"),
                        ("modifier_kinds", ("hit_roll",)),
                    )
                ),
            ),
        )
        if kind == "ignore"
        else tuple(
            RuleEffectSpec(
                RuleEffectKind.MODIFY_CHARACTERISTIC,
                span,
                parameters_from_pairs(
                    (
                        (
                            "characteristic",
                            "ballistic_skill" if kind in {"skill", "random-skill"} else "strength",
                        ),
                        ("delta", value),
                        ("weapon_scope", "ranged"),
                    )
                ),
            )
            for value in ((1, 2) if kind == "strength-pair" else (1,))
        )
    )
    clause = RuleClause(
        source + ":clause",
        span,
        trigger=RuleTrigger(
            RuleTriggerKind.TIMING_WINDOW,
            span,
            parameters_from_pairs((("edge", "start"), ("phase", "any"))),
        ),
        conditions=(
            RuleCondition(
                RuleConditionKind.FREQUENCY_LIMIT,
                span,
                parameters_from_pairs(
                    (
                        ("activation_kind", "optional_ability_use"),
                        ("max_uses", 1),
                        ("scope", "battle"),
                        ("usage_subject", "this_model"),
                    )
                ),
            ),
        ),
        target=RuleTargetSpec(RuleTargetKind.THIS_MODEL, span),
        effects=effects,
        duration=RuleDuration(
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            span,
            parameters_from_pairs((("endpoint", "phase"),)),
        ),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-declared-activated-" + kind,
        name="S25 declared activated " + kind,
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
