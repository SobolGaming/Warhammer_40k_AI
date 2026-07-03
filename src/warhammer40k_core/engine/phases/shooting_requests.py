# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.shooting_imports import *
from warhammer40k_core.engine.phases.shooting_model import *
from warhammer40k_core.engine.phases.shooting_handler import *
from warhammer40k_core.engine.phases.shooting_reactions import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord, RangedAttackHistoryRecord
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
    from warhammer40k_core.engine.phases.shooting_model import SELECT_SHOOTING_UNIT_DECISION_TYPE, SELECT_SHOOTING_TYPE_DECISION_TYPE, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE, COMPLETE_SHOOTING_PHASE_OPTION_ID, _COMPLETE_SHOOTING_PHASE_STATUS, _default_stratagem_index, ShootingUnitSelectionPayload, ShootingTypeSelectionPayload, ShootingPhaseStatePayload, OutOfPhaseShootingStatePayload, ShootingDeclarationProposalRequestPayload, ShootingDeclarationDecisionPayload, _AvailableWeapon, _ShootingUnitCandidateCacheKey, _ShootingModelCandidateCacheKey, _ShootingModelCandidateCache, ShootingUnitSelection, ShootingTypeSelection, ShootingPhaseState, OutOfPhaseShootingState
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler, invalid_shooting_phase_start_faction_rule_status, _shooting_phase_start_faction_rule_drift_reason, _request_shooting_phase_start_rule_if_available
    from warhammer40k_core.engine.phases.shooting_reactions import _complete_out_of_phase_shooting, _request_active_shooting_phase_stratagem_if_available, _request_after_unit_selected_as_target_stratagem_if_available, _resolve_completed_shooting_attack_sequence_continuation, _request_friendly_unit_has_shot_stratagem_if_available, _request_enemy_unit_has_shot_stratagem_if_available, _request_shooting_end_surge_if_available, _eligible_triggered_movement_units_from_shooting_grants, _shooting_end_surge_grant_distance_bonus, _shooting_end_surge_distance_roll_spec, _attack_sequence_completed_event_id, _friendly_unit_has_shot_timing_window_id, _active_shooting_phase_stratagem_timing_window_id, _selected_as_target_timing_window_id, _enemy_unit_has_shot_timing_window_id, _target_unit_ids_for_attack_sequence, _stratagem_used_for_context, _successful_hit_target_unit_ids_for_sequence, _destroyed_target_unit_ids_for_sequence, _destroyed_enemy_unit_ids_for_sequence, _shooting_end_surge_event_already_processed
    from warhammer40k_core.engine.phases.shooting_unit_selection import _apply_shooting_unit_selection_decision, _apply_shooting_unit_selected_effect_grants, _request_shooting_unit_selected_grant_decision_if_available, _shooting_unit_selected_grant_options, _apply_shooting_unit_selected_grant_decision, _selected_shooting_unit_grants_from_payload, _validate_selected_shooting_unit_grants, _record_shooting_unit_selected_grant_effects, _shooting_unit_selected_context, _active_shooting_unit_selection, _validate_shooting_unit_selected_grant_payload_context, _shooting_unit_selected_grant_unit_effect_target_ids, _shooting_unit_selected_grant_effect_expiration
    from warhammer40k_core.engine.phases.shooting_decisions import _apply_shooting_dice_reroll_decision, _apply_shooting_type_selection_decision, _apply_shooting_declaration_decision, _apply_out_of_phase_shooting_declaration_decision, _record_ranged_attack_history_for_declaration, _record_one_shot_weapon_uses_for_attack_pools, apply_hidden_status_loss_after_ranged_attacks, _apply_attack_sequence_decision, _apply_attack_sequence_selection_decision, _apply_attack_sequence_selection_to_sequence, _apply_attack_sequence_decision_to_sequence
    from warhammer40k_core.engine.phases.shooting_declaration_validation import _validate_declaration_submission, _validate_out_of_phase_declaration_submission, _attack_pools_for_proposal, _AttackPoolValidationResult, _attack_pools_or_validation, _validate_duplicate_weapon_ability_selection, _shooting_candidate_with_target_restrictions, _modified_shooting_weapon_profile, _runtime_modifier_registry, _out_of_phase_allowed_target_unit_ids, _out_of_phase_uses_fire_overwatch, _forced_shooting_type_for_out_of_phase, _selected_shooting_type_for_declaration, _shooting_types_for_declaration_candidate, _targeting_rule_ids_with_shooting_type, _validate_model_pistol_exclusivity, _apply_phase13d_weapon_modifiers
    from warhammer40k_core.engine.phases.shooting_targeting import _target_within_half_weapon_range, _snap_shooting_type_allowed_for_unit_target, _declaration_target_within_max_range, _unit_target_within_max_range, _unit_placements_for_rules_unit_or_none, _rules_unit_remained_stationary, _heavy_hit_roll_modifier_applies, _rules_unit_set_up_this_turn, _rules_unit_within_enemy_engagement_range, _target_visible_to_friendly_unit, _declaration_source_unit
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_embedded_weapon_ability_request_prefix",
    "_request_shooting_declaration",
    "_request_shooting_type_selection",
    "_required_weapon_ability_selections_for_target",
    "_shooting_types_for_candidate_payload",
    "_shooting_types_for_selected_type",
    "_shooting_types_for_selected_type_for_rules_unit",
    "_target_candidate_payload_for_request",
    "request_out_of_phase_shooting_declaration",
)


