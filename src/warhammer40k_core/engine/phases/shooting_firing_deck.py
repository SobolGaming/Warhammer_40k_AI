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
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_available_firing_deck_weapons",
    "_available_own_weapons_for_model",
    "_available_weapon_by_declaration_key_for_rules_unit",
    "_available_weapon_key",
    "_available_weapon_to_payload",
    "_available_weapons_for_model",
    "_available_weapons_for_rules_unit",
    "_available_weapons_for_unit",
    "_component_unit_by_id",
    "_component_unit_for_available_weapon",
    "_component_unit_for_declaration",
    "_declaration_available_weapon_key",
    "_declaration_source_model_id",
    "_transport_firing_deck_model",
    "_validate_firing_deck_selection",
    "_validate_firing_deck_weapon_against_catalog",
)


def _declaration_source_model_id(declaration: WeaponDeclaration) -> str:
    source_model_id = declaration.firing_deck_source_model_instance_id
    if source_model_id is not None:
        return source_model_id
    return declaration.attacker_model_instance_id


def _validate_firing_deck_selection(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    army_catalog: ArmyCatalog,
) -> tuple[str, ...] | ShootingProposalValidationResult:
    firing_deck_declarations = tuple(
        declaration for declaration in proposal.declarations if declaration.uses_firing_deck
    )
    if not firing_deck_declarations:
        if proposal.firing_deck_selection is not None:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="firing_deck_selection_without_declaration",
                message="Firing Deck selection requires Firing Deck declarations.",
                field="firing_deck_selection",
            )
        return ()
    selection = proposal.firing_deck_selection
    if selection is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_selection_missing",
            message="Firing Deck declarations require a Firing Deck selection payload.",
            field="firing_deck_selection",
        )
    shooting_state = state.shooting_phase_state
    if shooting_state is None:
        raise GameLifecycleError("Firing Deck validation requires shooting_phase_state.")
    if selection.player_id != _active_player_id(state):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_player_drift",
            message="Firing Deck selection player_id does not match active player.",
            field="firing_deck_selection",
        )
    if selection.battle_round != state.battle_round:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_battle_round_drift",
            message="Firing Deck selection battle_round does not match current round.",
            field="firing_deck_selection",
        )
    if selection.transport_unit_instance_id != proposal.unit_instance_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_transport_drift",
            message="Firing Deck selection transport does not match shooting unit.",
            field="firing_deck_selection",
        )
    transport_unit = _unit_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    firing_deck_value = _firing_deck_value_for_unit(
        unit=transport_unit,
        army_catalog=army_catalog,
    )
    if firing_deck_value is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_ability_missing",
            message="Firing Deck declarations require a Firing Deck ability descriptor.",
            field="firing_deck_selection",
        )
    if selection.firing_deck_value != firing_deck_value:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_value_drift",
            message="Firing Deck selection value does not match engine rules.",
            field="firing_deck_selection",
        )
    if selection.already_shot_unit_instance_ids != shooting_state.shot_unit_ids:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_shot_state_drift",
            message="Firing Deck selection shot-state evidence does not match engine state.",
            field="firing_deck_selection",
        )
    weapon_selection_keys = {
        (
            weapon_selection.embarked_unit_instance_id,
            weapon_selection.model_instance_id,
            weapon_selection.wargear_id,
            weapon_selection.weapon_profile.profile_id,
        )
        for weapon_selection in selection.weapon_selections
    }
    declaration_keys = {
        (
            declaration.firing_deck_source_unit_instance_id,
            declaration.firing_deck_source_model_instance_id,
            declaration.wargear_id,
            declaration.weapon_profile_id,
        )
        for declaration in firing_deck_declarations
    }
    if weapon_selection_keys != declaration_keys:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_weapon_selection_drift",
            message="Firing Deck selected weapons do not match declarations.",
            field="firing_deck_selection",
        )
    for weapon_selection in selection.weapon_selections:
        validation = _validate_firing_deck_weapon_against_catalog(
            state=state,
            weapon_selection=weapon_selection,
            army_catalog=army_catalog,
            proposal_request_id=proposal.proposal_request_id,
        )
        if validation is not None:
            return validation
    cargo_state = state.transport_cargo_state_for_transport(proposal.unit_instance_id)
    if cargo_state is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="firing_deck_transport_cargo_missing",
            message="Firing Deck requires a Transport cargo state.",
            field="firing_deck_selection",
        )
    resolution = resolve_firing_deck_selection(
        cargo_state=cargo_state,
        selection=selection,
        embarked_units=tuple(
            _unit_by_id(state=state, unit_instance_id=unit_id)
            for unit_id in cargo_state.embarked_unit_instance_ids
        ),
    )
    if not resolution.is_valid:
        violation = resolution.violations[0]
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code=violation.violation_code.value,
            message=violation.message,
            field="firing_deck_selection",
        )
    return resolution.ineligible_unit_instance_ids


