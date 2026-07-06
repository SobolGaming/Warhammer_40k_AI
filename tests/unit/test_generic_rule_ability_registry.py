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
