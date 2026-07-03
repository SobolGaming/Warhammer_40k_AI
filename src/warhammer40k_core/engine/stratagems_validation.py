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
from warhammer40k_core.engine.stratagems_geometry import *
from warhammer40k_core.engine.stratagems_ingress import *
from warhammer40k_core.engine.stratagems_core_handlers import *
from warhammer40k_core.engine.stratagems_tactical_secondaries import *
from warhammer40k_core.engine.stratagems_fire_overwatch import *
from warhammer40k_core.engine.stratagems_effect_handlers import *

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
    from warhammer40k_core.engine.stratagems_geometry import _fire_overwatch_triggering_enemy_unit_id, _fire_overwatch_triggering_enemy_unit_id_or_none, _heroic_intervention_target_binding_error, _crushing_impact_context_error, _counteroffensive_target_context_error, _epic_challenge_context_error, _units_are_within_range_inches, _friendly_unit_within_enemy_range, _units_are_engaged, _model_engaged_with_unit, _geometry_model_for_model_id, _model_is_alive_and_placed, _model_toughness, _crushing_impact_enemy_target_id_or_none, _crushing_impact_model_id_or_none, _epic_challenge_character_model_id_or_none, _explosives_context_error, _explosives_target_unit_id, _explosives_target_unit_id_or_none, _explosives_target_is_visible_and_in_range, _unit_is_within_enemy_engagement_range, _enemy_unit_is_within_friendly_engagement_range, _any_models_within_engagement_range, _geometry_models_for_unit, _battlefield_scenario_for_stratagem, _stratagem_terrain_features, _stratagem_ruleset_descriptor, _explosives_visibility_profile, _unit_owner, _unit_by_id, _unit_by_id_or_none, _reserve_state_for_target, _unit_for_reserve_state, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _unit_has_deep_strike_keyword, _battlefield_scenario, _proposal_from_request_payload, _proposal_from_result_payload, _proposal_context_error, _movement_proposal_request_from_payload, _heroic_intervention_charge_move_from_result_payload, _heroic_intervention_charge_move_request_error, _heroic_intervention_maximum_distance, _heroic_intervention_mode_from_request, _heroic_intervention_requested_reachable_distances, _heroic_intervention_request_context, _placement_proposal_from_result_payload, _proposal_request_is_rapid_ingress
    from warhammer40k_core.engine.stratagems_ingress import _apply_rapid_ingress_placement, _strategic_reserve_rule_for_ingress_request, _proposal_request_marks_movement_phase_arrival, _request_rapid_ingress_placement_retry
    from warhammer40k_core.engine.stratagems_core_handlers import _stratagem_use_from_proposal_context, _apply_supported_stratagem_handler, _validate_supported_stratagem_handler_available, _validate_supported_stratagem_handler_preflight, _generic_rule_ir_from_stratagem_payload, _apply_generic_rule_ir_stratagem_handler, _apply_command_reroll_handler, is_command_reroll_decision_request, invalid_command_reroll_decision_status, apply_command_reroll_decision, _command_reroll_request_context, _apply_insane_bravery_handler, _apply_rapid_ingress_handler, _apply_ingress_move_handler, _ingress_move_effect_payload, _apply_force_desperate_escape_handler
    from warhammer40k_core.engine.stratagems_tactical_secondaries import _apply_new_orders_handler
    from warhammer40k_core.engine.stratagems_fire_overwatch import _apply_fire_overwatch_handler
    from warhammer40k_core.engine.stratagems_effect_handlers import _apply_go_to_ground_handler, _apply_smokescreen_handler, _apply_explosives_handler, apply_explosives_mortal_wound_feel_no_pain_decision, _emit_explosives_resolved, _apply_counteroffensive_handler, _apply_crushing_impact_handler, _apply_epic_challenge_handler, _apply_heroic_intervention_handler, _apply_stratagem_mortal_wounds, _heroic_intervention_reachable_target_distances, _enemy_unit_ids_for_player, _closest_unit_distance_inches, _unit_made_charge_move
# fmt: on

__all__ = (
    "_apply_command_point_effects",
    "_invalid",
    "_next_stratagem_use_id",
    "_require_decline_event_fields",
    "_require_target_unit_id",
    "_stratagem_handler_is_unsupported",
    "_target_binding_token",
    "_target_secondary_mission_id",
    "_validate_bool",
    "_validate_catalog_records",
    "_validate_identifier",
    "_validate_identifier_tuple",
    "_validate_non_negative_int",
    "_validate_optional_identifier",
    "_validate_optional_phase",
    "_validate_positive_int",
    "_validate_stratagem_affected_unit_ids",
    "_validate_target_policy_id",
)


