from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from math import comb
from typing import Any, cast

import pytest

from tests.fight_movement_event_helpers import (
    grouped_fight_movement_resolution_payload,
    standalone_fight_movement_event_evidence,
)
from tests.move_marker_fixture_helpers import resolve_surveil_markers_for_fixture
from tests.phase11c_command_phase_helpers import (
    battle_state,
    default_unit_selection,
    phase11c_config,
    with_model_offsets,
)
from tests.phase17n_primary_mission_helpers import append_authenticated_normal_move
from tests.phase17n_primary_mission_helpers import (
    phase17n_action_turn_end_record as shared_action_turn_end_record,
)
from tests.phase17n_primary_mission_helpers import (
    phase17n_started_primary_action_fixture as shared_started_primary_action_fixture,
)
from tests.sequential_translation_helpers import leading_first_translation_paths
from tests.setup_completion_helpers import record_completed_command_occurrences_for_fixture
from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.engine.actions import MissionActionState, MissionActionStatus
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_shock import BattleShockedUnitState
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelDisplacementRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_options import mission_action_for_state
from warhammer40k_core.engine.mission_action_policies import (
    mission_action_policy_for_id,
    primary_mission_choice_rule_for_id,
    primary_mission_state_rule_for_id,
)
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    request_mission_action_start,
)
from warhammer40k_core.engine.mission_scoring_policies import MissionScoringPolicies
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.mission_terrain import (
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.missions import (
    mission_scoring_policies_from_setup,
    primary_scoring_rules_from_definition,
)
from warhammer40k_core.engine.movement_proposals import ProposalKind
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlContribution,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.phases.command import CommandPhaseHandler
from warhammer40k_core.engine.phases.fight import FightPhaseHandler
from warhammer40k_core.engine.primary_battlefield_departure import (
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    ObjectiveMarkerModelWitness,
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    primary_unattributed_destruction_cause_from_token,
)
from warhammer40k_core.engine.primary_historical_events import (
    PRIMARY_TURN_START_EVIDENCE_RECORDED_EVENT,
    PRIMARY_UNIT_DESTRUCTION_RECORDED_EVENT,
    record_primary_battlefield_departure_event,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
)
from warhammer40k_core.engine.primary_mission_action_integrity import (
    validate_primary_mission_action_integrity,
)
from warhammer40k_core.engine.primary_mission_action_interruptions import (
    reconcile_primary_mission_action_interruptions,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_evidence import (
    PRIMARY_MISSION_ACTION_COMPLETION_EVIDENCE_KEY,
    PRIMARY_MISSION_ACTION_START_EVIDENCE_KEY,
    MissionActionPriorUseEvidence,
    MissionActionStartAuthorityOptionEvidence,
    PrimaryMissionActionCompletionEvidence,
    PrimaryMissionActionStartEvidence,
)
from warhammer40k_core.engine.primary_mission_action_lifecycle_policy import (
    validate_primary_mission_action_start_evidence,
    validate_primary_mission_action_use_limits,
)
from warhammer40k_core.engine.primary_mission_action_resolution import (
    resolve_primary_mission_actions_at_turn_end,
)
from warhammer40k_core.engine.primary_mission_choice_payloads import PrimaryMissionChoiceData
from warhammer40k_core.engine.primary_mission_choices import (
    PRIMARY_MISSION_CHOICE_RESOLVED_EVENT,
    PRIMARY_OPERATION_MARKER_KIND,
    SELECT_PRIMARY_MISSION_CHOICE_DECISION_TYPE,
    SENSOR_SWEEP_EXTRACT_ACTION_ID,
    SENSOR_SWEEP_LOCATE_ACTION_ID,
    apply_primary_mission_choice,
    consecrate_choice_request,
    invalid_primary_mission_choice_request_status,
    locate_and_deny_setup_choice_request,
    primary_mission_choice_option_id,
    punishment_choice_request,
    sensor_sweep_marker_removal_choice_request,
)
from warhammer40k_core.engine.primary_mission_decision_integrity import (
    validate_primary_mission_decision_integrity,
)
from warhammer40k_core.engine.primary_mission_marker_integrity import (
    validate_surveil_marker_removal_events,
)
from warhammer40k_core.engine.primary_mission_state import (
    MarkerAnchorKind,
    PrimaryConsecrationStatus,
    PrimaryMissionMarkerState,
    PrimaryMissionMarkerStatus,
    PrimaryMissionProgressState,
    primary_condemned_selection_id,
    primary_mission_marker_id,
)
from warhammer40k_core.engine.primary_mission_state_validation import (
    validate_primary_mission_progress_state,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_condition_evaluator import (
    PrimaryScoringConditionContext,
    evaluate_primary_scoring_condition,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
    cross_turn_destruction_comparison_evidence,
    home_objective_ids,
    opponent_home_control_evidence,
    primary_score_count_evidence,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_SPATIAL_CONDITIONS,
    PrimaryScoringSpatialEvidence,
    PrimaryTableQuarterUnitWitness,
    PrimaryTerritoryUnitWitness,
    objective_control_record_hash,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringStateEvidence,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    build_primary_rules_unit_turn_start_snapshot,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.primary_victory_point_policy import (
    validate_primary_victory_point_award,
    validate_primary_victory_point_transaction,
    validate_victory_point_ledger_policy,
)
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.reserves import ReserveKind, ReserveState
from warhammer40k_core.engine.runtime_modifiers import RuntimeModifierRegistry
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.starting_attached_units import StartingAttachedUnitRecord
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.unit_state import StartingStrengthRecord
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.table_quarters import TABLE_QUARTER_IDS
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
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
__all__ += ["VictoryPointTransaction", "append_authenticated_normal_move"]
__all__ += ["apply_primary_mission_choice", "battle_state"]
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
__all__ += ["pytest", "reconcile_primary_mission_action_interruptions"]
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
