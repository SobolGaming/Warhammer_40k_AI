# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *
from warhammer40k_core.engine.phases.movement_model import *
from warhammer40k_core.engine.phases.movement_state import *
from warhammer40k_core.engine.phases.movement_handler import *
from warhammer40k_core.engine.phases.movement_reactions import *
from warhammer40k_core.engine.phases.movement_reinforcements import *
from warhammer40k_core.engine.phases.movement_transports import *
from warhammer40k_core.engine.phases.movement_placement_proposals import *
from warhammer40k_core.engine.phases.movement_action_decisions import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_REINFORCEMENT_UNIT_DECISION_TYPE, SELECT_DISEMBARK_UNIT_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, COMPLETE_REINFORCEMENTS_OPTION_ID, COMPLETE_DISEMBARKS_OPTION_ID, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _begin_reinforcements_step, _complete_reinforcements_step
    from warhammer40k_core.engine.phases.movement_reactions import _request_end_opponent_movement_reaction_if_available, _request_end_movement_active_player_stratagem_if_available, _request_rapid_ingress_reaction_if_available, _request_fire_overwatch_reaction_if_available, _request_selected_to_move_stratagem_if_available, _request_selected_to_fall_back_stratagem_if_available, _request_friendly_unit_fell_back_stratagem_if_available, _friendly_unit_fell_back_context_from_event, _friendly_unit_fell_back_timing_window_id, _stratagem_used_for_context, _selected_to_fall_back_trigger_payload, _selected_to_fall_back_timing_window_id, _selected_to_move_timing_window_id, _stratagem_use_payload_factory, _stratagem_target_proposal_payload_factory, _request_movement_end_surge_if_available, _movement_end_surge_distance_roll_spec, _eligible_triggered_movement_units_from_grants, _movement_end_surge_grant_distance_bonus, _movement_end_surge_event_already_processed, _active_player_end_movement_overwatch_trigger_unit_ids, _fire_overwatch_end_movement_trigger_payload
    from warhammer40k_core.engine.phases.movement_reinforcements import _reinforcement_unit_options, _eligible_reinforcement_reserve_states, _required_reinforcement_reserve_states, _overdue_required_reinforcement_reserve_states, _apply_reinforcement_unit_selection_decision, _request_reinforcement_placement, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _request_placement_proposal_retry, _optional_proposal_context_string, _resolve_reinforcement_placement_submission, _deep_strike_enemy_distance_for_reserve_arrival, _unit_for_reserve_state, _apply_valid_reinforcement_placement
    from warhammer40k_core.engine.phases.movement_transports import _request_pre_move_disembark_if_available, _request_post_normal_move_disembark_if_available, _pre_move_disembark_entries, _post_normal_move_disembark_entries, _disembark_unit_selection_options, _apply_disembark_unit_selection_decision, _request_disembark_placement, _resolve_disembark_placement_submission, _allowed_disembark_modes_for_placement_request, _resolve_combat_disembark_placement_submission
    from warhammer40k_core.engine.phases.movement_placement_proposals import _parse_movement_proposal_submission_or_invalid, _parse_placement_proposal_submission_or_invalid, _proposal_payload_parse_failure, _key_error_field, _apply_placement_proposal_decision, _missing_disembark_proposal_field, _apply_valid_disembark, _apply_valid_combat_disembark
    from warhammer40k_core.engine.phases.movement_action_decisions import _request_movement_action, _apply_movement_action_decision, _request_advance_move_grant_decision_if_available, _decline_advance_move_grant_option, _advance_move_grant_option, _apply_advance_move_grant_decision, _assert_advance_move_grant_still_available, _record_movement_action_grant_effects, _movement_action_grant_unit_effect_target_ids, _movement_action_grant_effect_expiration, _resolve_pending_movement_action_after_grants, _resolve_pending_advance_action, _request_pending_movement_action_proposal, _request_movement_proposal, _forced_desperate_escape_sources_for_unit, _forced_desperate_escape_source_rule_ids_from_context, _request_movement_proposal_retry
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_desperate_escape_model_selection_decision, _apply_fall_back_result, _request_embark_after_move_or_complete_activation, _complete_activation_then_request_post_normal_disembark_if_available, _post_move_embark_options, _apply_embark_transport_selection_decision, _apply_valid_embark, _complete_movement_activation, _complete_movement_activation_with_record_ids, _maximum_model_distance_inches_from_witness, _interrupt_started_mission_actions_for_movement_activation
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_action_result_from_proposal_request",
    "_advance_move_grants_from_context",
    "_aircraft_reserve_transition_reason_for_normal_move",
    "_apply_advance_move_grants",
    "_apply_advance_roll_reroll_decision",
    "_apply_aircraft_reserve_transition_for_normal_move",
    "_apply_movement_proposal_decision",
    "_grant_ranged_weapon_keywords",
    "_reject_invalid_movement_resolution",
    "_reject_invalid_proposal",
    "_resolve_and_apply_advance_move",
    "_selected_advance_move_grant_hook_ids_from_context",
)


