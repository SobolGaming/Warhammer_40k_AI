# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.shooting_imports import *
from warhammer40k_core.engine.phases.shooting_model import *
from warhammer40k_core.engine.phases.shooting_handler import *
from warhammer40k_core.engine.phases.shooting_reactions import *
from warhammer40k_core.engine.phases.shooting_requests import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord, RangedAttackHistoryRecord
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
    from warhammer40k_core.engine.phases.shooting_model import SELECT_SHOOTING_UNIT_DECISION_TYPE, SELECT_SHOOTING_TYPE_DECISION_TYPE, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE, COMPLETE_SHOOTING_PHASE_OPTION_ID, _COMPLETE_SHOOTING_PHASE_STATUS, _default_stratagem_index, ShootingUnitSelectionPayload, ShootingTypeSelectionPayload, ShootingPhaseStatePayload, OutOfPhaseShootingStatePayload, ShootingDeclarationProposalRequestPayload, ShootingDeclarationDecisionPayload, _AvailableWeapon, _ShootingUnitCandidateCacheKey, _ShootingModelCandidateCacheKey, _ShootingModelCandidateCache, ShootingUnitSelection, ShootingTypeSelection, ShootingPhaseState, OutOfPhaseShootingState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler, invalid_shooting_phase_start_faction_rule_status, _shooting_phase_start_faction_rule_drift_reason, _request_shooting_phase_start_rule_if_available
    from warhammer40k_core.engine.phases.shooting_reactions import _complete_out_of_phase_shooting, _request_active_shooting_phase_stratagem_if_available, _request_after_unit_selected_as_target_stratagem_if_available, _resolve_completed_shooting_attack_sequence_continuation, _request_friendly_unit_has_shot_stratagem_if_available, _request_enemy_unit_has_shot_stratagem_if_available, _request_shooting_end_surge_if_available, _eligible_triggered_movement_units_from_shooting_grants, _shooting_end_surge_grant_distance_bonus, _shooting_end_surge_distance_roll_spec, _attack_sequence_completed_event_id, _friendly_unit_has_shot_timing_window_id, _active_shooting_phase_stratagem_timing_window_id, _selected_as_target_timing_window_id, _enemy_unit_has_shot_timing_window_id, _target_unit_ids_for_attack_sequence, _stratagem_used_for_context, _successful_hit_target_unit_ids_for_sequence, _destroyed_target_unit_ids_for_sequence, _destroyed_enemy_unit_ids_for_sequence, _shooting_end_surge_event_already_processed
    from warhammer40k_core.engine.phases.shooting_requests import _request_shooting_type_selection, _request_shooting_declaration, request_out_of_phase_shooting_declaration, _target_candidate_payload_for_request, _embedded_weapon_ability_request_prefix, _required_weapon_ability_selections_for_target, _shooting_types_for_candidate_payload, _shooting_types_for_selected_type, _shooting_types_for_selected_type_for_rules_unit
    from warhammer40k_core.engine.phases.shooting_decisions import _apply_shooting_dice_reroll_decision, _apply_shooting_type_selection_decision, _apply_shooting_declaration_decision, _apply_out_of_phase_shooting_declaration_decision, _record_ranged_attack_history_for_declaration, _record_one_shot_weapon_uses_for_attack_pools, apply_hidden_status_loss_after_ranged_attacks, _apply_attack_sequence_decision, _apply_attack_sequence_selection_decision, _apply_attack_sequence_selection_to_sequence, _apply_attack_sequence_decision_to_sequence
    from warhammer40k_core.engine.phases.shooting_declaration_validation import _validate_declaration_submission, _validate_out_of_phase_declaration_submission, _attack_pools_for_proposal, _AttackPoolValidationResult, _attack_pools_or_validation, _validate_duplicate_weapon_ability_selection, _shooting_candidate_with_target_restrictions, _modified_shooting_weapon_profile, _runtime_modifier_registry, _out_of_phase_allowed_target_unit_ids, _out_of_phase_uses_fire_overwatch, _forced_shooting_type_for_out_of_phase, _selected_shooting_type_for_declaration, _shooting_types_for_declaration_candidate, _targeting_rule_ids_with_shooting_type, _validate_model_pistol_exclusivity, _apply_phase13d_weapon_modifiers
    from warhammer40k_core.engine.phases.shooting_targeting import _target_within_half_weapon_range, _snap_shooting_type_allowed_for_unit_target, _declaration_target_within_max_range, _unit_target_within_max_range, _unit_placements_for_rules_unit_or_none, _rules_unit_remained_stationary, _heavy_hit_roll_modifier_applies, _rules_unit_set_up_this_turn, _rules_unit_within_enemy_engagement_range, _target_visible_to_friendly_unit, _declaration_source_unit
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_active_shooting_unit_selection",
    "_apply_shooting_unit_selected_effect_grants",
    "_apply_shooting_unit_selected_grant_decision",
    "_apply_shooting_unit_selection_decision",
    "_record_shooting_unit_selected_grant_effects",
    "_request_shooting_unit_selected_grant_decision_if_available",
    "_selected_shooting_unit_grants_from_payload",
    "_shooting_unit_selected_context",
    "_shooting_unit_selected_grant_effect_expiration",
    "_shooting_unit_selected_grant_options",
    "_shooting_unit_selected_grant_unit_effect_target_ids",
    "_validate_selected_shooting_unit_grants",
    "_validate_shooting_unit_selected_grant_payload_context",
)


