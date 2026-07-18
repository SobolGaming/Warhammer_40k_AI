# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_imports import *
from warhammer40k_core.engine.dice_result_overrides import (
    DICE_RESULT_OVERRIDE_EVENT_TYPE,
    request_dice_result_override_if_available,
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
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _unit_has_model_within_deadly_demise_range, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "_append_replay_resume_unique_event_once",
    "_canonical_keyword",
    "_command_reroll_opportunity_boundary_state_payload",
    "_command_reroll_opportunity_option",
    "_command_reroll_opportunity_options",
    "_command_reroll_opportunity_state_hash",
    "_command_reroll_opportunity_window",
    "_conditional_wound_full_reroll_applies",
    "_dice_rolled_event_id_for_roll",
    "_latest_reroll_state_for_original_roll",
    "_random_characteristic_roll_spec",
    "_request_command_reroll_for_attack_roll_if_available",
    "_request_source_backed_hit_reroll_if_available",
    "_request_source_backed_save_reroll_if_available",
    "_request_source_backed_wound_reroll_if_available",
    "_roll_hit_and_wound",
    "_roll_or_reuse_state",
    "_source_backed_attack_context_id_matches_active_pool",
    "_source_backed_attack_kind_for_phase",
    "_source_backed_hit_permission_for_attack",
    "_source_backed_reroll_already_answered",
    "_source_backed_save_permission_for_attack",
    "_source_backed_wound_permission_for_attack",
    "_target_unit_within_any_objective_marker_range",
    "_validate_current_source_backed_attack_reroll_context_if_required",
    "apply_source_backed_attack_dice_reroll_decision",
)


