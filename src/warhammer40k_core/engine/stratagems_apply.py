# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_model import *
from warhammer40k_core.engine.stratagems_requests import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE, STRATAGEM_PROPOSAL_PAYLOAD_KIND, DECLINE_STRATAGEM_WINDOW_OPTION_ID, DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE, UNSUPPORTED_STRATAGEM_HANDLER_PREFIX, CORE_COMMAND_REROLL_HANDLER_ID, CORE_INSANE_BRAVERY_HANDLER_ID, CORE_RAPID_INGRESS_HANDLER_ID, CORE_NEW_ORDERS_HANDLER_ID, CORE_FIRE_OVERWATCH_HANDLER_ID, CORE_GO_TO_GROUND_HANDLER_ID, CORE_EXPLOSIVES_HANDLER_ID, CORE_SMOKESCREEN_HANDLER_ID, CORE_HEROIC_INTERVENTION_HANDLER_ID, CORE_COUNTEROFFENSIVE_HANDLER_ID, CORE_CRUSHING_IMPACT_HANDLER_ID, CORE_EPIC_CHALLENGE_HANDLER_ID, GENERIC_INGRESS_MOVE_HANDLER_ID, GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID, GENERIC_RULE_IR_STRATAGEM_HANDLER_ID, COMMAND_REROLL_DICE_CONTEXT_KEY, COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY, INSANE_BRAVERY_TARGET_POLICY_ID, RAPID_INGRESS_TARGET_POLICY_ID, STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID, NEW_ORDERS_TARGET_POLICY_ID, FIRE_OVERWATCH_TARGET_POLICY_ID, GO_TO_GROUND_TARGET_POLICY_ID, SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID, EXPLOSIVES_TARGET_POLICY_ID, SMOKESCREEN_TARGET_POLICY_ID, HEROIC_INTERVENTION_TARGET_POLICY_ID, COUNTEROFFENSIVE_TARGET_POLICY_ID, CRUSHING_IMPACT_TARGET_POLICY_ID, EPIC_CHALLENGE_TARGET_POLICY_ID, SELECTED_TO_MOVE_TARGET_POLICY_ID, JUST_FELL_BACK_UNIT_TARGET_POLICY_ID, JUST_SHOT_UNIT_TARGET_POLICY_ID, ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID, EXPLOSIVES_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_MODEL_CONTEXT_KEY, EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND, HEROIC_INTERVENTION_MODE_INTO_THE_FRAY, SELECTED_TARGET_UNIT_CONTEXT_KEY, SELECTED_TO_MOVE_UNIT_CONTEXT_KEY, JUST_FELL_BACK_UNIT_CONTEXT_KEY, JUST_SHOT_UNIT_CONTEXT_KEY, HIT_TARGET_UNIT_CONTEXT_KEY, DESTROYED_TARGET_UNIT_CONTEXT_KEY, DESTROYED_ENEMY_UNIT_CONTEXT_KEY, HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND, HIT_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND, ENGAGED_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY, FALL_BACK_UNIT_CONTEXT_KEY, FALL_BACK_MODE_CONTEXT_KEY, FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND, FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY, FIRE_OVERWATCH_MAX_RANGE_INCHES, HEROIC_INTERVENTION_TARGET_RANGE_INCHES, HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES, CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT, StratagemAvailabilityKind, StratagemCategory, StratagemTargetKind, StratagemUseRecordPayload, StratagemTimingDescriptorPayload, StratagemRestrictionPolicyPayload, StratagemTargetSpecPayload, StratagemDefinitionPayload, StratagemCatalogRecordPayload, StratagemEligibilityContextPayload, StratagemTargetBindingPayload, StratagemTargetProposalPayload, StratagemTimingDescriptor, StratagemRestrictionPolicy, StratagemTargetSpec, StratagemDefinition, StratagemCatalogRecord, StratagemCatalogIndex, StratagemEligibilityContext, StratagemTargetBinding, StratagemTargetProposal, StratagemUseRequest, StratagemUseRecord
    from warhammer40k_core.engine.stratagems_requests import request_stratagem_use, request_stratagem_use_from_index, _request_stratagem_use_with_options, create_stratagem_use_decision_request, stratagem_decline_option, stratagem_decline_payload, is_stratagem_window_decline_result, stratagem_window_decline_allowed, stratagem_window_context_from_request, stratagem_window_decline_event_payload, stratagem_window_declined_for_context, stratagem_use_options, stratagem_use_options_from_index, stratagem_use_options_for_handler_from_index, hit_enemy_unit_effect_selection, engaged_enemy_unit_effect_selection, _stratagem_use_options_for_records, _effect_selections_for_binding, request_stratagem_target_proposal, create_stratagem_target_proposal_decision_request, stratagem_target_proposal_request_payload, stratagem_target_proposal_from_index
    from warhammer40k_core.engine.stratagems_selection import stratagem_availability_kind_from_token, stratagem_category_from_token, stratagem_target_kind_from_token, _stratagem_decision_option, _effect_selection_token, _stratagem_selection_from_result_payload, _require_stratagem_selection, stratagem_selection_from_decision_result, stratagem_selection_from_target_proposal_result, _record_is_available_for_context, _stratagem_unavailable_reason, _context_state_drift, _detachment_gate_allows, _effect_selection_error, _selected_command_point_cost, _selected_command_point_cost_result, _heroic_intervention_mode_error, _heroic_intervention_mode, _heroic_intervention_mode_additional_cost, _heroic_intervention_mode_costs, _required_effect_selection_fields_error, _effect_selection_string_or_none
    from warhammer40k_core.engine.stratagems_eligibility import _handler_unavailable_reason, _restriction_violation, _same_stratagem_phase, _stratagem_targeted_unit_ids, _stratagem_affected_unit_ids, _canonical_stratagem_affected_unit_id, _attached_unit_id_for_component, _unit_has_runtime_attached_role, _rules_unit_owner, _enumerated_target_bindings
    from warhammer40k_core.engine.stratagems_targeting import _target_binding_error, _target_unit_owner, _target_unit_has_keyword, _target_unit_within_controlled_objective_range, _objective_control_result_has_unit, _target_unit_satisfies_required_keywords, _target_unit_satisfies_required_keywords_any, _target_unit_satisfies_required_faction_keywords, _unit_has_keyword, _canonical_keyword, _active_tactical_secondary_cards, _battle_shock_test_unit_ids, _rapid_ingress_unit_ids, _strategic_reserves_ingress_unit_ids, _command_reroll_context_error, _command_reroll_roll_class, _command_reroll_state, _command_reroll_affected_unit_id, _command_reroll_permission, _selected_target_context_error, _selected_target_unit_ids_or_none, _selected_to_move_target_context_error, _selected_to_move_unit_id_or_none, _just_fell_back_target_context_error, _just_fell_back_unit_id_or_none, _just_shot_target_context_error, _just_shot_unit_id_or_none, _hit_target_unit_ids_or_empty, _engaged_enemy_unit_ids_or_empty, _effect_selection_required_target_keywords, _target_unit_has_all_keywords, destroyed_target_unit_ids_from_context, destroyed_enemy_unit_ids_from_context, _identifier_list_from_trigger_payload, _hit_enemy_unit_id_or_none, _engaged_enemy_unit_id_or_none, _engaged_with_fall_back_unit_target_context_error, _fall_back_unit_id_or_none, _engaged_fall_back_target_unit_ids, _fire_overwatch_target_binding_error
    from warhammer40k_core.engine.stratagems_geometry import _fire_overwatch_triggering_enemy_unit_id, _fire_overwatch_triggering_enemy_unit_id_or_none, _heroic_intervention_target_binding_error, _crushing_impact_context_error, _counteroffensive_target_context_error, _epic_challenge_context_error, _units_are_within_range_inches, _friendly_unit_within_enemy_range, _units_are_engaged, _model_engaged_with_unit, _geometry_model_for_model_id, _model_is_alive_and_placed, _model_toughness, _crushing_impact_enemy_target_id_or_none, _crushing_impact_model_id_or_none, _epic_challenge_character_model_id_or_none, _explosives_context_error, _explosives_target_unit_id, _explosives_target_unit_id_or_none, _explosives_target_is_visible_and_in_range, _unit_is_within_enemy_engagement_range, _enemy_unit_is_within_friendly_engagement_range, _any_models_within_engagement_range, _geometry_models_for_unit, _battlefield_scenario_for_stratagem, _stratagem_terrain_features, _stratagem_ruleset_descriptor, _explosives_visibility_profile, _unit_owner, _unit_by_id, _unit_by_id_or_none, _reserve_state_for_target, _unit_for_reserve_state, _reserve_placement_kinds_for_unit, _reserve_proposal_kind, _unit_has_deep_strike_keyword, _battlefield_scenario, _proposal_from_request_payload, _proposal_from_result_payload, _proposal_context_error, _movement_proposal_request_from_payload, _heroic_intervention_charge_move_from_result_payload, _heroic_intervention_charge_move_request_error, _heroic_intervention_maximum_distance, _heroic_intervention_mode_from_request, _heroic_intervention_requested_reachable_distances, _heroic_intervention_request_context, _placement_proposal_from_result_payload, _proposal_request_is_rapid_ingress
    from warhammer40k_core.engine.stratagems_ingress import _apply_rapid_ingress_placement, _strategic_reserve_rule_for_ingress_request, _proposal_request_marks_movement_phase_arrival, _request_rapid_ingress_placement_retry
    from warhammer40k_core.engine.stratagems_core_handlers import _stratagem_use_from_proposal_context, _apply_supported_stratagem_handler, _validate_supported_stratagem_handler_available, _validate_supported_stratagem_handler_preflight, _generic_rule_ir_from_stratagem_payload, _apply_generic_rule_ir_stratagem_handler, _apply_command_reroll_handler, is_command_reroll_decision_request, invalid_command_reroll_decision_status, apply_command_reroll_decision, _command_reroll_request_context, _apply_insane_bravery_handler, _apply_rapid_ingress_handler, _apply_ingress_move_handler, _ingress_move_effect_payload, _apply_force_desperate_escape_handler
    from warhammer40k_core.engine.stratagems_tactical_secondaries import _apply_new_orders_handler
    from warhammer40k_core.engine.stratagems_fire_overwatch import _apply_fire_overwatch_handler
    from warhammer40k_core.engine.stratagems_effect_handlers import _apply_go_to_ground_handler, _apply_smokescreen_handler, _apply_explosives_handler, apply_explosives_mortal_wound_feel_no_pain_decision, _emit_explosives_resolved, _apply_counteroffensive_handler, _apply_crushing_impact_handler, _apply_epic_challenge_handler, _apply_heroic_intervention_handler, _apply_stratagem_mortal_wounds, _heroic_intervention_reachable_target_distances, _enemy_unit_ids_for_player, _closest_unit_distance_inches, _unit_made_charge_move
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "_apply_stratagem_use",
    "_request_heroic_intervention_charge_move_retry",
    "apply_heroic_intervention_charge_move",
    "apply_stratagem_decision",
    "apply_stratagem_placement_proposal",
    "apply_stratagem_target_proposal",
    "invalid_heroic_intervention_charge_move_status",
    "invalid_stratagem_placement_proposal_status",
    "invalid_stratagem_target_proposal_status",
    "invalid_stratagem_use_status",
    "is_heroic_intervention_charge_move_request",
    "is_stratagem_placement_proposal_request",
)


