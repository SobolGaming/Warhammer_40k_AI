# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *
from warhammer40k_core.engine.phases.movement_model import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.mission_setup import MissionSetup
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_REINFORCEMENT_UNIT_DECISION_TYPE, SELECT_DISEMBARK_UNIT_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, COMPLETE_REINFORCEMENTS_OPTION_ID, COMPLETE_DISEMBARKS_OPTION_ID, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _begin_reinforcements_step, _complete_reinforcements_step
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
    "AdvanceMoveResolution",
    "FallBackActionResult",
    "MovementPhaseState",
    "NormalMoveResolution",
    "_ResolvedUnitMove",
)


@dataclass(frozen=True, slots=True)
class MovementPhaseState:
    battle_round: int
    active_player_id: str
    step: MovementPhaseStepKind = MovementPhaseStepKind.MOVE_UNITS
    reinforcements_completed: bool = False
    declined_disembark_unit_ids: tuple[str, ...] = ()
    declined_post_normal_move_disembark_unit_ids: tuple[str, ...] = ()
    selected_unit_ids: tuple[str, ...] = ()
    moved_unit_ids: tuple[str, ...] = ()
    movement_distance_records: tuple[MovementDistanceRecord, ...] = ()
    active_selection: MovementUnitSelection | None = None
    pending_action: PendingMovementActionSelection | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("MovementPhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("MovementPhaseState active_player_id", self.active_player_id),
        )
        object.__setattr__(self, "step", movement_phase_step_kind_from_token(self.step))
        object.__setattr__(
            self,
            "reinforcements_completed",
            _validate_bool(
                "MovementPhaseState reinforcements_completed",
                self.reinforcements_completed,
            ),
        )
        object.__setattr__(
            self,
            "declined_disembark_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState declined_disembark_unit_ids",
                self.declined_disembark_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "declined_post_normal_move_disembark_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState declined_post_normal_move_disembark_unit_ids",
                self.declined_post_normal_move_disembark_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState selected_unit_ids",
                self.selected_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "moved_unit_ids",
            _validate_identifier_tuple(
                "MovementPhaseState moved_unit_ids",
                self.moved_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "movement_distance_records",
            _validate_movement_distance_records(
                "MovementPhaseState movement_distance_records",
                self.movement_distance_records,
            ),
        )
        for unit_id in self.moved_unit_ids:
            if unit_id not in self.selected_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState moved_unit_ids must be in selected_unit_ids."
                )
        for record in self.movement_distance_records:
            if record.unit_instance_id not in self.moved_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState movement_distance_records must be in moved_unit_ids."
                )
        if self.step is MovementPhaseStepKind.REINFORCEMENTS:
            raise GameLifecycleError("Reinforcements is not a Movement phase step.")
        if self.active_selection is not None:
            if type(self.active_selection) is not MovementUnitSelection:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must be a MovementUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must match active_player_id."
                )
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must match battle_round."
                )
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must be in selected_unit_ids."
                )
            if self.active_selection.unit_instance_id in self.moved_unit_ids:
                raise GameLifecycleError(
                    "MovementPhaseState active_selection must not already be moved."
                )
        if self.pending_action is not None:
            if type(self.pending_action) is not PendingMovementActionSelection:
                raise GameLifecycleError(
                    "MovementPhaseState pending_action must be a PendingMovementActionSelection."
                )
            if self.active_selection is None:
                raise GameLifecycleError(
                    "MovementPhaseState pending_action requires active_selection."
                )
            if self.pending_action.player_id != self.active_player_id:
                raise GameLifecycleError(
                    "MovementPhaseState pending_action must match active_player_id."
                )
            if self.pending_action.battle_round != self.battle_round:
                raise GameLifecycleError(
                    "MovementPhaseState pending_action must match battle_round."
                )
            if self.pending_action.unit_instance_id != self.active_selection.unit_instance_id:
                raise GameLifecycleError(
                    "MovementPhaseState pending_action must match active_selection."
                )

    def legal_unit_ids(
        self,
        scenario: BattlefieldScenario,
        *,
        accounted_unplaced_model_ids: tuple[str, ...] = (),
    ) -> tuple[str, ...]:
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            return ()
        return _remaining_move_units_unit_ids(
            scenario=scenario,
            active_player_id=self.active_player_id,
            selected_unit_ids=self.selected_unit_ids,
            accounted_unplaced_model_ids=accounted_unplaced_model_ids,
        )

    def with_unit_selection(self, selection: MovementUnitSelection) -> Self:
        if type(selection) is not MovementUnitSelection:
            raise GameLifecycleError("Movement selection must be a MovementUnitSelection.")
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Movement selection requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Movement selection requires no active movement selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Movement selection player_id must match active player.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Movement selection battle_round must match phase state.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Movement unit has already been selected this phase.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            moved_unit_ids=self.moved_unit_ids,
            movement_distance_records=self.movement_distance_records,
            active_selection=selection,
            pending_action=None,
        )

    def with_pending_action(self, pending_action: PendingMovementActionSelection) -> Self:
        if type(pending_action) is not PendingMovementActionSelection:
            raise GameLifecycleError(
                "Movement pending action requires a PendingMovementActionSelection."
            )
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Movement pending action requires Move Units step.")
        if self.active_selection is None:
            raise GameLifecycleError("Movement pending action requires active_selection.")
        if pending_action.player_id != self.active_player_id:
            raise GameLifecycleError("Movement pending action player_id drift.")
        if pending_action.battle_round != self.battle_round:
            raise GameLifecycleError("Movement pending action battle_round drift.")
        if pending_action.unit_instance_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Movement pending action unit drift.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            movement_distance_records=self.movement_distance_records,
            active_selection=self.active_selection,
            pending_action=pending_action,
        )

    def without_pending_action(self) -> Self:
        if self.pending_action is None:
            return self
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            movement_distance_records=self.movement_distance_records,
            active_selection=self.active_selection,
            pending_action=None,
        )

    def with_disembark_declined(self, unit_instance_ids: tuple[str, ...]) -> Self:
        declined_ids = _validate_identifier_tuple("unit_instance_ids", unit_instance_ids)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Disembark decline requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Disembark decline requires no active_selection.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=tuple(
                sorted((*self.declined_disembark_unit_ids, *declined_ids))
            ),
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            movement_distance_records=self.movement_distance_records,
            active_selection=None,
            pending_action=None,
        )

    def with_post_normal_move_disembark_declined(
        self,
        unit_instance_ids: tuple[str, ...],
    ) -> Self:
        declined_ids = _validate_identifier_tuple("unit_instance_ids", unit_instance_ids)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Post-move Disembark decline requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Post-move Disembark decline requires no active_selection.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=tuple(
                sorted((*self.declined_post_normal_move_disembark_unit_ids, *declined_ids))
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            movement_distance_records=self.movement_distance_records,
            active_selection=None,
            pending_action=None,
        )

    def with_post_normal_move_disembark_counted_as_moved(
        self,
        unit_instance_id: str,
    ) -> Self:
        moved_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError(
                "Post-move Disembark movement record requires Move Units step."
            )
        if self.active_selection is not None:
            raise GameLifecycleError(
                "Post-move Disembark movement record requires no active_selection."
            )
        if moved_unit_id in self.selected_unit_ids or moved_unit_id in self.moved_unit_ids:
            raise GameLifecycleError("Post-move Disembark unit already has movement state.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=(*self.selected_unit_ids, moved_unit_id),
            moved_unit_ids=(*self.moved_unit_ids, moved_unit_id),
            movement_distance_records=self.movement_distance_records,
            active_selection=None,
            pending_action=None,
        )

    def with_activation_complete(
        self,
        unit_instance_id: str,
        *,
        maximum_model_distance_inches: float,
    ) -> Self:
        completed_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        maximum_distance = _validate_non_negative_finite_number(
            "maximum_model_distance_inches",
            maximum_model_distance_inches,
        )
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Movement activation completion requires Move Units step.")
        if self.active_selection is None:
            raise GameLifecycleError("Movement activation completion requires active_selection.")
        if completed_unit_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Movement activation completion must match active_selection.")
        if completed_unit_id in self.moved_unit_ids:
            raise GameLifecycleError("Movement unit has already completed movement.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=(*self.moved_unit_ids, completed_unit_id),
            movement_distance_records=(
                *self.movement_distance_records,
                MovementDistanceRecord(
                    unit_instance_id=completed_unit_id,
                    maximum_model_distance_inches=maximum_distance,
                ),
            ),
            active_selection=None,
            pending_action=None,
        )

    def with_step(self, step: MovementPhaseStepKind) -> Self:
        requested_step = movement_phase_step_kind_from_token(step)
        if requested_step is self.step:
            return self
        raise GameLifecycleError("MovementPhaseState has no secondary movement phase step.")

    def with_reinforcement_arrival(self, unit_instance_id: str) -> Self:
        arrived_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Reinforcement arrival requires Move Units step.")
        if self.reinforcements_completed:
            raise GameLifecycleError("Reinforcement arrival requires incomplete Move Units.")
        selected = self.selected_unit_ids
        moved = self.moved_unit_ids
        if arrived_unit_id not in selected:
            selected = (*selected, arrived_unit_id)
        if arrived_unit_id not in moved:
            moved = (*moved, arrived_unit_id)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=self.reinforcements_completed,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=selected,
            moved_unit_ids=moved,
            movement_distance_records=self.movement_distance_records,
            active_selection=None,
            pending_action=None,
        )

    def with_end_movement_ingress_arrival(self, unit_instance_id: str) -> Self:
        arrived_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("End-movement ingress requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("End-movement ingress requires no active_selection.")
        selected = self.selected_unit_ids
        moved = self.moved_unit_ids
        if arrived_unit_id not in selected:
            selected = (*selected, arrived_unit_id)
        if arrived_unit_id not in moved:
            moved = (*moved, arrived_unit_id)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=True,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=selected,
            moved_unit_ids=moved,
            movement_distance_records=self.movement_distance_records,
            active_selection=None,
            pending_action=None,
        )

    def with_reinforcements_completed(self) -> Self:
        if self.step is not MovementPhaseStepKind.MOVE_UNITS:
            raise GameLifecycleError("Completing reserve arrivals requires Move Units step.")
        if self.active_selection is not None:
            raise GameLifecycleError("Completing reserve arrivals requires no active_selection.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            step=self.step,
            reinforcements_completed=True,
            declined_disembark_unit_ids=self.declined_disembark_unit_ids,
            declined_post_normal_move_disembark_unit_ids=(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            selected_unit_ids=self.selected_unit_ids,
            moved_unit_ids=self.moved_unit_ids,
            movement_distance_records=self.movement_distance_records,
            active_selection=None,
            pending_action=None,
        )

    def to_payload(self) -> MovementPhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "step": self.step.value,
            "reinforcements_completed": self.reinforcements_completed,
            "declined_disembark_unit_ids": list(self.declined_disembark_unit_ids),
            "declined_post_normal_move_disembark_unit_ids": list(
                self.declined_post_normal_move_disembark_unit_ids
            ),
            "selected_unit_ids": list(self.selected_unit_ids),
            "moved_unit_ids": list(self.moved_unit_ids),
            "movement_distance_records": [
                record.to_payload() for record in self.movement_distance_records
            ],
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
            "pending_action": (
                None if self.pending_action is None else self.pending_action.to_payload()
            ),
        }

    @classmethod
    def from_payload(cls, payload: MovementPhaseStatePayload) -> Self:
        active_selection_payload = payload["active_selection"]
        pending_action_payload = payload["pending_action"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            step=movement_phase_step_kind_from_token(payload["step"]),
            reinforcements_completed=payload["reinforcements_completed"],
            declined_disembark_unit_ids=tuple(payload["declined_disembark_unit_ids"]),
            declined_post_normal_move_disembark_unit_ids=tuple(
                payload["declined_post_normal_move_disembark_unit_ids"]
            ),
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            moved_unit_ids=tuple(payload["moved_unit_ids"]),
            movement_distance_records=tuple(
                MovementDistanceRecord.from_payload(record_payload)
                for record_payload in payload.get("movement_distance_records", [])
            ),
            active_selection=(
                None
                if active_selection_payload is None
                else MovementUnitSelection.from_payload(active_selection_payload)
            ),
            pending_action=(
                None
                if pending_action_payload is None
                else PendingMovementActionSelection.from_payload(pending_action_payload)
            ),
        )


