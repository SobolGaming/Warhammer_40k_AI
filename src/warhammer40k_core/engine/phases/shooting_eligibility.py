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
from warhammer40k_core.engine.phases.shooting_decisions import *
from warhammer40k_core.engine.phases.shooting_declaration_validation import *
from warhammer40k_core.engine.phases.shooting_targeting import *
from warhammer40k_core.engine.phases.shooting_firing_deck import *

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
    from warhammer40k_core.engine.phases.shooting_decisions import _apply_shooting_dice_reroll_decision, _apply_shooting_type_selection_decision, _apply_shooting_declaration_decision, _apply_out_of_phase_shooting_declaration_decision, _record_ranged_attack_history_for_declaration, _record_one_shot_weapon_uses_for_attack_pools, apply_hidden_status_loss_after_ranged_attacks, _apply_attack_sequence_decision, _apply_attack_sequence_selection_decision, _apply_attack_sequence_selection_to_sequence, _apply_attack_sequence_decision_to_sequence
    from warhammer40k_core.engine.phases.shooting_declaration_validation import _validate_declaration_submission, _validate_out_of_phase_declaration_submission, _attack_pools_for_proposal, _AttackPoolValidationResult, _attack_pools_or_validation, _validate_duplicate_weapon_ability_selection, _shooting_candidate_with_target_restrictions, _modified_shooting_weapon_profile, _runtime_modifier_registry, _out_of_phase_allowed_target_unit_ids, _out_of_phase_uses_fire_overwatch, _forced_shooting_type_for_out_of_phase, _selected_shooting_type_for_declaration, _shooting_types_for_declaration_candidate, _targeting_rule_ids_with_shooting_type, _validate_model_pistol_exclusivity, _apply_phase13d_weapon_modifiers
    from warhammer40k_core.engine.phases.shooting_targeting import _target_within_half_weapon_range, _snap_shooting_type_allowed_for_unit_target, _declaration_target_within_max_range, _unit_target_within_max_range, _unit_placements_for_rules_unit_or_none, _rules_unit_remained_stationary, _heavy_hit_roll_modifier_applies, _rules_unit_set_up_this_turn, _rules_unit_within_enemy_engagement_range, _target_visible_to_friendly_unit, _declaration_source_unit
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_advanced_unit_is_restricted_to_assault_weapons",
    "_cached_shooting_target_candidate_for_model",
    "_detection_range_bonus_inches_by_target_id",
    "_hidden_target_unit_ids",
    "_legal_shooting_types_for_rules_unit",
    "_legal_shooting_unit_ids",
    "_rules_unit_advanced_is_restricted_to_assault_weapons",
    "_rules_unit_advanced_this_turn",
    "_rules_unit_can_select_to_shoot",
    "_rules_unit_has_assault_ranged_weapon",
    "_rules_unit_has_indirect_ranged_weapon",
    "_rules_unit_has_legal_shooting_declaration",
    "_rules_unit_state_unit_ids",
    "_shooting_model_candidate_cache_key",
    "_shooting_unit_candidate_cache_key",
    "_shot_source_unit_ids_for_detection_effects",
    "_target_unit_ids_with_recent_ranged_attacks",
    "_targeting_detection_context_fingerprint",
    "_unit_advanced_this_turn",
    "_unit_can_select_to_shoot",
    "_unit_has_already_shot",
    "_unit_has_assault_ranged_weapon",
    "_unit_has_indirect_ranged_weapon",
    "_unit_has_legal_shooting_declaration",
    "_weapon_profile_cache_fingerprint",
    "shooting_rules_unit_has_legal_declaration_against_targets",
    "shooting_rules_unit_is_eligible_to_shoot",
    "shooting_unit_can_select_to_shoot",
    "shooting_unit_has_legal_declaration_against_targets",
)


