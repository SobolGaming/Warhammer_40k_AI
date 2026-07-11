# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_generic_metadata import (
    CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND,
    SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
    companion_effect_selections_for_binding,
    controlled_objective_effect_selections_for_binding,
)
from warhammer40k_core.engine.stratagems_model import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE, STRATAGEM_PROPOSAL_PAYLOAD_KIND, DECLINE_STRATAGEM_WINDOW_OPTION_ID, DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE, UNSUPPORTED_STRATAGEM_HANDLER_PREFIX, CORE_COMMAND_REROLL_HANDLER_ID, CORE_INSANE_BRAVERY_HANDLER_ID, CORE_RAPID_INGRESS_HANDLER_ID, CORE_NEW_ORDERS_HANDLER_ID, CORE_FIRE_OVERWATCH_HANDLER_ID, CORE_GO_TO_GROUND_HANDLER_ID, CORE_EXPLOSIVES_HANDLER_ID, CORE_SMOKESCREEN_HANDLER_ID, CORE_HEROIC_INTERVENTION_HANDLER_ID, CORE_COUNTEROFFENSIVE_HANDLER_ID, CORE_CRUSHING_IMPACT_HANDLER_ID, CORE_EPIC_CHALLENGE_HANDLER_ID, GENERIC_INGRESS_MOVE_HANDLER_ID, GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID, GENERIC_RULE_IR_STRATAGEM_HANDLER_ID, COMMAND_REROLL_DICE_CONTEXT_KEY, COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY, INSANE_BRAVERY_TARGET_POLICY_ID, RAPID_INGRESS_TARGET_POLICY_ID, STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID, NEW_ORDERS_TARGET_POLICY_ID, FIRE_OVERWATCH_TARGET_POLICY_ID, GO_TO_GROUND_TARGET_POLICY_ID, SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID, EXPLOSIVES_TARGET_POLICY_ID, SMOKESCREEN_TARGET_POLICY_ID, HEROIC_INTERVENTION_TARGET_POLICY_ID, COUNTEROFFENSIVE_TARGET_POLICY_ID, CRUSHING_IMPACT_TARGET_POLICY_ID, EPIC_CHALLENGE_TARGET_POLICY_ID, SELECTED_TO_MOVE_TARGET_POLICY_ID, JUST_FELL_BACK_UNIT_TARGET_POLICY_ID, JUST_SHOT_UNIT_TARGET_POLICY_ID, ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID, EXPLOSIVES_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_MODEL_CONTEXT_KEY, EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND, HEROIC_INTERVENTION_MODE_INTO_THE_FRAY, SELECTED_TARGET_UNIT_CONTEXT_KEY, SELECTED_TO_MOVE_UNIT_CONTEXT_KEY, JUST_FELL_BACK_UNIT_CONTEXT_KEY, JUST_SHOT_UNIT_CONTEXT_KEY, HIT_TARGET_UNIT_CONTEXT_KEY, DESTROYED_TARGET_UNIT_CONTEXT_KEY, DESTROYED_ENEMY_UNIT_CONTEXT_KEY, HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND, HIT_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND, ENGAGED_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY, FALL_BACK_UNIT_CONTEXT_KEY, FALL_BACK_MODE_CONTEXT_KEY, FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND, FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY, FIRE_OVERWATCH_MAX_RANGE_INCHES, HEROIC_INTERVENTION_TARGET_RANGE_INCHES, HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES, CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT, StratagemAvailabilityKind, StratagemCategory, StratagemTargetKind, StratagemUseRecordPayload, StratagemTimingDescriptorPayload, StratagemRestrictionPolicyPayload, StratagemTargetSpecPayload, StratagemDefinitionPayload, StratagemCatalogRecordPayload, StratagemEligibilityContextPayload, StratagemTargetBindingPayload, StratagemTargetProposalPayload, StratagemTimingDescriptor, StratagemRestrictionPolicy, StratagemTargetSpec, StratagemDefinition, StratagemCatalogRecord, StratagemCatalogIndex, StratagemEligibilityContext, StratagemTargetBinding, StratagemTargetProposal, StratagemUseRequest, StratagemUseRecord
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
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "_effect_selections_for_binding",
    "_request_stratagem_use_with_options",
    "_stratagem_use_options_for_records",
    "create_stratagem_target_proposal_decision_request",
    "create_stratagem_use_decision_request",
    "engaged_enemy_unit_effect_selection",
    "hit_enemy_unit_effect_selection",
    "is_stratagem_window_decline_result",
    "request_stratagem_target_proposal",
    "request_stratagem_use",
    "request_stratagem_use_from_index",
    "stratagem_decline_option",
    "stratagem_decline_payload",
    "stratagem_target_proposal_from_index",
    "stratagem_target_proposal_request_payload",
    "stratagem_use_options",
    "stratagem_use_options_for_handler_from_index",
    "stratagem_use_options_from_index",
    "stratagem_window_context_from_request",
    "stratagem_window_decline_allowed",
    "stratagem_window_decline_event_payload",
    "stratagem_window_declined_for_context",
    "visible_enemy_unit_effect_selection",
)


