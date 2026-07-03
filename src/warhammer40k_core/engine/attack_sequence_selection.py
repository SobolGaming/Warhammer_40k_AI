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
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_fast_dice_pool_key",
    "_first_unresolved_pool_index",
    "_first_unresolved_pool_index_for_target",
    "_first_unresolved_pool_index_for_target_from",
    "_first_unresolved_pool_index_from",
    "_gathered_attack_contribution",
    "_gathered_attack_group_from_indices",
    "_gathered_attack_group_id",
    "_pool_id",
    "_resolve_target_option_id",
    "_synthetic_pool_for_gathered_group",
    "_validate_weapon_profile_signature_shape",
    "_weapon_rule_tokens_for_signature",
    "build_select_attack_weapon_group_request",
    "build_select_resolve_target_unit_request",
    "gathered_attack_groups_for_target",
    "identical_attack_signature",
    "selected_attack_weapon_group_from_result",
    "selected_resolve_target_from_result",
    "unresolved_target_unit_ids",
)


def identical_attack_signature(pool: RangedAttackPool) -> IdenticalAttackSignature:
    if type(pool) is not RangedAttackPool:
        raise GameLifecycleError("identical_attack_signature requires a RangedAttackPool.")
    profile = pool.weapon_profile
    _validate_weapon_profile_signature_shape(profile)
    hit_basis = (
        "auto_hit:torrent"
        if WeaponKeyword.TORRENT in profile.keywords
        else f"hit_target:{_hit_skill(profile)}"
    )
    return IdenticalAttackSignature(
        attacker_model_instance_id=pool.attacker_model_instance_id,
        target_visible_model_ids=pool.target_visible_model_ids,
        target_in_range_model_ids=pool.target_in_range_model_ids,
        hit_basis=hit_basis,
        hit_roll_modifier=pool.hit_roll_modifier,
        wound_roll_modifiers=(),
        strength=canonical_json(profile.strength.to_payload()),
        armor_penetration=canonical_json(profile.armor_penetration.to_payload()),
        damage=canonical_json(profile.damage_profile.to_payload()),
        weapon_rule_tokens=(
            *_weapon_rule_tokens_for_signature(profile),
            *(
                f"selected-weapon-ability:{ability_id}"
                for ability_id in pool.selected_weapon_ability_ids
            ),
        ),
        targeting_rule_ids=tuple(sorted(pool.targeting_rule_ids)),
        shooting_type=pool.shooting_type.value,
        firing_deck_source_unit_instance_id=pool.firing_deck_source_unit_instance_id,
        firing_deck_source_model_instance_id=pool.firing_deck_source_model_instance_id,
    )


def unresolved_target_unit_ids(attack_sequence: AttackSequence) -> tuple[str, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Unresolved target lookup requires an AttackSequence.")
    used = set(attack_sequence.used_pool_indices)
    target_ids = {
        pool.target_unit_instance_id
        for pool_index, pool in enumerate(attack_sequence.attack_pools)
        if pool_index not in used
    }
    return tuple(sorted(target_ids))


def gathered_attack_groups_for_target(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> tuple[GatheredAttackGroup, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Gathered attack grouping requires an AttackSequence.")
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    used = set(attack_sequence.used_pool_indices)
    grouped_indices: dict[IdenticalAttackSignature, list[int]] = {}
    for pool_index, pool in enumerate(attack_sequence.attack_pools):
        if pool_index in used or pool.target_unit_instance_id != target_id:
            continue
        signature = identical_attack_signature(pool)
        grouped_indices.setdefault(signature, []).append(pool_index)
    groups = tuple(
        _gathered_attack_group_from_indices(
            attack_sequence=attack_sequence,
            target_unit_instance_id=target_id,
            signature=signature,
            pool_indices=tuple(indices),
        )
        for signature, indices in grouped_indices.items()
    )
    return tuple(sorted(groups, key=lambda group: group.group_id))


def build_select_resolve_target_unit_request(
    *,
    request_id: str,
    state: GameState,
    attack_sequence: AttackSequence,
) -> DecisionRequest:
    target_ids = unresolved_target_unit_ids(attack_sequence)
    if not target_ids:
        raise GameLifecycleError("Resolve target selection requires unresolved target units.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
        actor_id=attack_sequence.attacker_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": attack_sequence.source_phase.value,
                "sequence_id": attack_sequence.sequence_id,
                "attacker_player_id": attack_sequence.attacker_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "target_unit_instance_ids": list(target_ids),
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=_resolve_target_option_id(target_id),
                label=target_id,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "target_unit_instance_id": target_id,
                    }
                ),
            )
            for target_id in target_ids
        ),
    )


