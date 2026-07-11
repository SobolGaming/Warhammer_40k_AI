# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.stratagems_imports import *
from warhammer40k_core.engine.stratagems_generic_metadata import (
    COMPANION_OPTIONAL_KEY,
    CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND,
    OBJECTIVE_MARKER_CONTEXT_KEY,
    SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND,
    companion_unit_id_or_none,
    objective_marker_id_or_none,
)
from warhammer40k_core.engine.stratagems_model import *
from warhammer40k_core.engine.stratagems_requests import *
from warhammer40k_core.engine.stratagems_apply import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.faction_content.stratagem_handlers import StratagemHandlerRegistry
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems_model import STRATAGEM_DECISION_TYPE, STRATAGEM_TARGET_PROPOSAL_DECISION_TYPE, STRATAGEM_PROPOSAL_PAYLOAD_KIND, DECLINE_STRATAGEM_WINDOW_OPTION_ID, DECLINE_STRATAGEM_WINDOW_PAYLOAD_KIND, STRATAGEM_WINDOW_DECLINED_EVENT_TYPE, UNSUPPORTED_STRATAGEM_HANDLER_PREFIX, CORE_COMMAND_REROLL_HANDLER_ID, CORE_INSANE_BRAVERY_HANDLER_ID, CORE_RAPID_INGRESS_HANDLER_ID, CORE_NEW_ORDERS_HANDLER_ID, CORE_FIRE_OVERWATCH_HANDLER_ID, CORE_GO_TO_GROUND_HANDLER_ID, CORE_EXPLOSIVES_HANDLER_ID, CORE_SMOKESCREEN_HANDLER_ID, CORE_HEROIC_INTERVENTION_HANDLER_ID, CORE_COUNTEROFFENSIVE_HANDLER_ID, CORE_CRUSHING_IMPACT_HANDLER_ID, CORE_EPIC_CHALLENGE_HANDLER_ID, GENERIC_INGRESS_MOVE_HANDLER_ID, GENERIC_FORCE_DESPERATE_ESCAPE_HANDLER_ID, GENERIC_RULE_IR_STRATAGEM_HANDLER_ID, COMMAND_REROLL_DICE_CONTEXT_KEY, COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY, INSANE_BRAVERY_TARGET_POLICY_ID, RAPID_INGRESS_TARGET_POLICY_ID, STRATEGIC_RESERVES_INGRESS_TARGET_POLICY_ID, NEW_ORDERS_TARGET_POLICY_ID, FIRE_OVERWATCH_TARGET_POLICY_ID, GO_TO_GROUND_TARGET_POLICY_ID, SELECTED_TARGET_CONTROLLED_OBJECTIVE_INFANTRY_TARGET_POLICY_ID, EXPLOSIVES_TARGET_POLICY_ID, SMOKESCREEN_TARGET_POLICY_ID, HEROIC_INTERVENTION_TARGET_POLICY_ID, COUNTEROFFENSIVE_TARGET_POLICY_ID, CRUSHING_IMPACT_TARGET_POLICY_ID, EPIC_CHALLENGE_TARGET_POLICY_ID, SELECTED_TO_MOVE_TARGET_POLICY_ID, JUST_FELL_BACK_UNIT_TARGET_POLICY_ID, JUST_SHOT_UNIT_TARGET_POLICY_ID, ENGAGED_WITH_FALL_BACK_UNIT_TARGET_POLICY_ID, EXPLOSIVES_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY, CRUSHING_IMPACT_MODEL_CONTEXT_KEY, EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_CONTEXT_KEY, HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND, HEROIC_INTERVENTION_MODE_INTO_THE_FRAY, SELECTED_TARGET_UNIT_CONTEXT_KEY, SELECTED_TO_MOVE_UNIT_CONTEXT_KEY, JUST_FELL_BACK_UNIT_CONTEXT_KEY, JUST_SHOT_UNIT_CONTEXT_KEY, HIT_TARGET_UNIT_CONTEXT_KEY, DESTROYED_TARGET_UNIT_CONTEXT_KEY, DESTROYED_ENEMY_UNIT_CONTEXT_KEY, HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND, HIT_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND, ENGAGED_ENEMY_UNIT_CONTEXT_KEY, ENGAGED_ENEMY_UNIT_IDS_CONTEXT_KEY, FALL_BACK_UNIT_CONTEXT_KEY, FALL_BACK_MODE_CONTEXT_KEY, FORCED_FALL_BACK_DESPERATE_ESCAPE_EFFECT_KIND, FIRE_OVERWATCH_TRIGGER_CONTEXT_KEY, FIRE_OVERWATCH_MAX_RANGE_INCHES, HEROIC_INTERVENTION_TARGET_RANGE_INCHES, HEROIC_INTERVENTION_INTO_THE_FRAY_TARGET_RANGE_INCHES, CRUSHING_IMPACT_MAX_MORTAL_WOUNDS_PER_UNIT, StratagemAvailabilityKind, StratagemCategory, StratagemTargetKind, StratagemUseRecordPayload, StratagemTimingDescriptorPayload, StratagemRestrictionPolicyPayload, StratagemTargetSpecPayload, StratagemDefinitionPayload, StratagemCatalogRecordPayload, StratagemEligibilityContextPayload, StratagemTargetBindingPayload, StratagemTargetProposalPayload, StratagemTimingDescriptor, StratagemRestrictionPolicy, StratagemTargetSpec, StratagemDefinition, StratagemCatalogRecord, StratagemCatalogIndex, StratagemEligibilityContext, StratagemTargetBinding, StratagemTargetProposal, StratagemUseRequest, StratagemUseRecord
    from warhammer40k_core.engine.stratagems_requests import request_stratagem_use, request_stratagem_use_from_index, _request_stratagem_use_with_options, create_stratagem_use_decision_request, stratagem_decline_option, stratagem_decline_payload, is_stratagem_window_decline_result, stratagem_window_decline_allowed, stratagem_window_context_from_request, stratagem_window_decline_event_payload, stratagem_window_declined_for_context, stratagem_use_options, stratagem_use_options_from_index, stratagem_use_options_for_handler_from_index, hit_enemy_unit_effect_selection, engaged_enemy_unit_effect_selection, _stratagem_use_options_for_records, _effect_selections_for_binding, request_stratagem_target_proposal, create_stratagem_target_proposal_decision_request, stratagem_target_proposal_request_payload, stratagem_target_proposal_from_index
    from warhammer40k_core.engine.stratagems_apply import invalid_stratagem_use_status, apply_stratagem_decision, _apply_stratagem_use, invalid_stratagem_target_proposal_status, apply_stratagem_target_proposal, is_stratagem_placement_proposal_request, invalid_stratagem_placement_proposal_status, apply_stratagem_placement_proposal, is_heroic_intervention_charge_move_request, invalid_heroic_intervention_charge_move_status, apply_heroic_intervention_charge_move, _request_heroic_intervention_charge_move_retry
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
    "_context_state_drift",
    "_detachment_gate_allows",
    "_effect_selection_error",
    "_effect_selection_string_or_none",
    "_effect_selection_token",
    "_heroic_intervention_mode",
    "_heroic_intervention_mode_additional_cost",
    "_heroic_intervention_mode_costs",
    "_heroic_intervention_mode_error",
    "_record_is_available_for_context",
    "_require_stratagem_selection",
    "_required_effect_selection_fields_error",
    "_selected_command_point_cost",
    "_selected_command_point_cost_result",
    "_stratagem_decision_option",
    "_stratagem_selection_from_result_payload",
    "_stratagem_unavailable_reason",
    "stratagem_availability_kind_from_token",
    "stratagem_category_from_token",
    "stratagem_selection_from_decision_result",
    "stratagem_selection_from_target_proposal_result",
    "stratagem_target_kind_from_token",
)


