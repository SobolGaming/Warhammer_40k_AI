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
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_benefit_of_cover_ballistic_skill_penalty",
    "_cover_result_with_effect_source",
    "_destroyed_model_placement_payload",
    "_destroyed_model_removal_record",
    "_devastating_wounds_resolution_for_attack",
    "_emit_damage_event",
    "_emit_event",
    "_hit_reroll_forbidden_rule_ids",
    "_hit_roll_modifier",
    "_hit_skill_modifier",
    "_melta_damage_modifier",
    "_persisting_hit_roll_modifier",
    "_plunging_fire_ballistic_skill_improvement",
    "_reroll_wound_for_twin_linked_if_needed",
    "_roll_hit",
    "_roll_wound",
    "_save_options_with_effect_invulnerable",
    "_selected_anti_keyword_ability_id",
    "_target_has_effect_cover",
    "_target_has_effect_cover_denial",
    "_unit_instance_id_for_model",
    "_wound_roll_modifier",
)


def _roll_hit(
    *,
    state: GameState,
    manager: DiceRollManager,
    pool: RangedAttackPool,
    attacker_player_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
    psychic_modifier_selection: PsychicAttackModifierIgnoreSelection | None = None,
) -> HitRoll:
    skill_modifier = _hit_skill_modifier(state=state, pool=pool)
    modifier = _hit_roll_modifier(
        state=state,
        pool=pool,
        source_phase=source_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if psychic_modifier_selection is not None:
        if (
            psychic_modifier_selection.skill_modifier != skill_modifier
            or psychic_modifier_selection.hit_roll_modifier != modifier
        ):
            raise GameLifecycleError("Psychic modifier ignore selection context drift.")
        skill_modifier = psychic_modifier_selection.effective_skill_modifier
        modifier = psychic_modifier_selection.effective_hit_roll_modifier
    skill = _hit_skill(pool.weapon_profile) + skill_modifier
    skill = max(2, min(skill, 6))
    is_snap_shooting = (
        FIRE_OVERWATCH_RULE_ID in pool.targeting_rule_ids
        or SNAP_SHOOTING_RULE_ID in pool.targeting_rule_ids
    )
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TORRENT):
        return HitRoll.auto_hit(target_number=skill)
    roll_state = _roll_or_reuse_state(
        manager,
        attack_sequence_hit_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id=attacker_player_id,
            reroll_forbidden_rule_ids=_hit_reroll_forbidden_rule_ids(
                is_snap_shooting=is_snap_shooting,
                targeting_rule_ids=pool.targeting_rule_ids,
            ),
        ),
    )
    unmodified = roll_state.current_total
    capped_modifier = _cap_roll_modifier(modifier)
    final_roll = unmodified + capped_modifier
    if is_snap_shooting:
        base_minimum_success = 6
    elif INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in pool.targeting_rule_ids:
        base_minimum_success = (
            4 if INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID in pool.targeting_rule_ids else 6
        )
    else:
        base_minimum_success = 2
    minimum_success = _runtime_modifier_registry(
        runtime_modifier_registry
    ).minimum_unmodified_hit_success(
        HitRollMinimumUnmodifiedSuccessContext(
            state=state,
            source_phase=source_phase,
            attacking_unit_instance_id=_unit_instance_id_for_model(
                state=state,
                model_instance_id=pool.attacker_model_instance_id,
            ),
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            weapon_profile=pool.weapon_profile,
            targeting_rule_ids=pool.targeting_rule_ids,
            current_minimum_unmodified_success=base_minimum_success,
        )
    )
    unmodified_success_threshold_active = minimum_success < base_minimum_success
    target_keywords = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    ).keywords
    sustained_hits_d3_value: int | None = None
    if unmodified == 6 and (
        weapon_ability_value(
            pool.weapon_profile,
            AbilityKind.SUSTAINED_HITS,
            target_keywords=target_keywords,
        )
        == SUSTAINED_HITS_D3_VALUE
    ):
        sustained_hits_d3_value = manager.roll_d3(
            reason=(
                "Sustained Hits D3 generated hits for "
                f"{pool.weapon_profile_id} attack {attack_context_id}"
            ),
            roll_type="attack_sequence.sustained_hits.generated_hits",
            actor_id=attacker_player_id,
        ).value
    generated_hits = sustained_hits_generated_hits(
        pool.weapon_profile,
        critical_hit=unmodified == 6,
        target_keywords=target_keywords,
        d3_value=sustained_hits_d3_value,
    )
    return HitRoll(
        target_number=skill,
        roll_state=roll_state,
        unmodified_roll=unmodified,
        modifier=modifier,
        capped_modifier=capped_modifier,
        final_roll=final_roll,
        successful=(
            unmodified == 6
            or (unmodified_success_threshold_active and unmodified >= minimum_success)
            or (unmodified >= minimum_success and final_roll >= skill)
        ),
        critical=unmodified == 6,
        minimum_unmodified_success=minimum_success,
        unmodified_success_threshold_active=unmodified_success_threshold_active,
        generated_hits=generated_hits,
    )


