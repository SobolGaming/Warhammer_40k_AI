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
    from warhammer40k_core.engine.phases.movement_resolution_flow import _apply_movement_proposal_decision, _action_result_from_proposal_request, _reject_invalid_proposal, _reject_invalid_movement_resolution, _apply_advance_roll_reroll_decision, _resolve_and_apply_advance_move, _advance_move_grants_from_context, _selected_advance_move_grant_hook_ids_from_context, _apply_advance_move_grants, _grant_ranged_weapon_keywords, _aircraft_reserve_transition_reason_for_normal_move, _apply_aircraft_reserve_transition_for_normal_move
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_desperate_escape_model_selection_decision, _apply_fall_back_result, _request_embark_after_move_or_complete_activation, _complete_activation_then_request_post_normal_disembark_if_available, _post_move_embark_options, _apply_embark_transport_selection_decision, _apply_valid_embark, _complete_movement_activation, _complete_movement_activation_with_record_ids, _maximum_model_distance_inches_from_witness, _interrupt_started_mission_actions_for_movement_activation
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_advance_move_grant_option",
    "_apply_advance_move_grant_decision",
    "_apply_movement_action_decision",
    "_assert_advance_move_grant_still_available",
    "_decline_advance_move_grant_option",
    "_forced_desperate_escape_source_rule_ids_from_context",
    "_forced_desperate_escape_sources_for_unit",
    "_movement_action_grant_effect_expiration",
    "_movement_action_grant_unit_effect_target_ids",
    "_record_movement_action_grant_effects",
    "_request_advance_move_grant_decision_if_available",
    "_request_movement_action",
    "_request_movement_proposal",
    "_request_movement_proposal_retry",
    "_request_pending_movement_action_proposal",
    "_resolve_pending_advance_action",
    "_resolve_pending_movement_action_after_grants",
)


def _request_movement_action(
    *,
    state: GameState,
    decisions: DecisionController,
    active_selection: MovementUnitSelection,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus:
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        active_selection.unit_instance_id
    )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": active_selection.unit_instance_id,
        },
        options=_movement_action_options(
            scenario=scenario,
            unit_placement=unit_placement,
            ruleset_descriptor=ruleset_descriptor,
            battle_round=state.battle_round,
            hover_mode_states=tuple(state.hover_mode_states),
            battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
            objective_markers=_objective_markers_for_state(state),
            disembarked_unit_state=state.disembarked_unit_state_for_unit(
                player_id=_active_player_id(state),
                battle_round=state.battle_round,
                unit_instance_id=active_selection.unit_instance_id,
            ),
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": active_selection.unit_instance_id,
            "legal_action_count": len(request.options),
        },
    )


