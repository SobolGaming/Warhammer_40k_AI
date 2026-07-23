# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_imports import *
from warhammer40k_core.engine.attack_sequence_post_roll import (
    defer_grouped_devastating_wounds as _defer_grouped_devastating_wounds,
)

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
    from warhammer40k_core.engine.attack_sequence_model import ATTACK_ALLOCATION_DECISION_TYPES, SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE, SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE, SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE, KEEP_ALL_MODIFIERS_OPTION_ID, IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID, IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID, IGNORE_ALL_MODIFIERS_OPTION_ID, ATTACK_RESOLUTION_SELECTION_DECISION_TYPES, SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS, DAMAGE_ALLOCATION_RULE_ID, DEADLY_DEMISE_SOURCE_KIND, HAZARDOUS_SOURCE_KIND, _PRECISION_CHARACTER_GROUP_ROLES, attack_sequence_hit_roll_spec, attack_sequence_wound_roll_spec, deadly_demise_trigger_roll_spec, deadly_demise_mortal_wounds_roll_spec, AttackSequenceStep, AttackSequenceEventPayload, HitRollPayload, WoundRollPayload, PsychicAttackModifierIgnoreSelection, AttackSequencePayload, AttackResolutionContextPayload, SaveDieEntryPayload, PendingGroupedDamagePayload, PendingDestroyedTransportDisembarkPayload, LostWoundContextPayload, DestructionReactionContextPayload, DeferredMortalWoundsPayload, HazardousMortalWoundSourceContextPayload, FastDiceGroupPayload, AttackModifierStackSetPayload, IdenticalAttackSignaturePayload, GatheredAttackContributionPayload, GatheredAttackGroupPayload, HitRoll, WoundRoll, AttackSequenceEvent, AttackSequenceEventHandler, AttackSequenceHooks, DestroyedModelEmission, PrecisionPoolSelection, PendingGroupedDamage, PendingDestroyedTransportDisembark, AttackModifierStackSet, DeferredMortalWounds, IdenticalAttackSignature, GatheredAttackContribution, GatheredAttackGroup
    from warhammer40k_core.engine.attack_sequence_state import AttackSequence, FastDiceGroup, attack_sequence_step_from_token, _runtime_modifier_registry, wound_roll_target_number
    from warhammer40k_core.engine.attack_sequence_dispatch import apply_resolve_target_unit_decision, apply_attack_weapon_group_decision, resolve_attack_sequence_until_blocked
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import is_destroyed_transport_disembark_proposal_request, invalid_destroyed_transport_disembark_proposal_status, apply_destroyed_transport_disembark_proposal_decision, _continue_pending_destroyed_transport_disembark, _remove_resolved_destroyed_transport_cargo_state, _begin_destroyed_transport_disembark_if_needed, _request_destroyed_transport_disembark_placement, _parse_destroyed_transport_disembark_submission_or_invalid, _destroyed_transport_proposal_parse_failure, _key_error_field, _missing_destroyed_transport_disembark_field, _destroyed_transport_proposal_invalid_status, _destroyed_transport_placement_invalid_status, _request_destroyed_transport_disembark_placement_retry, _resolve_destroyed_transport_disembark_submission, _apply_valid_destroyed_transport_disembark, _destroyed_transport_cargo_state_for_damage, _destroyed_transport_placement, _battlefield_scenario_for_attack_sequence, _objective_markers_for_attack_sequence
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import _continue_grouped_allocation_for_wound_contexts, _continue_after_grouped_allocation_order, _resolve_grouped_damage_from, _alive_allocated_model_ids, _alive_allocated_model_ids_for_target_unit, _advance_after_current_pool, _attack_sequence_for_context, _grouped_attack_context_payload, _emit_grouped_allocation_event, _roll_grouped_saves, _emit_grouped_save_die_event
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _unit_has_model_within_deadly_demise_range, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, validate_destruction_reaction_context_matches_sequence, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_apply_deferred_mortal_wound_feel_no_pain_decision",
    "_apply_deferred_mortal_wounds",
    "_build_precision_allocation_request",
    "_continue_deadly_demise_after_mortal_wound_feel_no_pain",
    "_continue_grouped_damage_after_interruption",
    "_continue_hazardous_after_mortal_wound_feel_no_pain",
    "_defer_grouped_devastating_wounds",
    "_emit_deferred_mortal_wounds_applied",
    "_grouped_precision_request_if_available",
    "_grouped_wounded_contexts_for_pool",
    "_precision_grouped_allocation_context_and_groups",
    "_precision_pool_selection",
    "_record_auto_attack_sequence_selection",
    "_resolve_grouped_current_pool",
    "_select_or_request_next_gathered_group",
    "apply_allocation_order_decision",
    "apply_damage_allocation_model_decision",
    "apply_destruction_reaction_decision",
    "apply_feel_no_pain_decision",
    "apply_precision_allocation_decision",
    "current_legal_damage_allocation_model_ids",
)


