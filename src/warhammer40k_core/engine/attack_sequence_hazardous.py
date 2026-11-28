# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.battlefield_visibility_context import battlefield_visibility_context
from warhammer40k_core.engine.catalog_contextual_status_consumption import (
    CATALOG_IR_FORTIFICATION_COVER_CONSUMER_ID,
    rules_unit_has_fortification_consumer,
)
from warhammer40k_core.engine.targetless_weapons import TargetlessWeapon

from warhammer40k_core.engine.event_log import EventRecord

from typing import TYPE_CHECKING, Literal

from warhammer40k_core.core.ruleset_descriptor import CoverEffect
from warhammer40k_core.engine.attack_sequence_group_selection import (
    allocation_models_reachable_by_pool,
)
from warhammer40k_core.engine.native_gathering_cover_rules import (
    allocation_cover_bindings_by_model,
    allocation_cover_provenance,
    approved_allocation_cover_bindings,
)

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
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_cover_for_allocated_model",
    "_emit_hazardous_mortal_wounds_applied",
    "_emit_hazardous_test_resolved",
    "_hazardous_feel_no_pain_status",
    "_hazardous_mortal_wounds_for_attacker",
    "_hazardous_source_context_from_payload",
    "_hazardous_source_context_payload",
    "_resolve_hazardous_tests",
    "validate_hazardous_mortal_wound_source_context",
    "validate_pending_hazardous_mortal_wound_requests",
)


