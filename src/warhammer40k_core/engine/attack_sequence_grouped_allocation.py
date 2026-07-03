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
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import is_destroyed_transport_disembark_proposal_request, invalid_destroyed_transport_disembark_proposal_status, apply_destroyed_transport_disembark_proposal_decision, _continue_pending_destroyed_transport_disembark, _remove_resolved_destroyed_transport_cargo_state, _begin_destroyed_transport_disembark_if_needed, _request_destroyed_transport_disembark_placement, _parse_destroyed_transport_disembark_submission_or_invalid, _destroyed_transport_proposal_parse_failure, _key_error_field, _missing_destroyed_transport_disembark_field, _destroyed_transport_proposal_invalid_status, _destroyed_transport_placement_invalid_status, _request_destroyed_transport_disembark_placement_retry, _resolve_destroyed_transport_disembark_submission, _apply_valid_destroyed_transport_disembark, _destroyed_transport_cargo_state_for_damage, _destroyed_transport_placement, _battlefield_scenario_for_attack_sequence, _objective_markers_for_attack_sequence
    from warhammer40k_core.engine.attack_sequence_group_selection import _select_or_request_next_gathered_group, _record_auto_attack_sequence_selection, apply_allocation_order_decision, apply_damage_allocation_model_decision, current_legal_damage_allocation_model_ids, apply_precision_allocation_decision, apply_feel_no_pain_decision, apply_destruction_reaction_decision, _continue_grouped_damage_after_interruption, _apply_deferred_mortal_wounds, _emit_deferred_mortal_wounds_applied, _apply_deferred_mortal_wound_feel_no_pain_decision, _continue_hazardous_after_mortal_wound_feel_no_pain, _continue_deadly_demise_after_mortal_wound_feel_no_pain, _grouped_precision_request_if_available, _precision_grouped_allocation_context_and_groups, _build_precision_allocation_request, _precision_pool_selection, _resolve_grouped_current_pool, _grouped_wounded_contexts_for_pool, _defer_grouped_devastating_wounds
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
    "_advance_after_current_pool",
    "_alive_allocated_model_ids",
    "_alive_allocated_model_ids_for_target_unit",
    "_attack_sequence_for_context",
    "_continue_after_grouped_allocation_order",
    "_continue_grouped_allocation_for_wound_contexts",
    "_emit_grouped_allocation_event",
    "_emit_grouped_save_die_event",
    "_grouped_attack_context_payload",
    "_resolve_grouped_damage_from",
    "_roll_grouped_saves",
)


def _continue_grouped_allocation_for_wound_contexts(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    priority_group_ids: tuple[str, ...] = (),
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if not wounded_contexts:
        raise GameLifecycleError("Grouped allocation requires wounded contexts.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    pool = attack_sequence.current_pool()
    grouped_attack_context = _grouped_attack_context_payload(
        attack_sequence=attack_sequence,
        attack_contexts=tuple(context for _, context in wounded_contexts),
        pool=pool,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ),
    )
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.PRECISION):
        precision_selection = _precision_pool_selection(
            decisions=decisions,
            attack_sequence=attack_sequence,
        )
        if not precision_selection.selection_recorded:
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
        if precision_selection.selected_group_id is not None:
            allocation_context, allocation_groups, priority_group_ids = (
                _precision_grouped_allocation_context_and_groups(
                    state=state,
                    target_unit_instance_id=pool.target_unit_instance_id,
                    allocated_model_ids=allocated_model_ids,
                    precision_selection=precision_selection,
                )
            )
    allocation_orders = legal_allocation_group_orders(
        allocation_groups,
        priority_group_ids=priority_group_ids,
    )
    if not allocation_orders:
        raise GameLifecycleError("Grouped allocation has no legal group order.")
    if len(allocation_orders) > 1:
        request = build_allocation_order_request(
            request_id=state.next_decision_request_id(),
            defender_player_id=grouped_attack_context["defender_player_id"],
            attack_context=validate_json_value(grouped_attack_context),
            attack_contexts=tuple(validate_json_value(context) for _, context in wounded_contexts),
            allocation_context=allocation_context,
            allocation_groups=allocation_groups,
            priority_group_ids=priority_group_ids,
        )
        decisions.request_decision(request)
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.ALLOCATE,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=grouped_attack_context["attack_context_id"],
                pool_index=attack_sequence.pool_index,
                attack_index=0,
                payload=validate_json_value(
                    {
                        "allocation_context": allocation_context.to_payload(),
                        "allocation_groups": [group.to_payload() for group in allocation_groups],
                        "priority_group_ids": list(priority_group_ids),
                        "attack_context_ids": [
                            context["attack_context_id"] for _, context in wounded_contexts
                        ],
                        "forced": False,
                        "grouped_save_before_allocation": True,
                    }
                ),
            ),
        )
        return (
            attack_sequence,
            allocated_model_ids,
            LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_ALLOCATION_ORDER_DECISION_TYPE,
                    "attack_context_id": grouped_attack_context["attack_context_id"],
                },
            ),
        )
    ordered_groups = _first_allocation_group_order(
        "Grouped allocation orders",
        allocation_orders,
    )
    _emit_grouped_allocation_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        attack_contexts=tuple(context for _, context in wounded_contexts),
        allocation_context=allocation_context,
        allocation_groups=ordered_groups,
    )
    save_results, status = _roll_grouped_saves(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        wounded_contexts=wounded_contexts,
        allocation_group=_first_allocation_group("Grouped allocation order", ordered_groups),
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    pending = PendingGroupedDamage(
        sorted_save_dice=save_results,
        ordered_allocation_group_payloads=tuple(group.to_payload() for group in ordered_groups),
        allocation_context_payload=allocation_context.to_payload(),
        allocated_model_ids=allocated_model_ids,
    )
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(pending),
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )


def _continue_after_grouped_allocation_order(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if not attack_contexts:
        raise GameLifecycleError("Grouped allocation order requires attack contexts.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    ordered_groups = _validate_ordered_allocation_group_tuple(
        "Grouped allocation order allocation_groups",
        allocation_groups,
    )
    wounded_contexts = tuple(
        (
            _attack_sequence_for_context(
                attack_sequence=attack_sequence,
                attack_context=attack_context,
            ),
            attack_context,
        )
        for attack_context in attack_contexts
    )
    _emit_grouped_allocation_event(
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        attack_contexts=attack_contexts,
        allocation_context=allocation_context,
        allocation_groups=ordered_groups,
    )
    save_results, status = _roll_grouped_saves(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        wounded_contexts=wounded_contexts,
        allocation_group=_first_allocation_group("Grouped allocation order", ordered_groups),
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )
    if status is not None:
        return attack_sequence, allocated_model_ids, status
    pending = PendingGroupedDamage(
        sorted_save_dice=save_results,
        ordered_allocation_group_payloads=tuple(group.to_payload() for group in ordered_groups),
        allocation_context_payload=allocation_context.to_payload(),
        allocated_model_ids=allocated_model_ids,
    )
    return _resolve_grouped_damage_from(
        state=state,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        manager=manager,
        attack_sequence=attack_sequence.with_pending_grouped_damage(pending),
        hooks=hooks,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifiers,
    )


def _resolve_grouped_damage_from(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    selected_model_id: str | None = None,
    stratagem_index: StratagemCatalogIndex | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if attack_sequence.pending_grouped_damage is None:
        raise GameLifecycleError("Grouped damage resume requires pending grouped damage.")
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    pool = attack_sequence.current_pool()
    current_pending = attack_sequence.pending_grouped_damage
    while current_pending.next_index < len(current_pending.sorted_save_dice):
        save_die = current_pending.sorted_save_dice[current_pending.next_index]
        attack_context = save_die["attack_context"]
        save_attack_sequence = _attack_sequence_for_context(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        )
        ordered_groups = current_pending.ordered_allocation_groups()
        current_group = _current_allocation_group_for_order(
            state=state,
            allocation_groups=ordered_groups,
        )
        if current_group is None:
            return (
                _advance_after_current_pool(
                    attack_sequence=attack_sequence.without_pending_grouped_damage()
                ),
                current_pending.allocated_model_ids,
                None,
            )
        base_allocation_context = current_pending.allocation_context()
        allocation_context = allocation_context_for_unit(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
            already_allocated_model_ids=_alive_allocated_model_ids_for_target_unit(
                state=state,
                target_unit_instance_id=pool.target_unit_instance_id,
                allocated_model_ids=current_pending.allocated_model_ids,
            ),
            attacker_constraint=base_allocation_context.attacker_constraint,
        )
        legal_group_model_ids = _legal_model_ids_for_allocation_group_damage(
            state=state,
            allocation_group=current_group,
        )
        if not legal_group_model_ids:
            raise GameLifecycleError("Allocation group has no alive legal damage models.")
        if selected_model_id is not None:
            current_model_id = _validate_identifier(
                "selected_model_id",
                selected_model_id,
            )
            if current_model_id not in legal_group_model_ids:
                raise GameLifecycleError("Selected damage allocation model is not legal.")
            allocation_forced = False
            selected_model_id = None
        elif len(legal_group_model_ids) > 1:
            request = build_damage_allocation_model_request(
                request_id=state.next_decision_request_id(),
                defender_player_id=attack_context["defender_player_id"],
                attack_context=validate_json_value(attack_context),
                allocation_context=allocation_context,
                allocation_group=current_group,
                legal_model_ids=legal_group_model_ids,
                save_die=validate_json_value(save_die),
            )
            decisions.request_decision(request)
            return (
                attack_sequence.with_pending_grouped_damage(current_pending),
                current_pending.allocated_model_ids,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=request,
                    payload={
                        "phase": attack_sequence.source_phase.value,
                        "decision_type": SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
                        "attack_context_id": attack_context["attack_context_id"],
                        "allocation_group_id": current_group.group_id,
                    },
                ),
            )
        else:
            current_model_id = next(iter(legal_group_model_ids))
            allocation_forced = True
        updated_allocated_ids = tuple(
            sorted({*current_pending.allocated_model_ids, *current_group.model_ids})
        )
        allocation = AttackAllocation(
            target_unit_instance_id=allocation_context.target_unit_instance_id,
            allocated_model_id=current_model_id,
            legal_model_ids=legal_group_model_ids,
            forced=allocation_forced,
            rule_context=allocation_context,
            source_rule_ids=(
                ()
                if allocation_context.attacker_constraint is None
                else allocation_context.attacker_constraint.source_rule_ids
            ),
        )
        damage_attack_context = cast(
            AttackResolutionContextPayload,
            {
                **attack_context,
                "allocation": allocation.to_payload(),
                "save_options": [],
            },
        )
        save_options = _save_options_for_allocation(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=save_attack_sequence,
            attack_context=attack_context,
            allocated_model_id=current_model_id,
            runtime_modifier_registry=runtime_modifiers,
        )
        if save_options:
            damage_attack_context = cast(
                AttackResolutionContextPayload,
                {
                    **damage_attack_context,
                    "save_options": [option.to_payload() for option in save_options],
                },
            )
        roll_state = DiceRollState.from_payload(save_die["roll_state"])
        saving_throw = (
            None
            if not save_options
            else resolve_saving_throw(options=save_options, roll_state=roll_state)
        )
        _emit_grouped_save_die_event(
            decisions=decisions,
            hooks=hooks,
            attack_sequence=save_attack_sequence,
            attack_context=attack_context,
            roll_state=roll_state,
            saving_throw=saving_throw,
            save_options=save_options,
            allocation_group=current_group,
            allocated_model_id=current_model_id,
        )
        pending_for_die = current_pending.with_allocated_model_ids(updated_allocated_ids)
        if saving_throw is not None and saving_throw.successful:
            _emit_damage_event(
                state=state,
                decisions=decisions,
                hooks=hooks,
                attack_sequence=save_attack_sequence,
                damage=None,
                saving_throw=saving_throw,
            )
            current_pending = pending_for_die.advanced_after_current_die()
            continue
        damage_value, status = _damage_value(
            state=state,
            decisions=decisions,
            manager=manager,
            profile=pool.weapon_profile.damage_profile,
            attack_context_id=damage_attack_context["attack_context_id"],
            attacker_player_id=attack_sequence.attacker_player_id,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
        )
        if status is not None:
            return (
                attack_sequence.with_pending_grouped_damage(pending_for_die),
                pending_for_die.allocated_model_ids,
                status,
            )
        if damage_value is None:
            raise GameLifecycleError("Damage roll did not resolve a value.")
        damage_amount = damage_value + _melta_damage_modifier(
            pool,
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=pool.target_unit_instance_id,
            ).keywords,
        )
        _next_sequence, resolved_allocated_ids, status = _resolve_lost_wound_stage(
            state=state,
            decisions=decisions,
            attack_sequence=save_attack_sequence,
            target_unit_instance_id=pool.target_unit_instance_id,
            model_instance_id=current_model_id,
            requested_wounds=damage_amount,
            damage_kind=DamageKind.NORMAL,
            saving_throw=saving_throw,
            attack_context=damage_attack_context,
            allocated_model_ids=updated_allocated_ids,
            hooks=hooks,
            manager=manager,
        )
        pending_for_die = pending_for_die.with_allocated_model_ids(resolved_allocated_ids)
        if status is not None:
            interrupted_sequence = attack_sequence.with_pending_grouped_damage(pending_for_die)
            if (
                _next_sequence is not None
                and _next_sequence.pending_destroyed_transport_disembark is not None
            ):
                interrupted_sequence = (
                    interrupted_sequence.with_pending_destroyed_transport_disembark(
                        _next_sequence.pending_destroyed_transport_disembark
                    )
                )
            return (
                interrupted_sequence,
                pending_for_die.allocated_model_ids,
                status,
            )
        current_pending = pending_for_die.advanced_after_current_die()
    return (
        _advance_after_current_pool(
            attack_sequence=attack_sequence.without_pending_grouped_damage()
        ),
        current_pending.allocated_model_ids,
        None,
    )


