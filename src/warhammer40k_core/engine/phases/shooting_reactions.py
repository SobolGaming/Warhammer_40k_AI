# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.shooting_imports import *
from warhammer40k_core.engine.phases.shooting_model import *
from warhammer40k_core.engine.phases.shooting_handler import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord, RangedAttackHistoryRecord
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
    from warhammer40k_core.engine.phases.shooting_model import SELECT_SHOOTING_UNIT_DECISION_TYPE, SELECT_SHOOTING_TYPE_DECISION_TYPE, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE, COMPLETE_SHOOTING_PHASE_OPTION_ID, _COMPLETE_SHOOTING_PHASE_STATUS, _default_stratagem_index, ShootingUnitSelectionPayload, ShootingTypeSelectionPayload, ShootingPhaseStatePayload, OutOfPhaseShootingStatePayload, ShootingDeclarationProposalRequestPayload, ShootingDeclarationDecisionPayload, _AvailableWeapon, _ShootingUnitCandidateCacheKey, _ShootingModelCandidateCacheKey, _ShootingModelCandidateCache, ShootingUnitSelection, ShootingTypeSelection, ShootingPhaseState, OutOfPhaseShootingState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler, invalid_shooting_phase_start_faction_rule_status, _shooting_phase_start_faction_rule_drift_reason, _request_shooting_phase_start_rule_if_available
    from warhammer40k_core.engine.phases.shooting_requests import _request_shooting_type_selection, _request_shooting_declaration, request_out_of_phase_shooting_declaration, _target_candidate_payload_for_request, _embedded_weapon_ability_request_prefix, _required_weapon_ability_selections_for_target, _shooting_types_for_candidate_payload, _shooting_types_for_selected_type, _shooting_types_for_selected_type_for_rules_unit
    from warhammer40k_core.engine.phases.shooting_unit_selection import _apply_shooting_unit_selection_decision, _apply_shooting_unit_selected_effect_grants, _request_shooting_unit_selected_grant_decision_if_available, _shooting_unit_selected_grant_options, _apply_shooting_unit_selected_grant_decision, _selected_shooting_unit_grants_from_payload, _validate_selected_shooting_unit_grants, _record_shooting_unit_selected_grant_effects, _shooting_unit_selected_context, _active_shooting_unit_selection, _validate_shooting_unit_selected_grant_payload_context, _shooting_unit_selected_grant_unit_effect_target_ids, _shooting_unit_selected_grant_effect_expiration
    from warhammer40k_core.engine.phases.shooting_decisions import _apply_shooting_dice_reroll_decision, _apply_shooting_type_selection_decision, _apply_shooting_declaration_decision, _apply_out_of_phase_shooting_declaration_decision, _record_ranged_attack_history_for_declaration, _record_one_shot_weapon_uses_for_attack_pools, apply_hidden_status_loss_after_ranged_attacks, _apply_attack_sequence_decision, _apply_attack_sequence_selection_decision, _apply_attack_sequence_selection_to_sequence, _apply_attack_sequence_decision_to_sequence
    from warhammer40k_core.engine.phases.shooting_declaration_validation import _validate_declaration_submission, _validate_out_of_phase_declaration_submission, _attack_pools_for_proposal, _AttackPoolValidationResult, _attack_pools_or_validation, _validate_duplicate_weapon_ability_selection, _shooting_candidate_with_target_restrictions, _modified_shooting_weapon_profile, _runtime_modifier_registry, _out_of_phase_allowed_target_unit_ids, _out_of_phase_uses_fire_overwatch, _forced_shooting_type_for_out_of_phase, _selected_shooting_type_for_declaration, _shooting_types_for_declaration_candidate, _targeting_rule_ids_with_shooting_type, _validate_model_pistol_exclusivity, _apply_phase13d_weapon_modifiers
    from warhammer40k_core.engine.phases.shooting_targeting import _target_within_half_weapon_range, _snap_shooting_type_allowed_for_unit_target, _declaration_target_within_max_range, _unit_target_within_max_range, _unit_placements_for_rules_unit_or_none, _rules_unit_remained_stationary, _heavy_hit_roll_modifier_applies, _rules_unit_set_up_this_turn, _rules_unit_within_enemy_engagement_range, _target_visible_to_friendly_unit, _declaration_source_unit
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_active_shooting_phase_stratagem_timing_window_id",
    "_attack_sequence_completed_event_id",
    "_complete_out_of_phase_shooting",
    "_destroyed_enemy_unit_ids_for_sequence",
    "_destroyed_target_unit_ids_for_sequence",
    "_eligible_triggered_movement_units_from_shooting_grants",
    "_enemy_unit_has_shot_timing_window_id",
    "_friendly_unit_has_shot_timing_window_id",
    "_request_active_shooting_phase_stratagem_if_available",
    "_request_after_unit_selected_as_target_stratagem_if_available",
    "_request_enemy_unit_has_shot_stratagem_if_available",
    "_request_friendly_unit_has_shot_stratagem_if_available",
    "_request_selected_to_shoot_stratagem_if_available",
    "_request_shooting_end_surge_if_available",
    "_resolve_completed_shooting_attack_sequence_continuation",
    "_selected_as_target_timing_window_id",
    "_selected_to_shoot_timing_window_id",
    "_shooting_end_surge_distance_roll_spec",
    "_shooting_end_surge_event_already_processed",
    "_shooting_end_surge_grant_distance_bonus",
    "_stratagem_used_for_context",
    "_successful_hit_target_unit_ids_for_sequence",
    "_target_unit_ids_for_attack_sequence",
)


