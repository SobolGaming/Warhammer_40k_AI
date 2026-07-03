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
    from warhammer40k_core.engine.stratagems_validation import _apply_command_point_effects, _stratagem_handler_is_unsupported, _next_stratagem_use_id, _target_binding_token, _require_target_unit_id, _target_secondary_mission_id, _validate_catalog_records, _require_decline_event_fields, _invalid, _validate_identifier, _validate_optional_identifier, _validate_identifier_tuple, _validate_stratagem_affected_unit_ids, _validate_optional_phase, _validate_target_policy_id, _validate_positive_int, _validate_non_negative_int, _validate_bool
# fmt: on

__all__ = (
    "_apply_counteroffensive_handler",
    "_apply_crushing_impact_handler",
    "_apply_epic_challenge_handler",
    "_apply_explosives_handler",
    "_apply_go_to_ground_handler",
    "_apply_heroic_intervention_handler",
    "_apply_smokescreen_handler",
    "_apply_stratagem_mortal_wounds",
    "_closest_unit_distance_inches",
    "_emit_explosives_resolved",
    "_enemy_unit_ids_for_player",
    "_heroic_intervention_reachable_target_distances",
    "_unit_made_charge_move",
    "apply_explosives_mortal_wound_feel_no_pain_decision",
)


def _apply_go_to_ground_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:go-to-ground",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": GO_TO_GROUND_EFFECT_KIND,
            "stratagem_use_id": use_record.use_id,
            "benefit_of_cover": True,
            "invulnerable_save": GO_TO_GROUND_INVULNERABLE_SAVE,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "go_to_ground_effect_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_smokescreen_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:smokescreen",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": SMOKESCREEN_EFFECT_KIND,
            "stratagem_use_id": use_record.use_id,
            "benefit_of_cover": True,
            "hit_roll_modifier": SMOKESCREEN_HIT_ROLL_MODIFIER,
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "smokescreen_effect_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_explosives_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _explosives_target_unit_id(context)
    context_error = _explosives_context_error(
        state=state,
        context=context,
        target_binding=target_binding,
    )
    if context_error is not None:
        raise GameLifecycleError("Prevalidated Explosives context failed.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=6, sides=6),
            reason=f"Explosives mortal wounds for {use_record.use_id}",
            roll_type="stratagem.explosives",
            actor_id=use_record.player_id,
        )
    )
    mortal_wounds = sum(1 for value in roll_state.current_values if value >= 4)
    mortal_application = None
    if mortal_wounds > 0:
        progress = MortalWoundApplicationProgress.start(
            application_id=f"{use_record.use_id}:explosives:mortal-wounds",
            source_rule_id=CORE_EXPLOSIVES_HANDLER_ID,
            source_context=validate_json_value(
                {
                    "source_kind": "explosives",
                    "stratagem_use": use_record.to_payload(),
                    "explosives_unit_instance_id": _require_target_unit_id(target_binding),
                    "target_unit_instance_id": target_unit_id,
                    "roll_state": roll_state.to_payload(),
                }
            ),
            target_unit_instance_id=target_unit_id,
            defender_player_id=unit_owner_player_id(
                state=state,
                unit_instance_id=target_unit_id,
            ),
            mortal_wounds=mortal_wounds,
            spill_over=True,
        )
        routed = continue_mortal_wound_application(
            state=state,
            request_id=state.next_decision_request_id(),
            progress=progress,
            dice_manager=manager,
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return
        if routed.application is None:
            raise GameLifecycleError("Explosives mortal wounds did not produce application.")
        mortal_application = routed.application
    _emit_explosives_resolved(
        decisions=decisions,
        state=state,
        use_record=use_record,
        explosives_unit_instance_id=_require_target_unit_id(target_binding),
        target_unit_instance_id=target_unit_id,
        roll_state=validate_json_value(roll_state.to_payload()),
        mortal_wounds=mortal_wounds,
        mortal_application=mortal_application,
    )


def apply_explosives_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError("Explosives Feel No Pain requires mortal wound context.")
    source_context = mortal_wound_feel_no_pain_source_context(request)
    if not isinstance(source_context, dict) or source_context.get("source_kind") != "explosives":
        raise GameLifecycleError("Explosives Feel No Pain source context is invalid.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=routed.request,
            payload={
                "phase": state.current_battle_phase.value
                if state.current_battle_phase is not None
                else None,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": CORE_EXPLOSIVES_HANDLER_ID,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Explosives Feel No Pain did not finish routing.")
    use_record = StratagemUseRecord.from_payload(
        cast(StratagemUseRecordPayload, source_context["stratagem_use"])
    )
    roll_state_payload = source_context["roll_state"]
    if not isinstance(roll_state_payload, dict):
        raise GameLifecycleError("Explosives source context roll_state is invalid.")
    _emit_explosives_resolved(
        decisions=decisions,
        state=state,
        use_record=use_record,
        explosives_unit_instance_id=_validate_identifier(
            "explosives_unit_instance_id",
            source_context["explosives_unit_instance_id"],
        ),
        target_unit_instance_id=routed.progress.target_unit_instance_id,
        roll_state=validate_json_value(roll_state_payload),
        mortal_wounds=routed.progress.mortal_wounds,
        mortal_application=routed.application,
    )
    return None


def _emit_explosives_resolved(
    *,
    decisions: DecisionController,
    state: GameState,
    use_record: StratagemUseRecord,
    explosives_unit_instance_id: str,
    target_unit_instance_id: str,
    roll_state: JsonValue,
    mortal_wounds: int,
    mortal_application: MortalWoundApplication | None,
) -> None:
    decisions.event_log.append(
        "explosives_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "explosives_unit_instance_id": explosives_unit_instance_id,
            "target_unit_instance_id": target_unit_instance_id,
            "roll_state": roll_state,
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": (
                None if mortal_application is None else mortal_application.to_payload()
            ),
        },
    )


