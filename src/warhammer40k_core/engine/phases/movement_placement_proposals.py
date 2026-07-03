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
    from warhammer40k_core.engine.phases.movement_action_decisions import _request_movement_action, _apply_movement_action_decision, _request_advance_move_grant_decision_if_available, _decline_advance_move_grant_option, _advance_move_grant_option, _apply_advance_move_grant_decision, _assert_advance_move_grant_still_available, _record_movement_action_grant_effects, _movement_action_grant_unit_effect_target_ids, _movement_action_grant_effect_expiration, _resolve_pending_movement_action_after_grants, _resolve_pending_advance_action, _request_pending_movement_action_proposal, _request_movement_proposal, _forced_desperate_escape_sources_for_unit, _forced_desperate_escape_source_rule_ids_from_context, _request_movement_proposal_retry
    from warhammer40k_core.engine.phases.movement_resolution_flow import _apply_movement_proposal_decision, _action_result_from_proposal_request, _reject_invalid_proposal, _reject_invalid_movement_resolution, _apply_advance_roll_reroll_decision, _resolve_and_apply_advance_move, _advance_move_grants_from_context, _selected_advance_move_grant_hook_ids_from_context, _apply_advance_move_grants, _grant_ranged_weapon_keywords, _aircraft_reserve_transition_reason_for_normal_move, _apply_aircraft_reserve_transition_for_normal_move
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_desperate_escape_model_selection_decision, _apply_fall_back_result, _request_embark_after_move_or_complete_activation, _complete_activation_then_request_post_normal_disembark_if_available, _post_move_embark_options, _apply_embark_transport_selection_decision, _apply_valid_embark, _complete_movement_activation, _complete_movement_activation_with_record_ids, _maximum_model_distance_inches_from_witness, _interrupt_started_mission_actions_for_movement_activation
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_apply_placement_proposal_decision",
    "_apply_valid_combat_disembark",
    "_apply_valid_disembark",
    "_key_error_field",
    "_missing_disembark_proposal_field",
    "_parse_movement_proposal_submission_or_invalid",
    "_parse_placement_proposal_submission_or_invalid",
    "_proposal_payload_parse_failure",
)


def _parse_movement_proposal_submission_or_invalid(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> _MovementProposalParseResult:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    try:
        submission = MovementProposalPayload.from_payload(
            cast(MovementProposalPayloadPayload, _decision_payload_object(result.payload))
        )
    except (GameLifecycleError, GeometryError, KeyError, TypeError) as exc:
        return _reject_invalid_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=_proposal_payload_parse_failure(
                proposal_request=proposal_request,
                error=exc,
                default_field="witness",
            ),
            event_type="movement_proposal_invalid",
            message="Movement proposal payload is malformed.",
        )
    return (proposal_request, submission)


def _parse_placement_proposal_submission_or_invalid(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> _PlacementProposalParseResult:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    try:
        submission = PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, _decision_payload_object(result.payload))
        )
    except (GameLifecycleError, GeometryError, PlacementError, KeyError, TypeError) as exc:
        return _reject_invalid_proposal(
            state=state,
            decisions=decisions,
            result=result,
            proposal_validation=_proposal_payload_parse_failure(
                proposal_request=proposal_request,
                error=exc,
                default_field="attempted_placement",
            ),
            event_type="placement_proposal_invalid",
            message="Placement proposal payload is malformed.",
        )
    return (proposal_request, submission)


def _proposal_payload_parse_failure(
    *,
    proposal_request: MovementProposalRequest,
    error: GameLifecycleError | GeometryError | PlacementError | KeyError | TypeError,
    default_field: str,
) -> ProposalValidationResult:
    violation_code = "proposal_payload_malformed"
    field: str | None = default_field
    if type(error) is KeyError:
        missing = _key_error_field(error)
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="proposal_payload_missing_field",
            message=f"Proposal payload missing required field: {missing}.",
            field=missing,
        )
    message = str(error)
    if "Unsupported ProposalKind token" in message:
        violation_code = "unsupported_proposal_kind"
        field = "proposal_kind"
    elif "proposal_kind" in message:
        field = "proposal_kind"
    elif "movement_mode" in message or "MovementMode" in message:
        field = "movement_mode"
    elif "fall_back_mode" in message or "FallBackModeKind" in message:
        field = "fall_back_mode"
    elif "witness" in message or "PathWitness" in message:
        field = "witness"
    elif "attempted_placement" in message or "UnitPlacement" in message:
        field = "attempted_placement"
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=f"Proposal payload is malformed: {message}",
        field=field,
    )


