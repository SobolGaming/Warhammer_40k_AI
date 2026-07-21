# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *
from warhammer40k_core.engine.phases.movement_model import *
from warhammer40k_core.engine.phases.movement_state import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_REINFORCEMENT_UNIT_DECISION_TYPE, SELECT_DISEMBARK_UNIT_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, COMPLETE_REINFORCEMENTS_OPTION_ID, COMPLETE_DISEMBARKS_OPTION_ID, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_reactions import _request_end_opponent_movement_reaction_if_available, _request_end_movement_active_player_stratagem_if_available, _request_rapid_ingress_reaction_if_available, _request_fire_overwatch_reaction_if_available, _request_selected_to_move_stratagem_if_available, _request_selected_to_fall_back_stratagem_if_available, _request_friendly_unit_fell_back_stratagem_if_available, _friendly_unit_fell_back_context_from_event, _friendly_unit_fell_back_timing_window_id, _stratagem_used_for_context, _selected_to_fall_back_trigger_payload, _selected_to_fall_back_timing_window_id, _selected_to_move_timing_window_id, _stratagem_use_payload_factory, _stratagem_target_proposal_payload_factory, _request_movement_end_surge_if_available, _movement_end_surge_distance_roll_spec, _eligible_triggered_movement_units_from_grants, _movement_end_surge_grant_distance_bonus, _movement_end_surge_event_already_processed, _active_player_end_movement_overwatch_trigger_unit_ids, _fire_overwatch_end_movement_trigger_payload
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
    "MovementPhaseHandler",
    "_begin_reinforcements_step",
    "_complete_reinforcements_step",
)


