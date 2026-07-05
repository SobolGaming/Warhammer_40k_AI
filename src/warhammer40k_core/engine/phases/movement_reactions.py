# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *
from warhammer40k_core.engine.phases.movement_model import *
from warhammer40k_core.engine.phases.movement_state import *
from warhammer40k_core.engine.phases.movement_handler import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_REINFORCEMENT_UNIT_DECISION_TYPE, SELECT_DISEMBARK_UNIT_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, COMPLETE_REINFORCEMENTS_OPTION_ID, COMPLETE_DISEMBARKS_OPTION_ID, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _begin_reinforcements_step, _complete_reinforcements_step
    from warhammer40k_core.engine.phases.movement_reinforcements import _reinforcement_unit_options, _eligible_reinforcement_reserve_states, _required_reinforcement_reserve_states, _overdue_required_reinforcement_reserve_states, _apply_reinforcement_unit_selection_decision, _request_reinforcement_placement, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _request_placement_proposal_retry, _optional_proposal_context_string, _resolve_reinforcement_placement_submission, _deep_strike_enemy_distance_for_reserve_arrival, _unit_for_reserve_state, _apply_valid_reinforcement_placement
    from warhammer40k_core.engine.phases.movement_transports import _request_pre_move_disembark_if_available, _request_post_normal_move_disembark_if_available, _pre_move_disembark_entries, _post_normal_move_disembark_entries, _disembark_unit_selection_options, _apply_disembark_unit_selection_decision, _request_disembark_placement, _resolve_disembark_placement_submission, _allowed_disembark_modes_for_placement_request, _resolve_combat_disembark_placement_submission
    from warhammer40k_core.engine.phases.movement_placement_proposals import _parse_movement_proposal_submission_or_invalid, _parse_placement_proposal_submission_or_invalid, _proposal_payload_parse_failure, _key_error_field, _apply_placement_proposal_decision, _missing_disembark_proposal_field, _apply_valid_disembark, _apply_valid_combat_disembark
    from warhammer40k_core.engine.phases.movement_action_decisions import _request_movement_action, _apply_movement_action_decision, _request_advance_move_grant_decision_if_available, _decline_advance_move_grant_option, _advance_move_grant_option, _apply_advance_move_grant_decision, _assert_advance_move_grant_still_available, _record_movement_action_grant_effects, _movement_action_grant_unit_effect_target_ids, _movement_action_grant_effect_expiration, _resolve_pending_movement_action_after_grants, _resolve_pending_advance_action, _request_pending_movement_action_proposal, _request_movement_proposal, _forced_desperate_escape_sources_for_unit, _forced_desperate_escape_source_rule_ids_from_context, _request_movement_proposal_retry
    from warhammer40k_core.engine.phases.movement_resolution_flow import _apply_movement_proposal_decision, _action_result_from_proposal_request, _reject_invalid_proposal, _reject_invalid_movement_resolution, _apply_advance_roll_reroll_decision, _resolve_and_apply_advance_move, _advance_move_grants_from_context, _selected_advance_move_grant_hook_ids_from_context, _apply_advance_move_grants, _grant_ranged_weapon_keywords, _aircraft_reserve_transition_reason_for_normal_move, _apply_aircraft_reserve_transition_for_normal_move
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_desperate_escape_model_selection_decision, _apply_fall_back_result, _request_embark_after_move_or_complete_activation, _complete_activation_then_request_post_normal_disembark_if_available, _post_move_embark_options, _apply_embark_transport_selection_decision, _apply_valid_embark, _complete_movement_activation, _complete_movement_activation_with_record_ids, _maximum_model_distance_inches_from_witness, _interrupt_started_mission_actions_for_movement_activation
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_active_player_end_movement_overwatch_trigger_unit_ids",
    "_eligible_triggered_movement_units_from_grants",
    "_fire_overwatch_end_movement_trigger_payload",
    "_friendly_unit_fell_back_context_from_event",
    "_friendly_unit_fell_back_timing_window_id",
    "_movement_end_surge_distance_roll_spec",
    "_movement_end_surge_event_already_processed",
    "_movement_end_surge_grant_distance_bonus",
    "_request_end_movement_active_player_stratagem_if_available",
    "_request_end_opponent_movement_reaction_if_available",
    "_request_fire_overwatch_reaction_if_available",
    "_request_friendly_unit_fell_back_stratagem_if_available",
    "_request_movement_end_surge_if_available",
    "_request_rapid_ingress_reaction_if_available",
    "_request_selected_to_fall_back_stratagem_if_available",
    "_request_selected_to_move_stratagem_if_available",
    "_selected_to_fall_back_timing_window_id",
    "_selected_to_fall_back_trigger_payload",
    "_selected_to_move_timing_window_id",
    "_stratagem_target_proposal_payload_factory",
    "_stratagem_use_payload_factory",
    "_stratagem_used_for_context",
)


