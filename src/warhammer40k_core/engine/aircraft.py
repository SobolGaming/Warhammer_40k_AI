from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from itertools import pairwise
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRemovalKind,
    BattlefieldRuntimeState,
    BattlefieldScenario,
    BattlefieldTransitionBatch,
    BattlefieldTransitionBatchPayload,
    ModelRemovalRecord,
    UnitPlacement,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError
from warhammer40k_core.engine.reserves import (
    ReinforcementPlacement,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReserveState,
    ReserveStatePayload,
    resolve_reserve_arrival,
)
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.movement_envelope import (
    AircraftBaseMovementWitness,
    AircraftBaseMovementWitnessPayload,
    PivotCostPolicy,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition
from warhammer40k_core.geometry.volume import Model

_AIRCRAFT_KEYWORD = "AIRCRAFT"
_FLY_KEYWORD = "FLY"
_HOVER_KEYWORD = "HOVER"
_MONSTER_KEYWORD = "MONSTER"
_VEHICLE_KEYWORD = "VEHICLE"
_AIRCRAFT_MINIMUM_MOVE_INCHES = 20.0
_AIRCRAFT_MAXIMUM_PIVOT_DEGREES = 90.0
_AIRCRAFT_RESERVE_DESTINATION_ID = "strategic_reserves"
_EPSILON = 1e-9


class AircraftReserveTransitionReason(StrEnum):
    BATTLEFIELD_EDGE_CROSSED = "aircraft_battlefield_edge_crossed"
    MINIMUM_MOVE_UNAVAILABLE = "aircraft_minimum_move_unavailable"


class AircraftMovementViolationCode(StrEnum):
    UNIT_NOT_AIRCRAFT = "unit_not_aircraft"
    HOVER_MODE_USES_NORMAL_MOVEMENT = "hover_mode_uses_normal_movement"
    AIRCRAFT_MINIMUM_MOVE_REQUIRED = "aircraft_minimum_move_required"
    AIRCRAFT_FORWARD_MOVE_REQUIRED = "aircraft_forward_move_required"
    AIRCRAFT_PIVOT_LIMIT_EXCEEDED = "aircraft_pivot_limit_exceeded"
    AIRCRAFT_PIVOT_BEFORE_MOVE = "aircraft_pivot_before_move"
    AIRCRAFT_MULTIPLE_PIVOTS = "aircraft_multiple_pivots"
    AIRCRAFT_TRANSLATION_AFTER_PIVOT = "aircraft_translation_after_pivot"
    AIRCRAFT_PIVOT_DURING_TRANSLATION = "aircraft_pivot_during_translation"


class HoverModeStatePayload(TypedDict):
    player_id: str
    unit_instance_id: str
    active: bool
    source_id: str
    decision_request_id: str | None
    decision_result_id: str | None


class AircraftMovementPolicyPayload(TypedDict):
    ruleset_descriptor_hash: str
    unit_instance_id: str
    model_instance_ids: list[str]
    original_keywords: list[str]
    effective_keywords: list[str]
    has_aircraft_keyword: bool
    hover_mode_active: bool
    uses_aircraft_rules: bool
    minimum_move_inches: float | None
    maximum_pivot_degrees: float | None
    pivot_cost_inches: float
    can_move_over_other_models: bool
    other_models_can_move_over_this_aircraft: bool
    can_declare_charge: bool
    fight_phase_restriction_exposed: bool


class AircraftMovementViolationPayload(TypedDict):
    violation_code: str
    message: str
    model_instance_id: str | None


class AircraftMinimumMoveResultPayload(TypedDict):
    model_instance_id: str
    minimum_move_inches: float
    minimum_move_satisfied: bool
    base_movement_witness: AircraftBaseMovementWitnessPayload


class AircraftReserveTransitionPayload(TypedDict):
    reason: str
    policy: AircraftMovementPolicyPayload
    is_valid: bool
    violations: list[AircraftMovementViolationPayload]
    reserve_state: ReserveStatePayload | None
    transition_batch: BattlefieldTransitionBatchPayload | None


@dataclass(frozen=True, slots=True)
class HoverModeState:
    player_id: str
    unit_instance_id: str
    active: bool
    source_id: str = "hover"
    decision_request_id: str | None = None
    decision_result_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("HoverModeState player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("HoverModeState unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "active",
            _validate_bool("HoverModeState active", self.active),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("HoverModeState source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "decision_request_id",
            _validate_optional_identifier(
                "HoverModeState decision_request_id",
                self.decision_request_id,
            ),
        )
        object.__setattr__(
            self,
            "decision_result_id",
            _validate_optional_identifier(
                "HoverModeState decision_result_id",
                self.decision_result_id,
            ),
        )

    @classmethod
    def active_for_unit(
        cls,
        *,
        player_id: str,
        unit_instance_id: str,
        decision_request_id: str | None = None,
        decision_result_id: str | None = None,
    ) -> Self:
        return cls(
            player_id=player_id,
            unit_instance_id=unit_instance_id,
            active=True,
            decision_request_id=decision_request_id,
            decision_result_id=decision_result_id,
        )

    def to_payload(self) -> HoverModeStatePayload:
        return {
            "player_id": self.player_id,
            "unit_instance_id": self.unit_instance_id,
            "active": self.active,
            "source_id": self.source_id,
            "decision_request_id": self.decision_request_id,
            "decision_result_id": self.decision_result_id,
        }

    @classmethod
    def from_payload(cls, payload: HoverModeStatePayload) -> Self:
        return cls(
            player_id=payload["player_id"],
            unit_instance_id=payload["unit_instance_id"],
            active=payload["active"],
            source_id=payload["source_id"],
            decision_request_id=payload["decision_request_id"],
            decision_result_id=payload["decision_result_id"],
        )


@dataclass(frozen=True, slots=True)
class AircraftMinimumMoveResult:
    model_instance_id: str
    minimum_move_inches: float
    minimum_move_satisfied: bool
    base_movement_witness: AircraftBaseMovementWitness

    def __post_init__(self) -> None:
        model_instance_id = _validate_identifier(
            "AircraftMinimumMoveResult model_instance_id",
            self.model_instance_id,
        )
        minimum_move_inches = _validate_positive_number(
            "AircraftMinimumMoveResult minimum_move_inches",
            self.minimum_move_inches,
        )
        _validate_bool(
            "AircraftMinimumMoveResult minimum_move_satisfied",
            self.minimum_move_satisfied,
        )
        if type(self.base_movement_witness) is not AircraftBaseMovementWitness:
            raise GameLifecycleError(
                "AircraftMinimumMoveResult base_movement_witness must be "
                "AircraftBaseMovementWitness."
            )
        if self.base_movement_witness.model_id != model_instance_id:
            raise GameLifecycleError("AircraftMinimumMoveResult model_id drift.")
        if not math.isclose(
            self.base_movement_witness.minimum_move_inches,
            minimum_move_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise GameLifecycleError("AircraftMinimumMoveResult minimum move drift.")
        if self.base_movement_witness.minimum_move_satisfied != self.minimum_move_satisfied:
            raise GameLifecycleError("AircraftMinimumMoveResult satisfaction drift.")
        object.__setattr__(self, "model_instance_id", model_instance_id)
        object.__setattr__(self, "minimum_move_inches", minimum_move_inches)

    @classmethod
    def for_model_path(
        cls,
        *,
        moving_model: Model,
        witness: PathWitness,
        minimum_move_inches: float,
    ) -> Self:
        if type(moving_model) is not Model:
            raise GameLifecycleError("Aircraft minimum move requires a Model.")
        if type(witness) is not PathWitness:
            raise GameLifecycleError("Aircraft minimum move requires a PathWitness.")
        path = witness.poses_for_model(moving_model.model_id)
        movement_end_pose = _aircraft_movement_endpoint_before_pivot(path)
        base_witness = AircraftBaseMovementWitness.for_model_movement(
            model=moving_model,
            movement_end_pose=movement_end_pose,
            minimum_move_inches=minimum_move_inches,
        )
        return cls(
            model_instance_id=moving_model.model_id,
            minimum_move_inches=minimum_move_inches,
            minimum_move_satisfied=base_witness.minimum_move_satisfied,
            base_movement_witness=base_witness,
        )

    def to_payload(self) -> AircraftMinimumMoveResultPayload:
        return {
            "model_instance_id": self.model_instance_id,
            "minimum_move_inches": self.minimum_move_inches,
            "minimum_move_satisfied": self.minimum_move_satisfied,
            "base_movement_witness": self.base_movement_witness.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: AircraftMinimumMoveResultPayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            minimum_move_inches=payload["minimum_move_inches"],
            minimum_move_satisfied=payload["minimum_move_satisfied"],
            base_movement_witness=AircraftBaseMovementWitness.from_payload(
                payload["base_movement_witness"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AircraftMovementPolicy:
    ruleset_descriptor_hash: str
    unit_instance_id: str
    model_instance_ids: tuple[str, ...]
    original_keywords: tuple[str, ...]
    effective_keywords: tuple[str, ...]
    has_aircraft_keyword: bool
    hover_mode_active: bool
    uses_aircraft_rules: bool
    minimum_move_inches: float | None
    maximum_pivot_degrees: float | None
    pivot_cost_inches: float
    can_move_over_other_models: bool
    other_models_can_move_over_this_aircraft: bool
    can_declare_charge: bool
    fight_phase_restriction_exposed: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ruleset_descriptor_hash",
            _validate_identifier(
                "AircraftMovementPolicy ruleset_descriptor_hash",
                self.ruleset_descriptor_hash,
            ),
        )
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_identifier("AircraftMovementPolicy unit_instance_id", self.unit_instance_id),
        )
        object.__setattr__(
            self,
            "model_instance_ids",
            _validate_identifier_tuple(
                "AircraftMovementPolicy model_instance_ids",
                self.model_instance_ids,
            ),
        )
        object.__setattr__(
            self,
            "original_keywords",
            _validate_keyword_tuple(
                "AircraftMovementPolicy original_keywords",
                self.original_keywords,
            ),
        )
        object.__setattr__(
            self,
            "effective_keywords",
            _validate_keyword_tuple(
                "AircraftMovementPolicy effective_keywords",
                self.effective_keywords,
            ),
        )
        for field_name, value in (
            ("has_aircraft_keyword", self.has_aircraft_keyword),
            ("hover_mode_active", self.hover_mode_active),
            ("uses_aircraft_rules", self.uses_aircraft_rules),
            ("can_move_over_other_models", self.can_move_over_other_models),
            (
                "other_models_can_move_over_this_aircraft",
                self.other_models_can_move_over_this_aircraft,
            ),
            ("can_declare_charge", self.can_declare_charge),
            ("fight_phase_restriction_exposed", self.fight_phase_restriction_exposed),
        ):
            _validate_bool(f"AircraftMovementPolicy {field_name}", value)
        object.__setattr__(
            self,
            "minimum_move_inches",
            _validate_optional_positive_number(
                "AircraftMovementPolicy minimum_move_inches",
                self.minimum_move_inches,
            ),
        )
        object.__setattr__(
            self,
            "maximum_pivot_degrees",
            _validate_optional_positive_number(
                "AircraftMovementPolicy maximum_pivot_degrees",
                self.maximum_pivot_degrees,
            ),
        )
        object.__setattr__(
            self,
            "pivot_cost_inches",
            _validate_non_negative_number(
                "AircraftMovementPolicy pivot_cost_inches",
                self.pivot_cost_inches,
            ),
        )
        if self.uses_aircraft_rules and not self.has_aircraft_keyword:
            raise GameLifecycleError("AircraftMovementPolicy cannot use rules without AIRCRAFT.")
        if self.hover_mode_active and self.uses_aircraft_rules:
            raise GameLifecycleError("Hover mode must disable AIRCRAFT movement rules.")
        if self.uses_aircraft_rules and (
            self.minimum_move_inches is None or self.maximum_pivot_degrees is None
        ):
            raise GameLifecycleError("AIRCRAFT movement policy requires minimum move and pivot.")
        if not self.uses_aircraft_rules and (
            self.minimum_move_inches is not None or self.maximum_pivot_degrees is not None
        ):
            raise GameLifecycleError(
                "Non-AIRCRAFT movement policy must not include aircraft-only limits."
            )

    @classmethod
    def from_unit(
        cls,
        *,
        unit: UnitInstance,
        ruleset_descriptor: RulesetDescriptor,
        hover_mode_state: HoverModeState | None = None,
    ) -> Self:
        if type(unit) is not UnitInstance:
            raise GameLifecycleError("AircraftMovementPolicy requires a UnitInstance.")
        if type(ruleset_descriptor) is not RulesetDescriptor:
            raise GameLifecycleError("AircraftMovementPolicy requires a RulesetDescriptor.")
        if hover_mode_state is not None:
            if type(hover_mode_state) is not HoverModeState:
                raise GameLifecycleError("hover_mode_state must be a HoverModeState.")
            if hover_mode_state.unit_instance_id != unit.unit_instance_id:
                raise GameLifecycleError("HoverModeState unit_instance_id drift.")
        original_keywords = _validate_keyword_tuple(
            "AircraftMovementPolicy unit keywords",
            unit.keywords,
        )
        has_aircraft = _AIRCRAFT_KEYWORD in original_keywords
        hover_active = hover_mode_state is not None and hover_mode_state.active
        effective_keywords = (
            tuple(keyword for keyword in original_keywords if keyword != _AIRCRAFT_KEYWORD)
            if hover_active
            else original_keywords
        )
        uses_aircraft_rules = has_aircraft and not hover_active
        return cls(
            ruleset_descriptor_hash=ruleset_descriptor.descriptor_hash,
            unit_instance_id=unit.unit_instance_id,
            model_instance_ids=tuple(model.model_instance_id for model in unit.own_models),
            original_keywords=original_keywords,
            effective_keywords=effective_keywords,
            has_aircraft_keyword=has_aircraft,
            hover_mode_active=hover_active,
            uses_aircraft_rules=uses_aircraft_rules,
            minimum_move_inches=_AIRCRAFT_MINIMUM_MOVE_INCHES if uses_aircraft_rules else None,
            maximum_pivot_degrees=_AIRCRAFT_MAXIMUM_PIVOT_DEGREES if uses_aircraft_rules else None,
            pivot_cost_inches=0.0 if uses_aircraft_rules else _generic_pivot_cost_placeholder(),
            can_move_over_other_models=uses_aircraft_rules or _FLY_KEYWORD in effective_keywords,
            other_models_can_move_over_this_aircraft=uses_aircraft_rules,
            can_declare_charge=not uses_aircraft_rules,
            fight_phase_restriction_exposed=uses_aircraft_rules,
        )

    def aircraft_model_ids(self) -> tuple[str, ...]:
        return self.model_instance_ids if self.uses_aircraft_rules else ()

    def to_pivot_cost_policy(self, model_instance_id: str) -> PivotCostPolicy:
        requested_model_id = _validate_identifier("model_instance_id", model_instance_id)
        if requested_model_id not in set(self.model_instance_ids):
            raise GameLifecycleError("model_instance_id is not governed by this aircraft policy.")
        effective_keyword_set = set(self.effective_keywords)
        aircraft_model_ids = (requested_model_id,) if self.uses_aircraft_rules else ()
        vehicle_or_monster_model_ids = (
            (requested_model_id,)
            if (
                _VEHICLE_KEYWORD in effective_keyword_set
                or _MONSTER_KEYWORD in effective_keyword_set
            )
            else ()
        )
        round_base_flying_stem_or_hover_model_ids = (
            (requested_model_id,)
            if _VEHICLE_KEYWORD in effective_keyword_set
            and (_FLY_KEYWORD in effective_keyword_set or _HOVER_KEYWORD in effective_keyword_set)
            else ()
        )
        return PivotCostPolicy(
            vehicle_or_monster_model_ids=vehicle_or_monster_model_ids,
            aircraft_model_ids=aircraft_model_ids,
            round_base_flying_stem_or_hover_stand_vehicle_model_ids=(
                round_base_flying_stem_or_hover_model_ids
            ),
        )

    def validate_normal_move_witness(
        self,
        *,
        moving_model: Model,
        witness: PathWitness,
    ) -> tuple[AircraftMovementViolation, ...]:
        violations, _minimum_move_result = self.validate_normal_move_witness_with_minimum_result(
            moving_model=moving_model,
            witness=witness,
        )
        return violations

    def validate_normal_move_witness_with_minimum_result(
        self,
        *,
        moving_model: Model,
        witness: PathWitness,
    ) -> tuple[tuple[AircraftMovementViolation, ...], AircraftMinimumMoveResult | None]:
        if type(moving_model) is not Model:
            raise GameLifecycleError("Aircraft movement validation requires a Model.")
        if type(witness) is not PathWitness:
            raise GameLifecycleError("Aircraft movement validation requires a PathWitness.")
        if moving_model.model_id not in set(self.model_instance_ids):
            raise GameLifecycleError("Aircraft movement validation model is not in policy.")
        if not self.has_aircraft_keyword:
            return (
                (
                    AircraftMovementViolation(
                        violation_code=AircraftMovementViolationCode.UNIT_NOT_AIRCRAFT,
                        message="Unit does not have the AIRCRAFT keyword.",
                        model_instance_id=moving_model.model_id,
                    ),
                ),
                None,
            )
        if self.hover_mode_active:
            return ((), None)
        path = witness.poses_for_model(moving_model.model_id)
        minimum_move_inches = _required_number(
            "AircraftMovementPolicy minimum_move_inches",
            self.minimum_move_inches,
        )
        minimum_move_result = AircraftMinimumMoveResult.for_model_path(
            moving_model=moving_model,
            witness=witness,
            minimum_move_inches=minimum_move_inches,
        )
        return (
            _validate_aircraft_normal_move_path(
                model_instance_id=moving_model.model_id,
                poses=path,
                minimum_move_result=minimum_move_result,
                maximum_pivot_degrees=_required_number(
                    "AircraftMovementPolicy maximum_pivot_degrees",
                    self.maximum_pivot_degrees,
                ),
            ),
            minimum_move_result,
        )

    def to_payload(self) -> AircraftMovementPolicyPayload:
        return {
            "ruleset_descriptor_hash": self.ruleset_descriptor_hash,
            "unit_instance_id": self.unit_instance_id,
            "model_instance_ids": list(self.model_instance_ids),
            "original_keywords": list(self.original_keywords),
            "effective_keywords": list(self.effective_keywords),
            "has_aircraft_keyword": self.has_aircraft_keyword,
            "hover_mode_active": self.hover_mode_active,
            "uses_aircraft_rules": self.uses_aircraft_rules,
            "minimum_move_inches": self.minimum_move_inches,
            "maximum_pivot_degrees": self.maximum_pivot_degrees,
            "pivot_cost_inches": self.pivot_cost_inches,
            "can_move_over_other_models": self.can_move_over_other_models,
            "other_models_can_move_over_this_aircraft": (
                self.other_models_can_move_over_this_aircraft
            ),
            "can_declare_charge": self.can_declare_charge,
            "fight_phase_restriction_exposed": self.fight_phase_restriction_exposed,
        }

    @classmethod
    def from_payload(cls, payload: AircraftMovementPolicyPayload) -> Self:
        return cls(
            ruleset_descriptor_hash=payload["ruleset_descriptor_hash"],
            unit_instance_id=payload["unit_instance_id"],
            model_instance_ids=tuple(payload["model_instance_ids"]),
            original_keywords=tuple(payload["original_keywords"]),
            effective_keywords=tuple(payload["effective_keywords"]),
            has_aircraft_keyword=payload["has_aircraft_keyword"],
            hover_mode_active=payload["hover_mode_active"],
            uses_aircraft_rules=payload["uses_aircraft_rules"],
            minimum_move_inches=payload["minimum_move_inches"],
            maximum_pivot_degrees=payload["maximum_pivot_degrees"],
            pivot_cost_inches=payload["pivot_cost_inches"],
            can_move_over_other_models=payload["can_move_over_other_models"],
            other_models_can_move_over_this_aircraft=payload[
                "other_models_can_move_over_this_aircraft"
            ],
            can_declare_charge=payload["can_declare_charge"],
            fight_phase_restriction_exposed=payload["fight_phase_restriction_exposed"],
        )


@dataclass(frozen=True, slots=True)
class AircraftMovementViolation:
    violation_code: AircraftMovementViolationCode
    message: str
    model_instance_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "violation_code",
            aircraft_movement_violation_code_from_token(self.violation_code),
        )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("AircraftMovementViolation message", self.message),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_optional_identifier(
                "AircraftMovementViolation model_instance_id",
                self.model_instance_id,
            ),
        )

    def to_payload(self) -> AircraftMovementViolationPayload:
        return {
            "violation_code": self.violation_code.value,
            "message": self.message,
            "model_instance_id": self.model_instance_id,
        }

    @classmethod
    def from_payload(cls, payload: AircraftMovementViolationPayload) -> Self:
        return cls(
            violation_code=aircraft_movement_violation_code_from_token(payload["violation_code"]),
            message=payload["message"],
            model_instance_id=payload["model_instance_id"],
        )


@dataclass(frozen=True, slots=True)
class AircraftReserveTransition:
    reason: AircraftReserveTransitionReason
    policy: AircraftMovementPolicy
    violations: tuple[AircraftMovementViolation, ...]
    reserve_state: ReserveState | None
    transition_batch: BattlefieldTransitionBatch | None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason",
            aircraft_reserve_transition_reason_from_token(self.reason),
        )
        if type(self.policy) is not AircraftMovementPolicy:
            raise GameLifecycleError("AircraftReserveTransition policy must be a policy.")
        object.__setattr__(
            self,
            "violations",
            _validate_aircraft_movement_violations(
                "AircraftReserveTransition violations",
                self.violations,
            ),
        )
        if self.reserve_state is not None and type(self.reserve_state) is not ReserveState:
            raise GameLifecycleError(
                "AircraftReserveTransition reserve_state must be ReserveState."
            )
        if self.transition_batch is not None and type(self.transition_batch) is not (
            BattlefieldTransitionBatch
        ):
            raise GameLifecycleError(
                "AircraftReserveTransition transition_batch must be BattlefieldTransitionBatch."
            )
        if self.violations and (
            self.reserve_state is not None or self.transition_batch is not None
        ):
            raise GameLifecycleError(
                "Invalid AircraftReserveTransition must not include state changes."
            )
        if not self.violations and (self.reserve_state is None or self.transition_batch is None):
            raise GameLifecycleError("Valid AircraftReserveTransition requires state changes.")

    @property
    def is_valid(self) -> bool:
        return not self.violations

    def to_payload(self) -> AircraftReserveTransitionPayload:
        return {
            "reason": self.reason.value,
            "policy": self.policy.to_payload(),
            "is_valid": self.is_valid,
            "violations": [violation.to_payload() for violation in self.violations],
            "reserve_state": None
            if self.reserve_state is None
            else self.reserve_state.to_payload(),
            "transition_batch": None
            if self.transition_batch is None
            else self.transition_batch.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: AircraftReserveTransitionPayload) -> Self:
        reserve_payload = payload["reserve_state"]
        transition_payload = payload["transition_batch"]
        transition = cls(
            reason=aircraft_reserve_transition_reason_from_token(payload["reason"]),
            policy=AircraftMovementPolicy.from_payload(payload["policy"]),
            violations=tuple(
                AircraftMovementViolation.from_payload(violation)
                for violation in payload["violations"]
            ),
            reserve_state=None
            if reserve_payload is None
            else ReserveState.from_payload(reserve_payload),
            transition_batch=None
            if transition_payload is None
            else BattlefieldTransitionBatch.from_payload(transition_payload),
        )
        if transition.is_valid != payload["is_valid"]:
            raise GameLifecycleError("AircraftReserveTransition payload validity drift.")
        return transition


def resolve_aircraft_reserve_transition(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    unit_placement: UnitPlacement,
    battle_round: int,
    reason: AircraftReserveTransitionReason,
    source_event_id: str | None = None,
    hover_mode_state: HoverModeState | None = None,
) -> AircraftReserveTransition:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("Aircraft reserve transition requires a BattlefieldScenario.")
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("Aircraft reserve transition requires a RulesetDescriptor.")
    if type(unit_placement) is not UnitPlacement:
        raise GameLifecycleError("Aircraft reserve transition requires a UnitPlacement.")
    requested_round = _validate_positive_int("battle_round", battle_round)
    transition_reason = aircraft_reserve_transition_reason_from_token(reason)
    event_id = _validate_optional_identifier("source_event_id", source_event_id)
    unit = scenario.unit_instance_for_placement(unit_placement)
    policy = AircraftMovementPolicy.from_unit(
        unit=unit,
        ruleset_descriptor=ruleset_descriptor,
        hover_mode_state=hover_mode_state,
    )
    violations: tuple[AircraftMovementViolation, ...] = ()
    if not policy.has_aircraft_keyword:
        violations = (
            AircraftMovementViolation(
                violation_code=AircraftMovementViolationCode.UNIT_NOT_AIRCRAFT,
                message="Only AIRCRAFT can use the aircraft reserve transition.",
            ),
        )
    elif policy.hover_mode_active or not policy.uses_aircraft_rules:
        violations = (
            AircraftMovementViolation(
                violation_code=AircraftMovementViolationCode.HOVER_MODE_USES_NORMAL_MOVEMENT,
                message="Hover mode disables the aircraft reserve transition.",
            ),
        )
    if violations:
        return AircraftReserveTransition(
            reason=transition_reason,
            policy=policy,
            violations=violations,
            reserve_state=None,
            transition_batch=None,
        )
    reserve_state = ReserveState.entered_during_battle(
        player_id=unit_placement.player_id,
        unit_instance_id=unit_placement.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        battle_round=requested_round,
        phase=BattlePhase.MOVEMENT,
        required_arrival_battle_round=requested_round + 1,
        required_arrival_phase=BattlePhase.MOVEMENT,
        required_arrival_source_rule_id=transition_reason.value,
        destruction_deadline_policy=(
            ReserveDestructionTimingPolicy.from_mission_policy(ruleset_descriptor.mission_policy)
        ),
    )
    transition_batch = _aircraft_reserve_transition_batch(
        unit_placement=unit_placement,
        reason=transition_reason,
        source_event_id=event_id,
    )
    return AircraftReserveTransition(
        reason=transition_reason,
        policy=policy,
        violations=(),
        reserve_state=reserve_state,
        transition_batch=transition_batch,
    )


def apply_aircraft_reserve_transition_to_battlefield(
    *,
    battlefield_state: BattlefieldRuntimeState,
    transition: AircraftReserveTransition,
) -> BattlefieldRuntimeState:
    if type(battlefield_state) is not BattlefieldRuntimeState:
        raise GameLifecycleError("battlefield_state must be a BattlefieldRuntimeState.")
    if type(transition) is not AircraftReserveTransition:
        raise GameLifecycleError("transition must be an AircraftReserveTransition.")
    if not transition.is_valid:
        raise GameLifecycleError("Invalid AircraftReserveTransition cannot mutate battlefield.")
    return battlefield_state.without_unit_placement(transition.policy.unit_instance_id)


def resolve_aircraft_arrival(
    *,
    scenario: BattlefieldScenario,
    ruleset_descriptor: RulesetDescriptor,
    reserve_state: ReserveState,
    attempted_placement: UnitPlacement,
    battle_round: int,
    battlefield_width_inches: float = 60.0,
    battlefield_depth_inches: float = 44.0,
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
) -> ReinforcementPlacement:
    if type(reserve_state) is not ReserveState:
        raise GameLifecycleError("Aircraft arrival requires ReserveState.")
    if reserve_state.reserve_kind is not ReserveKind.STRATEGIC_RESERVES:
        raise GameLifecycleError("Aircraft arrival requires Strategic Reserves state.")
    return resolve_reserve_arrival(
        scenario=scenario,
        ruleset_descriptor=ruleset_descriptor,
        reserve_state=reserve_state,
        attempted_placement=attempted_placement,
        battle_round=battle_round,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        battlefield_width_inches=battlefield_width_inches,
        battlefield_depth_inches=battlefield_depth_inches,
        terrain_features=terrain_features,
    )


def aircraft_model_ids_for_scenario(
    scenario: BattlefieldScenario,
    *,
    hover_mode_states: tuple[HoverModeState, ...] = (),
) -> tuple[str, ...]:
    if type(scenario) is not BattlefieldScenario:
        raise GameLifecycleError("aircraft_model_ids_for_scenario requires a scenario.")
    hover_states_by_unit_id = _active_hover_states_by_unit_id(hover_mode_states)
    aircraft_model_ids: list[str] = []
    for placed_army in scenario.battlefield_state.placed_armies:
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            if _AIRCRAFT_KEYWORD not in _validate_keyword_tuple(
                "aircraft unit keywords",
                unit.keywords,
            ):
                continue
            if unit.unit_instance_id in hover_states_by_unit_id:
                continue
            aircraft_model_ids.extend(
                placement.model_instance_id for placement in unit_placement.model_placements
            )
    return tuple(sorted(aircraft_model_ids))


def aircraft_reserve_transition_reason_from_token(
    token: object,
) -> AircraftReserveTransitionReason:
    if type(token) is AircraftReserveTransitionReason:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AircraftReserveTransitionReason token must be a string.")
    try:
        return AircraftReserveTransitionReason(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported AircraftReserveTransitionReason token: {token}."
        ) from exc


def aircraft_movement_violation_code_from_token(token: object) -> AircraftMovementViolationCode:
    if type(token) is AircraftMovementViolationCode:
        return token
    if type(token) is not str:
        raise GameLifecycleError("AircraftMovementViolationCode token must be a string.")
    try:
        return AircraftMovementViolationCode(token)
    except ValueError as exc:
        raise GameLifecycleError(
            f"Unsupported AircraftMovementViolationCode token: {token}."
        ) from exc


def _active_hover_states_by_unit_id(
    hover_mode_states: tuple[HoverModeState, ...],
) -> dict[str, HoverModeState]:
    if type(hover_mode_states) is not tuple:
        raise GameLifecycleError("hover_mode_states must be a tuple.")
    states_by_unit_id: dict[str, HoverModeState] = {}
    for hover_state in cast(tuple[object, ...], hover_mode_states):
        if type(hover_state) is not HoverModeState:
            raise GameLifecycleError("hover_mode_states must contain HoverModeState values.")
        if not hover_state.active:
            continue
        if hover_state.unit_instance_id in states_by_unit_id:
            raise GameLifecycleError("hover_mode_states must be unique by unit.")
        states_by_unit_id[hover_state.unit_instance_id] = hover_state
    return states_by_unit_id


def _aircraft_reserve_transition_batch(
    *,
    unit_placement: UnitPlacement,
    reason: AircraftReserveTransitionReason,
    source_event_id: str | None,
) -> BattlefieldTransitionBatch:
    return BattlefieldTransitionBatch(
        removals=tuple(
            ModelRemovalRecord(
                model_instance_id=placement.model_instance_id,
                removal_kind=BattlefieldRemovalKind.INTO_RESERVES,
                source_phase=BattlePhase.MOVEMENT.value,
                source_step="move_units",
                source_rule_id=reason.value,
                source_event_id=source_event_id,
                destination_id=_AIRCRAFT_RESERVE_DESTINATION_ID,
            )
            for placement in unit_placement.model_placements
        )
    )


def _validate_aircraft_normal_move_path(
    *,
    model_instance_id: str,
    poses: tuple[Pose, ...],
    minimum_move_result: AircraftMinimumMoveResult,
    maximum_pivot_degrees: float,
) -> tuple[AircraftMovementViolation, ...]:
    violations: list[AircraftMovementViolation] = []
    if type(minimum_move_result) is not AircraftMinimumMoveResult:
        raise GameLifecycleError("AIRCRAFT minimum move result is required.")
    if minimum_move_result.model_instance_id != model_instance_id:
        raise GameLifecycleError("AIRCRAFT minimum move result model drift.")
    start_facing_degrees = poses[0].facing.degrees
    translation_distance = 0.0
    pivot_count = 0
    pivot_seen = False
    for start_pose, end_pose in pairwise(poses):
        segment_distance = start_pose.distance_2d_to(end_pose)
        facing_delta = _angle_delta_degrees(start_pose.facing.degrees, end_pose.facing.degrees)
        is_translation = segment_distance > _EPSILON
        is_pivot = facing_delta > _EPSILON
        if is_translation and is_pivot:
            violations.append(
                AircraftMovementViolation(
                    violation_code=(
                        AircraftMovementViolationCode.AIRCRAFT_PIVOT_DURING_TRANSLATION
                    ),
                    message="AIRCRAFT pivots must happen after translation.",
                    model_instance_id=model_instance_id,
                )
            )
        if is_translation:
            translation_distance += segment_distance
            if pivot_seen:
                violations.append(
                    AircraftMovementViolation(
                        violation_code=(
                            AircraftMovementViolationCode.AIRCRAFT_TRANSLATION_AFTER_PIVOT
                        ),
                        message="AIRCRAFT cannot translate after its final pivot.",
                        model_instance_id=model_instance_id,
                    )
                )
            if not _segment_is_forward(start_pose, end_pose, start_facing_degrees):
                violations.append(
                    AircraftMovementViolation(
                        violation_code=(
                            AircraftMovementViolationCode.AIRCRAFT_FORWARD_MOVE_REQUIRED
                        ),
                        message="AIRCRAFT must move straight forward before pivoting.",
                        model_instance_id=model_instance_id,
                    )
                )
        if is_pivot:
            pivot_count += 1
            pivot_seen = True
            if translation_distance <= _EPSILON:
                violations.append(
                    AircraftMovementViolation(
                        violation_code=AircraftMovementViolationCode.AIRCRAFT_PIVOT_BEFORE_MOVE,
                        message="AIRCRAFT can only pivot after it has moved.",
                        model_instance_id=model_instance_id,
                    )
                )
            if pivot_count > 1:
                violations.append(
                    AircraftMovementViolation(
                        violation_code=AircraftMovementViolationCode.AIRCRAFT_MULTIPLE_PIVOTS,
                        message="AIRCRAFT can only pivot once.",
                        model_instance_id=model_instance_id,
                    )
                )
            if facing_delta > maximum_pivot_degrees:
                violations.append(
                    AircraftMovementViolation(
                        violation_code=(
                            AircraftMovementViolationCode.AIRCRAFT_PIVOT_LIMIT_EXCEEDED
                        ),
                        message="AIRCRAFT pivot exceeds 90 degrees.",
                        model_instance_id=model_instance_id,
                    )
                )
    if not minimum_move_result.minimum_move_satisfied:
        violations.append(
            AircraftMovementViolation(
                violation_code=AircraftMovementViolationCode.AIRCRAFT_MINIMUM_MOVE_REQUIRED,
                message="AIRCRAFT must move at least 20 inches before pivoting.",
                model_instance_id=model_instance_id,
            )
        )
    return tuple(violations)


def _aircraft_movement_endpoint_before_pivot(poses: tuple[Pose, ...]) -> Pose:
    if type(poses) is not tuple:
        raise GameLifecycleError("AIRCRAFT path poses must be a tuple.")
    path = tuple(poses)
    if len(path) < 2:
        raise GameLifecycleError("AIRCRAFT path must contain at least two poses.")
    movement_end_pose = path[0]
    pivot_seen = False
    for start_pose, end_pose in pairwise(path):
        segment_distance = start_pose.distance_2d_to(end_pose)
        facing_delta = _angle_delta_degrees(start_pose.facing.degrees, end_pose.facing.degrees)
        is_translation = segment_distance > _EPSILON
        is_pivot = facing_delta > _EPSILON
        if is_translation and not pivot_seen:
            movement_end_pose = end_pose
        if is_pivot:
            pivot_seen = True
    return movement_end_pose


def _segment_is_forward(start_pose: Pose, end_pose: Pose, facing_degrees: float) -> bool:
    dx = end_pose.position.x - start_pose.position.x
    dy = end_pose.position.y - start_pose.position.y
    if math.hypot(dx, dy) <= _EPSILON:
        return True
    segment_degrees = math.degrees(math.atan2(dy, dx)) % 360.0
    return _angle_delta_degrees(segment_degrees, facing_degrees) <= 1e-6


def _angle_delta_degrees(first: float, second: float) -> float:
    return abs((first - second + 180.0) % 360.0 - 180.0)


def _generic_pivot_cost_placeholder() -> float:
    return 0.0


def _required_number(field_name: str, value: float | None) -> float:
    if value is None:
        raise GameLifecycleError(f"{field_name} is required.")
    return value


def _validate_aircraft_movement_violations(
    field_name: str,
    values: object,
) -> tuple[AircraftMovementViolation, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    violations: list[AircraftMovementViolation] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not AircraftMovementViolation:
            raise GameLifecycleError(f"{field_name} must contain aircraft violations.")
        violations.append(value)
    return tuple(violations)


def _validate_keyword_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        keyword = _validate_identifier(f"{field_name} value", value)
        keyword = keyword.upper().replace(" ", "_").replace("-", "_")
        if keyword in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(keyword)
        keywords.append(keyword)
    return tuple(sorted(keywords))


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


def _validate_optional_positive_number(field_name: str, value: object | None) -> float | None:
    if value is None:
        return None
    return _validate_positive_number(field_name, value)


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GameLifecycleError(f"{field_name} must be greater than 0.")
    return number


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number < 0.0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return number


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GameLifecycleError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GameLifecycleError(f"{field_name} must be finite.")
    return number