def _resolve_hazardous_tests(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.hazardous_retention import (
        finish_retained_hazardous_damage,
        resume_retained_hazardous_destructions,
        route_hazardous_damage,
    )

    resumed, status = resume_retained_hazardous_destructions(
        state=state, decisions=decisions, sequence=attack_sequence
    )
    if resumed:
        return status
    hazardous_pools = tuple(
        pool
        for pool in attack_sequence.selected_weapons
        if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.HAZARDOUS)
    )
    if not hazardous_pools:
        return None
    hazardous_weapon_instance_ids, hazardous_weapon_profile_ids = _hazardous_weapon_identity_pairs(
        hazardous_pools
    )
    from warhammer40k_core.engine.retained_shooting import (
        automatically_pass_retained_shooting_hazardous,
    )

    if automatically_pass_retained_shooting_hazardous(
        state=state,
        decisions=decisions,
        sequence=attack_sequence,
        weapon_instance_ids=hazardous_weapon_instance_ids,
        weapon_profile_ids=hazardous_weapon_profile_ids,
    ):
        return None
    roll_state = manager.roll(
        _hazardous_roll_spec(
            attack_sequence=attack_sequence,
            quantity=len(hazardous_weapon_instance_ids),
        )
    )
    failed_roll_indices = failed_hazard_roll_indices(roll_state)
    failed_hazardous_weapon_instance_ids = tuple(
        hazardous_weapon_instance_ids[index] for index in failed_roll_indices
    )
    mortal_wounds_per_failed_roll = _hazardous_mortal_wounds_for_attacker(
        state=state,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
    )
    mortal_wounds = len(failed_roll_indices) * mortal_wounds_per_failed_roll
    if not failed_roll_indices:
        _emit_hazardous_test_resolved(
            decisions=decisions,
            attack_sequence=attack_sequence,
            hazardous_weapon_instance_ids=hazardous_weapon_instance_ids,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            failed_hazardous_weapon_instance_ids=failed_hazardous_weapon_instance_ids,
            roll_state=roll_state,
            successful=True,
            mortal_wounds_per_failed_roll=mortal_wounds_per_failed_roll,
            mortal_wounds=mortal_wounds,
            mortal_wound_application=None,
            pending_mortal_wound_request_id=None,
        )
        return None

    progress = MortalWoundApplicationProgress.start(
        application_id=f"{attack_sequence.sequence_id}:hazardous:mortal-wounds",
        source_rule_id=HAZARDOUS_RULE_ID,
        source_context=_hazardous_source_context_payload(
            attack_sequence=attack_sequence,
            hazardous_weapon_instance_ids=hazardous_weapon_instance_ids,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            failed_hazardous_weapon_instance_ids=failed_hazardous_weapon_instance_ids,
            roll_state=roll_state,
            mortal_wounds_per_failed_roll=mortal_wounds_per_failed_roll,
            mortal_wounds=mortal_wounds,
        ),
        target_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=attack_sequence.attacking_unit_instance_id,
        ),
        mortal_wounds=mortal_wounds,
        spill_over=True,
        destruction_evidence=MortalWoundDestructionEvidence.for_non_attack_state(
            state=state,
            destroying_player_id=attack_sequence.attacker_player_id,
            source_rules_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_model_instance_id=None,
            destruction_source_kind=DestructionSourceKind.HAZARDOUS,
            action_phase=attack_sequence.source_phase,
            source_step="hazardous_test",
        ),
    )
    routed = route_hazardous_damage(
        state=state, decisions=decisions, progress=progress, manager=manager
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        _emit_hazardous_test_resolved(
            decisions=decisions,
            attack_sequence=attack_sequence,
            hazardous_weapon_instance_ids=hazardous_weapon_instance_ids,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            failed_hazardous_weapon_instance_ids=failed_hazardous_weapon_instance_ids,
            roll_state=roll_state,
            successful=False,
            mortal_wounds_per_failed_roll=mortal_wounds_per_failed_roll,
            mortal_wounds=mortal_wounds,
            mortal_wound_application=None,
            pending_mortal_wound_request_id=routed.request.request_id,
        )
        return _hazardous_feel_no_pain_status(
            attack_sequence=attack_sequence,
            request=routed.request,
        )
    if routed.application is None:
        raise GameLifecycleError("Hazardous mortal wounds did not produce application.")
    _emit_hazardous_test_resolved(
        decisions=decisions,
        attack_sequence=attack_sequence,
        hazardous_weapon_instance_ids=hazardous_weapon_instance_ids,
        hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
        failed_hazardous_weapon_instance_ids=failed_hazardous_weapon_instance_ids,
        roll_state=roll_state,
        successful=False,
        mortal_wounds_per_failed_roll=mortal_wounds_per_failed_roll,
        mortal_wounds=mortal_wounds,
        mortal_wound_application=routed.application,
        pending_mortal_wound_request_id=None,
    )
    _emit_hazardous_mortal_wounds_applied(
        decisions=decisions,
        attack_sequence=attack_sequence,
        source_context=_hazardous_source_context_from_payload(progress.source_context),
        application=routed.application,
    )
    return finish_retained_hazardous_damage(
        state=state, decisions=decisions, sequence=attack_sequence, routed=routed
    )


def _emit_hazardous_test_resolved(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    hazardous_weapon_instance_ids: tuple[str, ...],
    hazardous_weapon_profile_ids: tuple[str, ...],
    failed_hazardous_weapon_instance_ids: tuple[str, ...],
    roll_state: DiceRollState,
    successful: bool,
    mortal_wounds_per_failed_roll: int,
    mortal_wounds: int,
    mortal_wound_application: MortalWoundApplication | None,
    pending_mortal_wound_request_id: str | None,
) -> None:
    decisions.event_log.append(
        "hazardous_test_resolved",
        {
            "source_rule_id": HAZARDOUS_RULE_ID,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "source_phase": attack_sequence.source_phase.value,
            "hazardous_weapon_instance_ids": list(hazardous_weapon_instance_ids),
            "hazardous_weapon_profile_ids": list(hazardous_weapon_profile_ids),
            "failed_hazardous_weapon_instance_ids": list(failed_hazardous_weapon_instance_ids),
            "roll_state": roll_state.to_payload(),
            "successful": successful,
            "mortal_wounds_per_failed_roll": mortal_wounds_per_failed_roll,
            "mortal_wounds": mortal_wounds,
            "mortal_wound_application": (
                None if mortal_wound_application is None else mortal_wound_application.to_payload()
            ),
            "pending_mortal_wound_request_id": pending_mortal_wound_request_id,
        },
    )


def _emit_hazardous_mortal_wounds_applied(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    source_context: HazardousMortalWoundSourceContextPayload,
    application: MortalWoundApplication,
) -> None:
    decisions.event_log.append(
        "hazardous_mortal_wounds_applied",
        {
            "source_rule_id": HAZARDOUS_RULE_ID,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "source_phase": source_context["source_phase"],
            "hazardous_weapon_instance_ids": source_context["hazardous_weapon_instance_ids"],
            "hazardous_weapon_profile_ids": source_context["hazardous_weapon_profile_ids"],
            "failed_hazardous_weapon_instance_ids": source_context[
                "failed_hazardous_weapon_instance_ids"
            ],
            "hazardous_roll_state": source_context["hazardous_roll_state"],
            "mortal_wounds_per_failed_roll": source_context["mortal_wounds_per_failed_roll"],
            "mortal_wounds": source_context["mortal_wounds"],
            "mortal_wound_application": application.to_payload(),
        },
    )


def _hazardous_feel_no_pain_status(
    *,
    attack_sequence: AttackSequence,
    request: DecisionRequest,
) -> LifecycleStatus:
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": attack_sequence.source_phase.value,
            "decision_type": request.decision_type,
            "sequence_id": attack_sequence.sequence_id,
            "source_rule_id": HAZARDOUS_RULE_ID,
            "source_kind": HAZARDOUS_SOURCE_KIND,
        },
    )


