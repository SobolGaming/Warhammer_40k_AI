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
    from warhammer40k_core.engine.stratagems_tactical_secondaries import _apply_new_orders_handler
    from warhammer40k_core.engine.stratagems_fire_overwatch import _apply_fire_overwatch_handler
    from warhammer40k_core.engine.stratagems_effect_handlers import _apply_go_to_ground_handler, _apply_smokescreen_handler, _apply_explosives_handler, apply_explosives_mortal_wound_feel_no_pain_decision, _emit_explosives_resolved, _apply_counteroffensive_handler, _apply_crushing_impact_handler, _apply_epic_challenge_handler, _apply_heroic_intervention_handler, _apply_stratagem_mortal_wounds, _heroic_intervention_reachable_target_distances, _enemy_unit_ids_for_player, _closest_unit_distance_inches, _unit_made_charge_move
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "_apply_command_reroll_handler",
    "_apply_force_desperate_escape_handler",
    "_apply_generic_rule_ir_stratagem_handler",
    "_apply_ingress_move_handler",
    "_apply_insane_bravery_handler",
    "_apply_rapid_ingress_handler",
    "_apply_supported_stratagem_handler",
    "_command_reroll_request_context",
    "_generic_rule_ir_from_stratagem_payload",
    "_ingress_move_effect_payload",
    "_stratagem_use_from_proposal_context",
    "_validate_supported_stratagem_handler_available",
    "_validate_supported_stratagem_handler_preflight",
    "apply_command_reroll_decision",
    "invalid_command_reroll_decision_status",
    "is_command_reroll_decision_request",
)


def _stratagem_use_from_proposal_context(
    proposal_request: MovementProposalRequest,
) -> StratagemUseRecord:
    context = proposal_request.context or {}
    use_payload = context.get("stratagem_use")
    if not isinstance(use_payload, dict):
        raise GameLifecycleError("Rapid Ingress placement context requires stratagem_use.")
    return StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, use_payload))


