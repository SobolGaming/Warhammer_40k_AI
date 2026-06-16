from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import TYPE_CHECKING, Self, TypedDict, cast

from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.weapon_profiles import (
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelPlacementRecord,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest, DecisionRequestPayload
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
    terrain_endpoint_placement_violation,
)
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.hazard import (
    CORE_HAZARD_ROLLS_RULE_ID,
    HAZARD_ROLL_FAILURE_THRESHOLD,
    hazard_mortal_wounds_per_failed_roll,
    hazard_roll_failed,
    hazard_roll_spec,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatus
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    unit_placement_coherency_result,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.unit_rule_effects import (
    embark_transport_forbidden_effect_source_ids,
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model

if TYPE_CHECKING:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplication,
        MortalWoundApplicationPayload,
    )
    from warhammer40k_core.engine.game_state import GameState


class TransportMovementStatus(StrEnum):
    NOT_MOVED = "not_moved"
    REMAIN_STATIONARY = "remain_stationary"
    NORMAL_MOVE = "normal_move"
    ADVANCE = "advance"
    FALL_BACK = "fall_back"
    INGRESS_MOVE = "ingress_move"


class TransportRestrictionOverrideKind(StrEnum):
    ALLOW_EMBARK_AFTER_DISEMBARK = "allow_embark_after_disembark"
    ALLOW_DISEMBARK_AFTER_ADVANCE_OR_FALL_BACK = "allow_disembark_after_advance_or_fall_back"


class DisembarkModeKind(StrEnum):
    RAPID_DISEMBARK = "rapid_disembark"
    TACTICAL_DISEMBARK = "tactical_disembark"
    COMBAT_DISEMBARK = "combat_disembark"
    DESTROYED_TRANSPORT = "destroyed_transport"
    EMERGENCY_DISEMBARK = "emergency_disembark"


class TransportOperationViolationCode(StrEnum):
    TRANSPORT_KEYWORD_REQUIRED = "transport_keyword_required"
    TRANSPORT_DATASHEET_MISMATCH = "transport_datasheet_mismatch"
    FRIENDLY_TRANSPORT_REQUIRED = "friendly_transport_required"
    CAPACITY_EXCEEDED = "capacity_exceeded"
    UNIT_ALREADY_EMBARKED = "unit_already_embarked"
    UNIT_NOT_EMBARKED = "unit_not_embarked"
    UNIT_DID_NOT_START_PHASE_EMBARKED = "unit_did_not_start_phase_embarked"
    EMBARK_AFTER_DISEMBARK_FORBIDDEN = "embark_after_disembark_forbidden"
    EMBARK_FORBIDDEN_BY_EFFECT = "embark_forbidden_by_effect"
    EMBARK_DISTANCE = "embark_distance"
    DISEMBARK_DISTANCE = "disembark_distance"
    TRANSPORT_ADVANCED_OR_FELL_BACK = "transport_advanced_or_fell_back"
    UNIT_PLACEMENT_DRIFT = "unit_placement_drift"
    MODEL_OVERLAP = "model_overlap"
    BATTLEFIELD_EDGE_CROSSED = "battlefield_edge_crossed"
    TERRAIN_ENDPOINT_ILLEGAL = "terrain_endpoint_illegal"
    OBJECTIVE_MARKER_ENDPOINT_OVERLAP = "objective_marker_endpoint_overlap"
    ENEMY_ENGAGEMENT_RANGE = "enemy_engagement_range"
    UNIT_COHERENCY_BROKEN = "unit_coherency_broken"
    COMBAT_DISEMBARK_TACTICAL_AVAILABLE = "combat_disembark_tactical_available"
    FIRING_DECK_CAPACITY_EXCEEDED = "firing_deck_capacity_exceeded"
    FIRING_DECK_UNIT_NOT_EMBARKED = "firing_deck_unit_not_embarked"
    FIRING_DECK_UNIT_ALREADY_SHOT = "firing_deck_unit_already_shot"
    FIRING_DECK_MODEL_DRIFT = "firing_deck_model_drift"
    FIRING_DECK_DUPLICATE_MODEL_SELECTION = "firing_deck_duplicate_model_selection"
    FIRING_DECK_MELEE_WEAPON = "firing_deck_melee_weapon"
    FIRING_DECK_ONE_SHOT_WEAPON = "firing_deck_one_shot_weapon"


class TransportCapacityProfilePayload(TypedDict):
    transport_datasheet_id: str
    max_model_count: int
    allowed_keywords: list[str]
    excluded_keywords: list[str]
    source_id: str


class TransportRestrictionOverridePayload(TypedDict):
    override_kind: str
    source_rule_id: str


class TransportCargoStatePayload(TypedDict):
    player_id: str
    transport_unit_instance_id: str
    capacity_profile: TransportCapacityProfilePayload
    embarked_unit_instance_ids: list[str]
    phase_battle_round: int | None
    started_phase_embarked_unit_instance_ids: list[str]
    disembarked_this_phase_unit_instance_ids: list[str]


class TransportOperationViolationPayload(TypedDict):
    violation_code: str
    message: str
    unit_instance_id: str | None
    model_instance_id: str | None
    blocker_id: str | None
    source_rule_id: str | None


class EmbarkSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    movement_phase_action: str
    restriction_overrides: list[TransportRestrictionOverridePayload]


class EmbarkResolutionPayload(TypedDict):
    selection: EmbarkSelectionPayload
    is_valid: bool
    violations: list[TransportOperationViolationPayload]
    updated_cargo_state: TransportCargoStatePayload | None
    transition_batch: BattlefieldTransitionBatchPayload | None


class DisembarkSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    attempted_placement: UnitPlacementPayload
    disembark_mode: str
    transport_movement_status: str
    restriction_overrides: list[TransportRestrictionOverridePayload]


class DisembarkedUnitStatePayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: str
    can_move_further: bool
    can_choose_remain_stationary: bool
    can_declare_charge: bool
    battle_shocked_until: str | None
    source_rule_id: str


class DisembarkResolutionPayload(TypedDict):
    selection: DisembarkSelectionPayload
    is_valid: bool
    violations: list[TransportOperationViolationPayload]
    coherency_result: UnitCoherencyResultPayload
    updated_cargo_state: TransportCargoStatePayload | None
    disembarked_unit_state: DisembarkedUnitStatePayload | None
    transition_batch: BattlefieldTransitionBatchPayload | None


class DestroyedTransportModelRollPayload(TypedDict):
    model_instance_id: str
    roll_state: DiceRollStatePayload
    mortal_wound_inflicted: bool


class DestroyedTransportDisembarkPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: str
    placement: DisembarkResolutionPayload
    roll_threshold: int
    mortal_wounds_per_failed_roll: int
    model_rolls: list[DestroyedTransportModelRollPayload]
    mortal_wound_count: int
    destroyed_model_instance_ids: list[str]
    disembarked_unit_state: DisembarkedUnitStatePayload | None


class CombatDisembarkPayload(TypedDict):
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    placement: DisembarkResolutionPayload
    roll_threshold: int
    mortal_wounds_per_failed_roll: int
    model_rolls: list[DestroyedTransportModelRollPayload]
    mortal_wound_count: int
    disembarked_unit_state: DisembarkedUnitStatePayload | None


class TransportHazardMortalWoundsPayload(TypedDict):
    source_rule_id: str
    source_kind: str
    disembark_mode: str
    disembark: CombatDisembarkPayload | DestroyedTransportDisembarkPayload
    mortal_wounds: int
    mortal_wound_application: MortalWoundApplicationPayload | None
    pending_mortal_wound_request: DecisionRequestPayload | None
    pending_mortal_wound_request_id: str | None


class FiringDeckWeaponSelectionPayload(TypedDict):
    embarked_unit_instance_id: str
    model_instance_id: str
    wargear_id: str
    weapon_profile: WeaponProfilePayload


class FiringDeckSelectionPayload(TypedDict):
    player_id: str
    battle_round: int
    transport_unit_instance_id: str
    firing_deck_value: int
    weapon_selections: list[FiringDeckWeaponSelectionPayload]
    already_shot_unit_instance_ids: list[str]


class FiringDeckResolutionPayload(TypedDict):
    selection: FiringDeckSelectionPayload
    is_valid: bool
    violations: list[TransportOperationViolationPayload]
    temporary_weapon_profiles: list[WeaponProfilePayload]
    ineligible_unit_instance_ids: list[str]


_TRANSPORT_KEYWORD = "TRANSPORT"
_EPSILON = 1e-9
_DEFAULT_BATTLEFIELD_WIDTH_INCHES = 60.0
_DEFAULT_BATTLEFIELD_DEPTH_INCHES = 44.0
_EMBARK_DISTANCE_INCHES = 3.0
_DISEMBARK_DISTANCE_INCHES = 3.0
_EMERGENCY_DISEMBARK_DISTANCE_INCHES = 6.0
_CORE_TRANSPORT_RULE_ID = "core_rules_transports"
_RAPID_DISEMBARK_RULE_ID = "core_rules_rapid_disembark"
_TACTICAL_DISEMBARK_RULE_ID = "core_rules_tactical_disembark"
_COMBAT_DISEMBARK_RULE_ID = "core_rules_combat_disembark"
_DESTROYED_TRANSPORT_RULE_ID = "core_rules_destroyed_transport"
_EMERGENCY_DISEMBARK_RULE_ID = "core_rules_emergency_disembark"
TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND = "transport_hazard_mortal_wounds"
TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE = "transport_hazard_mortal_wounds_resolved"


@dataclass(frozen=True, slots=True)
class TransportCapacityProfile:
    transport_datasheet_id: str
    max_model_count: int
    allowed_keywords: tuple[str, ...] = ()
    excluded_keywords: tuple[str, ...] = ()
    source_id: str = _CORE_TRANSPORT_RULE_ID

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "transport_datasheet_id",
            _validate_identifier(
                "TransportCapacityProfile transport_datasheet_id",
                self.transport_datasheet_id,
            ),
        )
        object.__setattr__(
            self,
            "max_model_count",
            _validate_positive_int(
                "TransportCapacityProfile max_model_count", self.max_model_count
            ),
        )
        object.__setattr__(
            self,
            "allowed_keywords",
            _validate_identifier_tuple(
                "TransportCapacityProfile allowed_keywords",
                self.allowed_keywords,
            ),
        )
        object.__setattr__(
            self,
            "excluded_keywords",
            _validate_identifier_tuple(
                "TransportCapacityProfile excluded_keywords",
                self.excluded_keywords,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TransportCapacityProfile source_id", self.source_id),
        )

    def allows_unit(self, unit: UnitInstance) -> bool:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("Transport capacity requires a UnitInstance.")
        unit_keywords = {_canonical_keyword(keyword) for keyword in unit.keywords}
        allowed = {_canonical_keyword(keyword) for keyword in self.allowed_keywords}
        excluded = {_canonical_keyword(keyword) for keyword in self.excluded_keywords}
        if allowed and not unit_keywords.intersection(allowed):
            return False
        return not unit_keywords.intersection(excluded)

    def to_payload(self) -> TransportCapacityProfilePayload:
        return {
            "transport_datasheet_id": self.transport_datasheet_id,
            "max_model_count": self.max_model_count,
            "allowed_keywords": list(self.allowed_keywords),
            "excluded_keywords": list(self.excluded_keywords),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: TransportCapacityProfilePayload) -> Self:
        return cls(
            transport_datasheet_id=payload["transport_datasheet_id"],
            max_model_count=payload["max_model_count"],
            allowed_keywords=tuple(payload["allowed_keywords"]),
            excluded_keywords=tuple(payload["excluded_keywords"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class TransportRestrictionOverride:
    override_kind: TransportRestrictionOverrideKind
    source_rule_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "override_kind",
            transport_restriction_override_kind_from_token(self.override_kind),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "TransportRestrictionOverride source_rule_id", self.source_rule_id
            ),
        )

    def to_payload(self) -> TransportRestrictionOverridePayload:
        return {
            "override_kind": self.override_kind.value,
            "source_rule_id": self.source_rule_id,
        }

    @classmethod
    def from_payload(cls, payload: TransportRestrictionOverridePayload) -> Self:
        return cls(
            override_kind=transport_restriction_override_kind_from_token(payload["override_kind"]),
            source_rule_id=payload["source_rule_id"],
        )


@dataclass(frozen=True, slots=True)
class TransportCargoState:
    player_id: str
    transport_unit_instance_id: str
    capacity_profile: TransportCapacityProfile
    embarked_unit_instance_ids: tuple[str, ...] = ()
    phase_battle_round: int | None = None
    started_phase_embarked_unit_instance_ids: tuple[str, ...] = ()
    disembarked_this_phase_unit_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("TransportCargoState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "TransportCargoState transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        if type(self.capacity_profile) is not TransportCapacityProfile:
            raise GameLifecycleError(
                "TransportCargoState capacity_profile must be a TransportCapacityProfile."
            )
        object.__setattr__(
            self,
            "embarked_unit_instance_ids",
            _validate_identifier_tuple(
                "TransportCargoState embarked_unit_instance_ids",
                self.embarked_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "phase_battle_round",
            _validate_optional_positive_int(
                "TransportCargoState phase_battle_round",
                self.phase_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "started_phase_embarked_unit_instance_ids",
            _validate_identifier_tuple(
                "TransportCargoState started_phase_embarked_unit_instance_ids",
                self.started_phase_embarked_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "disembarked_this_phase_unit_instance_ids",
            _validate_identifier_tuple(
                "TransportCargoState disembarked_this_phase_unit_instance_ids",
                self.disembarked_this_phase_unit_instance_ids,
            ),
        )
        if self.transport_unit_instance_id in self.embarked_unit_instance_ids:
            raise GameLifecycleError("TransportCargoState cannot embark itself.")

    def for_movement_phase(self, *, battle_round: int) -> Self:
        requested_round = _validate_positive_int("battle_round", battle_round)
        if self.phase_battle_round == requested_round:
            return self
        return replace(
            self,
            phase_battle_round=requested_round,
            started_phase_embarked_unit_instance_ids=self.embarked_unit_instance_ids,
            disembarked_this_phase_unit_instance_ids=(),
        )

    def contains_unit(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return requested_unit_id in self.embarked_unit_instance_ids

    def unit_started_phase_embarked(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return requested_unit_id in self.started_phase_embarked_unit_instance_ids

    def unit_disembarked_this_phase(self, unit_instance_id: str) -> bool:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        return requested_unit_id in self.disembarked_this_phase_unit_instance_ids

    def with_embarked_unit(self, unit_instance_id: str) -> Self:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if requested_unit_id in self.embarked_unit_instance_ids:
            raise GameLifecycleError("TransportCargoState unit is already embarked.")
        return replace(
            self,
            embarked_unit_instance_ids=tuple(
                sorted((*self.embarked_unit_instance_ids, requested_unit_id))
            ),
        )

    def with_disembarked_unit(self, unit_instance_id: str) -> Self:
        requested_unit_id = _validate_identifier("unit_instance_id", unit_instance_id)
        if requested_unit_id not in self.embarked_unit_instance_ids:
            raise GameLifecycleError("TransportCargoState unit is not embarked.")
        embarked = tuple(
            unit_id for unit_id in self.embarked_unit_instance_ids if unit_id != requested_unit_id
        )
        disembarked = self.disembarked_this_phase_unit_instance_ids
        if requested_unit_id not in disembarked:
            disembarked = tuple(sorted((*disembarked, requested_unit_id)))
        return replace(
            self,
            embarked_unit_instance_ids=embarked,
            disembarked_this_phase_unit_instance_ids=disembarked,
        )

    def to_payload(self) -> TransportCargoStatePayload:
        return {
            "player_id": self.player_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "capacity_profile": self.capacity_profile.to_payload(),
            "embarked_unit_instance_ids": list(self.embarked_unit_instance_ids),
            "phase_battle_round": self.phase_battle_round,
            "started_phase_embarked_unit_instance_ids": list(
                self.started_phase_embarked_unit_instance_ids
            ),
            "disembarked_this_phase_unit_instance_ids": list(
                self.disembarked_this_phase_unit_instance_ids
            ),
        }

    @classmethod
    def from_payload(cls, payload: TransportCargoStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            capacity_profile=TransportCapacityProfile.from_payload(payload["capacity_profile"]),
            embarked_unit_instance_ids=tuple(payload["embarked_unit_instance_ids"]),
            phase_battle_round=payload["phase_battle_round"],
            started_phase_embarked_unit_instance_ids=tuple(
                payload["started_phase_embarked_unit_instance_ids"]
            ),
            disembarked_this_phase_unit_instance_ids=tuple(
                payload["disembarked_this_phase_unit_instance_ids"]
            ),
        )


@dataclass(frozen=True, slots=True)
class TransportOperationViolation:
    violation_code: TransportOperationViolationCode
    message: str
    unit_instance_id: str | None = None
    model_instance_id: str | None = None
    blocker_id: str | None = None
    source_rule_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            transport_operation_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("TransportOperationViolation message", self.message),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_optional_identifier(
                "TransportOperationViolation unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "TransportOperationViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier(
                "TransportOperationViolation blocker_id", self.blocker_id
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_optional_identifier(
                "TransportOperationViolation source_rule_id",
                self.source_rule_id,
            ),
        )

    def to_payload(self) -> TransportOperationViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "blocker_id": self.blocker_id,
            "source_rule_id": self.source_rule_id,
        }

    @classmethod
    def from_payload(cls, payload: TransportOperationViolationPayload) -> Self:
        return cls(
            violation_code=transport_operation_violation_code_from_token(payload["violation_code"]),
            message=payload["message"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            blocker_id=payload["blocker_id"],
            source_rule_id=payload["source_rule_id"],
        )


@dataclass(frozen=True, slots=True)
class EmbarkSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    movement_phase_action: TransportMovementStatus
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("EmbarkSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("EmbarkSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("EmbarkSelection unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "EmbarkSelection transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "movement_phase_action",
            transport_movement_status_from_token(self.movement_phase_action),
        )
        if self.movement_phase_action not in {
            TransportMovementStatus.NORMAL_MOVE,
            TransportMovementStatus.ADVANCE,
            TransportMovementStatus.FALL_BACK,
        }:
            raise GameLifecycleError(
                "EmbarkSelection requires a Normal, Advance, or Fall Back action."
            )
        object.__setattr__(
            self,
            "restriction_overrides",
            _validate_transport_override_tuple(
                "EmbarkSelection restriction_overrides",
                self.restriction_overrides,
            ),
        )

    def has_override(self, override_kind: TransportRestrictionOverrideKind) -> bool:
        kind = transport_restriction_override_kind_from_token(override_kind)
        return any(override.override_kind is kind for override in self.restriction_overrides)

    def to_payload(self) -> EmbarkSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "movement_phase_action": self.movement_phase_action.value,
            "restriction_overrides": [
                override.to_payload() for override in self.restriction_overrides
            ],
        }

    @classmethod
    def from_payload(cls, payload: EmbarkSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            movement_phase_action=transport_movement_status_from_token(
                payload["movement_phase_action"]
            ),
            restriction_overrides=tuple(
                TransportRestrictionOverride.from_payload(override)
                for override in payload["restriction_overrides"]
            ),
        )


@dataclass(frozen=True, slots=True)
class EmbarkResolution:
    selection: EmbarkSelection
    violations: tuple[TransportOperationViolation, ...]
    updated_cargo_state: TransportCargoState | None
    transition_batch: BattlefieldTransitionBatch | None

    def __post_init__(self) -> None:
        if type(self.selection) is not EmbarkSelection:
            raise GameLifecycleError("EmbarkResolution selection must be an EmbarkSelection.")
        object.__setattr__(
            self,
            "violations",
            _validate_transport_violation_tuple(
                "EmbarkResolution violations",
                self.violations,
            ),
        )
        if self.updated_cargo_state is not None and type(self.updated_cargo_state) is not (
            TransportCargoState
        ):
            raise GameLifecycleError(
                "EmbarkResolution updated_cargo_state must be a TransportCargoState."
            )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "EmbarkResolution transition_batch must be a BattlefieldTransitionBatch."
            )
        if self.violations and (
            self.updated_cargo_state is not None or self.transition_batch is not None
        ):
            raise GameLifecycleError("Invalid EmbarkResolution cannot include mutation records.")
        if not self.violations and (
            self.updated_cargo_state is None or self.transition_batch is None
        ):
            raise GameLifecycleError("Valid EmbarkResolution requires mutation records.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> EmbarkResolutionPayload:
        return {
            "selection": self.selection.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "updated_cargo_state": (
                None if self.updated_cargo_state is None else self.updated_cargo_state.to_payload()
            ),
            "transition_batch": None
            if self.transition_batch is None
            else self.transition_batch.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: EmbarkResolutionPayload) -> Self:
        transition_payload = payload["transition_batch"]
        resolution = cls(
            selection=EmbarkSelection.from_payload(payload["selection"]),
            violations=tuple(
                TransportOperationViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            updated_cargo_state=(
                None
                if payload["updated_cargo_state"] is None
                else TransportCargoState.from_payload(payload["updated_cargo_state"])
            ),
            transition_batch=(
                None
                if transition_payload is None
                else BattlefieldTransitionBatch.from_payload(transition_payload)
            ),
        )
        if resolution.is_valid != payload["is_valid"]:
            raise GameLifecycleError("EmbarkResolution payload validity drift.")
        return resolution


@dataclass(frozen=True, slots=True)
class DisembarkSelection:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    attempted_placement: UnitPlacement
    disembark_mode: DisembarkModeKind
    transport_movement_status: TransportMovementStatus
    restriction_overrides: tuple[TransportRestrictionOverride, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DisembarkSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DisembarkSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("DisembarkSelection unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DisembarkSelection transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "DisembarkSelection attempted_placement must be UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.unit_instance_id:
            raise GameLifecycleError("DisembarkSelection attempted_placement unit drift.")
        if self.attempted_placement.player_id != self.player_id:
            raise GameLifecycleError("DisembarkSelection attempted_placement player drift.")
        object.__setattr__(
            self,
            "disembark_mode",
            disembark_mode_kind_from_token(self.disembark_mode),
        )
        object.__setattr__(
            self,
            "transport_movement_status",
            transport_movement_status_from_token(self.transport_movement_status),
        )
        _validate_disembark_mode_status(
            disembark_mode=self.disembark_mode,
            transport_movement_status=self.transport_movement_status,
        )
        object.__setattr__(
            self,
            "restriction_overrides",
            _validate_transport_override_tuple(
                "DisembarkSelection restriction_overrides",
                self.restriction_overrides,
            ),
        )

    def has_override(self, override_kind: TransportRestrictionOverrideKind) -> bool:
        kind = transport_restriction_override_kind_from_token(override_kind)
        return any(override.override_kind is kind for override in self.restriction_overrides)

    def to_payload(self) -> DisembarkSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "attempted_placement": self.attempted_placement.to_payload(),
            "disembark_mode": self.disembark_mode.value,
            "transport_movement_status": self.transport_movement_status.value,
            "restriction_overrides": [
                override.to_payload() for override in self.restriction_overrides
            ],
        }

    @classmethod
    def from_payload(cls, payload: DisembarkSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            attempted_placement=UnitPlacement.from_payload(payload["attempted_placement"]),
            disembark_mode=disembark_mode_kind_from_token(payload["disembark_mode"]),
            transport_movement_status=transport_movement_status_from_token(
                payload["transport_movement_status"]
            ),
            restriction_overrides=tuple(
                TransportRestrictionOverride.from_payload(override)
                for override in payload["restriction_overrides"]
            ),
        )


@dataclass(frozen=True, slots=True)
class DisembarkedUnitState:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: DisembarkModeKind
    can_move_further: bool
    can_choose_remain_stationary: bool
    can_declare_charge: bool
    battle_shocked_until: str | None
    source_rule_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DisembarkedUnitState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DisembarkedUnitState battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("DisembarkedUnitState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DisembarkedUnitState transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "disembark_mode",
            disembark_mode_kind_from_token(self.disembark_mode),
        )
        object.__setattr__(
            self,
            "can_move_further",
            _validate_bool("DisembarkedUnitState can_move_further", self.can_move_further),
        )
        object.__setattr__(
            self,
            "can_choose_remain_stationary",
            _validate_bool(
                "DisembarkedUnitState can_choose_remain_stationary",
                self.can_choose_remain_stationary,
            ),
        )
        object.__setattr__(
            self,
            "can_declare_charge",
            _validate_bool("DisembarkedUnitState can_declare_charge", self.can_declare_charge),
        )
        object.__setattr__(
            self,
            "battle_shocked_until",
            _validate_optional_identifier(
                "DisembarkedUnitState battle_shocked_until",
                self.battle_shocked_until,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DisembarkedUnitState source_rule_id", self.source_rule_id),
        )

    @classmethod
    def for_mode(
        cls,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
        transport_unit_instance_id: str,
        disembark_mode: DisembarkModeKind,
        transport_movement_status: TransportMovementStatus,
    ) -> Self:
        mode = disembark_mode_kind_from_token(disembark_mode)
        status = transport_movement_status_from_token(transport_movement_status)
        _validate_disembark_mode_status(
            disembark_mode=mode,
            transport_movement_status=status,
        )
        if mode is DisembarkModeKind.RAPID_DISEMBARK:
            return cls(
                player_id=player_id,
                battle_round=battle_round,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=transport_unit_instance_id,
                disembark_mode=mode,
                can_move_further=False,
                can_choose_remain_stationary=False,
                can_declare_charge=False,
                battle_shocked_until=None,
                source_rule_id=_RAPID_DISEMBARK_RULE_ID,
            )
        if mode is DisembarkModeKind.COMBAT_DISEMBARK:
            return cls(
                player_id=player_id,
                battle_round=battle_round,
                unit_instance_id=unit_instance_id,
                transport_unit_instance_id=transport_unit_instance_id,
                disembark_mode=mode,
                can_move_further=False,
                can_choose_remain_stationary=False,
                can_declare_charge=False,
                battle_shocked_until="end_of_turn",
                source_rule_id=_COMBAT_DISEMBARK_RULE_ID,
            )
        if mode is not DisembarkModeKind.TACTICAL_DISEMBARK:
            raise GameLifecycleError("Normal Disembark requires Tactical, Rapid, or Combat mode.")
        return cls(
            player_id=player_id,
            battle_round=battle_round,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=transport_unit_instance_id,
            disembark_mode=mode,
            can_move_further=True,
            can_choose_remain_stationary=False,
            can_declare_charge=True,
            battle_shocked_until=None,
            source_rule_id=_TACTICAL_DISEMBARK_RULE_ID,
        )

    @classmethod
    def for_destroyed_transport(
        cls,
        *,
        player_id: str,
        battle_round: int,
        unit_instance_id: str,
        transport_unit_instance_id: str,
        disembark_mode: DisembarkModeKind,
    ) -> Self:
        mode = disembark_mode_kind_from_token(disembark_mode)
        if mode not in {
            DisembarkModeKind.DESTROYED_TRANSPORT,
            DisembarkModeKind.EMERGENCY_DISEMBARK,
        }:
            raise GameLifecycleError(
                "Destroyed Transport Disembark requires destroyed or emergency mode."
            )
        return cls(
            player_id=player_id,
            battle_round=battle_round,
            unit_instance_id=unit_instance_id,
            transport_unit_instance_id=transport_unit_instance_id,
            disembark_mode=mode,
            can_move_further=False,
            can_choose_remain_stationary=False,
            can_declare_charge=False,
            battle_shocked_until="end_of_turn",
            source_rule_id=(
                _EMERGENCY_DISEMBARK_RULE_ID
                if mode is DisembarkModeKind.EMERGENCY_DISEMBARK
                else _DESTROYED_TRANSPORT_RULE_ID
            ),
        )

    def to_payload(self) -> DisembarkedUnitStatePayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "disembark_mode": self.disembark_mode.value,
            "can_move_further": self.can_move_further,
            "can_choose_remain_stationary": self.can_choose_remain_stationary,
            "can_declare_charge": self.can_declare_charge,
            "battle_shocked_until": self.battle_shocked_until,
            "source_rule_id": self.source_rule_id,
        }

    @classmethod
    def from_payload(cls, payload: DisembarkedUnitStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            disembark_mode=disembark_mode_kind_from_token(payload["disembark_mode"]),
            can_move_further=payload["can_move_further"],
            can_choose_remain_stationary=payload["can_choose_remain_stationary"],
            can_declare_charge=payload["can_declare_charge"],
            battle_shocked_until=payload["battle_shocked_until"],
            source_rule_id=payload["source_rule_id"],
        )


@dataclass(frozen=True, slots=True)
class DisembarkResolution:
    selection: DisembarkSelection
    violations: tuple[TransportOperationViolation, ...]
    coherency_result: UnitCoherencyResult
    updated_cargo_state: TransportCargoState | None
    disembarked_unit_state: DisembarkedUnitState | None
    transition_batch: BattlefieldTransitionBatch | None

    def __post_init__(self) -> None:
        if type(self.selection) is not DisembarkSelection:
            raise GameLifecycleError("DisembarkResolution selection must be a DisembarkSelection.")
        object.__setattr__(
            self,
            "violations",
            _validate_transport_violation_tuple(
                "DisembarkResolution violations",
                self.violations,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "DisembarkResolution coherency_result must be a UnitCoherencyResult."
            )
        if self.updated_cargo_state is not None and type(self.updated_cargo_state) is not (
            TransportCargoState
        ):
            raise GameLifecycleError(
                "DisembarkResolution updated_cargo_state must be TransportCargoState."
            )
        if self.disembarked_unit_state is not None and type(self.disembarked_unit_state) is not (
            DisembarkedUnitState
        ):
            raise GameLifecycleError(
                "DisembarkResolution disembarked_unit_state must be DisembarkedUnitState."
            )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "DisembarkResolution transition_batch must be BattlefieldTransitionBatch."
            )
        if self.violations and (
            self.updated_cargo_state is not None
            or self.disembarked_unit_state is not None
            or self.transition_batch is not None
        ):
            raise GameLifecycleError("Invalid DisembarkResolution cannot include mutation records.")
        if not self.violations and (
            self.updated_cargo_state is None
            or self.disembarked_unit_state is None
            or self.transition_batch is None
        ):
            raise GameLifecycleError("Valid DisembarkResolution requires mutation records.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> DisembarkResolutionPayload:
        return {
            "selection": self.selection.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "coherency_result": self.coherency_result.to_payload(),
            "updated_cargo_state": (
                None if self.updated_cargo_state is None else self.updated_cargo_state.to_payload()
            ),
            "disembarked_unit_state": None
            if self.disembarked_unit_state is None
            else self.disembarked_unit_state.to_payload(),
            "transition_batch": None
            if self.transition_batch is None
            else self.transition_batch.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DisembarkResolutionPayload) -> Self:
        transition_payload = payload["transition_batch"]
        resolution = cls(
            selection=DisembarkSelection.from_payload(payload["selection"]),
            violations=tuple(
                TransportOperationViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            coherency_result=UnitCoherencyResult.from_payload(payload["coherency_result"]),
            updated_cargo_state=(
                None
                if payload["updated_cargo_state"] is None
                else TransportCargoState.from_payload(payload["updated_cargo_state"])
            ),
            disembarked_unit_state=(
                None
                if payload["disembarked_unit_state"] is None
                else DisembarkedUnitState.from_payload(payload["disembarked_unit_state"])
            ),
            transition_batch=(
                None
                if transition_payload is None
                else BattlefieldTransitionBatch.from_payload(transition_payload)
            ),
        )
        if resolution.is_valid != payload["is_valid"]:
            raise GameLifecycleError("DisembarkResolution payload validity drift.")
        return resolution


@dataclass(frozen=True, slots=True)
class DestroyedTransportModelRoll:
    model_instance_id: str
    roll_state: DiceRollState
    mortal_wound_inflicted: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "DestroyedTransportModelRoll model_instance_id", self.model_instance_id
            ),
        )
        if type(self.roll_state) is not DiceRollState:
            raise GameLifecycleError(
                "DestroyedTransportModelRoll roll_state must be DiceRollState."
            )
        object.__setattr__(
            self,
            "mortal_wound_inflicted",
            _validate_bool(
                "DestroyedTransportModelRoll mortal_wound_inflicted",
                self.mortal_wound_inflicted,
            ),
        )

    def to_payload(self) -> DestroyedTransportModelRollPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "roll_state": self.roll_state.to_payload(),
            "mortal_wound_inflicted": self.mortal_wound_inflicted,
        }

    @classmethod
    def from_payload(cls, payload: DestroyedTransportModelRollPayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            roll_state=DiceRollState.from_payload(payload["roll_state"]),
            mortal_wound_inflicted=payload["mortal_wound_inflicted"],
        )


@dataclass(frozen=True, slots=True)
class DestroyedTransportDisembark:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    disembark_mode: DisembarkModeKind
    placement: DisembarkResolution
    roll_threshold: int
    model_rolls: tuple[DestroyedTransportModelRoll, ...]
    mortal_wounds_per_failed_roll: int = 1
    destroyed_model_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DestroyedTransportDisembark player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("DestroyedTransportDisembark battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DestroyedTransportDisembark unit_instance_id", self.unit_instance_id
            ),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "DestroyedTransportDisembark transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "disembark_mode",
            disembark_mode_kind_from_token(self.disembark_mode),
        )
        if self.disembark_mode not in {
            DisembarkModeKind.DESTROYED_TRANSPORT,
            DisembarkModeKind.EMERGENCY_DISEMBARK,
        }:
            raise GameLifecycleError(
                "DestroyedTransportDisembark requires destroyed or emergency mode."
            )
        if type(self.placement) is not DisembarkResolution:
            raise GameLifecycleError(
                "DestroyedTransportDisembark placement must be a DisembarkResolution."
            )
        object.__setattr__(
            self,
            "roll_threshold",
            _validate_positive_int(
                "DestroyedTransportDisembark roll_threshold", self.roll_threshold
            ),
        )
        object.__setattr__(
            self,
            "model_rolls",
            _validate_destroyed_transport_roll_tuple(
                "DestroyedTransportDisembark model_rolls",
                self.model_rolls,
            ),
        )
        wounds_per_failed_roll = _validate_positive_int(
            "DestroyedTransportDisembark mortal_wounds_per_failed_roll",
            self.mortal_wounds_per_failed_roll,
        )
        if wounds_per_failed_roll not in {1, 3}:
            raise GameLifecycleError(
                "DestroyedTransportDisembark mortal_wounds_per_failed_roll drift."
            )
        object.__setattr__(
            self,
            "mortal_wounds_per_failed_roll",
            wounds_per_failed_roll,
        )
        object.__setattr__(
            self,
            "destroyed_model_instance_ids",
            _validate_identifier_tuple(
                "DestroyedTransportDisembark destroyed_model_instance_ids",
                self.destroyed_model_instance_ids,
            ),
        )
        if self.roll_threshold != HAZARD_ROLL_FAILURE_THRESHOLD:
            raise GameLifecycleError("DestroyedTransportDisembark roll threshold drift.")
        for roll in self.model_rolls:
            expected_mortal_wound = hazard_roll_failed(roll.roll_state)
            if roll.mortal_wound_inflicted != expected_mortal_wound:
                raise GameLifecycleError("DestroyedTransportDisembark mortal wound roll drift.")
        if self.placement.is_valid:
            placed_model_ids = {
                placement.model_instance_id
                for placement in self.placement.selection.attempted_placement.model_placements
            }
            expected_roll_model_ids = set(placed_model_ids)
            if self.disembark_mode is DisembarkModeKind.EMERGENCY_DISEMBARK:
                expected_roll_model_ids.update(self.destroyed_model_instance_ids)
            rolled_model_ids = {roll.model_instance_id for roll in self.model_rolls}
            if rolled_model_ids != expected_roll_model_ids:
                raise GameLifecycleError("DestroyedTransportDisembark roll model drift.")

    @property
    def mortal_wound_count(self) -> int:
        return sum(
            self.mortal_wounds_per_failed_roll
            for roll in self.model_rolls
            if roll.mortal_wound_inflicted
        )

    @property
    def disembarked_unit_state(self) -> DisembarkedUnitState | None:
        return self.placement.disembarked_unit_state

    def to_payload(self) -> DestroyedTransportDisembarkPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "disembark_mode": self.disembark_mode.value,
            "placement": self.placement.to_payload(),
            "roll_threshold": self.roll_threshold,
            "mortal_wounds_per_failed_roll": self.mortal_wounds_per_failed_roll,
            "model_rolls": [roll.to_payload() for roll in self.model_rolls],
            "mortal_wound_count": self.mortal_wound_count,
            "destroyed_model_instance_ids": list(self.destroyed_model_instance_ids),
            "disembarked_unit_state": None
            if self.disembarked_unit_state is None
            else self.disembarked_unit_state.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: DestroyedTransportDisembarkPayload) -> Self:
        result = cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            disembark_mode=disembark_mode_kind_from_token(payload["disembark_mode"]),
            placement=DisembarkResolution.from_payload(payload["placement"]),
            roll_threshold=payload["roll_threshold"],
            mortal_wounds_per_failed_roll=payload["mortal_wounds_per_failed_roll"],
            model_rolls=tuple(
                DestroyedTransportModelRoll.from_payload(roll) for roll in payload["model_rolls"]
            ),
            destroyed_model_instance_ids=tuple(payload["destroyed_model_instance_ids"]),
        )
        if result.mortal_wound_count != payload["mortal_wound_count"]:
            raise GameLifecycleError("DestroyedTransportDisembark mortal wound count drift.")
        expected_disembarked_state = (
            None if result.disembarked_unit_state is None else result.disembarked_unit_state
        )
        payload_disembarked_state = (
            None
            if payload["disembarked_unit_state"] is None
            else DisembarkedUnitState.from_payload(payload["disembarked_unit_state"])
        )
        if expected_disembarked_state != payload_disembarked_state:
            raise GameLifecycleError("DestroyedTransportDisembark disembarked state drift.")
        return result


@dataclass(frozen=True, slots=True)
class CombatDisembark:
    player_id: str
    battle_round: int
    unit_instance_id: str
    transport_unit_instance_id: str
    placement: DisembarkResolution
    roll_threshold: int
    model_rolls: tuple[DestroyedTransportModelRoll, ...]
    mortal_wounds_per_failed_roll: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("CombatDisembark player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("CombatDisembark battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("CombatDisembark unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "CombatDisembark transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        if type(self.placement) is not DisembarkResolution:
            raise GameLifecycleError("CombatDisembark placement must be a DisembarkResolution.")
        if self.placement.selection.disembark_mode is not DisembarkModeKind.COMBAT_DISEMBARK:
            raise GameLifecycleError("CombatDisembark requires Combat Disembark placement.")
        object.__setattr__(
            self,
            "roll_threshold",
            _validate_positive_int("CombatDisembark roll_threshold", self.roll_threshold),
        )
        if self.roll_threshold != HAZARD_ROLL_FAILURE_THRESHOLD:
            raise GameLifecycleError("CombatDisembark roll threshold drift.")
        object.__setattr__(
            self,
            "model_rolls",
            _validate_destroyed_transport_roll_tuple(
                "CombatDisembark model_rolls",
                self.model_rolls,
            ),
        )
        wounds_per_failed_roll = _validate_positive_int(
            "CombatDisembark mortal_wounds_per_failed_roll",
            self.mortal_wounds_per_failed_roll,
        )
        if wounds_per_failed_roll not in {1, 3}:
            raise GameLifecycleError("CombatDisembark mortal_wounds_per_failed_roll drift.")
        object.__setattr__(
            self,
            "mortal_wounds_per_failed_roll",
            wounds_per_failed_roll,
        )
        for roll in self.model_rolls:
            expected_mortal_wound = hazard_roll_failed(roll.roll_state)
            if roll.mortal_wound_inflicted != expected_mortal_wound:
                raise GameLifecycleError("CombatDisembark hazard roll drift.")
        if self.placement.is_valid:
            placed_model_ids = {
                placement.model_instance_id
                for placement in self.placement.selection.attempted_placement.model_placements
            }
            rolled_model_ids = {roll.model_instance_id for roll in self.model_rolls}
            if rolled_model_ids != placed_model_ids:
                raise GameLifecycleError("CombatDisembark hazard roll model drift.")

    @property
    def mortal_wound_count(self) -> int:
        return sum(
            self.mortal_wounds_per_failed_roll
            for roll in self.model_rolls
            if roll.mortal_wound_inflicted
        )

    @property
    def disembarked_unit_state(self) -> DisembarkedUnitState | None:
        return self.placement.disembarked_unit_state

    def to_payload(self) -> CombatDisembarkPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "unit_instance_id": self.unit_instance_id,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "placement": self.placement.to_payload(),
            "roll_threshold": self.roll_threshold,
            "mortal_wounds_per_failed_roll": self.mortal_wounds_per_failed_roll,
            "model_rolls": [roll.to_payload() for roll in self.model_rolls],
            "mortal_wound_count": self.mortal_wound_count,
            "disembarked_unit_state": None
            if self.disembarked_unit_state is None
            else self.disembarked_unit_state.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: CombatDisembarkPayload) -> Self:
        result = cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            unit_instance_id=payload["unit_instance_id"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            placement=DisembarkResolution.from_payload(payload["placement"]),
            roll_threshold=payload["roll_threshold"],
            mortal_wounds_per_failed_roll=payload["mortal_wounds_per_failed_roll"],
            model_rolls=tuple(
                DestroyedTransportModelRoll.from_payload(roll) for roll in payload["model_rolls"]
            ),
        )
        if result.mortal_wound_count != payload["mortal_wound_count"]:
            raise GameLifecycleError("CombatDisembark mortal wound count drift.")
        expected_disembarked_state = (
            None if result.disembarked_unit_state is None else result.disembarked_unit_state
        )
        payload_disembarked_state = (
            None
            if payload["disembarked_unit_state"] is None
            else DisembarkedUnitState.from_payload(payload["disembarked_unit_state"])
        )
        if expected_disembarked_state != payload_disembarked_state:
            raise GameLifecycleError("CombatDisembark disembarked state drift.")
        return result


@dataclass(frozen=True, slots=True)
class TransportHazardMortalWounds:
    source_rule_id: str
    source_kind: str
    disembark: CombatDisembark | DestroyedTransportDisembark
    mortal_wound_application: MortalWoundApplication | None = None
    pending_mortal_wound_request: DecisionRequest | None = None

    def __post_init__(self) -> None:
        from warhammer40k_core.engine.damage_allocation import (
            MortalWoundApplication,
            is_mortal_wound_feel_no_pain_request,
            mortal_wound_feel_no_pain_source_context,
        )

        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("TransportHazardMortalWounds source_rule_id", self.source_rule_id),
        )
        if self.source_rule_id != CORE_HAZARD_ROLLS_RULE_ID:
            raise GameLifecycleError("TransportHazardMortalWounds source_rule_id drift.")
        object.__setattr__(
            self,
            "source_kind",
            _validate_identifier("TransportHazardMortalWounds source_kind", self.source_kind),
        )
        if self.source_kind != TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND:
            raise GameLifecycleError("TransportHazardMortalWounds source_kind drift.")
        if type(self.disembark) not in {CombatDisembark, DestroyedTransportDisembark}:
            raise GameLifecycleError(
                "TransportHazardMortalWounds requires a transport hazard disembark."
            )
        if not self.disembark.placement.is_valid:
            raise GameLifecycleError(
                "TransportHazardMortalWounds requires a valid disembark placement."
            )
        application = self.mortal_wound_application
        request = self.pending_mortal_wound_request
        if application is not None and type(application) is not MortalWoundApplication:
            raise GameLifecycleError(
                "TransportHazardMortalWounds mortal_wound_application must be "
                "MortalWoundApplication."
            )
        if request is not None and type(request) is not DecisionRequest:
            raise GameLifecycleError(
                "TransportHazardMortalWounds pending_mortal_wound_request must be DecisionRequest."
            )
        if self.mortal_wounds == 0 and (application is not None or request is not None):
            raise GameLifecycleError("TransportHazardMortalWounds cannot route zero mortal wounds.")
        if self.mortal_wounds > 0 and (application is None) == (request is None):
            raise GameLifecycleError(
                "TransportHazardMortalWounds requires exactly one completed application or "
                "pending request."
            )
        if application is not None:
            if application.target_unit_instance_id != self.disembark.unit_instance_id:
                raise GameLifecycleError("TransportHazardMortalWounds application target drift.")
            if application.mortal_wounds != self.mortal_wounds:
                raise GameLifecycleError(
                    "TransportHazardMortalWounds application mortal wound drift."
                )
        if request is not None:
            if not is_mortal_wound_feel_no_pain_request(request):
                raise GameLifecycleError(
                    "TransportHazardMortalWounds request must use mortal wound Feel No Pain."
                )
            source_context = mortal_wound_feel_no_pain_source_context(request)
            if not isinstance(source_context, dict):
                raise GameLifecycleError(
                    "TransportHazardMortalWounds request source context is invalid."
                )
            if source_context.get("source_kind") != TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND:
                raise GameLifecycleError("TransportHazardMortalWounds request source kind drift.")
            if source_context.get("unit_instance_id") != self.disembark.unit_instance_id:
                raise GameLifecycleError("TransportHazardMortalWounds request unit drift.")
            if source_context.get("transport_unit_instance_id") != (
                self.disembark.transport_unit_instance_id
            ):
                raise GameLifecycleError("TransportHazardMortalWounds request transport drift.")
            if source_context.get("disembark_mode") != self.disembark_mode.value:
                raise GameLifecycleError("TransportHazardMortalWounds request mode drift.")
            if source_context.get("mortal_wounds") != self.mortal_wounds:
                raise GameLifecycleError("TransportHazardMortalWounds request mortal wound drift.")

    @property
    def disembark_mode(self) -> DisembarkModeKind:
        if type(self.disembark) is CombatDisembark:
            return DisembarkModeKind.COMBAT_DISEMBARK
        if type(self.disembark) is DestroyedTransportDisembark:
            return self.disembark.disembark_mode
        raise GameLifecycleError("Unsupported transport hazard disembark.")

    @property
    def mortal_wounds(self) -> int:
        return self.disembark.mortal_wound_count

    def to_payload(self) -> TransportHazardMortalWoundsPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "source_kind": self.source_kind,
            "disembark_mode": self.disembark_mode.value,
            "disembark": self.disembark.to_payload(),
            "mortal_wounds": self.mortal_wounds,
            "mortal_wound_application": None
            if self.mortal_wound_application is None
            else self.mortal_wound_application.to_payload(),
            "pending_mortal_wound_request": None
            if self.pending_mortal_wound_request is None
            else self.pending_mortal_wound_request.to_payload(),
            "pending_mortal_wound_request_id": None
            if self.pending_mortal_wound_request is None
            else self.pending_mortal_wound_request.request_id,
        }

    @classmethod
    def from_payload(cls, payload: TransportHazardMortalWoundsPayload) -> Self:
        from warhammer40k_core.engine.damage_allocation import MortalWoundApplication

        disembark_mode = disembark_mode_kind_from_token(payload["disembark_mode"])
        if disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK:
            disembark: CombatDisembark | DestroyedTransportDisembark = CombatDisembark.from_payload(
                payload["disembark"]
            )
        elif disembark_mode in {
            DisembarkModeKind.DESTROYED_TRANSPORT,
            DisembarkModeKind.EMERGENCY_DISEMBARK,
        }:
            disembark = DestroyedTransportDisembark.from_payload(
                cast(DestroyedTransportDisembarkPayload, payload["disembark"])
            )
        else:
            raise GameLifecycleError(
                "TransportHazardMortalWounds requires a hazard disembark mode."
            )
        application_payload = payload["mortal_wound_application"]
        request_payload = payload["pending_mortal_wound_request"]
        result = cls(
            source_rule_id=payload["source_rule_id"],
            source_kind=payload["source_kind"],
            disembark=disembark,
            mortal_wound_application=None
            if application_payload is None
            else MortalWoundApplication.from_payload(application_payload),
            pending_mortal_wound_request=None
            if request_payload is None
            else DecisionRequest.from_payload(request_payload),
        )
        if result.mortal_wounds != payload["mortal_wounds"]:
            raise GameLifecycleError("TransportHazardMortalWounds mortal wound drift.")
        expected_request_id = (
            None
            if result.pending_mortal_wound_request is None
            else result.pending_mortal_wound_request.request_id
        )
        if expected_request_id != payload["pending_mortal_wound_request_id"]:
            raise GameLifecycleError("TransportHazardMortalWounds pending request drift.")
        return result


@dataclass(frozen=True, slots=True)
class FiringDeckWeaponSelection:
    embarked_unit_instance_id: str
    model_instance_id: str
    wargear_id: str
    weapon_profile: WeaponProfile

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "embarked_unit_instance_id",
            _validate_identifier(
                "FiringDeckWeaponSelection embarked_unit_instance_id",
                self.embarked_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "FiringDeckWeaponSelection model_instance_id", self.model_instance_id
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("FiringDeckWeaponSelection wargear_id", self.wargear_id),
        )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError(
                "FiringDeckWeaponSelection weapon_profile must be a WeaponProfile."
            )

    def to_payload(self) -> FiringDeckWeaponSelectionPayload:
        return {
            "embarked_unit_instance_id": self.embarked_unit_instance_id,
            "model_instance_id": self.model_instance_id,
            "wargear_id": self.wargear_id,
            "weapon_profile": self.weapon_profile.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: FiringDeckWeaponSelectionPayload) -> Self:
        return cls(
            embarked_unit_instance_id=payload["embarked_unit_instance_id"],
            model_instance_id=payload["model_instance_id"],
            wargear_id=payload["wargear_id"],
            weapon_profile=WeaponProfile.from_payload(payload["weapon_profile"]),
        )


@dataclass(frozen=True, slots=True)
class FiringDeckSelection:
    player_id: str
    battle_round: int
    transport_unit_instance_id: str
    firing_deck_value: int
    weapon_selections: tuple[FiringDeckWeaponSelection, ...]
    already_shot_unit_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("FiringDeckSelection player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("FiringDeckSelection battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "transport_unit_instance_id",
            _validate_identifier(
                "FiringDeckSelection transport_unit_instance_id",
                self.transport_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "firing_deck_value",
            _validate_positive_int("FiringDeckSelection firing_deck_value", self.firing_deck_value),
        )
        object.__setattr__(
            self,
            "weapon_selections",
            _validate_firing_deck_weapon_selection_tuple(
                "FiringDeckSelection weapon_selections",
                self.weapon_selections,
            ),
        )
        object.__setattr__(
            self,
            "already_shot_unit_instance_ids",
            _validate_identifier_tuple(
                "FiringDeckSelection already_shot_unit_instance_ids",
                self.already_shot_unit_instance_ids,
            ),
        )

    def to_payload(self) -> FiringDeckSelectionPayload:
        return {
            "player_id": self.player_id,
            "battle_round": self.battle_round,
            "transport_unit_instance_id": self.transport_unit_instance_id,
            "firing_deck_value": self.firing_deck_value,
            "weapon_selections": [selection.to_payload() for selection in self.weapon_selections],
            "already_shot_unit_instance_ids": list(self.already_shot_unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: FiringDeckSelectionPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            battle_round=payload["battle_round"],
            transport_unit_instance_id=payload["transport_unit_instance_id"],
            firing_deck_value=payload["firing_deck_value"],
            weapon_selections=tuple(
                FiringDeckWeaponSelection.from_payload(selection)
                for selection in payload["weapon_selections"]
            ),
            already_shot_unit_instance_ids=tuple(payload["already_shot_unit_instance_ids"]),
        )


@dataclass(frozen=True, slots=True)
class FiringDeckResolution:
    selection: FiringDeckSelection
    violations: tuple[TransportOperationViolation, ...]
    temporary_weapon_profiles: tuple[WeaponProfile, ...]
    ineligible_unit_instance_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        if type(self.selection) is not FiringDeckSelection:
            raise GameLifecycleError("FiringDeckResolution selection must be FiringDeckSelection.")
        object.__setattr__(
            self,
            "violations",
            _validate_transport_violation_tuple(
                "FiringDeckResolution violations",
                self.violations,
            ),
        )
        profiles = tuple(self.temporary_weapon_profiles)
        for profile in profiles:
            if type(profile) is not WeaponProfile:
                raise GameLifecycleError(
                    "FiringDeckResolution temporary_weapon_profiles must contain WeaponProfile."
                )
        object.__setattr__(self, "temporary_weapon_profiles", profiles)
        object.__setattr__(
            self,
            "ineligible_unit_instance_ids",
            _validate_identifier_tuple(
                "FiringDeckResolution ineligible_unit_instance_ids",
                self.ineligible_unit_instance_ids,
            ),
        )
        if self.violations and (
            self.temporary_weapon_profiles or self.ineligible_unit_instance_ids
        ):
            raise GameLifecycleError("Invalid FiringDeckResolution cannot mark shooting state.")
        if not self.violations and len(self.temporary_weapon_profiles) != len(
            self.selection.weapon_selections
        ):
            raise GameLifecycleError("Valid FiringDeckResolution weapon count drift.")
        if not self.violations:
            expected_profiles = tuple(
                selection.weapon_profile for selection in self.selection.weapon_selections
            )
            if self.temporary_weapon_profiles != expected_profiles:
                raise GameLifecycleError("Valid FiringDeckResolution weapon profile drift.")
            expected_unit_ids = tuple(
                sorted(
                    {
                        selection.embarked_unit_instance_id
                        for selection in self.selection.weapon_selections
                    }
                )
            )
            if self.ineligible_unit_instance_ids != expected_unit_ids:
                raise GameLifecycleError("Valid FiringDeckResolution ineligible unit drift.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> FiringDeckResolutionPayload:
        return {
            "selection": self.selection.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "temporary_weapon_profiles": [
                profile.to_payload() for profile in self.temporary_weapon_profiles
            ],
            "ineligible_unit_instance_ids": list(self.ineligible_unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: FiringDeckResolutionPayload) -> Self:
        resolution = cls(
            selection=FiringDeckSelection.from_payload(payload["selection"]),
            violations=tuple(
                TransportOperationViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            temporary_weapon_profiles=tuple(
                WeaponProfile.from_payload(profile)
                for profile in payload["temporary_weapon_profiles"]
            ),
            ineligible_unit_instance_ids=tuple(payload["ineligible_unit_instance_ids"]),
        )
        if resolution.is_valid != payload["is_valid"]:
            raise GameLifecycleError("FiringDeckResolution payload validity drift.")
        return resolution


def resolve_embark(
    *,
    scenario: BattlefieldScenario,
    cargo_state: TransportCargoState,
    selection: EmbarkSelection,
    unit_placement: UnitPlacement,
    transport_placement: UnitPlacement,
    persisting_effects: tuple[PersistingEffect, ...] = (),
) -> EmbarkResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("resolve_embark requires a BattlefieldScenario.")
    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("resolve_embark requires a TransportCargoState.")
    if type(selection) is not EmbarkSelection:
        raise GameLifecycleError("resolve_embark requires an EmbarkSelection.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("resolve_embark unit_placement must be UnitPlacement.")
    if type(transport_placement) is not UnitPlacement:
        raise GameLifecycleError("resolve_embark transport_placement must be UnitPlacement.")
    if type(persisting_effects) is not tuple:
        raise GameLifecycleError("resolve_embark persisting_effects must be a tuple.")
    for effect in persisting_effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("resolve_embark persisting_effects must contain effects.")
    active_cargo = cargo_state.for_movement_phase(battle_round=selection.battle_round)
    unit = scenario.unit_instance_for_placement(unit_placement)
    transport = scenario.unit_instance_for_placement(transport_placement)
    violations: list[TransportOperationViolation] = []
    _append_transport_common_violations(
        violations=violations,
        cargo_state=active_cargo,
        selection_player_id=selection.player_id,
        transport=transport,
        transport_placement=transport_placement,
    )
    if unit_placement.unit_instance_id != selection.unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Embark unit placement does not match selected unit.",
                unit_instance_id=selection.unit_instance_id,
            )
        )
    if unit_placement.player_id != selection.player_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
                message="Embarking unit must belong to the selected player.",
                unit_instance_id=unit_placement.unit_instance_id,
            )
        )
    if active_cargo.contains_unit(unit_placement.unit_instance_id):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_ALREADY_EMBARKED,
                message="Unit is already embarked in this Transport.",
                unit_instance_id=unit_placement.unit_instance_id,
            )
        )
    forbidden_source_ids = embark_transport_forbidden_effect_source_ids(
        persisting_effects,
        owner_player_id=selection.player_id,
    )
    for source_rule_id in forbidden_source_ids:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.EMBARK_FORBIDDEN_BY_EFFECT,
                message="A persisting rule effect forbids this unit from Embarking.",
                unit_instance_id=unit_placement.unit_instance_id,
                source_rule_id=source_rule_id,
            )
        )
    if active_cargo.unit_disembarked_this_phase(unit_placement.unit_instance_id) and not (
        selection.has_override(TransportRestrictionOverrideKind.ALLOW_EMBARK_AFTER_DISEMBARK)
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.EMBARK_AFTER_DISEMBARK_FORBIDDEN,
                message="Unit cannot Embark after it Disembarked in the same phase.",
                unit_instance_id=unit_placement.unit_instance_id,
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
            )
        )
    if not active_cargo.capacity_profile.allows_unit(unit):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.CAPACITY_EXCEEDED,
                message="Transport capacity profile does not allow this unit.",
                unit_instance_id=unit.unit_instance_id,
                source_rule_id=active_cargo.capacity_profile.source_id,
            )
        )
    if (
        _cargo_model_count(
            scenario=scenario,
            cargo_state=active_cargo,
        )
        + len(unit.own_models)
        > active_cargo.capacity_profile.max_model_count
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.CAPACITY_EXCEEDED,
                message="Transport capacity would be exceeded.",
                unit_instance_id=unit.unit_instance_id,
                source_rule_id=active_cargo.capacity_profile.source_id,
            )
        )
    transport_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=transport_placement,
    )
    for model in _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=unit_placement,
    ):
        if not _model_within_any_transport_model(
            model,
            transport_models=transport_models,
            distance_inches=_EMBARK_DISTANCE_INCHES,
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.EMBARK_DISTANCE,
                    message="Embark requires every model to end within 3 inches of the Transport.",
                    unit_instance_id=unit.unit_instance_id,
                    model_instance_id=model.model_id,
                    blocker_id=transport_placement.unit_instance_id,
                    source_rule_id=_CORE_TRANSPORT_RULE_ID,
                )
            )
    if violations:
        return EmbarkResolution(
            selection=selection,
            violations=tuple(violations),
            updated_cargo_state=None,
            transition_batch=None,
        )
    return EmbarkResolution(
        selection=selection,
        violations=(),
        updated_cargo_state=active_cargo.with_embarked_unit(unit.unit_instance_id),
        transition_batch=_embark_transition_batch(
            unit_placement=unit_placement,
            transport_unit_instance_id=transport_placement.unit_instance_id,
        ),
    )