def _apply_counteroffensive_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
    ruleset_descriptor: RulesetDescriptor,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    fight_state = state.fight_phase_state
    if fight_state is None:
        raise GameLifecycleError("Counteroffensive requires fight_phase_state.")
    contexts = eligible_fight_contexts_for_player(
        state=state,
        fight_state=fight_state,
        player_id=use_record.player_id,
        policy=ruleset_descriptor.fight_policy,
    )
    fight_context = next(
        (candidate for candidate in contexts if candidate.unit_instance_id == target_unit_id),
        None,
    )
    if fight_context is None:
        raise GameLifecycleError("Counteroffensive target was not prevalidated.")
    fight_types = legal_fight_types_for_context(
        context=fight_context,
        policy=ruleset_descriptor.fight_policy,
    )
    if not fight_types:
        raise GameLifecycleError("Counteroffensive target has no legal fight type.")
    interrupt_id = f"counteroffensive:{use_record.use_id}"
    selection = FightActivationSelection(
        player_id=use_record.player_id,
        battle_round=use_record.battle_round,
        unit_instance_id=target_unit_id,
        ordering_band=fight_context.ordering_band,
        fight_type=fight_types[0],
        eligibility_reasons=fight_context.eligibility_reasons,
        request_id=use_record.request_id,
        result_id=use_record.result_id,
        interrupt_id=interrupt_id,
    )
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:counteroffensive:fights-first",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": FIGHTS_FIRST_EFFECT_KIND,
            "source_rule_id": use_record.source_id,
            "stratagem_use_id": use_record.use_id,
        },
    )
    state.record_persisting_effect(effect)
    state.replace_fight_phase_state(
        fight_state.with_activation(selection).with_active_activation(selection)
    )
    decisions.event_log.append(
        "counteroffensive_activation_selected",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
            "activation_selection": selection.to_payload(),
        },
    )


