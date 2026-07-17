# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_imports import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
    from warhammer40k_core.engine.attack_sequence_model import ATTACK_ALLOCATION_DECISION_TYPES, SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE, SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE, SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE, KEEP_ALL_MODIFIERS_OPTION_ID, IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID, IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID, IGNORE_ALL_MODIFIERS_OPTION_ID, ATTACK_RESOLUTION_SELECTION_DECISION_TYPES, SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS, DAMAGE_ALLOCATION_RULE_ID, DEADLY_DEMISE_SOURCE_KIND, HAZARDOUS_SOURCE_KIND, _PRECISION_CHARACTER_GROUP_ROLES, attack_sequence_hit_roll_spec, attack_sequence_wound_roll_spec, deadly_demise_trigger_roll_spec, deadly_demise_mortal_wounds_roll_spec, AttackSequenceStep, AttackSequenceEventPayload, HitRollPayload, WoundRollPayload, PsychicAttackModifierIgnoreSelection, AttackSequencePayload, AttackResolutionContextPayload, SaveDieEntryPayload, PendingGroupedDamagePayload, PendingDestroyedTransportDisembarkPayload, LostWoundContextPayload, DestructionReactionContextPayload, DeferredMortalWoundsPayload, HazardousMortalWoundSourceContextPayload, FastDiceGroupPayload, AttackModifierStackSetPayload, IdenticalAttackSignaturePayload, GatheredAttackContributionPayload, GatheredAttackGroupPayload, HitRoll, WoundRoll, AttackSequenceEvent, AttackSequenceEventHandler, AttackSequenceHooks, DestroyedModelEmission, PrecisionPoolSelection, PendingGroupedDamage, PendingDestroyedTransportDisembark, AttackModifierStackSet, DeferredMortalWounds, IdenticalAttackSignature, GatheredAttackContribution, GatheredAttackGroup
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence, FastDiceGroup, attack_sequence_step_from_token, _runtime_modifier_registry, wound_roll_target_number
    from warhammer40k_core.engine.attack_sequence_dispatch import apply_resolve_target_unit_decision, apply_attack_weapon_group_decision, resolve_attack_sequence_until_blocked
    from warhammer40k_core.engine.attack_sequence_group_selection import _select_or_request_next_gathered_group, _record_auto_attack_sequence_selection, apply_allocation_order_decision, apply_damage_allocation_model_decision, current_legal_damage_allocation_model_ids, apply_precision_allocation_decision, apply_feel_no_pain_decision, apply_destruction_reaction_decision, _continue_grouped_damage_after_interruption, _apply_deferred_mortal_wounds, _emit_deferred_mortal_wounds_applied, _apply_deferred_mortal_wound_feel_no_pain_decision, _continue_hazardous_after_mortal_wound_feel_no_pain, _continue_deadly_demise_after_mortal_wound_feel_no_pain, _grouped_precision_request_if_available, _precision_grouped_allocation_context_and_groups, _build_precision_allocation_request, _precision_pool_selection, _resolve_grouped_current_pool, _grouped_wounded_contexts_for_pool, _defer_grouped_devastating_wounds
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import _continue_grouped_allocation_for_wound_contexts, _continue_after_grouped_allocation_order, _resolve_grouped_damage_from, _alive_allocated_model_ids, _alive_allocated_model_ids_for_target_unit, _advance_after_current_pool, _attack_sequence_for_context, _grouped_attack_context_payload, _emit_grouped_allocation_event, _roll_grouped_saves, _emit_grouped_save_die_event
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _unit_has_model_within_deadly_demise_range, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_apply_valid_destroyed_transport_disembark",
    "_battlefield_scenario_for_attack_sequence",
    "_begin_destroyed_transport_disembark_if_needed",
    "_continue_pending_destroyed_transport_disembark",
    "_destroyed_transport_cargo_state_for_damage",
    "_destroyed_transport_placement",
    "_destroyed_transport_placement_invalid_status",
    "_destroyed_transport_proposal_invalid_status",
    "_destroyed_transport_proposal_parse_failure",
    "_key_error_field",
    "_missing_destroyed_transport_disembark_field",
    "_objective_markers_for_attack_sequence",
    "_parse_destroyed_transport_disembark_submission_or_invalid",
    "_remove_resolved_destroyed_transport_cargo_state",
    "_request_destroyed_transport_disembark_placement",
    "_request_destroyed_transport_disembark_placement_retry",
    "_resolve_destroyed_transport_disembark_submission",
    "apply_destroyed_transport_disembark_proposal_decision",
    "invalid_destroyed_transport_disembark_proposal_status",
    "is_destroyed_transport_disembark_proposal_request",
)


