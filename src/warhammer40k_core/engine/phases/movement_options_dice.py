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
from warhammer40k_core.engine.battle_shock import (
    BattleShockTestReason,
    BattleShockTestRequest,
    battle_shock_leadership_target_for_unit,
)
from warhammer40k_core.engine.battle_shock_hooks import (
    BattleShockDiceExpressionContext,
    BattleShockHookRegistry,
)
from warhammer40k_core.engine.battle_shock_resolution import (
    resolve_battle_shock_test_with_optional_reroll,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.engine.unit_state import BelowHalfStrengthContext

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
    from warhammer40k_core.engine.phases.movement_resolvers import resolve_normal_move, resolve_advance_move, resolve_fall_back_move, _resolve_unit_move, _default_move_witness, _default_fall_back_witness, _movement_transition_batch, _fall_back_transition_batch, _normal_move_transition_batch, _movement_action_availability_result
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND",
    "FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID",
    "_advance_reroll_permission_for_unit",
    "_advance_roll_request_for_action",
    "_advance_roll_reroll_request",
    "_desperate_escape_model_selection_options",
    "_desperate_escape_model_selection_request",
    "_dice_roll_manager_for_state",
    "_mission_action_state_is_active_for_unit",
    "_movement_action_options",
    "_record_advance_roll_resolved_event",
    "_resolve_forced_desperate_escape_battle_shock",
    "_roll_advance_dice",
    "_roll_desperate_escape_dice",
)

FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND = "forced_desperate_escape_battle_shock"
FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID = (
    "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:09.07.01-forced-desperate-escape"
)


def _mission_action_state_is_active_for_unit(
    *,
    action_state: MissionActionState,
    unit_instance_id: str,
) -> bool:
    if type(action_state) is not MissionActionState:
        raise GameLifecycleError("Mission Action interruption requires MissionActionState.")
    return (
        action_state.status is MissionActionStatus.STARTED
        and action_state.unit_instance_id == unit_instance_id
    )


