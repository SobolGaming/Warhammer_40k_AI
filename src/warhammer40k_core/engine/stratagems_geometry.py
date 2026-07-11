# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_model import *
from warhammer40k_core.engine.stratagems_requests import *
from warhammer40k_core.engine.stratagems_apply import *
from warhammer40k_core.engine.stratagems_selection import *
from warhammer40k_core.engine.stratagems_eligibility import *
from warhammer40k_core.engine.stratagems_targeting import *
from warhammer40k_core.engine.shooting_targets import unit_has_line_of_sight_to_target

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE, STRATAGEM_PROPOSAL_PAYLOAD_KIND, DECLINE_STRATAGEM_WINDOW_OPTION_ID, DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE, UNSUPPORTED_STRATAGEM_HANDLER_PREFIX, CORE_COMMAND_REROLL_HANDLER_ID, CORE_INSANE_BRAVERY_HANDLER_ID, CORE_RAPID_INGRESS_HANDLER_ID, CORE_NEW_ORDERS_HANDLER_ID, CORE_FIRE_OVERWATCH_HANDLER_ID, CORE_GO_TO_GROUND_HANDLER_ID, CORE_EXPLOSIVES_HANDLER_ID, CORE_SMOKESCREEN_HANDLER_ID, CORE_HEROIC_INTERVENTION_HANDLER_ID, CORE_COUNTEROFFENSIVE_HANDLER_ID, CORE_CRUSHING_IMPACT_HANDLER_ID, CORE_EPIC_CHALLENGE_HANDLER_ID, GENERIC_INGRESS_MOVE_HANDLER_ID, GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID, GENERIC_RULE_IR_STRATAGEM_HANDLER_ID, COMMAND_REROLL_DICE_CONTEXT_KEY, COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY, INSANE_BRAVERY_TARGET_POLICY_ID, RAPID_INGRESS_TARGET_POLICY_ID, STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID, NEW_ORDERS_TARGET_POLICY_ID, FIRE_OVERWATCH_TARGET_POLICY_ID, GO_TO_GROUND_TARGET_POLICY_ID, SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID, EXPLOSIVES_TARGET_POLICY_ID, SMOKESCREEN_TARGET_POLICY_ID, HEROIC_INTERVENTION_TARGET_POLICY_ID, COUNTEROFFENSIVE_TARGET_POLICY_ID, CRUSHING_IMPACT_TARGET_POLICY_ID, EPIC_CHALLENGE_TARGET_POLICY_ID, SELECTED_TO_MOVE_TARGET_POLICY_ID, JUST_FELL_BACK_UNIT_TARGET_POLICY_ID, JUST_SHOT_UNIT_TARGET_POLICY_ID, ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID, EXPLOSIVES_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_MODEL_CONTEXT_KEY, EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND, HEROIC_INTERVENTION_MODE_INTO_THE_FRAY, SELECTED_TARGET_UNIT_CONTEXT_KEY, SELECTED_TO_MOVE_UNIT_CONTEXT_KEY, JUST_FELL_BACK_UNIT_CONTEXT_KEY, JUST_SHOT_UNIT_CONTEXT_KEY, HIT_TARGET_UNIT_CONTEXT_KEY, DESTROYED_TARGET_UNIT_CONTEXT_KEY, DESTROYED_ENEMY_UNIT_CONTEXT_KEY, HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND, HIT_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND, ENGAGED_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY, FALL_BACK_UNIT_CONTEXT_KEY, FALL_BACK_MODE_CONTEXT_KEY, FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND, FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY, FIRE_OVERWATCH_MAX_RANGE_INCHES, HEROIC_INTERVENTION_TARGET_RANGE_INCHES, HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES, CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT, StratagemAvailabilityKind, StratagemCategory, StratagemTargetKind, StratagemUseRecordPayload, StratagemTimingDescriptorPayload, StratagemRestrictionPolicyPayload, StratagemTargetSpecPayload, StratagemDefinitionPayload, StratagemCatalogRecordPayload, StratagemEligibilityContextPayload, StratagemTargetBindingPayload, StratagemTargetProposalPayload, StratagemTimingDescriptor, StratagemRestrictionPolicy, StratagemTargetSpec, StratagemDefinition, StratagemCatalogRecord, StratagemCatalogIndex, StratagemEligibilityContext, StratagemTargetBinding, StratagemTargetProposal, StratagemUseRequest, StratagemUseRecord
    from warhammer40k_core.engine.stratagems_requests import request_stratagem_use, request_stratagem_use_from_index, _request_stratagem_use_with_options, create_stratagem_use_decision_request, stratagem_decline_option, stratagem_decline_payload, is_stratagem_window_decline_result, stratagem_window_decline_allowed, stratagem_window_context_from_request, stratagem_window_decline_event_payload, stratagem_window_declined_for_context, stratagem_use_options, stratagem_use_options_from_index, stratagem_use_options_for_handler_from_index, hit_enemy_unit_effect_selection, engaged_enemy_unit_effect_selection, _stratagem_use_options_for_records, _effect_selections_for_binding, request_stratagem_target_proposal, create_stratagem_target_proposal_decision_request, stratagem_target_proposal_request_payload, stratagem_target_proposal_from_index
    from warhammer40k_core.engine.stratagems_apply import invalid_stratagem_use_status, apply_stratagem_decision, _apply_stratagem_use, invalid_stratagem_target_proposal_status, apply_stratagem_target_proposal, is_stratagem_placement_proposal_request, invalid_stratagem_placement_proposal_status, apply_stratagem_placement_proposal, is_heroic_intervention_charge_move_request, invalid_heroic_intervention_charge_move_status, apply_heroic_intervention_charge_move, _request_heroic_intervention_charge_move_retry
    from warhammer40k_core.engine.stratagems_selection import stratagem_availability_kind_from_token, stratagem_category_from_token, stratagem_target_kind_from_token, _stratagem_decision_option, _effect_selection_token, _stratagem_selection_from_result_payload, _require_stratagem_selection, stratagem_selection_from_decision_result, stratagem_selection_from_target_proposal_result, _record_is_available_for_context, _stratagem_unavailable_reason, _context_state_drift, _detachment_gate_allows, _effect_selection_error, _selected_command_point_cost, _selected_command_point_cost_result, _heroic_intervention_mode_error, _heroic_intervention_mode, _heroic_intervention_mode_additional_cost, _heroic_intervention_mode_costs, _required_effect_selection_fields_error, _effect_selection_string_or_none
    from warhammer40k_core.engine.stratagems_eligibility import _handler_unavailable_reason, _restriction_violation, _same_stratagem_phase, _stratagem_targeted_unit_ids, _stratagem_affected_unit_ids, _canonical_stratagem_affected_unit_id, _attached_unit_id_for_component, _unit_has_runtime_attached_role, _rules_unit_owner, _enumerated_target_bindings
    from warhammer40k_core.engine.stratagems_targeting import _target_binding_error, _target_unit_owner, _target_unit_has_keyword, _target_unit_within_controlled_objective_range, _objective_control_result_has_unit, _target_unit_satisfies_required_keywords, _target_unit_satisfies_required_keywords_any, _target_unit_satisfies_required_faction_keywords, _unit_has_keyword, _canonical_keyword, _active_tactical_secondary_cards, _battle_shock_test_unit_ids, _rapid_ingress_unit_ids, _strategic_reserves_ingress_unit_ids, _command_reroll_context_error, _command_reroll_roll_class, _command_reroll_state, _command_reroll_affected_unit_id, _command_reroll_permission, _selected_target_context_error, _selected_target_unit_ids_or_none, _selected_to_move_target_context_error, _selected_to_move_unit_id_or_none, _just_fell_back_target_context_error, _just_fell_back_unit_id_or_none, _just_shot_target_context_error, _just_shot_unit_id_or_none, _hit_target_unit_ids_or_empty, _engaged_enemy_unit_ids_or_empty, _effect_selection_required_target_keywords, _target_unit_has_all_keywords, destroyed_target_unit_ids_from_context, destroyed_enemy_unit_ids_from_context, _identifier_list_from_trigger_payload, _hit_enemy_unit_id_or_none, _engaged_enemy_unit_id_or_none, _engaged_with_fall_back_unit_target_context_error, _fall_back_unit_id_or_none, _engaged_fall_back_target_unit_ids, _fire_overwatch_target_binding_error
    from warhammer40k_core.engine.stratagems_ingress import _apply_rapid_ingress_placement, _strategic_reserve_rule_for_ingress_request, _proposal_request_marks_movement_phase_arrival, _request_rapid_ingress_placement_retry
    from warhammer40k_core.engine.stratagems_core_handlers import _stratagem_use_from_proposal_context, _apply_supported_stratagem_handler, _validate_supported_stratagem_handler_available, _validate_supported_stratagem_handler_preflight, _generic_rule_ir_from_stratagem_payload, _apply_generic_rule_ir_stratagem_handler, _apply_command_reroll_handler, is_command_reroll_decision_request, invalid_command_reroll_decision_status, apply_command_reroll_decision, _command_reroll_request_context, _apply_insane_bravery_handler, _apply_rapid_ingress_handler, _apply_ingress_move_handler, _ingress_move_effect_payload, _apply_force_desperate_escape_handler
    from warhammer40k_core.engine.stratagems_tactical_secondaries import _apply_new_orders_handler
    from warhammer40k_core.engine.stratagems_fire_overwatch import _apply_fire_overwatch_handler
    from warhammer40k_core.engine.stratagems_effect_handlers import _apply_go_to_ground_handler, _apply_smokescreen_handler, _apply_explosives_handler, apply_explosives_mortal_wound_feel_no_pain_decision, _emit_explosives_resolved, _apply_counteroffensive_handler, _apply_crushing_impact_handler, _apply_epic_challenge_handler, _apply_heroic_intervention_handler, _apply_stratagem_mortal_wounds, _heroic_intervention_reachable_target_distances, _enemy_unit_ids_for_player, _closest_unit_distance_inches, _unit_made_charge_move
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "_any_models_within_engagement_range",
    "_battlefield_scenario",
    "_battlefield_scenario_for_stratagem",
    "_counteroffensive_target_context_error",
    "_crushing_impact_context_error",
    "_crushing_impact_enemy_target_id_or_none",
    "_crushing_impact_model_id_or_none",
    "_enemy_unit_is_within_friendly_engagement_range",
    "_epic_challenge_character_model_id_or_none",
    "_epic_challenge_context_error",
    "_explosives_context_error",
    "_explosives_target_is_visible_and_in_range",
    "_explosives_target_unit_id",
    "_explosives_target_unit_id_or_none",
    "_explosives_visibility_profile",
    "_fire_overwatch_triggering_enemy_unit_id",
    "_fire_overwatch_triggering_enemy_unit_id_or_none",
    "_friendly_unit_within_enemy_range",
    "_geometry_model_for_model_id",
    "_geometry_models_for_unit",
    "_heroic_intervention_charge_move_from_result_payload",
    "_heroic_intervention_charge_move_request_error",
    "_heroic_intervention_maximum_distance",
    "_heroic_intervention_mode_from_request",
    "_heroic_intervention_request_context",
    "_heroic_intervention_requested_reachable_distances",
    "_heroic_intervention_target_binding_error",
    "_model_engaged_with_unit",
    "_model_is_alive_and_placed",
    "_model_toughness",
    "_movement_proposal_request_from_payload",
    "_placement_proposal_from_result_payload",
    "_proposal_context_error",
    "_proposal_from_request_payload",
    "_proposal_from_result_payload",
    "_proposal_request_is_rapid_ingress",
    "_reserve_placement_kinds_for_unit",
    "_reserve_proposal_kind",
    "_reserve_state_for_target",
    "_stratagem_ruleset_descriptor",
    "_stratagem_terrain_features",
    "_unit_by_id",
    "_unit_by_id_or_none",
    "_unit_for_reserve_state",
    "_unit_has_deep_strike_keyword",
    "_unit_is_within_enemy_engagement_range",
    "_unit_owner",
    "_units_are_engaged",
    "_units_are_within_range_inches",
    "visible_enemy_unit_ids_for_source",
)