def apply_embark_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    embark: EmbarkResolution,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(embark) is not EmbarkResolution:
        raise GameLifecycleError("embark must be an EmbarkResolution.")
    if not embark.is_valid:
        raise GameLifecycleError("Invalid EmbarkResolution cannot mutate battlefield_state.")
    return battlefield_state.without_unit_placement(embark.selection.unit_instance_id)


def resolve_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    battlefield_width_inches: float = _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
) -> DisembarkResolution:
    if selection.disembark_mode is DisembarkModeKind.COMBAT_DISEMBARK:
        raise GameLifecycleError("Combat Disembark requires resolve_combat_disembark.")
    if selection.disembark_mode not in {
        DisembarkModeKind.RAPID_DISEMBARK,
        DisembarkModeKind.TACTICAL_DISEMBARK,
    }:
        raise GameLifecycleError("resolve_disembark requires a standard Disembark mode.")
    return _resolve_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=unit,
        transport_placement=transport_placement,
        require_started_phase_embarked=True,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
    )


def resolve_combat_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    dice_manager: DiceRollManager,
    battlefield_width_inches: float = _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
) -> CombatDisembark:
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Combat Disembark requires a DiceRollManager.")
    if selection.disembark_mode is not DisembarkModeKind.COMBAT_DISEMBARK:
        raise GameLifecycleError("Combat Disembark resolver requires Combat mode.")
    placement = _resolve_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=selection,
        unit=unit,
        transport_placement=transport_placement,
        require_started_phase_embarked=True,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
    )
    model_rolls: list[DestroyedTransportModelRoll] = []
    if placement.is_valid:
        for model_placement in selection.attempted_placement.model_placements:
            roll_state = dice_manager.roll(
                hazard_roll_spec(
                    reason=f"Combat Disembark hazard roll for {model_placement.model_instance_id}",
                    roll_type="combat_disembark.hazard_roll",
                    actor_id=model_placement.model_instance_id,
                )
            )
            model_rolls.append(
                DestroyedTransportModelRoll(
                    model_instance_id=model_placement.model_instance_id,
                    roll_state=roll_state,
                    mortal_wound_inflicted=hazard_roll_failed(roll_state),
                )
            )
    return CombatDisembark(
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        transport_unit_instance_id=selection.transport_unit_instance_id,
        placement=placement,
        roll_threshold=HAZARD_ROLL_FAILURE_THRESHOLD,
        model_rolls=tuple(model_rolls),
        mortal_wounds_per_failed_roll=hazard_mortal_wounds_per_failed_roll(unit),
    )