def _roll_hit_and_wound(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
    hooks: AttackSequenceHooks,
    stratagem_index: StratagemCatalogIndex | None,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[AttackResolutionContextPayload | None, LifecycleStatus | None]:
    pool = attack_sequence.current_pool()
    attack_context_id = attack_sequence.attack_context_id()
    is_psychic_attack = is_psychic_weapon_profile(pool.weapon_profile)
    if attack_sequence.generated_hit_index == 0:
        psychic_modifier_selection = _psychic_attack_modifier_ignore_selection_for_attack(
            decisions=decisions,
            attack_context_id=attack_context_id,
        )
        if psychic_modifier_selection is None:
            request = _psychic_attack_modifier_ignore_request(
                state=state,
                pool=pool,
                attacker_player_id=attack_sequence.attacker_player_id,
                attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
                attack_context_id=attack_context_id,
                source_phase=attack_sequence.source_phase,
                runtime_modifier_registry=runtime_modifier_registry,
            )
            if request is not None:
                decisions.request_decision(request)
                return (
                    None,
                    LifecycleStatus.waiting_for_decision(
                        stage=GameLifecycleStage.BATTLE,
                        decision_request=request,
                        payload={
                            "phase": attack_sequence.source_phase.value,
                            "phase_body_status": "psychic_attack_modifier_ignore_pending",
                            "attack_context_id": attack_context_id,
                            "weapon_profile_id": pool.weapon_profile_id,
                        },
                    ),
                )
        hit_roll = _roll_hit(
            state=state,
            manager=manager,
            pool=pool,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
            source_phase=attack_sequence.source_phase,
            runtime_modifier_registry=runtime_modifier_registry,
            psychic_modifier_selection=psychic_modifier_selection,
        )
        status = _request_source_backed_hit_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=hit_roll.roll_state,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            attack_context_id=attack_context_id,
            source_phase=attack_sequence.source_phase,
            weapon_profile_id=pool.weapon_profile_id,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        if status is not None:
            return None, status
        status = _request_command_reroll_for_attack_roll_if_available(
            state=state,
            decisions=decisions,
            roll_state=hit_roll.roll_state,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
            phase_body_status="attack_hit_command_reroll_pending",
        )
        if status is not None:
            return None, status
        target_keywords = rules_unit_view_by_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ).keywords
        override_request = request_dice_result_override_if_available(
            state=state,
            decisions=decisions,
            roll_state=hit_roll.roll_state,
            roll_type="hit",
            roll_successful=hit_roll.successful,
            roll_critical=hit_roll.critical,
            source_phase=attack_sequence.source_phase.value,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context_id,
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            weapon_profile_id=pool.weapon_profile_id,
            weapon_profile=pool.weapon_profile,
            target_keywords=target_keywords,
        )
        if override_request is not None:
            if hit_roll.roll_state is None:
                raise GameLifecycleError("Dice-result override request requires a Hit roll state.")
            decisions.request_decision(override_request)
            return (
                None,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=override_request,
                    payload={
                        "phase": attack_sequence.source_phase.value,
                        "phase_body_status": "attack_hit_dice_result_override_pending",
                        "attack_context_id": attack_context_id,
                        "roll_id": hit_roll.roll_state.original_result.roll_id,
                    },
                ),
            )
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.HIT,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=attack_context_id,
                pool_index=attack_sequence.pool_index,
                attack_index=attack_sequence.attack_index,
                payload=validate_json_value(
                    {
                        **hit_roll.to_payload(),
                        "weapon_profile_id": pool.weapon_profile_id,
                        "is_psychic_attack": is_psychic_attack,
                        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                    }
                ),
            ),
        )
        if hit_roll.critical:
            _emit_event(
                decisions=decisions,
                hooks=hooks,
                event=AttackSequenceEvent(
                    step=AttackSequenceStep.CRITICAL_HIT,
                    sequence_id=attack_sequence.sequence_id,
                    attack_context_id=attack_context_id,
                    pool_index=attack_sequence.pool_index,
                    attack_index=attack_sequence.attack_index,
                    payload=validate_json_value(
                        {
                            **hit_roll.to_payload(),
                            "weapon_profile_id": pool.weapon_profile_id,
                            "is_psychic_attack": is_psychic_attack,
                            "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                        }
                    ),
                ),
            )
    else:
        if attack_sequence.current_hit_roll is None:
            raise GameLifecycleError("Generated hit resolution requires a hit roll.")
        hit_roll = attack_sequence.current_hit_roll
    if not hit_roll.successful:
        return None, None

    target_rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=pool.target_unit_instance_id,
    )
    toughness = _target_unit_toughness(
        state=state,
        target_unit_instance_id=pool.target_unit_instance_id,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if (
        attack_sequence.generated_hit_index == 0
        and hit_roll.critical
        and lethal_hits_applies(pool.weapon_profile, target_keywords=target_rules_unit.keywords)
    ):
        wound_roll = WoundRoll.auto_wound(
            strength=pool.weapon_profile.strength.final,
            toughness=toughness,
            target_number=wound_roll_target_number(
                strength=pool.weapon_profile.strength.final,
                toughness=toughness,
            ),
        )
    else:
        wound_roll = _roll_wound(
            manager=manager,
            pool=pool,
            toughness=toughness,
            target_keywords=target_rules_unit.keywords,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
            wound_modifier=_wound_roll_modifier(
                state=state,
                pool=pool,
                source_phase=attack_sequence.source_phase,
                toughness=toughness,
                runtime_modifier_registry=runtime_modifier_registry,
            ),
        )
        status = _request_source_backed_wound_reroll_if_available(
            state=state,
            decisions=decisions,
            roll_state=wound_roll.roll_state,
            pool=pool,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            attacker_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=attack_sequence.attacking_unit_instance_id,
            ).keywords,
            attack_context_id=attack_context_id,
            source_phase=attack_sequence.source_phase,
        )
        if status is not None:
            return None, status
        status = _request_command_reroll_for_attack_roll_if_available(
            state=state,
            decisions=decisions,
            roll_state=wound_roll.roll_state,
            affected_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            source_phase=attack_sequence.source_phase,
            stratagem_index=stratagem_index,
            phase_body_status="attack_wound_command_reroll_pending",
        )
        if status is not None:
            return None, status
        wound_roll = _reroll_wound_for_twin_linked_if_needed(
            manager=manager,
            decisions=decisions,
            pool=pool,
            initial_wound_roll=wound_roll,
            toughness=toughness,
            target_keywords=target_rules_unit.keywords,
            attacker_player_id=attack_sequence.attacker_player_id,
            attack_context_id=attack_context_id,
        )
        override_request = request_dice_result_override_if_available(
            state=state,
            decisions=decisions,
            roll_state=wound_roll.roll_state,
            roll_type="wound",
            roll_successful=wound_roll.successful,
            roll_critical=wound_roll.critical,
            source_phase=attack_sequence.source_phase.value,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context_id,
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
            attacker_model_instance_id=pool.attacker_model_instance_id,
            target_unit_instance_id=pool.target_unit_instance_id,
            weapon_profile_id=pool.weapon_profile_id,
            weapon_profile=pool.weapon_profile,
            target_keywords=target_rules_unit.keywords,
        )
        if override_request is not None:
            if wound_roll.roll_state is None:
                raise GameLifecycleError(
                    "Dice-result override request requires a Wound roll state."
                )
            decisions.request_decision(override_request)
            return (
                None,
                LifecycleStatus.waiting_for_decision(
                    stage=GameLifecycleStage.BATTLE,
                    decision_request=override_request,
                    payload={
                        "phase": attack_sequence.source_phase.value,
                        "phase_body_status": "attack_wound_dice_result_override_pending",
                        "attack_context_id": attack_context_id,
                        "roll_id": wound_roll.roll_state.original_result.roll_id,
                    },
                ),
            )
    _emit_event(
        decisions=decisions,
        hooks=hooks,
        event=AttackSequenceEvent(
            step=AttackSequenceStep.WOUND,
            sequence_id=attack_sequence.sequence_id,
            attack_context_id=attack_context_id,
            pool_index=attack_sequence.pool_index,
            attack_index=attack_sequence.attack_index,
            payload=validate_json_value(
                {
                    **wound_roll.to_payload(),
                    "weapon_profile_id": pool.weapon_profile_id,
                    "is_psychic_attack": is_psychic_attack,
                    "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                }
            ),
        ),
    )
    if wound_roll.critical:
        _emit_event(
            decisions=decisions,
            hooks=hooks,
            event=AttackSequenceEvent(
                step=AttackSequenceStep.CRITICAL_WOUND,
                sequence_id=attack_sequence.sequence_id,
                attack_context_id=attack_context_id,
                pool_index=attack_sequence.pool_index,
                attack_index=attack_sequence.attack_index,
                payload=validate_json_value(
                    {
                        **wound_roll.to_payload(),
                        "weapon_profile_id": pool.weapon_profile_id,
                        "is_psychic_attack": is_psychic_attack,
                        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
                    }
                ),
            ),
        )
    return {
        "sequence_id": attack_sequence.sequence_id,
        "source_phase": attack_sequence.source_phase.value,
        "attack_context_id": attack_context_id,
        "pool_index": attack_sequence.pool_index,
        "attack_index": attack_sequence.attack_index,
        "generated_hit_index": attack_sequence.generated_hit_index,
        "attacker_player_id": attack_sequence.attacker_player_id,
        "defender_player_id": unit_owner_player_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ),
        "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
        "attacker_model_instance_id": pool.attacker_model_instance_id,
        "target_unit_instance_id": pool.target_unit_instance_id,
        "weapon_profile_id": pool.weapon_profile_id,
        "is_psychic_attack": is_psychic_attack,
        "selected_weapon_ability_ids": list(pool.selected_weapon_ability_ids),
        "damage_profile": pool.weapon_profile.damage_profile.to_payload(),
        "hit_roll": hit_roll.to_payload(),
        "wound_roll": wound_roll.to_payload(),
        "allocation": None,
        "save_options": [],
    }, None