@dataclass(frozen=True, slots=True)
class MovementPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None
    army_catalog: ArmyCatalog | None = None
    parameterized_proposals: bool = True
    stratagem_index: StratagemCatalogIndex = field(default_factory=eleventh_edition_stratagem_index)
    advance_move_hooks: AdvanceMoveHookRegistry = field(
        default_factory=AdvanceMoveHookRegistry.empty
    )
    advance_eligibility_hooks: AdvanceEligibilityHookRegistry = field(
        default_factory=AdvanceEligibilityHookRegistry.empty
    )
    fall_back_hooks: FallBackEligibilityHookRegistry = field(
        default_factory=FallBackEligibilityHookRegistry.empty
    )
    movement_end_surge_hooks: MovementEndSurgeHookRegistry = field(
        default_factory=MovementEndSurgeHookRegistry.empty
    )
    reserve_arrival_distance_hooks: ReserveArrivalDistanceHookRegistry = field(
        default_factory=ReserveArrivalDistanceHookRegistry.empty
    )
    reserve_arrival_restriction_hooks: ReserveArrivalRestrictionHookRegistry = field(
        default_factory=ReserveArrivalRestrictionHookRegistry.empty
    )
    unit_move_completed_mortal_wound_hooks: UnitMoveCompletedMortalWoundHookRegistry = field(
        default_factory=UnitMoveCompletedMortalWoundHookRegistry.empty
    )
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry = field(
        default_factory=ChargeTargetRestrictionHookRegistry.empty
    )
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry = field(
        default_factory=StratagemCostModifierRegistry.empty
    )
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] = field(
        default_factory=_empty_ability_indexes
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "MovementPhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )
        if self.army_catalog is not None and type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("MovementPhaseHandler army_catalog must be an ArmyCatalog.")
        if type(self.parameterized_proposals) is not bool:
            raise GameLifecycleError("MovementPhaseHandler parameterized_proposals must be a bool.")
        if not self.parameterized_proposals:
            raise GameLifecycleError("MovementPhaseHandler requires parameterized proposals.")
        if type(self.stratagem_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("MovementPhaseHandler stratagem_index must be an index.")
        if type(self.advance_move_hooks) is not AdvanceMoveHookRegistry:
            raise GameLifecycleError("MovementPhaseHandler advance_move_hooks must be a registry.")
        if type(self.advance_eligibility_hooks) is not AdvanceEligibilityHookRegistry:
            raise GameLifecycleError(
                "MovementPhaseHandler advance_eligibility_hooks must be a registry."
            )
        if type(self.fall_back_hooks) is not FallBackEligibilityHookRegistry:
            raise GameLifecycleError("MovementPhaseHandler fall_back_hooks must be a registry.")
        if type(self.movement_end_surge_hooks) is not MovementEndSurgeHookRegistry:
            raise GameLifecycleError(
                "MovementPhaseHandler movement_end_surge_hooks must be a registry."
            )
        if type(self.reserve_arrival_distance_hooks) is not ReserveArrivalDistanceHookRegistry:
            raise GameLifecycleError(
                "MovementPhaseHandler reserve_arrival_distance_hooks must be a registry."
            )
        if (
            type(self.reserve_arrival_restriction_hooks)
            is not ReserveArrivalRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "MovementPhaseHandler reserve_arrival_restriction_hooks must be a registry."
            )
        if (
            type(self.unit_move_completed_mortal_wound_hooks)
            is not UnitMoveCompletedMortalWoundHookRegistry
        ):
            raise GameLifecycleError(
                "MovementPhaseHandler unit_move_completed_mortal_wound_hooks must be a registry."
            )
        if type(self.charge_target_restriction_hooks) is not ChargeTargetRestrictionHookRegistry:
            raise GameLifecycleError(
                "MovementPhaseHandler charge_target_restriction_hooks must be a registry."
            )
        if type(self.stratagem_cost_modifier_registry) is not StratagemCostModifierRegistry:
            raise GameLifecycleError(
                "MovementPhaseHandler stratagem_cost_modifier_registry must be a registry."
            )
        object.__setattr__(
            self,
            "ability_indexes_by_player_id",
            _validate_ability_index_mapping(self.ability_indexes_by_player_id),
        )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "MovementPhaseHandler runtime_modifier_registry must be a registry."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.MOVEMENT

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        _validate_movement_phase_state(state)
        movement_state = _ensure_movement_phase_state(state=state, decisions=decisions)
        _ensure_transport_cargo_phase_states(state)
        active_selection = movement_state.active_selection
        if active_selection is not None:
            if movement_state.pending_action is not None:
                from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
                    request_catalog_movement_target_pair_start_if_available,
                )

                target_pair_status = request_catalog_movement_target_pair_start_if_available(
                    state=state,
                    decisions=decisions,
                    pending_action=movement_state.pending_action,
                    ability_indexes_by_player_id=self.ability_indexes_by_player_id,
                )
                if target_pair_status is not None:
                    return target_pair_status
                return _request_pending_movement_action_proposal(
                    state=state,
                    decisions=decisions,
                    pending_action=movement_state.pending_action,
                    ability_indexes_by_player_id=self.ability_indexes_by_player_id,
                )
            stratagem_status = _request_selected_to_move_stratagem_if_available(
                state=state,
                decisions=decisions,
                active_selection=active_selection,
                stratagem_index=self.stratagem_index,
                stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
            )
            if stratagem_status is not None:
                return stratagem_status
            return _request_movement_action(
                state=state,
                decisions=decisions,
                active_selection=active_selection,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )

        scenario = _battlefield_scenario(state)
        legal_unit_ids = movement_state.legal_unit_ids(
            scenario,
            accounted_unplaced_model_ids=state.unavailable_model_ids(),
        )

        move_completed_status = resolve_unit_move_completed_mortal_wound_hooks(
            state=state,
            decisions=decisions,
            registry=self.unit_move_completed_mortal_wound_hooks,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            runtime_modifier_registry=self.runtime_modifier_registry,
            completed_phase=BattlePhase.MOVEMENT,
            event_type="movement_activation_completed",
            movement_actions=(
                MovementPhaseActionKind.NORMAL_MOVE.value,
                MovementPhaseActionKind.ADVANCE.value,
                MovementPhaseActionKind.FALL_BACK.value,
            ),
            ability_indexes_by_player_id=self.ability_indexes_by_player_id,
        )
        if move_completed_status is not None:
            return move_completed_status

        for setup_event_type in ("reinforcement_unit_arrived", "unit_disembarked"):
            setup_completed_status = resolve_unit_move_completed_mortal_wound_hooks(
                state=state,
                decisions=decisions,
                registry=self.unit_move_completed_mortal_wound_hooks,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                runtime_modifier_registry=self.runtime_modifier_registry,
                completed_phase=BattlePhase.MOVEMENT,
                event_type=setup_event_type,
                movement_actions=("set_up",),
                ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            )
            if setup_completed_status is not None:
                return setup_completed_status

        fell_back_stratagem_status = _request_friendly_unit_fell_back_stratagem_if_available(
            state=state,
            decisions=decisions,
            stratagem_index=self.stratagem_index,
            stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
        )
        if fell_back_stratagem_status is not None:
            return fell_back_stratagem_status

        surge_status = _request_movement_end_surge_if_available(
            state=state,
            decisions=decisions,
            registry=self.movement_end_surge_hooks,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
        )
        if surge_status is not None:
            return surge_status

        if state.transport_cargo_states:
            disembark_status = _request_pre_move_disembark_if_available(
                state=state,
                decisions=decisions,
                movement_state=movement_state,
            )
            if disembark_status is not None:
                return disembark_status

        if not legal_unit_ids:
            return _begin_reinforcements_step(
                state=state,
                decisions=decisions,
                reaction_queue=reaction_queue,
                stratagem_index=self.stratagem_index,
                ability_indexes_by_player_id=self.ability_indexes_by_player_id,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=self.army_catalog,
                runtime_modifier_registry=self.runtime_modifier_registry,
                charge_target_restriction_hooks=self.charge_target_restriction_hooks,
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_MOVEMENT_UNIT_DECISION_TYPE,
            actor_id=_active_player_id(state),
            payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "active_player_id": _active_player_id(state),
            },
            options=_movement_unit_options(scenario=scenario, unit_ids=legal_unit_ids),
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.MOVEMENT.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "legal_unit_count": len(legal_unit_ids),
            },
        )

    def invalid_proposal_submission_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        if request.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            movement_parsed = _parse_movement_proposal_submission_or_invalid(
                state=state,
                request=request,
                result=result,
                decisions=decisions,
            )
            if isinstance(movement_parsed, LifecycleStatus):
                return movement_parsed
            proposal_request, movement_submission = movement_parsed
            proposal_validation = movement_submission.validation_result_for_request(
                proposal_request
            )
            if not proposal_validation.is_valid:
                return _reject_invalid_proposal(
                    state=state,
                    decisions=decisions,
                    result=result,
                    proposal_validation=proposal_validation,
                    event_type="movement_proposal_invalid",
                    message="Movement proposal does not match the pending request.",
                )
            return None
        if request.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE:
            placement_parsed = _parse_placement_proposal_submission_or_invalid(
                state=state,
                request=request,
                result=result,
                decisions=decisions,
            )
            if isinstance(placement_parsed, LifecycleStatus):
                return placement_parsed
            proposal_request, placement_submission = placement_parsed
            proposal_validation = placement_submission.validation_result_for_request(
                proposal_request
            )
            if not proposal_validation.is_valid:
                return _reject_invalid_proposal(
                    state=state,
                    decisions=decisions,
                    result=result,
                    proposal_validation=proposal_validation,
                    event_type="placement_proposal_invalid",
                    message="Placement proposal does not match the pending request.",
                )
            if proposal_request.proposal_kind is ProposalKind.DISEMBARK:
                missing = _missing_disembark_proposal_field(placement_submission)
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
            return None
        raise GameLifecycleError("Movement proposal prevalidation received unsupported request.")

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus | None:
        from warhammer40k_core.engine.catalog_movement_target_pair_runtime import (
            SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE,
            apply_catalog_movement_target_pair_result,
        )

        if result.decision_type == SELECT_CATALOG_MOVEMENT_TARGET_PAIR_DECISION_TYPE:
            record = decisions.record_for_result(result)
            apply_catalog_movement_target_pair_result(
                state=state,
                decisions=decisions,
                request=record.request,
                result=result,
                ability_indexes_by_player_id=self.ability_indexes_by_player_id,
            )
            return None
        if result.decision_type == DICE_REROLL_DECISION_TYPE:
            reroll_record = decisions.record_for_result(result)
            if is_triggered_movement_distance_reroll_request(reroll_record.request):
                return apply_triggered_movement_distance_reroll_decision(
                    state=state,
                    result=result,
                    decisions=decisions,
                )
            return _apply_advance_roll_reroll_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                reaction_queue=reaction_queue,
                stratagem_index=self.stratagem_index,
            )
        if result.decision_type == SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE:
            return _apply_desperate_escape_model_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                fall_back_hooks=self.fall_back_hooks,
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
        if result.decision_type == SELECT_MOVEMENT_ACTION_DECISION_TYPE:
            return _apply_movement_action_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                reaction_queue=reaction_queue,
                stratagem_index=self.stratagem_index,
                advance_move_hooks=self.advance_move_hooks,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=_active_player_id(state),
                ),
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
        if result.decision_type == SELECT_ADVANCE_MOVE_GRANT_DECISION_TYPE:
            return _apply_advance_move_grant_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                reaction_queue=reaction_queue,
                stratagem_index=self.stratagem_index,
                advance_move_hooks=self.advance_move_hooks,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=_active_player_id(state),
                ),
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
        if result.decision_type == MOVEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_movement_proposal_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                reaction_queue=reaction_queue,
                stratagem_index=self.stratagem_index,
                advance_move_hooks=self.advance_move_hooks,
                advance_eligibility_hooks=self.advance_eligibility_hooks,
                fall_back_hooks=self.fall_back_hooks,
                ability_index=_ability_index_for_player(
                    self.ability_indexes_by_player_id,
                    player_id=_active_player_id(state),
                ),
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
        if result.decision_type == SELECT_REINFORCEMENT_UNIT_DECISION_TYPE:
            return _apply_reinforcement_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_placement_proposal_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                reserve_arrival_distance_hooks=self.reserve_arrival_distance_hooks,
                reserve_arrival_restriction_hooks=self.reserve_arrival_restriction_hooks,
            )
        if result.decision_type == SELECT_DISEMBARK_UNIT_DECISION_TYPE:
            return _apply_disembark_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type == SELECT_EMBARK_TRANSPORT_DECISION_TYPE:
            return _apply_embark_transport_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            )
        if result.decision_type != SELECT_MOVEMENT_UNIT_DECISION_TYPE:
            raise GameLifecycleError("MovementPhaseHandler received an unsupported decision_type.")
        _validate_movement_phase_state(state)
        active_player_id = _active_player_id(state)
        if result.actor_id != active_player_id:
            raise GameLifecycleError("Movement unit selection actor must be the active player.")
        movement_state = state.movement_phase_state
        if movement_state is None:
            raise GameLifecycleError("Movement unit selection requires movement phase state.")

        payload = _decision_payload_object(result.payload)
        unit_instance_id = _payload_string(payload, key="unit_instance_id")
        scenario = _battlefield_scenario(state)
        if unit_instance_id not in movement_state.legal_unit_ids(
            scenario,
            accounted_unplaced_model_ids=state.unavailable_model_ids(),
        ):
            raise GameLifecycleError("Movement unit selection is not currently legal.")

        selection = MovementUnitSelection(
            player_id=active_player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_instance_id,
            request_id=result.request_id,
            result_id=result.result_id,
        )
        state.replace_movement_phase_state(movement_state.with_unit_selection(selection))
        decisions.event_log.append(
            "movement_unit_selected",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "unit_selected",
            },
        )
        return None


