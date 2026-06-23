from __future__ import annotations

import math
from dataclasses import dataclass, replace
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.deployment_zones import DeploymentZone
from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    MissionPolicyDescriptor,
    ReserveDestructionTimingKind,
    RulesetDescriptor,
    reserve_destruction_timing_kind_from_token,
)
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusteringError
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    ModelPlacementRecord,
    ModelRemovalRecord,
    PlacementError,
    UnitPlacement,
    UnitPlacementPayload,
    battlefield_placement_kind_from_token,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.endpoint_placement import (
    objective_marker_endpoint_placement_violation,
    terrain_endpoint_placement_violation,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, SetupStep
from warhammer40k_core.engine.unit_abilities import unit_has_deep_strike
from warhammer40k_core.engine.unit_coherency import (
    UnitCoherencyResult,
    UnitCoherencyResultPayload,
    unit_placement_coherency_result,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model


class ReserveKind(StrEnum):
    RESERVES = "reserves"
    STRATEGIC_RESERVES = "strategic_reserves"
    DEEP_STRIKE = "deep_strike"


class ReserveOrigin(StrEnum):
    DECLARE_BATTLE_FORMATIONS = "declare_battle_formations"
    DEPLOY_ARMIES_OVERFLOW = "deploy_armies_overflow"
    AIRCRAFT_MANDATORY_RESERVE = "aircraft_mandatory_reserve"
    DURING_BATTLE_ABILITY = "during_battle_ability"
    DURING_BATTLE_STRATAGEM = "during_battle_stratagem"
    DURING_BATTLE_OTHER = "during_battle_other"


class ReserveStatus(StrEnum):
    IN_RESERVES = "in_reserves"
    ARRIVED = "arrived"
    DESTROYED = "destroyed"


class BattlefieldEdge(StrEnum):
    NORTH = "north"
    SOUTH = "south"
    EAST = "east"
    WEST = "west"


class ReservePostArrivalRestriction(StrEnum):
    NO_NORMAL_MOVE = "no_normal_move"
    NO_ADVANCE = "no_advance"
    NO_FALL_BACK = "no_fall_back"
    NO_REMAIN_STATIONARY = "no_remain_stationary"
    NO_RANGED_ATTACKS = "no_ranged_attacks"
    NO_CHARGE = "no_charge"


class ReservePlacementViolationCode(StrEnum):
    RESERVE_STATE_NOT_UNARRIVED = "reserve_state_not_unarrived"
    RESERVE_KIND_MISMATCH = "reserve_kind_mismatch"
    UNIT_PLACEMENT_DRIFT = "unit_placement_drift"
    RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN = "reserve_arrival_battle_round_forbidden"
    RESERVE_EMBARKED_CARGO_UNSUPPORTED = "reserve_embarked_cargo_unsupported"
    STRATEGIC_RESERVES_BATTLE_ROUND_1 = "strategic_reserves_battle_round_1"
    STRATEGIC_RESERVES_EDGE_DISTANCE = "strategic_reserves_edge_distance"
    STRATEGIC_RESERVES_ENEMY_DEPLOYMENT_ZONE = "strategic_reserves_enemy_deployment_zone"
    DEEP_STRIKE_KEYWORD_REQUIRED = "deep_strike_keyword_required"
    RESERVE_ENEMY_DISTANCE = "reserve_enemy_distance"
    RESERVE_ENEMY_ENGAGEMENT_RANGE = "reserve_enemy_engagement_range"
    BATTLEFIELD_EDGE_CROSSED = "battlefield_edge_crossed"
    MODEL_OVERLAP = "end_on_model_overlap"
    TERRAIN_ENDPOINT_ILLEGAL = "terrain_endpoint_illegal"
    OBJECTIVE_MARKER_ENDPOINT_OVERLAP = "objective_marker_endpoint_overlap"
    UNIT_COHERENCY_BROKEN = "unit_coherency_broken"
    LARGE_MODEL_EXCEPTION_UNNEEDED = "large_model_exception_unneeded"
    LARGE_MODEL_EXCEPTION_MODEL_CAN_FIT = "large_model_exception_model_can_fit"
    LARGE_MODEL_EXCEPTION_EDGE_NOT_QUALIFYING = "large_model_exception_edge_not_qualifying"
    LARGE_MODEL_EXCEPTION_EDGE_CONTACT_MISSING = "large_model_exception_edge_contact_missing"


LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS = (
    ReservePostArrivalRestriction.NO_NORMAL_MOVE,
    ReservePostArrivalRestriction.NO_ADVANCE,
    ReservePostArrivalRestriction.NO_FALL_BACK,
    ReservePostArrivalRestriction.NO_REMAIN_STATIONARY,
    ReservePostArrivalRestriction.NO_RANGED_ATTACKS,
    ReservePostArrivalRestriction.NO_CHARGE,
)

_DEFAULT_BATTLEFIELD_WIDTH_INCHES = 60.0
_DEFAULT_BATTLEFIELD_DEPTH_INCHES = 44.0
DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES = 8.0
_RESERVE_ENEMY_DISTANCE_INCHES = DEFAULT_RESERVE_ENEMY_DISTANCE_INCHES
_EPSILON = 1e-9
_RESERVES_RULE_ID = "reserves"
_STRATEGIC_RESERVES_RULE_ID = "strategic_reserves"
_DEEP_STRIKE_RULE_ID = "deep_strike"


class ReserveDestructionTimingPolicyPayload(TypedDict):
    timing_kind: str
    battle_round: int | None
    exclude_during_battle_strategic_reserves: bool
    only_declare_battle_formations: bool
    source_id: str


class ReserveStatePayload(TypedDict):
    player_id: str
    unit_instance_id: str
    reserve_origin: str
    reserve_kind: str
    source_rule_ids: list[str]
    points_contribution: int
    declared_during_step: str | None
    entered_reserves_battle_round: int | None
    entered_reserves_phase: str | None
    required_arrival_battle_round: int | None
    required_arrival_phase: str | None
    required_arrival_source_rule_id: str | None
    destruction_deadline_policy: ReserveDestructionTimingPolicyPayload
    status: str
    embarked_unit_instance_ids: list[str]
    arrived_battle_round: int | None
    arrived_phase: str | None
    destroyed_battle_round: int | None
    large_model_exception_used: bool
    post_arrival_restrictions: list[str]
    restriction_battle_round: int | None


class StrategicReserveDeclarationPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    reserve_origin: str
    declared_during_step: str
    source_rule_id: str
    unit_points: int
    embarked_unit_points: int
    points_limit: int
    has_fortification_keyword: bool
    embarked_unit_instance_ids: list[str]


class DeepStrikeSetupDeclarationPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    reserve_origin: str
    declared_during_step: str
    source_rule_id: str
    has_deep_strike_keyword: bool
    points_contribution: int


class AircraftReserveDeclarationPayload(TypedDict):
    player_id: str
    unit_instance_id: str
    reserve_origin: str
    declared_during_step: str
    source_rule_id: str
    unit_points: int
    points_limit: int
    has_aircraft_keyword: bool


class ReserveUnitPointValuePayload(TypedDict):
    unit_instance_id: str
    points: int
    source_id: str


class LargeModelReservePlacementExceptionPayload(TypedDict):
    model_instance_id: str
    battlefield_edge: str


class ReservePlacementViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_instance_id: str | None
    blocker_id: str | None
    battlefield_edge: str | None


class ReserveArrivalCandidatePayload(TypedDict):
    reserve_state: ReserveStatePayload
    battle_round: int
    placement_kind: str
    attempted_placement: UnitPlacementPayload
    qualifying_edges: list[str]
    large_model_exceptions: list[LargeModelReservePlacementExceptionPayload]


class ReinforcementPlacementPayload(TypedDict):
    candidate: ReserveArrivalCandidatePayload
    is_valid: bool
    violations: list[ReservePlacementViolationPayload]
    coherency_result: UnitCoherencyResultPayload
    transition_batch: dict[str, object] | None
    large_model_exception_used: bool
    post_arrival_restrictions: list[str]


class ReserveDestructionResultPayload(TypedDict):
    policy: ReserveDestructionTimingPolicyPayload
    battle_round: int
    end_of_battle: bool
    destroyed_unit_instance_ids: list[str]
    destroyed_model_instance_ids: list[str]
    transition_batch: dict[str, object]
    updated_reserve_states: list[ReserveStatePayload]


@dataclass(frozen=True, slots=True)
class ReserveDestructionTimingPolicy:
    timing_kind: ReserveDestructionTimingKind
    battle_round: int | None = None
    exclude_during_battle_strategic_reserves: bool = False
    only_declare_battle_formations: bool = False
    source_id: str = "core_rules_reserve_destruction"

    def __post_init__(self) -> None:
        timing = reserve_destruction_timing_kind_from_token(self.timing_kind)
        object.__setattr__(self, "timing_kind", timing)
        object.__setattr__(
            self,
            "battle_round",
            _validate_optional_positive_int(
                "ReserveDestructionTimingPolicy battle_round",
                self.battle_round,
            ),
        )
        object.__setattr__(
            self,
            "exclude_during_battle_strategic_reserves",
            _validate_bool(
                "ReserveDestructionTimingPolicy exclude_during_battle_strategic_reserves",
                self.exclude_during_battle_strategic_reserves,
            ),
        )
        object.__setattr__(
            self,
            "only_declare_battle_formations",
            _validate_bool(
                "ReserveDestructionTimingPolicy only_declare_battle_formations",
                self.only_declare_battle_formations,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ReserveDestructionTimingPolicy source_id", self.source_id),
        )
        if timing is ReserveDestructionTimingKind.END_OF_BATTLE and self.battle_round is not None:
            raise GameLifecycleError("END_OF_BATTLE reserve destruction must not set battle_round.")
        if (
            timing is ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N
            and self.battle_round is None
        ):
            raise GameLifecycleError(
                "END_OF_BATTLE_ROUND_N reserve destruction requires battle_round."
            )

    @classmethod
    def core_rules_default(cls) -> Self:
        return cls(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE,
            battle_round=None,
            exclude_during_battle_strategic_reserves=False,
            only_declare_battle_formations=False,
            source_id="core_rules_end_of_battle_reserves",
        )

    @classmethod
    def chapter_approved_2026_27(cls) -> Self:
        return cls(
            timing_kind=ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N,
            battle_round=3,
            exclude_during_battle_strategic_reserves=True,
            only_declare_battle_formations=True,
            source_id="chapter_approved_2026_27_reserves_restrictions",
        )

    @classmethod
    def from_mission_policy(cls, mission_policy: MissionPolicyDescriptor) -> Self:
        if type(mission_policy) is not MissionPolicyDescriptor:
            raise GameLifecycleError(
                "ReserveDestructionTimingPolicy requires a MissionPolicyDescriptor."
            )
        source_id = (
            "chapter_approved_2026_27_reserves_restrictions"
            if (
                mission_policy.reserve_destruction_timing
                is ReserveDestructionTimingKind.END_OF_BATTLE_ROUND_N
            )
            else "core_rules_end_of_battle_reserves"
        )
        return cls(
            timing_kind=mission_policy.reserve_destruction_timing,
            battle_round=mission_policy.reserve_destruction_battle_round,
            exclude_during_battle_strategic_reserves=(
                mission_policy.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            only_declare_battle_formations=(
                mission_policy.reserve_destruction_only_declare_battle_formations
            ),
            source_id=source_id,
        )

    def applies_at(self, *, battle_round: int, end_of_battle: bool) -> bool:
        requested_round = _validate_positive_int("battle_round", battle_round)
        if self.timing_kind is ReserveDestructionTimingKind.END_OF_BATTLE:
            return _validate_bool("end_of_battle", end_of_battle)
        return (
            not _validate_bool("end_of_battle", end_of_battle)
            and self.battle_round == requested_round
        )

    def applies_to_reserve_state(self, reserve_state: ReserveState) -> bool:
        if type(reserve_state) is not ReserveState:
            raise GameLifecycleError("reserve_state must be a ReserveState.")
        if reserve_state.status is not ReserveStatus.IN_RESERVES:
            return False
        if (
            self.exclude_during_battle_strategic_reserves
            and reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
            and reserve_state.reserve_origin
            in {
                ReserveOrigin.DURING_BATTLE_ABILITY,
                ReserveOrigin.DURING_BATTLE_STRATAGEM,
                ReserveOrigin.DURING_BATTLE_OTHER,
            }
        ):
            return False
        return not (
            self.only_declare_battle_formations
            and reserve_state.reserve_origin is not ReserveOrigin.DECLARE_BATTLE_FORMATIONS
        )

    def to_payload(self) -> ReserveDestructionTimingPolicyPayload:
        return {
            "timing_kind": self.timing_kind.value,
            "battle_round": self.battle_round,
            "exclude_during_battle_strategic_reserves": (
                self.exclude_during_battle_strategic_reserves
            ),
            "only_declare_battle_formations": self.only_declare_battle_formations,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ReserveDestructionTimingPolicyPayload) -> Self:
        return cls(
            timing_kind=reserve_destruction_timing_kind_from_token(payload["timing_kind"]),
            battle_round=payload["battle_round"],
            exclude_during_battle_strategic_reserves=payload[
                "exclude_during_battle_strategic_reserves"
            ],
            only_declare_battle_formations=payload["only_declare_battle_formations"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ReserveState:
    player_id: str
    unit_instance_id: str
    reserve_origin: ReserveOrigin
    reserve_kind: ReserveKind
    declared_during_step: str | None
    entered_reserves_battle_round: int | None
    entered_reserves_phase: str | None
    destruction_deadline_policy: ReserveDestructionTimingPolicy
    source_rule_ids: tuple[str, ...] = ()
    points_contribution: int = 0
    required_arrival_battle_round: int | None = None
    required_arrival_phase: str | None = None
    required_arrival_source_rule_id: str | None = None
    status: ReserveStatus = ReserveStatus.IN_RESERVES
    embarked_unit_instance_ids: tuple[str, ...] = ()
    arrived_battle_round: int | None = None
    arrived_phase: str | None = None
    destroyed_battle_round: int | None = None
    large_model_exception_used: bool = False
    post_arrival_restrictions: tuple[ReservePostArrivalRestriction, ...] = ()
    restriction_battle_round: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ReserveState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ReserveState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(self, "reserve_origin", reserve_origin_from_token(self.reserve_origin))
        object.__setattr__(self, "reserve_kind", reserve_kind_from_token(self.reserve_kind))
        source_rule_ids = (
            _default_source_rule_ids_for_reserve_kind(self.reserve_kind)
            if not self.source_rule_ids
            else self.source_rule_ids
        )
        object.__setattr__(
            self,
            "source_rule_ids",
            _validate_identifier_tuple(
                "ReserveState source_rule_ids",
                source_rule_ids,
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "points_contribution",
            _validate_non_negative_int(
                "ReserveState points_contribution",
                self.points_contribution,
            ),
        )
        object.__setattr__(
            self,
            "declared_during_step",
            _validate_optional_identifier(
                "ReserveState declared_during_step",
                self.declared_during_step,
            ),
        )
        object.__setattr__(
            self,
            "entered_reserves_battle_round",
            _validate_optional_positive_int(
                "ReserveState entered_reserves_battle_round",
                self.entered_reserves_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "entered_reserves_phase",
            _validate_optional_identifier(
                "ReserveState entered_reserves_phase",
                self.entered_reserves_phase,
            ),
        )
        object.__setattr__(
            self,
            "required_arrival_battle_round",
            _validate_optional_positive_int(
                "ReserveState required_arrival_battle_round",
                self.required_arrival_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "required_arrival_phase",
            _validate_optional_identifier(
                "ReserveState required_arrival_phase",
                self.required_arrival_phase,
            ),
        )
        object.__setattr__(
            self,
            "required_arrival_source_rule_id",
            _validate_optional_identifier(
                "ReserveState required_arrival_source_rule_id",
                self.required_arrival_source_rule_id,
            ),
        )
        if type(self.destruction_deadline_policy) is not ReserveDestructionTimingPolicy:
            raise GameLifecycleError("ReserveState destruction_deadline_policy must be a policy.")
        object.__setattr__(self, "status", reserve_status_from_token(self.status))
        object.__setattr__(
            self,
            "embarked_unit_instance_ids",
            _validate_identifier_tuple(
                "ReserveState embarked_unit_instance_ids",
                self.embarked_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "arrived_battle_round",
            _validate_optional_positive_int(
                "ReserveState arrived_battle_round",
                self.arrived_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "arrived_phase",
            _validate_optional_identifier("ReserveState arrived_phase", self.arrived_phase),
        )
        object.__setattr__(
            self,
            "destroyed_battle_round",
            _validate_optional_positive_int(
                "ReserveState destroyed_battle_round",
                self.destroyed_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "large_model_exception_used",
            _validate_bool(
                "ReserveState large_model_exception_used",
                self.large_model_exception_used,
            ),
        )
        restrictions = _validate_post_arrival_restriction_tuple(
            "ReserveState post_arrival_restrictions",
            self.post_arrival_restrictions,
        )
        object.__setattr__(self, "post_arrival_restrictions", restrictions)
        object.__setattr__(
            self,
            "restriction_battle_round",
            _validate_optional_positive_int(
                "ReserveState restriction_battle_round",
                self.restriction_battle_round,
            ),
        )
        self._validate_status_fields()

    @classmethod
    def declared_before_battle(
        cls,
        *,
        player_id: str,
        unit_instance_id: str,
        reserve_kind: ReserveKind,
        destruction_deadline_policy: ReserveDestructionTimingPolicy | None = None,
        embarked_unit_instance_ids: tuple[str, ...] = (),
        source_rule_ids: tuple[str, ...] | None = None,
        points_contribution: int = 0,
    ) -> Self:
        resolved_reserve_kind = reserve_kind_from_token(reserve_kind)
        return cls(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_origin=ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
            reserve_kind=resolved_reserve_kind,
            source_rule_ids=(
                _default_source_rule_ids_for_reserve_kind(resolved_reserve_kind)
                if source_rule_ids is None
                else source_rule_ids
            ),
            points_contribution=points_contribution,
            declared_during_step=SetupStep.DECLARE_BATTLE_FORMATIONS.value,
            entered_reserves_battle_round=None,
            entered_reserves_phase=None,
            required_arrival_battle_round=None,
            required_arrival_phase=None,
            required_arrival_source_rule_id=None,
            destruction_deadline_policy=(
                destruction_deadline_policy or ReserveDestructionTimingPolicy.core_rules_default()
            ),
            embarked_unit_instance_ids=embarked_unit_instance_ids,
        )

    @classmethod
    def entered_during_battle(
        cls,
        *,
        player_id: str,
        unit_instance_id: str,
        reserve_kind: ReserveKind,
        battle_round: int,
        phase: BattlePhase,
        reserve_origin: ReserveOrigin = ReserveOrigin.DURING_BATTLE_OTHER,
        destruction_deadline_policy: ReserveDestructionTimingPolicy | None = None,
        embarked_unit_instance_ids: tuple[str, ...] = (),
        source_rule_ids: tuple[str, ...] | None = None,
        points_contribution: int = 0,
        required_arrival_battle_round: int | None = None,
        required_arrival_phase: BattlePhase | str | None = None,
        required_arrival_source_rule_id: str | None = None,
    ) -> Self:
        resolved_reserve_kind = reserve_kind_from_token(reserve_kind)
        return cls(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            reserve_origin=reserve_origin,
            reserve_kind=resolved_reserve_kind,
            source_rule_ids=(
                _default_source_rule_ids_for_reserve_kind(resolved_reserve_kind)
                if source_rule_ids is None
                else source_rule_ids
            ),
            points_contribution=points_contribution,
            declared_during_step=None,
            entered_reserves_battle_round=_validate_positive_int("battle_round", battle_round),
            entered_reserves_phase=battle_phase_token(phase),
            required_arrival_battle_round=required_arrival_battle_round,
            required_arrival_phase=(
                None
                if required_arrival_phase is None
                else battle_phase_token(required_arrival_phase)
            ),
            required_arrival_source_rule_id=required_arrival_source_rule_id,
            destruction_deadline_policy=(
                destruction_deadline_policy or ReserveDestructionTimingPolicy.core_rules_default()
            ),
            embarked_unit_instance_ids=embarked_unit_instance_ids,
        )

    @property
    def is_unarrived(self) -> bool:
        return self.status is ReserveStatus.IN_RESERVES

    @property
    def has_required_arrival(self) -> bool:
        return self.required_arrival_battle_round is not None

    def arrival_is_required_at(self, *, battle_round: int, phase: BattlePhase) -> bool:
        if not self.has_required_arrival:
            return False
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_phase = battle_phase_token(phase)
        return (
            self.status is ReserveStatus.IN_RESERVES
            and self.required_arrival_battle_round == requested_round
            and self.required_arrival_phase == requested_phase
        )

    def arrival_is_eligible_at(self, *, battle_round: int, phase: BattlePhase) -> bool:
        if self.status is not ReserveStatus.IN_RESERVES:
            return False
        if not self.has_required_arrival:
            return True
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_phase = battle_phase_token(phase)
        return (
            self.required_arrival_battle_round == requested_round
            and self.required_arrival_phase == requested_phase
        )

    def mark_arrived(
        self,
        *,
        battle_round: int,
        phase: BattlePhase,
        large_model_exception_used: bool,
        post_arrival_restrictions: tuple[ReservePostArrivalRestriction, ...],
    ) -> Self:
        requested_round = _validate_positive_int("battle_round", battle_round)
        requested_phase = battle_phase_token(phase)
        restrictions = _validate_post_arrival_restriction_tuple(
            "post_arrival_restrictions",
            post_arrival_restrictions,
        )
        return replace(
            self,
            status=ReserveStatus.ARRIVED,
            arrived_battle_round=requested_round,
            arrived_phase=requested_phase,
            large_model_exception_used=large_model_exception_used,
            post_arrival_restrictions=restrictions,
            restriction_battle_round=(requested_round if restrictions else None),
        )

    def mark_destroyed(self, *, battle_round: int) -> Self:
        return replace(
            self,
            status=ReserveStatus.DESTROYED,
            destroyed_battle_round=_validate_positive_int("battle_round", battle_round),
            post_arrival_restrictions=(),
            restriction_battle_round=None,
        )

    def clear_expired_post_arrival_restrictions(
        self,
        *,
        player_id: str,
        battle_round: int,
    ) -> Self:
        requested_player_id = _validate_identifier("player_id", player_id)
        requested_round = _validate_positive_int("battle_round", battle_round)
        if (
            self.player_id != requested_player_id
            or self.restriction_battle_round != requested_round
        ):
            return self
        return replace(
            self,
            post_arrival_restrictions=(),
            restriction_battle_round=None,
        )

    def to_payload(self) -> ReserveStatePayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "reserve_origin": self.reserve_origin.value,
            "reserve_kind": self.reserve_kind.value,
            "source_rule_ids": list(self.source_rule_ids),
            "points_contribution": self.points_contribution,
            "declared_during_step": self.declared_during_step,
            "entered_reserves_battle_round": self.entered_reserves_battle_round,
            "entered_reserves_phase": self.entered_reserves_phase,
            "required_arrival_battle_round": self.required_arrival_battle_round,
            "required_arrival_phase": self.required_arrival_phase,
            "required_arrival_source_rule_id": self.required_arrival_source_rule_id,
            "destruction_deadline_policy": self.destruction_deadline_policy.to_payload(),
            "status": self.status.value,
            "embarked_unit_instance_ids": list(self.embarked_unit_instance_ids),
            "arrived_battle_round": self.arrived_battle_round,
            "arrived_phase": self.arrived_phase,
            "destroyed_battle_round": self.destroyed_battle_round,
            "large_model_exception_used": self.large_model_exception_used,
            "post_arrival_restrictions": [
                restriction.value for restriction in self.post_arrival_restrictions
            ],
            "restriction_battle_round": self.restriction_battle_round,
        }

    @classmethod
    def from_payload(cls, payload: ReserveStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            reserve_origin=reserve_origin_from_token(payload["reserve_origin"]),
            reserve_kind=reserve_kind_from_token(payload["reserve_kind"]),
            source_rule_ids=tuple(payload["source_rule_ids"]),
            points_contribution=payload["points_contribution"],
            declared_during_step=payload["declared_during_step"],
            entered_reserves_battle_round=payload["entered_reserves_battle_round"],
            entered_reserves_phase=payload["entered_reserves_phase"],
            required_arrival_battle_round=payload["required_arrival_battle_round"],
            required_arrival_phase=payload["required_arrival_phase"],
            required_arrival_source_rule_id=payload["required_arrival_source_rule_id"],
            destruction_deadline_policy=ReserveDestructionTimingPolicy.from_payload(
                payload["destruction_deadline_policy"]
            ),
            status=reserve_status_from_token(payload["status"]),
            embarked_unit_instance_ids=tuple(payload["embarked_unit_instance_ids"]),
            arrived_battle_round=payload["arrived_battle_round"],
            arrived_phase=payload["arrived_phase"],
            destroyed_battle_round=payload["destroyed_battle_round"],
            large_model_exception_used=payload["large_model_exception_used"],
            post_arrival_restrictions=tuple(
                reserve_post_arrival_restriction_from_token(restriction)
                for restriction in payload["post_arrival_restrictions"]
            ),
            restriction_battle_round=payload["restriction_battle_round"],
        )

    def _validate_status_fields(self) -> None:
        required_arrival_fields = (
            self.required_arrival_battle_round,
            self.required_arrival_phase,
            self.required_arrival_source_rule_id,
        )
        if any(value is None for value in required_arrival_fields) and any(
            value is not None for value in required_arrival_fields
        ):
            raise GameLifecycleError("ReserveState required arrival fields must be complete.")
        if self.status is ReserveStatus.IN_RESERVES:
            if self.arrived_battle_round is not None or self.arrived_phase is not None:
                raise GameLifecycleError("Unarrived ReserveState must not have arrival fields.")
            if self.destroyed_battle_round is not None:
                raise GameLifecycleError("Unarrived ReserveState must not have destruction fields.")
        if self.status is ReserveStatus.ARRIVED:
            if self.arrived_battle_round is None or self.arrived_phase is None:
                raise GameLifecycleError("Arrived ReserveState requires arrival fields.")
            if self.destroyed_battle_round is not None:
                raise GameLifecycleError("Arrived ReserveState must not have destruction fields.")
            if self.has_required_arrival and (
                self.arrived_battle_round != self.required_arrival_battle_round
                or self.arrived_phase != self.required_arrival_phase
            ):
                raise GameLifecycleError("Arrived ReserveState must satisfy required arrival.")
        if self.status is ReserveStatus.DESTROYED:
            if self.destroyed_battle_round is None:
                raise GameLifecycleError("Destroyed ReserveState requires destroyed_battle_round.")
            if self.post_arrival_restrictions:
                raise GameLifecycleError("Destroyed ReserveState must not keep restrictions.")
        if self.post_arrival_restrictions and self.restriction_battle_round is None:
            raise GameLifecycleError("ReserveState restrictions require restriction_battle_round.")
        if (
            self.large_model_exception_used
            and self.post_arrival_restrictions
            and set(self.post_arrival_restrictions)
            != set(LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS)
        ):
            raise GameLifecycleError(
                "Large-model ReserveState must record all post-arrival restrictions."
            )


@dataclass(frozen=True, slots=True)
class StrategicReserveDeclaration:
    player_id: str
    unit_instance_id: str
    reserve_origin: ReserveOrigin
    declared_during_step: str
    unit_points: int
    embarked_unit_points: int
    points_limit: int
    source_rule_id: str = _STRATEGIC_RESERVES_RULE_ID
    has_fortification_keyword: bool = False
    embarked_unit_instance_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("StrategicReserveDeclaration player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "StrategicReserveDeclaration unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(self, "reserve_origin", reserve_origin_from_token(self.reserve_origin))
        object.__setattr__(
            self,
            "declared_during_step",
            _validate_identifier(
                "StrategicReserveDeclaration declared_during_step",
                self.declared_during_step,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier(
                "StrategicReserveDeclaration source_rule_id",
                self.source_rule_id,
            ),
        )
        object.__setattr__(
            self,
            "unit_points",
            _validate_non_negative_int("StrategicReserveDeclaration unit_points", self.unit_points),
        )
        object.__setattr__(
            self,
            "embarked_unit_points",
            _validate_non_negative_int(
                "StrategicReserveDeclaration embarked_unit_points",
                self.embarked_unit_points,
            ),
        )
        object.__setattr__(
            self,
            "points_limit",
            _validate_non_negative_int(
                "StrategicReserveDeclaration points_limit",
                self.points_limit,
            ),
        )
        object.__setattr__(
            self,
            "has_fortification_keyword",
            _validate_bool(
                "StrategicReserveDeclaration has_fortification_keyword",
                self.has_fortification_keyword,
            ),
        )
        object.__setattr__(
            self,
            "embarked_unit_instance_ids",
            _validate_identifier_tuple(
                "StrategicReserveDeclaration embarked_unit_instance_ids",
                self.embarked_unit_instance_ids,
            ),
        )
        if self.has_fortification_keyword:
            raise GameLifecycleError("Strategic Reserves cannot include FORTIFICATIONS.")
        if self.unit_points + self.embarked_unit_points > self.points_limit:
            raise GameLifecycleError("Strategic Reserves declaration exceeds points limit.")

    @classmethod
    def for_unit(
        cls,
        *,
        unit: UnitInstance,
        player_id: str,
        unit_points: int,
        embarked_unit_points: int,
        points_limit: int,
        reserve_origin: ReserveOrigin = ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        declared_during_step: str = "declare_battle_formations",
        source_rule_id: str = _STRATEGIC_RESERVES_RULE_ID,
        embarked_unit_instance_ids: tuple[str, ...] = (),
    ) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("StrategicReserveDeclaration requires a UnitInstance.")
        return cls(
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            reserve_origin=reserve_origin,
            declared_during_step=declared_during_step,
            source_rule_id=source_rule_id,
            unit_points=unit_points,
            embarked_unit_points=embarked_unit_points,
            points_limit=points_limit,
            has_fortification_keyword=_unit_has_keyword(unit, "FORTIFICATION"),
            embarked_unit_instance_ids=embarked_unit_instance_ids,
        )

    def to_reserve_state(
        self,
        *,
        destruction_deadline_policy: ReserveDestructionTimingPolicy,
    ) -> ReserveState:
        return ReserveState(
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            reserve_origin=self.reserve_origin,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            source_rule_ids=(self.source_rule_id,),
            points_contribution=self.unit_points + self.embarked_unit_points,
            declared_during_step=self.declared_during_step,
            entered_reserves_battle_round=None,
            entered_reserves_phase=None,
            destruction_deadline_policy=destruction_deadline_policy,
            embarked_unit_instance_ids=self.embarked_unit_instance_ids,
        )

    def to_payload(self) -> StrategicReserveDeclarationPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "reserve_origin": self.reserve_origin.value,
            "declared_during_step": self.declared_during_step,
            "source_rule_id": self.source_rule_id,
            "unit_points": self.unit_points,
            "embarked_unit_points": self.embarked_unit_points,
            "points_limit": self.points_limit,
            "has_fortification_keyword": self.has_fortification_keyword,
            "embarked_unit_instance_ids": list(self.embarked_unit_instance_ids),
        }

    @classmethod
    def from_payload(cls, payload: StrategicReserveDeclarationPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            reserve_origin=reserve_origin_from_token(payload["reserve_origin"]),
            declared_during_step=payload["declared_during_step"],
            source_rule_id=payload["source_rule_id"],
            unit_points=payload["unit_points"],
            embarked_unit_points=payload["embarked_unit_points"],
            points_limit=payload["points_limit"],
            has_fortification_keyword=payload["has_fortification_keyword"],
            embarked_unit_instance_ids=tuple(payload["embarked_unit_instance_ids"]),
        )


@dataclass(frozen=True, slots=True)
class DeepStrikeSetupDeclaration:
    player_id: str
    unit_instance_id: str
    reserve_origin: ReserveOrigin
    declared_during_step: str
    source_rule_id: str
    has_deep_strike_keyword: bool
    points_contribution: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("DeepStrikeSetupDeclaration player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "DeepStrikeSetupDeclaration unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(self, "reserve_origin", reserve_origin_from_token(self.reserve_origin))
        object.__setattr__(
            self,
            "declared_during_step",
            _validate_identifier(
                "DeepStrikeSetupDeclaration declared_during_step",
                self.declared_during_step,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DeepStrikeSetupDeclaration source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "has_deep_strike_keyword",
            _validate_bool(
                "DeepStrikeSetupDeclaration has_deep_strike_keyword",
                self.has_deep_strike_keyword,
            ),
        )
        object.__setattr__(
            self,
            "points_contribution",
            _validate_non_negative_int(
                "DeepStrikeSetupDeclaration points_contribution",
                self.points_contribution,
            ),
        )
        if not self.has_deep_strike_keyword:
            raise GameLifecycleError(
                "Deep Strike declaration requires every model to have Deep Strike."
            )

    @classmethod
    def for_unit(
        cls,
        *,
        unit: UnitInstance,
        player_id: str,
        points_contribution: int = 0,
        reserve_origin: ReserveOrigin = ReserveOrigin.DECLARE_BATTLE_FORMATIONS,
        declared_during_step: str = "declare_battle_formations",
        source_rule_id: str = _DEEP_STRIKE_RULE_ID,
    ) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("DeepStrikeSetupDeclaration requires a UnitInstance.")
        return cls(
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            reserve_origin=reserve_origin,
            declared_during_step=declared_during_step,
            source_rule_id=source_rule_id,
            has_deep_strike_keyword=_unit_has_deep_strike(unit),
            points_contribution=points_contribution,
        )

    def to_reserve_state(
        self,
        *,
        destruction_deadline_policy: ReserveDestructionTimingPolicy,
    ) -> ReserveState:
        return ReserveState(
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            reserve_origin=self.reserve_origin,
            reserve_kind=ReserveKind.DEEP_STRIKE,
            source_rule_ids=(self.source_rule_id,),
            points_contribution=self.points_contribution,
            declared_during_step=self.declared_during_step,
            entered_reserves_battle_round=None,
            entered_reserves_phase=None,
            destruction_deadline_policy=destruction_deadline_policy,
        )

    def to_payload(self) -> DeepStrikeSetupDeclarationPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "reserve_origin": self.reserve_origin.value,
            "declared_during_step": self.declared_during_step,
            "source_rule_id": self.source_rule_id,
            "has_deep_strike_keyword": self.has_deep_strike_keyword,
            "points_contribution": self.points_contribution,
        }

    @classmethod
    def from_payload(cls, payload: DeepStrikeSetupDeclarationPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            reserve_origin=reserve_origin_from_token(payload["reserve_origin"]),
            declared_during_step=payload["declared_during_step"],
            source_rule_id=payload["source_rule_id"],
            has_deep_strike_keyword=payload["has_deep_strike_keyword"],
            points_contribution=payload["points_contribution"],
        )


@dataclass(frozen=True, slots=True)
class AircraftReserveDeclaration:
    player_id: str
    unit_instance_id: str
    reserve_origin: ReserveOrigin
    declared_during_step: str
    source_rule_id: str
    unit_points: int
    points_limit: int
    has_aircraft_keyword: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("AircraftReserveDeclaration player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier(
                "AircraftReserveDeclaration unit_instance_id",
                self.unit_instance_id,
            ),
        )
        object.__setattr__(self, "reserve_origin", reserve_origin_from_token(self.reserve_origin))
        object.__setattr__(
            self,
            "declared_during_step",
            _validate_identifier(
                "AircraftReserveDeclaration declared_during_step",
                self.declared_during_step,
            ),
        )
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("AircraftReserveDeclaration source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "unit_points",
            _validate_non_negative_int("AircraftReserveDeclaration unit_points", self.unit_points),
        )
        object.__setattr__(
            self,
            "points_limit",
            _validate_non_negative_int(
                "AircraftReserveDeclaration points_limit",
                self.points_limit,
            ),
        )
        object.__setattr__(
            self,
            "has_aircraft_keyword",
            _validate_bool(
                "AircraftReserveDeclaration has_aircraft_keyword",
                self.has_aircraft_keyword,
            ),
        )
        if not self.has_aircraft_keyword:
            raise GameLifecycleError("Aircraft reserve declaration requires AIRCRAFT.")
        if self.unit_points > self.points_limit:
            raise GameLifecycleError("Aircraft reserve declaration exceeds points limit.")

    @classmethod
    def for_unit(
        cls,
        *,
        unit: UnitInstance,
        player_id: str,
        unit_points: int,
        points_limit: int,
        reserve_origin: ReserveOrigin = ReserveOrigin.AIRCRAFT_MANDATORY_RESERVE,
        declared_during_step: str = "declare_battle_formations",
        source_rule_id: str = "aircraft_mandatory_reserve",
    ) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("AircraftReserveDeclaration requires a UnitInstance.")
        return cls(
            player_id=player_id,
            unit_instance_id=unit.unit_instance_id,
            reserve_origin=reserve_origin,
            declared_during_step=declared_during_step,
            source_rule_id=source_rule_id,
            unit_points=unit_points,
            points_limit=points_limit,
            has_aircraft_keyword=_unit_has_keyword(unit, "AIRCRAFT"),
        )

    def to_reserve_state(
        self,
        *,
        destruction_deadline_policy: ReserveDestructionTimingPolicy,
    ) -> ReserveState:
        return ReserveState(
            player_id=self.player_id,
            unit_instance_id=self.unit_instance_id,
            reserve_origin=self.reserve_origin,
            reserve_kind=ReserveKind.STRATEGIC_RESERVES,
            source_rule_ids=(self.source_rule_id,),
            points_contribution=self.unit_points,
            declared_during_step=self.declared_during_step,
            entered_reserves_battle_round=None,
            entered_reserves_phase=None,
            destruction_deadline_policy=destruction_deadline_policy,
        )

    def to_payload(self) -> AircraftReserveDeclarationPayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "reserve_origin": self.reserve_origin.value,
            "declared_during_step": self.declared_during_step,
            "source_rule_id": self.source_rule_id,
            "unit_points": self.unit_points,
            "points_limit": self.points_limit,
            "has_aircraft_keyword": self.has_aircraft_keyword,
        }

    @classmethod
    def from_payload(cls, payload: AircraftReserveDeclarationPayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            reserve_origin=reserve_origin_from_token(payload["reserve_origin"]),
            declared_during_step=payload["declared_during_step"],
            source_rule_id=payload["source_rule_id"],
            unit_points=payload["unit_points"],
            points_limit=payload["points_limit"],
            has_aircraft_keyword=payload["has_aircraft_keyword"],
        )


@dataclass(frozen=True, slots=True)
class ReserveUnitPointValue:
    unit_instance_id: str
    points: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("ReserveUnitPointValue unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "points",
            _validate_non_negative_int("ReserveUnitPointValue points", self.points),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ReserveUnitPointValue source_id", self.source_id),
        )

    def to_payload(self) -> ReserveUnitPointValuePayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "points": self.points,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ReserveUnitPointValuePayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            points=payload["points"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class LargeModelReservePlacementException:
    model_instance_id: str
    battlefield_edge: BattlefieldEdge

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "LargeModelReservePlacementException model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_edge",
            battlefield_edge_from_token(self.battlefield_edge),
        )

    def to_payload(self) -> LargeModelReservePlacementExceptionPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "battlefield_edge": self.battlefield_edge.value,
        }

    @classmethod
    def from_payload(cls, payload: LargeModelReservePlacementExceptionPayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            battlefield_edge=battlefield_edge_from_token(payload["battlefield_edge"]),
        )


@dataclass(frozen=True, slots=True)
class StrategicReserveRule:
    edge_distance_inches: float = 6.0
    enemy_horizontal_distance_inches: float = _RESERVE_ENEMY_DISTANCE_INCHES
    earliest_arrival_battle_round: int = 2
    ignores_mission_arrival_round_blocks: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "edge_distance_inches",
            _validate_positive_number(
                "StrategicReserveRule edge_distance_inches",
                self.edge_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "enemy_horizontal_distance_inches",
            _validate_positive_number(
                "StrategicReserveRule enemy_horizontal_distance_inches",
                self.enemy_horizontal_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "earliest_arrival_battle_round",
            _validate_positive_int(
                "StrategicReserveRule earliest_arrival_battle_round",
                self.earliest_arrival_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "ignores_mission_arrival_round_blocks",
            _validate_bool(
                "StrategicReserveRule ignores_mission_arrival_round_blocks",
                self.ignores_mission_arrival_round_blocks,
            ),
        )

    def qualifying_edges_for_battle_round(self, battle_round: int) -> tuple[BattlefieldEdge, ...]:
        requested_round = _validate_positive_int("battle_round", battle_round)
        if requested_round < self.earliest_arrival_battle_round:
            return ()
        return (
            BattlefieldEdge.NORTH,
            BattlefieldEdge.SOUTH,
            BattlefieldEdge.EAST,
            BattlefieldEdge.WEST,
        )


@dataclass(frozen=True, slots=True)
class ReservePlacementViolation:
    violation_code: ReservePlacementViolationCode
    message: str
    model_instance_id: str | None = None
    blocker_id: str | None = None
    battlefield_edge: BattlefieldEdge | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            reserve_placement_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("ReservePlacementViolation message", self.message),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "ReservePlacementViolation model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "blocker_id",
            _validate_optional_identifier("ReservePlacementViolation blocker_id", self.blocker_id),
        )
        if self.battlefield_edge is not None:
            object.__setattr__(
                self,
                "battlefield_edge",
                battlefield_edge_from_token(self.battlefield_edge),
            )

    def to_payload(self) -> ReservePlacementViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "model_instance_id": self.model_instance_id,
            "blocker_id": self.blocker_id,
            "battlefield_edge": (
                None if self.battlefield_edge is None else self.battlefield_edge.value
            ),
        }

    @classmethod
    def from_payload(cls, payload: ReservePlacementViolationPayload) -> Self:
        edge = payload["battlefield_edge"]
        return cls(
            violation_code=reserve_placement_violation_code_from_token(payload["violation_code"]),
            message=payload["message"],
            model_instance_id=payload["model_instance_id"],
            blocker_id=payload["blocker_id"],
            battlefield_edge=None if edge is None else battlefield_edge_from_token(edge),
        )


@dataclass(frozen=True, slots=True)
class ReserveArrivalCandidate:
    reserve_state: ReserveState
    battle_round: int
    placement_kind: BattlefieldPlacementKind
    attempted_placement: UnitPlacement
    qualifying_edges: tuple[BattlefieldEdge, ...]
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...] = ()

    def __post_init__(self) -> None:
        if type(self.reserve_state) is not ReserveState:
            raise GameLifecycleError("ReserveArrivalCandidate reserve_state must be ReserveState.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ReserveArrivalCandidate battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "placement_kind",
            battlefield_placement_kind_from_token(self.placement_kind),
        )
        if type(self.attempted_placement) is not UnitPlacement:
            raise GameLifecycleError(
                "ReserveArrivalCandidate attempted_placement must be UnitPlacement."
            )
        if self.attempted_placement.unit_instance_id != self.reserve_state.unit_instance_id:
            raise GameLifecycleError("ReserveArrivalCandidate placement unit drift.")
        if self.attempted_placement.player_id != self.reserve_state.player_id:
            raise GameLifecycleError("ReserveArrivalCandidate placement player drift.")
        object.__setattr__(
            self,
            "qualifying_edges",
            _validate_battlefield_edge_tuple(
                "ReserveArrivalCandidate qualifying_edges",
                self.qualifying_edges,
            ),
        )
        object.__setattr__(
            self,
            "large_model_exceptions",
            _validate_large_model_exception_tuple(
                "ReserveArrivalCandidate large_model_exceptions",
                self.large_model_exceptions,
            ),
        )

    def to_payload(self) -> ReserveArrivalCandidatePayload:
        return {
            "reserve_state": self.reserve_state.to_payload(),
            "battle_round": self.battle_round,
            "placement_kind": self.placement_kind.value,
            "attempted_placement": self.attempted_placement.to_payload(),
            "qualifying_edges": [edge.value for edge in self.qualifying_edges],
            "large_model_exceptions": [
                exception.to_payload() for exception in self.large_model_exceptions
            ],
        }

    @classmethod
    def from_payload(cls, payload: ReserveArrivalCandidatePayload) -> Self:
        return cls(
            reserve_state=ReserveState.from_payload(payload["reserve_state"]),
            battle_round=payload["battle_round"],
            placement_kind=battlefield_placement_kind_from_token(payload["placement_kind"]),
            attempted_placement=UnitPlacement.from_payload(payload["attempted_placement"]),
            qualifying_edges=tuple(
                battlefield_edge_from_token(edge) for edge in payload["qualifying_edges"]
            ),
            large_model_exceptions=tuple(
                LargeModelReservePlacementException.from_payload(exception)
                for exception in payload["large_model_exceptions"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ReinforcementPlacement:
    candidate: ReserveArrivalCandidate
    violations: tuple[ReservePlacementViolation, ...]
    coherency_result: UnitCoherencyResult
    transition_batch: BattlefieldTransitionBatch | None
    large_model_exception_used: bool
    post_arrival_restrictions: tuple[ReservePostArrivalRestriction, ...]

    def __post_init__(self) -> None:
        if type(self.candidate) is not ReserveArrivalCandidate:
            raise GameLifecycleError("ReinforcementPlacement candidate must be a candidate.")
        object.__setattr__(
            self,
            "violations",
            _validate_reserve_placement_violation_tuple(
                "ReinforcementPlacement violations",
                self.violations,
            ),
        )
        if type(self.coherency_result) is not UnitCoherencyResult:
            raise GameLifecycleError(
                "ReinforcementPlacement coherency_result must be UnitCoherencyResult."
            )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "ReinforcementPlacement transition_batch must be BattlefieldTransitionBatch."
            )
        object.__setattr__(
            self,
            "large_model_exception_used",
            _validate_bool(
                "ReinforcementPlacement large_model_exception_used",
                self.large_model_exception_used,
            ),
        )
        restrictions = _validate_post_arrival_restriction_tuple(
            "ReinforcementPlacement post_arrival_restrictions",
            self.post_arrival_restrictions,
        )
        object.__setattr__(self, "post_arrival_restrictions", restrictions)
        if self.violations and self.transition_batch is not None:
            raise GameLifecycleError("Invalid ReinforcementPlacement cannot have transitions.")
        if not self.violations and self.transition_batch is None:
            raise GameLifecycleError("Valid ReinforcementPlacement requires transitions.")
        if self.large_model_exception_used and set(restrictions) != set(
            LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS
        ):
            raise GameLifecycleError(
                "Large-model ReinforcementPlacement must apply all turn restrictions."
            )
        if not self.large_model_exception_used and restrictions:
            raise GameLifecycleError(
                "ReinforcementPlacement restrictions require large_model_exception_used."
            )

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def arrived_reserve_state(self) -> ReserveState:
        if not self.is_valid:
            raise GameLifecycleError("Invalid ReinforcementPlacement cannot mark arrival.")
        return self.candidate.reserve_state.mark_arrived(
            battle_round=self.candidate.battle_round,
            phase=BattlePhase.MOVEMENT,
            large_model_exception_used=self.large_model_exception_used,
            post_arrival_restrictions=self.post_arrival_restrictions,
        )

    def to_payload(self) -> ReinforcementPlacementPayload:
        return {
            "candidate": self.candidate.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "coherency_result": self.coherency_result.to_payload(),
            "transition_batch": None
            if self.transition_batch is None
            else cast(dict[str, object], self.transition_batch.to_payload()),
            "large_model_exception_used": self.large_model_exception_used,
            "post_arrival_restrictions": [
                restriction.value for restriction in self.post_arrival_restrictions
            ],
        }


@dataclass(frozen=True, slots=True)
class ReserveDestructionResult:
    policy: ReserveDestructionTimingPolicy
    battle_round: int
    end_of_battle: bool
    destroyed_unit_instance_ids: tuple[str, ...]
    destroyed_model_instance_ids: tuple[str, ...]
    transition_batch: BattlefieldTransitionBatch
    updated_reserve_states: tuple[ReserveState, ...]

    def __post_init__(self) -> None:
        if type(self.policy) is not ReserveDestructionTimingPolicy:
            raise GameLifecycleError("ReserveDestructionResult policy must be a policy.")
        object.__setattr__(
            self,
            "battle_round",
            _validate_positive_int("ReserveDestructionResult battle_round", self.battle_round),
        )
        object.__setattr__(
            self,
            "end_of_battle",
            _validate_bool("ReserveDestructionResult end_of_battle", self.end_of_battle),
        )
        object.__setattr__(
            self,
            "destroyed_unit_instance_ids",
            _validate_identifier_tuple(
                "ReserveDestructionResult destroyed_unit_instance_ids",
                self.destroyed_unit_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "destroyed_model_instance_ids",
            _validate_identifier_tuple(
                "ReserveDestructionResult destroyed_model_instance_ids",
                self.destroyed_model_instance_ids,
            ),
        )
        if type(self.transition_batch) is not BattlefieldTransitionBatch:
            raise GameLifecycleError(
                "ReserveDestructionResult transition_batch must be BattlefieldTransitionBatch."
            )
        object.__setattr__(
            self,
            "updated_reserve_states",
            _validate_reserve_state_tuple(
                "ReserveDestructionResult updated_reserve_states",
                self.updated_reserve_states,
            ),
        )

    def to_payload(self) -> ReserveDestructionResultPayload:
        return {
            "policy": self.policy.to_payload(),
            "battle_round": self.battle_round,
            "end_of_battle": self.end_of_battle,
            "destroyed_unit_instance_ids": list(self.destroyed_unit_instance_ids),
            "destroyed_model_instance_ids": list(self.destroyed_model_instance_ids),
            "transition_batch": cast(dict[str, object], self.transition_batch.to_payload()),
            "updated_reserve_states": [state.to_payload() for state in self.updated_reserve_states],
        }


def resolve_reserve_arrival(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    reserve_state: ReserveState,
    attempted_placement: UnitPlacement,
    battle_round: int,
    placement_kind: BattlefieldPlacementKind,
    battlefield_width_inches: float = _DEFAULT_BATTLEFIELD_WIDTH_INCHES,
    battlefield_depth_inches: float = _DEFAULT_BATTLEFIELD_DEPTH_INCHES,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    objective_markers: tuple[ObjectiveMarker, ...] = (),
    enemy_deployment_zones: tuple[DeploymentZone, ...] = (),
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...] = (),
    strategic_reserve_rule: StrategicReserveRule | None = None,
    deep_strike_enemy_horizontal_distance_inches: float | None = None,
) -> ReinforcementPlacement:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("resolve_reserve_arrival scenario must be a scenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("resolve_reserve_arrival requires a RulesetDescriptor.")
    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("resolve_reserve_arrival reserve_state must be ReserveState.")
    if type(attempted_placement) is not UnitPlacement:
        raise GameLifecycleError(
            "resolve_reserve_arrival attempted_placement must be UnitPlacement."
        )
    placement_kind = battlefield_placement_kind_from_token(placement_kind)
    requested_round = _validate_positive_int("battle_round", battle_round)
    width = _validate_positive_number("battlefield_width_inches", battlefield_width_inches)
    depth = _validate_positive_number("battlefield_depth_inches", battlefield_depth_inches)
    features = _validate_terrain_feature_tuple("terrain_features", terrain_features)
    markers = _validate_objective_marker_tuple("objective_markers", objective_markers)
    deployment_zones = _validate_deployment_zone_tuple(
        "enemy_deployment_zones",
        enemy_deployment_zones,
    )
    exceptions = _validate_large_model_exception_tuple(
        "large_model_exceptions",
        large_model_exceptions,
    )
    strategic_rule = strategic_reserve_rule or StrategicReserveRule()
    if type(strategic_rule) is not StrategicReserveRule:
        raise GameLifecycleError("strategic_reserve_rule must be a StrategicReserveRule.")
    deep_strike_enemy_distance = (
        None
        if deep_strike_enemy_horizontal_distance_inches is None
        else _validate_positive_number(
            "deep_strike_enemy_horizontal_distance_inches",
            deep_strike_enemy_horizontal_distance_inches,
        )
    )
    if (
        deep_strike_enemy_distance is not None
        and placement_kind is not BattlefieldPlacementKind.DEEP_STRIKE
    ):
        raise GameLifecycleError(
            "deep_strike_enemy_horizontal_distance_inches only applies to Deep Strike placement."
        )

    unit = _unit_for_reserve_state(scenario=scenario, reserve_state=reserve_state)
    qualifying_edges = strategic_rule.qualifying_edges_for_battle_round(requested_round)
    candidate = ReserveArrivalCandidate(
        reserve_state=reserve_state,
        battle_round=requested_round,
        placement_kind=placement_kind,
        attempted_placement=attempted_placement,
        qualifying_edges=qualifying_edges,
        large_model_exceptions=exceptions,
    )
    violations: list[ReservePlacementViolation] = []
    _append_reserve_state_violations(
        violations=violations,
        reserve_state=reserve_state,
        unit=unit,
        placement_kind=placement_kind,
        battle_round=requested_round,
        mission_policy=ruleset_descriptor.mission_policy,
        strategic_reserve_rule=strategic_rule,
    )
    _append_unit_placement_drift_violations(
        violations=violations,
        unit=unit,
        attempted_placement=attempted_placement,
    )

    models = _geometry_models_for_unit_placement(
        scenario=scenario,
        unit_placement=attempted_placement,
    )
    if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES:
        _append_strategic_reserves_edge_violations(
            violations=violations,
            models=models,
            battle_round=requested_round,
            battlefield_width_inches=width,
            battlefield_depth_inches=depth,
            strategic_reserve_rule=strategic_rule,
            qualifying_edges=qualifying_edges,
            large_model_exceptions=exceptions,
        )
        if requested_round == 2:
            _append_enemy_deployment_zone_violations(
                violations=violations,
                models=models,
                enemy_deployment_zones=deployment_zones,
            )
    _append_common_reserve_placement_violations(
        violations=violations,
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit=unit,
        attempted_placement=attempted_placement,
        models=models,
        battlefield_width_inches=width,
        battlefield_depth_inches=depth,
        terrain_features=features,
        objective_markers=markers,
        enemy_distance_inches=(
            strategic_rule.enemy_horizontal_distance_inches
            if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES
            else deep_strike_enemy_distance
            if deep_strike_enemy_distance is not None
            else _RESERVE_ENEMY_DISTANCE_INCHES
        ),
    )
    coherency_result = unit_placement_coherency_result(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        unit_placement=attempted_placement,
    )
    if not coherency_result.is_coherent:
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.UNIT_COHERENCY_BROKEN,
                message="Reserve placement violates unit coherency.",
            )
        )

    exception_model_ids = {exception.model_instance_id for exception in exceptions}
    large_model_exception_used = bool(exception_model_ids)
    restrictions = LARGE_MODEL_STRATEGIC_RESERVE_RESTRICTIONS if large_model_exception_used else ()
    transition_batch = None
    if not violations:
        transition_batch = _reserve_arrival_transition_batch(
            attempted_placement=attempted_placement,
            placement_kind=placement_kind,
            source_rule_id=_source_rule_id_for_placement_kind(placement_kind),
        )
    return ReinforcementPlacement(
        candidate=candidate,
        violations=tuple(violations),
        coherency_result=coherency_result,
        transition_batch=transition_batch,
        large_model_exception_used=large_model_exception_used,
        post_arrival_restrictions=restrictions,
    )


def apply_reinforcement_placement_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    placement: ReinforcementPlacement,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(placement) is not ReinforcementPlacement:
        raise GameLifecycleError("placement must be a ReinforcementPlacement.")
    if not placement.is_valid:
        raise GameLifecycleError("Invalid reserve placement cannot mutate battlefield_state.")
    return battlefield_state.with_added_unit_placement(placement.candidate.attempted_placement)


def resolve_unarrived_reserve_destruction(
    *,
    reserve_states: tuple[ReserveState, ...],
    armies: tuple[ArmyDefinition, ...],
    battlefield_state: BattlefieldRuntimeState,
    policy: ReserveDestructionTimingPolicy,
    battle_round: int,
    end_of_battle: bool,
) -> ReserveDestructionResult:
    states = _validate_reserve_state_tuple("reserve_states", reserve_states)
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(policy) is not ReserveDestructionTimingPolicy:
        raise GameLifecycleError("policy must be a ReserveDestructionTimingPolicy.")
    requested_round = _validate_positive_int("battle_round", battle_round)
    end = _validate_bool("end_of_battle", end_of_battle)
    if not policy.applies_at(battle_round=requested_round, end_of_battle=end):
        return ReserveDestructionResult(
            policy=policy,
            battle_round=requested_round,
            end_of_battle=end,
            destroyed_unit_instance_ids=(),
            destroyed_model_instance_ids=(),
            transition_batch=BattlefieldTransitionBatch(),
            updated_reserve_states=states,
        )

    army_tuple = _validate_army_tuple("armies", armies)
    unit_by_id = _unit_by_id(army_tuple)
    destroyed_unit_ids: set[str] = set()
    destroyed_model_ids: set[str] = set()
    updated_states: list[ReserveState] = []
    for reserve_state in states:
        if not policy.applies_to_reserve_state(reserve_state):
            updated_states.append(reserve_state)
            continue
        impacted_unit_ids = (
            reserve_state.unit_instance_id,
            *reserve_state.embarked_unit_instance_ids,
        )
        for unit_id in impacted_unit_ids:
            unit = unit_by_id.get(unit_id)
            if unit is None:
                raise GameLifecycleError("ReserveState references an unknown unit.")
            destroyed_unit_ids.add(unit_id)
            destroyed_model_ids.update(model.model_instance_id for model in unit.own_models)
        updated_states.append(reserve_state.mark_destroyed(battle_round=requested_round))

    transition_batch = BattlefieldTransitionBatch(
        removals=tuple(
            ModelRemovalRecord(
                model_instance_id=model_id,
                removal_kind=BattlefieldRemovalKind.DESTROYED,
                source_phase=None,
                source_step=None,
                source_rule_id=policy.source_id,
                source_event_id=None,
                destination_id=None,
            )
            for model_id in sorted(destroyed_model_ids)
        )
    )
    return ReserveDestructionResult(
        policy=policy,
        battle_round=requested_round,
        end_of_battle=end,
        destroyed_unit_instance_ids=tuple(sorted(destroyed_unit_ids)),
        destroyed_model_instance_ids=tuple(sorted(destroyed_model_ids)),
        transition_batch=transition_batch,
        updated_reserve_states=tuple(updated_states),
    )


def apply_reserve_destruction_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    destruction: ReserveDestructionResult,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(destruction) is not ReserveDestructionResult:
        raise GameLifecycleError("destruction must be a ReserveDestructionResult.")
    destroyed_model_ids = set(destruction.destroyed_model_instance_ids)
    if not destroyed_model_ids:
        return battlefield_state
    placed_model_ids = set(battlefield_state.placed_model_ids())
    placed_destroyed_model_ids = tuple(sorted(destroyed_model_ids & placed_model_ids))
    updated_state = battlefield_state
    if placed_destroyed_model_ids:
        updated_state = updated_state.with_removed_models(placed_destroyed_model_ids)
    unplaced_destroyed_model_ids = tuple(
        sorted(destroyed_model_ids - set(updated_state.removed_model_ids))
    )
    if unplaced_destroyed_model_ids:
        updated_state = updated_state.with_unplaced_models_marked_removed(
            unplaced_destroyed_model_ids
        )
    return updated_state


def reserve_kind_from_token(token: object) -> ReserveKind:
    if type(token) is ReserveKind:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ReserveKind token must be a string.")
    try:
        return ReserveKind(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ReserveKind token: {token}.") from exc


def reserve_origin_from_token(token: object) -> ReserveOrigin:
    if type(token) is ReserveOrigin:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ReserveOrigin token must be a string.")
    try:
        return ReserveOrigin(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ReserveOrigin token: {token}.") from exc


def reserve_status_from_token(token: object) -> ReserveStatus:
    if type(token) is ReserveStatus:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ReserveStatus token must be a string.")
    try:
        return ReserveStatus(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported ReserveStatus token: {token}.") from exc


def battlefield_edge_from_token(token: object) -> BattlefieldEdge:
    if type(token) is BattlefieldEdge:
        return token
    if type(token) is not str:
        raise GameLifecycleError("BattlefieldEdge token must be a string.")
    try:
        return BattlefieldEdge(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported BattlefieldEdge token: {token}.") from exc


def reserve_post_arrival_restriction_from_token(token: object) -> ReservePostArrivalRestriction:
    if type(token) is ReservePostArrivalRestriction:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ReservePostArrivalRestriction token must be a string.")
    try:
        return ReservePostArrivalRestriction(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported ReservePostArrivalRestriction token: {token}."
        ) from exc


def reserve_placement_violation_code_from_token(token: object) -> ReservePlacementViolationCode:
    if type(token) is ReservePlacementViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ReservePlacementViolationCode token must be a string.")
    try:
        return ReservePlacementViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported ReservePlacementViolationCode token: {token}."
        ) from exc


def battle_phase_token(token: object) -> str:
    if type(token) is BattlePhase:
        return token.value
    return _validate_identifier("battle_phase", token)


def _default_source_rule_ids_for_reserve_kind(reserve_kind: ReserveKind) -> tuple[str, ...]:
    resolved_kind = reserve_kind_from_token(reserve_kind)
    if resolved_kind is ReserveKind.STRATEGIC_RESERVES:
        return (_STRATEGIC_RESERVES_RULE_ID,)
    if resolved_kind is ReserveKind.DEEP_STRIKE:
        return (_DEEP_STRIKE_RULE_ID,)
    return (_RESERVES_RULE_ID,)


def _append_reserve_state_violations(
    *,
    violations: list[ReservePlacementViolation],
    reserve_state: ReserveState,
    unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
    battle_round: int,
    mission_policy: MissionPolicyDescriptor,
    strategic_reserve_rule: StrategicReserveRule,
) -> None:
    if type(mission_policy) is not MissionPolicyDescriptor:
        raise GameLifecycleError("reserve arrival requires a MissionPolicyDescriptor.")
    if type(strategic_reserve_rule) is not StrategicReserveRule:
        raise GameLifecycleError("reserve arrival requires a StrategicReserveRule.")
    if (
        battle_round in mission_policy.reserves_arrival_blocked_battle_rounds
        and not strategic_reserve_rule.ignores_mission_arrival_round_blocks
        and not _reserve_arrival_block_exemption_applies(
            reserve_state=reserve_state,
            mission_policy=mission_policy,
        )
    ):
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN,
                message="Mission policy forbids this Reserve arrival battle round.",
            )
        )
    if not reserve_state.arrival_is_eligible_at(
        battle_round=battle_round,
        phase=BattlePhase.MOVEMENT,
    ):
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.RESERVE_ARRIVAL_BATTLE_ROUND_FORBIDDEN,
                message="Reserve arrival is required in a different battle round or phase.",
            )
        )
    if reserve_state.embarked_unit_instance_ids:
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.RESERVE_EMBARKED_CARGO_UNSUPPORTED,
                message="Reserve arrival with embarked cargo is unsupported before transports.",
            )
        )
    if reserve_state.status is not ReserveStatus.IN_RESERVES:
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.RESERVE_STATE_NOT_UNARRIVED,
                message="Reserve unit has already left Reserves.",
            )
        )
    if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES:
        if reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES:
            violations.append(
                ReservePlacementViolation(
                    violation_code=ReservePlacementViolationCode.RESERVE_KIND_MISMATCH,
                    message="Strategic Reserves placement requires Strategic Reserves state.",
                )
            )
        if battle_round < strategic_reserve_rule.earliest_arrival_battle_round:
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.STRATEGIC_RESERVES_BATTLE_ROUND_1
                    ),
                    message="Strategic Reserves cannot arrive in battle round 1.",
                )
            )
    if placement_kind is BattlefieldPlacementKind.DEEP_STRIKE and not _unit_has_deep_strike(unit):
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.DEEP_STRIKE_KEYWORD_REQUIRED,
                message="Deep Strike placement requires every model to have Deep Strike.",
            )
        )


