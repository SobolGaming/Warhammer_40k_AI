# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.shooting_imports import *
from warhammer40k_core.engine.phases.shooting_model import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord, RangedAttackHistoryRecord
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
    from warhammer40k_core.engine.phases.shooting_model import SELECT_SHOOTING_UNIT_DECISION_TYPE, SELECT_SHOOTING_TYPE_DECISION_TYPE, SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE, COMPLETE_SHOOTING_PHASE_OPTION_ID, _COMPLETE_SHOOTING_PHASE_STATUS, _default_stratagem_index, ShootingUnitSelectionPayload, ShootingTypeSelectionPayload, ShootingPhaseStatePayload, OutOfPhaseShootingStatePayload, ShootingDeclarationProposalRequestPayload, ShootingDeclarationDecisionPayload, _AvailableWeapon, _ShootingUnitCandidateCacheKey, _ShootingModelCandidateCacheKey, _ShootingModelCandidateCache, ShootingUnitSelection, ShootingTypeSelection, ShootingPhaseState, OutOfPhaseShootingState
    from warhammer40k_core.engine.phases.shooting_reactions import _complete_out_of_phase_shooting, _request_active_shooting_phase_stratagem_if_available, _request_after_unit_selected_as_target_stratagem_if_available, _request_selected_to_shoot_stratagem_if_available, _resolve_completed_shooting_attack_sequence_continuation, _request_friendly_unit_has_shot_stratagem_if_available, _request_enemy_unit_has_shot_stratagem_if_available, _request_shooting_end_surge_if_available, _eligible_triggered_movement_units_from_shooting_grants, _shooting_end_surge_grant_distance_bonus, _shooting_end_surge_distance_roll_spec, _attack_sequence_completed_event_id, _friendly_unit_has_shot_timing_window_id, _active_shooting_phase_stratagem_timing_window_id, _selected_to_shoot_timing_window_id, _selected_as_target_timing_window_id, _enemy_unit_has_shot_timing_window_id, _target_unit_ids_for_attack_sequence, _stratagem_used_for_context, _successful_hit_target_unit_ids_for_sequence, _destroyed_target_unit_ids_for_sequence, _destroyed_enemy_unit_ids_for_sequence, _shooting_end_surge_event_already_processed
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
    "SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE",
    "SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE",
    "ShootingPhaseHandler",
    "_request_shooting_phase_start_rule_if_available",
    "_shooting_phase_start_faction_rule_drift_reason",
    "invalid_catalog_post_shoot_decision_status",
    "invalid_shooting_phase_start_faction_rule_status",
)