def _hit_reroll_forbidden_rule_ids(
    *,
    is_snap_shooting: bool,
    targeting_rule_ids: tuple[str, ...],
) -> tuple[str, ...]:
    rule_ids: list[str] = []
    if is_snap_shooting:
        rule_ids.append(SNAP_SHOOTING_RULE_ID)
    if INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID in targeting_rule_ids:
        rule_ids.append(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID)
    return tuple(dict.fromkeys(rule_ids))


def _roll_wound(
    *,
    manager: DiceRollManager,
    pool: RangedAttackPool,
    toughness: int,
    target_keywords: tuple[str, ...],
    attacker_player_id: str,
    attack_context_id: str,
    wound_modifier: int = 0,
) -> WoundRoll:
    strength = pool.weapon_profile.strength.final
    target_number = wound_roll_target_number(strength=strength, toughness=toughness)
    roll_state = _roll_or_reuse_state(
        manager,
        attack_sequence_wound_roll_spec(
            weapon_profile_id=pool.weapon_profile_id,
            attack_context_id=attack_context_id,
            attacker_player_id=attacker_player_id,
        ),
    )
    unmodified = roll_state.current_total
    capped_modifier = _cap_roll_modifier(wound_modifier)
    final_roll = unmodified + capped_modifier
    critical_threshold = anti_keyword_critical_threshold(
        profile=pool.weapon_profile,
        target_keywords=target_keywords,
        selected_ability_id=_selected_anti_keyword_ability_id(pool),
    )
    if critical_threshold is None:
        critical_threshold = 6
    critical = unmodified >= critical_threshold
    return WoundRoll(
        strength=strength,
        toughness=toughness,
        target_number=target_number,
        roll_state=roll_state,
        unmodified_roll=unmodified,
        modifier=wound_modifier,
        capped_modifier=capped_modifier,
        final_roll=final_roll,
        successful=critical or (unmodified != 1 and final_roll >= target_number),
        critical=critical,
        critical_threshold=critical_threshold,
    )


