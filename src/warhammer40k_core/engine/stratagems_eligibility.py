# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_model import *
from warhammer40k_core.engine.stratagems_requests import *
from warhammer40k_core.engine.stratagems_apply import *
from warhammer40k_core.engine.stratagems_selection import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE, STRATAGEM_PROPOSAL_PAYLOAD_KIND, DECLINE_STRATAGEM_WINDOW_OPTION_ID, DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE, UNSUPPORTED_STRATAGEM_HANDLER_PREFIX, CORE_COMMAND_REROLL_HANDLER_ID, CORE_INSANE_BRAVERY_HANDLER_ID, CORE_RAPID_INGRESS_HANDLER_ID, CORE_NEW_ORDERS_HANDLER_ID, CORE_FIRE_OVERWATCH_HANDLER_ID, CORE_GO_TO_GROUND_HANDLER_ID, CORE_EXPLOSIVES_HANDLER_ID, CORE_SMOKESCREEN_HANDLER_ID, CORE_HEROIC_INTERVENTION_HANDLER_ID, CORE_COUNTEROFFENSIVE_HANDLER_ID, CORE_CRUSHING_IMPACT_HANDLER_ID, CORE_EPIC_CHALLENGE_HANDLER_ID, GENERIC_INGRESS_MOVE_HANDLER_ID, GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID, GENERIC_RULE_IR_STRATAGEM_HANDLER_ID, COMMAND_REROLL_DICE_CONTEXT_KEY, COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY, INSANE_BRAVERY_TARGET_POLICY_ID, RAPID_INGRESS_TARGET_POLICY_ID, STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID, NEW_ORDERS_TARGET_POLICY_ID, FIRE_OVERWATCH_TARGET_POLICY_ID, GO_TO_GROUND_TARGET_POLICY_ID, SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID, EXPLOSIVES_TARGET_POLICY_ID, SMOKESCREEN_TARGET_POLICY_ID, HEROIC_INTERVENTION_TARGET_POLICY_ID, COUNTEROFFENSIVE_TARGET_POLICY_ID, CRUSHING_IMPACT_TARGET_POLICY_ID, EPIC_CHALLENGE_TARGET_POLICY_ID, SELECTED_TO_MOVE_TARGET_POLICY_ID, JUST_FELL_BACK_UNIT_TARGET_POLICY_ID, JUST_SHOT_UNIT_TARGET_POLICY_ID, ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID, EXPLOSIVES_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_MODEL_CONTEXT_KEY, EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND, HEROIC_INTERVENTION_MODE_INTO_THE_FRAY, SELECTED_TARGET_UNIT_CONTEXT_KEY, SELECTED_TO_MOVE_UNIT_CONTEXT_KEY, JUST_FELL_BACK_UNIT_CONTEXT_KEY, JUST_SHOT_UNIT_CONTEXT_KEY, HIT_TARGET_UNIT_CONTEXT_KEY, DESTROYED_TARGET_UNIT_CONTEXT_KEY, DESTROYED_ENEMY_UNIT_CONTEXT_KEY, HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND, HIT_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND, ENGAGED_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY, FALL_BACK_UNIT_CONTEXT_KEY, FALL_BACK_MODE_CONTEXT_KEY, FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND, FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY, FIRE_OVERWATCH_MAX_RANGE_INCHES, HEROIC_INTERVENTION_TARGET_RANGE_INCHES, HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES, CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT, StratagemAvailabilityKind, StratagemCategory, StratagemTargetKind, StratagemUseRecordPayload, StratagemTimingDescriptorPayload, StratagemRestrictionPolicyPayload, StratagemTargetSpecPayload, StratagemDefinitionPayload, StratagemCatalogRecordPayload, StratagemEligibilityContextPayload, StratagemTargetBindingPayload, StratagemTargetProposalPayload, StratagemTimingDescriptor, StratagemRestrictionPolicy, StratagemTargetSpec, StratagemDefinition, StratagemCatalogRecord, StratagemCatalogIndex, StratagemEligibilityContext, StratagemTargetBinding, StratagemTargetProposal, StratagemUseRequest, StratagemUseRecord
    from warhammer40k_core.engine.stratagems_requests import request_stratagem_use, request_stratagem_use_from_index, _request_stratagem_use_with_options, create_stratagem_use_decision_request, stratagem_decline_option, stratagem_decline_payload, is_stratagem_window_decline_result, stratagem_window_decline_allowed, stratagem_window_context_from_request, stratagem_window_decline_event_payload, stratagem_window_declined_for_context, stratagem_use_options, stratagem_use_options_from_index, stratagem_use_options_for_handler_from_index, hit_enemy_unit_effect_selection, engaged_enemy_unit_effect_selection, _stratagem_use_options_for_records, _effect_selections_for_binding, request_stratagem_target_proposal, create_stratagem_target_proposal_decision_request, stratagem_target_proposal_request_payload, stratagem_target_proposal_from_index
    from warhammer40k_core.engine.stratagems_apply import invalid_stratagem_use_status, apply_stratagem_decision, _apply_stratagem_use, invalid_stratagem_target_proposal_status, apply_stratagem_target_proposal, is_stratagem_placement_proposal_request, invalid_stratagem_placement_proposal_status, apply_stratagem_placement_proposal, is_heroic_intervention_charge_move_request, invalid_heroic_intervention_charge_move_status, apply_heroic_intervention_charge_move, _request_heroic_intervention_charge_move_retry
    from warhammer40k_core.engine.stratagems_selection import stratagem_availability_kind_from_token, stratagem_category_from_token, stratagem_target_kind_from_token, _stratagem_decision_option, _effect_selection_token, _stratagem_selection_from_result_payload, _require_stratagem_selection, stratagem_selection_from_decision_result, stratagem_selection_from_target_proposal_result, _record_is_available_for_context, _stratagem_unavailable_reason, _context_state_drift, _detachment_gate_allows, _effect_selection_error, _selected_command_point_cost, _selected_command_point_cost_result, _heroic_intervention_mode_error, _heroic_intervention_mode, _heroic_intervention_mode_additional_cost, _heroic_intervention_mode_costs, _required_effect_selection_fields_error, _effect_selection_string_or_none
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
    "_attached_unit_id_for_component",
    "_canonical_stratagem_affected_unit_id",
    "_enumerated_target_bindings",
    "_handler_unavailable_reason",
    "_restriction_violation",
    "_rules_unit_owner",
    "_same_stratagem_phase",
    "_stratagem_affected_unit_ids",
    "_stratagem_targeted_unit_ids",
    "_unit_has_runtime_attached_role",
)


