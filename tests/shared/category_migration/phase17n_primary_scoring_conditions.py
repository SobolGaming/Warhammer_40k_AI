from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_conditions_bindings import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY,
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    PRIMARY_OPERATION_MARKER_KIND,
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    SENSOR_SWEEP_EXTRACT_ACTION_ID,
    SENSOR_SWEEP_LOCATE_ACTION_ID,
    TABLE_QUARTER_IDS,
    Any,
    AttachedUnitFormation,
    BattlefieldRegionKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    BattlePhase,
    BattleRoundFlow,
    BattleShockedUnitState,
    CommandPhaseHandler,
    DecisionController,
    DecisionRequest,
    DecisionResult,
    DestructionSourceKind,
    EventLog,
    FightPhaseHandler,
    GameLifecycle,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    JsonValue,
    MarkerAnchorKind,
    MissionActionPriorUseEvidence,
    MissionActionStartAuthorityOptionEvidence,
    MissionActionState,
    MissionActionStatus,
    MissionScoringPolicies,
    MissionScoringPolicy,
    MissionSetup,
    ModelDestructionAttribution,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    ObjectiveControlContext,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    ObjectiveMarkerModelWitness,
    ObjectiveMarkerRole,
    PathWitness,
    Pose,
    PrimaryConsecrationStatus,
    PrimaryMissionActionCompletionEvidence,
    PrimaryMissionActionStartEvidence,
    PrimaryMissionChoiceData,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryRulesUnitTurnStartSnapshot,
    PrimaryScoringConditionContext,
    PrimaryScoringSpatialEvidence,
    PrimaryScoringStateEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerrainTrapState,
    PrimaryTerritoryUnitWitness,
    PrimaryUnattributedDestructionCause,
    PrimaryUnitDestructionEvidence,
    PrimaryUnitDestructionState,
    ProposalKind,
    ReactionWindow,
    ReactionWindowKind,
    ReserveKind,
    ReserveState,
    RulesUnitObjectiveProximityWitness,
    RuntimeModifierRegistry,
    StartingAttachedUnitRecord,
    StartingStrengthRecord,
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
    UnitPlacement,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    append_authenticated_normal_move,
    apply_primary_mission_choice,
    battle_state,
    build_primary_rules_unit_turn_start_snapshot,
    build_primary_scoring_state_evidence,
    canonical_json,
    cast,
    comb,
    consecrate_choice_request,
    cross_turn_destruction_comparison_evidence,
    deepcopy,
    default_unit_selection,
    destroy_model_by_rule,
    evaluate_primary_scoring_condition,
    grouped_fight_movement_resolution_payload,
    home_objective_ids,
    invalid_primary_mission_choice_request_status,
    leading_first_translation_paths,
    locate_and_deny_setup_choice_request,
    logical_terrain_area_within_player_territory,
    mission_action_for_state,
    mission_action_policy_for_id,
    mission_logical_terrain_areas,
    mission_scoring_policies_from_setup,
    objective_control_record_hash,
    opponent_home_control_evidence,
    phase11c_config,
    primary_condemned_selection_id,
    primary_mission_choice_option_id,
    primary_mission_choice_rule_for_id,
    primary_mission_marker_id,
    primary_mission_state_rule_for_id,
    primary_score_count_evidence,
    primary_scoring_rules_from_definition,
    primary_unattributed_destruction_cause_from_token,
    punishment_choice_request,
    pytest,
    reconcile_primary_mission_action_interruptions,
    record_completed_command_occurrences_for_fixture,
    record_primary_battlefield_departure,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    record_primary_scoring_state_evidence,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
    replace,
    request_mission_action_start,
    resolve_objective_control,
    resolve_primary_mission_actions_at_turn_end,
    resolve_surveil_markers_for_fixture,
    score_primary_objective_control_boundary,
    sensor_sweep_marker_removal_choice_request,
    shared_action_turn_end_record,
    shared_started_primary_action_fixture,
    standalone_fight_movement_event_evidence,
    validate_json_value,
    validate_primary_mission_action_integrity,
    validate_primary_mission_action_start_evidence,
    validate_primary_mission_action_use_limits,
    validate_primary_mission_decision_integrity,
    validate_primary_mission_progress_state,
    validate_primary_victory_point_award,
    validate_primary_victory_point_transaction,
    validate_surveil_marker_removal_events,
    validate_victory_point_ledger_policy,
    warhammer_event_companion_2026_07_mission_pack,
    with_model_offsets,
)
from tests.shared.category_migration.phase17n_primary_scoring_conditions_common_fixtures import (
    _phase17n_attach_test_leader,
    _phase17n_clear_turn_start_contributors,
    _phase17n_enter_battle_turn_end,
    _phase17n_event_setup,
    _phase17n_move_attached_components_away,
    _phase17n_refresh_turn_start_snapshot,
    _phase17n_set_model_wounds,
    _phase17n_submit_primary_mission_choice,
    battlefield_dominance_setup,
    purge_and_secure_setup,
)
from tests.shared.category_migration.phase17n_primary_scoring_conditions_scoring_evidence import (
    _control_record,
    _controlled_result,
    _primary_historical_evidence_fixture,
    _primary_scoring_state_evidence,
    _primary_scoring_unit_placement_at_anchor,
    _primary_transaction_from_award,
    _primary_vp_policy_fixture,
    _run_invalid_primary_scoring_operation,
    _run_primary_scoring_context_corruption,
    _spatial_evidence,
    _territory_objective_ids,
)
from tests.shared.category_migration.primary_conditions_decision_action_builders import (
    _phase17n_action_turn_end_record,
    _phase17n_completed_sensor_action,
    _phase17n_consecrate_choice_state,
    _phase17n_forged_completion_marker,
    _phase17n_locate_choice_state,
    _phase17n_punishment_attached_choice_state,
    _phase17n_punishment_choice_state,
    _phase17n_resolved_consecrate_choice_fixture,
    _phase17n_resolved_sensor_choice_fixture,
    _phase17n_sensor_start_integrity_fixture,
    _phase17n_started_primary_action_fixture,
    _phase17n_surveil_action_start_evidence_fixture,
    _phase17n_surveil_integrity_fixture,
    _phase17n_surveil_move_marker_state,
    _phase17n_use_limit_action,
)

