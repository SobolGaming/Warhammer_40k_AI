# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.shooting_imports import *
from warhammer40k_core.engine.phases.shooting_model import *
from warhammer40k_core.engine.phases.shooting_handler import *
from warhammer40k_core.engine.phases.shooting_reactions import *
from warhammer40k_core.engine.phases.shooting_requests import *
from warhammer40k_core.engine.phases.shooting_unit_selection import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord, RangedAttackHistoryRecord
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
    from warhammer40k_core.engine.phases.shooting_model import SELECT_SHOOTING_UNIT_DECISION_TYPE, SELECT_SHOOTING_TYPE_DECISION_TYPE, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE, COMPLETE_SHOOTING_PHASE_OPTION_ID, _COMPLETE_SHOOTING_PHASE_STATUS, _default_stratagem_index, ShootingUnitSelectionPayload, ShootingTypeSelectionPayload, ShootingPhaseStatePayload, OutOfPhaseShootingStatePayload, ShootingDeclarationProposalRequestPayload, ShootingDeclarationDecisionPayload, _AvailableWeapon, _ShootingUnitCandidateCacheKey, _ShootingModelCandidateCacheKey, _ShootingModelCandidateCache, ShootingUnitSelection, ShootingTypeSelection, ShootingPhaseState, OutOfPhaseShootingState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler, invalid_shooting_phase_start_faction_rule_status, _shooting_phase_start_faction_rule_drift_reason, _request_shooting_phase_start_rule_if_available
    from warhammer40k_core.engine.phases.shooting_reactions import _complete_out_of_phase_shooting, _request_active_shooting_phase_stratagem_if_available, _request_after_unit_selected_as_target_stratagem_if_available, _resolve_completed_shooting_attack_sequence_continuation, _request_friendly_unit_has_shot_stratagem_if_available, _request_enemy_unit_has_shot_stratagem_if_available, _request_shooting_end_surge_if_available, _eligible_triggered_movement_units_from_shooting_grants, _shooting_end_surge_grant_distance_bonus, _shooting_end_surge_distance_roll_spec, _attack_sequence_completed_event_id, _friendly_unit_has_shot_timing_window_id, _active_shooting_phase_stratagem_timing_window_id, _selected_as_target_timing_window_id, _enemy_unit_has_shot_timing_window_id, _target_unit_ids_for_attack_sequence, _stratagem_used_for_context, _successful_hit_target_unit_ids_for_sequence, _destroyed_target_unit_ids_for_sequence, _destroyed_enemy_unit_ids_for_sequence, _shooting_end_surge_event_already_processed
    from warhammer40k_core.engine.phases.shooting_requests import _request_shooting_type_selection, _request_shooting_declaration, request_out_of_phase_shooting_declaration, _target_candidate_payload_for_request, _embedded_weapon_ability_request_prefix, _required_weapon_ability_selections_for_target, _shooting_types_for_candidate_payload, _shooting_types_for_selected_type, _shooting_types_for_selected_type_for_rules_unit
    from warhammer40k_core.engine.phases.shooting_unit_selection import _apply_shooting_unit_selection_decision, _apply_shooting_unit_selected_effect_grants, _request_shooting_unit_selected_grant_decision_if_available, _shooting_unit_selected_grant_options, _apply_shooting_unit_selected_grant_decision, _selected_shooting_unit_grants_from_payload, _validate_selected_shooting_unit_grants, _record_shooting_unit_selected_grant_effects, _shooting_unit_selected_context, _active_shooting_unit_selection, _validate_shooting_unit_selected_grant_payload_context, _shooting_unit_selected_grant_unit_effect_target_ids, _shooting_unit_selected_grant_effect_expiration
    from warhammer40k_core.engine.phases.shooting_declaration_validation import _validate_declaration_submission, _validate_out_of_phase_declaration_submission, _attack_pools_for_proposal, _AttackPoolValidationResult, _attack_pools_or_validation, _validate_duplicate_weapon_ability_selection, _shooting_candidate_with_target_restrictions, _modified_shooting_weapon_profile, _runtime_modifier_registry, _out_of_phase_allowed_target_unit_ids, _out_of_phase_uses_fire_overwatch, _forced_shooting_type_for_out_of_phase, _selected_shooting_type_for_declaration, _shooting_types_for_declaration_candidate, _targeting_rule_ids_with_shooting_type, _validate_model_pistol_exclusivity, _apply_phase13d_weapon_modifiers
    from warhammer40k_core.engine.phases.shooting_targeting import _target_within_half_weapon_range, _snap_shooting_type_allowed_for_unit_target, _declaration_target_within_max_range, _unit_target_within_max_range, _unit_placements_for_rules_unit_or_none, _rules_unit_remained_stationary, _heavy_hit_roll_modifier_applies, _rules_unit_set_up_this_turn, _rules_unit_within_enemy_engagement_range, _target_visible_to_friendly_unit, _declaration_source_unit
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_apply_attack_sequence_decision",
    "_apply_attack_sequence_decision_to_sequence",
    "_apply_attack_sequence_selection_decision",
    "_apply_attack_sequence_selection_to_sequence",
    "_apply_out_of_phase_shooting_declaration_decision",
    "_apply_shooting_declaration_decision",
    "_apply_shooting_dice_reroll_decision",
    "_apply_shooting_type_selection_decision",
    "_record_one_shot_weapon_uses_for_attack_pools",
    "_record_ranged_attack_history_for_declaration",
    "apply_hidden_status_loss_after_ranged_attacks",
)