def _select_or_request_next_gathered_group(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    current = attack_sequence
    while current.current_gathered_group is None and not current.is_complete:
        target_ids = unresolved_target_unit_ids(current)
        if not target_ids:
            return (
                AttackSequence(
                    sequence_id=current.sequence_id,
                    source_phase=current.source_phase,
                    attacker_player_id=current.attacker_player_id,
                    attacking_unit_instance_id=current.attacking_unit_instance_id,
                    attack_pools=current.attack_pools,
                    used_pool_indices=tuple(range(len(current.attack_pools))),
                    pool_index=len(current.attack_pools),
                    attack_index=0,
                    deferred_mortal_wounds=current.deferred_mortal_wounds,
                ),
                None,
            )
        if current.selected_target_unit_instance_id is None:
            request = build_select_resolve_target_unit_request(
                request_id=state.next_decision_request_id(),
                state=state,
                attack_sequence=current,
            )
            if len(target_ids) > 1:
                decisions.request_decision(request)
                return (
                    current,
                    LifecycleStatus.waiting_for_decision(
                        stage=GameLifecycleStage.BATTLE,
                        decision_request=request,
                        payload={
                            "phase": current.source_phase.value,
                            "decision_type": SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                            "sequence_id": current.sequence_id,
                        },
                    ),
                )
            target_id = next(iter(target_ids))
            _record_auto_attack_sequence_selection(
                decisions=decisions,
                request=request,
                option_id=_resolve_target_option_id(target_id),
            )
            current = current.with_selected_target_unit(target_id)
            continue
        target_unit_instance_id = current.selected_target_unit_instance_id
        groups = gathered_attack_groups_for_target(
            attack_sequence=current,
            target_unit_instance_id=target_unit_instance_id,
        )
        if not groups:
            current = current.without_selected_target_unit()
            continue
        request = build_select_attack_weapon_group_request(
            request_id=state.next_decision_request_id(),
            state=state,
            attack_sequence=current,
            target_unit_instance_id=target_unit_instance_id,
        )
        if len(groups) > 1:
            decisions.request_decision(request)
            return (
                current,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=request,
                    payload={
                        "phase": current.source_phase.value,
                        "decision_type": SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
                        "sequence_id": current.sequence_id,
                        "target_unit_instance_id": target_unit_instance_id,
                    },
                ),
            )
        group = next(iter(groups))
        _record_auto_attack_sequence_selection(
            decisions=decisions,
            request=request,
            option_id=group.group_id,
        )
        current = current.with_current_gathered_group(group)
    return current, None


def _record_auto_attack_sequence_selection(
    *,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
) -> DecisionResult:
    decisions.request_decision(request)
    result = DecisionResult.for_request(
        result_id=f"{request.request_id}:auto-result",
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    decisions.event_log.append(
        "attack_sequence_auto_selection_recorded",
        {
            "request_id": request.request_id,
            "result_id": result.result_id,
            "decision_type": request.decision_type,
            "selected_option_id": option_id,
        },
    )
    return result


def apply_allocation_order_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    request = decisions.record_for_result(result).request
    decision = AllocationOrderDecision.from_result(request=request, result=result)
    request_payload = _payload_object(request.payload)
    raw_attack_contexts = request_payload["attack_contexts"]
    if not isinstance(raw_attack_contexts, list) or not raw_attack_contexts:
        raise GameLifecycleError("Pooled allocation order requires grouped attack contexts.")
    attack_contexts = tuple(
        cast(AttackResolutionContextPayload, raw_context) for raw_context in raw_attack_contexts
    )
    attack_context = cast(AttackResolutionContextPayload, request_payload["attack_context"])
    _validate_grouped_request_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Allocation order",
    )
    return _continue_after_grouped_allocation_order(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_sequence=attack_sequence,
        attack_contexts=attack_contexts,
        allocation_context=decision.allocation_context,
        allocation_groups=decision.ordered_groups(),
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def apply_damage_allocation_model_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    decision = DamageAllocationModelDecision.from_result(request=request, result=result)
    attack_context = cast(AttackResolutionContextPayload, decision.attack_context)
    _validate_attack_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Damage allocation model",
    )
    if attack_sequence.pending_grouped_damage is None:
        raise GameLifecycleError("Damage allocation model decision requires grouped damage.")
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(
            attack_sequence.pending_grouped_damage.with_allocated_model_ids(
                already_allocated_model_ids
            )
        ),
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        selected_model_id=decision.selected_model_id,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def current_legal_damage_allocation_model_ids(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
) -> tuple[str, ...] | None:
    if attack_sequence.pending_grouped_damage is None:
        raise GameLifecycleError("Damage allocation model legality requires grouped damage.")
    current_group = _current_allocation_group_for_order(
        state=state,
        allocation_groups=attack_sequence.pending_grouped_damage.ordered_allocation_groups(),
    )
    if current_group is None:
        return None
    return _legal_model_ids_for_allocation_group_damage(
        state=state,
        allocation_group=current_group,
    )


