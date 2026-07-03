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
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import _continue_grouped_allocation_for_wound_contexts, _continue_after_grouped_allocation_order, _resolve_grouped_damage_from, _alive_allocated_model_ids, _alive_allocated_model_ids_for_target_unit, _advance_after_current_pool, _attack_sequence_for_context, _grouped_attack_context_payload, _emit_grouped_allocation_event, _roll_grouped_saves, _emit_grouped_save_die_event
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _unit_has_model_within_deadly_demise_range, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_current_allocation_group_for_order",
    "_current_model_id_for_allocation_group",
    "_damage_value",
    "_highest_toughness_for_models",
    "_hit_skill",
    "_legal_model_ids_for_allocation_group_damage",
    "_model_is_alive",
    "_target_unit_toughness",
    "_toughness_values_for_models",
    "attack_pool_attacker_unit_id",
    "cover_for_allocated_model",
)


def cover_for_allocated_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pool: RangedAttackPool,
    allocated_model_id: str,
) -> BenefitOfCoverResult | None:
    return _cover_for_allocated_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pool=pool,
        allocated_model_id=allocated_model_id,
    )


def attack_pool_attacker_unit_id(*, state: GameState, pool: RangedAttackPool) -> str:
    for army in state.army_definitions:
        for unit in army.units:
            if any(
                model.model_instance_id == pool.attacker_model_instance_id
                for model in unit.own_models
            ):
                return unit.unit_instance_id
    raise GameLifecycleError("Attack pool attacker model is unknown.")


def _hit_skill(profile: WeaponProfile) -> int:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Hit roll requires a WeaponProfile.")
    expected = (
        Characteristic.WEAPON_SKILL
        if profile.range_profile.kind is RangeProfileKind.MELEE
        else Characteristic.BALLISTIC_SKILL
    )
    if profile.skill.characteristic is not expected:
        raise GameLifecycleError("Weapon skill characteristic does not match attack kind.")
    return _validate_d6_target("Weapon skill target", profile.skill.final)


