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
)


def _resolve_hazardous_tests(
    *,
    state: GameState,
    decisions: DecisionController,
    manager: DiceRollManager,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    hazardous_pools = tuple(
        pool
        for pool in attack_sequence.attack_pools
        if has_weapon_keyword(pool.weapon_profile, WeaponKeyword.HAZARDOUS)
    )
    if not hazardous_pools:
        return None
    hazardous_weapon_profile_ids = tuple(
        sorted({pool.weapon_profile_id for pool in hazardous_pools})
    )
    roll_state = manager.roll(
        hazard_roll_spec(
            reason=(
                f"Hazardous test for {attack_sequence.attacking_unit_instance_id} after shooting"
            ),
            roll_type="hazardous_test",
            actor_id=attack_sequence.attacking_unit_instance_id,
        )
    )
    hazardous_failed = hazard_roll_failed(roll_state)
    mortal_wounds = 0
    if not hazardous_failed:
        _emit_hazardous_test_resolved(
            decisions=decisions,
            attack_sequence=attack_sequence,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            roll_state=roll_state,
            successful=True,
            mortal_wounds=mortal_wounds,
            mortal_wound_application=None,
            pending_mortal_wound_request_id=None,
        )
        return None

    mortal_wounds = _hazardous_mortal_wounds_for_attacker(
        state=state,
        attacking_unit_instance_id=attack_sequence.attacking_unit_instance_id,
    )
    progress = MortalWoundApplicationProgress.start(
        application_id=f"{attack_sequence.sequence_id}:hazardous:mortal-wounds",
        source_rule_id=HAZARDOUS_RULE_ID,
        source_context=_hazardous_source_context_payload(
            attack_sequence=attack_sequence,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            roll_state=roll_state,
            mortal_wounds=mortal_wounds,
        ),
        target_unit_instance_id=attack_sequence.attacking_unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=attack_sequence.attacking_unit_instance_id,
        ),
        mortal_wounds=mortal_wounds,
        spill_over=True,
    )
    routed = continue_mortal_wound_application(
        state=state,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        _emit_hazardous_test_resolved(
            decisions=decisions,
            attack_sequence=attack_sequence,
            hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
            roll_state=roll_state,
            successful=False,
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
        hazardous_weapon_profile_ids=hazardous_weapon_profile_ids,
        roll_state=roll_state,
        successful=False,
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
    return None


def _emit_hazardous_test_resolved(
    *,
    decisions: DecisionController,
    attack_sequence: AttackSequence,
    hazardous_weapon_profile_ids: tuple[str, ...],
    roll_state: DiceRollState,
    successful: bool,
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
            "hazardous_weapon_profile_ids": list(hazardous_weapon_profile_ids),
            "roll_state": roll_state.to_payload(),
            "successful": successful,
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
            "hazardous_weapon_profile_ids": source_context["hazardous_weapon_profile_ids"],
            "hazardous_roll_state": source_context["hazardous_roll_state"],
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
            "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
            "sequence_id": attack_sequence.sequence_id,
            "source_rule_id": HAZARDOUS_RULE_ID,
            "source_kind": HAZARDOUS_SOURCE_KIND,
        },
    )


def _hazardous_source_context_payload(
    *,
    attack_sequence: AttackSequence,
    hazardous_weapon_profile_ids: tuple[str, ...],
    roll_state: DiceRollState,
    mortal_wounds: int,
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": HAZARDOUS_SOURCE_KIND,
            "sequence_id": attack_sequence.sequence_id,
            "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
            "hazardous_weapon_profile_ids": list(hazardous_weapon_profile_ids),
            "hazardous_roll_state": roll_state.to_payload(),
            "mortal_wounds": mortal_wounds,
        }
    )


def _hazardous_source_context_from_payload(
    payload: JsonValue,
) -> HazardousMortalWoundSourceContextPayload:
    raw = _payload_object(payload)
    if raw.get("source_kind") != HAZARDOUS_SOURCE_KIND:
        raise GameLifecycleError("Hazardous mortal wound source context kind is invalid.")
    weapon_profile_ids = raw.get("hazardous_weapon_profile_ids")
    if not isinstance(weapon_profile_ids, list):
        raise GameLifecycleError(
            "Hazardous mortal wound source context weapon profile IDs must be a list."
        )
    hazardous_roll_state = raw.get("hazardous_roll_state")
    if not isinstance(hazardous_roll_state, dict):
        raise GameLifecycleError(
            "Hazardous mortal wound source context roll state must be an object."
        )
    return {
        "source_kind": HAZARDOUS_SOURCE_KIND,
        "sequence_id": _payload_string(raw, key="sequence_id"),
        "attacking_unit_instance_id": _payload_string(raw, key="attacking_unit_instance_id"),
        "hazardous_weapon_profile_ids": list(
            _validate_identifier_tuple(
                "Hazardous mortal wound weapon_profile_ids",
                tuple(weapon_profile_ids),
            )
        ),
        "hazardous_roll_state": cast(
            DiceRollStatePayload,
            validate_json_value(hazardous_roll_state),
        ),
        "mortal_wounds": _payload_positive_int(raw, key="mortal_wounds"),
    }