def _roll_or_reuse_state(manager: DiceRollManager, spec: DiceRollSpec) -> DiceRollState:
    if type(manager) is not DiceRollManager:
        raise GameLifecycleError("Roll reuse requires a DiceRollManager.")
    if type(spec) is not DiceRollSpec:
        raise GameLifecycleError("Roll reuse requires a DiceRollSpec.")
    spec_payload = spec.to_payload()
    original_state: DiceRollState | None = None
    for event in manager.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("dice_rolled event payload must be an object.")
        result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if result.spec.to_payload() == spec_payload:
            original_state = DiceRollState.from_result(result)
            break
    if original_state is None:
        return manager.roll(spec)
    return _latest_reroll_state_for_original_roll(
        manager=manager,
        original_state=original_state,
    )


def _latest_reroll_state_for_original_roll(
    *,
    manager: DiceRollManager,
    original_state: DiceRollState,
) -> DiceRollState:
    current = original_state
    roll_id = original_state.original_result.roll_id
    for event in manager.event_log.records:
        if event.event_type not in {
            "dice_reroll_resolved",
            "command_reroll_resolved",
            DICE_RESULT_OVERRIDE_EVENT_TYPE,
        }:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Reroll event payload must be an object.")
        if event.event_type in {"command_reroll_resolved", DICE_RESULT_OVERRIDE_EVENT_TYPE}:
            updated_payload = event.payload.get("updated_roll_state")
            if not isinstance(updated_payload, dict):
                raise GameLifecycleError("Command Re-roll event missing updated roll state.")
            updated_state = DiceRollState.from_payload(cast(DiceRollStatePayload, updated_payload))
        else:
            updated_state = DiceRollState.from_payload(cast(DiceRollStatePayload, event.payload))
        if updated_state.original_result.roll_id == roll_id:
            current = updated_state
    return current


def _request_command_reroll_for_attack_roll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    affected_unit_instance_id: str,
    source_phase: BattlePhase,
    stratagem_index: StratagemCatalogIndex | None,
    phase_body_status: str,
) -> LifecycleStatus | None:
    if roll_state is not None and roll_state.rerolls:
        return None
    if roll_state is None or stratagem_index is None:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    from warhammer40k_core.engine.stratagems import (
        COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY,
        COMMAND_REROLL_DICE_CONTEXT_KEY,
        CORE_COMMAND_REROLL_HANDLER_ID,
        DECLINE_STRATAGEM_WINDOW_OPTION_ID,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_for_handler_from_index,
        stratagem_window_declined_for_context,
    )

    phase = battle_phase_kind_from_token(source_phase)
    window_id = (
        f"command-reroll-{phase.value}-round-{state.battle_round:02d}-"
        f"{roll_state.original_result.roll_id}"
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=actor_id,
        trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
        timing_window_id=window_id,
        trigger_payload=validate_json_value(
            {
                COMMAND_REROLL_DICE_CONTEXT_KEY: roll_state.to_payload(),
                COMMAND_REROLL_AFFECTED_UNIT_CONTEXT_KEY: affected_unit_instance_id,
                "source_phase": phase.value,
                "roll_id": roll_state.original_result.roll_id,
                "roll_type": roll_state.original_result.spec.roll_type,
            }
        ),
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_for_handler_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        handler_id=CORE_COMMAND_REROLL_HANDLER_ID,
    )
    if not options:
        return None
    request_id = state.next_decision_request_id()
    opportunity_window = _command_reroll_opportunity_window(
        state=state,
        decisions=decisions,
        window_id=window_id,
        roll_state=roll_state,
        actor_id=actor_id,
        affected_unit_instance_id=affected_unit_instance_id,
        phase=phase,
        use_option_ids=tuple(option.option_id for option in options),
        decline_option_id=DECLINE_STRATAGEM_WINDOW_OPTION_ID,
    )
    enriched_options = _command_reroll_opportunity_options(
        window=opportunity_window,
        player_id=actor_id,
        use_options=options,
        decline_option=stratagem_decline_option(),
    )
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=enriched_options,
        request_id=request_id,
        payload_extra={
            "submission_family": OPPORTUNITY_REQUEST_FAMILY,
            "opportunity_window": cast(JsonValue, opportunity_window.to_payload()),
            "opportunity_window_id": opportunity_window.window_id,
            "legal_action_fingerprint": opportunity_window.legal_action_fingerprint(actor_id),
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": phase.value,
            "phase_body_status": phase_body_status,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": affected_unit_instance_id,
            "pending_request_id": request.request_id,
        },
    )


