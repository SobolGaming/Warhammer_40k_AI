# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_damage_helpers import (
    no_save_damage_order_roll_spec as _no_save_damage_order_roll_spec,
)
from warhammer40k_core.engine.attack_sequence_imports import *
from warhammer40k_core.engine.destruction_reaction_conditions import (
    optional_destruction_reaction_active_effect_requirement_is_met as _optional_destruction_reaction_active_effect_requirement_is_met,
)
from warhammer40k_core.engine.destruction_reaction_conditions import (
    optional_destruction_reaction_trigger_battle_round_is_current as _optional_destruction_reaction_trigger_battle_round_is_current,
)
from warhammer40k_core.engine.destruction_reaction_conditions import (
    optional_destruction_reaction_trigger_conditions_met as _optional_destruction_reaction_trigger_conditions_met,
)

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
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_advance_after_resolved_hit",
    "_apply_damage_after_feel_no_pain",
    "_continue_deadly_demise_after_secondary_destruction_reaction",
    "_deadly_demise_attack_context_from_source_context",
    "_deadly_demise_descriptor",
    "_deadly_demise_mortal_wounds_for_target",
    "_deadly_demise_secondary_continuation_payload",
    "_deadly_demise_source_context_payload",
    "_deadly_demise_target_unit_ids",
    "_destroyed_damage_applications",
    "_destruction_reaction_context_payload",
    "_destruction_reaction_status_if_needed",
    "_destruction_reaction_trigger_threshold",
    "_emit_deadly_demise_mortal_wounds_applied",
    "_emit_mandatory_destruction_reaction_record",
    "_is_deadly_demise_continuation",
    "_no_save_damage_order_roll_spec",
    "_optional_destruction_reaction_active_effect_requirement_is_met",
    "_optional_destruction_reaction_sources_after_trigger_rolls",
    "_optional_destruction_reaction_trigger_battle_round_is_current",
    "_optional_destruction_reaction_trigger_conditions_met",
    "_optional_destruction_reaction_trigger_descriptor",
    "_optional_destruction_reaction_trigger_roll_type",
    "_pre_removal_destruction_reaction_context_payload",
    "_resolve_deadly_demise_before_removal",
    "_resolve_deadly_demise_secondary_destroyed_models",
    "_resolve_lost_wound_stage",
    "_resolve_mandatory_destruction_reactions_before_removal",
    "_route_deadly_demise_mortal_wounds",
    "_save_options_for_allocation",
    "_unit_has_model_within_deadly_demise_range",
)