def invalid_stratagem_use_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> LifecycleStatus | None:
    selection = _stratagem_selection_from_result_payload(result.payload)
    if selection is None:
        return _invalid(state, "Malformed stratagem decision payload.", "malformed_payload")
    context = selection[0]
    record = selection[1]
    target_binding = selection[2]
    effect_selection = selection[3]
    drift = _context_state_drift(state=state, context=context)
    if drift is not None:
        return _invalid(state, "Stale stratagem decision context.", drift)
    if request.actor_id != context.player_id or result.actor_id != context.player_id:
        return _invalid(state, "Stratagem decision actor drift.", "wrong_context")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=record,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        decisions=decisions,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if violation is not None:
        return _invalid(state, "Stratagem decision is no longer legal.", violation)
    return None


def apply_stratagem_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None = None,
) -> StratagemUseRecord:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem application requires a DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem application requires a DecisionController.")
    selection = _require_stratagem_selection(result.payload)
    context, catalog_record, target_binding, effect_selection = selection
    return _apply_stratagem_use(
        state=state,
        result=result,
        decisions=decisions,
        context=context,
        catalog_record=catalog_record,
        target_binding=target_binding,
        effect_selection=effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
    )


def _apply_stratagem_use(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    catalog_record: StratagemCatalogRecord,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
) -> StratagemUseRecord:
    definition = catalog_record.definition
    if _stratagem_handler_is_unsupported(definition):
        raise GameLifecycleError("Unsupported stratagem handler cannot be applied.")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=catalog_record,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if violation is not None:
        raise GameLifecycleError(f"Prevalidated stratagem is no longer legal: {violation}.")
    use_id = _next_stratagem_use_id(state=state, player_id=context.player_id)
    command_point_modification = _selected_command_point_cost_result(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        decisions=decisions,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    command_point_cost = command_point_modification.command_point_cost
    try:
        targeted_unit_ids = _stratagem_targeted_unit_ids(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
        )
        affected_unit_ids = _stratagem_affected_unit_ids(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
        )
    except GameLifecycleError as exc:
        raise GameLifecycleError(
            "Prevalidated stratagem affected-unit context is invalid."
        ) from exc
    use_record = StratagemUseRecord(
        use_id=use_id,
        player_id=context.player_id,
        stratagem_id=definition.stratagem_id,
        source_id=definition.source_id,
        battle_round=context.battle_round,
        phase=context.phase,
        active_player_id=context.active_player_id,
        timing_window_id=context.timing_window_id,
        request_id=result.request_id,
        result_id=result.result_id,
        selected_option_id=result.selected_option_id,
        target_binding=target_binding,
        targeted_unit_instance_ids=targeted_unit_ids,
        affected_unit_instance_ids=affected_unit_ids,
        command_point_cost=command_point_cost,
        command_point_transaction_id=None,
        handler_id=definition.handler_id,
        command_point_modifier_ids=command_point_modification.modifier_ids,
        command_point_modifier_source_ids=command_point_modification.source_ids,
        effect_selection=effect_selection,
        effect_payload=definition.effect_payload,
    )
    _validate_supported_stratagem_handler_preflight(
        state=state,
        decisions=decisions,
        result=result,
        context=context,
        definition=definition,
        target_binding=target_binding,
        use_record=use_record,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
    )
    spend_result: CommandPointSpendResult | None = None
    transaction_id: str | None = None
    if command_point_cost > 0:
        spend_result = state.spend_command_points(
            player_id=context.player_id,
            amount=command_point_cost,
            source_id=use_id,
        )
        if spend_result.status is not CommandPointSpendStatus.APPLIED:
            raise GameLifecycleError("Prevalidated stratagem spend failed.")
        if spend_result.transaction is None:
            raise GameLifecycleError("Applied stratagem spend is missing transaction.")
        transaction_id = spend_result.transaction.transaction_id
        decisions.event_log.append("command_points_spent", spend_result.to_payload())
        use_record = replace(use_record, command_point_transaction_id=transaction_id)
    state.record_stratagem_use(use_record)
    decisions.event_log.append("stratagem_used", use_record.to_payload())
    _apply_command_point_effects(
        state=state,
        decisions=decisions,
        player_id=context.player_id,
        source_id=use_id,
        effect_payload=definition.effect_payload,
    )
    _apply_supported_stratagem_handler(
        state=state,
        decisions=decisions,
        result=result,
        context=context,
        definition=definition,
        target_binding=target_binding,
        use_record=use_record,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
        shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
    )
    return use_record


def invalid_stratagem_target_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    decisions: DecisionController | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> LifecycleStatus | None:
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(state, "Stratagem target proposal selected invalid option.", "malformed")
    request_proposal = _proposal_from_request_payload(request.payload)
    if request_proposal is None:
        return _invalid(state, "Malformed stratagem target proposal request.", "malformed_request")
    submitted_proposal = _proposal_from_result_payload(result.payload)
    if submitted_proposal is None:
        return _invalid(state, "Malformed stratagem target proposal payload.", "malformed_payload")
    context_error = _proposal_context_error(
        state=state,
        request_proposal=request_proposal,
        submitted_proposal=submitted_proposal,
    )
    if context_error is not None:
        return _invalid(state, "Stratagem target proposal context drift.", context_error)
    if submitted_proposal.target_binding is None:
        return _invalid(state, "Stratagem target proposal requires target binding.", "schema")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=request_proposal.catalog_record,
        context=request_proposal.context,
        target_binding=submitted_proposal.target_binding,
        effect_selection=submitted_proposal.effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if violation is not None:
        return _invalid(state, "Stratagem target proposal is not legal.", violation)
    return None


def apply_stratagem_target_proposal(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None = None,
) -> StratagemUseRecord:
    proposal = _proposal_from_result_payload(result.payload)
    if proposal is None or proposal.target_binding is None:
        raise GameLifecycleError("Stratagem target proposal was not prevalidated.")
    decisions.event_log.append(
        "stratagem_target_proposal_accepted",
        {
            "request_id": result.request_id,
            "result_id": result.result_id,
            "proposal": proposal.to_payload(),
        },
    )
    return _apply_stratagem_use(
        state=state,
        result=result,
        decisions=decisions,
        context=proposal.context,
        catalog_record=proposal.catalog_record,
        target_binding=proposal.target_binding,
        effect_selection=proposal.effect_selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        stratagem_handler_registry=stratagem_handler_registry,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
    )


def is_stratagem_placement_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem placement proposal check requires a request.")
    if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    return proposal_request is not None and _proposal_request_is_rapid_ingress(proposal_request)


def invalid_stratagem_placement_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(state, "Stratagem placement proposal selected invalid option.", "malformed")
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not _proposal_request_is_rapid_ingress(proposal_request):
        return _invalid(state, "Malformed stratagem placement proposal request.", "malformed")
    submitted = _placement_proposal_from_result_payload(result.payload)
    if submitted is None:
        return _invalid(state, "Malformed stratagem placement proposal payload.", "malformed")
    validation = submitted.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Stratagem placement proposal context drift.",
            payload=validate_json_value(
                {"proposal_validation": validate_json_value(validation.to_payload())}
            ),
        )
    reserve_state = state.reserve_state_for_unit(submitted.unit_instance_id)
    if reserve_state is None or reserve_state.status is not ReserveStatus.IN_RESERVES:
        return _invalid(state, "Stratagem placement proposal reserve drift.", "reserve_drift")
    return None