def apply_precision_allocation_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    result.validate_for_request(request)
    request_payload = _payload_object(request.payload)
    attack_context = cast(AttackResolutionContextPayload, request_payload["attack_context"])
    raw_attack_contexts = request_payload["attack_contexts"]
    if not isinstance(raw_attack_contexts, list) or not raw_attack_contexts:
        raise GameLifecycleError("Pooled Precision allocation requires grouped attack contexts.")
    _validate_grouped_request_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Precision allocation",
    )
    wounded_contexts = tuple(
        (
            _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=cast(AttackResolutionContextPayload, raw_context),
            ),
            cast(AttackResolutionContextPayload, raw_context),
        )
        for raw_context in raw_attack_contexts
    )
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    attack_sequence, normal_wounded_contexts, status = _defer_grouped_devastating_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        wounded_contexts=wounded_contexts,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=_runtime_modifier_registry(runtime_modifier_registry),
        precision_priority_model_ids=_precision_pool_selection(
            decisions=decisions,
            attack_sequence=attack_sequence,
        ).selected_model_ids,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    if not normal_wounded_contexts:
        return (
            _advance_after_current_pool(attack_sequence=attack_sequence),
            already_allocated_model_ids,
            None,
        )
    precision_selection = _precision_pool_selection(
        decisions=decisions,
        attack_sequence=attack_sequence,
    )
    allocation_context, allocation_groups, priority_group_ids = (
        _precision_grouped_allocation_context_and_groups(
            state=state,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            allocated_model_ids=already_allocated_model_ids,
            precision_selection=precision_selection,
        )
    )
    if not priority_group_ids:
        allocation_context = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            already_allocated_model_ids=_alive_allocated_model_ids(
                state=state,
                allocated_model_ids=already_allocated_model_ids,
            ),
        )
        allocation_groups = allocation_groups_for_context(
            state=state,
            allocation_context=allocation_context,
            include_priority_tiers=True,
        )
    return _continue_grouped_allocation_for_wound_contexts(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence,
        allocation_context=allocation_context,
        allocation_groups=allocation_groups,
        wounded_contexts=normal_wounded_contexts,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        priority_group_ids=priority_group_ids,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def apply_feel_no_pain_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks | None = None,
    dice_manager: DiceRollManager | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    record = decisions.record_for_result(result)
    request = record.request
    if is_mortal_wound_feel_no_pain_request(request):
        decision_attack_sequence = attack_sequence
        if attack_sequence.pending_grouped_damage is not None:
            request_payload = _payload_object(request.payload)
            lost_wound_context = _payload_object(request_payload["lost_wound_context"])
            source_context = _payload_object(lost_wound_context["source_context"])
            if source_context["source_kind"] != DEADLY_DEMISE_SOURCE_KIND:
                raise GameLifecycleError(
                    "Pending grouped damage only supports Deadly Demise mortal wound FNP."
                )
            decision_attack_sequence = _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=_deadly_demise_attack_context_from_source_context(source_context),
            )
        updated_sequence, allocated_model_ids, status = (
            _apply_deferred_mortal_wound_feel_no_pain_decision(
                state=state,
                decisions=decisions,
                attack_sequence=decision_attack_sequence,
                result=result,
                request=request,
                already_allocated_model_ids=already_allocated_model_ids,
                dice_manager=dice_manager,
                hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
            )
        )
        if attack_sequence.pending_grouped_damage is None:
            return updated_sequence, allocated_model_ids, status
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
            status=status,
            hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
            dice_manager=dice_manager,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    decision = FeelNoPainDecision.from_result(request=request, result=result)
    request_payload = _payload_object(request.payload)
    source_payloads = request_payload["sources"]
    if not isinstance(source_payloads, list):
        raise GameLifecycleError("Feel No Pain request sources must be a list.")
    sources = tuple(
        FeelNoPainSource.from_payload(cast(FeelNoPainSourcePayload, source_payload))
        for source_payload in source_payloads
    )
    selected_source: FeelNoPainSource | None = None
    if decision.selected_source_id is not None:
        for source in sources:
            if source.source_id == decision.selected_source_id:
                selected_source = source
                break
        if selected_source is None:
            raise GameLifecycleError("Selected Feel No Pain source is not in the request.")
    lost_wound = _lost_wound_context_from_payload(decision.lost_wound_context)
    attack_context = lost_wound["attack_context"]
    _validate_lost_wound_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    )
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    damage_attack_sequence = (
        _attack_sequence_for_context(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        )
        if attack_sequence.pending_grouped_damage is not None
        else attack_sequence
    )
    if selected_source is None:
        resolution = FeelNoPainResolution.declined(requested_wounds=lost_wound["requested_wounds"])
    else:
        resolution = resolve_feel_no_pain_rolls(
            manager=manager,
            source=selected_source,
            player_id=attack_context["defender_player_id"],
            model_instance_id=lost_wound["allocated_model_id"],
            requested_wounds=lost_wound["requested_wounds"],
        )
    updated_sequence, allocated_model_ids, status = _apply_damage_after_feel_no_pain(
        state=state,
        decisions=decisions,
        attack_sequence=damage_attack_sequence,
        attack_context=attack_context,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        model_instance_id=lost_wound["allocated_model_id"],
        damage_kind=damage_kind_from_token(lost_wound["damage_kind"]),
        resolution=resolution,
        allocated_model_ids=already_allocated_model_ids,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        saving_throw_payload=lost_wound["saving_throw"],
        manager=manager,
    )
    if attack_sequence.pending_grouped_damage is None:
        return updated_sequence, allocated_model_ids, status
    return _continue_grouped_damage_after_interruption(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=attack_sequence,
        allocated_model_ids=allocated_model_ids,
        status=status,
        hooks=AttackSequenceHooks.empty() if hooks is None else hooks,
        dice_manager=manager,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def apply_destruction_reaction_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    already_allocated_model_ids: tuple[str, ...],
    dice_manager: DiceRollManager | None = None,
    hooks: AttackSequenceHooks | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    resolved_hooks = AttackSequenceHooks.empty() if hooks is None else hooks
    record = decisions.record_for_result(result)
    request = record.request
    decision = DestructionReactionDecision.from_result(request=request, result=result)
    selected_source = _selected_destruction_reaction_source_from_request(
        request=request,
        selected_source_id=decision.selected_source_id,
    )
    if selected_source is not None and selected_source.reaction_kind is not (
        decision.selected_reaction_kind
    ):
        raise GameLifecycleError("Selected destruction reaction kind drift.")
    context = validate_destruction_reaction_context_matches_sequence(
        attack_sequence=attack_sequence,
        destruction_context=decision.destruction_context,
    )
    if decision.player_id != context["destroyed_model_controller_player_id"]:
        raise GameLifecycleError("Destruction reaction defender drift.")
    if (
        selected_source is not None
        and selected_source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH
    ):
        restore_selected_model_awaiting_fight_on_death(
            state=state,
            decisions=decisions,
            model_destroyed_event_id=context["model_destroyed_event_id"],
            model_instance_id=context["model_instance_id"],
            source_id=selected_source.source_id,
            source_rule_id=selected_source.source_rule_id,
            source_phase=attack_sequence.source_phase,
        )
    decisions.event_log.append(
        "destruction_reaction_resolved",
        {
            "decision": decision.to_payload(),
            "selected_source": None if selected_source is None else selected_source.to_payload(),
            "selected_reaction_kind": (
                None
                if decision.selected_reaction_kind is None
                else decision.selected_reaction_kind.value
            ),
            "action_host": _destruction_reaction_action_host(selected_source),
            "execution_status": (
                "declined" if selected_source is None else "recorded_for_action_host"
            ),
        },
    )
    continuation = context["continuation"]
    if _is_deadly_demise_continuation(continuation):
        manager = (
            DiceRollManager(state.game_id, event_log=decisions.event_log)
            if dice_manager is None
            else dice_manager
        )
        continuation_attack_sequence = attack_sequence
        if attack_sequence.pending_grouped_damage is not None:
            continuation_attack_sequence = _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=_deadly_demise_attack_context_from_source_context(
                    _payload_object(continuation)
                ),
            )
        updated_sequence, allocated_model_ids, status = (
            _continue_deadly_demise_after_secondary_destruction_reaction(
                state=state,
                decisions=decisions,
                manager=manager,
                hooks=resolved_hooks,
                attack_sequence=continuation_attack_sequence,
                already_allocated_model_ids=already_allocated_model_ids,
                continuation=continuation,
            )
        )
        if attack_sequence.pending_grouped_damage is None:
            return updated_sequence, allocated_model_ids, status
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
            status=status,
            hooks=resolved_hooks,
            dice_manager=manager,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    if attack_sequence.pending_grouped_damage is not None:
        return _continue_grouped_damage_after_interruption(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            allocated_model_ids=already_allocated_model_ids,
            status=None,
            hooks=resolved_hooks,
            dice_manager=dice_manager,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    updated_sequence = _advance_after_resolved_hit(
        attack_sequence=attack_sequence,
        attack_context=context["attack_context"],
    )
    return updated_sequence, already_allocated_model_ids, None


def _continue_grouped_damage_after_interruption(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    allocated_model_ids: tuple[str, ...],
    status: LifecycleStatus | None,
    hooks: AttackSequenceHooks,
    dice_manager: DiceRollManager | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    pending = attack_sequence.pending_grouped_damage
    if pending is None:
        raise GameLifecycleError("Grouped damage interruption requires pending grouped damage.")
    updated_pending = pending.with_allocated_model_ids(allocated_model_ids)
    if status is not None:
        return (
            attack_sequence.with_pending_grouped_damage(updated_pending),
            allocated_model_ids,
            status,
        )
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(
            updated_pending.advanced_after_current_die()
        ),
        hooks=hooks,
        runtime_modifier_registry=runtime_modifiers,
    )


def _apply_deferred_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> tuple[AttackSequence, LifecycleStatus | None]:
    if not attack_sequence.deferred_mortal_wounds:
        return attack_sequence, None
    for deferred_index, deferred in enumerate(attack_sequence.deferred_mortal_wounds):
        sequence_after_current_target = attack_sequence.with_pending_deferred_mortal_wounds(
            attack_sequence.deferred_mortal_wounds[deferred_index + 1 :]
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{attack_sequence.sequence_id}:devastating-wounds:"
                f"{deferred.attack_context_id}:mortal-wounds"
            ),
            source_rule_id=DEVASTATING_WOUNDS_RULE_ID,
            source_context=validate_json_value(
                {
                    "source_kind": "devastating_wounds",
                    "sequence_id": attack_sequence.sequence_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "target_unit_instance_id": deferred.target_unit_instance_id,
                    "attack_context_ids": [deferred.attack_context_id],
                }
            ),
            target_unit_instance_id=deferred.target_unit_instance_id,
            defender_player_id=unit_owner_player_id(
                state=state,
                unit_instance_id=deferred.target_unit_instance_id,
            ),
            mortal_wounds=deferred.mortal_wounds,
            spill_over=False,
            priority_model_ids=deferred.priority_model_ids,
        )
        routed = continue_mortal_wound_application(
            state=state,
            request_id=state.next_decision_request_id(),
            progress=progress,
            dice_manager=manager,
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return (
                sequence_after_current_target,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=routed.request,
                    payload={
                        "phase": attack_sequence.source_phase.value,
                        "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
                    },
                ),
            )
        if routed.application is None:
            raise GameLifecycleError("Deferred mortal wounds did not produce application.")
        _emit_deferred_mortal_wounds_applied(
            decisions=decisions,
            attack_sequence=attack_sequence,
            target_unit_id=deferred.target_unit_instance_id,
            attack_context_ids=(deferred.attack_context_id,),
            mortal_wounds=deferred.mortal_wounds,
            application=routed.application,
        )
    return attack_sequence.without_deferred_mortal_wounds(), None