def _apply_shooting_dice_reroll_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    _validate_shooting_phase_state(state)
    shooting_state = _ensure_shooting_phase_state(state=state)
    attack_sequence = shooting_state.attack_sequence
    if attack_sequence is None:
        raise GameLifecycleError("Shooting dice reroll requires an active attack sequence.")
    apply_source_backed_attack_dice_reroll_decision(
        state=state,
        result=result,
        decisions=decisions,
        attack_sequence=attack_sequence,
        expected_phase=BattlePhase.SHOOTING,
        phase_label="Shooting",
        runtime_modifier_registry=runtime_modifier_registry,
    )
    return None


def _apply_shooting_type_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
) -> None:
    _validate_shooting_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Shooting type selection actor must be the active player.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        raise GameLifecycleError("Shooting type selection requires active_selection.")
    if shooting_state.selected_shooting_type is not None:
        raise GameLifecycleError("Shooting type has already been selected.")
    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    if unit_instance_id != shooting_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Shooting type selection unit drift.")
    shooting_type = shooting_type_from_token(_payload_string(payload, key="shooting_type"))
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
    legal_types = _legal_shooting_types_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    if shooting_type not in legal_types:
        raise GameLifecycleError("Shooting type selection is not currently legal.")
    selection = ShootingTypeSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        shooting_type=shooting_type,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.replace_shooting_phase_state(shooting_state.with_shooting_type_selection(selection))
    decisions.event_log.append(
        "shooting_type_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": unit_instance_id,
                "shooting_type": shooting_type.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "shooting_type_selected",
            }
        ),
    )


def _apply_shooting_declaration_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> None:
    if _apply_out_of_phase_shooting_declaration_decision(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    ):
        return
    _validate_shooting_phase_state(state)
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        raise GameLifecycleError("Shooting declaration requires active_selection.")
    proposal = shooting_declaration_proposal_from_json(result.payload)
    attack_pools, ineligible_unit_ids = _attack_pools_for_proposal(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        result_id=result.result_id,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    one_shot_records = _record_one_shot_weapon_uses_for_attack_pools(
        state=state,
        attack_pools=attack_pools,
        source_phase=BattlePhase.SHOOTING,
        result_id=result.result_id,
    )
    attack_sequence = AttackSequence.start(
        sequence_id=f"attack-sequence:{result.result_id}",
        attacker_player_id=_active_player_id(state),
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=attack_pools,
    )
    state.replace_shooting_phase_state(
        shooting_state.with_declaration(
            attack_pools=attack_pools,
            ineligible_unit_instance_ids=ineligible_unit_ids,
            attack_sequence=attack_sequence,
        )
    )
    ranged_attack_history_record = _record_ranged_attack_history_for_declaration(
        state=state,
        player_id=_active_player_id(state),
        unit_instance_id=proposal.unit_instance_id,
        phase=BattlePhase.SHOOTING,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    apply_hidden_status_loss_after_ranged_attacks(
        state=state,
        decisions=decisions,
        unit_instance_id=proposal.unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
        ruleset_descriptor=ruleset_descriptor,
        event_type="unit_hidden_status_lost_after_shooting",
    )
    decisions.event_log.append(
        "shooting_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": proposal.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal.proposal_request_id,
                "visibility_cache_key": proposal.visibility_cache_key,
                "attack_pools": [pool.to_payload() for pool in attack_pools],
                "one_shot_weapon_use_records": [record.to_payload() for record in one_shot_records],
                "ranged_attack_history_record": ranged_attack_history_record.to_payload(),
                "ineligible_unit_instance_ids": list(ineligible_unit_ids),
                "phase_body_status": "declaration_accepted",
            }
        ),
    )