def _request_end_opponent_movement_reaction_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    fire_overwatch_status = _request_fire_overwatch_reaction_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
    )
    if fire_overwatch_status is not None:
        return fire_overwatch_status
    return _request_rapid_ingress_reaction_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
    )


def _request_end_movement_active_player_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    if stratagem_index is None:
        return None
    active_player_id = _active_player_id(state)
    window_id = f"end-movement-ingress-round-{state.battle_round:02d}-player-{active_player_id}"
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=active_player_id,
        trigger_kind=TimingTriggerKind.END_PHASE,
        timing_window_id=window_id,
        trigger_payload={
            "trigger_window": "end_movement_phase",
            "timing_window_id": window_id,
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_for_handler_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "phase_body_status": "end_movement_active_player_stratagem_pending",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "pending_request_id": request.request_id,
        },
    )


def _request_rapid_ingress_reaction_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    if reaction_queue is None or stratagem_index is None:
        return None
    active_player_id = _active_player_id(state)
    for player_id in state.player_ids:
        if player_id == active_player_id:
            continue
        window_id = f"rapid-ingress-end-movement-round-{state.battle_round:02d}-player-{player_id}"
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player_id,
            trigger_kind=TimingTriggerKind.END_PHASE,
            timing_window_id=window_id,
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        proposal = stratagem_target_proposal_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            handler_id=CORE_RAPID_INGRESS_HANDLER_ID,
        )
        if proposal is None:
            continue
        reaction_window = ReactionWindow(
            timing_window=TimingWindow(
                window_id=window_id,
                descriptor=TimingWindowDescriptor(
                    descriptor_id="core-rapid-ingress-end-movement",
                    trigger_kind=TimingTriggerKind.END_PHASE,
                    source_rule_id=CORE_RAPID_INGRESS_HANDLER_ID,
                    phase=BattlePhase.MOVEMENT,
                    source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                ),
                game_id=state.game_id,
                battle_round=state.battle_round,
                active_player_id=active_player_id,
                phase=BattlePhase.MOVEMENT,
            ),
            eligible_player_ids=(player_id,),
        )
        triggered = reaction_queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=reaction_window,
            parent_phase=BattlePhase.MOVEMENT,
            parent_step="end_movement_phase_reactions",
            resume_token=f"{window_id}-resume",
            actor_id=player_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            options=(parameterized_decision_option(),),
            payload_factory=_stratagem_target_proposal_payload_factory(proposal),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=triggered.decision_request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "step": MovementPhaseStepKind.MOVE_UNITS.value,
                "phase_body_status": "rapid_ingress_reaction_pending",
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "reacting_player_id": player_id,
            },
        )
    return None


