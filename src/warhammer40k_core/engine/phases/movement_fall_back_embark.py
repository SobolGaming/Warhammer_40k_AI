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
from warhammer40k_core.engine.phases.movement_resolution_flow import *

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
    from warhammer40k_core.engine.phases.movement_resolution_flow import _apply_movement_proposal_decision, _action_result_from_proposal_request, _reject_invalid_proposal, _reject_invalid_movement_resolution, _apply_advance_roll_reroll_decision, _resolve_and_apply_advance_move, _advance_move_grants_from_context, _selected_advance_move_grant_hook_ids_from_context, _apply_advance_move_grants, _grant_ranged_weapon_keywords, _aircraft_reserve_transition_reason_for_normal_move, _apply_aircraft_reserve_transition_for_normal_move
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_apply_desperate_escape_model_selection_decision",
    "_apply_embark_transport_selection_decision",
    "_apply_fall_back_result",
    "_apply_valid_embark",
    "_complete_activation_then_request_post_normal_disembark_if_available",
    "_complete_movement_activation",
    "_complete_movement_activation_with_record_ids",
    "_interrupt_started_mission_actions_for_movement_activation",
    "_maximum_model_distance_inches_from_witness",
    "_post_move_embark_options",
    "_request_embark_after_move_or_complete_activation",
)


def _apply_desperate_escape_model_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    fall_back_hooks: FallBackEligibilityHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Desperate Escape selection actor must be the active player.")
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Desperate Escape selection requires active movement selection.")

    record = decisions.record_for_result(result)
    request_payload = _decision_payload_object(record.request.payload)
    context_payload = _payload_object(request_payload, key="fall_back_context")
    unit_instance_id = _payload_string(context_payload, key="unit_instance_id")
    if unit_instance_id != movement_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Desperate Escape selection unit must match active selection.")
    fall_back_result_payload = cast(
        FallBackActionResultPayload,
        _payload_object(context_payload, key="fall_back_result"),
    )
    fall_back_result = FallBackActionResult.from_payload(fall_back_result_payload)
    destroyed_model_ids = tuple(
        cast(
            list[str],
            _payload_json_array(
                _decision_payload_object(result.payload),
                key="destroyed_model_ids",
            ),
        )
    )
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    action_result = DecisionResult(
        result_id=_payload_string(context_payload, key="action_result_id"),
        request_id=_payload_string(context_payload, key="action_request_id"),
        decision_type=SELECT_MOVEMENT_ACTION_DECISION_TYPE,
        actor_id=active_player_id,
        selected_option_id=_payload_string(context_payload, key="action_selected_option_id"),
        payload={
            "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
            "unit_instance_id": unit_instance_id,
            "witness": validate_json_value(fall_back_result.witness.to_payload()),
            **fall_back_result.movement_payload,
        },
    )
    return _apply_fall_back_result(
        state=state,
        decisions=decisions,
        result=action_result,
        unit_placement=unit_placement,
        fall_back_result=fall_back_result,
        destroyed_model_ids=destroyed_model_ids,
        ruleset_descriptor=ruleset_descriptor,
        fall_back_hooks=fall_back_hooks,
    )