def _alive_allocated_model_ids(
    *,
    state: GameState,
    allocated_model_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        model_id
        for model_id in allocated_model_ids
        if _model_is_alive(state=state, model_instance_id=model_id)
    )


def _alive_allocated_model_ids_for_target_unit(
    *,
    state: GameState,
    target_unit_instance_id: str,
    allocated_model_ids: tuple[str, ...],
) -> tuple[str, ...]:
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    target_model_ids = {model.model_instance_id for model in target_rules_unit.own_models}
    return tuple(
        model_id
        for model_id in allocated_model_ids
        if model_id in target_model_ids and _model_is_alive(state=state, model_instance_id=model_id)
    )


def _advance_after_current_pool(*, attack_sequence: AttackSequence) -> AttackSequence:
    if attack_sequence.is_complete:
        raise GameLifecycleError("Completed AttackSequence cannot advance pool.")
    used_pool_indices = attack_sequence.used_pool_indices
    selected_target_unit_instance_id = attack_sequence.selected_target_unit_instance_id
    current_group = attack_sequence.current_gathered_group
    if current_group is not None:
        used_pool_indices = tuple(sorted({*used_pool_indices, *current_group.pool_indices}))
        if any(
            pool_index not in used_pool_indices
            and pool.target_unit_instance_id == current_group.target_unit_instance_id
            for pool_index, pool in enumerate(attack_sequence.attack_pools)
        ):
            selected_target_unit_instance_id = current_group.target_unit_instance_id
        else:
            selected_target_unit_instance_id = None
    if selected_target_unit_instance_id is None:
        next_pool_index = _first_unresolved_pool_index_from(
            attack_pools=attack_sequence.attack_pools,
            used_pool_indices=used_pool_indices,
        )
    else:
        next_pool_index = _first_unresolved_pool_index_for_target_from(
            attack_pools=attack_sequence.attack_pools,
            used_pool_indices=used_pool_indices,
            target_unit_instance_id=selected_target_unit_instance_id,
        )
    return AttackSequence(
        sequence_id=attack_sequence.sequence_id,
        source_phase=attack_sequence.source_phase,
        attacker_player_id=attack_sequence.attacker_player_id,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=used_pool_indices,
        selected_target_unit_instance_id=selected_target_unit_instance_id,
        pool_index=next_pool_index,
        attack_index=0,
        deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
    )