def _request_fire_overwatch_reaction_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    if reaction_queue is None or stratagem_index is None:
        return None
    movement_state = state.movement_phase_state
    if movement_state is None:
        return None
    active_player_id = _active_player_id(state)
    moved_unit_instance_ids = _active_player_end_movement_overwatch_trigger_unit_ids(
        state=state,
        decisions=decisions,
        movement_state=movement_state,
    )
    if not moved_unit_instance_ids:
        return None
    for player_id in state.player_ids:
        if player_id == active_player_id:
            continue
        for moved_unit_instance_id in moved_unit_instance_ids:
            window_id = (
                f"fire-overwatch-end-movement-round-{state.battle_round:02d}-"
                f"unit-{moved_unit_instance_id}-player-{player_id}"
            )
            trigger_payload = _fire_overwatch_end_movement_trigger_payload(
                moved_unit_instance_id=moved_unit_instance_id,
                timing_window_id=window_id,
            )
            context = StratagemEligibilityContext.from_state(
                state=state,
                player_id=player_id,
                trigger_kind=TimingTriggerKind.END_PHASE,
                timing_window_id=window_id,
                trigger_payload=trigger_payload,
            )
            if stratagem_window_declined_for_context(decisions=decisions, context=context):
                continue
            proposal = stratagem_target_proposal_from_index(
                state=state,
                index=stratagem_index,
                context=context,
                handler_id=CORE_FIRE_OVERWATCH_HANDLER_ID,
            )
            if proposal is None:
                continue
            reaction_window = ReactionWindow(
                timing_window=TimingWindow(
                    window_id=window_id,
                    descriptor=TimingWindowDescriptor(
                        descriptor_id="core-fire-overwatch-end-opponent-movement",
                        trigger_kind=TimingTriggerKind.END_PHASE,
                        source_rule_id=CORE_FIRE_OVERWATCH_HANDLER_ID,
                        phase=BattlePhase.MOVEMENT,
                        source_step="end_movement_phase_reactions",
                        metadata=trigger_payload,
                    ),
                    game_id=state.game_id,
                    battle_round=state.battle_round,
                    active_player_id=active_player_id,
                    phase=BattlePhase.MOVEMENT,
                ),
                eligible_player_ids=(player_id,),
            )
            triggered = reaction_queue.emit_decision_request(
                state=state,
                decisions=decisions,
                reaction_window=reaction_window,
                parent_phase=BattlePhase.MOVEMENT,
                parent_step="end_movement_phase_reactions",
                resume_token=f"{window_id}-resume",
                actor_id=player_id,
                decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
                options=(parameterized_decision_option(),),
                payload_factory=_stratagem_target_proposal_payload_factory(proposal),
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=triggered.decision_request,
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "step": MovementPhaseStepKind.MOVE_UNITS.value,
                    "phase_body_status": "fire_overwatch_reaction_pending",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "reacting_player_id": player_id,
                    "moved_unit_instance_id": moved_unit_instance_id,
                },
            )
    return None


