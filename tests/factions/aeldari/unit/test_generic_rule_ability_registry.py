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


def test_default_generic_rule_ability_registry_maps_corsair_coterie_enhancement_grants() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY

    archraider_source = _aeldari_corsair_coterie_source(
        corsair_ir.ARCHRAIDER_ENHANCEMENT_DESCRIPTOR_ID
    )
    archraider = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_MARKER_ABILITY,)
    )
    assert archraider.hook_family is GenericRuleAbilityHookFamily.ENHANCEMENT_EFFECT
    assert archraider.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert archraider.enhancement_id == corsair_ir.ARCHRAIDER_ENHANCEMENT_ID
    assert archraider.effect_id(archraider_source) == corsair_enhancements.ARCHRAIDER_EFFECT_ID

    archraider_setup = next(
        descriptor
        for descriptor in registry.battle_formation_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_MODEL_SELECTION_ABILITY,)
    )
    assert archraider_setup.hook_family is GenericRuleAbilityHookFamily.BATTLE_FORMATION
    assert archraider_setup.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert (
        archraider_setup.hook_id(archraider_source) == corsair_enhancements.ARCHRAIDER_SETUP_HOOK_ID
    )

    archraider_cost_choice = next(
        descriptor
        for descriptor in registry.stratagem_cost_choice_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_STRATAGEM_COST_CHOICE_ABILITY,)
    )
    assert archraider_cost_choice.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_CHOICE
    assert archraider_cost_choice.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert (
        archraider_cost_choice.hook_id(archraider_source)
        == corsair_enhancements.ARCHRAIDER_COST_CHOICE_HOOK_ID
    )

    archraider_cost_modifier = next(
        descriptor
        for descriptor in registry.stratagem_cost_modifier_abilities
        if descriptor.ability_ids() == (corsair_ir.ARCHRAIDER_STRATAGEM_COST_MODIFIER_ABILITY,)
    )
    assert (
        archraider_cost_modifier.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_MODIFIER
    )
    assert archraider_cost_modifier.source_rule_id == corsair_ir.ARCHRAIDER_SOURCE_RULE_ID
    assert (
        archraider_cost_modifier.modifier_id(archraider_source)
        == corsair_enhancements.ARCHRAIDER_COST_MODIFIER_ID
    )

    infamy_source = _aeldari_corsair_coterie_source(corsair_ir.INFAMY_ENHANCEMENT_DESCRIPTOR_ID)
    infamy = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.INFAMY_MARKER_ABILITY,)
    )
    assert infamy.source_rule_id == corsair_ir.INFAMY_SOURCE_RULE_ID
    assert infamy.enhancement_id == corsair_ir.INFAMY_ENHANCEMENT_ID
    assert infamy.effect_id(infamy_source) == corsair_enhancements.INFAMY_EFFECT_ID

    infamy_oc = next(
        descriptor
        for descriptor in registry.objective_control_modifier_abilities
        if descriptor.ability_ids() == (corsair_ir.INFAMY_OBJECTIVE_CONTROL_ABILITY,)
    )
    assert infamy_oc.hook_family is GenericRuleAbilityHookFamily.OBJECTIVE_CONTROL_MODIFIER
    assert infamy_oc.source_rule_id == corsair_ir.INFAMY_SOURCE_RULE_ID
    assert (
        infamy_oc.modifier_id(infamy_source)
        == corsair_enhancements.INFAMY_OBJECTIVE_CONTROL_MODIFIER_ID
    )

    voidstone_source = _aeldari_corsair_coterie_source(
        corsair_ir.VOIDSTONE_ENHANCEMENT_DESCRIPTOR_ID
    )
    voidstone = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.VOIDSTONE_MARKER_ABILITY,)
    )
    assert voidstone.source_rule_id == corsair_ir.VOIDSTONE_SOURCE_RULE_ID
    assert voidstone.enhancement_id == corsair_ir.VOIDSTONE_ENHANCEMENT_ID
    assert voidstone.effect_id(voidstone_source) == corsair_enhancements.VOIDSTONE_EFFECT_ID

    voidstone_save = next(
        descriptor
        for descriptor in registry.save_option_modifier_abilities
        if descriptor.ability_ids() == (corsair_ir.VOIDSTONE_SAVE_OPTION_ABILITY,)
    )
    assert voidstone_save.hook_family is GenericRuleAbilityHookFamily.SAVE_OPTION_MODIFIER
    assert voidstone_save.source_rule_id == corsair_ir.VOIDSTONE_SOURCE_RULE_ID
    assert (
        voidstone_save.modifier_id(voidstone_source)
        == corsair_enhancements.VOIDSTONE_SAVE_MODIFIER_ID
    )

    webway_source = _aeldari_corsair_coterie_source(
        corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_DESCRIPTOR_ID
    )
    webway = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.WEBWAY_PATHSTONE_MARKER_ABILITY,)
    )
    assert webway.source_rule_id == corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
    assert webway.enhancement_id == corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_ID
    assert webway.effect_id(webway_source) == corsair_enhancements.WEBWAY_PATHSTONE_EFFECT_ID

    webway_deep_strike = next(
        descriptor
        for descriptor in registry.enhancement_effect_abilities
        if descriptor.ability_ids() == (corsair_ir.WEBWAY_PATHSTONE_DEEP_STRIKE_ABILITY,)
    )
    assert webway_deep_strike.source_rule_id == corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
    assert webway_deep_strike.enhancement_id == corsair_ir.WEBWAY_PATHSTONE_ENHANCEMENT_ID
    assert (
        webway_deep_strike.effect_id(webway_source)
        == corsair_enhancements.WEBWAY_PATHSTONE_DEEP_STRIKE_EFFECT_ID
    )

    webway_turn_end = next(
        descriptor
        for descriptor in registry.turn_end_abilities
        if descriptor.ability_ids() == (corsair_ir.WEBWAY_PATHSTONE_RESERVES_ABILITY,)
    )
    assert webway_turn_end.hook_family is GenericRuleAbilityHookFamily.TURN_END
    assert webway_turn_end.source_rule_id == corsair_ir.WEBWAY_PATHSTONE_SOURCE_RULE_ID
    assert (
        webway_turn_end.hook_id(webway_source)
        == corsair_enhancements.WEBWAY_PATHSTONE_TURN_END_HOOK_ID
    )