def _save_options_for_allocation(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    allocated_model_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> tuple[SaveOption, ...]:
    pool = attack_sequence.current_pool()
    cover_result = _cover_for_allocated_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        pool=pool,
        allocated_model_id=allocated_model_id,
    )
    if has_weapon_keyword(
        pool.weapon_profile,
        WeaponKeyword.IGNORES_COVER,
    ) or _target_has_effect_cover_denial(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        cover_result = None
    elif _target_has_effect_cover(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        cover_result = _cover_result_with_effect_source(
            ruleset_descriptor=ruleset_descriptor,
            current_cover_result=cover_result,
            source_rule_id=GO_TO_GROUND_EFFECT_KIND,
            los_cache_key=f"{attack_context['attack_context_id']}:effect-cover",
        )
    elif INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids:
        cover_result = _cover_result_with_effect_source(
            ruleset_descriptor=ruleset_descriptor,
            current_cover_result=cover_result,
            source_rule_id=INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
            los_cache_key=f"{attack_context['attack_context_id']}:indirect-cover",
        )
    no_saves_allowed = (
        _devastating_wounds_resolution_for_attack(
            pool=pool,
            attack_context=attack_context,
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=attack_context["target_unit_instance_id"],
            ).keywords,
        )
        is DevastatingWoundsResolution.NO_SAVES
    )
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    save_options = runtime_modifiers.modified_save_options(
        SaveOptionModifierContext(
            state=state,
            source_phase=attack_sequence.source_phase,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            allocated_model_instance_id=allocated_model_id,
            weapon_profile=pool.weapon_profile,
            save_options=save_options_for_model(
                model=model_by_id(state=state, model_instance_id=allocated_model_id),
                armor_penetration=pool.weapon_profile.armor_penetration.final,
                cover_result=cover_result,
                no_saves_allowed=no_saves_allowed,
            ),
        )
    )
    return _save_options_with_effect_invulnerable(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        armor_penetration=pool.weapon_profile.armor_penetration.final,
        save_options=save_options,
    )


def _resolve_lost_wound_stage(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    model_instance_id: str,
    requested_wounds: int,
    damage_kind: DamageKind,
    saving_throw: SavingThrow | None,
    attack_context: AttackResolutionContextPayload,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    manager: DiceRollManager,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    wounds = _validate_positive_int("requested_wounds", requested_wounds)
    sources = _feel_no_pain_sources_for_attack(
        state=state,
        model_instance_id=model_instance_id,
        attack_context=attack_context,
    )
    decline_allowed = _state_feel_no_pain_decline_allowed(
        state=state,
        model_instance_id=model_instance_id,
    )
    lost_wound_context = _lost_wound_context_payload(
        attack_context=attack_context,
        allocated_model_id=model_instance_id,
        damage_kind=damage_kind,
        requested_wounds=wounds,
        saving_throw=saving_throw,
    )
    if not sources:
        return _apply_damage_after_feel_no_pain(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage_kind=damage_kind,
            resolution=FeelNoPainResolution.declined(requested_wounds=wounds),
            allocated_model_ids=allocated_model_ids,
            hooks=hooks,
            saving_throw_payload=lost_wound_context["saving_throw"],
            manager=manager,
        )
    if len(sources) == 1 and not decline_allowed:
        resolution = resolve_feel_no_pain_rolls(
            manager=manager,
            source=sources[0],
            player_id=attack_context["defender_player_id"],
            model_instance_id=model_instance_id,
            requested_wounds=wounds,
        )
        return _apply_damage_after_feel_no_pain(
            state=state,
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage_kind=damage_kind,
            resolution=resolution,
            allocated_model_ids=allocated_model_ids,
            hooks=hooks,
            saving_throw_payload=lost_wound_context["saving_throw"],
            manager=manager,
        )

    request = build_feel_no_pain_request(
        request_id=state.next_decision_request_id(),
        defender_player_id=attack_context["defender_player_id"],
        lost_wound_context=validate_json_value(lost_wound_context),
        sources=sources,
        decline_allowed=decline_allowed,
    )
    decisions.request_decision(request)
    return (
        attack_sequence,
        allocated_model_ids,
        LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": attack_sequence.source_phase.value,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "attack_context_id": attack_sequence.attack_context_id(),
            },
        ),
    )


