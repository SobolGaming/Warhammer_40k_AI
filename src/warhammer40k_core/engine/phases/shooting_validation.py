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
from warhammer40k_core.engine.phases.shooting_eligibility import *

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
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
# fmt: on

__all__ = (
    "_active_player_id",
    "_active_player_placed_unit_ids",
    "_army_catalog_for_handler",
    "_attack_sequence_for_selection_request",
    "_battlefield_scenario",
    "_canonical_keyword",
    "_decision_payload_object",
    "_enemy_placed_unit_ids",
    "_ensure_shooting_phase_state",
    "_firing_deck_value_for_rules_unit",
    "_firing_deck_value_for_unit",
    "_invalid_finite_decision_status",
    "_invalid_if_current_option_payload_drifted",
    "_model_by_id",
    "_model_has_wargear_id",
    "_payload_int",
    "_payload_string",
    "_proposal_request_from_decision_request",
    "_reject_invalid_declaration",
    "_rules_unit_has_vehicle_or_monster_keyword",
    "_rules_unit_label",
    "_ruleset_descriptor_for_handler",
    "_shooting_phase_status_payload",
    "_shooting_type_options",
    "_shooting_unit_options",
    "_terrain_features_for_state",
    "_unit_by_id",
    "_unit_has_keyword",
    "_unit_has_vehicle_or_monster_keyword",
    "_validate_attack_pools",
    "_validate_identifier",
    "_validate_identifier_tuple",
    "_validate_positive_int",
    "_validate_shooting_phase_state",
    "_wargear_by_id",
    "_weapon_profile_for_wargear",
)


def _attack_sequence_for_selection_request(
    *,
    state: GameState,
    request: DecisionRequest,
) -> AttackSequence:
    payload = _decision_payload_object(request.payload)
    sequence_id = _payload_string(payload, key="sequence_id")
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and out_of_phase_state.attack_sequence is not None
        and out_of_phase_state.attack_sequence.sequence_id == sequence_id
    ):
        return out_of_phase_state.attack_sequence
    shooting_state = state.shooting_phase_state
    if (
        shooting_state is not None
        and shooting_state.attack_sequence is not None
        and shooting_state.attack_sequence.sequence_id == sequence_id
    ):
        return shooting_state.attack_sequence
    raise GameLifecycleError("Attack sequence selection request has no active sequence.")


def _invalid_if_current_option_payload_drifted(
    *,
    state: GameState,
    result: DecisionResult,
    expected_request: DecisionRequest,
    invalid_reason: str,
) -> LifecycleStatus | None:
    try:
        expected_option = expected_request.option_by_id(result.selected_option_id)
    except DecisionError:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Attack sequence selection option is no longer legal.",
            payload={
                "invalid_reason": invalid_reason,
                "selected_option_id": result.selected_option_id,
            },
        )
    if result.payload != expected_option.payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Attack sequence selection payload drifted.",
            payload={
                "invalid_reason": invalid_reason,
                "selected_option_id": result.selected_option_id,
            },
        )
    return None


def _invalid_finite_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    invalid_reason: str,
) -> LifecycleStatus | None:
    if result.request_id != request.request_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "request_id"},
        )
    if result.decision_type != request.decision_type:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result type does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "decision_type"},
        )
    if result.actor_id != request.actor_id:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result actor does not match the pending request.",
            payload={"invalid_reason": invalid_reason, "field": "actor_id"},
        )
    if result.selected_option_id not in {option.option_id for option in request.options}:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result selected option is not pending.",
            payload={"invalid_reason": invalid_reason, "field": "selected_option_id"},
        )
    selected_payload = next(
        option.payload
        for option in request.options
        if option.option_id == result.selected_option_id
    )
    if result.payload != selected_payload:
        return LifecycleStatus.invalid(
            stage=state.stage,
            message="Decision result payload does not match the selected option.",
            payload={"invalid_reason": invalid_reason, "field": "payload"},
        )
    return None