def _fire_overwatch_triggering_enemy_unit_id(
    context: StratagemEligibilityContext,
) -> str:
    unit_id = _fire_overwatch_triggering_enemy_unit_id_or_none(context)
    if unit_id is None:
        raise GameLifecycleError("Fire Overwatch trigger payload requires moved unit id.")
    return unit_id


def _fire_overwatch_triggering_enemy_unit_id_or_none(
    context: StratagemEligibilityContext,
) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    unit_id = trigger_payload.get(FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY)
    if type(unit_id) is not str:
        return None
    return _validate_identifier("Fire Overwatch moved unit id", unit_id)


def _heroic_intervention_target_binding_error(
    *,
    state: GameState,
    player_id: str,
    target_binding: StratagemTargetBinding,
) -> str | None:
    target_unit_id = _require_target_unit_id(target_binding)
    target_unit = _unit_by_id(state=state, unit_instance_id=target_unit_id)
    if _unit_has_keyword(target_unit, "VEHICLE") and not (
        _unit_has_keyword(target_unit, "CHARACTER") or _unit_has_keyword(target_unit, "WALKER")
    ):
        return "heroic_intervention_vehicle_not_character_or_walker"
    if _unit_is_within_enemy_engagement_range(
        state=state,
        player_id=player_id,
        unit_instance_id=target_unit_id,
    ):
        return "heroic_intervention_unit_engaged"
    if not _friendly_unit_within_enemy_range(
        state=state,
        player_id=player_id,
        unit_instance_id=target_unit_id,
        distance_inches=HEROIC_INTERVENTION_TARGET_RANGE_INCHES,
    ):
        return "heroic_intervention_unit_not_within_12"
    return None