def _request_shooting_type_selection(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_state: ShootingPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
) -> LifecycleStatus:
    active_selection = shooting_state.active_selection
    if active_selection is None:
        raise GameLifecycleError("Shooting type request requires active_selection.")
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
    )
    legal_types = _legal_shooting_types_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )
    if not legal_types:
        raise GameLifecycleError("Selected shooting unit has no legal shooting types.")
    request = DecisionRequest(
        request_id=state.next_decision_request_id(),
        decision_type=SELECT_SHOOTING_TYPE_DECISION_TYPE,
        actor_id=active_selection.player_id,
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": active_selection.player_id,
                "unit_instance_id": active_selection.unit_instance_id,
                "source_decision_request_id": active_selection.request_id,
                "source_decision_result_id": active_selection.result_id,
                "legal_shooting_types": [shooting_type.value for shooting_type in legal_types],
            }
        ),
        options=_shooting_type_options(
            state=state,
            active_selection=active_selection,
            legal_types=legal_types,
        ),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_type_selection_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": active_selection.request_id,
                "source_decision_result_id": active_selection.result_id,
                "legal_shooting_types": [shooting_type.value for shooting_type in legal_types],
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": BattlePhase.SHOOTING.value,
            "battle_round": state.battle_round,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "legal_shooting_type_count": len(legal_types),
        },
    )