def request_stratagem_use(
    *,
    state: GameState,
    decisions: DecisionController,
    catalog_records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem use requires a DecisionController.")
    records = _validate_catalog_records(catalog_records)
    options = _stratagem_use_options_for_records(
        state=state,
        records=records,
        context=context,
    )
    return _request_stratagem_use_with_options(
        state=state,
        decisions=decisions,
        context=context,
        options=options,
    )


def request_stratagem_use_from_index(
    *,
    state: GameState,
    decisions: DecisionController,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem use requires a DecisionController.")
    options = stratagem_use_options_from_index(
        state=state,
        index=index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    return _request_stratagem_use_with_options(
        state=state,
        decisions=decisions,
        context=context,
        options=options,
    )


def _request_stratagem_use_with_options(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    options: tuple[DecisionOption, ...],
) -> LifecycleStatus:
    if not options:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="No stratagems are available for this timing window.",
            payload={"player_id": context.player_id, "trigger_kind": context.trigger_kind.value},
        )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=options,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"pending_request_id": request.request_id},
    )


def create_stratagem_use_decision_request(
    *,
    state: GameState,
    context: StratagemEligibilityContext,
    options: tuple[DecisionOption, ...],
    request_id: str | None = None,
    payload_extra: dict[str, JsonValue] | None = None,
) -> DecisionRequest:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem decision requires an eligibility context.")
    extra = {} if payload_extra is None else payload_extra
    if type(extra) is not dict:
        raise GameLifecycleError("Stratagem decision payload_extra must be a dictionary.")
    return DecisionRequest(
        request_id=state.next_decision_request_id()
        if request_id is None
        else _validate_identifier("request_id", request_id),
        decision_type=STRATAGEM_DECISION_TYPE,
        actor_id=context.player_id,
        payload=validate_json_value(
            {
                "stratagem_context": context.to_payload(),
                "finite": True,
                **extra,
            }
        ),
        options=options,
    )


def stratagem_decline_option() -> DecisionOption:
    return DecisionOption(
        option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        label="Decline Stratagem Window",
        payload=stratagem_decline_payload(),
    )


def stratagem_decline_payload() -> JsonValue:
    return validate_json_value({"submission_kind": DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND})


def is_stratagem_window_decline_result(result: DecisionResult) -> bool:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem decline check requires a DecisionResult.")
    return (
        result.decision_type in (STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE)
        and isinstance(result.payload, dict)
        and result.payload.get("submission_kind") == DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND
    )