def apply_disembark_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    disembark: DisembarkResolution,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(disembark) is not DisembarkResolution:
        raise GameLifecycleError("disembark must be a DisembarkResolution.")
    if not disembark.is_valid:
        raise GameLifecycleError("Invalid DisembarkResolution cannot mutate battlefield_state.")
    return battlefield_state.with_added_unit_placement(disembark.selection.attempted_placement)


def apply_combat_disembark_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    disembark: CombatDisembark,
) -> BattlefieldRuntimeState:
    if type(disembark) is not CombatDisembark:
        raise GameLifecycleError("disembark must be CombatDisembark.")
    return apply_disembark_to_battlefield(
        battlefield_state=battlefield_state,
        disembark=disembark.placement,
    )


def resolve_destroyed_transport_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    dice_manager: DiceRollManager,
    battlefield_width_inches: float = _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
) -> DestroyedTransportDisembark:
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Destroyed Transport disembark requires a DiceRollManager.")
    if selection.disembark_mode not in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        raise GameLifecycleError(
            "Destroyed Transport disembark requires destroyed or emergency mode."
        )
    emergency = selection.disembark_mode is DisembarkModeKind.EMERGENCY_DISEMBARK
    destroyed_selection = replace(
        selection,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    placement = _resolve_disembark(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        cargo_state=cargo_state,
        selection=destroyed_selection,
        unit=unit,
        transport_placement=transport_placement,
        require_started_phase_embarked=False,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
        objective_markers=objective_markers,
    )
    roll_threshold = HAZARD_ROLL_FAILURE_THRESHOLD
    expected_model_ids = {model.model_instance_id for model in unit.own_models}
    placed_model_ids = {
        placement.model_instance_id for placement in selection.attempted_placement.model_placements
    }
    destroyed_model_ids = tuple(sorted(expected_model_ids - placed_model_ids)) if emergency else ()
    model_rolls: list[DestroyedTransportModelRoll] = []
    if placement.is_valid:
        roll_model_ids = tuple(sorted(expected_model_ids if emergency else placed_model_ids))
        for model_instance_id in roll_model_ids:
            roll_state = dice_manager.roll(
                hazard_roll_spec(
                    reason=(f"Destroyed Transport disembark roll for {model_instance_id}"),
                    roll_type="destroyed_transport_disembark",
                    actor_id=model_instance_id,
                )
            )
            model_rolls.append(
                DestroyedTransportModelRoll(
                    model_instance_id=model_instance_id,
                    roll_state=roll_state,
                    mortal_wound_inflicted=hazard_roll_failed(roll_state),
                )
            )
    return DestroyedTransportDisembark(
        player_id=selection.player_id,
        battle_round=selection.battle_round,
        unit_instance_id=selection.unit_instance_id,
        transport_unit_instance_id=selection.transport_unit_instance_id,
        disembark_mode=selection.disembark_mode,
        placement=placement,
        roll_threshold=roll_threshold,
        model_rolls=tuple(model_rolls),
        mortal_wounds_per_failed_roll=hazard_mortal_wounds_per_failed_roll(unit),
        destroyed_model_instance_ids=destroyed_model_ids,
    )


def apply_destroyed_transport_disembark_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    disembark: DestroyedTransportDisembark,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(disembark) is not DestroyedTransportDisembark:
        raise GameLifecycleError("disembark must be DestroyedTransportDisembark.")
    if not disembark.placement.is_valid:
        raise GameLifecycleError("Invalid destroyed Transport disembark cannot mutate battlefield.")
    updated = battlefield_state.with_added_unit_placement(
        disembark.placement.selection.attempted_placement
    )
    if disembark.destroyed_model_instance_ids:
        updated = updated.with_unplaced_models_marked_removed(
            disembark.destroyed_model_instance_ids
        )
    return updated


def apply_transport_hazard_mortal_wounds(
    *,
    state: GameState,
    decisions: DecisionController,
    disembark: CombatDisembark | DestroyedTransportDisembark,
    dice_manager: DiceRollManager,
) -> TransportHazardMortalWounds:
    from warhammer40k_core.engine.damage_allocation import (
        MortalWoundApplicationProgress,
        continue_mortal_wound_application,
        unit_owner_player_id,
    )
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Transport hazard mortal wounds require GameState.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Transport hazard mortal wounds require DecisionController.")
    if type(disembark) not in {CombatDisembark, DestroyedTransportDisembark}:
        raise GameLifecycleError(
            "Transport hazard mortal wounds require a transport hazard disembark."
        )
    if type(dice_manager) is not DiceRollManager:
        raise GameLifecycleError("Transport hazard mortal wounds require DiceRollManager.")
    if state.battle_round != disembark.battle_round:
        raise GameLifecycleError("Transport hazard mortal wounds battle_round drift.")
    if not disembark.placement.is_valid:
        raise GameLifecycleError(
            "Transport hazard mortal wounds require a valid disembark placement."
        )
    battlefield = state.battlefield_state
    if battlefield is None:
        raise GameLifecycleError("Transport hazard mortal wounds require battlefield_state.")
    try:
        battlefield.unit_placement_by_id(disembark.unit_instance_id)
    except PlacementError as exc:
        raise GameLifecycleError(
            "Transport hazard mortal wounds require the disembarked unit to be placed."
        ) from exc

    mortal_wounds = disembark.mortal_wound_count
    if mortal_wounds == 0:
        resolved = TransportHazardMortalWounds(
            source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
            source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            disembark=disembark,
        )
        _emit_transport_hazard_mortal_wounds_resolved(decisions=decisions, result=resolved)
        return resolved

    progress = MortalWoundApplicationProgress.start(
        application_id=(
            f"{disembark.unit_instance_id}:{disembark_mode_for_hazard(disembark).value}:"
            f"transport-hazard-mortal-wounds:r{disembark.battle_round}"
        ),
        source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
        source_context=_transport_hazard_source_context(
            disembark=disembark,
            mortal_wounds=mortal_wounds,
        ),
        target_unit_instance_id=disembark.unit_instance_id,
        defender_player_id=unit_owner_player_id(
            state=state,
            unit_instance_id=disembark.unit_instance_id,
        ),
        mortal_wounds=mortal_wounds,
        spill_over=True,
    )
    routed = continue_mortal_wound_application(
        state=state,
        request_id=state.next_decision_request_id(),
        progress=progress,
        dice_manager=dice_manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return TransportHazardMortalWounds(
            source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
            source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            disembark=disembark,
            pending_mortal_wound_request=routed.request,
        )
    if routed.application is None:
        raise GameLifecycleError("Transport hazard mortal wounds did not produce application.")
    resolved = TransportHazardMortalWounds(
        source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
        source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
        disembark=disembark,
        mortal_wound_application=routed.application,
    )
    _emit_transport_hazard_mortal_wounds_resolved(decisions=decisions, result=resolved)
    return resolved


def apply_transport_hazard_mortal_wound_feel_no_pain_decision(
    *,
    state: GameState,
    result: DecisionResult,
    decisions: DecisionController,
) -> LifecycleStatus | None:
    from warhammer40k_core.engine.damage_allocation import (
        SELECT_FEEL_NO_PAIN_DECISION_TYPE,
        is_mortal_wound_feel_no_pain_request,
        mortal_wound_feel_no_pain_source_context,
        resolve_mortal_wound_feel_no_pain_decision,
    )
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Transport hazard Feel No Pain requires GameState.")
    if type(result) is not DecisionResult:
        raise GameLifecycleError("Transport hazard Feel No Pain requires DecisionResult.")
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Transport hazard Feel No Pain requires DecisionController.")
    record = decisions.record_for_result(result)
    request = record.request
    if not is_mortal_wound_feel_no_pain_request(request):
        raise GameLifecycleError("Transport hazard Feel No Pain requires mortal wound context.")
    source_context = mortal_wound_feel_no_pain_source_context(request)
    disembark = _transport_hazard_disembark_from_source_context(source_context)
    manager = DiceRollManager(state.game_id, event_log=decisions.event_log)
    routed = resolve_mortal_wound_feel_no_pain_decision(
        state=state,
        request=request,
        result=result,
        next_request_id=state.next_decision_request_id(),
        dice_manager=manager,
    )
    if routed.request is not None:
        decisions.request_decision(routed.request)
        return LifecycleStatus.waiting_for_decision(
            stage=state.stage,
            decision_request=routed.request,
            payload={
                "phase": state.current_battle_phase.value
                if state.current_battle_phase is not None
                else None,
                "decision_type": SELECT_FEEL_NO_PAIN_DECISION_TYPE,
                "source_rule_id": CORE_HAZARD_ROLLS_RULE_ID,
                "source_kind": TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            },
        )
    if routed.application is None:
        raise GameLifecycleError("Transport hazard Feel No Pain did not finish routing.")
    resolved = TransportHazardMortalWounds(
        source_rule_id=CORE_HAZARD_ROLLS_RULE_ID,
        source_kind=TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
        disembark=disembark,
        mortal_wound_application=routed.application,
    )
    _emit_transport_hazard_mortal_wounds_resolved(decisions=decisions, result=resolved)
    return None


def disembark_mode_for_hazard(
    disembark: CombatDisembark | DestroyedTransportDisembark,
) -> DisembarkModeKind:
    if type(disembark) is CombatDisembark:
        return DisembarkModeKind.COMBAT_DISEMBARK
    if type(disembark) is DestroyedTransportDisembark:
        return disembark.disembark_mode
    raise GameLifecycleError("Unsupported transport hazard disembark.")


def _transport_hazard_source_context(
    *,
    disembark: CombatDisembark | DestroyedTransportDisembark,
    mortal_wounds: int,
) -> JsonValue:
    return validate_json_value(
        {
            "source_kind": TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND,
            "source_rule_id": CORE_HAZARD_ROLLS_RULE_ID,
            "player_id": disembark.player_id,
            "battle_round": disembark.battle_round,
            "unit_instance_id": disembark.unit_instance_id,
            "transport_unit_instance_id": disembark.transport_unit_instance_id,
            "disembark_mode": disembark_mode_for_hazard(disembark).value,
            "mortal_wounds": mortal_wounds,
            "disembark": disembark.to_payload(),
        }
    )


def _transport_hazard_disembark_from_source_context(
    source_context: JsonValue,
) -> CombatDisembark | DestroyedTransportDisembark:
    if not isinstance(source_context, dict):
        raise GameLifecycleError("Transport hazard source context is invalid.")
    if source_context.get("source_kind") != TRANSPORT_HAZARD_MORTAL_WOUNDS_SOURCE_KIND:
        raise GameLifecycleError("Transport hazard source kind is invalid.")
    if source_context.get("source_rule_id") != CORE_HAZARD_ROLLS_RULE_ID:
        raise GameLifecycleError("Transport hazard source_rule_id is invalid.")
    mode = disembark_mode_kind_from_token(source_context.get("disembark_mode"))
    disembark_payload = source_context.get("disembark")
    if not isinstance(disembark_payload, dict):
        raise GameLifecycleError("Transport hazard disembark payload is invalid.")
    if mode is DisembarkModeKind.COMBAT_DISEMBARK:
        disembark: CombatDisembark | DestroyedTransportDisembark = CombatDisembark.from_payload(
            cast(CombatDisembarkPayload, disembark_payload)
        )
    elif mode in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        disembark = DestroyedTransportDisembark.from_payload(
            cast(DestroyedTransportDisembarkPayload, disembark_payload)
        )
    else:
        raise GameLifecycleError("Transport hazard source mode is invalid.")
    if source_context.get("player_id") != disembark.player_id:
        raise GameLifecycleError("Transport hazard source player drift.")
    if source_context.get("battle_round") != disembark.battle_round:
        raise GameLifecycleError("Transport hazard source battle_round drift.")
    if source_context.get("unit_instance_id") != disembark.unit_instance_id:
        raise GameLifecycleError("Transport hazard source unit drift.")
    if source_context.get("transport_unit_instance_id") != disembark.transport_unit_instance_id:
        raise GameLifecycleError("Transport hazard source transport drift.")
    if source_context.get("mortal_wounds") != disembark.mortal_wound_count:
        raise GameLifecycleError("Transport hazard source mortal wound drift.")
    return disembark


def _emit_transport_hazard_mortal_wounds_resolved(
    *,
    decisions: DecisionController,
    result: TransportHazardMortalWounds,
) -> None:
    if type(decisions) is not DecisionController:
        raise GameLifecycleError("Transport hazard event requires DecisionController.")
    if type(result) is not TransportHazardMortalWounds:
        raise GameLifecycleError("Transport hazard event requires TransportHazardMortalWounds.")
    decisions.event_log.append(
        TRANSPORT_HAZARD_MORTAL_WOUNDS_EVENT_TYPE,
        result.to_payload(),
    )


def resolve_firing_deck_selection(
    *,
    cargo_state: TransportCargoState,
    selection: FiringDeckSelection,
    embarked_units: tuple[UnitInstance, ...],
) -> FiringDeckResolution:
    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("resolve_firing_deck_selection requires TransportCargoState.")
    if type(selection) is not FiringDeckSelection:
        raise GameLifecycleError("resolve_firing_deck_selection requires FiringDeckSelection.")
    units = _unit_by_id(embarked_units)
    violations: list[TransportOperationViolation] = []
    if selection.transport_unit_instance_id != cargo_state.transport_unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
                message="Firing Deck selection transport drift.",
                unit_instance_id=selection.transport_unit_instance_id,
            )
        )
    if len(selection.weapon_selections) > selection.firing_deck_value:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FIRING_DECK_CAPACITY_EXCEEDED,
                message="Firing Deck selection exceeds the ability value.",
                unit_instance_id=selection.transport_unit_instance_id,
            )
        )
    selected_model_keys: set[tuple[str, str]] = set()
    for weapon_selection in selection.weapon_selections:
        selected_model_key = (
            weapon_selection.embarked_unit_instance_id,
            weapon_selection.model_instance_id,
        )
        if selected_model_key in selected_model_keys:
            violations.append(
                TransportOperationViolation(
                    violation_code=(
                        TransportOperationViolationCode.FIRING_DECK_DUPLICATE_MODEL_SELECTION
                    ),
                    message="Firing Deck can select at most one weapon per embarked model.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
        selected_model_keys.add(selected_model_key)
        unit = units.get(weapon_selection.embarked_unit_instance_id)
        if unit is None or not cargo_state.contains_unit(
            weapon_selection.embarked_unit_instance_id
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_UNIT_NOT_EMBARKED,
                    message="Firing Deck selected unit is not embarked in this Transport.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                )
            )
            continue
        if weapon_selection.embarked_unit_instance_id in selection.already_shot_unit_instance_ids:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_UNIT_ALREADY_SHOT,
                    message="Firing Deck cannot select a unit that has already shot.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                )
            )
        if weapon_selection.model_instance_id not in {
            model.model_instance_id for model in unit.own_models
        }:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_MODEL_DRIFT,
                    message="Firing Deck selected model is not in the embarked unit.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
        if weapon_selection.weapon_profile.range_profile.kind is RangeProfileKind.MELEE:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_MELEE_WEAPON,
                    message="Firing Deck requires a ranged weapon.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
        if WeaponKeyword.ONE_SHOT in weapon_selection.weapon_profile.keywords:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.FIRING_DECK_ONE_SHOT_WEAPON,
                    message="Firing Deck cannot select One Shot weapons.",
                    unit_instance_id=weapon_selection.embarked_unit_instance_id,
                    model_instance_id=weapon_selection.model_instance_id,
                )
            )
    if violations:
        return FiringDeckResolution(
            selection=selection,
            violations=tuple(violations),
            temporary_weapon_profiles=(),
            ineligible_unit_instance_ids=(),
        )
    return FiringDeckResolution(
        selection=selection,
        violations=(),
        temporary_weapon_profiles=tuple(
            weapon_selection.weapon_profile for weapon_selection in selection.weapon_selections
        ),
        ineligible_unit_instance_ids=tuple(
            sorted(
                {
                    weapon_selection.embarked_unit_instance_id
                    for weapon_selection in selection.weapon_selections
                }
            )
        ),
    )