def _request_selected_to_move_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    active_selection: MovementUnitSelection,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    if type(active_selection) is not MovementUnitSelection:
        raise GameLifecycleError("Selected-to-move Stratagem window requires active selection.")
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=active_selection.player_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_MOVE,
        timing_window_id=_selected_to_move_timing_window_id(active_selection),
        trigger_payload={
            SELECTED_TO_MOVE_UNIT_CONTEXT_KEY: active_selection.unit_instance_id,
            "selection_request_id": active_selection.request_id,
            "selection_result_id": active_selection.result_id,
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": active_selection.unit_instance_id,
            "phase_body_status": "selected_to_move_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _request_selected_to_fall_back_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    if reaction_queue is None or stratagem_index is None:
        return None
    if pending_action.movement_phase_action is not MovementPhaseActionKind.FALL_BACK:
        raise GameLifecycleError("Selected-to-Fall-Back Stratagem requires Fall Back action.")
    active_player_id = _active_player_id(state)
    if pending_action.player_id != active_player_id:
        raise GameLifecycleError("Selected-to-Fall-Back Stratagem active player drift.")
    trigger_payload = _selected_to_fall_back_trigger_payload(pending_action)
    for player_id in sorted(player for player in state.player_ids if player != active_player_id):
        window_id = _selected_to_fall_back_timing_window_id(
            pending_action=pending_action,
            reacting_player_id=player_id,
        )
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=player_id,
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
            timing_window_id=window_id,
            trigger_payload={**trigger_payload, "timing_window_id": window_id},
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_for_handler_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            handler_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
        )
        if not options:
            continue
        reaction_window = ReactionWindow(
            timing_window=TimingWindow(
                window_id=window_id,
                descriptor=TimingWindowDescriptor(
                    descriptor_id="generic-rule-ir-selected-fall-back",
                    trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
                    source_rule_id=GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
                    phase=BattlePhase.MOVEMENT,
                    source_step="selected_fall_back_reactions",
                    metadata={**trigger_payload, "timing_window_id": window_id},
                ),
                game_id=state.game_id,
                battle_round=state.battle_round,
                active_player_id=active_player_id,
                phase=BattlePhase.MOVEMENT,
            ),
            eligible_player_ids=(player_id,),
        )
        triggered = reaction_queue.emit_decision_request(
            state=state,
            decisions=decisions,
            reaction_window=reaction_window,
            parent_phase=BattlePhase.MOVEMENT,
            parent_step="selected_fall_back_reactions",
            resume_token=f"{window_id}-resume",
            actor_id=player_id,
            decision_type=STRATAGEM_DECISION_TYPE,
            options=(*options, stratagem_decline_option()),
            payload_factory=_stratagem_use_payload_factory(context),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=triggered.decision_request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "phase_body_status": "selected_to_fall_back_stratagem_pending",
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "reacting_player_id": player_id,
                "fall_back_unit_instance_id": pending_action.unit_instance_id,
            },
        )
    return None


def _request_friendly_unit_fell_back_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    for record in decisions.event_log.records:
        if record.event_type != "movement_activation_completed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement activation completed payload must be an object.")
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("phase") != BattlePhase.MOVEMENT.value:
            continue
        if payload.get("active_player_id") != _active_player_id(state):
            continue
        if payload.get("movement_phase_action") != MovementPhaseActionKind.FALL_BACK.value:
            continue
        context = _friendly_unit_fell_back_context_from_event(
            state=state,
            event_id=record.event_id,
            payload=payload,
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        if _stratagem_used_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if not options:
            continue
        request = create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "friendly_unit_fell_back_stratagem_window_opened",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.MOVEMENT.value,
                    "player_id": context.player_id,
                    "fell_back_unit_instance_id": _payload_string(
                        payload,
                        key="unit_instance_id",
                    ),
                    "trigger_event_id": record.event_id,
                    "stratagem_context": context.to_payload(),
                    "request_id": request.request_id,
                    "phase_body_status": "friendly_unit_fell_back_stratagem_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": context.player_id,
                "phase_body_status": "friendly_unit_fell_back_stratagem_pending",
                "pending_request_id": request.request_id,
            },
        )
    return None


def _friendly_unit_fell_back_context_from_event(
    *,
    state: GameState,
    event_id: str,
    payload: dict[str, JsonValue],
) -> StratagemEligibilityContext:
    unit_id = _payload_string(payload, key="unit_instance_id")
    player_id = _payload_string(payload, key="active_player_id")
    engaged_enemy_ids = _identifier_list_from_json_object(
        payload,
        key="start_engaged_enemy_unit_instance_ids",
        field_name="start engaged enemy unit id",
    )
    return StratagemEligibilityContext.from_state(
        state=state,
        player_id=player_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK,
        timing_window_id=_friendly_unit_fell_back_timing_window_id(event_id),
        trigger_payload={
            JUST_FELL_BACK_UNIT_CONTEXT_KEY: unit_id,
            ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY: list(engaged_enemy_ids),
            "movement_activation_completed_event_id": _validate_identifier(
                "movement_activation_completed_event_id",
                event_id,
            ),
            "request_id": _payload_string(payload, key="request_id"),
            "result_id": _payload_string(payload, key="result_id"),
        },
    )