def _key_error_field(error: KeyError) -> str:
    if len(error.args) != 1:
        return "payload"
    key = error.args[0]
    if type(key) is str and key.strip():
        return key.strip()
    return "payload"


def _apply_placement_proposal_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    reserve_arrival_distance_hooks: ReserveArrivalDistanceHookRegistry,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Placement proposal actor must be the active player.")
    record = decisions.record_for_result(result)
    parsed = _parse_placement_proposal_submission_or_invalid(
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
            event_type="placement_proposal_invalid",
            message="Placement proposal does not match the pending request.",
        )

    if proposal_request.proposal_kind in (
        ProposalKind.REINFORCEMENT,
        ProposalKind.DEEP_STRIKE,
        ProposalKind.STRATEGIC_RESERVES,
    ):
        status = _resolve_reinforcement_placement_submission(
            state=state,
            result=result,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            reserve_arrival_distance_hooks=reserve_arrival_distance_hooks,
            unit_instance_id=submission.unit_instance_id,
            placement_kind=submission.placement_kind,
            attempted_placement=submission.attempted_placement,
            large_model_exceptions=submission.large_model_exceptions,
        )
        if (
            status is not None
            and status.status_kind is LifecycleStatusKind.INVALID
            and proposal_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        ):
            _request_placement_proposal_retry(
                state=state,
                decisions=decisions,
                proposal_request=proposal_request,
                rejected_result=result,
            )
        return status

    if proposal_request.proposal_kind is ProposalKind.DISEMBARK:
        missing = _missing_disembark_proposal_field(submission)
        if missing is not None:
            return _reject_invalid_proposal(
                state=state,
                decisions=decisions,
                result=result,
                proposal_validation=ProposalValidationResult.invalid(
                    proposal_request_id=proposal_request.request_id,
                    proposal_kind=proposal_request.proposal_kind,
                    violation_code="proposal_payload_missing_field",
                    message=f"Disembark placement proposal missing {missing}.",
                    field=missing,
                ),
                event_type="placement_proposal_invalid",
                message="Disembark placement proposal is incomplete.",
            )
        if (
            submission.transport_unit_instance_id is None
            or submission.disembark_mode is None
            or submission.transport_movement_status is None
        ):
            raise GameLifecycleError("Complete Disembark placement submission drifted.")
        status = _resolve_disembark_placement_submission(
            state=state,
            result=result,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            unit_instance_id=submission.unit_instance_id,
            transport_unit_instance_id=submission.transport_unit_instance_id,
            attempted_placement=submission.attempted_placement,
            disembark_mode=submission.disembark_mode,
            transport_movement_status=submission.transport_movement_status,
            restriction_overrides=submission.restriction_overrides,
        )
        if (
            status is not None
            and status.status_kind is LifecycleStatusKind.INVALID
            and proposal_request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        ):
            _request_placement_proposal_retry(
                state=state,
                decisions=decisions,
                proposal_request=proposal_request,
                rejected_result=result,
            )
        return status

    raise GameLifecycleError("Unsupported placement proposal kind.")


def _missing_disembark_proposal_field(submission: PlacementProposalPayload) -> str | None:
    if submission.transport_unit_instance_id is None:
        return "transport_unit_instance_id"
    if submission.disembark_mode is None:
        return "disembark_mode"
    if submission.transport_movement_status is None:
        return "transport_movement_status"
    return None