def is_destroyed_transport_disembark_proposal_request(request: DecisionRequest) -> bool:
    if type(request) is not DecisionRequest:
        raise GameLifecycleError(
            "Destroyed Transport disembark proposal routing requires a DecisionRequest."
        )
    if request.decision_type != PLACEMENT_PROPOSAL_DECISION_TYPE:
        return False
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    if proposal_request.proposal_kind is not ProposalKind.DISEMBARK:
        return False
    context = proposal_request.context or {}
    return context.get("destruction_timing") == "destroyed_transport"


def invalid_destroyed_transport_disembark_proposal_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    if not is_destroyed_transport_disembark_proposal_request(request):
        raise GameLifecycleError(
            "Destroyed Transport disembark prevalidation received unsupported request."
        )
    result.validate_for_request(request)
    pending = attack_sequence.pending_destroyed_transport_disembark
    if pending is None:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=MovementProposalRequest.from_decision_request_payload(request.payload),
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=request.request_id,
                proposal_kind=ProposalKind.DISEMBARK,
                violation_code="destroyed_transport_context_missing",
                message="Destroyed Transport placement has no pending attack context.",
                field=None,
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal has no pending context.",
        )
    parsed = _parse_destroyed_transport_disembark_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return parsed
    proposal_request, submission = parsed
    proposal_validation = submission.validation_result_for_request(proposal_request)
    if not proposal_validation.is_valid:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=proposal_validation,
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal does not match request.",
        )
    field = _missing_destroyed_transport_disembark_field(submission)
    if field is not None:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="proposal_payload_missing_field",
                message=f"Destroyed Transport disembark proposal missing {field}.",
                field=field,
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal is incomplete.",
        )
    if submission.unit_instance_id != pending.next_unit_instance_id:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_unit_drift",
                message="Destroyed Transport disembark unit does not match pending cargo.",
                field="unit_instance_id",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal unit drifted.",
        )
    if submission.disembark_mode is not DisembarkModeKind.EMERGENCY_DISEMBARK:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_mode_drift",
                message="Destroyed Transport disembark must use Emergency Disembark mode.",
                field="disembark_mode",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal mode drifted.",
        )
    if submission.transport_unit_instance_id != pending.transport_unit_instance_id:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_transport_drift",
                message="Destroyed Transport disembark transport does not match pending context.",
                field="transport_unit_instance_id",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal transport drifted.",
        )
    if submission.transport_movement_status is not TransportMovementStatus.NOT_MOVED:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=ProposalValidationResult.invalid(
                proposal_request_id=proposal_request.request_id,
                proposal_kind=proposal_request.proposal_kind,
                violation_code="destroyed_transport_status_drift",
                message="Destroyed Transport disembark must use destroyed timing.",
                field="transport_movement_status",
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal timing drifted.",
        )
    return None


