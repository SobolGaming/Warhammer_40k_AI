from __future__ import annotations

from tests.shared.category_migration.ws14_generic_ir_lifecycle_bindings import (
    _COURT_ENHANCEMENT_EXECUTION_IDS,
    _COURT_GENERIC_EXECUTION_IDS,
    _MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS,
    _MORE_DAKKA_GENERIC_EXECUTION_IDS,
    _SPECTACLE_ENHANCEMENT_EXECUTION_IDS,
    _SPECTACLE_GENERIC_EXECUTION_IDS,
    CHARGE_FIGHTS_FIRST_EFFECT_KIND,
    DESTROYED_TARGET_UNIT_CONTEXT_KEY,
    ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
    FALL_BACK_UNIT_CONTEXT_KEY,
    JUST_SHOT_UNIT_CONTEXT_KEY,
    SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE,
    SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE,
    STRATAGEM_DECISION_TYPE,
    AbilityKind,
    ArmyCatalog,
    ArmyMusterRequest,
    BattleFormationRequestContext,
    BattlePhase,
    BattlePhaseKind,
    Characteristic,
    CharacteristicValue,
    CommandPointGainStatus,
    CommandPointSourceKind,
    DatasheetKeywordSet,
    DecisionResult,
    DetachmentDefinition,
    DetachmentSelection,
    EffectExpiration,
    EnhancementAssignment,
    EnhancementDefinition,
    FactionDefinition,
    FactionRuleExecutionContext,
    FactionRuleExecutionResult,
    FactionRuleExecutionStatus,
    FightPhaseState,
    FightsFirstRegistry,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    HitRollModifierContext,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    MissionSetup,
    ModelProfileSelection,
    MovementBudgetModifierContext,
    MovementCapabilitySet,
    MovementMode,
    ObjectiveControlModifierContext,
    PersistingEffect,
    Phase17FExecutionStatus,
    Pose,
    ReactionQueue,
    RulesetDescriptor,
    RuntimeContentBundle,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SetupStep,
    ShootingPhaseState,
    ShootingTargetRestrictionContext,
    ShootingType,
    StratagemDefinition,
    StratagemEligibilityContext,
    StratagemUseRecord,
    TimingTriggerKind,
    UnitCharacteristicModifierContext,
    UnitMusterSelection,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileModifierContext,
    WoundRollModifierContext,
    apply_stratagem_decision,
    chapter_approved_2026_27_mission_pack,
    charge_transit_through_non_vehicle_monster_models_allowed,
    court_ir,
    create_deterministic_battlefield_scenario,
    emperors_children_july,
    enter_battle_for_fixture,
    json,
    july_faction_packs_2026_07,
    movement_transit_through_terrain_features_allowed,
    muster_army,
    pytest,
    replace,
    request_stratagem_use_from_index,
    source_backed_reroll_permission_context_for_unit,
)
from tests.shared.category_migration.ws14_generic_ir_lifecycle_court import (
    _court_battle_lifecycle,
    _court_blade_profile,
    _court_catalog,
    _court_datasheet_id_for_selection,
    _court_lifecycle_config,
    _court_muster_request,
    _court_shoota_profile,
    _court_stratagem,
    _court_stratagem_decision_result,
    _court_weapon_profile_context,
    _place_units_for_court_within_12,
    _use_court_stratagem,
    _use_court_stratagem_through_lifecycle,
)
from tests.shared.category_migration.ws14_generic_ir_lifecycle_more_dakka import (
    _mob_shoota_profile,
    _more_dakka_battle_lifecycle,
    _more_dakka_catalog,
    _more_dakka_lifecycle_config,
    _more_dakka_muster_request,
    _more_dakka_stratagem,
    _more_dakka_stratagem_decision_result,
    _place_units_for_more_dakka_shooting,
    _use_more_dakka_stratagem,
    _use_more_dakka_stratagem_through_lifecycle,
)
from tests.shared.category_migration.ws14_generic_ir_lifecycle_shared_lifecycle import (
    _apply_battle_formation_hooks_from_bundle,
    _clear_terrain,
    _effect_parameter,
    _first_model_id,
    _grant_cp,
    _json_object,
    _last_event_payload,
    _mission_setup,
    _option_stratagem_id,
    _option_target_unit_id,
    _prepare_battle_phase,
    _profile_has_ability,
    _record_charge_move_effect,
    _record_fixed_secondary_choices_for_fixture,
    _replace_unit_poses,
    _runtime_content_bundle,
    _set_current_battle_phase,
    _state,
    _weapon_profile_context,
)
from tests.shared.category_migration.ws14_generic_ir_lifecycle_spectacle import (
    _leader_blade_profile,
    _spectacle_battle_lifecycle,
    _spectacle_catalog,
    _spectacle_lifecycle_config,
    _spectacle_muster_request,
    _spectacle_stratagem,
    _spectacle_stratagem_decision_result,
    _spectacle_weapon_profile_context,
    _use_spectacle_stratagem,
    _use_spectacle_stratagem_through_lifecycle,
)

