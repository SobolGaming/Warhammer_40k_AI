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
from warhammer40k_core.engine.phases.movement_fall_back_embark import *
from warhammer40k_core.engine.phases.movement_options_dice import *
from warhammer40k_core.engine.phases.movement_resolvers import *
from warhammer40k_core.engine.phases.movement_geometry import *

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
    from warhammer40k_core.engine.phases.movement_fall_back_embark import _apply_desperate_escape_model_selection_decision, _apply_fall_back_result, _request_embark_after_move_or_complete_activation, _complete_activation_then_request_post_normal_disembark_if_available, _post_move_embark_options, _apply_embark_transport_selection_decision, _apply_valid_embark, _complete_movement_activation, _complete_movement_activation_with_record_ids, _maximum_model_distance_inches_from_witness, _interrupt_started_mission_actions_for_movement_activation
    from warhammer40k_core.engine.phases.movement_options_dice import _mission_action_state_is_active_for_unit, _movement_action_options, _advance_roll_request_for_action, _roll_advance_dice, _record_advance_roll_resolved_event, _advance_roll_reroll_request, _dice_roll_manager_for_state, _advance_reroll_permission_for_unit, _roll_desperate_escape_dice, _desperate_escape_model_selection_request, _desperate_escape_model_selection_options
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
# fmt: on

__all__ = (
    "_active_movement_selection",
    "_active_player_id",
    "_battlefield_scenario",
    "_decision_payload_object",
    "_default_move_end_pose",
    "_effective_movement_keywords",
    "_ensure_movement_phase_state",
    "_ensure_transport_cargo_phase_states",
    "_fall_back_mode_from_payload",
    "_fall_back_mode_from_proposal_submission",
    "_fall_back_mode_violation_code",
    "_fall_back_modes_for_parameterized_option",
    "_fall_back_result_with_mode",
    "_identifier_list_from_json_object",
    "_mission_setup_for_live_reinforcements",
    "_model_base_movement_inches",
    "_model_default_movement_distance_inches",
    "_model_movement_budget_inches",
    "_model_movement_inches",
    "_modified_movement_inches",
    "_movement_action_invalid_payload",
    "_movement_action_label",
    "_movement_action_option_id",
    "_movement_bonus_inches_for_unit",
    "_movement_completion_context_payload",
    "_movement_distance_modifier_inches",
    "_movement_mode_for_action",
    "_movement_mode_from_payload",
    "_movement_mode_from_proposal_submission",
    "_movement_modes_for_action_options",
    "_movement_unit_options",
    "_normal_move_invalid_message",
    "_objective_markers_for_state",
    "_optional_payload_path_witness",
    "_payload_json_array",
    "_payload_json_object",
    "_payload_model_displacement_kind",
    "_payload_object",
    "_payload_positive_int",
    "_payload_string",
    "_payload_transition_batch",
    "_remaining_move_units_unit_ids",
    "_request_payload_for_result",
    "_ruleset_descriptor_for_handler",
    "_runtime_modifier_registry",
    "_temporary_movement_keywords_for_unit",
    "_transport_operation_invalid_payload",
    "_transport_status_for_movement_action",
    "_unit_can_take_to_the_skies",
    "_unit_has_keyword",
    "_unit_instance_by_id",
    "_validate_advance_roll_spec",
    "_validate_bool",
    "_validate_desperate_escape_reason_tuple",
    "_validate_desperate_escape_requirement_tuple",
    "_validate_desperate_escape_roll_tuple",
    "_validate_identifier",
    "_validate_identifier_tuple",
    "_validate_json_object",
    "_validate_movement_action_tuple",
    "_validate_movement_distance_records",
    "_validate_movement_phase_state",
    "_validate_non_negative_finite_number",
    "_validate_objective_marker_tuple",
    "_validate_path_validation_result_tuple",
    "_validate_positive_int",
    "_validate_terrain_path_legality_result_tuple",
    "_validate_transport_restriction_override_tuple",
    "assert_move_units_step_complete_for_reinforcements",
    "desperate_escape_requirement_reason_from_token",
    "fall_back_mode_kind_from_token",
    "movement_mode_for_phase_action",
    "movement_phase_action_kind_from_token",
    "movement_phase_step_kind_from_token",
)