def _request_shooting_declaration(
    *,
    state: GameState,
    decisions: DecisionController,
    active_selection: ShootingUnitSelection,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    selected_shooting_type: ShootingType | None = None,
    phase: BattlePhase = BattlePhase.SHOOTING,
    request_context: JsonValue | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    forced_shooting_type: ShootingType | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> LifecycleStatus:
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    rules_unit = rules_unit_view_by_id(
        state=state,
        unit_instance_id=active_selection.unit_instance_id,
    )
    available_weapons = _available_weapons_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=active_selection.player_id,
        selected_shooting_type=selected_shooting_type,
    )
    candidate_target_unit_ids = (
        _enemy_placed_unit_ids(
            state=state,
            player_id=active_selection.player_id,
        )
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting target_unit_ids", target_unit_ids)
    )
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=candidate_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=candidate_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=candidate_target_unit_ids,
    )
    detection_context_fingerprint = _targeting_detection_context_fingerprint(
        hidden_target_unit_ids=hidden_target_unit_ids,
        target_unit_ids_with_recent_ranged_attacks=target_unit_ids_with_recent_ranged_attacks,
        detection_range_bonus_by_target_id=detection_range_bonus_by_target_id,
    )
    target_candidates: list[JsonValue] = []
    target_candidate_cache: dict[
        _ShootingUnitCandidateCacheKey,
        tuple[ShootingTargetCandidate, ...],
    ] = {}
    for weapon in available_weapons:
        profile = weapon["weapon_profile"]
        attacker_unit = _component_unit_for_available_weapon(
            rules_unit=rules_unit,
            weapon=weapon,
        )
        candidate_cache_key = _shooting_unit_candidate_cache_key(
            weapon=weapon,
            attacker_unit=attacker_unit,
            detection_context_fingerprint=detection_context_fingerprint,
        )
        if candidate_cache_key not in target_candidate_cache:
            target_candidate_cache[candidate_cache_key] = tuple(
                _shooting_candidate_with_target_restrictions(
                    candidate=candidate,
                    state=state,
                    player_id=active_selection.player_id,
                    attacking_unit_instance_id=attacker_unit.unit_instance_id,
                    target_unit_instance_id=candidate.target_unit_instance_id,
                    registry=shooting_target_restriction_hooks,
                    attacker_model_instance_id=candidate.observer_model_id,
                    shooting_type=forced_shooting_type or selected_shooting_type,
                )
                for candidate in shooting_target_candidates_for_unit(
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    attacker_unit=attacker_unit,
                    weapon_profile=profile,
                    target_unit_ids=candidate_target_unit_ids,
                    terrain_features=terrain_features,
                    hidden_target_unit_ids=hidden_target_unit_ids,
                    target_unit_ids_with_recent_ranged_attacks=(
                        target_unit_ids_with_recent_ranged_attacks
                    ),
                    target_detection_range_bonus_inches_by_unit_id=(
                        detection_range_bonus_by_target_id
                    ),
                )
            )
        candidates = target_candidate_cache[candidate_cache_key]
        target_candidates.extend(
            _target_candidate_payload_for_request(
                state=state,
                scenario=scenario,
                candidate=cast(dict[str, JsonValue], candidate.to_payload()),
                unit=attacker_unit,
                rules_unit=rules_unit,
                weapon_profile=profile,
                player_id=active_selection.player_id,
                army_catalog=army_catalog,
                selected_shooting_type=selected_shooting_type,
                forced_shooting_type=forced_shooting_type,
            )
            for candidate in candidates
        )
    visibility_cache_key = shooting_visibility_cache_key(
        scenario=scenario,
        terrain_features=terrain_features,
    )
    request_id = state.next_decision_request_id()
    proposal_request: ShootingDeclarationProposalRequestPayload = {
        "request_id": request_id,
        "decision_type": SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        "actor_id": active_selection.player_id,
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "phase": phase.value,
        "active_player_id": active_selection.player_id,
        "unit_instance_id": active_selection.unit_instance_id,
        "proposal_kind": SHOOTING_DECLARATION_PROPOSAL_KIND,
        "source_decision_request_id": active_selection.request_id,
        "source_decision_result_id": active_selection.result_id,
        "selected_shooting_type": (
            None if selected_shooting_type is None else selected_shooting_type.value
        ),
        "ruleset_descriptor_hash": state.ruleset_descriptor_hash,
        "visibility_cache_key": visibility_cache_key,
        "firing_deck_value": _firing_deck_value_for_rules_unit(
            rules_unit=rules_unit,
            army_catalog=army_catalog,
        ),
        "available_weapons": [_available_weapon_to_payload(weapon) for weapon in available_weapons],
        "target_candidates": target_candidates,
    }
    request = DecisionRequest(
        request_id=request_id,
        decision_type=SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE,
        actor_id=active_selection.player_id,
        payload=validate_json_value(
            {
                "proposal_request": proposal_request,
                "request_context": request_context,
            }
        ),
        options=(parameterized_decision_option(),),
    )
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_declaration_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_selection.player_id,
                "phase": phase.value,
                "unit_instance_id": active_selection.unit_instance_id,
                "request_id": request.request_id,
                "source_decision_request_id": active_selection.request_id,
                "source_decision_result_id": active_selection.result_id,
                "selected_shooting_type": (
                    None if selected_shooting_type is None else selected_shooting_type.value
                ),
                "available_weapon_count": len(available_weapons),
                "target_candidate_count": len(target_candidates),
                "visibility_cache_key": visibility_cache_key,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload={
            "phase": phase.value,
            "battle_round": state.battle_round,
            "active_player_id": active_selection.player_id,
            "unit_instance_id": active_selection.unit_instance_id,
            "proposal_kind": SHOOTING_DECLARATION_PROPOSAL_KIND,
        },
    )