def _apply_out_of_phase_shooting_declaration_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> bool:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is None:
        return False
    proposal = shooting_declaration_proposal_from_json(result.payload)
    if (
        proposal.source_decision_request_id != out_of_phase_state.source_decision_request_id
        or proposal.source_decision_result_id != out_of_phase_state.source_decision_result_id
    ):
        return False
    attack_pools, ineligible_unit_ids = _attack_pools_for_proposal(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        result_id=result.result_id,
        shooting_player_id=out_of_phase_state.player_id,
        out_of_phase_state=out_of_phase_state,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if ineligible_unit_ids:
        raise GameLifecycleError("Out-of-phase shooting cannot mark extra units as shot.")
    one_shot_records = _record_one_shot_weapon_uses_for_attack_pools(
        state=state,
        attack_pools=attack_pools,
        source_phase=out_of_phase_state.parent_phase,
        result_id=result.result_id,
    )
    attack_sequence = AttackSequence.start(
        sequence_id=f"out-of-phase-attack-sequence:{result.result_id}",
        attacker_player_id=out_of_phase_state.player_id,
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=attack_pools,
    )
    state.replace_out_of_phase_shooting_state(
        out_of_phase_state.with_declaration(
            attack_pools=attack_pools,
            attack_sequence=attack_sequence,
        )
    )
    ranged_attack_history_record = _record_ranged_attack_history_for_declaration(
        state=state,
        player_id=out_of_phase_state.player_id,
        unit_instance_id=proposal.unit_instance_id,
        phase=out_of_phase_state.parent_phase,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    apply_hidden_status_loss_after_ranged_attacks(
        state=state,
        decisions=decisions,
        unit_instance_id=proposal.unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
        ruleset_descriptor=ruleset_descriptor,
        event_type="unit_hidden_status_lost_after_out_of_phase_shooting",
    )
    decisions.event_log.append(
        "out_of_phase_shooting_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "player_id": out_of_phase_state.player_id,
                "parent_phase": out_of_phase_state.parent_phase.value,
                "source_rule_id": out_of_phase_state.source_rule_id,
                "unit_instance_id": proposal.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal.proposal_request_id,
                "visibility_cache_key": proposal.visibility_cache_key,
                "attack_pools": [pool.to_payload() for pool in attack_pools],
                "one_shot_weapon_use_records": [record.to_payload() for record in one_shot_records],
                "ranged_attack_history_record": ranged_attack_history_record.to_payload(),
            }
        ),
    )
    return True


def _record_ranged_attack_history_for_declaration(
    *,
    state: GameState,
    player_id: str,
    unit_instance_id: str,
    phase: BattlePhase,
    request_id: str,
    result_id: str,
) -> RangedAttackHistoryRecord:
    from warhammer40k_core.engine.game_state import RangedAttackHistoryRecord

    active_player_id = state.active_player_id
    if active_player_id is None:
        raise GameLifecycleError("Ranged attack history requires an active player turn.")
    record = RangedAttackHistoryRecord(
        player_id=player_id,
        unit_instance_id=unit_instance_id,
        battle_round=state.battle_round,
        active_player_id=active_player_id,
        phase=phase,
        request_id=request_id,
        result_id=result_id,
    )
    state.record_ranged_attack_history(record)
    return record


def _record_one_shot_weapon_uses_for_attack_pools(
    *,
    state: GameState,
    attack_pools: tuple[RangedAttackPool, ...],
    source_phase: BattlePhase,
    result_id: str,
) -> tuple[OneShotWeaponUseRecord, ...]:
    records: list[OneShotWeaponUseRecord] = []
    for pool_index, pool in enumerate(attack_pools, start=1):
        if not has_weapon_keyword(pool.weapon_profile, WeaponKeyword.ONE_SHOT):
            continue
        model_instance_id = (
            pool.attacker_model_instance_id
            if pool.firing_deck_source_model_instance_id is None
            else pool.firing_deck_source_model_instance_id
        )
        records.append(
            state.record_one_shot_weapon_selected(
                model_instance_id=model_instance_id,
                wargear_id=pool.wargear_id,
                weapon_profile_id=pool.weapon_profile_id,
                source_phase=source_phase,
                selection_id=f"{result_id}:one-shot-pool-{pool_index:03d}",
            )
        )
    return tuple(records)