def _apply_crushing_impact_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    context_error = _crushing_impact_context_error(
        state=state,
        context=context,
        target_binding=target_binding,
        effect_selection=use_record.effect_selection,
    )
    if context_error is not None:
        raise GameLifecycleError("Prevalidated Crushing Impact context failed.")
    source_unit_id = _require_target_unit_id(target_binding)
    enemy_unit_id = _crushing_impact_enemy_target_id_or_none(use_record.effect_selection)
    model_id = _crushing_impact_model_id_or_none(use_record.effect_selection)
    if enemy_unit_id is None or model_id is None:
        raise GameLifecycleError("Crushing Impact selection was not prevalidated.")
    toughness = _model_toughness(state=state, model_instance_id=model_id)
    if toughness is None:
        raise GameLifecycleError("Crushing Impact model Toughness was not prevalidated.")
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=toughness, sides=6),
            reason=f"Crushing Impact mortal wounds for {use_record.use_id}",
            roll_type="stratagem.crushing_impact",
            actor_id=use_record.player_id,
        )
    )
    source_mortal_wounds = sum(1 for value in roll_state.current_values if value == 1)
    enemy_mortal_wounds = min(
        CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT,
        sum(1 for value in roll_state.current_values if value >= 5),
    )
    source_application = _apply_stratagem_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        use_record=use_record,
        application_id=f"{use_record.use_id}:crushing-impact:self",
        target_unit_instance_id=source_unit_id,
        mortal_wounds=source_mortal_wounds,
        source_context=validate_json_value(
            {
                "source_kind": "crushing_impact_self",
                "stratagem_use": use_record.to_payload(),
                "roll_state": roll_state.to_payload(),
            }
        ),
    )
    if decisions.queue.pending_requests:
        return
    enemy_application = _apply_stratagem_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        use_record=use_record,
        application_id=f"{use_record.use_id}:crushing-impact:enemy",
        target_unit_instance_id=enemy_unit_id,
        mortal_wounds=enemy_mortal_wounds,
        source_context=validate_json_value(
            {
                "source_kind": "crushing_impact_enemy",
                "stratagem_use": use_record.to_payload(),
                "roll_state": roll_state.to_payload(),
            }
        ),
    )
    decisions.event_log.append(
        "crushing_impact_resolved",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "source_unit_instance_id": source_unit_id,
            "source_model_instance_id": model_id,
            "target_unit_instance_id": enemy_unit_id,
            "roll_state": roll_state.to_payload(),
            "source_mortal_wounds": source_mortal_wounds,
            "enemy_mortal_wounds": enemy_mortal_wounds,
            "source_mortal_wound_application": (
                None if source_application is None else source_application.to_payload()
            ),
            "enemy_mortal_wound_application": (
                None if enemy_application is None else enemy_application.to_payload()
            ),
        },
    )


def _apply_epic_challenge_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    context_error = _epic_challenge_context_error(
        state=state,
        context=context,
        target_binding=target_binding,
        effect_selection=use_record.effect_selection,
    )
    if context_error is not None:
        raise GameLifecycleError("Prevalidated Epic Challenge context failed.")
    target_unit_id = _require_target_unit_id(target_binding)
    model_id = _epic_challenge_character_model_id_or_none(use_record.effect_selection)
    if model_id is None:
        raise GameLifecycleError("Epic Challenge model was not prevalidated.")
    effect = PersistingEffect(
        effect_id=f"{use_record.use_id}:epic-challenge:precision",
        source_rule_id=use_record.source_id,
        owner_player_id=use_record.player_id,
        target_unit_instance_ids=(target_unit_id,),
        started_battle_round=use_record.battle_round,
        started_phase=use_record.phase,
        expiration=EffectExpiration.end_phase(
            battle_round=use_record.battle_round,
            phase=use_record.phase,
            player_id=context.active_player_id or use_record.player_id,
        ),
        effect_payload={
            "effect_kind": "epic_challenge_precision",
            "source_rule_id": use_record.source_id,
            "stratagem_use_id": use_record.use_id,
            "model_instance_id": model_id,
            "weapon_keyword": "Precision",
        },
    )
    state.record_persisting_effect(effect)
    decisions.event_log.append(
        "epic_challenge_precision_registered",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": use_record.battle_round,
            "phase": use_record.phase.value,
            "stratagem_use": use_record.to_payload(),
            "persisting_effect": effect.to_payload(),
        },
    )