def build_select_attack_weapon_group_request(
    *,
    request_id: str,
    state: GameState,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> DecisionRequest:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    groups = gathered_attack_groups_for_target(
        attack_sequence=attack_sequence,
        target_unit_instance_id=target_id,
    )
    if not groups:
        raise GameLifecycleError("Attack weapon group selection requires unresolved groups.")
    return DecisionRequest(
        request_id=request_id,
        decision_type=SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
        actor_id=attack_sequence.attacker_player_id,
        payload=validate_json_value(
            {
                "submission_kind": SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": attack_sequence.source_phase.value,
                "sequence_id": attack_sequence.sequence_id,
                "attacker_player_id": attack_sequence.attacker_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "target_unit_instance_id": target_id,
                "group_ids": [group.group_id for group in groups],
            }
        ),
        options=tuple(
            DecisionOption(
                option_id=group.group_id,
                label=group.group_id,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
                        "sequence_id": attack_sequence.sequence_id,
                        "target_unit_instance_id": target_id,
                        "gathered_group": group.to_payload(),
                    }
                ),
            )
            for group in groups
        ),
    )


def selected_resolve_target_from_result(result: DecisionResult) -> str:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Resolve target selection requires a DecisionResult.")
    payload = _payload_object(result.payload)
    if payload.get("submission_kind") != SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        raise GameLifecycleError("Resolve target selection payload kind is invalid.")
    return _payload_string(payload, key="target_unit_instance_id")


def selected_attack_weapon_group_from_result(result: DecisionResult) -> GatheredAttackGroup:
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Attack weapon group selection requires a DecisionResult.")
    payload = _payload_object(result.payload)
    if payload.get("submission_kind") != SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        raise GameLifecycleError("Attack weapon group selection payload kind is invalid.")
    gathered_payload = payload["gathered_group"]
    if not isinstance(gathered_payload, dict):
        raise GameLifecycleError("Attack weapon group payload must contain gathered_group.")
    return GatheredAttackGroup.from_payload(cast(GatheredAttackGroupPayload, gathered_payload))


def _fast_dice_pool_key(pool: RangedAttackPool) -> tuple[object, ...]:
    profile = pool.weapon_profile
    return (
        pool.target_unit_instance_id,
        profile.skill.final,
        profile.strength.final,
        profile.armor_penetration.final,
        profile.damage_profile.to_payload(),
        tuple(keyword.value for keyword in profile.keywords),
        tuple(ability.to_payload() for ability in profile.abilities),
        pool.selected_weapon_ability_ids,
        pool.shooting_type.value,
        pool.hit_roll_modifier,
        pool.targeting_rule_ids,
    )


def _pool_id(pool: RangedAttackPool) -> str:
    return (
        f"{pool.attacker_model_instance_id}:{pool.wargear_id}:"
        f"{pool.weapon_profile_id}:{pool.target_unit_instance_id}"
    )


def _resolve_target_option_id(target_unit_instance_id: str) -> str:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return f"resolve-target:{target_id}"


def _gathered_attack_group_from_indices(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
    signature: IdenticalAttackSignature,
    pool_indices: tuple[int, ...],
) -> GatheredAttackGroup:
    _validate_pool_indices_within_attack_pools(
        field_name="Gathered attack pool_indices",
        pool_indices=pool_indices,
        attack_pools=attack_sequence.attack_pools,
    )
    contributions = tuple(
        _gathered_attack_contribution(
            pool_index=pool_index,
            pool=attack_sequence.attack_pools[pool_index],
        )
        for pool_index in pool_indices
    )
    total_attacks = sum(contribution.attacks for contribution in contributions)
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    return GatheredAttackGroup(
        group_id=_gathered_attack_group_id(
            target_unit_instance_id=target_id,
            signature=signature,
            pool_indices=pool_indices,
        ),
        target_unit_instance_id=target_id,
        signature=signature,
        pool_indices=pool_indices,
        total_attacks=total_attacks,
        contributions=contributions,
    )


def _gathered_attack_contribution(
    *,
    pool_index: int,
    pool: RangedAttackPool,
) -> GatheredAttackContribution:
    return GatheredAttackContribution(
        pool_index=pool_index,
        attacker_model_instance_id=pool.attacker_model_instance_id,
        wargear_id=pool.wargear_id,
        weapon_profile_id=pool.weapon_profile_id,
        target_unit_instance_id=pool.target_unit_instance_id,
        attacks=pool.attacks,
        firing_deck_source_unit_instance_id=pool.firing_deck_source_unit_instance_id,
        firing_deck_source_model_instance_id=pool.firing_deck_source_model_instance_id,
    )


def _gathered_attack_group_id(
    *,
    target_unit_instance_id: str,
    signature: IdenticalAttackSignature,
    pool_indices: tuple[int, ...],
) -> str:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    indices = _validate_pool_index_tuple("GatheredAttackGroup pool_indices", pool_indices)
    encoded = canonical_json(
        {
            "target_unit_instance_id": target_id,
            "signature": signature.to_payload(),
            "pool_indices": list(indices),
        }
    ).encode("utf-8")
    return f"attack-group:{sha256(encoded).hexdigest()[:16]}"