def _apply_movement_action_decision(  # noqa: RET503
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    advance_move_hooks: AdvanceMoveHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Movement action actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement action requires active movement selection.")

    active_selection = movement_state.active_selection
    payload = _decision_payload_object(result.payload)
    action = movement_phase_action_kind_from_token(
        _payload_string(payload, key="movement_phase_action")
    )
    if _payload_string(payload, key="unit_instance_id") != active_selection.unit_instance_id:
        raise GameLifecycleError("Movement action unit_instance_id must match active_selection.")

    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        active_selection.unit_instance_id
    )
    availability_result = _movement_action_availability_result(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=tuple(state.hover_mode_states),
    )
    if not availability_result.is_available(action):
        raise GameLifecycleError("Movement action is not currently legal for the selected unit.")
    disembarked_state = state.disembarked_unit_state_for_unit(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=active_selection.unit_instance_id,
    )
    if disembarked_state is not None:
        if (
            action is MovementPhaseActionKind.REMAIN_STATIONARY
            and not disembarked_state.can_choose_remain_stationary
        ):
            raise GameLifecycleError("Disembarked unit cannot Remain Stationary.")
        if (
            action is not MovementPhaseActionKind.REMAIN_STATIONARY
            and not disembarked_state.can_move_further
        ):
            raise GameLifecycleError("Disembarked unit cannot move further.")

    if action is MovementPhaseActionKind.REMAIN_STATIONARY:
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=None,
            movement_payload={
                "movement_inches": 0,
                "model_movements": [],
            },
        )
        return None
    if action is MovementPhaseActionKind.NORMAL_MOVE:
        movement_mode = _movement_mode_from_payload(payload=payload, action=action)
        pending_action = PendingMovementActionSelection.from_result(
            result=result,
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=active_selection.unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=movement_mode,
            fall_back_mode=None,
        )
        movement_grant_status = _request_advance_move_grant_decision_if_available(
            state=state,
            decisions=decisions,
            unit_placement=unit_placement,
            pending_action=pending_action,
            registry=advance_move_hooks,
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if movement_grant_status is not None:
            if _is_movement_action_grant_decision_pending(movement_grant_status):
                state.replace_movement_phase_state(
                    movement_state.with_pending_action(pending_action)
                )
            return movement_grant_status
        return _request_movement_proposal(
            state=state,
            decisions=decisions,
            result=result,
            unit_instance_id=active_selection.unit_instance_id,
            action=MovementPhaseActionKind.NORMAL_MOVE,
            proposal_kind=ProposalKind.NORMAL_MOVE,
            context={"movement_mode": movement_mode.value},
        )

    if action is MovementPhaseActionKind.ADVANCE:
        movement_mode = _movement_mode_from_payload(payload=payload, action=action)
        pending_action = PendingMovementActionSelection.from_result(
            result=result,
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=active_selection.unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            movement_mode=movement_mode,
            fall_back_mode=None,
        )
        advance_grant_status = _request_advance_move_grant_decision_if_available(
            state=state,
            decisions=decisions,
            unit_placement=unit_placement,
            pending_action=pending_action,
            registry=advance_move_hooks,
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if advance_grant_status is not None:
            if _is_movement_action_grant_decision_pending(advance_grant_status):
                state.replace_movement_phase_state(
                    movement_state.with_pending_action(pending_action)
                )
            return advance_grant_status
        return _resolve_pending_advance_action(
            state=state,
            decisions=decisions,
            pending_action=pending_action,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_advance_move_grants=(),
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )

    if action is MovementPhaseActionKind.FALL_BACK:
        movement_mode = _movement_mode_from_payload(payload=payload, action=action)
        fall_back_mode = _fall_back_mode_from_payload(payload)
        pending_action = PendingMovementActionSelection.from_result(
            result=result,
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=active_selection.unit_instance_id,
            movement_phase_action=MovementPhaseActionKind.FALL_BACK,
            movement_mode=movement_mode,
            fall_back_mode=fall_back_mode,
        )
        fall_back_stratagem_status = _request_selected_to_fall_back_stratagem_if_available(
            state=state,
            decisions=decisions,
            pending_action=pending_action,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
        )
        if fall_back_stratagem_status is not None:
            state.replace_movement_phase_state(movement_state.with_pending_action(pending_action))
            return fall_back_stratagem_status
        movement_grant_status = _request_advance_move_grant_decision_if_available(
            state=state,
            decisions=decisions,
            unit_placement=unit_placement,
            pending_action=pending_action,
            registry=advance_move_hooks,
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if movement_grant_status is not None:
            if _is_movement_action_grant_decision_pending(movement_grant_status):
                state.replace_movement_phase_state(
                    movement_state.with_pending_action(pending_action)
                )
            return movement_grant_status
        return _request_movement_proposal(
            state=state,
            decisions=decisions,
            result=result,
            unit_instance_id=active_selection.unit_instance_id,
            action=MovementPhaseActionKind.FALL_BACK,
            proposal_kind=ProposalKind.FALL_BACK,
            context={
                "movement_mode": movement_mode.value,
                "fall_back_mode": fall_back_mode.value,
            },
        )


def _request_advance_move_grant_decision_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_placement: UnitPlacement,
    pending_action: PendingMovementActionSelection,
    registry: AdvanceMoveHookRegistry,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    if type(pending_action) is not PendingMovementActionSelection:
        raise GameLifecycleError("Movement action grant decision requires a pending action.")
    if type(registry) is not AdvanceMoveHookRegistry:
        raise GameLifecycleError("Movement action grant decision requires a hook registry.")
    grants = registry.grants_for(
        AdvanceMoveContext(
            state=state,
            player_id=pending_action.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_placement.unit_instance_id,
            movement_phase_action=pending_action.movement_phase_action.value,
            movement_request_id=pending_action.request_id,
            movement_result_id=pending_action.result_id,
        )
    )
    if not grants:
        return None
    automatic_grants = tuple(grant for grant in grants if grant.automatic)
    optional_grants = tuple(grant for grant in grants if not grant.automatic)
    if not optional_grants:
        persisting_effects = tuple(
            effect
            for grant in automatic_grants
            for effect in _record_movement_action_grant_effects(
                state=state,
                player_id=pending_action.player_id,
                unit_instance_id=pending_action.unit_instance_id,
                source_request_id=pending_action.request_id,
                source_result_id=pending_action.result_id,
                grant=grant,
            )
        )
        decisions.event_log.append(
            "advance_move_grants_auto_selected",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": pending_action.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": unit_placement.unit_instance_id,
                "movement_phase_action": pending_action.movement_phase_action.value,
                "source_decision_request_id": pending_action.request_id,
                "source_decision_result_id": pending_action.result_id,
                "selected_grants": validate_json_value(
                    [grant.to_payload() for grant in automatic_grants]
                ),
                "persisting_effects": validate_json_value(
                    [effect.to_payload() for effect in persisting_effects]
                ),
            },
        )
        return _resolve_pending_movement_action_after_grants(
            state=state,
            decisions=decisions,
            pending_action=pending_action,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_advance_move_grants=automatic_grants,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
        actor_id=pending_action.player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": pending_action.player_id,
            "unit_instance_id": unit_placement.unit_instance_id,
            "movement_phase_action": pending_action.movement_phase_action.value,
            "movement_mode": pending_action.movement_mode.value,
            "source_decision_request_id": pending_action.request_id,
            "source_decision_result_id": pending_action.result_id,
            "available_grants": validate_json_value([grant.to_payload() for grant in grants]),
        },
        options=(
            _decline_advance_move_grant_option(
                pending_action=pending_action,
                automatic_grants=automatic_grants,
            ),
            *tuple(
                _advance_move_grant_option(
                    pending_action=pending_action,
                    grant=grant,
                    automatic_grants=automatic_grants,
                )
                for grant in optional_grants
            ),
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "advance_move_grant_decision_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": pending_action.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_placement.unit_instance_id,
            "movement_phase_action": pending_action.movement_phase_action.value,
            "request_id": request.request_id,
            "source_decision_request_id": pending_action.request_id,
            "source_decision_result_id": pending_action.result_id,
            "available_grants": validate_json_value([grant.to_payload() for grant in grants]),
            "phase_body_status": "movement_action_grant_decision_pending",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "movement_action_grant_decision_pending",
            "battle_round": state.battle_round,
            "active_player_id": pending_action.player_id,
            "unit_instance_id": unit_placement.unit_instance_id,
        },
    )


def _is_movement_action_grant_decision_pending(status: LifecycleStatus) -> bool:
    if type(status) is not LifecycleStatus:
        raise GameLifecycleError("Movement action grant status requires LifecycleStatus.")
    payload = status.payload
    return (
        isinstance(payload, dict)
        and payload.get("phase_body_status") == "movement_action_grant_decision_pending"
    )


def _decline_advance_move_grant_option(
    *,
    pending_action: PendingMovementActionSelection,
    automatic_grants: tuple[AdvanceMoveGrant, ...] = (),
) -> DecisionOption:
    return DecisionOption(
        option_id=DECLINE_ADVANCE_MOVE_GRANT_OPTION_ID,
        label="Decline Movement Action Grant",
        payload={
            "submission_kind": SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
            "unit_instance_id": pending_action.unit_instance_id,
            "movement_phase_action": pending_action.movement_phase_action.value,
            "movement_mode": pending_action.movement_mode.value,
            "source_decision_request_id": pending_action.request_id,
            "source_decision_result_id": pending_action.result_id,
            "selected_movement_action_grants": validate_json_value(
                [grant.to_payload() for grant in automatic_grants]
            ),
        },
    )


def _advance_move_grant_option(
    *,
    pending_action: PendingMovementActionSelection,
    grant: AdvanceMoveGrant,
    automatic_grants: tuple[AdvanceMoveGrant, ...] = (),
) -> DecisionOption:
    selected_grants = tuple(sorted((*automatic_grants, grant), key=lambda item: item.hook_id))
    return DecisionOption(
        option_id=grant.hook_id,
        label=grant.label,
        payload={
            "submission_kind": SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE,
            "unit_instance_id": pending_action.unit_instance_id,
            "movement_phase_action": pending_action.movement_phase_action.value,
            "movement_mode": pending_action.movement_mode.value,
            "source_decision_request_id": pending_action.request_id,
            "source_decision_result_id": pending_action.result_id,
            "selected_movement_action_grants": validate_json_value(
                [selected_grant.to_payload() for selected_grant in selected_grants]
            ),
        },
    )


def _apply_advance_move_grant_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    advance_move_hooks: AdvanceMoveHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Advance move grant actor must be the active player.")
    movement_state = state.movement_phase_state
    if (
        movement_state is None
        or movement_state.active_selection is None
        or movement_state.pending_action is None
    ):
        raise GameLifecycleError("Movement action grant decision requires a pending action.")
    pending_action = movement_state.pending_action
    payload = _decision_payload_object(result.payload)
    if _payload_string(payload, key="submission_kind") != SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE:
        raise GameLifecycleError("Movement action grant payload has invalid submission_kind.")
    if _payload_string(payload, key="unit_instance_id") != pending_action.unit_instance_id:
        raise GameLifecycleError("Movement action grant unit drift.")
    if _payload_string(payload, key="source_decision_request_id") != pending_action.request_id:
        raise GameLifecycleError("Movement action grant source request drift.")
    if _payload_string(payload, key="source_decision_result_id") != pending_action.result_id:
        raise GameLifecycleError("Movement action grant source result drift.")
    if (
        _payload_string(payload, key="movement_phase_action")
        != pending_action.movement_phase_action.value
    ):
        raise GameLifecycleError("Movement action grant action drift.")
    movement_mode = _movement_mode_from_payload(
        payload=payload,
        action=pending_action.movement_phase_action,
    )
    if movement_mode is not pending_action.movement_mode:
        raise GameLifecycleError("Movement action grant movement mode drift.")

    selected_grants = _advance_move_grants_from_context(payload)
    optional_selected_grants = tuple(grant for grant in selected_grants if not grant.automatic)
    if result.selected_option_id == DECLINE_ADVANCE_MOVE_GRANT_OPTION_ID:
        if optional_selected_grants:
            raise GameLifecycleError(
                "Declined movement action grant cannot carry optional selected grants."
            )
    else:
        if len(optional_selected_grants) != 1:
            raise GameLifecycleError(
                "Movement action grant selection must carry one optional grant."
            )
        if optional_selected_grants[0].hook_id != result.selected_option_id:
            raise GameLifecycleError("Movement action grant selected option drift.")
    for selected_grant in selected_grants:
        _assert_advance_move_grant_still_available(
            state=state,
            pending_action=pending_action,
            selected_grant=selected_grant,
            registry=advance_move_hooks,
        )

    persisting_effects = tuple(
        effect
        for grant in selected_grants
        for effect in _record_movement_action_grant_effects(
            state=state,
            player_id=active_player_id,
            unit_instance_id=pending_action.unit_instance_id,
            source_request_id=result.request_id,
            source_result_id=result.result_id,
            grant=grant,
        )
    )
    state.replace_movement_phase_state(movement_state.without_pending_action())
    decisions.event_log.append(
        "movement_action_grant_decision_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": pending_action.unit_instance_id,
            "movement_phase_action": pending_action.movement_phase_action.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "selected_option_id": result.selected_option_id,
            "selected_grants": validate_json_value(
                [grant.to_payload() for grant in selected_grants]
            ),
            "persisting_effects": validate_json_value(
                [effect.to_payload() for effect in persisting_effects]
            ),
        },
    )

    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(
        pending_action.unit_instance_id
    )
    return _resolve_pending_movement_action_after_grants(
        state=state,
        decisions=decisions,
        pending_action=pending_action,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        selected_advance_move_grants=selected_grants,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def _assert_advance_move_grant_still_available(
    *,
    state: GameState,
    pending_action: PendingMovementActionSelection,
    selected_grant: AdvanceMoveGrant,
    registry: AdvanceMoveHookRegistry,
) -> None:
    current_grants = registry.grants_for(
        AdvanceMoveContext(
            state=state,
            player_id=pending_action.player_id,
            battle_round=state.battle_round,
            unit_instance_id=pending_action.unit_instance_id,
            movement_phase_action=pending_action.movement_phase_action.value,
            movement_request_id=pending_action.request_id,
            movement_result_id=pending_action.result_id,
        )
    )
    for current_grant in current_grants:
        if current_grant == selected_grant:
            return
    raise GameLifecycleError("Advance move grant selection is no longer available.")


def _record_movement_action_grant_effects(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    source_request_id: str,
    source_result_id: str,
    grant: AdvanceMoveGrant,
) -> tuple[PersistingEffect, ...]:
    source_request_id = _validate_identifier("source_request_id", source_request_id)
    source_result_id = _validate_identifier("source_result_id", source_result_id)
    effects: list[PersistingEffect] = []
    if grant.decision_effect_payload is not None:
        resource_spend_result = apply_faction_resource_spend_effect(
            state=state,
            player_id=player_id,
            source_id=f"{grant.source_id}:{source_request_id}:{source_result_id}:spend",
            effect_payload=grant.decision_effect_payload,
        )
        spend_effect = PersistingEffect(
            effect_id=f"{grant.hook_id}:{source_request_id}:{source_result_id}:decision",
            source_rule_id=grant.source_id,
            owner_player_id=player_id,
            target_unit_instance_ids=(unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.MOVEMENT,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=faction_resource_result_enriched_payload(
                effect_payload=grant.decision_effect_payload,
                result=resource_spend_result,
            ),
        )
        state.record_persisting_effect(spend_effect)
        effects.append(spend_effect)
    if grant.unit_effect_payload is not None:
        unit_effect = PersistingEffect(
            effect_id=f"{grant.hook_id}:{source_request_id}:{source_result_id}:unit",
            source_rule_id=grant.source_id,
            owner_player_id=player_id,
            target_unit_instance_ids=_movement_action_grant_unit_effect_target_ids(
                unit_instance_id=unit_instance_id,
                effect_payload=grant.unit_effect_payload,
            ),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.MOVEMENT,
            expiration=_movement_action_grant_effect_expiration(
                state=state,
                player_id=player_id,
                expiration=grant.unit_effect_expiration,
            ),
            effect_payload=grant.unit_effect_payload,
        )
        state.record_persisting_effect(unit_effect)
        effects.append(unit_effect)
    return tuple(effects)


def _movement_action_grant_unit_effect_target_ids(
    *,
    unit_instance_id: str,
    effect_payload: JsonValue,
) -> tuple[str, ...]:
    if not isinstance(effect_payload, dict):
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    if raw_target_ids is None:
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Movement action grant target_unit_instance_ids must be a list.")
    target_ids = tuple(
        _validate_identifier("target_unit_instance_ids", raw_id) for raw_id in raw_target_ids
    )
    if not target_ids:
        raise GameLifecycleError("Movement action grant target_unit_instance_ids is empty.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Movement action grant target_unit_instance_ids are duplicated.")
    return target_ids


def _movement_action_grant_effect_expiration(
    *,
    state: GameState,
    player_id: str,
    expiration: str | None,
) -> EffectExpiration:
    if expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
            player_id=player_id,
        )
    if expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=player_id,
        )
    raise GameLifecycleError("Movement action grant effect expiration is missing.")