def _begin_reinforcements_step(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None = None,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.MOVE_UNITS:
        raise GameLifecycleError("Reserve arrivals require Move Units state.")
    assert_move_units_step_complete_for_reinforcements(
        state=state,
        movement_state=movement_state,
    )
    unarrived_reserve_states = state.unarrived_reserve_states_for_player(active_player_id)
    if _overdue_required_reinforcement_reserve_states(state=state):
        raise GameLifecycleError("Required reserve arrival was missed.")
    eligible_reserve_states = _eligible_reinforcement_reserve_states(state=state)
    required_reserve_states = _required_reinforcement_reserve_states(state=state)
    if movement_state.reinforcements_completed or not eligible_reserve_states:
        return _complete_reinforcements_step(
            state=state,
            decisions=decisions,
            reaction_queue=reaction_queue,
            stratagem_index=stratagem_index,
            ability_indexes_by_player_id=ability_indexes_by_player_id,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            runtime_modifier_registry=runtime_modifier_registry,
            charge_target_restriction_hooks=charge_target_restriction_hooks,
            unarrived_reserve_count=len(unarrived_reserve_states),
        )

    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_REINFORCEMENT_UNIT_DECISION_TYPE,
        actor_id=active_player_id,
        payload={
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "active_player_id": active_player_id,
        },
        options=_reinforcement_unit_options(
            eligible_reserve_states,
            completion_allowed=not required_reserve_states,
        ),
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "phase_body_status": "move_units_waiting_for_arrival_choice",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unarrived_reserve_count": len(unarrived_reserve_states),
            "eligible_reserve_count": len(eligible_reserve_states),
            "required_reserve_count": len(required_reserve_states),
        },
    )