def _apply_fall_back_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    unit_placement: UnitPlacement,
    fall_back_result: FallBackActionResult,
    destroyed_model_ids: tuple[str, ...],
    ruleset_descriptor: RulesetDescriptor,
    fall_back_hooks: FallBackEligibilityHookRegistry,
    reaction_queue: ReactionQueue | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    scenario = _battlefield_scenario(state)
    surviving_placement = fall_back_result.surviving_attempted_placement(
        destroyed_model_ids=destroyed_model_ids,
    )
    if surviving_placement is not None:
        survivor_coherency_result = unit_placement_coherency_result(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=surviving_placement,
        )
        if not survivor_coherency_result.is_coherent:
            violation_code = "unit_coherency_broken"
            invalid_payload = _movement_action_invalid_payload(
                state=state,
                active_player_id=active_player_id,
                unit_instance_id=unit_placement.unit_instance_id,
                action=MovementPhaseActionKind.FALL_BACK,
                result=result,
                violation_code=violation_code,
                movement_payload={
                    **fall_back_result.movement_payload,
                    "destroyed_model_ids": list(destroyed_model_ids),
                    "surviving_coherency_result": validate_json_value(
                        survivor_coherency_result.to_payload()
                    ),
                },
                rollback_record=None,
            )
            decisions.event_log.append("movement_action_invalid", invalid_payload)
            return LifecycleStatus.invalid(
                stage=GameLifecycleStage.BATTLE,
                message="Fall Back surviving endpoint violates unit coherency.",
                payload={
                    "phase": BattlePhase.MOVEMENT.value,
                    "phase_body_status": "movement_action_invalid",
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "unit_instance_id": unit_placement.unit_instance_id,
                    "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                    "violation_code": violation_code,
                },
            )
    transition_batch = fall_back_result.transition_batch(
        before=unit_placement,
        destroyed_model_ids=destroyed_model_ids,
    )
    start_engaged_enemy_unit_ids = _enemy_engaged_unit_ids_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
    )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fall Back requires battlefield_state.")
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(
            fall_back_result.attempted_placement
        ).with_removed_models(destroyed_model_ids)
    )
    permission_grants: tuple[FallBackEligibilityGrant, ...] = ()
    if surviving_placement is not None:
        permission_grants = fall_back_hooks.grants_for(
            FallBackEligibilityContext(
                state=state,
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                movement_request_id=result.request_id,
                movement_result_id=result.result_id,
            )
        )
        state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                desperate_escape_rolls=fall_back_result.desperate_escape_rolls,
                can_shoot=any(grant.can_shoot for grant in permission_grants),
                can_declare_charge=any(grant.can_declare_charge for grant in permission_grants),
            )
        )
        if permission_grants:
            decisions.event_log.append(
                "fall_back_eligibility_hooks_resolved",
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": active_player_id,
                    "phase": BattlePhase.MOVEMENT.value,
                    "unit_instance_id": unit_placement.unit_instance_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "grants": [
                        validate_json_value(grant.to_payload()) for grant in permission_grants
                    ],
                },
            )
    return _request_embark_after_move_or_complete_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.FALL_BACK,
        witness=fall_back_result.witness,
        movement_payload={
            **fall_back_result.movement_payload,
            "destroyed_model_ids": list(destroyed_model_ids),
            "start_engaged_enemy_unit_instance_ids": list(start_engaged_enemy_unit_ids),
            "fall_back_eligibility_grants": [
                validate_json_value(grant.to_payload()) for grant in permission_grants
            ],
        },
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        transition_batch=transition_batch,
        ruleset_descriptor=ruleset_descriptor,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
    )


def _request_embark_after_move_or_complete_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    active_selection = _active_movement_selection(state)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Movement activation completion requires battlefield_state.")
    if active_selection.unit_instance_id not in {
        placement.unit_instance_id
        for army in battlefield_state.placed_armies
        for placement in army.unit_placements
    }:
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=movement_payload,
            displacement_kind=displacement_kind,
            transition_batch=transition_batch,
        )
        return None
    options = _post_move_embark_options(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
        movement_phase_action=_transport_status_for_movement_action(action),
    )
    if not options:
        return _complete_activation_then_request_post_normal_disembark_if_available(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload=movement_payload,
            displacement_kind=displacement_kind,
            transition_batch=transition_batch,
            ruleset_descriptor=ruleset_descriptor,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
        )
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_EMBARK_TRANSPORT_DECISION_TYPE,
        actor_id=active_selection.player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "movement_context": _movement_completion_context_payload(
                result=result,
                action=action,
                witness=witness,
                movement_payload=movement_payload,
                displacement_kind=displacement_kind,
                transition_batch=transition_batch,
            ),
        },
        options=(
            DecisionOption(
                option_id=DECLINE_EMBARK_OPTION_ID,
                label="Decline Embark",
                payload={
                    "transport_decision": DECLINE_EMBARK_OPTION_ID,
                    "unit_instance_id": active_selection.unit_instance_id,
                },
            ),
            *options,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "phase_body_status": "embark_choice_required",
            "battle_round": state.battle_round,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "eligible_transport_count": len(options),
        },
    )