def _wound_roll_modifier(
    *,
    state: GameState,
    pool: RangedAttackPool,
    source_phase: BattlePhase,
    toughness: int,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> int:
    if type(pool) is not RangedAttackPool:
        raise GameLifecycleError("Wound roll modifier requires a RangedAttackPool.")
    modifier = 0
    if LANCE_RULE_ID in pool.targeting_rule_ids:
        modifier += 1
    modifier += _runtime_modifier_registry(runtime_modifier_registry).wound_roll_modifier(
        WoundRollModifierContext(
            state=state,
            source_phase=source_phase,
            attacking_unit_instance_id=_unit_instance_id_for_model(
                state=state,
                model_instance_id=pool.attacker_model_instance_id,
            ),
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            weapon_profile=pool.weapon_profile,
            strength=pool.weapon_profile.strength.final,
            toughness=toughness,
        )
    )
    return modifier


def _reroll_wound_for_twin_linked_if_needed(
    *,
    manager: DiceRollManager,
    decisions: DecisionController,
    pool: RangedAttackPool,
    initial_wound_roll: WoundRoll,
    toughness: int,
    target_keywords: tuple[str, ...],
    attacker_player_id: str,
    attack_context_id: str,
) -> WoundRoll:
    if initial_wound_roll.successful:
        return initial_wound_roll
    if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TWIN_LINKED):
        return initial_wound_roll
    if initial_wound_roll.roll_state is None:
        raise GameLifecycleError("Twin-linked reroll requires a wound roll state.")
    permission = RerollPermission(
        source_id=TWIN_LINKED_RULE_ID,
        timing_window="attack_sequence.wound",
        owning_player_id=attacker_player_id,
        eligible_roll_type=initial_wound_roll.roll_state.original_result.spec.roll_type,
        component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
    )
    request = manager.build_reroll_request(
        initial_wound_roll.roll_state,
        request_id=f"{attack_context_id}:twin-linked-reroll-request",
        actor_id=attacker_player_id,
        permission=permission,
        extra_payload={
            "source_rule_id": TWIN_LINKED_RULE_ID,
            "attack_context_id": attack_context_id,
            "weapon_profile_id": pool.weapon_profile_id,
        },
    )
    reroll_option_ids = tuple(
        option.option_id for option in request.options if option.option_id != "decline"
    )
    if len(reroll_option_ids) != 1:
        raise GameLifecycleError("Twin-linked reroll must resolve exactly one option.")
    result = DecisionResult.for_request(
        result_id=f"{attack_context_id}:twin-linked-reroll-result",
        request=request,
        selected_option_id=reroll_option_ids[0],
    )
    updated_state = manager.resolve_reroll(
        initial_wound_roll.roll_state,
        request=request,
        result=result,
        record_decision=False,
    )
    unmodified = updated_state.current_total
    capped_modifier = _cap_roll_modifier(initial_wound_roll.modifier)
    final_roll = unmodified + capped_modifier
    critical_threshold = anti_keyword_critical_threshold(
        profile=pool.weapon_profile,
        target_keywords=target_keywords,
        selected_ability_id=_selected_anti_keyword_ability_id(pool),
    )
    if critical_threshold is None:
        critical_threshold = 6
    critical = unmodified >= critical_threshold
    wound_roll = WoundRoll(
        strength=pool.weapon_profile.strength.final,
        toughness=toughness,
        target_number=initial_wound_roll.target_number,
        roll_state=updated_state,
        unmodified_roll=unmodified,
        modifier=initial_wound_roll.modifier,
        capped_modifier=capped_modifier,
        final_roll=final_roll,
        successful=critical or (unmodified != 1 and final_roll >= initial_wound_roll.target_number),
        critical=critical,
        critical_threshold=critical_threshold,
    )
    decisions.event_log.append(
        "weapon_ability_reroll_resolved",
        {
            "source_rule_id": TWIN_LINKED_RULE_ID,
            "attack_context_id": attack_context_id,
            "weapon_profile_id": pool.weapon_profile_id,
            "reroll_request": request.to_payload(),
            "reroll_result": result.to_payload(),
            "wound_roll": wound_roll.to_payload(),
        },
    )
    return wound_roll


def _selected_anti_keyword_ability_id(pool: RangedAttackPool) -> str | None:
    ability_by_id = {ability.ability_id: ability for ability in pool.weapon_profile.abilities}
    selected_ids: list[str] = []
    for ability_id in pool.selected_weapon_ability_ids:
        ability = ability_by_id.get(ability_id)
        if ability is None:
            raise GameLifecycleError(
                "Selected weapon ability ID is not on the attack pool profile."
            )
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD:
            selected_ids.append(ability_id)
    if len(selected_ids) > 1:
        raise GameLifecycleError("Attack pool must not select multiple Anti ability IDs.")
    if not selected_ids:
        return None
    return selected_ids[0]