def transport_movement_status_from_token(token: object) -> TransportMovementStatus:
    if type(token) is TransportMovementStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TransportMovementStatus token must be a string.")
    try:
        return TransportMovementStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported TransportMovementStatus token: {token}.") from exc


def transport_restriction_override_kind_from_token(
    token: object,
) -> TransportRestrictionOverrideKind:
    if type(token) is TransportRestrictionOverrideKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TransportRestrictionOverrideKind token must be a string.")
    try:
        return TransportRestrictionOverrideKind(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported TransportRestrictionOverrideKind token: {token}."
        ) from exc


def disembark_mode_kind_from_token(token: object) -> DisembarkModeKind:
    if type(token) is DisembarkModeKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("DisembarkModeKind token must be a string.")
    try:
        return DisembarkModeKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported DisembarkModeKind token: {token}.") from exc


def transport_operation_violation_code_from_token(
    token: object,
) -> TransportOperationViolationCode:
    if type(token) is TransportOperationViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("TransportOperationViolationCode token must be a string.")
    try:
        return TransportOperationViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported TransportOperationViolationCode token: {token}."
        ) from exc


def _resolve_disembark(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    cargo_state: TransportCargoState,
    selection: DisembarkSelection,
    unit: UnitInstance,
    transport_placement: UnitPlacement,
    require_started_phase_embarked: bool,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
) -> DisembarkResolution:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("resolve_disembark requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("resolve_disembark requires a RulesetDescriptor.")
    if type(cargo_state) is not TransportCargoState:
        raise GameLifecycleError("resolve_disembark requires a TransportCargoState.")
    if type(selection) is not DisembarkSelection:
        raise GameLifecycleError("resolve_disembark requires a DisembarkSelection.")
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("resolve_disembark unit must be a UnitInstance.")
    if type(transport_placement) is not UnitPlacement:
        raise GameLifecycleError("resolve_disembark transport_placement must be UnitPlacement.")
    width = _validate_positive_number("battlefield_width_inches", battlefield_width_inches)
    depth = _validate_positive_number("battlefield_depth_inches", battlefield_depth_inches)
    features = _validate_terrain_feature_tuple("terrain_features", terrain_features)
    markers = _validate_objective_marker_tuple("objective_markers", objective_markers)
    disembark_mode = selection.disembark_mode
    distance_inches = _disembark_distance_inches(disembark_mode)
    allow_partial = disembark_mode is DisembarkModeKind.EMERGENCY_DISEMBARK
    active_cargo = cargo_state.for_movement_phase(battle_round=selection.battle_round)
    transport = scenario.unit_instance_for_placement(transport_placement)
    violations: list[TransportOperationViolation] = []
    _append_transport_common_violations(
        violations=violations,
        cargo_state=active_cargo,
        selection_player_id=selection.player_id,
        transport=transport,
        transport_placement=transport_placement,
    )
    if selection.unit_instance_id != unit.unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Disembark unit does not match selected unit.",
                unit_instance_id=selection.unit_instance_id,
            )
        )
    if not active_cargo.contains_unit(unit.unit_instance_id):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_NOT_EMBARKED,
                message="Disembark requires the unit to be embarked in the Transport.",
                unit_instance_id=unit.unit_instance_id,
                blocker_id=active_cargo.transport_unit_instance_id,
            )
        )
    if require_started_phase_embarked and not active_cargo.unit_started_phase_embarked(
        unit.unit_instance_id
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_DID_NOT_START_PHASE_EMBARKED,
                message="Disembark requires the unit to have started the phase embarked.",
                unit_instance_id=unit.unit_instance_id,
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
            )
        )
    if selection.transport_movement_status in {
        TransportMovementStatus.ADVANCE,
        TransportMovementStatus.FALL_BACK,
    } and not selection.has_override(
        TransportRestrictionOverrideKind.ALLOW_DISEMBARK_AFTER_ADVANCE_OR_FALL_BACK
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.TRANSPORT_ADVANCED_OR_FELL_BACK,
                message="Units cannot Disembark after their Transport Advanced or Fell Back.",
                unit_instance_id=unit.unit_instance_id,
                blocker_id=transport_placement.unit_instance_id,
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
            )
        )
    _append_unit_placement_drift_violations(
        violations=violations,
        unit=unit,
        attempted_placement=selection.attempted_placement,
        allow_partial=allow_partial,
    )
    models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=selection.attempted_placement,
    )
    transport_models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=transport_placement,
    )
    _append_disembark_endpoint_violations(
        violations=violations,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit=unit,
        attempted_placement=selection.attempted_placement,
        models=models,
        transport_models=transport_models,
        distance_inches=distance_inches,
        battlefield_width_inches=width,
        battlefield_depth_inches=depth,
        terrain_features=features,
        objective_markers=markers,
        disembark_mode=disembark_mode,
    )
    coherency_result = unit_placement_coherency_result(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=selection.attempted_placement,
    )
    if not coherency_result.is_coherent:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_COHERENCY_BROKEN,
                message="Disembark placement violates unit coherency.",
                unit_instance_id=unit.unit_instance_id,
            )
        )
    if violations:
        return DisembarkResolution(
            selection=selection,
            violations=tuple(violations),
            coherency_result=coherency_result,
            updated_cargo_state=None,
            disembarked_unit_state=None,
            transition_batch=None,
        )
    is_destroyed_transport_disembark_mode = selection.disembark_mode in (
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    )
    disembarked_state = (
        DisembarkedUnitState.for_destroyed_transport(
            player_id=selection.player_id,
            battle_round=selection.battle_round,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            disembark_mode=selection.disembark_mode,
        )
        if is_destroyed_transport_disembark_mode
        else DisembarkedUnitState.for_mode(
            player_id=selection.player_id,
            battle_round=selection.battle_round,
            unit_instance_id=selection.unit_instance_id,
            transport_unit_instance_id=selection.transport_unit_instance_id,
            disembark_mode=selection.disembark_mode,
            transport_movement_status=selection.transport_movement_status,
        )
    )
    return DisembarkResolution(
        selection=selection,
        violations=(),
        coherency_result=coherency_result,
        updated_cargo_state=active_cargo.with_disembarked_unit(unit.unit_instance_id),
        disembarked_unit_state=disembarked_state,
        transition_batch=_disembark_transition_batch(
            attempted_placement=selection.attempted_placement,
            source_rule_id=disembarked_state.source_rule_id,
        ),
    )