def _reserve_arrival_block_exemption_applies(
    *,
    reserve_state: ReserveState,
    mission_policy: MissionPolicyDescriptor,
) -> bool:
    return (
        mission_policy.reserves_arrival_excludes_during_battle_strategic_reserves
        and reserve_state.reserve_kind is ReserveKind.STRATEGIC_RESERVES
        and reserve_state.reserve_origin
        in {
            ReserveOrigin.DURING_BATTLE_ABILITY,
            ReserveOrigin.DURING_BATTLE_STRATAGEM,
            ReserveOrigin.DURING_BATTLE_OTHER,
        }
    )


def _append_unit_placement_drift_violations(
    *,
    violations: list[ReservePlacementViolation],
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
) -> None:
    if attempted_placement.unit_instance_id != unit.unit_instance_id:
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Reserve placement unit_instance_id does not match unit.",
            )
        )
        return
    attempted_model_ids = tuple(
        sorted(placement.model_instance_id for placement in attempted_placement.model_placements)
    )
    expected_model_ids = tuple(sorted(model.model_instance_id for model in unit.own_models))
    if attempted_model_ids != expected_model_ids:
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.UNIT_PLACEMENT_DRIFT,
                message="Reserve placement must include every model in the unit.",
            )
        )


def _append_strategic_reserves_edge_violations(
    *,
    violations: list[ReservePlacementViolation],
    models: tuple[Model, ...],
    battle_round: int,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    strategic_reserve_rule: StrategicReserveRule,
    qualifying_edges: tuple[BattlefieldEdge, ...],
    large_model_exceptions: tuple[LargeModelReservePlacementException, ...],
) -> None:
    if battle_round == 1:
        return
    exception_by_model_id = {
        exception.model_instance_id: exception for exception in large_model_exceptions
    }
    model_ids = {model.model_id for model in models}
    for exception in large_model_exceptions:
        model = next(
            (
                candidate
                for candidate in models
                if candidate.model_id == exception.model_instance_id
            ),
            None,
        )
        if model is None:
            violations.append(
                ReservePlacementViolation(
                    violation_code=ReservePlacementViolationCode.UNIT_PLACEMENT_DRIFT,
                    message="Large-model exception references a model outside the placement.",
                    model_instance_id=exception.model_instance_id,
                )
            )
            continue
        if exception.battlefield_edge not in qualifying_edges:
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_EDGE_NOT_QUALIFYING
                    ),
                    message="Large-model exception edge is not a qualifying edge.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
        if _model_wholly_within_any_edge_band(
            model,
            edges=qualifying_edges,
            distance_inches=strategic_reserve_rule.edge_distance_inches,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_UNNEEDED,
                    message="Model already satisfies Strategic Reserves edge distance.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
        if _model_can_fit_within_edge_band(
            model,
            edge=exception.battlefield_edge,
            distance_inches=strategic_reserve_rule.edge_distance_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_MODEL_CAN_FIT
                    ),
                    message="Model can physically fit wholly within the required edge area.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
        if not _model_touches_edge(
            model,
            edge=exception.battlefield_edge,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.LARGE_MODEL_EXCEPTION_EDGE_CONTACT_MISSING
                    ),
                    message="Large-model exception requires touching the battlefield edge.",
                    model_instance_id=model.model_id,
                    battlefield_edge=exception.battlefield_edge,
                )
            )
    for model in models:
        if model.model_id in exception_by_model_id:
            continue
        if _model_wholly_within_any_edge_band(
            model,
            edges=qualifying_edges,
            distance_inches=strategic_reserve_rule.edge_distance_inches,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            continue
        violations.append(
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.STRATEGIC_RESERVES_EDGE_DISTANCE,
                message="Strategic Reserves model is not wholly within 6 inches of an edge.",
                model_instance_id=model.model_id,
            )
        )
    if set(exception_by_model_id).difference(model_ids):
        return