def _apply_valid_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    disembark: DisembarkResolution,
    result: DecisionResult,
) -> None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Disembark placement requires battlefield_state.")
    if disembark.updated_cargo_state is None or disembark.disembarked_unit_state is None:
        raise GameLifecycleError("Valid DisembarkResolution requires state records.")
    state.replace_battlefield_state(
        apply_disembark_to_battlefield(
            battlefield_state=battlefield_state,
            disembark=disembark,
        )
    )
    state.replace_transport_cargo_state(disembark.updated_cargo_state)
    state.record_disembarked_unit_state(disembark.disembarked_unit_state)
    if disembark.selection.disembark_mode is DisembarkModeKind.RAPID_DISEMBARK:
        movement_state = state.movement_phase_state
        if movement_state is None:
            raise GameLifecycleError("Post-move Disembark requires movement_phase_state.")
        state.replace_movement_phase_state(
            movement_state.with_post_normal_move_disembark_counted_as_moved(
                disembark.selection.unit_instance_id
            )
        )
    decisions.event_log.append(
        "unit_disembarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": disembark.selection.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": disembark.selection.unit_instance_id,
            "transport_unit_instance_id": disembark.selection.transport_unit_instance_id,
            "disembark_mode": disembark.selection.disembark_mode.value,
            "transport_movement_status": disembark.selection.transport_movement_status.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_disembarked",
            "updated_cargo_state": validate_json_value(disembark.updated_cargo_state.to_payload()),
            "disembarked_unit_state": validate_json_value(
                disembark.disembarked_unit_state.to_payload()
            ),
            "transition_batch": validate_json_value(disembark.transition_batch.to_payload())
            if disembark.transition_batch is not None
            else None,
        },
    )


def _apply_valid_combat_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    combat_disembark: CombatDisembark,
    tactical_resolution: DisembarkResolution,
    result: DecisionResult,
) -> LifecycleStatus | None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Combat Disembark placement requires battlefield_state.")
    disembark = combat_disembark.placement
    if disembark.updated_cargo_state is None or disembark.disembarked_unit_state is None:
        raise GameLifecycleError("Valid Combat Disembark requires state records.")
    state.replace_battlefield_state(
        apply_combat_disembark_to_battlefield(
            battlefield_state=battlefield_state,
            disembark=combat_disembark,
        )
    )
    state.replace_transport_cargo_state(disembark.updated_cargo_state)
    state.record_disembarked_unit_state(disembark.disembarked_unit_state)
    movement_state = state.movement_phase_state
    if movement_state is None:
        raise GameLifecycleError("Combat Disembark requires movement_phase_state.")
    state.replace_movement_phase_state(
        movement_state.with_post_normal_move_disembark_counted_as_moved(
            disembark.selection.unit_instance_id
        )
    )
    decisions.event_log.append(
        "unit_disembarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": disembark.selection.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": disembark.selection.unit_instance_id,
            "transport_unit_instance_id": disembark.selection.transport_unit_instance_id,
            "disembark_mode": disembark.selection.disembark_mode.value,
            "transport_movement_status": disembark.selection.transport_movement_status.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_disembarked",
            "updated_cargo_state": validate_json_value(disembark.updated_cargo_state.to_payload()),
            "disembarked_unit_state": validate_json_value(
                disembark.disembarked_unit_state.to_payload()
            ),
            "transition_batch": validate_json_value(disembark.transition_batch.to_payload())
            if disembark.transition_batch is not None
            else None,
            "tactical_fallback_violations": [
                validate_json_value(violation.to_payload())
                for violation in tactical_resolution.violations
            ],
        },
    )
    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=decisions,
        disembark=combat_disembark,
        dice_manager=_dice_roll_manager_for_state(state=state, decisions=decisions),
    )
    if routed.pending_mortal_wound_request is not None:
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=routed.pending_mortal_wound_request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "battle_round": state.battle_round,
                "active_player_id": disembark.selection.player_id,
                "unit_instance_id": disembark.selection.unit_instance_id,
                "transport_unit_instance_id": disembark.selection.transport_unit_instance_id,
                "disembark_mode": disembark.selection.disembark_mode.value,
                "decision_type": routed.pending_mortal_wound_request.decision_type,
                "phase_body_status": "transport_hazard_feel_no_pain_required",
            },
        )
    return None