def _hazardous_source_context_payload(
    *,
    attack_sequence: AttackSequence,
    hazardous_weapon_instance_ids: tuple[str, ...],
    hazardous_weapon_profile_ids: tuple[str, ...],
    failed_hazardous_weapon_instance_ids: tuple[str, ...],
    roll_state: DiceRollState,
    mortal_wounds_per_failed_roll: int,
    mortal_wounds: int,
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": HAZARDOUS_SOURCE_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "source_phase": attack_sequence.source_phase.value,
            "hazardous_weapon_instance_ids": list(hazardous_weapon_instance_ids),
            "hazardous_weapon_profile_ids": list(hazardous_weapon_profile_ids),
            "failed_hazardous_weapon_instance_ids": list(failed_hazardous_weapon_instance_ids),
            "hazardous_roll_state": roll_state.to_payload(),
            "mortal_wounds_per_failed_roll": mortal_wounds_per_failed_roll,
            "mortal_wounds": mortal_wounds,
        }
    )


def _hazardous_source_context_from_payload(
    payload: JsonValue,
) -> HazardousMortalWoundSourceContextPayload:
    raw = _payload_object(payload)
    if raw.get("source_kind") != HAZARDOUS_SOURCE_KIND:
        raise GameLifecycleError("Hazardous mortal wound source context kind is invalid.")
    weapon_instance_ids = raw.get("hazardous_weapon_instance_ids")
    if not isinstance(weapon_instance_ids, list):
        raise GameLifecycleError(
            "Hazardous mortal wound source context weapon instance IDs must be a list."
        )
    weapon_profile_ids = raw.get("hazardous_weapon_profile_ids")
    if not isinstance(weapon_profile_ids, list):
        raise GameLifecycleError(
            "Hazardous mortal wound source context weapon profile IDs must be a list."
        )
    failed_weapon_instance_ids = raw.get("failed_hazardous_weapon_instance_ids")
    if not isinstance(failed_weapon_instance_ids, list):
        raise GameLifecycleError(
            "Hazardous mortal wound source context failed weapon instance IDs must be a list."
        )
    hazardous_roll_state = raw.get("hazardous_roll_state")
    if not isinstance(hazardous_roll_state, dict):
        raise GameLifecycleError(
            "Hazardous mortal wound source context roll state must be an object."
        )
    validated_weapon_instance_ids = _validate_ordered_identifier_tuple(
        "Hazardous mortal wound weapon_instance_ids",
        tuple(weapon_instance_ids),
    )
    validated_weapon_profile_ids = tuple(
        _validate_identifier("Hazardous mortal wound weapon_profile_id", value)
        for value in weapon_profile_ids
    )
    validated_failed_weapon_instance_ids = _validate_ordered_identifier_tuple(
        "Hazardous mortal wound failed weapon_instance_ids",
        tuple(failed_weapon_instance_ids),
    )
    if len(validated_weapon_instance_ids) != len(validated_weapon_profile_ids):
        raise GameLifecycleError(
            "Hazardous mortal wound source context weapon identity lengths drifted."
        )
    if not set(validated_failed_weapon_instance_ids) <= set(validated_weapon_instance_ids):
        raise GameLifecycleError(
            "Hazardous mortal wound source context failed weapon identity drifted."
        )
    try:
        roll_state = DiceRollState.from_payload(cast(DiceRollStatePayload, hazardous_roll_state))
    except (KeyError, TypeError, DiceRollSpecError) as exc:
        raise GameLifecycleError(
            "Hazardous mortal wound source context roll state is invalid."
        ) from exc
    if len(roll_state.current_values) != len(validated_weapon_instance_ids):
        raise GameLifecycleError("Hazardous mortal wound source context roll count drifted.")
    failed_indices = failed_hazard_roll_indices(roll_state)
    expected_failed_weapon_instance_ids = tuple(
        validated_weapon_instance_ids[index] for index in failed_indices
    )
    if validated_failed_weapon_instance_ids != expected_failed_weapon_instance_ids:
        raise GameLifecycleError("Hazardous mortal wound source context failed rolls drifted.")
    mortal_wounds_per_failed_roll = _payload_positive_int(
        raw,
        key="mortal_wounds_per_failed_roll",
    )
    mortal_wounds = _payload_positive_int(raw, key="mortal_wounds")
    if mortal_wounds != len(failed_indices) * mortal_wounds_per_failed_roll:
        raise GameLifecycleError("Hazardous mortal wound source context wound total drifted.")
    return {
        "source_kind": HAZARDOUS_SOURCE_KIND,
        "sequence_id": _payload_string(raw, key="sequence_id"),
        "attacking_unit_instance_id": _payload_string(raw, key="attacking_unit_instance_id"),
        "source_phase": _payload_string(raw, key="source_phase"),
        "hazardous_weapon_instance_ids": list(validated_weapon_instance_ids),
        "hazardous_weapon_profile_ids": list(validated_weapon_profile_ids),
        "failed_hazardous_weapon_instance_ids": list(validated_failed_weapon_instance_ids),
        "hazardous_roll_state": roll_state.to_payload(),
        "mortal_wounds_per_failed_roll": mortal_wounds_per_failed_roll,
        "mortal_wounds": mortal_wounds,
    }