def _legal_shooting_unit_ids(
    *,
    state: GameState,
    shooting_state: ShootingPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> tuple[str, ...]:
    scenario = _battlefield_scenario(state)
    active_player_id = _active_player_id(state)
    placed_unit_ids = _active_player_placed_unit_ids(state=state, player_id=active_player_id)
    legal: list[str] = []
    for unit_id in placed_unit_ids:
        if (
            unit_id in shooting_state.selected_unit_ids
            or unit_id in shooting_state.shot_unit_ids
            or unit_id in shooting_state.skipped_unit_ids
        ):
            continue
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        if not _rules_unit_can_select_to_shoot(
            state=state,
            rules_unit=rules_unit,
            army_catalog=army_catalog,
        ):
            continue
        if _rules_unit_has_legal_shooting_declaration(
            state=state,
            scenario=scenario,
            rules_unit=rules_unit,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        ):
            legal.append(rules_unit.unit_instance_id)
    return tuple(sorted(legal))


def _rules_unit_has_legal_shooting_declaration(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    selected_shooting_type: ShootingType | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    terrain_features = _terrain_features_for_state(state)
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    candidate_cache: _ShootingModelCandidateCache = {}
    for weapon in _available_weapons_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=actor_id,
        selected_shooting_type=selected_shooting_type,
    ):
        attacker_unit = _component_unit_for_available_weapon(
            rules_unit=rules_unit,
            weapon=weapon,
        )
        for target_unit_id in resolved_target_unit_ids:
            candidate = _cached_shooting_target_candidate_for_model(
                cache=candidate_cache,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                attacker_unit=attacker_unit,
                weapon=weapon,
                target_unit_id=target_unit_id,
                terrain_features=terrain_features,
                hidden_target_unit_ids=hidden_target_unit_ids,
                target_unit_ids_with_recent_ranged_attacks=(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                    target_unit_id,
                    0,
                ),
                shooting_target_restriction_hooks=shooting_target_restriction_hooks,
                state=state,
                player_id=actor_id,
            )
            if not candidate.is_legal:
                continue
            if selected_shooting_type is None:
                return True
            if _shooting_types_for_selected_type_for_rules_unit(
                state=state,
                base_types=candidate.shooting_types,
                rules_unit=rules_unit,
                weapon_profile=weapon["weapon_profile"],
                selected_shooting_type=selected_shooting_type,
                player_id=actor_id,
                army_catalog=army_catalog,
            ):
                return True
    return False


def _hidden_target_unit_ids(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            target_unit_id
            for target_unit_id in _validate_identifier_tuple(
                "hidden target target_unit_ids",
                target_unit_ids,
            )
            if unit_is_hidden_by_effects(state.persisting_effects_for_unit(target_unit_id))
        )
    )


def _detection_range_bonus_inches_by_target_id(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
) -> dict[str, int]:
    shot_source_unit_ids = _shot_source_unit_ids_for_detection_effects(state)
    bonuses: dict[str, int] = {}
    for target_unit_id in _validate_identifier_tuple(
        "detection range target_unit_ids",
        target_unit_ids,
    ):
        bonus_inches = detection_range_bonus_inches_for_effects(
            state.persisting_effects_for_unit(target_unit_id),
            shot_source_unit_ids=shot_source_unit_ids,
        )
        if bonus_inches > 0:
            bonuses[target_unit_id] = bonus_inches
    return bonuses


def _shot_source_unit_ids_for_detection_effects(state: GameState) -> tuple[str, ...]:
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        return ()
    return shooting_state.shot_unit_ids


def _target_unit_ids_with_recent_ranged_attacks(
    *,
    state: GameState,
    target_unit_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            target_unit_id
            for target_unit_id in _validate_identifier_tuple(
                "recent ranged attack target_unit_ids",
                target_unit_ids,
            )
            if state.unit_made_ranged_attacks_current_or_previous_turn(
                unit_instance_id=target_unit_id,
            )
        )
    )