def _movement_action_invalid_payload(
    *,
    state: GameState,
    active_player_id: str,
    unit_instance_id: str,
    action: MovementPhaseActionKind,
    result: DecisionResult,
    violation_code: str,
    movement_payload: dict[str, JsonValue],
    rollback_record: MovementRollbackRecord | None,
) -> dict[str, JsonValue]:
    invalid_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": active_player_id,
        "phase": BattlePhase.MOVEMENT.value,
        "unit_instance_id": unit_instance_id,
        "movement_phase_action": action.value,
        "request_id": result.request_id,
        "result_id": result.result_id,
        "phase_body_status": "movement_action_invalid",
        "violation_code": violation_code,
        **movement_payload,
    }
    if rollback_record is not None:
        invalid_payload["rollback_record"] = validate_json_value(rollback_record.to_payload())
    return invalid_payload


def assert_move_units_step_complete_for_reinforcements(
    *,
    state: GameState,
    movement_state: MovementPhaseState,
    message: str = "Move Units step must be complete before reserve arrivals.",
) -> None:
    if type(movement_state) is not MovementPhaseState:
        raise GameLifecycleError("Move Units completion check requires MovementPhaseState.")
    if movement_state.step is not MovementPhaseStepKind.MOVE_UNITS:
        raise GameLifecycleError("Move Units completion check requires Move Units step.")
    if movement_state.active_selection is not None:
        raise GameLifecycleError(message)
    incomplete_selected_unit_ids = tuple(
        unit_id
        for unit_id in movement_state.selected_unit_ids
        if unit_id not in movement_state.moved_unit_ids
    )
    if incomplete_selected_unit_ids:
        raise GameLifecycleError(message)
    remaining_unit_ids = _remaining_move_units_unit_ids(
        scenario=_battlefield_scenario(state),
        active_player_id=movement_state.active_player_id,
        selected_unit_ids=movement_state.selected_unit_ids,
        accounted_unplaced_model_ids=state.unavailable_model_ids(),
    )
    if remaining_unit_ids:
        raise GameLifecycleError(message)


def _remaining_move_units_unit_ids(
    *,
    scenario: BattlefieldScenario,
    active_player_id: str,
    selected_unit_ids: tuple[str, ...],
    accounted_unplaced_model_ids: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("MovementPhaseState scenario must be a BattlefieldScenario.")
    player_id = _validate_identifier("active_player_id", active_player_id)
    selected = set(_validate_identifier_tuple("selected_unit_ids", selected_unit_ids))
    accounted_ids = _validate_identifier_tuple(
        "accounted_unplaced_model_ids",
        accounted_unplaced_model_ids,
    )
    try:
        scenario.assert_all_mustered_models_placed_or_accounted(accounted_ids)
    except PlacementError as exc:
        raise GameLifecycleError("Movement phase requires complete placed armies.") from exc
    placed_army = scenario.battlefield_state.placed_army_for_player_or_none(player_id)
    if placed_army is None:
        return ()
    return tuple(
        placement.unit_instance_id
        for placement in placed_army.unit_placements
        if placement.unit_instance_id not in selected
    )


def _normal_move_invalid_message(violation_code: str) -> str:
    code = _validate_identifier("Normal Move violation_code", violation_code)
    if code == "unit_coherency_broken":
        return "Normal Move endpoint violates unit coherency."
    if code == "objective_marker_endpoint_overlap":
        return "Normal Move endpoint overlaps an objective marker."
    if code.startswith("terrain") or code in {
        "end_on_forbidden_terrain",
        "upper_floor_keyword_forbidden",
        "base_overhangs_support_surface",
        "model_cannot_be_placed_at_endpoint",
        "ends_mid_climb",
        "manual_geometry_required",
    }:
        return "Normal Move terrain path is invalid."
    return "Normal Move path is invalid."


def _ensure_movement_phase_state(
    *,
    state: GameState,
    decisions: DecisionController,
) -> MovementPhaseState:
    active_player_id = _active_player_id(state)
    current = state.movement_phase_state
    if (
        current is not None
        and current.battle_round == state.battle_round
        and current.active_player_id == active_player_id
    ):
        return current

    movement_state = MovementPhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    state.replace_movement_phase_state(movement_state)
    decisions.event_log.append(
        "movement_phase_entered",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
        },
    )
    return movement_state