def _apply_damage_after_feel_no_pain(
    *,
    state: GameState,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    target_unit_instance_id: str,
    model_instance_id: str,
    damage_kind: DamageKind,
    resolution: FeelNoPainResolution,
    allocated_model_ids: tuple[str, ...],
    hooks: AttackSequenceHooks,
    saving_throw_payload: JsonValue,
    manager: DiceRollManager,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    damage: DamageApplication | None = None
    if resolution.remaining_wounds > 0:
        damage = apply_damage_to_model(
            state=state,
            target_unit_instance_id=target_unit_instance_id,
            model_instance_id=model_instance_id,
            damage=resolution.remaining_wounds,
            damage_kind=damage_kind,
            remove_destroyed_model=False,
        )
    destroyed_model_controller_player_id = attack_context["defender_player_id"]
    attack_sequence, destroyed_transport_status = _begin_destroyed_transport_disembark_if_needed(
        state=state,
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        sources=tuple(
            source
            for source in _state_destruction_reaction_sources(
                state=state,
                model_instance_id=model_instance_id,
            )
            if not source.optional
        ),
    )
    if destroyed_transport_status is not None:
        return attack_sequence, allocated_model_ids, destroyed_transport_status
    mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
    )
    if mandatory_status is not None:
        return attack_sequence, allocated_model_ids, mandatory_status
    if damage is not None and damage.destroyed:
        destroyed_model_placement = _destroyed_model_placement_payload(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
        remove_destroyed_model_from_battlefield(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
    else:
        destroyed_model_placement = None
    destroyed_emission = _emit_damage_event(
        state=state,
        decisions=decisions,
        hooks=hooks,
        attack_sequence=attack_sequence,
        damage=damage,
        saving_throw=None,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=resolution,
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
    )
    if reaction_status is not None:
        return attack_sequence, allocated_model_ids, reaction_status
    return (
        _advance_after_resolved_hit(
            attack_sequence=attack_sequence,
            attack_context=attack_context,
        ),
        allocated_model_ids,
        None,
    )


def _advance_after_resolved_hit(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> AttackSequence:
    hit_roll = HitRoll.from_payload(attack_context["hit_roll"])
    if hit_roll.generated_hits <= attack_sequence.generated_hit_index:
        raise GameLifecycleError("Resolved hit context has invalid generated hits.")
    if attack_sequence.current_gathered_group is not None:
        return attack_sequence
    return attack_sequence.advanced_after_generated_hit(hit_roll)


def _destruction_reaction_status_if_needed(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    destruction_provenance: DestructionProvenance,
    damage: DamageApplication | None,
    destroyed_emission: DestroyedModelEmission | None,
    destroyed_model_controller_player_id: str | None = None,
    continuation: JsonValue = None,
) -> LifecycleStatus | None:
    if damage is None or not damage.destroyed:
        return None
    if destroyed_emission is None:
        raise GameLifecycleError("Destroyed damage requires a destroyed model event.")
    sources = _state_destruction_reaction_sources(
        state=state,
        model_instance_id=damage.model_instance_id,
    )
    if not sources:
        return None
    controller_player_id = (
        attack_context["defender_player_id"]
        if destroyed_model_controller_player_id is None
        else _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        )
    )
    destruction_context = validate_json_value(
        _destruction_reaction_context_payload(
            attack_context=attack_context,
            destruction_provenance=destruction_provenance,
            damage=damage,
            destroyed_emission=destroyed_emission,
            destroyed_model_controller_player_id=controller_player_id,
            continuation=continuation,
        )
    )
    optional_sources = _optional_destruction_reaction_sources_after_trigger_rolls(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        destruction_provenance=destruction_provenance,
        damage=damage,
        destroyed_emission=destroyed_emission,
        sources=tuple(source for source in sources if source.optional),
        destroyed_model_controller_player_id=controller_player_id,
    )
    if not optional_sources:
        return None
    request = build_destruction_reaction_request(
        request_id=state.next_decision_request_id(),
        defender_player_id=controller_player_id,
        destruction_context=destruction_context,
        sources=optional_sources,
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "destruction_reaction_window_opened",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_sequence.attack_context_id(),
            "model_instance_id": damage.model_instance_id,
            "target_unit_instance_id": damage.target_unit_instance_id,
            "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
            "destruction_provenance": destruction_provenance.to_payload(),
            "sources": [source.to_payload() for source in optional_sources],
            "request_id": request.request_id,
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": attack_sequence.source_phase.value,
            "decision_type": SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
            "attack_context_id": attack_sequence.attack_context_id(),
            "model_instance_id": damage.model_instance_id,
            "destruction_source_kind": destruction_provenance.destruction_source_kind.value,
        },
    )


def _optional_destruction_reaction_sources_after_trigger_rolls(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    destruction_provenance: DestructionProvenance,
    damage: DamageApplication,
    destroyed_emission: DestroyedModelEmission,
    sources: tuple[DestructionReactionSource, ...],
    destroyed_model_controller_player_id: str,
) -> tuple[DestructionReactionSource, ...]:
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("Destruction reaction trigger rolls require DiceRollManager.")
    active_sources: list[DestructionReactionSource] = []
    for source in sources:
        descriptor = _optional_destruction_reaction_trigger_descriptor(source)
        if descriptor is None:
            active_sources.append(source)
            continue
        if not _optional_destruction_reaction_trigger_conditions_met(
            state=state,
            destruction_provenance=destruction_provenance,
            damage=damage,
            descriptor=descriptor,
        ):
            decisions.event_log.append(
                "destruction_reaction_trigger_not_applicable",
                {
                    "sequence_id": attack_sequence.sequence_id,
                    "attack_context_id": attack_sequence.attack_context_id(),
                    "model_instance_id": damage.model_instance_id,
                    "target_unit_instance_id": damage.target_unit_instance_id,
                    "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
                    "destruction_provenance": destruction_provenance.to_payload(),
                    "selected_source": source.to_payload(),
                    "descriptor": descriptor,
                },
            )
            continue
        threshold = _destruction_reaction_trigger_threshold(descriptor)
        roll_state = manager.roll(
            DiceRollSpec(
                expression=DiceExpression(quantity=1, sides=6),
                reason="Destruction reaction trigger",
                roll_type=_optional_destruction_reaction_trigger_roll_type(descriptor),
                actor_id=destroyed_model_controller_player_id,
            )
        )
        triggered = roll_state.current_total >= threshold
        decisions.event_log.append(
            "destruction_reaction_trigger_rolled",
            {
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "model_instance_id": damage.model_instance_id,
                "target_unit_instance_id": damage.target_unit_instance_id,
                "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
                "destruction_provenance": destruction_provenance.to_payload(),
                "selected_source": source.to_payload(),
                "descriptor": descriptor,
                "trigger_roll": roll_state.to_payload(),
                "trigger_roll_threshold": threshold,
                "triggered": triggered,
                "attacker_player_id": attack_context["attacker_player_id"],
                "defender_player_id": attack_context["defender_player_id"],
            },
        )
        if triggered:
            active_sources.append(source)
    return tuple(active_sources)


def _optional_destruction_reaction_trigger_descriptor(
    source: DestructionReactionSource,
) -> dict[str, JsonValue] | None:
    if type(source) is not DestructionReactionSource:
        raise GameLifecycleError("Destruction reaction trigger source drift.")
    if not source.optional:
        raise GameLifecycleError("Optional destruction reaction trigger received mandatory source.")
    if source.payload is None:
        return None
    payload = _payload_object(source.payload)
    if "trigger_roll_threshold" not in payload:
        return None
    return payload


def _destruction_reaction_trigger_threshold(descriptor: dict[str, JsonValue]) -> int:
    threshold = _payload_positive_int(descriptor, key="trigger_roll_threshold")
    if threshold > 6:
        raise GameLifecycleError("Destruction reaction trigger threshold must be on a D6.")
    return threshold


def _optional_destruction_reaction_trigger_roll_type(
    descriptor: dict[str, JsonValue],
) -> str:
    raw_roll_type = descriptor.get("trigger_roll_type")
    if raw_roll_type is None:
        return "destruction_reaction_trigger"
    if type(raw_roll_type) is not str or not raw_roll_type.strip():
        raise GameLifecycleError("Destruction reaction trigger_roll_type must be a string.")
    return raw_roll_type


def _resolve_mandatory_destruction_reactions_before_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication | None,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str | None = None,
    sources: tuple[DestructionReactionSource, ...] | None = None,
) -> LifecycleStatus | None:
    if damage is None or not damage.destroyed:
        return None
    controller_player_id = (
        attack_context["defender_player_id"]
        if destroyed_model_controller_player_id is None
        else _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        )
    )
    active_sources = (
        _state_destruction_reaction_sources(
            state=state,
            model_instance_id=damage.model_instance_id,
        )
        if sources is None
        else sources
    )
    mandatory_sources = tuple(source for source in active_sources if not source.optional)
    for source_index, source in enumerate(mandatory_sources):
        if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
            status = _resolve_deadly_demise_before_removal(
                state=state,
                decisions=decisions,
                manager=manager,
                attack_sequence=attack_sequence,
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                destroyed_model_controller_player_id=controller_player_id,
                pending_sources=mandatory_sources[source_index + 1 :],
            )
            if status is not None:
                return status
            continue
        _emit_mandatory_destruction_reaction_record(
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            destroyed_model_controller_player_id=controller_player_id,
            execution_status="recorded_for_action_host",
        )
    return None