def _complete_out_of_phase_shooting(
    *,
    state: GameState,
    decisions: DecisionController,
    completed_state: OutOfPhaseShootingState,
) -> LifecycleStatus:
    if type(completed_state) is not OutOfPhaseShootingState:
        raise GameLifecycleError("Out-of-phase shooting completion requires state.")
    if completed_state.attack_sequence is not None:
        raise GameLifecycleError("Out-of-phase shooting completion requires no sequence.")
    removed_grant_effects = (
        state.remove_persisting_effects_by_id(completed_state.grant_effect_ids)
        if completed_state.grant_effect_ids
        else ()
    )
    decisions.event_log.append(
        "out_of_phase_shooting_completed",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "player_id": completed_state.player_id,
            "parent_phase": completed_state.parent_phase.value,
            "source_rule_id": completed_state.source_rule_id,
            "selected_unit_instance_id": completed_state.selected_unit_instance_id,
            "removed_grant_effects": [effect.to_payload() for effect in removed_grant_effects],
        },
    )
    state.replace_out_of_phase_shooting_state(None)
    return LifecycleStatus.advanced(
        stage=GameLifecycleStage.BATTLE,
        payload={
            "phase": completed_state.parent_phase.value,
            "phase_body_status": "out_of_phase_shooting_complete",
            "source_rule_id": completed_state.source_rule_id,
        },
    )