def _validate_movement_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("MovementPhaseHandler can run only during battle.")
    if state.current_battle_phase is not BattlePhase.MOVEMENT:
        raise GameLifecycleError("MovementPhaseHandler can run only in the MOVEMENT phase.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Movement phase requires placed battlefield state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )


def _movement_unit_options(
    *,
    scenario: BattlefieldScenario,
    unit_ids: tuple[str, ...],
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        unit_placement = scenario.battlefield_state.unit_placement_by_id(unit_id)
        unit = scenario.unit_instance_for_placement(unit_placement)
        options.append(
            DecisionOption(
                option_id=unit.unit_instance_id,
                label=unit.name,
                payload={
                    "unit_instance_id": unit.unit_instance_id,
                    "model_instance_ids": [
                        placement.model_instance_id for placement in unit_placement.model_placements
                    ],
                },
            )
        )
    return tuple(options)


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Battle state requires an active player.")
    return state.active_player_id


def movement_phase_action_kind_from_token(token: object) -> MovementPhaseActionKind:
    if type(token) is MovementPhaseActionKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("MovementPhaseActionKind token must be a string.")
    try:
        return MovementPhaseActionKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported MovementPhaseActionKind token: {token}.") from exc


def fall_back_mode_kind_from_token(token: object) -> FallBackModeKind:
    if type(token) is FallBackModeKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("FallBackModeKind token must be a string.")
    try:
        return FallBackModeKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported FallBackModeKind token: {token}.") from exc


def movement_phase_step_kind_from_token(token: object) -> MovementPhaseStepKind:
    if type(token) is MovementPhaseStepKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("MovementPhaseStepKind token must be a string.")
    try:
        return MovementPhaseStepKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported MovementPhaseStepKind token: {token}.") from exc


def desperate_escape_requirement_reason_from_token(
    token: object,
) -> DesperateEscapeRequirementReason:
    if type(token) is DesperateEscapeRequirementReason:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DesperateEscapeRequirementReason token must be a string.")
    try:
        return DesperateEscapeRequirementReason(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported DesperateEscapeRequirementReason token: {token}."
        ) from exc


def movement_mode_for_phase_action(action: object) -> MovementMode | None:
    action_kind = movement_phase_action_kind_from_token(action)
    if action_kind is MovementPhaseActionKind.REMAIN_STATIONARY:
        return None
    if action_kind is MovementPhaseActionKind.NORMAL_MOVE:
        return MovementMode.NORMAL
    if action_kind is MovementPhaseActionKind.ADVANCE:
        return MovementMode.ADVANCE
    if action_kind is MovementPhaseActionKind.FALL_BACK:
        return MovementMode.FALL_BACK
    raise GameLifecycleError(f"Unsupported MovementPhaseActionKind token: {action_kind.value}.")


def _movement_mode_from_payload(
    *,
    payload: dict[str, JsonValue],
    action: MovementPhaseActionKind,
) -> MovementMode:
    movement_mode = movement_mode_from_token(_payload_string(payload, key="movement_mode"))
    return _movement_mode_for_action(action=action, movement_mode=movement_mode)


def _movement_mode_from_proposal_submission(
    *,
    submission: MovementProposalPayload,
    action: MovementPhaseActionKind,
) -> MovementMode:
    if submission.movement_mode is None:
        raise GameLifecycleError("Movement proposal requires movement_mode.")
    movement_mode = movement_mode_from_token(submission.movement_mode)
    return _movement_mode_for_action(action=action, movement_mode=movement_mode)


def _fall_back_mode_from_payload(payload: dict[str, JsonValue]) -> FallBackModeKind:
    return fall_back_mode_kind_from_token(_payload_string(payload, key="fall_back_mode"))


def _fall_back_mode_from_proposal_submission(
    *,
    submission: MovementProposalPayload,
) -> FallBackModeKind:
    if submission.fall_back_mode is None:
        raise GameLifecycleError("Fall Back movement proposal requires fall_back_mode.")
    return fall_back_mode_kind_from_token(submission.fall_back_mode)


def _movement_action_option_id(
    *,
    action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    fall_back_mode: FallBackModeKind | None = None,
) -> str:
    default_mode = movement_mode_for_phase_action(action)
    if action is MovementPhaseActionKind.FALL_BACK:
        if fall_back_mode is None:
            raise GameLifecycleError("Fall Back option IDs require fall_back_mode.")
        parts = [action.value, fall_back_mode.value]
        if movement_mode is not default_mode:
            parts.append(movement_mode.value)
        return ":".join(parts)
    if movement_mode is default_mode:
        return action.value
    return f"{action.value}:{movement_mode.value}"


def _movement_action_label(
    *,
    action: MovementPhaseActionKind,
    movement_mode: MovementMode,
    fall_back_mode: FallBackModeKind | None = None,
) -> str:
    action_label = action.value.replace("_", " ").title()
    labels: list[str] = [action_label]
    if fall_back_mode is not None:
        labels.append(fall_back_mode.value.replace("_", " ").title())
    if movement_mode is MovementMode.FLY_TAKE_TO_SKIES:
        labels.append("Take To Skies")
    return " - ".join(labels)


def _movement_modes_for_action_options(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...],
    action: MovementPhaseActionKind,
) -> tuple[MovementMode, ...]:
    default_mode = movement_mode_for_phase_action(action)
    if default_mode is None:
        return ()
    modes = [default_mode]
    if _unit_can_take_to_the_skies(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=hover_mode_states,
    ):
        modes.append(MovementMode.FLY_TAKE_TO_SKIES)
    return tuple(modes)


def _unit_can_take_to_the_skies(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...],
) -> bool:
    if not ruleset_descriptor.fly_policy.take_to_the_skies_supported:
        return False
    unit = scenario.unit_instance_for_placement(unit_placement)
    hover_mode_state = _hover_mode_state_for_unit(
        hover_mode_states=hover_mode_states,
        unit_instance_id=unit_placement.unit_instance_id,
    )
    aircraft_policy = AircraftMovementPolicy.from_unit(
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=hover_mode_state,
    )
    return "FLY" in aircraft_policy.effective_keywords and not aircraft_policy.hover_mode_active