@dataclass(frozen=True, slots=True)
class NormalMoveResolution:
    unit_instance_id: str
    attempted_placement: UnitPlacement
    witness: PathWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("NormalMoveResolution unit_instance_id", self.unit_instance_id),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "NormalMoveResolution attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError(
                "NormalMoveResolution attempted_placement must match unit_instance_id."
            )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("NormalMoveResolution witness must be a PathWitness.")
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(
                "NormalMoveResolution path_validation_results",
                self.path_validation_results,
            ),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(
                "NormalMoveResolution terrain_path_legality_results",
                self.terrain_path_legality_results,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "NormalMoveResolution coherency_result must be a UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "NormalMoveResolution rollback_record must be a MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "NormalMoveResolution movement_payload",
                self.movement_payload,
            ),
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    def transition_batch(self, *, before: UnitPlacement) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Normal Move cannot emit displacement records.")
        return _normal_move_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
        )


@dataclass(frozen=True, slots=True)
class AdvanceMoveResolution:
    unit_instance_id: str
    attempted_placement: UnitPlacement
    witness: PathWitness
    advance_roll: AdvanceRollResult
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AdvanceMoveResolution unit_instance_id", self.unit_instance_id),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "AdvanceMoveResolution attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError(
                "AdvanceMoveResolution attempted_placement must match unit_instance_id."
            )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("AdvanceMoveResolution witness must be a PathWitness.")
        if type(self.advance_roll) is not AdvanceRollResult:
            raise GameLifecycleError(
                "AdvanceMoveResolution advance_roll must be an AdvanceRollResult."
            )
        if self.advance_roll.request.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("AdvanceMoveResolution advance_roll unit drift.")
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(
                "AdvanceMoveResolution path_validation_results",
                self.path_validation_results,
            ),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(
                "AdvanceMoveResolution terrain_path_legality_results",
                self.terrain_path_legality_results,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "AdvanceMoveResolution coherency_result must be a UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "AdvanceMoveResolution rollback_record must be a MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "AdvanceMoveResolution movement_payload",
                self.movement_payload,
            ),
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    def transition_batch(self, *, before: UnitPlacement) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Advance cannot emit displacement records.")
        return _movement_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
            displacement_kind=ModelDisplacementKind.ADVANCE,
        )