def stratagem_availability_kind_from_token(token: object) -> StratagemAvailabilityKind:
    if type(token) is StratagemAvailabilityKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemAvailabilityKind token must be a string.")
    try:
        return StratagemAvailabilityKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported StratagemAvailabilityKind token: {token}.") from exc


def stratagem_category_from_token(token: object) -> StratagemCategory:
    if type(token) is StratagemCategory:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemCategory token must be a string.")
    try:
        return StratagemCategory(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported StratagemCategory token: {token}.") from exc


def stratagem_target_kind_from_token(token: object) -> StratagemTargetKind:
    if type(token) is StratagemTargetKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("StratagemTargetKind token must be a string.")
    try:
        return StratagemTargetKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported StratagemTargetKind token: {token}.") from exc


def _stratagem_decision_option(
    *,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding,
    effect_selection: JsonValue = None,
) -> DecisionOption:
    definition = record.definition
    option_id = (
        f"use-stratagem:{definition.stratagem_id}:target:{_target_binding_token(target_binding)}"
    )
    if effect_selection is not None:
        option_id = f"{option_id}:effect:{_effect_selection_token(effect_selection)}"
    return DecisionOption(
        option_id=option_id,
        label=definition.name,
        payload=validate_json_value(
            {
                "submission_kind": STRATAGEM_DECISION_TYPE,
                "context": context.to_payload(),
                "catalog_record": record.to_payload(),
                "target_binding": target_binding.to_payload(),
                "effect_selection": effect_selection,
            }
        ),
    )


def _effect_selection_token(effect_selection: JsonValue) -> str:
    hit_enemy_unit_id = _hit_enemy_unit_id_or_none(effect_selection)
    if hit_enemy_unit_id is not None:
        return f"{HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND}:{hit_enemy_unit_id}"
    engaged_enemy_unit_id = _engaged_enemy_unit_id_or_none(effect_selection)
    if engaged_enemy_unit_id is not None:
        return f"{ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND}:{engaged_enemy_unit_id}"
    if isinstance(effect_selection, dict) and (
        effect_selection.get("effect_selection_kind") == VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND
    ):
        visible_enemy_unit_id = _effect_selection_string_or_none(
            effect_selection=effect_selection,
            key=VISIBLE_ENEMY_UNIT_CONTEXT_KEY,
        )
        if visible_enemy_unit_id is not None:
            return f"{VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND}:{visible_enemy_unit_id}"
    companion_unit_id = companion_unit_id_or_none(effect_selection)
    if companion_unit_id is not None:
        return f"{SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND}:{companion_unit_id}"
    objective_marker_id = objective_marker_id_or_none(effect_selection)
    if objective_marker_id is not None:
        return f"{CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND}:{objective_marker_id}"
    raise GameLifecycleError("Unsupported Stratagem effect selection token.")


def _stratagem_selection_from_result_payload(
    payload: JsonValue,
) -> (
    tuple[
        StratagemEligibilityContext,
        StratagemCatalogRecord,
        StratagemTargetBinding,
        JsonValue,
    ]
    | None
):
    if not isinstance(payload, dict):
        return None
    if payload.get("submission_kind") != STRATAGEM_DECISION_TYPE:
        return None
    context_payload = payload.get("context")
    record_payload = payload.get("catalog_record")
    binding_payload = payload.get("target_binding")
    effect_selection = payload.get("effect_selection")
    if not isinstance(context_payload, dict):
        return None
    if not isinstance(record_payload, dict):
        return None
    if not isinstance(binding_payload, dict):
        return None
    try:
        return (
            StratagemEligibilityContext.from_payload(
                cast(StratagemEligibilityContextPayload, context_payload)
            ),
            StratagemCatalogRecord.from_payload(
                cast(StratagemCatalogRecordPayload, record_payload)
            ),
            StratagemTargetBinding.from_payload(
                cast(StratagemTargetBindingPayload, binding_payload)
            ),
            validate_json_value(effect_selection),
        )
    except (KeyError, GameLifecycleError):  # fmt: skip
        return None


def _require_stratagem_selection(
    payload: JsonValue,
) -> tuple[StratagemEligibilityContext, StratagemCatalogRecord, StratagemTargetBinding, JsonValue]:
    selection = _stratagem_selection_from_result_payload(payload)
    if selection is None:
        raise GameLifecycleError("Stratagem decision payload was not prevalidated.")
    return selection


def stratagem_selection_from_decision_result(
    result: DecisionResult,
) -> (
    tuple[
        StratagemEligibilityContext,
        StratagemCatalogRecord,
        StratagemTargetBinding,
        JsonValue,
    ]
    | None
):
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem selection lookup requires DecisionResult.")
    return _stratagem_selection_from_result_payload(result.payload)


def stratagem_selection_from_target_proposal_result(
    result: DecisionResult,
) -> (
    tuple[
        StratagemEligibilityContext,
        StratagemCatalogRecord,
        StratagemTargetBinding,
        JsonValue,
    ]
    | None
):
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Stratagem proposal selection lookup requires DecisionResult.")
    proposal = _proposal_from_result_payload(result.payload)
    if proposal is None or proposal.target_binding is None:
        return None
    return (
        proposal.context,
        proposal.catalog_record,
        proposal.target_binding,
        proposal.effect_selection,
    )


def _record_is_available_for_context(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
) -> bool:
    return (
        _stratagem_unavailable_reason(
            state=state,
            record=record,
            context=context,
            target_binding=None,
        )
        is None
    )


def _stratagem_unavailable_reason(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue = None,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    decisions: DecisionController | None = None,
    source_decision_request_id: str | None = None,
    source_decision_result_id: str | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> str | None:
    if state.stage is not GameLifecycleStage.BATTLE:
        return "not_battle_stage"
    drift = _context_state_drift(state=state, context=context)
    if drift is not None:
        return drift
    if record.disabled:
        return "stratagem_disabled"
    if _stratagem_handler_is_unsupported(record.definition):
        return "unsupported_handler"
    if not record.definition.timing.matches(context):
        return "timing_window_mismatch"
    effect_selection_error = _effect_selection_error(
        definition=record.definition,
        context=context,
        effect_selection=effect_selection,
    )
    if effect_selection_error is not None:
        return effect_selection_error
    command_point_cost = _selected_command_point_cost(
        state=state,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        decisions=decisions,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if state.command_point_total(context.player_id) < command_point_cost:
        return "insufficient_command_points"
    if not _detachment_gate_allows(state=state, record=record, player_id=context.player_id):
        return "detachment_gate_closed"
    handler_reason = _handler_unavailable_reason(
        state=state,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        ruleset_descriptor=ruleset_descriptor,
    )
    if handler_reason is not None:
        return handler_reason
    if target_binding is not None:
        target_error = _target_binding_error(
            state=state,
            player_id=context.player_id,
            target_spec=record.definition.target_spec,
            policy=record.definition.restriction_policy,
            target_binding=target_binding,
            context=context,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        )
        if target_error is not None:
            return target_error
    restriction = _restriction_violation(
        state=state,
        player_id=context.player_id,
        definition=record.definition,
        context=context,
        target_binding=target_binding,
    )
    if restriction is not None:
        return restriction
    return None


def _context_state_drift(*, state: GameState, context: StratagemEligibilityContext) -> str | None:
    if state.game_id != context.game_id:
        return "wrong_context"
    if state.battle_round != context.battle_round:
        return "stale_battle_round"
    if state.current_battle_phase is not context.phase:
        return "stale_phase"
    if state.active_player_id != context.active_player_id:
        return "stale_active_player"
    if context.player_id not in state.player_ids:
        return "unknown_player"
    return None


def _detachment_gate_allows(
    *,
    state: GameState,
    record: StratagemCatalogRecord,
    player_id: str,
) -> bool:
    if record.availability_kind is StratagemAvailabilityKind.CORE:
        return True
    for army in state.army_definitions:
        if army.player_id != player_id:
            continue
        selection = army.detachment_selection
        return record.detachment_id in selection.detachment_ids
    return False


def _effect_selection_error(
    *,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    effect_selection: JsonValue,
) -> str | None:
    if definition.handler_id == CORE_HEROIC_INTERVENTION_HANDLER_ID:
        return _heroic_intervention_mode_error(
            definition=definition,
            effect_selection=effect_selection,
        )
    if definition.handler_id == CORE_CRUSHING_IMPACT_HANDLER_ID:
        if effect_selection is None:
            return None
        return _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(
                CRUSHING_IMPACT_ENEMY_TARGET_CONTEXT_KEY,
                CRUSHING_IMPACT_MODEL_CONTEXT_KEY,
            ),
        )
    if definition.handler_id == CORE_EPIC_CHALLENGE_HANDLER_ID:
        if effect_selection is None:
            return None
        return _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(EPIC_CHALLENGE_CHARACTER_MODEL_CONTEXT_KEY,),
        )
    payload = definition.effect_payload
    payload_object = payload if isinstance(payload, dict) else None
    selection_kind = (
        payload_object.get("effect_selection_kind") if payload_object is not None else None
    )
    if selection_kind == HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        if effect_selection is None:
            return None
        field_error = _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(HIT_ENEMY_UNIT_CONTEXT_KEY,),
        )
        if field_error is not None:
            return field_error
        if (
            _effect_selection_string_or_none(
                effect_selection=effect_selection,
                key="effect_selection_kind",
            )
            != HIT_ENEMY_UNIT_EFFECT_SELECTION_KIND
        ):
            return "effect_selection_kind_mismatch"
        selected_unit_id = _hit_enemy_unit_id_or_none(effect_selection)
        if selected_unit_id is None:
            return f"{HIT_ENEMY_UNIT_CONTEXT_KEY}_required"
        if selected_unit_id not in _hit_target_unit_ids_or_empty(context):
            return "hit_enemy_unit_not_in_trigger_context"
        return None
    if selection_kind == ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        if effect_selection is None:
            return None
        field_error = _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(ENGAGED_ENEMY_UNIT_CONTEXT_KEY,),
        )
        if field_error is not None:
            return field_error
        if (
            _effect_selection_string_or_none(
                effect_selection=effect_selection,
                key="effect_selection_kind",
            )
            != ENGAGED_ENEMY_UNIT_EFFECT_SELECTION_KIND
        ):
            return "effect_selection_kind_mismatch"
        selected_unit_id = _engaged_enemy_unit_id_or_none(effect_selection)
        if selected_unit_id is None:
            return f"{ENGAGED_ENEMY_UNIT_CONTEXT_KEY}_required"
        if selected_unit_id not in _engaged_enemy_unit_ids_or_empty(context):
            return "engaged_enemy_unit_not_in_trigger_context"
        return None
    if selection_kind == VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND:
        if effect_selection is None:
            return None
        field_error = _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(VISIBLE_ENEMY_UNIT_CONTEXT_KEY,),
        )
        if field_error is not None:
            return field_error
        if (
            _effect_selection_string_or_none(
                effect_selection=effect_selection,
                key="effect_selection_kind",
            )
            != VISIBLE_ENEMY_UNIT_EFFECT_SELECTION_KIND
        ):
            return "effect_selection_kind_mismatch"
        if (
            _effect_selection_string_or_none(
                effect_selection=effect_selection,
                key=VISIBLE_ENEMY_UNIT_CONTEXT_KEY,
            )
            is None
        ):
            return f"{VISIBLE_ENEMY_UNIT_CONTEXT_KEY}_required"
        return None
    if selection_kind == SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND:
        if payload_object is None:
            raise GameLifecycleError("Stratagem effect payload must be an object.")
        companion_optional = payload_object.get(COMPANION_OPTIONAL_KEY)
        if companion_optional is not None and type(companion_optional) is not bool:
            raise GameLifecycleError("companion_optional must be a bool.")
        if effect_selection is None:
            return None if companion_optional is True else "companion_unit_instance_id_required"
        if (
            _effect_selection_string_or_none(
                effect_selection=effect_selection,
                key="effect_selection_kind",
            )
            != SELECTED_FRIENDLY_COMPANION_UNIT_EFFECT_SELECTION_KIND
        ):
            return "effect_selection_kind_mismatch"
        if companion_unit_id_or_none(effect_selection) is None:
            return "companion_unit_instance_id_required"
        return None
    if selection_kind == CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND:
        if effect_selection is None:
            return f"{OBJECTIVE_MARKER_CONTEXT_KEY}_required"
        field_error = _required_effect_selection_fields_error(
            effect_selection=effect_selection,
            field_names=(OBJECTIVE_MARKER_CONTEXT_KEY,),
        )
        if field_error is not None:
            return field_error
        if (
            _effect_selection_string_or_none(
                effect_selection=effect_selection,
                key="effect_selection_kind",
            )
            != CONTROLLED_OBJECTIVE_MARKER_EFFECT_SELECTION_KIND
        ):
            return "effect_selection_kind_mismatch"
        if objective_marker_id_or_none(effect_selection) is None:
            return f"{OBJECTIVE_MARKER_CONTEXT_KEY}_required"
        return None
    if effect_selection is not None:
        return "effect_selection_not_supported"
    return None