def _complete_activation_then_request_post_normal_disembark_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
    ruleset_descriptor: RulesetDescriptor,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
) -> LifecycleStatus | None:
    active_selection = _active_movement_selection(state)
    transport_unit_instance_id = active_selection.unit_instance_id
    _complete_movement_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )
    if action is not MovementPhaseActionKind.NORMAL_MOVE:
        return None
    movement_state = state.movement_phase_state
    if movement_state is None:
        raise GameLifecycleError("Post-move Disembark requires movement_phase_state.")
    return _request_post_normal_move_disembark_if_available(
        state=state,
        decisions=decisions,
        movement_state=movement_state,
        transport_unit_instance_id=transport_unit_instance_id,
    )


def _post_move_embark_options(
    *,
    state: GameState,
    unit_instance_id: str,
    movement_phase_action: TransportMovementStatus,
) -> tuple[DecisionOption, ...]:
    scenario = _battlefield_scenario(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_instance_id)
    options: list[DecisionOption] = []
    for cargo_state in state.transport_cargo_states:
        if cargo_state.player_id != unit_placement.player_id:
            continue
        transport_placement = scenario.battlefield_state.unit_placement_by_id(
            cargo_state.transport_unit_instance_id
        )
        selection = EmbarkSelection(
            player_id=unit_placement.player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=cargo_state.transport_unit_instance_id,
            movement_phase_action=movement_phase_action,
        )
        resolution = resolve_embark(
            scenario=scenario,
            cargo_state=cargo_state,
            selection=selection,
            unit_placement=unit_placement,
            transport_placement=transport_placement,
            persisting_effects=state.persisting_effects_for_unit(unit_instance_id),
        )
        if not resolution.is_valid:
            continue
        options.append(
            DecisionOption(
                option_id=cargo_state.transport_unit_instance_id,
                label=f"Embark {cargo_state.transport_unit_instance_id}",
                payload=validate_json_value(
                    {
                        "transport_decision": "embark_unit",
                        **selection.to_payload(),
                    }
                ),
            )
        )
    return tuple(sorted(options, key=lambda option: option.option_id))