def _request_source_backed_hit_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None = None,
    target_unit_instance_id: str | None = None,
    attack_context_id: str,
    source_phase: BattlePhase,
    weapon_profile_id: str,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> LifecycleStatus | None:
    if roll_state is None:
        return None
    if source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return None
    if roll_state.rerolls:
        return None
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=actor_id,
        unit_instance_id=attacking_unit_instance_id,
        model_instance_id=attacker_model_instance_id,
        roll_type=roll_state.original_result.spec.roll_type,
        timing_window="attack_sequence.hit",
        attack_kind=_source_backed_attack_kind_for_phase(source_phase),
        target_unit_instance_id=target_unit_instance_id,
    )
    registry = (
        RuntimeModifierRegistry.empty()
        if runtime_modifier_registry is None
        else runtime_modifier_registry
    )
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Attack hit reroll requires RuntimeModifierRegistry.")
    catalog_permission_context = None
    if target_unit_instance_id is not None:
        catalog_permission_context = registry.attack_reroll_permission_context(
            AttackRerollPermissionContext(
                state=state,
                player_id=actor_id,
                attacking_unit_instance_id=attacking_unit_instance_id,
                attacker_model_instance_id=attacker_model_instance_id,
                target_unit_instance_id=target_unit_instance_id,
                source_phase=source_phase,
                roll_type=roll_state.original_result.spec.roll_type,
                timing_window="attack_sequence.hit",
            )
        )
    if permission_context is not None and catalog_permission_context is not None:
        raise GameLifecycleError("Multiple source-backed hit reroll permissions are available.")
    if catalog_permission_context is not None:
        permission_context = catalog_permission_context
    if permission_context is None:
        return None
    permission = _source_backed_hit_permission_for_attack(
        permission_context=permission_context,
        roll_state=roll_state,
        state=state,
        target_unit_instance_id=target_unit_instance_id,
    )
    if permission is None:
        return None
    if _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        source_id=permission.source_id,
    ):
        return None
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=actor_id,
        permission=permission,
        extra_payload={
            "source_rule_id": permission.source_id,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "unit_instance_id": attacking_unit_instance_id,
                "attack_context_id": attack_context_id,
                "weapon_profile_id": weapon_profile_id,
                "hit_roll_state": validate_json_value(roll_state.to_payload()),
                "source_payload": validate_json_value(permission_context.source_payload),
            },
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": source_phase.value,
            "phase_body_status": "attack_hit_source_backed_reroll_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": attacking_unit_instance_id,
            "attack_context_id": attack_context_id,
            "pending_request_id": request.request_id,
        },
    )


def _source_backed_hit_permission_for_attack(
    *,
    permission_context: SourceBackedRerollPermissionContext,
    roll_state: DiceRollState,
    state: GameState,
    target_unit_instance_id: str | None,
) -> RerollPermission | None:
    source_payload = permission_context.source_payload
    conditional = source_payload.get("conditional_hit_reroll")
    if conditional is None:
        return permission_context.permission
    if not isinstance(conditional, dict):
        raise GameLifecycleError("Conditional hit reroll payload must be an object.")
    if target_unit_instance_id is not None and _conditional_wound_full_reroll_applies(
        state=state,
        conditional=conditional,
        target_unit_instance_id=target_unit_instance_id,
        attacker_keywords=(),
    ):
        return permission_context.permission
    reroll_values = conditional.get("reroll_unmodified_values")
    if not isinstance(reroll_values, list) or not all(
        type(value) is int for value in reroll_values
    ):
        raise GameLifecycleError("Conditional hit reroll requires integer reroll values.")
    selections = tuple(
        (index,)
        for index, value in enumerate(roll_state.current_values)
        if value in cast(list[int], reroll_values)
    )
    if not selections:
        return None
    return replace(
        permission_context.permission,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=selections,
    )


def _request_source_backed_save_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    attack_context_id: str,
    source_phase: BattlePhase,
    weapon_profile_id: str,
    allocated_model_id: str,
    save_kind: SaveKind,
) -> LifecycleStatus | None:
    if roll_state is None:
        return None
    if source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return None
    if roll_state.rerolls:
        return None
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    if type(save_kind) is not SaveKind:
        raise GameLifecycleError("Source-backed save reroll requires a SaveKind.")
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=actor_id,
        unit_instance_id=attacking_unit_instance_id,
        roll_type=roll_state.original_result.spec.roll_type,
        timing_window=roll_state.original_result.spec.roll_type,
        attack_kind=_source_backed_attack_kind_for_phase(source_phase),
        target_unit_instance_id=target_unit_instance_id,
    )
    if permission_context is None:
        return None
    permission = _source_backed_save_permission_for_attack(
        permission_context=permission_context,
        roll_state=roll_state,
    )
    if permission is None:
        return None
    if _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        source_id=permission.source_id,
    ):
        return None
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=actor_id,
        permission=permission,
        extra_payload={
            "source_rule_id": permission.source_id,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "unit_instance_id": attacking_unit_instance_id,
                "target_unit_instance_id": target_unit_instance_id,
                "attack_context_id": attack_context_id,
                "weapon_profile_id": weapon_profile_id,
                "allocated_model_id": allocated_model_id,
                "save_kind": save_kind.value,
                "save_roll_state": validate_json_value(roll_state.to_payload()),
                "source_payload": validate_json_value(permission_context.source_payload),
            },
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": source_phase.value,
            "phase_body_status": "attack_save_source_backed_reroll_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": target_unit_instance_id,
            "attack_context_id": attack_context_id,
            "allocated_model_id": allocated_model_id,
            "save_kind": save_kind.value,
            "pending_request_id": request.request_id,
        },
    )


