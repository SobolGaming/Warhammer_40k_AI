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
    from warhammer40k_core.engine.phases.shooting_targeting import _target_within_half_weapon_range, _snap_shooting_type_allowed_for_unit_target, _declaration_target_within_max_range, _unit_target_within_max_range, _unit_placements_for_rules_unit_or_none, _rules_unit_remained_stationary, _heavy_hit_roll_modifier_applies, _rules_unit_set_up_this_turn, _rules_unit_within_enemy_engagement_range, _target_visible_to_friendly_unit, _declaration_source_unit
    from warhammer40k_core.engine.phases.shooting_firing_deck import _declaration_source_model_id, _validate_firing_deck_selection, _validate_firing_deck_weapon_against_catalog, _available_weapon_by_declaration_key_for_rules_unit, _available_weapon_key, _component_unit_for_available_weapon, _component_unit_for_declaration, _component_unit_by_id, _declaration_available_weapon_key, _available_weapons_for_unit, _available_weapons_for_rules_unit, _available_weapons_for_model, _available_own_weapons_for_model, _available_firing_deck_weapons, _transport_firing_deck_model, _available_weapon_to_payload
    from warhammer40k_core.engine.phases.shooting_eligibility import _legal_shooting_unit_ids, _rules_unit_has_legal_shooting_declaration, _hidden_target_unit_ids, _detection_range_bonus_inches_by_target_id, _shot_source_unit_ids_for_detection_effects, _target_unit_ids_with_recent_ranged_attacks, _targeting_detection_context_fingerprint, _unit_has_legal_shooting_declaration, _legal_shooting_types_for_rules_unit, _cached_shooting_target_candidate_for_model, _shooting_unit_candidate_cache_key, _shooting_model_candidate_cache_key, _weapon_profile_cache_fingerprint, shooting_unit_can_select_to_shoot, shooting_unit_has_legal_declaration_against_targets, shooting_rules_unit_is_eligible_to_shoot, _rules_unit_state_unit_ids, _unit_can_select_to_shoot, _rules_unit_can_select_to_shoot, _advanced_unit_is_restricted_to_assault_weapons, _rules_unit_advanced_is_restricted_to_assault_weapons, _unit_advanced_this_turn, _rules_unit_advanced_this_turn, _unit_has_assault_ranged_weapon, _rules_unit_has_assault_ranged_weapon, _unit_has_indirect_ranged_weapon, _rules_unit_has_indirect_ranged_weapon, _unit_has_already_shot
    from warhammer40k_core.engine.phases.shooting_validation import _attack_sequence_for_selection_request, _invalid_if_current_option_payload_drifted, _invalid_finite_decision_status, _proposal_request_from_decision_request, _reject_invalid_declaration, _ensure_shooting_phase_state, _validate_shooting_phase_state, _battlefield_scenario, _terrain_features_for_state, _active_player_id, _active_player_placed_unit_ids, _enemy_placed_unit_ids, _unit_by_id, _model_by_id, _model_has_wargear_id, _wargear_by_id, _weapon_profile_for_wargear, _shooting_unit_options, _shooting_type_options, _shooting_phase_status_payload, _decision_payload_object, _payload_string, _payload_int, _army_catalog_for_handler, _ruleset_descriptor_for_handler, _firing_deck_value_for_unit, _firing_deck_value_for_rules_unit, _unit_has_vehicle_or_monster_keyword, _rules_unit_has_vehicle_or_monster_keyword, _rules_unit_label, _unit_has_keyword, _canonical_keyword, _validate_attack_pools, _validate_identifier, _validate_positive_int, _validate_identifier_tuple
# fmt: on

