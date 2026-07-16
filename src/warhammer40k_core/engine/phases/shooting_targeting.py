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
from warhammer40k_core.engine.shooting_selection_range import (
    target_within_shooting_selection_range,
)

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
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_declaration_source_unit",
    "_declaration_target_within_max_range",
    "_heavy_hit_roll_modifier_applies",
    "_rules_unit_remained_stationary",
    "_rules_unit_set_up_this_turn",
    "_rules_unit_within_enemy_engagement_range",
    "_snap_shooting_type_allowed_for_unit_target",
    "_target_visible_to_friendly_unit",
    "_target_within_half_weapon_range",
    "_unit_placements_for_rules_unit_or_none",
    "_unit_target_within_max_range",
)


def _target_within_half_weapon_range(
    *,
    scenario: BattlefieldScenario,
    declaration: WeaponDeclaration,
    weapon_profile: WeaponProfile,
    target_in_range_model_ids: tuple[str, ...],
) -> bool:
    range_inches = weapon_profile.range_profile.distance_inches
    if range_inches is None:
        raise GameLifecycleError("Half-range weapon modifier requires a ranged weapon.")
    if not target_in_range_model_ids:
        return False
    battlefield = scenario.battlefield_state
    attacker_placement = battlefield.model_placement_by_id(declaration.attacker_model_instance_id)
    attacker_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(attacker_placement),
        placement=attacker_placement,
    )
    half_range = float(range_inches) / 2.0
    for target_model_id in target_in_range_model_ids:
        target_placement = battlefield.model_placement_by_id(target_model_id)
        target_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(target_placement),
            placement=target_placement,
        )
        distance = DistanceMeasurementContext.from_models(
            attacker_model,
            target_model,
        ).closest_distance_inches()
        if distance <= half_range:
            return True
    return False


def _snap_shooting_type_allowed_for_unit_target(
    *,
    scenario: BattlefieldScenario,
    candidate: dict[str, JsonValue],
    unit: UnitInstance,
    target_unit_id: str,
) -> bool:
    target_visible_model_ids = candidate.get("target_visible_model_ids")
    if not isinstance(target_visible_model_ids, list) or not target_visible_model_ids:
        return False
    return _unit_target_within_max_range(
        scenario=scenario,
        unit=unit,
        target_unit_id=target_unit_id,
        range_inches=24,
    )


def _declaration_target_within_max_range(
    *,
    scenario: BattlefieldScenario,
    declaration: WeaponDeclaration,
    target_in_range_model_ids: tuple[str, ...],
    range_inches: int,
) -> bool:
    if not target_in_range_model_ids:
        return False
    battlefield = scenario.battlefield_state
    attacker_placement = battlefield.model_placement_by_id(declaration.attacker_model_instance_id)
    attacker_model = geometry_model_for_placement(
        model=scenario.model_instance_for_placement(attacker_placement),
        placement=attacker_placement,
    )
    for target_model_id in target_in_range_model_ids:
        target_placement = battlefield.model_placement_by_id(target_model_id)
        target_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(target_placement),
            placement=target_placement,
        )
        if DistanceMeasurementContext.from_models(
            attacker_model,
            target_model,
        ).closest_distance_inches() <= float(range_inches):
            return True
    return False


def _unit_target_within_max_range(
    *,
    scenario: BattlefieldScenario,
    unit: UnitInstance,
    target_unit_id: str,
    range_inches: int,
) -> bool:
    return target_within_shooting_selection_range(
        scenario=scenario,
        attacking_unit_instance_id=unit.unit_instance_id,
        target_unit_instance_id=target_unit_id,
        max_range_inches=range_inches,
    )


def _unit_placements_for_rules_unit_or_none(
    *,
    scenario: BattlefieldScenario,
    rules_unit: RulesUnitView,
) -> tuple[UnitPlacement, ...] | None:
    placements: list[UnitPlacement] = []
    for component in rules_unit.components:
        try:
            placements.append(
                scenario.battlefield_state.unit_placement_by_id(component.unit.unit_instance_id)
            )
        except PlacementError as exc:
            if not any(model.is_alive for model in component.unit.own_models):
                continue
            raise GameLifecycleError("Shooting rules-unit component is not placed.") from exc
    if not placements:
        return None
    return tuple(sorted(placements, key=lambda placement: placement.unit_instance_id))