def _append_enemy_deployment_zone_violations(
    *,
    violations: list[ReservePlacementViolation],
    models: tuple[Model, ...],
    enemy_deployment_zones: tuple[DeploymentZone, ...],
) -> None:
    for model in models:
        for zone in enemy_deployment_zones:
            if shapely_backend.base_footprint_intersects_deployment_zone(
                model.base,
                model.pose,
                zone,
            ):
                violations.append(
                    ReservePlacementViolation(
                        violation_code=(
                            ReservePlacementViolationCode.STRATEGIC_RESERVES_ENEMY_DEPLOYMENT_ZONE
                        ),
                        message="Strategic Reserves cannot arrive in the enemy deployment zone.",
                        model_instance_id=model.model_id,
                        blocker_id=zone.deployment_zone_id,
                    )
                )


def _append_common_reserve_placement_violations(
    *,
    violations: list[ReservePlacementViolation],
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit: UnitInstance,
    attempted_placement: UnitPlacement,
    models: tuple[Model, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    objective_markers: tuple[ObjectiveMarker, ...],
    enemy_distance_inches: float,
) -> None:
    placed_models = _placed_geometry_models(scenario)
    own_model_ids = {model.model_id for model in models}
    blockers = tuple(model for model in placed_models if model.model_id not in own_model_ids)
    enemy_models = tuple(
        blocker
        for blocker in blockers
        if _model_owner_player_id(scenario=scenario, model_instance_id=blocker.model_id)
        != attempted_placement.player_id
    )
    for model in models:
        if not _model_is_within_battlefield(
            model,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        ):
            violations.append(
                ReservePlacementViolation(
                    violation_code=ReservePlacementViolationCode.BATTLEFIELD_EDGE_CROSSED,
                    message="Reserve placement crosses the battlefield edge.",
                    model_instance_id=model.model_id,
                )
            )
        for blocker in blockers:
            if _models_overlap_with_volume(model, blocker):
                violations.append(
                    ReservePlacementViolation(
                        violation_code=ReservePlacementViolationCode.MODEL_OVERLAP,
                        message="Reserve placement overlaps another model.",
                        model_instance_id=model.model_id,
                        blocker_id=blocker.model_id,
                    )
                )
        for enemy_model in enemy_models:
            if model.base_distance_to(enemy_model) <= enemy_distance_inches:
                violations.append(
                    ReservePlacementViolation(
                        violation_code=ReservePlacementViolationCode.RESERVE_ENEMY_DISTANCE,
                        message=(
                            "Reserve placement is within the configured reserve "
                            "enemy-distance limit."
                        ),
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
            if model.is_within_engagement_range(
                enemy_model,
                horizontal_inches=ruleset_descriptor.engagement_policy.horizontal_inches,
                vertical_inches=ruleset_descriptor.engagement_policy.vertical_inches,
            ):
                violations.append(
                    ReservePlacementViolation(
                        violation_code=(
                            ReservePlacementViolationCode.RESERVE_ENEMY_ENGAGEMENT_RANGE
                        ),
                        message="Reserve placement is within enemy Engagement Range.",
                        model_instance_id=model.model_id,
                        blocker_id=enemy_model.model_id,
                    )
                )
        terrain_violation = _terrain_endpoint_violation(
            model=model,
            unit=unit,
            ruleset_descriptor=ruleset_descriptor,
            terrain_features=terrain_features,
        )
        if terrain_violation is not None:
            violations.append(terrain_violation)
        objective_marker_violation = objective_marker_endpoint_placement_violation(
            model=model,
            objective_markers=objective_markers,
            violation_code=ReservePlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP.value,
            placement_label="Reserve placement",
        )
        if objective_marker_violation is not None:
            violations.append(
                ReservePlacementViolation(
                    violation_code=(
                        ReservePlacementViolationCode.OBJECTIVE_MARKER_ENDPOINT_OVERLAP
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
            ReservePlacementViolation(
                violation_code=ReservePlacementViolationCode.MODEL_OVERLAP,
                message="Reserve placement models overlap each other.",
                model_instance_id=first_id,
                blocker_id=second_id,
            )
        )


def _reserve_arrival_transition_batch(
    *,
    attempted_placement: UnitPlacement,
    placement_kind: BattlefieldPlacementKind,
    source_rule_id: str,
) -> BattlefieldTransitionBatch:
    return BattlefieldTransitionBatch(
        placements=tuple(
            ModelPlacementRecord(
                model_instance_id=model_placement.model_instance_id,
                placement_kind=placement_kind,
                pose=model_placement.pose,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_rule_id=source_rule_id,
                source_event_id=None,
            )
            for model_placement in attempted_placement.model_placements
        )
    )


def _source_rule_id_for_placement_kind(placement_kind: BattlefieldPlacementKind) -> str:
    if placement_kind is BattlefieldPlacementKind.STRATEGIC_RESERVES:
        return _STRATEGIC_RESERVES_RULE_ID
    if placement_kind is BattlefieldPlacementKind.DEEP_STRIKE:
        return _DEEP_STRIKE_RULE_ID
    return _RESERVES_RULE_ID


def _terrain_endpoint_violation(
    *,
    model: Model,
    unit: UnitInstance,
    ruleset_descriptor: RulesetDescriptor,
    terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> ReservePlacementViolation | None:
    violation = terrain_endpoint_placement_violation(
        model=model,
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        terrain_features=terrain_features,
        violation_code=ReservePlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value,
        placement_label="Reserve placement",
    )
    if violation is not None:
        return ReservePlacementViolation(
            violation_code=ReservePlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL,
            message=violation.message,
            model_instance_id=violation.model_instance_id,
            blocker_id=violation.blocker_id,
        )
    return None


def _model_wholly_within_any_edge_band(
    model: Model,
    *,
    edges: tuple[BattlefieldEdge, ...],
    distance_inches: float,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    return any(
        _model_wholly_within_edge_band(
            model,
            edge=edge,
            distance_inches=distance_inches,
            battlefield_width_inches=battlefield_width_inches,
            battlefield_depth_inches=battlefield_depth_inches,
        )
        for edge in edges
    )


def _model_wholly_within_edge_band(
    model: Model,
    *,
    edge: BattlefieldEdge,
    distance_inches: float,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    if edge is BattlefieldEdge.SOUTH:
        return min_y >= 0.0 and max_y <= distance_inches
    if edge is BattlefieldEdge.NORTH:
        return (
            min_y >= battlefield_depth_inches - distance_inches
            and max_y <= battlefield_depth_inches
        )
    if edge is BattlefieldEdge.WEST:
        return min_x >= 0.0 and max_x <= distance_inches
    if edge is BattlefieldEdge.EAST:
        return (
            min_x >= battlefield_width_inches - distance_inches
            and max_x <= battlefield_width_inches
        )
    raise GameLifecycleError("Unsupported BattlefieldEdge.")


def _model_can_fit_within_edge_band(
    model: Model,
    *,
    edge: BattlefieldEdge,
    distance_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    if edge in {BattlefieldEdge.NORTH, BattlefieldEdge.SOUTH}:
        return (max_y - min_y) <= distance_inches
    if edge in {BattlefieldEdge.EAST, BattlefieldEdge.WEST}:
        return (max_x - min_x) <= distance_inches
    raise GameLifecycleError("Unsupported BattlefieldEdge.")


def _model_touches_edge(
    model: Model,
    *,
    edge: BattlefieldEdge,
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = shapely_backend.footprint_for_base(model.base, model.pose).bounds
    if edge is BattlefieldEdge.SOUTH:
        return math.isclose(min_y, 0.0, rel_tol=0.0, abs_tol=_EPSILON)
    if edge is BattlefieldEdge.NORTH:
        return math.isclose(max_y, battlefield_depth_inches, rel_tol=0.0, abs_tol=_EPSILON)
    if edge is BattlefieldEdge.WEST:
        return math.isclose(min_x, 0.0, rel_tol=0.0, abs_tol=_EPSILON)
    if edge is BattlefieldEdge.EAST:
        return math.isclose(max_x, battlefield_width_inches, rel_tol=0.0, abs_tol=_EPSILON)
    raise GameLifecycleError("Unsupported BattlefieldEdge.")


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


def _unit_for_reserve_state(
    *,
    scenario: BattlefieldScenario,
    reserve_state: ReserveState,
) -> UnitInstance:
    try:
        return scenario.army_by_id(
            reserve_state.unit_instance_id.split(":", maxsplit=1)[0]
        ).unit_by_id(reserve_state.unit_instance_id)
    except (PlacementError, ArmyMusteringError) as exc:
        raise GameLifecycleError("ReserveState references an unknown unit.") from exc


def _unit_by_id(armies: tuple[ArmyDefinition, ...]) -> dict[str, UnitInstance]:
    return {unit.unit_instance_id: unit for army in armies for unit in army.units}


def _unit_has_deep_strike(unit: UnitInstance) -> bool:
    return unit_has_deep_strike(unit)


def _unit_has_keyword(unit: UnitInstance, keyword: str) -> bool:
    if type(unit) is not UnitInstance:
        raise GameLifecycleError("unit must be a UnitInstance.")
    requested_keyword = _canonical_keyword(keyword)
    return requested_keyword in {_canonical_keyword(stored) for stored in unit.keywords}


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _validate_reserve_state_tuple(field_name: str, values: object) -> tuple[ReserveState, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    states: list[ReserveState] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ReserveState:
            raise GameLifecycleError(f"{field_name} must contain ReserveState values.")
        if value.unit_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate unit IDs.")
        seen.add(value.unit_instance_id)
        states.append(value)
    return tuple(sorted(states, key=lambda state: state.unit_instance_id))


def _validate_army_tuple(field_name: str, values: object) -> tuple[ArmyDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    armies: list[ArmyDefinition] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not ArmyDefinition:
            raise GameLifecycleError(f"{field_name} must contain ArmyDefinition values.")
        armies.append(value)
    return tuple(sorted(armies, key=lambda army: army.army_id))


def _validate_post_arrival_restriction_tuple(
    field_name: str,
    values: object,
) -> tuple[ReservePostArrivalRestriction, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    restrictions = tuple(
        reserve_post_arrival_restriction_from_token(value)
        for value in cast(tuple[object, ...], values)
    )
    seen: set[ReservePostArrivalRestriction] = set()
    for restriction in restrictions:
        if restriction in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(restriction)
    return tuple(sorted(restrictions, key=lambda restriction: restriction.value))


def _validate_large_model_exception_tuple(
    field_name: str,
    values: object,
) -> tuple[LargeModelReservePlacementException, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    exceptions: list[LargeModelReservePlacementException] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not LargeModelReservePlacementException:
            raise GameLifecycleError(
                f"{field_name} must contain LargeModelReservePlacementException values."
            )
        if value.model_instance_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(value.model_instance_id)
        exceptions.append(value)
    return tuple(sorted(exceptions, key=lambda exception: exception.model_instance_id))


def _validate_reserve_placement_violation_tuple(
    field_name: str,
    values: object,
) -> tuple[ReservePlacementViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    violations: list[ReservePlacementViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not ReservePlacementViolation:
            raise GameLifecycleError(f"{field_name} must contain violations.")
        violations.append(value)
    return tuple(
        sorted(
            violations,
            key=lambda violation: (
                violation.violation_code.value,
                "" if violation.model_instance_id is None else violation.model_instance_id,
                "" if violation.blocker_id is None else violation.blocker_id,
            ),
        )
    )


def _validate_battlefield_edge_tuple(
    field_name: str,
    values: object,
) -> tuple[BattlefieldEdge, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    edges = tuple(battlefield_edge_from_token(value) for value in cast(tuple[object, ...], values))
    seen: set[BattlefieldEdge] = set()
    for edge in edges:
        if edge in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(edge)
    return tuple(sorted(edges, key=lambda edge: edge.value))


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


def _validate_deployment_zone_tuple(
    field_name: str,
    values: object,
) -> tuple[DeploymentZone, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    zones: list[DeploymentZone] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeploymentZone:
            raise GameLifecycleError(f"{field_name} must contain DeploymentZone values.")
        zones.append(value)
    return tuple(sorted(zones, key=lambda zone: zone.deployment_zone_id))


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int = 0,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    minimum = _validate_non_negative_int(f"{field_name} min_length", min_length)
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    if len(identifiers) < minimum:
        raise GameLifecycleError(f"{field_name} must contain at least {minimum} value(s).")
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


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value


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


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    if number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be greater than 0.")
    return number