__all__ = (
    "_AttackPoolValidationResult",
    "_apply_phase13d_weapon_modifiers",
    "_attack_pools_for_proposal",
    "_attack_pools_or_validation",
    "_forced_shooting_type_for_out_of_phase",
    "_modified_shooting_weapon_profile",
    "_out_of_phase_allowed_target_unit_ids",
    "_out_of_phase_uses_fire_overwatch",
    "_runtime_modifier_registry",
    "_selected_shooting_type_for_declaration",
    "_shooting_candidate_with_target_restrictions",
    "_shooting_types_for_declaration_candidate",
    "_targeting_rule_ids_with_shooting_type",
    "_validate_declaration_submission",
    "_validate_duplicate_weapon_ability_selection",
    "_validate_model_pistol_exclusivity",
    "_validate_out_of_phase_declaration_submission",
)


def _validate_declaration_submission(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ShootingProposalValidationResult:
    out_of_phase_state = state.out_of_phase_shooting_state
    if (
        out_of_phase_state is not None
        and proposal.source_decision_request_id == out_of_phase_state.source_decision_request_id
        and proposal.source_decision_result_id == out_of_phase_state.source_decision_result_id
    ):
        return _validate_out_of_phase_declaration_submission(
            state=state,
            proposal=proposal,
            out_of_phase_state=out_of_phase_state,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
            shooting_target_restriction_hooks=shooting_target_restriction_hooks,
            runtime_modifier_registry=runtime_modifier_registry,
        )
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="wrong_context",
            message="Shooting declaration requires an active shooting selection.",
            field=None,
        )
    active_selection = shooting_state.active_selection
    if proposal.unit_instance_id != active_selection.unit_instance_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="proposal_unit_drift",
            message="Shooting declaration unit does not match active selection.",
            field="unit_instance_id",
        )
    if shooting_state.selected_shooting_type is None:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="shooting_type_not_selected",
            message="Shooting declaration requires a selected shooting type.",
            field="declarations",
        )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    if not _rules_unit_can_select_to_shoot(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
    ):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="shooting_unit_ineligible",
            message="Selected shooting unit is no longer eligible to shoot.",
            field="unit_instance_id",
        )
    attack_validation = _attack_pools_or_validation(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if isinstance(attack_validation, ShootingProposalValidationResult):
        return attack_validation
    return ShootingProposalValidationResult.valid(proposal_request_id=proposal.proposal_request_id)


def _validate_out_of_phase_declaration_submission(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    out_of_phase_state: OutOfPhaseShootingState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
) -> ShootingProposalValidationResult:
    if proposal.player_id != out_of_phase_state.player_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="proposal_player_drift",
            message="Out-of-phase shooting declaration player drift.",
            field="player_id",
        )
    if proposal.unit_instance_id != out_of_phase_state.selected_unit_instance_id:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="proposal_unit_drift",
            message="Out-of-phase shooting declaration unit drift.",
            field="unit_instance_id",
        )
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    if not _rules_unit_can_select_to_shoot(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=out_of_phase_state.player_id,
    ):
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="shooting_unit_ineligible",
            message="Out-of-phase shooting unit is no longer eligible to shoot.",
            field="unit_instance_id",
        )
    attack_validation = _attack_pools_or_validation(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        shooting_player_id=out_of_phase_state.player_id,
        out_of_phase_state=out_of_phase_state,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if isinstance(attack_validation, ShootingProposalValidationResult):
        return attack_validation
    return ShootingProposalValidationResult.valid(proposal_request_id=proposal.proposal_request_id)


def _attack_pools_for_proposal(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    decisions: DecisionController,
    result_id: str,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry,
    runtime_modifier_registry: RuntimeModifierRegistry,
    shooting_player_id: str | None = None,
    out_of_phase_state: OutOfPhaseShootingState | None = None,
) -> tuple[tuple[RangedAttackPool, ...], tuple[str, ...]]:
    result = _attack_pools_or_validation(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        attack_count_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
        attack_count_scope_prefix=result_id,
        shooting_player_id=shooting_player_id,
        out_of_phase_state=out_of_phase_state,
        shooting_target_restriction_hooks=shooting_target_restriction_hooks,
        runtime_modifier_registry=runtime_modifier_registry,
    )
    if isinstance(result, ShootingProposalValidationResult):
        raise GameLifecycleError("Accepted shooting declaration failed revalidation.")
    return result


type _AttackPoolValidationResult = (
    tuple[tuple[RangedAttackPool, ...], tuple[str, ...]] | ShootingProposalValidationResult
)


def _attack_pools_or_validation(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    attack_count_manager: DiceRollManager | None = None,
    attack_count_scope_prefix: str | None = None,
    shooting_player_id: str | None = None,
    out_of_phase_state: OutOfPhaseShootingState | None = None,
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry | None = None,
    runtime_modifier_registry: RuntimeModifierRegistry | None = None,
) -> _AttackPoolValidationResult:
    player_id = proposal.player_id if shooting_player_id is None else shooting_player_id
    rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    selected_shooting_type = _selected_shooting_type_for_declaration(
        state=state,
        out_of_phase_state=out_of_phase_state,
    )
    available_weapon_by_key = _available_weapon_by_declaration_key_for_rules_unit(
        state=state,
        rules_unit=rules_unit,
        army_catalog=army_catalog,
        player_id=player_id,
        selected_shooting_type=selected_shooting_type,
    )
    firing_deck_validation = _validate_firing_deck_selection(
        state=state,
        proposal=proposal,
        army_catalog=army_catalog,
    )
    if isinstance(firing_deck_validation, ShootingProposalValidationResult):
        return firing_deck_validation
    ineligible_unit_ids = firing_deck_validation
    allowed_out_of_phase_target_ids = _out_of_phase_allowed_target_unit_ids(
        state,
        out_of_phase_state,
    )
    proposal_target_unit_ids = tuple(
        sorted({declaration.target_unit_instance_id for declaration in proposal.declarations})
    )
    hidden_target_unit_ids = _hidden_target_unit_ids(
        state=state,
        target_unit_ids=proposal_target_unit_ids,
    )
    target_unit_ids_with_recent_ranged_attacks = _target_unit_ids_with_recent_ranged_attacks(
        state=state,
        target_unit_ids=proposal_target_unit_ids,
    )
    detection_range_bonus_by_target_id = _detection_range_bonus_inches_by_target_id(
        state=state,
        target_unit_ids=proposal_target_unit_ids,
    )
    attack_pools: list[RangedAttackPool] = []
    seen_declaration_keys: set[tuple[str, str, str, str | None, str | None]] = set()
    model_pistol_declaration_kind: dict[tuple[str, str], bool] = {}
    snap_target_unit_ids: set[str] = set()
    for declaration_index, declaration in enumerate(proposal.declarations, start=1):
        key = _declaration_available_weapon_key(declaration)
        if key in seen_declaration_keys:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="duplicate_weapon_declaration",
                message="Each model/wargear/profile/source declaration may be used once.",
                field="declarations",
            )
        seen_declaration_keys.add(key)
        weapon = available_weapon_by_key.get(key)
        if weapon is None:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_declaration_unavailable",
                message="Declared weapon is not available to the selected shooting unit.",
                field="declarations",
            )
        weapon_profile = weapon["weapon_profile"]
        if declaration.shooting_type is ShootingType.INDIRECT and not has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.INDIRECT_FIRE,
        ):
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="shooting_type_unavailable",
                message="Indirect shooting requires an Indirect Fire weapon profile.",
                field="declarations",
            )
        if (
            allowed_out_of_phase_target_ids is not None
            and declaration.target_unit_instance_id not in allowed_out_of_phase_target_ids
        ):
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="out_of_phase_target_unit_drift",
                message="Out-of-phase shooting declaration target is not allowed by its source.",
                field="declarations",
            )
        source_unit = _component_unit_for_declaration(
            rules_unit=rules_unit,
            declaration=declaration,
        )
        pistol_validation = _validate_model_pistol_exclusivity(
            state=state,
            selected_unit=source_unit,
            declaration=declaration,
            weapon_profile=weapon_profile,
            model_pistol_declaration_kind=model_pistol_declaration_kind,
            proposal_request_id=proposal.proposal_request_id,
        )
        if pistol_validation is not None:
            return pistol_validation
        candidate = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            attacker_unit=source_unit,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            weapon_profile=weapon_profile,
            target_unit_id=declaration.target_unit_instance_id,
            terrain_features=terrain_features,
            hidden_target_unit_ids=hidden_target_unit_ids,
            target_unit_ids_with_recent_ranged_attacks=target_unit_ids_with_recent_ranged_attacks,
            target_detection_range_bonus_inches=detection_range_bonus_by_target_id.get(
                declaration.target_unit_instance_id,
                0,
            ),
        )
        candidate = _shooting_candidate_with_target_restrictions(
            candidate=candidate,
            state=state,
            player_id=player_id,
            attacking_unit_instance_id=source_unit.unit_instance_id,
            target_unit_instance_id=declaration.target_unit_instance_id,
            registry=shooting_target_restriction_hooks,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            shooting_type=declaration.shooting_type,
        )
        if not candidate.is_legal:
            violation = candidate.violation_code
            if violation is None:
                raise GameLifecycleError("Illegal target candidate requires violation_code.")
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code=f"target_{violation.value}",
                message=candidate.message or "Declared target is not legal.",
                field="declarations",
            )
        target_rules_unit = rules_unit_view_by_id(
            state=state,
            unit_instance_id=declaration.target_unit_instance_id,
        )
        weapon_profile = weapon_profile_with_character_target_ap_effects(
            weapon_profile,
            state.persisting_effects_for_unit(source_unit.unit_instance_id),
            owner_player_id=player_id,
            target_keywords=target_rules_unit.keywords,
        )
        weapon_profile = _modified_shooting_weapon_profile(
            state=state,
            runtime_modifier_registry=_runtime_modifier_registry(runtime_modifier_registry),
            attacking_unit_instance_id=source_unit.unit_instance_id,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            target_unit_instance_id=declaration.target_unit_instance_id,
            profile=weapon_profile,
        )
        ability_selection_validation = _validate_duplicate_weapon_ability_selection(
            proposal=proposal,
            declaration=declaration,
            declaration_index=declaration_index,
            weapon_profile=weapon_profile,
            target_rules_unit=target_rules_unit,
            player_id=player_id,
        )
        if ability_selection_validation is not None:
            return ability_selection_validation
        allowed_shooting_types = _shooting_types_for_declaration_candidate(
            state=state,
            scenario=scenario,
            candidate=candidate,
            declaration=declaration,
            unit=source_unit,
            rules_unit=rules_unit,
            weapon_profile=weapon_profile,
            player_id=player_id,
            out_of_phase_state=out_of_phase_state,
            selected_shooting_type=selected_shooting_type,
            army_catalog=army_catalog,
        )
        if declaration.shooting_type not in allowed_shooting_types:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="shooting_type_unavailable",
                message="Declared shooting type is not available for this weapon and target.",
                field="declarations",
            )
        if declaration.shooting_type is ShootingType.SNAP:
            snap_target_unit_ids.add(declaration.target_unit_instance_id)
        if attack_count_manager is None:
            attacks = unresolved_attacks_for_validation(weapon_profile)
        else:
            if attack_count_scope_prefix is None:
                raise GameLifecycleError("Random Attacks resolution requires a scope prefix.")
            attacks = attacks_for_profile(
                weapon_profile,
                manager=attack_count_manager,
                scope_id=(
                    f"{attack_count_scope_prefix}:declaration-{declaration_index:03d}:"
                    f"{declaration.attacker_model_instance_id}:{declaration.wargear_id}:"
                    f"{declaration.weapon_profile_id}:{declaration.target_unit_instance_id}:"
                    "attacks"
                ),
                actor_id=proposal.player_id,
            )
        target_within_half_range = _target_within_half_weapon_range(
            scenario=scenario,
            declaration=declaration,
            weapon_profile=weapon_profile,
            target_in_range_model_ids=candidate.target_in_range_model_ids,
        )
        attacks, targeting_rule_ids, hit_roll_modifier = _apply_phase13d_weapon_modifiers(
            state=state,
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            rules_unit=rules_unit,
            target_rules_unit=target_rules_unit,
            weapon_profile=weapon_profile,
            shooting_type=declaration.shooting_type,
            base_attacks=attacks,
            base_targeting_rule_ids=candidate.targeting_rule_ids,
            base_hit_roll_modifier=candidate.hit_roll_modifier,
            target_within_half_range=target_within_half_range,
            terrain_features=terrain_features,
            player_id=player_id,
            out_of_phase_state=out_of_phase_state,
        )
        if _out_of_phase_uses_fire_overwatch(out_of_phase_state):
            targeting_rule_ids = (*targeting_rule_ids, FIRE_OVERWATCH_RULE_ID)
        targeting_rule_ids = _targeting_rule_ids_with_shooting_type(
            shooting_type=declaration.shooting_type,
            targeting_rule_ids=targeting_rule_ids,
        )
        attack_pools.append(
            RangedAttackPool.from_declaration(
                declaration=declaration,
                weapon_profile=weapon_profile,
                attacks=attacks,
                target_visible_model_ids=candidate.target_visible_model_ids,
                target_in_range_model_ids=candidate.target_in_range_model_ids,
                hit_roll_modifier=hit_roll_modifier,
                targeting_rule_ids=targeting_rule_ids,
            )
        )
    if len(snap_target_unit_ids) > 1:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="snap_shooting_multiple_targets",
            message="Snap Shooting declarations must target one enemy unit.",
            field="declarations",
        )
    return (tuple(attack_pools), ineligible_unit_ids)