def _request_active_shooting_phase_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_state: ShootingPhaseState,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(shooting_state) is not ShootingPhaseState:
        raise GameLifecycleError("Active shooting stratagem trigger requires shooting state.")
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=shooting_state.active_player_id,
        trigger_kind=TimingTriggerKind.DURING_PHASE,
        timing_window_id=_active_shooting_phase_stratagem_timing_window_id(shooting_state),
        trigger_payload={
            "selected_unit_instance_ids": list(shooting_state.selected_unit_ids),
            "shot_unit_instance_ids": list(shooting_state.shot_unit_ids),
            "skipped_unit_instance_ids": list(shooting_state.skipped_unit_ids),
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    if _stratagem_used_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "active_shooting_phase_stratagem_window_opened",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": shooting_state.active_player_id,
                "stratagem_context": context.to_payload(),
                "request_id": request.request_id,
                "phase_body_status": "active_shooting_phase_stratagem_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": shooting_state.active_player_id,
            "phase_body_status": "active_shooting_phase_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _request_selected_to_shoot_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_state: ShootingPhaseState,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(shooting_state) is not ShootingPhaseState:
        raise GameLifecycleError("Selected-to-shoot stratagem trigger requires shooting state.")
    selection = shooting_state.active_selection
    if selection is None:
        return None
    if shooting_state.selected_shooting_type is not None:
        return None
    trigger_payload = validate_json_value(
        {
            SELECTED_TO_SHOOT_UNIT_CONTEXT_KEY: selection.unit_instance_id,
            "selected_unit_instance_id": selection.unit_instance_id,
            "shooting_unit_selection": selection.to_payload(),
        }
    )
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=selection.player_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_SELECTED_TO_SHOOT,
        timing_window_id=_selected_to_shoot_timing_window_id(selection),
        trigger_payload=trigger_payload,
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    if _stratagem_used_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "selected_to_shoot_stratagem_window_opened",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "player_id": selection.player_id,
                "stratagem_context": context.to_payload(),
                "request_id": request.request_id,
                "phase_body_status": "selected_to_shoot_stratagem_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "player_id": selection.player_id,
            "phase_body_status": "selected_to_shoot_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _request_after_unit_selected_as_target_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    attack_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        SELECTED_TARGET_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Selected-as-target trigger requires an AttackSequence.")
    target_unit_ids = _target_unit_ids_for_attack_sequence(attack_sequence)
    if not target_unit_ids:
        return None
    attacking_player_id = attack_sequence.attacker_player_id
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != attacking_player_id
    ):
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=reacting_player_id,
            trigger_kind=TimingTriggerKind.AFTER_UNIT_SELECTED_AS_TARGET,
            timing_window_id=_selected_as_target_timing_window_id(
                sequence_id=attack_sequence.sequence_id,
                player_id=reacting_player_id,
            ),
            trigger_payload={
                SELECTED_TARGET_UNIT_CONTEXT_KEY: list(target_unit_ids),
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "attacking_player_id": attacking_player_id,
                "attack_sequence_id": attack_sequence.sequence_id,
            },
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        if _stratagem_used_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if not options:
            continue
        request = create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "unit_selected_as_target_stratagem_window_opened",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "player_id": reacting_player_id,
                    "attacking_player_id": attacking_player_id,
                    "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                    "selected_target_unit_instance_ids": list(target_unit_ids),
                    "attack_sequence_id": attack_sequence.sequence_id,
                    "stratagem_context": context.to_payload(),
                    "request_id": request.request_id,
                    "phase_body_status": "unit_selected_as_target_stratagem_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": reacting_player_id,
                "attacking_unit_instance_id": attack_sequence.attacking_unit_instance_id,
                "phase_body_status": "unit_selected_as_target_stratagem_pending",
                "pending_request_id": request.request_id,
            },
        )
    return None