def stratagem_window_decline_allowed(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem decline allowance requires a DecisionRequest.")
    if not is_stratagem_window_decline_result(result):
        return False
    if request.decision_type == STRATAGEM_DECISION_TYPE:
        return any(
            option.option_id == DECLINE_STRATAGEM_WINDOW_OPTION_ID for option in request.options
        )
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        if not isinstance(request.payload, dict):
            return False
        return request.payload.get("declinable") is True
    return False


def stratagem_window_context_from_request(request: DecisionRequest) -> StratagemEligibilityContext:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Stratagem window context requires a DecisionRequest.")
    if request.decision_type == STRATAGEM_DECISION_TYPE:
        if not isinstance(request.payload, dict):
            raise GameLifecycleError("Stratagem decision request payload must be an object.")
        context_payload = request.payload.get("stratagem_context")
        if not isinstance(context_payload, dict):
            raise GameLifecycleError("Stratagem decision request is missing context.")
        try:
            return StratagemEligibilityContext.from_payload(
                cast(StratagemEligibilityContextPayload, context_payload)
            )
        except KeyError as exc:
            raise GameLifecycleError("Stratagem decision context payload is malformed.") from exc
    if request.decision_type == STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        proposal = _proposal_from_request_payload(request.payload)
        if proposal is None:
            raise GameLifecycleError("Stratagem proposal request is missing proposal context.")
        return proposal.context
    raise GameLifecycleError("DecisionRequest is not a Stratagem window request.")


def stratagem_window_decline_event_payload(
    *,
    request: DecisionRequest,
    result: DecisionResult,
) -> JsonValue:
    if not is_stratagem_window_decline_result(result):
        raise GameLifecycleError("Stratagem decline event requires a decline result.")
    context = stratagem_window_context_from_request(request)
    return validate_json_value(
        {
            "game_id": context.game_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": context.phase.value,
            "active_player_id": context.active_player_id,
            "trigger_kind": context.trigger_kind.value,
            "timing_window_id": context.timing_window_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "decision_type": result.decision_type,
        }
    )


def stratagem_window_declined_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem decline lookup requires a DecisionController.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem decline lookup requires an eligibility context.")
    for event in decisions.event_log.records:
        if event.event_type != STRATAGEM_WINDOW_DECLINED_EVENT_TYPE:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Stratagem decline event payload must be an object.")
        payload = event.payload
        _require_decline_event_fields(payload)
        if (
            payload["game_id"] == context.game_id
            and payload["player_id"] == context.player_id
            and payload["battle_round"] == context.battle_round
            and payload["phase"] == context.phase.value
            and payload["active_player_id"] == context.active_player_id
            and payload["trigger_kind"] == context.trigger_kind.value
            and payload["timing_window_id"] == context.timing_window_id
        ):
            return True
    return False


def stratagem_use_options(
    *,
    state: GameState,
    catalog_records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
) -> tuple[DecisionOption, ...]:
    records = _validate_catalog_records(catalog_records)
    return _stratagem_use_options_for_records(state=state, records=records, context=context)


def stratagem_use_options_from_index(
    *,
    state: GameState,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> tuple[DecisionOption, ...]:
    if type(index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Stratagem options require a StratagemCatalogIndex.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem options require an eligibility context.")
    return _stratagem_use_options_for_records(
        state=state,
        records=index.records_for(context.trigger_kind),
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )


def stratagem_use_options_for_handler_from_index(
    *,
    state: GameState,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    handler_id: str,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> tuple[DecisionOption, ...]:
    if type(index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Stratagem options require a StratagemCatalogIndex.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem options require an eligibility context.")
    requested_handler_id = _validate_identifier("handler_id", handler_id)
    return _stratagem_use_options_for_records(
        state=state,
        records=tuple(
            record
            for record in index.records_for(context.trigger_kind)
            if record.definition.handler_id == requested_handler_id
        ),
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )


def hit_enemy_unit_effect_selection(unit_instance_id: str) -> JsonValue:
    return {
        "effect_selection_kind": HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        HIT_ENEMY_UNIT_CONTEXT_KEY: _validate_identifier(
            HIT_ENEMY_UNIT_CONTEXT_KEY,
            unit_instance_id,
        ),
    }


def engaged_enemy_unit_effect_selection(unit_instance_id: str) -> JsonValue:
    return {
        "effect_selection_kind": ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        ENGAGED_ENEMY_UNIT_CONTEXT_KEY: _validate_identifier(
            ENGAGED_ENEMY_UNIT_CONTEXT_KEY,
            unit_instance_id,
        ),
    }


def visible_enemy_unit_effect_selection(unit_instance_id: str) -> JsonValue:
    return {
        "effect_selection_kind": VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND,
        VISIBLE_ENEMY_UNIT_CONTEXT_KEY: _validate_identifier(
            VISIBLE_ENEMY_UNIT_CONTEXT_KEY,
            unit_instance_id,
        ),
    }


def _stratagem_use_options_for_records(
    *,
    state: GameState,
    records: tuple[StratagemCatalogRecord, ...],
    context: StratagemEligibilityContext,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> tuple[DecisionOption, ...]:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem options require an eligibility context.")
    options: list[DecisionOption] = []
    for record in records:
        if not _record_can_enumerate_targets(
            state=state,
            record=record,
            context=context,
        ):
            continue
        definition = record.definition
        if not definition.target_spec.enumerable:
            continue
        bindings = _enumerated_target_bindings(
            state=state,
            player_id=context.player_id,
            definition=definition,
            context=context,
        )
        for binding in bindings:
            if (
                _restriction_violation(
                    state=state,
                    player_id=context.player_id,
                    definition=definition,
                    context=context,
                    target_binding=binding,
                )
                is not None
            ):
                continue
            for effect_selection in _effect_selections_for_binding(
                state=state,
                definition=definition,
                context=context,
                target_binding=binding,
            ):
                if (
                    _stratagem_unavailable_reason(
                        state=state,
                        record=record,
                        context=context,
                        target_binding=binding,
                        effect_selection=effect_selection,
                        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
                    )
                    is not None
                ):
                    continue
                options.append(
                    _stratagem_decision_option(
                        record=record,
                        context=context,
                        target_binding=binding,
                        effect_selection=effect_selection,
                    )
                )
    return tuple(sorted(options, key=lambda option: option.option_id))


def _record_can_enumerate_targets(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
) -> bool:
    unavailable = _stratagem_unavailable_reason(
        state=state,
        record=record,
        context=context,
        target_binding=None,
    )
    return unavailable is None or unavailable == "insufficient_command_points"


def _effect_selections_for_binding(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
) -> tuple[JsonValue, ...]:
    payload = definition.effect_payload
    if not isinstance(payload, dict):
        return (None,)
    selection_kind = payload.get("effect_selection_kind")
    if selection_kind == HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        hit_target_ids = _hit_target_unit_ids_or_empty(context)
        return tuple(hit_enemy_unit_effect_selection(unit_id) for unit_id in hit_target_ids)
    if selection_kind == ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        required_keywords = _effect_selection_required_target_keywords(payload)
        if required_keywords and not _target_unit_has_all_keywords(
            state=state,
            target_binding=target_binding,
            required_keywords=required_keywords,
        ):
            return (None,)
        engaged_enemy_ids = _engaged_enemy_unit_ids_or_empty(context)
        if not engaged_enemy_ids:
            return ()
        return tuple(engaged_enemy_unit_effect_selection(unit_id) for unit_id in engaged_enemy_ids)
    if selection_kind == VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        source_context_key = payload.get(VISIBLE_ENEMY_SOURCE_UNIT_CONTEXT_KEY)
        if source_context_key != TARGET_BINDING_UNIT_CONTEXT_KEY:
            raise GameLifecycleError(
                "Visible enemy effect selection requires target binding source."
            )
        source_unit_id = target_binding.target_unit_instance_id
        if source_unit_id is None:
            return ()
        range_inches = payload.get(VISIBLE_ENEMY_RANGE_INCHES_KEY)
        if type(range_inches) is not int or range_inches <= 0:
            raise GameLifecycleError("Visible enemy effect selection requires positive range.")
        if state.battlefield_state is None:
            return ()
        from warhammer40k_core.engine.stratagems_geometry import visible_enemy_unit_ids_for_source

        return tuple(
            visible_enemy_unit_effect_selection(unit_id)
            for unit_id in visible_enemy_unit_ids_for_source(
                state=state,
                player_id=context.player_id,
                source_unit_instance_id=source_unit_id,
                range_inches=range_inches,
            )
        )
    if selection_kind == SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND:
        return companion_effect_selections_for_binding(
            state=state,
            definition=definition,
            context=context,
            target_binding=target_binding,
        )
    if selection_kind == CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND:
        return controlled_objective_effect_selections_for_binding(
            state=state,
            context=context,
            target_binding=target_binding,
        )
    if selection_kind is not None:
        raise GameLifecycleError("Unsupported stratagem effect selection kind.")
    return (None,)


def request_stratagem_target_proposal(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: StratagemTargetProposal,
    allow_decline: bool = False,
) -> LifecycleStatus:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Stratagem proposal requires a DecisionController.")
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    if proposal_request.target_binding is not None:
        raise GameLifecycleError("Stratagem proposal request cannot include a target binding.")
    violation = _stratagem_unavailable_reason(
        state=state,
        record=proposal_request.catalog_record,
        context=proposal_request.context,
        target_binding=None,
    )
    if violation is not None:
        return LifecycleStatus.unsupported(
            stage=state.stage,
            message="Stratagem target proposal is not available for this timing window.",
            payload={
                "player_id": proposal_request.player_id,
                "stratagem_id": proposal_request.stratagem_id,
                "unavailable_reason": violation,
            },
        )
    request = create_stratagem_target_proposal_decision_request(
        state=state,
        proposal_request=proposal_request,
        allow_decline=allow_decline,
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={"pending_request_id": request.request_id},
    )


def create_stratagem_target_proposal_decision_request(
    *,
    state: GameState,
    proposal_request: StratagemTargetProposal,
    allow_decline: bool = False,
) -> DecisionRequest:
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    request_id = state.next_decision_request_id()
    return DecisionRequest(
        request_id=request_id,
        decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.player_id,
        payload=stratagem_target_proposal_request_payload(
            proposal_request,
            request_id=request_id,
            decision_type=STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE,
            actor_id=proposal_request.player_id,
            allow_decline=allow_decline,
        ),
        options=(parameterized_decision_option(),),
    )


def stratagem_target_proposal_request_payload(
    proposal_request: StratagemTargetProposal,
    *,
    request_id: str,
    decision_type: str,
    actor_id: str,
    allow_decline: bool = False,
) -> JsonValue:
    if type(proposal_request) is not StratagemTargetProposal:
        raise GameLifecycleError("Stratagem proposal request must be a StratagemTargetProposal.")
    validated_request_id = _validate_identifier("Stratagem proposal request_id", request_id)
    validated_decision_type = _validate_identifier(
        "Stratagem proposal decision_type",
        decision_type,
    )
    validated_actor_id = _validate_identifier("Stratagem proposal actor_id", actor_id)
    if validated_decision_type != STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE:
        raise GameLifecycleError("Stratagem proposal decision_type is unsupported.")
    if validated_actor_id != proposal_request.player_id:
        raise GameLifecycleError("Stratagem proposal actor_id must match proposal player.")
    if type(allow_decline) is not bool:
        raise GameLifecycleError("Stratagem proposal decline allowance must be a bool.")
    proposal_payload = validate_json_value(proposal_request.to_payload())
    if not isinstance(proposal_payload, dict):
        raise GameLifecycleError("Stratagem proposal payload must be an object.")
    payload: dict[str, JsonValue] = {
        "proposal_request": {
            "request_id": validated_request_id,
            "decision_type": validated_decision_type,
            "actor_id": validated_actor_id,
            **proposal_payload,
        }
    }
    if allow_decline:
        payload["declinable"] = True
    return validate_json_value(payload)


def stratagem_target_proposal_from_index(
    *,
    state: GameState,
    index: StratagemCatalogIndex,
    context: StratagemEligibilityContext,
    handler_id: str,
) -> StratagemTargetProposal | None:
    if type(index) is not StratagemCatalogIndex:
        raise GameLifecycleError("Stratagem target proposal requires a StratagemCatalogIndex.")
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Stratagem target proposal requires an eligibility context.")
    requested_handler_id = _validate_identifier("handler_id", handler_id)
    matches: list[StratagemCatalogRecord] = []
    for record in index.records_for(context.trigger_kind):
        definition = record.definition
        if definition.handler_id != requested_handler_id:
            continue
        if definition.target_spec.enumerable:
            continue
        if _record_is_available_for_context(state=state, record=record, context=context):
            matches.append(record)
    if not matches:
        return None
    if len(matches) > 1:
        raise GameLifecycleError("Stratagem target proposal index matched multiple records.")
    return StratagemTargetProposal.for_request(context=context, catalog_record=matches[0])