__all__: list[str] = []
__all__ += ["AbilityKind", "ArmyCatalog", "ArmyMusterRequest", "BattleFormationRequestContext"]
__all__ += ["CHARGE_FIGHTS_FIRST_EFFECT_KIND", "BattlePhase", "BattlePhaseKind", "Characteristic"]
__all__ += ["CharacteristicValue", "CommandPointGainStatus", "CommandPointSourceKind"]
__all__ += ["DESTROYED_TARGET_UNIT_CONTEXT_KEY", "DatasheetKeywordSet", "DecisionResult"]
__all__ += ["ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY", "DetachmentDefinition", "DetachmentSelection"]
__all__ += ["EffectExpiration", "EnhancementAssignment", "EnhancementDefinition"]
__all__ += ["FALL_BACK_UNIT_CONTEXT_KEY", "FactionDefinition", "FactionRuleExecutionContext"]
__all__ += ["FactionRuleExecutionResult", "FactionRuleExecutionStatus", "FightPhaseState"]
__all__ += ["FightsFirstRegistry", "GameConfig", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecycleStage", "GameState", "HitRollModifierContext"]
__all__ += ["JUST_SHOT_UNIT_CONTEXT_KEY", "JsonValue", "LifecycleStatus", "LifecycleStatusKind"]
__all__ += ["MissionSetup", "ModelProfileSelection", "MovementBudgetModifierContext"]
__all__ += ["MovementCapabilitySet", "MovementMode", "ObjectiveControlModifierContext"]
__all__ += ["PersistingEffect", "Phase17FExecutionStatus", "Pose", "ReactionQueue"]
__all__ += ["RulesetDescriptor", "RuntimeContentBundle"]
__all__ += ["SELECT_FACTION_RULE_COMMAND_PHASE_START_OPTION_DECISION_TYPE"]
__all__ += ["SELECT_TRIGGERED_MOVEMENT_DECISION_TYPE", "STRATAGEM_DECISION_TYPE"]
__all__ += ["SecondaryMissionChoice", "SecondaryMissionMode", "SetupStep", "ShootingPhaseState"]
__all__ += ["ShootingTargetRestrictionContext", "ShootingType", "StratagemDefinition"]
__all__ += ["StratagemEligibilityContext", "StratagemUseRecord", "TimingTriggerKind"]
__all__ += ["UnitCharacteristicModifierContext", "UnitMusterSelection", "WeaponKeyword"]
__all__ += ["WeaponProfile", "WeaponProfileModifierContext", "WoundRollModifierContext"]
__all__ += ["_COURT_ENHANCEMENT_EXECUTION_IDS", "_COURT_GENERIC_EXECUTION_IDS"]
__all__ += ["_MORE_DAKKA_ENHANCEMENT_EXECUTION_IDS", "_MORE_DAKKA_GENERIC_EXECUTION_IDS"]
__all__ += ["_SPECTACLE_ENHANCEMENT_EXECUTION_IDS", "_SPECTACLE_GENERIC_EXECUTION_IDS"]
__all__ += ["_apply_battle_formation_hooks_from_bundle", "_clear_terrain"]
__all__ += ["_court_battle_lifecycle", "_court_blade_profile", "_court_catalog"]
__all__ += ["_court_datasheet_id_for_selection", "_court_lifecycle_config"]
__all__ += ["_court_muster_request", "_court_shoota_profile", "_court_stratagem"]
__all__ += ["_court_stratagem_decision_result", "_court_weapon_profile_context"]
__all__ += ["_effect_parameter", "_first_model_id", "_grant_cp", "_json_object"]
__all__ += ["_last_event_payload", "_leader_blade_profile", "_mission_setup"]
__all__ += ["_mob_shoota_profile", "_more_dakka_battle_lifecycle", "_more_dakka_catalog"]
__all__ += ["_more_dakka_lifecycle_config", "_more_dakka_muster_request", "_more_dakka_stratagem"]
__all__ += ["_more_dakka_stratagem_decision_result", "_option_stratagem_id"]
__all__ += ["_option_target_unit_id", "_place_units_for_court_within_12"]
__all__ += ["_place_units_for_more_dakka_shooting", "_prepare_battle_phase"]
__all__ += ["_profile_has_ability", "_record_charge_move_effect"]
__all__ += ["_record_fixed_secondary_choices_for_fixture", "_replace_unit_poses"]
__all__ += ["_runtime_content_bundle", "_set_current_battle_phase", "_spectacle_battle_lifecycle"]
__all__ += ["_spectacle_catalog", "_spectacle_lifecycle_config", "_spectacle_muster_request"]
__all__ += ["_spectacle_stratagem", "_spectacle_stratagem_decision_result"]
__all__ += ["_spectacle_weapon_profile_context", "_state", "_use_court_stratagem"]
__all__ += ["_use_court_stratagem_through_lifecycle", "_use_more_dakka_stratagem"]
__all__ += ["_use_more_dakka_stratagem_through_lifecycle", "_use_spectacle_stratagem"]
__all__ += ["_use_spectacle_stratagem_through_lifecycle", "_weapon_profile_context"]
__all__ += ["apply_stratagem_decision", "chapter_approved_2026_27_mission_pack"]
__all__ += ["charge_transit_through_non_vehicle_monster_models_allowed", "court_ir"]
__all__ += ["create_deterministic_battlefield_scenario", "emperors_children_july"]
__all__ += ["enter_battle_for_fixture", "json", "july_faction_packs_2026_07"]
__all__ += ["movement_transit_through_terrain_features_allowed", "muster_army", "pytest"]
__all__ += ["replace", "request_stratagem_use_from_index"]
__all__ += ["source_backed_reroll_permission_context_for_unit"]