def _disembark_distance_inches(disembark_mode: DisembarkModeKind) -> float:
    mode = disembark_mode_kind_from_token(disembark_mode)
    if mode in {
        DisembarkModeKind.EMERGENCY_DISEMBARK,
        DisembarkModeKind.COMBAT_DISEMBARK,
    }:
        return _EMERGENCY_DISEMBARK_DISTANCE_INCHES
    if mode in {
        DisembarkModeKind.RAPID_DISEMBARK,
        DisembarkModeKind.TACTICAL_DISEMBARK,
        DisembarkModeKind.DESTROYED_TRANSPORT,
    }:
        return _DISEMBARK_DISTANCE_INCHES
    raise GameLifecycleError("Unsupported DisembarkModeKind.")


def _validate_disembark_mode_status(
    *,
    disembark_mode: DisembarkModeKind,
    transport_movement_status: TransportMovementStatus,
) -> None:
    mode = disembark_mode_kind_from_token(disembark_mode)
    status = transport_movement_status_from_token(transport_movement_status)
    if mode is DisembarkModeKind.TACTICAL_DISEMBARK:
        if status not in {
            TransportMovementStatus.NOT_MOVED,
            TransportMovementStatus.REMAIN_STATIONARY,
        }:
            raise GameLifecycleError(
                "Tactical Disembark requires an unmoved or stationary Transport."
            )
        return
    if mode is DisembarkModeKind.RAPID_DISEMBARK:
        if status not in {
            TransportMovementStatus.NORMAL_MOVE,
            TransportMovementStatus.INGRESS_MOVE,
        }:
            raise GameLifecycleError(
                "Rapid Disembark requires Normal or Ingress Transport movement."
            )
        return
    if mode is DisembarkModeKind.COMBAT_DISEMBARK:
        if status not in {
            TransportMovementStatus.NOT_MOVED,
            TransportMovementStatus.REMAIN_STATIONARY,
        }:
            raise GameLifecycleError(
                "Combat Disembark requires an unmoved or stationary Transport."
            )
        return
    if mode in {
        DisembarkModeKind.DESTROYED_TRANSPORT,
        DisembarkModeKind.EMERGENCY_DISEMBARK,
    }:
        if status is not TransportMovementStatus.NOT_MOVED:
            raise GameLifecycleError("Destroyed Transport Disembark requires destroyed timing.")
        return
    raise GameLifecycleError("Unsupported DisembarkModeKind.")