@dataclass(frozen=True, slots=True)
class FallBackActionResult:
    unit_instance_id: str
    attempted_placement: UnitPlacement
    witness: PathWitness
    desperate_escape_requirements: tuple[DesperateEscapeRequirement, ...]
    desperate_escape_rolls: tuple[DesperateEscapeRoll, ...]
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("FallBackActionResult unit_instance_id", self.unit_instance_id),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "FallBackActionResult attempted_placement must be a UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError(
                "FallBackActionResult attempted_placement must match unit_instance_id."
            )
        if type(self.witness) is not PathWitness:
            raise GameLifecycleError("FallBackActionResult witness must be a PathWitness.")
        object.__setattr__(
            self,
            "desperate_escape_requirements",
            _validate_desperate_escape_requirement_tuple(
                "FallBackActionResult desperate_escape_requirements",
                self.desperate_escape_requirements,
            ),
        )
        for requirement in self.desperate_escape_requirements:
            if requirement.unit_instance_id != self.unit_instance_id:
                raise GameLifecycleError("FallBackActionResult requirement unit drift.")
        object.__setattr__(
            self,
            "desperate_escape_rolls",
            _validate_desperate_escape_roll_tuple(
                "FallBackActionResult desperate_escape_rolls",
                self.desperate_escape_rolls,
            ),
        )
        requirement_by_id = {
            requirement.requirement_id: requirement
            for requirement in self.desperate_escape_requirements
        }
        for roll in self.desperate_escape_rolls:
            expected_requirement = requirement_by_id.get(roll.requirement.requirement_id)
            if expected_requirement is None:
                raise GameLifecycleError(
                    "FallBackActionResult roll must match a Desperate Escape requirement."
                )
            if roll.requirement != expected_requirement:
                raise GameLifecycleError("FallBackActionResult roll requirement drift.")
        if len(self.desperate_escape_rolls) not in {0, len(self.desperate_escape_requirements)}:
            raise GameLifecycleError(
                "FallBackActionResult must roll either no Desperate Escape tests or every "
                "requirement."
            )
        object.__setattr__(
            self,
            "path_validation_results",
            _validate_path_validation_result_tuple(
                "FallBackActionResult path_validation_results",
                self.path_validation_results,
            ),
        )
        object.__setattr__(
            self,
            "terrain_path_legality_results",
            _validate_terrain_path_legality_result_tuple(
                "FallBackActionResult terrain_path_legality_results",
                self.terrain_path_legality_results,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "FallBackActionResult coherency_result must be a UnitCoherencyResult."
            )
        if self.rollback_record is not None and type(self.rollback_record) is not (
            MovementRollbackRecord
        ):
            raise GameLifecycleError(
                "FallBackActionResult rollback_record must be a MovementRollbackRecord."
            )
        object.__setattr__(
            self,
            "movement_payload",
            _validate_json_object(
                "FallBackActionResult movement_payload",
                self.movement_payload,
            ),
        )

    @classmethod
    def unresolved(
        cls,
        *,
        unit_instance_id: str,
        attempted_placement: UnitPlacement,
        witness: PathWitness,
        desperate_escape_requirements: tuple[DesperateEscapeRequirement, ...],
        path_validation_results: tuple[PathValidationResult, ...],
        terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...],
        coherency_result: UnitCoherencyResult,
        rollback_record: MovementRollbackRecord | None,
        movement_payload: dict[str, JsonValue],
    ) -> Self:
        return cls(
            unit_instance_id=unit_instance_id,
            attempted_placement=attempted_placement,
            witness=witness,
            desperate_escape_requirements=desperate_escape_requirements,
            desperate_escape_rolls=(),
            path_validation_results=path_validation_results,
            terrain_path_legality_results=terrain_path_legality_results,
            coherency_result=coherency_result,
            rollback_record=rollback_record,
            movement_payload=movement_payload,
        )

    @classmethod
    def with_desperate_escape_rolls(
        cls,
        *,
        resolution: FallBackActionResult,
        desperate_escape_rolls: tuple[DesperateEscapeRoll, ...],
    ) -> Self:
        if type(resolution) is not FallBackActionResult:
            raise GameLifecycleError("Fall Back resolution must be a FallBackActionResult.")
        return cls(
            unit_instance_id=resolution.unit_instance_id,
            attempted_placement=resolution.attempted_placement,
            witness=resolution.witness,
            desperate_escape_requirements=resolution.desperate_escape_requirements,
            desperate_escape_rolls=desperate_escape_rolls,
            path_validation_results=resolution.path_validation_results,
            terrain_path_legality_results=resolution.terrain_path_legality_results,
            coherency_result=resolution.coherency_result,
            rollback_record=resolution.rollback_record,
            movement_payload={
                **resolution.movement_payload,
                "desperate_escape_rolls": validate_json_value(
                    [roll.to_payload() for roll in desperate_escape_rolls]
                ),
            },
        )

    @property
    def is_valid(self) -> bool:
        return (
            all(result.is_valid for result in self.path_validation_results)
            and all(result.is_valid for result in self.terrain_path_legality_results)
            and self.rollback_record is None
        )

    @property
    def failed_desperate_escape_rolls(self) -> tuple[DesperateEscapeRoll, ...]:
        return tuple(roll for roll in self.desperate_escape_rolls if roll.is_failed)

    def transition_batch(
        self,
        *,
        before: UnitPlacement,
        destroyed_model_ids: tuple[str, ...],
    ) -> BattlefieldTransitionBatch:
        if not self.is_valid:
            raise GameLifecycleError("Invalid Fall Back cannot emit transition records.")
        if self.desperate_escape_requirements and not self.desperate_escape_rolls:
            raise GameLifecycleError(
                "Fall Back cannot emit transition records before Desperate Escape rolls are "
                "resolved."
            )
        destroyed_ids = _validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids)
        failed_model_ids = tuple(
            roll.requirement.model_instance_id for roll in self.failed_desperate_escape_rolls
        )
        if len(destroyed_ids) != len(failed_model_ids):
            raise GameLifecycleError(
                "Fall Back must select one model for every failed Desperate Escape roll."
            )
        eligible_model_ids = {
            placement.model_instance_id for placement in self.attempted_placement.model_placements
        }
        for destroyed_id in destroyed_ids:
            if destroyed_id not in eligible_model_ids:
                raise GameLifecycleError(
                    "Fall Back destroyed_model_ids must be eligible falling-back models."
                )
        return _fall_back_transition_batch(
            before=before,
            after=self.attempted_placement,
            witness=self.witness,
            destroyed_model_ids=destroyed_ids,
        )

    def surviving_attempted_placement(
        self,
        *,
        destroyed_model_ids: tuple[str, ...],
    ) -> UnitPlacement | None:
        destroyed_ids = set(_validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids))
        surviving_placements = tuple(
            placement
            for placement in self.attempted_placement.model_placements
            if placement.model_instance_id not in destroyed_ids
        )
        if not surviving_placements:
            return None
        return self.attempted_placement.with_model_placements(surviving_placements)

    def to_payload(self) -> FallBackActionResultPayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "attempted_placement": self.attempted_placement.to_payload(),
            "witness": self.witness.to_payload(),
            "desperate_escape_requirements": [
                requirement.to_payload() for requirement in self.desperate_escape_requirements
            ],
            "desperate_escape_rolls": [roll.to_payload() for roll in self.desperate_escape_rolls],
            "path_validation_results": [
                result.to_payload() for result in self.path_validation_results
            ],
            "terrain_path_legality_results": [
                result.to_payload() for result in self.terrain_path_legality_results
            ],
            "coherency_result": self.coherency_result.to_payload(),
            "rollback_record": (
                None if self.rollback_record is None else self.rollback_record.to_payload()
            ),
            "movement_payload": self.movement_payload,
        }

    @classmethod
    def from_payload(cls, payload: FallBackActionResultPayload) -> Self:
        rollback_payload = payload["rollback_record"]
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            attempted_placement=UnitPlacement.from_payload(payload["attempted_placement"]),
            witness=PathWitness.from_payload(payload["witness"]),
            desperate_escape_requirements=tuple(
                DesperateEscapeRequirement.from_payload(requirement)
                for requirement in payload["desperate_escape_requirements"]
            ),
            desperate_escape_rolls=tuple(
                DesperateEscapeRoll.from_payload(roll) for roll in payload["desperate_escape_rolls"]
            ),
            path_validation_results=tuple(
                PathValidationResult.from_payload(result)
                for result in payload["path_validation_results"]
            ),
            terrain_path_legality_results=tuple(
                TerrainPathLegalityResult.from_payload(result)
                for result in payload["terrain_path_legality_results"]
            ),
            coherency_result=UnitCoherencyResult.from_payload(payload["coherency_result"]),
            rollback_record=(
                None
                if rollback_payload is None
                else MovementRollbackRecord.from_payload(rollback_payload)
            ),
            movement_payload=payload["movement_payload"],
        )


@dataclass(frozen=True, slots=True)
class _ResolvedUnitMove:
    attempted_placement: UnitPlacement
    witness: PathWitness
    path_validation_results: tuple[PathValidationResult, ...]
    terrain_path_legality_results: tuple[TerrainPathLegalityResult, ...]
    coherency_result: UnitCoherencyResult
    rollback_record: MovementRollbackRecord | None
    movement_payload: dict[str, JsonValue]
    desperate_escape_auto_pass_model_ids: tuple[str, ...] = ()