def _emit_deferred_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    target_unit_id: str,
    attack_context_ids: tuple[str, ...],
    mortal_wounds: int,
    application: MortalWoundApplication,
) -> None:
    decisions.event_log.append(
        "devastating_wounds_mortal_wounds_applied",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "target_unit_instance_id": target_unit_id,
            "attack_context_ids": list(attack_context_ids),
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": application.to_payload(),
            "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
        },
    )


def _apply_deferred_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    request: DecisionRequest,
    already_allocated_model_ids: tuple[str, ...],
    dice_manager: DiceRollManager | None,
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    manager = (
        DiceRollManager(state.game_id, event_log=decisions.event_log)
        if dice_manager is None
        else dice_manager
    )
    request_payload = _payload_object(request.payload)
    lost_wound_context = _payload_object(request_payload["lost_wound_context"])
    request_source_context = _payload_object(lost_wound_context["source_context"])
    is_deadly_demise_request = (
        request_source_context.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND
    )
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
        remove_destroyed_models=not is_deadly_demise_request,
    )
    source_context = _payload_object(routed.progress.source_context)
    if source_context.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND:
        return _continue_deadly_demise_after_mortal_wound_feel_no_pain(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            already_allocated_model_ids=already_allocated_model_ids,
            routed=routed,
            hooks=hooks,
        )
    if source_context.get("source_kind") == HAZARDOUS_SOURCE_KIND:
        return _continue_hazardous_after_mortal_wound_feel_no_pain(
            decisions=decisions,
            attack_sequence=attack_sequence,
            already_allocated_model_ids=already_allocated_model_ids,
            routed=routed,
        )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return (
            attack_sequence,
            already_allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": DEVASTATING_WOUNDS_RULE_ID,
                },
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Deferred mortal wound Feel No Pain did not finish routing.")
    raw_attack_context_ids = source_context.get("attack_context_ids")
    if not isinstance(raw_attack_context_ids, list):
        raise GameLifecycleError("Deferred mortal wound source context is missing attacks.")
    attack_context_ids = tuple(
        _validate_identifier("Deferred mortal wound attack_context_id", value)
        for value in raw_attack_context_ids
    )
    _emit_deferred_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        target_unit_id=routed.progress.target_unit_instance_id,
        attack_context_ids=attack_context_ids,
        mortal_wounds=routed.progress.mortal_wounds,
        application=routed.application,
    )
    next_sequence, status = _apply_deferred_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
    )
    return next_sequence, already_allocated_model_ids, status