def _apply_movement_proposal_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    advance_move_hooks: AdvanceMoveHookRegistry,
    advance_eligibility_hooks: AdvanceEligibilityHookRegistry,
    fall_back_hooks: FallBackEligibilityHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Movement proposal actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement proposal requires active movement selection.")

    record = decisions.record_for_result(result)
    parsed = _parse_movement_proposal_submission_or_invalid(
        state=state,
        request=record.request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal_request, submission = parsed
    proposal_validation = submission.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _reject_invalid_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=proposal_validation,
            event_type="movement_proposal_invalid",
            message="Movement proposal does not match the pending request.",
        )

    if proposal_request.unit_instance_id != movement_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Movement proposal unit must match active selection.")
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        proposal_request.unit_instance_id
    )
    action = movement_phase_action_kind_from_token(submission.movement_phase_action)
    source_selected_option_id = _payload_string(
        proposal_request.context or {},
        key="source_selected_option_id",
    )
    if action is MovementPhaseActionKind.NORMAL_MOVE:
        movement_mode = _movement_mode_from_proposal_submission(
            submission=submission,
            action=action,
        )
        resolution = resolve_normal_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            state=state,
            movement_mode=movement_mode,
            path_witness=submission.witness,
            objective_markers=_objective_markers_for_state(state),
            hover_mode_states=tuple(state.hover_mode_states),
            movement_bonus_inches=_movement_bonus_inches_for_unit(
                state=state,
                player_id=active_player_id,
                unit_instance_id=proposal_request.unit_instance_id,
            ),
            runtime_modifier_registry=runtime_modifier_registry,
            ability_index=ability_index,
            temporary_movement_keywords=_temporary_movement_keywords_for_unit(
                state=state,
                player_id=active_player_id,
                unit_instance_id=proposal_request.unit_instance_id,
            ),
        )
        transition_reason = _aircraft_reserve_transition_reason_for_normal_move(
            resolution=resolution,
            scenario=scenario,
            unit_placement=unit_placement,
        )
        if transition_reason is not None:
            _apply_aircraft_reserve_transition_for_normal_move(
                state=state,
                decisions=decisions,
                result=_action_result_from_proposal_request(
                    proposal_request=proposal_request,
                    actor_id=active_player_id,
                    selected_option_id=source_selected_option_id,
                    payload={
                        "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
                        "unit_instance_id": proposal_request.unit_instance_id,
                        "witness": validate_json_value(submission.witness.to_payload()),
                        **resolution.movement_payload,
                    },
                ),
                ruleset_descriptor=ruleset_descriptor,
                unit_placement=unit_placement,
                resolution=resolution,
                witness=submission.witness,
                reason=transition_reason,
            )
            return None
        if not resolution.is_valid:
            return _reject_invalid_movement_resolution(
                state=state,
                decisions=decisions,
                result=result,
                unit_instance_id=proposal_request.unit_instance_id,
                action=action,
                movement_payload=resolution.movement_payload,
                rollback_record=resolution.rollback_record,
                violation_code=_normal_move_violation_code(resolution),
                message=_normal_move_invalid_message(_normal_move_violation_code(resolution)),
                proposal_request=proposal_request,
            )
        transition_batch = resolution.transition_batch(before=unit_placement)
        battlefield_state = state.battlefield_state
        if battlefield_state is None:
            raise GameLifecycleError("Normal Move proposal requires battlefield_state.")
        state.replace_battlefield_state(
            battlefield_state.with_unit_placement(resolution.attempted_placement)
        )
        return _request_embark_after_move_or_complete_activation(
            state=state,
            decisions=decisions,
            result=_action_result_from_proposal_request(
                proposal_request=proposal_request,
                actor_id=active_player_id,
                selected_option_id=source_selected_option_id,
                payload={
                    "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "witness": validate_json_value(submission.witness.to_payload()),
                    **resolution.movement_payload,
                },
            ),
            action=MovementPhaseActionKind.NORMAL_MOVE,
            witness=submission.witness,
            movement_payload={
                **resolution.movement_payload,
                "proposal_request_id": proposal_request.request_id,
            },
            displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
            transition_batch=transition_batch,
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
        )

    if action is MovementPhaseActionKind.ADVANCE:
        movement_mode = _movement_mode_from_proposal_submission(
            submission=submission,
            action=action,
        )
        advance_roll_payload = _payload_object(proposal_request.context or {}, key="advance_roll")
        advance_roll = AdvanceRollResult.from_payload(
            cast(AdvanceRollResultPayload, advance_roll_payload)
        )
        advance_resolution = resolve_advance_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            state=state,
            advance_roll=advance_roll,
            movement_mode=movement_mode,
            path_witness=submission.witness,
            objective_markers=_objective_markers_for_state(state),
            hover_mode_states=tuple(state.hover_mode_states),
            movement_bonus_inches=_movement_bonus_inches_for_unit(
                state=state,
                player_id=active_player_id,
                unit_instance_id=proposal_request.unit_instance_id,
            ),
            runtime_modifier_registry=runtime_modifier_registry,
            ability_index=ability_index,
            temporary_movement_keywords=_temporary_movement_keywords_for_unit(
                state=state,
                player_id=active_player_id,
                unit_instance_id=proposal_request.unit_instance_id,
            ),
        )
        if not advance_resolution.is_valid:
            violation_code = _normal_move_violation_code(advance_resolution)
            return _reject_invalid_movement_resolution(
                state=state,
                decisions=decisions,
                result=result,
                unit_instance_id=proposal_request.unit_instance_id,
                action=action,
                movement_payload=advance_resolution.movement_payload,
                rollback_record=advance_resolution.rollback_record,
                violation_code=violation_code,
                message=_normal_move_invalid_message(violation_code).replace(
                    "Normal Move",
                    "Advance",
                ),
                proposal_request=proposal_request,
            )
        transition_batch = advance_resolution.transition_batch(before=unit_placement)
        battlefield_state = state.battlefield_state
        if battlefield_state is None:
            raise GameLifecycleError("Advance proposal requires battlefield_state.")
        state.replace_battlefield_state(
            battlefield_state.with_unit_placement(advance_resolution.attempted_placement)
        )
        movement_dice_record = MovementDiceRecord(
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            advance_roll=advance_roll,
        )
        permission_grants = advance_eligibility_hooks.grants_for(
            AdvanceEligibilityContext(
                state=state,
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                movement_request_id=proposal_request.request_id,
                movement_result_id=result.result_id,
            )
        )
        state.record_advanced_unit_state(
            AdvancedUnitState(
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                movement_dice_record=movement_dice_record,
                can_shoot=any(grant.can_shoot for grant in permission_grants),
                can_declare_charge=any(grant.can_declare_charge for grant in permission_grants),
            )
        )
        if permission_grants:
            decisions.event_log.append(
                "advance_eligibility_hooks_resolved",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.MOVEMENT.value,
                    "unit_instance_id": unit_placement.unit_instance_id,
                    "request_id": proposal_request.request_id,
                    "result_id": result.result_id,
                    "grants": [
                        validate_json_value(grant.to_payload()) for grant in permission_grants
                    ],
                },
            )
        advance_grants = _apply_advance_move_grants(
            state=state,
            decisions=decisions,
            registry=advance_move_hooks,
            player_id=active_player_id,
            unit_instance_id=unit_placement.unit_instance_id,
            proposal_request=proposal_request,
            proposal_result=result,
        )
        return _request_embark_after_move_or_complete_activation(
            state=state,
            decisions=decisions,
            result=_action_result_from_proposal_request(
                proposal_request=proposal_request,
                actor_id=active_player_id,
                selected_option_id=source_selected_option_id,
                payload={
                    "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "witness": validate_json_value(submission.witness.to_payload()),
                    **advance_resolution.movement_payload,
                },
            ),
            action=MovementPhaseActionKind.ADVANCE,
            witness=submission.witness,
            movement_payload={
                **advance_resolution.movement_payload,
                "proposal_request_id": proposal_request.request_id,
                "advance_eligibility_grants": validate_json_value(
                    [grant.to_payload() for grant in permission_grants]
                ),
                "advance_move_grants": validate_json_value(
                    [grant.to_payload() for grant in advance_grants]
                ),
            },
            displacement_kind=ModelDisplacementKind.ADVANCE,
            transition_batch=transition_batch,
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
        )

    if action is MovementPhaseActionKind.FALL_BACK:
        movement_mode = _movement_mode_from_proposal_submission(
            submission=submission,
            action=action,
        )
        fall_back_mode = _fall_back_mode_from_proposal_submission(submission=submission)
        forced_desperate_escape_source_rule_ids = (
            _forced_desperate_escape_source_rule_ids_from_context(proposal_request.context or {})
        )
        fall_back_resolution = resolve_fall_back_move(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            state=state,
            movement_mode=movement_mode,
            path_witness=submission.witness,
            battle_round=state.battle_round,
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            forced_desperate_escape_source_rule_ids=forced_desperate_escape_source_rule_ids,
            objective_markers=_objective_markers_for_state(state),
            hover_mode_states=tuple(state.hover_mode_states),
            movement_bonus_inches=_movement_bonus_inches_for_unit(
                state=state,
                player_id=active_player_id,
                unit_instance_id=proposal_request.unit_instance_id,
            ),
            runtime_modifier_registry=runtime_modifier_registry,
            ability_index=ability_index,
            temporary_movement_keywords=_temporary_movement_keywords_for_unit(
                state=state,
                player_id=active_player_id,
                unit_instance_id=proposal_request.unit_instance_id,
            ),
        )
        fall_back_resolution = _fall_back_result_with_mode(
            resolution=fall_back_resolution,
            fall_back_mode=fall_back_mode,
        )
        mode_violation_code = _fall_back_mode_violation_code(
            resolution=fall_back_resolution,
            fall_back_mode=fall_back_mode,
        )
        if mode_violation_code is not None:
            return _reject_invalid_movement_resolution(
                state=state,
                decisions=decisions,
                result=result,
                unit_instance_id=proposal_request.unit_instance_id,
                action=action,
                movement_payload=fall_back_resolution.movement_payload,
                rollback_record=fall_back_resolution.rollback_record,
                violation_code=mode_violation_code,
                message="Fall Back mode is not legal for the submitted movement path.",
                proposal_request=proposal_request,
                field="fall_back_mode",
            )
        if not fall_back_resolution.is_valid:
            violation_code = _normal_move_violation_code(fall_back_resolution)
            return _reject_invalid_movement_resolution(
                state=state,
                decisions=decisions,
                result=result,
                unit_instance_id=proposal_request.unit_instance_id,
                action=action,
                movement_payload=fall_back_resolution.movement_payload,
                rollback_record=fall_back_resolution.rollback_record,
                violation_code=violation_code,
                message=_normal_move_invalid_message(violation_code).replace(
                    "Normal Move",
                    "Fall Back",
                ),
                proposal_request=proposal_request,
            )
        fall_back_result = fall_back_resolution
        if fall_back_mode is FallBackModeKind.DESPERATE_ESCAPE:
            desperate_escape_rolls = _roll_desperate_escape_dice(
                state=state,
                decisions=decisions,
                resolution=fall_back_resolution,
            )
            fall_back_result = FallBackActionResult.with_desperate_escape_rolls(
                resolution=fall_back_resolution,
                desperate_escape_rolls=desperate_escape_rolls,
            )
        action_result = _action_result_from_proposal_request(
            proposal_request=proposal_request,
            actor_id=active_player_id,
            selected_option_id=source_selected_option_id,
            payload={
                "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                "unit_instance_id": proposal_request.unit_instance_id,
                "witness": validate_json_value(submission.witness.to_payload()),
                **fall_back_result.movement_payload,
            },
        )
        if fall_back_result.failed_desperate_escape_rolls:
            request = _desperate_escape_model_selection_request(
                state=state,
                fall_back_result=fall_back_result,
                action_result=action_result,
            )
            decisions.request_decision(request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "desperate_escape_model_selection_pending",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": proposal_request.unit_instance_id,
                    "proposal_request_id": proposal_request.request_id,
                },
            )
        return _apply_fall_back_result(
            state=state,
            decisions=decisions,
            result=action_result,
            unit_placement=unit_placement,
            fall_back_result=fall_back_result,
            destroyed_model_ids=(),
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            fall_back_hooks=fall_back_hooks,
        )

    raise GameLifecycleError("Unsupported movement proposal action.")