def _proposal_request_from_decision_request(
    request: DecisionRequest,
) -> ShootingDeclarationProposalRequest:
    if request.decision_type != SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
        raise GameLifecycleError("Shooting proposal request has wrong decision_type.")
    payload = request.payload
    if not isinstance(payload, dict):
        raise GameLifecycleError("Shooting proposal DecisionRequest payload must be an object.")
    proposal_request = payload.get("proposal_request")
    if not isinstance(proposal_request, dict):
        raise GameLifecycleError("Shooting proposal DecisionRequest missing proposal_request.")
    raw = cast(dict[str, object], proposal_request)
    return ShootingDeclarationProposalRequest(
        request_id=_payload_string(raw, key="request_id"),
        active_player_id=_payload_string(raw, key="active_player_id"),
        battle_round=_payload_int(raw, key="battle_round"),
        unit_instance_id=_payload_string(raw, key="unit_instance_id"),
        source_decision_request_id=_payload_string(raw, key="source_decision_request_id"),
        source_decision_result_id=_payload_string(raw, key="source_decision_result_id"),
        visibility_cache_key=_payload_string(raw, key="visibility_cache_key"),
        proposal_kind=_payload_string(raw, key="proposal_kind"),
    )


def _reject_invalid_declaration(
    *,
    state: GameState,
    proposal_validation: ShootingProposalValidationResult,
    message: str,
) -> LifecycleStatus:
    return LifecycleStatus.invalid(
        stage=state.stage,
        message=message,
        payload={"proposal_validation": validate_json_value(proposal_validation.to_payload())},
    )


def _ensure_shooting_phase_state(*, state: GameState) -> ShootingPhaseState:
    current = state.shooting_phase_state
    active_player_id = _active_player_id(state)
    if current is not None:
        return current
    shooting_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    state.replace_shooting_phase_state(shooting_state)
    return shooting_state


def _validate_shooting_phase_state(state: GameState) -> None:
    if state.stage is not GameLifecycleStage.BATTLE:
        raise GameLifecycleError("Shooting phase requires battle stage.")
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        raise GameLifecycleError("Shooting phase requires SHOOTING phase.")
    _active_player_id(state)
    if state.battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    if state.shooting_phase_state is None:
        return
    shooting_state = state.shooting_phase_state
    if shooting_state.battle_round != state.battle_round:
        raise GameLifecycleError("shooting_phase_state battle round drift.")
    if shooting_state.active_player_id != state.active_player_id:
        raise GameLifecycleError("shooting_phase_state active player drift.")


def _battlefield_scenario(state: GameState) -> BattlefieldScenario:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    try:
        scenario = BattlefieldScenario(
            armies=tuple(state.army_definitions),
            battlefield_state=battlefield_state,
        )
        scenario.assert_all_mustered_models_placed_or_accounted(state.unavailable_model_ids())
    except PlacementError as exc:
        raise GameLifecycleError("Shooting battlefield scenario is invalid.") from exc
    return scenario


