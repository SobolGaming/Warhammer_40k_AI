"""Explicit synthetic optional IR for relevance and duplicate-source controls."""

from typing import cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
from warhammer40k_core.core.weapon_profiles import WeaponKeyword
from warhammer40k_core.rules.parsed_tokens import TextSpan
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


def declared_activated_relevance_ability(kind: str) -> DatasheetAbilityDescriptor:
    kind = kind.removesuffix("-one")
    kinds = {
        "unused-wound": ("wound_roll",),
        "unused-defender-save-with-inv-provider": ("save_characteristic",),
        "unused-defender-zero-ap-save-roll": ("save_roll",),
        "unused-defender-characteristics": (
            "toughness_characteristic",
            "save_characteristic",
            "invulnerable_save_characteristic",
        ),
        "unused-damage-roll": ("damage_roll",),
        "unused-characteristics": (
            "strength_characteristic",
            "armor_penetration_characteristic",
            "damage_characteristic",
        ),
    }
    duplicate = kind == "duplicate-rapid-fire"
    assert duplicate or kind in kinds
    text = "S25 synthetic analytical source: once per battle at phase start, this model " + (
        "gains Rapid Fire 1 on ranged weapons."
        if duplicate
        else "may ignore " + ", ".join(kinds[kind]) + " modifiers."
    )
    source = "analytical:s25-declared-relevance-" + kind
    span = TextSpan(text, 0, len(text))
    parameters = (
        (
            ("weapon_ability", WeaponKeyword.RAPID_FIRE.value),
            ("weapon_ability_value", 1),
            ("weapon_scope", "ranged"),
        )
        if duplicate
        else (
            ("ability", "modifier_ignore_permission"),
            ("selection", "any_or_all"),
            ("modifier_kinds", kinds[kind]),
        )
    )
    effect = RuleEffectSpec(
        RuleEffectKind.GRANT_WEAPON_ABILITY if duplicate else RuleEffectKind.GRANT_ABILITY,
        span,
        parameters_from_pairs(parameters),
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
        effects=(effect,),
        duration=RuleDuration(
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            span,
            parameters_from_pairs((("endpoint", "phase"),)),
        ),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-declared-relevance-" + kind,
        name="S25 synthetic relevance " + kind,
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )


def declared_passive_invulnerable_provider_ability() -> DatasheetAbilityDescriptor:
    """Normal catalog descriptor, declared before startup; no registry injection."""
    text = "S25 synthetic passive source: this model has a 4+ invulnerable save."
    source = "analytical:s25-passive-invulnerable-provider"
    span = TextSpan(text, 0, len(text))
    clause = RuleClause(
        source + ":clause",
        span,
        target=RuleTargetSpec(RuleTargetKind.THIS_MODEL, span),
        effects=(
            RuleEffectSpec(
                RuleEffectKind.SET_CHARACTERISTIC,
                span,
                parameters_from_pairs((("characteristic", "invulnerable_save"), ("value", 4))),
            ),
        ),
        template_id="phase17c:passive-model-characteristic-set",
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-passive-invulnerable-provider",
        name="S25 synthetic InvSave provider",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