def _action_result_from_proposal_request(
    *,
    proposal_request: MovementProposalRequest,
    actor_id: str,
    selected_option_id: str,
    payload: JsonValue,
) -> DecisionResult:
    return DecisionResult(
        result_id=proposal_request.source_decision_result_id,
        request_id=proposal_request.source_decision_request_id,
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=actor_id,
        selected_option_id=selected_option_id,
        payload=validate_json_value(payload),
    )


def _reject_invalid_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_validation: ProposalValidationResult,
    event_type: str,
    message: str,
) -> LifecycleStatus:
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": proposal_validation.status,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        }
    )
    decisions.event_log.append(event_type, payload)
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload=payload,
    )


def _reject_invalid_movement_resolution(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_instance_id: str,
    action: MovementPhaseActionKind,
    movement_payload: dict[str, JsonValue],
    rollback_record: MovementRollbackRecord | None,
    violation_code: str,
    message: str,
    proposal_request: MovementProposalRequest,
    field: str = "witness",
) -> LifecycleStatus:
    proposal_validation = ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=message,
        field=field,
    )
    invalid_payload = _movement_action_invalid_payload(
        state=state,
        active_player_id=_active_player_id(state),
        unit_instance_id=unit_instance_id,
        action=action,
        result=result,
        violation_code=violation_code,
        movement_payload={
            **movement_payload,
            "proposal_request_id": proposal_request.request_id,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        },
        rollback_record=rollback_record,
    )
    decisions.event_log.append("movement_proposal_invalid", invalid_payload)
    retry_request = _request_movement_proposal_retry(
        state=state,
        decisions=decisions,
        proposal_request=proposal_request,
        rejected_result=result,
    )
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "movement_proposal_invalid",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": unit_instance_id,
            "movement_phase_action": action.value,
            "violation_code": violation_code,
            "next_request_id": retry_request.request_id,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        },
    )


