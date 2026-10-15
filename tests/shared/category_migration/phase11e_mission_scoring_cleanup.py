from __future__ import annotations

from tests.shared.category_migration.phase11e_mission_scoring_cleanup_bindings import (
    ATTACHED_UNIT_DESTRUCTION_SOURCE_RULE_ID,
    ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256,
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    FIRE_OVERWATCH_RULE_ID,
    PARAMETERIZED_DECISION_OPTION_ID,
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    SCORING_TERRAIN_FEATURE_ID,
    SECONDARY_MISSION_DECISION_TYPE,
    SEEDED_TACTICAL_DRAW_REQUEST_ID,
    SEEDED_TACTICAL_DRAW_RESULT_ID,
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    SNAP_SHOOTING_RULE_ID,
    START_MISSION_ACTION_DECISION_TYPE,
    STRATAGEM_DECISION_TYPE,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
    TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    AttachmentDeclaration,
    AttackSequence,
    AuthenticatedPrincipal,
    BattlefieldRegionKind,
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlePhase,
    BattleRoundFlow,
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
    BelowHalfStrengthContext,
    Characteristic,
    CharacteristicValue,
    CoherencyCleanupRemoval,
    CommandPointGainStatus,
    CommandPointSourceKind,
    DamageProfile,
    DecisionController,
    DecisionRecord,
    DecisionRequest,
    DecisionResult,
    DeploymentZoneCircleCutout,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
    DestructionSourceKind,
    DetachmentSelection,
    DiceExpression,
    DiceRollManager,
    DiceRollSpec,
    EndTurnCleanupState,
    EventLog,
    EventRecord,
    EventStreamCursor,
    FellBackUnitState,
    FiniteOptionSubmission,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    GameStatePayload,
    JsonValue,
    LifecycleStatus,
    LifecycleStatusKind,
    LocalGameSession,
    MissionActionState,
    MissionActionStatus,
    MissionLogicalTerrainArea,
    MissionScoringPolicy,
    MissionSetup,
    ModelDestructionAttribution,
    ModelDisplacementKind,
    ModelInstance,
    ModelPlacement,
    ModelProfileSelection,
    ModelRemovalRecord,
    ModifierOperation,
    ModifierTerm,
    MovementDiceRecord,
    MovementMode,
    MovementPhaseActionKind,
    ObjectiveControlContext,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerRole,
    Path,
    PendingReturnOnDeath,
    PlaceholderPhaseHandler,
    PlayerPrimaryMissionAssignment,
    Pose,
    PrimaryBattlefieldDepartureState,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryObjectiveTurnStartStatePayload,
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryTerrainTrapState,
    PrimaryUnattributedDestructionCause,
    PrimaryUnitDestructionEvidence,
    PrimaryUnitDestructionState,
    PrimaryUnitDestructionStatePayload,
    PrincipalRole,
    ReplayArtifact,
    ReplayRunner,
    ReplayRunStatus,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    RulesetDescriptor,
    RulesUnitObjectiveProximityWitness,
    RuntimeModifierRegistry,
    SaveKind,
    SecondaryDestroyedModelState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    SecondaryMissionScoringRule,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    ShootingPhaseHandler,
    ShootingPhaseState,
    ShootingType,
    TacticalSecondaryAchievementContext,
    TacticalSecondaryDraw,
    TransportCapacityProfile,
    TransportCargoState,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
    advance_completed_phase_fixture,
    append_authenticated_normal_move,
    apply_return_on_death_placement_decision,
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
    battlefield_removal_kind_from_token,
    build_primary_scoring_state_evidence,
    build_return_on_death_placement_request,
    cast,
    chapter_approved_2026_27_mission_pack,
    create_deterministic_battlefield_scenario,
    cross_turn_destruction_comparison_evidence,
    deepcopy,
    destroy_model_by_rule,
    destruction_source_objective_proximity_witness,
    destruction_timeline_integrity,
    deterministic_tactical_secondary_draw,
    drain_pending_secondary_mission_setup,
    enter_battle_for_fixture,
    expected_tactical_secondary_award_from_state,
    historical_event_integrity,
    interrupt_mission_action_for_battlefield_departure,
    interrupt_mission_action_for_displacement,
    json,
    logical_terrain_area_within_player_deployment_zone,
    logical_terrain_area_within_player_territory,
    mission_action_interruption_reason_for_displacement,
    mission_action_status_from_token,
    mission_action_unit_ineligibility_reason,
    mission_logical_terrain_areas,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    muster_army,
    objective_control_timing_from_token,
    opponent_home_control_evidence,
    primary_battlefield_departure_id,
    primary_reserve_entry_source_terminal_bindings_payload,
    primary_unit_destruction_id,
    pytest,
    record_new_primary_battlefield_departure_events,
    record_new_primary_turn_start_evidence_events,
    record_primary_battlefield_departure,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    record_primary_reserve_entry_mutation_event,
    record_primary_reserve_entry_provider_terminal_event,
    record_primary_turn_start_evidence,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
    record_primary_unit_destructions_for_destroyed_models,
    record_secondary_destruction_for_fixture,
    record_shooting_declaration_for_executor_fixture,
    render_pending_decision_for_cli,
    replace,
    request_mission_action_start,
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
    reserve_destruction_policy_from_scoring_policy,
    reserve_entry_evidence_payload,
    resolve_attack_sequence_until_blocked,
    resolve_end_turn_cleanup,
    resolve_objective_control,
    resolve_unarrived_reserve_destruction,
    resolved_secondary_mission_selection_for_card,
    rules_unit_is_battle_shocked,
    rules_unit_objective_proximity_witness,
    rules_unit_started_mission_action_this_turn,
    rules_unit_view_by_id,
    saving_throw_roll_spec,
    score_primary_objective_control_boundary,
    secondary_mission_card_mode_from_token,
    secondary_mission_card_status_from_token,
    seed_completed_fight_phase,
    seed_resolved_secondary_mission_selections,
    sha256,
    shapely_backend,
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
    synchronize_secondary_destruction_projection_payload,
    tactical_secondary_achievement_context_from_award,
    unit_destruction_completion_events_for_interval,
    validate_primary_historical_event_integrity,
    victory_point_source_kind_from_token,
    warhammer_event_companion_2026_07_mission_pack,
    with_unit_keywords,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_configuration import (
    _army_muster_request,
    _battle_state,
    _battle_state_for_primary,
    _battle_state_from_config,
    _catalog_with_directional_force_dispositions,
    _chapter_approved_immovable_object_mission_setup,
    _config,
    _config_for_primary,
    _config_with_player_a_attached_unit,
    _config_with_player_a_transport,
    _config_with_player_a_vehicle,
    _config_with_player_b_character,
    _config_with_player_b_horde_units,
    _config_with_player_b_vehicles,
    _config_with_two_player_a_infantry_units,
    _event_companion_death_trap_mission_setup,
    _event_companion_meatgrinder_mission_setup,
    _event_companion_mission_setup,
    _event_companion_mission_setup_with_scoring_terrain_feature,
    _event_companion_purge_and_secure_mission_setup,
    _mission_setup,
    _mission_setup_for_primary,
    _mustered_armies,
    _ruleset,
    _unit_muster_selection,
    _with_player_primary_mission,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_history_and_reserves import (
    _authentic_attached_unit_lifecycle_payload,
    _authentic_integrity_graph,
    _authentic_primary_destruction_lifecycle_payload,
    _authentic_reserve_deadline_lifecycle_payload,
    _authentic_timeline_graph,
    _battle_state_with_unarrived_reserve_at_round_three_deadline,
    _historical_event_index,
    _record_secondary_unit_destruction,
    _record_secondary_vehicle_destruction,
    _record_test_completed_primary_unit_destruction,
    _record_test_primary_unit_destruction,
    _remove_unit_for_primary_destruction,
    _replace_historical_event,
    _resequence_historical_events,
    _resolve_transport_reserve_at_round_boundary,
    _set_model_wounds_remaining,
    _set_unit_wounds_remaining,
    _test_primary_destruction_attribution,
    _transport_reserve_deadline_lifecycle,
    _typed_primary_reserve_entry_evidence,
    _unattributed_timeline_destruction,
    authentic_attached_unit_lifecycle_payload,
    authentic_primary_destruction_lifecycle_payload,
    authentic_reserve_deadline_lifecycle_payload,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_mission_lifecycle import (
    _advanced_unit_state,
    _attached_cleanse_action,
    _battle_lifecycle,
    _battle_lifecycle_for_primary,
    _battle_lifecycle_with_player_a_vehicle,
    _center_marker_definition,
    _center_marker_definition_for_setup,
    _complete_shooting_for_action_test,
    _controlled_objective_result,
    _decline_stratagem_window_if_pending,
    _event_binds_objective_control_record,
    _first_plunderable_logical_terrain_area,
    _logical_terrain_area_test_point,
    _mission_action_state,
    _no_mans_land_non_home_objective_ids,
    _objective_logical_terrain_area,
    _objective_marker_definition,
    _objective_marker_matches_suffix,
    _objective_marker_suffix_aliases,
    _place_unit_near_objective,
    _record_completed_zero_vp_mission_action,
    _record_missing_turn_start_evidence_events,
    _replace_unit,
    _replace_unit_objective_control,
    _start_mission_action_via_lifecycle,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_state_primitives import (
    _place_unit_near_point,
    _record_active_tactical_secondary,
    _secondary_choice,
    _with_model_offsets,
)
from tests.shared.category_migration.phase11e_mission_scoring_cleanup_tactical_ledgers import (
    _active_tactical_card,
    _advance_to_secondary_request,
    _battle_lifecycle_with_active_tactical_cards,
    _event_companion_battle_lifecycle_with_active_tactical_cards,
    _public_card_states,
    _public_ledger,
    _public_secondary_choice,
    _record_tactical_secondary_achievement_context,
    _seed_player_a_tactical_secondary_cards,
    _tactical_secondary_achievement_context_for_card,
    _transaction_metadata,
)

__all__: list[str] = []
__all__ += ["ATTACHED_UNIT_DESTRUCTION_SOURCE_RULE_ID", "ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256"]
__all__ += ["AdvanceRollRequest", "AdvanceRollResult", "AdvancedUnitState", "ArmyCatalog"]
__all__ += ["ArmyDefinition", "ArmyMusterRequest", "AttachmentDeclaration", "AttackSequence"]
__all__ += ["AuthenticatedPrincipal", "BattlePhase", "BattleRoundFlow", "BattleShockResult"]
__all__ += ["BattleShockTestReason", "BattleShockTestRequest", "BattlefieldRegionKind"]
__all__ += ["BattlefieldRemovalKind", "BattlefieldScenario", "BattlefieldTransitionBatch"]
__all__ += ["BelowHalfStrengthContext", "Characteristic", "CharacteristicValue"]
__all__ += ["CoherencyCleanupRemoval", "CommandPointGainStatus", "CommandPointSourceKind"]
__all__ += ["DECLINE_MISSION_ACTION_START_OPTION_ID", "DECLINE_STRATAGEM_WINDOW_OPTION_ID"]
__all__ += ["DamageProfile", "DecisionController", "DecisionRecord", "DecisionRequest"]
__all__ += ["DecisionResult", "DeploymentZoneCircleCutout", "DeploymentZonePoint"]
__all__ += ["DeploymentZonePolygon", "DeploymentZoneShape", "DestructionSourceKind"]
__all__ += ["DetachmentSelection", "DiceExpression", "DiceRollManager", "DiceRollSpec"]
__all__ += ["EndTurnCleanupState", "EventLog", "EventRecord", "EventStreamCursor"]
__all__ += ["FIRE_OVERWATCH_RULE_ID", "FellBackUnitState", "FiniteOptionSubmission", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecyclePayload", "GameLifecycleStage"]
__all__ += ["GameState", "GameStatePayload", "JsonValue", "LifecycleStatus"]
__all__ += ["LifecycleStatusKind", "LocalGameSession", "MissionActionState"]
__all__ += ["MissionActionStatus", "MissionLogicalTerrainArea", "MissionScoringPolicy"]
__all__ += ["MissionSetup", "ModelDestructionAttribution", "ModelDisplacementKind"]
__all__ += ["ModelInstance", "ModelPlacement", "ModelProfileSelection", "ModelRemovalRecord"]
__all__ += ["ModifierOperation", "ModifierTerm", "MovementDiceRecord", "MovementMode"]
__all__ += ["MovementPhaseActionKind", "ObjectiveControlContext"]
__all__ += ["ObjectiveControlModifierBinding", "ObjectiveControlModifierContext"]
__all__ += ["ObjectiveControlRecord", "ObjectiveControlResult", "ObjectiveControlScore"]
__all__ += ["ObjectiveControlStatus", "ObjectiveControlTiming", "ObjectiveMarkerDefinition"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "ObjectiveMarkerRole", "Path"]
__all__ += ["PendingReturnOnDeath", "PlaceholderPhaseHandler", "PlayerPrimaryMissionAssignment"]
__all__ += ["Pose", "PrimaryBattlefieldDepartureState", "PrimaryMissionScoringRule"]
__all__ += ["PrimaryObjectiveTurnStartState", "PrimaryObjectiveTurnStartStatePayload"]
__all__ += ["PrimaryReserveEntryProvider", "PrimaryReserveEntryProviderKind"]
__all__ += ["PrimaryRulesUnitTurnStartSnapshot", "PrimaryTerrainTrapState"]
__all__ += ["PrimaryUnattributedDestructionCause", "PrimaryUnitDestructionEvidence"]
__all__ += ["PrimaryUnitDestructionState", "PrimaryUnitDestructionStatePayload", "PrincipalRole"]
__all__ += ["RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE", "ReplayArtifact", "ReplayRunStatus"]
__all__ += ["ReplayRunner", "ReserveDestructionTimingPolicy", "ReserveKind", "ReserveOrigin"]
__all__ += ["ReserveState", "ReserveStatus", "ReturnDestroyedTargetScope"]
__all__ += ["ReturnRestoreWoundsMode", "RulesUnitObjectiveProximityWitness", "RulesetDescriptor"]
__all__ += ["SCORING_TERRAIN_FEATURE_ID", "RuntimeModifierRegistry"]
__all__ += ["SECONDARY_MISSION_DECISION_TYPE", "SEEDED_TACTICAL_DRAW_REQUEST_ID"]
__all__ += ["SEEDED_TACTICAL_DRAW_RESULT_ID", "SELECT_MOVEMENT_ACTION_DECISION_TYPE"]
__all__ += ["SELECT_MOVEMENT_UNIT_DECISION_TYPE", "SELECT_SHOOTING_UNIT_DECISION_TYPE"]
__all__ += ["SNAP_SHOOTING_RULE_ID", "START_MISSION_ACTION_DECISION_TYPE"]
__all__ += ["STRATAGEM_DECISION_TYPE", "SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE"]
__all__ += ["SaveKind", "SecondaryDestroyedModelState", "SecondaryMissionCardMode"]
__all__ += ["SecondaryMissionCardState", "SecondaryMissionCardStatus", "SecondaryMissionChoice"]
__all__ += ["SecondaryMissionMode", "SecondaryMissionScoringRule"]
__all__ += ["SecondaryObjectiveCleanseState", "SecondaryTerrainPlunderState"]
__all__ += ["SecondaryUnitDestructionState", "ShootingPhaseHandler", "ShootingPhaseState"]
__all__ += ["TACTICAL_SECONDARY_DISCARD_DECISION_TYPE", "ShootingType"]
__all__ += ["TACTICAL_SECONDARY_DRAW_DECISION_TYPE"]
__all__ += ["TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE"]
__all__ += ["TACTICAL_SECONDARY_SCORE_DECISION_TYPE", "TacticalSecondaryAchievementContext"]
__all__ += ["TacticalSecondaryDraw", "TransportCapacityProfile", "TransportCargoState"]
__all__ += ["UnitInstance", "UnitMusterSelection", "UnitPlacement", "VictoryPointAward"]
__all__ += ["VictoryPointLedger", "VictoryPointSourceKind", "VictoryPointTransaction"]
__all__ += ["_active_tactical_card", "_advance_to_secondary_request", "_advanced_unit_state"]
__all__ += ["_army_muster_request", "_attached_cleanse_action", "_attack_pool_for_test"]
__all__ += ["_authentic_attached_unit_lifecycle_payload", "_authentic_integrity_graph"]
__all__ += ["_authentic_primary_destruction_lifecycle_payload"]
__all__ += ["_authentic_reserve_deadline_lifecycle_payload", "_authentic_timeline_graph"]
__all__ += ["_battle_lifecycle", "_battle_lifecycle_for_primary"]
__all__ += ["_battle_lifecycle_with_active_tactical_cards"]
__all__ += ["_battle_lifecycle_with_player_a_vehicle", "_battle_state"]
__all__ += ["_battle_state_for_primary", "_battle_state_from_config"]
__all__ += ["_battle_state_with_unarrived_reserve_at_round_three_deadline"]
__all__ += ["_catalog_with_directional_force_dispositions", "_center_marker_definition"]
__all__ += ["_center_marker_definition_for_setup"]
__all__ += ["_chapter_approved_immovable_object_mission_setup"]
__all__ += ["_complete_shooting_for_action_test", "_config", "_config_for_primary"]
__all__ += ["_config_with_player_a_attached_unit", "_config_with_player_a_transport"]
__all__ += ["_config_with_player_a_vehicle", "_config_with_player_b_character"]
__all__ += ["_config_with_player_b_horde_units", "_config_with_player_b_vehicles"]
__all__ += ["_config_with_two_player_a_infantry_units", "_controlled_objective_result"]
__all__ += ["_decline_stratagem_window_if_pending", "_event_binds_objective_control_record"]
__all__ += ["_event_companion_battle_lifecycle_with_active_tactical_cards"]
__all__ += ["_event_companion_death_trap_mission_setup"]
__all__ += ["_event_companion_meatgrinder_mission_setup", "_event_companion_mission_setup"]
__all__ += ["_event_companion_mission_setup_with_scoring_terrain_feature"]
__all__ += ["_event_companion_purge_and_secure_mission_setup"]
__all__ += ["_first_plunderable_logical_terrain_area", "_first_weapon_profile"]
__all__ += ["_fixed_roll_result", "_historical_event_index", "_logical_terrain_area_test_point"]
__all__ += ["_mission_action_state", "_mission_setup", "_mission_setup_for_primary"]
__all__ += ["_mustered_armies", "_no_mans_land_non_home_objective_ids"]
__all__ += ["_objective_logical_terrain_area", "_objective_marker_definition"]
__all__ += ["_objective_marker_matches_suffix", "_objective_marker_suffix_aliases"]
__all__ += ["_place_unit_near_objective", "_place_unit_near_point", "_public_card_states"]
__all__ += ["_public_ledger", "_public_secondary_choice", "_record_active_tactical_secondary"]
__all__ += ["_record_completed_zero_vp_mission_action"]
__all__ += ["_record_missing_turn_start_evidence_events", "_record_secondary_unit_destruction"]
__all__ += ["_record_secondary_vehicle_destruction"]
__all__ += ["_record_tactical_secondary_achievement_context"]
__all__ += ["_record_test_completed_primary_unit_destruction"]
__all__ += ["_record_test_primary_unit_destruction", "_remove_unit_for_primary_destruction"]
__all__ += ["_replace_historical_event", "_replace_unit", "_replace_unit_objective_control"]
__all__ += ["_resequence_historical_events", "_resolve_transport_reserve_at_round_boundary"]
__all__ += ["_ruleset", "_secondary_choice", "_seed_player_a_tactical_secondary_cards"]
__all__ += ["_set_model_wounds_remaining", "_set_unit_wounds_remaining"]
__all__ += ["_start_mission_action_via_lifecycle"]
__all__ += ["_tactical_secondary_achievement_context_for_card"]
__all__ += ["_test_primary_destruction_attribution", "_transaction_metadata"]
__all__ += ["_transport_reserve_deadline_lifecycle", "_typed_primary_reserve_entry_evidence"]
__all__ += ["_unattributed_timeline_destruction", "_unit_muster_selection", "_with_model_offsets"]
__all__ += ["_with_player_primary_mission", "advance_completed_phase_fixture"]
__all__ += ["append_authenticated_normal_move", "apply_return_on_death_placement_decision"]
__all__ += ["attack_sequence_hit_roll_spec", "attack_sequence_wound_roll_spec"]
__all__ += ["authentic_attached_unit_lifecycle_payload"]
__all__ += ["authentic_primary_destruction_lifecycle_payload"]
__all__ += ["authentic_reserve_deadline_lifecycle_payload", "battlefield_removal_kind_from_token"]
__all__ += ["build_primary_scoring_state_evidence", "build_return_on_death_placement_request"]
__all__ += ["cast", "chapter_approved_2026_27_mission_pack"]
__all__ += ["create_deterministic_battlefield_scenario"]
__all__ += ["cross_turn_destruction_comparison_evidence", "deepcopy", "destroy_model_by_rule"]
__all__ += ["destruction_source_objective_proximity_witness", "destruction_timeline_integrity"]
__all__ += ["deterministic_tactical_secondary_draw", "drain_pending_secondary_mission_setup"]
__all__ += ["enter_battle_for_fixture", "expected_tactical_secondary_award_from_state"]
__all__ += ["historical_event_integrity", "interrupt_mission_action_for_battlefield_departure"]
__all__ += ["interrupt_mission_action_for_displacement", "json"]
__all__ += ["logical_terrain_area_within_player_deployment_zone"]
__all__ += ["logical_terrain_area_within_player_territory"]
__all__ += ["mission_action_interruption_reason_for_displacement"]
__all__ += ["mission_action_status_from_token", "mission_action_unit_ineligibility_reason"]
__all__ += ["mission_logical_terrain_areas", "mission_pack_for_id"]
__all__ += ["mission_scoring_policies_from_setup", "muster_army"]
__all__ += ["objective_control_timing_from_token", "opponent_home_control_evidence"]
__all__ += ["primary_battlefield_departure_id"]
__all__ += ["primary_reserve_entry_source_terminal_bindings_payload"]
__all__ += ["primary_unit_destruction_id", "pytest"]
__all__ += ["record_new_primary_battlefield_departure_events"]
__all__ += ["record_new_primary_turn_start_evidence_events"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures"]
__all__ += ["record_primary_reserve_entry_mutation_event"]
__all__ += ["record_primary_reserve_entry_provider_terminal_event"]
__all__ += ["record_primary_turn_start_evidence", "record_primary_turn_start_evidence_event"]
__all__ += ["record_primary_unit_destruction_event"]
__all__ += ["record_primary_unit_destructions_for_destroyed_models"]
__all__ += ["record_secondary_destruction_for_fixture"]
__all__ += ["record_shooting_declaration_for_executor_fixture", "render_pending_decision_for_cli"]
__all__ += ["replace", "request_mission_action_start", "request_tactical_secondary_discard"]
__all__ += ["request_tactical_secondary_score", "reserve_destruction_policy_from_scoring_policy"]
__all__ += ["reserve_entry_evidence_payload", "resolve_attack_sequence_until_blocked"]
__all__ += ["resolve_end_turn_cleanup", "resolve_objective_control"]
__all__ += ["resolve_unarrived_reserve_destruction"]
__all__ += ["resolved_secondary_mission_selection_for_card", "rules_unit_is_battle_shocked"]
__all__ += ["rules_unit_objective_proximity_witness"]
__all__ += ["rules_unit_started_mission_action_this_turn", "rules_unit_view_by_id"]
__all__ += ["saving_throw_roll_spec", "score_primary_objective_control_boundary"]
__all__ += ["secondary_mission_card_mode_from_token", "secondary_mission_card_status_from_token"]
__all__ += ["seed_completed_fight_phase", "seed_resolved_secondary_mission_selections", "sha256"]
__all__ += ["shapely_backend", "straight_line_witness_for_unit"]
__all__ += ["submit_action_and_movement_proposal"]
__all__ += ["synchronize_secondary_destruction_projection_payload"]
__all__ += ["tactical_secondary_achievement_context_from_award"]
__all__ += ["unit_destruction_completion_events_for_interval"]
__all__ += ["validate_primary_historical_event_integrity", "victory_point_source_kind_from_token"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack", "with_unit_keywords"]