def apply_stratagem_placement_proposal(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not _proposal_request_is_rapid_ingress(proposal_request):
        raise GameLifecycleError("Stratagem placement proposal was not prevalidated.")
    submitted = _placement_proposal_from_result_payload(result.payload)
    if submitted is None:
        raise GameLifecycleError("Stratagem placement proposal payload was not prevalidated.")
    return _apply_rapid_ingress_placement(
        state=state,
        decisions=decisions,
        result=result,
        proposal_request=proposal_request,
        submitted=submitted,
        ruleset_descriptor=ruleset_descriptor,
    )


def is_heroic_intervention_charge_move_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Heroic Intervention proposal check requires a request.")
    if request.decision_type != MOVEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    return (
        proposal_request is not None
        and proposal_request.context is not None
        and proposal_request.context.get("stratagem_handler_id")
        == CORE_HEROIC_INTERVENTION_HANDLER_ID
    )


def invalid_heroic_intervention_charge_move_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if result.selected_option_id != PARAMETERIZED_DECISION_OPTION_ID:
        return _invalid(state, "Heroic Intervention proposal selected invalid option.", "malformed")
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not is_heroic_intervention_charge_move_request(request):
        return _invalid(state, "Malformed Heroic Intervention proposal request.", "malformed")
    submitted = _heroic_intervention_charge_move_from_result_payload(result.payload)
    if submitted is None:
        return _invalid(state, "Malformed Heroic Intervention proposal payload.", "malformed")
    validation = submitted.validation_result_for_request(proposal_request)
    if not validation.is_valid:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Heroic Intervention proposal context drift.",
            payload={"proposal_validation": validate_json_value(validation.to_payload())},
        )
    request_error = _heroic_intervention_charge_move_request_error(
        state=state,
        proposal_request=proposal_request,
        proposal=submitted,
    )
    if request_error is not None:
        return _invalid(
            state,
            "Heroic Intervention charge move is not legal.",
            request_error,
        )
    return None