def apply_destroyed_transport_disembark_proposal_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    if not is_destroyed_transport_disembark_proposal_request(request):
        raise GameLifecycleError(
            "Destroyed Transport disembark apply received unsupported request."
        )
    pending = attack_sequence.pending_destroyed_transport_disembark
    if pending is None:
        raise GameLifecycleError("Destroyed Transport disembark apply requires pending state.")
    parsed = _parse_destroyed_transport_disembark_submission_or_invalid(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if isinstance(parsed, LifecycleStatus):
        return attack_sequence, already_allocated_model_ids, parsed
    proposal_request, submission = parsed
    if (
        submission.transport_unit_instance_id is None
        or submission.disembark_mode is None
        or submission.transport_movement_status is None
    ):
        raise GameLifecycleError("Destroyed Transport disembark submission drifted.")
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    disembark = _resolve_destroyed_transport_disembark_submission(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pending=pending,
        submission=submission,
        dice_manager=manager,
    )
    if not disembark.placement.is_valid:
        status = _destroyed_transport_placement_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            disembark=disembark,
        )
        _request_destroyed_transport_disembark_placement_retry(
            state=state,
            decisions=decisions,
            proposal_request=proposal_request,
            pending=pending,
            rejected_result=result,
        )
        return attack_sequence, already_allocated_model_ids, status
    _apply_valid_destroyed_transport_disembark(
        state=state,
        decisions=decisions,
        disembark=disembark,
        result=result,
        source_phase=attack_sequence.source_phase,
    )
    updated_pending = pending.with_resolved_disembark(disembark)
    updated_sequence = attack_sequence.with_pending_destroyed_transport_disembark(updated_pending)
    routed = apply_transport_hazard_mortal_wounds(
        state=state,
        decisions=decisions,
        disembark=disembark,
        dice_manager=manager,
    )
    if routed.pending_mortal_wound_request is not None:
        return (
            updated_sequence,
            already_allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.pending_mortal_wound_request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "battle_round": state.battle_round,
                    "active_player_id": disembark.player_id,
                    "unit_instance_id": disembark.unit_instance_id,
                    "transport_unit_instance_id": disembark.transport_unit_instance_id,
                    "disembark_mode": disembark.disembark_mode.value,
                    "decision_type": routed.pending_mortal_wound_request.decision_type,
                    "phase_body_status": "destroyed_transport_hazard_feel_no_pain_required",
                },
            ),
        )
    return _continue_pending_destroyed_transport_disembark(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=updated_sequence,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
    )


def _continue_pending_destroyed_transport_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    pending = attack_sequence.pending_destroyed_transport_disembark
    if pending is None:
        raise GameLifecycleError("Destroyed Transport continuation requires pending state.")
    if pending.next_unit_instance_id is not None:
        request = _request_destroyed_transport_disembark_placement(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            pending=pending,
        )
        return (
            attack_sequence,
            allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": PLACEMENT_PROPOSAL_DECISION_TYPE,
                    "unit_instance_id": pending.next_unit_instance_id,
                    "transport_unit_instance_id": pending.transport_unit_instance_id,
                    "phase_body_status": "destroyed_transport_disembark_placement_required",
                },
            ),
        )

    sequence_without_pending = attack_sequence.without_pending_destroyed_transport_disembark()
    _remove_resolved_destroyed_transport_cargo_state(
        state=state,
        transport_unit_instance_id=pending.transport_unit_instance_id,
    )
    mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=sequence_without_pending,
        attack_context=pending.attack_context,
        damage=pending.damage_application,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
        sources=pending.pending_sources,
    )
    if mandatory_status is not None:
        return sequence_without_pending, allocated_model_ids, mandatory_status
    destroyed_model_placement = _destroyed_model_placement_payload(
        state=state,
        model_instance_id=pending.damage_application.model_instance_id,
    )
    remove_destroyed_model_from_battlefield(
        state=state,
        model_instance_id=pending.damage_application.model_instance_id,
    )
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=sequence_without_pending,
        damage=pending.damage_application,
        saving_throw=None,
        saving_throw_payload=pending.saving_throw_payload,
        feel_no_pain=pending.feel_no_pain,
        destroyed_model_placement=destroyed_model_placement,
    )
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=sequence_without_pending,
        attack_context=pending.attack_context,
        destruction_provenance=DestructionProvenance.for_attack(
            weapon_profile=sequence_without_pending.current_pool().weapon_profile,
            attack_context_id=pending.attack_context["attack_context_id"],
        ),
        damage=pending.damage_application,
        destroyed_emission=destroyed_emission,
        destroyed_model_controller_player_id=pending.destroyed_model_controller_player_id,
    )
    if reaction_status is not None:
        return sequence_without_pending, allocated_model_ids, reaction_status
    if sequence_without_pending.pending_grouped_damage is not None:
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=sequence_without_pending,
            allocated_model_ids=allocated_model_ids,
            status=None,
            hooks=hooks,
            dice_manager=manager,
        )
    return (
        _advance_after_resolved_hit(
            attack_sequence=sequence_without_pending,
            attack_context=pending.attack_context,
        ),
        allocated_model_ids,
        None,
    )