def _attack_sequence_for_context(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> AttackSequence:
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError("Grouped attack context sequence drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError("Grouped attack context pool drift.")
    return AttackSequence(
        sequence_id=attack_sequence.sequence_id,
        source_phase=attack_sequence.source_phase,
        attacker_player_id=attack_sequence.attacker_player_id,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
        selected_target_unit_instance_id=attack_sequence.selected_target_unit_instance_id,
        current_gathered_group=attack_sequence.current_gathered_group,
        pool_index=attack_context["pool_index"],
        attack_index=attack_context["attack_index"],
        generated_hit_index=attack_context["generated_hit_index"],
        current_hit_roll=(
            None
            if attack_context["generated_hit_index"] == 0
            else HitRoll.from_payload(attack_context["hit_roll"])
        ),
        deferred_mortal_wounds=attack_sequence.deferred_mortal_wounds,
    )


def _grouped_attack_context_payload(
    *,
    attack_sequence: AttackSequence,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    pool: RangedAttackPool,
    defender_player_id: str,
) -> AttackResolutionContextPayload:
    if not attack_contexts:
        raise GameLifecycleError("Grouped attack context requires wound contexts.")
    first_context = attack_contexts[0]
    return {
        **first_context,
        "attack_context_id": (
            f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:grouped"
        ),
        "attack_index": 0,
        "generated_hit_index": 0,
        "defender_player_id": _validate_identifier("defender_player_id", defender_player_id),
        "target_unit_instance_id": pool.target_unit_instance_id,
        "allocation": None,
        "save_options": [],
    }


def _emit_grouped_allocation_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    attack_contexts: tuple[AttackResolutionContextPayload, ...],
    allocation_context: AttackAllocationRuleContext,
    allocation_groups: tuple[AllocationGroup, ...],
) -> None:
    ordered_groups = _validate_ordered_allocation_group_tuple(
        "Grouped allocation event allocation_groups",
        allocation_groups,
    )
    first_group = _first_allocation_group(
        "Grouped allocation event allocation_groups", ordered_groups
    )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.ALLOCATE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=(
                f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:grouped"
            ),
            pool_index=attack_sequence.pool_index,
            attack_index=0,
            payload=validate_json_value(
                {
                    "allocation_group": first_group.to_payload(),
                    "allocation_order_group_ids": [group.group_id for group in ordered_groups],
                    "allocation_groups": [group.to_payload() for group in ordered_groups],
                    "allocation_context": allocation_context.to_payload(),
                    "attack_context_ids": [
                        context["attack_context_id"] for context in attack_contexts
                    ],
                    "forced": True,
                    "grouped_save_before_allocation": True,
                }
            ),
        ),
    )


