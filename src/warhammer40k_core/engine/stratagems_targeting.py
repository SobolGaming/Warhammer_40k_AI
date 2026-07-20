# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.selected_target_context import selected_target_unit_ids_or_none
from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_model import *
from warhammer40k_core.engine.stratagems_requests import *
from warhammer40k_core.engine.stratagems_apply import *
from warhammer40k_core.engine.stratagems_selection import *
from warhammer40k_core.engine.stratagems_eligibility import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE, STRATAGEM_PROPOSAL_PAYLOAD_KIND, DECLINE_STRATAGEM_WINDOW_OPTION_ID, DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE, UNSUPPORTED_STRATAGEM_HANDLER_PREFIX, CORE_COMMAND_REROLL_HANDLER_ID, CORE_INSANE_BRAVERY_HANDLER_ID, CORE_RAPID_INGRESS_HANDLER_ID, CORE_NEW_ORDERS_HANDLER_ID, CORE_FIRE_OVERWATCH_HANDLER_ID, CORE_GO_TO_GROUND_HANDLER_ID, CORE_EXPLOSIVES_HANDLER_ID, CORE_SMOKESCREEN_HANDLER_ID, CORE_HEROIC_INTERVENTION_HANDLER_ID, CORE_COUNTEROFFENSIVE_HANDLER_ID, CORE_CRUSHING_IMPACT_HANDLER_ID, CORE_EPIC_CHALLENGE_HANDLER_ID, GENERIC_INGRESS_MOVE_HANDLER_ID, GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID, GENERIC_RULE_IR_STRATAGEM_HANDLER_ID, COMMAND_REROLL_DICE_CONTEXT_KEY, COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY, INSANE_BRAVERY_TARGET_POLICY_ID, RAPID_INGRESS_TARGET_POLICY_ID, STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID, NEW_ORDERS_TARGET_POLICY_ID, FIRE_OVERWATCH_TARGET_POLICY_ID, GO_TO_GROUND_TARGET_POLICY_ID, SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID, EXPLOSIVES_TARGET_POLICY_ID, SMOKESCREEN_TARGET_POLICY_ID, HEROIC_INTERVENTION_TARGET_POLICY_ID, COUNTEROFFENSIVE_TARGET_POLICY_ID, CRUSHING_IMPACT_TARGET_POLICY_ID, EPIC_CHALLENGE_TARGET_POLICY_ID, SELECTED_TO_MOVE_TARGET_POLICY_ID, JUST_FELL_BACK_UNIT_TARGET_POLICY_ID, JUST_SHOT_UNIT_TARGET_POLICY_ID, ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID, EXPLOSIVES_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_MODEL_CONTEXT_KEY, EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND, HEROIC_INTERVENTION_MODE_INTO_THE_FRAY, SELECTED_TARGET_UNIT_CONTEXT_KEY, SELECTED_TO_MOVE_UNIT_CONTEXT_KEY, JUST_FELL_BACK_UNIT_CONTEXT_KEY, JUST_SHOT_UNIT_CONTEXT_KEY, HIT_TARGET_UNIT_CONTEXT_KEY, DESTROYED_TARGET_UNIT_CONTEXT_KEY, DESTROYED_ENEMY_UNIT_CONTEXT_KEY, HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND, HIT_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND, ENGAGED_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY, FALL_BACK_UNIT_CONTEXT_KEY, FALL_BACK_MODE_CONTEXT_KEY, FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND, FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY, FIRE_OVERWATCH_MAX_RANGE_INCHES, HEROIC_INTERVENTION_TARGET_RANGE_INCHES, HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES, CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT, StratagemAvailabilityKind, StratagemCategory, StratagemTargetKind, StratagemUseRecordPayload, StratagemTimingDescriptorPayload, StratagemRestrictionPolicyPayload, StratagemTargetSpecPayload, StratagemDefinitionPayload, StratagemCatalogRecordPayload, StratagemEligibilityContextPayload, StratagemTargetBindingPayload, StratagemTargetProposalPayload, StratagemTimingDescriptor, StratagemRestrictionPolicy, StratagemTargetSpec, StratagemDefinition, StratagemCatalogRecord, StratagemCatalogIndex, StratagemEligibilityContext, StratagemTargetBinding, StratagemTargetProposal, StratagemUseRequest, StratagemUseRecord
    from warhammer40k_core.engine.stratagems_requests import request_stratagem_use, request_stratagem_use_from_index, _request_stratagem_use_with_options, create_stratagem_use_decision_request, stratagem_decline_option, stratagem_decline_payload, is_stratagem_window_decline_result, stratagem_window_decline_allowed, stratagem_window_context_from_request, stratagem_window_decline_event_payload, stratagem_window_declined_for_context, stratagem_use_options, stratagem_use_options_from_index, stratagem_use_options_for_handler_from_index, hit_enemy_unit_effect_selection, engaged_enemy_unit_effect_selection, _stratagem_use_options_for_records, _effect_selections_for_binding, request_stratagem_target_proposal, create_stratagem_target_proposal_decision_request, stratagem_target_proposal_request_payload, stratagem_target_proposal_from_index
    from warhammer40k_core.engine.stratagems_apply import invalid_stratagem_use_status, apply_stratagem_decision, _apply_stratagem_use, invalid_stratagem_target_proposal_status, apply_stratagem_target_proposal, is_stratagem_placement_proposal_request, invalid_stratagem_placement_proposal_status, apply_stratagem_placement_proposal, is_heroic_intervention_charge_move_request, invalid_heroic_intervention_charge_move_status, apply_heroic_intervention_charge_move, _request_heroic_intervention_charge_move_retry
    from warhammer40k_core.engine.stratagems_selection import stratagem_availability_kind_from_token, stratagem_category_from_token, stratagem_target_kind_from_token, _stratagem_decision_option, _effect_selection_token, _stratagem_selection_from_result_payload, _require_stratagem_selection, stratagem_selection_from_decision_result, stratagem_selection_from_target_proposal_result, _record_is_available_for_context, _stratagem_unavailable_reason, _context_state_drift, _detachment_gate_allows, _effect_selection_error, _selected_command_point_cost, _selected_command_point_cost_result, _heroic_intervention_mode_error, _heroic_intervention_mode, _heroic_intervention_mode_additional_cost, _heroic_intervention_mode_costs, _required_effect_selection_fields_error, _effect_selection_string_or_none
    from warhammer40k_core.engine.stratagems_eligibility import _handler_unavailable_reason, _restriction_violation, _same_stratagem_phase, _stratagem_targeted_unit_ids, _stratagem_affected_unit_ids, _canonical_stratagem_affected_unit_id, _attached_unit_id_for_component, _unit_has_runtime_attached_role, _rules_unit_owner, _enumerated_target_bindings
    from warhammer40k_core.engine.stratagems_geometry import _fire_overwatch_triggering_enemy_unit_id, _fire_overwatch_triggering_enemy_unit_id_or_none, _heroic_intervention_target_binding_error, _crushing_impact_context_error, _counteroffensive_target_context_error, _epic_challenge_context_error, _units_are_within_range_inches, _friendly_unit_within_enemy_range, _units_are_engaged, _model_engaged_with_unit, _geometry_model_for_model_id, _model_is_alive_and_placed, _model_toughness, _crushing_impact_enemy_target_id_or_none, _crushing_impact_model_id_or_none, _epic_challenge_character_model_id_or_none, _explosives_context_error, _explosives_target_unit_id, _explosives_target_unit_id_or_none, _explosives_target_is_visible_and_in_range, _unit_is_within_enemy_engagement_range, _enemy_unit_is_within_friendly_engagement_range, _any_models_within_engagement_range, _geometry_models_for_unit, _battlefield_scenario_for_stratagem, _stratagem_terrain_features, _stratagem_ruleset_descriptor, _explosives_visibility_profile, _unit_owner, _unit_by_id, _unit_by_id_or_none, _reserve_state_for_target, _unit_for_reserve_state, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _unit_has_deep_strike_keyword, _battlefield_scenario, _proposal_from_request_payload, _proposal_from_result_payload, _proposal_context_error, _movement_proposal_request_from_payload, _heroic_intervention_charge_move_from_result_payload, _heroic_intervention_charge_move_request_error, _heroic_intervention_maximum_distance, _heroic_intervention_mode_from_request, _heroic_intervention_requested_reachable_distances, _heroic_intervention_request_context, _placement_proposal_from_result_payload, _proposal_request_is_rapid_ingress
    from warhammer40k_core.engine.stratagems_ingress import _apply_rapid_ingress_placement, _strategic_reserve_rule_for_ingress_request, _proposal_request_marks_movement_phase_arrival, _request_rapid_ingress_placement_retry
    from warhammer40k_core.engine.stratagems_core_handlers import _stratagem_use_from_proposal_context, _apply_supported_stratagem_handler, _validate_supported_stratagem_handler_available, _validate_supported_stratagem_handler_preflight, _generic_rule_ir_from_stratagem_payload, _apply_generic_rule_ir_stratagem_handler, _apply_command_reroll_handler, is_command_reroll_decision_request, invalid_command_reroll_decision_status, apply_command_reroll_decision, _command_reroll_request_context, _apply_insane_bravery_handler, _apply_rapid_ingress_handler, _apply_ingress_move_handler, _ingress_move_effect_payload, _apply_force_desperate_escape_handler
    from warhammer40k_core.engine.stratagems_tactical_secondaries import _apply_new_orders_handler
    from warhammer40k_core.engine.stratagems_fire_overwatch import _apply_fire_overwatch_handler
    from warhammer40k_core.engine.stratagems_effect_handlers import _apply_go_to_ground_handler, _apply_smokescreen_handler, _apply_explosives_handler, apply_explosives_mortal_wound_feel_no_pain_decision, _emit_explosives_resolved, _apply_counteroffensive_handler, _apply_crushing_impact_handler, _apply_epic_challenge_handler, _apply_heroic_intervention_handler, _apply_stratagem_mortal_wounds, _heroic_intervention_reachable_target_distances, _enemy_unit_ids_for_player, _closest_unit_distance_inches, _unit_made_charge_move
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "_active_tactical_secondary_cards",
    "_battle_shock_test_unit_ids",
    "_canonical_keyword",
    "_command_reroll_affected_unit_id",
    "_command_reroll_context_error",
    "_command_reroll_permission",
    "_command_reroll_roll_class",
    "_command_reroll_state",
    "_controlled_objective_marker_ids_for_target",
    "_deep_strike_arriving_unit_ids",
    "_destroyed_target_by_just_shot_unit_target_context_error",
    "_effect_selection_required_target_keywords",
    "_engaged_enemy_unit_id_or_none",
    "_engaged_enemy_unit_ids_or_empty",
    "_engaged_fall_back_target_unit_ids",
    "_engaged_with_fall_back_unit_target_context_error",
    "_fall_back_unit_id_or_none",
    "_fire_overwatch_target_binding_error",
    "_hit_enemy_unit_id_or_none",
    "_hit_target_unit_ids_or_empty",
    "_identifier_list_from_trigger_payload",
    "_just_fell_back_target_context_error",
    "_just_fell_back_unit_id_or_none",
    "_just_shot_target_context_error",
    "_just_shot_unit_id_or_none",
    "_objective_control_result_has_unit",
    "_rapid_ingress_unit_ids",
    "_selected_target_context_error",
    "_selected_target_unit_ids_or_none",
    "_selected_to_fight_target_context_error",
    "_selected_to_fight_unit_id_or_none",
    "_selected_to_move_target_context_error",
    "_selected_to_move_unit_id_or_none",
    "_selected_to_shoot_target_context_error",
    "_selected_to_shoot_unit_id_or_none",
    "_strategic_reserves_ingress_unit_ids",
    "_target_binding_error",
    "_target_unit_has_all_keywords",
    "_target_unit_has_keyword",
    "_target_unit_owner",
    "_target_unit_satisfies_required_faction_keywords",
    "_target_unit_satisfies_required_keywords",
    "_target_unit_satisfies_required_keywords_any",
    "_target_unit_within_controlled_objective_range",
    "_unit_has_keyword",
    "_visible_enemy_unit_id_or_none",
    "destroyed_enemy_unit_ids_from_context",
    "destroyed_target_unit_ids_from_context",
)