def _apply_advance_roll_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Advance reroll actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Advance reroll requires active movement selection.")

    record = decisions.record_for_result(result)
    request_payload = _decision_payload_object(record.request.payload)
    context_payload = _payload_object(request_payload, key="movement_context")
    if _payload_string(context_payload, key="movement_phase_action") != (
        MovementPhaseActionKind.ADVANCE.value
    ):
        raise GameLifecycleError("Advance reroll request context must be for Advance.")
    unit_instance_id = _payload_string(context_payload, key="unit_instance_id")
    if unit_instance_id != movement_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Advance reroll unit must match active movement selection.")
    action_request_id = _payload_string(context_payload, key="action_request_id")
    action_result_id = _payload_string(context_payload, key="action_result_id")
    initial_roll_payload = _payload_object(context_payload, key="advance_roll_state")
    advance_request_payload = _payload_object(context_payload, key="advance_roll_request")
    advance_request = AdvanceRollRequest.from_payload(
        cast(AdvanceRollRequestPayload, advance_request_payload)
    )
    initial_roll_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, initial_roll_payload)
    )
    dice_manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    rerolled_state = dice_manager.resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )
    advance_roll = AdvanceRollResult.from_roll_state(
        request=advance_request,
        roll_state=rerolled_state,
    )
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    movement_mode = _movement_mode_from_payload(
        payload=context_payload,
        action=MovementPhaseActionKind.ADVANCE,
    )
    action_result = DecisionResult(
        result_id=action_result_id,
        request_id=action_request_id,
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=active_player_id,
        selected_option_id=_payload_string(context_payload, key="action_selected_option_id"),
        payload={
            "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
            "unit_instance_id": unit_instance_id,
            "movement_mode": movement_mode.value,
        },
    )
    return _resolve_and_apply_advance_move(
        state=state,
        decisions=decisions,
        result=action_result,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        advance_roll=advance_roll,
        movement_mode=movement_mode,
        selected_advance_move_grants=_advance_move_grants_from_context(context_payload),
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
    )


