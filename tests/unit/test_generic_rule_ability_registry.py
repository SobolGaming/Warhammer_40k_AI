from __future__ import annotations

from dataclasses import replace

import pytest

from warhammer40k_core.engine.faction_content.warhammer_40000_11th.chaos_space_marines import (
    army_rule as dark_pacts,
)
from warhammer40k_core.engine.generic_rule_ability_registry import (
    GenericRuleAbilityHookFamily,
    GenericRuleAbilityRegistry,
    GenericRuleAbilitySource,
    rule_ir_grants_any_ability,
)
from warhammer40k_core.engine.generic_rule_ability_registry_defaults import (
    DEFAULT_GENERIC_RULE_ABILITY_REGISTRY,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_blood_legion_ir_support_2026_27 as blood_legion_ir,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_shadow_legion_ir_support_2026_27 as shadow_legion_ir,
)


def test_default_generic_rule_ability_registry_maps_shadow_legion_grants() -> None:
    source = _shadow_legion_source()
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    advance = registry.advance_eligibility_abilities[0]
    assert advance.hook_family is GenericRuleAbilityHookFamily.ADVANCE_ELIGIBILITY
    assert advance.ability_ids() == (shadow_legion_ir.CAN_ADVANCE_AND_SHOOT_AND_CHARGE_ABILITY,)
    assert (
        advance.coverage_descriptor_id
        == shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert advance.source_rule_id == dark_pacts.SHADOW_LEGION_SOURCE_RULE_ID
    assert advance.hook_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:advance-eligibility"
    )

    restriction = registry.shooting_target_restriction_abilities[0]
    assert restriction.hook_family is GenericRuleAbilityHookFamily.SHOOTING_TARGET_RESTRICTION
    assert restriction.ability_ids() == (shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,)
    assert restriction.hook_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:snap-target-restriction"
    )

    shooting_grants = registry.shooting_unit_selected_grant_abilities
    assert {descriptor.hook_family for descriptor in shooting_grants} == {
        GenericRuleAbilityHookFamily.SHOOTING_UNIT_SELECTED_GRANT
    }
    assert {descriptor.ability_id for descriptor in shooting_grants} == {
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
    }
    assert {descriptor.hook_id(source) for descriptor in shooting_grants} == {
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:shooting:lethal_hits",
        (
            "phase17f:phase17e:chaos-daemons:shadow-legion:rule:"
            "shadow-legion:shooting:sustained_hits_1"
        ),
    }

    fight_grants = registry.fight_unit_selected_grant_abilities
    assert {descriptor.hook_family for descriptor in fight_grants} == {
        GenericRuleAbilityHookFamily.FIGHT_UNIT_SELECTED_GRANT
    }
    assert {descriptor.hook_id(source) for descriptor in fight_grants} == {
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:fight:lethal_hits",
        ("phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:fight:sustained_hits_1"),
    }

    attack_completion = registry.attack_sequence_completed_abilities[0]
    assert attack_completion.hook_family is GenericRuleAbilityHookFamily.ATTACK_SEQUENCE_COMPLETED
    assert set(attack_completion.ability_ids()) == {
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_LETHAL_HITS_CHOICE_ABILITY,
        shadow_legion_ir.SHADOW_LEGION_DARK_PACT_SUSTAINED_HITS_1_CHOICE_ABILITY,
    }
    assert attack_completion.hook_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:dark-pact-completion"
    )

    fnp = registry.mortal_wound_feel_no_pain_abilities[0]
    assert fnp.hook_family is GenericRuleAbilityHookFamily.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION
    assert fnp.source_kind == dark_pacts.SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND

    weapon_profile = registry.weapon_profile_modifier_abilities[0]
    assert weapon_profile.hook_family is GenericRuleAbilityHookFamily.WEAPON_PROFILE_MODIFIER
    assert weapon_profile.modifier_id(source) == (
        "phase17f:phase17e:chaos-daemons:shadow-legion:rule:shadow-legion:dark-pact-weapon-profile"
    )


