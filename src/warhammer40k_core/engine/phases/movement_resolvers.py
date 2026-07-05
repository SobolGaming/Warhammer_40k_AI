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
    from warhammer40k_core.engine.phases.movement_geometry import _movement_action_availability_context, _enemy_engagement_model_ids_for_unit, _enemy_engaged_unit_ids_for_unit_placement, _hover_mode_state_for_unit, _desperate_escape_requirements_for_fall_back, _enemy_model_ids_crossed_by_witness, _sampled_witness_transit_poses, _interpolate_pose, _model_at_pose, _geometry_models_for_unit_placement, _friendly_geometry_models_for_path, _enemy_geometry_models_for_player, _friendly_vehicle_monster_model_ids, _enemy_vehicle_monster_model_ids_for_player, _unit_has_vehicle_or_monster_keyword, _unit_has_deep_strike_keyword, _canonical_keyword, _validate_ability_index_mapping, _ability_index_for_player, _validate_move_witness_matches_unit, _path_result_with_aircraft_violations, _normal_move_violation_code
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_default_fall_back_witness",
    "_default_move_witness",
    "_fall_back_transition_batch",
    "_movement_action_availability_result",
    "_movement_transition_batch",
    "_normal_move_transition_batch",
    "_resolve_unit_move",
    "resolve_advance_move",
    "resolve_fall_back_move",
    "resolve_normal_move",
)


def resolve_normal_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    state: GameState | None = None,
    movement_mode: MovementMode = MovementMode.NORMAL,
    path_witness: PathWitness | None = None,
    hover_mode_states: tuple[HoverModeState, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    movement_bonus_inches: int = 0,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ability_index: AbilityCatalogIndex | None = None,
    temporary_movement_keywords: tuple[str, ...] = (),
) -> NormalMoveResolution:
    resolved = _resolve_unit_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
        path_witness=path_witness,
        battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
        terrain=terrain,
        terrain_features=scenario.battlefield_state.terrain_features,
        objective_markers=objective_markers,
        movement_bonus_inches=movement_bonus_inches,
        movement_mode=_movement_mode_for_action(
            action=MovementPhaseActionKind.NORMAL_MOVE,
            movement_mode=movement_mode,
        ),
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
        action_label="Normal Move",
        rollback_on_endpoint_coherency=True,
        hover_mode_states=hover_mode_states,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_index=ability_index,
        temporary_movement_keywords=temporary_movement_keywords,
    )
    return NormalMoveResolution(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=resolved.attempted_placement,
        witness=resolved.witness,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=resolved.rollback_record,
        movement_payload=resolved.movement_payload,
    )


def resolve_advance_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    advance_roll: AdvanceRollResult,
    state: GameState | None = None,
    movement_mode: MovementMode = MovementMode.ADVANCE,
    path_witness: PathWitness | None = None,
    hover_mode_states: tuple[HoverModeState, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    movement_bonus_inches: int = 0,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ability_index: AbilityCatalogIndex | None = None,
    temporary_movement_keywords: tuple[str, ...] = (),
) -> AdvanceMoveResolution:
    if type(advance_roll) is not AdvanceRollResult:
        raise GameLifecycleError("Advance requires an AdvanceRollResult.")
    resolved = _resolve_unit_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
        path_witness=path_witness,
        battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
        terrain=terrain,
        terrain_features=scenario.battlefield_state.terrain_features,
        objective_markers=objective_markers,
        movement_bonus_inches=advance_roll.value + movement_bonus_inches,
        movement_mode=_movement_mode_for_action(
            action=MovementPhaseActionKind.ADVANCE,
            movement_mode=movement_mode,
        ),
        movement_phase_action=MovementPhaseActionKind.ADVANCE,
        displacement_kind=ModelDisplacementKind.ADVANCE,
        action_label="Advance",
        rollback_on_endpoint_coherency=True,
        hover_mode_states=hover_mode_states,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_index=ability_index,
        temporary_movement_keywords=temporary_movement_keywords,
    )
    movement_payload = {
        **resolved.movement_payload,
        "advance_roll": validate_json_value(advance_roll.to_payload()),
    }
    return AdvanceMoveResolution(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=resolved.attempted_placement,
        witness=resolved.witness,
        advance_roll=advance_roll,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=resolved.rollback_record,
        movement_payload=movement_payload,
    )