def _terrain_features_for_state(state: GameState) -> tuple[TerrainFeatureDefinition, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    return battlefield_state.terrain_features


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Shooting phase requires active_player_id.")
    return state.active_player_id


def _active_player_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    placed_army = battlefield_state.placed_army_for_player_or_none(player_id)
    if placed_army is None:
        return ()
    unit_ids: list[str] = []
    seen: set[str] = set()
    armies = tuple(state.army_definitions)
    for placement in placed_army.unit_placements:
        rules_unit_id = rules_unit_id_for_unit_id(
            armies=armies,
            unit_instance_id=placement.unit_instance_id,
        )
        if rules_unit_id in seen:
            continue
        seen.add(rules_unit_id)
        unit_ids.append(rules_unit_id)
    return tuple(sorted(unit_ids))


def _enemy_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    unit_ids: list[str] = []
    seen: set[str] = set()
    armies = tuple(state.army_definitions)
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        for placement in placed_army.unit_placements:
            rules_unit_id = rules_unit_id_for_unit_id(
                armies=armies,
                unit_instance_id=placement.unit_instance_id,
            )
            if rules_unit_id in seen:
                continue
            seen.add(rules_unit_id)
            unit_ids.append(rules_unit_id)
    return tuple(sorted(unit_ids))


def _unit_by_id(*, state: GameState, unit_instance_id: str) -> UnitInstance:
    requested_id = _validate_identifier("unit_instance_id", unit_instance_id)
    for army in state.army_definitions:
        for unit in army.units:
            if unit.unit_instance_id == requested_id:
                return unit
    raise GameLifecycleError("Shooting unit_instance_id is unknown.")


def _model_by_id(unit: UnitInstance, model_instance_id: str) -> ModelInstance | None:
    requested_id = _validate_identifier("model_instance_id", model_instance_id)
    for model in unit.own_models:
        if model.model_instance_id == requested_id:
            return model
    return None


def _model_has_wargear_id(unit: UnitInstance, model: ModelInstance, wargear_id: str) -> bool:
    requested_wargear_id = _validate_identifier("wargear_id", wargear_id)
    for selection in unit.wargear_selections:
        if selection.model_profile_id == model.model_profile_id:
            return requested_wargear_id in selection.wargear_ids
    return False


def _wargear_by_id(*, army_catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_wargear_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in army_catalog.wargear:
        if wargear.wargear_id == requested_wargear_id:
            return wargear
    raise GameLifecycleError("Shooting wargear_id is not in the ArmyCatalog.")


def _weapon_profile_for_wargear(
    *,
    army_catalog: ArmyCatalog,
    wargear_id: str,
    weapon_profile_id: str,
) -> WeaponProfile:
    wargear = _wargear_by_id(army_catalog=army_catalog, wargear_id=wargear_id)
    requested_profile_id = _validate_identifier("weapon_profile_id", weapon_profile_id)
    for profile in wargear.weapon_profiles:
        if profile.profile_id == requested_profile_id:
            return profile
    raise GameLifecycleError("Shooting weapon_profile_id is not in the selected Wargear.")


def _shooting_unit_options(
    *,
    state: GameState,
    unit_ids: tuple[str, ...],
    include_complete: bool,
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for unit_id in unit_ids:
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_id)
        options.append(
            DecisionOption(
                option_id=rules_unit.unit_instance_id,
                label=_rules_unit_label(rules_unit),
                payload={"unit_instance_id": rules_unit.unit_instance_id},
            )
        )
    if include_complete:
        options.append(
            DecisionOption(
                option_id=COMPLETE_SHOOTING_PHASE_OPTION_ID,
                label="Complete Shooting Phase",
                payload={
                    "submission_kind": COMPLETE_SHOOTING_PHASE_OPTION_ID,
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": state.active_player_id,
                    "phase_body_status": _COMPLETE_SHOOTING_PHASE_STATUS,
                    "skipped_unit_ids": list(unit_ids),
                },
            )
        )
    return tuple(options)


def _shooting_type_options(
    *,
    state: GameState,
    active_selection: ShootingUnitSelection,
    legal_types: tuple[ShootingType, ...],
) -> tuple[DecisionOption, ...]:
    options: list[DecisionOption] = []
    for shooting_type in legal_types:
        options.append(
            DecisionOption(
                option_id=shooting_type.value,
                label=f"{shooting_type.value.replace('_', ' ').title()} Shooting",
                payload={
                    "submission_kind": SELECT_SHOOTING_TYPE_DECISION_TYPE,
                    "game_id": state.game_id,
                    "battle_round": state.battle_round,
                    "phase": BattlePhase.SHOOTING.value,
                    "active_player_id": active_selection.player_id,
                    "unit_instance_id": active_selection.unit_instance_id,
                    "shooting_type": shooting_type.value,
                    "source_decision_request_id": active_selection.request_id,
                    "source_decision_result_id": active_selection.result_id,
                },
            )
        )
    return tuple(options)


def _shooting_phase_status_payload(
    *,
    state: GameState,
    phase_body_status: str,
    skipped_unit_ids: tuple[str, ...] = (),
) -> dict[str, JsonValue]:
    skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
    return {
        "game_id": state.game_id,
        "battle_round": state.battle_round,
        "active_player_id": state.active_player_id,
        "phase": BattlePhase.SHOOTING.value,
        "phase_body_status": phase_body_status,
        "skipped_unit_ids": list(skipped_ids),
    }


def _decision_payload_object(payload: JsonValue) -> dict[str, object]:
    if not isinstance(payload, dict):
        raise GameLifecycleError("Decision payload must be an object.")
    return cast(dict[str, object], payload)


def _payload_string(payload: dict[str, object], *, key: str) -> str:
    value = payload.get(key)
    if type(value) is not str:
        raise GameLifecycleError(f"Payload field {key} must be a string.")
    return _validate_identifier(key, value)


def _payload_int(payload: dict[str, object], *, key: str) -> int:
    value = payload.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"Payload field {key} must be an int.")
    return value


def _army_catalog_for_handler(handler: ShootingPhaseHandler) -> ArmyCatalog:
    if type(handler) is not ShootingPhaseHandler:
        raise GameLifecycleError("Shooting army catalog requires a ShootingPhaseHandler.")
    if handler.army_catalog is None:
        raise GameLifecycleError("Shooting phase requires an ArmyCatalog.")
    return handler.army_catalog


def _ruleset_descriptor_for_handler(handler: ShootingPhaseHandler) -> RulesetDescriptor:
    if type(handler) is not ShootingPhaseHandler:
        raise GameLifecycleError("Shooting ruleset descriptor requires a ShootingPhaseHandler.")
    if handler.ruleset_descriptor is None:
        raise GameLifecycleError("Shooting phase requires a RulesetDescriptor.")
    return handler.ruleset_descriptor


def _firing_deck_value_for_unit(
    *,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
) -> int | None:
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Firing Deck lookup requires an ArmyCatalog.")
    return unit_firing_deck_value(unit)


def _firing_deck_value_for_rules_unit(
    *,
    rules_unit: RulesUnitView,
    army_catalog: ArmyCatalog,
) -> int | None:
    values: list[int] = []
    for component in rules_unit.components:
        value = _firing_deck_value_for_unit(
            unit=component.unit,
            army_catalog=army_catalog,
        )
        if value is not None:
            values.append(value)
    if not values:
        return None
    if len(values) > 1:
        raise GameLifecycleError("Attached rules unit cannot expose multiple Firing Deck values.")
    return values[0]


def _unit_has_vehicle_or_monster_keyword(unit: UnitInstance) -> bool:
    return _unit_has_keyword(unit, "VEHICLE") or _unit_has_keyword(unit, "MONSTER")


def _rules_unit_has_vehicle_or_monster_keyword(rules_unit: RulesUnitView) -> bool:
    return any(
        _canonical_keyword(keyword) in {"VEHICLE", "MONSTER"} for keyword in rules_unit.keywords
    )


def _rules_unit_label(rules_unit: RulesUnitView) -> str:
    if not rules_unit.is_attached_rules_unit:
        component = next(iter(rules_unit.components))
        return component.unit.name
    return "Attached Unit: " + " / ".join(
        component.unit.name for component in rules_unit.components
    )


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    canonical = _canonical_keyword(keyword)
    return canonical in {_canonical_keyword(unit_keyword) for unit_keyword in unit.keywords}


def _canonical_keyword(keyword: str) -> str:
    return keyword.strip().upper().replace(" ", "_").replace("-", "_")


def _validate_attack_pools(values: object) -> tuple[RangedAttackPool, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError("ShootingPhaseState attack_pools must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    pools: list[RangedAttackPool] = []
    for value in raw_values:
        if type(value) is not RangedAttackPool:
            raise GameLifecycleError("ShootingPhaseState attack_pools must be RangedAttackPool.")
        pools.append(value)
    return tuple(pools)


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an int.")
    if value <= 0:
        raise GameLifecycleError(f"{field_name} must be greater than zero.")
    return value


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    raw_values = cast(tuple[object, ...], values)
    validated = tuple(_validate_identifier(field_name, value) for value in raw_values)
    if len(set(validated)) != len(validated):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return validated