def _remove_resolved_destroyed_transport_cargo_state(
    *,
    state: GameState,
    transport_unit_instance_id: str,
) -> None:
    cargo_state = state.transport_cargo_state_for_transport(transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Destroyed Transport cargo state is missing before removal.")
    if cargo_state.embarked_unit_instance_ids:
        raise GameLifecycleError("Destroyed Transport cargo state still has embarked units.")
    state.remove_transport_cargo_state(transport_unit_instance_id)


def _begin_destroyed_transport_disembark_if_needed(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str,
    sources: tuple[DestructionReactionSource, ...] = (),
) -> tuple[AttackSequence, LifecycleStatus | None]:
    if damage is None or not damage.destroyed:
        return attack_sequence, None
    cargo_state = _destroyed_transport_cargo_state_for_damage(state=state, damage=damage)
    if cargo_state is None or not cargo_state.embarked_unit_instance_ids:
        return attack_sequence, None
    pending = PendingDestroyedTransportDisembark(
        attack_context=attack_context,
        damage_application=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        transport_unit_instance_id=cargo_state.transport_unit_instance_id,
        pending_unit_instance_ids=cargo_state.embarked_unit_instance_ids,
        pending_sources=sources,
    )
    updated_sequence = attack_sequence.with_pending_destroyed_transport_disembark(pending)
    request = _request_destroyed_transport_disembark_placement(
        state=state,
        decisions=decisions,
        attack_sequence=updated_sequence,
        pending=pending,
    )
    return (
        updated_sequence,
        LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": attack_sequence.source_phase.value,
                "decision_type": PLACEMENT_PROPOSAL_DECISION_TYPE,
                "unit_instance_id": pending.next_unit_instance_id,
                "transport_unit_instance_id": pending.transport_unit_instance_id,
                "phase_body_status": "destroyed_transport_disembark_placement_required",
            },
        ),
    )


def _request_destroyed_transport_disembark_placement(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    pending: PendingDestroyedTransportDisembark,
) -> DecisionRequest:
    unit_instance_id = pending.next_unit_instance_id
    if unit_instance_id is None:
        raise GameLifecycleError("Destroyed Transport placement request requires pending cargo.")
    attack_context_id = pending.attack_context["attack_context_id"]
    proposal_request = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=pending.destroyed_model_controller_player_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=attack_sequence.source_phase.value,
        unit_instance_id=unit_instance_id,
        proposal_kind=ProposalKind.DISEMBARK,
        source_decision_request_id=f"{attack_context_id}:destroyed-transport",
        source_decision_result_id=f"{attack_context_id}:destroyed-transport",
        placement_kinds=(BattlefieldPlacementKind.DISEMBARK,),
        context={
            "destruction_timing": "destroyed_transport",
            "transport_unit_instance_id": pending.transport_unit_instance_id,
            "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
            "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
            "attack_sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_context_id,
            "destroyed_model_instance_id": pending.damage_application.model_instance_id,
        },
    )
    request = proposal_request.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "destroyed_transport_disembark_placement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": attack_sequence.source_phase.value,
                "active_player_id": pending.destroyed_model_controller_player_id,
                "unit_instance_id": unit_instance_id,
                "transport_unit_instance_id": pending.transport_unit_instance_id,
                "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
                "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
                "request_id": request.request_id,
                "attack_sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_context_id,
                "destroyed_model_instance_id": pending.damage_application.model_instance_id,
                "remaining_embarked_unit_ids": list(pending.pending_unit_instance_ids),
                "phase_body_status": "destroyed_transport_disembark_placement_required",
            }
        ),
    )
    return request