def _resolve_and_apply_advance_move(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    advance_roll: AdvanceRollResult,
    movement_mode: MovementMode,
    selected_advance_move_grants: tuple[AdvanceMoveGrant, ...],
    reaction_queue: ReactionQueue | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
) -> LifecycleStatus | None:
    _record_advance_roll_resolved_event(
        state=state,
        decisions=decisions,
        advance_roll=advance_roll,
    )
    return _request_movement_proposal(
        state=state,
        decisions=decisions,
        result=result,
        unit_instance_id=unit_placement.unit_instance_id,
        action=MovementPhaseActionKind.ADVANCE,
        proposal_kind=ProposalKind.ADVANCE,
        context={
            "advance_roll": validate_json_value(advance_roll.to_payload()),
            "movement_mode": movement_mode.value,
            "selected_movement_action_grant_hook_ids": [
                grant.hook_id for grant in selected_advance_move_grants
            ],
            "selected_movement_action_grants": validate_json_value(
                [grant.to_payload() for grant in selected_advance_move_grants]
            ),
        },
    )


def _advance_move_grants_from_context(
    context: dict[str, JsonValue],
) -> tuple[AdvanceMoveGrant, ...]:
    value = context.get("selected_movement_action_grants")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GameLifecycleError("selected_movement_action_grants must be a list.")
    grants: list[AdvanceMoveGrant] = []
    seen_hook_ids: set[str] = set()
    for item in value:
        if not isinstance(item, dict):
            raise GameLifecycleError("selected_movement_action_grants must contain objects.")
        grant = AdvanceMoveGrant.from_payload(cast(AdvanceMoveGrantPayload, item))
        if grant.hook_id in seen_hook_ids:
            raise GameLifecycleError("selected_movement_action_grants must not contain duplicates.")
        seen_hook_ids.add(grant.hook_id)
        grants.append(grant)
    return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _selected_advance_move_grant_hook_ids_from_context(
    context: dict[str, JsonValue],
) -> tuple[str, ...]:
    value = context.get("selected_movement_action_grant_hook_ids")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GameLifecycleError("selected_movement_action_grant_hook_ids must be a list.")
    hook_ids: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError("selected_movement_action_grant_hook_ids must be strings.")
        hook_ids.append(item)
    return tuple(
        sorted(
            _validate_identifier_tuple(
                "selected_movement_action_grant_hook_ids",
                tuple(hook_ids),
            )
        )
    )