def _movement_action_options(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    battle_round: int = 1,
    hover_mode_states: tuple[HoverModeState, ...] = (),
    battle_shocked_unit_ids: tuple[str, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    disembarked_unit_state: DisembarkedUnitState | None = None,
) -> tuple[DecisionOption, ...]:
    if disembarked_unit_state is not None and type(disembarked_unit_state) is not (
        DisembarkedUnitState
    ):
        raise GameLifecycleError(
            "Movement action options disembarked_unit_state must be DisembarkedUnitState."
        )
    availability_result = _movement_action_availability_result(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=hover_mode_states,
    )
    options: list[DecisionOption] = []
    for action in availability_result.available_actions:
        if disembarked_unit_state is not None:
            if (
                action is MovementPhaseActionKind.REMAIN_STATIONARY
                and not disembarked_unit_state.can_choose_remain_stationary
            ):
                continue
            if (
                action is not MovementPhaseActionKind.REMAIN_STATIONARY
                and not disembarked_unit_state.can_move_further
            ):
                continue
        if action is MovementPhaseActionKind.REMAIN_STATIONARY:
            options.append(
                DecisionOption(
                    option_id=MovementPhaseActionKind.REMAIN_STATIONARY.value,
                    label="Remain Stationary",
                    payload={
                        "movement_phase_action": MovementPhaseActionKind.REMAIN_STATIONARY.value,
                        "unit_instance_id": unit_placement.unit_instance_id,
                        "movement_inches": 0,
                        "model_movements": [],
                        "witness": None,
                    },
                )
            )
            continue
        if action is MovementPhaseActionKind.NORMAL_MOVE:
            movement_modes = _movement_modes_for_action_options(
                scenario=scenario,
                unit_placement=unit_placement,
                ruleset_descriptor=ruleset_descriptor,
                hover_mode_states=hover_mode_states,
                action=action,
            )
            for movement_mode in movement_modes:
                option_id = _movement_action_option_id(
                    action=action,
                    movement_mode=movement_mode,
                )
                options.append(
                    DecisionOption(
                        option_id=option_id,
                        label=_movement_action_label(
                            action=action,
                            movement_mode=movement_mode,
                        ),
                        payload={
                            "movement_phase_action": MovementPhaseActionKind.NORMAL_MOVE.value,
                            "unit_instance_id": unit_placement.unit_instance_id,
                            "movement_mode": movement_mode.value,
                        },
                    )
                )
            continue
        if action is MovementPhaseActionKind.ADVANCE:
            movement_modes = _movement_modes_for_action_options(
                scenario=scenario,
                unit_placement=unit_placement,
                ruleset_descriptor=ruleset_descriptor,
                hover_mode_states=hover_mode_states,
                action=action,
            )
            for movement_mode in movement_modes:
                options.append(
                    DecisionOption(
                        option_id=_movement_action_option_id(
                            action=action,
                            movement_mode=movement_mode,
                        ),
                        label=_movement_action_label(
                            action=action,
                            movement_mode=movement_mode,
                        ),
                        payload={
                            "movement_phase_action": action.value,
                            "unit_instance_id": unit_placement.unit_instance_id,
                            "movement_mode": movement_mode.value,
                        },
                    )
                )
            continue
        if action is MovementPhaseActionKind.FALL_BACK:
            movement_modes = _movement_modes_for_action_options(
                scenario=scenario,
                unit_placement=unit_placement,
                ruleset_descriptor=ruleset_descriptor,
                hover_mode_states=hover_mode_states,
                action=action,
            )
            for movement_mode in movement_modes:
                for fall_back_mode in _fall_back_modes_for_parameterized_option(
                    unit_instance_id=unit_placement.unit_instance_id,
                    battle_shocked_unit_ids=battle_shocked_unit_ids,
                ):
                    options.append(
                        DecisionOption(
                            option_id=_movement_action_option_id(
                                action=action,
                                movement_mode=movement_mode,
                                fall_back_mode=fall_back_mode,
                            ),
                            label=_movement_action_label(
                                action=action,
                                movement_mode=movement_mode,
                                fall_back_mode=fall_back_mode,
                            ),
                            payload={
                                "movement_phase_action": MovementPhaseActionKind.FALL_BACK.value,
                                "unit_instance_id": unit_placement.unit_instance_id,
                                "movement_mode": movement_mode.value,
                                "fall_back_mode": fall_back_mode.value,
                            },
                        )
                    )
            continue
    return tuple(options)


def _advance_roll_request_for_action(
    *,
    state: GameState,
    unit: UnitInstance,
    unit_placement: UnitPlacement,
    action_result: DecisionResult,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> AdvanceRollRequest:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Advance roll requires a UnitInstance.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Advance roll requires a UnitPlacement.")
    roll_modifiers = runtime_modifier_registry.advance_roll_modifiers(
        AdvanceRollModifierContext(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            current_roll_modifiers=(),
        )
    )
    return AdvanceRollRequest.for_unit(
        request_id=f"{action_result.result_id}:advance-roll",
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        roll_modifiers=roll_modifiers,
        reroll_permission=_advance_reroll_permission_for_unit(
            state=state,
            unit=unit,
            unit_instance_id=unit_placement.unit_instance_id,
            player_id=unit_placement.player_id,
            keywords=unit.keywords,
            ability_index=ability_index,
            current_model_instance_ids=tuple(
                sorted(
                    model_placement.model_instance_id
                    for model_placement in unit_placement.model_placements
                )
            ),
        ),
    )


def _roll_advance_dice(
    *,
    state: GameState,
    decisions: DecisionController,
    request: AdvanceRollRequest,
) -> DiceRollState:
    decisions.event_log.append(
        "advance_roll_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": request.unit_instance_id,
            "advance_roll_request": validate_json_value(request.to_payload()),
        },
    )
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    return manager.roll(request.spec)


def _record_advance_roll_resolved_event(
    *,
    state: GameState,
    decisions: DecisionController,
    advance_roll: AdvanceRollResult,
) -> None:
    decisions.event_log.append(
        "advance_roll_resolved",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": advance_roll.request.unit_instance_id,
            "advance_roll": validate_json_value(advance_roll.to_payload()),
        },
    )