def _resolve_completed_shooting_attack_sequence_continuation(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    if type(handler) is not ShootingPhaseHandler:
        raise GameLifecycleError("Completed shooting continuation requires a handler.")
    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Completed shooting continuation requires an AttackSequence.")
    completed_event_id = attack_sequence_completed_event_id(
        decisions=decisions,
        attack_sequence=completed_sequence,
    )
    completion_hook_status = handler.attack_sequence_completed_hooks.resolve_completed_sequence(
        AttackSequenceCompletedContext(
            state=state,
            decisions=decisions,
            dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
            runtime_modifier_registry=handler.runtime_modifier_registry,
            source_phase=BattlePhase.SHOOTING,
            attack_sequence=completed_sequence,
            attack_sequence_completed_event_id=completed_event_id,
        )
    )
    if completion_hook_status is not None:
        return completion_hook_status
    stratagem_status = _request_friendly_unit_has_shot_stratagem_if_available(
        state=state,
        decisions=decisions,
        stratagem_index=handler.stratagem_index,
        stratagem_cost_modifier_registry=handler.stratagem_cost_modifier_registry,
        completed_sequence=completed_sequence,
    )
    if stratagem_status is not None:
        return stratagem_status
    enemy_stratagem_status = _request_enemy_unit_has_shot_stratagem_if_available(
        state=state,
        decisions=decisions,
        stratagem_index=handler.stratagem_index,
        stratagem_cost_modifier_registry=handler.stratagem_cost_modifier_registry,
        completed_sequence=completed_sequence,
    )
    if enemy_stratagem_status is not None:
        return enemy_stratagem_status
    return _request_shooting_end_surge_if_available(
        state=state,
        decisions=decisions,
        registry=handler.shooting_end_surge_hooks,
        completed_sequence=completed_sequence,
    )


def _request_friendly_unit_has_shot_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
        DESTROYED_TARGET_UNIT_CONTEXT_KEY,
        HIT_TARGET_UNIT_CONTEXT_KEY,
        JUST_SHOT_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Friendly-unit-has-shot trigger requires an AttackSequence.")
    completed_event_id = _attack_sequence_completed_event_id(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if completed_event_id is None:
        raise GameLifecycleError("Completed shooting sequence missing completion event.")
    context = StratagemEligibilityContext.from_state(
        state=state,
        player_id=completed_sequence.attacker_player_id,
        trigger_kind=TimingTriggerKind.JUST_AFTER_FRIENDLY_UNIT_HAS_SHOT,
        timing_window_id=_friendly_unit_has_shot_timing_window_id(completed_event_id),
        trigger_payload={
            JUST_SHOT_UNIT_CONTEXT_KEY: completed_sequence.attacking_unit_instance_id,
            HIT_TARGET_UNIT_CONTEXT_KEY: list(
                _successful_hit_target_unit_ids_for_sequence(
                    decisions=decisions,
                    sequence=completed_sequence,
                )
            ),
            DESTROYED_TARGET_UNIT_CONTEXT_KEY: list(
                _destroyed_target_unit_ids_for_sequence(
                    decisions=decisions,
                    sequence=completed_sequence,
                )
            ),
            DESTROYED_ENEMY_UNIT_CONTEXT_KEY: list(
                _destroyed_enemy_unit_ids_for_sequence(
                    state=state,
                    decisions=decisions,
                    sequence=completed_sequence,
                )
            ),
            "attack_sequence_id": completed_sequence.sequence_id,
            "attack_sequence_completed_event_id": completed_event_id,
        },
    )
    if stratagem_window_declined_for_context(decisions=decisions, context=context):
        return None
    if _stratagem_used_for_context(decisions=decisions, context=context):
        return None
    options = stratagem_use_options_from_index(
        state=state,
        index=stratagem_index,
        context=context,
        stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
    )
    if not options:
        return None
    request = create_stratagem_use_decision_request(
        state=state,
        context=context,
        options=(*options, stratagem_decline_option()),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "friendly_unit_has_shot_stratagem_window_opened",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": state.active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "player_id": completed_sequence.attacker_player_id,
            "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
            "attack_sequence_id": completed_sequence.sequence_id,
            "trigger_event_id": completed_event_id,
            "stratagem_context": context.to_payload(),
            "request_id": request.request_id,
            "phase_body_status": "friendly_unit_has_shot_stratagem_pending",
        },
    )
    return LifecycleStatus.waiting_for_decision(
        stage=state.stage,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": _active_player_id(state),
            "player_id": completed_sequence.attacker_player_id,
            "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
            "phase_body_status": "friendly_unit_has_shot_stratagem_pending",
            "pending_request_id": request.request_id,
        },
    )


def _request_enemy_unit_has_shot_stratagem_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    stratagem_index: StratagemCatalogIndex,
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.stratagems import (
        DESTROYED_ENEMY_UNIT_CONTEXT_KEY,
        DESTROYED_TARGET_UNIT_CONTEXT_KEY,
        HIT_TARGET_UNIT_CONTEXT_KEY,
        JUST_SHOT_UNIT_CONTEXT_KEY,
        StratagemEligibilityContext,
        create_stratagem_use_decision_request,
        stratagem_decline_option,
        stratagem_use_options_from_index,
        stratagem_window_declined_for_context,
    )
    from warhammer40k_core.engine.timing_windows import TimingTriggerKind

    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Enemy-unit-has-shot trigger requires an AttackSequence.")
    completed_event_id = _attack_sequence_completed_event_id(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if completed_event_id is None:
        raise GameLifecycleError("Completed shooting sequence missing completion event.")
    shooting_player_id = completed_sequence.attacker_player_id
    hit_target_ids = _successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=completed_sequence,
    )
    destroyed_target_ids = _destroyed_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=completed_sequence,
    )
    destroyed_enemy_unit_ids = _destroyed_enemy_unit_ids_for_sequence(
        state=state,
        decisions=decisions,
        sequence=completed_sequence,
    )
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != shooting_player_id
    ):
        context = StratagemEligibilityContext.from_state(
            state=state,
            player_id=reacting_player_id,
            trigger_kind=TimingTriggerKind.JUST_AFTER_ENEMY_UNIT_HAS_SHOT,
            timing_window_id=_enemy_unit_has_shot_timing_window_id(
                trigger_event_id=completed_event_id,
                player_id=reacting_player_id,
            ),
            trigger_payload={
                JUST_SHOT_UNIT_CONTEXT_KEY: completed_sequence.attacking_unit_instance_id,
                HIT_TARGET_UNIT_CONTEXT_KEY: list(hit_target_ids),
                DESTROYED_TARGET_UNIT_CONTEXT_KEY: list(destroyed_target_ids),
                DESTROYED_ENEMY_UNIT_CONTEXT_KEY: list(destroyed_enemy_unit_ids),
                "shooting_player_id": shooting_player_id,
                "attack_sequence_id": completed_sequence.sequence_id,
                "attack_sequence_completed_event_id": completed_event_id,
            },
        )
        if stratagem_window_declined_for_context(decisions=decisions, context=context):
            continue
        if _stratagem_used_for_context(decisions=decisions, context=context):
            continue
        options = stratagem_use_options_from_index(
            state=state,
            index=stratagem_index,
            context=context,
            stratagem_cost_modifier_registry=stratagem_cost_modifier_registry,
        )
        if not options:
            continue
        request = create_stratagem_use_decision_request(
            state=state,
            context=context,
            options=(*options, stratagem_decline_option()),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "enemy_unit_has_shot_stratagem_window_opened",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "player_id": reacting_player_id,
                    "shooting_player_id": shooting_player_id,
                    "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                    "attack_sequence_id": completed_sequence.sequence_id,
                    "trigger_event_id": completed_event_id,
                    "stratagem_context": context.to_payload(),
                    "request_id": request.request_id,
                    "phase_body_status": "enemy_unit_has_shot_stratagem_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "player_id": reacting_player_id,
                "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                "phase_body_status": "enemy_unit_has_shot_stratagem_pending",
                "pending_request_id": request.request_id,
            },
        )
    return None