@dataclass(frozen=True, slots=True)
class ShootingPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None
    army_catalog: ArmyCatalog | None = None
    stratagem_index: StratagemCatalogIndex = field(default_factory=_default_stratagem_index)
    shooting_unit_selected_hooks: ShootingUnitSelectedHookRegistry = field(
        default_factory=ShootingUnitSelectedHookRegistry.empty
    )
    shooting_unit_selected_grant_hooks: ShootingUnitSelectedGrantRegistry = field(
        default_factory=ShootingUnitSelectedGrantRegistry.empty
    )
    shooting_target_restriction_hooks: ShootingTargetRestrictionHookRegistry = field(
        default_factory=ShootingTargetRestrictionHookRegistry.empty
    )
    shooting_phase_start_hooks: ShootingPhaseStartHookRegistry = field(
        default_factory=ShootingPhaseStartHookRegistry.empty
    )
    shooting_end_surge_hooks: ShootingEndSurgeHookRegistry = field(
        default_factory=ShootingEndSurgeHookRegistry.empty
    )
    attack_sequence_completed_hooks: AttackSequenceCompletedHookRegistry = field(
        default_factory=AttackSequenceCompletedHookRegistry.empty
    )
    stratagem_cost_modifier_registry: StratagemCostModifierRegistry = field(
        default_factory=StratagemCostModifierRegistry.empty
    )
    runtime_modifier_registry: RuntimeModifierRegistry = field(
        default_factory=RuntimeModifierRegistry.empty
    )

    def __post_init__(self) -> None:
        if (
            self.ruleset_descriptor is not None
            and type(self.ruleset_descriptor) is not RulesetDescriptor
        ):
            raise GameLifecycleError(
                "ShootingPhaseHandler ruleset_descriptor must be a RulesetDescriptor."
            )
        if self.army_catalog is not None and type(self.army_catalog) is not ArmyCatalog:
            raise GameLifecycleError("ShootingPhaseHandler army_catalog must be an ArmyCatalog.")
        from warhammer40k_core.engine.stratagems import StratagemCatalogIndex

        if type(self.stratagem_index) is not StratagemCatalogIndex:
            raise GameLifecycleError("ShootingPhaseHandler stratagem_index must be an index.")
        if type(self.shooting_unit_selected_hooks) is not ShootingUnitSelectedHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_unit_selected_hooks must be a registry."
            )
        if type(self.shooting_unit_selected_grant_hooks) is not ShootingUnitSelectedGrantRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_unit_selected_grant_hooks must be a registry."
            )
        if type(self.shooting_target_restriction_hooks) is not (
            ShootingTargetRestrictionHookRegistry
        ):
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_target_restriction_hooks must be a registry."
            )
        if type(self.shooting_phase_start_hooks) is not ShootingPhaseStartHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_phase_start_hooks must be a registry."
            )
        if type(self.shooting_end_surge_hooks) is not ShootingEndSurgeHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler shooting_end_surge_hooks must be a registry."
            )
        if type(self.attack_sequence_completed_hooks) is not AttackSequenceCompletedHookRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler attack_sequence_completed_hooks must be a registry."
            )
        if type(self.stratagem_cost_modifier_registry) is not StratagemCostModifierRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler stratagem_cost_modifier_registry must be a registry."
            )
        if type(self.runtime_modifier_registry) is not RuntimeModifierRegistry:
            raise GameLifecycleError(
                "ShootingPhaseHandler runtime_modifier_registry must be a registry."
            )

    @property
    def phase(self) -> BattlePhase:
        return BattlePhase.SHOOTING

    def begin_phase(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
        reaction_queue: ReactionQueue | None = None,
    ) -> LifecycleStatus:
        del reaction_queue
        _validate_shooting_phase_state(state)
        if state.shooting_phase_state is None:
            phase_start_status = _request_shooting_phase_start_rule_if_available(
                handler=self,
                state=state,
                decisions=decisions,
            )
            if phase_start_status is not None:
                return phase_start_status
        shooting_state = _ensure_shooting_phase_state(state=state)
        if shooting_state.pending_completed_attack_sequence is not None:
            completion_status = _resolve_completed_shooting_attack_sequence_continuation(
                handler=self,
                state=state,
                decisions=decisions,
                completed_sequence=shooting_state.pending_completed_attack_sequence,
            )
            if completion_status is not None:
                return completion_status
            shooting_state = _ensure_shooting_phase_state(state=state)
            shooting_state = shooting_state.with_pending_completed_attack_sequence(None)
            state.replace_shooting_phase_state(shooting_state)
        if shooting_state.attack_sequence is not None:
            completed_candidate = shooting_state.attack_sequence
            target_stratagem_status = _request_after_unit_selected_as_target_stratagem_if_available(
                state=state,
                decisions=decisions,
                stratagem_index=self.stratagem_index,
                stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
                attack_sequence=shooting_state.attack_sequence,
            )
            if target_stratagem_status is not None:
                return target_stratagem_status
            attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
                state=state,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                attack_sequence=shooting_state.attack_sequence,
                already_allocated_model_ids=shooting_state.allocated_model_ids_this_phase,
                stratagem_index=self.stratagem_index,
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
            shooting_state = shooting_state.with_attack_sequence_update(
                attack_sequence=attack_sequence,
                allocated_model_ids_this_phase=allocated_model_ids,
            )
            state.replace_shooting_phase_state(shooting_state)
            if status is not None:
                return status
            if attack_sequence is None:
                shooting_state = shooting_state.with_pending_completed_attack_sequence(
                    completed_candidate
                )
                state.replace_shooting_phase_state(shooting_state)
                completion_status = _resolve_completed_shooting_attack_sequence_continuation(
                    handler=self,
                    state=state,
                    decisions=decisions,
                    completed_sequence=completed_candidate,
                )
                if completion_status is not None:
                    return completion_status
                shooting_state = _ensure_shooting_phase_state(state=state)
                shooting_state = shooting_state.with_pending_completed_attack_sequence(None)
                state.replace_shooting_phase_state(shooting_state)
        if shooting_state.phase_complete:
            decisions.event_log.append(
                "shooting_phase_completed",
                _shooting_phase_status_payload(
                    state=state,
                    phase_body_status="complete",
                    skipped_unit_ids=shooting_state.skipped_unit_ids,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_shooting_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                    skipped_unit_ids=shooting_state.skipped_unit_ids,
                ),
            )
        if (
            shooting_state.active_selection is not None
            and shooting_state.selected_shooting_type is None
        ):
            selected_to_shoot_stratagem_status = _request_selected_to_shoot_stratagem_if_available(
                state=state,
                decisions=decisions,
                shooting_state=shooting_state,
                stratagem_index=self.stratagem_index,
                stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
            )
            if selected_to_shoot_stratagem_status is not None:
                return selected_to_shoot_stratagem_status
            return _request_shooting_type_selection(
                state=state,
                decisions=decisions,
                shooting_state=shooting_state,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
        if (
            shooting_state.active_selection is not None
            and shooting_state.selected_shooting_type is not None
        ):
            return _request_shooting_declaration(
                state=state,
                decisions=decisions,
                active_selection=shooting_state.active_selection,
                selected_shooting_type=shooting_state.selected_shooting_type.shooting_type,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )

        active_stratagem_status = _request_active_shooting_phase_stratagem_if_available(
            state=state,
            decisions=decisions,
            shooting_state=shooting_state,
            stratagem_index=self.stratagem_index,
            stratagem_cost_modifier_registry=self.stratagem_cost_modifier_registry,
        )
        if active_stratagem_status is not None:
            return active_stratagem_status

        legal_unit_ids = _legal_shooting_unit_ids(
            state=state,
            shooting_state=shooting_state,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
            shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
        )
        if not legal_unit_ids:
            state.replace_shooting_phase_state(shooting_state.with_phase_complete())
            decisions.event_log.append(
                "shooting_phase_completed",
                _shooting_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                ),
            )
            return LifecycleStatus.advanced(
                stage=GameLifecycleStage.BATTLE,
                payload=_shooting_phase_status_payload(
                    state=state,
                    phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                ),
            )

        request = DecisionRequest(
            request_id=state.next_decision_request_id(),
            decision_type=SELECT_SHOOTING_UNIT_DECISION_TYPE,
            actor_id=_active_player_id(state),
            payload={
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": _active_player_id(state),
            },
            options=_shooting_unit_options(
                state=state,
                unit_ids=legal_unit_ids,
                include_complete=True,
            ),
        )
        decisions.request_decision(request)
        return LifecycleStatus.waiting_for_decision(
            stage=GameLifecycleStage.BATTLE,
            decision_request=request,
            payload={
                "phase": BattlePhase.SHOOTING.value,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "legal_unit_count": len(legal_unit_ids),
            },
        )

    def advance_out_of_phase_shooting_if_needed(
        self,
        *,
        state: GameState,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        out_of_phase_state = state.out_of_phase_shooting_state
        if out_of_phase_state is None:
            return None
        if out_of_phase_state.attack_sequence is None:
            if out_of_phase_state.attack_pools:
                return _complete_out_of_phase_shooting(
                    state=state,
                    decisions=decisions,
                    completed_state=out_of_phase_state,
                )
            return None
        completed_candidate = out_of_phase_state.attack_sequence
        attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            attack_sequence=out_of_phase_state.attack_sequence,
            already_allocated_model_ids=out_of_phase_state.allocated_model_ids,
            stratagem_index=self.stratagem_index,
            runtime_modifier_registry=self.runtime_modifier_registry,
        )
        completed_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )
        state.replace_out_of_phase_shooting_state(completed_state)
        if status is not None:
            return status
        if completed_state.attack_sequence is not None:
            raise GameLifecycleError("Out-of-phase shooting completion state drift.")
        completion_hook_status = self.attack_sequence_completed_hooks.resolve_completed_sequence(
            AttackSequenceCompletedContext(
                state=state,
                decisions=decisions,
                dice_manager=DiceRollManager(state.game_id, event_log=decisions.event_log),
                runtime_modifier_registry=self.runtime_modifier_registry,
                source_phase=completed_candidate.source_phase,
                attack_sequence=completed_candidate,
                attack_sequence_completed_event_id=attack_sequence_completed_event_id(
                    decisions=decisions,
                    attack_sequence=completed_candidate,
                ),
            )
        )
        if completion_hook_status is not None:
            return completion_hook_status
        return _complete_out_of_phase_shooting(
            state=state,
            decisions=decisions,
            completed_state=completed_state,
        )

    def invalid_declaration_submission_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        del decisions
        if request.decision_type != SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            raise GameLifecycleError("Shooting prevalidation received unsupported decision_type.")
        missing = shooting_declaration_missing_field(result.payload)
        proposal_request = _proposal_request_from_decision_request(request)
        if missing is not None:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=ShootingProposalValidationResult.invalid(
                    proposal_request_id=proposal_request.request_id,
                    violation_code="proposal_payload_missing_field",
                    message=f"Shooting declaration proposal missing {missing}.",
                    field=missing,
                ),
                message="Shooting declaration proposal is malformed.",
            )
        try:
            proposal = shooting_declaration_proposal_from_json(result.payload)
        except GameLifecycleError as exc:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=ShootingProposalValidationResult.invalid(
                    proposal_request_id=proposal_request.request_id,
                    violation_code="proposal_schema_invalid",
                    message=str(exc),
                    field=None,
                ),
                message="Shooting declaration proposal is schema-invalid.",
            )
        proposal_validation = proposal.validation_result_for_request(proposal_request)
        if not proposal_validation.is_valid:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=proposal_validation,
                message="Shooting declaration proposal does not match the pending request.",
            )
        rule_validation = _validate_declaration_submission(
            state=state,
            proposal=proposal,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
            shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            runtime_modifier_registry=self.runtime_modifier_registry,
        )
        if not rule_validation.is_valid:
            return _reject_invalid_declaration(
                state=state,
                proposal_validation=rule_validation,
                message="Shooting declaration proposal is not currently legal.",
            )
        return None

    def invalid_shooting_type_selection_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type != SELECT_SHOOTING_TYPE_DECISION_TYPE:
            raise GameLifecycleError(
                "Shooting type prevalidation received unsupported decision_type."
            )
        shooting_state = state.shooting_phase_state
        if shooting_state is None or shooting_state.active_selection is None:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting type selection requires an active shooting unit.",
                payload={"invalid_reason": "shooting_type_wrong_context"},
            )
        payload = _decision_payload_object(result.payload)
        unit_instance_id = _payload_string(payload, key="unit_instance_id")
        if unit_instance_id != shooting_state.active_selection.unit_instance_id:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting type selection unit drifted.",
                payload={"invalid_reason": "shooting_type_unit_drift"},
            )
        shooting_type = shooting_type_from_token(_payload_string(payload, key="shooting_type"))
        rules_unit = rules_unit_view_by_id(state=state, unit_instance_id=unit_instance_id)
        legal_types = _legal_shooting_types_for_rules_unit(
            state=state,
            rules_unit=rules_unit,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
            shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
        )
        if shooting_type not in legal_types:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting type selection is no longer legal.",
                payload={
                    "invalid_reason": "shooting_type_option_drift",
                    "unit_instance_id": unit_instance_id,
                    "shooting_type": shooting_type.value,
                    "legal_shooting_types": [legal.value for legal in legal_types],
                },
            )
        return None

    def invalid_shooting_unit_selected_grant_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type != SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
            raise GameLifecycleError(
                "Shooting unit grant prevalidation received unsupported decision_type."
            )
        try:
            result.validate_for_request(request)
            selection = _active_shooting_unit_selection(state)
            payload = _decision_payload_object(result.payload)
            _validate_shooting_unit_selected_grant_payload_context(
                payload=payload,
                selection=selection,
            )
            if result.selected_option_id == DECLINE_SHOOTING_UNIT_GRANT_OPTION_ID:
                if _selected_shooting_unit_grants_from_payload(payload):
                    return LifecycleStatus.invalid(
                        stage=state.stage,
                        message="Declined shooting unit grant cannot carry selected grants.",
                        payload={
                            "invalid_reason": "shooting_unit_grant_decline_payload_drift",
                            "unit_instance_id": selection.unit_instance_id,
                        },
                    )
                return None
            selected_grants = _selected_shooting_unit_grants_from_payload(payload)
            _validate_selected_shooting_unit_grants(
                state=state,
                selection=selection,
                registry=self.shooting_unit_selected_grant_hooks,
                selected_grants=selected_grants,
            )
        except (DecisionError, GameLifecycleError) as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Shooting unit grant result is invalid.",
                payload={
                    "invalid_reason": "shooting_unit_grant_invalid",
                    "detail": str(exc),
                },
            )
        return None

    def invalid_attack_sequence_selection_status(
        self,
        *,
        state: GameState,
        request: DecisionRequest,
        result: DecisionResult,
    ) -> LifecycleStatus | None:
        if request.decision_type not in ATTACK_RESOLUTION_SELECTION_DECISION_TYPES:
            raise GameLifecycleError(
                "Attack sequence selection prevalidation received unsupported decision_type."
            )
        try:
            result.validate_for_request(request)
        except DecisionError as exc:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Attack sequence selection result is malformed.",
                payload={
                    "invalid_reason": "attack_sequence_selection_malformed",
                    "detail": str(exc),
                },
            )
        attack_sequence = _attack_sequence_for_selection_request(state=state, request=request)
        if request.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
            selected_target_id = selected_resolve_target_from_result(result)
            if selected_target_id not in unresolved_target_unit_ids(attack_sequence):
                return LifecycleStatus.invalid(
                    stage=state.stage,
                    message="Resolve target selection is no longer legal.",
                    payload={
                        "invalid_reason": "resolve_target_option_drift",
                        "selected_target_unit_instance_id": selected_target_id,
                    },
                )
            expected_request = build_select_resolve_target_unit_request(
                request_id=request.request_id,
                state=state,
                attack_sequence=attack_sequence,
            )
            return _invalid_if_current_option_payload_drifted(
                state=state,
                result=result,
                expected_request=expected_request,
                invalid_reason="resolve_target_payload_drift",
            )
        selected_group = selected_attack_weapon_group_from_result(result)
        if (
            attack_sequence.selected_target_unit_instance_id
            != selected_group.target_unit_instance_id
        ):
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Attack weapon group target context drifted.",
                payload={
                    "invalid_reason": "attack_group_target_drift",
                    "selected_target_unit_instance_id": selected_group.target_unit_instance_id,
                },
            )
        current_groups = gathered_attack_groups_for_target(
            attack_sequence=attack_sequence,
            target_unit_instance_id=selected_group.target_unit_instance_id,
        )
        if selected_group.group_id not in {group.group_id for group in current_groups}:
            return LifecycleStatus.invalid(
                stage=state.stage,
                message="Attack weapon group selection is no longer legal.",
                payload={
                    "invalid_reason": "attack_group_option_drift",
                    "selected_group_id": selected_group.group_id,
                },
            )
        expected_request = build_select_attack_weapon_group_request(
            request_id=request.request_id,
            state=state,
            attack_sequence=attack_sequence,
            target_unit_instance_id=selected_group.target_unit_instance_id,
        )
        return _invalid_if_current_option_payload_drifted(
            state=state,
            result=result,
            expected_request=expected_request,
            invalid_reason="attack_group_payload_drift",
        )

    def apply_decision(
        self,
        *,
        state: GameState,
        result: DecisionResult,
        decisions: DecisionController,
    ) -> LifecycleStatus | None:
        if result.decision_type == SELECT_FACTION_RULE_SHOOTING_PHASE_START_OPTION_DECISION_TYPE:
            phase_start_result = self.shooting_phase_start_hooks.apply_result(
                ShootingPhaseStartResultContext(
                    state=state,
                    decisions=decisions,
                    request=decisions.record_for_result(result).request,
                    result=result,
                    ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                    army_catalog=_army_catalog_for_handler(self),
                    shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
                )
            )
            if type(phase_start_result) is LifecycleStatus:
                return phase_start_result
            if phase_start_result:
                return None
            raise GameLifecycleError("Shooting phase start faction rule result was not handled.")
        if result.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE:
            return apply_catalog_post_shoot_hit_target_status_result(
                state=state,
                decisions=decisions,
                result=result,
            )
        if result.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE:
            return apply_catalog_post_shoot_hit_target_effect_result(
                state=state,
                decisions=decisions,
                result=result,
            )
        if result.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
            return _apply_shooting_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_unit_selected_hooks=self.shooting_unit_selected_hooks,
                shooting_unit_selected_grant_hooks=self.shooting_unit_selected_grant_hooks,
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
        if result.decision_type == SELECT_SHOOTING_UNIT_GRANT_DECISION_TYPE:
            return _apply_shooting_unit_selected_grant_decision(
                state=state,
                result=result,
                decisions=decisions,
                registry=self.shooting_unit_selected_grant_hooks,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
        if result.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE:
            _apply_shooting_type_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
            )
            return None
        if result.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            _apply_shooting_declaration_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
                shooting_target_restriction_hooks=self.shooting_target_restriction_hooks,
                runtime_modifier_registry=self.runtime_modifier_registry,
            )
            return None
        if result.decision_type in ATTACK_RESOLUTION_SELECTION_DECISION_TYPES:
            _apply_attack_sequence_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
            return None
        if result.decision_type in ATTACK_ALLOCATION_DECISION_TYPES:
            return _apply_attack_sequence_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                stratagem_index=self.stratagem_index,
            )
        if result.decision_type == DICE_REROLL_DECISION_TYPE:
            return _apply_shooting_dice_reroll_decision(
                state=state,
                result=result,
                decisions=decisions,
            )
        if result.decision_type == PLACEMENT_PROPOSAL_DECISION_TYPE:
            return _apply_attack_sequence_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                stratagem_index=self.stratagem_index,
            )
        raise GameLifecycleError("ShootingPhaseHandler received unsupported decision_type.")