def _rules_unit_remained_stationary(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    unit_ids = _rules_unit_state_unit_ids(rules_unit)
    if _rules_unit_set_up_this_turn(
        state=state,
        unit_ids=unit_ids,
        player_id=actor_id,
    ):
        return False
    for unit_id in unit_ids:
        advanced_state = state.advanced_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if advanced_state is not None:
            return False
        fell_back_state = state.fell_back_unit_state_for_unit(
            player_id=actor_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if fell_back_state is not None:
            return False
    movement_state = state.movement_phase_state
    if movement_state is None:
        return True
    movement_unit_ids = set(movement_state.moved_unit_ids)
    if not movement_unit_ids.intersection(unit_ids):
        return True
    for record in movement_state.movement_distance_records:
        if record.unit_instance_id in unit_ids:
            return record.maximum_model_distance_inches <= 3.0
    return False


def _heavy_hit_roll_modifier_applies(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    player_id: str | None,
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    if out_of_phase_state is not None:
        return False
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return False
    if _active_player_id(state) != actor_id:
        return False
    if _rules_unit_within_enemy_engagement_range(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        player_id=actor_id,
    ):
        return False
    return _rules_unit_remained_stationary(
        state=state,
        rules_unit=rules_unit,
        player_id=actor_id,
    )


def _rules_unit_set_up_this_turn(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    player_id: str,
) -> bool:
    for unit_id in unit_ids:
        reserve_state = state.reserve_state_for_unit(unit_id)
        if (
            reserve_state is not None
            and reserve_state.player_id == player_id
            and reserve_state.arrived_battle_round == state.battle_round
        ):
            return True
        disembarked_state = state.disembarked_unit_state_for_unit(
            player_id=player_id,
            battle_round=state.battle_round,
            unit_instance_id=unit_id,
        )
        if disembarked_state is not None and not disembarked_state.can_choose_remain_stationary:
            return True
    return False


def _rules_unit_within_enemy_engagement_range(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    player_id: str,
) -> bool:
    unit_placements = _unit_placements_for_rules_unit_or_none(
        scenario=scenario,
        rules_unit=rules_unit,
    )
    if unit_placements is None:
        return False
    policy = ruleset_descriptor.engagement_policy
    friendly_models = tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(model_placement),
            placement=model_placement,
        )
        for unit_placement in unit_placements
        for model_placement in unit_placement.model_placements
    )
    for placed_army in scenario.battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        for enemy_unit_placement in placed_army.unit_placements:
            for enemy_model_placement in enemy_unit_placement.model_placements:
                enemy_model = geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(enemy_model_placement),
                    placement=enemy_model_placement,
                )
                if any(
                    friendly_model.is_within_engagement_range(
                        enemy_model,
                        horizontal_inches=policy.horizontal_inches,
                        vertical_inches=policy.vertical_inches,
                    )
                    for friendly_model in friendly_models
                ):
                    return True
    return False


def _target_visible_to_friendly_unit(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    target_unit_instance_id: str,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    player_id: str | None = None,
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Friendly visibility query requires battlefield_state.")
    try:
        placed_army = battlefield.placed_army_for_player(actor_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Friendly visibility query requires placed friendly units."
        ) from exc
    for unit_placement in placed_army.unit_placements:
        if unit_placement.unit_instance_id == target_unit_instance_id:
            raise GameLifecycleError("Friendly visibility query included the target unit.")
        friendly_unit = _unit_by_id(state=state, unit_instance_id=unit_placement.unit_instance_id)
        if unit_has_line_of_sight_to_target(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            observing_unit=friendly_unit,
            target_unit_id=target_unit_instance_id,
            terrain_features=terrain_features,
        ):
            return True
    return False


def _declaration_source_unit(
    *,
    state: GameState,
    selected_unit: UnitInstance,
    declaration: WeaponDeclaration,
) -> UnitInstance:
    source_unit_id = declaration.firing_deck_source_unit_instance_id
    if source_unit_id is None:
        return selected_unit
    return _unit_by_id(state=state, unit_instance_id=source_unit_id)