def _source_backed_save_permission_for_attack(
    *,
    permission_context: SourceBackedRerollPermissionContext,
    roll_state: DiceRollState,
) -> RerollPermission | None:
    source_payload = permission_context.source_payload
    conditional = source_payload.get("conditional_save_reroll")
    if conditional is None:
        return permission_context.permission
    if not isinstance(conditional, dict):
        raise GameLifecycleError("Conditional save reroll payload must be an object.")
    reroll_values = conditional.get("reroll_unmodified_values")
    if not isinstance(reroll_values, list) or not all(
        type(value) is int for value in reroll_values
    ):
        raise GameLifecycleError("Conditional save reroll requires integer reroll values.")
    if roll_state.current_total not in cast(list[int], reroll_values):
        return None
    return replace(
        permission_context.permission,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )


def apply_source_backed_attack_dice_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    expected_phase: BattlePhase,
    phase_label: str,
) -> None:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError(f"{phase_label} dice reroll requires an active attack sequence.")
    if attack_sequence.source_phase is not expected_phase:
        raise GameLifecycleError(f"{phase_label} dice reroll context must be for the phase.")
    record = decisions.record_for_result(result)
    request_payload = _payload_object(record.request.payload)
    roll_type = _payload_string(request_payload, key="roll_type")
    roll_state_key = SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS.get(roll_type)
    if roll_state_key is None:
        raise GameLifecycleError(
            f"{phase_label} dice reroll must target an attack source-backed roll."
        )
    attack_context = _nested_payload_object(request_payload, key="attack_context")
    initial_roll_payload = _nested_payload_object(attack_context, key=roll_state_key)
    initial_roll_state = DiceRollState.from_payload(
        cast(DiceRollStatePayload, initial_roll_payload)
    )
    expected_actor_id = initial_roll_state.original_result.spec.actor_id
    if expected_actor_id is None:
        raise GameLifecycleError(f"{phase_label} dice reroll initial roll actor is missing.")
    if result.actor_id != expected_actor_id:
        raise GameLifecycleError(f"{phase_label} dice reroll actor must match roll actor.")
    source_rule_id = _payload_string(request_payload, key="source_rule_id")
    permission_payload = _nested_payload_object(request_payload, key="permission")
    if _payload_string(permission_payload, key="source_id") != source_rule_id:
        raise GameLifecycleError(f"{phase_label} dice reroll source context drift.")
    if _payload_string(permission_payload, key="timing_window") != roll_type:
        raise GameLifecycleError(f"{phase_label} dice reroll timing window drift.")
    if _payload_string(permission_payload, key="eligible_roll_type") != roll_type:
        raise GameLifecycleError(f"{phase_label} dice reroll permission roll type drift.")
    if _payload_string(permission_payload, key="owning_player_id") != expected_actor_id:
        raise GameLifecycleError(f"{phase_label} dice reroll permission player drift.")
    if _payload_string(attack_context, key="phase") != expected_phase.value:
        raise GameLifecycleError(f"{phase_label} dice reroll context must be for the phase.")
    if (
        _payload_string(attack_context, key="unit_instance_id")
        != attack_sequence.attacking_unit_instance_id
    ):
        raise GameLifecycleError(
            f"{phase_label} dice reroll unit must match active attack sequence."
        )
    attack_context_id = _payload_string(attack_context, key="attack_context_id")
    if not _source_backed_attack_context_id_matches_active_pool(
        attack_sequence=attack_sequence,
        attack_context_id=attack_context_id,
    ):
        raise GameLifecycleError(f"{phase_label} dice reroll attack context drift.")
    current_pool = attack_sequence.current_pool()
    if _payload_string(attack_context, key="weapon_profile_id") != current_pool.weapon_profile_id:
        raise GameLifecycleError(f"{phase_label} dice reroll weapon profile drift.")
    _validate_current_source_backed_attack_reroll_context_if_required(
        state=state,
        attack_sequence=attack_sequence,
        current_pool=current_pool,
        roll_type=roll_type,
        attack_kind=_source_backed_attack_kind_for_phase(expected_phase),
        source_rule_id=source_rule_id,
        attack_context=attack_context,
        owning_player_id=expected_actor_id,
        phase_label=phase_label,
    )
    if initial_roll_state.original_result.spec.roll_type != roll_type:
        raise GameLifecycleError(f"{phase_label} dice reroll initial roll type drift.")
    if initial_roll_state.original_result.spec.actor_id != expected_actor_id:
        raise GameLifecycleError(f"{phase_label} dice reroll initial roll actor drift.")
    DiceRollManager(
        state.game_id,
        event_log=decisions.event_log,
    ).resolve_reroll(
        initial_roll_state,
        request=record.request,
        result=result,
        record_decision=False,
    )


def _validate_current_source_backed_attack_reroll_context_if_required(
    *,
    state: GameState,
    attack_sequence: AttackSequence,
    current_pool: RangedAttackPool,
    roll_type: str,
    attack_kind: str,
    source_rule_id: str,
    attack_context: dict[str, JsonValue],
    owning_player_id: str,
    phase_label: str,
) -> None:
    source_payload_value = attack_context.get("source_payload")
    if source_payload_value is None:
        return
    source_payload = _payload_object(source_payload_value)
    model_instance_id = None
    if not roll_type.startswith("attack_sequence.save."):
        model_instance_id = current_pool.attacker_model_instance_id
    current_permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=owning_player_id,
        unit_instance_id=attack_sequence.attacking_unit_instance_id,
        model_instance_id=model_instance_id,
        roll_type=roll_type,
        timing_window=roll_type,
        attack_kind=attack_kind,
        target_unit_instance_id=current_pool.target_unit_instance_id,
    )
    if current_permission_context is None:
        raise GameLifecycleError(f"{phase_label} dice reroll source context drift.")
    if current_permission_context.permission.source_id != source_rule_id:
        raise GameLifecycleError(f"{phase_label} dice reroll source context drift.")
    if (
        source_payload.get("effect_kind") == "tracked_target_reroll"
        and current_permission_context.source_payload != source_payload
    ):
        raise GameLifecycleError(f"{phase_label} dice reroll source payload drift.")