def _targeting_detection_context_fingerprint(
    *,
    hidden_target_unit_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    detection_range_bonus_by_target_id: dict[str, int],
) -> str:
    return canonical_json(
        validate_json_value(
            {
                "hidden_target_unit_ids": list(hidden_target_unit_ids),
                "target_unit_ids_with_recent_ranged_attacks": list(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                "detection_range_bonus_by_target_id": detection_range_bonus_by_target_id,
            }
        )
    )


def _unit_has_legal_shooting_declaration(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    selected_shooting_type: ShootingType | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    terrain_features = _terrain_features_for_state(state)
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    candidate_cache: _ShootingModelCandidateCache = {}
    for weapon in _available_weapons_for_unit(
        state=state,
        unit=unit,
        army_catalog=army_catalog,
        player_id=actor_id,
        selected_shooting_type=selected_shooting_type,
    ):
        for target_unit_id in resolved_target_unit_ids:
            candidate = _cached_shooting_target_candidate_for_model(
                cache=candidate_cache,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                attacker_unit=unit,
                weapon=weapon,
                target_unit_id=target_unit_id,
                terrain_features=terrain_features,
                hidden_target_unit_ids=hidden_target_unit_ids,
                target_unit_ids_with_recent_ranged_attacks=(
                    target_unit_ids_with_recent_ranged_attacks
                ),
                target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                    target_unit_id,
                    0,
                ),
                shooting_target_restriction_hooks=shooting_target_restriction_hooks,
                state=state,
                player_id=actor_id,
            )
            if not candidate.is_legal:
                continue
            if selected_shooting_type is None:
                return True
            if _shooting_types_for_selected_type(
                state=state,
                base_types=candidate.shooting_types,
                unit=unit,
                weapon_profile=weapon["weapon_profile"],
                selected_shooting_type=selected_shooting_type,
                player_id=actor_id,
                army_catalog=army_catalog,
            ):
                return True
    return False


def _legal_shooting_types_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> tuple[ShootingType, ...]:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=resolved_target_unit_ids,
    )
    candidate_cache: _ShootingModelCandidateCache = {}
    legal_types: set[ShootingType] = set()
    for shooting_type in (
        ShootingType.NORMAL,
        ShootingType.ASSAULT,
        ShootingType.CLOSE_QUARTERS,
        ShootingType.INDIRECT,
    ):
        for weapon in _available_weapons_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
            army_catalog=army_catalog,
            player_id=actor_id,
            selected_shooting_type=shooting_type,
        ):
            attacker_unit = _component_unit_for_available_weapon(
                rules_unit=rules_unit,
                weapon=weapon,
            )
            for target_unit_id in resolved_target_unit_ids:
                candidate = _cached_shooting_target_candidate_for_model(
                    cache=candidate_cache,
                    scenario=scenario,
                    ruleset_descriptor=ruleset_descriptor,
                    attacker_unit=attacker_unit,
                    weapon=weapon,
                    target_unit_id=target_unit_id,
                    terrain_features=terrain_features,
                    hidden_target_unit_ids=hidden_target_unit_ids,
                    target_unit_ids_with_recent_ranged_attacks=(
                        target_unit_ids_with_recent_ranged_attacks
                    ),
                    target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                        target_unit_id,
                        0,
                    ),
                    shooting_target_restriction_hooks=shooting_target_restriction_hooks,
                    state=state,
                    player_id=actor_id,
                )
                if not candidate.is_legal:
                    continue
                if _shooting_types_for_selected_type_for_rules_unit(
                    state=state,
                    base_types=candidate.shooting_types,
                    rules_unit=rules_unit,
                    weapon_profile=weapon["weapon_profile"],
                    selected_shooting_type=shooting_type,
                    player_id=actor_id,
                    army_catalog=army_catalog,
                ):
                    legal_types.add(shooting_type)
                    break
            if shooting_type in legal_types:
                break
    return tuple(
        shooting_type
        for shooting_type in (
            ShootingType.NORMAL,
            ShootingType.ASSAULT,
            ShootingType.CLOSE_QUARTERS,
            ShootingType.INDIRECT,
        )
        if shooting_type in legal_types
    )