def _apply_embark_transport_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    _validate_movement_phase_state(state)
    active_selection = _active_movement_selection(state)
    if result.actor_id != active_selection.player_id:
        raise GameLifecycleError("Embark selection actor must be the active player.")
    request_payload = _request_payload_for_result(decisions=decisions, result=result)
    context_payload = _payload_object(request_payload, key="movement_context")
    action = movement_phase_action_kind_from_token(
        _payload_string(context_payload, key="movement_phase_action")
    )
    witness = _optional_payload_path_witness(context_payload, key="witness")
    movement_payload = _payload_json_object(context_payload, key="movement_payload")
    displacement_kind = _payload_model_displacement_kind(context_payload, key="displacement_kind")
    transition_batch = _payload_transition_batch(context_payload, key="transition_batch")

    payload = _decision_payload_object(result.payload)
    transport_decision = _payload_string(payload, key="transport_decision")
    if transport_decision == DECLINE_EMBARK_OPTION_ID:
        if _payload_string(payload, key="unit_instance_id") != active_selection.unit_instance_id:
            raise GameLifecycleError("Embark decline unit drift.")
        declined_unit_id = active_selection.unit_instance_id
        _complete_movement_activation_with_record_ids(
            state=state,
            decisions=decisions,
            request_id=_payload_string(context_payload, key="action_request_id"),
            result_id=_payload_string(context_payload, key="action_result_id"),
            action=action,
            witness=witness,
            movement_payload=movement_payload,
            displacement_kind=displacement_kind,
            transition_batch=transition_batch,
        )
        decisions.event_log.append(
            "embark_declined",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "embark_declined",
            },
        )
        if action is not MovementPhaseActionKind.NORMAL_MOVE:
            return None
        movement_state = state.movement_phase_state
        if movement_state is None:
            raise GameLifecycleError("Post-move Disembark requires movement_phase_state.")
        return _request_post_normal_move_disembark_if_available(
            state=state,
            decisions=decisions,
            movement_state=movement_state,
            transport_unit_instance_id=declined_unit_id,
        )
    if transport_decision != "embark_unit":
        raise GameLifecycleError("Unsupported Embark selection payload.")
    selection = EmbarkSelection.from_payload(
        cast(
            EmbarkSelectionPayload,
            {
                "player_id": _payload_string(payload, key="player_id"),
                "battle_round": _payload_positive_int(payload, key="battle_round"),
                "unit_instance_id": _payload_string(payload, key="unit_instance_id"),
                "transport_unit_instance_id": _payload_string(
                    payload, key="transport_unit_instance_id"
                ),
                "movement_phase_action": _payload_string(payload, key="movement_phase_action"),
                "restriction_overrides": cast(
                    list[TransportRestrictionOverridePayload],
                    _payload_json_array(payload, key="restriction_overrides"),
                ),
            },
        )
    )
    cargo_state = state.transport_cargo_state_for_transport(selection.transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Embark requires TransportCargoState.")
    scenario = _battlefield_scenario(state)
    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=cargo_state,
        selection=selection,
        unit_placement=scenario.battlefield_state.unit_placement_by_id(
            active_selection.unit_instance_id
        ),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            selection.transport_unit_instance_id
        ),
        persisting_effects=state.persisting_effects_for_unit(active_selection.unit_instance_id),
    )
    if not resolution.is_valid:
        invalid_payload = _transport_operation_invalid_payload(
            state=state,
            active_player_id=active_selection.player_id,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            result=result,
            phase_body_status="embark_selection_invalid",
            violations=resolution.violations,
        )
        decisions.event_log.append("embark_selection_invalid", invalid_payload)
        return LifecycleStatus.invalid(
            stage=GameLifecycleStage.BATTLE,
            message="Embark selection is invalid.",
            payload=invalid_payload,
        )
    _apply_valid_embark(
        state=state,
        decisions=decisions,
        embark=resolution,
        result=result,
        context_payload=context_payload,
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )
    return None


def _apply_valid_embark(
    *,
    state: GameState,
    decisions: DecisionController,
    embark: EmbarkResolution,
    result: DecisionResult,
    context_payload: dict[str, JsonValue],
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
) -> None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Embark requires battlefield_state.")
    if embark.updated_cargo_state is None:
        raise GameLifecycleError("Valid EmbarkResolution requires updated cargo state.")
    state.replace_battlefield_state(
        apply_embark_to_battlefield(
            battlefield_state=battlefield_state,
            embark=embark,
        )
    )
    state.replace_transport_cargo_state(embark.updated_cargo_state)
    decisions.event_log.append(
        "unit_embarked",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": embark.selection.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": embark.selection.unit_instance_id,
            "transport_unit_instance_id": embark.selection.transport_unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_embarked",
            "updated_cargo_state": validate_json_value(embark.updated_cargo_state.to_payload()),
            "transition_batch": validate_json_value(embark.transition_batch.to_payload())
            if embark.transition_batch is not None
            else None,
        },
    )
    _complete_movement_activation_with_record_ids(
        state=state,
        decisions=decisions,
        request_id=_payload_string(context_payload, key="action_request_id"),
        result_id=_payload_string(context_payload, key="action_result_id"),
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )


def _complete_movement_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind | None = None,
    transition_batch: BattlefieldTransitionBatch | None = None,
) -> None:
    _complete_movement_activation_with_record_ids(
        state=state,
        decisions=decisions,
        request_id=result.request_id,
        result_id=result.result_id,
        action=action,
        witness=witness,
        movement_payload=movement_payload,
        displacement_kind=displacement_kind,
        transition_batch=transition_batch,
    )


def _complete_movement_activation_with_record_ids(
    *,
    state: GameState,
    decisions: DecisionController,
    request_id: str,
    result_id: str,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind | None = None,
    transition_batch: BattlefieldTransitionBatch | None = None,
) -> None:
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement activation completion requires active selection.")
    active_selection = movement_state.active_selection
    _interrupt_started_mission_actions_for_movement_activation(
        state=state,
        decisions=decisions,
        active_selection=active_selection,
        action=action,
        request_id=request_id,
        result_id=result_id,
        displacement_kind=displacement_kind,
    )
    state.replace_movement_phase_state(
        movement_state.with_activation_complete(
            active_selection.unit_instance_id,
            maximum_model_distance_inches=_maximum_model_distance_inches_from_witness(witness),
        )
    )
    event_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_selection.player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": active_selection.unit_instance_id,
        "movement_phase_action": action.value,
        "request_id": request_id,
        "result_id": result_id,
        "phase_body_status": "activation_complete",
        "witness": None if witness is None else validate_json_value(witness.to_payload()),
    }
    if displacement_kind is not None:
        event_payload["displacement_kind"] = displacement_kind.value
    if transition_batch is not None:
        event_payload["transition_batch"] = validate_json_value(transition_batch.to_payload())
    event_payload.update(movement_payload)
    decisions.event_log.append("movement_activation_completed", event_payload)


def _maximum_model_distance_inches_from_witness(witness: PathWitness | None) -> float:
    if witness is None:
        return 0.0
    maximum_distance = 0.0
    for _model_id, poses in witness.model_paths:
        model_distance = 0.0
        for index in range(1, len(poses)):
            model_distance += poses[index - 1].distance_3d_to(poses[index])
        maximum_distance = max(maximum_distance, model_distance)
    return maximum_distance


def _interrupt_started_mission_actions_for_movement_activation(
    *,
    state: GameState,
    decisions: DecisionController,
    active_selection: MovementUnitSelection,
    action: MovementPhaseActionKind,
    request_id: str,
    result_id: str,
    displacement_kind: ModelDisplacementKind | None,
) -> None:
    if type(active_selection) is not MovementUnitSelection:
        raise GameLifecycleError("Mission Action movement interruption requires active selection.")
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return
    active_unit_on_battlefield = active_selection.unit_instance_id in {
        placement.unit_instance_id
        for army in battlefield_state.placed_armies
        for placement in army.unit_placements
    }
    for action_state in tuple(state.mission_action_states):
        if not _mission_action_state_is_active_for_unit(
            action_state=action_state,
            unit_instance_id=active_selection.unit_instance_id,
        ):
            continue
        if active_unit_on_battlefield:
            if displacement_kind is None:
                continue
            interrupted = interrupt_mission_action_for_displacement(
                action_state,
                displacement_kind=displacement_kind,
            )
        else:
            interrupted = interrupt_mission_action_for_battlefield_departure(action_state)
        if interrupted is None:
            continue
        state.replace_mission_action_state(interrupted)
        decisions.event_log.append(
            "mission_action_interrupted",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "movement_phase_action": action.value,
                "request_id": request_id,
                "result_id": result_id,
                "phase_body_status": "mission_action_interrupted",
                "mission_action_state": validate_json_value(interrupted.to_payload()),
                "interrupted_reason": interrupted.interrupted_reason,
            },
        )