def _source_backed_attack_context_id_matches_active_pool(
    *,
    attack_sequence: AttackSequence,
    attack_context_id: str,
) -> bool:
    current_pool = attack_sequence.current_pool()
    pool_prefix = f"{attack_sequence.sequence_id}:pool-{attack_sequence.pool_index + 1:03d}:"
    for attack_index in range(current_pool.attacks):
        base_context_id = f"{pool_prefix}attack-{attack_index + 1:03d}"
        if attack_context_id == base_context_id:
            return True
        generated_prefix = f"{base_context_id}:generated-hit-"
        if not attack_context_id.startswith(generated_prefix):
            continue
        generated_hit_number = attack_context_id.removeprefix(generated_prefix)
        if generated_hit_number.isdecimal() and int(generated_hit_number) >= 2:
            return True
    return False


def _source_backed_attack_kind_for_phase(source_phase: BattlePhase) -> str:
    if source_phase is BattlePhase.SHOOTING:
        return "ranged"
    if source_phase is BattlePhase.FIGHT:
        return "melee"
    raise GameLifecycleError("Source-backed attack rerolls require Shooting or Fight phase.")


def _request_source_backed_wound_reroll_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    roll_state: DiceRollState | None,
    pool: RangedAttackPool,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str | None = None,
    attacker_keywords: tuple[str, ...],
    attack_context_id: str,
    source_phase: BattlePhase,
) -> LifecycleStatus | None:
    if roll_state is None:
        return None
    if source_phase not in {BattlePhase.SHOOTING, BattlePhase.FIGHT}:
        return None
    if roll_state.rerolls:
        return None
    if roll_state.original_result.spec.reroll_forbidden_rule_ids:
        return None
    actor_id = roll_state.original_result.spec.actor_id
    if actor_id is None:
        return None
    permission_context = source_backed_reroll_permission_context_for_unit(
        state=state,
        player_id=actor_id,
        unit_instance_id=attacking_unit_instance_id,
        model_instance_id=attacker_model_instance_id,
        roll_type=roll_state.original_result.spec.roll_type,
        timing_window="attack_sequence.wound",
        attack_kind=_source_backed_attack_kind_for_phase(source_phase),
        target_unit_instance_id=pool.target_unit_instance_id,
    )
    if permission_context is None:
        return None
    permission = _source_backed_wound_permission_for_attack(
        state=state,
        permission_context=permission_context,
        roll_state=roll_state,
        target_unit_instance_id=pool.target_unit_instance_id,
        attacker_keywords=attacker_keywords,
    )
    if permission is None:
        return None
    if _source_backed_reroll_already_answered(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
        source_id=permission.source_id,
    ):
        return None
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    request = manager.build_reroll_request(
        roll_state,
        request_id=state.next_decision_request_id(),
        actor_id=actor_id,
        permission=permission,
        extra_payload={
            "source_rule_id": permission.source_id,
            "attack_context": {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": source_phase.value,
                "unit_instance_id": attacking_unit_instance_id,
                "target_unit_instance_id": pool.target_unit_instance_id,
                "attack_context_id": attack_context_id,
                "weapon_profile_id": pool.weapon_profile_id,
                "wound_roll_state": validate_json_value(roll_state.to_payload()),
                "source_payload": validate_json_value(permission_context.source_payload),
            },
        },
    )
    decisions.request_decision(request)
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": source_phase.value,
            "phase_body_status": "attack_wound_source_backed_reroll_pending",
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": actor_id,
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "affected_unit_instance_id": attacking_unit_instance_id,
            "target_unit_instance_id": pool.target_unit_instance_id,
            "attack_context_id": attack_context_id,
            "pending_request_id": request.request_id,
        },
    )


def _source_backed_wound_permission_for_attack(
    *,
    state: GameState,
    permission_context: SourceBackedRerollPermissionContext,
    roll_state: DiceRollState,
    target_unit_instance_id: str,
    attacker_keywords: tuple[str, ...],
) -> RerollPermission | None:
    source_payload = permission_context.source_payload
    conditional = source_payload.get("conditional_wound_reroll")
    if conditional is None:
        return permission_context.permission
    if not isinstance(conditional, dict):
        raise GameLifecycleError("Conditional wound reroll payload must be an object.")
    if _conditional_wound_full_reroll_applies(
        state=state,
        conditional=conditional,
        target_unit_instance_id=target_unit_instance_id,
        attacker_keywords=attacker_keywords,
    ):
        return replace(
            permission_context.permission,
            component_selection_policy=RerollComponentSelectionPolicy.WHOLE_ROLL,
            allowed_component_selections=None,
        )
    reroll_values = conditional.get("reroll_unmodified_values")
    if not isinstance(reroll_values, list) or not all(
        type(value) is int for value in reroll_values
    ):
        raise GameLifecycleError("Conditional wound reroll requires integer reroll values.")
    if roll_state.current_total not in cast(list[int], reroll_values):
        return None
    return replace(
        permission_context.permission,
        component_selection_policy=RerollComponentSelectionPolicy.COMPONENT_SELECTION,
        allowed_component_selections=((0,),),
    )