def _resolve_pending_movement_action_after_grants(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    selected_advance_move_grants: tuple[AdvanceMoveGrant, ...],
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    if pending_action.movement_phase_action is MovementPhaseActionKind.NORMAL_MOVE:
        return _request_movement_proposal(
            state=state,
            decisions=decisions,
            result=pending_action.to_decision_result(),
            unit_instance_id=pending_action.unit_instance_id,
            action=MovementPhaseActionKind.NORMAL_MOVE,
            proposal_kind=ProposalKind.NORMAL_MOVE,
            context={
                "movement_mode": pending_action.movement_mode.value,
                "selected_movement_action_grant_hook_ids": [
                    grant.hook_id for grant in selected_advance_move_grants
                ],
                "selected_movement_action_grants": validate_json_value(
                    [grant.to_payload() for grant in selected_advance_move_grants]
                ),
            },
        )
    if pending_action.movement_phase_action is MovementPhaseActionKind.ADVANCE:
        return _resolve_pending_advance_action(
            state=state,
            decisions=decisions,
            pending_action=pending_action,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=unit_placement,
            selected_advance_move_grants=selected_advance_move_grants,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    if pending_action.movement_phase_action is MovementPhaseActionKind.FALL_BACK:
        if pending_action.fall_back_mode is None:
            raise GameLifecycleError("Pending Fall Back action requires fall_back_mode.")
        return _request_movement_proposal(
            state=state,
            decisions=decisions,
            result=pending_action.to_decision_result(),
            unit_instance_id=pending_action.unit_instance_id,
            action=MovementPhaseActionKind.FALL_BACK,
            proposal_kind=ProposalKind.FALL_BACK,
            context={
                "movement_mode": pending_action.movement_mode.value,
                "fall_back_mode": pending_action.fall_back_mode.value,
                "selected_movement_action_grant_hook_ids": [
                    grant.hook_id for grant in selected_advance_move_grants
                ],
                "selected_movement_action_grants": validate_json_value(
                    [grant.to_payload() for grant in selected_advance_move_grants]
                ),
            },
        )
    raise GameLifecycleError("Unsupported pending movement action after grant decision.")


def _resolve_pending_advance_action(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    selected_advance_move_grants: tuple[AdvanceMoveGrant, ...],
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    if pending_action.movement_phase_action is not MovementPhaseActionKind.ADVANCE:
        raise GameLifecycleError("Pending Advance resolution requires an Advance action.")
    action_result = pending_action.to_decision_result()
    scenario = _battlefield_scenario(state)
    unit = scenario.unit_instance_for_placement(unit_placement)
    advance_roll_request = _advance_roll_request_for_action(
        state=state,
        unit=unit,
        unit_placement=unit_placement,
        action_result=action_result,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    advance_roll_state = _roll_advance_dice(
        state=state,
        decisions=decisions,
        request=advance_roll_request,
    )
    if advance_roll_request.reroll_permission is not None:
        reroll_request = _advance_roll_reroll_request(
            state=state,
            decisions=decisions,
            dice_roll_state=advance_roll_state,
            advance_roll_request=advance_roll_request,
            action_result=action_result,
            movement_mode=pending_action.movement_mode,
            selected_advance_move_grants=selected_advance_move_grants,
        )
        decisions.request_decision(reroll_request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=reroll_request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "phase_body_status": "advance_roll_reroll_pending",
                "battle_round": state.battle_round,
                "active_player_id": pending_action.player_id,
                "unit_instance_id": pending_action.unit_instance_id,
            },
        )
    advance_roll = AdvanceRollResult.from_roll_state(
        request=advance_roll_request,
        roll_state=advance_roll_state,
    )
    return _resolve_and_apply_advance_move(
        state=state,
        decisions=decisions,
        result=action_result,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        advance_roll=advance_roll,
        movement_mode=pending_action.movement_mode,
        selected_advance_move_grants=selected_advance_move_grants,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
    )


def _request_pending_movement_action_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    pending_action: PendingMovementActionSelection,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None = None,
) -> LifecycleStatus:
    if pending_action.movement_phase_action is not MovementPhaseActionKind.FALL_BACK:
        raise GameLifecycleError("Only pending Fall Back actions are supported.")
    if pending_action.fall_back_mode is None:
        raise GameLifecycleError("Pending Fall Back action requires fall_back_mode.")
    forced_sources = _forced_desperate_escape_sources_for_unit(
        state=state,
        unit_instance_id=pending_action.unit_instance_id,
        ability_indexes_by_player_id=(
            _empty_ability_indexes()
            if ability_indexes_by_player_id is None
            else ability_indexes_by_player_id
        ),
    )
    fall_back_mode = (
        FallBackModeKind.DESPERATE_ESCAPE if forced_sources else pending_action.fall_back_mode
    )
    context: dict[str, JsonValue] = {
        "movement_mode": pending_action.movement_mode.value,
        "fall_back_mode": fall_back_mode.value,
    }
    if forced_sources:
        context["declared_fall_back_mode"] = pending_action.fall_back_mode.value
        context["forced_desperate_escape_source_rule_ids"] = [
            source["source_rule_id"] for source in forced_sources
        ]
        stratagem_use_ids = [
            source["stratagem_use_id"] for source in forced_sources if "stratagem_use_id" in source
        ]
        if stratagem_use_ids:
            context["forced_desperate_escape_stratagem_use_ids"] = stratagem_use_ids
        context["forced_desperate_escape_sources"] = validate_json_value(forced_sources)
    return _request_movement_proposal(
        state=state,
        decisions=decisions,
        result=pending_action.to_decision_result(),
        unit_instance_id=pending_action.unit_instance_id,
        action=MovementPhaseActionKind.FALL_BACK,
        proposal_kind=ProposalKind.FALL_BACK,
        context=context,
    )


def _request_movement_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_instance_id: str,
    action: MovementPhaseActionKind,
    proposal_kind: ProposalKind,
    context: dict[str, JsonValue] | None = None,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    request_context: dict[str, JsonValue] = {
        "source_selected_option_id": result.selected_option_id,
    }
    if context is not None:
        request_context.update(context)
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=active_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        movement_phase_action=action.value,
        context=request_context,
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "movement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_instance_id,
            "movement_phase_action": action.value,
            "proposal_kind": proposal_kind.value,
            "request_id": request.request_id,
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "phase_body_status": "movement_proposal_required",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "movement_proposal_required",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unit_instance_id": unit_instance_id,
            "movement_phase_action": action.value,
            "proposal_kind": proposal_kind.value,
        },
    )


