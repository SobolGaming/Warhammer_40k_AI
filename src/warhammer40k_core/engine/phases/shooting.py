from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, NotRequired, Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    battle_phase_kind_from_token,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    AbilityKind,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
)
from warhammer40k_core.engine.attack_sequence import (
    ATTACK_ALLOCATION_DECISION_TYPES,
    ATTACK_RESOLUTION_SELECTION_DECISION_TYPES,
    SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE,
    SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE,
    AttackSequence,
    AttackSequencePayload,
    apply_allocation_order_decision,
    apply_attack_weapon_group_decision,
    apply_damage_allocation_model_decision,
    apply_destruction_reaction_decision,
    apply_feel_no_pain_decision,
    apply_precision_allocation_decision,
    apply_resolve_target_unit_decision,
    build_select_attack_weapon_group_request,
    build_select_resolve_target_unit_request,
    gathered_attack_groups_for_target,
    resolve_attack_sequence_until_blocked,
    selected_attack_weapon_group_from_result,
    selected_resolve_target_from_result,
    unresolved_target_unit_ids,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldScenario,
    PlacementError,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import (
    SELECT_ALLOCATION_ORDER_DECISION_TYPE,
    SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE,
    SELECT_DESTRUCTION_REACTION_DECISION_TYPE,
    SELECT_FEEL_NO_PAIN_DECISION_TYPE,
    SELECT_PRECISION_ALLOCATION_DECISION_TYPE,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    DecisionError,
    DecisionOption,
    DecisionRequest,
    parameterized_decision_option,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.event_log import JsonValue, canonical_json, validate_json_value
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetCandidate,
    shooting_target_candidate_for_model,
    shooting_target_candidates_for_unit,
    shooting_visibility_cache_key,
    unit_has_line_of_sight_to_target,
)
from warhammer40k_core.engine.shooting_types import ShootingType, shooting_type_from_token
from warhammer40k_core.engine.transports import (
    FiringDeckWeaponSelection,
    resolve_firing_deck_selection,
)
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.engine.weapon_abilities import (
    ASSAULT_RULE_ID,
    CLOSE_QUARTERS_RULE_ID,
    FIRE_OVERWATCH_RULE_ID,
    INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID,
    INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID,
    INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID,
    SNAP_SHOOTING_RULE_ID,
    blast_attack_bonus,
    blast_rule_id,
    has_close_quarters_weapon_keyword,
    has_weapon_keyword,
    heavy_rule_id,
    melta_damage_bonus,
    melta_rule_id,
    rapid_fire_attack_bonus,
    rapid_fire_rule_id,
    weapon_ability_selection_request,
)
from warhammer40k_core.engine.weapon_declaration import (
    SHOOTING_DECLARATION_PROPOSAL_KIND,
    AvailableWeaponPayload,
    RangedAttackPool,
    RangedAttackPoolPayload,
    ShootingDeclarationProposal,
    ShootingDeclarationProposalRequest,
    ShootingProposalValidationResult,
    WeaponDeclaration,
    attacks_for_profile,
    shooting_declaration_missing_field,
    shooting_declaration_proposal_from_json,
    unresolved_attacks_for_validation,
)
from warhammer40k_core.geometry.measurement import DistanceMeasurementContext
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState
    from warhammer40k_core.engine.reaction_queue import ReactionQueue


SELECT_SHOOTING_UNIT_DECISION_TYPE = "select_shooting_unit"
SELECT_SHOOTING_TYPE_DECISION_TYPE = "select_shooting_type"
SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE = "submit_shooting_declaration"
COMPLETE_SHOOTING_PHASE_OPTION_ID = "complete_shooting_phase"
_COMPLETE_SHOOTING_PHASE_STATUS = "shooting_phase_complete"
_FIRING_DECK_ABILITY_ID = "core-firing-deck"


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


type _ShootingUnitCandidateCacheKey = tuple[str, str, str]
type _ShootingModelCandidateCacheKey = tuple[
    str,
    str,
    str,
    str | None,
    str | None,
    str,
    str,
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
            attack_pools=self.attack_pools,
            attack_sequence=attack_sequence,
            allocated_model_ids_this_phase=allocated_model_ids_this_phase,
        )

    def with_phase_complete(self, *, skipped_unit_ids: tuple[str, ...] = ()) -> Self:
        if self.active_selection is not None:
            raise GameLifecycleError("Shooting completion requires no active selection.")
        if self.selected_shooting_type is not None:
            raise GameLifecycleError("Shooting completion requires no selected shooting type.")
        if self.attack_sequence is not None:
            raise GameLifecycleError("Shooting completion requires no active attack sequence.")
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
            attack_pools=attack_pools,
            attack_sequence=attack_sequence,
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
            "attack_pools": [pool.to_payload() for pool in self.attack_pools],
            "attack_sequence": (
                None if self.attack_sequence is None else self.attack_sequence.to_payload()
            ),
            "allocated_model_ids": list(self.allocated_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: OutOfPhaseShootingStatePayload) -> Self:
        return cls(
            battle_round=payload["battle_round"],
            player_id=payload["player_id"],
            parent_phase=battle_phase_kind_from_token(payload["parent_phase"]),
            source_rule_id=payload["source_rule_id"],
            source_decision_request_id=payload["source_decision_request_id"],
            source_decision_result_id=payload["source_decision_result_id"],
            source_context=payload["source_context"],
            selected_unit_instance_id=payload["selected_unit_instance_id"],
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


@dataclass(frozen=True, slots=True)
class ShootingPhaseHandler:
    ruleset_descriptor: RulesetDescriptor | None = None
    army_catalog: ArmyCatalog | None = None

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
        shooting_state = _ensure_shooting_phase_state(state=state)
        if shooting_state.attack_sequence is not None:
            attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
                state=state,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                attack_sequence=shooting_state.attack_sequence,
                already_allocated_model_ids=shooting_state.allocated_model_ids_this_phase,
            )
            shooting_state = shooting_state.with_attack_sequence_update(
                attack_sequence=attack_sequence,
                allocated_model_ids_this_phase=allocated_model_ids,
            )
            state.shooting_phase_state = shooting_state
            if status is not None:
                return status
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
            return _request_shooting_type_selection(
                state=state,
                decisions=decisions,
                shooting_state=shooting_state,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
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
            )

        legal_unit_ids = _legal_shooting_unit_ids(
            state=state,
            shooting_state=shooting_state,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
        )
        if not legal_unit_ids:
            state.shooting_phase_state = shooting_state.with_phase_complete()
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
            return None
        attack_sequence, allocated_model_ids, status = resolve_attack_sequence_until_blocked(
            state=state,
            decisions=decisions,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            attack_sequence=out_of_phase_state.attack_sequence,
            already_allocated_model_ids=out_of_phase_state.allocated_model_ids,
        )
        state.out_of_phase_shooting_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )
        if status is not None:
            return status
        completed_state = state.out_of_phase_shooting_state
        if completed_state.attack_sequence is not None:
            raise GameLifecycleError("Out-of-phase shooting completion state drift.")
        decisions.event_log.append(
            "out_of_phase_shooting_completed",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "player_id": completed_state.player_id,
                "parent_phase": completed_state.parent_phase.value,
                "source_rule_id": completed_state.source_rule_id,
                "selected_unit_instance_id": completed_state.selected_unit_instance_id,
            },
        )
        state.out_of_phase_shooting_state = None
        return LifecycleStatus.advanced(
            stage=GameLifecycleStage.BATTLE,
            payload={
                "phase": completed_state.parent_phase.value,
                "phase_body_status": "out_of_phase_shooting_complete",
                "source_rule_id": completed_state.source_rule_id,
            },
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
        unit = _unit_by_id(state=state, unit_instance_id=unit_instance_id)
        legal_types = _legal_shooting_types_for_unit(
            state=state,
            unit=unit,
            ruleset_descriptor=_ruleset_descriptor_for_handler(self),
            army_catalog=_army_catalog_for_handler(self),
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
        if result.decision_type == SELECT_SHOOTING_UNIT_DECISION_TYPE:
            _apply_shooting_unit_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
            )
            return None
        if result.decision_type == SELECT_SHOOTING_TYPE_DECISION_TYPE:
            _apply_shooting_type_selection_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
            )
            return None
        if result.decision_type == SUBMIT_SHOOTING_DECLARATION_DECISION_TYPE:
            _apply_shooting_declaration_decision(
                state=state,
                result=result,
                decisions=decisions,
                ruleset_descriptor=_ruleset_descriptor_for_handler(self),
                army_catalog=_army_catalog_for_handler(self),
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
            )
        raise GameLifecycleError("ShootingPhaseHandler received unsupported decision_type.")