def _append_transport_common_violations(
    *,
    violations: list[TransportOperationViolation],
    cargo_state: TransportCargoState,
    selection_player_id: str,
    transport: UnitInstance,
    transport_placement: UnitPlacement,
) -> None:
    if transport_placement.unit_instance_id != cargo_state.transport_unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
                message="Transport placement does not match cargo state.",
                unit_instance_id=cargo_state.transport_unit_instance_id,
            )
        )
    if transport_placement.player_id != selection_player_id or cargo_state.player_id != (
        selection_player_id
    ):
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.FRIENDLY_TRANSPORT_REQUIRED,
                message="Transport and selected unit must belong to the active player.",
                unit_instance_id=cargo_state.transport_unit_instance_id,
            )
        )
    if _TRANSPORT_KEYWORD not in {_canonical_keyword(keyword) for keyword in transport.keywords}:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.TRANSPORT_KEYWORD_REQUIRED,
                message="Transport cargo state must reference a Transport unit.",
                unit_instance_id=transport.unit_instance_id,
            )
        )
    if transport.datasheet_id != cargo_state.capacity_profile.transport_datasheet_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.TRANSPORT_DATASHEET_MISMATCH,
                message="Transport capacity profile datasheet does not match the Transport unit.",
                unit_instance_id=transport.unit_instance_id,
                source_rule_id=cargo_state.capacity_profile.source_id,
            )
        )