def _request_shooting_end_surge_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    registry: ShootingEndSurgeHookRegistry,
    completed_sequence: AttackSequence,
) -> LifecycleStatus | None:
    if type(registry) is not ShootingEndSurgeHookRegistry:
        raise GameLifecycleError("Shooting-end surge trigger requires a registry.")
    if type(completed_sequence) is not AttackSequence:
        raise GameLifecycleError("Shooting-end surge trigger requires an AttackSequence.")
    if not registry.all_bindings():
        return None
    completed_event_id = _attack_sequence_completed_event_id(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if completed_event_id is None:
        raise GameLifecycleError("Completed shooting sequence missing completion event.")
    if _shooting_end_surge_event_already_processed(
        decisions=decisions,
        trigger_event_id=completed_event_id,
    ):
        return None
    hit_target_ids = _successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=completed_sequence,
    )
    if not hit_target_ids:
        return None
    shooting_player_id = completed_sequence.attacker_player_id
    for reacting_player_id in sorted(
        player_id for player_id in state.player_ids if player_id != shooting_player_id
    ):
        context = ShootingEndSurgeContext(
            state=state,
            shooting_unit_instance_id=completed_sequence.attacking_unit_instance_id,
            shooting_player_id=shooting_player_id,
            reacting_player_id=reacting_player_id,
            trigger_event_id=completed_event_id,
            hit_target_unit_instance_ids=hit_target_ids,
        )
        grants = registry.grants_for(context)
        if not grants:
            continue
        max_distance_bonus_inches = _shooting_end_surge_grant_distance_bonus(grants)
        roll_state = DiceRollManager(state.game_id, event_log=decisions.event_log).roll(
            _shooting_end_surge_distance_roll_spec(
                source_rule_id=grants[0].source_id,
                player_id=reacting_player_id,
                shooting_unit_instance_id=completed_sequence.attacking_unit_instance_id,
                trigger_event_id=completed_event_id,
            )
        )
        descriptor = TriggeredMovementDescriptor(
            movement_kind=TriggeredMovementKind.SURGE,
            source_rule_id=grants[0].source_id,
            trigger_timing=TriggeredReactionWindow(
                phase=BattlePhase.SHOOTING,
                window_kind=ReactionWindowKind.RULE_TRIGGER,
                source_step="just_after_enemy_unit_has_shot",
                source_event_id=completed_event_id,
            ),
            max_distance_inches=float(roll_state.current_total + max_distance_bonus_inches),
            movement_mode=MovementMode.NORMAL,
            allow_battle_shocked=False,
            allow_within_engagement_range=False,
            one_per_phase=True,
            optional=True,
        )
        request = triggered_movement_unit_selection_request(
            state=state,
            player_id=reacting_player_id,
            descriptor=descriptor,
            eligible_units=_eligible_triggered_movement_units_from_shooting_grants(
                grants=grants,
                roll_state=roll_state,
                distance_bonus_inches=max_distance_bonus_inches,
            ),
        )
        decisions.request_decision(request)
        decisions.event_log.append(
            "shooting_end_surge_triggered",
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "shooting_player_id": shooting_player_id,
                    "reacting_player_id": reacting_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                    "trigger_event_id": completed_event_id,
                    "hit_target_unit_instance_ids": list(hit_target_ids),
                    "surge_distance_roll": roll_state.to_payload(),
                    "max_distance_bonus_inches": max_distance_bonus_inches,
                    "descriptor": descriptor.to_payload(),
                    "grants": [grant.to_payload() for grant in grants],
                    "request_id": request.request_id,
                    "phase_body_status": "shooting_end_surge_pending",
                }
            ),
        )
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "reacting_player_id": reacting_player_id,
                "shooting_unit_instance_id": completed_sequence.attacking_unit_instance_id,
                "decision_type": request.decision_type,
                "phase_body_status": "shooting_end_surge_pending",
            },
        )
    return None