def validate_hazardous_mortal_wound_source_context(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    attack_sequence: AttackSequence,
    source_context_payload: JsonValue,
    mortal_wounds: int,
) -> HazardousMortalWoundSourceContextPayload:
    source_context = _hazardous_source_context_from_payload(source_context_payload)
    if source_context["sequence_id"] != attack_sequence.sequence_id:
        raise GameLifecycleError("Hazardous mortal wound source context sequence drift.")
    if source_context["attacking_unit_instance_id"] != (attack_sequence.attacking_unit_instance_id):
        raise GameLifecycleError("Hazardous mortal wound source context attacker drift.")
    if source_context["source_phase"] != attack_sequence.source_phase.value:
        raise GameLifecycleError("Hazardous mortal wound source context phase drift.")
    hazardous_pools = tuple(
        pool
        for pool in attack_sequence.selected_weapons
        if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.HAZARDOUS)
    )
    expected_weapon_instance_ids, expected_weapon_profile_ids = _hazardous_weapon_identity_pairs(
        hazardous_pools
    )
    if source_context["hazardous_weapon_instance_ids"] != list(expected_weapon_instance_ids):
        raise GameLifecycleError("Hazardous mortal wound weapon instance authority drift.")
    if source_context["hazardous_weapon_profile_ids"] != list(expected_weapon_profile_ids):
        raise GameLifecycleError("Hazardous mortal wound weapon profile authority drift.")
    roll_state = DiceRollState.from_payload(source_context["hazardous_roll_state"])
    expected_roll_spec = _hazardous_roll_spec(
        attack_sequence=attack_sequence,
        quantity=len(expected_weapon_instance_ids),
    )
    if roll_state.original_result.spec != expected_roll_spec:
        raise GameLifecycleError("Hazardous mortal wound roll specification drift.")
    from warhammer40k_core.engine.mortal_wound_application_authority import (
        MORTAL_WOUND_APPLICATION_STARTED_EVENT,
        mortal_wound_application_authority_from_event,
    )

    starts = tuple(
        event
        for event in event_records
        if event.event_type == MORTAL_WOUND_APPLICATION_STARTED_EVENT
        and isinstance(event.payload, dict)
        and event.payload.get("application_id")
        == f"{attack_sequence.sequence_id}:hazardous:mortal-wounds"
    )
    if starts:
        # Registration precedes allocation. Casualties must not change a simultaneous roll's count.
        if len(starts) != 1:
            raise GameLifecycleError("Hazardous mortal wound application start drift.")
        authority = mortal_wound_application_authority_from_event(starts[0])
        if source_context != _hazardous_source_context_from_payload(authority.source_context):
            raise GameLifecycleError("Hazardous mortal wound application source context drift.")
    else:
        # The initial retained-damage binding is validated before registering its application.
        expected_mortal_wounds_per_failed_roll = _hazardous_mortal_wounds_for_attacker(
            state=state,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        )
        if (
            source_context["mortal_wounds_per_failed_roll"]
            != expected_mortal_wounds_per_failed_roll
        ):
            raise GameLifecycleError("Hazardous mortal wound value per failure drift.")
    if source_context["mortal_wounds_per_failed_roll"] not in {1, 3}:
        raise GameLifecycleError("Hazardous mortal wound value per failure is invalid.")
    if source_context["mortal_wounds"] != mortal_wounds:
        raise GameLifecycleError("Hazardous mortal wound source context wound drift.")
    return source_context


