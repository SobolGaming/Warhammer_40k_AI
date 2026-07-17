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
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
# fmt: on

__all__ = (
    "_attack_context_matches_pending_grouped_damage",
    "_cap_roll_modifier",
    "_destruction_reaction_action_host",
    "_destruction_reaction_context_from_payload",
    "_feel_no_pain_source_applies_to_attack",
    "_feel_no_pain_sources_for_attack",
    "_first_allocation_group",
    "_first_allocation_group_order",
    "_lost_wound_context_from_payload",
    "_lost_wound_context_payload",
    "_nested_payload_object",
    "_optional_payload_string",
    "_payload_bool",
    "_payload_identifier_tuple",
    "_payload_int",
    "_payload_object",
    "_payload_positive_int",
    "_payload_positive_number",
    "_payload_string",
    "_payload_string_list",
    "_precision_selected_group_id",
    "_precision_selected_model_ids",
    "_selected_destruction_reaction_source_from_request",
    "_state_destruction_reaction_sources",
    "_state_feel_no_pain_decline_allowed",
    "_state_feel_no_pain_sources",
    "_validate_allocation_group_payload_tuple",
    "_validate_allocation_group_tuple",
    "_validate_attack_context_matches_sequence",
    "_validate_attack_pools",
    "_validate_d6_minimum_success",
    "_validate_d6_target",
    "_validate_d6_value",
    "_validate_deferred_mortal_wounds",
    "_validate_destroyed_transport_disembark_tuple",
    "_validate_destruction_reaction_source_tuple",
    "_validate_fast_dice_pools",
    "_validate_gathered_attack_contributions",
    "_validate_gathered_group_matches_attack_pools",
    "_validate_grouped_request_context_matches_sequence",
    "_validate_identifier",
    "_validate_identifier_tuple",
    "_validate_int",
    "_validate_lost_wound_context_matches_sequence",
    "_validate_non_negative_int",
    "_validate_optional_identifier",
    "_validate_ordered_allocation_group_tuple",
    "_validate_ordered_identifier_tuple",
    "_validate_pool_index_tuple",
    "_validate_pool_indices_within_attack_pools",
    "_validate_positive_int",
    "_validate_roll_modifier_tuple",
    "_validate_save_die_entry_payload",
    "_validate_save_die_entry_tuple",
)


def _validate_gathered_group_matches_attack_pools(
    *,
    attack_pools: tuple[RangedAttackPool, ...],
    used_pool_indices: tuple[int, ...],
    gathered_group: GatheredAttackGroup,
) -> None:
    _validate_pool_indices_within_attack_pools(
        field_name="GatheredAttackGroup pool_indices",
        pool_indices=gathered_group.pool_indices,
        attack_pools=attack_pools,
    )
    used = set(used_pool_indices)
    if any(pool_index in used for pool_index in gathered_group.pool_indices):
        raise GameLifecycleError("GatheredAttackGroup contains already used attack pools.")
    for contribution in gathered_group.contributions:
        pool = attack_pools[contribution.pool_index]
        expected = _gathered_attack_contribution(
            pool_index=contribution.pool_index,
            pool=pool,
        )
        if contribution != expected:
            raise GameLifecycleError("GatheredAttackGroup contribution pool drift.")
        if pool.target_unit_instance_id != gathered_group.target_unit_instance_id:
            raise GameLifecycleError("GatheredAttackGroup target pool drift.")
        if identical_attack_signature(pool) != gathered_group.signature:
            raise GameLifecycleError("GatheredAttackGroup signature drift.")