def _apply_supported_stratagem_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
) -> None:
    if definition.handler_id == "record_only":
        return
    if stratagem_handler_registry is not None:
        from warhammer40k_core.engine.faction_content.stratagem_handlers import (
            StratagemHandlerContext,
            StratagemHandlerExecutionStatus,
            StratagemHandlerRegistry,
        )

        if type(stratagem_handler_registry) is not StratagemHandlerRegistry:
            raise GameLifecycleError("Stratagem handler registry is invalid.")
        if stratagem_handler_registry.has_handler(definition.handler_id):
            handler_result = stratagem_handler_registry.execute(
                handler_id=definition.handler_id,
                context=StratagemHandlerContext(
                    state=state,
                    decisions=decisions,
                    result=result,
                    eligibility_context=context,
                    definition=definition,
                    target_binding=target_binding,
                    use_record=use_record,
                    ruleset_descriptor=ruleset_descriptor,
                    army_catalog=army_catalog,
                ),
            )
            if handler_result.status is not StratagemHandlerExecutionStatus.APPLIED:
                if handler_result.reason is None:
                    raise GameLifecycleError("Stratagem handler failed without reason.")
                raise GameLifecycleError(f"Stratagem handler failed: {handler_result.reason}.")
            decisions.event_log.append("stratagem_handler_applied", handler_result.to_payload())
            return
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        _apply_command_reroll_handler(
            state=state,
            decisions=decisions,
            context=context,
            definition=definition,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_INSANE_BRAVERY_HANDLER_ID:
        _apply_insane_bravery_handler(
            state=state,
            decisions=decisions,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_RAPID_INGRESS_HANDLER_ID:
        _apply_rapid_ingress_handler(
            state=state,
            decisions=decisions,
            result=result,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == GENERIC_INGRESS_MOVE_HANDLER_ID:
        _apply_ingress_move_handler(
            state=state,
            decisions=decisions,
            result=result,
            context=context,
            definition=definition,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID:
        _apply_force_desperate_escape_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_NEW_ORDERS_HANDLER_ID:
        _apply_new_orders_handler(
            state=state,
            decisions=decisions,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_FIRE_OVERWATCH_HANDLER_ID:
        _apply_fire_overwatch_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
        )
        return
    if definition.handler_id == CORE_GO_TO_GROUND_HANDLER_ID:
        _apply_go_to_ground_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_EXPLOSIVES_HANDLER_ID:
        _apply_explosives_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_SMOKESCREEN_HANDLER_ID:
        _apply_smokescreen_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_COUNTEROFFENSIVE_HANDLER_ID:
        _apply_counteroffensive_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
        )
        return
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID:
        _apply_crushing_impact_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_EPIC_CHALLENGE_HANDLER_ID:
        _apply_epic_challenge_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == CORE_HEROIC_INTERVENTION_HANDLER_ID:
        _apply_heroic_intervention_handler(
            state=state,
            decisions=decisions,
            result=result,
            context=context,
            definition=definition,
            target_binding=target_binding,
            use_record=use_record,
        )
        return
    if definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        _apply_generic_rule_ir_stratagem_handler(
            state=state,
            decisions=decisions,
            context=context,
            target_binding=target_binding,
            definition=definition,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
        )
        return
    raise GameLifecycleError("Stratagem handler is not supported.")


def _validate_supported_stratagem_handler_available(
    *,
    definition: StratagemDefinition,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
) -> None:
    if definition.handler_id == "record_only":
        return
    if stratagem_handler_registry is not None:
        from warhammer40k_core.engine.faction_content.stratagem_handlers import (
            StratagemHandlerRegistry,
        )

        if type(stratagem_handler_registry) is not StratagemHandlerRegistry:
            raise GameLifecycleError("Stratagem handler registry is invalid.")
        if stratagem_handler_registry.has_handler(definition.handler_id):
            return
    if definition.handler_id in {
        CORE_COMMAND_REROLL_HANDLER_ID,
        CORE_INSANE_BRAVERY_HANDLER_ID,
        CORE_RAPID_INGRESS_HANDLER_ID,
        CORE_NEW_ORDERS_HANDLER_ID,
        CORE_FIRE_OVERWATCH_HANDLER_ID,
        CORE_GO_TO_GROUND_HANDLER_ID,
        CORE_EXPLOSIVES_HANDLER_ID,
        CORE_SMOKESCREEN_HANDLER_ID,
        CORE_COUNTEROFFENSIVE_HANDLER_ID,
        CORE_CRUSHING_IMPACT_HANDLER_ID,
        CORE_EPIC_CHALLENGE_HANDLER_ID,
        CORE_HEROIC_INTERVENTION_HANDLER_ID,
        GENERIC_INGRESS_MOVE_HANDLER_ID,
        GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID,
        GENERIC_RULE_IR_STRATAGEM_HANDLER_ID,
    }:
        return
    raise GameLifecycleError("Stratagem handler is not supported.")


def _validate_supported_stratagem_handler_preflight(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    stratagem_handler_registry: StratagemHandlerRegistry | None,
) -> None:
    _validate_supported_stratagem_handler_available(
        definition=definition,
        stratagem_handler_registry=stratagem_handler_registry,
    )
    if definition.handler_id == "record_only" or stratagem_handler_registry is None:
        return
    from warhammer40k_core.engine.faction_content.stratagem_handlers import (
        StratagemHandlerContext,
        StratagemHandlerExecutionStatus,
        StratagemHandlerRegistry,
    )

    if type(stratagem_handler_registry) is not StratagemHandlerRegistry:
        raise GameLifecycleError("Stratagem handler registry is invalid.")
    if not stratagem_handler_registry.has_handler(definition.handler_id):
        return
    validation_result = stratagem_handler_registry.validate(
        handler_id=definition.handler_id,
        context=StratagemHandlerContext(
            state=state,
            decisions=decisions,
            result=result,
            eligibility_context=context,
            definition=definition,
            target_binding=target_binding,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        ),
    )
    if validation_result.status is not StratagemHandlerExecutionStatus.APPLIED:
        if validation_result.reason is None:
            raise GameLifecycleError("Stratagem handler validation failed without reason.")
        raise GameLifecycleError(
            f"Stratagem handler validation failed: {validation_result.reason}."
        )


def _generic_rule_ir_from_stratagem_payload(effect_payload: JsonValue) -> object:
    from warhammer40k_core.engine.rule_execution import rule_ir_from_execution_payload

    return rule_ir_from_execution_payload(effect_payload)


def _apply_generic_rule_ir_stratagem_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
) -> None:
    from warhammer40k_core.engine.rule_execution import (
        RuleExecutionContext,
        RuleExecutionStatus,
        execute_rule_ir,
        rule_ir_from_execution_payload,
    )

    rule_ir = rule_ir_from_execution_payload(definition.effect_payload)
    result = execute_rule_ir(
        rule_ir=rule_ir,
        context=RuleExecutionContext(
            game_id=context.game_id,
            player_id=context.player_id,
            battle_round=context.battle_round,
            phase=context.phase,
            active_player_id=context.active_player_id,
            timing_window_id=context.timing_window_id,
            source_unit_instance_id=_single_target_unit_id_or_none(use_record),
            target_unit_instance_ids=use_record.targeted_unit_instance_ids,
            target_player_id=target_binding.target_player_id,
            trigger_payload=_generic_stratagem_rule_trigger_payload(
                context=context,
                definition=definition,
                use_record=use_record,
            ),
            state=state,
            event_log=decisions.event_log,
        ),
    )
    if result.status is not RuleExecutionStatus.APPLIED:
        if result.reason is None:
            raise GameLifecycleError("Generic Stratagem rule execution failed without reason.")
        raise GameLifecycleError(f"Generic Stratagem rule execution failed: {result.reason}.")
    if _rule_execution_result_grants_out_of_phase_shoot(result.effect_payloads):
        _request_generic_out_of_phase_shooting(
            state=state,
            decisions=decisions,
            context=context,
            definition=definition,
            use_record=use_record,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
        )


def _single_target_unit_id_or_none(use_record: StratagemUseRecord) -> str | None:
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic Stratagem source binding requires use record.")
    if len(use_record.targeted_unit_instance_ids) == 1:
        return use_record.targeted_unit_instance_ids[0]
    return None


def _generic_stratagem_rule_trigger_payload(
    *,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
) -> JsonValue:
    if type(context) is not StratagemEligibilityContext:
        raise GameLifecycleError("Generic Stratagem trigger payload requires context.")
    if type(definition) is not StratagemDefinition:
        raise GameLifecycleError("Generic Stratagem trigger payload requires definition.")
    if type(use_record) is not StratagemUseRecord:
        raise GameLifecycleError("Generic Stratagem trigger payload requires use record.")
    payload: dict[str, JsonValue] = {}
    if isinstance(context.trigger_payload, dict):
        payload.update(context.trigger_payload)
    elif context.trigger_payload is not None:
        payload["source_trigger_payload"] = context.trigger_payload
    payload.update(
        {
            "stratagem_id": definition.stratagem_id,
            "stratagem_use_id": use_record.use_id,
            "effect_selection": use_record.effect_selection,
            "stratagem_context": validate_json_value(context.to_payload()),
        }
    )
    return validate_json_value(payload)


def _rule_execution_result_grants_out_of_phase_shoot(
    effect_payloads: tuple[dict[str, JsonValue], ...],
) -> bool:
    if type(effect_payloads) is not tuple:
        raise GameLifecycleError("Generic Stratagem effect payloads must be a tuple.")
    granted = False
    for effect_payload in effect_payloads:
        effect = effect_payload.get("effect")
        if not isinstance(effect, dict):
            raise GameLifecycleError("Generic Stratagem effect payload requires effect object.")
        if effect.get("kind") != "grant_ability":
            continue
        parameters = effect.get("parameters")
        if not isinstance(parameters, list):
            raise GameLifecycleError("Generic Stratagem effect parameters must be a list.")
        for parameter in parameters:
            if not isinstance(parameter, dict):
                raise GameLifecycleError("Generic Stratagem effect parameter must be an object.")
            if parameter.get("key") == "ability" and parameter.get("value") == "out_of_phase_shoot":
                granted = True
    return granted


def _request_generic_out_of_phase_shooting(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None,
) -> None:
    shooting_unit_id = _single_target_unit_id_or_none(use_record)
    if shooting_unit_id is None:
        raise GameLifecycleError("Generic out-of-phase shooting requires one target unit.")
    enemy_unit_id = _just_shot_unit_id_or_none(context)
    if enemy_unit_id is None:
        raise GameLifecycleError("Generic out-of-phase shooting requires just-shot unit context.")
    request_out_of_phase_shooting_declaration(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=use_record.player_id,
        unit_instance_id=shooting_unit_id,
        parent_phase=context.phase,
        source_rule_id=definition.source_id,
        source_decision_request_id=use_record.request_id,
        source_decision_result_id=use_record.result_id,
        source_context=validate_json_value(
            {
                "source_kind": "generic_rule_ir_stratagem",
                "stratagem_use": use_record.to_payload(),
                "stratagem_context": context.to_payload(),
                "trigger_kind": context.trigger_kind.value,
                "trigger_payload": context.trigger_payload,
                "target_unit_ids": [enemy_unit_id],
            }
        ),
        target_unit_ids=(enemy_unit_id,),
        shooting_unit_selected_grant_hooks=shooting_unit_selected_grant_hooks,
    )
    decisions.event_log.append(
        "generic_stratagem_out_of_phase_shooting_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "shooting_unit_instance_id": shooting_unit_id,
            "target_unit_instance_id": enemy_unit_id,
        },
    )


def _apply_command_reroll_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    use_record: StratagemUseRecord,
) -> None:
    roll_state = _command_reroll_state(context)
    if roll_state.original_result.spec.actor_id != context.player_id:
        raise GameLifecycleError("Command Re-roll roll actor was not prevalidated.")
    roll_type = roll_state.original_result.spec.roll_type
    if _command_reroll_roll_class(roll_type) not in definition.eligible_roll_types:
        raise GameLifecycleError("Command Re-roll roll type was not prevalidated.")
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        raise GameLifecycleError("Command Re-roll forbidden roll was not prevalidated.")
    permission = _command_reroll_permission(
        source_id=use_record.source_id,
        context=context,
        roll_state=roll_state,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=f"{use_record.use_id}:command-reroll-request",
        actor_id=context.player_id,
        permission=permission,
        extra_payload={
            "command_reroll_context": validate_json_value(
                {
                    "stratagem_use": use_record.to_payload(),
                    "stratagem_context": context.to_payload(),
                    "roll_state": roll_state.to_payload(),
                }
            ),
        },
    )
    reroll_option_ids = tuple(
        option.option_id for option in request.options if option.option_id != "decline"
    )
    if len(reroll_option_ids) > 1:
        decisions.request_decision(request)
        decisions.event_log.append(
            "command_reroll_selection_requested",
            {
                "game_id": state.game_id,
                "player_id": context.player_id,
                "battle_round": context.battle_round,
                "phase": context.phase.value,
                "stratagem_use": use_record.to_payload(),
                "reroll_request": request.to_payload(),
            },
        )
        return
    if len(reroll_option_ids) != 1:
        raise GameLifecycleError("Command Re-roll must resolve exactly one reroll option.")
    reroll_result = DecisionResult.for_request(
        result_id=f"{use_record.use_id}:command-reroll-result",
        request=request,
        selected_option_id=reroll_option_ids[0],
    )
    updated_state = manager.resolve_reroll(
        roll_state,
        request=request,
        result=reroll_result,
        record_decision=False,
    )
    decisions.event_log.append(
        "command_reroll_resolved",
        {
            "game_id": state.game_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": context.phase.value,
            "stratagem_use": use_record.to_payload(),
            "reroll_request": request.to_payload(),
            "reroll_result": reroll_result.to_payload(),
            "updated_roll_state": updated_state.to_payload(),
        },
    )