def _friendly_unit_fell_back_timing_window_id(trigger_event_id: str) -> str:
    return f"friendly-unit-fell-back:{_validate_identifier('trigger_event_id', trigger_event_id)}"


def _stratagem_used_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    context_payload = context.to_payload()
    for record in decisions.event_log.records:
        if record.event_type != "stratagem_used":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Stratagem use event payload must be an object.")
        payload_object = cast(dict[str, object], payload)
        if (
            payload_object.get("game_id") == context_payload.get("game_id")
            and payload_object.get("player_id") == context_payload.get("player_id")
            and payload_object.get("battle_round") == context_payload.get("battle_round")
            and payload_object.get("phase") == context_payload.get("phase")
            and payload_object.get("active_player_id") == context_payload.get("active_player_id")
            and payload_object.get("timing_window_id") == context_payload.get("timing_window_id")
        ):
            return True
    return False


def _selected_to_fall_back_trigger_payload(
    pending_action: PendingMovementActionSelection,
) -> dict[str, JsonValue]:
    if pending_action.fall_back_mode is None:
        raise GameLifecycleError("Selected-to-Fall-Back trigger requires fall_back_mode.")
    return {
        FALL_BACK_UNIT_CONTEXT_KEY: pending_action.unit_instance_id,
        FALL_BACK_MODE_CONTEXT_KEY: pending_action.fall_back_mode.value,
        "movement_mode": pending_action.movement_mode.value,
        "action_request_id": pending_action.request_id,
        "action_result_id": pending_action.result_id,
        "action_selected_option_id": pending_action.selected_option_id,
    }


def _selected_to_fall_back_timing_window_id(
    *,
    pending_action: PendingMovementActionSelection,
    reacting_player_id: str,
) -> str:
    return (
        f"selected-fall-back-round-{pending_action.battle_round:02d}-"
        f"active-{pending_action.player_id}-unit-{pending_action.unit_instance_id}-"
        f"reacting-{_validate_identifier('reacting_player_id', reacting_player_id)}"
    )


def _selected_to_move_timing_window_id(active_selection: MovementUnitSelection) -> str:
    if type(active_selection) is not MovementUnitSelection:
        raise GameLifecycleError("Selected-to-move timing window requires active selection.")
    return (
        f"selected-to-move-round-{active_selection.battle_round:02d}-"
        f"player-{active_selection.player_id}-unit-{active_selection.unit_instance_id}"
    )


def _stratagem_use_payload_factory(
    context: StratagemEligibilityContext,
) -> Callable[[str, str, str], JsonValue]:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem use payload factory requires a context.")

    def payload_factory(_request_id: str, _decision_type: str, _actor_id: str) -> JsonValue:
        return validate_json_value(
            {
                "stratagem_context": context.to_payload(),
                "finite": True,
            }
        )

    return payload_factory


def _stratagem_target_proposal_payload_factory(
    proposal: StratagemTargetProposal,
) -> Callable[[str, str, str], JsonValue]:
    if type(proposal) is not StratagemTargetProposal:
        raise GameLifecycleError(
            "Stratagem target proposal payload factory requires a StratagemTargetProposal."
        )

    def payload_factory(request_id: str, decision_type: str, actor_id: str) -> JsonValue:
        return stratagem_target_proposal_request_payload(
            proposal,
            request_id=request_id,
            decision_type=decision_type,
            actor_id=actor_id,
            allow_decline=True,
        )

    return payload_factory