def _apply_shooting_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_unit_selected_hooks: ShootingUnitSelectedHookRegistry,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
) -> LifecycleStatus | None:
    _validate_shooting_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Shooting unit selection actor must be the active player.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Shooting unit selection requires shooting_phase_state.")
    if result.selected_option_id == COMPLETE_SHOOTING_PHASE_OPTION_ID:
        skipped_unit_ids = _legal_shooting_unit_ids(
            state=state,
            shooting_state=shooting_state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        )
        state.replace_shooting_phase_state(
            shooting_state.with_phase_complete(skipped_unit_ids=skipped_unit_ids)
        )
        decisions.event_log.append(
            "shooting_phase_completion_declared",
            _shooting_phase_status_payload(
                state=state,
                phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                skipped_unit_ids=skipped_unit_ids,
            ),
        )
        return None

    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    legal_unit_ids = _legal_shooting_unit_ids(
        state=state,
        shooting_state=shooting_state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    if unit_instance_id not in legal_unit_ids:
        raise GameLifecycleError("Shooting unit selection is not currently legal.")
    selection = ShootingUnitSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.replace_shooting_phase_state(shooting_state.with_unit_selection(selection))
    decisions.event_log.append(
        "shooting_unit_selected",
        {
            "game_id": state.game_id,
            "battle_round": state.battle_round,
            "active_player_id": active_player_id,
            "phase": BattlePhase.SHOOTING.value,
            "unit_instance_id": unit_instance_id,
            "request_id": result.request_id,
            "result_id": result.result_id,
            "phase_body_status": "unit_selected",
        },
    )
    _apply_shooting_unit_selected_effect_grants(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=shooting_unit_selected_hooks,
    )
    return _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=shooting_unit_selected_grant_hooks,
    )


def _apply_shooting_unit_selected_effect_grants(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    registry: ShootingUnitSelectedHookRegistry,
) -> None:
    if type(registry) is not ShootingUnitSelectedHookRegistry:
        raise GameLifecycleError("Shooting-unit-selected effect grants require a registry.")
    context = ShootingUnitSelectedContext(
        state=state,
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        request_id=selection.request_id,
        result_id=selection.result_id,
    )
    for grant in registry.grants_for(context):
        state.record_persisting_effect(grant.persisting_effect)
        decisions.event_log.append(
            grant.event_type,
            validate_json_value(
                {
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "active_player_id": state.active_player_id,
                    "phase": BattlePhase.SHOOTING.value,
                    "player_id": selection.player_id,
                    "shooting_unit_instance_id": selection.unit_instance_id,
                    "request_id": selection.request_id,
                    "result_id": selection.result_id,
                    "grant": grant.to_payload(),
                    "persisting_effect": grant.persisting_effect.to_payload(),
                }
            ),
        )