def is_command_reroll_decision_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError("Command Re-roll request check requires a DecisionRequest.")
    if request.decision_type != DICE_REROLL_DECISION_TYPE:
        return False
    payload = request.payload
    return isinstance(payload, dict) and isinstance(payload.get("command_reroll_context"), dict)


def invalid_command_reroll_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if not is_command_reroll_decision_request(request):
        return _invalid(state, "Command Re-roll decision is malformed.", "malformed_request")
    try:
        result.validate_for_request(request)
        context, _use_record, _roll_state = _command_reroll_request_context(request)
    except (DecisionError, GameLifecycleError, KeyError):  # fmt: skip
        return _invalid(state, "Command Re-roll decision context is invalid.", "malformed")
    drift = _context_state_drift(state=state, context=context)
    if drift is not None:
        return _invalid(state, "Command Re-roll decision context drifted.", drift)
    return None


def apply_command_reroll_decision(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    context, use_record, roll_state = _command_reroll_request_context(request)
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    updated_state = manager.resolve_reroll(
        roll_state,
        request=request,
        result=result,
        record_decision=False,
    )
    decisions.event_log.append(
        "command_reroll_resolved",
        {
            "game_id": state.game_id,
            "player_id": context.player_id,
            "battle_round": context.battle_round,
            "phase": context.phase.value,
            "stratagem_use": use_record.to_payload(),
            "reroll_request": request.to_payload(),
            "reroll_result": result.to_payload(),
            "updated_roll_state": updated_state.to_payload(),
        },
    )


def _command_reroll_request_context(
    request: DecisionRequest,
) -> tuple[StratagemEligibilityContext, StratagemUseRecord, DiceRollState]:
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Command Re-roll decision payload must be an object.")
    context_payload = payload.get("command_reroll_context")
    if not isinstance(context_payload, dict):
        raise GameLifecycleError("Command Re-roll decision payload missing context.")
    stratagem_context_payload = context_payload.get("stratagem_context")
    use_record_payload = context_payload.get("stratagem_use")
    roll_state_payload = context_payload.get("roll_state")
    if not isinstance(stratagem_context_payload, dict):
        raise GameLifecycleError("Command Re-roll stratagem context is invalid.")
    if not isinstance(use_record_payload, dict):
        raise GameLifecycleError("Command Re-roll stratagem use is invalid.")
    if not isinstance(roll_state_payload, dict):
        raise GameLifecycleError("Command Re-roll roll state is invalid.")
    return (
        StratagemEligibilityContext.from_payload(
            cast(StratagemEligibilityContextPayload, stratagem_context_payload)
        ),
        StratagemUseRecord.from_payload(cast(StratagemUseRecordPayload, use_record_payload)),
        DiceRollState.from_payload(cast(DiceRollStatePayload, roll_state_payload)),
    )


def _apply_insane_bravery_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:insane-bravery-auto-pass",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=use_record.player_id,
        ),
        effect_payload={
            "effect_kind": "battle_shock_auto_pass",
            "stratagem_use_id": use_record.use_id,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "insane_bravery_auto_pass_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_rapid_ingress_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    reserve_state = _reserve_state_for_target(state=state, target_binding=target_binding)
    unit = _unit_for_reserve_state(state=state, reserve_state=reserve_state)
    placement_kinds = _reserve_placement_kinds_for_unit(reserve_state=reserve_state, unit=unit)
    proposal_kind = _reserve_proposal_kind(reserve_state)
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=context.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=reserve_state.unit_instance_id,
        proposal_kind=proposal_kind,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        placement_kinds=placement_kinds,
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": use_record.handler_id,
                    "stratagem_use": validate_json_value(use_record.to_payload()),
                    "reserve_state": validate_json_value(reserve_state.to_payload()),
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": context.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": proposal_kind.value,
            "placement_kinds": [kind.value for kind in placement_kinds],
            "request_id": request.request_id,
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "stratagem_use_id": use_record.use_id,
            "phase_body_status": "rapid_ingress_placement_proposal_required",
        },
    )


