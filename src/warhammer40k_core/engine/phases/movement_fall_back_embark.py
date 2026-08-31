# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.movement_imports import *
from warhammer40k_core.engine.battle_shock import BattleShockTestReason
from warhammer40k_core.engine.battle_shock_resolution import BattleShockPassedStatePolicy
from warhammer40k_core.engine.battle_shock_test_service import (
    BattleShockTestRuntime,
    resolve_battle_shock_test,
)
from warhammer40k_core.engine.desperate_escape import (
    DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND,
    DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
)
from warhammer40k_core.engine.primary_destruction_evidence import (
    PrimaryUnattributedDestructionCause,
)
from warhammer40k_core.engine.primary_historical_events import (
    record_new_primary_battlefield_departure_events,
    record_new_primary_unit_destruction_events,
)
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked
from warhammer40k_core.engine.primary_unit_destruction_tracking import (
    record_primary_unit_destructions_for_destroyed_models,
)
from warhammer40k_core.engine.phases.movement_model import *
from warhammer40k_core.engine.phases.movement_state import *
from warhammer40k_core.engine.phases.movement_battle_shock_continuation import (
    begin_desperate_escape_battle_shock_continuation,
    record_desperate_escape_battle_shock_resolution,
)
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
    from warhammer40k_core.engine.phases.movement_model import SELECT_MOVEMENT_UNIT_DECISION_TYPE, SELECT_MOVEMENT_ACTION_DECISION_TYPE, SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE, SELECT_EMBARK_TRANSPORT_DECISION_TYPE, DECLINE_EMBARK_OPTION_ID, MovementPhaseStepKind, MovementPhaseActionKind, MovementUnitLocationKind, FallBackModeKind, DesperateEscapeRequirementReason, _MOVEMENT_ACTIONS_OUTSIDE_ENEMY_ENGAGEMENT, _MOVEMENT_ACTIONS_INSIDE_ENEMY_ENGAGEMENT, _ADVANCE_REROLL_KEYWORD, _ADVANCED_UNIT_CLEANUP_POINT, _FELL_BACK_UNIT_CLEANUP_POINT, _DESPERATE_ESCAPE_ROLL_TYPE, _empty_ability_indexes, _MovementProposalParseResult, _PlacementProposalParseResult, MovementUnitSelectionPayload, PendingMovementActionSelectionPayload, MovementPhaseStatePayload, MovementActionAvailabilityContextPayload, MovementActionAvailabilityResultPayload, MovementDistanceRecordPayload, AdvanceRollRequestPayload, AdvanceRollResultPayload, MovementDiceRecordPayload, AdvancedUnitStatePayload, DesperateEscapeRequirementPayload, DesperateEscapeRollPayload, FellBackUnitStatePayload, FallBackActionResultPayload, MovementActionAvailabilityContext, MovementActionAvailabilityResult, AdvanceRollRequest, AdvanceRollResult, MovementDiceRecord, AdvancedUnitState, DesperateEscapeRequirement, DesperateEscapeRoll, FellBackUnitState, MovementUnitSelection, PendingMovementActionSelection, DisembarkCandidate, MovementDistanceRecord
    from warhammer40k_core.engine.phases.movement_state import MovementPhaseState, NormalMoveResolution, AdvanceMoveResolution, FallBackActionResult, _ResolvedUnitMove
    from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler, _complete_move_units_step
    from warhammer40k_core.engine.phases.movement_reactions import _request_end_opponent_movement_reaction_if_available, _request_end_movement_active_player_stratagem_if_available, _request_rapid_ingress_reaction_if_available, _request_fire_overwatch_reaction_if_available, _request_selected_to_move_stratagem_if_available, _request_selected_to_fall_back_stratagem_if_available, _request_friendly_unit_fell_back_stratagem_if_available, _friendly_unit_fell_back_context_from_event, _friendly_unit_fell_back_timing_window_id, _stratagem_used_for_context, _selected_to_fall_back_trigger_payload, _selected_to_fall_back_timing_window_id, _selected_to_move_timing_window_id, _stratagem_use_payload_factory, _stratagem_target_proposal_payload_factory, _request_movement_end_surge_if_available, _movement_end_surge_distance_roll_spec, _eligible_triggered_movement_units_from_grants, _movement_end_surge_grant_distance_bonus, _movement_end_surge_event_already_processed, _active_player_end_movement_overwatch_trigger_unit_ids, _fire_overwatch_end_movement_trigger_payload
    from warhammer40k_core.engine.phases.movement_reinforcements import _eligible_reinforcement_reserve_states, _required_reinforcement_reserve_states, _overdue_required_reinforcement_reserve_states, _request_reinforcement_placement, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _request_placement_proposal_retry, _optional_proposal_context_string, _resolve_reinforcement_placement_submission, _deep_strike_enemy_distance_for_reserve_arrival, _unit_for_reserve_state, _apply_valid_reinforcement_placement
    from warhammer40k_core.engine.phases.movement_transports import _request_disembark_placement, _resolve_disembark_placement_submission, _allowed_disembark_modes_for_placement_request, _resolve_combat_disembark_placement_submission, _disembark_candidate_for_movement_unit
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
    "_maximum_model_horizontal_distance_inches_from_witness",
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
    battle_shock_hooks: BattleShockHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    reaction_queue: ReactionQueue | None,
    stratagem_index: StratagemCatalogIndex | None,
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
    from warhammer40k_core.engine.phases.movement_rules_units import (
        rules_unit_placement_for_movement,
    )

    _rules_unit, unit_placement = rules_unit_placement_for_movement(
        state=state,
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )
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
        destruction_source_result_id=result.result_id,
        unit_placement=unit_placement,
        fall_back_result=fall_back_result,
        destroyed_model_ids=destroyed_model_ids,
        movement_proposal_request_id=_payload_string(
            context_payload,
            key="movement_proposal_request_id",
        ),
        ruleset_descriptor=ruleset_descriptor,
        fall_back_hooks=fall_back_hooks,
        battle_shock_hooks=battle_shock_hooks,
        ability_index=ability_index,
        runtime_modifier_registry=runtime_modifier_registry,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
    )