def test_default_generic_rule_ability_registry_maps_blood_legion_grants() -> None:
    source = _blood_legion_source()
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    surge = registry.movement_end_surge_abilities[0]
    assert surge.hook_family is GenericRuleAbilityHookFamily.MOVEMENT_END_SURGE
    assert surge.ability_ids() == (blood_legion_ir.MURDERCALL_SURGE_ABILITY,)
    assert (
        surge.coverage_descriptor_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert surge.source_rule_id == blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID
    assert surge.hook_id(source) == blood_legion_ir.MURDERCALL_HOOK_ID

    sticky = registry.phase_end_objective_control_abilities[0]
    assert sticky.hook_family is GenericRuleAbilityHookFamily.PHASE_END_OBJECTIVE_CONTROL
    assert sticky.ability_ids() == (blood_legion_ir.BLOOD_TAINTED_STICKY_OBJECTIVE_ABILITY,)
    assert (
        sticky.coverage_descriptor_id == blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert sticky.source_rule_id == blood_legion_ir.BLOOD_LEGION_SOURCE_RULE_ID
    assert sticky.hook_id(source) == blood_legion_ir.BLOOD_TAINTED_HOOK_ID


def test_default_generic_rule_ability_registry_maps_shadow_legion_enhancement_grants() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    leaping_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID
    )
    leaping = next(
        ability
        for ability in registry.enhancement_effect_abilities
        if ability.ability_ids() == (shadow_legion_ir.LEAPING_SHADOWS_SCOUTS_ABILITY,)
    )
    assert leaping.hook_family is GenericRuleAbilityHookFamily.ENHANCEMENT_EFFECT
    assert leaping.ability_ids() == (shadow_legion_ir.LEAPING_SHADOWS_SCOUTS_ABILITY,)
    assert (
        leaping.coverage_descriptor_id == shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert leaping.source_rule_id == shadow_legion_ir.LEAPING_SHADOWS_SOURCE_RULE_ID
    assert leaping.enhancement_id == shadow_legion_ir.LEAPING_SHADOWS_ENHANCEMENT_ID
    assert leaping.effect_id(leaping_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:leaping_shadows:scouts_9"
    )

    mantle_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID
    )
    mantle = registry.objective_control_modifier_abilities[0]
    assert mantle.hook_family is GenericRuleAbilityHookFamily.OBJECTIVE_CONTROL_MODIFIER
    assert mantle.ability_ids() == (shadow_legion_ir.MANTLE_OF_GLOOM_OBJECTIVE_CONTROL_ABILITY,)
    assert (
        mantle.coverage_descriptor_id == shadow_legion_ir.MANTLE_OF_GLOOM_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert mantle.source_rule_id == shadow_legion_ir.MANTLE_OF_GLOOM_SOURCE_RULE_ID
    assert mantle.modifier_id(mantle_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:mantle_of_gloom:objective-control"
    )

    fade_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID
    )
    unit_destroyed = registry.unit_destroyed_abilities[0]
    assert unit_destroyed.hook_family is GenericRuleAbilityHookFamily.UNIT_DESTROYED
    assert unit_destroyed.ability_ids() == (shadow_legion_ir.FADE_TO_DARKNESS_RESERVES_ABILITY,)
    assert (
        unit_destroyed.coverage_descriptor_id
        == shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert unit_destroyed.source_rule_id == shadow_legion_ir.FADE_TO_DARKNESS_SOURCE_RULE_ID
    assert unit_destroyed.hook_id(fade_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:fade_to_darkness:unit-destroyed"
    )

    turn_end = registry.turn_end_abilities[0]
    assert turn_end.hook_family is GenericRuleAbilityHookFamily.TURN_END
    assert turn_end.ability_ids() == (shadow_legion_ir.FADE_TO_DARKNESS_RESERVES_ABILITY,)
    assert (
        turn_end.coverage_descriptor_id
        == shadow_legion_ir.FADE_TO_DARKNESS_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert turn_end.source_rule_id == shadow_legion_ir.FADE_TO_DARKNESS_SOURCE_RULE_ID
    assert turn_end.hook_id(fade_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:fade_to_darkness:turn-end-reserves"
    )

    malice_source = _shadow_legion_enhancement_source(
        shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
    )
    fight_start = registry.fight_phase_start_abilities[0]
    assert fight_start.hook_family is GenericRuleAbilityHookFamily.FIGHT_PHASE_START
    assert fight_start.ability_ids() == (
        shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
    )
    assert (
        fight_start.coverage_descriptor_id
        == shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert fight_start.source_rule_id == shadow_legion_ir.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    assert fight_start.hook_id(malice_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:malice_made_manifest"
    )

    malice_fnp = next(
        descriptor
        for descriptor in registry.mortal_wound_feel_no_pain_abilities
        if descriptor.coverage_descriptor_id
        == shadow_legion_ir.MALICE_MADE_MANIFEST_ENHANCEMENT_DESCRIPTOR_ID
    )
    assert (
        malice_fnp.hook_family
        is GenericRuleAbilityHookFamily.MORTAL_WOUND_FEEL_NO_PAIN_CONTINUATION
    )
    assert malice_fnp.ability_ids() == (
        shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_ABILITY,
    )
    assert malice_fnp.source_rule_id == shadow_legion_ir.MALICE_MADE_MANIFEST_SOURCE_RULE_ID
    assert malice_fnp.source_kind == shadow_legion_ir.MALICE_MADE_MANIFEST_MORTAL_WOUNDS_SOURCE_KIND
    assert malice_fnp.hook_id(malice_source) == (
        "warhammer_40000_11th:chaos_daemons:detachment:shadow_legion:"
        "enhancement:malice_made_manifest:mortal-wound-fnp"
    )


def test_generic_rule_ability_registry_rejects_duplicate_descriptors() -> None:
    descriptor = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY.advance_eligibility_abilities[0]

    with pytest.raises(GameLifecycleError, match="descriptors must be unique"):
        GenericRuleAbilityRegistry(advance_eligibility_abilities=(descriptor, descriptor))


def test_generic_rule_ability_source_validates_rule_ir_hash() -> None:
    source = _shadow_legion_source()
    stale_record = replace(source.record, rule_ir_hash="0" * 64)

    with pytest.raises(GameLifecycleError, match="stale RuleIR hash"):
        GenericRuleAbilitySource(record=stale_record, rule_ir=source.rule_ir)


def test_rule_ir_grants_any_ability_uses_grant_ability_parameters() -> None:
    source = _shadow_legion_source()

    assert rule_ir_grants_any_ability(
        source.rule_ir,
        abilities=(shadow_legion_ir.SNAP_SHOOTING_TARGET_FORBIDDEN_ABILITY,),
    )
    assert not rule_ir_grants_any_ability(source.rule_ir, abilities=("missing_ability",))


def _shadow_legion_source() -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id
        == shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _blood_legion_source() -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id
        == blood_legion_ir.BLOOD_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)


def _shadow_legion_enhancement_source(coverage_descriptor_id: str) -> GenericRuleAbilitySource:
    record = next(
        record
        for record in faction_execution_2026_27.execution_records()
        if record.coverage_descriptor_id == coverage_descriptor_id
    )
    rule_ir = faction_generic_ir_support_2026_27.generic_rule_ir_by_coverage_descriptor_id(
        record.coverage_descriptor_id
    )
    return GenericRuleAbilitySource(record=record, rule_ir=rule_ir)