__all__: list[str] = []
__all__ += ["Any", "AttachedUnitFormation", "BattlePhase", "BattleRoundFlow"]
__all__ += ["BattleShockedUnitState", "BattlefieldRegionKind", "BattlefieldRemovalKind"]
__all__ += ["BattlefieldRuntimeState", "BattlefieldTransitionBatch", "CommandPhaseHandler"]
__all__ += ["DECLINE_MISSION_ACTION_START_OPTION_ID", "DECLINE_TRIGGERED_MOVEMENT_OPTION_ID"]
__all__ += ["DecisionController", "DecisionRequest", "DecisionResult", "DestructionSourceKind"]
__all__ += ["EventLog", "FightPhaseHandler", "GameLifecycle", "GameLifecycleError"]
__all__ += ["GameLifecycleStage", "GameState", "JsonValue", "MarkerAnchorKind"]
__all__ += ["MissionActionPriorUseEvidence", "MissionActionStartAuthorityOptionEvidence"]
__all__ += ["MissionActionState", "MissionActionStatus", "MissionScoringPolicies"]
__all__ += ["MissionScoringPolicy", "MissionSetup", "ModelDestructionAttribution"]
__all__ += ["ModelDisplacementKind", "ModelDisplacementRecord", "ObjectiveControlContext"]
__all__ += ["ObjectiveControlContribution", "ObjectiveControlRecord", "ObjectiveControlResult"]
__all__ += ["ObjectiveControlScore", "ObjectiveControlStatus", "ObjectiveControlTiming"]
__all__ += ["ObjectiveMarkerModelWitness", "ObjectiveMarkerRole"]
__all__ += ["PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY"]
__all__ += ["PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY", "PRIMARY_MISSION_CHOICE_RESOLVED_EVENT"]
__all__ += ["PRIMARY_OPERATION_MARKER_KIND", "PRIMARY_SCORING_SPATIAL_CONDITIONS"]
__all__ += ["PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT"]
__all__ += ["PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT", "PathWitness", "Pose"]
__all__ += ["PrimaryConsecrationStatus", "PrimaryMissionActionCompletionEvidence"]
__all__ += ["PrimaryMissionActionStartEvidence", "PrimaryMissionChoiceData"]
__all__ += ["PrimaryMissionMarkerState", "PrimaryMissionMarkerStatus"]
__all__ += ["PrimaryMissionProgressState", "PrimaryMissionScoringRule"]
__all__ += ["PrimaryObjectiveTurnStartState", "PrimaryRulesUnitTurnStartSnapshot"]
__all__ += ["PrimaryScoringConditionContext", "PrimaryScoringSpatialEvidence"]
__all__ += ["PrimaryScoringStateEvidence", "PrimaryTableQuarterUnitWitness"]
__all__ += ["PrimaryTerrainTrapState", "PrimaryTerritoryUnitWitness"]
__all__ += ["PrimaryUnattributedDestructionCause", "PrimaryUnitDestructionEvidence"]
__all__ += ["PrimaryUnitDestructionState", "ProposalKind", "ReactionWindow", "ReactionWindowKind"]
__all__ += ["ReserveKind", "ReserveState", "RulesUnitObjectiveProximityWitness"]
__all__ += ["SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE", "RuntimeModifierRegistry"]
__all__ += ["SENSOR_SWEEP_EXTRACT_ACTION_ID", "SENSOR_SWEEP_LOCATE_ACTION_ID"]
__all__ += ["TABLE_QUARTER_IDS", "StartingAttachedUnitRecord", "StartingStrengthRecord"]
__all__ += ["TriggeredMovementDescriptor", "TriggeredMovementHandler", "TriggeredMovementKind"]
__all__ += ["UnitPlacement", "VictoryPointAward", "VictoryPointLedger", "VictoryPointSourceKind"]
__all__ += ["VictoryPointTransaction", "_control_record", "_controlled_result"]
__all__ += ["_phase17n_action_turn_end_record", "_phase17n_attach_test_leader"]
__all__ += ["_phase17n_clear_turn_start_contributors", "_phase17n_completed_sensor_action"]
__all__ += ["_phase17n_consecrate_choice_state", "_phase17n_enter_battle_turn_end"]
__all__ += ["_phase17n_event_setup", "_phase17n_forged_completion_marker"]
__all__ += ["_phase17n_locate_choice_state", "_phase17n_move_attached_components_away"]
__all__ += ["_phase17n_punishment_attached_choice_state", "_phase17n_punishment_choice_state"]
__all__ += ["_phase17n_refresh_turn_start_snapshot"]
__all__ += ["_phase17n_resolved_consecrate_choice_fixture"]
__all__ += ["_phase17n_resolved_sensor_choice_fixture"]
__all__ += ["_phase17n_sensor_start_integrity_fixture", "_phase17n_set_model_wounds"]
__all__ += ["_phase17n_started_primary_action_fixture", "_phase17n_submit_primary_mission_choice"]
__all__ += ["_phase17n_surveil_action_start_evidence_fixture"]
__all__ += ["_phase17n_surveil_integrity_fixture", "_phase17n_surveil_move_marker_state"]
__all__ += ["_phase17n_use_limit_action", "_primary_historical_evidence_fixture"]
__all__ += ["_primary_scoring_state_evidence", "_primary_scoring_unit_placement_at_anchor"]
__all__ += ["_primary_transaction_from_award", "_primary_vp_policy_fixture"]
__all__ += ["_run_invalid_primary_scoring_operation", "_run_primary_scoring_context_corruption"]
__all__ += ["_spatial_evidence", "_territory_objective_ids", "append_authenticated_normal_move"]
__all__ += ["apply_primary_mission_choice", "battle_state", "battlefield_dominance_setup"]
__all__ += ["build_primary_rules_unit_turn_start_snapshot"]
__all__ += ["build_primary_scoring_state_evidence", "canonical_json", "cast", "comb"]
__all__ += ["consecrate_choice_request", "cross_turn_destruction_comparison_evidence", "deepcopy"]
__all__ += ["default_unit_selection", "destroy_model_by_rule"]
__all__ += ["evaluate_primary_scoring_condition", "grouped_fight_movement_resolution_payload"]
__all__ += ["home_objective_ids", "invalid_primary_mission_choice_request_status"]
__all__ += ["leading_first_translation_paths", "locate_and_deny_setup_choice_request"]
__all__ += ["logical_terrain_area_within_player_territory", "mission_action_for_state"]
__all__ += ["mission_action_policy_for_id", "mission_logical_terrain_areas"]
__all__ += ["mission_scoring_policies_from_setup", "objective_control_record_hash"]
__all__ += ["opponent_home_control_evidence", "phase11c_config", "primary_condemned_selection_id"]
__all__ += ["primary_mission_choice_option_id", "primary_mission_choice_rule_for_id"]
__all__ += ["primary_mission_marker_id", "primary_mission_state_rule_for_id"]
__all__ += ["primary_score_count_evidence", "primary_scoring_rules_from_definition"]
__all__ += ["primary_unattributed_destruction_cause_from_token", "punishment_choice_request"]
__all__ += ["purge_and_secure_setup", "pytest", "reconcile_primary_mission_action_interruptions"]
__all__ += ["record_completed_command_occurrences_for_fixture"]
__all__ += ["record_primary_battlefield_departure", "record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "record_primary_scoring_state_evidence"]
__all__ += ["record_primary_turn_start_evidence_event", "record_primary_unit_destruction_event"]
__all__ += ["replace", "request_mission_action_start", "resolve_objective_control"]
__all__ += ["resolve_primary_mission_actions_at_turn_end", "resolve_surveil_markers_for_fixture"]
__all__ += ["score_primary_objective_control_boundary"]
__all__ += ["sensor_sweep_marker_removal_choice_request", "shared_action_turn_end_record"]
__all__ += ["shared_started_primary_action_fixture", "standalone_fight_movement_event_evidence"]
__all__ += ["validate_json_value", "validate_primary_mission_action_integrity"]
__all__ += ["validate_primary_mission_action_start_evidence"]
__all__ += ["validate_primary_mission_action_use_limits"]
__all__ += ["validate_primary_mission_decision_integrity"]
__all__ += ["validate_primary_mission_progress_state", "validate_primary_victory_point_award"]
__all__ += ["validate_primary_victory_point_transaction"]
__all__ += ["validate_surveil_marker_removal_events", "validate_victory_point_ledger_policy"]
__all__ += ["warhammer_event_companion_2026_07_mission_pack", "with_model_offsets"]
