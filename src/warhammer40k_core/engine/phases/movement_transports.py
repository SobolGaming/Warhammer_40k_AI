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

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, MovementUnitLocationKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _complete_move_units_step
    from warhammer40k_core.engine.phases.movement_reactions import _request_end_opponent_movement_reaction_if_available, _request_end_movement_active_player_stratagem_if_available, _request_rapid_ingress_reaction_if_available, _request_fire_overwatch_reaction_if_available, _request_selected_to_move_stratagem_if_available, _request_selected_to_fall_back_stratagem_if_available, _request_friendly_unit_fell_back_stratagem_if_available, _friendly_unit_fell_back_context_from_event, _friendly_unit_fell_back_timing_window_id, _stratagem_used_for_context, _selected_to_fall_back_trigger_payload, _selected_to_fall_back_timing_window_id, _selected_to_move_timing_window_id, _stratagem_use_payload_factory, _stratagem_target_proposal_payload_factory, _request_movement_end_surge_if_available, _movement_end_surge_distance_roll_spec, _eligible_triggered_movement_units_from_grants, _movement_end_surge_grant_distance_bonus, _movement_end_surge_event_already_processed, _active_player_end_movement_overwatch_trigger_unit_ids, _fire_overwatch_end_movement_trigger_payload
    from warhammer40k_core.engine.phases.movement_reinforcements import _eligible_reinforcement_reserve_states, _required_reinforcement_reserve_states, _overdue_required_reinforcement_reserve_states, _request_reinforcement_placement, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _request_placement_proposal_retry, _optional_proposal_context_string, _resolve_reinforcement_placement_submission, _deep_strike_enemy_distance_for_reserve_arrival, _unit_for_reserve_state, _apply_valid_reinforcement_placement
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
    "_allowed_disembark_modes_for_placement_request",
    "_disembark_candidate_for_movement_unit",
    "_request_disembark_placement",
    "_resolve_combat_disembark_placement_submission",
    "_resolve_disembark_placement_submission",
)


def _disembark_candidate_for_movement_unit(
    *,
    state: GameState,
    movement_state: MovementPhaseState,
    unit_instance_id: str,
    transport_unit_instance_id: str,
) -> DisembarkCandidate | None:
    unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    transport_id = _validate_identifier(
        "transport_unit_instance_id",
        transport_unit_instance_id,
    )
    cargo_state = state.transport_cargo_state_for_transport(transport_id)
    if cargo_state is None or cargo_state.player_id != movement_state.active_player_id:
        return None
    active_cargo = cargo_state.for_movement_phase(battle_round=state.battle_round)
    if not active_cargo.contains_unit(unit_id):
        return None
    if not active_cargo.unit_started_phase_embarked(unit_id):
        return None
    if (
        state.disembarked_unit_state_for_unit(
            player_id=movement_state.active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        is not None
    ):
        return None
    if state.battlefield_state is None:
        raise GameLifecycleError("Disembark eligibility requires battlefield state.")
    if state.battlefield_state.unit_placement_or_none(transport_id) is None:
        return None

    if (
        state.advanced_unit_state_for_unit(
            player_id=movement_state.active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=transport_id,
        )
        is not None
    ):
        return None
    if (
        state.fell_back_unit_state_for_unit(
            player_id=movement_state.active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=transport_id,
        )
        is not None
    ):
        return None
    normal_move_states = state.normal_move_states_for_unit_phase(
        player_id=movement_state.active_player_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT,
        unit_instance_id=transport_id,
    )
    reserve_state = state.reserve_state_for_unit(transport_id)
    arrived_by_ingress = (
        reserve_state is not None
        and reserve_state.arrived_battle_round == state.battle_round
        and reserve_state.arrived_phase == BattlePhase.MOVEMENT.value
    )
    if normal_move_states:
        movement_status = TransportMovementStatus.NORMAL_MOVE
        disembark_mode = DisembarkModeKind.RAPID_DISEMBARK
    elif arrived_by_ingress:
        movement_status = TransportMovementStatus.INGRESS_MOVE
        disembark_mode = DisembarkModeKind.RAPID_DISEMBARK
    elif transport_id in movement_state.moved_unit_ids:
        movement_status = TransportMovementStatus.REMAIN_STATIONARY
        disembark_mode = DisembarkModeKind.TACTICAL_DISEMBARK
    else:
        movement_status = TransportMovementStatus.NOT_MOVED
        disembark_mode = DisembarkModeKind.TACTICAL_DISEMBARK
    return DisembarkCandidate(
        player_id=movement_state.active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_id,
        transport_unit_instance_id=transport_id,
        disembark_mode=disembark_mode,
        transport_movement_status=movement_status,
    )


def _request_disembark_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    selection: DisembarkCandidate,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus:
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=_active_player_id(state),
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=selection.unit_instance_id,
        proposal_kind=ProposalKind.DISEMBARK,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        spatial_context_hash=state.physical_proposal_context_hash(),
        placement_kinds=(BattlefieldPlacementKind.DISEMBARK,),
        context={
            "transport_unit_instance_id": selection.transport_unit_instance_id,
            "disembark_mode": selection.disembark_mode.value,
            "allowed_disembark_modes": list(
                _allowed_disembark_modes_for_placement_request(selection)
            ),
            "transport_movement_status": selection.transport_movement_status.value,
            "restriction_overrides": [
                validate_json_value(override.to_payload())
                for override in selection.restriction_overrides
            ],
        },
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": selection.unit_instance_id,
            "transport_unit_instance_id": selection.transport_unit_instance_id,
            "disembark_mode": selection.disembark_mode.value,
            "allowed_disembark_modes": list(
                _allowed_disembark_modes_for_placement_request(selection)
            ),
            "proposal_kind": ProposalKind.DISEMBARK.value,
            "placement_kinds": [BattlefieldPlacementKind.DISEMBARK.value],
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
            "phase_body_status": "placement_proposal_required",
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "unit_instance_id": selection.unit_instance_id,
            "transport_unit_instance_id": selection.transport_unit_instance_id,
            "disembark_mode": selection.disembark_mode.value,
            "allowed_disembark_modes": list(
                _allowed_disembark_modes_for_placement_request(selection)
            ),
            "proposal_kind": ProposalKind.DISEMBARK.value,
            "placement_kinds": [BattlefieldPlacementKind.DISEMBARK.value],
            "ruleset_descriptor_hash": ruleset_descriptor.descriptor_hash,
        },
    )


