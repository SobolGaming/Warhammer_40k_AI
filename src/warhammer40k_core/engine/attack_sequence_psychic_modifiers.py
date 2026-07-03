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
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_has_beneficial_psychic_modifier",
    "_has_detrimental_psychic_modifier",
    "_psychic_attack_modifier_ignore_options",
    "_psychic_attack_modifier_ignore_request",
    "_psychic_attack_modifier_ignore_selection_for_attack",
    "validate_psychic_attack_modifier_ignore_decision",
)


def _psychic_attack_modifier_ignore_request(
    *,
    state: GameState,
    pool: RangedAttackPool,
    attacker_player_id: str,
    attacking_unit_instance_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> DecisionRequest | None:
    if not is_psychic_weapon_profile(pool.weapon_profile):
        return None
    skill_modifier = _hit_skill_modifier(state=state, pool=pool)
    hit_roll_modifier = _hit_roll_modifier(
        state=state,
        pool=pool,
        source_phase=source_phase,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if skill_modifier == 0 and hit_roll_modifier == 0:
        return None
    options = _psychic_attack_modifier_ignore_options(
        attack_context_id=attack_context_id,
        weapon_profile_id=pool.weapon_profile_id,
        skill_modifier=skill_modifier,
        hit_roll_modifier=hit_roll_modifier,
    )
    if len(options) <= 1:
        return None
    request_id = state.next_decision_request_id()
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
        actor_id=attacker_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE,
                "attack_context_id": attack_context_id,
                "attacking_unit_instance_id": attacking_unit_instance_id,
                "attacker_model_instance_id": pool.attacker_model_instance_id,
                "target_unit_instance_id": pool.target_unit_instance_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "source_phase": source_phase.value,
                "skill_modifier": skill_modifier,
                "hit_roll_modifier": hit_roll_modifier,
            }
        ),
        options=options,
    )


def _psychic_attack_modifier_ignore_options(
    *,
    attack_context_id: str,
    weapon_profile_id: str,
    skill_modifier: int,
    hit_roll_modifier: int,
) -> tuple[DecisionOption, ...]:
    candidates: list[tuple[str, str, int, int]] = [
        (
            KEEP_ALL_MODIFIERS_OPTION_ID,
            "Keep all modifiers",
            skill_modifier,
            hit_roll_modifier,
        )
    ]
    if _has_detrimental_psychic_modifier(
        skill_modifier=skill_modifier,
        hit_roll_modifier=hit_roll_modifier,
    ):
        candidates.append(
            (
                IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID,
                "Ignore detrimental modifiers",
                0 if skill_modifier > 0 else skill_modifier,
                0 if hit_roll_modifier < 0 else hit_roll_modifier,
            )
        )
    if _has_beneficial_psychic_modifier(
        skill_modifier=skill_modifier,
        hit_roll_modifier=hit_roll_modifier,
    ):
        candidates.append(
            (
                IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID,
                "Ignore beneficial modifiers",
                0 if skill_modifier < 0 else skill_modifier,
                0 if hit_roll_modifier > 0 else hit_roll_modifier,
            )
        )
    candidates.append((IGNORE_ALL_MODIFIERS_OPTION_ID, "Ignore all modifiers", 0, 0))
    options: list[DecisionOption] = []
    seen_effective_values: set[tuple[int, int]] = set()
    for option_id, label, effective_skill_modifier, effective_hit_roll_modifier in candidates:
        effective_key = (effective_skill_modifier, effective_hit_roll_modifier)
        if effective_key in seen_effective_values:
            continue
        seen_effective_values.add(effective_key)
        options.append(
            DecisionOption(
                option_id=option_id,
                label=label,
                payload=validate_json_value(
                    {
                        "submission_kind": (SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE),
                        "attack_context_id": attack_context_id,
                        "weapon_profile_id": weapon_profile_id,
                        "option_id": option_id,
                        "skill_modifier": skill_modifier,
                        "hit_roll_modifier": hit_roll_modifier,
                        "effective_skill_modifier": effective_skill_modifier,
                        "effective_hit_roll_modifier": effective_hit_roll_modifier,
                        "ignored_skill_modifier": (skill_modifier - effective_skill_modifier),
                        "ignored_hit_roll_modifier": (
                            hit_roll_modifier - effective_hit_roll_modifier
                        ),
                    }
                ),
            )
        )
    return tuple(options)


def _psychic_attack_modifier_ignore_selection_for_attack(
    *,
    decisions: DecisionController,
    attack_context_id: str,
) -> PsychicAttackModifierIgnoreSelection | None:
    requested_attack_context_id = _validate_identifier("attack_context_id", attack_context_id)
    for record in reversed(decisions.records):
        if record.request.decision_type != SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
            continue
        request_payload = _payload_object(record.request.payload)
        if _payload_string(request_payload, key="attack_context_id") != requested_attack_context_id:
            continue
        payload = _payload_object(record.result.payload)
        return PsychicAttackModifierIgnoreSelection(
            option_id=_payload_string(payload, key="option_id"),
            skill_modifier=_payload_int(payload, key="skill_modifier"),
            hit_roll_modifier=_payload_int(payload, key="hit_roll_modifier"),
            effective_skill_modifier=_payload_int(payload, key="effective_skill_modifier"),
            effective_hit_roll_modifier=_payload_int(
                payload,
                key="effective_hit_roll_modifier",
            ),
        )
    return None


def validate_psychic_attack_modifier_ignore_decision(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    result: DecisionResult,
) -> None:
    record = decisions.record_for_result(result)
    if record.request.decision_type != SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
        raise GameLifecycleError("Psychic modifier ignore decision has wrong request type.")
    request_payload = _payload_object(record.request.payload)
    attack_context_id = _payload_string(request_payload, key="attack_context_id")
    if attack_context_id != attack_sequence.attack_context_id():
        raise GameLifecycleError("Psychic modifier ignore decision attack context drift.")
    payload = _payload_object(result.payload)
    selection = PsychicAttackModifierIgnoreSelection(
        option_id=_payload_string(payload, key="option_id"),
        skill_modifier=_payload_int(payload, key="skill_modifier"),
        hit_roll_modifier=_payload_int(payload, key="hit_roll_modifier"),
        effective_skill_modifier=_payload_int(payload, key="effective_skill_modifier"),
        effective_hit_roll_modifier=_payload_int(payload, key="effective_hit_roll_modifier"),
    )
    if selection.option_id != result.selected_option_id:
        raise GameLifecycleError("Psychic modifier ignore decision option drift.")


def _has_detrimental_psychic_modifier(*, skill_modifier: int, hit_roll_modifier: int) -> bool:
    return skill_modifier > 0 or hit_roll_modifier < 0


def _has_beneficial_psychic_modifier(*, skill_modifier: int, hit_roll_modifier: int) -> bool:
    return skill_modifier < 0 or hit_roll_modifier > 0
