"""Synthetic characteristic sources declared before the normal optional activation."""

from typing import cast

from warhammer40k_core.core.datasheet import (
    CatalogAbilitySourceKind,
    CatalogAbilitySupport,
    CatalogJsonObject,
    DatasheetAbilityDescriptor,
)
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


def declared_attack_relevance_characteristic(kind: str) -> DatasheetAbilityDescriptor:
    """Analytical controls, not a claim of an official datasheet rule or injected state."""
    assert kind in {"unused-movement", "meaningful-strength"}
    movement = kind == "unused-movement"
    characteristic = "movement" if movement else "strength"
    text = (
        "S25 synthetic analytical source: once per battle at phase start, "
        "add 1 to this model's " + ("Movement." if movement else "ranged Strength.")
    )
    source = "analytical:s25-declared-attack-relevance-" + kind
    span = TextSpan(text, 0, len(text))
    parameters = (
        parameters_from_pairs((("characteristic", characteristic), ("delta", 1)))
        if movement
        else parameters_from_pairs(
            (("characteristic", characteristic), ("delta", 1), ("weapon_scope", "ranged"))
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
        effects=(RuleEffectSpec(RuleEffectKind.MODIFY_CHARACTERISTIC, span, parameters),),
        duration=RuleDuration(
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            span,
            parameters_from_pairs((("endpoint", "phase"),)),
        ),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-declared-attack-relevance-" + kind,
        name="S25 synthetic attack relevance " + kind,
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