def _roll_grouped_saves(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    manager: DiceRollManager,
    wounded_contexts: tuple[tuple[AttackSequence, AttackResolutionContextPayload], ...],
    allocation_group: AllocationGroup,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[tuple[SaveDieEntryPayload, ...], LifecycleStatus | None]:
    results: list[SaveDieEntryPayload] = []
    for wounded_sequence, attack_context in wounded_contexts:
        current_model_id = _current_model_id_for_allocation_group(
            state=state,
            allocation_group=allocation_group,
        )
        save_options = _save_options_for_allocation(
            state=state,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=wounded_sequence,
            attack_context=attack_context,
            allocated_model_id=current_model_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        save_roll_option = mandatory_save_option(save_options)
        if save_roll_option is None:
            roll_state = _roll_or_reuse_state(
                manager,
                _no_save_damage_order_roll_spec(
                    player_id=attack_context["defender_player_id"],
                    allocated_model_id=current_model_id,
                    attack_context_id=attack_context["attack_context_id"],
                ),
            )
        else:
            roll_state = _roll_or_reuse_state(
                manager,
                saving_throw_roll_spec(
                    save_kind=save_roll_option.save_kind,
                    player_id=attack_context["defender_player_id"],
                    allocated_model_id=current_model_id,
                    attack_context_id=attack_context["attack_context_id"],
                ),
            )
            status = _request_command_reroll_for_attack_roll_if_available(
                state=state,
                decisions=decisions,
                roll_state=roll_state,
                affected_unit_instance_id=attack_context["target_unit_instance_id"],
                source_phase=battle_phase_kind_from_token(attack_context["source_phase"]),
                stratagem_index=stratagem_index,
                phase_body_status="attack_save_command_reroll_pending",
            )
            if status is not None:
                return (), status
        results.append(
            {
                "roll_state": roll_state.to_payload(),
                "value": roll_state.current_total,
                "attack_context": attack_context,
            }
        )
    return tuple(
        sorted(
            results,
            key=lambda entry: (
                entry["value"],
                entry["attack_context"]["attack_index"],
                entry["attack_context"]["attack_context_id"],
            ),
        )
    ), None


def _emit_grouped_save_die_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    roll_state: DiceRollState,
    saving_throw: SavingThrow | None,
    save_options: tuple[SaveOption, ...],
    allocation_group: AllocationGroup,
    allocated_model_id: str,
) -> None:
    save_option_payloads = [option.to_payload() for option in save_options]
    if saving_throw is None:
        payload = validate_json_value(
            {
                "save_kind": None,
                "target_number": None,
                "roll_state": roll_state.to_payload(),
                "unmodified_roll": roll_state.current_total,
                "final_roll": roll_state.current_total,
                "successful": False,
                "option": None,
                "save_options": save_option_payloads,
                "weapon_profile_id": attack_context["weapon_profile_id"],
                "allocation_group_id": allocation_group.group_id,
                "allocated_model_id": allocated_model_id,
            }
        )
    else:
        payload = validate_json_value(
            {
                **saving_throw.to_payload(),
                "save_options": save_option_payloads,
                "weapon_profile_id": attack_context["weapon_profile_id"],
                "allocation_group_id": allocation_group.group_id,
                "allocated_model_id": allocated_model_id,
            }
        )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.SAVE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context["attack_context_id"],
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=payload,
        ),
    )
