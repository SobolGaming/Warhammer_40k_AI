# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.attack_sequence_imports import *
from warhammer40k_core.engine.post_roll_attack_profiles import PostRollAttackPoolSet

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex
    from warhammer40k_core.engine.attack_sequence_model import ATTACK_ALLOCATION_DECISION_TYPES, SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE, SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE, SELECT_PSYCHIC_ATTACK_MODIFIER_IGNORES_DECISION_TYPE, KEEP_ALL_MODIFIERS_OPTION_ID, IGNORE_DETRIMENTAL_MODIFIERS_OPTION_ID, IGNORE_BENEFICIAL_MODIFIERS_OPTION_ID, IGNORE_ALL_MODIFIERS_OPTION_ID, ATTACK_RESOLUTION_SELECTION_DECISION_TYPES, SOURCE_BACKED_ATTACK_REROLL_ROLL_STATE_KEYS, DAMAGE_ALLOCATION_RULE_ID, DEADLY_DEMISE_SOURCE_KIND, HAZARDOUS_SOURCE_KIND, _PRECISION_CHARACTER_GROUP_ROLES, attack_sequence_hit_roll_spec, attack_sequence_wound_roll_spec, deadly_demise_trigger_roll_spec, deadly_demise_mortal_wounds_roll_spec, AttackSequenceStep, AttackSequenceEventPayload, HitRollPayload, WoundRollPayload, PsychicAttackModifierIgnoreSelection, AttackSequencePayload, AttackResolutionContextPayload, SaveDieEntryPayload, PendingGroupedDamagePayload, PendingDestroyedTransportDisembarkPayload, LostWoundContextPayload, DestructionReactionContextPayload, DeferredMortalWoundsPayload, HazardousMortalWoundSourceContextPayload, FastDiceGroupPayload, AttackModifierStackSetPayload, IdenticalAttackSignaturePayload, GatheredAttackContributionPayload, GatheredAttackGroupPayload, HitRoll, WoundRoll, AttackSequenceEvent, AttackSequenceEventHandler, AttackSequenceHooks, DestroyedModelEmission, PrecisionPoolSelection, PendingGroupedDamage, PendingDestroyedTransportDisembark, AttackModifierStackSet, DeferredMortalWounds, IdenticalAttackSignature, GatheredAttackContribution, GatheredAttackGroup
    from warhammer40k_core.engine.attack_sequence_dispatch import apply_resolve_target_unit_decision, apply_attack_weapon_group_decision, resolve_attack_sequence_until_blocked
    from warhammer40k_core.engine.attack_sequence_destroyed_transport import is_destroyed_transport_disembark_proposal_request, invalid_destroyed_transport_disembark_proposal_status, apply_destroyed_transport_disembark_proposal_decision, _continue_pending_destroyed_transport_disembark, _remove_resolved_destroyed_transport_cargo_state, _begin_destroyed_transport_disembark_if_needed, _request_destroyed_transport_disembark_placement, _parse_destroyed_transport_disembark_submission_or_invalid, _destroyed_transport_proposal_parse_failure, _key_error_field, _missing_destroyed_transport_disembark_field, _destroyed_transport_proposal_invalid_status, _destroyed_transport_placement_invalid_status, _request_destroyed_transport_disembark_placement_retry, _resolve_destroyed_transport_disembark_submission, _apply_valid_destroyed_transport_disembark, _destroyed_transport_cargo_state_for_damage, _destroyed_transport_placement, _battlefield_scenario_for_attack_sequence, _objective_markers_for_attack_sequence
    from warhammer40k_core.engine.attack_sequence_group_selection import _select_or_request_next_gathered_group, _record_auto_attack_sequence_selection, apply_allocation_order_decision, apply_damage_allocation_model_decision, current_legal_damage_allocation_model_ids, apply_precision_allocation_decision, apply_feel_no_pain_decision, apply_destruction_reaction_decision, _continue_grouped_damage_after_interruption, _apply_deferred_mortal_wounds, _emit_deferred_mortal_wounds_applied, _apply_deferred_mortal_wound_feel_no_pain_decision, _continue_hazardous_after_mortal_wound_feel_no_pain, _continue_deadly_demise_after_mortal_wound_feel_no_pain, _grouped_precision_request_if_available, _precision_grouped_allocation_context_and_groups, _build_precision_allocation_request, _precision_pool_selection, _resolve_grouped_current_pool, _grouped_wounded_contexts_for_pool, _defer_grouped_devastating_wounds
    from warhammer40k_core.engine.attack_sequence_grouped_allocation import _continue_grouped_allocation_for_wound_contexts, _continue_after_grouped_allocation_order, _resolve_grouped_damage_from, _alive_allocated_model_ids, _alive_allocated_model_ids_for_target_unit, _advance_after_current_pool, _attack_sequence_for_context, _grouped_attack_context_payload, _emit_grouped_allocation_event, _roll_grouped_saves, _emit_grouped_save_die_event
    from warhammer40k_core.engine.attack_sequence_damage_resolution import _no_save_damage_order_roll_spec, _save_options_for_allocation, _resolve_lost_wound_stage, _apply_damage_after_feel_no_pain, _advance_after_resolved_hit, _destruction_reaction_status_if_needed, _optional_destruction_reaction_sources_after_trigger_rolls, _optional_destruction_reaction_trigger_descriptor, _optional_destruction_reaction_trigger_conditions_met, _optional_destruction_reaction_trigger_battle_round_is_current, _optional_destruction_reaction_active_effect_requirement_is_met, _destruction_reaction_trigger_threshold, _optional_destruction_reaction_trigger_roll_type, _resolve_mandatory_destruction_reactions_before_removal, _emit_mandatory_destruction_reaction_record, _resolve_deadly_demise_before_removal, _route_deadly_demise_mortal_wounds, _resolve_deadly_demise_secondary_destroyed_models, _continue_deadly_demise_after_secondary_destruction_reaction, _deadly_demise_secondary_continuation_payload, _is_deadly_demise_continuation, _destroyed_damage_applications, _deadly_demise_mortal_wounds_for_target, _emit_deadly_demise_mortal_wounds_applied, _deadly_demise_target_unit_ids, _unit_has_model_within_deadly_demise_range, _deadly_demise_descriptor, _deadly_demise_source_context_payload, _deadly_demise_attack_context_from_source_context, _pre_removal_destruction_reaction_context_payload, _destruction_reaction_context_payload
    from warhammer40k_core.engine.attack_sequence_dice_rerolls import _roll_hit_and_wound, _roll_or_reuse_state, _latest_reroll_state_for_original_roll, _request_command_reroll_for_attack_roll_if_available, _request_source_backed_hit_reroll_if_available, _source_backed_hit_permission_for_attack, apply_source_backed_attack_dice_reroll_decision, _validate_current_source_backed_attack_reroll_context_if_required, _source_backed_attack_context_id_matches_active_pool, _source_backed_attack_kind_for_phase, _request_source_backed_wound_reroll_if_available, _source_backed_wound_permission_for_attack, _conditional_wound_full_reroll_applies, _target_unit_within_any_objective_marker_range, _canonical_keyword, _source_backed_reroll_already_answered, _command_reroll_opportunity_window, _command_reroll_opportunity_options, _command_reroll_opportunity_option, _command_reroll_opportunity_state_hash, _command_reroll_opportunity_boundary_state_payload, _dice_rolled_event_id_for_roll, _random_characteristic_roll_spec, _append_replay_resume_unique_event_once
    from warhammer40k_core.engine.attack_sequence_psychic_modifiers import _psychic_attack_modifier_ignore_request, _psychic_attack_modifier_ignore_options, _psychic_attack_modifier_ignore_selection_for_attack, validate_psychic_attack_modifier_ignore_decision, _has_detrimental_psychic_modifier, _has_beneficial_psychic_modifier
    from warhammer40k_core.engine.attack_sequence_hit_wound import _roll_hit, _hit_reroll_forbidden_rule_ids, _roll_wound, _wound_roll_modifier, _reroll_wound_for_twin_linked_if_needed, _selected_anti_keyword_ability_id, _emit_damage_event, _destroyed_model_removal_record, _destroyed_model_placement_payload, _emit_event, _target_has_effect_cover, _target_has_effect_cover_denial, _benefit_of_cover_ballistic_skill_penalty, _hit_skill_modifier, _hit_roll_modifier, _plunging_fire_ballistic_skill_improvement, _persisting_hit_roll_modifier, _unit_instance_id_for_model, _save_options_with_effect_invulnerable, _cover_result_with_effect_source, _melta_damage_modifier, _devastating_wounds_resolution_for_attack
    from warhammer40k_core.engine.attack_sequence_hazardous import _resolve_hazardous_tests, _emit_hazardous_test_resolved, _emit_hazardous_mortal_wounds_applied, _hazardous_feel_no_pain_status, _hazardous_source_context_payload, _hazardous_source_context_from_payload, _hazardous_mortal_wounds_for_attacker, _cover_for_allocated_model
    from warhammer40k_core.engine.attack_sequence_geometry_targets import cover_for_allocated_model, attack_pool_attacker_unit_id, _hit_skill, _target_unit_toughness, _highest_toughness_for_models, _toughness_values_for_models, _damage_value, _model_is_alive, _current_model_id_for_allocation_group, _legal_model_ids_for_allocation_group_damage, _current_allocation_group_for_order
    from warhammer40k_core.engine.attack_sequence_selection import identical_attack_signature, unresolved_target_unit_ids, gathered_attack_groups_for_target, build_select_resolve_target_unit_request, build_select_attack_weapon_group_request, selected_resolve_target_from_result, selected_attack_weapon_group_from_result, _fast_dice_pool_key, _pool_id, _resolve_target_option_id, _gathered_attack_group_from_indices, _gathered_attack_contribution, _gathered_attack_group_id, _synthetic_pool_for_gathered_group, _first_unresolved_pool_index, _first_unresolved_pool_index_from, _first_unresolved_pool_index_for_target, _first_unresolved_pool_index_for_target_from, _weapon_rule_tokens_for_signature, _validate_weapon_profile_signature_shape
    from warhammer40k_core.engine.attack_sequence_validation import _validate_gathered_group_matches_attack_pools, _validate_attack_pools, _validate_pool_index_tuple, _validate_pool_indices_within_attack_pools, _validate_gathered_attack_contributions, _validate_deferred_mortal_wounds, _validate_destroyed_transport_disembark_tuple, _validate_destruction_reaction_source_tuple, _validate_save_die_entry_tuple, _validate_save_die_entry_payload, _validate_allocation_group_payload_tuple, _validate_allocation_group_tuple, _validate_ordered_allocation_group_tuple, _first_allocation_group, _first_allocation_group_order, _validate_fast_dice_pools, _validate_roll_modifier_tuple, _payload_object, _nested_payload_object, _precision_selected_group_id, _precision_selected_model_ids, _lost_wound_context_payload, _lost_wound_context_from_payload, _validate_lost_wound_context_matches_sequence, _validate_grouped_request_context_matches_sequence, _validate_attack_context_matches_sequence, _attack_context_matches_pending_grouped_damage, _destruction_reaction_context_from_payload, _state_feel_no_pain_sources, _feel_no_pain_sources_for_attack, _feel_no_pain_source_applies_to_attack, _state_destruction_reaction_sources, _selected_destruction_reaction_source_from_request, _destruction_reaction_action_host, _state_feel_no_pain_decline_allowed, _payload_string, _optional_payload_string, _payload_int, _payload_string_list, _payload_bool, _payload_positive_int, _payload_positive_number, _payload_identifier_tuple, _cap_roll_modifier, _validate_d6_target, _validate_d6_value, _validate_d6_minimum_success, _validate_positive_int, _validate_non_negative_int, _validate_identifier_tuple, _validate_ordered_identifier_tuple, _validate_identifier, _validate_int, _validate_optional_identifier