def _validate_attack_pools(values: object) -> tuple[RangedAttackPool, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("AttackSequence attack_pools must be a tuple.")
    pools: list[RangedAttackPool] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not RangedAttackPool:
            raise GameLifecycleError("AttackSequence attack_pools must contain attack pools.")
        pools.append(value)
    if not pools:
        raise GameLifecycleError("AttackSequence requires at least one attack pool.")
    return tuple(pools)


def _validate_pool_index_tuple(field_name: str, values: object) -> tuple[int, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    indices: list[int] = []
    seen: set[int] = set()
    for value in cast(tuple[object, ...], values):
        index = _validate_non_negative_int(f"{field_name} value", value)
        if index in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(index)
        indices.append(index)
    return tuple(sorted(indices))


def _validate_pool_indices_within_attack_pools(
    *,
    field_name: str,
    pool_indices: tuple[int, ...],
    attack_pools: tuple[RangedAttackPool, ...],
) -> None:
    _validate_pool_index_tuple(field_name, pool_indices)
    _validate_attack_pools(attack_pools)
    for pool_index in pool_indices:
        if pool_index >= len(attack_pools):
            raise GameLifecycleError(f"{field_name} contains an index outside attack_pools.")


def _validate_gathered_attack_contributions(
    values: object,
) -> tuple[GatheredAttackContribution, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("GatheredAttackGroup contributions must be a tuple.")
    contributions: list[GatheredAttackContribution] = []
    seen: set[int] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not GatheredAttackContribution:
            raise GameLifecycleError(
                "GatheredAttackGroup contributions must contain gathered attack contributions."
            )
        if value.pool_index in seen:
            raise GameLifecycleError("GatheredAttackGroup contributions duplicate pool indices.")
        seen.add(value.pool_index)
        contributions.append(value)
    if not contributions:
        raise GameLifecycleError("GatheredAttackGroup contributions must not be empty.")
    return tuple(sorted(contributions, key=lambda contribution: contribution.pool_index))


def _validate_deferred_mortal_wounds(values: object) -> tuple[DeferredMortalWounds, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("AttackSequence deferred_mortal_wounds must be a tuple.")
    deferred: list[DeferredMortalWounds] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeferredMortalWounds:
            raise GameLifecycleError(
                "AttackSequence deferred_mortal_wounds must contain deferred mortal wounds."
            )
        deferred.append(value)
    return tuple(deferred)


def _validate_destroyed_transport_disembark_tuple(
    values: object,
) -> tuple[DestroyedTransportDisembark, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("Destroyed Transport disembarks must be a tuple.")
    disembarks: list[DestroyedTransportDisembark] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestroyedTransportDisembark:
            raise GameLifecycleError(
                "Destroyed Transport disembarks must contain DestroyedTransportDisembark."
            )
        if value.unit_instance_id in seen:
            raise GameLifecycleError("Destroyed Transport disembarks duplicate units.")
        seen.add(value.unit_instance_id)
        disembarks.append(value)
    return tuple(disembarks)


def _validate_destruction_reaction_source_tuple(
    field_name: str,
    values: object,
) -> tuple[DestructionReactionSource, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    sources: list[DestructionReactionSource] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestructionReactionSource:
            raise GameLifecycleError(f"{field_name} must contain DestructionReactionSource.")
        if value.source_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate source IDs.")
        seen.add(value.source_id)
        sources.append(value)
    return tuple(sources)


def _validate_save_die_entry_tuple(values: object) -> tuple[SaveDieEntryPayload, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("PendingGroupedDamage sorted_save_dice must be a tuple.")
    entries: list[SaveDieEntryPayload] = []
    seen_context_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        entry = _validate_save_die_entry_payload(value)
        context_id = entry["attack_context"]["attack_context_id"]
        if context_id in seen_context_ids:
            raise GameLifecycleError("PendingGroupedDamage save dice must not duplicate attacks.")
        seen_context_ids.add(context_id)
        entries.append(entry)
    return tuple(entries)


def _validate_save_die_entry_payload(value: object) -> SaveDieEntryPayload:
    if not isinstance(value, dict):
        raise GameLifecycleError("Save die entry payload must be an object.")
    payload = validate_json_value(cast(JsonValue, value))
    if not isinstance(payload, dict):
        raise GameLifecycleError("Save die entry payload must be an object.")
    roll_state_payload = payload["roll_state"]
    if not isinstance(roll_state_payload, dict):
        raise GameLifecycleError("Save die entry roll_state must be an object.")
    roll_state = DiceRollState.from_payload(cast(DiceRollStatePayload, roll_state_payload))
    die_value = _validate_d6_value("Save die entry value", payload["value"])
    if die_value != roll_state.current_total:
        raise GameLifecycleError("Save die entry value must match roll_state.")
    attack_context_payload = payload["attack_context"]
    if not isinstance(attack_context_payload, dict):
        raise GameLifecycleError("Save die entry attack_context must be an object.")
    attack_context = cast(
        AttackResolutionContextPayload,
        validate_json_value(attack_context_payload),
    )
    _validate_identifier("Save die entry sequence_id", attack_context["sequence_id"])
    _validate_identifier("Save die entry attack_context_id", attack_context["attack_context_id"])
    _validate_non_negative_int("Save die entry pool_index", attack_context["pool_index"])
    _validate_non_negative_int("Save die entry attack_index", attack_context["attack_index"])
    _validate_non_negative_int(
        "Save die entry generated_hit_index",
        attack_context["generated_hit_index"],
    )
    return {
        "roll_state": roll_state.to_payload(),
        "value": die_value,
        "attack_context": attack_context,
    }


def _validate_allocation_group_payload_tuple(
    values: object,
) -> tuple[AllocationGroupPayload, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(
            "PendingGroupedDamage ordered_allocation_group_payloads must be a tuple."
        )
    group_payloads: list[AllocationGroupPayload] = []
    seen_group_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if not isinstance(value, dict):
            raise GameLifecycleError("PendingGroupedDamage allocation group must be an object.")
        payload = cast(AllocationGroupPayload, validate_json_value(cast(JsonValue, value)))
        group = AllocationGroup.from_payload(payload)
        if group.group_id in seen_group_ids:
            raise GameLifecycleError("PendingGroupedDamage allocation groups duplicate IDs.")
        seen_group_ids.add(group.group_id)
        group_payloads.append(group.to_payload())
    if not group_payloads:
        raise GameLifecycleError("PendingGroupedDamage allocation groups must not be empty.")
    return tuple(group_payloads)


def _validate_allocation_group_tuple(
    field_name: str,
    values: object,
) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    groups: list[AllocationGroup] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not AllocationGroup:
            raise GameLifecycleError(f"{field_name} must contain AllocationGroup values.")
        if value.group_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate group IDs.")
        seen.add(value.group_id)
        groups.append(value)
    return tuple(sorted(groups, key=lambda group: group.group_id))


def _validate_ordered_allocation_group_tuple(
    field_name: str,
    values: object,
) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    groups: list[AllocationGroup] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not AllocationGroup:
            raise GameLifecycleError(f"{field_name} must contain AllocationGroup values.")
        if value.group_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate group IDs.")
        seen.add(value.group_id)
        groups.append(value)
    if not groups:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return tuple(groups)


def _first_allocation_group(field_name: str, values: object) -> AllocationGroup:
    groups = _validate_ordered_allocation_group_tuple(field_name, values)
    for group in groups:
        return group
    raise GameLifecycleError(f"{field_name} must not be empty.")


def _first_allocation_group_order(
    field_name: str,
    values: tuple[tuple[AllocationGroup, ...], ...],
) -> tuple[AllocationGroup, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    for order in values:
        return _validate_ordered_allocation_group_tuple(field_name, order)
    raise GameLifecycleError(f"{field_name} must not be empty.")


def _validate_fast_dice_pools(values: object) -> tuple[RangedAttackPool, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("FastDiceGroup pools must be a tuple.")
    pools: list[RangedAttackPool] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not RangedAttackPool:
            raise GameLifecycleError("FastDiceGroup pools must contain attack pools.")
        pools.append(value)
    return tuple(pools)


def _validate_roll_modifier_tuple(field_name: str, values: object) -> tuple[RollModifier, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    modifiers: list[RollModifier] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not RollModifier:
            raise GameLifecycleError(f"{field_name} must contain RollModifier values.")
        if value.modifier_id in seen:
            raise GameLifecycleError(f"{field_name} must not duplicate modifier IDs.")
        seen.add(value.modifier_id)
        modifiers.append(value)
    return tuple(sorted(modifiers, key=lambda modifier: (modifier.priority, modifier.modifier_id)))


def _payload_object(payload: JsonValue) -> dict[str, JsonValue]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Attack sequence payload must be an object.")
    return payload


def _nested_payload_object(payload: dict[str, JsonValue], *, key: str) -> dict[str, JsonValue]:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    return _payload_object(payload[key])


def _precision_selected_group_id(payload: JsonValue) -> str | None:
    value = _payload_object(payload).get("selected_group_id")
    if value is None:
        return None
    return _validate_identifier("Precision selected_group_id", value)


def _precision_selected_model_ids(payload: JsonValue) -> tuple[str, ...]:
    raw_ids = _payload_object(payload).get("selected_model_ids")
    if not isinstance(raw_ids, list):
        raise GameLifecycleError("Precision selected_model_ids must be a list.")
    return _validate_identifier_tuple(
        "Precision selected_model_ids",
        tuple(raw_ids),
    )


def _lost_wound_context_payload(
    *,
    attack_context: AttackResolutionContextPayload,
    allocated_model_id: str,
    damage_kind: DamageKind,
    requested_wounds: int,
    saving_throw: SavingThrow | None,
) -> LostWoundContextPayload:
    return {
        "attack_context": attack_context,
        "allocated_model_id": _validate_identifier("allocated_model_id", allocated_model_id),
        "damage_kind": damage_kind_from_token(damage_kind).value,
        "requested_wounds": _validate_positive_int("requested_wounds", requested_wounds),
        "saving_throw": (
            None if saving_throw is None else validate_json_value(saving_throw.to_payload())
        ),
    }


def _lost_wound_context_from_payload(payload: JsonValue) -> LostWoundContextPayload:
    raw = _payload_object(payload)
    attack_context = raw["attack_context"]
    if not isinstance(attack_context, dict):
        raise GameLifecycleError("Feel No Pain context attack_context must be an object.")
    return {
        "attack_context": cast(AttackResolutionContextPayload, attack_context),
        "allocated_model_id": _payload_string(raw, key="allocated_model_id"),
        "damage_kind": damage_kind_from_token(raw["damage_kind"]).value,
        "requested_wounds": _payload_positive_int(raw, key="requested_wounds"),
        "saving_throw": validate_json_value(raw["saving_throw"]),
    }


def _validate_lost_wound_context_matches_sequence(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> None:
    _validate_attack_context_matches_sequence(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
        context_name="Feel No Pain",
    )


def _validate_grouped_request_context_matches_sequence(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    context_name: str,
) -> None:
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError(f"{context_name} attack context sequence drift.")
    if (
        battle_phase_kind_from_token(attack_context["source_phase"])
        is not attack_sequence.source_phase
    ):
        raise GameLifecycleError(f"{context_name} source phase drift.")
    if attack_context["attack_context_id"] != (
        f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:grouped"
    ):
        raise GameLifecycleError(f"{context_name} grouped attack context ID drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError(f"{context_name} pool index drift.")
    if attack_context["attack_index"] != 0:
        raise GameLifecycleError(f"{context_name} grouped attack index drift.")
    if attack_context["generated_hit_index"] != 0:
        raise GameLifecycleError(f"{context_name} grouped generated hit index drift.")


def _validate_attack_context_matches_sequence(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
    context_name: str,
) -> None:
    if _attack_context_matches_pending_grouped_damage(
        attack_sequence=attack_sequence,
        attack_context=attack_context,
    ):
        return
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError(f"{context_name} attack context sequence drift.")
    if (
        battle_phase_kind_from_token(attack_context["source_phase"])
        is not attack_sequence.source_phase
    ):
        raise GameLifecycleError(f"{context_name} source phase drift.")
    if attack_context["attack_context_id"] != attack_sequence.attack_context_id():
        raise GameLifecycleError(f"{context_name} attack context ID drift.")
    if attack_context["pool_index"] != attack_sequence.pool_index:
        raise GameLifecycleError(f"{context_name} pool index drift.")
    if attack_context["attack_index"] != attack_sequence.attack_index:
        raise GameLifecycleError(f"{context_name} attack index drift.")
    if attack_context["generated_hit_index"] != attack_sequence.generated_hit_index:
        raise GameLifecycleError(f"{context_name} generated hit index drift.")


def _attack_context_matches_pending_grouped_damage(
    *,
    attack_sequence: AttackSequence,
    attack_context: AttackResolutionContextPayload,
) -> bool:
    pending = attack_sequence.pending_grouped_damage
    if pending is None:
        return False
    if attack_context["sequence_id"] != attack_sequence.sequence_id:
        return False
    if (
        battle_phase_kind_from_token(attack_context["source_phase"])
        is not attack_sequence.source_phase
    ):
        return False
    if attack_context["pool_index"] != attack_sequence.pool_index:
        return False
    if pending.next_index >= len(pending.sorted_save_dice):
        raise GameLifecycleError("Pending grouped damage has no current die.")
    current_context = pending.sorted_save_dice[pending.next_index]["attack_context"]
    return (
        attack_context["attack_context_id"] == current_context["attack_context_id"]
        and attack_context["source_phase"] == current_context["source_phase"]
        and attack_context["attack_index"] == current_context["attack_index"]
        and attack_context["generated_hit_index"] == current_context["generated_hit_index"]
    )


def _destruction_reaction_context_from_payload(
    payload: JsonValue,
) -> DestructionReactionContextPayload:
    raw = _payload_object(payload)
    if raw.get("context_kind") != "attack_sequence_model_destroyed":
        raise GameLifecycleError("Destruction reaction context kind is invalid.")
    attack_context = raw["attack_context"]
    if not isinstance(attack_context, dict):
        raise GameLifecycleError("Destruction reaction context attack_context must be an object.")
    provenance_payload = raw["destruction_provenance"]
    if not isinstance(provenance_payload, dict):
        raise GameLifecycleError("Destruction reaction provenance must be an object.")
    provenance = DestructionProvenance.from_payload(
        cast(DestructionProvenancePayload, provenance_payload)
    )
    if provenance.destruction_source_kind is DestructionSourceKind.ATTACK and (
        provenance.attack_context_id != attack_context.get("attack_context_id")
        or provenance.source_weapon_profile is None
        or provenance.source_weapon_profile.profile_id != attack_context.get("weapon_profile_id")
    ):
        raise GameLifecycleError("Destruction reaction attack provenance drift.")
    return {
        "context_kind": "attack_sequence_model_destroyed",
        "attack_context": cast(AttackResolutionContextPayload, attack_context),
        "destruction_provenance": provenance.to_payload(),
        "damage_application": validate_json_value(raw["damage_application"]),
        "model_destroyed_event_id": _payload_string(raw, key="model_destroyed_event_id"),
        "damage_event_id": _payload_string(raw, key="damage_event_id"),
        "target_unit_instance_id": _payload_string(raw, key="target_unit_instance_id"),
        "model_instance_id": _payload_string(raw, key="model_instance_id"),
        "destroyed_model_controller_player_id": _payload_string(
            raw,
            key="destroyed_model_controller_player_id",
        ),
        "source_phase": _payload_string(raw, key="source_phase"),
        "source_step": _payload_string(raw, key="source_step"),
        "removal_record": validate_json_value(raw["removal_record"]),
        "transition_batch": validate_json_value(raw["transition_batch"]),
        "destroyed_model_rules_triggered": _payload_bool(
            raw,
            key="destroyed_model_rules_triggered",
        ),
        "continuation": validate_json_value(raw["continuation"]),
    }


def _state_feel_no_pain_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[FeelNoPainSource, ...]:
    lookup = state.feel_no_pain_sources_for_model
    sources = lookup(model_instance_id=model_instance_id)
    if type(sources) is not tuple:
        raise GameLifecycleError("Feel No Pain source lookup must return a tuple.")
    for source in sources:
        if type(source) is not FeelNoPainSource:
            raise GameLifecycleError("Feel No Pain source lookup returned an invalid source.")
    return sources


def _feel_no_pain_sources_for_attack(
    *,
    state: GameState,
    model_instance_id: str,
    attack_context: AttackResolutionContextPayload,
) -> tuple[FeelNoPainSource, ...]:
    sources = _state_feel_no_pain_sources(state=state, model_instance_id=model_instance_id)
    return tuple(
        source
        for source in sources
        if _feel_no_pain_source_applies_to_attack(
            source=source,
            attack_context=attack_context,
        )
    )


def _feel_no_pain_source_applies_to_attack(
    *,
    source: FeelNoPainSource,
    attack_context: AttackResolutionContextPayload,
) -> bool:
    if type(source) is not FeelNoPainSource:
        raise GameLifecycleError("Feel No Pain source filtering requires a source.")
    if source.attack_condition is None:
        return True
    if source.attack_condition is FeelNoPainAttackCondition.PSYCHIC_ATTACK:
        is_psychic_attack = attack_context["is_psychic_attack"]
        if type(is_psychic_attack) is not bool:
            raise GameLifecycleError("Attack context is_psychic_attack must be a bool.")
        return is_psychic_attack
    raise GameLifecycleError("Unsupported Feel No Pain attack condition.")


def _state_destruction_reaction_sources(
    *,
    state: GameState,
    model_instance_id: str,
) -> tuple[DestructionReactionSource, ...]:
    lookup = state.destruction_reaction_sources_for_model
    sources = lookup(model_instance_id=model_instance_id)
    if type(sources) is not tuple:
        raise GameLifecycleError("Destruction reaction source lookup must return a tuple.")
    for source in sources:
        if type(source) is not DestructionReactionSource:
            raise GameLifecycleError(
                "Destruction reaction source lookup returned an invalid source."
            )
    return sources


def _selected_destruction_reaction_source_from_request(
    *,
    request: DecisionRequest,
    selected_source_id: str | None,
) -> DestructionReactionSource | None:
    request_payload = _payload_object(request.payload)
    source_payloads = request_payload["sources"]
    if not isinstance(source_payloads, list):
        raise GameLifecycleError("Destruction reaction request sources must be a list.")
    sources = tuple(
        DestructionReactionSource.from_payload(
            cast(DestructionReactionSourcePayload, source_payload)
        )
        for source_payload in source_payloads
    )
    if selected_source_id is None:
        return None
    for source in sources:
        if source.source_id == selected_source_id:
            return source
    raise GameLifecycleError("Selected destruction reaction source is not in the request.")


def _destruction_reaction_action_host(source: DestructionReactionSource | None) -> str | None:
    if source is None:
        return None
    if source.reaction_kind is DestructionReactionKind.SHOOT_ON_DEATH:
        return BattlePhase.SHOOTING.value
    if source.reaction_kind is DestructionReactionKind.FIGHT_ON_DEATH:
        return BattlePhase.FIGHT.value
    if source.reaction_kind is DestructionReactionKind.DEADLY_DEMISE:
        return "destruction_reaction"
    raise GameLifecycleError("Unsupported destruction reaction kind.")


def _state_feel_no_pain_decline_allowed(
    *,
    state: GameState,
    model_instance_id: str,
) -> bool:
    lookup = state.feel_no_pain_decline_allowed_for_model
    value = lookup(model_instance_id=model_instance_id)
    if type(value) is not bool:
        raise GameLifecycleError("Feel No Pain decline lookup must return a bool.")
    return value


def _payload_string(payload: dict[str, JsonValue], *, key: str) -> str:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not str:
        raise GameLifecycleError(f"Attack sequence payload {key} must be a string.")
    return value


def _optional_payload_string(payload: dict[str, JsonValue], *, key: str) -> str | None:
    if key not in payload:
        return None
    return _payload_string(payload, key=key)


def _payload_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not int:
        raise GameLifecycleError(f"Attack sequence payload {key} must be an integer.")
    return value


def _payload_string_list(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if not isinstance(value, list):
        raise GameLifecycleError(f"Attack sequence payload {key} must be a list.")
    strings: list[str] = []
    for item in value:
        if type(item) is not str:
            raise GameLifecycleError(f"Attack sequence payload {key} must contain strings.")
        strings.append(item)
    return tuple(strings)


def _payload_bool(payload: dict[str, JsonValue], *, key: str) -> bool:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not bool:
        raise GameLifecycleError(f"Attack sequence payload {key} must be a bool.")
    return value


def _payload_positive_int(payload: dict[str, JsonValue], *, key: str) -> int:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    return _validate_positive_int(key, payload[key])


def _payload_positive_number(payload: dict[str, JsonValue], *, key: str) -> float:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    value = payload[key]
    if type(value) is not int and type(value) is not float:
        raise GameLifecycleError(f"Attack sequence payload {key} must be a number.")
    if value <= 0:
        raise GameLifecycleError(f"Attack sequence payload {key} must be positive.")
    return float(value)


def _payload_identifier_tuple(payload: dict[str, JsonValue], *, key: str) -> tuple[str, ...]:
    if key not in payload:
        raise GameLifecycleError(f"Attack sequence payload missing {key}.")
    raw_values = payload[key]
    if not isinstance(raw_values, list):
        raise GameLifecycleError(f"Attack sequence payload {key} must be a list.")
    return tuple(_validate_identifier(key, value) for value in raw_values)


def _cap_roll_modifier(modifier: int) -> int:
    if type(modifier) is not int:
        raise GameLifecycleError("Roll modifier must be an integer.")
    return max(-1, min(1, modifier))


def _validate_d6_target(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value


def _validate_d6_value(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 1 and 6.")
    return value


def _validate_d6_minimum_success(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 2 or value > 6:
        raise GameLifecycleError(f"{field_name} must be between 2 and 6.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_ordered_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(identifiers)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    return value


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)
