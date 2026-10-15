from __future__ import annotations

from tests.shared.category_migration.phase17n_primary_scoring_boundary_lifecycle_bindings import (
    _OC_SOURCE_RULE_ID,
    GENERIC_RULE_IR_EFFECT_INDEX_KEY,
    GENERIC_RULE_IR_EXECUTION_CONTEXT_KEY,
    GENERIC_RULE_IR_EXECUTION_EVENT_ID_KEY,
    GENERIC_RULE_IR_HASH_KEY,
    GENERIC_RULE_IR_SOURCE_ID_KEY,
    PARAMETERIZED_DECISION_OPTION_ID,
    PRIMARY_MISSION_BOUNDARY_CHECKPOINT_EVENT,
    PRIMARY_SCORING_COMMIT_CHECKPOINT_EVENT,
    PRIMARY_SCORING_NO_ENEMY_IN_OWN_TERRITORY_CONDITION,
    PRIMARY_SCORING_PENDING_WINDOW_PHASE_END_UNIT_DESTROYED,
    PRIMARY_SCORING_PENDING_WINDOW_RETURN_ON_DEATH,
    RETURN_ON_DEATH_PENDING_CREATED_EVENT_TYPE,
    RULE_EXECUTION_VICTORY_POINTS_AWARDED_EVENT_TYPE,
    SCORING_COMMIT_CHECKPOINT_HASH_KEY,
    SCORING_COMMIT_CHECKPOINT_ID_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_HASH_KEY,
    SECONDARY_SCORING_STATE_EVIDENCE_ID_KEY,
    SELECT_CATALOG_ANY_PHASE_ONCE_PER_BATTLE_DECISION_TYPE,
    SELECT_FACTION_RULE_TURN_END_OPTION_DECISION_TYPE,
    SOURCE_KEYWORD_SEQUENCE_PARTS,
    SUBMIT_RETURN_ON_DEATH_PLACEMENT_DECISION_TYPE,
    TABLE_QUARTER_NORTH_WEST,
    ArmyCatalog,
    BattlePhase,
    BattlePhaseKind,
    DecisionController,
    DecisionOption,
    DecisionRequest,
    DecisionResult,
    DestructionSourceKind,
    DiceExpression,
    DiceRollManager,
    DiceRollResult,
    DiceRollSpec,
    EventLog,
    EventRecord,
    GameConfig,
    GameLifecycle,
    GameLifecycleError,
    GameLifecyclePayload,
    GameLifecycleStage,
    GameState,
    JsonValue,
    ModelDestructionAttribution,
    ModelPlacement,
    ModifierOperation,
    ModifierTerm,
    ObjectiveControlModifierBinding,
    ObjectiveControlModifierContext,
    ObjectiveControlRecord,
    ObjectiveControlRecordAuthority,
    ObjectiveControlTiming,
    ObjectiveMarkerRole,
    ObjectiveRuleScope,
    PendingReturnOnDeath,
    Pose,
    PrimaryBattlefieldDepartureState,
    PrimaryMissionBoundaryCheckpoint,
    PrimaryMissionBoundaryModelState,
    PrimaryMissionObjectiveControlModifierSource,
    PrimaryScoringBoundaryKind,
    PrimaryScoringBoundaryLifecyclePayload,
    PrimaryScoringBoundaryStatus,
    PrimaryScoringRulesUnitPositionWitnessPayload,
    PrimaryScoringStateEvidence,
    PrimaryScoringStateEvidencePayload,
    PrimaryTerritoryUnitWitness,
    RegisteredPhase11FCapProbe,
    ReturnDestroyedTargetScope,
    ReturnRestoreWoundsMode,
    RuleClause,
    RuleEffectKind,
    RuleEffectSpec,
    RuleExecutionContext,
    RuleExecutionStatus,
    RuleIR,
    RuleParameter,
    RulesetDescriptor,
    RuleSourceText,
    RuntimeModifierRegistry,
    RuntimeRuleIRAuthorityIndex,
    RuntimeRuleIRSourceKey,
    SecondaryMissionCardMode,
    SecondaryMissionCardState,
    SecondaryMissionCardStatus,
    SecondaryMissionMode,
    SecondaryScoringConditionContext,
    SecondaryScoringProviderKind,
    StickyObjectiveControlState,
    UnitInstance,
    UnitPlacement,
    VictoryPointAward,
    VictoryPointCapBucket,
    VictoryPointSourceKind,
    VictoryPointTransaction,
    _card_for_state_backed_scoring,  # pyright: ignore[reportPrivateUsage]
    _emit_objective_control_boundary_event_if_missing,  # pyright: ignore[reportPrivateUsage]
    _expected_state_backed_secondary_award,  # pyright: ignore[reportPrivateUsage]
    _legacy_score_secondary_mission_award,  # pyright: ignore[reportPrivateUsage]
    _record_for_binding,  # pyright: ignore[reportPrivateUsage]
    _reject_duplicate_tactical_source,  # pyright: ignore[reportPrivateUsage]
    _transaction_objective_control_record_id,  # pyright: ignore[reportPrivateUsage]
    _uncapped_award_from_transaction,  # pyright: ignore[reportPrivateUsage]
    _validate_registered_phase11f_cap_probe,  # pyright: ignore[reportPrivateUsage]
    _validate_scored_tactical_card_bindings,  # pyright: ignore[reportPrivateUsage]
    _validate_secondary_primary_closure,  # pyright: ignore[reportPrivateUsage]
    append_authenticated_normal_move,
    apply_generic_rule_ir_victory_points,
    apply_return_on_death_placement_decision,
    army_muster_request,
    bind_state_backed_secondary_scoring_commit,
    bound_primary_scoring_commit_checkpoint,
    build_primary_rules_unit_membership_from_model_placements,
    build_primary_scoring_spatial_evidence,
    build_primary_scoring_state_evidence,
    canonical_json,
    canonical_payload_sha256,
    cast,
    compile_rule_source_text,
    complete_setup_through_gate,
    create_deterministic_battlefield_scenario,
    deepcopy,
    default_rule_execution_registry,
    default_unit_selection,
    enemy_unit_ids_in_player_deployment_zone_for_secondary_boundary,
    enemy_unit_ids_in_player_deployment_zone_from_battlefield,
    enemy_unit_ids_in_player_deployment_zone_from_model_placements,
    escape,
    execute_rule_ir,
    generic_rule_ir_secondary_award,
    is_registered_phase11f_cap_probe,
    json_loads,
    mark_pending_primary_scoring_boundaries,
    mission_scoring_policies_from_setup,
    mustered_armies,
    next_generic_rule_ir_victory_point_event_id,
    pending_primary_scoring_boundary_keys,
    phase11c_mission_setup,
    phase17n_event_setup,
    phase17n_state_with_setup,
    primary_mission_model_placements_from_checkpoint,
    pytest,
    record_new_primary_unit_destruction_events,
    record_primary_battlefield_departure_event,
    record_primary_destroyed_model_departures,
    record_primary_scoring_state_evidence,
    record_primary_turn_start_evidence_for_fixture,
    record_secondary_destruction_for_fixture,
    registered_phase11f_cap_probe,
    replace,
    request_mission_action_start,
    require_generic_rule_ir_loaded_authority,
    require_source_backed_secondary_cap_bucket,
    require_state_backed_secondary_scoring_commit,
    resolve_primary_scoring_boundary_lifecycle,
    rules_unit_objective_proximity_witness,
    ruleset,
    score_primary_objective_control_boundary,
    score_secondary_mission_from_state,
    secondary_choice,
    secondary_scoring_provider_kind_from_metadata,
    secondary_scoring_provider_kind_from_token,
    state_backed_secondary_binding_identity,
    state_backed_secondary_objective_control_record_id,
    validate_generic_rule_ir_secondary_award,
    validate_json_value,
    validate_legacy_phase11f_secondary_award,
    validate_primary_scoring_spatial_rows_from_checkpoint,
    validate_secondary_award_semantics,
    validate_secondary_generic_rule_ir_restore_authority,
    validate_secondary_transaction_semantics,
    validate_state_backed_secondary_award_binding,
    validate_state_backed_secondary_ledger_binding,
    with_model_offsets,
    with_unit_keywords,
)
from tests.shared.category_migration.primary_boundary_authority_history import (
    _append_player_transaction_from_award,
    _award_from_transaction,
    _compiled_generic_vp_rule_ir,
    _empty_rule_ir_authority_index,
    _execute_generic_vp_on_lifecycle,
    _fabricated_generic_rule_ir_metadata,
    _fixed_secondary_record_ids,
    _generic_rule_ir_transaction,
    _generic_vp_clause_and_effect,
    _generic_vp_execution_context,
    _ledger_payload,
    _registered_phase11f_cap_probe_award,
    _rehash_evidence_transactions_and_lifecycles,
    _rehash_lifecycle_row,
    _replace_player_transaction,
    _require_registered_phase11f_cap_probe,
    _rule_ir_authority_index,
    _secondary_transaction,
    _secondary_transaction_payload,
    _secondary_transaction_payloads,
    _transaction_record_id,
)
from tests.shared.category_migration.primary_boundary_scoring_builders import (
    _battlefield_dominance_lifecycle,
    _bring_it_down_player_a_scored_lifecycle,
    _defend_stronghold_ready_lifecycle,
    _pending_command_boundary_lifecycle,
    _pending_final_turn_end_boundary_lifecycle,
    _same_boundary_bring_it_down_and_assassination_lifecycle,
    _same_boundary_two_player_bring_it_down_lifecycle,
    _scored_command_boundary_after_mutation,
    _scored_determined_acquisition_command_lifecycle,
    _scored_reconnaissance_turn_end_lifecycle,
    _single_mode_bring_it_down_lifecycle,
    _two_defender_battlefield_dominance_lifecycle,
    _two_model_battlefield_dominance_lifecycle,
    _two_player_bring_it_down_scored_lifecycle,
    _two_round_bring_it_down_lifecycle,
)
from tests.shared.category_migration.primary_boundary_state_and_geometry import (
    _add_unit_keyword,
    _assert_scoring_commit_differs_from_oc_checkpoint,
    _authenticated_move_unit_to,
    _checkpoint_with_model_states,
    _destroy_all_models,
    _destroy_first_model,
    _destroy_model_with_event,
    _destroy_unit_with_events,
    _emit_oc_event,
    _first_unit,
    _json_list,
    _json_map,
    _json_object,
    _offset_checkpoint_model_state,
    _place_in_player_deployment_zone_away_from_home,
    _place_player_away_from_objectives,
    _place_player_on_role,
    _place_unit_interior_non_overlapping,
    _queue_pending_window,
    _replace_secondary_scoring_evidence_binding_from_payload,
    _return_destroyed_unit,
    _set_unit_starting_wounds,
    _sticky_state_for,
    _swap_secondary_scoring_evidence_bindings,
    _tactical_secondary_amount,
    _zone_anchor_away_from_home,
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
__all__ += ["_add_unit_keyword", "_append_player_transaction_from_award"]
__all__ += ["_assert_scoring_commit_differs_from_oc_checkpoint", "_authenticated_move_unit_to"]
__all__ += ["_award_from_transaction", "_battlefield_dominance_lifecycle"]
__all__ += ["_bring_it_down_player_a_scored_lifecycle", "_card_for_state_backed_scoring"]
__all__ += ["_checkpoint_with_model_states", "_compiled_generic_vp_rule_ir"]
__all__ += ["_defend_stronghold_ready_lifecycle", "_destroy_all_models", "_destroy_first_model"]
__all__ += ["_destroy_model_with_event", "_destroy_unit_with_events"]
__all__ += ["_emit_objective_control_boundary_event_if_missing", "_emit_oc_event"]
__all__ += ["_empty_rule_ir_authority_index", "_execute_generic_vp_on_lifecycle"]
__all__ += ["_expected_state_backed_secondary_award", "_fabricated_generic_rule_ir_metadata"]
__all__ += ["_first_unit", "_fixed_secondary_record_ids", "_generic_rule_ir_transaction"]
__all__ += ["_generic_vp_clause_and_effect", "_generic_vp_execution_context", "_json_list"]
__all__ += ["_json_map", "_json_object", "_ledger_payload"]
__all__ += ["_legacy_score_secondary_mission_award", "_offset_checkpoint_model_state"]
__all__ += ["_pending_command_boundary_lifecycle", "_pending_final_turn_end_boundary_lifecycle"]
__all__ += ["_place_in_player_deployment_zone_away_from_home"]
__all__ += ["_place_player_away_from_objectives", "_place_player_on_role"]
__all__ += ["_place_unit_interior_non_overlapping", "_queue_pending_window"]
__all__ += ["_record_for_binding", "_registered_phase11f_cap_probe_award"]
__all__ += ["_rehash_evidence_transactions_and_lifecycles", "_rehash_lifecycle_row"]
__all__ += ["_reject_duplicate_tactical_source", "_replace_player_transaction"]
__all__ += ["_replace_secondary_scoring_evidence_binding_from_payload"]
__all__ += ["_require_registered_phase11f_cap_probe", "_return_destroyed_unit"]
__all__ += ["_rule_ir_authority_index"]
__all__ += ["_same_boundary_bring_it_down_and_assassination_lifecycle"]
__all__ += ["_same_boundary_two_player_bring_it_down_lifecycle"]
__all__ += ["_scored_command_boundary_after_mutation"]
__all__ += ["_scored_determined_acquisition_command_lifecycle"]
__all__ += ["_scored_reconnaissance_turn_end_lifecycle", "_secondary_transaction"]
__all__ += ["_secondary_transaction_payload", "_secondary_transaction_payloads"]
__all__ += ["_set_unit_starting_wounds", "_single_mode_bring_it_down_lifecycle"]
__all__ += ["_sticky_state_for", "_swap_secondary_scoring_evidence_bindings"]
__all__ += ["_tactical_secondary_amount", "_transaction_objective_control_record_id"]
__all__ += ["_transaction_record_id", "_two_defender_battlefield_dominance_lifecycle"]
__all__ += ["_two_model_battlefield_dominance_lifecycle"]
__all__ += ["_two_player_bring_it_down_scored_lifecycle", "_two_round_bring_it_down_lifecycle"]
__all__ += ["_uncapped_award_from_transaction", "_validate_registered_phase11f_cap_probe"]
__all__ += ["_validate_scored_tactical_card_bindings", "_validate_secondary_primary_closure"]
__all__ += ["_zone_anchor_away_from_home", "append_authenticated_normal_move"]
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