def _request_shooting_unit_selected_grant_decision_if_available(
    *,
    state: GameState,
    decisions: DecisionController,
    selection: ShootingUnitSelection,
    registry: ShootingUnitSelectedGrantRegistry,
) -> LifecycleStatus | None:
    if type(registry) is not ShootingUnitSelectedGrantRegistry:
        raise GameLifecycleError("Shooting-unit-selected grants require a registry.")
    context = _shooting_unit_selected_context(state=state, selection=selection)
    grants = registry.grants_for(context)
    if not grants:
        return None
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
        actor_id=selection.player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "source_decision_request_id": selection.request_id,
                "source_decision_result_id": selection.result_id,
                "available_shooting_unit_grants": [grant.to_payload() for grant in grants],
            }
        ),
        options=_shooting_unit_selected_grant_options(selection=selection, grants=grants),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_unit_selected_grant_decision_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": selection.request_id,
                "source_decision_result_id": selection.result_id,
                "available_shooting_unit_grants": [grant.to_payload() for grant in grants],
                "phase_body_status": "shooting_unit_selected_grant_decision_pending",
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "phase_body_status": "shooting_unit_selected_grant_decision_pending",
            "battle_round": state.battle_round,
            "active_player_id": selection.player_id,
            "unit_instance_id": selection.unit_instance_id,
            "decision_type": request.decision_type,
        },
    )


def _shooting_unit_selected_grant_options(
    *,
    selection: ShootingUnitSelection,
    grants: tuple[ShootingUnitSelectedGrant, ...],
) -> tuple[DecisionOption, ...]:
    options = [
        DecisionOption(
            option_id=DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID,
            label="Decline Shooting Unit Grant",
            payload=validate_json_value(
                {
                    "submission_kind": SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
                    "unit_instance_id": selection.unit_instance_id,
                    "source_decision_request_id": selection.request_id,
                    "source_decision_result_id": selection.result_id,
                    "selected_shooting_unit_grants": [],
                }
            ),
        )
    ]
    for grant in grants:
        options.append(
            DecisionOption(
                option_id=grant.hook_id,
                label=grant.label,
                payload=validate_json_value(
                    {
                        "submission_kind": SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE,
                        "unit_instance_id": selection.unit_instance_id,
                        "source_decision_request_id": selection.request_id,
                        "source_decision_result_id": selection.result_id,
                        "selected_shooting_unit_grants": [grant.to_payload()],
                    }
                ),
            )
        )
    return tuple(options)


def _apply_shooting_unit_selected_grant_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    registry: ShootingUnitSelectedGrantRegistry,
    ruleset_descriptor: RulesetDescriptor | None = None,
    army_catalog: ArmyCatalog | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus | None:
    selection = _active_shooting_unit_selection(state)
    if state.out_of_phase_shooting_state is None:
        _validate_shooting_phase_state(state)
    if result.actor_id != selection.player_id:
        raise GameLifecycleError("Shooting unit grant actor must be the selected unit player.")
    payload = _decision_payload_object(result.payload)
    _validate_shooting_unit_selected_grant_payload_context(payload=payload, selection=selection)
    if result.selected_option_id == DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID:
        selected_grants: tuple[ShootingUnitSelectedGrant, ...] = ()
    else:
        selected_grants = _selected_shooting_unit_grants_from_payload(payload)
        _validate_selected_shooting_unit_grants(
            state=state,
            selection=selection,
            registry=registry,
            selected_grants=selected_grants,
        )
    persisting_effects = tuple(
        effect
        for grant in selected_grants
        for effect in _record_shooting_unit_selected_grant_effects(
            state=state,
            result=result,
            selection=selection,
            grant=grant,
        )
    )
    decisions.event_log.append(
        "shooting_unit_selected_grant_decision_resolved",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": selection.player_id,
                "unit_instance_id": selection.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "selected_option_id": result.selected_option_id,
                "selected_shooting_unit_grants": [grant.to_payload() for grant in selected_grants],
                "persisting_effects": [effect.to_payload() for effect in persisting_effects],
                "phase_body_status": "shooting_unit_selected_grant_decision_resolved",
            }
        ),
    )
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and out_of_phase_state.selected_unit_instance_id == selection.unit_instance_id
        and not out_of_phase_state.attack_pools
        and out_of_phase_state.attack_sequence is None
    ):
        state.replace_out_of_phase_shooting_state(
            out_of_phase_state.with_grant_effect_ids(
                tuple(effect.effect_id for effect in persisting_effects)
            )
        )
        if ruleset_descriptor is None or army_catalog is None:
            return None
        return _request_shooting_declaration(
            state=state,
            decisions=decisions,
            active_selection=selection,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            phase=out_of_phase_state.parent_phase,
            request_context=validate_json_value(
                {
                    "request_kind": "out_of_phase_shooting",
                    "source_rule_id": out_of_phase_state.source_rule_id,
                    "source_context": out_of_phase_state.source_context,
                }
            ),
            target_unit_ids=out_of_phase_state.target_unit_ids,
            forced_shooting_type=(
                ShootingType.SNAP
                if out_of_phase_state.source_rule_id == FIRE_OVERWATCH_RULE_ID
                else None
            ),
            shooting_target_restriction_hooks=(
                ShootingTargetRestrictionHookRegistry.empty()
                if shooting_target_restriction_hooks is None
                else shooting_target_restriction_hooks
            ),
        )
    return None