def resolve_fall_back_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    state: GameState | None = None,
    movement_mode: MovementMode = MovementMode.FALL_BACK,
    path_witness: PathWitness | None = None,
    battle_round: int = 1,
    battle_shocked_unit_ids: tuple[str, ...] = (),
    forced_desperate_escape_source_rule_ids: tuple[str, ...] = (),
    hover_mode_states: tuple[HoverModeState, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    movement_bonus_inches: int = 0,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    ability_index: AbilityCatalogIndex | None = None,
    temporary_movement_keywords: tuple[str, ...] = (),
) -> FallBackActionResult:
    forced_source_ids = _validate_identifier_tuple(
        "forced_desperate_escape_source_rule_ids",
        forced_desperate_escape_source_rule_ids,
    )
    fall_back_witness = (
        _default_fall_back_witness(
            scenario=scenario,
            unit_placement=unit_placement,
            state=state,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if path_witness is None
        else path_witness
    )
    resolved = _resolve_unit_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        state=state,
        path_witness=fall_back_witness,
        battlefield_width_inches=scenario.battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=scenario.battlefield_state.battlefield_depth_inches,
        terrain=terrain,
        terrain_features=scenario.battlefield_state.terrain_features,
        objective_markers=objective_markers,
        movement_bonus_inches=movement_bonus_inches,
        movement_mode=_movement_mode_for_action(
            action=MovementPhaseActionKind.FALL_BACK,
            movement_mode=movement_mode,
        ),
        movement_phase_action=MovementPhaseActionKind.FALL_BACK,
        displacement_kind=ModelDisplacementKind.FALL_BACK,
        action_label="Fall Back",
        rollback_on_endpoint_coherency=False,
        hover_mode_states=hover_mode_states,
        runtime_modifier_registry=runtime_modifier_registry,
        ability_index=ability_index,
        temporary_movement_keywords=temporary_movement_keywords,
    )
    desperate_escape_requirements = _desperate_escape_requirements_for_fall_back(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        witness=resolved.witness,
        battle_round=battle_round,
        battle_shocked_unit_ids=battle_shocked_unit_ids,
        forced_desperate_escape_source_rule_ids=forced_source_ids,
    )
    movement_payload = {
        **resolved.movement_payload,
        "desperate_escape_requirements": validate_json_value(
            [requirement.to_payload() for requirement in desperate_escape_requirements]
        ),
        "desperate_escape_rolls": [],
    }
    if forced_source_ids:
        movement_payload["forced_desperate_escape_source_rule_ids"] = list(forced_source_ids)
    return FallBackActionResult.unresolved(
        unit_instance_id=unit_placement.unit_instance_id,
        attempted_placement=resolved.attempted_placement,
        witness=resolved.witness,
        desperate_escape_requirements=desperate_escape_requirements,
        path_validation_results=resolved.path_validation_results,
        terrain_path_legality_results=resolved.terrain_path_legality_results,
        coherency_result=resolved.coherency_result,
        rollback_record=resolved.rollback_record,
        movement_payload=movement_payload,
    )