def _eligible_triggered_movement_units_from_shooting_grants(
    *,
    grants: tuple[ShootingEndSurgeGrant, ...],
    roll_state: DiceRollState,
    distance_bonus_inches: int,
) -> tuple[TriggeredMovementEligibleUnit, ...]:
    return tuple(
        TriggeredMovementEligibleUnit(
            unit_instance_id=grant.unit_instance_id,
            hook_id=grant.hook_id,
            source_id=grant.source_id,
            replay_payload=grant.replay_payload,
            decision_effect_payload=grant.decision_effect_payload,
            distance_roll_state=(
                roll_state if grant.distance_reroll_permission is not None else None
            ),
            distance_roll_bonus_inches=(
                distance_bonus_inches if grant.distance_reroll_permission is not None else 0
            ),
            distance_reroll_permission=grant.distance_reroll_permission,
        )
        for grant in grants
    )


def _shooting_end_surge_grant_distance_bonus(
    grants: tuple[ShootingEndSurgeGrant, ...],
) -> int:
    if type(grants) is not tuple:
        raise GameLifecycleError("Shooting-end surge distance bonus requires grant tuple.")
    for grant in grants:
        if type(grant) is not ShootingEndSurgeGrant:
            raise GameLifecycleError(
                "Shooting-end surge distance bonus requires ShootingEndSurgeGrant values."
            )
    bonuses = {grant.max_distance_bonus_inches for grant in grants}
    if len(bonuses) != 1:
        raise GameLifecycleError("Shooting-end surge grants must share one distance bonus.")
    return bonuses.pop()


def _shooting_end_surge_distance_roll_spec(
    *,
    source_rule_id: str,
    player_id: str,
    shooting_unit_instance_id: str,
    trigger_event_id: str,
) -> DiceRollSpec:
    return DiceRollSpec(
        expression=DiceExpression(quantity=1, sides=6),
        reason=(
            "Shooting-end surge distance "
            f"{source_rule_id} for {shooting_unit_instance_id} from {trigger_event_id}"
        ),
        roll_type="shooting_end_surge.distance",
        actor_id=player_id,
    )


