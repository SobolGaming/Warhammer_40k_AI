# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *
from warhammer40k_core.engine.phases.movement_model import *
from warhammer40k_core.engine.phases.movement_state import *
from warhammer40k_core.engine.phases.movement_handler import *
from warhammer40k_core.engine.phases.movement_reactions import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_REINFORCEMENT_UNIT_DECISION_TYPE, SELECT_DISEMBARK_UNIT_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, COMPLETE_REINFORCEMENTS_OPTION_ID, COMPLETE_DISEMBARKS_OPTION_ID, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _begin_reinforcements_step, _complete_reinforcements_step
    from warhammer40k_core.engine.phases.movement_reactions import _request_end_opponent_movement_reaction_if_available, _request_end_movement_active_player_stratagem_if_available, _request_rapid_ingress_reaction_if_available, _request_fire_overwatch_reaction_if_available, _request_selected_to_move_stratagem_if_available, _request_selected_to_fall_back_stratagem_if_available, _request_friendly_unit_fell_back_stratagem_if_available, _friendly_unit_fell_back_context_from_event, _friendly_unit_fell_back_timing_window_id, _stratagem_used_for_context, _selected_to_fall_back_trigger_payload, _selected_to_fall_back_timing_window_id, _selected_to_move_timing_window_id, _stratagem_use_payload_factory, _stratagem_target_proposal_payload_factory, _request_movement_end_surge_if_available, _movement_end_surge_distance_roll_spec, _eligible_triggered_movement_units_from_grants, _movement_end_surge_grant_distance_bonus, _movement_end_surge_event_already_processed, _active_player_end_movement_overwatch_trigger_unit_ids, _fire_overwatch_end_movement_trigger_payload
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
    "_apply_reinforcement_unit_selection_decision",
    "_apply_valid_reinforcement_placement",
    "_deep_strike_enemy_distance_for_reserve_arrival",
    "_eligible_reinforcement_reserve_states",
    "_optional_proposal_context_string",
    "_overdue_required_reinforcement_reserve_states",
    "_reinforcement_unit_options",
    "_request_placement_proposal_retry",
    "_request_reinforcement_placement",
    "_required_reinforcement_reserve_states",
    "_reserve_placement_kinds_for_unit",
    "_reserve_proposal_kind",
    "_resolve_reinforcement_placement_submission",
    "_unit_for_reserve_state",
)