def _apply_advance_move_grants(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: AdvanceMoveHookRegistry,
    player_id: str,
    unit_instance_id: str,
    proposal_request: MovementProposalRequest,
    proposal_result: DecisionResult,
) -> tuple[AdvanceMoveGrant, ...]:
    if type(registry) is not AdvanceMoveHookRegistry:
        raise GameLifecycleError("Advance grants require an AdvanceMoveHookRegistry.")
    if type(proposal_request) is not MovementProposalRequest:
        raise GameLifecycleError("Advance grants require a MovementProposalRequest.")
    if type(proposal_result) is not DecisionResult:
        raise GameLifecycleError("Advance grants require a DecisionResult.")
    grants = _advance_move_grants_from_context(proposal_request.context or {})
    if not grants:
        return ()
    selected_hook_ids = _selected_advance_move_grant_hook_ids_from_context(
        proposal_request.context or {}
    )
    if selected_hook_ids != tuple(grant.hook_id for grant in grants):
        raise GameLifecycleError("Advance move grant context hook IDs drift.")
    for grant in grants:
        _grant_ranged_weapon_keywords(grant)
    decisions.event_log.append(
        "advance_move_hooks_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_instance_id,
            "proposal_request_id": proposal_request.request_id,
            "proposal_result_id": proposal_result.result_id,
            "grants": validate_json_value([grant.to_payload() for grant in grants]),
            "persisting_effects": [],
        },
    )
    return grants