def _parse_destroyed_transport_disembark_submission_or_invalid(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    decisions: DecisionController,
) -> tuple[MovementProposalRequest, PlacementProposalPayload] | LifecycleStatus:
    proposal_request = MovementProposalRequest.from_decision_request_payload(request.payload)
    try:
        submission = PlacementProposalPayload.from_payload(
            cast(PlacementProposalPayloadPayload, _payload_object(result.payload))
        )
    except (GameLifecycleError, PlacementError, KeyError, TypeError) as exc:
        return _destroyed_transport_proposal_invalid_status(
            state=state,
            decisions=decisions,
            result=result,
            proposal_request=proposal_request,
            proposal_validation=_destroyed_transport_proposal_parse_failure(
                proposal_request=proposal_request,
                error=exc,
            ),
            event_type="destroyed_transport_disembark_proposal_invalid",
            message="Destroyed Transport disembark proposal payload is malformed.",
        )
    return proposal_request, submission


def _destroyed_transport_proposal_parse_failure(
    *,
    proposal_request: MovementProposalRequest,
    error: GameLifecycleError | PlacementError | KeyError | TypeError,
) -> ProposalValidationResult:
    if type(error) is KeyError:
        missing = _key_error_field(error)
        return ProposalValidationResult.invalid(
            proposal_request_id=proposal_request.request_id,
            proposal_kind=proposal_request.proposal_kind,
            violation_code="proposal_payload_missing_field",
            message=f"Proposal payload missing required field: {missing}.",
            field=missing,
        )
    message = str(error)
    field: str | None = "attempted_placement"
    violation_code = "proposal_payload_malformed"
    if "proposal_kind" in message:
        field = "proposal_kind"
    elif "disembark_mode" in message or "DisembarkModeKind" in message:
        field = "disembark_mode"
    elif "transport_movement_status" in message or "TransportMovementStatus" in message:
        field = "transport_movement_status"
    elif "transport_unit_instance_id" in message:
        field = "transport_unit_instance_id"
    return ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=violation_code,
        message=f"Proposal payload is malformed: {message}",
        field=field,
    )


def _key_error_field(error: KeyError) -> str:
    if len(error.args) != 1:
        return "payload"
    key = error.args[0]
    if type(key) is str and key.strip():
        return key.strip()
    return "payload"


def _missing_destroyed_transport_disembark_field(
    submission: PlacementProposalPayload,
) -> str | None:
    if submission.transport_unit_instance_id is None:
        return "transport_unit_instance_id"
    if submission.disembark_mode is None:
        return "disembark_mode"
    if submission.transport_movement_status is None:
        return "transport_movement_status"
    return None


def _destroyed_transport_proposal_invalid_status(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    proposal_validation: ProposalValidationResult,
    event_type: str,
    message: str,
) -> LifecycleStatus:
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": proposal_request.actor_id,
            "phase": proposal_request.phase,
            "unit_instance_id": proposal_request.unit_instance_id,
            "proposal_kind": proposal_request.proposal_kind.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": proposal_validation.status,
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
        }
    )
    decisions.event_log.append(event_type, payload)
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message=message,
        payload=payload,
    )


def _destroyed_transport_placement_invalid_status(
    *,
    state: GameState,
    decisions: DecisionController,
    result: DecisionResult,
    proposal_request: MovementProposalRequest,
    disembark: DestroyedTransportDisembark,
) -> LifecycleStatus:
    first_violation = disembark.placement.violations[0]
    proposal_validation = ProposalValidationResult.invalid(
        proposal_request_id=proposal_request.request_id,
        proposal_kind=proposal_request.proposal_kind,
        violation_code=first_violation.violation_code.value,
        message=first_violation.message,
        field=None,
    )
    payload = validate_json_value(
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": disembark.player_id,
            "phase": proposal_request.phase,
            "unit_instance_id": disembark.unit_instance_id,
            "transport_unit_instance_id": disembark.transport_unit_instance_id,
            "disembark_mode": disembark.disembark_mode.value,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "invalid",
            "proposal_validation": validate_json_value(proposal_validation.to_payload()),
            "destroyed_transport_disembark": validate_json_value(disembark.to_payload()),
        }
    )
    decisions.event_log.append("destroyed_transport_disembark_placement_invalid", payload)
    return LifecycleStatus.invalid(
        stage=GameLifecycleStage.BATTLE,
        message="Destroyed Transport disembark placement is not currently legal.",
        payload=payload,
    )