def _reinforcement_unit_options(
    reserve_states: tuple[ReserveState, ...],
    *,
    completion_allowed: bool = True,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    if completion_allowed:
        options.append(
            DecisionOption(
                option_id=COMPLETE_REINFORCEMENTS_OPTION_ID,
                label="Complete Reserve Arrivals",
                payload={
                    "reinforcement_decision": COMPLETE_REINFORCEMENTS_OPTION_ID,
                },
            )
        )
    options.extend(
        DecisionOption(
            option_id=reserve_state.unit_instance_id,
            label=f"Arrive {reserve_state.unit_instance_id}",
            payload={
                "reinforcement_decision": "select_arrival",
                "unit_instance_id": reserve_state.unit_instance_id,
                "reserve_kind": reserve_state.reserve_kind.value,
                "reserve_origin": reserve_state.reserve_origin.value,
            },
        )
        for reserve_state in reserve_states
    )
    return tuple(options)


def _eligible_reinforcement_reserve_states(*, state: GameState) -> tuple[ReserveState, ...]:
    active_player_id = _active_player_id(state)
    return tuple(
        reserve_state
        for reserve_state in state.unarrived_reserve_states_for_player(active_player_id)
        if reserve_state.arrival_is_eligible_at(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
        )
    )


def _required_reinforcement_reserve_states(*, state: GameState) -> tuple[ReserveState, ...]:
    active_player_id = _active_player_id(state)
    return tuple(
        reserve_state
        for reserve_state in state.unarrived_reserve_states_for_player(active_player_id)
        if reserve_state.arrival_is_required_at(
            battle_round=state.battle_round,
            phase=BattlePhase.MOVEMENT,
        )
    )


def _overdue_required_reinforcement_reserve_states(*, state: GameState) -> tuple[ReserveState, ...]:
    active_player_id = _active_player_id(state)
    return tuple(
        reserve_state
        for reserve_state in state.unarrived_reserve_states_for_player(active_player_id)
        if reserve_state.has_required_arrival
        and reserve_state.required_arrival_phase == BattlePhase.MOVEMENT.value
        and reserve_state.required_arrival_battle_round is not None
        and reserve_state.required_arrival_battle_round < state.battle_round
    )


def _apply_reinforcement_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Reinforcement selection actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.MOVE_UNITS:
        raise GameLifecycleError("Reinforcement selection requires Move Units step.")
    if movement_state.reinforcements_completed:
        raise GameLifecycleError("Reinforcement selection requires incomplete Move Units.")

    payload = _decision_payload_object(result.payload)
    reinforcement_decision = _payload_string(payload, key="reinforcement_decision")
    if reinforcement_decision == COMPLETE_REINFORCEMENTS_OPTION_ID:
        if _required_reinforcement_reserve_states(state=state):
            raise GameLifecycleError("Required reserve arrival cannot be skipped.")
        state.replace_movement_phase_state(movement_state.with_reinforcements_completed())
        decisions.event_log.append(
            "reserve_arrival_completion_selected",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "step": MovementPhaseStepKind.MOVE_UNITS.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "reserve_arrival_completion_selected",
            },
        )
        return None
    if reinforcement_decision != "select_arrival":
        raise GameLifecycleError("Unsupported reserve arrival selection payload.")

    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    reserve_state = state.reserve_state_for_unit(unit_instance_id)
    if reserve_state is None:
        raise GameLifecycleError("Reinforcement selection requires ReserveState.")
    if reserve_state not in _eligible_reinforcement_reserve_states(state=state):
        raise GameLifecycleError("Reinforcement selection is not currently legal.")

    decisions.event_log.append(
        "reinforcement_unit_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "unit_instance_id": unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "reinforcement_unit_selected",
        },
    )
    return _request_reinforcement_placement(
        state=state,
        decisions=decisions,
        result=result,
        reserve_state=reserve_state,
        ruleset_descriptor=ruleset_descriptor,
    )


def _request_reinforcement_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    reserve_state: ReserveState,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    scenario = _battlefield_scenario(state)
    rules_unit = _unit_for_reserve_state(
        scenario=scenario,
        reserve_state=reserve_state,
    )
    placement_kinds = _reserve_placement_kinds_for_unit(
        reserve_state=reserve_state,
        unit=rules_unit,
    )
    proposal_kind = _reserve_proposal_kind(reserve_state)
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=active_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=reserve_state.unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        placement_kinds=placement_kinds,
        context={
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "reserve_state": validate_json_value(reserve_state.to_payload()),
            "component_unit_instance_ids": list(rules_unit.component_unit_instance_ids),
            "model_instance_ids": validate_json_value(
                sorted(model.model_instance_id for model in rules_unit.alive_models())
            ),
        },
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": proposal_kind.value,
            "placement_kinds": [kind.value for kind in placement_kinds],
            "request_id": request.request_id,
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "phase_body_status": "placement_proposal_required",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "phase_body_status": "placement_proposal_required",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": proposal_kind.value,
            "placement_kinds": [kind.value for kind in placement_kinds],
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
    )


def _reserve_placement_kinds_for_unit(
    *,
    reserve_state: ReserveState,
    unit: RulesUnitView,
) -> tuple[BattlefieldPlacementKind, ...]:
    if reserve_state.required_arrival_placement_kind is not None:
        return (
            battlefield_placement_kind_from_token(reserve_state.required_arrival_placement_kind),
        )
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        kinds = [BattlefieldPlacementKind.STRATEGIC_RESERVES]
        if all(_unit_has_deep_strike_keyword(component.unit) for component in unit.components):
            kinds.append(BattlefieldPlacementKind.DEEP_STRIKE)
        return tuple(kinds)
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return (BattlefieldPlacementKind.DEEP_STRIKE,)
    return (BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,)


