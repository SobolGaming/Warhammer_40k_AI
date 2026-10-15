from __future__ import annotations

from copy import deepcopy
from dataclasses import replace
from json import loads as json_loads
from re import escape
from typing import cast

import pytest

from tests.phase11c_command_phase_helpers import (
    army_muster_request,
    complete_setup_through_gate,
    default_unit_selection,
    mustered_armies,
    ruleset,
    secondary_choice,
    with_model_offsets,
)
from tests.phase11c_command_phase_helpers import mission_setup as phase11c_mission_setup
from tests.phase17n_primary_mission_helpers import (
    append_authenticated_normal_move,
    phase17n_event_setup,
    phase17n_state_with_setup,
)
from tests.secondary_destruction_helpers import record_secondary_destruction_for_fixture
from tests.setup_completion_helpers import record_primary_turn_start_evidence_for_fixture
from tests.support.catalog_runtime_fixtures import SOURCE_KEYWORD_SEQUENCE_PARTS
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.descriptor_hash import canonical_payload_sha256
from warhammer40k_core.core.dice import DiceExpression, DiceRollResult, DiceRollSpec
from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.ruleset_descriptor import BattlePhaseKind, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
from warhammer40k_core.engine.catalog_any_phase_once_per_battle import (
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
)
from warhammer40k_core.engine.decision import DiceRollManager
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionOption,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.destruction_provenance import (
    DestructionSourceKind,
    ModelDestructionAttribution,
)
from warhammer40k_core.engine.event_log import (
    EventLog,
    EventRecord,
    JsonValue,
    canonical_json,
    validate_json_value,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState, SecondaryMissionMode
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.mission_decisions import request_mission_action_start
from warhammer40k_core.engine.mission_scoring_transaction import (
    _card_for_state_backed_scoring,  # pyright: ignore[reportPrivateUsage]
    _emit_objective_control_boundary_event_if_missing,  # pyright: ignore[reportPrivateUsage]
    _transaction_objective_control_record_id,  # pyright: ignore[reportPrivateUsage]
    _validate_secondary_primary_closure,  # pyright: ignore[reportPrivateUsage]
    score_secondary_mission_from_state,
)
from warhammer40k_core.engine.missions import mission_scoring_policies_from_setup
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.objective_control_record_authority import (
    ObjectiveControlRecordAuthority,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, GameLifecycleStage
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.primary_battlefield_departure import PrimaryBattlefieldDepartureState
from warhammer40k_core.engine.primary_destruction_evidence import (
    rules_unit_objective_proximity_witness,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
)
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
    PrimaryMissionObjectiveControlModifierSource,
)
from warhammer40k_core.engine.primary_mission_boundary_physical_authority import (
    primary_mission_model_placements_from_checkpoint,
)
from warhammer40k_core.engine.primary_position_membership import (
    build_primary_rules_unit_membership_from_model_placements,
)
from warhammer40k_core.engine.primary_scoring_boundary import (
    score_primary_objective_control_boundary,
)
from warhammer40k_core.engine.primary_scoring_boundary_lifecycle import (
    PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
    PrimaryScoringBoundaryLifecyclePayload,
    PrimaryScoringBoundaryStatus,
    mark_pending_primary_scoring_boundaries,
    pending_primary_scoring_boundary_keys,
    resolve_primary_scoring_boundary_lifecycle,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint import (
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    bound_primary_scoring_commit_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_commit_checkpoint_authority import (
    validate_primary_scoring_spatial_rows_from_checkpoint,
)
from warhammer40k_core.engine.primary_scoring_position_witness import (
    PrimaryScoringRulesUnitPositionWitnessPayload,
)
from warhammer40k_core.engine.primary_scoring_spatial_evidence import (
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    PrimaryTerritoryUnitWitness,
    build_primary_scoring_spatial_evidence,
)
from warhammer40k_core.engine.primary_scoring_state_evidence import (
    PrimaryScoringBoundaryKind,
    PrimaryScoringStateEvidence,
    PrimaryScoringStateEvidencePayload,
    build_primary_scoring_state_evidence,
    record_primary_scoring_state_evidence,
)
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_destroyed_model_departures,
)
from warhammer40k_core.engine.return_on_death import (
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    PendingReturnOnDeath,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    apply_return_on_death_placement_decision,
)
from warhammer40k_core.engine.rule_execution import (
    RuleExecutionContext,
    RuleExecutionStatus,
    default_rule_execution_registry,
    execute_rule_ir,
)
from warhammer40k_core.engine.runtime_modifiers import (
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    RuntimeModifierRegistry,
)
from warhammer40k_core.engine.runtime_rule_ir_authority import (
    RuntimeRuleIRAuthorityIndex,
    RuntimeRuleIRSourceKey,
)
from warhammer40k_core.engine.scoring import (
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    VictoryPointAward,
    VictoryPointCapBucket,
    VictoryPointSourceKind,
    VictoryPointTransaction,
)
from warhammer40k_core.engine.secondary_deployment_zone_evidence import (
    SCORING_COMMIT_CHECKPOINT_HASH_KEY,
    SCORING_COMMIT_CHECKPOINT_ID_KEY,
    bind_state_backed_secondary_scoring_commit,
    enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary,
    enemy_unit_ids_in_player_deployment_zone_from_battlefield,
    enemy_unit_ids_in_player_deployment_zone_from_model_placements,
    require_state_backed_secondary_scoring_commit,
)
from warhammer40k_core.engine.secondary_rule_ir_scoring_authority import (
    GENERIC_RULE_IR_EFFECT_INDEX_KEY,
    GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY,
    GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY,
    GENERIC_RULE_IR_HASH_KEY,
    GENERIC_RULE_IR_SOURCE_ID_KEY,
    RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
    apply_generic_rule_ir_victory_points,
    generic_rule_ir_secondary_award,
    next_generic_rule_ir_victory_point_event_id,
    require_generic_rule_ir_loaded_authority,
    validate_secondary_generic_rule_ir_restore_authority,
)
from warhammer40k_core.engine.secondary_scoring_conditions import SecondaryScoringConditionContext
from warhammer40k_core.engine.secondary_scoring_provider import (
    RegisteredPhase11FCapProbe,
    SecondaryScoringProviderKind,
    _validate_registered_phase11f_cap_probe,  # pyright: ignore[reportPrivateUsage]
    is_registered_phase11f_cap_probe,
    registered_phase11f_cap_probe,
    secondary_scoring_provider_kind_from_metadata,
    secondary_scoring_provider_kind_from_token,
    validate_generic_rule_ir_secondary_award,
    validate_legacy_phase11f_secondary_award,
)
from warhammer40k_core.engine.secondary_scoring_state_evidence import (
    SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
)
from warhammer40k_core.engine.secondary_scoring_transaction_integrity import (
    _expected_state_backed_secondary_award,  # pyright: ignore[reportPrivateUsage]
    _legacy_score_secondary_mission_award,  # pyright: ignore[reportPrivateUsage]
    _record_for_binding,  # pyright: ignore[reportPrivateUsage]
    _reject_duplicate_tactical_source,  # pyright: ignore[reportPrivateUsage]
    _uncapped_award_from_transaction,  # pyright: ignore[reportPrivateUsage]
    _validate_scored_tactical_card_bindings,  # pyright: ignore[reportPrivateUsage]
    validate_secondary_award_semantics,
    validate_secondary_transaction_semantics,
)
from warhammer40k_core.engine.secondary_victory_point_policy import (
    require_source_backed_secondary_cap_bucket,
    state_backed_secondary_binding_identity,
    state_backed_secondary_objective_control_record_id,
    validate_state_backed_secondary_award_binding,
    validate_state_backed_secondary_ledger_binding,
)
from warhammer40k_core.engine.sticky_objective_control import StickyObjectiveControlState
from warhammer40k_core.engine.turn_end_hooks import (
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.table_quarters import TABLE_QUARTER_NORTH_WEST
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.rule_compiler import compile_rule_source_text
from warhammer40k_core.rules.rule_ir import (
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleIR,
    RuleParameter,
)
from warhammer40k_core.rules.source_data import RuleSourceText

_OC_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
)


__all__: list[str] = []
__all__ += ["ArmyCatalog", "BattlePhase", "BattlePhaseKind", "DecisionController"]
__all__ += ["DecisionOption", "DecisionRequest", "DecisionResult", "DestructionSourceKind"]
__all__ += ["DiceExpression", "DiceRollManager", "DiceRollResult", "DiceRollSpec", "EventLog"]
__all__ += ["GENERIC_RULE_IR_EFFECT_INDEX_KEY", "EventRecord"]
__all__ += ["GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY", "GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY"]
__all__ += ["GENERIC_RULE_IR_HASH_KEY", "GENERIC_RULE_IR_SOURCE_ID_KEY", "GameConfig"]
__all__ += ["GameLifecycle", "GameLifecycleError", "GameLifecyclePayload", "GameLifecycleStage"]
__all__ += ["GameState", "JsonValue", "ModelDestructionAttribution", "ModelPlacement"]
__all__ += ["ModifierOperation", "ModifierTerm", "ObjectiveControlModifierBinding"]
__all__ += ["ObjectiveControlModifierContext", "ObjectiveControlRecord"]
__all__ += ["ObjectiveControlRecordAuthority", "ObjectiveControlTiming", "ObjectiveMarkerRole"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "ObjectiveRuleScope"]
__all__ += ["PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT"]
__all__ += ["PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED"]
__all__ += ["PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH", "PendingReturnOnDeath", "Pose"]
__all__ += ["PrimaryBattlefieldDepartureState", "PrimaryMissionBoundaryCheckpoint"]
__all__ += ["PrimaryMissionBoundaryModelState", "PrimaryMissionObjectiveControlModifierSource"]
__all__ += ["PrimaryScoringBoundaryKind", "PrimaryScoringBoundaryLifecyclePayload"]
__all__ += ["PrimaryScoringBoundaryStatus", "PrimaryScoringRulesUnitPositionWitnessPayload"]
__all__ += ["PrimaryScoringStateEvidence", "PrimaryScoringStateEvidencePayload"]
__all__ += ["RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE", "PrimaryTerritoryUnitWitness"]
__all__ += ["RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE", "RegisteredPhase11FCapProbe"]
__all__ += ["ReturnDestroyedTargetScope", "ReturnRestoreWoundsMode", "RuleClause"]
__all__ += ["RuleEffectKind", "RuleEffectSpec", "RuleExecutionContext", "RuleExecutionStatus"]
__all__ += ["RuleIR", "RuleParameter", "RuleSourceText", "RulesetDescriptor"]
__all__ += ["RuntimeModifierRegistry", "RuntimeRuleIRAuthorityIndex", "RuntimeRuleIRSourceKey"]
__all__ += ["SCORING_COMMIT_CHECKPOINT_HASH_KEY", "SCORING_COMMIT_CHECKPOINT_ID_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY"]
__all__ += ["SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY"]
__all__ += ["SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE"]
__all__ += ["SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE", "SOURCE_KEYWORD_SEQUENCE_PARTS"]
__all__ += ["SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE", "SecondaryMissionCardMode"]
__all__ += ["SecondaryMissionCardState", "SecondaryMissionCardStatus", "SecondaryMissionMode"]
__all__ += ["SecondaryScoringConditionContext", "SecondaryScoringProviderKind"]
__all__ += ["TABLE_QUARTER_NORTH_WEST", "StickyObjectiveControlState", "UnitInstance"]
__all__ += ["UnitPlacement", "VictoryPointAward", "VictoryPointCapBucket"]
__all__ += ["_OC_SOURCE_RULE_ID", "VictoryPointSourceKind", "VictoryPointTransaction"]
__all__ += ["_card_for_state_backed_scoring", "_emit_objective_control_boundary_event_if_missing"]
__all__ += ["_expected_state_backed_secondary_award", "_legacy_score_secondary_mission_award"]
__all__ += ["_record_for_binding", "_reject_duplicate_tactical_source"]
__all__ += ["_transaction_objective_control_record_id", "_uncapped_award_from_transaction"]
__all__ += ["_validate_registered_phase11f_cap_probe", "_validate_scored_tactical_card_bindings"]
__all__ += ["_validate_secondary_primary_closure", "append_authenticated_normal_move"]
__all__ += ["apply_generic_rule_ir_victory_points", "apply_return_on_death_placement_decision"]
__all__ += ["army_muster_request", "bind_state_backed_secondary_scoring_commit"]
__all__ += ["bound_primary_scoring_commit_checkpoint"]
__all__ += ["build_primary_rules_unit_membership_from_model_placements"]
__all__ += ["build_primary_scoring_spatial_evidence", "build_primary_scoring_state_evidence"]
__all__ += ["canonical_json", "canonical_payload_sha256", "cast", "compile_rule_source_text"]
__all__ += ["complete_setup_through_gate", "create_deterministic_battlefield_scenario"]
__all__ += ["deepcopy", "default_rule_execution_registry", "default_unit_selection"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_battlefield"]
__all__ += ["enemy_unit_ids_in_player_deployment_zone_from_model_placements", "escape"]
__all__ += ["execute_rule_ir", "generic_rule_ir_secondary_award"]
__all__ += ["is_registered_phase11f_cap_probe", "json_loads"]
__all__ += ["mark_pending_primary_scoring_boundaries", "mission_scoring_policies_from_setup"]
__all__ += ["mustered_armies", "next_generic_rule_ir_victory_point_event_id"]
__all__ += ["pending_primary_scoring_boundary_keys", "phase11c_mission_setup"]
__all__ += ["phase17n_event_setup", "phase17n_state_with_setup"]
__all__ += ["primary_mission_model_placements_from_checkpoint", "pytest"]
__all__ += ["record_new_primary_unit_destruction_events"]
__all__ += ["record_primary_battlefield_departure_event"]
__all__ += ["record_primary_destroyed_model_departures", "record_primary_scoring_state_evidence"]
__all__ += ["record_primary_turn_start_evidence_for_fixture"]
__all__ += ["record_secondary_destruction_for_fixture", "registered_phase11f_cap_probe"]
__all__ += ["replace", "request_mission_action_start", "require_generic_rule_ir_loaded_authority"]
__all__ += ["require_source_backed_secondary_cap_bucket"]
__all__ += ["require_state_backed_secondary_scoring_commit"]
__all__ += ["resolve_primary_scoring_boundary_lifecycle"]
__all__ += ["rules_unit_objective_proximity_witness", "ruleset"]
__all__ += ["score_primary_objective_control_boundary", "score_secondary_mission_from_state"]
__all__ += ["secondary_choice", "secondary_scoring_provider_kind_from_metadata"]
__all__ += ["secondary_scoring_provider_kind_from_token"]
__all__ += ["state_backed_secondary_binding_identity"]
__all__ += ["state_backed_secondary_objective_control_record_id"]
__all__ += ["validate_generic_rule_ir_secondary_award", "validate_json_value"]
__all__ += ["validate_legacy_phase11f_secondary_award"]
__all__ += ["validate_primary_scoring_spatial_rows_from_checkpoint"]
__all__ += ["validate_secondary_award_semantics"]
__all__ += ["validate_secondary_generic_rule_ir_restore_authority"]
__all__ += ["validate_secondary_transaction_semantics"]
__all__ += ["validate_state_backed_secondary_award_binding"]
__all__ += ["validate_state_backed_secondary_ledger_binding", "with_model_offsets"]
__all__ += ["with_unit_keywords"]