def _attack_sequence_completed_event_id(
    *,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> str | None:
    for record in reversed(decisions.event_log.records):
        if record.event_type != "attack_sequence_completed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("sequence_id") == sequence.sequence_id:
            return record.event_id
    return None


def _friendly_unit_has_shot_timing_window_id(trigger_event_id: str) -> str:
    return f"friendly-unit-has-shot:{_validate_identifier('trigger_event_id', trigger_event_id)}"


def _active_shooting_phase_stratagem_timing_window_id(
    shooting_state: ShootingPhaseState,
) -> str:
    if type(shooting_state) is not ShootingPhaseState:
        raise GameLifecycleError("Active shooting stratagem timing requires shooting state.")
    return (
        f"active-shooting-stratagem:round-{shooting_state.battle_round}:"
        f"player-{shooting_state.active_player_id}:selected-{len(shooting_state.selected_unit_ids)}:"
        f"shot-{len(shooting_state.shot_unit_ids)}:skipped-{len(shooting_state.skipped_unit_ids)}"
    )


def _selected_to_shoot_timing_window_id(selection: ShootingUnitSelection) -> str:
    if type(selection) is not ShootingUnitSelection:
        raise GameLifecycleError("Selected-to-shoot timing requires shooting unit selection.")
    return (
        f"selected-to-shoot:round-{selection.battle_round}:"
        f"player-{selection.player_id}:unit-{selection.unit_instance_id}:"
        f"request-{selection.request_id}:result-{selection.result_id}"
    )


def _selected_as_target_timing_window_id(*, sequence_id: str, player_id: str) -> str:
    return (
        "selected-as-target:"
        f"{_validate_identifier('sequence_id', sequence_id)}:"
        f"player-{_validate_identifier('player_id', player_id)}"
    )


def _enemy_unit_has_shot_timing_window_id(*, trigger_event_id: str, player_id: str) -> str:
    return (
        "enemy-unit-has-shot:"
        f"{_validate_identifier('trigger_event_id', trigger_event_id)}:"
        f"player-{_validate_identifier('player_id', player_id)}"
    )


def _target_unit_ids_for_attack_sequence(attack_sequence: AttackSequence) -> tuple[str, ...]:
    if type(attack_sequence) is not AttackSequence:
        raise GameLifecycleError("Attack sequence target ids require an AttackSequence.")
    return tuple(sorted({pool.target_unit_instance_id for pool in attack_sequence.attack_pools}))


def _stratagem_used_for_context(
    *,
    decisions: DecisionController,
    context: StratagemEligibilityContext,
) -> bool:
    context_payload = context.to_payload()
    for record in decisions.event_log.records:
        if record.event_type != "stratagem_used":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Stratagem use event payload must be an object.")
        payload_object = cast(dict[str, object], payload)
        if (
            payload_object.get("game_id") == context_payload.get("game_id")
            and payload_object.get("player_id") == context_payload.get("player_id")
            and payload_object.get("battle_round") == context_payload.get("battle_round")
            and payload_object.get("phase") == context_payload.get("phase")
            and payload_object.get("active_player_id") == context_payload.get("active_player_id")
            and payload_object.get("timing_window_id") == context_payload.get("timing_window_id")
        ):
            return True
    return False


def _successful_hit_target_unit_ids_for_sequence(
    *,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[str, ...]:
    return successful_hit_target_unit_ids_for_sequence(
        decisions=decisions,
        sequence=sequence,
    )


def _destroyed_target_unit_ids_for_sequence(
    *,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[str, ...]:
    target_ids: set[str] = set()
    for record in decisions.event_log.records:
        if record.event_type != "model_destroyed":
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Model destroyed payload must be an object.")
        if payload.get("sequence_id") != sequence.sequence_id:
            continue
        target_unit_id = payload.get("target_unit_instance_id")
        if type(target_unit_id) is not str:
            raise GameLifecycleError("Model destroyed payload requires target unit id.")
        target_ids.add(_validate_identifier("target_unit_instance_id", target_unit_id))
    return tuple(sorted(target_ids))


def _destroyed_enemy_unit_ids_for_sequence(
    *,
    state: GameState,
    decisions: DecisionController,
    sequence: AttackSequence,
) -> tuple[str, ...]:
    return tuple(
        unit_id
        for unit_id in _destroyed_target_unit_ids_for_sequence(
            decisions=decisions,
            sequence=sequence,
        )
        if not rules_unit_view_by_id(state=state, unit_instance_id=unit_id).alive_models()
    )


def _shooting_end_surge_event_already_processed(
    *,
    decisions: DecisionController,
    trigger_event_id: str,
) -> bool:
    requested_event_id = _validate_identifier("trigger_event_id", trigger_event_id)
    for record in decisions.event_log.records:
        if record.event_type not in {
            "shooting_end_surge_triggered",
            "triggered_movement_declined",
            "triggered_movement_unit_selected",
            "triggered_movement_resolved",
        }:
            continue
        payload = record.payload
        if not isinstance(payload, dict):
            continue
        if payload.get("trigger_event_id") == requested_event_id:
            return True
        trigger_timing = payload.get("trigger_timing")
        if isinstance(trigger_timing, dict) and trigger_timing.get("source_event_id") == (
            requested_event_id
        ):
            return True
    return False