def _reserve_proposal_kind(reserve_state: ReserveState) -> ProposalKind:
    if reserve_state.required_arrival_placement_kind == BattlefieldPlacementKind.DEEP_STRIKE.value:
        return ProposalKind.DEEP_STRIKE
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return ProposalKind.DEEP_STRIKE
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        return ProposalKind.STRATEGIC_RESERVES
    return ProposalKind.REINFORCEMENT


def _request_placement_proposal_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    active_player_id = _active_player_id(state)
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        placement_kinds=proposal_request.placement_kinds,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    event_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": proposal_request.unit_instance_id,
        "proposal_kind": proposal_request.proposal_kind.value,
        "placement_kinds": [kind.value for kind in proposal_request.placement_kinds],
        "request_id": request.request_id,
        "source_decision_request_id": proposal_request.source_decision_request_id,
        "source_decision_result_id": proposal_request.source_decision_result_id,
        "previous_proposal_request_id": proposal_request.request_id,
        "rejected_result_id": rejected_result.result_id,
        "phase_body_status": "placement_proposal_required",
    }
    for key in (
        "step",
        "transport_unit_instance_id",
        "transport_movement_status",
    ):
        context_value = _optional_proposal_context_string(proposal_request, key=key)
        if context_value is not None:
            event_payload[key] = context_value
    decisions.event_log.append("placement_proposal_requested", event_payload)
    return request


def _optional_proposal_context_string(
    proposal_request: MovementProposalRequest,
    *,
    key: str,
) -> str | None:
    context = proposal_request.context or {}
    if key not in context:
        return None
    value = context[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Proposal request context key must be a string: {key}.")
    return value


def _resolve_reinforcement_placement_submission(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    reserve_arrival_distance_hooks: ReserveArrivalDistanceHookRegistry,
    reserve_arrival_restriction_hooks: ReserveArrivalRestrictionHookRegistry,
    unit_instance_id: str,
    placement_kind: BattlefieldPlacementKind,
    attempted_placement: RulesUnitPlacement,
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...],
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Reinforcement placement actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.MOVE_UNITS:
        raise GameLifecycleError("Reinforcement placement requires Move Units step.")
    if movement_state.reinforcements_completed:
        raise GameLifecycleError("Reinforcement placement requires incomplete Move Units.")

    reserve_state = state.reserve_state_for_unit(unit_instance_id)
    if reserve_state is None:
        raise GameLifecycleError("Reinforcement placement requires ReserveState.")
    if reserve_state not in _eligible_reinforcement_reserve_states(state=state):
        raise GameLifecycleError("Reinforcement placement is not currently legal.")
    mission_setup = _mission_setup_for_live_reinforcements(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
    )
    scenario = _battlefield_scenario(state)
    battlefield_state = scenario.battlefield_state
    enemy_deployment_zones = mission_setup.enemy_deployment_zones_for_player(
        reserve_state.player_id,
    )
    deep_strike_enemy_distance = _deep_strike_enemy_distance_for_reserve_arrival(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        placement_kind=placement_kind,
        battle_round=state.battle_round,
        battlefield_width_inches=battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        terrain_features=battlefield_state.terrain_features,
        objective_markers=_objective_markers_for_state(state),
        enemy_deployment_zones=enemy_deployment_zones,
        reserve_arrival_distance_hooks=reserve_arrival_distance_hooks,
    )
    restriction_violations = reserve_arrival_restriction_violations(
        state=state,
        scenario=scenario,
        reserve_state=reserve_state,
        rules_unit=_unit_for_reserve_state(
            scenario=scenario,
            reserve_state=reserve_state,
        ),
        attempted_rules_unit_placement=attempted_placement,
        placement_kind=placement_kind,
        registry=reserve_arrival_restriction_hooks,
    )
    placement = resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        battle_round=state.battle_round,
        placement_kind=placement_kind,
        battlefield_width_inches=battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        terrain_features=battlefield_state.terrain_features,
        objective_markers=_objective_markers_for_state(state),
        enemy_deployment_zones=enemy_deployment_zones,
        large_model_exceptions=large_model_exceptions,
        deep_strike_enemy_horizontal_distance_inches=deep_strike_enemy_distance,
        additional_violations=restriction_violations,
    )
    if not placement.is_valid:
        invalid_payload = {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "unit_instance_id": unit_instance_id,
            "placement_kind": placement_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "reinforcement_placement_invalid",
            "violations": [violation.to_payload() for violation in placement.violations],
            "coherency_result": placement.coherency_result.to_payload(),
        }
        decisions.event_log.append(
            "reinforcement_placement_invalid",
            validate_json_value(invalid_payload),
        )
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Reinforcement placement is invalid.",
            payload=validate_json_value(invalid_payload),
        )
    _apply_valid_reinforcement_placement(
        state=state,
        decisions=decisions,
        placement=placement,
        result=result,
    )
    return None


