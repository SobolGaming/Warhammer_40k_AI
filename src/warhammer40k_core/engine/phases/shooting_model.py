# ruff: noqa: E501,F401,F403,F405,I001
# pyright: reportUnusedImport=false
from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.phases.shooting_imports import *

# fmt: off
if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState, OneShotWeaponUseRecord, RangedAttackHistoryRecord
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.stratagems import StratagemCatalogIndex, StratagemEligibilityContext
    from warhammer40k_core.engine.phases.shooting_handler import ShootingPhaseHandler, invalid_shooting_phase_start_faction_rule_status, _shooting_phase_start_faction_rule_drift_reason, _request_shooting_phase_start_rule_if_available
    from warhammer40k_core.engine.phases.shooting_reactions import _complete_out_of_phase_shooting, _request_active_shooting_phase_stratagem_if_available, _request_after_unit_selected_as_target_stratagem_if_available, _resolve_completed_shooting_attack_sequence_continuation, _request_friendly_unit_has_shot_stratagem_if_available, _request_enemy_unit_has_shot_stratagem_if_available, _request_shooting_end_surge_if_available, _eligible_triggered_movement_units_from_shooting_grants, _shooting_end_surge_grant_distance_bonus, _shooting_end_surge_distance_roll_spec, _attack_sequence_completed_event_id, _friendly_unit_has_shot_timing_window_id, _active_shooting_phase_stratagem_timing_window_id, _selected_as_target_timing_window_id, _enemy_unit_has_shot_timing_window_id, _target_unit_ids_for_attack_sequence, _stratagem_used_for_context, _successful_hit_target_unit_ids_for_sequence, _destroyed_target_unit_ids_for_sequence, _destroyed_enemy_unit_ids_for_sequence, _shooting_end_surge_event_already_processed
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
    "COMPLETE_SHOOTING_PHASE_OPTION_ID",
    "SELECT_SHOOTING_TYPE_DECISION_TYPE",
    "SELECT_SHOOTING_UNIT_DECISION_TYPE",
    "SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE",
    "_COMPLETE_SHOOTING_PHASE_STATUS",
    "OutOfPhaseShootingState",
    "OutOfPhaseShootingStatePayload",
    "ShootingDeclarationDecisionPayload",
    "ShootingDeclarationProposalRequestPayload",
    "ShootingPhaseState",
    "ShootingPhaseStatePayload",
    "ShootingTypeSelection",
    "ShootingTypeSelectionPayload",
    "ShootingUnitSelection",
    "ShootingUnitSelectionPayload",
    "_AvailableWeapon",
    "_ShootingModelCandidateCache",
    "_ShootingModelCandidateCacheKey",
    "_ShootingUnitCandidateCacheKey",
    "_default_stratagem_index",
)

SELECT_SHOOTING_UNIT_DECISION_TYPE = "select_shooting_unit"
SELECT_SHOOTING_TYPE_DECISION_TYPE = "select_shooting_type"
SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE = "submit_shooting_declaration"
COMPLETE_SHOOTING_PHASE_OPTION_ID = "complete_shooting_phase"
_COMPLETE_SHOOTING_PHASE_STATUS = "shooting_phase_complete"


def _default_stratagem_index() -> StratagemCatalogIndex:
    from warhammer40k_core.engine.stratagem_catalog import eleventh_edition_stratagem_index

    return eleventh_edition_stratagem_index()


class ShootingUnitSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str


class ShootingTypeSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    shooting_type: str
    request_id: str
    result_id: str


class ShootingPhaseStatePayload(TypedDict):
    battle_round: int
    active_player_id: str
    phase_complete: bool
    selected_unit_ids: list[str]
    shot_unit_ids: list[str]
    skipped_unit_ids: list[str]
    active_selection: ShootingUnitSelectionPayload | None
    selected_shooting_type: ShootingTypeSelectionPayload | None
    pending_completed_attack_sequence: AttackSequencePayload | None
    attack_pools: list[RangedAttackPoolPayload]
    attack_sequence: AttackSequencePayload | None
    allocated_model_ids_this_phase: list[str]


class OutOfPhaseShootingStatePayload(TypedDict):
    battle_round: int
    player_id: str
    parent_phase: str
    source_rule_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    source_context: JsonValue
    selected_unit_instance_id: str
    target_unit_ids: list[str] | None
    grant_effect_ids: list[str]
    attack_pools: list[RangedAttackPoolPayload]
    attack_sequence: AttackSequencePayload | None
    allocated_model_ids: list[str]