def _crushing_impact_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
) -> str | None:
    source_unit_id = _require_target_unit_id(target_binding)
    enemy_unit_id = _crushing_impact_enemy_target_id_or_none(effect_selection)
    if enemy_unit_id is None:
        return "missing_crushing_impact_enemy_target"
    enemy_owner = _unit_owner(state=state, unit_instance_id=enemy_unit_id)
    if enemy_owner is None:
        return "unknown_crushing_impact_enemy_target"
    if enemy_owner == context.player_id:
        return "crushing_impact_target_not_enemy"
    model_id = _crushing_impact_model_id_or_none(effect_selection)
    if model_id is None:
        return "missing_crushing_impact_model"
    if model_id not in _unit_by_id(state=state, unit_instance_id=source_unit_id).own_model_ids():
        return "crushing_impact_model_not_in_unit"
    if not _model_is_alive_and_placed(state=state, model_instance_id=model_id):
        return "crushing_impact_model_not_alive_and_placed"
    if not _units_are_engaged(
        state=state,
        first_unit_instance_id=source_unit_id,
        second_unit_instance_id=enemy_unit_id,
    ):
        return "crushing_impact_units_not_engaged"
    if not _model_engaged_with_unit(
        state=state,
        model_instance_id=model_id,
        target_unit_instance_id=enemy_unit_id,
    ):
        return "crushing_impact_model_not_engaged_with_target"
    if _model_toughness(state=state, model_instance_id=model_id) is None:
        return "crushing_impact_model_missing_toughness"
    return None