def _selected_shooting_unit_grants_from_payload(
    payload: dict[str, object],
) -> tuple[ShootingUnitSelectedGrant, ...]:
    raw_grants = payload.get("selected_shooting_unit_grants")
    if not isinstance(raw_grants, list):
        raise GameLifecycleError("Shooting unit grant payload missing selected grants.")
    raw_grant_payloads = cast(list[object], raw_grants)
    grants: list[ShootingUnitSelectedGrant] = []
    for raw_grant in raw_grant_payloads:
        if not isinstance(raw_grant, dict):
            raise GameLifecycleError("Shooting unit selected grants must be objects.")
        grants.append(
            ShootingUnitSelectedGrant.from_payload(
                cast(ShootingUnitSelectedGrantPayload, raw_grant)
            )
        )
    return tuple(sorted(grants, key=lambda grant: grant.hook_id))


def _validate_selected_shooting_unit_grants(
    *,
    state: GameState,
    selection: ShootingUnitSelection,
    registry: ShootingUnitSelectedGrantRegistry,
    selected_grants: tuple[ShootingUnitSelectedGrant, ...],
) -> None:
    if not selected_grants:
        raise GameLifecycleError("Shooting unit grant selection requires a selected grant.")
    available_payloads = {
        grant.hook_id: grant.to_payload()
        for grant in registry.grants_for(
            _shooting_unit_selected_context(state=state, selection=selection)
        )
    }
    for grant in selected_grants:
        expected = available_payloads.get(grant.hook_id)
        if expected is None:
            raise GameLifecycleError("Selected shooting unit grant is not available.")
        if grant.to_payload() != expected:
            raise GameLifecycleError("Selected shooting unit grant payload drift.")


def _record_shooting_unit_selected_grant_effects(
    *,
    state: GameState,
    result: DecisionResult,
    selection: ShootingUnitSelection,
    grant: ShootingUnitSelectedGrant,
) -> tuple[PersistingEffect, ...]:
    effects: list[PersistingEffect] = []
    if grant.decision_effect_payload is not None:
        resource_spend_result = apply_faction_resource_spend_effect(
            state=state,
            player_id=selection.player_id,
            source_id=f"{grant.source_id}:{result.request_id}:{result.result_id}:spend",
            effect_payload=grant.decision_effect_payload,
        )
        spend_effect = PersistingEffect(
            effect_id=f"{result.result_id}:{grant.hook_id}:decision",
            source_rule_id=grant.source_id,
            owner_player_id=selection.player_id,
            target_unit_instance_ids=(selection.unit_instance_id,),
            started_battle_round=state.battle_round,
            started_phase=BattlePhaseKind.SHOOTING,
            expiration=EffectExpiration.end_battle_round(battle_round=state.battle_round),
            effect_payload=faction_resource_result_enriched_payload(
                effect_payload=grant.decision_effect_payload,
                result=resource_spend_result,
            ),
        )
        state.record_persisting_effect(spend_effect)
        effects.append(spend_effect)
    if grant.unit_effect_payload is None:
        if not effects:
            raise GameLifecycleError("Shooting unit selected grant has no effect to record.")
        return tuple(effects)
    unit_effect = PersistingEffect(
        effect_id=f"{result.result_id}:{grant.hook_id}:unit",
        source_rule_id=grant.source_id,
        owner_player_id=selection.player_id,
        target_unit_instance_ids=_shooting_unit_selected_grant_unit_effect_target_ids(
            unit_instance_id=selection.unit_instance_id,
            effect_payload=grant.unit_effect_payload,
        ),
        started_battle_round=state.battle_round,
        started_phase=BattlePhaseKind.SHOOTING,
        expiration=_shooting_unit_selected_grant_effect_expiration(
            state=state,
            selection=selection,
            grant=grant,
        ),
        effect_payload=grant.unit_effect_payload,
    )
    state.record_persisting_effect(unit_effect)
    effects.append(unit_effect)
    return tuple(effects)