class ShootingDeclarationProposalRequestPayload(TypedDict):
    request_id: str
    decision_type: str
    actor_id: str
    game_id: str
    battle_round: int
    phase: str
    active_player_id: str
    unit_instance_id: str
    proposal_kind: str
    source_decision_request_id: str
    source_decision_result_id: str
    selected_shooting_type: str | None
    ruleset_descriptor_hash: str
    visibility_cache_key: str
    firing_deck_value: int | None
    available_weapons: list[AvailableWeaponPayload]
    target_candidates: list[JsonValue]


class ShootingDeclarationDecisionPayload(TypedDict):
    proposal_request: ShootingDeclarationProposalRequestPayload


class _AvailableWeapon(TypedDict):
    model_instance_id: str
    wargear_id: str
    weapon_profile: WeaponProfile
    firing_deck_source_unit_instance_id: NotRequired[str]
    firing_deck_source_model_instance_id: NotRequired[str]


type _ShootingUnitCandidateCacheKey = tuple[str, str, str, str, str]
type _ShootingModelCandidateCacheKey = tuple[
    str,
    str,
    str,
    str | None,
    str | None,
    str,
    str,
    bool,
    bool,
    int,
]
type _ShootingModelCandidateCache = dict[
    _ShootingModelCandidateCacheKey,
    ShootingTargetCandidate,
]


@dataclass(frozen=True, slots=True)
class ShootingUnitSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ShootingUnitSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ShootingUnitSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ShootingUnitSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ShootingUnitSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ShootingUnitSelection result_id", self.result_id),
        )

    def to_payload(self) -> ShootingUnitSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ShootingUnitSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class ShootingTypeSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    shooting_type: ShootingType
    request_id: str
    result_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ShootingTypeSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ShootingTypeSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "ShootingTypeSelection unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "shooting_type",
            shooting_type_from_token(self.shooting_type),
        )
        object.__setattr__(
            self,
            "request_id",
            _validate_identifier("ShootingTypeSelection request_id", self.request_id),
        )
        object.__setattr__(
            self,
            "result_id",
            _validate_identifier("ShootingTypeSelection result_id", self.result_id),
        )

    def to_payload(self) -> ShootingTypeSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "shooting_type": self.shooting_type.value,
            "request_id": self.request_id,
            "result_id": self.result_id,
        }

    @classmethod
    def from_payload(cls, payload: ShootingTypeSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            shooting_type=shooting_type_from_token(payload["shooting_type"]),
            request_id=payload["request_id"],
            result_id=payload["result_id"],
        )


