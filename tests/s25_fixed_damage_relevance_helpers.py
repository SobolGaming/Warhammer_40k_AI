"""Explicit synthetic catalog source text compiled before native game startup."""

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


def declared_fixed_damage_roll_ability(*, qualified_roll: bool) -> DatasheetAbilityDescriptor:
    """Synthetic supported IR with real optional per-model phase-start activation."""
    text = (
        "S25 analytical source: once per battle at phase start, add 1 to this model's Damage rolls."
    )
    source = "analytical:s25-declared-fixed-damage-roll"
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
                RuleEffectKind.MODIFY_DICE_ROLL,
                span,
                parameters_from_pairs(
                    (
                        ("roll_type", "attack_sequence.damage" if qualified_roll else "damage"),
                        ("delta", 1),
                    )
                ),
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
        ability_id="s25-declared-fixed-damage-roll",
        name="S25 declared fixed-Damage unused-roll control",
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