def _hazardous_weapon_identity_pairs(
    hazardous_pools: tuple[RangedAttackPool | TargetlessWeapon, ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    weapon_instance_ids: list[str] = []
    weapon_profile_ids: list[str] = []
    profile_id_by_weapon_instance_id: dict[str, str] = {}
    for pool in hazardous_pools:
        existing_profile_id = profile_id_by_weapon_instance_id.get(pool.weapon_instance_id)
        if existing_profile_id is None:
            profile_id_by_weapon_instance_id[pool.weapon_instance_id] = pool.weapon_profile_id
            weapon_instance_ids.append(pool.weapon_instance_id)
            weapon_profile_ids.append(pool.weapon_profile_id)
            continue
        if existing_profile_id != pool.weapon_profile_id:
            raise GameLifecycleError(
                "Hazardous physical weapon instance selected multiple profiles."
            )
    return tuple(weapon_instance_ids), tuple(weapon_profile_ids)


def _hazardous_roll_spec(
    *,
    attack_sequence: AttackSequence,
    quantity: int,
) -> DiceRollSpec:
    return hazard_roll_spec(
        reason=(
            f"Hazardous tests for {attack_sequence.attacking_unit_instance_id} "
            f"after {attack_sequence.source_phase.value}"
        ),
        roll_type="hazardous_test",
        actor_id=attack_sequence.attacking_unit_instance_id,
        quantity=quantity,
    )


def validate_pending_hazardous_mortal_wound_requests(
    *,
    state: GameState,
    event_records: tuple[EventRecord, ...],
    pending_decision_requests: tuple[DecisionRequest, ...],
) -> None:
    for request in pending_decision_requests:
        if not is_mortal_wound_resolution_request(request):
            continue
        progress = mortal_wound_resolution_progress(request)
        source_context = progress.source_context
        if not isinstance(source_context, dict) or (
            source_context.get("source_kind") != HAZARDOUS_SOURCE_KIND
        ):
            continue
        from warhammer40k_core.engine.hazardous_completion import hazardous_sequence_for_progress

        hazardous_sequence_for_progress(state=state, event_records=event_records, progress=progress)


def _hazardous_mortal_wounds_for_attacker(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
) -> int:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=attacking_unit_instance_id,
    )
    return hazard_mortal_wounds_per_failed_roll(rules_unit)


def _cover_for_allocated_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    pool: RangedAttackPool,
    allocated_model_id: str,
) -> BenefitOfCoverResult | None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Allocated-model cover requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield,
        )
        attacker_model = model_by_id(
            state=state,
            model_instance_id=pool.attacker_model_instance_id,
        )
        allocated_model = model_by_id(state=state, model_instance_id=allocated_model_id)
        observer_placement = battlefield.model_placement_by_id(pool.attacker_model_instance_id)
        target_placement = battlefield.model_placement_by_id(allocated_model_id)
        observer_geometry = geometry_model_for_placement(
            model=attacker_model,
            placement=observer_placement,
        )
        target_geometry = geometry_model_for_placement(
            model=allocated_model,
            placement=target_placement,
        )
    except PlacementError as exc:
        raise GameLifecycleError("Allocated-model cover context is invalid.") from exc
    terrain_features = battlefield.terrain_features
    terrain_areas = shooting_terrain_areas_for_state(state)
    terrain_volumes = tuple(
        volume for feature in terrain_features for volume in feature.terrain_volumes()
    )
    attacking_unit_id = attack_pool_attacker_unit_id(state=state, pool=pool)
    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    )
    target_placements = unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=target_rules_unit,
    )
    if target_placements is None:
        raise GameLifecycleError("Allocated-model cover requires a placed target rules unit.")
    target_geometries = geometry_models_for_unit_placements(
        scenario=scenario,
        unit_placements=target_placements,
    )
    dynamic_blockers = shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacking_unit_id,
        target_unit_id=pool.target_unit_instance_id,
    )
    context = battlefield_visibility_context(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=terrain_features,
            terrain_areas=terrain_areas,
        ),
        observer_model=observer_geometry,
        target_models=target_geometries,
        terrain_features=terrain_features,
        terrain_areas=terrain_visibility_areas_from_placements(terrain_areas),
        terrain_volumes=terrain_volumes,
        dynamic_model_blockers=dynamic_blockers,
        observer_keywords=attacker_model.keywords,
        target_model_keywords=model_visibility_keywords_for_rules_unit(
            rules_unit=target_rules_unit,
            models=target_geometries,
        ),
    )
    witness = context.resolve_line_of_sight()
    cover_result = context.benefit_of_cover(witness)
    if cover_result.has_benefit:
        return cover_result
    fortification_cover = _fortification_cover_for_allocated_model(
        state=state,
        ruleset_descriptor=ruleset_descriptor,
        scenario=scenario,
        pool=pool,
        allocated_model_id=allocated_model_id,
        attacking_unit_id=attacking_unit_id,
        target_geometry=target_geometry,
        terrain_features=terrain_features,
        terrain_volumes=terrain_volumes,
        dynamic_blockers=dynamic_blockers,
    )
    return fortification_cover if fortification_cover is not None else cover_result