def _validate_duplicate_weapon_ability_selection(
    *,
    proposal: ShootingDeclarationProposal,
    declaration: WeaponDeclaration,
    declaration_index: int,
    weapon_profile: WeaponProfile,
    target_rules_unit: RulesUnitView,
    player_id: str,
) -> ShootingProposalValidationResult | None:
    ability_by_id: dict[str, AbilityDescriptor] = {
        ability.ability_id: ability for ability in weapon_profile.abilities
    }
    selected_abilities: list[AbilityDescriptor] = []
    for selected_id in declaration.selected_weapon_ability_ids:
        selected_ability = ability_by_id.get(selected_id)
        if selected_ability is None:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_ability_selection_unavailable",
                message="Selected weapon ability ID is not on the declared weapon profile.",
                field="declarations",
            )
        if selected_ability.ability_kind is not AbilityKind.ANTI_KEYWORD:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_ability_selection_unsupported",
                message="This shooting declaration only supports duplicate Anti selections.",
                field="declarations",
            )
        selected_abilities.append(selected_ability)

    selected_anti_ids: tuple[str, ...] = tuple(
        ability.ability_id
        for ability in selected_abilities
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD
    )
    selection_request = weapon_ability_selection_request(
        weapon_profile,
        AbilityKind.ANTI_KEYWORD,
        target_keywords=target_rules_unit.keywords,
        actor_id=player_id,
        request_id=(
            f"{proposal.proposal_request_id}:declaration-{declaration_index:03d}:anti-keyword"
        ),
        source_context={
            "phase": BattlePhase.SHOOTING.value,
            "proposal_request_id": proposal.proposal_request_id,
            "declaration_index": declaration_index,
            "target_unit_instance_id": target_rules_unit.unit_instance_id,
        },
    )
    if selection_request is None:
        if selected_anti_ids:
            return ShootingProposalValidationResult.invalid(
                proposal_request_id=proposal.proposal_request_id,
                violation_code="weapon_ability_selection_not_required",
                message="Selected Anti ability ID was supplied when no duplicate choice exists.",
                field="declarations",
            )
        return None

    legal_ids = {option.option_id for option in selection_request.options}
    if len(selected_anti_ids) != 1:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="weapon_ability_selection_required",
            message="Duplicate matching Anti abilities require exactly one selected ability ID.",
            field="declarations",
        )
    if selected_anti_ids[0] not in legal_ids:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal.proposal_request_id,
            violation_code="weapon_ability_selection_invalid",
            message="Selected Anti ability ID is not legal for this target.",
            field="declarations",
        )
    return None