__all__: list[str] = []
__all__ += ["AdvanceEligibilityContext", "AdvanceMoveContext", "AdvanceMoveGrant", "ArmyCatalog"]
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["BattleFormationRequestContext", "BattleFormationResultContext", "BattlePhase"]
__all__ += ["CORE_FIRE_OVERWATCH_HANDLER_ID", "Callable", "Characteristic", "CharacteristicValue"]
__all__ += ["DecisionController", "DetachmentSelection", "EffectExpiration"]
__all__ += ["EnhancementAssignment", "EnhancementEffectContext", "FallBackEligibilityContext"]
__all__ += ["FightActivationAbilityContext", "FightPhaseStartRequestContext"]
__all__ += ["FightPhaseStartResultContext", "FightUnitSelectedContext", "GameConfig"]
__all__ += ["GameLifecycleError", "GameLifecycleStage", "GameState", "GenericRuleAbilityRegistry"]
__all__ += ["GenericRuleAbilitySource", "JsonValue", "ModelGeometry", "ModelInstance"]
__all__ += ["ModelKeywordAssignment", "ModelProfileSelection", "ModifierOperation"]
__all__ += ["ModifierTerm", "MovementEndSurgeContext", "ObjectiveControlModifierContext"]
__all__ += ["PersistingEffect", "PhaseEndObjectiveControlContext"]
__all__ += ["ReserveArrivalDistanceContext", "RuleEffectKind", "RuleExecutionResult"]
__all__ += ["RuleExecutionStatus", "RuleIR", "RuleTargetKind", "RulesetDescriptor"]
__all__ += ["RuntimeContentActivation", "SaveOptionModifierContext", "SetupStep"]
__all__ += ["ShootingTargetRestrictionContext", "ShootingUnitSelectedContext"]
__all__ += ["StartingStrengthRecord", "StratagemCategory", "StratagemCostChoiceRequestContext"]
__all__ += ["StratagemCostChoiceResultContext", "StratagemCostModifierContext"]
__all__ += ["StratagemDefinition", "StratagemEligibilityContext", "StratagemTargetBinding"]
__all__ += ["StratagemTargetKind", "StratagemTargetSpec", "StratagemTimingDescriptor"]
__all__ += ["TimingTriggerKind", "TurnEndRequestContext", "TurnEndResultContext"]
__all__ += ["UnitDestroyedContext", "UnitInstance", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["_ENEMY_UNIT_ID", "_RANGERS_UNIT_ID", "_SHROUD_RUNNERS_UNIT_ID", "_WARPTIDE_UNIT_ID"]
__all__ += ["_aeldari_path_of_the_outcast_source", "_army", "_blood_legion_source"]
__all__ += ["_court_of_the_phoenician_source", "_grant_ability_effect", "_keyword_any_state"]
__all__ += ["_minimal_warptide_game_config", "_model", "_muster_request"]
__all__ += ["_owner_player_id_for_unit_id", "_raise_selected_to_fight_payload_error"]
__all__ += ["_selected_to_fight_effect_payload", "_selected_to_fight_grant_payload"]
__all__ += ["_selected_to_fight_reroll_payload", "_shadow_legion_enhancement_source"]
__all__ += ["_shadow_legion_source", "_unit", "_warptide_activation"]
__all__ += ["_warptide_cost_modifier_context", "_warptide_grant_ability_effect"]
__all__ += ["_warptide_setup_state", "_warptide_source", "_warptide_state"]
__all__ += ["advance_move_lifecycle_hooks", "blood_legion_ir", "cast", "copy", "court_ir"]
__all__ += ["court_rule", "dark_pacts", "faction_execution_2026_27"]
__all__ += ["faction_generic_ir_support_2026_27", "generic_detachment_effects"]
__all__ += ["generic_rule_ability_effects_for_unit", "generic_rule_lifecycle_hook_handlers"]
__all__ += ["generic_rule_lifecycle_hooks", "generic_rule_persisting_effect"]
__all__ += ["generic_rule_selected_to_fight_effects", "path_outcast_ir", "pytest", "replace"]
__all__ += ["rule_ir_grants_any_ability", "shadow_legion_ir", "validate_json_value"]
__all__ += ["warptide_ir", "with_unit_keywords"]