def _emit_mandatory_destruction_reaction_record(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    destroyed_model_controller_player_id: str,
    execution_status: str,
    extra_payload: dict[str, JsonValue] | None = None,
) -> None:
    if source.optional:
        raise GameLifecycleError("Mandatory destruction reaction source was optional.")
    payload = {
        "resolution_kind": "mandatory",
        "decision": None,
        "selected_source": source.to_payload(),
        "selected_reaction_kind": source.reaction_kind.value,
        "action_host": _destruction_reaction_action_host(source),
        "execution_status": execution_status,
        "destruction_context": validate_json_value(
            _pre_removal_destruction_reaction_context_payload(
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            )
        ),
        "sequence_id": attack_sequence.sequence_id,
        "attack_context_id": attack_sequence.attack_context_id(),
        "model_instance_id": damage.model_instance_id,
        "target_unit_instance_id": damage.target_unit_instance_id,
        "model_destroyed_event_id": None,
    }
    if extra_payload is not None:
        payload.update(extra_payload)
    decisions.event_log.append("destruction_reaction_resolved", validate_json_value(payload))


def _resolve_deadly_demise_before_removal(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    destroyed_model_controller_player_id: str,
    pending_sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    descriptor = _deadly_demise_descriptor(source)
    trigger_roll_threshold = _payload_positive_int(descriptor, key="trigger_roll_threshold")
    range_inches = _payload_positive_number(descriptor, key="range_inches")
    trigger_roll = manager.roll(
        deadly_demise_trigger_roll_spec(
            source=source,
            player_id=destroyed_model_controller_player_id,
            model_instance_id=damage.model_instance_id,
        )
    )
    trigger_roll_payload = validate_json_value(trigger_roll.to_payload())
    triggered = trigger_roll.current_total >= trigger_roll_threshold
    if not triggered:
        _emit_mandatory_destruction_reaction_record(
            decisions=decisions,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            execution_status="resolved_no_effect",
            extra_payload={
                "deadly_demise": {
                    "descriptor": validate_json_value(descriptor),
                    "trigger_roll": trigger_roll_payload,
                    "triggered": False,
                    "affected_target_unit_ids": [],
                },
            },
        )
        return None
    target_unit_ids = _deadly_demise_target_unit_ids(
        state=state,
        source_model_instance_id=damage.model_instance_id,
        range_inches=range_inches,
    )
    status = _route_deadly_demise_mortal_wounds(
        state=state,
        decisions=decisions,
        manager=manager,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        source=source,
        descriptor=descriptor,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        trigger_roll_payload=trigger_roll_payload,
        target_unit_ids=target_unit_ids,
        pending_sources=pending_sources,
    )
    if status is not None:
        return status
    _emit_mandatory_destruction_reaction_record(
        decisions=decisions,
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        damage=damage,
        saving_throw_payload=saving_throw_payload,
        feel_no_pain=feel_no_pain,
        source=source,
        destroyed_model_controller_player_id=destroyed_model_controller_player_id,
        execution_status="resolved",
        extra_payload={
            "deadly_demise": {
                "descriptor": validate_json_value(descriptor),
                "trigger_roll": trigger_roll_payload,
                "triggered": True,
                "affected_target_unit_ids": list(target_unit_ids),
            },
        },
    )
    return None


def _route_deadly_demise_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
) -> LifecycleStatus | None:
    for target_index, target_unit_id in enumerate(target_unit_ids):
        mortal_wounds, wound_roll_payload = _deadly_demise_mortal_wounds_for_target(
            manager=manager,
            source=source,
            descriptor=descriptor,
            player_id=destroyed_model_controller_player_id,
            target_unit_instance_id=target_unit_id,
        )
        progress = MortalWoundApplicationProgress.start(
            application_id=(
                f"{attack_sequence.sequence_id}:deadly-demise:{source.source_id}:"
                f"{target_unit_id}:mortal-wounds"
            ),
            source_rule_id=source.source_rule_id,
            source_context=_deadly_demise_source_context_payload(
                attack_sequence=attack_sequence,
                attack_context=attack_context,
                damage=damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                descriptor=descriptor,
                destroyed_model_controller_player_id=destroyed_model_controller_player_id,
                trigger_roll_payload=trigger_roll_payload,
                affected_target_unit_ids=target_unit_ids,
                pending_target_unit_ids=target_unit_ids[target_index + 1 :],
                pending_sources=pending_sources,
                wound_roll_payload=wound_roll_payload,
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
            remove_destroyed_models=False,
        )
        if routed.request is not None:
            decisions.request_decision(routed.request)
            return LifecycleStatus.waiting_for_decision(
                stage=GameLifecycleStage.BATTLE,
                decision_request=routed.request,
                payload={
                    "phase": attack_sequence.source_phase.value,
                    "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                    "sequence_id": attack_sequence.sequence_id,
                    "source_rule_id": source.source_rule_id,
                    "source_kind": DEADLY_DEMISE_SOURCE_KIND,
                },
            )
        if routed.application is None:
            raise GameLifecycleError("Deadly Demise mortal wounds did not produce application.")
        _emit_deadly_demise_mortal_wounds_applied(
            decisions=decisions,
            attack_sequence=attack_sequence,
            source=source,
            target_unit_id=target_unit_id,
            mortal_wounds=mortal_wounds,
            application=routed.application,
            wound_roll_payload=wound_roll_payload,
        )
        status = _resolve_deadly_demise_secondary_destroyed_models(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            source_damage=damage,
            saving_throw_payload=saving_throw_payload,
            feel_no_pain=feel_no_pain,
            source=source,
            descriptor=descriptor,
            destroyed_model_controller_player_id=destroyed_model_controller_player_id,
            trigger_roll_payload=trigger_roll_payload,
            affected_target_unit_ids=target_unit_ids,
            pending_target_unit_ids=target_unit_ids[target_index + 1 :],
            pending_sources=pending_sources,
            secondary_damage_applications=_destroyed_damage_applications(
                routed.application.applications
            ),
        )
        if status is not None:
            return status
    return None


def _resolve_deadly_demise_secondary_destroyed_models(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    secondary_damage_applications: tuple[DamageApplication, ...],
) -> LifecycleStatus | None:
    for damage_index, secondary_damage in enumerate(secondary_damage_applications):
        secondary_controller_player_id = unit_owner_player_id(
            state=state,
            unit_instance_id=secondary_damage.target_unit_instance_id,
        )
        secondary_feel_no_pain = FeelNoPainResolution.declined(
            requested_wounds=secondary_damage.requested_damage
        )
        mandatory_status = _resolve_mandatory_destruction_reactions_before_removal(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            damage=secondary_damage,
            saving_throw_payload=None,
            feel_no_pain=secondary_feel_no_pain,
            destroyed_model_controller_player_id=secondary_controller_player_id,
        )
        if mandatory_status is not None:
            return mandatory_status
        destroyed_model_placement = _destroyed_model_placement_payload(
            state=state,
            model_instance_id=secondary_damage.model_instance_id,
        )
        remove_destroyed_model_from_battlefield(
            state=state,
            model_instance_id=secondary_damage.model_instance_id,
        )
        destroyed_emission = _emit_damage_event(
            state=state,
            decisions=decisions,
            hooks=AttackSequenceHooks.empty(),
            attack_sequence=attack_sequence,
            damage=secondary_damage,
            saving_throw=None,
            saving_throw_payload=None,
            feel_no_pain=secondary_feel_no_pain,
            destroyed_model_placement=destroyed_model_placement,
        )
        reaction_status = _destruction_reaction_status_if_needed(
            state=state,
            decisions=decisions,
            manager=manager,
            attack_sequence=attack_sequence,
            attack_context=attack_context,
            destruction_provenance=DestructionProvenance.for_non_attack(
                DestructionSourceKind.DEADLY_DEMISE
            ),
            damage=secondary_damage,
            destroyed_emission=destroyed_emission,
            destroyed_model_controller_player_id=secondary_controller_player_id,
            continuation=_deadly_demise_secondary_continuation_payload(
                attack_context=attack_context,
                source_damage=source_damage,
                saving_throw_payload=saving_throw_payload,
                feel_no_pain=feel_no_pain,
                source=source,
                descriptor=descriptor,
                destroyed_model_controller_player_id=destroyed_model_controller_player_id,
                trigger_roll_payload=trigger_roll_payload,
                affected_target_unit_ids=affected_target_unit_ids,
                pending_target_unit_ids=pending_target_unit_ids,
                pending_sources=pending_sources,
                pending_secondary_damage_applications=secondary_damage_applications[
                    damage_index + 1 :
                ],
            ),
        )
        if reaction_status is not None:
            return reaction_status
    return None


def _continue_deadly_demise_after_secondary_destruction_reaction(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    continuation: JsonValue,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    source_context = _payload_object(continuation)
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
        raise GameLifecycleError("Deadly Demise continuation pending_sources must be a list.")
    pending_sources = tuple(
        DestructionReactionSource.from_payload(cast(DestructionReactionSourcePayload, payload))
        for payload in pending_source_payloads
    )
    pending_secondary_payloads = source_context.get("pending_secondary_damage_applications")
    if not isinstance(pending_secondary_payloads, list):
        raise GameLifecycleError(
            "Deadly Demise continuation pending secondary damage must be a list."
        )
    pending_secondary_damage = tuple(
        DamageApplication.from_payload(cast(DamageApplicationPayload, payload))
        for payload in pending_secondary_payloads
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
        secondary_damage_applications=pending_secondary_damage,
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


def _deadly_demise_secondary_continuation_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    source_damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    pending_secondary_damage_applications: tuple[DamageApplication, ...],
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": DEADLY_DEMISE_SOURCE_KIND,
            "continuation_kind": "secondary_destroyed_model_reaction",
            "attack_context": attack_context,
            "damage_application": source_damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "source": source.to_payload(),
            "descriptor": validate_json_value(descriptor),
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "trigger_roll": validate_json_value(trigger_roll_payload),
            "affected_target_unit_ids": list(affected_target_unit_ids),
            "pending_target_unit_ids": list(pending_target_unit_ids),
            "pending_sources": [pending_source.to_payload() for pending_source in pending_sources],
            "pending_secondary_damage_applications": [
                application.to_payload() for application in pending_secondary_damage_applications
            ],
        }
    )


def _is_deadly_demise_continuation(payload: JsonValue) -> bool:
    if payload is None:
        return False
    if not isinstance(payload, dict):
        raise GameLifecycleError("Destruction reaction continuation must be an object.")
    return (
        payload.get("source_kind") == DEADLY_DEMISE_SOURCE_KIND
        and payload.get("continuation_kind") == "secondary_destroyed_model_reaction"
    )


def _destroyed_damage_applications(
    applications: tuple[DamageApplication, ...],
) -> tuple[DamageApplication, ...]:
    return tuple(application for application in applications if application.destroyed)


def _deadly_demise_mortal_wounds_for_target(
    *,
    manager: DiceRollManager,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    player_id: str,
    target_unit_instance_id: str,
) -> tuple[int, JsonValue]:
    wound_descriptor = _payload_object(descriptor["mortal_wounds"])
    kind = _payload_string(wound_descriptor, key="kind")
    if kind == "fixed":
        return _payload_positive_int(wound_descriptor, key="value"), None
    if kind == "d3":
        reason = (
            f"Deadly Demise mortal wounds for {source.source_id} into {target_unit_instance_id}"
        )
        result = manager.roll_d3(
            reason=reason,
            roll_type="destruction_reaction.deadly_demise.mortal_wounds",
            actor_id=player_id,
        )
        return result.value, validate_json_value(result.to_payload())
    if kind == "d6":
        roll = manager.roll(
            deadly_demise_mortal_wounds_roll_spec(
                source=source,
                player_id=player_id,
                target_unit_instance_id=target_unit_instance_id,
                sides=6,
            )
        )
        return roll.current_total, validate_json_value(roll.to_payload())
    raise GameLifecycleError("Unsupported Deadly Demise mortal-wound descriptor.")


def _emit_deadly_demise_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    source: DestructionReactionSource,
    target_unit_id: str,
    mortal_wounds: int,
    application: MortalWoundApplication,
    wound_roll_payload: JsonValue,
) -> None:
    decisions.event_log.append(
        "deadly_demise_mortal_wounds_applied",
        {
            "sequence_id": attack_sequence.sequence_id,
            "attack_context_id": attack_sequence.attack_context_id(),
            "source": source.to_payload(),
            "source_rule_id": source.source_rule_id,
            "target_unit_instance_id": target_unit_id,
            "mortal_wounds": mortal_wounds,
            "mortal_wound_roll": wound_roll_payload,
            "mortal_wound_application": application.to_payload(),
        },
    )