def _validate_firing_deck_weapon_against_catalog(
    *,
    state: GameState,
    weapon_selection: FiringDeckWeaponSelection,
    army_catalog: ArmyCatalog,
    proposal_request_id: str,
) -> ShootingProposalValidationResult | None:
    embarked_unit = _unit_by_id(
        state=state, unit_instance_id=weapon_selection.embarked_unit_instance_id
    )
    model = _model_by_id(embarked_unit, weapon_selection.model_instance_id)
    if model is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="firing_deck_model_drift",
            message="Firing Deck selected model is not in the embarked unit.",
            field="firing_deck_selection",
        )
    if not _model_has_wargear_id(embarked_unit, model, weapon_selection.wargear_id):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="firing_deck_wargear_drift",
            message="Firing Deck selected wargear is not equipped by the embarked model.",
            field="firing_deck_selection",
        )
    catalog_profile = _weapon_profile_for_wargear(
        army_catalog=army_catalog,
        wargear_id=weapon_selection.wargear_id,
        weapon_profile_id=weapon_selection.weapon_profile.profile_id,
    )
    if catalog_profile != weapon_selection.weapon_profile:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="firing_deck_weapon_profile_drift",
            message="Firing Deck selected weapon profile does not match the catalog.",
            field="firing_deck_selection",
        )
    return None


def _available_weapon_by_declaration_key_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> dict[tuple[str, str, str, str | None, str | None], _AvailableWeapon]:
    return {
        _available_weapon_key(weapon): weapon
        for weapon in _available_weapons_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
            army_catalog=army_catalog,
            player_id=player_id,
            selected_shooting_type=selected_shooting_type,
        )
    }


def _available_weapon_key(
    weapon: _AvailableWeapon,
) -> tuple[str, str, str, str | None, str | None]:
    return (
        weapon["model_instance_id"],
        weapon["wargear_id"],
        weapon["weapon_profile"].profile_id,
        weapon.get("firing_deck_source_unit_instance_id"),
        weapon.get("firing_deck_source_model_instance_id"),
    )


def _component_unit_for_available_weapon(
    *,
    rules_unit: RulesUnitView,
    weapon: _AvailableWeapon,
) -> UnitInstance:
    return _component_unit_by_id(
        rules_unit=rules_unit,
        unit_instance_id=rules_unit.component_unit_id_for_model(weapon["model_instance_id"]),
    )


def _component_unit_for_declaration(
    *,
    rules_unit: RulesUnitView,
    declaration: WeaponDeclaration,
) -> UnitInstance:
    return _component_unit_by_id(
        rules_unit=rules_unit,
        unit_instance_id=rules_unit.component_unit_id_for_model(
            declaration.attacker_model_instance_id
        ),
    )