def _target_binding_error(
    *,
    state: GameState,
    player_id: str,
    target_spec: StratagemTargetSpec,
    policy: StratagemRestrictionPolicy,
    target_binding: StratagemTargetBinding,
    context: StratagemEligibilityContext | None,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> str | None:
    if target_spec.target_kind is StratagemTargetKind.NONE:
        if target_binding.target_kind is not StratagemTargetKind.NONE:
            return "target_not_allowed"
        return None
    if target_binding.target_kind is StratagemTargetKind.NONE:
        return "target_required"
    if target_spec.target_policy_id.startswith("unsupported:"):
        return "unsupported_target_policy"
    if target_spec.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        if target_binding.target_kind is not StratagemTargetKind.TACTICAL_SECONDARY_CARD:
            return "target_kind_mismatch"
        if target_binding.target_player_id != player_id:
            return "target_not_controlled_by_player"
        if _target_secondary_mission_id(target_binding) not in {
            card.secondary_mission_id
            for card in _active_tactical_secondary_cards(state=state, player_id=player_id)
        }:
            return "tactical_secondary_card_not_active"
        if target_spec.target_policy_id != NEW_ORDERS_TARGET_POLICY_ID:
            return "unsupported_target_policy"
        return None
    if target_binding.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        return "target_kind_mismatch"
    if (
        target_spec.target_kind is StratagemTargetKind.FRIENDLY_UNIT
        and target_binding.target_player_id != player_id
    ):
        return "target_not_friendly"
    target_owner = _target_unit_owner(state=state, target_binding=target_binding)
    if target_owner is None:
        return "unknown_target_unit"
    if target_owner != target_binding.target_player_id:
        return "target_owner_drift"
    if (
        target_spec.target_policy_id == EXPLOSIVES_TARGET_POLICY_ID
        and _target_unit_has_forbidden_stratagem_handler_effect(
            state=state,
            target_unit_instance_id=_require_target_unit_id(target_binding),
            handler_id=CORE_EXPLOSIVES_HANDLER_ID,
        )
    ):
        return "stratagem_target_forbidden_by_effect"
    permission = friendly_stratagem_target_permission(
        player_id=player_id,
        target_player_id=target_owner,
        target_unit_instance_id=_require_target_unit_id(target_binding),
        battle_shocked_unit_ids=tuple(state.battle_shocked_unit_ids),
        allow_battle_shocked=policy.allow_battle_shocked_targets,
    )
    if not permission.is_allowed:
        if permission.denial_reason is None:
            raise GameLifecycleError("Denied stratagem target permission must explain denial.")
        return permission.denial_reason
    if not _target_unit_satisfies_required_keywords(
        state=state,
        target_binding=target_binding,
        required_keywords=target_spec.required_keywords,
    ):
        return "unit_missing_required_keyword"
    if not _target_unit_satisfies_required_keywords_any(
        state=state,
        target_binding=target_binding,
        required_keywords_any=target_spec.required_keywords_any,
    ):
        return "unit_missing_required_keyword"
    if not _target_unit_satisfies_required_faction_keywords(
        state=state,
        target_binding=target_binding,
        required_faction_keywords=target_spec.required_faction_keywords,
    ):
        return "unit_missing_required_faction_keyword"
    if _target_unit_has_excluded_keywords(
        state=state,
        target_binding=target_binding,
        excluded_keywords=target_spec.excluded_keywords,
    ):
        return "unit_has_excluded_keyword"
    if _target_unit_has_excluded_faction_keywords(
        state=state,
        target_binding=target_binding,
        excluded_faction_keywords=target_spec.excluded_faction_keywords,
    ):
        return "unit_has_excluded_faction_keyword"
    if target_spec.target_policy_id == ENEMY_UNIT_TARGET_POLICY_ID:
        if target_owner == player_id:
            return "target_not_enemy"
        return None
    if target_spec.target_policy_id == SELECTED_TARGET_UNIT_TARGET_POLICY_ID:
        if context is None:
            return None
        return _selected_target_context_error(
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == SELECTED_TO_SHOOT_TARGET_POLICY_ID:
        if context is None:
            return None
        return _selected_to_shoot_target_context_error(
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id in {
        SELECTED_TO_FIGHT_TARGET_POLICY_ID,
        SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID,
    }:
        if context is None:
            return None
        return _selected_to_fight_target_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
            requires_charge_move=(
                target_spec.target_policy_id == SELECTED_TO_FIGHT_CHARGED_TARGET_POLICY_ID
            ),
        )
    if target_spec.target_policy_id == NOT_SELECTED_TO_SHOOT_TARGET_POLICY_ID:
        return _not_selected_to_shoot_target_error(
            state=state,
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == NOT_SELECTED_TO_FIGHT_TARGET_POLICY_ID:
        return _not_selected_to_fight_target_error(
            state=state,
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == INSANE_BRAVERY_TARGET_POLICY_ID:
        if _require_target_unit_id(target_binding) not in _battle_shock_test_unit_ids(
            state=state,
            player_id=player_id,
        ):
            return "unit_not_pending_battle_shock_test"
        return None
    if target_spec.target_policy_id == RAPID_INGRESS_TARGET_POLICY_ID:
        if _require_target_unit_id(target_binding) not in _rapid_ingress_unit_ids(
            state=state,
            player_id=player_id,
        ):
            return "unit_not_eligible_for_rapid_ingress"
        return None
    if target_spec.target_policy_id == STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID:
        if _require_target_unit_id(target_binding) not in _strategic_reserves_ingress_unit_ids(
            state=state,
            player_id=player_id,
        ):
            return "unit_not_eligible_for_strategic_reserves_ingress"
        return None
    if target_spec.target_policy_id == DEEP_STRIKE_ARRIVING_TARGET_POLICY_ID:
        if _require_target_unit_id(target_binding) not in _deep_strike_arriving_unit_ids(
            state=state,
            player_id=player_id,
        ):
            return "unit_not_eligible_for_deep_strike_arrival"
        return None
    if target_spec.target_policy_id == CONTROLLED_OBJECTIVE_UNIT_TARGET_POLICY_ID:
        if not _target_unit_within_controlled_objective_range(
            state=state,
            player_id=player_id,
            context=context,
            target_binding=target_binding,
            ruleset_descriptor=ruleset_descriptor,
        ):
            return "unit_not_within_controlled_objective_range"
        return None
    if target_spec.target_policy_id == GO_TO_GROUND_TARGET_POLICY_ID:
        if context is not None:
            selected_context_error = _selected_target_context_error(
                context=context,
                target_binding=target_binding,
            )
            if selected_context_error is not None:
                return selected_context_error
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="INFANTRY",
        ):
            return "unit_not_infantry"
        return None
    if (
        target_spec.target_policy_id
        == SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID
    ):
        if context is not None:
            selected_context_error = _selected_target_context_error(
                context=context,
                target_binding=target_binding,
            )
            if selected_context_error is not None:
                return selected_context_error
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="INFANTRY",
        ):
            return "unit_not_infantry"
        if not _target_unit_within_controlled_objective_range(
            state=state,
            player_id=player_id,
            context=context,
            target_binding=target_binding,
            ruleset_descriptor=ruleset_descriptor,
        ):
            return "unit_not_within_controlled_objective"
        return None
    if target_spec.target_policy_id == SMOKESCREEN_TARGET_POLICY_ID:
        if context is not None:
            selected_context_error = _selected_target_context_error(
                context=context,
                target_binding=target_binding,
            )
            if selected_context_error is not None:
                return selected_context_error
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="SMOKE",
        ):
            return "unit_not_smoke"
        return None
    if target_spec.target_policy_id == EXPLOSIVES_TARGET_POLICY_ID:
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="GRENADES",
        ):
            return "unit_not_grenades"
        return None
    if target_spec.target_policy_id == FIRE_OVERWATCH_TARGET_POLICY_ID:
        if context is None:
            return None
        return _fire_overwatch_target_binding_error(
            state=state,
            player_id=player_id,
            context=context,
            target_binding=target_binding,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
    if target_spec.target_policy_id == HEROIC_INTERVENTION_TARGET_POLICY_ID:
        if context is None:
            return None
        return _heroic_intervention_target_binding_error(
            state=state,
            player_id=player_id,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == COUNTEROFFENSIVE_TARGET_POLICY_ID:
        return None
    if target_spec.target_policy_id == CRUSHING_IMPACT_TARGET_POLICY_ID:
        if not (
            _target_unit_has_keyword(state=state, target_binding=target_binding, keyword="MONSTER")
            or _target_unit_has_keyword(
                state=state,
                target_binding=target_binding,
                keyword="VEHICLE",
            )
        ):
            return "unit_not_monster_or_vehicle"
        return None
    if target_spec.target_policy_id == EPIC_CHALLENGE_TARGET_POLICY_ID:
        if not _target_unit_has_keyword(
            state=state,
            target_binding=target_binding,
            keyword="CHARACTER",
        ):
            return "unit_not_character"
        return None
    if target_spec.target_policy_id == SELECTED_TO_MOVE_TARGET_POLICY_ID:
        if context is None:
            return None
        return _selected_to_move_target_context_error(
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == JUST_SHOT_UNIT_TARGET_POLICY_ID:
        if context is None:
            return None
        return _just_shot_target_context_error(
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == DESTROYED_TARGET_BY_JUST_SHOT_UNIT_TARGET_POLICY_ID:
        if context is None:
            return None
        return _destroyed_target_by_just_shot_unit_target_context_error(
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == JUST_FELL_BACK_UNIT_TARGET_POLICY_ID:
        if context is None:
            return None
        return _just_fell_back_target_context_error(
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id == ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID:
        if context is None:
            return None
        return _engaged_with_fall_back_unit_target_context_error(
            state=state,
            player_id=player_id,
            context=context,
            target_binding=target_binding,
        )
    if target_spec.target_policy_id not in {"friendly_unit", "any_unit"}:
        return "unsupported_target_policy"
    return None


def _target_unit_owner(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
) -> str | None:
    target_unit_id = target_binding.target_unit_instance_id
    if target_unit_id is None:
        return None
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == target_unit_id:
                return army.player_id
    return None


def _target_unit_has_keyword(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    keyword: str,
) -> bool:
    target_unit_id = _require_target_unit_id(target_binding)
    canonical = _canonical_keyword(keyword)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id != target_unit_id:
                continue
            return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}
    raise GameLifecycleError("Stratagem target unit is unknown.")


def _target_unit_within_controlled_objective_range(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext | None,
    target_binding: StratagemTargetBinding,
    ruleset_descriptor: RulesetDescriptor | None,
) -> bool:
    return bool(
        _controlled_objective_marker_ids_for_target(
            state=state,
            player_id=player_id,
            context=context,
            target_binding=target_binding,
            ruleset_descriptor=ruleset_descriptor,
        )
    )


def _controlled_objective_marker_ids_for_target(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext | None,
    target_binding: StratagemTargetBinding,
    ruleset_descriptor: RulesetDescriptor | None,
) -> tuple[str, ...]:
    if state.mission_setup is None or state.battlefield_state is None:
        return ()
    if state.active_player_id is None:
        return ()
    target_unit_id = _require_target_unit_id(target_binding)
    record = resolve_objective_control(
        ObjectiveControlContext.from_game_state(
            state,
            timing=ObjectiveControlTiming.PHASE_END,
            phase=BattlePhase.SHOOTING if context is None else context.phase,
            ruleset_descriptor=ruleset_descriptor,
        )
    )
    from warhammer40k_core.engine.sticky_objective_control import apply_sticky_objective_control

    record = apply_sticky_objective_control(
        record=record,
        states=tuple(state.sticky_objective_control_states),
    )
    return tuple(
        sorted(
            result.objective_id
            for result in record.results
            if result.controlled_by_player_id == player_id
            and _objective_control_result_has_unit(
                result=result,
                unit_instance_id=target_unit_id,
            )
        )
    )


def _objective_control_result_has_unit(
    *,
    result: ObjectiveControlResult,
    unit_instance_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    return any(
        contribution.unit_instance_id == requested_unit_id for contribution in result.contributors
    )


def _target_unit_satisfies_required_keywords(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    required_keywords: tuple[str, ...],
) -> bool:
    required = {_canonical_keyword(keyword) for keyword in required_keywords}
    if not required:
        return True
    target_unit_id = _require_target_unit_id(target_binding)
    unit = _unit_by_id_or_none(state=state, unit_instance_id=target_unit_id)
    if unit is None:
        raise GameLifecycleError("Stratagem target unit is unknown.")
    stored = {_canonical_keyword(keyword) for keyword in unit.keywords}
    return required.issubset(stored)


def _target_unit_has_forbidden_stratagem_handler_effect(
    *,
    state: GameState,
    target_unit_instance_id: str,
    handler_id: str,
) -> bool:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    requested_handler_id = _validate_identifier("handler_id", handler_id)
    for effect in state.persisting_effects_for_unit(target_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        raw_handler_ids = payload.get("forbidden_stratagem_handler_ids")
        if raw_handler_ids is None:
            continue
        if not isinstance(raw_handler_ids, list) or not all(
            type(value) is str for value in raw_handler_ids
        ):
            raise GameLifecycleError(
                "Stratagem target restriction handler IDs must be a string list."
            )
        if requested_handler_id in cast(list[str], raw_handler_ids):
            return True
    return False


def _target_unit_satisfies_required_keywords_any(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    required_keywords_any: tuple[str, ...],
) -> bool:
    required = {_canonical_keyword(keyword) for keyword in required_keywords_any}
    if not required:
        return True
    target_unit_id = _require_target_unit_id(target_binding)
    unit = _unit_by_id_or_none(state=state, unit_instance_id=target_unit_id)
    if unit is None:
        raise GameLifecycleError("Stratagem target unit is unknown.")
    stored = {_canonical_keyword(keyword) for keyword in unit.keywords}
    return bool(required & stored)


def _target_unit_satisfies_required_faction_keywords(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    required_faction_keywords: tuple[str, ...],
) -> bool:
    required = {_canonical_keyword(keyword) for keyword in required_faction_keywords}
    if not required:
        return True
    target_unit_id = _require_target_unit_id(target_binding)
    unit = _unit_by_id_or_none(state=state, unit_instance_id=target_unit_id)
    if unit is None:
        raise GameLifecycleError("Stratagem target unit is unknown.")
    stored = {_canonical_keyword(keyword) for keyword in unit.faction_keywords}
    return required.issubset(stored)


def _target_unit_has_excluded_keywords(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    excluded_keywords: tuple[str, ...],
) -> bool:
    excluded = {_canonical_keyword(keyword) for keyword in excluded_keywords}
    if not excluded:
        return False
    target_unit_id = _require_target_unit_id(target_binding)
    unit = _unit_by_id_or_none(state=state, unit_instance_id=target_unit_id)
    if unit is None:
        raise GameLifecycleError("Stratagem target unit is unknown.")
    stored = {_canonical_keyword(keyword) for keyword in unit.keywords}
    return bool(excluded & stored)


def _target_unit_has_excluded_faction_keywords(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    excluded_faction_keywords: tuple[str, ...],
) -> bool:
    excluded = {_canonical_keyword(keyword) for keyword in excluded_faction_keywords}
    if not excluded:
        return False
    target_unit_id = _require_target_unit_id(target_binding)
    unit = _unit_by_id_or_none(state=state, unit_instance_id=target_unit_id)
    if unit is None:
        raise GameLifecycleError("Stratagem target unit is unknown.")
    stored = {_canonical_keyword(keyword) for keyword in unit.faction_keywords}
    return bool(excluded & stored)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Stratagem keyword lookup requires a UnitInstance.")
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str:
        raise GameLifecycleError("Stratagem keyword must be a string.")
    stripped = keyword.strip()
    if not stripped:
        raise GameLifecycleError("Stratagem keyword must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _active_tactical_secondary_cards(
    *,
    state: GameState,
    player_id: str,
) -> tuple[SecondaryMissionCardState, ...]:
    return tuple(
        sorted(
            (
                card
                for card in state.secondary_mission_card_states
                if card.player_id == player_id
                and card.mode is SecondaryMissionCardMode.TACTICAL
                and card.status is SecondaryMissionCardStatus.ACTIVE
            ),
            key=lambda card: card.secondary_mission_id,
        )
    )


def _battle_shock_test_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        return ()
    army = state.army_definition_for_player(player_id)
    if army is None:
        return ()
    requests = collect_battle_shock_test_requests(
        game_id=state.game_id,
        battle_round=state.battle_round,
        player_id=player_id,
        army=army,
        battlefield_state=battlefield_state,
        starting_strength_records=tuple(state.starting_strength_records),
    )
    return tuple(sorted({request.unit_instance_id for request in requests}))


def _rapid_ingress_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    return tuple(
        sorted(
            reserve_state.unit_instance_id
            for reserve_state in state.unarrived_reserve_states_for_player(player_id)
            if reserve_state.status is ReserveStatus.IN_RESERVES
            and not reserve_state_is_cult_ambush(reserve_state)
        )
    )


def _strategic_reserves_ingress_unit_ids(
    *,
    state: GameState,
    player_id: str,
) -> tuple[str, ...]:
    return tuple(
        sorted(
            reserve_state.unit_instance_id
            for reserve_state in state.unarrived_reserve_states_for_player(player_id)
            if reserve_state.status is ReserveStatus.IN_RESERVES
            and reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
        )
    )


def _deep_strike_arriving_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    army = state.army_definition_for_player(player_id)
    if army is None:
        return ()
    units_by_id = {unit.unit_instance_id: unit for unit in army.units}
    unit_ids: list[str] = []
    for reserve_state in state.unarrived_reserve_states_for_player(player_id):
        unit = units_by_id.get(reserve_state.unit_instance_id)
        if unit is None:
            raise GameLifecycleError("ReserveState references an unknown unit.")
        if reserve_state.status is ReserveStatus.IN_RESERVES and (
            reserve_state.reserve_kind is ReserveKind.DEEP_STRIKE or unit_has_deep_strike(unit)
        ):
            unit_ids.append(reserve_state.unit_instance_id)
    return tuple(sorted(unit_ids))


def _command_reroll_context_error(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
) -> str | None:
    try:
        roll_state = _command_reroll_state(context)
        if roll_state.original_result.spec.actor_id != context.player_id:
            return "dice_roll_actor_drift"
        roll_type = roll_state.original_result.spec.roll_type
        if _command_reroll_roll_class(roll_type) not in definition.eligible_roll_types:
            return "ineligible_dice_roll_type"
        if roll_state.original_result.spec.reroll_forbidden_rule_ids:
            return "dice_roll_reroll_forbidden"
        affected_unit_id = _command_reroll_affected_unit_id(context)
        if _rules_unit_owner(state=state, unit_instance_id=affected_unit_id) != context.player_id:
            return "affected_unit_owner_drift"
        _canonical_stratagem_affected_unit_id(
            state=state,
            unit_instance_id=affected_unit_id,
        )
        permission = _command_reroll_permission(
            source_id=CORE_COMMAND_REROLL_HANDLER_ID,
            context=context,
            roll_state=roll_state,
        )
        permission.legal_selections_for_state(roll_state)
    except (DiceRollSpecError, GameLifecycleError):  # fmt: skip
        return "invalid_dice_roll_context"
    return None


def _command_reroll_roll_class(roll_type: str) -> str:
    if roll_type == "attack_sequence.hit":
        return "hit_roll"
    if roll_type == "attack_sequence.wound":
        return "wound_roll"
    if roll_type.startswith("attack_sequence.save."):
        return "save_roll"
    if roll_type.startswith("attack_sequence.damage"):
        return "damage_roll"
    if roll_type.startswith("random_characteristic.damage."):
        return "damage_roll"
    return roll_type


def _command_reroll_state(context: StratagemEligibilityContext) -> DiceRollState:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice roll trigger payload.")
    roll_payload = trigger_payload.get(COMMAND_REROLL_DICE_CONTEXT_KEY)
    if not isinstance(roll_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice_roll_state payload.")
    return DiceRollState.from_payload(cast(DiceRollStatePayload, roll_payload))


def _command_reroll_affected_unit_id(context: StratagemEligibilityContext) -> str:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        raise GameLifecycleError("Command Re-roll requires dice roll trigger payload.")
    unit_id = trigger_payload.get(COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY)
    if type(unit_id) is not str:
        raise GameLifecycleError("Command Re-roll requires affected unit context.")
    return _validate_identifier("Command Re-roll affected unit id", unit_id)


def _command_reroll_permission(
    *,
    source_id: str,
    context: StratagemEligibilityContext,
    roll_state: DiceRollState,
) -> RerollPermission:
    roll_type = roll_state.original_result.spec.roll_type
    if roll_type == "charge_roll" or len(roll_state.current_values) == 1:
        return RerollPermission(
            source_id=source_id,
            timing_window=context.timing_window_id or context.trigger_kind.value,
            owning_player_id=context.player_id,
            eligible_roll_type=roll_type,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
        )
    already_rerolled = set(roll_state.rerolled_indices())
    return RerollPermission(
        source_id=source_id,
        timing_window=context.timing_window_id or context.trigger_kind.value,
        owning_player_id=context.player_id,
        eligible_roll_type=roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=tuple(
            (index,)
            for index, _value in enumerate(roll_state.current_values)
            if index not in already_rerolled
        ),
    )


def _selected_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind is not TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET:
        return "selected_target_requires_target_selection_trigger"
    if context.phase is not BattlePhase.SHOOTING:
        return "selected_target_requires_shooting_phase"
    selected_unit_ids = _selected_target_unit_ids_or_none(context)
    if selected_unit_ids is None:
        return "missing_selected_target_context"
    if not selected_unit_ids:
        return "no_selected_target_units"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) not in selected_unit_ids:
        return "unit_not_selected_as_target"
    return None


def _selected_target_unit_ids_or_none(
    context: StratagemEligibilityContext,
) -> tuple[str, ...] | None:
    return selected_target_unit_ids_or_none(context.trigger_payload)


def _not_selected_to_shoot_target_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext | None,
    target_binding: StratagemTargetBinding,
) -> str | None:
    if context is not None and context.phase is not BattlePhase.SHOOTING:
        return "not_selected_to_shoot_requires_shooting_phase"
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return "missing_shooting_phase_state"
    target_unit_id = _require_target_unit_id(target_binding)
    if target_unit_id in shooting_state.selected_unit_ids:
        return "unit_already_selected_to_shoot"
    if target_unit_id in shooting_state.shot_unit_ids:
        return "unit_already_shot"
    if target_unit_id in shooting_state.skipped_unit_ids:
        return "unit_already_skipped_shooting"
    return None


def _not_selected_to_fight_target_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext | None,
    target_binding: StratagemTargetBinding,
) -> str | None:
    if context is not None and context.phase is not BattlePhase.FIGHT:
        return "not_selected_to_fight_requires_fight_phase"
    fight_state = state.fight_phase_state
    if fight_state is None:
        return "missing_fight_phase_state"
    target_unit_id = _require_target_unit_id(target_binding)
    if target_unit_id in fight_state.fight_order_state.selected_to_fight_unit_ids:
        return "unit_already_selected_to_fight"
    return None


def _selected_to_move_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_MOVE:
        return "selected_to_move_requires_unit_selection_trigger"
    if context.phase is not BattlePhase.MOVEMENT:
        return "selected_to_move_requires_movement_phase"
    selected_unit_id = _selected_to_move_unit_id_or_none(context)
    if selected_unit_id is None:
        return "missing_selected_to_move_context"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) != selected_unit_id:
        return "unit_not_selected_to_move"
    return None


def _selected_to_move_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_id = trigger_payload.get(SELECTED_TO_MOVE_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Selected to move unit id", raw_unit_id)


def _selected_to_shoot_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_SHOOT:
        return "selected_to_shoot_requires_unit_selection_trigger"
    if context.phase is not BattlePhase.SHOOTING:
        return "selected_to_shoot_requires_shooting_phase"
    selected_unit_id = _selected_to_shoot_unit_id_or_none(context)
    if selected_unit_id is None:
        return "missing_selected_to_shoot_context"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) != selected_unit_id:
        return "unit_not_selected_to_shoot"
    return None


def _selected_to_shoot_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_id = trigger_payload.get(SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Selected to shoot unit id", raw_unit_id)


def _selected_to_fight_target_context_error(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    requires_charge_move: bool,
) -> str | None:
    if type(requires_charge_move) is not bool:
        raise GameLifecycleError("Selected-to-fight charge flag must be boolean.")
    if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT:
        return "selected_to_fight_requires_unit_selection_trigger"
    if context.phase is not BattlePhase.FIGHT:
        return "selected_to_fight_requires_fight_phase"
    selected_unit_id = _selected_to_fight_unit_id_or_none(context)
    if selected_unit_id is None:
        return "missing_selected_to_fight_context"
    if target_binding is not None and _require_target_unit_id(target_binding) != selected_unit_id:
        return "unit_not_selected_to_fight"
    if requires_charge_move and not _unit_made_charge_move_for_selected_to_fight(
        state=state,
        unit_instance_id=selected_unit_id,
    ):
        return "unit_did_not_make_charge_move"
    return None


def _selected_to_fight_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_id = trigger_payload.get(SELECTED_TO_FIGHT_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        raw_unit_id = trigger_payload.get("selected_unit_instance_id")
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Selected to fight unit id", raw_unit_id)


def _unit_made_charge_move_for_selected_to_fight(
    *,
    state: GameState,
    unit_instance_id: str,
) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects_for_unit(requested_unit_id):
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            continue
        if payload.get("effect_kind") == "charge_grants_fights_first":
            return True
    return False


def _just_fell_back_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_FALLS_BACK:
        return "fell_back_unit_requires_fall_back_trigger"
    if context.phase is not BattlePhase.MOVEMENT:
        return "fell_back_unit_requires_movement_phase"
    fell_back_unit_id = _just_fell_back_unit_id_or_none(context)
    if fell_back_unit_id is None:
        return "missing_fell_back_unit_context"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) != fell_back_unit_id:
        return "unit_not_fell_back"
    return None


def _just_fell_back_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_id = trigger_payload.get(JUST_FELL_BACK_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Just-fell-back unit id", raw_unit_id)


def _just_shot_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT:
        return "just_shot_requires_unit_has_shot_trigger"
    if context.phase is not BattlePhase.SHOOTING:
        return "just_shot_requires_shooting_phase"
    shot_unit_id = _just_shot_unit_id_or_none(context)
    if shot_unit_id is None:
        return "missing_just_shot_unit_context"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) != shot_unit_id:
        return "unit_not_just_shot"
    return None


def _just_shot_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_id = trigger_payload.get(JUST_SHOT_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Just-shot unit id", raw_unit_id)


def _destroyed_target_by_just_shot_unit_target_context_error(
    *,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    if context.trigger_kind not in {
        TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
    }:
        return "destroyed_target_requires_unit_has_shot_trigger"
    if context.phase is not BattlePhase.SHOOTING:
        return "destroyed_target_requires_shooting_phase"
    if _just_shot_unit_id_or_none(context) is None:
        return "missing_just_shot_unit_context"
    destroyed_target_unit_ids = destroyed_target_unit_ids_from_context(context)
    if not destroyed_target_unit_ids:
        return "missing_destroyed_target_context"
    if target_binding is None:
        return None
    if _require_target_unit_id(target_binding) not in destroyed_target_unit_ids:
        return "unit_not_destroyed_target_of_just_shot_unit"
    return None


def _hit_target_unit_ids_or_empty(context: StratagemEligibilityContext) -> tuple[str, ...]:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return ()
    return _identifier_list_from_trigger_payload(
        trigger_payload=trigger_payload,
        key=HIT_TARGET_UNIT_CONTEXT_KEY,
        field_name="Hit target unit id",
    )


def _engaged_enemy_unit_ids_or_empty(context: StratagemEligibilityContext) -> tuple[str, ...]:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return ()
    return _identifier_list_from_trigger_payload(
        trigger_payload=trigger_payload,
        key=ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
        field_name="Engaged enemy unit id",
    )


def _effect_selection_required_target_keywords(
    payload: dict[str, JsonValue],
) -> tuple[str, ...]:
    raw_keywords = payload.get("effect_selection_required_target_keywords")
    if raw_keywords is None:
        return ()
    if not isinstance(raw_keywords, list):
        raise GameLifecycleError("Effect selection required target keywords must be a list.")
    return tuple(
        _canonical_keyword(_validate_identifier("Effect selection target keyword", keyword))
        for keyword in raw_keywords
    )


def _target_unit_has_all_keywords(
    *,
    state: GameState,
    target_binding: StratagemTargetBinding,
    required_keywords: tuple[str, ...],
) -> bool:
    return _target_unit_satisfies_required_keywords(
        state=state,
        target_binding=target_binding,
        required_keywords=required_keywords,
    )


def destroyed_target_unit_ids_from_context(
    context: StratagemEligibilityContext,
) -> tuple[str, ...]:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return ()
    return _identifier_list_from_trigger_payload(
        trigger_payload=trigger_payload,
        key=DESTROYED_TARGET_UNIT_CONTEXT_KEY,
        field_name="Destroyed target unit id",
    )


def destroyed_enemy_unit_ids_from_context(
    context: StratagemEligibilityContext,
) -> tuple[str, ...]:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return ()
    return _identifier_list_from_trigger_payload(
        trigger_payload=trigger_payload,
        key=DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
        field_name="Destroyed enemy unit id",
    )


def _identifier_list_from_trigger_payload(
    *,
    trigger_payload: Mapping[str, object],
    key: str,
    field_name: str,
) -> tuple[str, ...]:
    raw_unit_ids = trigger_payload.get(key)
    if raw_unit_ids is None:
        return ()
    if not isinstance(raw_unit_ids, list):
        return ()
    raw_unit_id_values = cast(list[object], raw_unit_ids)
    unit_ids: list[str] = []
    seen: set[str] = set()
    for raw_unit_id in raw_unit_id_values:
        if type(raw_unit_id) is not str:
            return ()
        unit_id = _validate_identifier(field_name, raw_unit_id)
        if unit_id in seen:
            return ()
        seen.add(unit_id)
        unit_ids.append(unit_id)
    return tuple(sorted(unit_ids))


def _hit_enemy_unit_id_or_none(effect_selection: JsonValue) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    raw_unit_id = effect_selection.get(HIT_ENEMY_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Hit enemy unit id", raw_unit_id)


def _engaged_enemy_unit_id_or_none(effect_selection: JsonValue) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    raw_unit_id = effect_selection.get(ENGAGED_ENEMY_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Engaged enemy unit id", raw_unit_id)


def _visible_enemy_unit_id_or_none(effect_selection: JsonValue) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    if effect_selection.get("effect_selection_kind") != VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        return None
    raw_unit_id = effect_selection.get(VISIBLE_ENEMY_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Visible enemy unit id", raw_unit_id)


def _engaged_with_fall_back_unit_target_context_error(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> str | None:
    if context.trigger_kind not in {
        TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK,
        TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE,
    }:
        return "fall_back_engagement_requires_fall_back_selection_trigger"
    if context.phase is not BattlePhase.MOVEMENT:
        return "fall_back_engagement_requires_movement_phase"
    fall_back_unit_id = _fall_back_unit_id_or_none(context)
    if fall_back_unit_id is None:
        return "missing_fall_back_unit_context"
    fall_back_owner = _unit_owner(state=state, unit_instance_id=fall_back_unit_id)
    if fall_back_owner is None:
        return "unknown_fall_back_unit"
    if fall_back_owner == player_id:
        return "fall_back_unit_not_enemy"
    target_unit_id = _require_target_unit_id(target_binding)
    if target_unit_id not in _engaged_fall_back_target_unit_ids(
        state=state,
        player_id=player_id,
        context=context,
    ):
        return "unit_not_engaged_with_fall_back_unit"
    return None


def _fall_back_unit_id_or_none(context: StratagemEligibilityContext) -> str | None:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return None
    raw_unit_id = trigger_payload.get(FALL_BACK_UNIT_CONTEXT_KEY)
    if type(raw_unit_id) is not str:
        return None
    return _validate_identifier("Fall Back unit id", raw_unit_id)


def _engaged_fall_back_target_unit_ids(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext,
) -> tuple[str, ...]:
    fall_back_unit_id = _fall_back_unit_id_or_none(context)
    if fall_back_unit_id is None:
        return ()
    snapshotted_unit_ids = _snapshotted_engaged_fall_back_target_unit_ids(
        state=state,
        player_id=player_id,
        context=context,
    )
    if snapshotted_unit_ids:
        return snapshotted_unit_ids
    if context.trigger_kind is TimingTriggerKind.AFTER_ENEMY_UNIT_ENDS_MOVE:
        return ()
    return tuple(
        sorted(
            unit.unit_instance_id
            for army in state.army_definitions
            if army.player_id == player_id
            for unit in army.units
            if _units_are_engaged(
                state=state,
                first_unit_instance_id=unit.unit_instance_id,
                second_unit_instance_id=fall_back_unit_id,
            )
        )
    )


def _snapshotted_engaged_fall_back_target_unit_ids(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext,
) -> tuple[str, ...]:
    trigger_payload = context.trigger_payload
    if not isinstance(trigger_payload, dict):
        return ()
    unit_ids = _identifier_list_from_trigger_payload(
        trigger_payload=trigger_payload,
        key=ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY,
        field_name="Engaged Fall Back target unit id",
    )
    if not unit_ids:
        return ()
    return tuple(
        sorted(
            unit_id
            for unit_id in unit_ids
            if _unit_owner(state=state, unit_instance_id=unit_id) == player_id
        )
    )


def _fire_overwatch_target_binding_error(
    *,
    state: GameState,
    player_id: str,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    ruleset_descriptor: RulesetDescriptor | None,
    army_catalog: ArmyCatalog | None,
) -> str | None:
    triggering_unit_id = _fire_overwatch_triggering_enemy_unit_id_or_none(context)
    if triggering_unit_id is None:
        return "missing_fire_overwatch_trigger_unit"
    triggering_owner = _unit_owner(state=state, unit_instance_id=triggering_unit_id)
    if triggering_owner is None:
        return "unknown_fire_overwatch_trigger_unit"
    if triggering_owner == player_id:
        return "fire_overwatch_trigger_unit_not_enemy"
    if fire_overwatch_forbidden_by_effects(
        state.persisting_effects_for_unit(triggering_unit_id),
        owner_player_id=triggering_owner,
    ):
        return "fire_overwatch_target_forbidden"
    if state.battlefield_state is None:
        return "fire_overwatch_requires_battlefield"
    shooting_unit_id = _require_target_unit_id(target_binding)
    if not _units_are_within_range_inches(
        state=state,
        first_unit_instance_id=shooting_unit_id,
        second_unit_instance_id=triggering_unit_id,
        distance_inches=FIRE_OVERWATCH_MAX_RANGE_INCHES,
    ):
        return "fire_overwatch_unit_not_within_24"
    if ruleset_descriptor is None or army_catalog is None:
        return "fire_overwatch_requires_shooting_rules_context"
    shooting_unit = _unit_by_id(state=state, unit_instance_id=shooting_unit_id)
    if _unit_has_keyword(shooting_unit, "TITANIC"):
        return "fire_overwatch_unit_titanic"
    if _unit_is_within_enemy_engagement_range(
        state=state,
        player_id=player_id,
        unit_instance_id=shooting_unit_id,
    ):
        return "fire_overwatch_unit_engaged"
    if not shooting_unit_can_select_to_shoot(
        state=state,
        unit=shooting_unit,
        army_catalog=army_catalog,
        player_id=player_id,
    ):
        return "fire_overwatch_unit_ineligible_to_shoot"
    if not shooting_unit_has_legal_declaration_against_targets(
        state=state,
        unit=shooting_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=player_id,
        target_unit_ids=(triggering_unit_id,),
    ):
        return "fire_overwatch_no_legal_shooting_declaration"
    return None