def _continue_hazardous_after_mortal_wound_feel_no_pain(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    routed: MortalWoundRoutingResult,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    source_context = _hazardous_source_context_from_payload(routed.progress.source_context)
    if source_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError("Hazardous mortal wound source context sequence drift.")
    if source_context["attacking_unit_instance_id"] != attack_sequence.attacking_unit_instance_id:
        raise GameLifecycleError("Hazardous mortal wound source context attacker drift.")
    if source_context["mortal_wounds"] != routed.progress.mortal_wounds:
        raise GameLifecycleError("Hazardous mortal wound source context wound drift.")
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return (
            attack_sequence,
            already_allocated_model_ids,
            _hazardous_feel_no_pain_status(
                attack_sequence=attack_sequence,
                request=routed.request,
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Hazardous mortal wound Feel No Pain did not finish routing.")
    _emit_hazardous_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        source_context=source_context,
        application=routed.application,
    )
    return None, already_allocated_model_ids, None


def _continue_deadly_demise_after_mortal_wound_feel_no_pain(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    routed: MortalWoundRoutingResult,
    hooks: AttackSequenceHooks,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return (
            attack_sequence,
            already_allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": routed.progress.source_rule_id,
                    "source_kind": DEADLY_DEMISE_SOURCE_KIND,
                },
            ),
        )
    if routed.application is None:
        raise GameLifecycleError("Deadly Demise Feel No Pain did not finish routing.")
    source_context = _payload_object(routed.progress.source_context)
    attack_context = _deadly_demise_attack_context_from_source_context(source_context)
    damage = DamageApplication.from_payload(
        cast(DamageApplicationPayload, source_context["damage_application"])
    )
    feel_no_pain = FeelNoPainResolution.from_payload(
        cast(FeelNoPainResolutionPayload, source_context["feel_no_pain"])
    )
    source = DestructionReactionSource.from_payload(
        cast(DestructionReactionSourcePayload, source_context["source"])
    )
    descriptor = _payload_object(source_context["descriptor"])
    destroyed_model_controller_player_id = _payload_string(
        source_context,
        key="destroyed_model_controller_player_id",
    )
    trigger_roll_payload = validate_json_value(source_context["trigger_roll"])
    affected_target_unit_ids = _payload_identifier_tuple(
        source_context,
        key="affected_target_unit_ids",
    )
    pending_target_unit_ids = _payload_identifier_tuple(
        source_context,
        key="pending_target_unit_ids",
    )
    pending_source_payloads = source_context.get("pending_sources")
    if not isinstance(pending_source_payloads, list):
        raise GameLifecycleError("Deadly Demise source context pending_sources must be a list.")
    pending_sources = tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, payload))
        for payload in pending_source_payloads
    )
    _emit_deadly_demise_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        source=source,
        target_unit_id=routed.progress.target_unit_instance_id,
        mortal_wounds=routed.progress.mortal_wounds,
        application=routed.application,
        wound_roll_payload=validate_json_value(source_context["mortal_wound_roll"]),
    )
    status = _resolve_deadly_demise_secondary_destroyed_models(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        source_damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        affected_target_unit_ids=affected_target_unit_ids,
        pending_target_unit_ids=pending_target_unit_ids,
        pending_sources=pending_sources,
        secondary_damage_applications=_destroyed_damage_applications(
            routed.application.applications
        ),
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    status = _route_deadly_demise_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        target_unit_ids=pending_target_unit_ids,
        pending_sources=pending_sources,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    _emit_mandatory_destruction_reaction_record(
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        source=source,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        execution_status="resolved",
        extra_payload={
            "deadly_demise": {
                "descriptor": validate_json_value(descriptor),
                "trigger_roll": trigger_roll_payload,
                "triggered": True,
                "affected_target_unit_ids": list(affected_target_unit_ids),
            },
        },
    )
    status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        sources=pending_sources,
    )
    if status is not None:
        return attack_sequence, already_allocated_model_ids, status
    destroyed_model_placement = _destroyed_model_placement_payload(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    remove_destroyed_model_from_battlefield(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=validate_json_value(source_context["saving_throw"]),
        feel_no_pain=feel_no_pain,
        destroyed_model_placement=destroyed_model_placement,
    )
    reaction_status = _destruction_reaction_status_if_needed(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        destruction_provenance=DestructionProvenance.for_attack(
            weapon_profile=attack_sequence.current_pool().weapon_profile,
            attack_context_id=attack_context["attack_context_id"],
        ),
        damage=damage,
        destroyed_emission=destroyed_emission,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
    )
    if reaction_status is not None:
        return attack_sequence, already_allocated_model_ids, reaction_status
    return (
        _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        ),
        already_allocated_model_ids,
        None,
    )