def _request_shooting_type_selection(
    *,
    state: GameState,
    decisions: DecisionController,
    shooting_state: ShootingPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> LifecycleStatus:
    active_selection = shooting_state.active_selection
    if active_selection is None:
        raise GameLifecycleError("Shooting type request requires active_selection.")
    unit = _unit_by_id(state=state, unit_instance_id=active_selection.unit_instance_id)
    legal_types = _legal_shooting_types_for_unit(
        state=state,
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
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
) -> LifecycleStatus:
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    unit = _unit_by_id(state=state, unit_instance_id=active_selection.unit_instance_id)
    available_weapons = _available_weapons_for_unit(
        state=state,
        unit=unit,
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
    target_candidates: list[JsonValue] = []
    target_candidate_cache: dict[
        _ShootingUnitCandidateCacheKey,
        tuple[ShootingTargetCandidate, ...],
    ] = {}
    for weapon in available_weapons:
        profile = weapon["weapon_profile"]
        candidate_cache_key = _shooting_unit_candidate_cache_key(weapon)
        if candidate_cache_key not in target_candidate_cache:
            target_candidate_cache[candidate_cache_key] = shooting_target_candidates_for_unit(
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                attacker_unit=unit,
                weapon_profile=profile,
                target_unit_ids=candidate_target_unit_ids,
                terrain_features=terrain_features,
            )
        candidates = target_candidate_cache[candidate_cache_key]
        target_candidates.extend(
            _target_candidate_payload_for_request(
                state=state,
                scenario=scenario,
                candidate=cast(dict[str, JsonValue], candidate.to_payload()),
                unit=unit,
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
        "firing_deck_value": _firing_deck_value_for_unit(
            unit=unit,
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
) -> LifecycleStatus:
    if state.out_of_phase_shooting_state is not None:
        raise GameLifecycleError("Out-of-phase shooting state is already active.")
    selection = ShootingUnitSelection(
        player_id=player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        request_id=source_decision_request_id,
        result_id=source_decision_result_id,
    )
    state.out_of_phase_shooting_state = OutOfPhaseShootingState(
        battle_round=state.battle_round,
        player_id=player_id,
        parent_phase=parent_phase,
        source_rule_id=source_rule_id,
        source_decision_request_id=source_decision_request_id,
        source_decision_result_id=source_decision_result_id,
        source_context=source_context,
        selected_unit_instance_id=unit_instance_id,
    )
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
            attacker_unit_id=unit.unit_instance_id,
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
    target_unit = _unit_by_id(state=state, unit_instance_id=target_unit_id)
    selection_request = weapon_ability_selection_request(
        weapon_profile,
        AbilityKind.ANTI_KEYWORD,
        target_keywords=target_unit.keywords,
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
        return _shooting_types_for_selected_type(
            state=state,
            base_types=base_types,
            unit=unit,
            weapon_profile=weapon_profile,
            selected_shooting_type=selected_shooting_type,
            player_id=player_id,
            army_catalog=army_catalog,
        )
    if _advanced_unit_is_restricted_to_assault_weapons(
        state=state,
        unit=unit,
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
    shooting_type = shooting_type_from_token(selected_shooting_type)
    advanced = _unit_advanced_this_turn(state=state, unit=unit, player_id=player_id)
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
        if _unit_has_vehicle_or_monster_keyword(unit) or has_close_quarters_weapon_keyword(
            weapon_profile
        ):
            return (ShootingType.CLOSE_QUARTERS,)
        return ()
    if shooting_type is ShootingType.INDIRECT:
        if advanced or not _unit_has_indirect_ranged_weapon(
            unit=unit,
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


def _apply_shooting_unit_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> None:
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
        )
        state.shooting_phase_state = shooting_state.with_phase_complete(
            skipped_unit_ids=skipped_unit_ids,
        )
        decisions.event_log.append(
            "shooting_phase_completion_declared",
            _shooting_phase_status_payload(
                state=state,
                phase_body_status=_COMPLETE_SHOOTING_PHASE_STATUS,
                skipped_unit_ids=skipped_unit_ids,
            ),
        )
        return

    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    legal_unit_ids = _legal_shooting_unit_ids(
        state=state,
        shooting_state=shooting_state,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
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
    state.shooting_phase_state = shooting_state.with_unit_selection(selection)
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


def _apply_shooting_type_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> None:
    _validate_shooting_phase_state(state)
    active_player_id = _active_player_id(state)
    if result.actor_id != active_player_id:
        raise GameLifecycleError("Shooting type selection actor must be the active player.")
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        raise GameLifecycleError("Shooting type selection requires active_selection.")
    if shooting_state.selected_shooting_type is not None:
        raise GameLifecycleError("Shooting type has already been selected.")
    payload = _decision_payload_object(result.payload)
    unit_instance_id = _payload_string(payload, key="unit_instance_id")
    if unit_instance_id != shooting_state.active_selection.unit_instance_id:
        raise GameLifecycleError("Shooting type selection unit drift.")
    shooting_type = shooting_type_from_token(_payload_string(payload, key="shooting_type"))
    unit = _unit_by_id(state=state, unit_instance_id=unit_instance_id)
    legal_types = _legal_shooting_types_for_unit(
        state=state,
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    )
    if shooting_type not in legal_types:
        raise GameLifecycleError("Shooting type selection is not currently legal.")
    selection = ShootingTypeSelection(
        player_id=active_player_id,
        battle_round=state.battle_round,
        unit_instance_id=unit_instance_id,
        shooting_type=shooting_type,
        request_id=result.request_id,
        result_id=result.result_id,
    )
    state.shooting_phase_state = shooting_state.with_shooting_type_selection(selection)
    decisions.event_log.append(
        "shooting_type_selected",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": active_player_id,
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": unit_instance_id,
                "shooting_type": shooting_type.value,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "phase_body_status": "shooting_type_selected",
            }
        ),
    )


def _apply_shooting_declaration_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> None:
    if _apply_out_of_phase_shooting_declaration_decision(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
    ):
        return
    _validate_shooting_phase_state(state)
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.active_selection is None:
        raise GameLifecycleError("Shooting declaration requires active_selection.")
    proposal = shooting_declaration_proposal_from_json(result.payload)
    attack_pools, ineligible_unit_ids = _attack_pools_for_proposal(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        result_id=result.result_id,
    )
    attack_sequence = AttackSequence.start(
        sequence_id=f"attack-sequence:{result.result_id}",
        attacker_player_id=_active_player_id(state),
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=attack_pools,
    )
    state.shooting_phase_state = shooting_state.with_declaration(
        attack_pools=attack_pools,
        ineligible_unit_instance_ids=ineligible_unit_ids,
        attack_sequence=attack_sequence,
    )
    decisions.event_log.append(
        "shooting_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": _active_player_id(state),
                "phase": BattlePhase.SHOOTING.value,
                "unit_instance_id": proposal.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal.proposal_request_id,
                "visibility_cache_key": proposal.visibility_cache_key,
                "attack_pools": [pool.to_payload() for pool in attack_pools],
                "ineligible_unit_instance_ids": list(ineligible_unit_ids),
                "phase_body_status": "declaration_accepted",
            }
        ),
    )


def _apply_out_of_phase_shooting_declaration_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
) -> bool:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is None:
        return False
    proposal = shooting_declaration_proposal_from_json(result.payload)
    if (
        proposal.source_decision_request_id != out_of_phase_state.source_decision_request_id
        or proposal.source_decision_result_id != out_of_phase_state.source_decision_result_id
    ):
        return False
    attack_pools, ineligible_unit_ids = _attack_pools_for_proposal(
        state=state,
        proposal=proposal,
        ruleset_descriptor=ruleset_descriptor,
        army_catalog=army_catalog,
        decisions=decisions,
        result_id=result.result_id,
        shooting_player_id=out_of_phase_state.player_id,
        out_of_phase_state=out_of_phase_state,
    )
    if ineligible_unit_ids:
        raise GameLifecycleError("Out-of-phase shooting cannot mark extra units as shot.")
    attack_sequence = AttackSequence.start(
        sequence_id=f"out-of-phase-attack-sequence:{result.result_id}",
        attacker_player_id=out_of_phase_state.player_id,
        attacking_unit_instance_id=proposal.unit_instance_id,
        attack_pools=attack_pools,
    )
    state.out_of_phase_shooting_state = out_of_phase_state.with_declaration(
        attack_pools=attack_pools,
        attack_sequence=attack_sequence,
    )
    decisions.event_log.append(
        "out_of_phase_shooting_declaration_accepted",
        validate_json_value(
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "player_id": out_of_phase_state.player_id,
                "parent_phase": out_of_phase_state.parent_phase.value,
                "source_rule_id": out_of_phase_state.source_rule_id,
                "unit_instance_id": proposal.unit_instance_id,
                "request_id": result.request_id,
                "result_id": result.result_id,
                "proposal_request_id": proposal.proposal_request_id,
                "visibility_cache_key": proposal.visibility_cache_key,
                "attack_pools": [pool.to_payload() for pool in attack_pools],
            }
        ),
    )
    return True


def _apply_attack_sequence_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
) -> LifecycleStatus | None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        attack_sequence, allocated_model_ids, status = _apply_attack_sequence_decision_to_sequence(
            state=state,
            result=result,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=out_of_phase_state.attack_sequence,
            already_allocated_model_ids=out_of_phase_state.allocated_model_ids,
        )
        state.out_of_phase_shooting_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=attack_sequence,
            allocated_model_ids=allocated_model_ids,
        )
        return status
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.attack_sequence is None:
        raise GameLifecycleError("Attack sequence decision requires active attack_sequence.")
    attack_sequence, allocated_model_ids, status = _apply_attack_sequence_decision_to_sequence(
        state=state,
        result=result,
        decisions=decisions,
        ruleset_descriptor=ruleset_descriptor,
        attack_sequence=shooting_state.attack_sequence,
        already_allocated_model_ids=shooting_state.allocated_model_ids_this_phase,
    )
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=attack_sequence,
        allocated_model_ids_this_phase=allocated_model_ids,
    )
    return status