def request_out_of_phase_shooting_declaration(
    *,
    state: GameState,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
    unit_instance_id: str,
    parent_phase: BattlePhase,
    source_rule_id: str,
    source_decision_request_id: str,
    source_decision_result_id: str,
    source_context: JsonValue,
    target_unit_ids: tuple[str, ...] | None = None,
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry | None = None,
) -> LifecycleStatus:
    if state.out_of_phase_shooting_state is not None:
        raise GameLifecycleError("Out-of-phase shooting state is already active.")
    selected_rules_unit_id = rules_unit_id_for_unit_id(
        armies=tuple(state.army_definitions),
        unit_instance_id=unit_instance_id,
    )
    selection = ShootingUnitSelection(
        player_id=player_id,
        battle_round=state.battle_round,
        unit_instance_id=selected_rules_unit_id,
        request_id=source_decision_request_id,
        result_id=source_decision_result_id,
    )
    state.replace_out_of_phase_shooting_state(
        OutOfPhaseShootingState(
            battle_round=state.battle_round,
            player_id=player_id,
            parent_phase=parent_phase,
            source_rule_id=source_rule_id,
            source_decision_request_id=source_decision_request_id,
            source_decision_result_id=source_decision_result_id,
            source_context=source_context,
            selected_unit_instance_id=selected_rules_unit_id,
            target_unit_ids=target_unit_ids,
        )
    )
    grant_status = _request_shooting_unit_selected_grant_decision_if_available(
        state=state,
        decisions=decisions,
        selection=selection,
        registry=(
            ShootingUnitSelectedGrantRegistry.empty()
            if shooting_unit_selected_grant_hooks is None
            else shooting_unit_selected_grant_hooks
        ),
    )
    if grant_status is not None:
        return grant_status
    return _request_shooting_declaration(
        state=state,
        decisions=decisions,
        active_selection=selection,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        phase=parent_phase,
        request_context=validate_json_value(
            {
                "request_kind": "out_of_phase_shooting",
                "source_rule_id": source_rule_id,
                "source_context": source_context,
            }
        ),
        target_unit_ids=target_unit_ids,
        forced_shooting_type=(
            ShootingType.SNAP if source_rule_id == FIRE_OVERWATCH_RULE_ID else None
        ),
    )


def _target_candidate_payload_for_request(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    candidate: dict[str, JsonValue],
    unit: UnitInstance,
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    player_id: str,
    army_catalog: ArmyCatalog,
    selected_shooting_type: ShootingType | None,
    forced_shooting_type: ShootingType | None,
) -> JsonValue:
    payload = dict(candidate)
    payload["required_weapon_ability_selections"] = _required_weapon_ability_selections_for_target(
        state=state,
        proposal_request_id=_embedded_weapon_ability_request_prefix(
            state=state,
            attacker_unit_id=rules_unit.unit_instance_id,
            weapon_profile=weapon_profile,
        ),
        weapon_profile=weapon_profile,
        target_unit_id=_payload_string(
            cast(dict[str, object], payload), key="target_unit_instance_id"
        ),
        player_id=player_id,
    )
    payload["shooting_types"] = [
        shooting_type.value
        for shooting_type in _shooting_types_for_candidate_payload(
            state=state,
            scenario=scenario,
            candidate=candidate,
            unit=unit,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            player_id=player_id,
            army_catalog=army_catalog,
            selected_shooting_type=selected_shooting_type,
            forced_shooting_type=forced_shooting_type,
        )
    ]
    return validate_json_value(payload)


def _embedded_weapon_ability_request_prefix(
    *,
    state: GameState,
    attacker_unit_id: str,
    weapon_profile: WeaponProfile,
) -> str:
    return f"{state.game_id}:shooting-declaration:{attacker_unit_id}:{weapon_profile.profile_id}"


def _required_weapon_ability_selections_for_target(
    *,
    state: GameState,
    proposal_request_id: str,
    weapon_profile: WeaponProfile,
    target_unit_id: str,
    player_id: str,
) -> list[JsonValue]:
    target_rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=target_unit_id)
    selection_request = weapon_ability_selection_request(
        weapon_profile,
        AbilityKind.ANTI_KEYWORD,
        target_keywords=target_rules_unit.keywords,
        actor_id=player_id,
        request_id=f"{proposal_request_id}:{target_unit_id}:anti-keyword",
        source_context={
            "phase": BattlePhase.SHOOTING.value,
            "target_unit_instance_id": target_unit_id,
        },
    )
    if selection_request is None:
        return []
    return [validate_json_value(selection_request.to_payload())]