def _grouped_precision_request_if_available(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    allocated_model_ids: tuple[str, ...],
) -> DecisionRequest | None:
    pool = attack_sequence.current_pool()
    if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION):
        return None
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=attack_context["target_unit_instance_id"],
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state,
            target_unit_instance_id=attack_context["target_unit_instance_id"],
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
        ),
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        visible_model_ids=pool.target_visible_model_ids,
        include_priority_tiers=True,
    )
    eligible_character_groups = tuple(
        group for group in allocation_groups if group.role in _PRECISION_CHARACTER_GROUP_ROLES
    )
    if not eligible_character_groups:
        return None
    request = _build_precision_allocation_request(
        request_id=state.next_decision_request_id(),
        attacker_player_id=attack_context["attacker_player_id"],
        attack_context=validate_json_value(attack_context),
        allocation_context=allocation_context,
        eligible_character_groups=eligible_character_groups,
    )
    return DecisionRequest(
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        payload=validate_json_value(
            {
                **cast(dict[str, JsonValue], request.payload),
                "attack_contexts": [validate_json_value(context) for context in attack_contexts],
            }
        ),
        options=request.options,
    )


def _precision_grouped_allocation_context_and_groups(
    *,
    state: GameState,
    target_unit_instance_id: str,
    allocated_model_ids: tuple[str, ...],
    precision_selection: PrecisionPoolSelection,
) -> tuple[AttackAllocationRuleContext, tuple[AllocationGroup, ...], tuple[str, ...]]:
    if type(precision_selection) is not PrecisionPoolSelection:
        raise GameLifecycleError("Precision grouped allocation selection is invalid.")
    alive_selected_model_ids = tuple(
        model_id
        for model_id in precision_selection.selected_model_ids
        if _model_is_alive(state=state, model_instance_id=model_id)
    )
    attacker_constraint = None
    priority_group_ids: tuple[str, ...] = ()
    if precision_selection.selected_group_id is not None and alive_selected_model_ids:
        attacker_constraint = AttackAllocationConstraint(
            source_rule_ids=(PRECISION_RULE_ID,),
            can_allocate_protected_characters=True,
            attacker_selected_group_id=precision_selection.selected_group_id,
        )
        priority_group_ids = (precision_selection.selected_group_id,)
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=attacker_constraint,
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        include_priority_tiers=True,
    )
    if priority_group_ids and not any(
        group.group_id == priority_group_ids[0] for group in allocation_groups
    ):
        return _precision_grouped_allocation_context_and_groups(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            allocated_model_ids=allocated_model_ids,
            precision_selection=PrecisionPoolSelection(
                selected_group_id=None,
                selected_model_ids=(),
                selection_recorded=precision_selection.selection_recorded,
            ),
        )
    return allocation_context, allocation_groups, priority_group_ids