def _advance_roll_reroll_request(
    *,
    state: GameState,
    decisions: DecisionController,
    dice_roll_state: DiceRollState,
    advance_roll_request: AdvanceRollRequest,
    action_result: DecisionResult,
    movement_mode: MovementMode,
    selected_advance_move_grants: tuple[AdvanceMoveGrant, ...],
) -> DecisionRequest:
    permission = advance_roll_request.reroll_permission
    if permission is None:
        raise GameLifecycleError("Advance reroll request requires a legal reroll permission.")
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    return manager.build_reroll_request(
        dice_roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=advance_roll_request.player_id,
        permission=permission,
        extra_payload={
            "movement_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "movement_phase_action": MovementPhaseActionKind.ADVANCE.value,
                "movement_mode": movement_mode.value,
                "unit_instance_id": advance_roll_request.unit_instance_id,
                "action_request_id": action_result.request_id,
                "action_result_id": action_result.result_id,
                "action_selected_option_id": action_result.selected_option_id,
                "advance_roll_request": validate_json_value(advance_roll_request.to_payload()),
                "advance_roll_state": validate_json_value(dice_roll_state.to_payload()),
                "selected_movement_action_grant_hook_ids": [
                    grant.hook_id for grant in selected_advance_move_grants
                ],
                "selected_movement_action_grants": validate_json_value(
                    [grant.to_payload() for grant in selected_advance_move_grants]
                ),
            }
        },
    )


def _dice_roll_manager_for_state(
    *,
    state: GameState,
    decisions: DecisionController,
) -> DiceRollManager:
    return DiceRollManager(state.game_id, event_log=decisions.event_log)


def _advance_reroll_permission_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    unit_instance_id: str,
    player_id: str,
    keywords: tuple[str, ...],
    ability_index: AbilityCatalogIndex,
    current_model_instance_ids: tuple[str, ...],
) -> RerollPermission | None:
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    if _ADVANCE_REROLL_KEYWORD in keyword_set:
        return RerollPermission(
            source_id=f"{unit_instance_id}:advance-reroll",
            timing_window="after_roll_before_modifiers",
            owning_player_id=player_id,
            eligible_roll_type="advance_roll",
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
    catalog_permission = catalog_advance_roll_reroll_permission_for_unit(
        ability_index=ability_index,
        unit=unit,
        current_model_instance_ids=current_model_instance_ids,
        player_id=player_id,
    )
    source_backed_permission = source_backed_reroll_permission_for_unit(
        state=state,
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        roll_type="advance_roll",
        timing_window="after_advance_roll",
    )
    conditional_leader_permission = conditional_leading_roll_reroll_permission(
        state=state,
        rules_unit_instance_id=unit_instance_id,
        player_id=player_id,
        rule_roll_type="advance_roll",
        eligible_roll_type="advance_roll",
        timing_window="after_advance_roll",
    )
    permissions = tuple(
        permission
        for permission in (
            catalog_permission,
            source_backed_permission,
            conditional_leader_permission,
        )
        if permission is not None
    )
    if len(permissions) > 1:
        raise GameLifecycleError("Multiple advance reroll permissions are available.")
    return permissions[0] if permissions else None


def _roll_desperate_escape_dice(
    *,
    state: GameState,
    decisions: DecisionController,
    resolution: FallBackActionResult,
) -> tuple[DesperateEscapeRoll, ...]:
    rolls: list[DesperateEscapeRoll] = []
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    roll_modifiers = _desperate_escape_roll_modifiers(resolution)
    for requirement in resolution.desperate_escape_requirements:
        decisions.event_log.append(
            "desperate_escape_roll_requested",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": requirement.unit_instance_id,
                "model_instance_id": requirement.model_instance_id,
                "desperate_escape_requirement": validate_json_value(requirement.to_payload()),
            },
        )
        roll = DesperateEscapeRoll.from_roll_state(
            requirement=requirement,
            roll_state=manager.roll(requirement.roll_spec()),
            roll_modifiers=roll_modifiers,
        )
        decisions.event_log.append(
            "desperate_escape_roll_resolved",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": requirement.unit_instance_id,
                "model_instance_id": requirement.model_instance_id,
                "desperate_escape_roll": validate_json_value(roll.to_payload()),
            },
        )
        rolls.append(roll)
    return tuple(rolls)