def _fall_back_modes_for_parameterized_option(
    *,
    unit_instance_id: str,
    battle_shocked_unit_ids: tuple[str, ...],
) -> tuple[FallBackModeKind, ...]:
    if unit_instance_id in set(battle_shocked_unit_ids):
        return (FallBackModeKind.DESPERATE_ESCAPE,)
    return (FallBackModeKind.ORDERED_RETREAT, FallBackModeKind.DESPERATE_ESCAPE)


def _fall_back_result_with_mode(
    *,
    resolution: FallBackActionResult,
    fall_back_mode: FallBackModeKind,
) -> FallBackActionResult:
    if type(resolution) is not FallBackActionResult:
        raise GameLifecycleError("Fall Back mode payload requires FallBackActionResult.")
    if type(fall_back_mode) is not FallBackModeKind:
        raise GameLifecycleError("Fall Back mode payload requires FallBackModeKind.")
    return replace(
        resolution,
        movement_payload={
            **resolution.movement_payload,
            "fall_back_mode": fall_back_mode.value,
        },
    )


def _fall_back_mode_violation_code(
    *,
    resolution: FallBackActionResult,
    fall_back_mode: FallBackModeKind,
) -> str | None:
    if fall_back_mode is FallBackModeKind.ORDERED_RETREAT:
        if resolution.desperate_escape_requirements:
            return "ordered_retreat_requires_desperate_escape"
        return None
    if fall_back_mode is FallBackModeKind.DESPERATE_ESCAPE:
        if not resolution.desperate_escape_requirements:
            return "desperate_escape_has_no_requirements"
        return None
    raise GameLifecycleError("Unsupported Fall Back mode.")


def _model_movement_inches(model: ModelInstance) -> int:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Movement model must be a ModelInstance.")
    for characteristic in model.characteristics:
        if characteristic.characteristic is Characteristic.MOVEMENT:
            return characteristic.final
    raise GameLifecycleError("Normal Move requires a Movement characteristic.")


