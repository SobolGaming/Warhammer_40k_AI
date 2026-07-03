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
    from warhammer40k_core.engine.phases.movement_validation import _movement_action_invalid_payload, assert_move_units_step_complete_for_reinforcements, _remaining_move_units_unit_ids, _normal_move_invalid_message, _ensure_movement_phase_state, _validate_movement_phase_state, _battlefield_scenario, _movement_unit_options, _active_player_id, movement_phase_action_kind_from_token, fall_back_mode_kind_from_token, movement_phase_step_kind_from_token, desperate_escape_requirement_reason_from_token, movement_mode_for_phase_action, _movement_mode_from_payload, _movement_mode_from_proposal_submission, _fall_back_mode_from_payload, _fall_back_mode_from_proposal_submission, _movement_action_option_id, _movement_action_label, _movement_modes_for_action_options, _unit_can_take_to_the_skies, _fall_back_modes_for_parameterized_option, _fall_back_result_with_mode, _fall_back_mode_violation_code, _model_movement_inches, _model_base_movement_inches, _model_movement_budget_inches, _movement_distance_modifier_inches, _movement_mode_for_action, _temporary_movement_keywords_for_unit, _movement_bonus_inches_for_unit, _effective_movement_keywords, _model_default_movement_distance_inches, _modified_movement_inches, _runtime_modifier_registry, _default_move_end_pose, _ruleset_descriptor_for_handler, _mission_setup_for_live_reinforcements, _objective_markers_for_state, _active_movement_selection, _ensure_transport_cargo_phase_states, _unit_instance_by_id, _unit_has_keyword, _transport_status_for_movement_action, _movement_completion_context_payload, _transport_operation_invalid_payload, _request_payload_for_result, _decision_payload_object, _payload_string, _payload_object, _payload_json_object, _identifier_list_from_json_object, _payload_positive_int, _optional_payload_path_witness, _payload_model_displacement_kind, _payload_transition_batch, _payload_json_array, _validate_json_object, _validate_movement_action_tuple, _validate_transport_restriction_override_tuple, _validate_path_validation_result_tuple, _validate_terrain_path_legality_result_tuple, _validate_desperate_escape_reason_tuple, _validate_desperate_escape_requirement_tuple, _validate_desperate_escape_roll_tuple, _validate_identifier_tuple, _validate_movement_distance_records, _validate_objective_marker_tuple, _validate_advance_roll_spec, _validate_identifier, _validate_positive_int, _validate_non_negative_finite_number, _validate_bool
# fmt: on

__all__ = (
    "_ability_index_for_player",
    "_canonical_keyword",
    "_desperate_escape_requirements_for_fall_back",
    "_enemy_engaged_unit_ids_for_unit_placement",
    "_enemy_engagement_model_ids_for_unit",
    "_enemy_geometry_models_for_player",
    "_enemy_model_ids_crossed_by_witness",
    "_enemy_vehicle_monster_model_ids_for_player",
    "_friendly_geometry_models_for_path",
    "_friendly_vehicle_monster_model_ids",
    "_geometry_models_for_unit_placement",
    "_hover_mode_state_for_unit",
    "_interpolate_pose",
    "_model_at_pose",
    "_movement_action_availability_context",
    "_normal_move_violation_code",
    "_path_result_with_aircraft_violations",
    "_sampled_witness_transit_poses",
    "_unit_has_deep_strike_keyword",
    "_unit_has_vehicle_or_monster_keyword",
    "_validate_ability_index_mapping",
    "_validate_move_witness_matches_unit",
)


