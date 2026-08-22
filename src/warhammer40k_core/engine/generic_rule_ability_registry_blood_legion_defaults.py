from __future__ import annotations

from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.fight_unit_selected_grant_resolution import (
    SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
    apply_selected_to_fight_self_mortal_wound_feel_no_pain_decision,
)
from warhammer40k_core.engine.fight_unit_selected_hooks import (
    FightUnitSelectedContext,
    FightUnitSelectedGrant,
)
from warhammer40k_core.engine.generic_rule_ability_effects import (
    generic_rule_fight_unit_selected_unit_id,
)
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilitySource,
    GenericRuleFightUnitSelectedGrantAbility,
    GenericRuleMortalWoundFeelNoPainAbility,
)
from warhammer40k_core.engine.generic_rule_runtime_consumer_identity import (
    generic_rule_runtime_consumer_id_builder,
)
from warhammer40k_core.engine.generic_rule_selected_to_fight_effects import (
    build_selected_to_fight_self_mortal_wounds_and_rerolls_grant,
    selected_to_fight_enhancement_bearer_is_alive,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)


def _furys_cage_grant(
    context: FightUnitSelectedContext,
    source: GenericRuleAbilitySource,
    matching_effects: tuple[PersistingEffect, ...],
) -> FightUnitSelectedGrant:
    return build_selected_to_fight_self_mortal_wounds_and_rerolls_grant(
        context,
        source,
        matching_effects,
        ability_id=blood_legion_ir.FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY,
        hook_id=blood_legion_ir.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
        label="Fury's Cage",
    )


def blood_legion_fight_unit_selected_grant_abilities() -> tuple[
    GenericRuleFightUnitSelectedGrantAbility,
    ...,
]:
    return (
        GenericRuleFightUnitSelectedGrantAbility(
            ability_id=blood_legion_ir.FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY,
            coverage_descriptor_id=blood_legion_ir.FURYS_CAGE_DESCRIPTOR_ID,
            source_rule_id=blood_legion_ir.FURYS_CAGE_SOURCE_RULE_ID,
            hook_id_builder=generic_rule_runtime_consumer_id_builder(
                coverage_descriptor_id=blood_legion_ir.FURYS_CAGE_DESCRIPTOR_ID,
                consumer_id=blood_legion_ir.FURYS_CAGE_SELECTED_TO_FIGHT_CONSUMER_ID,
            ),
            target_unit_id_builder=generic_rule_fight_unit_selected_unit_id,
            context_predicate=selected_to_fight_enhancement_bearer_is_alive,
            grant_builder=_furys_cage_grant,
        ),
    )


def blood_legion_mortal_wound_feel_no_pain_abilities() -> tuple[
    GenericRuleMortalWoundFeelNoPainAbility,
    ...,
]:
    return (
        GenericRuleMortalWoundFeelNoPainAbility(
            ability_ids_value=(blood_legion_ir.FURYS_CAGE_SELECTED_TO_FIGHT_ABILITY,),
            coverage_descriptor_id=blood_legion_ir.FURYS_CAGE_DESCRIPTOR_ID,
            source_rule_id=blood_legion_ir.FURYS_CAGE_SOURCE_RULE_ID,
            source_kind=SELECTED_TO_FIGHT_SELF_MORTAL_WOUNDS_SOURCE_KIND,
            hook_id_builder=generic_rule_runtime_consumer_id_builder(
                coverage_descriptor_id=blood_legion_ir.FURYS_CAGE_DESCRIPTOR_ID,
                consumer_id=blood_legion_ir.FURYS_CAGE_MORTAL_WOUND_FNP_CONSUMER_ID,
            ),
            handler=apply_selected_to_fight_self_mortal_wound_feel_no_pain_decision,
        ),
    )


__all__ = (
    "blood_legion_fight_unit_selected_grant_abilities",
    "blood_legion_mortal_wound_feel_no_pain_abilities",
)