def _resolve_unit_move(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    state: GameState | None,
    path_witness: PathWitness | None,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain: tuple[TerrainVolume, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    movement_bonus_inches: int,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind,
    displacement_kind: ModelDisplacementKind,
    action_label: str,
    rollback_on_endpoint_coherency: bool,
    hover_mode_states: tuple[HoverModeState, ...],
    runtime_modifier_registry: RuntimeModifierRegistry | None,
    ability_index: AbilityCatalogIndex | None,
    temporary_movement_keywords: tuple[str, ...],
) -> _ResolvedUnitMove:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError(f"{action_label} requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError(f"{action_label} requires a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError(f"{action_label} unit_placement must be a UnitPlacement.")
    if type(movement_bonus_inches) is not int:
        raise GameLifecycleError(f"{action_label} movement_bonus_inches must be an integer.")
    if movement_bonus_inches < 0:
        raise GameLifecycleError(f"{action_label} movement_bonus_inches must not be negative.")
    validated_temporary_keywords = _validate_identifier_tuple(
        f"{action_label} temporary_movement_keywords",
        temporary_movement_keywords,
    )
    markers = _validate_objective_marker_tuple(
        f"{action_label} objective_markers",
        objective_markers,
    )
    unit = scenario.unit_instance_for_placement(unit_placement)
    unit_persisting_effects = (
        tuple(state.persisting_effects_for_unit(unit_placement.unit_instance_id))
        if state is not None
        else ()
    )
    hover_mode_state = _hover_mode_state_for_unit(
        hover_mode_states=hover_mode_states,
        unit_instance_id=unit_placement.unit_instance_id,
    )
    aircraft_policy = AircraftMovementPolicy.from_unit(
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=hover_mode_state,
    )
    effective_movement_keywords = _effective_movement_keywords(
        aircraft_policy.effective_keywords,
        temporary_keywords=validated_temporary_keywords,
    )
    witness = (
        _default_move_witness(
            scenario=scenario,
            unit_placement=unit_placement,
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            aircraft_policy=aircraft_policy,
            movement_bonus_inches=movement_bonus_inches,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if path_witness is None
        else path_witness
    )
    _validate_move_witness_matches_unit(
        witness=witness,
        unit_placement=unit_placement,
        action_label=action_label,
    )
    aircraft_model_ids = aircraft_model_ids_for_scenario(
        scenario,
        hover_mode_states=hover_mode_states,
    )
    moved_placements: list[ModelPlacement] = []
    for placement in unit_placement.model_placements:
        moved_placements.append(
            placement.with_pose(witness.final_pose_for_model(placement.model_instance_id))
        )
    attempted_placement = unit_placement.with_model_placements(tuple(moved_placements))
    path_validation_results: list[PathValidationResult] = []
    terrain_path_legality_results: list[TerrainPathLegalityResult] = []
    model_movements: list[JsonValue] = []
    max_movement_inches = 0.0
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        base_movement_inches = _model_base_movement_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            model_instance_id=placement.model_instance_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        movement_inches = _model_default_movement_distance_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            ruleset_descriptor=ruleset_descriptor,
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            model_instance_id=placement.model_instance_id,
            movement_bonus_inches=movement_bonus_inches,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        movement_distance_budget_inches = _model_movement_budget_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            ruleset_descriptor=ruleset_descriptor,
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            model_instance_id=placement.model_instance_id,
            movement_bonus_inches=movement_bonus_inches,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        movement_distance_modifier_inches = _movement_distance_modifier_inches(
            aircraft_policy=aircraft_policy,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
        )
        max_movement_inches = max(max_movement_inches, movement_inches)
        moving_model = geometry_model_for_placement(model=model, placement=placement)
        model_witness = PathWitness.for_paths(
            ((placement.model_instance_id, witness.poses_for_model(placement.model_instance_id)),)
        )
        legality_context = MovementLegalityContext.from_keywords(
            keywords=effective_movement_keywords,
            ruleset_descriptor=ruleset_descriptor,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action.value,
            displacement_kind=displacement_kind,
            ability_index=ability_index,
            unit=unit,
            model_instance_id=placement.model_instance_id,
            current_model_instance_ids=tuple(
                model_placement.model_instance_id
                for model_placement in unit_placement.model_placements
            ),
            unit_persisting_effects=unit_persisting_effects,
            owner_player_id=unit_placement.player_id,
        )
        path_result = legality_context.to_path_validation_context(
            moving_model=moving_model,
            witness=model_witness,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
            friendly_models=_friendly_geometry_models_for_path(
                scenario=scenario,
                unit_placement=unit_placement,
                attempted_placement=attempted_placement,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_models=_enemy_geometry_models_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            terrain=(),
            friendly_vehicle_monster_model_ids=_friendly_vehicle_monster_model_ids(
                scenario=scenario,
                player_id=unit_placement.player_id,
                moving_model_instance_id=placement.model_instance_id,
            ),
            enemy_vehicle_monster_model_ids=_enemy_vehicle_monster_model_ids_for_player(
                scenario=scenario,
                player_id=unit_placement.player_id,
            ),
            aircraft_model_ids=tuple(
                model_id
                for model_id in aircraft_model_ids
                if model_id != placement.model_instance_id
            ),
            movement_distance_budget_inches=movement_distance_budget_inches,
        ).validate()
        aircraft_violations: tuple[AircraftMovementViolation, ...] = ()
        if (
            aircraft_policy.uses_aircraft_rules
            and movement_phase_action is MovementPhaseActionKind.NORMAL_MOVE
        ):
            aircraft_violations = aircraft_policy.validate_normal_move_witness(
                moving_model=moving_model,
                witness=model_witness,
            )
            path_result = _path_result_with_aircraft_violations(
                path_result=path_result,
                aircraft_violations=aircraft_violations,
            )
        terrain_result = legality_context.to_terrain_path_legality_context(
            moving_model=moving_model,
            witness=model_witness,
            terrain=terrain,
            terrain_features=terrain_features,
        ).validate()
        end_model = geometry_model_for_placement(
            model=model,
            placement=placement.with_pose(
                witness.final_pose_for_model(placement.model_instance_id)
            ),
        )
        objective_marker_violation = objective_marker_endpoint_placement_violation(
            model=end_model,
            objective_markers=markers,
            violation_code="objective_marker_endpoint_overlap",
            placement_label=action_label,
        )
        if objective_marker_violation is not None and path_result.is_valid:
            path_result = PathValidationResult.invalid(
                PathConstraintViolation(
                    violation_code=objective_marker_violation.violation_code,
                    message=objective_marker_violation.message,
                    model_id=objective_marker_violation.model_instance_id,
                    blocker_id=objective_marker_violation.blocker_id,
                ),
                sampled_pose_count=path_result.sampled_pose_count,
                model_collision_check_count=path_result.model_collision_check_count,
                terrain_collision_check_count=path_result.terrain_collision_check_count,
                engagement_check_count=path_result.engagement_check_count,
                movement_distance_witness=path_result.movement_distance_witness,
            )
        path_validation_results.append(path_result)
        terrain_path_legality_results.append(terrain_result)
        model_movement_payload: dict[str, object] = {
            "model_instance_id": placement.model_instance_id,
            "movement_inches": movement_inches,
            "base_movement_inches": base_movement_inches,
            "movement_bonus_inches": movement_bonus_inches,
            "movement_mode": movement_mode.value,
            "movement_distance_modifier_inches": movement_distance_modifier_inches,
            "movement_keywords": list(effective_movement_keywords),
            "temporary_movement_keywords": list(validated_temporary_keywords),
            "base_size": model.base_size.to_payload(),
            "start_pose": placement.pose.to_payload(),
            "end_pose": witness.final_pose_for_model(placement.model_instance_id).to_payload(),
            "movement_distance_witness": (
                None
                if path_result.movement_distance_witness is None
                else path_result.movement_distance_witness.to_payload()
            ),
            "path_validation_result": path_result.to_payload(),
            "terrain_path_legality_result": terrain_result.to_payload(),
        }
        if aircraft_violations:
            model_movement_payload["aircraft_movement_violations"] = [
                violation.to_payload() for violation in aircraft_violations
            ]
        model_movements.append(validate_json_value(model_movement_payload))
    if rollback_on_endpoint_coherency:
        _, coherency_result, rollback_record = resolve_unit_movement_endpoint_coherency(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            before=unit_placement,
            attempted=attempted_placement,
            displacement_kind=displacement_kind,
        )
    else:
        coherency_result = unit_placement_coherency_result(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            unit_placement=attempted_placement,
        )
        rollback_record = None
    movement_payload: dict[str, JsonValue] = {
        "movement_mode": movement_mode.value,
        "movement_inches": max_movement_inches,
        "model_movements": model_movements,
        "path_validation_results": validate_json_value(
            [result.to_payload() for result in path_validation_results]
        ),
        "terrain_path_legality_results": validate_json_value(
            [result.to_payload() for result in terrain_path_legality_results]
        ),
        "coherency_result": validate_json_value(coherency_result.to_payload()),
    }
    if aircraft_policy.has_aircraft_keyword:
        movement_payload["aircraft_movement_policy"] = validate_json_value(
            aircraft_policy.to_payload()
        )
    return _ResolvedUnitMove(
        attempted_placement=attempted_placement,
        witness=witness,
        path_validation_results=tuple(path_validation_results),
        terrain_path_legality_results=tuple(terrain_path_legality_results),
        coherency_result=coherency_result,
        rollback_record=rollback_record,
        movement_payload=movement_payload,
    )


def _default_move_witness(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    state: GameState | None,
    ruleset_descriptor: RulesetDescriptor,
    aircraft_policy: AircraftMovementPolicy,
    movement_bonus_inches: int,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        movement_inches = _model_default_movement_distance_inches(
            model=model,
            aircraft_policy=aircraft_policy,
            ruleset_descriptor=ruleset_descriptor,
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            model_instance_id=placement.model_instance_id,
            movement_bonus_inches=movement_bonus_inches,
            movement_mode=movement_mode,
            movement_phase_action=movement_phase_action,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                _default_move_end_pose(
                    start_pose=placement.pose,
                    aircraft_policy=aircraft_policy,
                    movement_inches=movement_inches,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _default_fall_back_witness(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    state: GameState | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> PathWitness:
    model_paths: list[tuple[str, Pose, Pose]] = []
    for placement in unit_placement.model_placements:
        model = scenario.model_instance_for_placement(placement)
        base_movement_inches = float(_model_movement_inches(model))
        movement_inches = _modified_movement_inches(
            state=state,
            unit_instance_id=unit_placement.unit_instance_id,
            model_instance_id=placement.model_instance_id,
            base_movement_inches=base_movement_inches,
            current_movement_inches=base_movement_inches,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        model_paths.append(
            (
                placement.model_instance_id,
                placement.pose,
                Pose.at(
                    x=placement.pose.position.x,
                    y=placement.pose.position.y + movement_inches,
                    z=placement.pose.position.z,
                    facing_degrees=placement.pose.facing.degrees,
                ),
            )
        )
    return PathWitness.for_straight_line_endpoints(tuple(model_paths))


def _movement_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
    displacement_kind: ModelDisplacementKind,
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    displacement_records: list[ModelDisplacementRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Movement transition references an unknown model.")
        if placement.pose == before_poses[placement.model_instance_id]:
            continue
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=displacement_kind,
                start_pose=before_poses[placement.model_instance_id],
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.MOVEMENT.value,
                source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(displacements=tuple(displacement_records))


def _fall_back_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
    destroyed_model_ids: tuple[str, ...],
) -> BattlefieldTransitionBatch:
    before_poses = {
        placement.model_instance_id: placement.pose for placement in before.model_placements
    }
    destroyed_id_set = set(_validate_identifier_tuple("destroyed_model_ids", destroyed_model_ids))
    displacement_records: list[ModelDisplacementRecord] = []
    removal_records: list[ModelRemovalRecord] = []
    for placement in after.model_placements:
        if placement.model_instance_id not in before_poses:
            raise GameLifecycleError("Fall Back transition references an unknown model.")
        if placement.model_instance_id in destroyed_id_set:
            removal_records.append(
                ModelRemovalRecord(
                    model_instance_id=placement.model_instance_id,
                    removal_kind=BattlefieldRemovalKind.DESTROYED,
                    source_phase=BattlePhase.MOVEMENT.value,
                    source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                    source_rule_id="desperate_escape",
                    source_event_id=None,
                    destination_id=None,
                )
            )
            continue
        if placement.pose == before_poses[placement.model_instance_id]:
            continue
        model_path = witness.poses_for_model(placement.model_instance_id)
        displacement_records.append(
            ModelDisplacementRecord(
                model_instance_id=placement.model_instance_id,
                displacement_kind=ModelDisplacementKind.FALL_BACK,
                start_pose=before_poses[placement.model_instance_id],
                end_pose=placement.pose,
                path_witness=PathWitness.for_paths(((placement.model_instance_id, model_path),)),
                source_phase=BattlePhase.MOVEMENT.value,
                source_step=MovementPhaseStepKind.MOVE_UNITS.value,
                source_rule_id=None,
                source_event_id=None,
            )
        )
    return BattlefieldTransitionBatch(
        removals=tuple(removal_records),
        displacements=tuple(displacement_records),
    )


def _normal_move_transition_batch(
    *,
    before: UnitPlacement,
    after: UnitPlacement,
    witness: PathWitness,
) -> BattlefieldTransitionBatch:
    return _movement_transition_batch(
        before=before,
        after=after,
        witness=witness,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )


def _movement_action_availability_result(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> MovementActionAvailabilityResult:
    return _movement_action_availability_context(
        scenario=scenario,
        unit_placement=unit_placement,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_states=hover_mode_states,
    ).evaluate()