def _resolve_forced_desperate_escape_battle_shock(
    *,
    state: GameState,
    decisions: DecisionController,
    resolution: FallBackActionResult,
    action_result: DecisionResult,
    battle_shock_hooks: BattleShockHookRegistry,
    ability_index: AbilityCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
    movement_proposal_request_id: str,
) -> LifecycleStatus | None:
    raw_sources = resolution.movement_payload.get("forced_desperate_escape_sources")
    if raw_sources is None:
        return None
    if not isinstance(raw_sources, list) or not raw_sources:
        raise GameLifecycleError(
            "forced_desperate_escape_sources must be a non-empty list when present."
        )
    source_rule_ids = _forced_desperate_escape_source_rule_ids_from_context(
        resolution.movement_payload
    )
    if not source_rule_ids:
        raise GameLifecycleError("Forced Desperate Escape requires source rule IDs.")
    for event in decisions.event_log.records:
        if event.event_type != "forced_desperate_escape_battle_shock_resolved":
            continue
        payload = cast(dict[str, JsonValue], event.payload)
        if (
            payload.get("unit_instance_id") == resolution.unit_instance_id
            and payload.get("battle_round") == state.battle_round
            and payload.get("source_rule_ids") == list(source_rule_ids)
        ):
            return None

    unit = _unit_instance_by_id(
        state=state,
        unit_instance_id=resolution.unit_instance_id,
    )
    player_id = resolution.attempted_placement.player_id
    current_model_ids = tuple(
        model.model_instance_id for model in unit.own_models if model.is_alive
    )
    if not current_model_ids:
        raise GameLifecycleError("Forced Desperate Escape battle-shock found no living models.")
    phase_start_battle_shocked_unit_ids = tuple(state.battle_shocked_unit_ids)
    reason = (
        BattleShockTestReason.FORCED_BY_STRATAGEM
        if any(
            isinstance(source, dict) and source.get("stratagem_use_id") is not None
            for source in raw_sources
        )
        else BattleShockTestReason.FORCED_BY_ARMY_RULE
    )
    dice_expression = battle_shock_hooks.dice_expression_for(
        BattleShockDiceExpressionContext(
            state=state,
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            reason=reason,
            active_player_id=_active_player_id(state),
            phase=BattlePhase.MOVEMENT,
            default_expression=DiceExpression(quantity=2, sides=6),
            phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        )
    )
    request = BattleShockTestRequest.for_unit(
        request_id=(f"forced-desperate-escape:{state.battle_round:02d}:{unit.unit_instance_id}"),
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        unit_instance_id=unit.unit_instance_id,
        reason=reason,
        leadership_target=battle_shock_leadership_target_for_unit(
            unit,
            current_model_ids=current_model_ids,
            ability_index=ability_index,
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        ),
        below_half_strength_context=BelowHalfStrengthContext.from_unit(
            player_id=player_id,
            unit=unit,
            starting_strength=state.starting_strength_record_for_unit(unit.unit_instance_id),
            current_model_ids=current_model_ids,
        ),
        dice_expression=dice_expression,
    )
    base_payload: dict[str, JsonValue] = {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "unit_instance_id": unit.unit_instance_id,
        "source_kind": FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND,
        "source_rule_ids": list(source_rule_ids),
        "source_rule_id": FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_RULE_ID,
        "fall_back_result": validate_json_value(resolution.to_payload()),
        "action_result": validate_json_value(action_result.to_payload()),
        "movement_proposal_request_id": movement_proposal_request_id,
    }
    decisions.event_log.append(
        "forced_desperate_escape_battle_shock_requested",
        {
            **base_payload,
            "battle_shock_test_request": request.to_payload(),
        },
    )
    manager = _dice_roll_manager_for_state(state=state, decisions=decisions)
    battle_shock_resolution = resolve_battle_shock_test_with_optional_reroll(
        state=state,
        decisions=decisions,
        manager=manager,
        battle_shock_hooks=battle_shock_hooks,
        request=request,
        roll_state=manager.roll(request.spec),
        active_player_id=_active_player_id(state),
        phase=BattlePhase.MOVEMENT,
        phase_start_battle_shocked_unit_ids=phase_start_battle_shocked_unit_ids,
        source_kind=FORCED_DESPERATE_ESCAPE_BATTLE_SHOCK_SOURCE_KIND,
        base_payload=base_payload,
        resolved_event_types=("forced_desperate_escape_battle_shock_resolved",),
        pending_phase_body_status=("forced_desperate_escape_battle_shock_reroll_pending"),
    )
    if battle_shock_resolution.pending_status is not None:
        return battle_shock_resolution.pending_status
    if battle_shock_resolution.resolved_payload is None:
        raise GameLifecycleError("Forced Desperate Escape Battle-shock did not resolve.")
    return None