def apply_hidden_status_loss_after_ranged_attacks(
    *,
    state: GameState,
    decisions: DecisionController,
    unit_instance_id: str,
    request_id: str,
    result_id: str,
    ruleset_descriptor: RulesetDescriptor,
    event_type: str,
) -> None:
    if not ruleset_descriptor.terrain_visibility_policy.hidden_lost_after_shooting:
        return
    effects = state.persisting_effects_for_unit(unit_instance_id)
    hidden_effect_ids = hidden_unit_effect_ids(effects)
    if not hidden_effect_ids:
        return
    current_phase = state.current_battle_phase
    if current_phase is None:
        raise GameLifecycleError("Hidden shooting status loss requires a battle phase.")
    if ranged_attacks_keep_hidden_by_effects(effects):
        decisions.event_log.append(
            "unit_hidden_status_preserved_after_shooting",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": current_phase.value,
                    "unit_instance_id": unit_instance_id,
                    "request_id": request_id,
                    "result_id": result_id,
                    "hidden_effect_ids": list(hidden_effect_ids),
                    "phase_body_status": "hidden_status_preserved",
                }
            ),
        )
        return
    removed_effects = state.remove_persisting_effects_by_id(hidden_effect_ids)
    decisions.event_log.append(
        event_type,
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": current_phase.value,
                "unit_instance_id": unit_instance_id,
                "request_id": request_id,
                "result_id": result_id,
                "removed_persisting_effects": [effect.to_payload() for effect in removed_effects],
                "phase_body_status": "hidden_status_lost",
            }
        ),
    )


def _apply_attack_sequence_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    stratagem_index: StratagemCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> LifecycleStatus | None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        attack_sequence, allocated_model_ids, status = _apply_attack_sequence_decision_to_sequence(
            state=state,
            result=result,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=out_of_phase_state.attack_sequence,
            already_allocated_model_ids=out_of_phase_state.allocated_model_ids,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
        state.replace_out_of_phase_shooting_state(
            out_of_phase_state.with_attack_sequence_update(
                attack_sequence=attack_sequence,
                allocated_model_ids=allocated_model_ids,
            )
        )
        return status
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.attack_sequence is None:
        raise GameLifecycleError("Attack sequence decision requires active attack_sequence.")
    attack_sequence, allocated_model_ids, status = _apply_attack_sequence_decision_to_sequence(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=shooting_state.attack_sequence,
        already_allocated_model_ids=shooting_state.allocated_model_ids_this_phase,
        stratagem_index=stratagem_index,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    state.replace_shooting_phase_state(
        shooting_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids,
        )
    )
    return status


def _apply_attack_sequence_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        state.replace_out_of_phase_shooting_state(
            out_of_phase_state.with_attack_sequence_update(
                attack_sequence=_apply_attack_sequence_selection_to_sequence(
                    attack_sequence=out_of_phase_state.attack_sequence,
                    result=result,
                    decisions=decisions,
                ),
                allocated_model_ids=out_of_phase_state.allocated_model_ids,
            )
        )
        return
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.attack_sequence is None:
        raise GameLifecycleError("Attack sequence selection requires active attack_sequence.")
    state.replace_shooting_phase_state(
        shooting_state.with_attack_sequence_update(
            attack_sequence=_apply_attack_sequence_selection_to_sequence(
                attack_sequence=shooting_state.attack_sequence,
                result=result,
                decisions=decisions,
            ),
            allocated_model_ids_this_phase=shooting_state.allocated_model_ids_this_phase,
        )
    )


def _apply_attack_sequence_selection_to_sequence(
    *,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    decisions: DecisionController,
) -> AttackSequence:
    if result.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        return apply_resolve_target_unit_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
    if result.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        return apply_attack_weapon_group_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
    raise GameLifecycleError("Unsupported attack sequence selection decision type.")


def _apply_attack_sequence_decision_to_sequence(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
    stratagem_index: StratagemCatalogIndex,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    updated_sequence: AttackSequence | None
    allocated_model_ids: tuple[str, ...]
    status: LifecycleStatus | None
    if result.decision_type == SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE:
        validate_psychic_attack_modifier_ignore_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
        updated_sequence = attack_sequence
        allocated_model_ids = already_allocated_model_ids
        status = None
    elif result.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_allocation_order_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    elif result.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_damage_allocation_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    elif result.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_precision_allocation_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            stratagem_index=stratagem_index,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    elif result.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    elif result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_destruction_reaction_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    elif (
        result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE
        and is_destroyed_transport_disembark_proposal_request(
            decisions.record_for_result(result).request
        )
    ):
        updated_sequence, allocated_model_ids, status = (
            apply_destroyed_transport_disembark_proposal_decision(
                state=state,
                decisions=decisions,
                ruleset_descriptor=ruleset_descriptor,
                attack_sequence=attack_sequence,
                result=result,
                already_allocated_model_ids=already_allocated_model_ids,
            )
        )
    else:
        raise GameLifecycleError("Unsupported attack sequence decision type.")
    return updated_sequence, allocated_model_ids, status