def apply_heroic_intervention_charge_move(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    proposal_request = _movement_proposal_request_from_payload(request.payload)
    if proposal_request is None or not is_heroic_intervention_charge_move_request(request):
        raise GameLifecycleError("Heroic Intervention proposal was not prevalidated.")
    proposal = _heroic_intervention_charge_move_from_result_payload(result.payload)
    if proposal is None:
        raise GameLifecycleError("Heroic Intervention proposal payload was not prevalidated.")
    if proposal.is_no_move_choice:
        decisions.event_log.append(
            "heroic_intervention_charge_move_declined",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.CHARGE.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
            },
        )
        return None
    if proposal.witness is None:
        raise GameLifecycleError("Validated Heroic Intervention proposal requires a witness.")
    use_record = _stratagem_use_from_proposal_context(proposal_request)
    maximum_distance = _heroic_intervention_maximum_distance(proposal_request)
    scenario = _battlefield_scenario_for_stratagem(state)
    unit_placement = scenario.battlefield_state.unit_placement_by_id(proposal.unit_instance_id)
    resolution = resolve_charge_move(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=unit_placement,
        selected_target_unit_instance_ids=proposal.charge_target_unit_instance_ids,
        maximum_distance_inches=maximum_distance,
        path_witness=proposal.witness,
        hover_mode_states=tuple(state.hover_mode_states),
    )
    violation = charge_move_violation_code(
        resolution=resolution,
        ruleset_descriptor=ruleset_descriptor,
        maximum_distance_inches=maximum_distance,
    )
    if violation is not None:
        message = charge_move_invalid_message(violation)
        invalid_validation = ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code=violation,
            message=message,
            field=charge_move_violation_field(violation),
        )
        payload = validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "heroic_intervention_charge_move_invalid",
                "unit_instance_id": resolution.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal_request.request_id,
                "violation_code": violation,
                "proposal_validation": invalid_validation.to_payload(),
                **resolution.movement_payload,
            }
        )
        decisions.event_log.append("heroic_intervention_charge_move_invalid", payload)
        retry_request = _request_heroic_intervention_charge_move_retry(
            state=state,
            decisions=decisions,
            proposal_request=proposal_request,
            rejected_result=result,
        )
        return LifecycleStatus.invalid(
            stage=state.stage,
            message=message,
            payload={
                "phase": BattlePhase.CHARGE.value,
                "phase_body_status": "heroic_intervention_charge_move_invalid",
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "unit_instance_id": resolution.unit_instance_id,
                "movement_phase_action": CHARGE_MOVE_ACTION,
                "violation_code": violation,
                "next_request_id": retry_request.request_id,
                "proposal_validation": validate_json_value(invalid_validation.to_payload()),
            },
        )
    transition_batch = resolution.transition_batch(before=unit_placement)
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Heroic Intervention requires battlefield_state.")
    state.replace_battlefield_state(
        battlefield_state.with_unit_placement(resolution.attempted_placement)
    )
    effect = PersistingEffect(
        effect_id=f"{result.result_id}:heroic-intervention:fights-first",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(proposal.unit_instance_id,),
        started_battle_round=state.battle_round,
        started_phase=BattlePhase.CHARGE,
        expiration=EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=state.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": "charge_grants_fights_first",
            "source_rule_id": use_record.source_id,
            "stratagem_use_id": use_record.use_id,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "heroic_intervention_charge_move_completed",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "proposal_request_id": proposal_request.request_id,
            "transition_batch": transition_batch.to_payload(),
            "persisting_effect": effect.to_payload(),
            **resolution.movement_payload,
        },
    )
    return None


def _request_heroic_intervention_charge_move_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    use_record = _stratagem_use_from_proposal_context(proposal_request)
    context = _heroic_intervention_request_context(proposal_request)
    reachable = _heroic_intervention_requested_reachable_distances(proposal_request)
    decisions.event_log.append(
        "heroic_intervention_charge_move_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "mode": _heroic_intervention_mode_from_request(proposal_request),
            "charge_roll_state": context["charge_roll_state"],
            "maximum_distance_inches": _heroic_intervention_maximum_distance(proposal_request),
            "reachable_target_unit_instance_ids": list(reachable),
            "reachable_target_distances_inches": reachable,
            "request_id": request.request_id,
            "previous_proposal_request_id": proposal_request.request_id,
            "rejected_result_id": rejected_result.result_id,
            "phase_body_status": "heroic_intervention_charge_move_proposal_required",
        },
    )
    return request