def _apply_attack_sequence_selection_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> None:
    out_of_phase_state = state.out_of_phase_shooting_state
    if out_of_phase_state is not None and out_of_phase_state.attack_sequence is not None:
        state.out_of_phase_shooting_state = out_of_phase_state.with_attack_sequence_update(
            attack_sequence=_apply_attack_sequence_selection_to_sequence(
                attack_sequence=out_of_phase_state.attack_sequence,
                result=result,
                decisions=decisions,
            ),
            allocated_model_ids=out_of_phase_state.allocated_model_ids,
        )
        return
    shooting_state = state.shooting_phase_state
    if shooting_state is None or shooting_state.attack_sequence is None:
        raise GameLifecycleError("Attack sequence selection requires active attack_sequence.")
    state.shooting_phase_state = shooting_state.with_attack_sequence_update(
        attack_sequence=_apply_attack_sequence_selection_to_sequence(
            attack_sequence=shooting_state.attack_sequence,
            result=result,
            decisions=decisions,
        ),
        allocated_model_ids_this_phase=shooting_state.allocated_model_ids_this_phase,
    )


def _apply_attack_sequence_selection_to_sequence(
    *,
    attack_sequence: AttackSequence,
    result: DecisionResult,
    decisions: DecisionController,
) -> AttackSequence:
    if result.decision_type == SELECT_RESOLVE_TARGET_UNIT_DECISION_TYPE:
        return apply_resolve_target_unit_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
    if result.decision_type == SELECT_ATTACK_WEAPON_GROUP_DECISION_TYPE:
        return apply_attack_weapon_group_decision(
            decisions=decisions,
            attack_sequence=attack_sequence,
            result=result,
        )
    raise GameLifecycleError("Unsupported attack sequence selection decision type.")