def _synthetic_pool_for_gathered_group(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    gathered_group: GatheredAttackGroup,
) -> RangedAttackPool:
    _validate_pool_indices_within_attack_pools(
        field_name="GatheredAttackGroup pool_indices",
        pool_indices=gathered_group.pool_indices,
        attack_pools=attack_pools,
    )
    base_pool = attack_pools[gathered_group.primary_pool_index]
    wargear_id = base_pool.wargear_id
    weapon_profile = base_pool.weapon_profile
    weapon_profile_id = base_pool.weapon_profile_id
    if len(gathered_group.pool_indices) > 1:
        wargear_id = f"gathered-wargear:{gathered_group.group_id}"
        weapon_profile_id = f"gathered-profile:{gathered_group.group_id}"
        weapon_profile = replace(
            base_pool.weapon_profile,
            profile_id=weapon_profile_id,
            name=f"Gathered weapon pool {gathered_group.group_id}",
        )
    return RangedAttackPool(
        attacker_model_instance_id=base_pool.attacker_model_instance_id,
        wargear_id=wargear_id,
        weapon_profile_id=weapon_profile_id,
        weapon_profile=weapon_profile,
        target_unit_instance_id=gathered_group.target_unit_instance_id,
        shooting_type=base_pool.shooting_type,
        attacks=gathered_group.total_attacks,
        target_visible_model_ids=base_pool.target_visible_model_ids,
        target_in_range_model_ids=base_pool.target_in_range_model_ids,
        hit_roll_modifier=base_pool.hit_roll_modifier,
        targeting_rule_ids=base_pool.targeting_rule_ids,
        selected_weapon_ability_ids=base_pool.selected_weapon_ability_ids,
        firing_deck_source_unit_instance_id=base_pool.firing_deck_source_unit_instance_id,
        firing_deck_source_model_instance_id=base_pool.firing_deck_source_model_instance_id,
    )


def _first_unresolved_pool_index(attack_sequence: AttackSequence) -> int:
    return _first_unresolved_pool_index_from(
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
    )


def _first_unresolved_pool_index_from(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    used_pool_indices: tuple[int, ...],
) -> int:
    used = set(used_pool_indices)
    for pool_index in range(len(attack_pools)):
        if pool_index not in used:
            return pool_index
    return len(attack_pools)


def _first_unresolved_pool_index_for_target(
    *,
    attack_sequence: AttackSequence,
    target_unit_instance_id: str,
) -> int:
    return _first_unresolved_pool_index_for_target_from(
        attack_pools=attack_sequence.attack_pools,
        used_pool_indices=attack_sequence.used_pool_indices,
        target_unit_instance_id=target_unit_instance_id,
    )


def _first_unresolved_pool_index_for_target_from(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    used_pool_indices: tuple[int, ...],
    target_unit_instance_id: str,
) -> int:
    target_id = _validate_identifier("target_unit_instance_id", target_unit_instance_id)
    used = set(used_pool_indices)
    for pool_index, pool in enumerate(attack_pools):
        if pool_index not in used and pool.target_unit_instance_id == target_id:
            return pool_index
    raise GameLifecycleError("Target unit has no unresolved attack pools.")


def _weapon_rule_tokens_for_signature(profile: WeaponProfile) -> tuple[str, ...]:
    _validate_weapon_profile_signature_shape(profile)
    tokens: list[str] = [f"keyword:{keyword.value}" for keyword in profile.keywords]
    tokens.extend(
        f"ability:{canonical_json(ability.to_payload())}" for ability in profile.abilities
    )
    return tuple(sorted(tokens))


def _validate_weapon_profile_signature_shape(profile: WeaponProfile) -> None:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Identical attack signature requires a WeaponProfile.")
    ability_kinds = {ability.ability_kind for ability in profile.abilities}
    required_ability_kinds_by_keyword = {
        WeaponKeyword.SUSTAINED_HITS: AbilityKind.SUSTAINED_HITS,
        WeaponKeyword.LETHAL_HITS: AbilityKind.LETHAL_HITS,
        WeaponKeyword.RAPID_FIRE: AbilityKind.RAPID_FIRE,
        WeaponKeyword.MELTA: AbilityKind.MELTA,
        WeaponKeyword.CLEAVE: AbilityKind.CLEAVE,
        WeaponKeyword.HUNTER: AbilityKind.HUNTER,
        WeaponKeyword.DEVASTATING_WOUNDS: AbilityKind.DEVASTATING_WOUNDS,
        WeaponKeyword.HEAVY: AbilityKind.HEAVY,
    }
    for keyword, ability_kind in required_ability_kinds_by_keyword.items():
        if keyword in profile.keywords and ability_kind not in ability_kinds:
            raise GameLifecycleError(
                f"{keyword.value} requires a structured ability descriptor for identical attacks."
            )
    for ability in profile.abilities:
        if ability.ability_kind is AbilityKind.DEVASTATING_WOUNDS:
            devastating_wounds_resolution(profile)
            continue
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD:
            continue
        if ability.ability_kind in required_ability_kinds_by_keyword.values():
            continue
        raise GameLifecycleError("Unsupported weapon ability kind for identical attacks.")