@dataclass(frozen=True, slots=True)
class ShootingPhaseState:
    battle_round: int
    active_player_id: str
    phase_complete: bool = False
    selected_unit_ids: tuple[str, ...] = ()
    shot_unit_ids: tuple[str, ...] = ()
    skipped_unit_ids: tuple[str, ...] = ()
    active_selection: ShootingUnitSelection | None = None
    selected_shooting_type: ShootingTypeSelection | None = None
    pending_completed_attack_sequence: AttackSequence | None = None
    attack_pools: tuple[RangedAttackPool, ...] = ()
    attack_sequence: AttackSequence | None = None
    allocated_model_ids_this_phase: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ShootingPhaseState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "active_player_id",
            _validate_identifier("ShootingPhaseState active_player_id", self.active_player_id),
        )
        if type(self.phase_complete) is not bool:
            raise GameLifecycleError("ShootingPhaseState phase_complete must be a bool.")
        object.__setattr__(
            self,
            "selected_unit_ids",
            _validate_identifier_tuple(
                "ShootingPhaseState selected_unit_ids",
                self.selected_unit_ids,
            ),
        )
        object.__setattr__(
            self,
            "shot_unit_ids",
            _validate_identifier_tuple("ShootingPhaseState shot_unit_ids", self.shot_unit_ids),
        )
        object.__setattr__(
            self,
            "skipped_unit_ids",
            _validate_identifier_tuple(
                "ShootingPhaseState skipped_unit_ids",
                self.skipped_unit_ids,
            ),
        )
        if set(self.skipped_unit_ids) & set(self.shot_unit_ids):
            raise GameLifecycleError("Shooting skipped units must not also count as shot.")
        if self.active_selection is not None:
            if type(self.active_selection) is not ShootingUnitSelection:
                raise GameLifecycleError(
                    "ShootingPhaseState active_selection must be ShootingUnitSelection."
                )
            if self.active_selection.player_id != self.active_player_id:
                raise GameLifecycleError("Shooting active_selection active player drift.")
            if self.active_selection.battle_round != self.battle_round:
                raise GameLifecycleError("Shooting active_selection battle round drift.")
            if self.active_selection.unit_instance_id not in self.selected_unit_ids:
                raise GameLifecycleError("Shooting active_selection must be selected.")
            if self.active_selection.unit_instance_id in self.shot_unit_ids:
                raise GameLifecycleError("Shooting active_selection has already shot.")
            if self.active_selection.unit_instance_id in self.skipped_unit_ids:
                raise GameLifecycleError("Shooting active_selection has already been skipped.")
        if self.selected_shooting_type is not None:
            if type(self.selected_shooting_type) is not ShootingTypeSelection:
                raise GameLifecycleError(
                    "ShootingPhaseState selected_shooting_type must be ShootingTypeSelection."
                )
            if self.active_selection is None:
                raise GameLifecycleError(
                    "Shooting selected_shooting_type requires active_selection."
                )
            if self.selected_shooting_type.player_id != self.active_player_id:
                raise GameLifecycleError("Shooting selected_shooting_type active player drift.")
            if self.selected_shooting_type.battle_round != self.battle_round:
                raise GameLifecycleError("Shooting selected_shooting_type battle round drift.")
            if (
                self.selected_shooting_type.unit_instance_id
                != self.active_selection.unit_instance_id
            ):
                raise GameLifecycleError("Shooting selected_shooting_type unit drift.")
        if self.pending_completed_attack_sequence is not None:
            if type(self.pending_completed_attack_sequence) is not AttackSequence:
                raise GameLifecycleError(
                    "ShootingPhaseState pending_completed_attack_sequence must be an "
                    "AttackSequence."
                )
            if self.active_selection is not None:
                raise GameLifecycleError(
                    "Shooting pending completed attack sequence requires no active selection."
                )
            if self.selected_shooting_type is not None:
                raise GameLifecycleError(
                    "Shooting pending completed attack sequence requires no selected shooting type."
                )
        object.__setattr__(
            self,
            "attack_pools",
            _validate_attack_pools(self.attack_pools),
        )
        if self.attack_sequence is not None:
            if type(self.attack_sequence) is not AttackSequence:
                raise GameLifecycleError(
                    "ShootingPhaseState attack_sequence must be an AttackSequence."
                )
            if self.active_selection is not None:
                raise GameLifecycleError("Shooting attack_sequence requires no active_selection.")
            if self.pending_completed_attack_sequence is not None:
                raise GameLifecycleError(
                    "Shooting cannot have active and pending completed attack sequences."
                )
        object.__setattr__(
            self,
            "allocated_model_ids_this_phase",
            _validate_identifier_tuple(
                "ShootingPhaseState allocated_model_ids_this_phase",
                self.allocated_model_ids_this_phase,
            ),
        )
        if self.phase_complete and self.active_selection is not None:
            raise GameLifecycleError("Completed Shooting phase cannot have active_selection.")
        if self.phase_complete and self.attack_sequence is not None:
            raise GameLifecycleError("Completed Shooting phase cannot have attack_sequence.")
        if self.phase_complete and self.pending_completed_attack_sequence is not None:
            raise GameLifecycleError(
                "Completed Shooting phase cannot have pending completed attack sequence."
            )

    def with_unit_selection(self, selection: ShootingUnitSelection) -> Self:
        if type(selection) is not ShootingUnitSelection:
            raise GameLifecycleError("Shooting selection must be ShootingUnitSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a shooting unit after phase completion.")
        if self.active_selection is not None:
            raise GameLifecycleError("Shooting unit selection requires no active selection.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Shooting selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Shooting selection battle round drift.")
        if selection.unit_instance_id in self.selected_unit_ids:
            raise GameLifecycleError("Shooting unit was already selected.")
        if selection.unit_instance_id in self.shot_unit_ids:
            raise GameLifecycleError("Shooting unit has already shot.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=(*self.selected_unit_ids, selection.unit_instance_id),
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=selection,
            selected_shooting_type=None,
            pending_completed_attack_sequence=self.pending_completed_attack_sequence,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_shooting_type_selection(self, selection: ShootingTypeSelection) -> Self:
        if type(selection) is not ShootingTypeSelection:
            raise GameLifecycleError("Shooting type selection must be ShootingTypeSelection.")
        if self.phase_complete:
            raise GameLifecycleError("Cannot select a shooting type after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Shooting type selection requires active_selection.")
        if self.selected_shooting_type is not None:
            raise GameLifecycleError("Shooting type has already been selected.")
        if selection.player_id != self.active_player_id:
            raise GameLifecycleError("Shooting type selection player drift.")
        if selection.battle_round != self.battle_round:
            raise GameLifecycleError("Shooting type selection battle round drift.")
        if selection.unit_instance_id != self.active_selection.unit_instance_id:
            raise GameLifecycleError("Shooting type selection unit drift.")
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=self.active_selection,
            selected_shooting_type=selection,
            pending_completed_attack_sequence=self.pending_completed_attack_sequence,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_declaration(
        self,
        *,
        attack_pools: tuple[RangedAttackPool, ...],
        ineligible_unit_instance_ids: tuple[str, ...] = (),
        attack_sequence: AttackSequence | None = None,
    ) -> Self:
        if self.phase_complete:
            raise GameLifecycleError("Cannot record shooting declaration after phase completion.")
        if self.active_selection is None:
            raise GameLifecycleError("Shooting declaration requires active_selection.")
        if self.selected_shooting_type is None:
            raise GameLifecycleError("Shooting declaration requires selected_shooting_type.")
        for pool in attack_pools:
            if type(pool) is not RangedAttackPool:
                raise GameLifecycleError("Shooting declaration attack_pools must be attack pools.")
            if pool.shooting_type is not self.selected_shooting_type.shooting_type:
                raise GameLifecycleError("Shooting declaration attack pool type drift.")
        if attack_sequence is not None:
            if type(attack_sequence) is not AttackSequence:
                raise GameLifecycleError("Shooting declaration attack_sequence is invalid.")
            if attack_sequence.attack_pools != attack_pools:
                raise GameLifecycleError("Shooting declaration attack_sequence pool drift.")
            if attack_sequence.attacking_unit_instance_id != self.active_selection.unit_instance_id:
                raise GameLifecycleError("Shooting declaration attack_sequence unit drift.")
        ineligible_ids = _validate_identifier_tuple(
            "ineligible_unit_instance_ids",
            ineligible_unit_instance_ids,
        )
        completed_unit_id = self.active_selection.unit_instance_id
        shot_unit_ids = tuple(sorted({*self.shot_unit_ids, completed_unit_id, *ineligible_ids}))
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=False,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=None,
            selected_shooting_type=None,
            pending_completed_attack_sequence=self.pending_completed_attack_sequence,
            attack_pools=(*self.attack_pools, *attack_pools),
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_attack_sequence_update(
        self,
        *,
        attack_sequence: AttackSequence | None,
        allocated_model_ids_this_phase: tuple[str, ...],
    ) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=self.phase_complete,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=self.active_selection,
            selected_shooting_type=self.selected_shooting_type,
            pending_completed_attack_sequence=self.pending_completed_attack_sequence,
            attack_pools=self.attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids_this_phase,
        )

    def with_pending_completed_attack_sequence(
        self,
        attack_sequence: AttackSequence | None,
    ) -> Self:
        if attack_sequence is not None and type(attack_sequence) is not AttackSequence:
            raise GameLifecycleError(
                "Shooting pending completed attack sequence must be an AttackSequence."
            )
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=self.phase_complete,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=self.skipped_unit_ids,
            active_selection=self.active_selection,
            selected_shooting_type=self.selected_shooting_type,
            pending_completed_attack_sequence=attack_sequence,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def with_phase_complete(self, *, skipped_unit_ids: tuple[str, ...] = ()) -> Self:
        if self.active_selection is not None:
            raise GameLifecycleError("Shooting completion requires no active selection.")
        if self.selected_shooting_type is not None:
            raise GameLifecycleError("Shooting completion requires no selected shooting type.")
        if self.attack_sequence is not None:
            raise GameLifecycleError("Shooting completion requires no active attack sequence.")
        if self.pending_completed_attack_sequence is not None:
            raise GameLifecycleError(
                "Shooting completion requires no pending completed attack sequence."
            )
        skipped_ids = _validate_identifier_tuple("skipped_unit_ids", skipped_unit_ids)
        return type(self)(
            battle_round=self.battle_round,
            active_player_id=self.active_player_id,
            phase_complete=True,
            selected_unit_ids=self.selected_unit_ids,
            shot_unit_ids=self.shot_unit_ids,
            skipped_unit_ids=tuple(sorted({*self.skipped_unit_ids, *skipped_ids})),
            active_selection=None,
            selected_shooting_type=None,
            pending_completed_attack_sequence=None,
            attack_pools=self.attack_pools,
            attack_sequence=None,
            allocated_model_ids_this_phase=self.allocated_model_ids_this_phase,
        )

    def to_payload(self) -> ShootingPhaseStatePayload:
        return {
            "battle_round": self.battle_round,
            "active_player_id": self.active_player_id,
            "phase_complete": self.phase_complete,
            "selected_unit_ids": list(self.selected_unit_ids),
            "shot_unit_ids": list(self.shot_unit_ids),
            "skipped_unit_ids": list(self.skipped_unit_ids),
            "active_selection": (
                None if self.active_selection is None else self.active_selection.to_payload()
            ),
            "selected_shooting_type": (
                None
                if self.selected_shooting_type is None
                else self.selected_shooting_type.to_payload()
            ),
            "pending_completed_attack_sequence": (
                None
                if self.pending_completed_attack_sequence is None
                else self.pending_completed_attack_sequence.to_payload()
            ),
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "attack_sequence": (
                None if self.attack_sequence is None else self.attack_sequence.to_payload()
            ),
            "allocated_model_ids_this_phase": list(self.allocated_model_ids_this_phase),
        }

    @classmethod
    def from_payload(cls, payload: ShootingPhaseStatePayload) -> Self:
        active_selection = payload["active_selection"]
        selected_shooting_type = payload["selected_shooting_type"]
        pending_completed_attack_sequence = payload["pending_completed_attack_sequence"]
        return cls(
            battle_round=payload["battle_round"],
            active_player_id=payload["active_player_id"],
            phase_complete=payload["phase_complete"],
            selected_unit_ids=tuple(payload["selected_unit_ids"]),
            shot_unit_ids=tuple(payload["shot_unit_ids"]),
            skipped_unit_ids=tuple(payload["skipped_unit_ids"]),
            active_selection=(
                None
                if active_selection is None
                else ShootingUnitSelection.from_payload(active_selection)
            ),
            selected_shooting_type=(
                None
                if selected_shooting_type is None
                else ShootingTypeSelection.from_payload(selected_shooting_type)
            ),
            pending_completed_attack_sequence=(
                None
                if pending_completed_attack_sequence is None
                else AttackSequence.from_payload(pending_completed_attack_sequence)
            ),
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            attack_sequence=(
                None
                if payload["attack_sequence"] is None
                else AttackSequence.from_payload(payload["attack_sequence"])
            ),
            allocated_model_ids_this_phase=tuple(payload["allocated_model_ids_this_phase"]),
        )