def _deadly_demise_target_unit_ids(
    *,
    state: GameState,
    source_model_instance_id: str,
    range_inches: float,
) -> tuple[str, ...]:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deadly Demise requires battlefield_state.")
    source_model_id = _validate_identifier("source_model_instance_id", source_model_instance_id)
    try:
        source_placement = battlefield.model_placement_by_id(source_model_id)
    except PlacementError as exc:
        raise GameLifecycleError("Deadly Demise source model must remain placed.") from exc
    source_model = geometry_model_for_placement(
        model=model_by_id(state=state, model_instance_id=source_model_id),
        placement=source_placement,
    )
    placed_model_ids = set(battlefield.placed_model_ids())
    target_unit_ids: list[str] = []
    for army in state.army_definitions:
        for unit in army.units:
            if _unit_has_model_within_deadly_demise_range(
                state=state,
                unit=unit,
                source_model_id=source_model_id,
                source_model=source_model,
                placed_model_ids=placed_model_ids,
                range_inches=range_inches,
            ):
                target_unit_ids.append(unit.unit_instance_id)
    return tuple(sorted(target_unit_ids))


def _unit_has_model_within_deadly_demise_range(
    *,
    state: GameState,
    unit: UnitInstance,
    source_model_id: str,
    source_model: GeometryModel,
    placed_model_ids: set[str],
    range_inches: float,
) -> bool:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Deadly Demise requires battlefield_state.")
    for model in unit.own_models:
        if model.model_instance_id == source_model_id:
            continue
        if not model.is_alive or model.model_instance_id not in placed_model_ids:
            continue
        try:
            placement = battlefield.model_placement_by_id(model.model_instance_id)
        except PlacementError as exc:
            raise GameLifecycleError("Deadly Demise target model placement drift.") from exc
        target_model = geometry_model_for_placement(model=model, placement=placement)
        distance = DistanceMeasurementContext.from_models(source_model, target_model)
        if distance.closest_distance_inches() <= range_inches:
            return True
    return False