def _apply_fall_back_result(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    destruction_source_result_id: str | None,
    unit_placement: UnitPlacement | RulesUnitPlacement,
    fall_back_result: FallBackActionResult,
    destroyed_model_ids: tuple[str, ...],
    movement_proposal_request_id: str,
    ruleset_descriptor: RulesetDescriptor,
    fall_back_hooks: FallBackEligibilityHookRegistry,
    battle_shock_hooks: BattleShockHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    reaction_queue: ReactionQueue | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
) -> LifecycleStatus | None:
    active_player_id = _active_player_id(state)
    scenario = _battlefield_scenario(state)
    movement_unit_id = (
        unit_placement.unit_instance_id
        if isinstance(unit_placement, UnitPlacement)
        else unit_placement.rules_unit_instance_id
    )
    if movement_unit_id != fall_back_result.unit_instance_id:
        raise GameLifecycleError("Fall Back rules-unit identity drift.")
    destruction_source_payload: dict[str, JsonValue] = {}
    if destroyed_model_ids:
        if destruction_source_result_id is None:
            raise GameLifecycleError(
                "Desperate Escape destruction requires its model-selection result ID."
            )
        destruction_source_payload["desperate_escape_source_mutation_id"] = _validate_identifier(
            "destruction_source_result_id",
            destruction_source_result_id,
        )
    elif destruction_source_result_id is not None:
        raise GameLifecycleError(
            "Desperate Escape source result requires destroyed model evidence."
        )
    surviving_placement = fall_back_result.surviving_attempted_placement(
        destroyed_model_ids=destroyed_model_ids,
    )
    if surviving_placement is not None:
        from warhammer40k_core.engine.phases.movement_rules_units import (
            rules_unit_placement_coherency_result,
        )

        survivor_coherency_result = rules_unit_placement_coherency_result(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            placement=surviving_placement,
            rules_unit_instance_id=movement_unit_id,
        )
        if not survivor_coherency_result.is_coherent:
            violation_code = "unit_coherency_broken"
            invalid_payload = _movement_action_invalid_payload(
                state=state,
                active_player_id=active_player_id,
                unit_instance_id=movement_unit_id,
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
                    "unit_instance_id": movement_unit_id,
                    "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                    "violation_code": violation_code,
                },
            )
    transition_batch = fall_back_result.transition_batch(
        before=unit_placement,
        destroyed_model_ids=destroyed_model_ids,
    )
    engagement_placement = (
        unit_placement
        if isinstance(unit_placement, UnitPlacement)
        else unit_placement.component_unit_placements[0]
    )
    start_engaged_enemy_unit_ids = _enemy_engaged_unit_ids_for_unit_placement(
        scenario=scenario,
        unit_placement=engagement_placement,
        ruleset_descriptor=ruleset_descriptor,
    )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Fall Back requires battlefield_state.")
    attempted = fall_back_result.attempted_placement
    if isinstance(attempted, UnitPlacement):
        updated_battlefield = battlefield_state.with_unit_placement(attempted)
    else:
        updated_battlefield = battlefield_state
        for component in attempted.component_unit_placements:
            updated_battlefield = updated_battlefield.with_unit_placement(component)
    state.replace_battlefield_state(updated_battlefield.with_removed_models(destroyed_model_ids))
    if destroyed_model_ids:
        destruction_source_id = _payload_string(
            destruction_source_payload,
            key="desperate_escape_source_mutation_id",
        )
        departure_ids_before = tuple(
            value.departure_id for value in state.primary_battlefield_departure_states
        )
        destruction_ids_before = tuple(
            value.destruction_id for value in state.primary_unit_destruction_states
        )
        record_primary_unit_destructions_for_destroyed_models(
            state=state,
            destroyed_model_instance_ids=destroyed_model_ids,
            destruction_attribution=None,
            source_model_destroyed_event_id=None,
            source_rules_unit_objective_proximity_witness=None,
            destroyed_rules_unit_objective_proximity_witness=None,
            unattributed_cause=PrimaryUnattributedDestructionCause.DESPERATE_ESCAPE,
            source_mutation_id=destruction_source_id,
            left_battlefield=True,
            source_id=f"core-rules:desperate-escape:{destruction_source_id}",
        )
        record_new_primary_battlefield_departure_events(
            state=state,
            event_log=decisions.event_log,
            departure_ids_before=departure_ids_before,
        )
        record_new_primary_unit_destruction_events(
            state=state,
            event_log=decisions.event_log,
            destruction_ids_before=destruction_ids_before,
        )
    permission_grants: tuple[FallBackEligibilityGrant, ...] = ()
    if surviving_placement is not None:
        permission_grants = fall_back_hooks.grants_for(
            FallBackEligibilityContext(
                state=state,
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=movement_unit_id,
                movement_request_id=result.request_id,
                movement_result_id=result.result_id,
            )
        )
        state.record_fell_back_unit_state(
            FellBackUnitState(
                player_id=active_player_id,
                battle_round=state.battle_round,
                unit_instance_id=movement_unit_id,
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
                    "unit_instance_id": movement_unit_id,
                    "request_id": result.request_id,
                    "result_id": result.result_id,
                    "grants": [
                        validate_json_value(grant.to_payload()) for grant in permission_grants
                    ],
                },
            )
    movement_payload: dict[str, JsonValue] = {
        **fall_back_result.movement_payload,
        "battle_shocked_after_move": rules_unit_is_battle_shocked(
            state=state,
            unit_instance_id=movement_unit_id,
        ),
        "destroyed_model_ids": list(destroyed_model_ids),
        **destruction_source_payload,
        "start_engaged_enemy_unit_instance_ids": list(start_engaged_enemy_unit_ids),
        "fall_back_eligibility_grants": [
            validate_json_value(grant.to_payload()) for grant in permission_grants
        ],
    }
    fall_back_applied_event_id: str | None = None
    if desperate_escape_battle_shock_required(
        movement_payload=movement_payload,
        has_surviving_models=surviving_placement is not None,
    ):
        applied_event = decisions.event_log.append(
            "fall_back_move_applied",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": movement_unit_id,
                "source_rule_id": DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
                "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "destroyed_model_ids": list(destroyed_model_ids),
                **destruction_source_payload,
                "movement_proposal_request_id": movement_proposal_request_id,
                "fall_back_result": validate_json_value(fall_back_result.to_payload()),
                "movement_payload": validate_json_value(movement_payload),
                "transition_batch": validate_json_value(transition_batch.to_payload()),
            },
        )
        fall_back_applied_event_id = applied_event.event_id
        begin_desperate_escape_battle_shock_continuation(
            state=state,
            continuation=PendingDesperateEscapeBattleShockContinuation(
                source_kind=(DesperateEscapeBattleShockContinuationSourceKind.VOLUNTARY_POST_MOVE),
                continuation_phase=(
                    DesperateEscapeBattleShockContinuationPhase.AWAITING_BATTLE_SHOCK
                ),
                canonical_unit_instance_id=movement_unit_id,
                movement_proposal_request_id=movement_proposal_request_id,
                action_result=result,
                fall_back_result=fall_back_result,
                fall_back_applied_event_id=applied_event.event_id,
                movement_payload=movement_payload,
                transition_batch=transition_batch,
                battle_shock_request_id=(
                    f"desperate-escape:{state.battle_round:02d}:{movement_unit_id}"
                ),
            ),
        )
        battle_shock_status = _resolve_desperate_escape_battle_shock_after_move(
            state=state,
            decisions=decisions,
            fall_back_result=fall_back_result,
            result=result,
            movement_proposal_request_id=movement_proposal_request_id,
            movement_payload=movement_payload,
            transition_batch=transition_batch,
            fall_back_applied_event_id=applied_event.event_id,
            battle_shock_hooks=battle_shock_hooks,
            ability_index=ability_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if battle_shock_status is not None:
            return battle_shock_status
    return _request_embark_after_move_or_complete_activation(
        state=state,
        decisions=decisions,
        result=result,
        action=MovementPhaseActionKind.FALL_BACK,
        witness=fall_back_result.witness,
        movement_payload=movement_payload,
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        transition_batch=transition_batch,
        ruleset_descriptor=ruleset_descriptor,
        reaction_queue=reaction_queue,
        stratagem_index=stratagem_index,
        fall_back_applied_event_id=fall_back_applied_event_id,
    )


def _resolve_desperate_escape_battle_shock_after_move(
    *,
    state: GameState,
    decisions: DecisionController,
    fall_back_result: FallBackActionResult,
    result: DecisionResult,
    movement_proposal_request_id: str,
    movement_payload: dict[str, JsonValue],
    transition_batch: BattlefieldTransitionBatch,
    fall_back_applied_event_id: str,
    battle_shock_hooks: BattleShockHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    raw_destroyed_model_ids = movement_payload.get("destroyed_model_ids")
    if not isinstance(raw_destroyed_model_ids, list) or any(
        type(model_id) is not str for model_id in raw_destroyed_model_ids
    ):
        raise GameLifecycleError("Desperate Escape destroyed-model authority is invalid.")
    active_player_id = _active_player_id(state)
    execution = resolve_battle_shock_test(
        runtime=BattleShockTestRuntime(
            ability_indexes_by_player_id={active_player_id: ability_index},
            runtime_modifier_registry=runtime_modifier_registry,
            battle_shock_hook_registry=battle_shock_hooks,
        ),
        state=state,
        decisions=decisions,
        request_id=(
            f"desperate-escape:{state.battle_round:02d}:{fall_back_result.unit_instance_id}"
        ),
        target_unit_instance_id=fall_back_result.unit_instance_id,
        reason=BattleShockTestReason.DESPERATE_ESCAPE,
        active_player_id=active_player_id,
        phase=BattlePhase.MOVEMENT,
        phase_start_battle_shocked_unit_ids=tuple(sorted(state.battle_shocked_unit_ids)),
        passed_state_policy=BattleShockPassedStatePolicy.PRESERVE,
        source_kind=DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND,
        source_payload={
            "unit_instance_id": fall_back_result.unit_instance_id,
            "source_rule_id": DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
            "fall_back_applied_event_id": fall_back_applied_event_id,
            "fall_back_result": validate_json_value(fall_back_result.to_payload()),
            "action_result": validate_json_value(result.to_payload()),
            "movement_proposal_request_id": movement_proposal_request_id,
            "movement_payload": validate_json_value(movement_payload),
            "transition_batch": validate_json_value(transition_batch.to_payload()),
        },
        resolved_event_types=(
            "battle_shock_test_resolved",
            "desperate_escape_battle_shock_resolved",
        ),
        pending_phase_body_status="desperate_escape_battle_shock_reroll_pending",
    )
    return record_desperate_escape_battle_shock_resolution(
        state=state,
        decisions=decisions,
        battle_shock_hooks=battle_shock_hooks,
        resolution=execution.resolution,
        reroll_result_id=None,
    )


def desperate_escape_battle_shock_required(
    *,
    movement_payload: dict[str, JsonValue],
    has_surviving_models: bool,
) -> bool:
    if type(has_surviving_models) is not bool:
        raise GameLifecycleError("Desperate Escape survivor status must be bool.")
    battle_shocked_after_move = movement_payload.get("battle_shocked_after_move")
    if type(battle_shocked_after_move) is not bool:
        raise GameLifecycleError("Desperate Escape requires battle_shocked_after_move authority.")
    return (
        _fall_back_mode_from_payload(movement_payload) is FallBackModeKind.DESPERATE_ESCAPE
        and not battle_shocked_after_move
        and has_surviving_models
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
    fall_back_applied_event_id: str | None = None,
) -> LifecycleStatus | None:
    active_selection = _active_movement_selection(state)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Movement activation completion requires battlefield_state.")
    if fall_back_applied_event_id is not None:
        movement_payload = {
            **movement_payload,
            "fall_back_applied_event_id": _validate_identifier(
                "fall_back_applied_event_id",
                fall_back_applied_event_id,
            ),
        }
    reconciliation = reconcile_rules_unit_identity(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
    )
    if reconciliation.placed_surviving_unit_instance_ids != (active_selection.unit_instance_id,):
        _complete_movement_activation(
            state=state,
            decisions=decisions,
            result=result,
            action=action,
            witness=witness,
            movement_payload={
                **movement_payload,
                "rules_unit_identity_reconciliation": validate_json_value(
                    reconciliation.to_payload()
                ),
            },
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


def _post_move_embark_options(
    *,
    state: GameState,
    unit_instance_id: str,
    movement_phase_action: TransportMovementStatus,
) -> tuple[DecisionOption, ...]:
    scenario = _battlefield_scenario(state)
    from warhammer40k_core.engine.phases.movement_rules_units import (
        representative_movement_placement,
        rules_unit_placement_for_movement,
    )

    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    placed_model_ids = set(scenario.battlefield_state.placed_model_ids())
    if any(
        model.is_alive and model.model_instance_id not in placed_model_ids
        for model in rules_unit.own_models
    ):
        return ()
    _rules_unit, rules_unit_placement = rules_unit_placement_for_movement(
        state=state,
        scenario=scenario,
        unit_instance_id=unit_instance_id,
    )
    unit_placement = representative_movement_placement(rules_unit_placement)
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
            persisting_effects=_embark_persisting_effects(
                state=state,
                unit_instance_id=unit_instance_id,
            ),
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
        return None
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
    from warhammer40k_core.engine.phases.movement_rules_units import (
        representative_movement_placement,
        rules_unit_placement_for_movement,
    )

    _rules_unit, rules_unit_placement = rules_unit_placement_for_movement(
        state=state,
        scenario=scenario,
        unit_instance_id=active_selection.unit_instance_id,
    )
    resolution = resolve_embark(
        scenario=scenario,
        cargo_state=cargo_state,
        selection=selection,
        unit_placement=representative_movement_placement(rules_unit_placement),
        transport_placement=scenario.battlefield_state.unit_placement_by_id(
            selection.transport_unit_instance_id
        ),
        persisting_effects=_embark_persisting_effects(
            state=state,
            unit_instance_id=active_selection.unit_instance_id,
        ),
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
    if embark.transition_batch is None:
        raise GameLifecycleError("Valid EmbarkResolution requires a transition batch.")
    state.replace_battlefield_state(
        apply_embark_to_battlefield(
            battlefield_state=battlefield_state,
            embark=embark,
        )
    )
    state.replace_transport_cargo_state(embark.updated_cargo_state)
    embarked_rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=embark.selection.unit_instance_id,
    )
    departure_ids_before = tuple(
        value.departure_id for value in state.primary_battlefield_departure_states
    )
    record_primary_battlefield_departure(
        state=state,
        rules_unit_instance_id=embarked_rules_unit.unit_instance_id,
        affected_component_unit_instance_ids=(embarked_rules_unit.component_unit_instance_ids),
        departed_component_unit_instance_ids=(embarked_rules_unit.component_unit_instance_ids),
        removed_model_instance_ids=tuple(
            removal.model_instance_id for removal in embark.transition_batch.removals
        ),
        removal_kind=BattlefieldRemovalKind.EMBARK,
        occurrence_id=result.result_id,
        source_id=result.result_id,
    )
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
            "transition_batch": validate_json_value(embark.transition_batch.to_payload()),
        },
    )
    record_new_primary_battlefield_departure_events(
        state=state,
        event_log=decisions.event_log,
        departure_ids_before=departure_ids_before,
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


def _embark_persisting_effects(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[PersistingEffect, ...]:
    rules_unit = rules_unit_view_from_armies(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    identity_ids = tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )
    effect_by_id = {
        effect.effect_id: effect
        for identity_id in identity_ids
        for effect in state.persisting_effects_for_unit(identity_id)
    }
    return tuple(effect_by_id[effect_id] for effect_id in sorted(effect_by_id))


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
    if action is MovementPhaseActionKind.NORMAL_MOVE:
        state.record_normal_move_state(
            NormalMoveState(
                player_id=active_selection.player_id,
                battle_round=state.battle_round,
                phase=BattlePhase.MOVEMENT,
                unit_instance_id=active_selection.unit_instance_id,
                source_rule_id=ONE_NORMAL_MOVE_PER_PHASE_SOURCE_RULE_ID,
                source_kind=NormalMoveSourceKind.MOVEMENT_PHASE_ACTION,
                request_id=request_id,
                result_id=result_id,
            )
        )
    state.replace_movement_phase_state(
        movement_state.with_activation_complete(
            active_selection.unit_instance_id,
            maximum_model_distance_inches=_maximum_model_distance_inches_from_witness(witness),
            maximum_model_horizontal_distance_inches=(
                _maximum_model_horizontal_distance_inches_from_witness(witness)
            ),
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


def _maximum_model_horizontal_distance_inches_from_witness(
    witness: PathWitness | None,
) -> float:
    if witness is None:
        return 0.0
    maximum_distance = 0.0
    for _model_id, poses in witness.model_paths:
        model_distance = 0.0
        for index in range(1, len(poses)):
            model_distance += poses[index - 1].distance_2d_to(poses[index])
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
    active_unit_on_battlefield = reconcile_rules_unit_identity(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
    ).placed_surviving_unit_instance_ids == (active_selection.unit_instance_id,)
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