def _forced_desperate_escape_sources_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None = None,
) -> tuple[dict[str, JsonValue], ...]:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    sources: list[dict[str, JsonValue]] = []
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Persisting effect payload must be an object.")
        if payload.get("effect_kind") != FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND:
            continue
        fall_back_unit_id = payload.get("fall_back_unit_instance_id")
        if fall_back_unit_id != requested_unit_id:
            raise GameLifecycleError("Forced Desperate Escape effect target drift.")
        source_rule_id = payload.get("source_rule_id")
        stratagem_use_id = payload.get("stratagem_use_id")
        forcing_unit_id = payload.get("forcing_unit_instance_id")
        source_stratagem_id = payload.get("source_stratagem_id")
        required_mode = payload.get("required_fall_back_mode")
        if (
            type(source_rule_id) is not str
            or type(stratagem_use_id) is not str
            or type(forcing_unit_id) is not str
            or type(source_stratagem_id) is not str
            or required_mode != FallBackModeKind.DESPERATE_ESCAPE.value
        ):
            raise GameLifecycleError("Forced Desperate Escape effect payload is malformed.")
        sources.append(
            {
                "effect_id": effect.effect_id,
                "source_rule_id": _validate_identifier("source_rule_id", source_rule_id),
                "stratagem_use_id": _validate_identifier("stratagem_use_id", stratagem_use_id),
                "source_stratagem_id": _validate_identifier(
                    "source_stratagem_id",
                    source_stratagem_id,
                ),
                "forcing_unit_instance_id": _validate_identifier(
                    "forcing_unit_instance_id",
                    forcing_unit_id,
                ),
                "fall_back_unit_instance_id": requested_unit_id,
                "required_fall_back_mode": FallBackModeKind.DESPERATE_ESCAPE.value,
            }
        )
    if ability_indexes_by_player_id is not None:
        sources.extend(
            catalog_forced_desperate_escape_sources_for_unit(
                state=state,
                unit_instance_id=requested_unit_id,
                ability_indexes_by_player_id=ability_indexes_by_player_id,
                armies=tuple(state.army_definitions),
            )
        )
    return tuple(sorted(sources, key=lambda source: str(source["effect_id"])))