def _deadly_demise_descriptor(source: DestructionReactionSource) -> dict[str, JsonValue]:
    if source.reaction_kind is not DestructionReactionKind.DEADLY_DEMISE:
        raise GameLifecycleError("Deadly Demise descriptor requires a Deadly Demise source.")
    payload = _payload_object(source.payload)
    range_inches = _payload_positive_number(payload, key="range_inches")
    mortal_wounds = _payload_object(payload["mortal_wounds"])
    kind = _payload_string(mortal_wounds, key="kind")
    if kind == "fixed":
        _payload_positive_int(mortal_wounds, key="value")
    elif kind not in {"d3", "d6"}:
        raise GameLifecycleError("Unsupported Deadly Demise mortal-wound descriptor.")
    return {
        "trigger_roll_threshold": _validate_d6_target(
            "Deadly Demise trigger_roll_threshold",
            payload["trigger_roll_threshold"],
        ),
        "range_inches": range_inches,
        "mortal_wounds": validate_json_value(mortal_wounds),
    }


def _deadly_demise_source_context_payload(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    source: DestructionReactionSource,
    descriptor: dict[str, JsonValue],
    destroyed_model_controller_player_id: str,
    trigger_roll_payload: JsonValue,
    affected_target_unit_ids: tuple[str, ...],
    pending_target_unit_ids: tuple[str, ...],
    pending_sources: tuple[DestructionReactionSource, ...],
    wound_roll_payload: JsonValue,
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": DEADLY_DEMISE_SOURCE_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attack_context": attack_context,
            "damage_application": damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "source": source.to_payload(),
            "descriptor": validate_json_value(descriptor),
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "trigger_roll": validate_json_value(trigger_roll_payload),
            "affected_target_unit_ids": list(affected_target_unit_ids),
            "pending_target_unit_ids": list(pending_target_unit_ids),
            "pending_sources": [pending_source.to_payload() for pending_source in pending_sources],
            "mortal_wound_roll": validate_json_value(wound_roll_payload),
        }
    )