def _counteroffensive_target_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    ruleset_descriptor: RulesetDescriptor | None,
) -> str | None:
    fight_state = state.fight_phase_state
    if fight_state is None:
        return "counteroffensive_requires_fight_phase_state"
    descriptor = (
        _stratagem_ruleset_descriptor() if ruleset_descriptor is None else ruleset_descriptor
    )
    target_unit_id = _require_target_unit_id(target_binding)
    contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=context.player_id,
        policy=descriptor.fight_policy,
    )
    for fight_context in contexts:
        if fight_context.unit_instance_id != target_unit_id:
            continue
        if legal_fight_types_for_context(
            context=fight_context,
            policy=descriptor.fight_policy,
        ):
            return None
        return "counteroffensive_target_has_no_legal_fight_type"
    return "counteroffensive_target_not_eligible_to_fight"


def _epic_challenge_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
) -> str | None:
    target_unit_id = _require_target_unit_id(target_binding)
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return "missing_epic_challenge_trigger_context"
    selected_unit_id = trigger_payload.get("selected_unit_instance_id")
    if selected_unit_id != target_unit_id:
        return "epic_challenge_unit_not_selected_to_fight"
    model_id = _epic_challenge_character_model_id_or_none(effect_selection)
    if model_id is None:
        return "missing_epic_challenge_character_model"
    unit = _unit_by_id(state=state, unit_instance_id=target_unit_id)
    if model_id not in unit.own_model_ids():
        return "epic_challenge_model_not_in_unit"
    if not _unit_has_keyword(unit, "CHARACTER"):
        return "epic_challenge_unit_not_character"
    if not _model_is_alive_and_placed(state=state, model_instance_id=model_id):
        return "epic_challenge_model_not_alive_and_placed"
    return None


def _units_are_within_range_inches(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
    distance_inches: float,
) -> bool:
    first_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    if not first_models or not second_models:
        return False
    for first_model in first_models:
        for second_model in second_models:
            if first_model.range_to(second_model) <= distance_inches:
                return True
    return False


def _friendly_unit_within_enemy_range(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    distance_inches: float,
) -> bool:
    for army in state.army_definitions:
        if army.player_id == player_id:
            continue
        for unit in army.units:
            if _units_are_within_range_inches(
                state=state,
                first_unit_instance_id=unit_instance_id,
                second_unit_instance_id=unit.unit_instance_id,
                distance_inches=distance_inches,
            ):
                return True
    return False