def _apply_ingress_move_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    reserve_state = _reserve_state_for_target(state=state, target_binding=target_binding)
    if reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES:
        raise GameLifecycleError("Ingress move requires a Strategic Reserves target.")
    _ingress_move_effect_payload(definition)
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=context.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.MOVEMENT.value,
        unit_instance_id=reserve_state.unit_instance_id,
        proposal_kind=ProposalKind.STRATEGIC_RESERVES,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        placement_kinds=(BattlefieldPlacementKind.STRATEGIC_RESERVES,),
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": GENERIC_INGRESS_MOVE_HANDLER_ID,
                    "stratagem_use": validate_json_value(use_record.to_payload()),
                    "reserve_state": validate_json_value(reserve_state.to_payload()),
                    "from_start_of_battle": True,
                    "mark_movement_phase_reinforcement_arrival": (
                        context.active_player_id == context.player_id
                    ),
                    "placement_scope": "strategic_reserves_only",
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "placement_proposal_requested",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": context.player_id,
            "phase": BattlePhase.MOVEMENT.value,
            "unit_instance_id": reserve_state.unit_instance_id,
            "proposal_kind": ProposalKind.STRATEGIC_RESERVES.value,
            "placement_kinds": [BattlefieldPlacementKind.STRATEGIC_RESERVES.value],
            "request_id": request.request_id,
            "source_decision_request_id": result.request_id,
            "source_decision_result_id": result.result_id,
            "stratagem_use_id": use_record.use_id,
            "phase_body_status": "ingress_move_placement_proposal_required",
        },
    )