def _movement_action_availability_context(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> MovementActionAvailabilityContext:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Movement action availability requires a scenario.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Movement action availability requires a UnitPlacement.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Movement action availability requires a RulesetDescriptor.")
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
    enemy_engagement_model_ids, enemy_aircraft_engagement_model_ids = (
        _enemy_engagement_model_ids_for_unit(
            scenario=scenario,
            unit_placement=unit_placement,
            ruleset_descriptor=ruleset_descriptor,
            hover_mode_states=hover_mode_states,
        )
    )
    return MovementActionAvailabilityContext(
        ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
        unit_instance_id=unit_placement.unit_instance_id,
        player_id=unit_placement.player_id,
        enemy_engagement_model_ids=enemy_engagement_model_ids,
        enemy_aircraft_engagement_model_ids=enemy_aircraft_engagement_model_ids,
        aircraft_movement_policy=aircraft_policy if aircraft_policy.has_aircraft_keyword else None,
    )


def _enemy_engagement_model_ids_for_unit(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    friendly_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    enemy_models = _enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    aircraft_model_ids = set(
        aircraft_model_ids_for_scenario(
            scenario,
            hover_mode_states=hover_mode_states,
        )
    )
    enemy_model_ids: set[str] = set()
    enemy_aircraft_model_ids: set[str] = set()
    for friendly_model in friendly_models:
        for enemy_model in enemy_models:
            if friendly_model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                if enemy_model.model_id in aircraft_model_ids:
                    enemy_aircraft_model_ids.add(enemy_model.model_id)
                else:
                    enemy_model_ids.add(enemy_model.model_id)
    return tuple(sorted(enemy_model_ids)), tuple(sorted(enemy_aircraft_model_ids))


def _enemy_engaged_unit_ids_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    ruleset_descriptor: RulesetDescriptor,
) -> tuple[str, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Enemy engaged unit query requires a scenario.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Enemy engaged unit query requires a unit placement.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Enemy engaged unit query requires ruleset descriptor.")
    friendly_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    )
    engaged_unit_ids: set[str] = set()
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == unit_placement.player_id:
            continue
        for enemy_unit_placement in placed_army.unit_placements:
            enemy_models = _geometry_models_for_unit_placement(
                scenario=scenario,
                unit_placement=enemy_unit_placement,
            )
            if any(
                friendly_model.is_within_engagement_range(
                    enemy_model,
                    horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                    vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
                )
                for friendly_model in friendly_models
                for enemy_model in enemy_models
            ):
                engaged_unit_ids.add(enemy_unit_placement.unit_instance_id)
    return tuple(sorted(engaged_unit_ids))


def _hover_mode_state_for_unit(
    *,
    hover_mode_states: tuple[HoverModeState, ...],
    unit_instance_id: str,
) -> HoverModeState | None:
    if type(hover_mode_states) is not tuple:
        raise GameLifecycleError("hover_mode_states must be a tuple.")
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    found: HoverModeState | None = None
    for hover_mode_state in cast(tuple[object, ...], hover_mode_states):
        if type(hover_mode_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_states must contain HoverModeState values.")
        if hover_mode_state.unit_instance_id != requested_unit_id:
            continue
        if found is not None:
            raise GameLifecycleError("hover_mode_states must be unique by unit.")
        found = hover_mode_state
    return found if found is not None and found.active else None


def _desperate_escape_requirements_for_fall_back(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    witness: PathWitness,
    battle_round: int,
    battle_shocked_unit_ids: tuple[str, ...],
    forced_desperate_escape_source_rule_ids: tuple[str, ...] = (),
) -> tuple[DesperateEscapeRequirement, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Desperate Escape requirements require a scenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Desperate Escape requirements require a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Desperate Escape requirements require a UnitPlacement.")
    if type(witness) is not PathWitness:
        raise GameLifecycleError("Desperate Escape requirements require a PathWitness.")
    requirement_battle_round = _validate_positive_int(
        "Desperate Escape requirements battle_round",
        battle_round,
    )
    battle_shocked_ids = set(
        _validate_identifier_tuple(
            "battle_shocked_unit_ids",
            battle_shocked_unit_ids,
        )
    )
    forced_source_ids = _validate_identifier_tuple(
        "forced_desperate_escape_source_rule_ids",
        forced_desperate_escape_source_rule_ids,
    )
    unit = scenario.unit_instance_for_placement(unit_placement)
    unit_keyword_set = {_canonical_keyword(keyword) for keyword in unit.keywords}
    overflight_exempt = "FLY" in unit_keyword_set or "TITANIC" in unit_keyword_set
    enemy_models = _enemy_geometry_models_for_player(
        scenario=scenario,
        player_id=unit_placement.player_id,
    )
    requirements: list[DesperateEscapeRequirement] = []
    for index, placement in enumerate(unit_placement.model_placements, start=1):
        reasons: list[DesperateEscapeRequirementReason] = []
        enemy_model_ids: tuple[str, ...] = ()
        if unit_placement.unit_instance_id in battle_shocked_ids:
            reasons.append(DesperateEscapeRequirementReason.BATTLE_SHOCKED)
        if forced_source_ids:
            reasons.append(DesperateEscapeRequirementReason.FORCED_BY_RULE)
        if not overflight_exempt:
            moving_model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(placement),
                placement=placement,
            )
            enemy_model_ids = _enemy_model_ids_crossed_by_witness(
                moving_model=moving_model,
                witness=witness,
                enemy_models=enemy_models,
            )
            if enemy_model_ids:
                reasons.append(DesperateEscapeRequirementReason.ENEMY_MODEL_OVERFLIGHT)
        if not reasons:
            continue
        requirements.append(
            DesperateEscapeRequirement(
                requirement_id=f"{unit_placement.unit_instance_id}:desperate-escape:{index:03d}",
                player_id=unit_placement.player_id,
                battle_round=requirement_battle_round,
                unit_instance_id=unit_placement.unit_instance_id,
                model_instance_id=placement.model_instance_id,
                reasons=tuple(reasons),
                enemy_model_ids=enemy_model_ids,
            )
        )
    return tuple(requirements)


def _enemy_model_ids_crossed_by_witness(
    *,
    moving_model: Model,
    witness: PathWitness,
    enemy_models: tuple[Model, ...],
) -> tuple[str, ...]:
    crossed_enemy_ids: set[str] = set()
    for pose in _sampled_witness_transit_poses(
        witness.poses_for_model(moving_model.model_id),
        sample_interval_inches=0.5,
    ):
        sampled_model = _model_at_pose(moving_model, pose)
        for enemy_model in enemy_models:
            if sampled_model.base_overlaps(enemy_model):
                crossed_enemy_ids.add(enemy_model.model_id)
    return tuple(sorted(crossed_enemy_ids))


def _sampled_witness_transit_poses(
    poses: tuple[Pose, ...],
    *,
    sample_interval_inches: float,
) -> tuple[Pose, ...]:
    if type(poses) is not tuple:
        raise GameLifecycleError("Fall Back witness poses must be a tuple.")
    if len(poses) < 2:
        raise GameLifecycleError("Fall Back witness poses must include start and end.")
    interval = float(sample_interval_inches)
    if not math.isfinite(interval) or interval <= 0:
        raise GameLifecycleError("sample_interval_inches must be greater than 0.")
    sampled: list[Pose] = [poses[0]]
    previous = poses[0]
    for pose in poses[1:]:
        distance = previous.distance_3d_to(pose)
        steps = max(1, math.ceil(distance / interval))
        for step in range(1, steps + 1):
            sampled.append(_interpolate_pose(previous, pose, step / steps))
        previous = pose
    return tuple(sampled[1:-1])


def _interpolate_pose(start: Pose, end: Pose, t: float) -> Pose:
    return Pose.at(
        x=start.position.x + ((end.position.x - start.position.x) * t),
        y=start.position.y + ((end.position.y - start.position.y) * t),
        z=start.position.z + ((end.position.z - start.position.z) * t),
        facing_degrees=start.facing.degrees + ((end.facing.degrees - start.facing.degrees) * t),
    )


def _model_at_pose(model: Model, pose: Pose) -> Model:
    if type(model) is not Model:
        raise GameLifecycleError("model must be a geometry Model.")
    if type(pose) is not Pose:
        raise GameLifecycleError("pose must be a Pose.")
    return Model(
        model_id=model.model_id,
        pose=pose,
        base=model.base,
        volume=model.volume,
    )


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[Model, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )


def _friendly_geometry_models_for_path(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
    attempted_placement: UnitPlacement,
    moving_model_instance_id: str,
) -> tuple[Model, ...]:
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    friendly_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != unit_placement.player_id:
            continue
        for current_unit_placement in placed_army.unit_placements:
            placements = (
                attempted_placement.model_placements
                if current_unit_placement.unit_instance_id == unit_placement.unit_instance_id
                else current_unit_placement.model_placements
            )
            for placement in placements:
                if placement.model_instance_id == moving_model_id:
                    continue
                friendly_models.append(
                    geometry_model_for_placement(
                        model=scenario.model_instance_for_placement(placement),
                        placement=placement,
                    )
                )
    return tuple(friendly_models)


def _enemy_geometry_models_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[Model, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    enemy_models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            enemy_models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(enemy_models)


def _friendly_vehicle_monster_model_ids(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
    moving_model_instance_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    moving_model_id = _validate_identifier("moving_model_instance_id", moving_model_instance_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id != requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id
                for placement in unit_placement.model_placements
                if placement.model_instance_id != moving_model_id
            )
    return tuple(sorted(model_ids))


def _enemy_vehicle_monster_model_ids_for_player(
    *,
    scenario: BattlefieldScenario,
    player_id: str,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == requested_player_id:
            continue
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if not _unit_has_vehicle_or_monster_keyword(unit.keywords):
                continue
            model_ids.extend(
                placement.model_instance_id for placement in unit_placement.model_placements
            )
    return tuple(sorted(model_ids))


def _unit_has_vehicle_or_monster_keyword(keywords: tuple[str, ...]) -> bool:
    keyword_set = {_canonical_keyword(keyword) for keyword in keywords}
    return "VEHICLE" in keyword_set or "MONSTER" in keyword_set


def _unit_has_deep_strike_keyword(unit: UnitInstance) -> bool:
    return unit_has_deep_strike(unit)


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _validate_ability_index_mapping(indexes: object) -> Mapping[str, AbilityCatalogIndex]:
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("ability_indexes_by_player_id must be a mapping.")
    mapped_indexes = cast(Mapping[object, object], indexes)
    validated: dict[str, AbilityCatalogIndex] = {}
    for raw_player_id, raw_index in mapped_indexes.items():
        player_id = _validate_identifier("ability_indexes_by_player_id key", raw_player_id)
        if type(raw_index) is not AbilityCatalogIndex:
            raise GameLifecycleError(
                "ability_indexes_by_player_id values must be AbilityCatalogIndex."
            )
        validated[player_id] = raw_index
    return MappingProxyType(validated)


def _ability_index_for_player(
    indexes: object,
    *,
    player_id: str,
) -> AbilityCatalogIndex:
    player = _validate_identifier("player_id", player_id)
    if not isinstance(indexes, Mapping):
        raise GameLifecycleError("ability_indexes_by_player_id must be a mapping.")
    mapped_indexes = cast(Mapping[str, AbilityCatalogIndex], indexes)
    index = mapped_indexes.get(player)
    if index is None:
        return AbilityCatalogIndex.from_records(())
    if type(index) is not AbilityCatalogIndex:
        raise GameLifecycleError("ability index mapping contained an invalid value.")
    return index


def _validate_move_witness_matches_unit(
    *,
    witness: PathWitness,
    unit_placement: UnitPlacement,
    action_label: str,
) -> None:
    if type(witness) is not PathWitness:
        raise GameLifecycleError(f"{action_label} requires a PathWitness.")
    expected_model_ids = tuple(
        sorted(placement.model_instance_id for placement in unit_placement.model_placements)
    )
    if tuple(sorted(witness.model_ids())) != expected_model_ids:
        raise GameLifecycleError(f"{action_label} witness must match the selected unit models.")


def _path_result_with_aircraft_violations(
    *,
    path_result: PathValidationResult,
    aircraft_violations: tuple[AircraftMovementViolation, ...],
) -> PathValidationResult:
    if type(path_result) is not PathValidationResult:
        raise GameLifecycleError("Aircraft path validation requires a PathValidationResult.")
    if type(aircraft_violations) is not tuple:
        raise GameLifecycleError("aircraft_violations must be a tuple.")
    if not aircraft_violations:
        return path_result
    return PathValidationResult(
        violations=(
            *path_result.violations,
            *(
                PathConstraintViolation(
                    violation_code=violation.violation_code.value,
                    message=violation.message,
                    model_id=violation.model_instance_id,
                )
                for violation in aircraft_violations
            ),
        ),
        sampled_pose_count=path_result.sampled_pose_count,
        model_collision_check_count=path_result.model_collision_check_count,
        terrain_collision_check_count=path_result.terrain_collision_check_count,
        engagement_check_count=path_result.engagement_check_count,
        movement_distance_witness=path_result.movement_distance_witness,
    )


def _normal_move_violation_code(
    resolution: NormalMoveResolution | AdvanceMoveResolution | FallBackActionResult,
) -> str:
    for path_result in resolution.path_validation_results:
        if path_result.is_valid:
            continue
        return path_result.violations[0].violation_code
    for terrain_result in resolution.terrain_path_legality_results:
        if terrain_result.is_valid:
            continue
        return terrain_result.violations[0].violation_code
    if resolution.rollback_record is not None:
        return "unit_coherency_broken"
    return "normal_move_invalid"