def invalid_catalog_post_shoot_decision_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    if request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_STATUS_DECISION_TYPE:
        return invalid_catalog_post_shoot_hit_target_status_status(
            state=state,
            request=request,
            result=result,
        )
    if request.decision_type == SELECT_CATALOG_POST_SHOOT_HIT_TARGET_EFFECT_DECISION_TYPE:
        return invalid_catalog_post_shoot_hit_target_effect_status(
            state=state,
            request=request,
            result=result,
        )
    return None


def invalid_shooting_phase_start_faction_rule_status(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
) -> LifecycleStatus | None:
    invalid_status = _invalid_finite_decision_status(
        state=state,
        request=request,
        result=result,
        invalid_reason="invalid_shooting_phase_start_faction_rule_result",
    )
    if invalid_status is not None:
        return invalid_status
    payload = _decision_payload_object(result.payload)
    request_payload = _decision_payload_object(request.payload)
    drift_reason = _shooting_phase_start_faction_rule_drift_reason(
        state=state,
        request=request,
        result=result,
        payload=payload,
        request_payload=request_payload,
    )
    if drift_reason is None:
        return None
    return LifecycleStatus.invalid(
        stage=state.stage,
        message="Shooting phase start faction rule option drifted.",
        payload=validate_json_value(
            {
                "game_id": state.game_id,
                "player_id": result.actor_id,
                "battle_round": state.battle_round,
                "phase": (
                    None if state.current_battle_phase is None else state.current_battle_phase.value
                ),
                "invalid_reason": drift_reason,
            }
        ),
    )