def _grant_ranged_weapon_keywords(grant: AdvanceMoveGrant) -> tuple[WeaponKeyword, ...]:
    if type(grant) is not AdvanceMoveGrant:
        raise GameLifecycleError("Advance grant keyword conversion requires a grant.")
    keywords: list[WeaponKeyword] = []
    for raw_keyword in grant.granted_ranged_weapon_keywords:
        if raw_keyword == WeaponKeyword.ASSAULT.value:
            keywords.append(WeaponKeyword.ASSAULT)
            continue
        raise GameLifecycleError("Advance grant contains unsupported ranged weapon keyword.")
    return tuple(sorted(keywords, key=lambda keyword: keyword.value))


def _aircraft_reserve_transition_reason_for_normal_move(
    *,
    resolution: NormalMoveResolution,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> AircraftReserveTransitionReason | None:
    if type(resolution) is not NormalMoveResolution:
        raise GameLifecycleError("Aircraft reserve transition requires NormalMoveResolution.")
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Aircraft reserve transition requires a BattlefieldScenario.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Aircraft reserve transition requires a UnitPlacement.")
    policy_payload = resolution.movement_payload.get("aircraft_movement_policy")
    if policy_payload is None:
        return None
    policy = AircraftMovementPolicy.from_payload(
        cast(
            AircraftMovementPolicyPayload,
            _validate_json_object("aircraft policy", policy_payload),
        )
    )
    if not policy.uses_aircraft_rules:
        return None
    violation_codes = {
        violation.violation_code
        for path_result in resolution.path_validation_results
        for violation in path_result.violations
    }
    if "battlefield_edge_crossed" in violation_codes:
        return AircraftReserveTransitionReason.BATTLEFIELD_EDGE_CROSSED
    return None


def _apply_aircraft_reserve_transition_for_normal_move(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    resolution: NormalMoveResolution,
    witness: PathWitness,
    reason: AircraftReserveTransitionReason,
) -> None:
    transition = resolve_aircraft_reserve_transition(
        scenario=_battlefield_scenario(state),
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        battle_round=state.battle_round,
        reason=reason,
        source_event_id=result.result_id,
        hover_mode_state=state.hover_mode_state_for_unit(unit_placement.unit_instance_id),
    )
    if not transition.is_valid:
        raise GameLifecycleError("Aircraft reserve transition must be valid for lifecycle apply.")
    if transition.reserve_state is None or transition.transition_batch is None:
        raise GameLifecycleError("Aircraft reserve transition requires mutation data.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Aircraft reserve transition requires battlefield_state.")
    state.replace_battlefield_state(
        apply_aircraft_reserve_transition_to_battlefield(
            battlefield_state=battlefield_state,
            transition=transition,
        )
    )
    if state.reserve_state_for_unit(transition.reserve_state.unit_instance_id) is None:
        state.record_reserve_state(transition.reserve_state)
    else:
        state.replace_reserve_state(transition.reserve_state)
    _complete_movement_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.NORMAL_MOVE,
        witness=witness,
        movement_payload={
            **resolution.movement_payload,
            "aircraft_reserve_transition": validate_json_value(transition.to_payload()),
        },
        displacement_kind=None,
        transition_batch=transition.transition_batch,
    )