def approved_pre_hit_cover_sources(
    *,
    state: GameState,
    pool: RangedAttackPool,
    runtime_modifier_registry: RuntimeModifierRegistry,
    allocated_model_ids: tuple[str, ...] | None = None,
    gathering_preview: bool = False,
) -> JsonValue:
    """Qualify the same admitted source across all reachable allocation recipients."""
    from functools import cache

    from warhammer40k_core.core.weapon_profiles import RangeProfileKind
    from warhammer40k_core.engine.weapon_abilities import (
        DevastatingWoundsResolution,
        devastating_wounds_resolution,
        sustained_hits_generated_hits,
    )
    from warhammer40k_core.engine.attack_sequence_geometry_targets import (
        attack_pool_attacker_unit_id,
    )
    from warhammer40k_core.engine.damage_allocation_targets import (
        DamageAllocationTargetState,
        damage_allocation_target_state,
    )

    if (
        pool.weapon_profile.range_profile.kind is not RangeProfileKind.DISTANCE
        or has_weapon_keyword(pool.weapon_profile, WeaponKeyword.IGNORES_COVER)
        or has_weapon_keyword(pool.weapon_profile, WeaponKeyword.TORRENT)
        or state.battlefield_state is None
    ):
        return None
    bindings_by_model = allocation_cover_bindings_by_model(
        tuple(state.army_definitions), approved_allocation_cover_bindings()
    )
    if not bindings_by_model:
        return None
    descriptor = state.ruleset_descriptor_for_runtime_policy()
    if (
        descriptor.terrain_visibility_policy.cover_policy.cover_effect
        is not CoverEffect.ATTACKER_BS_MODIFIER
    ):
        return None
    if (
        damage_allocation_target_state(
            state=state, target_unit_instance_id=pool.target_unit_instance_id
        )
        is not DamageAllocationTargetState.ALLOCATABLE
    ):
        return None
    scenario = battlefield_scenario_for_state(state=state)
    attacking_unit_id = attack_pool_attacker_unit_id(state=state, pool=pool)
    dynamic_blockers = shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacking_unit_id,
        target_unit_id=pool.target_unit_instance_id,
    )
    common_sources = frozenset(
        model.model_id for model in dynamic_blockers if model.model_id in bindings_by_model
    )
    if not common_sources:
        return None

    if allocated_model_ids is None:
        out_of_phase = state.out_of_phase_shooting_state
        shooting = state.shooting_phase_state
        if out_of_phase is not None and out_of_phase.attack_sequence is not None:
            allocated_model_ids = out_of_phase.allocated_model_ids
        elif shooting is not None:
            allocated_model_ids = shooting.allocated_model_ids_this_phase
        else:
            allocated_model_ids = ()
    target = rules_unit_view_by_id(state=state, unit_instance_id=pool.target_unit_instance_id)
    profile = pool.weapon_profile
    post_roll_profiles = runtime_modifier_registry.post_roll_weapon_profile_modifier_bindings
    wound_slots = None
    if not gathering_preview and pool.pending_attack_count_bonus is None and not post_roll_profiles:
        # No-save wounds share this ordinary allocation walk. Mortal conversion
        # and additional mortal wounds are deferred beyond the ordinary slots.
        wound_slots = pool.attacks * sustained_hits_generated_hits(
            profile,
            critical_hit=True,
            target_keywords=target.keywords,
            name_keywords=target.datasheet_name_keywords,
            d3_value=3,
        )

    @cache
    def refine_save_group(group: AllocationGroup) -> tuple[AllocationGroup, ...] | None:
        return _project_allocation_save_subgroups(
            state=state,
            descriptor=descriptor,
            pool=pool,
            attacking_unit_id=attacking_unit_id,
            registry=runtime_modifier_registry,
            group=group,
        )

    candidates = allocation_models_reachable_by_pool(
        state=state,
        pool=pool,
        allocated_model_ids=allocated_model_ids,
        wound_slots=wound_slots,
        maximum_damage=_ordinary_attack_damage_ceiling(pool, runtime_modifier_registry),
        precision_possible=bool(post_roll_profiles)
        or has_weapon_keyword(profile, WeaponKeyword.PRECISION),
        refine_save_group=refine_save_group,
        may_skip_saves=devastating_wounds_resolution(
            profile,
            target_keywords=target.keywords,
            name_keywords=target.datasheet_name_keywords,
        )
        is DevastatingWoundsResolution.NO_SAVES,
    )
    if not candidates:
        return None

    battlefield = scenario.battlefield_state
    terrain_features = battlefield.terrain_features
    terrain_volumes = tuple(
        volume for feature in terrain_features for volume in feature.terrain_volumes()
    )
    for model_id in sorted(candidates):
        target_geometry = geometry_model_for_placement(
            model=model_by_id(state=state, model_instance_id=model_id),
            placement=battlefield.model_placement_by_id(model_id),
        )
        cover = _fortification_cover_for_allocated_model(
            state=state,
            ruleset_descriptor=descriptor,
            scenario=scenario,
            pool=pool,
            allocated_model_id=model_id,
            attacking_unit_id=attacking_unit_id,
            target_geometry=target_geometry,
            terrain_features=terrain_features,
            terrain_volumes=terrain_volumes,
            dynamic_blockers=dynamic_blockers,
            eligible_source_model_ids=common_sources,
        )
        if cover is None:
            return None
        common_sources = common_sources.intersection(cover.source_feature_ids)
        if not common_sources:
            return None
    return allocation_cover_provenance(bindings_by_model, common_sources, candidates)


def _ordinary_attack_damage_ceiling(
    pool: RangedAttackPool, registry: RuntimeModifierRegistry
) -> int | None:
    damage = pool.weapon_profile.damage_profile
    if (
        damage.modifiers
        or has_weapon_keyword(pool.weapon_profile, WeaponKeyword.MELTA)
        or registry.allocated_attack_damage_modifier_bindings
    ):
        return None
    if damage.fixed_damage is not None:
        return damage.fixed_damage
    expression = damage.dice_expression
    if expression is None or registry.damage_roll_modifier_bindings:
        return None
    return max(1, expression.total((expression.sides,) * expression.quantity))