def _conditional_wound_full_reroll_applies(
    *,
    state: GameState,
    conditional: dict[str, JsonValue],
    target_unit_instance_id: str,
    attacker_keywords: tuple[str, ...],
) -> bool:
    battle_shock_reroll = conditional.get("full_reroll_if_target_battle_shocked")
    if battle_shock_reroll is not None and type(battle_shock_reroll) is not bool:
        raise GameLifecycleError("Conditional wound battle-shock reroll must be bool.")
    if battle_shock_reroll is True and target_unit_instance_id in state.battle_shocked_unit_ids:
        return True
    objective_reroll = conditional.get("full_reroll_if_target_within_objective_range")
    if objective_reroll is not None and type(objective_reroll) is not bool:
        raise GameLifecycleError("Conditional wound objective reroll must be bool.")
    if objective_reroll is not True:
        return False
    required_keyword = conditional.get("full_reroll_required_attacker_keyword")
    if required_keyword is not None:
        if type(required_keyword) is not str:
            raise GameLifecycleError("Conditional wound reroll required keyword must be a string.")
        canonical_required = _canonical_keyword(required_keyword)
        if canonical_required not in {_canonical_keyword(keyword) for keyword in attacker_keywords}:
            return False
    return _target_unit_within_any_objective_marker_range(
        state=state,
        target_unit_instance_id=target_unit_instance_id,
    )


def _target_unit_within_any_objective_marker_range(
    *,
    state: GameState,
    target_unit_instance_id: str,
) -> bool:
    if state.mission_setup is None or state.battlefield_state is None:
        return False
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=target_unit_instance_id,
    )
    alive_model_ids = {model.model_instance_id for model in rules_unit.alive_models()}
    removed_model_ids = set(state.battlefield_state.removed_model_ids)
    target_models = tuple(
        geometry_model_for_placement(
            model=model_by_id(state=state, model_instance_id=placement.model_instance_id),
            placement=placement,
        )
        for component in rules_unit.components
        for unit_placement in (
            state.battlefield_state.unit_placement_or_none(component.unit.unit_instance_id),
        )
        if unit_placement is not None
        for placement in unit_placement.model_placements
        if placement.model_instance_id in alive_model_ids
        and placement.model_instance_id not in removed_model_ids
    )
    return any(
        objective_marker_controls_model(
            marker_pose=Pose.at(marker.x_inches, marker.y_inches, marker.z_inches),
            model=target_model,
            marker_id=marker.objective_marker_id,
            horizontal_inches=marker.control_horizontal_inches,
            vertical_inches=marker.control_vertical_inches,
            marker_diameter_inches=marker.marker_diameter_inches,
        )
        for marker in (
            mission_marker.to_objective_marker()
            for mission_marker in state.mission_setup.objective_markers
        )
        for target_model in target_models
    )


def _canonical_keyword(keyword: str) -> str:
    return keyword.replace("_", " ").replace("-", " ").upper()


def _source_backed_reroll_already_answered(
    *,
    decisions: DecisionController,
    roll_id: str,
    source_id: str,
) -> bool:
    requested_roll_id = _validate_identifier("roll_id", roll_id)
    requested_source_id = _validate_identifier("source_id", source_id)
    for record in decisions.records:
        if record.request.decision_type != DICE_REROLL_DECISION_TYPE:
            continue
        if not isinstance(record.request.payload, dict):
            raise GameLifecycleError("Dice reroll request payload must be an object.")
        if record.request.payload.get("roll_id") != requested_roll_id:
            continue
        permission_payload = record.request.payload.get("permission")
        if not isinstance(permission_payload, dict):
            continue
        if permission_payload.get("source_id") == requested_source_id:
            return True
    return False


def _command_reroll_opportunity_window(
    *,
    state: GameState,
    decisions: DecisionController,
    window_id: str,
    roll_state: DiceRollState,
    actor_id: str,
    affected_unit_instance_id: str,
    phase: BattlePhase,
    use_option_ids: tuple[str, ...],
    decline_option_id: str,
) -> OpportunityWindow:
    sequence_number = len(decisions.event_log.records)
    anchor_event_id = _dice_rolled_event_id_for_roll(
        decisions=decisions,
        roll_id=roll_state.original_result.roll_id,
    )
    timing_window = TimingWindow(
        window_id=window_id,
        descriptor=TimingWindowDescriptor(
            descriptor_id=f"{window_id}:descriptor",
            trigger_kind=TimingTriggerKind.AFTER_DICE_ROLL,
            source_rule_id="core:command-reroll",
            phase=phase,
            source_step=roll_state.original_result.spec.roll_type,
            metadata={
                "roll_id": roll_state.original_result.roll_id,
                "roll_type": roll_state.original_result.spec.roll_type,
                "affected_unit_instance_id": affected_unit_instance_id,
            },
        ),
        game_id=state.game_id,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        phase=phase,
        trigger_event_id=anchor_event_id,
    )
    legal_actions = (
        OpportunityLegalAction(
            action_id=decline_option_id,
            source_id="core:pass",
            action_kind=OpportunityActionKind.PASS,
            controller_id=None,
            label="Decline Command Re-roll",
            batching_mode=TriggerBatchingMode.NONE,
            payload={"pass": True},
        ),
        *(
            OpportunityLegalAction(
                action_id=option_id,
                source_id="core:command-reroll",
                action_kind=OpportunityActionKind.REROLL,
                controller_id=actor_id,
                label="Command Re-roll",
                cost=({"resource": "cp", "amount": 1},),
                target_ids=(roll_state.original_result.roll_id,),
                target_spec={
                    "roll_id": roll_state.original_result.roll_id,
                    "roll_type": roll_state.original_result.spec.roll_type,
                    "affected_unit_instance_id": affected_unit_instance_id,
                },
                batching_mode=TriggerBatchingMode.ONE_OF,
                payload={
                    "stratagem_id": "command-reroll",
                    "option_id": option_id,
                    "roll_state": cast(JsonValue, roll_state.to_payload()),
                },
            )
            for option_id in use_option_ids
        ),
    )
    return OpportunityWindow(
        window_id=window_id,
        timing_window=timing_window,
        state_hash=_command_reroll_opportunity_state_hash(state=state, decisions=decisions),
        sequence_number=sequence_number,
        revision=1,
        anchor_event_ids=(anchor_event_id,),
        acting_player_id=state.active_player_id,
        eligible_player_ids=(actor_id,),
        priority_order=(actor_id,),
        legal_actions=legal_actions,
        default_action_id=decline_option_id,
        metadata={
            "roll_id": roll_state.original_result.roll_id,
            "roll_type": roll_state.original_result.spec.roll_type,
            "phase": phase.value,
        },
    )