def _cached_shooting_target_candidate_for_model(
    *,
    cache: _ShootingModelCandidateCache,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    attacker_unit: UnitInstance,
    weapon: _AvailableWeapon,
    target_unit_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    hidden_target_unit_ids: tuple[str, ...],
    target_unit_ids_with_recent_ranged_attacks: tuple[str, ...],
    target_detection_range_bonus_inches: int,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
    state: GameState | None = None,
    player_id: str | None = None,
) -> ShootingTargetCandidate:
    cache_key = _shooting_model_candidate_cache_key(
        weapon=weapon,
        target_unit_id=target_unit_id,
        target_is_hidden=target_unit_id in hidden_target_unit_ids,
        target_made_recent_ranged_attacks=(
            target_unit_id in target_unit_ids_with_recent_ranged_attacks
        ),
        target_detection_range_bonus_inches=target_detection_range_bonus_inches,
    )
    if cache_key not in cache:
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            attacker_unit=attacker_unit,
            attacker_model_instance_id=weapon["model_instance_id"],
            weapon_profile=weapon["weapon_profile"],
            target_unit_id=target_unit_id,
            terrain_features=terrain_features,
            hidden_target_unit_ids=hidden_target_unit_ids,
            target_unit_ids_with_recent_ranged_attacks=(target_unit_ids_with_recent_ranged_attacks),
            target_detection_range_bonus_inches=target_detection_range_bonus_inches,
        )
        if shooting_target_restriction_hooks is not None:
            if state is None or player_id is None:
                raise GameLifecycleError("Shooting target restriction requires state/player.")
            candidate = _shooting_candidate_with_target_restrictions(
                candidate=candidate,
                state=state,
                player_id=player_id,
                attacking_unit_instance_id=attacker_unit.unit_instance_id,
                target_unit_instance_id=target_unit_id,
                registry=shooting_target_restriction_hooks,
                attacker_model_instance_id=weapon["model_instance_id"],
                shooting_type=None,
            )
        cache[cache_key] = candidate
    return cache[cache_key]


def _shooting_unit_candidate_cache_key(
    weapon: _AvailableWeapon,
    attacker_unit: UnitInstance,
    detection_context_fingerprint: str,
) -> _ShootingUnitCandidateCacheKey:
    profile = weapon["weapon_profile"]
    return (
        attacker_unit.unit_instance_id,
        weapon["wargear_id"],
        profile.profile_id,
        _weapon_profile_cache_fingerprint(profile),
        detection_context_fingerprint,
    )


def _shooting_model_candidate_cache_key(
    *,
    weapon: _AvailableWeapon,
    target_unit_id: str,
    target_is_hidden: bool,
    target_made_recent_ranged_attacks: bool,
    target_detection_range_bonus_inches: int,
) -> _ShootingModelCandidateCacheKey:
    profile = weapon["weapon_profile"]
    return (
        weapon["model_instance_id"],
        weapon["wargear_id"],
        profile.profile_id,
        weapon.get("firing_deck_source_unit_instance_id"),
        weapon.get("firing_deck_source_model_instance_id"),
        _weapon_profile_cache_fingerprint(profile),
        target_unit_id,
        target_is_hidden,
        target_made_recent_ranged_attacks,
        target_detection_range_bonus_inches,
    )


def _weapon_profile_cache_fingerprint(weapon_profile: WeaponProfile) -> str:
    return canonical_json(weapon_profile.to_payload())