def _model_base_movement_inches(
    *,
    model: ModelInstance,
    aircraft_policy: AircraftMovementPolicy,
    state: GameState | None = None,
    unit_instance_id: str | None = None,
    model_instance_id: str | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> float:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Movement model must be a ModelInstance.")
    if type(aircraft_policy) is not AircraftMovementPolicy:
        raise GameLifecycleError("Movement budget requires an AircraftMovementPolicy.")
    if aircraft_policy.hover_mode_active:
        base_movement = 20.0
    else:
        base_movement = float(_model_movement_inches(model))
    return _modified_movement_inches(
        state=state,
        unit_instance_id=unit_instance_id,
        model_instance_id=model_instance_id,
        base_movement_inches=base_movement,
        current_movement_inches=base_movement,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def _model_movement_budget_inches(
    *,
    model: ModelInstance,
    aircraft_policy: AircraftMovementPolicy,
    ruleset_descriptor: RulesetDescriptor,
    movement_bonus_inches: int,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind,
    state: GameState | None = None,
    unit_instance_id: str | None = None,
    model_instance_id: str | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> float | None:
    if type(movement_phase_action) is not MovementPhaseActionKind:
        raise GameLifecycleError("movement_phase_action must be a MovementPhaseActionKind.")
    movement_budget = (
        _model_base_movement_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            state=state,
            unit_instance_id=unit_instance_id,
            model_instance_id=model_instance_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        + float(movement_bonus_inches)
        + _movement_distance_modifier_inches(
            aircraft_policy=aircraft_policy,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
        )
    )
    if movement_budget < 0.0:
        raise GameLifecycleError("Movement distance modifier cannot reduce budget below 0.")
    return movement_budget


def _movement_distance_modifier_inches(
    *,
    aircraft_policy: AircraftMovementPolicy,
    ruleset_descriptor: RulesetDescriptor,
    movement_mode: MovementMode,
) -> float:
    if type(aircraft_policy) is not AircraftMovementPolicy:
        raise GameLifecycleError("Movement distance modifier requires AircraftMovementPolicy.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Movement distance modifier requires RulesetDescriptor.")
    if type(movement_mode) is not MovementMode:
        raise GameLifecycleError("Movement distance modifier requires MovementMode.")
    try:
        movement_mode_policy = ruleset_descriptor.movement_policy.policy_for_mode(movement_mode)
    except RulesetDescriptorError as exc:
        raise GameLifecycleError("Movement mode is not defined by the RulesetDescriptor.") from exc
    if movement_mode is not MovementMode.FLY_TAKE_TO_SKIES:
        return movement_mode_policy.movement_distance_modifier
    if not ruleset_descriptor.fly_policy.take_to_the_skies_supported:
        raise GameLifecycleError("RulesetDescriptor does not support Take to the Skies.")
    if "FLY" not in aircraft_policy.effective_keywords:
        raise GameLifecycleError("Take to the Skies requires the FLY keyword.")
    if "HOVER" in aircraft_policy.effective_keywords:
        return 0.0
    return movement_mode_policy.movement_distance_modifier


def _movement_mode_for_action(
    *,
    action: MovementPhaseActionKind,
    movement_mode: MovementMode,
) -> MovementMode:
    if type(action) is not MovementPhaseActionKind:
        raise GameLifecycleError("Movement mode selection requires MovementPhaseActionKind.")
    if type(movement_mode) is not MovementMode:
        raise GameLifecycleError("Movement mode selection requires MovementMode.")
    if action is MovementPhaseActionKind.NORMAL_MOVE:
        allowed_modes = (MovementMode.NORMAL, MovementMode.FLY_TAKE_TO_SKIES)
    elif action is MovementPhaseActionKind.ADVANCE:
        allowed_modes = (MovementMode.ADVANCE, MovementMode.FLY_TAKE_TO_SKIES)
    elif action is MovementPhaseActionKind.FALL_BACK:
        allowed_modes = (MovementMode.FALL_BACK, MovementMode.FLY_TAKE_TO_SKIES)
    else:
        raise GameLifecycleError("Movement mode selection received a non-move action.")
    if movement_mode not in allowed_modes:
        raise GameLifecycleError("Movement mode is not legal for the selected movement action.")
    return movement_mode


def _temporary_movement_keywords_for_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> tuple[str, ...]:
    return movement_keywords_granted_by_effects(
        state.persisting_effects_for_unit(unit_instance_id),
        owner_player_id=player_id,
    )


def _movement_bonus_inches_for_unit(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> int:
    return movement_bonus_inches_from_effects(
        state.persisting_effects_for_unit(unit_instance_id),
        owner_player_id=player_id,
    )


def _effective_movement_keywords(
    base_keywords: tuple[str, ...],
    *,
    temporary_keywords: tuple[str, ...],
) -> tuple[str, ...]:
    validated_base = _validate_identifier_tuple("base movement keywords", base_keywords)
    validated_temporary = _validate_identifier_tuple(
        "temporary movement keywords",
        temporary_keywords,
    )
    return tuple(sorted({*validated_base, *validated_temporary}))


def _model_default_movement_distance_inches(
    *,
    model: ModelInstance,
    aircraft_policy: AircraftMovementPolicy,
    ruleset_descriptor: RulesetDescriptor,
    movement_bonus_inches: int,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind,
    state: GameState | None = None,
    unit_instance_id: str | None = None,
    model_instance_id: str | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> float:
    movement_budget = _model_movement_budget_inches(
        model=model,
        aircraft_policy=aircraft_policy,
        ruleset_descriptor=ruleset_descriptor,
        state=state,
        unit_instance_id=unit_instance_id,
        model_instance_id=model_instance_id,
        movement_bonus_inches=movement_bonus_inches,
        movement_mode=movement_mode,
        movement_phase_action=movement_phase_action,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if movement_budget is None:
        raise GameLifecycleError("Default movement distance requires a finite movement budget.")
    return movement_budget


def _modified_movement_inches(
    *,
    state: GameState | None,
    unit_instance_id: str | None,
    model_instance_id: str | None,
    base_movement_inches: float,
    current_movement_inches: float,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> float:
    if state is None:
        return current_movement_inches
    if unit_instance_id is None:
        raise GameLifecycleError("Movement modifier requires unit_instance_id.")
    if model_instance_id is None:
        raise GameLifecycleError("Movement modifier requires model_instance_id.")
    return _runtime_modifier_registry(runtime_modifier_registry).modified_movement_inches(
        MovementBudgetModifierContext(
            state=state,
            unit_instance_id=unit_instance_id,
            model_instance_id=model_instance_id,
            base_movement_inches=base_movement_inches,
            current_movement_inches=current_movement_inches,
        )
    )


def _runtime_modifier_registry(
    registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if registry is None:
        return RuntimeModifierRegistry.empty()
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Runtime modifier registry must be a RuntimeModifierRegistry.")
    return registry


def _default_move_end_pose(
    *,
    start_pose: Pose,
    aircraft_policy: AircraftMovementPolicy,
    movement_inches: float,
) -> Pose:
    return Pose.at(
        x=start_pose.position.x + movement_inches,
        y=start_pose.position.y,
        z=start_pose.position.z,
        facing_degrees=start_pose.facing.degrees,
    )


def _ruleset_descriptor_for_handler(handler: MovementPhaseHandler) -> RulesetDescriptor:
    if type(handler) is not MovementPhaseHandler:
        raise GameLifecycleError("Movement ruleset descriptor requires a MovementPhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Movement phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _mission_setup_for_live_reinforcements(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
) -> MissionSetup:
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Live Reinforcements requires a RulesetDescriptor.")
    if (
        ruleset_descriptor.mission_policy.deployment_zone_source
        is not MissionDeploymentZoneSource.MISSION
    ):
        raise GameLifecycleError(
            "Live Reinforcements requires mission-sourced deployment-zone geometry."
        )
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError(
            "Live Reinforcements requires MissionSetup with deployment zones and terrain features."
        )
    return mission_setup


def _objective_markers_for_state(state: GameState) -> tuple[ObjectiveMarker, ...]:
    from warhammer40k_core.engine.game_state import GameState as RuntimeGameState

    if type(state) is not RuntimeGameState:
        raise GameLifecycleError("Objective marker lookup requires a GameState.")
    if state.mission_setup is None:
        return ()
    return tuple(marker.to_objective_marker() for marker in state.mission_setup.objective_markers)


def _active_movement_selection(state: GameState) -> MovementUnitSelection:
    movement_state = state.movement_phase_state
    if movement_state is None or movement_state.active_selection is None:
        raise GameLifecycleError("Movement transport decision requires active_selection.")
    return movement_state.active_selection


def _ensure_transport_cargo_phase_states(state: GameState) -> None:
    for cargo_state in tuple(state.transport_cargo_states):
        active_cargo_state = cargo_state.for_movement_phase(battle_round=state.battle_round)
        if active_cargo_state != cargo_state:
            state.replace_transport_cargo_state(active_cargo_state)


def _unit_instance_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("Unknown unit_instance_id.")


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(_canonical_keyword(stored) == canonical for stored in unit.keywords)


def _transport_status_for_movement_action(
    action: MovementPhaseActionKind,
) -> TransportMovementStatus:
    action_kind = movement_phase_action_kind_from_token(action)
    if action_kind is MovementPhaseActionKind.NORMAL_MOVE:
        return TransportMovementStatus.NORMAL_MOVE
    if action_kind is MovementPhaseActionKind.ADVANCE:
        return TransportMovementStatus.ADVANCE
    if action_kind is MovementPhaseActionKind.FALL_BACK:
        return TransportMovementStatus.FALL_BACK
    if action_kind is MovementPhaseActionKind.REMAIN_STATIONARY:
        return TransportMovementStatus.REMAIN_STATIONARY
    raise GameLifecycleError(f"Unsupported transport movement status action: {action_kind.value}.")


def _movement_completion_context_payload(
    *,
    result: DecisionResult,
    action: MovementPhaseActionKind,
    witness: PathWitness | None,
    movement_payload: dict[str, JsonValue],
    displacement_kind: ModelDisplacementKind,
    transition_batch: BattlefieldTransitionBatch,
) -> dict[str, JsonValue]:
    return {
        "action_request_id": result.request_id,
        "action_result_id": result.result_id,
        "movement_phase_action": action.value,
        "witness": None if witness is None else validate_json_value(witness.to_payload()),
        "movement_payload": validate_json_value(movement_payload),
        "displacement_kind": displacement_kind.value,
        "transition_batch": validate_json_value(transition_batch.to_payload()),
    }


def _transport_operation_invalid_payload(
    *,
    state: GameState,
    active_player_id: str,
    unit_instance_id: str,
    transport_unit_instance_id: str,
    result: DecisionResult,
    phase_body_status: str,
    violations: tuple[TransportOperationViolation, ...],
) -> dict[str, JsonValue]:
    return _validate_json_object(
        "transport invalid payload",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": unit_instance_id,
            "transport_unit_instance_id": transport_unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": phase_body_status,
            "violations": [violation.to_payload() for violation in violations],
        },
    )


def _request_payload_for_result(
    *,
    decisions: DecisionController,
    result: DecisionResult,
) -> dict[str, JsonValue]:
    for request in decisions.queue.pending_requests:
        if request.request_id == result.request_id:
            return _decision_payload_object(request.payload)
    for record in reversed(decisions.records):
        if record.result == result:
            return _decision_payload_object(record.request.payload)
    raise GameLifecycleError("DecisionResult does not match a known Movement request.")


def _decision_payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return payload


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Decision payload key must be a string: {key}.")
    return value


def _payload_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be an object: {key}.")
    return value


def _payload_json_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    return _payload_object(payload, key=key)


def _identifier_list_from_json_object(
    payload: dict[str, JsonValue],
    *,
    key: str,
    field_name: str,
) -> tuple[str, ...]:
    value = payload.get(key)
    if value is None:
        return ()
    if not isinstance(value, list):
        raise GameLifecycleError(f"Payload key must be a list: {key}.")
    return tuple(sorted(_validate_identifier(field_name, item) for item in value))


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Decision payload key must be an integer: {key}.")
    return _validate_positive_int(key, value)


def _optional_payload_path_witness(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> PathWitness | None:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if value is None:
        return None
    if not isinstance(value, dict):
        raise GameLifecycleError(f"Decision payload key must be a PathWitness payload: {key}.")
    return PathWitness.from_payload(cast(PathWitnessPayload, value))


def _payload_model_displacement_kind(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> ModelDisplacementKind:
    return model_displacement_kind_from_token(_payload_string(payload, key=key))


def _payload_transition_batch(
    payload: dict[str, JsonValue],
    *,
    key: str,
) -> BattlefieldTransitionBatch:
    value = _payload_object(payload, key=key)
    return BattlefieldTransitionBatch.from_payload(cast(BattlefieldTransitionBatchPayload, value))


def _payload_json_array(payload: dict[str, JsonValue], *, key: str) -> list[JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Decision payload missing required key: {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Decision payload key must be an array: {key}.")
    return value


def _validate_json_object(field_name: str, value: object) -> dict[str, JsonValue]:
    json_value = validate_json_value(value)
    if not isinstance(json_value, dict):
        raise GameLifecycleError(f"{field_name} must be a JSON object.")
    return json_value


def _validate_movement_action_tuple(
    field_name: str,
    values: object,
) -> tuple[MovementPhaseActionKind, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    actions = tuple(
        movement_phase_action_kind_from_token(value) for value in cast(tuple[object, ...], values)
    )
    seen: set[MovementPhaseActionKind] = set()
    for action in actions:
        if action in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(action)
    return actions


def _validate_transport_restriction_override_tuple(
    field_name: str,
    values: object,
) -> tuple[TransportRestrictionOverride, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    overrides: list[TransportRestrictionOverride] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TransportRestrictionOverride:
            raise GameLifecycleError(
                f"{field_name} must contain TransportRestrictionOverride values."
            )
        overrides.append(value)
    return tuple(sorted(overrides, key=lambda override: override.override_kind.value))


def _validate_path_validation_result_tuple(
    field_name: str,
    values: object,
) -> tuple[PathValidationResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    results: list[PathValidationResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not PathValidationResult:
            raise GameLifecycleError(f"{field_name} must contain PathValidationResult values.")
        results.append(value)
    if not results:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(results)


def _validate_terrain_path_legality_result_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainPathLegalityResult, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    results: list[TerrainPathLegalityResult] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainPathLegalityResult:
            raise GameLifecycleError(f"{field_name} must contain TerrainPathLegalityResult values.")
        results.append(value)
    if not results:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(results)


def _validate_desperate_escape_reason_tuple(
    field_name: str,
    values: object,
) -> tuple[DesperateEscapeRequirementReason, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    reasons = tuple(
        desperate_escape_requirement_reason_from_token(value)
        for value in cast(tuple[object, ...], values)
    )
    if not reasons:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    seen: set[DesperateEscapeRequirementReason] = set()
    for reason in reasons:
        if reason in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(reason)
    return tuple(sorted(reasons, key=lambda reason: reason.value))


def _validate_desperate_escape_requirement_tuple(
    field_name: str,
    values: object,
) -> tuple[DesperateEscapeRequirement, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    requirements: list[DesperateEscapeRequirement] = []
    seen_requirement_ids: set[str] = set()
    seen_model_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DesperateEscapeRequirement:
            raise GameLifecycleError(
                f"{field_name} must contain DesperateEscapeRequirement values."
            )
        if value.requirement_id in seen_requirement_ids:
            raise GameLifecycleError(f"{field_name} must not contain duplicate requirement IDs.")
        if value.model_instance_id in seen_model_ids:
            raise GameLifecycleError(f"{field_name} must not test the same model twice.")
        seen_requirement_ids.add(value.requirement_id)
        seen_model_ids.add(value.model_instance_id)
        requirements.append(value)
    return tuple(sorted(requirements, key=lambda requirement: requirement.requirement_id))


def _validate_desperate_escape_roll_tuple(
    field_name: str,
    values: object,
) -> tuple[DesperateEscapeRoll, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    rolls: list[DesperateEscapeRoll] = []
    seen_requirement_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DesperateEscapeRoll:
            raise GameLifecycleError(f"{field_name} must contain DesperateEscapeRoll values.")
        requirement_id = value.requirement.requirement_id
        if requirement_id in seen_requirement_ids:
            raise GameLifecycleError(f"{field_name} must not contain duplicate requirements.")
        seen_requirement_ids.add(requirement_id)
        rolls.append(value)
    return tuple(sorted(rolls, key=lambda roll: roll.requirement.requirement_id))


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_movement_distance_records(
    field_name: str,
    values: object,
) -> tuple[MovementDistanceRecord, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    records: list[MovementDistanceRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not MovementDistanceRecord:
            raise GameLifecycleError(f"{field_name} must contain MovementDistanceRecord values.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate unit IDs.")
        seen.add(value.unit_instance_id)
        records.append(value)
    return tuple(sorted(records, key=lambda record: record.unit_instance_id))


def _validate_objective_marker_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveMarker, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    markers: list[ObjectiveMarker] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarker:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveMarker values.")
        if value.objective_marker_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate markers.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def _validate_advance_roll_spec(spec: DiceRollSpec, *, unit_instance_id: str) -> None:
    if type(spec) is not DiceRollSpec:
        raise GameLifecycleError("Advance roll spec must be a DiceRollSpec.")
    if spec.expression != DiceExpression(quantity=1, sides=6):
        raise GameLifecycleError("Advance roll spec must be an unmodified D6.")
    if spec.roll_type != "advance_roll":
        raise GameLifecycleError("Advance roll spec roll_type must be advance_roll.")
    if spec.actor_id != unit_instance_id:
        raise GameLifecycleError("Advance roll spec actor_id must match unit_instance_id.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return number


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