def _command_reroll_opportunity_options(
    *,
    window: OpportunityWindow,
    player_id: str,
    use_options: tuple[DecisionOption, ...],
    decline_option: DecisionOption,
) -> tuple[DecisionOption, ...]:
    return tuple(
        _command_reroll_opportunity_option(
            window=window,
            player_id=player_id,
            option=option,
        )
        for option in (*use_options, decline_option)
    )


def _command_reroll_opportunity_option(
    *,
    window: OpportunityWindow,
    player_id: str,
    option: DecisionOption,
) -> DecisionOption:
    action = window.action_by_id(option.option_id)
    if not isinstance(option.payload, dict):
        raise GameLifecycleError("Command Re-roll opportunity option payload must be an object.")
    fingerprint = window.legal_action_fingerprint(player_id)
    payload = dict(option.payload)
    payload[OPPORTUNITY_SUBMISSION_PAYLOAD_KEY] = window.submission_payload_for_action(
        action=action,
        player_id=player_id,
        legal_action_fingerprint=fingerprint,
    )
    return DecisionOption(
        option_id=option.option_id,
        label=option.label,
        payload=validate_json_value(payload),
    )


def _command_reroll_opportunity_state_hash(
    *,
    state: GameState,
    decisions: DecisionController,
) -> str:
    records = decisions.event_log.records
    return opportunity_boundary_state_hash(
        state_payload=_command_reroll_opportunity_boundary_state_payload(state),
        event_count=len(records),
        last_event_id=None if not records else records[-1].event_id,
    )


def _command_reroll_opportunity_boundary_state_payload(state: GameState) -> JsonValue:
    return opportunity_boundary_game_state_payload(
        game_id=state.game_id,
        ruleset_descriptor_hash=state.ruleset_descriptor_hash,
        stage=state.stage.value,
        battle_phase_index=state.battle_phase_index,
        battle_round=state.battle_round,
        active_player_id=state.active_player_id,
        player_ids=state.player_ids,
        turn_order=state.turn_order,
        decision_request_count=state.decision_request_count,
        command_point_ledgers=cast(
            JsonValue,
            [ledger.to_payload() for ledger in state.command_point_ledgers],
        ),
        stratagem_use_records=cast(
            JsonValue,
            [record.to_payload() for record in state.stratagem_use_records],
        ),
        faction_rule_states=cast(
            JsonValue,
            [record.to_payload() for record in state.faction_rule_states],
        ),
    )


def _dice_rolled_event_id_for_roll(*, decisions: DecisionController, roll_id: str) -> str:
    requested_roll_id = _validate_identifier("roll_id", roll_id)
    for event in decisions.event_log.records:
        if event.event_type != "dice_rolled":
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("dice_rolled event payload must be an object.")
        result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
        if result.roll_id == requested_roll_id:
            return event.event_id
    raise GameLifecycleError("Command Re-roll opportunity requires a recorded dice roll.")


def _random_characteristic_roll_spec(
    *,
    characteristic: Characteristic,
    timing: RandomCharacteristicTiming,
    scope_id: str,
    expression: DiceExpression,
    reason: str,
    actor_id: str | None,
) -> DiceRollSpec:
    if type(characteristic) is not Characteristic:
        raise GameLifecycleError("Random characteristic requires a Characteristic.")
    if type(timing) is not RandomCharacteristicTiming:
        raise GameLifecycleError("Random characteristic requires a timing.")
    if type(expression) is not DiceExpression:
        raise GameLifecycleError("Random characteristic requires a DiceExpression.")
    scope = _validate_identifier("Random characteristic scope_id", scope_id)
    return DiceRollSpec(
        expression=expression,
        reason=reason,
        roll_type=f"random_characteristic.{characteristic.value}.{timing.value}.{scope}",
        actor_id=actor_id,
    )


def _append_replay_resume_unique_event_once(
    *,
    decisions: DecisionController,
    event_type: str,
    payload: JsonValue,
) -> EventRecord:
    """Append one logical replay event whose payload carries a stable unique identity.

    This is only for attack-sequence resume paths where rerunning a resolver can
    revisit an already-emitted event with the same roll, attack context, or
    characteristic scope. Do not use it for events whose payloads can be
    legitimately identical across separate game happenings.
    """

    event_payload = validate_json_value(payload)
    for event in decisions.event_log.records:
        if event.event_type == event_type and event.payload == event_payload:
            return event
    return decisions.event_log.append(event_type, event_payload)