def _hazardous_mortal_wounds_for_attacker(
    *,
    state: GameState,
    attacking_unit_instance_id: str,
) -> int:
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=attacking_unit_instance_id,
    )
    component_wound_values = tuple(
        hazard_mortal_wounds_per_failed_roll(component.unit) for component in rules_unit.components
    )
    if not component_wound_values:
        raise GameLifecycleError("Hazardous attacker requires at least one component.")
    return min(component_wound_values)


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
    terrain_volumes = tuple(
        volume for feature in terrain_features for volume in feature.terrain_volumes()
    )
    attacking_unit_id = attack_pool_attacker_unit_id(state=state, pool=pool)
    dynamic_blockers = shooting_dynamic_model_blockers(
        scenario=scenario,
        observing_unit_id=attacking_unit_id,
        target_unit_id=pool.target_unit_instance_id,
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset_descriptor,
        los_cache_key=shooting_visibility_cache_key(
            scenario=scenario,
            terrain_features=terrain_features,
        ),
        observer_model=observer_geometry,
        target_models=(target_geometry,),
        terrain_features=terrain_features,
        terrain_volumes=terrain_volumes,
        dynamic_model_blockers=dynamic_blockers,
        observer_keywords=unit_by_id(
            state=state,
            unit_instance_id=attacking_unit_id,
        ).keywords,
        target_keywords=rules_unit_view_by_id(
            state=state,
            unit_instance_id=pool.target_unit_instance_id,
        ).keywords,
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
) -> BenefitOfCoverResult | None:
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Fortification cover requires battlefield_state.")
    try:
        attacking_unit_placement = battlefield.unit_placement_by_id(attacking_unit_id)
    except PlacementError as exc:
        raise GameLifecycleError("Fortification cover attacker placement is invalid.") from exc
    blocker_records: set[CoverSourceRecord] = set()
    blocker_witness: LineOfSightWitness | None = None
    for attacker_placement in attacking_unit_placement.model_placements:
        attacker_model = model_by_id(
            state=state,
            model_instance_id=attacker_placement.model_instance_id,
        )
        observer_geometry = geometry_model_for_placement(
            model=attacker_model,
            placement=attacker_placement,
        )
        context = TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=ruleset_descriptor,
            los_cache_key=shooting_visibility_cache_key(
                scenario=scenario,
                terrain_features=terrain_features,
            ),
            observer_model=observer_geometry,
            target_models=(target_geometry,),
            terrain_features=terrain_features,
            terrain_volumes=terrain_volumes,
            dynamic_model_blockers=dynamic_blockers,
            observer_keywords=unit_by_id(
                state=state,
                unit_instance_id=attacking_unit_id,
            ).keywords,
            target_keywords=rules_unit_view_by_id(
                state=state,
                unit_instance_id=pool.target_unit_instance_id,
            ).keywords,
        )
        witness = context.resolve_line_of_sight()
        fortification_blocker_ids = _fortification_full_visibility_blocker_ids(
            state=state,
            witness=witness,
        )
        if not fortification_blocker_ids:
            continue
        blocker_witness = witness
        for blocker_id in fortification_blocker_ids:
            blocker_records.add(
                CoverSourceRecord(
                    feature_id=blocker_id,
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
        cover_effect=CoverEffect.SAVE_BONUS,
        source_feature_ids=tuple(record.feature_id for record in sorted_records),
        source_policy_kinds=(LineOfSightPolicy.TRUE_LINE_OF_SIGHT,),
        source_records=sorted_records,
        los_cache_key=blocker_witness.los_cache_key,
        target_unit_visible=blocker_witness.unit_visible,
        target_unit_fully_visible=blocker_witness.unit_fully_visible,
        non_stacking=True,
        ap_zero_save_bonus_excluded_for_save_3_plus_or_better=True,
    )


def _fortification_full_visibility_blocker_ids(
    *,
    state: GameState,
    witness: LineOfSightWitness,
) -> tuple[str, ...]:
    blocker_ids: set[str] = set()
    for blocker in witness.all_blocker_records():
        if blocker.blocker_kind is not VisibilityBlockerKind.MODEL:
            continue
        if not blocker.blocks_full_visibility:
            continue
        if _model_owner_unit_has_keyword(
            state=state,
            model_instance_id=blocker.blocker_id,
            keyword="FORTIFICATION",
        ):
            blocker_ids.add(blocker.blocker_id)
    return tuple(sorted(blocker_ids))


def _model_owner_unit_has_keyword(
    *,
    state: GameState,
    model_instance_id: str,
    keyword: str,
) -> bool:
    canonical = _canonical_keyword(keyword)
    for army in state.army_definitions:
        for unit in army.units:
            if not any(model.model_instance_id == model_instance_id for model in unit.own_models):
                continue
            return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}
    raise GameLifecycleError("Fortification cover blocker model is unknown.")