def _handler_unavailable_reason(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue,
    ruleset_descriptor: RulesetDescriptor | None,
) -> str | None:
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        return _command_reroll_context_error(
            state=state,
            definition=definition,
            context=context,
        )
    if definition.handler_id == CORE_INSANE_BRAVERY_HANDLER_ID:
        if target_binding is None:
            if _battle_shock_test_unit_ids(state=state, player_id=context.player_id):
                return None
            return "no_eligible_battle_shock_test"
        return None
    if definition.handler_id == CORE_RAPID_INGRESS_HANDLER_ID:
        if context.active_player_id == context.player_id:
            return "rapid_ingress_requires_opponent_turn"
        if target_binding is None:
            return (
                None
                if _rapid_ingress_unit_ids(state=state, player_id=context.player_id)
                else ("no_eligible_reserve_unit")
            )
        return None
    if definition.handler_id == GENERIC_INGRESS_MOVE_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.END_PHASE:
            return "ingress_move_requires_end_phase"
        if context.phase is not BattlePhase.MOVEMENT:
            return "ingress_move_requires_movement_phase"
        if target_binding is None:
            return (
                None
                if _strategic_reserves_ingress_unit_ids(state=state, player_id=context.player_id)
                else "no_eligible_strategic_reserve_unit"
            )
        return None
    if definition.handler_id == GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID:
        if context.trigger_kind is not (
            TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_SELECTED_TO_FALL_BACK
        ):
            return "force_desperate_escape_requires_fall_back_selection_trigger"
        if context.phase is not BattlePhase.MOVEMENT:
            return "force_desperate_escape_requires_movement_phase"
        if context.active_player_id == context.player_id:
            return "force_desperate_escape_requires_opponent_turn"
        if _fall_back_unit_id_or_none(context) is None:
            return "missing_fall_back_unit_context"
        if target_binding is None:
            return (
                None
                if _engaged_fall_back_target_unit_ids(
                    state=state,
                    player_id=context.player_id,
                    context=context,
                )
                else "no_eligible_engaged_unit"
            )
        return None
    if definition.handler_id == CORE_NEW_ORDERS_HANDLER_ID:
        if target_binding is None:
            return (
                None
                if _active_tactical_secondary_cards(
                    state=state,
                    player_id=context.player_id,
                )
                else "no_active_tactical_secondary_card"
            )
        return None
    if definition.handler_id == CORE_FIRE_OVERWATCH_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.END_PHASE:
            return "fire_overwatch_requires_end_opponent_movement_phase"
        if context.phase is not BattlePhase.MOVEMENT:
            return "fire_overwatch_requires_movement_phase"
        if context.active_player_id == context.player_id:
            return "fire_overwatch_requires_opponent_turn"
        if _fire_overwatch_triggering_enemy_unit_id_or_none(context) is None:
            return "missing_fire_overwatch_trigger_unit"
        return None
    if definition.handler_id in {
        CORE_GO_TO_GROUND_HANDLER_ID,
        CORE_SMOKESCREEN_HANDLER_ID,
    }:
        if context.active_player_id == context.player_id:
            return "defensive_stratagem_requires_opponent_turn"
        selected_context_error = _selected_target_context_error(
            context=context,
            target_binding=target_binding,
        )
        if selected_context_error is not None:
            return selected_context_error
        return None
    if definition.handler_id == CORE_EXPLOSIVES_HANDLER_ID:
        if target_binding is None:
            return None
        return _explosives_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
        )
    if definition.handler_id == CORE_HEROIC_INTERVENTION_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.END_PHASE:
            return "heroic_intervention_requires_end_charge_phase"
        if context.phase is not BattlePhase.CHARGE:
            return "heroic_intervention_requires_charge_phase"
        if context.active_player_id == context.player_id:
            return "heroic_intervention_requires_opponent_turn"
        return None
    if definition.handler_id == CORE_COUNTEROFFENSIVE_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_FOUGHT:
            return "counteroffensive_requires_enemy_fought_trigger"
        if context.phase is not BattlePhase.FIGHT:
            return "counteroffensive_requires_fight_phase"
        if context.active_player_id is None:
            return "counteroffensive_requires_active_player"
        if target_binding is not None:
            return _counteroffensive_target_context_error(
                state=state,
                context=context,
                target_binding=target_binding,
                ruleset_descriptor=ruleset_descriptor,
            )
        return None
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.AFTER_UNIT_ENDS_CHARGE_MOVE:
            return "crushing_impact_requires_charge_move_trigger"
        if context.phase is not BattlePhase.CHARGE:
            return "crushing_impact_requires_charge_phase"
        if context.active_player_id != context.player_id:
            return "crushing_impact_requires_own_charge_phase"
        if target_binding is None:
            return None
        return _crushing_impact_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
        )
    if definition.handler_id == CORE_EPIC_CHALLENGE_HANDLER_ID:
        if context.trigger_kind is not TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_FIGHT:
            return "epic_challenge_requires_selected_to_fight_trigger"
        if context.phase is not BattlePhase.FIGHT:
            return "epic_challenge_requires_fight_phase"
        if target_binding is None:
            return None
        return _epic_challenge_context_error(
            state=state,
            context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
        )
    if definition.handler_id == GENERIC_RULE_IR_STRATAGEM_HANDLER_ID:
        _generic_rule_ir_from_stratagem_payload(definition.effect_payload)
        return None
    return None