def _shooting_candidate_with_target_restrictions(
    *,
    candidate: ShootingTargetCandidate,
    state: GameState,
    player_id: str,
    attacking_unit_instance_id: str,
    target_unit_instance_id: str,
    registry: ShootingTargetRestrictionHookRegistry | None,
    attacker_model_instance_id: str | None = None,
    shooting_type: ShootingType | None = None,
) -> ShootingTargetCandidate:
    if type(candidate) is not ShootingTargetCandidate:
        raise GameLifecycleError("Shooting target restriction requires a target candidate.")
    if not candidate.is_legal:
        return candidate
    if registry is None:
        return candidate
    if type(registry) is not ShootingTargetRestrictionHookRegistry:
        raise GameLifecycleError("Shooting target restriction requires a registry.")
    restrictions = registry.restrictions_for(
        ShootingTargetRestrictionContext(
            state=state,
            player_id=player_id,
            battle_round=state.battle_round,
            attacking_unit_instance_id=attacking_unit_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            shooting_type=shooting_type,
        )
    )
    if not restrictions:
        return candidate
    restriction = restrictions[0]
    return ShootingTargetCandidate.invalid(
        attacker_unit_instance_id=candidate.attacker_unit_instance_id,
        weapon_profile_id=candidate.weapon_profile_id,
        target_unit_instance_id=candidate.target_unit_instance_id,
        violation_code=ShootingTargetViolationCode.RUNTIME_TARGET_RESTRICTION,
        message=restriction.message,
        visibility_cache_key=candidate.visibility_cache_key,
        target_visible_model_ids=candidate.target_visible_model_ids,
        target_in_range_model_ids=candidate.target_in_range_model_ids,
        line_of_sight_witness=candidate.line_of_sight_witness,
        observer_model_id=candidate.observer_model_id,
        hit_roll_modifier=candidate.hit_roll_modifier,
        targeting_rule_ids=(*candidate.targeting_rule_ids, restriction.hook_id),
    )