def _append_unit_placement_drift_violations(
    *,
    violations: list[TransportOperationViolation],
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
    allow_partial: bool,
) -> None:
    if attempted_placement.unit_instance_id != unit.unit_instance_id:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Transport placement unit_instance_id does not match unit.",
                unit_instance_id=unit.unit_instance_id,
            )
        )
        return
    attempted_model_ids = tuple(
        sorted(placement.model_instance_id for placement in attempted_placement.model_placements)
    )
    expected_model_ids = tuple(sorted(model.model_instance_id for model in unit.own_models))
    if allow_partial:
        if set(attempted_model_ids) - set(expected_model_ids):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                    message="Emergency Disembark placement references an unknown model.",
                    unit_instance_id=unit.unit_instance_id,
                )
            )
        return
    if attempted_model_ids != expected_model_ids:
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Disembark placement must include every model in the unit.",
                unit_instance_id=unit.unit_instance_id,
            )
        )


def _append_disembark_endpoint_violations(
    *,
    violations: list[TransportOperationViolation],
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
    models: tuple[Model, ...],
    transport_models: tuple[Model, ...],
    distance_inches: float,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    disembark_mode: DisembarkModeKind,
) -> None:
    mode = disembark_mode_kind_from_token(disembark_mode)
    placed_models = _placed_geometry_models(scenario)
    own_model_ids = {model.model_id for model in models}
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    enemy_models = tuple(
        blocker
        for blocker in blockers
        if _model_owner_player_id(scenario=scenario, model_instance_id=blocker.model_id)
        != attempted_placement.player_id
    )
    combat_engagement_unit_ids = (
        _enemy_unit_ids_engaged_with_transport(
            scenario=scenario,
            ruleset_descriptor=ruleset_descriptor,
            transport_models=transport_models,
            transport_player_id=attempted_placement.player_id,
        )
        if mode is DisembarkModeKind.COMBAT_DISEMBARK
        else ()
    )
    combat_engagement_units = set(combat_engagement_unit_ids)
    for model in models:
        if not _model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Disembark placement crosses the battlefield edge.",
                    model_instance_id=model.model_id,
                    unit_instance_id=attempted_placement.unit_instance_id,
                )
            )
        if not _model_wholly_within_any_transport_model(
            model,
            transport_models=transport_models,
            distance_inches=distance_inches,
        ):
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.DISEMBARK_DISTANCE,
                    message="Disembark placement must be wholly within the required distance.",
                    model_instance_id=model.model_id,
                    unit_instance_id=attempted_placement.unit_instance_id,
                )
            )
        for blocker in blockers:
            if _models_overlap_with_volume(model, blocker):
                violations.append(
                    TransportOperationViolation(
                        violation_code=TransportOperationViolationCode.MODEL_OVERLAP,
                        message="Disembark placement overlaps another model.",
                        model_instance_id=model.model_id,
                        blocker_id=blocker.model_id,
                    )
                )
        for enemy_model in enemy_models:
            if model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                enemy_unit_id = _model_owner_unit_id(
                    scenario=scenario,
                    model_instance_id=enemy_model.model_id,
                )
                if enemy_unit_id in combat_engagement_units:
                    continue
                violations.append(
                    TransportOperationViolation(
                        violation_code=TransportOperationViolationCode.ENEMY_ENGAGEMENT_RANGE,
                        message="Disembark placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = terrain_endpoint_placement_violation(
            model=model,
            unit=unit,
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=terrain_features,
            violation_code=TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
            placement_label="Disembark placement",
        )
        if terrain_violation is not None:
            violations.append(
                TransportOperationViolation(
                    violation_code=TransportOperationViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
                    message=terrain_violation.message,
                    model_instance_id=terrain_violation.model_instance_id,
                    blocker_id=terrain_violation.blocker_id,
                )
            )
        objective_marker_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=objective_markers,
            violation_code=TransportOperationViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Disembark placement",
        )
        if objective_marker_violation is not None:
            violations.append(
                TransportOperationViolation(
                    violation_code=(
                        TransportOperationViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP
                    ),
                    message=objective_marker_violation.message,
                    model_instance_id=objective_marker_violation.model_instance_id,
                    blocker_id=objective_marker_violation.blocker_id,
                )
            )
    overlap = _moving_models_overlap(models)
    if overlap is not None:
        first_id, second_id = overlap
        violations.append(
            TransportOperationViolation(
                violation_code=TransportOperationViolationCode.MODEL_OVERLAP,
                message="Disembark placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )


def _embark_transition_batch(
    *,
    unit_placement: UnitPlacement,
    transport_unit_instance_id: str,
) -> BattlefieldTransitionBatch:
    return BattlefieldTransitionBatch(
        removals=tuple(
            ModelRemovalRecord(
                model_instance_id=model_placement.model_instance_id,
                removal_kind=BattlefieldRemovalKind.EMBARK,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_rule_id=_CORE_TRANSPORT_RULE_ID,
                source_event_id=None,
                destination_id=transport_unit_instance_id,
            )
            for model_placement in unit_placement.model_placements
        )
    )


def _disembark_transition_batch(
    *,
    attempted_placement: UnitPlacement,
    source_rule_id: str,
) -> BattlefieldTransitionBatch:
    return BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=model_placement.model_instance_id,
                placement_kind=BattlefieldPlacementKind.DISEMBARK,
                pose=model_placement.pose,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_rule_id=source_rule_id,
                source_event_id=None,
            )
            for model_placement in attempted_placement.model_placements
        )
    )