def _deadly_demise_attack_context_from_source_context(
    source_context: dict[str, JsonValue],
) -> AttackResolutionContextPayload:
    raw_attack_context = source_context["attack_context"]
    if not isinstance(raw_attack_context, dict):
        raise GameLifecycleError("Deadly Demise source context attack_context must be an object.")
    return cast(AttackResolutionContextPayload, raw_attack_context)


def _pre_removal_destruction_reaction_context_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    damage: DamageApplication,
    saving_throw_payload: JsonValue,
    feel_no_pain: FeelNoPainResolution,
    destroyed_model_controller_player_id: str,
) -> JsonValue:
    return validate_json_value(
        {
            "context_kind": "attack_sequence_model_destroyed_pre_removal",
            "attack_context": attack_context,
            "damage_application": damage.to_payload(),
            "saving_throw": validate_json_value(saving_throw_payload),
            "feel_no_pain": feel_no_pain.to_payload(),
            "target_unit_instance_id": damage.target_unit_instance_id,
            "model_instance_id": damage.model_instance_id,
            "destroyed_model_controller_player_id": _validate_identifier(
                "destroyed_model_controller_player_id",
                destroyed_model_controller_player_id,
            ),
            "source_phase": attack_context["source_phase"],
            "source_step": AttackSequenceStep.DAMAGE.value,
            "destroyed_model_rules_triggered": True,
        }
    )