def _target_unit_toughness(
    *,
    state: GameState,
    target_unit_instance_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> int:
    allocation_context = allocation_context_for_unit(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    alive_model_ids = allocation_context.alive_model_ids
    if (
        allocation_context.attached_unit_bodyguard_model_ids
        or allocation_context.attached_unit_character_model_ids
    ):
        model_ids = (
            allocation_context.attached_unit_bodyguard_model_ids
            if allocation_context.attached_unit_bodyguard_model_ids
            else alive_model_ids
        )
        base_toughness = _highest_toughness_for_models(
            state=state,
            model_instance_ids=model_ids,
        )
        return runtime_modifiers.modified_unit_characteristic(
            UnitCharacteristicModifierContext(
                state=state,
                unit_instance_id=target_unit_instance_id,
                characteristic=Characteristic.TOUGHNESS,
                base_value=base_toughness,
                current_value=base_toughness,
            )
        )
    toughness_values = _toughness_values_for_models(
        state=state,
        model_instance_ids=alive_model_ids,
    )
    if len(toughness_values) != 1:
        raise GameLifecycleError("Mixed Toughness target units are deferred to Phase 14H/16D.")
    base_toughness = next(iter(toughness_values))
    return runtime_modifiers.modified_unit_characteristic(
        UnitCharacteristicModifierContext(
            state=state,
            unit_instance_id=target_unit_instance_id,
            characteristic=Characteristic.TOUGHNESS,
            base_value=base_toughness,
            current_value=base_toughness,
        )
    )


def _highest_toughness_for_models(
    *,
    state: GameState,
    model_instance_ids: tuple[str, ...],
) -> int:
    toughness_values = _toughness_values_for_models(
        state=state,
        model_instance_ids=model_instance_ids,
    )
    return max(toughness_values)


def _toughness_values_for_models(
    *,
    state: GameState,
    model_instance_ids: tuple[str, ...],
) -> set[int]:
    model_ids = _validate_identifier_tuple("target toughness model IDs", model_instance_ids)
    if not model_ids:
        raise GameLifecycleError("Target unit has no alive models.")
    toughness_values: set[int] = set()
    for model_id in model_ids:
        model = model_by_id(state=state, model_instance_id=model_id)
        for value in model.characteristics:
            if value.characteristic is Characteristic.TOUGHNESS:
                toughness_values.add(value.final)
                break
        else:
            raise GameLifecycleError("Target unit models require Toughness.")
    return toughness_values


def _damage_value(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    profile: DamageProfile,
    attack_context_id: str,
    attacker_player_id: str,
    affected_unit_instance_id: str,
    source_phase: BattlePhase,
    stratagem_index: StratagemCatalogIndex | None,
) -> tuple[int | None, LifecycleStatus | None]:
    if type(profile) is not DamageProfile:
        raise GameLifecycleError("Damage resolution requires a DamageProfile.")
    if profile.fixed_damage is not None:
        return profile.fixed_damage, None
    if profile.dice_expression is None:
        raise GameLifecycleError("DamageProfile requires fixed damage or a dice expression.")
    scope_id = f"{attack_context_id}:damage"
    timing = RandomCharacteristicTiming.PER_ATTACK
    roll_state = _roll_or_reuse_state(
        manager,
        _random_characteristic_roll_spec(
            characteristic=Characteristic.DAMAGE,
            timing=timing,
            scope_id=scope_id,
            expression=profile.dice_expression,
            reason="Phase 13C random Damage roll",
            actor_id=attacker_player_id,
        ),
    )
    status = _request_command_reroll_for_attack_roll_if_available(
        state=state,
        decisions=decisions,
        roll_state=roll_state,
        affected_unit_instance_id=affected_unit_instance_id,
        source_phase=source_phase,
        stratagem_index=stratagem_index,
        phase_body_status="attack_damage_command_reroll_pending",
    )
    if status is not None:
        return None, status
    random_roll = RandomCharacteristicRoll(
        characteristic=Characteristic.DAMAGE,
        timing=timing,
        scope_id=scope_id,
        roll_state=roll_state,
        value=roll_state.current_total,
    )
    _append_replay_resume_unique_event_once(
        decisions=decisions,
        event_type="random_characteristic_rolled",
        payload=validate_json_value(random_roll.to_payload()),
    )
    return random_roll.value, None


def _model_is_alive(*, state: GameState, model_instance_id: str) -> bool:
    model = model_by_id(state=state, model_instance_id=model_instance_id)
    if not model.is_alive:
        return False
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Alive model lookup requires battlefield_state.")
    return model_instance_id in set(battlefield.placed_model_ids())


def _current_model_id_for_allocation_group(
    *,
    state: GameState,
    allocation_group: AllocationGroup,
) -> str:
    if type(allocation_group) is not AllocationGroup:
        raise GameLifecycleError("Current allocation group must be an AllocationGroup.")
    for model_id in allocation_group.ordered_model_ids_for_damage():
        if _model_is_alive(state=state, model_instance_id=model_id):
            return model_id
    raise GameLifecycleError("Allocation group has no alive models.")


def _legal_model_ids_for_allocation_group_damage(
    *,
    state: GameState,
    allocation_group: AllocationGroup,
) -> tuple[str, ...]:
    if type(allocation_group) is not AllocationGroup:
        raise GameLifecycleError("Damage allocation group must be an AllocationGroup.")
    alive_models = tuple(
        model_by_id(state=state, model_instance_id=model_id)
        for model_id in allocation_group.model_ids
        if _model_is_alive(state=state, model_instance_id=model_id)
    )
    wounded_model_ids = tuple(
        model.model_instance_id
        for model in alive_models
        if model.wounds_remaining < model.starting_wounds
    )
    if wounded_model_ids:
        return wounded_model_ids
    return tuple(model.model_instance_id for model in alive_models)


def _current_allocation_group_for_order(
    *,
    state: GameState,
    allocation_groups: tuple[AllocationGroup, ...],
) -> AllocationGroup | None:
    ordered_groups = _validate_ordered_allocation_group_tuple(
        "Current allocation order allocation_groups",
        allocation_groups,
    )
    for group in ordered_groups:
        if any(
            _model_is_alive(state=state, model_instance_id=model_id) for model_id in group.model_ids
        ):
            return group
    return None
