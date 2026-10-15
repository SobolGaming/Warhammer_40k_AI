from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from typing import cast

import pytest

from tests.completed_attack_fixture_helpers import record_shooting_declaration_for_executor_fixture
from tests.fight_end_fixture_helpers import advance_completed_phase_fixture
from tests.movement_submission_helpers import (
    straight_line_witness_for_unit,
    submit_action_and_movement_proposal,
)
from tests.phase13b_shooting_declaration_helpers import (
    _attack_pool_for_test,
    _first_weapon_profile,
    _fixed_roll_result,
)
from tests.phase17n_primary_mission_helpers import append_authenticated_normal_move
from tests.phase17n_secondary_mission_helpers import (
    drain_pending_secondary_mission_setup,
    resolved_secondary_mission_selection_for_card,
    seed_resolved_secondary_mission_selections,
)
from tests.phase17n_step6g_secondary_certification_helpers import seed_completed_fight_phase
from tests.secondary_destruction_helpers import (
    record_secondary_destruction_for_fixture,
    synchronize_secondary_destruction_projection_payload,
)
from tests.setup_completion_helpers import enter_battle_for_fixture
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.adapters.access_control import AuthenticatedPrincipal, PrincipalRole
from warhammer40k_core.adapters.contracts import FiniteOptionSubmission
from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.deployment_zones import (
    DeploymentZoneCircleCutout,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
)
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerDefinition, ObjectiveMarkerRole
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import DamageProfile
from warhammer40k_core.engine import (
    primary_destruction_timeline_integrity as destruction_timeline_integrity,
)
from warhammer40k_core.engine import (
    primary_historical_event_integrity as historical_event_integrity,
)
from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatus,
    interrupt_mission_action_for_battlefield_departure,
    interrupt_mission_action_for_displacement,
    mission_action_interruption_reason_for_displacement,
    mission_action_status_from_token,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.attack_sequence import (
    AttackSequence,
    resolve_attack_sequence_until_blocked,
)
from warhammer40k_core.engine.attack_sequence_model import (
    attack_sequence_hit_roll_spec,
    attack_sequence_wound_roll_spec,
)
from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.battle_shock import (
    BattleShockResult,
    BattleShockTestReason,
    BattleShockTestRequest,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRemovalKind,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelDisplacementKind,
    ModelPlacement,
    ModelRemovalRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.command_points import CommandPointGainStatus, CommandPointSourceKind
from warhammer40k_core.engine.damage_allocation import destroy_model_by_rule
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_record import DecisionRecord
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import EventLog, EventRecord, JsonValue
from warhammer40k_core.engine.game_state import (
    GameConfig,
    GameState,
    GameStatePayload,
    SecondaryMissionChoice,
    SecondaryMissionMode,
    TacticalSecondaryDraw,
)
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_unit_ineligibility_reason,
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.mission_decisions import (
    DECLINE_MISSION_ACTION_START_OPTION_ID,
    START_MISSION_ACTION_DECISION_TYPE,
    TACTICAL_SECONDARY_DISCARD_DECISION_TYPE,
    TACTICAL_SECONDARY_SCORE_DECISION_TYPE,
    request_mission_action_start,
    request_tactical_secondary_discard,
    request_tactical_secondary_score,
)
from warhammer40k_core.engine.mission_setup import MissionSetup, PlayerPrimaryMissionAssignment
from warhammer40k_core.engine.mission_terrain import (
    MissionLogicalTerrainArea,
    logical_terrain_area_within_player_deployment_zone,
    logical_terrain_area_within_player_territory,
    mission_logical_terrain_areas,
)
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    reserve_destruction_policy_from_scoring_policy,
)
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlRecord,
    ObjectiveControlResult,
    ObjectiveControlScore,
    ObjectiveControlStatus,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
    LifecycleStatusKind,
    PlaceholderPhaseHandler,
)
from warhammer40k_core.engine.phases.command import (
    TACTICAL_SECONDARY_DRAW_DECISION_TYPE,
    TACTICAL_SECONDARY_REPLACEMENT_DECISION_TYPE,
)
from warhammer40k_core.engine.phases.movement import (
    SELECT_MOVEMENT_ACTION_DECISION_TYPE,
    SELECT_MOVEMENT_UNIT_DECISION_TYPE,
    AdvancedUnitState,
    AdvanceRollRequest,
    AdvanceRollResult,
    FellBackUnitState,
    MovementDiceRecord,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.phases.shooting import (
    SELECT_SHOOTING_UNIT_DECISION_TYPE,
    ShootingPhaseHandler,
    ShootingPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_battlefield_departure import (
    PrimaryBattlefieldDepartureState,
    primary_battlefield_departure_id,
    record_primary_battlefield_departure,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
    RulesUnitObjectiveProximityWitness,
    destruction_source_objective_proximity_witness,
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_event_integrity import (
    validate_primary_historical_event_integrity,
)
from warhammer40k_core.engine.primary_historical_events import (
    primary_reserve_entry_source_terminal_bindings_payload,
    record_new_primary_battlefield_departure_events,
    record_new_primary_turn_start_evidence_events,
    record_primary_battlefield_departure_event,
    record_primary_reserve_entry_mutation_event,
    record_primary_reserve_entry_provider_terminal_event,
    record_primary_turn_start_evidence_event,
    record_primary_unit_destruction_event,
    reserve_entry_evidence_payload,
)
from warhammer40k_core.engine.primary_reserve_entry_provider import (
    PrimaryReserveEntryProvider,
    PrimaryReserveEntryProviderKind,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_conditions import (
    PrimaryUnitDestructionEvidence,
    cross_turn_destruction_comparison_evidence,
    opponent_home_control_evidence,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    build_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_turn_start_evidence import (
    PrimaryRulesUnitTurnStartSnapshot,
    record_primary_turn_start_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    primary_unit_destruction_id,
    record_primary_destroyed_model_departures,
    record_primary_unit_destructions_for_destroyed_models,
)
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveOrigin,
    ReserveState,
    ReserveStatus,
    resolve_unarrived_reserve_destruction,
)
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    apply_return_on_death_placement_decision,
    build_return_on_death_placement_request,
)
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked, rules_unit_view_by_id
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.saves import SaveKind, saving_throw_roll_spec
from warhammer40k_core.engine.scoring import (
    MissionScoringPolicy,
    PrimaryMissionScoringRule,
    PrimaryObjectiveTurnStartState,
    PrimaryObjectiveTurnStartStatePayload,
    PrimaryTerrainTrapState,
    PrimaryUnitDestructionState,
    PrimaryUnitDestructionStatePayload,
    SecondaryDestroyedModelState,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionScoringRule,
    SecondaryObjectiveCleanseState,
    SecondaryTerrainPlunderState,
    SecondaryUnitDestructionState,
    TacticalSecondaryAchievementContext,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    objective_control_timing_from_token,
    secondary_mission_card_mode_from_token,
    secondary_mission_card_status_from_token,
    victory_point_source_kind_from_token,
)
from warhammer40k_core.engine.secondary_tactical_achievement import (
    expected_tactical_secondary_award_from_state,
    tactical_secondary_achievement_context_from_award,
)
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.engine.shooting_types import ShootingType
from warhammer40k_core.engine.stratagems import (
    DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    STRATAGEM_DECISION_TYPE,
)
from warhammer40k_core.engine.transports import TransportCapacityProfile, TransportCargoState
from warhammer40k_core.engine.turn_cleanup import (
    CoherencyCleanupRemoval,
    EndTurnCleanupState,
    battlefield_removal_kind_from_token,
    resolve_end_turn_cleanup,
)
from warhammer40k_core.engine.unit_destroyed_hooks import (
    ATTACHED_UNIT_DESTRUCTION_SOURCE_RULE_ID,
    ATTACHED_UNIT_DESTRUCTION_SOURCE_SHA256,
    unit_destruction_completion_events_for_interval,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection
from warhammer40k_core.engine.weapon_abilities import FIRE_OVERWATCH_RULE_ID, SNAP_SHOOTING_RULE_ID
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.interfaces.cli import render_pending_decision_for_cli
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)

SEEDED_TACTICAL_DRAW_REQUEST_ID = "phase11e-seeded-tactical-draw-request"


SEEDED_TACTICAL_DRAW_RESULT_ID = "phase11e-seeded-tactical-draw"


SCORING_TERRAIN_FEATURE_ID = "phase11e-scoring-terrain"


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
__all__ += ["_attack_pool_for_test", "_first_weapon_profile", "_fixed_roll_result"]
__all__ += ["advance_completed_phase_fixture", "append_authenticated_normal_move"]
__all__ += ["apply_return_on_death_placement_decision", "attack_sequence_hit_roll_spec"]
__all__ += ["attack_sequence_wound_roll_spec", "battlefield_removal_kind_from_token"]
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