def _ingress_move_effect_payload(definition: StratagemDefinition) -> dict[str, JsonValue]:
    payload = definition.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Ingress move effect payload must be an object.")
    if payload.get("effect_kind") != "ingress_move":
        raise GameLifecycleError("Ingress move effect payload has wrong effect kind.")
    if payload.get("from_start_of_battle") is not True:
        raise GameLifecycleError("Ingress move effect payload must allow start-of-battle use.")
    if payload.get("placement_scope") != "strategic_reserves_only":
        raise GameLifecycleError("Ingress move effect payload must be Strategic Reserves only.")
    return payload


def _apply_force_desperate_escape_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    fall_back_unit_id = _fall_back_unit_id_or_none(context)
    if fall_back_unit_id is None:
        raise GameLifecycleError("Force Desperate Escape requires Fall Back unit context.")
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:force-desperate-escape:{fall_back_unit_id}",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(fall_back_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=BattlePhase.MOVEMENT,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=BattlePhase.MOVEMENT,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND,
            "stratagem_use_id": use_record.use_id,
            "source_rule_id": use_record.source_id,
            "source_stratagem_id": use_record.stratagem_id,
            "forcing_unit_instance_id": target_unit_id,
            "fall_back_unit_instance_id": fall_back_unit_id,
            "required_fall_back_mode": "desperate_escape",
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "forced_fall_back_desperate_escape_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": BattlePhase.MOVEMENT.value,
            "active_player_id": context.active_player_id,
            "stratagem_use": use_record.to_payload(),
            "forcing_unit_instance_id": target_unit_id,
            "fall_back_unit_instance_id": fall_back_unit_id,
            "persisting_effect": effect.to_payload(),
        },
    )