def _project_allocation_save_subgroups(
    *,
    state: GameState,
    descriptor: RulesetDescriptor,
    pool: RangedAttackPool,
    attacking_unit_id: str,
    registry: RuntimeModifierRegistry,
    group: AllocationGroup,
) -> tuple[AllocationGroup, ...] | None:
    from warhammer40k_core.core.random_profile_values import RandomProfileValue
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import (
        allocation_group_by_save_signature,
    )
    from warhammer40k_core.engine.obscuring_model_cover import obscuring_model_cover_sources
    from warhammer40k_core.engine.stealth import rules_unit_stealth_sources
    from warhammer40k_core.engine.catalog_modifier_ignore import (
        ModifierIgnoreKind,
        modifier_ignore_sources_for_gathering,
    )
    from warhammer40k_core.engine.modifier_permission_context import ModifierPermissionAttackContext
    from warhammer40k_core.engine.saves import save_options_for_model
    from warhammer40k_core.engine.source_backed_rerolls import (
        source_backed_reroll_permission_contexts_for_unit,
    )

    profile = pool.weapon_profile
    if (
        registry.save_option_modifier_bindings
        or isinstance(profile.armor_penetration, RandomProfileValue)
        or len(rules_unit_view_by_id(state=state, unit_instance_id=attacking_unit_id).own_models)
        != 1
    ):
        return None

    # Save choices and source-backed rerolls can refine the native group even
    # when its initial profile is homogeneous. Leave those cases conservative.
    target_id = pool.target_unit_instance_id
    if (
        _target_has_effect_cover(state=state, target_unit_instance_id=target_id)
        or _target_has_effect_cover_denial(state=state, target_unit_instance_id=target_id)
        or INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID in pool.targeting_rule_ids
        or obscuring_model_cover_sources(state=state, pool=pool) is not None
        or rules_unit_stealth_sources(
            state=state, target_unit_instance_id=target_id, runtime_modifier_registry=registry
        )
        is not None
    ):
        return None

    target_owner = unit_owner_player_id(state=state, unit_instance_id=target_id)
    if any(
        source_backed_reroll_permission_contexts_for_unit(
            state=state,
            player_id=target_owner,
            unit_instance_id=attacking_unit_id,
            target_unit_instance_id=target_id,
            roll_type=roll,
            timing_window=roll,
            attack_kind="ranged",
        )
        for roll in ("attack_sequence.save.armour", "attack_sequence.save.invulnerable")
    ):
        return None

    def has_ignore_sources(
        unit_id: str, model_id: str, kind: ModifierIgnoreKind, role: Literal["attacker", "target"]
    ) -> bool:
        owner = unit_owner_player_id(state=state, unit_instance_id=unit_id)
        sources = modifier_ignore_sources_for_gathering(
            state=state,
            ability_index=registry.modifier_permission_index(owner),
            unit_instance_id=unit_id,
            kind=kind,
            model_instance_id=model_id,
            weapon_profile_id=pool.weapon_profile_id if role == "attacker" else None,
            attack_context=ModifierPermissionAttackContext(
                attacking_unit_id,
                pool.attacker_model_instance_id,
                target_id,
                role,
                BattlePhase.SHOOTING,
                profile,
                None,
                None,
            ),
        )
        return bool(sources.catalog_permissions or sources.persisted_source_templates)

    if has_ignore_sources(
        attacking_unit_id,
        pool.attacker_model_instance_id,
        ModifierIgnoreKind.ARMOR_PENETRATION_CHARACTERISTIC,
        "attacker",
    ):
        return None
    signatures: dict[str, str] = {}
    for model_id in group.model_ids:
        model = model_by_id(state=state, model_instance_id=model_id)
        if any(
            isinstance(value, RandomProfileValue)
            and value.characteristic in (Characteristic.SAVE, Characteristic.INVULNERABLE_SAVE)
            for value in model.characteristics
        ) or any(
            has_ignore_sources(target_id, model_id, kind, "target")
            for kind in (
                ModifierIgnoreKind.SAVE_CHARACTERISTIC,
                ModifierIgnoreKind.INVULNERABLE_SAVE_CHARACTERISTIC,
                ModifierIgnoreKind.SAVE_ROLL,
            )
        ):
            return None
        options = save_options_for_model(
            model=model,
            armor_penetration=profile.armor_penetration.final,
            cover_result=_cover_for_allocated_model(
                state=state,
                ruleset_descriptor=descriptor,
                pool=pool,
                allocated_model_id=model_id,
            ),
        )
        signatures[model_id] = canonical_json([option.to_payload() for option in options])
    return allocation_group_by_save_signature(group, signatures)