def _shooting_phase_start_faction_rule_drift_reason(
    *,
    state: GameState,
    request: DecisionRequest,
    result: DecisionResult,
    payload: dict[str, object],
    request_payload: dict[str, object],
) -> str | None:
    if result.actor_id is None:
        return "actor_missing"
    if request.actor_id != result.actor_id:
        return "actor_player_drift"
    if _payload_string(payload, key="game_id") != state.game_id:
        return "game_id_drift"
    if _payload_int(payload, key="battle_round") != state.battle_round:
        return "battle_round_drift"
    if _payload_string(payload, key="phase") != BattlePhase.SHOOTING.value:
        return "payload_phase_drift"
    if _payload_string(payload, key="active_player_id") != _active_player_id(state):
        return "active_player_drift"
    if _payload_string(request_payload, key="game_id") != state.game_id:
        return "request_game_id_drift"
    if _payload_int(request_payload, key="battle_round") != state.battle_round:
        return "request_battle_round_drift"
    if _payload_string(request_payload, key="phase") != BattlePhase.SHOOTING.value:
        return "request_phase_drift"
    if _payload_string(request_payload, key="active_player_id") != _active_player_id(state):
        return "request_active_player_drift"
    if state.current_battle_phase is not BattlePhase.SHOOTING:
        return "phase_drift"
    if state.shooting_phase_state is not None:
        return "shooting_phase_start_window_closed"
    return None


def _request_shooting_phase_start_rule_if_available(
    *,
    handler: ShootingPhaseHandler,
    state: GameState,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    request = handler.shooting_phase_start_hooks.next_request_for(
        ShootingPhaseStartRequestContext(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(handler),
            army_catalog=_army_catalog_for_handler(handler),
            shooting_target_restriction_hooks=handler.shooting_target_restriction_hooks,
        )
    )
    if request is None:
        return None
    decisions.request_decision(request)
    decisions.event_log.append(
        "shooting_phase_start_faction_rule_requested",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.SHOOTING.value,
                "decision_type": request.decision_type,
                "request_id": request.request_id,
                "actor_id": request.actor_id,
            }
        ),
    )
    return LifecycleStatus.waiting_for_decision(
        stage=GameLifecycleStage.BATTLE,
        decision_request=request,
        payload=validate_json_value(
            {
                "phase": BattlePhase.SHOOTING.value,
                "active_player_id": _active_player_id(state),
                "phase_body_status": "shooting_phase_start_faction_rule_pending",
                "request_id": request.request_id,
            }
        ),
    )