def _destruction_reaction_context_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    destruction_provenance: DestructionProvenance,
    damage: DamageApplication,
    destroyed_emission: DestroyedModelEmission,
    destroyed_model_controller_player_id: str,
    continuation: JsonValue,
) -> DestructionReactionContextPayload:
    if type(damage) is not DamageApplication:
        raise GameLifecycleError("Destruction reaction context requires damage.")
    if not damage.destroyed:
        raise GameLifecycleError("Destruction reaction context requires destroyed damage.")
    return {
        "context_kind": "attack_sequence_model_destroyed",
        "attack_context": attack_context,
        "destruction_provenance": destruction_provenance.to_payload(),
        "damage_application": validate_json_value(damage.to_payload()),
        "model_destroyed_event_id": destroyed_emission.model_destroyed_event_id,
        "damage_event_id": destroyed_emission.damage_event_id,
        "target_unit_instance_id": damage.target_unit_instance_id,
        "model_instance_id": damage.model_instance_id,
        "destroyed_model_controller_player_id": _validate_identifier(
            "destroyed_model_controller_player_id",
            destroyed_model_controller_player_id,
        ),
        "source_phase": attack_context["source_phase"],
        "source_step": AttackSequenceStep.DAMAGE.value,
        "removal_record": validate_json_value(destroyed_emission.removal_record.to_payload()),
        "transition_batch": validate_json_value(destroyed_emission.transition_batch.to_payload()),
        "destroyed_model_rules_triggered": True,
        "continuation": validate_json_value(continuation),
    }