def _apply_heroic_intervention_handler(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    context: StratagemEligibilityContext,
    definition: StratagemDefinition,
    target_binding: StratagemTargetBinding,
    use_record: StratagemUseRecord,
) -> None:
    target_unit_id = _require_target_unit_id(target_binding)
    mode = _heroic_intervention_mode(
        definition=definition,
        effect_selection=use_record.effect_selection,
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    roll_state = manager.roll(
        DiceRollSpec(
            expression=DiceExpression(quantity=2, sides=6),
            reason=f"Heroic Intervention charge roll for {use_record.use_id}",
            roll_type="charge_roll",
            actor_id=use_record.player_id,
            reroll_forbidden_rule_ids=(CORE_COMMAND_REROLL_HANDLER_ID,),
        )
    )
    maximum_distance = roll_state.current_total
    if mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY and maximum_distance > 6:
        maximum_distance = 6
    reachable = _heroic_intervention_reachable_target_distances(
        state=state,
        player_id=use_record.player_id,
        heroic_unit_id=target_unit_id,
        mode=mode,
        maximum_distance_inches=maximum_distance,
    )
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=MOVEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=context.player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=BattlePhase.CHARGE.value,
        unit_instance_id=target_unit_id,
        proposal_kind=ProposalKind.CHARGE_MOVE,
        source_decision_request_id=result.request_id,
        source_decision_result_id=result.result_id,
        movement_phase_action=CHARGE_MOVE_ACTION,
        context=cast(
            dict[str, JsonValue],
            validate_json_value(
                {
                    "stratagem_handler_id": CORE_HEROIC_INTERVENTION_HANDLER_ID,
                    "stratagem_use": use_record.to_payload(),
                    "mode": mode,
                    "movement_mode": MovementMode.CHARGE.value,
                    "charge_roll_state": roll_state.to_payload(),
                    "maximum_distance_inches": maximum_distance,
                    "reachable_target_unit_instance_ids": list(reachable),
                    "reachable_target_distances_inches": reachable,
                }
            ),
        ),
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "heroic_intervention_charge_move_requested",
        {
            "game_id": state.game_id,
            "player_id": use_record.player_id,
            "battle_round": state.battle_round,
            "phase": BattlePhase.CHARGE.value,
            "stratagem_use": use_record.to_payload(),
            "mode": mode,
            "charge_roll_state": roll_state.to_payload(),
            "maximum_distance_inches": maximum_distance,
            "reachable_target_unit_instance_ids": list(reachable),
            "reachable_target_distances_inches": reachable,
            "request_id": request.request_id,
        },
    )


def _apply_stratagem_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    use_record: StratagemUseRecord,
    application_id: str,
    target_unit_instance_id: str,
    mortal_wounds: int,
    source_context: JsonValue,
) -> MortalWoundApplication | None:
    if mortal_wounds <= 0:
        return None
    progress = MortalWoundApplicationProgress.start(
        application_id=application_id,
        source_rule_id=use_record.handler_id,
        source_context=validate_json_value(source_context),
        target_unit_instance_id=target_unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=target_unit_instance_id,
        ),
        mortal_wounds=mortal_wounds,
        spill_over=True,
    )
    routed = continue_mortal_wound_application(
        state=state,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return None
    if routed.application is None:
        raise GameLifecycleError("Stratagem mortal wounds did not produce application.")
    return routed.application


def _heroic_intervention_reachable_target_distances(
    *,
    state: GameState,
    player_id: str,
    heroic_unit_id: str,
    mode: str,
    maximum_distance_inches: int,
) -> dict[str, float]:
    distances: dict[str, float] = {}
    for enemy_unit_id in _enemy_unit_ids_for_player(state=state, player_id=player_id):
        distance = _closest_unit_distance_inches(
            state=state,
            first_unit_instance_id=heroic_unit_id,
            second_unit_instance_id=enemy_unit_id,
        )
        if distance > float(maximum_distance_inches):
            continue
        if (
            mode == HEROIC_INTERVENTION_MODE_INTO_THE_FRAY
            and distance > HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES
        ):
            continue
        if mode == HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND and not _unit_made_charge_move(
            state=state,
            unit_instance_id=enemy_unit_id,
        ):
            continue
        distances[enemy_unit_id] = distance
    return dict(sorted(distances.items()))


def _enemy_unit_ids_for_player(*, state: GameState, player_id: str) -> tuple[str, ...]:
    requested_player_id = _validate_identifier("player_id", player_id)
    ids: list[str] = []
    for army in state.army_definitions:
        if army.player_id == requested_player_id:
            continue
        ids.extend(unit.unit_instance_id for unit in army.units)
    return tuple(sorted(ids))


def _closest_unit_distance_inches(
    *,
    state: GameState,
    first_unit_instance_id: str,
    second_unit_instance_id: str,
) -> float:
    first_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=first_unit_instance_id,
    )
    second_models = _geometry_models_for_unit(
        state=state,
        unit_instance_id=second_unit_instance_id,
    )
    if not first_models or not second_models:
        raise GameLifecycleError("Stratagem unit distance requires placed models.")
    return min(
        first_model.range_to(second_model)
        for first_model in first_models
        for second_model in second_models
    )


def _unit_made_charge_move(*, state: GameState, unit_instance_id: str) -> bool:
    requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for effect in state.persisting_effects:
        if requested_unit_id not in effect.target_unit_instance_ids:
            continue
        effect_payload = effect.effect_payload
        if not isinstance(effect_payload, dict):
            continue
        if effect_payload.get("effect_kind") == "charge_grants_fights_first":
            return True
    return False