def _apply_attack_sequence_decision_to_sequence(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
    ruleset_descriptor: RulesetDescriptor,
    attack_sequence: AttackSequence,
    already_allocated_model_ids: tuple[str, ...],
) -> tuple[AttackSequence | None, tuple[str, ...], LifecycleStatus | None]:
    if result.decision_type == SELECT_ALLOCATION_ORDER_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_allocation_order_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    elif result.decision_type == SELECT_DAMAGE_ALLOCATION_MODEL_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_damage_allocation_model_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    elif result.decision_type == SELECT_PRECISION_ALLOCATION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_precision_allocation_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    elif result.decision_type == SELECT_FEEL_NO_PAIN_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_feel_no_pain_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    elif result.decision_type == SELECT_DESTRUCTION_REACTION_DECISION_TYPE:
        updated_sequence, allocated_model_ids, status = apply_destruction_reaction_decision(
            state=state,
            decisions=decisions,
            ruleset_descriptor=ruleset_descriptor,
            attack_sequence=attack_sequence,
            result=result,
            already_allocated_model_ids=already_allocated_model_ids,
        )
    else:
        raise GameLifecycleError("Unsupported attack sequence decision type.")
    return updated_sequence, allocated_model_ids, status


def _validate_declaration_submission(
    *,
    state: GameState,
    proposal: ShootingDeclarationProposal,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
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
    unit = _unit_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    if not _unit_can_select_to_shoot(state=state, unit=unit, army_catalog=army_catalog):
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
    unit = _unit_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    if not _unit_can_select_to_shoot(
        state=state,
        unit=unit,
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
) -> _AttackPoolValidationResult:
    player_id = proposal.player_id if shooting_player_id is None else shooting_player_id
    unit = _unit_by_id(state=state, unit_instance_id=proposal.unit_instance_id)
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    selected_shooting_type = _selected_shooting_type_for_declaration(
        state=state,
        out_of_phase_state=out_of_phase_state,
    )
    available_weapon_by_key = _available_weapon_by_declaration_key(
        state=state,
        unit=unit,
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
    allowed_out_of_phase_target_ids = _out_of_phase_allowed_target_unit_ids(out_of_phase_state)
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
        pistol_validation = _validate_model_pistol_exclusivity(
            state=state,
            selected_unit=unit,
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
            attacker_unit=unit,
            attacker_model_instance_id=declaration.attacker_model_instance_id,
            weapon_profile=weapon_profile,
            target_unit_id=declaration.target_unit_instance_id,
            terrain_features=terrain_features,
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
        target_unit = _unit_by_id(
            state=state,
            unit_instance_id=declaration.target_unit_instance_id,
        )
        ability_selection_validation = _validate_duplicate_weapon_ability_selection(
            proposal=proposal,
            declaration=declaration,
            declaration_index=declaration_index,
            weapon_profile=weapon_profile,
            target_unit=target_unit,
            player_id=player_id,
        )
        if ability_selection_validation is not None:
            return ability_selection_validation
        allowed_shooting_types = _shooting_types_for_declaration_candidate(
            state=state,
            scenario=scenario,
            candidate=candidate,
            declaration=declaration,
            unit=unit,
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
            unit=unit,
            target_unit=target_unit,
            weapon_profile=weapon_profile,
            shooting_type=declaration.shooting_type,
            base_attacks=attacks,
            base_targeting_rule_ids=candidate.targeting_rule_ids,
            base_hit_roll_modifier=candidate.hit_roll_modifier,
            target_within_half_range=target_within_half_range,
            terrain_features=terrain_features,
            player_id=player_id,
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
    target_unit: UnitInstance,
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
        target_keywords=target_unit.keywords,
        actor_id=player_id,
        request_id=(
            f"{proposal.proposal_request_id}:declaration-{declaration_index:03d}:anti-keyword"
        ),
        source_context={
            "phase": BattlePhase.SHOOTING.value,
            "proposal_request_id": proposal.proposal_request_id,
            "declaration_index": declaration_index,
            "target_unit_instance_id": target_unit.unit_instance_id,
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


def _out_of_phase_allowed_target_unit_ids(
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
    return (_validate_identifier("Fire Overwatch triggering unit id", triggering_unit_id),)


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
        return _shooting_types_for_selected_type(
            state=state,
            base_types=candidate.shooting_types,
            unit=unit,
            weapon_profile=weapon_profile,
            selected_shooting_type=selected_shooting_type,
            player_id=player_id,
            army_catalog=army_catalog,
        )
    if _advanced_unit_is_restricted_to_assault_weapons(
        state=state,
        unit=unit,
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
    unit: UnitInstance,
    target_unit: UnitInstance,
    weapon_profile: WeaponProfile,
    shooting_type: ShootingType,
    base_attacks: int,
    base_targeting_rule_ids: tuple[str, ...],
    base_hit_roll_modifier: int,
    target_within_half_range: bool,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    player_id: str | None = None,
) -> tuple[int, tuple[str, ...], int]:
    attacks = base_attacks
    hit_roll_modifier = base_hit_roll_modifier
    targeting_rule_ids: list[str] = list(base_targeting_rule_ids)

    rapid_bonus = rapid_fire_attack_bonus(
        weapon_profile,
        target_within_half_range=target_within_half_range,
    )
    if rapid_bonus > 0:
        attacks += rapid_bonus
        targeting_rule_ids.append(rapid_fire_rule_id(rapid_bonus))

    if has_weapon_keyword(weapon_profile, WeaponKeyword.BLAST):
        blast_bonus = blast_attack_bonus(target_model_count=len(target_unit.alive_own_models()))
        if blast_bonus > 0:
            attacks += blast_bonus
            targeting_rule_ids.append(blast_rule_id(blast_bonus))

    melta_bonus = melta_damage_bonus(
        weapon_profile,
        target_within_half_range=target_within_half_range,
    )
    if melta_bonus > 0:
        targeting_rule_ids.append(melta_rule_id(melta_bonus))

    if has_weapon_keyword(weapon_profile, WeaponKeyword.HEAVY) and _unit_remained_stationary(
        state=state,
        unit=unit,
        player_id=player_id,
    ):
        hit_roll_modifier += 1
        targeting_rule_ids.append(heavy_rule_id())

    if shooting_type is ShootingType.INDIRECT and has_weapon_keyword(
        weapon_profile, WeaponKeyword.INDIRECT_FIRE
    ):
        if INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID not in targeting_rule_ids:
            targeting_rule_ids.append(INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID)
        targeting_rule_ids.append(INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID)
        if _unit_remained_stationary(state=state, unit=unit, player_id=player_id) and (
            _target_visible_to_friendly_unit(
                state=state,
                scenario=scenario,
                ruleset_descriptor=ruleset_descriptor,
                target_unit_instance_id=target_unit.unit_instance_id,
                terrain_features=terrain_features,
                player_id=player_id,
            )
        ):
            targeting_rule_ids.append(INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID)

    return attacks, tuple(dict.fromkeys(targeting_rule_ids)), hit_roll_modifier


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
    battlefield = scenario.battlefield_state
    unit_placement = battlefield.unit_placement_by_id(unit.unit_instance_id)
    target_placement = battlefield.unit_placement_by_id(target_unit_id)
    for attacker_model_placement in unit_placement.model_placements:
        attacker_model = geometry_model_for_placement(
            model=scenario.model_instance_for_placement(attacker_model_placement),
            placement=attacker_model_placement,
        )
        for target_model_placement in target_placement.model_placements:
            target_model = geometry_model_for_placement(
                model=scenario.model_instance_for_placement(target_model_placement),
                placement=target_model_placement,
            )
            if DistanceMeasurementContext.from_models(
                attacker_model,
                target_model,
            ).closest_distance_inches() <= float(range_inches):
                return True
    return False


def _unit_remained_stationary(
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
    if advanced_state is not None:
        return False
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    if fell_back_state is not None:
        return False
    movement_state = state.movement_phase_state
    if movement_state is None:
        return True
    if unit.unit_instance_id not in movement_state.moved_unit_ids:
        return True
    for record in movement_state.movement_distance_records:
        if record.unit_instance_id == unit.unit_instance_id:
            return record.maximum_model_distance_inches <= 3.0
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


def _available_weapon_by_declaration_key(
    *,
    state: GameState,
    unit: UnitInstance,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    selected_shooting_type: ShootingType | None = None,
) -> dict[tuple[str, str, str, str | None, str | None], _AvailableWeapon]:
    return {
        _available_weapon_key(weapon): weapon
        for weapon in _available_weapons_for_unit(
            state=state,
            unit=unit,
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
            _available_weapons_for_model(
                model=model,
                unit=unit,
                army_catalog=army_catalog,
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


def _legal_shooting_unit_ids(
    *,
    state: GameState,
    shooting_state: ShootingPhaseState,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
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
        unit = _unit_by_id(state=state, unit_instance_id=unit_id)
        if not _unit_can_select_to_shoot(state=state, unit=unit, army_catalog=army_catalog):
            continue
        if _unit_has_legal_shooting_declaration(
            state=state,
            scenario=scenario,
            unit=unit,
            ruleset_descriptor=ruleset_descriptor,
            army_catalog=army_catalog,
        ):
            legal.append(unit_id)
    return tuple(sorted(legal))


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
) -> bool:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    terrain_features = _terrain_features_for_state(state)
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


def _legal_shooting_types_for_unit(
    *,
    state: GameState,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    army_catalog: ArmyCatalog,
    player_id: str | None = None,
    target_unit_ids: tuple[str, ...] | None = None,
) -> tuple[ShootingType, ...]:
    actor_id = _active_player_id(state) if player_id is None else player_id
    resolved_target_unit_ids = (
        _enemy_placed_unit_ids(state=state, player_id=actor_id)
        if target_unit_ids is None
        else _validate_identifier_tuple("shooting declaration target_unit_ids", target_unit_ids)
    )
    scenario = _battlefield_scenario(state)
    terrain_features = _terrain_features_for_state(state)
    candidate_cache: _ShootingModelCandidateCache = {}
    legal_types: set[ShootingType] = set()
    for shooting_type in (
        ShootingType.NORMAL,
        ShootingType.ASSAULT,
        ShootingType.CLOSE_QUARTERS,
        ShootingType.INDIRECT,
    ):
        for weapon in _available_weapons_for_unit(
            state=state,
            unit=unit,
            army_catalog=army_catalog,
            player_id=actor_id,
            selected_shooting_type=shooting_type,
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
                )
                if not candidate.is_legal:
                    continue
                if _shooting_types_for_selected_type(
                    state=state,
                    base_types=candidate.shooting_types,
                    unit=unit,
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
) -> ShootingTargetCandidate:
    cache_key = _shooting_model_candidate_cache_key(weapon=weapon, target_unit_id=target_unit_id)
    if cache_key not in cache:
        cache[cache_key] = shooting_target_candidate_for_model(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            attacker_unit=attacker_unit,
            attacker_model_instance_id=weapon["model_instance_id"],
            weapon_profile=weapon["weapon_profile"],
            target_unit_id=target_unit_id,
            terrain_features=terrain_features,
        )
    return cache[cache_key]


def _shooting_unit_candidate_cache_key(
    weapon: _AvailableWeapon,
) -> _ShootingUnitCandidateCacheKey:
    profile = weapon["weapon_profile"]
    return (
        weapon["wargear_id"],
        profile.profile_id,
        _weapon_profile_cache_fingerprint(profile),
    )


def _shooting_model_candidate_cache_key(
    *,
    weapon: _AvailableWeapon,
    target_unit_id: str,
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
        and not _unit_has_assault_ranged_weapon(unit=unit, army_catalog=army_catalog)
    ):
        return False
    fell_back_state = state.fell_back_unit_state_for_unit(
        player_id=actor_id,
        battle_round=state.battle_round,
        unit_instance_id=unit.unit_instance_id,
    )
    return not (fell_back_state is not None and not fell_back_state.can_shoot)


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


def _unit_has_assault_ranged_weapon(*, unit: UnitInstance, army_catalog: ArmyCatalog) -> bool:
    for model in unit.own_models:
        for weapon in _available_weapons_for_model(
            model=model,
            unit=unit,
            army_catalog=army_catalog,
        ):
            if has_weapon_keyword(weapon["weapon_profile"], WeaponKeyword.ASSAULT):
                return True
    return False


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


def _unit_has_already_shot(*, state: GameState, unit_instance_id: str) -> bool:
    shooting_state = state.shooting_phase_state
    return shooting_state is not None and unit_instance_id in shooting_state.shot_unit_ids


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
    state.shooting_phase_state = ShootingPhaseState(
        battle_round=state.battle_round,
        active_player_id=active_player_id,
    )
    return state.shooting_phase_state


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
    mission_setup = state.mission_setup
    if mission_setup is None:
        raise GameLifecycleError("Shooting phase requires mission_setup.")
    return mission_setup.terrain_features


def _active_player_id(state: GameState) -> str:
    if state.active_player_id is None:
        raise GameLifecycleError("Shooting phase requires active_player_id.")
    return state.active_player_id


def _active_player_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    try:
        placed_army = battlefield_state.placed_army_for_player(player_id)
    except PlacementError:
        return ()
    return tuple(sorted(placement.unit_instance_id for placement in placed_army.unit_placements))


def _enemy_placed_unit_ids(*, state: GameState, player_id: str) -> tuple[str, ...]:
    battlefield_state = state.battlefield_state
    if battlefield_state is None:
        raise GameLifecycleError("Shooting phase requires battlefield_state.")
    unit_ids: list[str] = []
    for placed_army in battlefield_state.placed_armies:
        if placed_army.player_id == player_id:
            continue
        unit_ids.extend(placement.unit_instance_id for placement in placed_army.unit_placements)
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
        unit = _unit_by_id(state=state, unit_instance_id=unit_id)
        options.append(
            DecisionOption(
                option_id=unit_id,
                label=unit.name,
                payload={"unit_instance_id": unit_id},
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
    datasheet = army_catalog.datasheet_by_id(unit.datasheet_id)
    descriptors = tuple(
        ability for ability in datasheet.abilities if ability.ability_id == _FIRING_DECK_ABILITY_ID
    )
    if not descriptors:
        return None
    if len(descriptors) > 1:
        raise GameLifecycleError("Datasheet must not contain duplicate Firing Deck descriptors.")
    descriptor = next(iter(descriptors))
    if len(descriptor.parameter_tokens) != 1:
        raise GameLifecycleError("Firing Deck descriptor requires exactly one value token.")
    token = descriptor.parameter_tokens[0]
    try:
        value = int(token)
    except ValueError as exc:
        raise GameLifecycleError("Firing Deck descriptor value token must be an int.") from exc
    return _validate_positive_int("Firing Deck descriptor value", value)


def _unit_has_vehicle_or_monster_keyword(unit: UnitInstance) -> bool:
    return _unit_has_keyword(unit, "VEHICLE") or _unit_has_keyword(unit, "MONSTER")


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


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


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