def _resolve_disembark_placement_submission(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    unit_instance_id: str,
    transport_unit_instance_id: str,
    attempted_placement: UnitPlacement,
    disembark_mode: DisembarkModeKind,
    transport_movement_status: TransportMovementStatus,
    restriction_overrides: tuple[TransportRestrictionOverride, ...],
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Disembark placement actor must be the active player.")
    selection = DisembarkSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        transport_unit_instance_id=transport_unit_instance_id,
        attempted_placement=attempted_placement,
        disembark_mode=disembark_mode,
        transport_movement_status=transport_movement_status,
        restriction_overrides=restriction_overrides,
    )
    cargo_state = state.transport_cargo_state_for_transport(transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Disembark placement requires TransportCargoState.")
    scenario = _battlefield_scenario(state)
    transport_placement = scenario.battlefield_state.unit_placement_by_id(
        transport_unit_instance_id
    )
    if disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK:
        return _resolve_combat_disembark_placement_submission(
            state=state,
            result=result,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            selection=selection,
            cargo_state=cargo_state,
            scenario=scenario,
            transport_placement=transport_placement,
        )
    resolution = resolve_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=_unit_instance_by_id(state=state, unit_instance_id=unit_instance_id),
        transport_placement=transport_placement,
        objective_markers=_objective_markers_for_state(state),
    )
    if not resolution.is_valid:
        invalid_payload = _transport_operation_invalid_payload(
            state=state,
            active_player_id=active_player_id,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=transport_unit_instance_id,
            result=result,
            phase_body_status="disembark_placement_invalid",
            violations=resolution.violations,
        )
        decisions.event_log.append("disembark_placement_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Disembark placement is invalid.",
            payload=invalid_payload,
        )
    _apply_valid_disembark(
        state=state,
        decisions=decisions,
        disembark=resolution,
        result=result,
    )
    return None


def _allowed_disembark_modes_for_placement_request(
    selection: DisembarkCandidate,
) -> tuple[str, ...]:
    if selection.disembark_mode is DisembarkModeKind.TACTICAL_DISEMBARK:
        return (
            DisembarkModeKind.TACTICAL_DISEMBARK.value,
            DisembarkModeKind.COMBAT_DISEMBARK.value,
        )
    return (selection.disembark_mode.value,)


def _resolve_combat_disembark_placement_submission(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    selection: DisembarkSelection,
    cargo_state: TransportCargoState,
    scenario: BattlefieldScenario,
    transport_placement: UnitPlacement,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    unit = _unit_instance_by_id(state=state, unit_instance_id=selection.unit_instance_id)
    tactical_selection = replace(
        selection,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
    )
    tactical_resolution = resolve_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=tactical_selection,
        unit=unit,
        transport_placement=transport_placement,
        objective_markers=_objective_markers_for_state(state),
    )
    if tactical_resolution.is_valid:
        invalid_payload = _transport_operation_invalid_payload(
            state=state,
            active_player_id=active_player_id,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            result=result,
            phase_body_status="combat_disembark_tactical_available",
            violations=(
                TransportOperationViolation(
                    violation_code=(
                        TransportOperationViolationCode.COMBAT_DISEMBARK_TACTICAL_AVAILABLE
                    ),
                    message=(
                        "Combat Disembark requires engine-owned evidence that the submitted "
                        "placement is not legal as Tactical Disembark."
                    ),
                    unit_instance_id=selection.unit_instance_id,
                    blocker_id=selection.transport_unit_instance_id,
                ),
            ),
        )
        decisions.event_log.append("combat_disembark_tactical_available", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Combat Disembark requires Tactical-impossible evidence.",
            payload=invalid_payload,
        )

    combat_result = resolve_combat_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=unit,
        transport_placement=transport_placement,
        dice_manager=_dice_roll_manager_for_state(state=state, decisions=decisions),
        objective_markers=_objective_markers_for_state(state),
    )
    if not combat_result.placement.is_valid:
        invalid_payload = _transport_operation_invalid_payload(
            state=state,
            active_player_id=active_player_id,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            result=result,
            phase_body_status="combat_disembark_placement_invalid",
            violations=combat_result.placement.violations,
        )
        decisions.event_log.append("combat_disembark_placement_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Combat Disembark placement is invalid.",
            payload=invalid_payload,
        )
    return _apply_valid_combat_disembark(
        state=state,
        decisions=decisions,
        combat_disembark=combat_result,
        tactical_resolution=tactical_resolution,
        result=result,
    )