def _selected_command_point_cost(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue,
    decisions: DecisionController | None = None,
    source_decision_request_id: str | None = None,
    source_decision_result_id: str | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> int:
    return _selected_command_point_cost_result(
        state=state,
        definition=definition,
        context=context,
        target_binding=target_binding,
        effect_selection=effect_selection,
        decisions=decisions,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    ).command_point_cost


def _selected_command_point_cost_result(
    *,
    state: GameState,
    definition: StratagemDefinition,
    context: StratagemEligibilityContext,
    target_binding: StratagemTargetBinding | None,
    effect_selection: JsonValue,
    decisions: DecisionController | None = None,
    source_decision_request_id: str | None = None,
    source_decision_result_id: str | None = None,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry | None = None,
) -> StratagemCostModificationResult:
    base_cost: int
    if definition.handler_id != CORE_HEROIC_INTERVENTION_HANDLER_ID:
        base_cost = definition.command_point_cost
    else:
        base_cost = definition.command_point_cost + _heroic_intervention_mode_additional_cost(
            definition=definition,
            effect_selection=effect_selection,
        )
    registry = (
        StratagemCostModifierRegistry.empty()
        if stratagem_cost_modifier_registry is None
        else stratagem_cost_modifier_registry
    )
    return registry.modified_command_point_cost_with_sources(
        StratagemCostModifierContext(
            state=state,
            definition=definition,
            eligibility_context=context,
            target_binding=target_binding,
            effect_selection=effect_selection,
            base_command_point_cost=base_cost,
            current_command_point_cost=base_cost,
            decisions=decisions,
            source_decision_request_id=source_decision_request_id,
            source_decision_result_id=source_decision_result_id,
        )
    )


def _heroic_intervention_mode_error(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> str | None:
    if effect_selection is None:
        return None
    mode = _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
    )
    if mode is None:
        return "heroic_intervention_mode_required"
    if mode not in _heroic_intervention_mode_costs(definition):
        return "heroic_intervention_mode_unknown"
    return None


def _heroic_intervention_mode(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> str:
    if effect_selection is None:
        return HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND
    mode = _effect_selection_string_or_none(
        effect_selection=effect_selection,
        key=HEROIC_INTERVENTION_MODE_CONTEXT_KEY,
    )
    if mode is None or mode not in _heroic_intervention_mode_costs(definition):
        raise GameLifecycleError("Heroic Intervention mode was not prevalidated.")
    return mode


def _heroic_intervention_mode_additional_cost(
    *,
    definition: StratagemDefinition,
    effect_selection: JsonValue,
) -> int:
    mode = _heroic_intervention_mode(definition=definition, effect_selection=effect_selection)
    return _heroic_intervention_mode_costs(definition)[mode]


def _heroic_intervention_mode_costs(definition: StratagemDefinition) -> Mapping[str, int]:
    payload = definition.effect_payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Heroic Intervention source payload requires modes.")
    modes = payload.get("modes")
    if not isinstance(modes, list):
        raise GameLifecycleError("Heroic Intervention source payload modes must be a list.")
    costs: dict[str, int] = {}
    for mode_payload in modes:
        if not isinstance(mode_payload, dict):
            raise GameLifecycleError("Heroic Intervention mode payload must be an object.")
        mode = mode_payload.get("mode")
        cost = mode_payload.get("additional_command_point_cost")
        if type(mode) is not str or type(cost) is not int:
            raise GameLifecycleError("Heroic Intervention mode payload is malformed.")
        costs[_validate_identifier("Heroic Intervention mode", mode)] = _validate_non_negative_int(
            "Heroic Intervention additional CP cost",
            cost,
        )
    if HEROIC_INTERVENTION_MODE_LEAP_TO_DEFEND not in costs:
        raise GameLifecycleError("Heroic Intervention modes require Leap to Defend.")
    return MappingProxyType(dict(sorted(costs.items())))


def _required_effect_selection_fields_error(
    *,
    effect_selection: JsonValue,
    field_names: tuple[str, ...],
) -> str | None:
    if not isinstance(effect_selection, dict):
        return "effect_selection_malformed"
    for field_name in field_names:
        if type(effect_selection.get(field_name)) is not str:
            return f"{field_name}_required"
    return None


def _effect_selection_string_or_none(
    *,
    effect_selection: JsonValue,
    key: str,
) -> str | None:
    if not isinstance(effect_selection, dict):
        return None
    value = effect_selection.get(key)
    if type(value) is not str:
        return None
    return _validate_identifier(key, value)