def _request_destroyed_transport_disembark_placement_retry(
    *,
    state: GameState,
    decisions: DecisionController,
    proposal_request: MovementProposalRequest,
    pending: PendingDestroyedTransportDisembark,
    rejected_result: DecisionResult,
) -> DecisionRequest:
    context = proposal_request.context or {}
    attack_sequence_id = context.get("attack_sequence_id")
    attack_context_id = context.get("attack_context_id")
    if type(attack_sequence_id) is not str or not attack_sequence_id:
        raise GameLifecycleError("Destroyed Transport retry missing attack_sequence_id.")
    if type(attack_context_id) is not str or not attack_context_id:
        raise GameLifecycleError("Destroyed Transport retry missing attack_context_id.")
    retry_proposal = MovementProposalRequest(
        request_id=state.next_decision_request_id(),
        decision_type=PLACEMENT_PROPOSAL_DECISION_TYPE,
        actor_id=proposal_request.actor_id,
        game_id=state.game_id,
        battle_round=state.battle_round,
        phase=proposal_request.phase,
        unit_instance_id=proposal_request.unit_instance_id,
        proposal_kind=proposal_request.proposal_kind,
        source_decision_request_id=proposal_request.source_decision_request_id,
        source_decision_result_id=proposal_request.source_decision_result_id,
        placement_kinds=proposal_request.placement_kinds,
        context=dict(proposal_request.context or {}),
    )
    request = retry_proposal.to_decision_request()
    decisions.request_decision(request)
    decisions.event_log.append(
        "destroyed_transport_disembark_placement_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": proposal_request.phase,
                "active_player_id": proposal_request.actor_id,
                "unit_instance_id": proposal_request.unit_instance_id,
                "transport_unit_instance_id": pending.transport_unit_instance_id,
                "disembark_mode": DisembarkModeKind.EMERGENCY_DISEMBARK.value,
                "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
                "request_id": request.request_id,
                "previous_proposal_request_id": proposal_request.request_id,
                "rejected_result_id": rejected_result.result_id,
                "attack_sequence_id": attack_sequence_id,
                "attack_context_id": attack_context_id,
                "destroyed_model_instance_id": pending.damage_application.model_instance_id,
                "remaining_embarked_unit_ids": list(pending.pending_unit_instance_ids),
                "phase_body_status": "destroyed_transport_disembark_placement_required",
            }
        ),
    )
    return request


def _resolve_destroyed_transport_disembark_submission(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pending: PendingDestroyedTransportDisembark,
    submission: PlacementProposalPayload,
    dice_manager: DiceRollManager,
) -> DestroyedTransportDisembark:
    if submission.transport_unit_instance_id is None or submission.disembark_mode is None:
        raise GameLifecycleError("Destroyed Transport disembark submission is incomplete.")
    cargo_state = state.transport_cargo_state_for_transport(submission.transport_unit_instance_id)
    if cargo_state is None:
        raise GameLifecycleError("Destroyed Transport disembark cargo state is missing.")
    unit = unit_by_id(state=state, unit_instance_id=submission.unit_instance_id)
    transport_placement = _destroyed_transport_placement(
        state=state,
        pending=pending,
    )
    selection = DisembarkSelection(
        player_id=pending.destroyed_model_controller_player_id,
        battle_round=state.battle_round,
        unit_instance_id=submission.unit_instance_id,
        transport_unit_instance_id=submission.transport_unit_instance_id,
        attempted_placement=submission.require_unit_placement(),
        disembark_mode=submission.disembark_mode,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=submission.restriction_overrides,
    )
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires battlefield_state.")
    return resolve_destroyed_transport_disembark(
        scenario=_battlefield_scenario_for_attack_sequence(state),
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=unit,
        transport_placement=transport_placement,
        dice_manager=dice_manager,
        battlefield_width_inches=battlefield_state.battlefield_width_inches,
        battlefield_depth_inches=battlefield_state.battlefield_depth_inches,
        terrain_features=battlefield_state.terrain_features,
        objective_markers=_objective_markers_for_attack_sequence(state),
    )