def _cargo_model_count(
    *,
    scenario: BattlefieldScenario,
    cargo_state: TransportCargoState,
) -> int:
    units = _all_unit_by_id(scenario)
    count = 0
    for unit_id in cargo_state.embarked_unit_instance_ids:
        unit = units.get(unit_id)
        if unit is None:
            raise GameLifecycleError("TransportCargoState references an unknown embarked unit.")
        count += len(unit.own_models)
    return count


def _all_unit_by_id(scenario: BattlefieldScenario) -> dict[str, UnitInstance]:
    return {unit.unit_instance_id: unit for army in scenario.armies for unit in army.units}


def _unit_by_id(units: tuple[UnitInstance, ...]) -> dict[str, UnitInstance]:
    validated = _validate_unit_tuple("embarked_units", units)
    return {unit.unit_instance_id: unit for unit in validated}


def _geometry_models_for_unit_placement(
    *,
    scenario: BattlefieldScenario,
    unit_placement: UnitPlacement,
) -> tuple[Model, ...]:
    return tuple(
        geometry_model_for_placement(
            model=scenario.model_instance_for_placement(placement),
            placement=placement,
        )
        for placement in unit_placement.model_placements
    )


def _placed_geometry_models(scenario: BattlefieldScenario) -> tuple[Model, ...]:
    models: list[Model] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            models.extend(
                geometry_model_for_placement(
                    model=scenario.model_instance_for_placement(placement),
                    placement=placement,
                )
                for placement in unit_placement.model_placements
            )
    return tuple(models)


def _model_owner_player_id(*, scenario: BattlefieldScenario, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                if model_placement.model_instance_id == requested_model_id:
                    return model_placement.player_id
    raise GameLifecycleError("model_instance_id is not placed.")


def _model_owner_unit_id(*, scenario: BattlefieldScenario, model_instance_id: str) -> str:
    requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            for model_placement in unit_placement.model_placements:
                if model_placement.model_instance_id == requested_model_id:
                    return unit_placement.unit_instance_id
    raise GameLifecycleError("model_instance_id is not placed.")


def _enemy_unit_ids_engaged_with_transport(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    transport_models: tuple[Model, ...],
    transport_player_id: str,
) -> tuple[str, ...]:
    enemy_unit_ids: set[str] = set()
    for blocker in _placed_geometry_models(scenario):
        if _model_owner_player_id(scenario=scenario, model_instance_id=blocker.model_id) == (
            transport_player_id
        ):
            continue
        if any(
            transport_model.is_within_engagement_range(
                blocker,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            )
            for transport_model in transport_models
        ):
            enemy_unit_ids.add(
                _model_owner_unit_id(
                    scenario=scenario,
                    model_instance_id=blocker.model_id,
                )
            )
    return tuple(sorted(enemy_unit_ids))


def _model_within_any_transport_model(
    model: Model,
    *,
    transport_models: tuple[Model, ...],
    distance_inches: float,
) -> bool:
    return any(
        model.base_distance_to(transport_model) <= distance_inches
        for transport_model in transport_models
    )


def _model_wholly_within_any_transport_model(
    model: Model,
    *,
    transport_models: tuple[Model, ...],
    distance_inches: float,
) -> bool:
    return any(
        shapely_backend.footprint_for_base(transport_model.base, transport_model.pose)
        .buffer(distance_inches)
        .covers(shapely_backend.footprint_for_base(model.base, model.pose))
        for transport_model in transport_models
    )


def _model_is_within_battlefield(
    model: Model,
    *,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    return (
        min_x >= -_EPSILON
        and min_y >= -_EPSILON
        and max_x <= battlefield_width_inches + _EPSILON
        and max_y <= battlefield_depth_inches + _EPSILON
    )


def _models_overlap_with_volume(first: Model, second: Model) -> bool:
    if first.volume.vertical_gap_to(first.pose, second.volume, second.pose) != 0.0:
        return False
    if not _model_pair_can_overlap_horizontally(first, second):
        return False
    return first.base_overlaps(second)


def _moving_models_overlap(models: tuple[Model, ...]) -> tuple[str, str] | None:
    for index, first in enumerate(models):
        for second in models[index + 1 :]:
            if _models_overlap_with_volume(first, second):
                return (first.model_id, second.model_id)
    return None


def _model_pair_can_overlap_horizontally(first: Model, second: Model) -> bool:
    return first.pose.distance_2d_to(second.pose) <= (
        first.base.max_radius() + second.base.max_radius()
    )


def _validate_transport_override_tuple(
    field_name: str,
    values: object,
) -> tuple[TransportRestrictionOverride, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    overrides: list[TransportRestrictionOverride] = []
    seen: set[TransportRestrictionOverrideKind] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TransportRestrictionOverride:
            raise GameLifecycleError(f"{field_name} must contain TransportRestrictionOverride.")
        if value.override_kind in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate override kinds.")
        seen.add(value.override_kind)
        overrides.append(value)
    return tuple(sorted(overrides, key=lambda override: override.override_kind.value))


def _validate_transport_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[TransportOperationViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    violations: list[TransportOperationViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TransportOperationViolation:
            raise GameLifecycleError(f"{field_name} must contain TransportOperationViolation.")
        violations.append(value)
    return tuple(
        sorted(
            violations,
            key=lambda violation: (
                violation.violation_code.value,
                "" if violation.unit_instance_id is None else violation.unit_instance_id,
                "" if violation.model_instance_id is None else violation.model_instance_id,
                "" if violation.blocker_id is None else violation.blocker_id,
            ),
        )
    )


def _validate_destroyed_transport_roll_tuple(
    field_name: str,
    values: object,
) -> tuple[DestroyedTransportModelRoll, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    rolls: list[DestroyedTransportModelRoll] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DestroyedTransportModelRoll:
            raise GameLifecycleError(f"{field_name} must contain DestroyedTransportModelRoll.")
        if value.model_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(value.model_instance_id)
        rolls.append(value)
    return tuple(sorted(rolls, key=lambda roll: roll.model_instance_id))


def _validate_firing_deck_weapon_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[FiringDeckWeaponSelection, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    selections: list[FiringDeckWeaponSelection] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not FiringDeckWeaponSelection:
            raise GameLifecycleError(f"{field_name} must contain FiringDeckWeaponSelection.")
        selections.append(value)
    return tuple(
        sorted(
            selections,
            key=lambda selection: (
                selection.embarked_unit_instance_id,
                selection.model_instance_id,
                selection.wargear_id,
                selection.weapon_profile.profile_id,
            ),
        )
    )


def _validate_unit_tuple(field_name: str, values: object) -> tuple[UnitInstance, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    units: list[UnitInstance] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not UnitInstance:
            raise GameLifecycleError(f"{field_name} must contain UnitInstance values.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate unit IDs.")
        seen.add(value.unit_instance_id)
        units.append(value)
    return tuple(sorted(units, key=lambda unit: unit.unit_instance_id))


def _validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GameLifecycleError(f"{field_name} must contain TerrainFeatureDefinition values.")
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_objective_marker_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveMarker, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    markers: list[ObjectiveMarker] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarker:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveMarker values.")
        if value.objective_marker_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate markers.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be greater than 0.")
    return number


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