@dataclass(frozen=True, slots=True)
class OutOfPhaseShootingState:
    battle_round: int
    player_id: str
    parent_phase: BattlePhase
    source_rule_id: str
    source_decision_request_id: str
    source_decision_result_id: str
    source_context: JsonValue
    selected_unit_instance_id: str
    target_unit_ids: tuple[str, ...] | None = None
    grant_effect_ids: tuple[str, ...] = ()
    attack_pools: tuple[RangedAttackPool, ...] = ()
    attack_sequence: AttackSequence | None = None
    allocated_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("OutOfPhaseShootingState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("OutOfPhaseShootingState player_id", self.player_id),
        )
        object.__setattr__(self, "parent_phase", battle_phase_kind_from_token(self.parent_phase))
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("OutOfPhaseShootingState source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_decision_request_id",
            _validate_identifier(
                "OutOfPhaseShootingState source_decision_request_id",
                self.source_decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "source_decision_result_id",
            _validate_identifier(
                "OutOfPhaseShootingState source_decision_result_id",
                self.source_decision_result_id,
            ),
        )
        object.__setattr__(self, "source_context", validate_json_value(self.source_context))
        object.__setattr__(
            self,
            "selected_unit_instance_id",
            _validate_identifier(
                "OutOfPhaseShootingState selected_unit_instance_id",
                self.selected_unit_instance_id,
            ),
        )
        if self.target_unit_ids is not None:
            object.__setattr__(
                self,
                "target_unit_ids",
                _validate_identifier_tuple(
                    "OutOfPhaseShootingState target_unit_ids",
                    self.target_unit_ids,
                ),
            )
        object.__setattr__(
            self,
            "grant_effect_ids",
            _validate_identifier_tuple(
                "OutOfPhaseShootingState grant_effect_ids",
                self.grant_effect_ids,
            ),
        )
        object.__setattr__(self, "attack_pools", _validate_attack_pools(self.attack_pools))
        if self.attack_sequence is not None:
            if type(self.attack_sequence) is not AttackSequence:
                raise GameLifecycleError(
                    "OutOfPhaseShootingState attack_sequence must be an AttackSequence."
                )
            if self.attack_sequence.attack_pools != self.attack_pools:
                raise GameLifecycleError("Out-of-phase attack_sequence pool drift.")
            if self.attack_sequence.attacking_unit_instance_id != self.selected_unit_instance_id:
                raise GameLifecycleError("Out-of-phase attack_sequence unit drift.")
        object.__setattr__(
            self,
            "allocated_model_ids",
            _validate_identifier_tuple(
                "OutOfPhaseShootingState allocated_model_ids",
                self.allocated_model_ids,
            ),
        )

    def with_declaration(
        self,
        *,
        attack_pools: tuple[RangedAttackPool, ...],
        attack_sequence: AttackSequence,
    ) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            player_id=self.player_id,
            parent_phase=self.parent_phase,
            source_rule_id=self.source_rule_id,
            source_decision_request_id=self.source_decision_request_id,
            source_decision_result_id=self.source_decision_result_id,
            source_context=self.source_context,
            selected_unit_instance_id=self.selected_unit_instance_id,
            target_unit_ids=self.target_unit_ids,
            grant_effect_ids=self.grant_effect_ids,
            attack_pools=attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids=self.allocated_model_ids,
        )

    def with_grant_effect_ids(self, grant_effect_ids: tuple[str, ...]) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            player_id=self.player_id,
            parent_phase=self.parent_phase,
            source_rule_id=self.source_rule_id,
            source_decision_request_id=self.source_decision_request_id,
            source_decision_result_id=self.source_decision_result_id,
            source_context=self.source_context,
            selected_unit_instance_id=self.selected_unit_instance_id,
            target_unit_ids=self.target_unit_ids,
            grant_effect_ids=grant_effect_ids,
            attack_pools=self.attack_pools,
            attack_sequence=self.attack_sequence,
            allocated_model_ids=self.allocated_model_ids,
        )

    def with_attack_sequence_update(
        self,
        *,
        attack_sequence: AttackSequence | None,
        allocated_model_ids: tuple[str, ...],
    ) -> Self:
        return type(self)(
            battle_round=self.battle_round,
            player_id=self.player_id,
            parent_phase=self.parent_phase,
            source_rule_id=self.source_rule_id,
            source_decision_request_id=self.source_decision_request_id,
            source_decision_result_id=self.source_decision_result_id,
            source_context=self.source_context,
            selected_unit_instance_id=self.selected_unit_instance_id,
            target_unit_ids=self.target_unit_ids,
            grant_effect_ids=self.grant_effect_ids,
            attack_pools=self.attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )

    def to_payload(self) -> OutOfPhaseShootingStatePayload:
        return {
            "battle_round": self.battle_round,
            "player_id": self.player_id,
            "parent_phase": self.parent_phase.value,
            "source_rule_id": self.source_rule_id,
            "source_decision_request_id": self.source_decision_request_id,
            "source_decision_result_id": self.source_decision_result_id,
            "source_context": self.source_context,
            "selected_unit_instance_id": self.selected_unit_instance_id,
            "target_unit_ids": None if self.target_unit_ids is None else list(self.target_unit_ids),
            "grant_effect_ids": list(self.grant_effect_ids),
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "attack_sequence": (
                None if self.attack_sequence is None else self.attack_sequence.to_payload()
            ),
            "allocated_model_ids": list(self.allocated_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: OutOfPhaseShootingStatePayload) -> Self:
        target_unit_ids = payload["target_unit_ids"]
        return cls(
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            parent_phase=battle_phase_kind_from_token(payload["parent_phase"]),
            source_rule_id=payload["source_rule_id"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            source_context=payload["source_context"],
            selected_unit_instance_id=payload["selected_unit_instance_id"],
            target_unit_ids=None if target_unit_ids is None else tuple(target_unit_ids),
            grant_effect_ids=tuple(payload["grant_effect_ids"]),
            attack_pools=tuple(
                RangedAttackPool.from_payload(pool) for pool in payload["attack_pools"]
            ),
            attack_sequence=(
                None
                if payload["attack_sequence"] is None
                else AttackSequence.from_payload(payload["attack_sequence"])
            ),
            allocated_model_ids=tuple(payload["allocated_model_ids"]),
        )