def _desperate_escape_roll_modifiers(
    resolution: FallBackActionResult,
) -> tuple[RollModifier, ...]:
    if type(resolution) is not FallBackActionResult:
        raise GameLifecycleError("Desperate Escape modifiers require FallBackActionResult.")
    raw_sources = resolution.movement_payload.get("forced_desperate_escape_sources")
    if raw_sources is None:
        return ()
    if not isinstance(raw_sources, list):
        raise GameLifecycleError("forced_desperate_escape_sources must be a list.")
    modifiers: list[RollModifier] = []
    for raw_source in raw_sources:
        if not isinstance(raw_source, dict):
            raise GameLifecycleError("forced_desperate_escape_sources must contain objects.")
        source = cast(dict[str, object], raw_source)
        delta = source.get("desperate_escape_roll_modifier", 0)
        if type(delta) is not int:
            raise GameLifecycleError("desperate_escape_roll_modifier must be an integer.")
        if delta == 0:
            continue
        effect_id = source.get("effect_id")
        source_rule_id = source.get("source_rule_id")
        if type(effect_id) is not str or type(source_rule_id) is not str:
            raise GameLifecycleError("Desperate Escape modifier source metadata is malformed.")
        modifiers.append(
            RollModifier(
                modifier_id=f"{_validate_identifier('effect_id', effect_id)}:roll-modifier",
                source_id=_validate_identifier("source_rule_id", source_rule_id),
                operand=delta,
            )
        )
    return tuple(sorted(modifiers, key=lambda modifier: modifier.modifier_id))


def _desperate_escape_model_selection_request(
    *,
    state: GameState,
    fall_back_result: FallBackActionResult,
    action_result: DecisionResult,
) -> DecisionRequest:
    failed_model_ids = tuple(
        roll.requirement.model_instance_id
        for roll in fall_back_result.failed_desperate_escape_rolls
    )
    if not failed_model_ids:
        raise GameLifecycleError("Desperate Escape model selection requires failed rolls.")
    return DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_DESPERATE_ESCAPE_MODEL_DECISION_TYPE,
        actor_id=_active_player_id(state),
        payload={
            "fall_back_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.MOVEMENT.value,
                "unit_instance_id": fall_back_result.unit_instance_id,
                "action_request_id": action_result.request_id,
                "action_result_id": action_result.result_id,
                "action_selected_option_id": action_result.selected_option_id,
                "fall_back_result": validate_json_value(fall_back_result.to_payload()),
                "failed_model_ids": list(failed_model_ids),
            }
        },
        options=_desperate_escape_model_selection_options(
            fall_back_result=fall_back_result,
        ),
    )


def _desperate_escape_model_selection_options(
    *,
    fall_back_result: FallBackActionResult,
) -> tuple[DecisionOption, ...]:
    failed_model_ids = tuple(
        roll.requirement.model_instance_id
        for roll in fall_back_result.failed_desperate_escape_rolls
    )
    destroyed_count = len(failed_model_ids)
    eligible_model_ids = tuple(
        placement.model_instance_id
        for placement in fall_back_result.attempted_placement.model_placements
    )
    options: list[DecisionOption] = []
    for selected_ids in combinations(eligible_model_ids, destroyed_count):
        option_id = "destroy:" + ",".join(selected_ids)
        options.append(
            DecisionOption(
                option_id=option_id,
                label="Destroy " + ", ".join(selected_ids),
                payload={
                    "unit_instance_id": fall_back_result.unit_instance_id,
                    "destroyed_model_ids": list(selected_ids),
                    "failed_model_ids": list(failed_model_ids),
                },
            )
        )
    return tuple(options)