def shooting_unit_can_select_to_shoot(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> bool:
    return _unit_can_select_to_shoot(
        state=state,
        unit=unit,
        army_catalog=army_catalog,
        player_id=player_id,
    )


def shooting_unit_has_legal_declaration_against_targets(
    *,
    state: GameState,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
    target_unit_ids: tuple[str, ...],
) -> bool:
    return _unit_has_legal_shooting_declaration(
        state=state,
        scenario=_battlefield_scenario(state),
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
    )


def shooting_rules_unit_has_legal_declaration_against_targets(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
    target_unit_ids: tuple[str, ...],
) -> bool:
    return _rules_unit_has_legal_shooting_declaration(
        state=state,
        scenario=_battlefield_scenario(state),
        rules_unit=rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=player_id,
        target_unit_ids=target_unit_ids,
    )


def shooting_rules_unit_is_eligible_to_shoot(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
) -> bool:
    if not _rules_unit_can_select_to_shoot(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=player_id,
    ):
        return False
    return _rules_unit_has_legal_shooting_declaration(
        state=state,
        scenario=_battlefield_scenario(state),
        rules_unit=rules_unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        player_id=player_id,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
    )


def _rules_unit_state_unit_ids(rules_unit: RulesUnitView) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys((rules_unit.unit_instance_id, *rules_unit.component_unit_instance_ids))
    )


def _unit_can_select_to_shoot(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    advanced_state = state.advanced_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    if (
        advanced_state is not None
        and not advanced_state.can_shoot
        and not _unit_has_assault_ranged_weapon(
            state=state,
            unit=unit,
            army_catalog=army_catalog,
            player_id=actor_id,
        )
    ):
        return False
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    return not (fell_back_state is not None and not fell_back_state.can_shoot)


def _rules_unit_can_select_to_shoot(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    if _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=actor_id,
    ) and not _rules_unit_has_assault_ranged_weapon(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=actor_id,
    ):
        return False
    for unit_id in _rules_unit_state_unit_ids(rules_unit):
        fell_back_state = state.fell_back_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if fell_back_state is not None and not fell_back_state.can_shoot:
            return False
    return True


def _advanced_unit_is_restricted_to_assault_weapons(
    *,
    state: GameState,
    unit: UnitInstance,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    advanced_state = state.advanced_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    return advanced_state is not None and not advanced_state.can_shoot


def _rules_unit_advanced_is_restricted_to_assault_weapons(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    return any(
        (
            advanced_state := state.advanced_unit_state_for_unit(
                player_id=actor_id,
                battle_round=state.battle_round,
                unit_instance_id=unit_id,
            )
        )
        is not None
        and not advanced_state.can_shoot
        for unit_id in _rules_unit_state_unit_ids(rules_unit)
    )


def _unit_advanced_this_turn(
    *,
    state: GameState,
    unit: UnitInstance,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    return (
        state.advanced_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit.unit_instance_id,
        )
        is not None
    )


def _rules_unit_advanced_this_turn(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    return any(
        state.advanced_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        is not None
        for unit_id in _rules_unit_state_unit_ids(rules_unit)
    )


def _unit_has_assault_ranged_weapon(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> bool:
    for model in unit.own_models:
        for weapon in _available_own_weapons_for_model(
            state=state,
            model=model,
            unit=unit,
            army_catalog=army_catalog,
            player_id=player_id,
        ):
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT):
                return True
    return False


def _rules_unit_has_assault_ranged_weapon(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str,
) -> bool:
    return any(
        _unit_has_assault_ranged_weapon(
            state=state,
            unit=component.unit,
            army_catalog=army_catalog,
            player_id=player_id,
        )
        for component in rules_unit.components
    )


def _unit_has_indirect_ranged_weapon(*, unit: UnitInstance, army_catalog: ArmyCatalog) -> bool:
    for model in unit.own_models:
        for weapon in _available_weapons_for_model(
            model=model,
            unit=unit,
            army_catalog=army_catalog,
        ):
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.INDIRECT_FIRE):
                return True
    return False


def _rules_unit_has_indirect_ranged_weapon(
    *,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> bool:
    return any(
        _unit_has_indirect_ranged_weapon(unit=component.unit, army_catalog=army_catalog)
        for component in rules_unit.components
    )


def _unit_has_already_shot(*, state: GameState, unit_instance_id: str) -> bool:
    shooting_state = state.shooting_phase_state
    return shooting_state is not None and unit_instance_id in shooting_state.shot_unit_ids