def _units_are_engaged(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> bool:
    return _any_models_within_engagement_range(
        first_models=_geometry_models_for_unit(
            state=state,
            unit_instance_id=first_unit_instance_id,
        ),
        second_models=_geometry_models_for_unit(
            state=state,
            unit_instance_id=second_unit_instance_id,
        ),
    )


def _model_engaged_with_unit(
    *,
    state: GameState,
    model_instance_id: str,
    target_unit_instance_id: str,
) -> bool:
    model = _geometry_model_for_model_id(state=state, model_instance_id=model_instance_id)
    return _any_models_within_engagement_range(
        first_models=(model,),
        second_models=_geometry_models_for_unit(
            state=state,
            unit_instance_id=target_unit_instance_id,
        ),
    )


def _geometry_model_for_model_id(*, state: GameState, model_instance_id: str) -> Model:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem model geometry requires battlefield_state.")
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    continue
                try:
                    return geometry_model_for_placement(
                        model=model,
                        placement=battlefield_state.model_placement_by_id(model.model_instance_id),
                    )
                except PlacementError as exc:
                    raise GameLifecycleError("Stratagem model placement is invalid.") from exc
    raise GameLifecycleError("model_instance_id is unknown.")


def _model_is_alive_and_placed(*, state: GameState, model_instance_id: str) -> bool:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem model placement requires battlefield_state.")
    placed_model_ids = set(battlefield_state.placed_model_ids())
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id == requested_model_id:
                    return model.is_alive and requested_model_id in placed_model_ids
    raise GameLifecycleError("model_instance_id is unknown.")


def _model_toughness(*, state: GameState, model_instance_id: str) -> int | None:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id != requested_model_id:
                    continue
                for value in model.characteristics:
                    if value.characteristic is Characteristic.TOUGHNESS:
                        return value.final
                return None
    raise GameLifecycleError("model_instance_id is unknown.")


def _crushing_impact_enemy_target_id_or_none(
    effect_selection: JsonValue,
) -> str | None:
    return _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY,
    )


def _crushing_impact_model_id_or_none(effect_selection: JsonValue) -> str | None:
    return _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=CRUSHING_IMPACT_MODEL_CONTEXT_KEY,
    )


def _epic_challenge_character_model_id_or_none(
    effect_selection: JsonValue,
) -> str | None:
    return _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY,
    )


def _explosives_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> str | None:
    if not _target_unit_has_keyword(state=state, target_binding=target_binding, keyword="GRENADES"):
        return "unit_not_grenades"
    explosives_unit_id = _require_target_unit_id(target_binding)
    if (
        state.advanced_unit_state_for_unit(
            player_id=context.player_id,
            battle_round=context.battle_round,
            unit_instance_id=explosives_unit_id,
        )
        is not None
    ):
        return "explosives_unit_advanced"
    if (
        state.fell_back_unit_state_for_unit(
            player_id=context.player_id,
            battle_round=context.battle_round,
            unit_instance_id=explosives_unit_id,
        )
        is not None
    ):
        return "explosives_unit_fell_back"
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and explosives_unit_id in shooting_state.shot_unit_ids:
        return "explosives_unit_already_shot"
    target_unit_id = _explosives_target_unit_id_or_none(context)
    if target_unit_id is None:
        return "missing_explosives_target"
    target_owner = _unit_owner(state=state, unit_instance_id=target_unit_id)
    if target_owner is None:
        return "unknown_explosives_target"
    if target_owner == context.player_id:
        return "explosives_target_not_enemy"
    if state.battlefield_state is None:
        return "explosives_requires_battlefield"
    if state.mission_setup is None:
        return "explosives_requires_mission_setup"
    if _unit_is_within_enemy_engagement_range(
        state=state,
        player_id=context.player_id,
        unit_instance_id=explosives_unit_id,
    ):
        return "explosives_unit_in_engagement_range"
    if _enemy_unit_is_within_friendly_engagement_range(
        state=state,
        player_id=context.player_id,
        target_unit_instance_id=target_unit_id,
    ):
        return "explosives_target_engaged_with_friendly_unit"
    if not _explosives_target_is_visible_and_in_range(
        state=state,
        explosives_unit_instance_id=explosives_unit_id,
        target_unit_instance_id=target_unit_id,
    ):
        return "explosives_target_not_visible_and_within_range"
    return None


def _explosives_target_unit_id(context: StratagemEligibilityContext) -> str:
    target_unit_id = _explosives_target_unit_id_or_none(context)
    if target_unit_id is None:
        raise GameLifecycleError("Explosives trigger payload requires enemy target unit id.")
    return target_unit_id


def _explosives_target_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    target_unit_id = trigger_payload.get(EXPLOSIVES_TARGET_CONTEXT_KEY)
    if type(target_unit_id) is not str:
        return None
    return _validate_identifier("Explosives target unit id", target_unit_id)