def _build_precision_allocation_request(
    *,
    request_id: str,
    attacker_player_id: str,
    attack_context: JsonValue,
    allocation_context: AttackAllocationRuleContext,
    eligible_character_groups: tuple[AllocationGroup, ...],
) -> DecisionRequest:
    character_groups = _validate_allocation_group_tuple(
        "Precision eligible_character_groups",
        eligible_character_groups,
    )
    if not character_groups:
        raise GameLifecycleError("Precision allocation request requires eligible characters.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
        actor_id=attacker_player_id,
        payload=validate_json_value(
            {
                "attack_context": attack_context,
                "allocation_context": allocation_context.to_payload(),
                "eligible_character_groups": [group.to_payload() for group in character_groups],
                "decline_option_id": "decline_precision",
                "source_rule_id": PRECISION_RULE_ID,
            }
        ),
        options=(
            DecisionOption(
                option_id="decline_precision",
                label="Decline Precision",
                payload={"selected_group_id": None, "selected_model_ids": []},
            ),
            *(
                DecisionOption(
                    option_id=group.group_id,
                    label=group.group_id,
                    payload={
                        "selected_group_id": group.group_id,
                        "selected_model_ids": list(group.model_ids),
                        "role": group.role.value,
                    },
                )
                for group in character_groups
            ),
        ),
    )


def _precision_pool_selection(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
) -> PrecisionPoolSelection:
    selected_group_id: str | None = None
    selected_model_ids: tuple[str, ...] = ()
    selection_recorded = False
    for record in decisions.records:
        if record.request.decision_type != SELECT_PRECISION_ALLOCATION_DECISION_TYPE:
            continue
        request_payload = _payload_object(record.request.payload)
        attack_context = cast(
            AttackResolutionContextPayload,
            request_payload["attack_context"],
        )
        if attack_context["sequence_id"] != attack_sequence.sequence_id:
            continue
        if attack_context["pool_index"] != attack_sequence.pool_index:
            continue
        current_selected_group_id = _precision_selected_group_id(record.result.payload)
        current_selected_model_ids = _precision_selected_model_ids(record.result.payload)
        if selection_recorded:
            if selected_group_id != current_selected_group_id:
                raise GameLifecycleError("Precision selection must be unique for an attack pool.")
            continue
        selected_group_id = current_selected_group_id
        selected_model_ids = current_selected_model_ids
        selection_recorded = True
    return PrecisionPoolSelection(
        selected_group_id=selected_group_id,
        selected_model_ids=selected_model_ids,
        selection_recorded=selection_recorded,
    )