def _modified_shooting_weapon_profile(
    *,
    state: GameState,
    runtime_modifier_registry: RuntimeModifierRegistry,
    attacking_unit_instance_id: str,
    attacker_model_instance_id: str,
    target_unit_instance_id: str,
    profile: WeaponProfile,
) -> WeaponProfile:
    return runtime_modifier_registry.modified_weapon_profile(
        WeaponProfileModifierContext(
            state=state,
            source_phase=BattlePhase.SHOOTING,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attacker_model_instance_id=attacker_model_instance_id,
            target_unit_instance_id=target_unit_instance_id,
            weapon_profile=profile,
        )
    )


def _runtime_modifier_registry(
    runtime_modifier_registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if runtime_modifier_registry is None:
        return RuntimeModifierRegistry.empty()
    if type(runtime_modifier_registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Runtime modifier registry must be a registry.")
    return runtime_modifier_registry


def _out_of_phase_allowed_target_unit_ids(
    state: GameState,
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> tuple[str, ...] | None:
    if not _out_of_phase_uses_fire_overwatch(out_of_phase_state):
        return None
    if out_of_phase_state is None:
        raise GameLifecycleError("Fire Overwatch out-of-phase state is missing.")
    source_context = out_of_phase_state.source_context
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Fire Overwatch source context must be an object.")
    triggering_unit_id = source_context.get("triggering_enemy_unit_instance_id")
    if type(triggering_unit_id) is not str:
        raise GameLifecycleError("Fire Overwatch source context is missing triggering unit id.")
    return (
        rules_unit_id_for_unit_id(
            armies=tuple(state.army_definitions),
            unit_instance_id=_validate_identifier(
                "Fire Overwatch triggering unit id",
                triggering_unit_id,
            ),
        ),
    )


def _out_of_phase_uses_fire_overwatch(
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> bool:
    return (
        out_of_phase_state is not None
        and out_of_phase_state.source_rule_id == FIRE_OVERWATCH_RULE_ID
    )


def _forced_shooting_type_for_out_of_phase(
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> ShootingType | None:
    if _out_of_phase_uses_fire_overwatch(out_of_phase_state):
        return ShootingType.SNAP
    return None


def _selected_shooting_type_for_declaration(
    *,
    state: GameState,
    out_of_phase_state: OutOfPhaseShootingState | None,
) -> ShootingType | None:
    forced = _forced_shooting_type_for_out_of_phase(out_of_phase_state)
    if forced is not None:
        return forced
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        return None
    if shooting_state.selected_shooting_type is None:
        return None
    return shooting_state.selected_shooting_type.shooting_type


def _shooting_types_for_declaration_candidate(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    candidate: ShootingTargetCandidate,
    declaration: WeaponDeclaration,
    unit: UnitInstance,
    rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    player_id: str,
    out_of_phase_state: OutOfPhaseShootingState | None,
    selected_shooting_type: ShootingType | None,
    army_catalog: ArmyCatalog,
) -> tuple[ShootingType, ...]:
    forced_shooting_type = _forced_shooting_type_for_out_of_phase(out_of_phase_state)
    if forced_shooting_type is not None:
        if forced_shooting_type is not ShootingType.SNAP:
            raise GameLifecycleError("Unsupported forced shooting type.")
        if candidate.target_visible_model_ids and _declaration_target_within_max_range(
            scenario=scenario,
            declaration=declaration,
            target_in_range_model_ids=candidate.target_visible_model_ids,
            range_inches=24,
        ):
            return (ShootingType.SNAP,)
        return ()
    if selected_shooting_type is not None:
        return _shooting_types_for_selected_type_for_rules_unit(
            state=state,
            base_types=candidate.shooting_types,
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
        if ShootingType.NORMAL in candidate.shooting_types and has_weapon_keyword(
            weapon_profile,
            WeaponKeyword.ASSAULT,
        ):
            return (ShootingType.ASSAULT,)
        return ()
    return candidate.shooting_types


def _targeting_rule_ids_with_shooting_type(
    *,
    shooting_type: ShootingType,
    targeting_rule_ids: tuple[str, ...],
) -> tuple[str, ...]:
    rule_ids = list(targeting_rule_ids)
    if shooting_type is ShootingType.ASSAULT:
        rule_ids.append(ASSAULT_RULE_ID)
    elif shooting_type is ShootingType.CLOSE_QUARTERS:
        rule_ids.append(CLOSE_QUARTERS_RULE_ID)
    elif shooting_type is ShootingType.SNAP:
        rule_ids.append(SNAP_SHOOTING_RULE_ID)
    elif shooting_type in {ShootingType.NORMAL, ShootingType.INDIRECT}:
        pass
    else:
        raise GameLifecycleError("Unsupported shooting type for targeting rule IDs.")
    return tuple(dict.fromkeys(rule_ids))


def _validate_model_pistol_exclusivity(
    *,
    state: GameState,
    selected_unit: UnitInstance,
    declaration: WeaponDeclaration,
    weapon_profile: WeaponProfile,
    model_pistol_declaration_kind: dict[tuple[str, str], bool],
    proposal_request_id: str,
) -> ShootingProposalValidationResult | None:
    source_unit = _declaration_source_unit(
        state=state,
        selected_unit=selected_unit,
        declaration=declaration,
    )
    if _unit_has_vehicle_or_monster_keyword(source_unit):
        return None
    source_model_id = _declaration_source_model_id(declaration)
    model_key = (source_unit.unit_instance_id, source_model_id)
    is_close_quarters = has_close_quarters_weapon_keyword(weapon_profile)
    existing = model_pistol_declaration_kind.get(model_key)
    if existing is not None and existing != is_close_quarters:
        return ShootingProposalValidationResult.invalid(
            proposal_request_id=proposal_request_id,
            violation_code="mixed_close_quarters_non_close_quarters_declaration",
            message=(
                "A non-Monster/Vehicle model cannot shoot close-quarters and "
                "non-close-quarters weapons together."
            ),
            field="declarations",
        )
    model_pistol_declaration_kind[model_key] = is_close_quarters
    return None


def _apply_phase13d_weapon_modifiers(
    *,
    state: GameState,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    rules_unit: RulesUnitView,
    target_rules_unit: RulesUnitView,
    weapon_profile: WeaponProfile,
    shooting_type: ShootingType,
    base_attacks: int,
    base_targeting_rule_ids: tuple[str, ...],
    base_hit_roll_modifier: int,
    target_within_half_range: bool,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    player_id: str | None = None,
    out_of_phase_state: OutOfPhaseShootingState | None = None,
) -> tuple[int, tuple[str, ...], int]:
    attacks = base_attacks
    hit_roll_modifier = base_hit_roll_modifier
    targeting_rule_ids: list[str] = list(base_targeting_rule_ids)

    rapid_bonus = rapid_fire_attack_bonus(
        weapon_profile,
        target_within_half_range=target_within_half_range,
        target_keywords=target_rules_unit.keywords,
    )
    if rapid_bonus > 0:
        attacks += rapid_bonus
        targeting_rule_ids.append(rapid_fire_rule_id(rapid_bonus))

    if has_weapon_keyword(weapon_profile, WeaponKeyword.BLAST):
        blast_bonus = blast_attack_bonus(target_model_count=len(target_rules_unit.alive_models()))
        if blast_bonus > 0:
            attacks += blast_bonus
            targeting_rule_ids.append(blast_rule_id(blast_bonus))

    melta_bonus = melta_damage_bonus(
        weapon_profile,
        target_within_half_range=target_within_half_range,
        target_keywords=target_rules_unit.keywords,
    )
    if melta_bonus > 0:
        targeting_rule_ids.append(melta_rule_id(melta_bonus))

    if has_weapon_keyword(
        weapon_profile,
        WeaponKeyword.HEAVY,
    ) and _heavy_hit_roll_modifier_applies(
        state=state,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        rules_unit=rules_unit,
        player_id=player_id,
        out_of_phase_state=out_of_phase_state,
    ):
        hit_roll_modifier += 1
        targeting_rule_ids.append(heavy_rule_id())

    if shooting_type is ShootingType.INDIRECT and has_weapon_keyword(
        weapon_profile, WeaponKeyword.INDIRECT_FIRE
    ):
        if INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID not in targeting_rule_ids:
            targeting_rule_ids.append(INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID)
        targeting_rule_ids.append(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID)
        if _rules_unit_remained_stationary(
            state=state,
            rules_unit=rules_unit,
            player_id=player_id,
        ) and (
            _target_visible_to_friendly_unit(
                state=state,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                target_unit_instance_id=target_rules_unit.unit_instance_id,
                terrain_features=terrain_features,
                player_id=player_id,
            )
        ):
            targeting_rule_ids.append(INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID)

    return attacks, tuple(dict.fromkeys(targeting_rule_ids)), hit_roll_modifier