def _forced_desperate_escape_source_rule_ids_from_context(
    context: dict[str, JsonValue],
) -> tuple[str, ...]:
    value = context.get("forced_desperate_escape_source_rule_ids")
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GameLifecycleError("forced_desperate_escape_source_rule_ids must be a list.")
    source_ids: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError("forced_desperate_escape_source_rule_ids must be strings.")
        source_ids.append(_validate_identifier("forced_desperate_escape_source_rule_id", item))
    return tuple(sorted(source_ids))


def _request_movement_proposal_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    active_player_id = _active_player_id(state)
    if proposal_request.movement_phase_action is None:
        raise GameLifecycleError("Movement proposal retry requires movement_phase_action.")
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        movement_phase_action=proposal_request.movement_phase_action,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "movement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": proposal_request.unit_instance_id,
            "movement_phase_action": proposal_request.movement_phase_action,
            "proposal_kind": proposal_request.proposal_kind.value,
            "request_id": request.request_id,
            "source_decision_request_id": proposal_request.source_decision_request_id,
            "source_decision_result_id": proposal_request.source_decision_result_id,
            "previous_proposal_request_id": proposal_request.request_id,
            "rejected_result_id": rejected_result.result_id,
            "phase_body_status": "movement_proposal_required",
        },
    )
    return request