def _request_movement_end_surge_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: MovementEndSurgeHookRegistry,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    if type(registry) is not MovementEndSurgeHookRegistry:
        raise GameLifecycleError("Movement-end surge trigger requires a registry.")
    if not registry.all_bindings():
        return None
    active_player_id = _active_player_id(state)
    for record in decisions.event_log.records:
        if record.event_type != "movement_activation_completed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("phase") != BattlePhase.MOVEMENT.value:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        movement_action = payload.get("movement_phase_action")
        if movement_action not in {
            MovementPhaseActionKind.NORMAL_MOVE.value,
            MovementPhaseActionKind.ADVANCE.value,
            MovementPhaseActionKind.FALL_BACK.value,
        }:
            continue
        triggering_unit_id = payload.get("unit_instance_id")
        if type(triggering_unit_id) is not str:
            raise GameLifecycleError("Movement completion event missing unit_instance_id.")
        triggering_unit = _unit_instance_by_id(
            state=state,
            unit_instance_id=triggering_unit_id,
        )
        if _unit_has_keyword(triggering_unit, "AIRCRAFT"):
            continue
        if _movement_end_surge_event_already_processed(
            decisions=decisions,
            trigger_event_id=record.event_id,
        ):
            continue
        for reacting_player_id in sorted(
            player_id for player_id in state.player_ids if player_id != active_player_id
        ):
            context = MovementEndSurgeContext(
                state=state,
                ruleset_descriptor=ruleset_descriptor,
                triggering_unit_instance_id=triggering_unit_id,
                triggering_player_id=active_player_id,
                reacting_player_id=reacting_player_id,
                trigger_event_id=record.event_id,
                movement_phase_action=movement_action,
                trigger_event_payload=payload,
            )
            grants = registry.grants_for(context)
            if not grants:
                continue
            max_distance_bonus_inches = _movement_end_surge_grant_distance_bonus(grants)
            roll_state = _dice_roll_manager_for_state(state=state, decisions=decisions).roll(
                _movement_end_surge_distance_roll_spec(
                    source_rule_id=grants[0].source_id,
                    player_id=reacting_player_id,
                    triggering_unit_instance_id=triggering_unit_id,
                    trigger_event_id=record.event_id,
                )
            )
            descriptor = TriggeredMovementDescriptor(
                movement_kind=TriggeredMovementKind.SURGE,
                source_rule_id=grants[0].source_id,
                trigger_timing=TriggeredReactionWindow(
                    phase=BattlePhase.MOVEMENT,
                    window_kind=ReactionWindowKind.RULE_TRIGGER,
                    source_step=TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE.value,
                    source_event_id=record.event_id,
                ),
                max_distance_inches=float(roll_state.current_total + max_distance_bonus_inches),
                movement_mode=MovementMode.NORMAL,
                allow_battle_shocked=False,
                allow_within_engagement_range=False,
                one_per_phase=True,
                optional=True,
            )
            request = triggered_movement_unit_selection_request(
                state=state,
                player_id=reacting_player_id,
                descriptor=descriptor,
                eligible_units=_eligible_triggered_movement_units_from_grants(grants),
            )
            decisions.request_decision(request)
            decisions.event_log.append(
                "movement_end_surge_triggered",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "reacting_player_id": reacting_player_id,
                    "phase": BattlePhase.MOVEMENT.value,
                    "triggering_unit_instance_id": triggering_unit_id,
                    "trigger_event_id": record.event_id,
                    "movement_phase_action": movement_action,
                    "surge_distance_roll": roll_state.to_payload(),
                    "max_distance_bonus_inches": max_distance_bonus_inches,
                    "descriptor": descriptor.to_payload(),
                    "grants": [grant.to_payload() for grant in grants],
                    "request_id": request.request_id,
                    "phase_body_status": "movement_end_surge_pending",
                },
            )
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "reacting_player_id": reacting_player_id,
                    "triggering_unit_instance_id": triggering_unit_id,
                    "decision_type": request.decision_type,
                    "phase_body_status": "movement_end_surge_pending",
                },
            )
    return None


def _movement_end_surge_distance_roll_spec(
    *,
    source_rule_id: str,
    player_id: str,
    triggering_unit_instance_id: str,
    trigger_event_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            "Movement-end surge distance "
            f"{source_rule_id} for {triggering_unit_instance_id} from {trigger_event_id}"
        ),
        roll_type="movement_end_surge.distance",
        actor_id=player_id,
    )


