"""Predeclared no-frequency shared Damage sources selected by the registered owner."""

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


def declared_shared_damage_permission(
    *, chooser: bool, qualified_roll: bool
) -> DatasheetAbilityDescriptor:
    """Analytical IR at muster, never a post-start effect or registry injection."""
    selected_source = "analytical:s25-declared-shared-damage-" + (
        "qualified" if qualified_roll else "canonical"
    )
    source = selected_source + ":chooser" if chooser else selected_source
    text = (
        "S25 synthetic source: at battle-round start, choose the declared Damage effect."
        if chooser
        else "S25 synthetic unit effect: add 1 to Damage rolls "
        "and permit ignoring Damage modifiers."
    )
    span = TextSpan(text, 0, len(text))
    effects = (
        (
            RuleEffectSpec(
                RuleEffectKind.SET_CONTEXTUAL_STATUS,
                span,
                parameters_from_pairs(
                    (
                        ("status", "catalog_shadow_form_selection"),
                        ("rules_context", "shadow_form"),
                        ("selectable_source_ids", (selected_source,)),
                    )
                ),
            ),
        )
        if chooser
        else (
            RuleEffectSpec(
                RuleEffectKind.GRANT_ABILITY,
                span,
                parameters_from_pairs(
                    (
                        ("ability", "modifier_ignore_permission"),
                        ("selection", "any_or_all"),
                        ("modifier_kinds", ("damage_roll",)),
                    )
                ),
            ),
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
        )
    )
    clause = RuleClause(
        source + ":clause",
        span,
        trigger=RuleTrigger(
            RuleTriggerKind.TIMING_WINDOW,
            span,
            parameters_from_pairs((("edge", "start"), ("phase", "battle_round"))),
        )
        if chooser
        else None,
        target=RuleTargetSpec(RuleTargetKind.THIS_UNIT, span),
        effects=effects,
        duration=None
        if chooser
        else RuleDuration(
            RuleDurationKind.UNTIL_TIMING_ENDPOINT,
            span,
            parameters_from_pairs((("endpoint", "battle"),)),
        ),
    )
    rule = RuleIR(source + ":rule", source, text, "analytical-declared-ir", (clause,))
    return DatasheetAbilityDescriptor(
        ability_id="s25-shared-damage-" + ("chooser" if chooser else "permission"),
        name="S25 synthetic shared Damage " + ("chooser" if chooser else "permission"),
        source_id=source,
        support=CatalogAbilitySupport.GENERIC_RULE_IR,
        source_kind=CatalogAbilitySourceKind.DATASHEET,
        effect_description=text,
        rule_ir_payload=cast(CatalogJsonObject, rule.to_payload()),
    )