def _apply_command_point_effects(
    *,
    state: GameState,
    decisions: DecisionController,
    player_id: str,
    source_id: str,
    effect_payload: JsonValue,
) -> None:
    if not isinstance(effect_payload, dict):
        return
    gain_payload = effect_payload.get("command_point_gain")
    if isinstance(gain_payload, dict):
        amount = gain_payload.get("amount")
        cap_exempt = gain_payload.get("cap_exempt", False)
        if type(amount) is not int:
            raise GameLifecycleError("command_point_gain amount must be an integer.")
        if type(cap_exempt) is not bool:
            raise GameLifecycleError("command_point_gain cap_exempt must be a bool.")
        gain = state.gain_command_points(
            player_id=player_id,
            amount=amount,
            source_id=f"{source_id}:cp-gain",
            source_kind=CommandPointSourceKind.OTHER,
            cap_exempt=cap_exempt,
        )
        event_type = (
            "command_points_gained"
            if gain.status is CommandPointGainStatus.APPLIED
            else "command_points_gain_capped"
        )
        decisions.event_log.append(event_type, gain.to_payload())
    refund_payload = effect_payload.get("command_point_refund")
    if isinstance(refund_payload, dict):
        amount = refund_payload.get("amount")
        cap_exempt = refund_payload.get("cap_exempt", False)
        if type(amount) is not int:
            raise GameLifecycleError("command_point_refund amount must be an integer.")
        if type(cap_exempt) is not bool:
            raise GameLifecycleError("command_point_refund cap_exempt must be a bool.")
        refund = state.refund_command_points(
            player_id=player_id,
            amount=amount,
            source_id=f"{source_id}:cp-refund",
            cap_exempt=cap_exempt,
        )
        event_type = (
            "command_points_refunded"
            if refund.status is CommandPointRefundStatus.APPLIED
            else "command_points_refund_capped"
        )
        decisions.event_log.append(event_type, refund.to_payload())


def _stratagem_handler_is_unsupported(definition: StratagemDefinition) -> bool:
    if type(definition) is not StratagemDefinition:
        raise GameLifecycleError("Stratagem handler support check requires a definition.")
    return definition.handler_id.startswith(UNSUPPORTED_STRATAGEM_HANDLER_PREFIX)


def _next_stratagem_use_id(*, state: GameState, player_id: str) -> str:
    return (
        f"stratagem-use:{player_id}:round-{state.battle_round:02d}:"
        f"{len(state.stratagem_use_records) + 1:06d}"
    )


def _target_binding_token(binding: StratagemTargetBinding) -> str:
    if binding.target_kind is StratagemTargetKind.NONE:
        return "none"
    if binding.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        return _target_secondary_mission_id(binding)
    return _require_target_unit_id(binding)


def _require_target_unit_id(binding: StratagemTargetBinding) -> str:
    if binding.target_unit_instance_id is None:
        raise GameLifecycleError("Stratagem target binding requires a unit id.")
    return binding.target_unit_instance_id


def _target_secondary_mission_id(binding: StratagemTargetBinding) -> str:
    if binding.target_secondary_mission_id is None:
        raise GameLifecycleError("Stratagem target binding requires a secondary mission id.")
    return binding.target_secondary_mission_id


def _validate_catalog_records(
    values: object,
) -> tuple[StratagemCatalogRecord, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Stratagem catalog records must be a tuple.")
    validated: list[StratagemCatalogRecord] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not StratagemCatalogRecord:
            raise GameLifecycleError(
                "Stratagem catalog records must contain StratagemCatalogRecord values."
            )
        if value.record_id in seen:
            raise GameLifecycleError("Stratagem catalog records must not contain duplicate IDs.")
        seen.add(value.record_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda record: record.record_id))


def _require_decline_event_fields(payload: Mapping[str, JsonValue]) -> None:
    for field_name in (
        "game_id",
        "player_id",
        "battle_round",
        "phase",
        "active_player_id",
        "trigger_kind",
        "timing_window_id",
        "request_id",
        "result_id",
        "decision_type",
    ):
        if field_name not in payload:
            raise GameLifecycleError("Stratagem decline event payload is malformed.")


def _invalid(state: GameState, message: str, reason: str) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload={"invalid_reason": reason},
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_identifier(field_name, value) for value in cast(tuple[object, ...], values)
    )


def _validate_stratagem_affected_unit_ids(values: object) -> tuple[str, ...]:
    affected_unit_ids = _validate_identifier_tuple(
        "StratagemUseRecord affected_unit_instance_ids",
        values,
    )
    if len(set(affected_unit_ids)) != len(affected_unit_ids):
        raise GameLifecycleError("StratagemUseRecord affected_unit_instance_ids must be unique.")
    return tuple(sorted(affected_unit_ids))


def _validate_optional_phase(field_name: str, value: object | None) -> BattlePhaseKind | None:
    if value is None:
        return None
    return battle_phase_kind_from_token(value)


def _validate_target_policy_id(
    *,
    target_kind: StratagemTargetKind,
    target_policy_id: object | None,
) -> str:
    if target_policy_id is None or target_policy_id == "":
        if target_kind is StratagemTargetKind.NONE:
            return "none"
        if target_kind is StratagemTargetKind.FRIENDLY_UNIT:
            return "friendly_unit"
        if target_kind is StratagemTargetKind.ANY_UNIT:
            return "any_unit"
        if target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
            return NEW_ORDERS_TARGET_POLICY_ID
        raise GameLifecycleError("StratagemTargetSpec target_kind is unsupported.")
    policy_id = _validate_identifier("StratagemTargetSpec target_policy_id", target_policy_id)
    if target_kind is StratagemTargetKind.NONE and policy_id != "none":
        raise GameLifecycleError("Targetless StratagemTargetSpec requires none target_policy_id.")
    if target_kind is not StratagemTargetKind.NONE and policy_id == "none":
        raise GameLifecycleError("Targeted StratagemTargetSpec cannot use none target_policy_id.")
    return policy_id


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
