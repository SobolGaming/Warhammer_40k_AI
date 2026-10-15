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


def test_default_generic_rule_ability_registry_maps_court_detachment_cost_grant() -> None:
    registry = DEFAULT_GENERIC_RULE_ABILITY_REGISTRY
    source = _court_of_the_phoenician_source()

    master_of_the_pageant = next(
        descriptor
        for descriptor in registry.stratagem_cost_modifier_abilities
        if descriptor.ability_ids()
        == (court_ir.MASTER_OF_THE_PAGEANT_STRATAGEM_COST_REDUCTION_ABILITY,)
    )

    assert master_of_the_pageant.hook_family is GenericRuleAbilityHookFamily.STRATAGEM_COST_MODIFIER
    assert master_of_the_pageant.coverage_descriptor_id == (
        court_ir.COURT_OF_THE_PHOENICIAN_DETACHMENT_RULE_DESCRIPTOR_ID
    )
    assert master_of_the_pageant.source_rule_id == court_rule.COURT_OF_THE_PHOENICIAN_RULE_SOURCE_ID
    assert (
        master_of_the_pageant.modifier_id(source)
        == court_rule.MASTER_OF_THE_PAGEANT_COST_MODIFIER_ID
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
__all__ += ["_aeldari_corsair_coterie_source", "_aeldari_path_of_the_outcast_source", "_army"]
__all__ += ["_blood_legion_source", "_grant_ability_effect", "_keyword_any_state"]
__all__ += ["_minimal_warptide_game_config", "_model", "_muster_request"]
__all__ += ["_owner_player_id_for_unit_id", "_raise_selected_to_fight_payload_error"]
__all__ += ["_selected_to_fight_effect_payload", "_selected_to_fight_grant_payload"]
__all__ += ["_selected_to_fight_reroll_payload", "_shadow_legion_enhancement_source"]
__all__ += ["_shadow_legion_source", "_unit", "_warptide_activation"]
__all__ += ["_warptide_cost_modifier_context", "_warptide_grant_ability_effect"]
__all__ += ["_warptide_setup_state", "_warptide_source", "_warptide_state"]
__all__ += ["advance_move_lifecycle_hooks", "blood_legion_ir", "cast", "copy"]
__all__ += ["corsair_enhancements", "corsair_ir", "dark_pacts", "faction_execution_2026_27"]
__all__ += ["faction_generic_ir_support_2026_27", "generic_detachment_effects"]
__all__ += ["generic_rule_ability_effects_for_unit", "generic_rule_lifecycle_hook_handlers"]
__all__ += ["generic_rule_lifecycle_hooks", "generic_rule_persisting_effect"]
__all__ += ["generic_rule_selected_to_fight_effects", "path_outcast_ir", "pytest", "replace"]
__all__ += ["rule_ir_grants_any_ability", "shadow_legion_ir", "validate_json_value"]
__all__ += ["warptide_ir", "with_unit_keywords"]