def _apply_valid_destroyed_transport_disembark(
    *,
    state: GameState,
    decisions: DecisionController,
    disembark: DestroyedTransportDisembark,
    result: DecisionResult,
    source_phase: BattlePhase,
) -> None:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires battlefield_state.")
    if disembark.placement.updated_cargo_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires updated cargo state.")
    if disembark.placement.disembarked_unit_state is None:
        raise GameLifecycleError("Destroyed Transport disembark requires disembarked state.")
    state.replace_battlefield_state(
        apply_destroyed_transport_disembark_to_battlefield(
            battlefield_state=battlefield_state,
            disembark=disembark,
        )
    )
    state.replace_transport_cargo_state(disembark.placement.updated_cargo_state)
    state.record_disembarked_unit_state(disembark.placement.disembarked_unit_state)
    decisions.event_log.append(
        "unit_disembarked",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": disembark.player_id,
                "phase": source_phase.value,
                "unit_instance_id": disembark.unit_instance_id,
                "transport_unit_instance_id": disembark.transport_unit_instance_id,
                "disembark_mode": disembark.disembark_mode.value,
                "transport_movement_status": TransportMovementStatus.NOT_MOVED.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "destroyed_transport_unit_disembarked",
                "updated_cargo_state": validate_json_value(
                    disembark.placement.updated_cargo_state.to_payload()
                ),
                "disembarked_unit_state": validate_json_value(
                    disembark.placement.disembarked_unit_state.to_payload()
                ),
                "transition_batch": validate_json_value(
                    disembark.placement.transition_batch.to_payload()
                )
                if disembark.placement.transition_batch is not None
                else None,
                "destroyed_transport_disembark": validate_json_value(disembark.to_payload()),
            }
        ),
    )


def _destroyed_transport_cargo_state_for_damage(
    *,
    state: GameState,
    damage: DamageApplication,
) -> TransportCargoState | None:
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=damage.target_unit_instance_id,
    )
    if not any(
        model.model_instance_id == damage.model_instance_id
        for model in target_rules_unit.own_models
    ):
        raise GameLifecycleError("Destroyed model is not in the damaged unit.")
    target_unit = unit_by_id(
        state=state,
        unit_instance_id=target_rules_unit.component_unit_id_for_model(damage.model_instance_id),
    )
    for cargo_state in state.transport_cargo_states:
        if cargo_state.transport_unit_instance_id == target_unit.unit_instance_id:
            if len(target_unit.own_models) != 1:
                raise GameLifecycleError(
                    "Destroyed Transport orchestration currently requires one model per "
                    "Transport cargo state."
                )
            return cargo_state
    return None


def _destroyed_transport_placement(
    *,
    state: GameState,
    pending: PendingDestroyedTransportDisembark,
) -> UnitPlacement:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Destroyed Transport disembark requires battlefield_state.")
    try:
        return battlefield.unit_placement_by_id(pending.transport_unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Destroyed Transport must still be placed before removal."
        ) from exc


def _battlefield_scenario_for_attack_sequence(state: GameState) -> BattlefieldScenario:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Attack sequence requires battlefield_state.")
    return BattlefieldScenario(
        armies=tuple(state.army_definitions),
        battlefield_state=battlefield,
    )


def _objective_markers_for_attack_sequence(state: GameState) -> tuple[ObjectiveMarker, ...]:
    if state.mission_setup is None:
        return ()
    return tuple(marker.to_objective_marker() for marker in state.mission_setup.objective_markers)