def _fortification_cover_for_allocated_model(
    *,
    state: GameState,
    ruleset_descriptor: RulesetDescriptor,
    scenario: BattlefieldScenario,
    pool: RangedAttackPool,
    allocated_model_id: str,
    attacking_unit_id: str,
    target_geometry: GeometryModel,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    terrain_volumes: tuple[TerrainVolume, ...],
    dynamic_blockers: tuple[GeometryModel, ...],
    eligible_source_model_ids: frozenset[str] | None = None,
) -> BenefitOfCoverResult | None:
    cover_policy = ruleset_descriptor.terrain_visibility_policy.cover_policy
    if not cover_policy.grants_benefit_of_cover or not dynamic_blockers:
        return None
    attacker = rules_unit_view_by_id(state=state, unit_instance_id=attacking_unit_id)
    placements = unit_placements_for_rules_unit_or_none(scenario=scenario, rules_unit=attacker)
    if placements is None:
        raise GameLifecycleError("Fortification cover requires placed attacking models.")
    blocker_records: set[CoverSourceRecord] = set()
    terrain_areas = shooting_terrain_areas_for_state(state)
    blocker_witness: LineOfSightWitness | None = None
    for attacker_placement in (
        model for placement in placements for model in placement.model_placements
    ):
        attacker_model = model_by_id(
            state=state,
            model_instance_id=attacker_placement.model_instance_id,
        )
        if not attacker_model.is_alive:
            continue
        observer_geometry = geometry_model_for_placement(
            model=attacker_model,
            placement=attacker_placement,
        )
        context = battlefield_visibility_context(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            los_cache_key=shooting_visibility_cache_key(
                scenario=scenario,
                terrain_features=terrain_features,
                terrain_areas=terrain_areas,
            ),
            observer_model=observer_geometry,
            target_models=(target_geometry,),
            terrain_features=terrain_features,
            terrain_areas=terrain_visibility_areas_from_placements(terrain_areas),
            terrain_volumes=terrain_volumes,
            dynamic_model_blockers=dynamic_blockers,
            observer_keywords=attacker_model.keywords,
            target_model_keywords=model_visibility_keywords_for_rules_unit(
                rules_unit=rules_unit_view_by_id(
                    state=state,
                    unit_instance_id=pool.target_unit_instance_id,
                ),
                models=(target_geometry,),
            ),
        )
        witness = context.resolve_line_of_sight()
        for blocker in witness.all_blocker_records():
            if (
                blocker.blocker_kind is not VisibilityBlockerKind.MODEL
                or not blocker.blocks_full_visibility
                or (
                    eligible_source_model_ids is not None
                    and blocker.blocker_id not in eligible_source_model_ids
                )
                or not _model_owner_grants_fortification_cover(
                    state=state, model_instance_id=blocker.blocker_id
                )
                or not context.not_fully_visible_because_of(
                    witness, target_model_id=allocated_model_id, sources=(blocker,)
                )
            ):
                continue
            blocker_witness = witness
            blocker_records.add(
                CoverSourceRecord(
                    feature_id=blocker.blocker_id,
                    feature_kind=TerrainFeatureKind.INDUSTRIAL_STRUCTURES,
                    policy_kind=LineOfSightPolicy.TRUE_LINE_OF_SIGHT,
                    reason=CoverSourceReason.NOT_FULLY_VISIBLE_BECAUSE_OF_FEATURE,
                )
            )
    if blocker_witness is None or not blocker_records:
        return None
    sorted_records = tuple(sorted(blocker_records, key=lambda item: item.feature_id))
    return BenefitOfCoverResult(
        has_benefit=True,
        cover_effect=cover_policy.cover_effect,
        source_feature_ids=tuple(record.feature_id for record in sorted_records),
        source_policy_kinds=(LineOfSightPolicy.TRUE_LINE_OF_SIGHT,),
        source_records=sorted_records,
        los_cache_key=blocker_witness.los_cache_key,
        target_unit_visible=blocker_witness.unit_visible,
        target_unit_fully_visible=blocker_witness.unit_fully_visible,
        non_stacking=cover_policy.non_stacking,
        ap_zero_save_bonus_excluded_for_save_3_plus_or_better=(
            cover_policy.ap_zero_save_bonus_excluded_for_save_3_plus_or_better
        ),
    )


def _model_owner_grants_fortification_cover(*, state: GameState, model_instance_id: str) -> bool:
    for army in state.army_definitions:
        for unit in army.units:
            for model in unit.own_models:
                if model.model_instance_id != model_instance_id:
                    continue
                if not model.is_alive:
                    return False
                return rules_unit_has_fortification_consumer(
                    rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
                    CATALOG_IR_FORTIFICATION_COVER_CONSUMER_ID,
                )
    raise GameLifecycleError("Fortification cover blocker model is unknown.")