def _deep_strike_enemy_distance_for_reserve_arrival(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    reserve_state: ReserveState,
    attempted_placement: RulesUnitPlacement,
    placement_kind: BattlefieldPlacementKind,
    battle_round: int,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    enemy_deployment_zones: tuple[DeploymentZone, ...],
    reserve_arrival_distance_hooks: ReserveArrivalDistanceHookRegistry,
) -> float | None:
    if placement_kind is not BattlefieldPlacementKind.DEEP_STRIKE:
        return None
    rules_unit = _unit_for_reserve_state(scenario=scenario, reserve_state=reserve_state)
    context = ReserveArrivalDistanceContext(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        reserve_state=reserve_state,
        rules_unit=rules_unit,
        attempted_rules_unit_placement=attempted_placement,
        placement_kind=placement_kind,
        battle_round=battle_round,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
        enemy_deployment_zones=enemy_deployment_zones,
        base_enemy_horizontal_distance_inches=DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES,
    )
    return reserve_arrival_distance_hooks.effective_enemy_horizontal_distance_inches(context)


def _unit_for_reserve_state(
    *,
    scenario: BattlefieldScenario,
    reserve_state: ReserveState,
) -> RulesUnitView:
    try:
        return rules_unit_view_from_armies(
            armies=scenario.armies,
            unit_instance_id=reserve_state.unit_instance_id,
        )
    except GameLifecycleError as exc:
        raise GameLifecycleError("Reserve arrival distance hook target unit is unknown.") from exc


def _apply_valid_reinforcement_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    placement: ReinforcementPlacement,
    result: DecisionResult,
) -> None:
    if type(placement) is not ReinforcementPlacement:
        raise GameLifecycleError("Reinforcement placement mutation requires placement result.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Reinforcement placement requires battlefield_state.")
    state.replace_battlefield_state(
        apply_reinforcement_placement_to_battlefield(
            battlefield_state=battlefield_state,
            placement=placement,
        )
    )
    arrived_state = placement.arrived_reserve_state()
    state.replace_reserve_state(arrived_state)
    movement_state = state.movement_phase_state
    if movement_state is None:
        raise GameLifecycleError("Reinforcement placement requires movement phase state.")
    state.replace_movement_phase_state(
        movement_state.with_reinforcement_arrival(arrived_state.unit_instance_id)
    )
    decisions.event_log.append(
        "reinforcement_unit_arrived",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": arrived_state.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "unit_instance_id": arrived_state.unit_instance_id,
            "movement_phase_action": "set_up",
            "component_unit_instance_ids": list(
                placement.candidate.attempted_rules_unit_placement.component_unit_instance_ids
            ),
            "rules_unit_placement": validate_json_value(
                placement.candidate.attempted_rules_unit_placement.to_payload()
            ),
            "placement_kind": placement.candidate.placement_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "reinforcement_unit_arrived",
            "transition_batch": validate_json_value(placement.transition_batch.to_payload())
            if placement.transition_batch is not None
            else None,
            "large_model_exception_used": placement.large_model_exception_used,
            "post_arrival_restrictions": [
                restriction.value for restriction in placement.post_arrival_restrictions
            ],
        },
    )
