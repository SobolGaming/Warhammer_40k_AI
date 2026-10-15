from __future__ import annotations

from typing import cast

from tests.shared.category_migration.generic_rule_ability_registry import (
    _ENEMY_UNIT_ID,
    _RANGERS_UNIT_ID,
    _SHROUD_RUNNERS_UNIT_ID,
    _WARPTIDE_UNIT_ID,
    CORE_FIRE_OVERWATCH_HANDLER_ID,
    DEFAULT_GENERIC_RULE_ABILITY_REGISTRY,
    AdvanceEligibilityContext,
    AdvanceMoveContext,
    AdvanceMoveGrant,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BaseSizeDefinition,
    BattleFormationRequestContext,
    BattleFormationResultContext,
    BattlePhase,
    Callable,
    Characteristic,
    CharacteristicValue,
    DecisionController,
    DetachmentSelection,
    EffectExpiration,
    EnhancementAssignment,
    EnhancementEffectContext,
    FallBackEligibilityContext,
    FightActivationAbilityContext,
    FightPhaseStartRequestContext,
    FightPhaseStartResultContext,
    FightUnitSelectedContext,
    GameConfig,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    GenericRuleAbilityHookFamily,
    GenericRuleAbilityRegistry,
    GenericRuleAbilitySource,
    JsonValue,
    ModelGeometry,
    ModelInstance,
    ModelKeywordAssignment,
    ModelProfileSelection,
    ModifierOperation,
    ModifierTerm,
    MovementEndSurgeContext,
    ObjectiveControlModifierContext,
    PersistingEffect,
    PhaseEndObjectiveControlContext,
    ReserveArrivalDistanceContext,
    RuleEffectKind,
    RuleExecutionResult,
    RuleExecutionStatus,
    RuleIR,
    RulesetDescriptor,
    RuleTargetKind,
    RuntimeContentActivation,
    SaveOptionModifierContext,
    SetupStep,
    ShootingTargetRestrictionContext,
    ShootingUnitSelectedContext,
    StartingStrengthRecord,
    StratagemCategory,
    StratagemCostChoiceRequestContext,
    StratagemCostChoiceResultContext,
    StratagemCostModifierContext,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemTargetBinding,
    StratagemTargetKind,
    StratagemTargetSpec,
    StratagemTimingDescriptor,
    TimingTriggerKind,
    TurnEndRequestContext,
    TurnEndResultContext,
    UnitDestroyedContext,
    UnitInstance,
    UnitMusterSelection,
    WeaponKeyword,
    _aeldari_corsair_coterie_source,
    _aeldari_path_of_the_outcast_source,
    _army,
    _blood_legion_source,
    _court_of_the_phoenician_source,
    _grant_ability_effect,
    _keyword_any_state,
    _minimal_warptide_game_config,
    _model,
    _muster_request,
    _owner_player_id_for_unit_id,
    _raise_selected_to_fight_payload_error,
    _selected_to_fight_effect_payload,
    _selected_to_fight_grant_payload,
    _selected_to_fight_reroll_payload,
    _shadow_legion_enhancement_source,
    _shadow_legion_source,
    _unit,
    _warptide_activation,
    _warptide_cost_modifier_context,
    _warptide_grant_ability_effect,
    _warptide_setup_state,
    _warptide_source,
    _warptide_state,
    advance_move_lifecycle_hooks,
    blood_legion_ir,
    copy,
    corsair_enhancements,
    corsair_ir,
    court_ir,
    court_rule,
    dark_pacts,
    faction_execution_2026_27,
    faction_generic_ir_support_2026_27,
    generic_detachment_effects,
    generic_rule_ability_effects_for_unit,
    generic_rule_lifecycle_hook_handlers,
    generic_rule_lifecycle_hooks,
    generic_rule_persisting_effect,
    generic_rule_selected_to_fight_effects,
    path_outcast_ir,
    pytest,
    replace,
    rule_ir_grants_any_ability,
    shadow_legion_ir,
    validate_json_value,
    warptide_ir,
    with_unit_keywords,
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

    fight_grants = tuple(
        descriptor
        for descriptor in registry.fight_unit_selected_grant_abilities
        if descriptor.coverage_descriptor_id
        == shadow_legion_ir.SHADOW_LEGION_DETACHMENT_RULE_DESCRIPTOR_ID
    )
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

    fnp = next(
        descriptor
        for descriptor in registry.mortal_wound_feel_no_pain_abilities
        if descriptor.source_kind == dark_pacts.SHADOW_LEGION_DARK_PACT_MORTAL_WOUNDS_SOURCE_KIND
    )
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


def test_default_generic_rule_ability_registry_maps_warptide_grants() -> None:
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    advance_move = next(
        descriptor
        for descriptor in registry.advance_move_abilities
        if descriptor.ability_ids() == (warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,)
    )
    assert advance_move.hook_family is GenericRuleAbilityHookFamily.ADVANCE_MOVE
    assert advance_move.coverage_descriptor_id == warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    assert advance_move.source_rule_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert advance_move.hook_id(source) == warptide_ir.SHUDDERBLINK_ADVANCE_MOVE_HOOK_ID

    advance_eligibility = next(
        descriptor
        for descriptor in registry.advance_eligibility_abilities
        if descriptor.ability_ids() == (warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,)
    )
    assert advance_eligibility.hook_family is GenericRuleAbilityHookFamily.ADVANCE_ELIGIBILITY
    assert (
        advance_eligibility.coverage_descriptor_id
        == warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert advance_eligibility.source_rule_id == warptide_ir.WARPTIDE_SOURCE_RULE_ID
    assert (
        advance_eligibility.hook_id(source) == warptide_ir.SHUDDERBLINK_ADVANCE_ELIGIBILITY_HOOK_ID
    )

    soul_hungry_source = _warptide_source(warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID)
    soul_hungry = next(
        descriptor
        for descriptor in registry.stratagem_cost_modifier_abilities
        if descriptor.ability_ids() == (warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_ABILITY,)
    )
    assert soul_hungry.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_MODIFIER
    assert soul_hungry.coverage_descriptor_id == warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_DESCRIPTOR_ID
    assert soul_hungry.source_rule_id == warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_SOURCE_RULE_ID
    assert soul_hungry.modifier_id(soul_hungry_source) == (
        warptide_ir.SOUL_HUNGRY_SLAUGHTERERS_COST_MODIFIER_ID
    )


def test_warptide_battle_formation_handler_records_generic_rule_effects() -> None:
    state = _warptide_setup_state()
    source = _warptide_source(warptide_ir.WARPTIDE_DETACHMENT_RULE_DESCRIPTOR_ID)
    bindings = generic_detachment_effects.generic_detachment_rule_battle_formation_hook_bindings(
        activation=_warptide_activation(),
        execution_records=(source.record,),
    )
    decisions = DecisionController()
    request_handler = bindings[0].request_handler

    assert request_handler is not None
    assert (
        request_handler(
            BattleFormationRequestContext(
                state=state,
                decisions=decisions,
                config=_minimal_warptide_game_config(),
            )
        )
        is None
    )

    effects = state.persisting_effects_for_unit(_WARPTIDE_UNIT_ID)
    effect_abilities: set[str] = set()
    for effect in effects:
        payload = effect.effect_payload
        assert isinstance(payload, dict)
        rule_effect = payload["effect"]
        assert isinstance(rule_effect, dict)
        parameters = rule_effect["parameters"]
        assert isinstance(parameters, list)
        for parameter in parameters:
            assert isinstance(parameter, dict)
            if parameter.get("key") == "ability":
                value = parameter.get("value")
                assert isinstance(value, str)
                effect_abilities.add(value)
    assert effect_abilities == {
        warptide_ir.SHUDDERBLINK_ASSAULT_AFTER_ADVANCE_ABILITY,
        warptide_ir.SHUDDERBLINK_CHARGE_AFTER_ADVANCE_ABILITY,
    }
    assert decisions.event_log.records[-1].event_type == "generic_detachment_rule_effects_applied"

    request_handler(
        BattleFormationRequestContext(
            state=state,
            decisions=decisions,
            config=_minimal_warptide_game_config(),
        )
    )
    assert len(state.persisting_effects_for_unit(_WARPTIDE_UNIT_ID)) == 2


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


__all__: list[str] = []
__all__ += ["AdvanceEligibilityContext", "AdvanceMoveContext", "AdvanceMoveGrant", "ArmyCatalog"]
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["CORE_FIRE_OVERWATCH_HANDLER_ID", "BattleFormationResultContext", "BattlePhase"]
__all__ += ["Callable", "Characteristic", "CharacteristicValue", "DetachmentSelection"]
__all__ += ["EffectExpiration", "EnhancementAssignment", "EnhancementEffectContext"]
__all__ += ["FallBackEligibilityContext", "FightActivationAbilityContext"]
__all__ += ["FightPhaseStartRequestContext", "FightPhaseStartResultContext"]
__all__ += ["FightUnitSelectedContext", "GameConfig", "GameLifecycleError", "GameLifecycleStage"]
__all__ += ["GameState", "GenericRuleAbilityRegistry", "GenericRuleAbilitySource", "JsonValue"]
__all__ += ["ModelGeometry", "ModelInstance", "ModelKeywordAssignment", "ModelProfileSelection"]
__all__ += ["ModifierOperation", "ModifierTerm", "MovementEndSurgeContext"]
__all__ += ["ObjectiveControlModifierContext", "PersistingEffect"]
__all__ += ["PhaseEndObjectiveControlContext", "ReserveArrivalDistanceContext", "RuleEffectKind"]
__all__ += ["RuleExecutionResult", "RuleExecutionStatus", "RuleIR", "RuleTargetKind"]
__all__ += ["RulesetDescriptor", "RuntimeContentActivation", "SaveOptionModifierContext"]
__all__ += ["SetupStep", "ShootingTargetRestrictionContext", "ShootingUnitSelectedContext"]
__all__ += ["StartingStrengthRecord", "StratagemCategory", "StratagemCostChoiceRequestContext"]
__all__ += ["StratagemCostChoiceResultContext", "StratagemCostModifierContext"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemTargetBinding"]
__all__ += ["StratagemTargetKind", "StratagemTargetSpec", "StratagemTimingDescriptor"]
__all__ += ["TimingTriggerKind", "TurnEndRequestContext", "TurnEndResultContext"]
__all__ += ["UnitDestroyedContext", "UnitInstance", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["_ENEMY_UNIT_ID", "_RANGERS_UNIT_ID", "_SHROUD_RUNNERS_UNIT_ID"]
__all__ += ["_aeldari_corsair_coterie_source", "_aeldari_path_of_the_outcast_source", "_army"]
__all__ += ["_court_of_the_phoenician_source", "_grant_ability_effect", "_keyword_any_state"]
__all__ += ["_model", "_muster_request", "_owner_player_id_for_unit_id"]
__all__ += ["_raise_selected_to_fight_payload_error", "_selected_to_fight_effect_payload"]
__all__ += ["_selected_to_fight_grant_payload", "_selected_to_fight_reroll_payload", "_unit"]
__all__ += ["_warptide_cost_modifier_context", "_warptide_grant_ability_effect"]
__all__ += ["_warptide_state", "advance_move_lifecycle_hooks", "cast", "copy"]
__all__ += ["corsair_enhancements", "corsair_ir", "court_ir", "court_rule"]
__all__ += ["faction_execution_2026_27", "faction_generic_ir_support_2026_27"]
__all__ += ["generic_rule_ability_effects_for_unit", "generic_rule_lifecycle_hook_handlers"]
__all__ += ["generic_rule_lifecycle_hooks", "generic_rule_persisting_effect"]
__all__ += ["generic_rule_selected_to_fight_effects", "path_outcast_ir", "pytest", "replace"]
__all__ += ["rule_ir_grants_any_ability", "validate_json_value", "with_unit_keywords"]