def _shooting_unit_selected_context(
    *,
    state: GameState,
    selection: ShootingUnitSelection,
) -> ShootingUnitSelectedContext:
    return ShootingUnitSelectedContext(
        state=state,
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        request_id=selection.request_id,
        result_id=selection.result_id,
    )


def _active_shooting_unit_selection(state: GameState) -> ShootingUnitSelection:
    shooting_state = state.shooting_phase_state
    if shooting_state is not None and shooting_state.active_selection is not None:
        return shooting_state.active_selection
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and not out_of_phase_state.attack_pools
        and out_of_phase_state.attack_sequence is None
    ):
        return ShootingUnitSelection(
            player_id=out_of_phase_state.player_id,
            battle_round=out_of_phase_state.battle_round,
            unit_instance_id=out_of_phase_state.selected_unit_instance_id,
            request_id=out_of_phase_state.source_decision_request_id,
            result_id=out_of_phase_state.source_decision_result_id,
        )
    raise GameLifecycleError("Shooting unit grant requires an active selection.")


def _validate_shooting_unit_selected_grant_payload_context(
    *,
    payload: dict[str, object],
    selection: ShootingUnitSelection,
) -> None:
    if _payload_string(payload, key="submission_kind") != SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
        raise GameLifecycleError("Shooting unit grant payload has invalid submission_kind.")
    if _payload_string(payload, key="unit_instance_id") != selection.unit_instance_id:
        raise GameLifecycleError("Shooting unit grant unit drift.")
    if (
        _payload_string(payload, key="source_decision_request_id") != selection.request_id
        or _payload_string(payload, key="source_decision_result_id") != selection.result_id
    ):
        raise GameLifecycleError("Shooting unit grant source decision drift.")


def _shooting_unit_selected_grant_unit_effect_target_ids(
    *,
    unit_instance_id: str,
    effect_payload: JsonValue,
) -> tuple[str, ...]:
    if not isinstance(effect_payload, dict):
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    raw_target_ids = effect_payload.get("target_unit_instance_ids")
    if raw_target_ids is None:
        return (_validate_identifier("unit_instance_id", unit_instance_id),)
    if not isinstance(raw_target_ids, list):
        raise GameLifecycleError("Shooting unit grant target_unit_instance_ids must be a list.")
    target_ids = tuple(
        _validate_identifier("target_unit_instance_ids", raw_id) for raw_id in raw_target_ids
    )
    if not target_ids:
        raise GameLifecycleError("Shooting unit grant target_unit_instance_ids is empty.")
    if len(set(target_ids)) != len(target_ids):
        raise GameLifecycleError("Shooting unit grant target_unit_instance_ids are duplicated.")
    return target_ids


def _shooting_unit_selected_grant_effect_expiration(
    *,
    state: GameState,
    selection: ShootingUnitSelection,
    grant: ShootingUnitSelectedGrant,
) -> EffectExpiration:
    expiration = grant.unit_effect_expiration
    if expiration == "end_phase":
        return EffectExpiration.end_phase(
            battle_round=state.battle_round,
            phase=BattlePhaseKind.SHOOTING,
            player_id=selection.player_id,
        )
    if expiration == "end_turn":
        return EffectExpiration.end_turn(
            battle_round=state.battle_round,
            player_id=selection.player_id,
        )
    raise GameLifecycleError("Shooting unit grant has unsupported expiration.")