# fmt: on

__all__ = (
    "AttackSequence",
    "FastDiceGroup",
    "_runtime_modifier_registry",
    "attack_sequence_step_from_token",
    "wound_roll_target_number",
)


@dataclass(frozen=True, slots=True)
class AttackSequence:
    sequence_id: str
    attacker_player_id: str
    attacking_unit_instance_id: str
    attack_pools: tuple[RangedAttackPool, ...]
    source_phase: BattlePhase = BattlePhase.SHOOTING
    used_pool_indices: tuple[int, ...] = ()
    selected_target_unit_instance_id: str | None = None
    current_gathered_group: GatheredAttackGroup | None = None
    pool_index: int = 0
    attack_index: int = 0
    generated_hit_index: int = 0
    current_hit_roll: HitRoll | None = None
    deferred_mortal_wounds: tuple[DeferredMortalWounds, ...] = ()
    pending_grouped_damage: PendingGroupedDamage | None = None
    pending_destroyed_transport_disembark: PendingDestroyedTransportDisembark | None = None
    post_roll_attack_pools: PostRollAttackPoolSet | None = None
    post_roll_attack_contexts: tuple[AttackResolutionContextPayload, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence_id",
            _validate_identifier("AttackSequence sequence_id", self.sequence_id),
        )
        object.__setattr__(
            self,
            "source_phase",
            battle_phase_kind_from_token(self.source_phase),
        )
        object.__setattr__(
            self,
            "attacker_player_id",
            _validate_identifier("AttackSequence attacker_player_id", self.attacker_player_id),
        )
        object.__setattr__(
            self,
            "attacking_unit_instance_id",
            _validate_identifier(
                "AttackSequence attacking_unit_instance_id",
                self.attacking_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attack_pools",
            _validate_attack_pools(self.attack_pools),
        )
        object.__setattr__(
            self,
            "used_pool_indices",
            _validate_pool_index_tuple("AttackSequence used_pool_indices", self.used_pool_indices),
        )
        _validate_pool_indices_within_attack_pools(
            field_name="AttackSequence used_pool_indices",
            pool_indices=self.used_pool_indices,
            attack_pools=self.attack_pools,
        )
        object.__setattr__(
            self,
            "selected_target_unit_instance_id",
            _validate_optional_identifier(
                "AttackSequence selected_target_unit_instance_id",
                self.selected_target_unit_instance_id,
            ),
        )
        if self.current_gathered_group is not None:
            if type(self.current_gathered_group) is not GatheredAttackGroup:
                raise GameLifecycleError(
                    "AttackSequence current_gathered_group must be a GatheredAttackGroup."
                )
            _validate_gathered_group_matches_attack_pools(
                attack_pools=self.attack_pools,
                used_pool_indices=self.used_pool_indices,
                gathered_group=self.current_gathered_group,
            )
            if (
                self.selected_target_unit_instance_id
                != self.current_gathered_group.target_unit_instance_id
            ):
                raise GameLifecycleError("AttackSequence gathered group target drift.")
        object.__setattr__(
            self,
            "pool_index",
            _validate_non_negative_int("AttackSequence pool_index", self.pool_index),
        )
        object.__setattr__(
            self,
            "attack_index",
            _validate_non_negative_int("AttackSequence attack_index", self.attack_index),
        )
        object.__setattr__(
            self,
            "generated_hit_index",
            _validate_non_negative_int(
                "AttackSequence generated_hit_index",
                self.generated_hit_index,
            ),
        )
        if self.current_hit_roll is not None and type(self.current_hit_roll) is not HitRoll:
            raise GameLifecycleError("AttackSequence current_hit_roll must be a HitRoll.")
        object.__setattr__(
            self,
            "deferred_mortal_wounds",
            _validate_deferred_mortal_wounds(self.deferred_mortal_wounds),
        )
        if self.pending_grouped_damage is not None:
            if type(self.pending_grouped_damage) is not PendingGroupedDamage:
                raise GameLifecycleError(
                    "AttackSequence pending_grouped_damage must be PendingGroupedDamage."
                )
            if self.attack_index != 0:
                raise GameLifecycleError(
                    "AttackSequence pending_grouped_damage requires attack_index 0."
                )
            if self.generated_hit_index != 0 or self.current_hit_roll is not None:
                raise GameLifecycleError(
                    "AttackSequence pending_grouped_damage requires no generated hit state."
                )
        if (
            self.pending_destroyed_transport_disembark is not None
            and type(self.pending_destroyed_transport_disembark)
            is not PendingDestroyedTransportDisembark
        ):
            raise GameLifecycleError(
                "AttackSequence pending_destroyed_transport_disembark must be "
                "PendingDestroyedTransportDisembark."
            )
        if self.post_roll_attack_pools is None:
            if self.post_roll_attack_contexts:
                raise GameLifecycleError(
                    "AttackSequence post-roll contexts require post-roll pools."
                )
        else:
            if type(self.post_roll_attack_pools) is not PostRollAttackPoolSet:
                raise GameLifecycleError(
                    "AttackSequence post_roll_attack_pools must be a PostRollAttackPoolSet."
                )
            if self.post_roll_attack_pools.sequence_id != self.sequence_id:
                raise GameLifecycleError("AttackSequence post-roll pool sequence drift.")
            if self.current_gathered_group is None:
                raise GameLifecycleError(
                    "AttackSequence post-roll pools require a gathered attack group."
                )
            context_ids = tuple(
                _validate_identifier(
                    "AttackSequence post-roll attack_context_id",
                    context["attack_context_id"],
                )
                for context in self.post_roll_attack_contexts
            )
            if len(set(context_ids)) != len(context_ids):
                raise GameLifecycleError("AttackSequence post-roll attack contexts must be unique.")
            if set(context_ids) != set(self.post_roll_attack_pools.all_attack_context_ids):
                raise GameLifecycleError(
                    "AttackSequence post-roll attack context membership drift."
                )
        if self.pool_index > len(self.attack_pools):
            raise GameLifecycleError("AttackSequence pool_index is outside attack_pools.")
        if self.pool_index == len(self.attack_pools):
            if self.used_pool_indices and len(self.used_pool_indices) != len(self.attack_pools):
                raise GameLifecycleError("Completed AttackSequence has unresolved attack pools.")
            if self.selected_target_unit_instance_id is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have selected target state."
                )
            if self.current_gathered_group is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have current_gathered_group."
                )
            if self.pending_grouped_damage is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have pending_grouped_damage."
                )
            if self.pending_destroyed_transport_disembark is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have pending destroyed Transport state."
                )
            if self.post_roll_attack_pools is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence cannot have post-roll attack pools."
                )
            if self.attack_index != 0:
                raise GameLifecycleError("Completed AttackSequence must have attack_index 0.")
            if self.generated_hit_index != 0:
                raise GameLifecycleError("Completed AttackSequence must not track generated hits.")
            if self.current_hit_roll is not None:
                raise GameLifecycleError(
                    "Completed AttackSequence must not include a current hit roll."
                )
            return
        if (
            self.current_gathered_group is not None
            and self.pool_index != self.current_gathered_group.primary_pool_index
        ):
            raise GameLifecycleError("AttackSequence pool_index must match gathered group.")
        if self.attack_index >= self.current_pool().attacks:
            raise GameLifecycleError("AttackSequence attack_index is outside current pool.")
        if self.generated_hit_index > 0:
            if self.current_hit_roll is None:
                raise GameLifecycleError("Generated hit continuation requires a hit roll.")
            if self.current_hit_roll.generated_hits <= self.generated_hit_index:
                raise GameLifecycleError("Generated hit index is outside generated hits.")
            if not self.current_hit_roll.successful:
                raise GameLifecycleError("Generated hit continuation requires a successful hit.")
        elif self.current_hit_roll is not None:
            raise GameLifecycleError("Initial attack must not store a current hit roll.")

    @classmethod
    def start(
        cls,
        *,
        sequence_id: str,
        attacker_player_id: str,
        attacking_unit_instance_id: str,
        attack_pools: tuple[RangedAttackPool, ...],
        source_phase: BattlePhase = BattlePhase.SHOOTING,
    ) -> Self:
        return cls(
            sequence_id=sequence_id,
            source_phase=source_phase,
            attacker_player_id=attacker_player_id,
            attacking_unit_instance_id=attacking_unit_instance_id,
            attack_pools=attack_pools,
        )

    @property
    def is_complete(self) -> bool:
        return self.pool_index == len(self.attack_pools) or (
            len(self.used_pool_indices) == len(self.attack_pools)
            and self.current_gathered_group is None
        )

    def current_pool(self) -> RangedAttackPool:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence has no current pool.")
        if self.current_gathered_group is not None:
            pool = _synthetic_pool_for_gathered_group(
                attack_pools=self.attack_pools,
                gathered_group=self.current_gathered_group,
            )
        else:
            pool = self.attack_pools[self.pool_index]
        if self.post_roll_attack_pools is None or self.post_roll_attack_pools.selected_pool is None:
            return pool
        profile = self.post_roll_attack_pools.selected_pool.weapon_profile
        return replace(
            pool,
            weapon_profile_id=profile.profile_id,
            weapon_profile=profile,
        )

    def with_post_roll_attack_pools(
        self,
        *,
        pools: PostRollAttackPoolSet,
        attack_contexts: tuple[AttackResolutionContextPayload, ...],
    ) -> Self:
        if type(pools) is not PostRollAttackPoolSet:
            raise GameLifecycleError("Post-roll attack pool state is invalid.")
        return replace(
            self,
            post_roll_attack_pools=pools,
            post_roll_attack_contexts=attack_contexts,
        )

    def with_selected_post_roll_attack_pool(
        self,
        *,
        actor_id: str,
        selected_pool_id: str,
    ) -> Self:
        if self.post_roll_attack_pools is None:
            raise GameLifecycleError("Post-roll attack pool selection requires pending pools.")
        return replace(
            self,
            post_roll_attack_pools=self.post_roll_attack_pools.with_selected_pool(
                actor_id=actor_id,
                selected_pool_id=selected_pool_id,
            ),
        )

    def without_post_roll_attack_pools(self) -> Self:
        if self.post_roll_attack_pools is None:
            raise GameLifecycleError("AttackSequence has no post-roll attack pools to discard.")
        return replace(
            self,
            post_roll_attack_pools=None,
            post_roll_attack_contexts=(),
        )

    def attack_context_id(self) -> str:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence has no attack context.")
        context_id = (
            f"{self.sequence_id}:pool-{self.pool_index + 1:03d}:attack-{self.attack_index + 1:03d}"
        )
        if self.generated_hit_index > 0:
            return f"{context_id}:generated-hit-{self.generated_hit_index + 1:03d}"
        return context_id

    def advanced_after_attack(self) -> Self:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence cannot advance.")
        if self.pending_grouped_damage is not None:
            raise GameLifecycleError("AttackSequence cannot advance with pending grouped damage.")
        if self.generated_hit_index != 0 or self.current_hit_roll is not None:
            raise GameLifecycleError("AttackSequence cannot skip unresolved generated hits.")
        pool = self.current_pool()
        next_attack_index = self.attack_index + 1
        if next_attack_index < pool.attacks:
            return type(self)(
                sequence_id=self.sequence_id,
                attacker_player_id=self.attacker_player_id,
                attacking_unit_instance_id=self.attacking_unit_instance_id,
                attack_pools=self.attack_pools,
                source_phase=self.source_phase,
                used_pool_indices=self.used_pool_indices,
                selected_target_unit_instance_id=self.selected_target_unit_instance_id,
                current_gathered_group=self.current_gathered_group,
                pool_index=self.pool_index,
                attack_index=next_attack_index,
                deferred_mortal_wounds=self.deferred_mortal_wounds,
                pending_grouped_damage=self.pending_grouped_damage,
                pending_destroyed_transport_disembark=(self.pending_destroyed_transport_disembark),
                post_roll_attack_pools=self.post_roll_attack_pools,
                post_roll_attack_contexts=self.post_roll_attack_contexts,
            )
        next_pool_index = self.pool_index + 1
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=next_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def advanced_after_generated_hit(self, hit_roll: HitRoll) -> Self:
        if self.is_complete:
            raise GameLifecycleError("Completed AttackSequence cannot advance generated hits.")
        if self.pending_grouped_damage is not None:
            raise GameLifecycleError(
                "AttackSequence cannot advance generated hits with pending grouped damage."
            )
        if type(hit_roll) is not HitRoll:
            raise GameLifecycleError("Generated hit advancement requires a HitRoll.")
        if not hit_roll.successful:
            raise GameLifecycleError("Generated hit advancement requires a successful hit.")
        next_generated_hit_index = self.generated_hit_index + 1
        if next_generated_hit_index >= hit_roll.generated_hits:
            return type(self)(
                sequence_id=self.sequence_id,
                attacker_player_id=self.attacker_player_id,
                attacking_unit_instance_id=self.attacking_unit_instance_id,
                attack_pools=self.attack_pools,
                source_phase=self.source_phase,
                used_pool_indices=self.used_pool_indices,
                selected_target_unit_instance_id=self.selected_target_unit_instance_id,
                current_gathered_group=self.current_gathered_group,
                pool_index=self.pool_index,
                attack_index=self.attack_index,
                deferred_mortal_wounds=self.deferred_mortal_wounds,
                pending_grouped_damage=self.pending_grouped_damage,
                pending_destroyed_transport_disembark=(self.pending_destroyed_transport_disembark),
                post_roll_attack_pools=self.post_roll_attack_pools,
                post_roll_attack_contexts=self.post_roll_attack_contexts,
            ).advanced_after_attack()
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=next_generated_hit_index,
            current_hit_roll=hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=(self.pending_destroyed_transport_disembark),
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def with_deferred_mortal_wounds(self, deferred: DeferredMortalWounds) -> Self:
        if type(deferred) is not DeferredMortalWounds:
            raise GameLifecycleError("AttackSequence deferred mortal wounds are invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=(*self.deferred_mortal_wounds, deferred),
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def without_deferred_mortal_wounds(self) -> Self:
        return self.with_pending_deferred_mortal_wounds(())

    def with_pending_deferred_mortal_wounds(
        self,
        deferred_mortal_wounds: tuple[DeferredMortalWounds, ...],
    ) -> Self:
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def with_pending_grouped_damage(self, pending: PendingGroupedDamage) -> Self:
        if type(pending) is not PendingGroupedDamage:
            raise GameLifecycleError("AttackSequence pending grouped damage is invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=pending,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def without_pending_grouped_damage(self) -> Self:
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def with_pending_destroyed_transport_disembark(
        self,
        pending: PendingDestroyedTransportDisembark,
    ) -> Self:
        if type(pending) is not PendingDestroyedTransportDisembark:
            raise GameLifecycleError("AttackSequence destroyed Transport pending state is invalid.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            pending_destroyed_transport_disembark=pending,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def without_pending_destroyed_transport_disembark(self) -> Self:
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=self.current_gathered_group,
            pool_index=self.pool_index,
            attack_index=self.attack_index,
            generated_hit_index=self.generated_hit_index,
            current_hit_roll=self.current_hit_roll,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_grouped_damage=self.pending_grouped_damage,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def with_selected_target_unit(self, target_unit_instance_id: str) -> Self:
        target_id = _validate_identifier("AttackSequence selected target", target_unit_instance_id)
        if target_id not in unresolved_target_unit_ids(self):
            raise GameLifecycleError("Selected resolve target has no unresolved attack pools.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=target_id,
            pool_index=_first_unresolved_pool_index_for_target(
                attack_sequence=self,
                target_unit_instance_id=target_id,
            ),
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def without_selected_target_unit(self) -> Self:
        next_pool_index = _first_unresolved_pool_index(self)
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=None,
            pool_index=next_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def with_current_gathered_group(self, gathered_group: GatheredAttackGroup) -> Self:
        if type(gathered_group) is not GatheredAttackGroup:
            raise GameLifecycleError("AttackSequence gathered group is invalid.")
        if self.selected_target_unit_instance_id != gathered_group.target_unit_instance_id:
            raise GameLifecycleError("Gathered attack group target drift.")
        return type(self)(
            sequence_id=self.sequence_id,
            attacker_player_id=self.attacker_player_id,
            attacking_unit_instance_id=self.attacking_unit_instance_id,
            attack_pools=self.attack_pools,
            source_phase=self.source_phase,
            used_pool_indices=self.used_pool_indices,
            selected_target_unit_instance_id=self.selected_target_unit_instance_id,
            current_gathered_group=gathered_group,
            pool_index=gathered_group.primary_pool_index,
            attack_index=0,
            deferred_mortal_wounds=self.deferred_mortal_wounds,
            pending_destroyed_transport_disembark=self.pending_destroyed_transport_disembark,
            post_roll_attack_pools=self.post_roll_attack_pools,
            post_roll_attack_contexts=self.post_roll_attack_contexts,
        )

    def to_payload(self) -> AttackSequencePayload:
        return {
            "sequence_id": self.sequence_id,
            "source_phase": self.source_phase.value,
            "attacker_player_id": self.attacker_player_id,
            "attacking_unit_instance_id": self.attacking_unit_instance_id,
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "used_pool_indices": list(self.used_pool_indices),
            "selected_target_unit_instance_id": self.selected_target_unit_instance_id,
            "current_gathered_group": (
                None
                if self.current_gathered_group is None
                else self.current_gathered_group.to_payload()
            ),
            "pool_index": self.pool_index,
            "attack_index": self.attack_index,
            "generated_hit_index": self.generated_hit_index,
            "current_hit_roll": (
                None if self.current_hit_roll is None else self.current_hit_roll.to_payload()
            ),
            "deferred_mortal_wounds": [
                deferred.to_payload() for deferred in self.deferred_mortal_wounds
            ],
            "pending_grouped_damage": (
                None
                if self.pending_grouped_damage is None
                else self.pending_grouped_damage.to_payload()
            ),
            "pending_destroyed_transport_disembark": (
                None
                if self.pending_destroyed_transport_disembark is None
                else self.pending_destroyed_transport_disembark.to_payload()
            ),
            "post_roll_attack_pools": (
                None
                if self.post_roll_attack_pools is None
                else self.post_roll_attack_pools.to_payload()
            ),
            "post_roll_attack_contexts": list(self.post_roll_attack_contexts),
        }

    @classmethod
    def from_payload(cls, payload: AttackSequencePayload) -> Self:
        pending_destroyed_transport_payload = payload.get("pending_destroyed_transport_disembark")
        return cls(
            sequence_id=payload["sequence_id"],
            source_phase=battle_phase_kind_from_token(
                payload.get("source_phase", BattlePhase.SHOOTING.value)
            ),
            attacker_player_id=payload["attacker_player_id"],
            attacking_unit_instance_id=payload["attacking_unit_instance_id"],
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            used_pool_indices=tuple(payload["used_pool_indices"]),
            selected_target_unit_instance_id=payload["selected_target_unit_instance_id"],
            current_gathered_group=(
                None
                if payload["current_gathered_group"] is None
                else GatheredAttackGroup.from_payload(payload["current_gathered_group"])
            ),
            pool_index=payload["pool_index"],
            attack_index=payload["attack_index"],
            generated_hit_index=payload["generated_hit_index"],
            current_hit_roll=(
                None
                if payload["current_hit_roll"] is None
                else HitRoll.from_payload(payload["current_hit_roll"])
            ),
            deferred_mortal_wounds=tuple(
                DeferredMortalWounds.from_payload(deferred)
                for deferred in payload["deferred_mortal_wounds"]
            ),
            pending_grouped_damage=(
                None
                if payload["pending_grouped_damage"] is None
                else PendingGroupedDamage.from_payload(payload["pending_grouped_damage"])
            ),
            pending_destroyed_transport_disembark=(
                None
                if pending_destroyed_transport_payload is None
                else PendingDestroyedTransportDisembark.from_payload(
                    pending_destroyed_transport_payload
                )
            ),
            post_roll_attack_pools=(
                None
                if payload["post_roll_attack_pools"] is None
                else PostRollAttackPoolSet.from_payload(payload["post_roll_attack_pools"])
            ),
            post_roll_attack_contexts=tuple(payload["post_roll_attack_contexts"]),
        )


@dataclass(frozen=True, slots=True)
class FastDiceGroup:
    group_id: str
    attack_pool_ids: tuple[str, ...]
    allowed: bool
    reason: str | None
    attacks: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "group_id",
            _validate_identifier("FastDiceGroup group_id", self.group_id),
        )
        object.__setattr__(
            self,
            "attack_pool_ids",
            _validate_identifier_tuple("FastDiceGroup attack_pool_ids", self.attack_pool_ids),
        )
        if type(self.allowed) is not bool:
            raise GameLifecycleError("FastDiceGroup allowed must be a bool.")
        object.__setattr__(
            self,
            "reason",
            _validate_optional_identifier("FastDiceGroup reason", self.reason),
        )
        object.__setattr__(
            self,
            "attacks",
            _validate_non_negative_int("FastDiceGroup attacks", self.attacks),
        )
        if self.allowed and self.reason is not None:
            raise GameLifecycleError("Allowed FastDiceGroup must not include reason.")
        if not self.allowed and self.reason is None:
            raise GameLifecycleError("Rejected FastDiceGroup requires reason.")

    @classmethod
    def evaluate(
        cls,
        *,
        group_id: str,
        pools: tuple[RangedAttackPool, ...],
        allocation_order_can_affect_random_damage: bool,
    ) -> Self:
        pool_tuple = _validate_fast_dice_pools(pools)
        if not pool_tuple:
            return cls(
                group_id=group_id,
                attack_pool_ids=(),
                allowed=False,
                reason="empty_group",
                attacks=0,
            )
        first = pool_tuple[0]
        first_key = _fast_dice_pool_key(first)
        for pool in pool_tuple[1:]:
            if _fast_dice_pool_key(pool) != first_key:
                return cls(
                    group_id=group_id,
                    attack_pool_ids=tuple(_pool_id(pool) for pool in pool_tuple),
                    allowed=False,
                    reason="attack_characteristics_or_target_differ",
                    attacks=sum(pool.attacks for pool in pool_tuple),
                )
        if (
            allocation_order_can_affect_random_damage
            and first.weapon_profile.damage_profile.dice_expression is not None
        ):
            return cls(
                group_id=group_id,
                attack_pool_ids=tuple(_pool_id(pool) for pool in pool_tuple),
                allowed=False,
                reason="random_damage_order_can_affect_outcome",
                attacks=sum(pool.attacks for pool in pool_tuple),
            )
        return cls(
            group_id=group_id,
            attack_pool_ids=tuple(_pool_id(pool) for pool in pool_tuple),
            allowed=True,
            reason=None,
            attacks=sum(pool.attacks for pool in pool_tuple),
        )

    def to_payload(self) -> FastDiceGroupPayload:
        return {
            "group_id": self.group_id,
            "attack_pool_ids": list(self.attack_pool_ids),
            "allowed": self.allowed,
            "reason": self.reason,
            "attacks": self.attacks,
        }


def attack_sequence_step_from_token(token: object) -> AttackSequenceStep:
    if type(token) is AttackSequenceStep:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AttackSequenceStep token must be a string.")
    try:
        return AttackSequenceStep(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported AttackSequenceStep token: {token}.") from exc


def _runtime_modifier_registry(
    registry: RuntimeModifierRegistry | None,
) -> RuntimeModifierRegistry:
    if registry is None:
        return RuntimeModifierRegistry.empty()
    if type(registry) is not RuntimeModifierRegistry:
        raise GameLifecycleError("Attack sequence runtime modifier registry is invalid.")
    return registry


def wound_roll_target_number(*, strength: int, toughness: int) -> int:
    valid_strength = _validate_positive_int("strength", strength)
    valid_toughness = _validate_positive_int("toughness", toughness)
    if valid_strength >= 2 * valid_toughness:
        return 2
    if valid_strength > valid_toughness:
        return 3
    if valid_strength == valid_toughness:
        return 4
    if 2 * valid_strength <= valid_toughness:
        return 6
    return 5