def _explosives_target_is_visible_and_in_range(
    *,
    state: GameState,
    explosives_unit_instance_id: str,
    target_unit_instance_id: str,
) -> bool:
    scenario = _battlefield_scenario_for_stratagem(state)
    unit = _unit_by_id(state=state, unit_instance_id=explosives_unit_instance_id)
    terrain_features = _stratagem_terrain_features(state)
    profile = _explosives_visibility_profile()
    for model in unit.own_models:
        if not model.is_alive:
            continue
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=_stratagem_ruleset_descriptor(),
            attacker_unit=unit,
            attacker_model_instance_id=model.model_instance_id,
            weapon_profile=profile,
            target_unit_id=target_unit_instance_id,
            terrain_features=terrain_features,
        )
        if candidate.is_legal:
            return True
    return False


def visible_enemy_unit_ids_for_source(
    *,
    state: GameState,
    player_id: str,
    source_unit_instance_id: str,
    range_inches: int,
) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    requested_source_id = _validate_identifier("source_unit_instance_id", source_unit_instance_id)
    distance = _visible_enemy_range_inches(range_inches)
    if _unit_owner(state=state, unit_instance_id=requested_source_id) != requested_player_id:
        return ()
    candidate_ids: list[str] = []
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            continue
        for unit in army.units:
            if _visible_enemy_target_is_visible_and_in_range(
                state=state,
                source_unit_instance_id=requested_source_id,
                target_unit_instance_id=unit.unit_instance_id,
                range_inches=distance,
            ):
                candidate_ids.append(unit.unit_instance_id)
    return tuple(sorted(candidate_ids))


def _visible_enemy_target_is_visible_and_in_range(
    *,
    state: GameState,
    source_unit_instance_id: str,
    target_unit_instance_id: str,
    range_inches: int,
) -> bool:
    if not _units_are_within_range_inches(
        state=state,
        first_unit_instance_id=source_unit_instance_id,
        second_unit_instance_id=target_unit_instance_id,
        distance_inches=range_inches,
    ):
        return False
    scenario = _battlefield_scenario_for_stratagem(state)
    source_unit = _unit_by_id(state=state, unit_instance_id=source_unit_instance_id)
    return unit_has_line_of_sight_to_target(
        scenario=scenario,
        ruleset_descriptor=_stratagem_ruleset_descriptor(),
        observing_unit=source_unit,
        target_unit_id=target_unit_instance_id,
        terrain_features=_stratagem_terrain_features(state),
    )


def _visible_enemy_range_inches(range_inches: object) -> int:
    if type(range_inches) is not int:
        raise GameLifecycleError("Visible enemy range must be an int.")
    if range_inches <= 0:
        raise GameLifecycleError("Visible enemy range must be greater than zero.")
    return range_inches


def _unit_is_within_enemy_engagement_range(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
) -> bool:
    unit_models = _geometry_models_for_unit(state=state, unit_instance_id=unit_instance_id)
    for army in state.army_definitions:
        if army.player_id == player_id:
            continue
        for unit in army.units:
            if _any_models_within_engagement_range(
                first_models=unit_models,
                second_models=_geometry_models_for_unit(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                ),
            ):
                return True
    return False


def _enemy_unit_is_within_friendly_engagement_range(
    *,
    state: GameState,
    player_id: str,
    target_unit_instance_id: str,
) -> bool:
    target_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    for army in state.army_definitions:
        if army.player_id != player_id:
            continue
        for unit in army.units:
            if _any_models_within_engagement_range(
                first_models=_geometry_models_for_unit(
                    state=state,
                    unit_instance_id=unit.unit_instance_id,
                ),
                second_models=target_models,
            ):
                return True
    return False


def _any_models_within_engagement_range(
    *,
    first_models: tuple[Model, ...],
    second_models: tuple[Model, ...],
) -> bool:
    policy = _stratagem_ruleset_descriptor().engagement_policy
    for first_model in first_models:
        for second_model in second_models:
            if first_model.is_within_engagement_range(
                second_model,
                horizontal_inches=policy.horizontal_inches,
                vertical_inches=policy.vertical_inches,
            ):
                return True
    return False