def _shooting_types_for_candidate_payload(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    candidate: dict[str, JsonValue],
    unit: UnitInstance,
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    player_id: str,
    army_catalog: ArmyCatalog,
    selected_shooting_type: ShootingType | None,
    forced_shooting_type: ShootingType | None,
) -> tuple[ShootingType, ...]:
    if candidate.get("is_legal") is not True:
        return ()
    raw_types = candidate.get("shooting_types")
    if not isinstance(raw_types, list):
        raise GameLifecycleError("Shooting target candidate payload missing shooting_types.")
    base_types = tuple(shooting_type_from_token(value) for value in raw_types)
    target_unit_id = _payload_string(
        cast(dict[str, object], candidate),
        key="target_unit_instance_id",
    )
    if forced_shooting_type is not None:
        if forced_shooting_type is not ShootingType.SNAP:
            raise GameLifecycleError("Unsupported forced shooting type.")
        if _snap_shooting_type_allowed_for_unit_target(
            scenario=scenario,
            candidate=candidate,
            unit=unit,
            target_unit_id=target_unit_id,
        ):
            return (ShootingType.SNAP,)
        return ()
    if selected_shooting_type is not None:
        return _shooting_types_for_selected_type_for_rules_unit(
            state=state,
            base_types=base_types,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            selected_shooting_type=selected_shooting_type,
            player_id=player_id,
            army_catalog=army_catalog,
        )
    if _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        if ShootingType.NORMAL in base_types and has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.ASSAULT,
        ):
            return (ShootingType.ASSAULT,)
        return ()
    return base_types


def _shooting_types_for_selected_type(
    *,
    state: GameState,
    base_types: tuple[ShootingType, ...],
    unit: UnitInstance,
    weapon_profile: WeaponProfile,
    selected_shooting_type: ShootingType,
    player_id: str,
    army_catalog: ArmyCatalog,
) -> tuple[ShootingType, ...]:
    return _shooting_types_for_selected_type_for_rules_unit(
        state=state,
        base_types=base_types,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        weapon_profile=weapon_profile,
        selected_shooting_type=selected_shooting_type,
        player_id=player_id,
        army_catalog=army_catalog,
    )


def _shooting_types_for_selected_type_for_rules_unit(
    *,
    state: GameState,
    base_types: tuple[ShootingType, ...],
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    selected_shooting_type: ShootingType,
    player_id: str,
    army_catalog: ArmyCatalog,
) -> tuple[ShootingType, ...]:
    shooting_type = shooting_type_from_token(selected_shooting_type)
    advanced = _rules_unit_advanced_this_turn(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    )
    if shooting_type is ShootingType.NORMAL:
        if advanced:
            return ()
        if ShootingType.NORMAL in base_types:
            return (ShootingType.NORMAL,)
        return ()
    if shooting_type is ShootingType.ASSAULT:
        if not advanced:
            return ()
        if ShootingType.NORMAL in base_types and has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.ASSAULT,
        ):
            return (ShootingType.ASSAULT,)
        return ()
    if shooting_type is ShootingType.CLOSE_QUARTERS:
        if advanced or ShootingType.CLOSE_QUARTERS not in base_types:
            return ()
        if _rules_unit_has_vehicle_or_monster_keyword(
            rules_unit
        ) or has_close_quarters_weapon_keyword(weapon_profile):
            return (ShootingType.CLOSE_QUARTERS,)
        return ()
    if shooting_type is ShootingType.INDIRECT:
        if advanced or not _rules_unit_has_indirect_ranged_weapon(
            rules_unit=rules_unit,
            army_catalog=army_catalog,
        ):
            return ()
        if not has_weapon_keyword(weapon_profile, WeaponKeyword.INDIRECT_FIRE):
            return ()
        if ShootingType.INDIRECT in base_types or ShootingType.NORMAL in base_types:
            return (ShootingType.INDIRECT,)
        return ()
    if shooting_type is ShootingType.SNAP:
        return ()
    raise GameLifecycleError("Unsupported selected shooting type.")