def _restriction_violation(
    *,
    state: GameState,
    player_id: str,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> str | None:
    policy = definition.restriction_policy
    previous_uses = state.stratagem_use_records_for_player(player_id)
    if policy.same_stratagem_per_phase and any(
        use.stratagem_id == definition.stratagem_id
        and _same_stratagem_phase(use=use, context=context)
        for use in previous_uses
    ):
        return "same_stratagem_per_phase"
    if policy.once_per_turn and any(
        use.stratagem_id == definition.stratagem_id
        and use.battle_round == context.battle_round
        and use.player_id == player_id
        for use in previous_uses
    ):
        return "once_per_turn"
    if policy.once_per_battle and any(
        use.stratagem_id == definition.stratagem_id for use in previous_uses
    ):
        return "once_per_battle"
    if (
        policy.once_per_target_per_phase
        and target_binding is not None
        and target_binding.target_unit_instance_id is not None
        and any(
            use.stratagem_id == definition.stratagem_id
            and _same_stratagem_phase(use=use, context=context)
            and use.target_binding.target_unit_instance_id == target_binding.target_unit_instance_id
            for use in previous_uses
        )
    ):
        return "once_per_target_per_phase"
    targeted_unit_ids = _stratagem_targeted_unit_ids(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
    )
    if policy.same_unit_target_per_phase and targeted_unit_ids:
        targeted_unit_id_set = set(targeted_unit_ids)
        if any(
            _same_stratagem_phase(use=use, context=context)
            and targeted_unit_id_set.intersection(use.targeted_unit_instance_ids)
            for use in previous_uses
        ):
            return "targeted_unit_already_stratagem_target"
    return None


def _same_stratagem_phase(*, use: StratagemUseRecord, context: StratagemEligibilityContext) -> bool:
    return (
        use.battle_round == context.battle_round
        and use.phase is context.phase
        and use.active_player_id == context.active_player_id
    )


def _stratagem_targeted_unit_ids(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
) -> tuple[str, ...]:
    raw_unit_ids: list[str] = []
    if target_binding is not None and target_binding.target_unit_instance_id is not None:
        raw_unit_ids.append(target_binding.target_unit_instance_id)
    if not raw_unit_ids:
        return ()
    return _validate_stratagem_affected_unit_ids(
        tuple(
            _canonical_stratagem_affected_unit_id(
                state=state,
                unit_instance_id=unit_instance_id,
            )
            for unit_instance_id in raw_unit_ids
        )
    )


def _stratagem_affected_unit_ids(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue = None,
) -> tuple[str, ...]:
    raw_unit_ids: list[str] = []
    if target_binding is not None and target_binding.target_unit_instance_id is not None:
        raw_unit_ids.append(target_binding.target_unit_instance_id)
    if definition.handler_id == CORE_COMMAND_REROLL_HANDLER_ID:
        raw_unit_ids.append(_command_reroll_affected_unit_id(context))
    if definition.handler_id == CORE_EXPLOSIVES_HANDLER_ID and target_binding is not None:
        explosives_target_id = _explosives_target_unit_id_or_none(context)
        if explosives_target_id is not None:
            raw_unit_ids.append(explosives_target_id)
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID and target_binding is not None:
        crushing_target_id = _crushing_impact_enemy_target_id_or_none(effect_selection)
        if crushing_target_id is not None:
            raw_unit_ids.append(crushing_target_id)
    if (
        definition.handler_id == GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID
        and target_binding is not None
    ):
        fall_back_unit_id = _fall_back_unit_id_or_none(context)
        if fall_back_unit_id is not None:
            raw_unit_ids.append(fall_back_unit_id)
    hit_enemy_unit_id = _hit_enemy_unit_id_or_none(effect_selection)
    if hit_enemy_unit_id is not None:
        raw_unit_ids.append(hit_enemy_unit_id)
    engaged_enemy_unit_id = _engaged_enemy_unit_id_or_none(effect_selection)
    if engaged_enemy_unit_id is not None:
        raw_unit_ids.append(engaged_enemy_unit_id)
    if not raw_unit_ids:
        return ()
    return _validate_stratagem_affected_unit_ids(
        tuple(
            _canonical_stratagem_affected_unit_id(
                state=state,
                unit_instance_id=unit_instance_id,
            )
            for unit_instance_id in raw_unit_ids
        )
    )


def _canonical_stratagem_affected_unit_id(
    *,
    state: GameState,
    unit_instance_id: str,
) -> str:
    requested_unit_id = _validate_identifier("affected_unit_instance_id", unit_instance_id)
    owner = _rules_unit_owner(state=state, unit_instance_id=requested_unit_id)
    if owner is None:
        raise GameLifecycleError("Stratagem affected unit is unknown.")
    if requested_unit_id.startswith("attached-unit:"):
        return requested_unit_id
    attached_unit_id = _attached_unit_id_for_component(
        state=state,
        unit_instance_id=requested_unit_id,
    )
    if attached_unit_id is not None:
        return attached_unit_id
    unit = _unit_by_id_or_none(state=state, unit_instance_id=requested_unit_id)
    if unit is not None and _unit_has_keyword(unit, "ATTACHED_UNIT"):
        return requested_unit_id
    if unit is not None and _unit_has_runtime_attached_role(unit):
        raise GameLifecycleError("Runtime attached unit requires attached-unit identity.")
    return requested_unit_id


def _attached_unit_id_for_component(
    *,
    state: GameState,
    unit_instance_id: str,
) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    matched_attached_ids = tuple(
        attached_unit.attached_unit_instance_id
        for army_definition in state.army_definitions
        for attached_unit in army_definition.attached_units
        if requested_unit_id in attached_unit.component_unit_instance_ids
    )
    if len(matched_attached_ids) > 1:
        raise GameLifecycleError("Attached component has multiple attached identities.")
    if matched_attached_ids:
        return matched_attached_ids[0]
    component_record = None
    for record in state.starting_strength_records:
        if record.unit_instance_id == requested_unit_id:
            component_record = record
            break
    if component_record is None:
        return None
    attached_unit_ids = tuple(
        record.unit_instance_id
        for record in state.starting_strength_records
        if record.player_id == component_record.player_id
        and record.source_id == component_record.source_id
        and record.unit_instance_id.startswith("attached-unit:")
    )
    if len(attached_unit_ids) > 1:
        raise GameLifecycleError("Attached-unit source has multiple attached identities.")
    if attached_unit_ids:
        return attached_unit_ids[0]
    return None


def _unit_has_runtime_attached_role(unit: UnitInstance) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("Attached-role lookup requires a UnitInstance.")
    return any(
        source_id.startswith(("runtime-attached-unit:", "attached-role:"))
        for model in unit.own_models
        for source_id in model.source_ids
    )


def _rules_unit_owner(*, state: GameState, unit_instance_id: str) -> str | None:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    owner = _unit_owner(state=state, unit_instance_id=requested_unit_id)
    if owner is not None:
        return owner
    for record in state.starting_strength_records:
        if record.unit_instance_id == requested_unit_id:
            return record.player_id
    return None


def _enumerated_target_bindings(
    *,
    state: GameState,
    player_id: str,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext | None = None,
) -> tuple[StratagemTargetBinding, ...]:
    target_spec = definition.target_spec
    if target_spec.target_kind is StratagemTargetKind.NONE:
        return (StratagemTargetBinding.none(),)
    if target_spec.target_kind is StratagemTargetKind.TACTICAL_SECONDARY_CARD:
        return tuple(
            StratagemTargetBinding(
                target_kind=StratagemTargetKind.TACTICAL_SECONDARY_CARD,
                target_player_id=card.player_id,
                target_secondary_mission_id=card.secondary_mission_id,
            )
            for card in _active_tactical_secondary_cards(state=state, player_id=player_id)
        )
    if target_spec.target_policy_id == SELECTED_TO_MOVE_TARGET_POLICY_ID:
        if context is None:
            return ()
        selected_unit_id = _selected_to_move_unit_id_or_none(context)
        if selected_unit_id is None:
            return ()
        target_owner = _unit_owner(state=state, unit_instance_id=selected_unit_id)
        if target_owner is None:
            return ()
        binding = StratagemTargetBinding(
            target_kind=target_spec.target_kind,
            target_player_id=target_owner,
            target_unit_instance_id=selected_unit_id,
        )
        return (
            (binding,)
            if _target_binding_error(
                state=state,
                player_id=player_id,
                target_spec=target_spec,
                policy=definition.restriction_policy,
                target_binding=binding,
                context=context,
                ruleset_descriptor=None,
                army_catalog=None,
            )
            is None
            else ()
        )
    if target_spec.target_policy_id == JUST_SHOT_UNIT_TARGET_POLICY_ID:
        if context is None:
            return ()
        shot_unit_id = _just_shot_unit_id_or_none(context)
        if shot_unit_id is None:
            return ()
        target_owner = _unit_owner(state=state, unit_instance_id=shot_unit_id)
        if target_owner is None:
            return ()
        binding = StratagemTargetBinding(
            target_kind=target_spec.target_kind,
            target_player_id=target_owner,
            target_unit_instance_id=shot_unit_id,
        )
        return (
            (binding,)
            if _target_binding_error(
                state=state,
                player_id=player_id,
                target_spec=target_spec,
                policy=definition.restriction_policy,
                target_binding=binding,
                context=context,
                ruleset_descriptor=None,
                army_catalog=None,
            )
            is None
            else ()
        )
    if target_spec.target_policy_id == JUST_FELL_BACK_UNIT_TARGET_POLICY_ID:
        if context is None:
            return ()
        fell_back_unit_id = _just_fell_back_unit_id_or_none(context)
        if fell_back_unit_id is None:
            return ()
        target_owner = _unit_owner(state=state, unit_instance_id=fell_back_unit_id)
        if target_owner is None:
            return ()
        binding = StratagemTargetBinding(
            target_kind=target_spec.target_kind,
            target_player_id=target_owner,
            target_unit_instance_id=fell_back_unit_id,
        )
        return (
            (binding,)
            if _target_binding_error(
                state=state,
                player_id=player_id,
                target_spec=target_spec,
                policy=definition.restriction_policy,
                target_binding=binding,
                context=context,
                ruleset_descriptor=None,
                army_catalog=None,
            )
            is None
            else ()
        )
    bindings: list[StratagemTargetBinding] = []
    for army in state.army_definitions:
        if (
            target_spec.target_kind is StratagemTargetKind.FRIENDLY_UNIT
            and army.player_id != player_id
        ):
            continue
        for unit in army.units:
            binding = StratagemTargetBinding(
                target_kind=target_spec.target_kind,
                target_player_id=army.player_id,
                target_unit_instance_id=unit.unit_instance_id,
            )
            if (
                _target_binding_error(
                    state=state,
                    player_id=player_id,
                    target_spec=target_spec,
                    policy=definition.restriction_policy,
                    target_binding=binding,
                    context=context,
                    ruleset_descriptor=None,
                    army_catalog=None,
                )
                is None
            ):
                bindings.append(binding)
    return tuple(
        sorted(
            bindings,
            key=lambda binding: (
                "" if binding.target_player_id is None else binding.target_player_id,
                "" if binding.target_unit_instance_id is None else binding.target_unit_instance_id,
                ""
                if binding.target_secondary_mission_id is None
                else binding.target_secondary_mission_id,
            ),
        )
    )