def _eligible_triggered_movement_units_from_grants(
    grants: tuple[MovementEndSurgeGrant, ...],
) -> tuple[TriggeredMovementEligibleUnit, ...]:
    units: list[TriggeredMovementEligibleUnit] = []
    for grant in grants:
        units.append(
            TriggeredMovementEligibleUnit(
                unit_instance_id=grant.unit_instance_id,
                hook_id=grant.hook_id,
                source_id=grant.source_id,
                replay_payload=grant.replay_payload,
                decision_effect_payload=grant.decision_effect_payload,
            )
        )
    return tuple(sorted(units, key=lambda unit: unit.unit_instance_id))


def _movement_end_surge_grant_distance_bonus(
    grants: tuple[MovementEndSurgeGrant, ...],
) -> int:
    if type(grants) is not tuple:
        raise GameLifecycleError("Movement-end surge distance bonus requires grant tuple.")
    for grant in grants:
        if type(grant) is not MovementEndSurgeGrant:
            raise GameLifecycleError(
                "Movement-end surge distance bonus requires MovementEndSurgeGrant values."
            )
    bonuses = {grant.max_distance_bonus_inches for grant in grants}
    if len(bonuses) != 1:
        raise GameLifecycleError("Movement-end surge grants must share one distance bonus.")
    return bonuses.pop()


def _movement_end_surge_event_already_processed(
    *,
    decisions: DecisionController,
    trigger_event_id: str,
) -> bool:
    requested_event_id = _validate_identifier("trigger_event_id", trigger_event_id)
    for record in decisions.event_log.records:
        if record.event_type not in {
            "movement_end_surge_triggered",
            "triggered_movement_declined",
            "triggered_movement_unit_selected",
            "triggered_movement_resolved",
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("trigger_event_id") == requested_event_id:
            return True
        trigger_timing = payload.get("trigger_timing")
        if isinstance(trigger_timing, dict) and trigger_timing.get("source_event_id") == (
            requested_event_id
        ):
            return True
    return False


def _active_player_end_movement_overwatch_trigger_unit_ids(
    *,
    state: GameState,
    decisions: DecisionController,
    movement_state: MovementPhaseState,
) -> tuple[str, ...]:
    active_player_id = _active_player_id(state)
    moved_ids = set(movement_state.moved_unit_ids)
    eligible_action_ids: set[str] = set()
    eligible_setup_ids: set[str] = set()
    for record in decisions.event_log.records:
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("game_id") != state.game_id:
            continue
        if payload.get("battle_round") != state.battle_round:
            continue
        if payload.get("phase") != BattlePhase.MOVEMENT.value:
            continue
        if payload.get("active_player_id") != active_player_id:
            continue
        unit_id = payload.get("unit_instance_id")
        if type(unit_id) is not str or unit_id not in moved_ids:
            continue
        if record.event_type == "reinforcement_unit_arrived":
            eligible_setup_ids.add(unit_id)
            continue
        if record.event_type != "movement_activation_completed":
            continue
        if payload.get("movement_phase_action") in {
            MovementPhaseActionKind.NORMAL_MOVE.value,
            MovementPhaseActionKind.ADVANCE.value,
            MovementPhaseActionKind.FALL_BACK.value,
        }:
            eligible_action_ids.add(unit_id)
    return tuple(sorted(eligible_action_ids | eligible_setup_ids))


def _fire_overwatch_end_movement_trigger_payload(
    *,
    moved_unit_instance_id: str,
    timing_window_id: str,
) -> JsonValue:
    moved_unit_id = _validate_identifier("moved_unit_instance_id", moved_unit_instance_id)
    return validate_json_value(
        {
            "moved_unit_instance_id": moved_unit_id,
            "timing_window_id": _validate_identifier("timing_window_id", timing_window_id),
            "trigger_window": "end_opponent_movement_phase",
            "eligible_trigger_kinds": ["set_up", "started_or_ended_move"],
        }
    )