def _component_unit_by_id(*, rules_unit: RulesUnitView, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("component unit_instance_id", unit_instance_id)
    for component in rules_unit.components:
        if component.unit.unit_instance_id == requested_id:
            return component.unit
    raise GameLifecycleError("Rules-unit component unit_instance_id is unknown.")


def _declaration_available_weapon_key(
    declaration: WeaponDeclaration,
) -> tuple[str, str, str, str | None, str | None]:
    return (
        declaration.attacker_model_instance_id,
        declaration.wargear_id,
        declaration.weapon_profile_id,
        declaration.firing_deck_source_unit_instance_id,
        declaration.firing_deck_source_model_instance_id,
    )


def _available_weapons_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> tuple[_AvailableWeapon, ...]:
    weapons: list[_AvailableWeapon] = []
    for model in unit.own_models:
        weapons.extend(
            _available_own_weapons_for_model(
                state=state,
                model=model,
                unit=unit,
                army_catalog=army_catalog,
                player_id=player_id,
            )
        )
    weapons.extend(
        _available_firing_deck_weapons(
            state=state,
            transport_unit=unit,
            army_catalog=army_catalog,
        )
    )
    if (
        selected_shooting_type is ShootingType.ASSAULT
        or _advanced_unit_is_restricted_to_assault_weapons(
            state=state,
            unit=unit,
            player_id=player_id,
        )
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    if (
        selected_shooting_type is ShootingType.CLOSE_QUARTERS
        and not _unit_has_vehicle_or_monster_keyword(unit)
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_close_quarters_weapon_keyword(weapon["weapon_profile"])
        ]
    if selected_shooting_type is ShootingType.INDIRECT:
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.INDIRECT_FIRE)
        ]
    if selected_shooting_type is ShootingType.NORMAL and _unit_advanced_this_turn(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is ShootingType.INDIRECT and _unit_advanced_this_turn(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is None and _advanced_unit_is_restricted_to_assault_weapons(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    return tuple(
        sorted(
            weapons,
            key=lambda weapon: (
                weapon.get("firing_deck_source_unit_instance_id") or "",
                weapon.get("firing_deck_source_model_instance_id") or "",
                weapon["model_instance_id"],
                weapon["wargear_id"],
                weapon["weapon_profile"].profile_id,
            ),
        )
    )


def _available_weapons_for_rules_unit(
    *,
    state: GameState,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> tuple[_AvailableWeapon, ...]:
    weapons: list[_AvailableWeapon] = []
    for component in rules_unit.components:
        weapons.extend(
            _available_weapons_for_unit(
                state=state,
                unit=component.unit,
                army_catalog=army_catalog,
                player_id=player_id,
                selected_shooting_type=selected_shooting_type,
            )
        )
    if (
        selected_shooting_type is ShootingType.ASSAULT
        or _rules_unit_advanced_is_restricted_to_assault_weapons(
            state=state,
            rules_unit=rules_unit,
            player_id=player_id,
        )
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    if (
        selected_shooting_type is ShootingType.CLOSE_QUARTERS
        and not _rules_unit_has_vehicle_or_monster_keyword(rules_unit)
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_close_quarters_weapon_keyword(weapon["weapon_profile"])
        ]
    if selected_shooting_type is ShootingType.INDIRECT:
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.INDIRECT_FIRE)
        ]
    if selected_shooting_type is ShootingType.NORMAL and _rules_unit_advanced_this_turn(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is ShootingType.INDIRECT and _rules_unit_advanced_this_turn(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        weapons = []
    if selected_shooting_type is None and _rules_unit_advanced_is_restricted_to_assault_weapons(
        state=state,
        rules_unit=rules_unit,
        player_id=player_id,
    ):
        weapons = [
            weapon
            for weapon in weapons
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT)
        ]
    return tuple(
        sorted(
            weapons,
            key=lambda weapon: (
                weapon.get("firing_deck_source_unit_instance_id") or "",
                weapon.get("firing_deck_source_model_instance_id") or "",
                weapon["model_instance_id"],
                weapon["wargear_id"],
                weapon["weapon_profile"].profile_id,
            ),
        )
    )


def _available_weapons_for_model(
    *,
    model: ModelInstance,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
) -> tuple[_AvailableWeapon, ...]:
    weapons: list[_AvailableWeapon] = []
    for selection in unit.wargear_selections:
        if selection.model_profile_id != model.model_profile_id:
            continue
        for wargear_id in selection.wargear_ids:
            wargear = _wargear_by_id(army_catalog=army_catalog, wargear_id=wargear_id)
            for profile in wargear.weapon_profiles:
                if profile.range_profile.kind is RangeProfileKind.MELEE:
                    continue
                weapons.append(
                    {
                        "model_instance_id": model.model_instance_id,
                        "wargear_id": wargear_id,
                        "weapon_profile": profile,
                    }
                )
    return tuple(weapons)


def _available_own_weapons_for_model(
    *,
    state: GameState,
    model: ModelInstance,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None,
) -> tuple[_AvailableWeapon, ...]:
    owner_player_id = (
        rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id).owner_player_id
        if player_id is None
        else player_id
    )
    effects = state.persisting_effects_for_unit(unit.unit_instance_id)
    weapons: list[_AvailableWeapon] = []
    for weapon in _available_weapons_for_model(
        model=model,
        unit=unit,
        army_catalog=army_catalog,
    ):
        weapon_profile = weapon_profile_with_ranged_keyword_effects(
            weapon["weapon_profile"],
            effects,
            owner_player_id=owner_player_id,
        )
        if has_weapon_keyword(weapon_profile, WeaponKeyword.ONE_SHOT) and not (
            state.one_shot_weapon_available(
                model_instance_id=weapon["model_instance_id"],
                wargear_id=weapon["wargear_id"],
                weapon_profile_id=weapon_profile.profile_id,
            )
        ):
            continue
        weapons.append(
            {
                "model_instance_id": weapon["model_instance_id"],
                "wargear_id": weapon["wargear_id"],
                "weapon_profile": weapon_profile,
            }
        )
    return tuple(weapons)


def _available_firing_deck_weapons(
    *,
    state: GameState,
    transport_unit: UnitInstance,
    army_catalog: ArmyCatalog,
) -> tuple[_AvailableWeapon, ...]:
    cargo_state = state.transport_cargo_state_for_transport(transport_unit.unit_instance_id)
    if cargo_state is None or not cargo_state.embarked_unit_instance_ids:
        return ()
    if not _unit_has_keyword(transport_unit, "TRANSPORT"):
        return ()
    if _firing_deck_value_for_unit(unit=transport_unit, army_catalog=army_catalog) is None:
        return ()
    transport_model = _transport_firing_deck_model(transport_unit)
    weapons: list[_AvailableWeapon] = []
    for embarked_unit_id in cargo_state.embarked_unit_instance_ids:
        if _unit_has_already_shot(state=state, unit_instance_id=embarked_unit_id):
            continue
        embarked_unit = _unit_by_id(state=state, unit_instance_id=embarked_unit_id)
        for source_model in embarked_unit.own_models:
            for weapon in _available_weapons_for_model(
                model=source_model,
                unit=embarked_unit,
                army_catalog=army_catalog,
            ):
                if WeaponKeyword.ONE_SHOT in weapon["weapon_profile"].keywords:
                    continue
                weapons.append(
                    {
                        "model_instance_id": transport_model.model_instance_id,
                        "wargear_id": weapon["wargear_id"],
                        "weapon_profile": weapon["weapon_profile"],
                        "firing_deck_source_unit_instance_id": embarked_unit.unit_instance_id,
                        "firing_deck_source_model_instance_id": source_model.model_instance_id,
                    }
                )
    return tuple(weapons)


def _transport_firing_deck_model(unit: UnitInstance) -> ModelInstance:
    if not unit.own_models:
        raise GameLifecycleError("Transport unit requires at least one model.")
    return unit.own_models[0]


def _available_weapon_to_payload(weapon: _AvailableWeapon) -> AvailableWeaponPayload:
    payload: AvailableWeaponPayload = {
        "model_instance_id": weapon["model_instance_id"],
        "wargear_id": weapon["wargear_id"],
        "weapon_profile_id": weapon["weapon_profile"].profile_id,
        "weapon_profile": weapon["weapon_profile"].to_payload(),
    }
    source_unit_id = weapon.get("firing_deck_source_unit_instance_id")
    source_model_id = weapon.get("firing_deck_source_model_instance_id")
    if source_unit_id is not None and source_model_id is not None:
        payload["firing_deck_source_unit_instance_id"] = source_unit_id
        payload["firing_deck_source_model_instance_id"] = source_model_id
    return payload