def _geometry_models_for_unit(
    *,
    state: GameState,
    unit_instance_id: str,
) -> tuple[Model, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem geometry requires battlefield_state.")
    unit = _unit_by_id(state=state, unit_instance_id=unit_instance_id)
    try:
        models = tuple(
            geometry_model_for_placement(
                model=model,
                placement=battlefield_state.model_placement_by_id(model.model_instance_id),
            )
            for model in unit.own_models
            if model.is_alive
        )
    except PlacementError as exc:
        raise GameLifecycleError("Stratagem geometry placement is invalid.") from exc
    return models


def _battlefield_scenario_for_stratagem(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem battlefield scenario requires battlefield_state.")
    try:
        return BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Stratagem battlefield scenario is invalid.") from exc


def _stratagem_terrain_features(state: GameState) -> tuple[TerrainFeatureDefinition, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem terrain requires battlefield_state.")
    return battlefield_state.terrain_features


def _stratagem_ruleset_descriptor() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh()


def _explosives_visibility_profile() -> WeaponProfile:
    return WeaponProfile(
        profile_id="core-stratagem:explosives:visibility-range",
        name="Explosives Stratagem Visibility Range",
        range_profile=RangeProfile.distance(8),
        attack_profile=AttackProfile.fixed(1),
        skill=CharacteristicValue.from_raw(Characteristic.BALLISTIC_SKILL, 4),
        strength=CharacteristicValue.from_raw(Characteristic.STRENGTH, 1),
        armor_penetration=CharacteristicValue.from_raw(Characteristic.ARMOR_PENETRATION, 0),
        damage_profile=DamageProfile.fixed(1),
    )


def _unit_owner(*, state: GameState, unit_instance_id: str) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return army.player_id
    return None


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    raise GameLifecycleError("unit_instance_id is unknown.")


def _unit_by_id_or_none(*, state: GameState, unit_instance_id: str) -> UnitInstance | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_unit_id:
                return unit
    return None


def _reserve_state_for_target(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
) -> ReserveState:
    reserve_state = state.reserve_state_for_unit(_require_target_unit_id(target_binding))
    if reserve_state is None:
        raise GameLifecycleError("Stratagem reserve target requires ReserveState.")
    if reserve_state.status is not ReserveStatus.IN_RESERVES:
        raise GameLifecycleError("Stratagem reserve target must be unarrived.")
    return reserve_state


def _unit_for_reserve_state(*, state: GameState, reserve_state: ReserveState) -> UnitInstance:
    army = state.army_definition_for_player(reserve_state.player_id)
    if army is None:
        raise GameLifecycleError("ReserveState player has no army definition.")
    for unit in army.units:
        if unit.unit_instance_id == reserve_state.unit_instance_id:
            return unit
    raise GameLifecycleError("ReserveState references an unknown unit.")


def _reserve_placement_kinds_for_unit(
    *,
    reserve_state: ReserveState,
    unit: UnitInstance,
) -> tuple[BattlefieldPlacementKind, ...]:
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        kinds = [BattlefieldPlacementKind.STRATEGIC_RESERVES]
        if _unit_has_deep_strike_keyword(unit):
            kinds.append(BattlefieldPlacementKind.DEEP_STRIKE)
        return tuple(kinds)
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return (BattlefieldPlacementKind.DEEP_STRIKE,)
    return (BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD,)


def _reserve_proposal_kind(reserve_state: ReserveState) -> ProposalKind:
    if reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE:
        return ProposalKind.DEEP_STRIKE
    if reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES:
        return ProposalKind.STRATEGIC_RESERVES
    return ProposalKind.REINFORCEMENT


def _unit_has_deep_strike_keyword(unit: UnitInstance) -> bool:
    return unit_has_deep_strike(unit)


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Stratagem placement requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield_state,
    )


def _proposal_from_request_payload(payload: JsonValue) -> StratagemTargetProposal | None:
    if not isinstance(payload, dict):
        return None
    proposal_payload = payload.get("proposal_request")
    if not isinstance(proposal_payload, dict):
        return None
    try:
        proposal = StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, proposal_payload)
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None
    if proposal.target_binding is not None:
        return None
    return proposal


def _proposal_from_result_payload(payload: JsonValue) -> StratagemTargetProposal | None:
    if not isinstance(payload, dict):
        return None
    proposal_payload = payload.get("proposal")
    if not isinstance(proposal_payload, dict):
        return None
    try:
        return StratagemTargetProposal.from_payload(
            cast(StratagemTargetProposalPayload, proposal_payload)
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _proposal_context_error(
    *,
    state: GameState,
    request_proposal: StratagemTargetProposal,
    submitted_proposal: StratagemTargetProposal,
) -> str | None:
    if submitted_proposal.proposal_kind != request_proposal.proposal_kind:
        return "wrong_context"
    if submitted_proposal.game_id != request_proposal.game_id:
        return "wrong_context"
    if submitted_proposal.player_id != request_proposal.player_id:
        return "wrong_context"
    if submitted_proposal.stratagem_id != request_proposal.stratagem_id:
        return "wrong_context"
    if submitted_proposal.catalog_record != request_proposal.catalog_record:
        return "wrong_context"
    if submitted_proposal.battle_round != request_proposal.battle_round:
        return "stale_battle_round"
    if submitted_proposal.phase is not request_proposal.phase:
        return "stale_phase"
    return _context_state_drift(state=state, context=request_proposal.context)


def _movement_proposal_request_from_payload(payload: JsonValue) -> MovementProposalRequest | None:
    try:
        return MovementProposalRequest.from_decision_request_payload(payload)
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _heroic_intervention_charge_move_from_result_payload(
    payload: JsonValue,
) -> ChargeMoveProposal | None:
    if not isinstance(payload, dict):
        return None
    try:
        return ChargeMoveProposal.from_payload(cast(ChargeMoveProposalPayload, payload))
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _heroic_intervention_charge_move_request_error(
    *,
    state: GameState,
    proposal_request: MovementProposalRequest,
    proposal: ChargeMoveProposal,
) -> str | None:
    use_record = _stratagem_use_from_proposal_context(proposal_request)
    if use_record.player_id != proposal_request.actor_id:
        return "heroic_intervention_actor_drift"
    if use_record.stratagem_id != "heroic-intervention":
        return "heroic_intervention_use_drift"
    maximum_distance = _heroic_intervention_maximum_distance(proposal_request)
    mode = _heroic_intervention_mode_from_request(proposal_request)
    current_reachable = _heroic_intervention_reachable_target_distances(
        state=state,
        player_id=use_record.player_id,
        heroic_unit_id=proposal.unit_instance_id,
        mode=mode,
        maximum_distance_inches=maximum_distance,
    )
    requested_reachable = _heroic_intervention_requested_reachable_distances(proposal_request)
    if current_reachable != requested_reachable:
        return "heroic_intervention_reachable_targets_drift"
    if proposal.is_no_move_choice:
        return None
    if proposal.witness is None:
        return "heroic_intervention_witness_required"
    if not set(proposal.charge_target_unit_instance_ids).issubset(set(current_reachable)):
        return "heroic_intervention_target_not_reachable"
    return None


def _heroic_intervention_maximum_distance(proposal_request: MovementProposalRequest) -> int:
    context = _heroic_intervention_request_context(proposal_request)
    value = context.get("maximum_distance_inches")
    if type(value) is not int:
        raise GameLifecycleError("Heroic Intervention request requires maximum distance.")
    if value < 2 or value > 12:
        raise GameLifecycleError("Heroic Intervention maximum distance is invalid.")
    return value


def _heroic_intervention_mode_from_request(proposal_request: MovementProposalRequest) -> str:
    context = _heroic_intervention_request_context(proposal_request)
    value = context.get("mode")
    if type(value) is not str:
        raise GameLifecycleError("Heroic Intervention request requires mode.")
    return _validate_identifier("Heroic Intervention mode", value)


def _heroic_intervention_requested_reachable_distances(
    proposal_request: MovementProposalRequest,
) -> dict[str, float]:
    context = _heroic_intervention_request_context(proposal_request)
    value = context.get("reachable_target_distances_inches")
    if not isinstance(value, dict):
        raise GameLifecycleError("Heroic Intervention request requires reachable target map.")
    distances: dict[str, float] = {}
    for unit_id, distance in value.items():
        if type(unit_id) is not str:
            raise GameLifecycleError("Heroic Intervention reachable target map is malformed.")
        if type(distance) is int:
            distance_value = float(distance)
        elif type(distance) is float:
            distance_value = distance
        else:
            raise GameLifecycleError("Heroic Intervention reachable target map is malformed.")
        distances[_validate_identifier("Heroic Intervention target id", unit_id)] = float(
            distance_value
        )
    return dict(sorted(distances.items()))


def _heroic_intervention_request_context(
    proposal_request: MovementProposalRequest,
) -> dict[str, JsonValue]:
    context = proposal_request.context
    if context is None:
        raise GameLifecycleError("Heroic Intervention request requires context.")
    return context


def _placement_proposal_from_result_payload(payload: JsonValue) -> PlacementProposalPayload | None:
    if not isinstance(payload, dict):
        return None
    try:
        return PlacementProposalPayload.from_payload(cast(PlacementProposalPayloadPayload, payload))
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _proposal_request_is_rapid_ingress(proposal_request: MovementProposalRequest) -> bool:
    context = proposal_request.context or {}
    handler = context.get("stratagem_handler_id")
    return handler in {
        CORE_RAPID_INGRESS_HANDLER_ID,
        GENERIC_INGRESS_MOVE_HANDLER_ID,
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    }