def _resolve_grouped_current_pool(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if attack_sequence.attack_index != 0:
        raise GameLifecycleError("Pooled attack resolution must enter pools at attack_index 0.")
    if attack_sequence.generated_hit_index != 0 or attack_sequence.current_hit_roll is not None:
        raise GameLifecycleError("Pooled attack resolution cannot start with generated hit state.")
    pool = attack_sequence.current_pool()
    allocation_target_state = damage_allocation_target_state(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    )
    if allocation_target_state is DamageAllocationTargetState.PRESENT_WITHOUT_LIVING_MODELS:
        decisions.event_log.append(
            "attack_pool_not_allocated",
            {
                "sequence_id": attack_sequence.sequence_id,
                "pool_index": attack_sequence.pool_index,
                "target_unit_instance_id": pool.target_unit_instance_id,
                "reason": "target_present_without_living_models",
            },
        )
        return (
            _advance_after_current_pool(attack_sequence=attack_sequence),
            allocated_model_ids,
            None,
        )
    if allocation_target_state is DamageAllocationTargetState.ABSENT:
        raise GameLifecycleError("Pooled attack target is absent from the battlefield.")
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
            allocated_model_ids=allocated_model_ids,
        ),
        attacker_constraint=None,
    )
    allocation_groups = allocation_groups_for_context(
        state=state,
        allocation_context=allocation_context,
        include_priority_tiers=True,
    )
    if not allocation_groups:
        raise GameLifecycleError("Pooled attack resolution has no legal allocation groups.")

    wounded_contexts, status = _grouped_wounded_contexts_for_pool(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    if not wounded_contexts:
        return (
            _advance_after_current_pool(attack_sequence=attack_sequence),
            allocated_model_ids,
            None,
        )
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION):
        precision_selection = _precision_pool_selection(
            decisions=decisions,
            attack_sequence=attack_sequence,
        )
        if not precision_selection.selection_recorded:
            grouped_attack_context = _grouped_attack_context_payload(
                attack_sequence=attack_sequence,
                attack_contexts=tuple(context for _, context in wounded_contexts),
                pool=pool,
                defender_player_id=unit_owner_player_id(
                    state=state,
                    unit_instance_id=pool.target_unit_instance_id,
                ),
            )
            precision_request = _grouped_precision_request_if_available(
                state=state,
                attack_sequence=attack_sequence,
                attack_context=grouped_attack_context,
                attack_contexts=tuple(context for _, context in wounded_contexts),
                allocated_model_ids=allocated_model_ids,
            )
            if precision_request is not None:
                decisions.request_decision(precision_request)
                return (
                    attack_sequence,
                    allocated_model_ids,
                    LifecycleStatus.waiting_for_decision(
                        stage=GameLifecycleStage.BATTLE,
                        decision_request=precision_request,
                        payload={
                            "phase": attack_sequence.source_phase.value,
                            "decision_type": SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
                            "attack_context_id": grouped_attack_context["attack_context_id"],
                        },
                    ),
                )
    attack_sequence, normal_wounded_contexts, status = _defer_grouped_devastating_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        wounded_contexts=wounded_contexts,
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
        precision_priority_model_ids=_precision_pool_selection(
            decisions=decisions,
            attack_sequence=attack_sequence,
        ).selected_model_ids,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    if not normal_wounded_contexts:
        return (
            _advance_after_current_pool(attack_sequence=attack_sequence),
            allocated_model_ids,
            None,
        )
    return _continue_grouped_allocation_for_wound_contexts(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence,
        allocation_context=allocation_context,
        allocation_groups=allocation_groups,
        wounded_contexts=normal_wounded_contexts,
        allocated_model_ids=allocated_model_ids,
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )


def _grouped_wounded_contexts_for_pool(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[
    tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    LifecycleStatus | None,
]:
    pool = attack_sequence.current_pool()
    wounded_contexts: list[tuple[AttackSequence, AttackResolutionContextPayload]] = []
    for attack_index in range(pool.attacks):
        current = AttackSequence(
            sequence_id=attack_sequence.sequence_id,
            source_phase=attack_sequence.source_phase,
            attacker_player_id=attack_sequence.attacker_player_id,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attack_pools=attack_sequence.attack_pools,
            used_pool_indices=attack_sequence.used_pool_indices,
            selected_target_unit_instance_id=attack_sequence.selected_target_unit_instance_id,
            current_gathered_group=attack_sequence.current_gathered_group,
            pool_index=attack_sequence.pool_index,
            attack_index=attack_index,
            deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
        )
        while True:
            attack_context, status = _roll_hit_and_wound(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=current,
                hooks=hooks,
                stratagem_index=stratagem_index,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            if status is not None:
                return (), status
            if attack_context is None:
                break
            if attack_context["wound_roll"]["successful"]:
                wounded_contexts.append((current, attack_context))
            hit_roll = HitRoll.from_payload(attack_context["hit_roll"])
            if current.generated_hit_index + 1 >= hit_roll.generated_hits:
                break
            next_sequence = current.advanced_after_generated_hit(hit_roll)
            if (
                next_sequence.pool_index != current.pool_index
                or next_sequence.attack_index != current.attack_index
            ):
                break
            current = next_sequence
    return tuple(wounded_contexts), None