def _complete_reinforcements_step(
    *,
    state: GameState,
    decisions: DecisionController,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
    ability_indexes_by_player_id: Mapping[str, AbilityCatalogIndex] | None = None,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    charge_target_restriction_hooks: ChargeTargetRestrictionHookRegistry | None = None,
    unarrived_reserve_count: int,
) -> LifecycleStatus:
    active_player_id = _active_player_id(state)
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.step is not MovementPhaseStepKind.MOVE_UNITS:
        raise GameLifecycleError("Completing reserve arrivals requires Move Units step.")
    end_movement_active_status = _request_end_movement_active_player_stratagem_if_available(
        state=state,
        decisions=decisions,
        stratagem_index=stratagem_index,
    )
    if end_movement_active_status is not None:
        return end_movement_active_status
    end_movement_reaction_status = _request_end_opponent_movement_reaction_if_available(
        state=state,
        decisions=decisions,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
        ability_indexes_by_player_id=ability_indexes_by_player_id,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        runtime_modifier_registry=runtime_modifier_registry,
        charge_target_restriction_hooks=charge_target_restriction_hooks,
    )
    if end_movement_reaction_status is not None:
        return end_movement_reaction_status
    phase_end_mortal_wounds_status = resolve_movement_phase_end_mortal_wounds(
        state=state,
        decisions=decisions,
    )
    if phase_end_mortal_wounds_status is not None:
        return phase_end_mortal_wounds_status
    if not movement_state.reinforcements_completed:
        state.replace_movement_phase_state(movement_state.with_reinforcements_completed())
    decisions.event_log.append(
        "move_units_reserve_arrivals_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "unarrived_reserve_count": unarrived_reserve_count,
            "phase_body_status": "move_units_complete",
        },
    )
    return LifecycleStatus.advanced(
        stage=GameLifecycleStage.BATTLE,
        payload={
            "phase": BattlePhase.MOVEMENT.value,
            "step": MovementPhaseStepKind.MOVE_UNITS.value,
            "phase_body_status": "move_units_complete",
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "unarrived_reserve_count": unarrived_reserve_count,
        },
    )