def _emit_damage_event(
    *,
    state: GameState,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    attack_sequence: AttackSequence,
    damage: DamageApplication | None,
    saving_throw: SavingThrow | None,
    saving_throw_payload: JsonValue | None = None,
    feel_no_pain: FeelNoPainResolution | None = None,
    destroyed_model_placement: JsonValue | None = None,
) -> DestroyedModelEmission | None:
    if saving_throw is not None and saving_throw_payload is not None:
        raise GameLifecycleError("Damage event saving throw payload is ambiguous.")
    resolved_saving_throw: JsonValue
    if saving_throw_payload is not None:
        resolved_saving_throw = saving_throw_payload
    elif saving_throw is not None:
        resolved_saving_throw = validate_json_value(saving_throw.to_payload())
    else:
        resolved_saving_throw = None
    payload = validate_json_value(
        {
            "saving_throw": resolved_saving_throw,
            "damage_application": None if damage is None else damage.to_payload(),
            "feel_no_pain": None if feel_no_pain is None else feel_no_pain.to_payload(),
            "weapon_profile_id": attack_sequence.current_pool().weapon_profile_id,
        }
    )
    damage_event = _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.DAMAGE,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_sequence.attack_context_id(),
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=payload,
        ),
    )
    if damage is not None and damage.destroyed:
        removal_record = _destroyed_model_removal_record(
            model_instance_id=damage.model_instance_id,
            source_phase=attack_sequence.source_phase.value,
            source_event_id=damage_event.event_id,
        )
        transition_batch = BattlefieldTransitionBatch(removals=(removal_record,))
        destroyed_event = decisions.event_log.append(
            "model_destroyed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": attack_sequence.source_phase.value,
                "destroying_player_id": attack_sequence.attacker_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "sequence_id": attack_sequence.sequence_id,
                "attack_context_id": attack_sequence.attack_context_id(),
                "target_unit_instance_id": damage.target_unit_instance_id,
                "model_instance_id": damage.model_instance_id,
                "damage_kind": damage.damage_kind.value,
                "damage_event_id": damage_event.event_id,
                "removal_record": removal_record.to_payload(),
                "transition_batch": transition_batch.to_payload(),
                "destroyed_model_placement": validate_json_value(destroyed_model_placement),
                "destroyed_model_rules_triggered": True,
            },
        )
        return DestroyedModelEmission(
            damage_event_id=damage_event.event_id,
            model_destroyed_event_id=destroyed_event.event_id,
            removal_record=removal_record,
            transition_batch=transition_batch,
        )
    return None


def _destroyed_model_removal_record(
    *,
    model_instance_id: str,
    source_phase: str,
    source_event_id: str,
) -> ModelRemovalRecord:
    return ModelRemovalRecord(
        model_instance_id=model_instance_id,
        removal_kind=BattlefieldRemovalKind.DESTROYED,
        source_phase=source_phase,
        source_step=AttackSequenceStep.DAMAGE.value,
        source_rule_id=DAMAGE_ALLOCATION_RULE_ID,
        source_event_id=source_event_id,
    )


def _destroyed_model_placement_payload(
    *,
    state: GameState,
    model_instance_id: str,
) -> JsonValue:
    if state.battlefield_state is None:
        raise GameLifecycleError("Destroyed model placement capture requires battlefield state.")
    try:
        placement = state.battlefield_state.model_placement_by_id(model_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Destroyed model placement capture requires placed model."
        ) from exc
    return validate_json_value(placement.to_payload())


def _emit_event(
    *,
    decisions: DecisionController,
    hooks: AttackSequenceHooks,
    event: AttackSequenceEvent,
) -> EventRecord:
    emitted = hooks.emit(event)
    return _append_replay_resume_unique_event_once(
        decisions=decisions,
        event_type="attack_sequence_step",
        payload=validate_json_value(emitted.to_payload()),
    )


def _target_has_effect_cover(*, state: GameState, target_unit_instance_id: str) -> bool:
    return unit_effects_grant_benefit_of_cover(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )


def _target_has_effect_cover_denial(*, state: GameState, target_unit_instance_id: str) -> bool:
    return unit_effects_deny_benefit_of_cover(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )


def _benefit_of_cover_ballistic_skill_penalty(
    *,
    state: GameState,
    pool: RangedAttackPool,
) -> int:
    if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.IGNORES_COVER):
        return 0
    if _target_has_effect_cover_denial(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        return 0
    if BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids:
        return 1
    if INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids:
        return 1
    if _target_has_effect_cover(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
    ):
        return 1
    return 0


def _hit_skill_modifier(*, state: GameState, pool: RangedAttackPool) -> int:
    return _benefit_of_cover_ballistic_skill_penalty(
        state=state,
        pool=pool,
    ) - _plunging_fire_ballistic_skill_improvement(pool=pool)


def _hit_roll_modifier(
    *,
    state: GameState,
    pool: RangedAttackPool,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> int:
    runtime_modifiers = _runtime_modifier_registry(runtime_modifier_registry)
    return (
        pool.hit_roll_modifier
        + _persisting_hit_roll_modifier(
            state=state,
            target_unit_instance_id=pool.target_unit_instance_id,
        )
        + runtime_modifiers.hit_roll_modifier(
            HitRollModifierContext(
                state=state,
                attacking_unit_instance_id=_unit_instance_id_for_model(
                    state=state,
                    model_instance_id=pool.attacker_model_instance_id,
                ),
                attacker_model_instance_id=pool.attacker_model_instance_id,
                target_unit_instance_id=pool.target_unit_instance_id,
                weapon_profile=pool.weapon_profile,
                source_phase=source_phase,
            )
        )
    )


def _plunging_fire_ballistic_skill_improvement(*, pool: RangedAttackPool) -> int:
    if PLUNGING_FIRE_RULE_ID in pool.targeting_rule_ids:
        return 1
    return 0


def _persisting_hit_roll_modifier(*, state: GameState, target_unit_instance_id: str) -> int:
    return unit_effect_hit_roll_modifier(state.persisting_effects_for_unit(target_unit_instance_id))


def _unit_instance_id_for_model(*, state: GameState, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if any(model.model_instance_id == requested_model_id for model in unit.own_models):
                return unit.unit_instance_id
    raise GameLifecycleError("Attack modifier model is not in any unit.")


def _save_options_with_effect_invulnerable(
    *,
    state: GameState,
    target_unit_instance_id: str,
    armor_penetration: int,
    save_options: tuple[SaveOption, ...],
) -> tuple[SaveOption, ...]:
    effect_save = unit_effect_invulnerable_save(
        state.persisting_effects_for_unit(target_unit_instance_id)
    )
    if effect_save is None:
        return save_options
    if any(
        option.save_kind is SaveKind.INVULNERABLE and option.target_number <= effect_save
        for option in save_options
    ):
        return save_options
    return tuple(
        sorted(
            (
                *(
                    option
                    for option in save_options
                    if option.save_kind is not SaveKind.INVULNERABLE
                ),
                SaveOption(
                    save_kind=SaveKind.INVULNERABLE,
                    target_number=effect_save,
                    characteristic_target_number=effect_save,
                    armor_penetration=armor_penetration,
                    source_rule_ids=(GO_TO_GROUND_EFFECT_KIND,),
                ),
            ),
            key=lambda option: option.save_kind.value,
        )
    )


def _cover_result_with_effect_source(
    *,
    ruleset_descriptor: RulesetDescriptor,
    current_cover_result: BenefitOfCoverResult | None,
    source_rule_id: str,
    los_cache_key: str,
) -> BenefitOfCoverResult:
    if current_cover_result is not None and current_cover_result.has_benefit:
        return current_cover_result
    cover_policy = ruleset_descriptor.terrain_visibility_policy.cover_policy
    source = CoverSourceRecord(
        feature_id=source_rule_id,
        feature_kind=TerrainFeatureKind.RUINS,
        policy_kind=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
        reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
    )
    return BenefitOfCoverResult(
        has_benefit=True,
        cover_effect=cover_policy.cover_effect,
        source_feature_ids=(source_rule_id,),
        source_policy_kinds=(LineOfSightPolicy.TRUE_LINE_OF_SIGHT,),
        source_records=(source,),
        los_cache_key=los_cache_key,
        target_unit_visible=False,
        target_unit_fully_visible=False,
        non_stacking=cover_policy.non_stacking,
        ap_zero_save_bonus_excluded_for_save_3_plus_or_better=(
            cover_policy.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
        ),
    )


def _melta_damage_modifier(
    pool: RangedAttackPool,
    *,
    target_keywords: tuple[str, ...],
) -> int:
    if not any(rule_id.startswith(MELTA_RULE_ID) for rule_id in pool.targeting_rule_ids):
        return 0
    return melta_damage_bonus(
        pool.weapon_profile,
        target_within_half_range=True,
        target_keywords=target_keywords,
    )


def _devastating_wounds_resolution_for_attack(
    *,
    pool: RangedAttackPool,
    attack_context: AttackResolutionContextPayload,
    target_keywords: tuple[str, ...],
) -> DevastatingWoundsResolution | None:
    if not bool(attack_context["wound_roll"]["critical"]):
        return None
    return devastating_wounds_resolution(pool.weapon_profile, target_keywords=target_keywords)
