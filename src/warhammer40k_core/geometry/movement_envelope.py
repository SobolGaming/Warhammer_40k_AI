from __future__ import annotations

import math
from dataclasses import dataclass, field
from itertools import pairwise
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.base import (
    BaseShape,
    BaseShapePayload,
    CircularBase,
    OvalBase,
    RectangularBase,
    base_shape_from_payload,
    validate_base_shape,
)
from warhammer40k_core.geometry.measurement import MILLIMETERS_PER_INCH
from warhammer40k_core.geometry.pose import (
    Facing,
    GeometryError,
    Point3,
    Pose,
    PosePayload,
    validate_finite_number,
    validate_pose,
)
from warhammer40k_core.geometry.volume import Model

_SEGMENT_MEASUREMENT_POINT = "pose_anchor"
_AIRCRAFT_BASE_POINT_SAMPLE_DEGREES = tuple(range(0, 360, 5))


class MovementSegmentPayload(TypedDict):
    model_id: str
    segment_index: int
    start_pose: PosePayload
    end_pose: PosePayload
    measurement_point: str
    distance_inches: float


class PivotEventPayload(TypedDict):
    model_id: str
    pivot_index: int
    start_pose: PosePayload
    end_pose: PosePayload
    pivot_value_inches: float
    applied_cost_inches: float
    first_pivot_for_model: bool


class MovementDistanceBudgetPayload(TypedDict):
    max_distance_inches: float
    straight_line_distance_inches: float
    pivot_cost_inches: float
    total_distance_inches: float
    remaining_distance_inches: float
    exceeded_by_inches: float


class MovementDistanceWitnessPayload(TypedDict):
    model_id: str
    segments: list[MovementSegmentPayload]
    pivot_events: list[PivotEventPayload]
    budget: MovementDistanceBudgetPayload | None


class BasePointDistanceWitnessPayload(TypedDict):
    point_id: str
    start_x_inches: float
    start_y_inches: float
    end_x_inches: float
    end_y_inches: float
    distance_inches: float


class AircraftBaseMovementWitnessPayload(TypedDict):
    model_id: str
    base: BaseShapePayload
    start_pose: PosePayload
    movement_end_pose: PosePayload
    minimum_move_inches: float
    used_circular_center_shortcut: bool
    point_distances: list[BasePointDistanceWitnessPayload]
    minimum_point_distance_inches: float
    minimum_move_satisfied: bool


class PivotCostPolicyPayload(TypedDict):
    non_round_pivot_cost_inches: float
    vehicle_or_monster_pivot_cost_inches: float
    round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches: float
    aircraft_pivot_cost_inches: float
    round_base_large_vehicle_threshold_mm: float
    vehicle_or_monster_model_ids: list[str]
    aircraft_model_ids: list[str]
    round_base_flying_stem_or_hover_stand_vehicle_model_ids: list[str]


class MovementEnvelopePayload(TypedDict):
    max_distance_inches: float
    sample_interval_inches: float
    coherency_horizontal_inches: float
    coherency_vertical_inches: float
    required_coherency_neighbors: int
    engagement_horizontal_inches: float
    engagement_vertical_inches: float
    pivot_cost_policy: PivotCostPolicyPayload


@dataclass(frozen=True, slots=True)
class BasePointDistanceWitness:
    point_id: str
    start_x_inches: float
    start_y_inches: float
    end_x_inches: float
    end_y_inches: float
    distance_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "point_id",
            _validate_identifier("BasePointDistanceWitness point_id", self.point_id),
        )
        start_x = validate_finite_number(
            "BasePointDistanceWitness start_x_inches",
            self.start_x_inches,
        )
        start_y = validate_finite_number(
            "BasePointDistanceWitness start_y_inches",
            self.start_y_inches,
        )
        end_x = validate_finite_number(
            "BasePointDistanceWitness end_x_inches",
            self.end_x_inches,
        )
        end_y = validate_finite_number(
            "BasePointDistanceWitness end_y_inches",
            self.end_y_inches,
        )
        distance = _validate_non_negative_number(
            "BasePointDistanceWitness distance_inches",
            self.distance_inches,
        )
        expected_distance = math.hypot(end_x - start_x, end_y - start_y)
        if not math.isclose(distance, expected_distance, rel_tol=0.0, abs_tol=1e-9):
            raise GeometryError("BasePointDistanceWitness distance_inches drift.")
        object.__setattr__(self, "start_x_inches", start_x)
        object.__setattr__(self, "start_y_inches", start_y)
        object.__setattr__(self, "end_x_inches", end_x)
        object.__setattr__(self, "end_y_inches", end_y)
        object.__setattr__(self, "distance_inches", distance)

    @classmethod
    def from_points(
        cls,
        *,
        point_id: str,
        start_x_inches: float,
        start_y_inches: float,
        end_x_inches: float,
        end_y_inches: float,
    ) -> Self:
        return cls(
            point_id=point_id,
            start_x_inches=start_x_inches,
            start_y_inches=start_y_inches,
            end_x_inches=end_x_inches,
            end_y_inches=end_y_inches,
            distance_inches=math.hypot(
                end_x_inches - start_x_inches,
                end_y_inches - start_y_inches,
            ),
        )

    def to_payload(self) -> BasePointDistanceWitnessPayload:
        return {
            "point_id": self.point_id,
            "start_x_inches": self.start_x_inches,
            "start_y_inches": self.start_y_inches,
            "end_x_inches": self.end_x_inches,
            "end_y_inches": self.end_y_inches,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: BasePointDistanceWitnessPayload) -> Self:
        return cls(
            point_id=payload["point_id"],
            start_x_inches=payload["start_x_inches"],
            start_y_inches=payload["start_y_inches"],
            end_x_inches=payload["end_x_inches"],
            end_y_inches=payload["end_y_inches"],
            distance_inches=payload["distance_inches"],
        )


@dataclass(frozen=True, slots=True)
class AircraftBaseMovementWitness:
    model_id: str
    base: BaseShape
    start_pose: Pose
    movement_end_pose: Pose
    minimum_move_inches: float
    used_circular_center_shortcut: bool
    point_distances: tuple[BasePointDistanceWitness, ...]

    def __post_init__(self) -> None:
        model_id = _validate_identifier("AircraftBaseMovementWitness model_id", self.model_id)
        base = validate_base_shape("AircraftBaseMovementWitness base", self.base)
        start_pose = validate_pose("AircraftBaseMovementWitness start_pose", self.start_pose)
        movement_end_pose = validate_pose(
            "AircraftBaseMovementWitness movement_end_pose",
            self.movement_end_pose,
        )
        minimum_move_inches = _validate_positive_number(
            "AircraftBaseMovementWitness minimum_move_inches",
            self.minimum_move_inches,
        )
        _validate_bool(
            "AircraftBaseMovementWitness used_circular_center_shortcut",
            self.used_circular_center_shortcut,
        )
        point_distances = _validate_base_point_distance_witnesses(
            "AircraftBaseMovementWitness point_distances",
            self.point_distances,
        )
        circular_shortcut_expected = type(base) is CircularBase
        if self.used_circular_center_shortcut != circular_shortcut_expected:
            raise GeometryError(
                "AircraftBaseMovementWitness circular shortcut must match base shape."
            )
        if self.used_circular_center_shortcut and (
            len(point_distances) != 1 or point_distances[0].point_id != "center"
        ):
            raise GeometryError(
                "AircraftBaseMovementWitness circular shortcut must use only center."
            )
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "base", base)
        object.__setattr__(self, "start_pose", start_pose)
        object.__setattr__(self, "movement_end_pose", movement_end_pose)
        object.__setattr__(self, "minimum_move_inches", minimum_move_inches)
        object.__setattr__(
            self,
            "point_distances",
            tuple(sorted(point_distances, key=lambda point: point.point_id)),
        )

    @classmethod
    def for_model_movement(
        cls,
        *,
        model: Model,
        movement_end_pose: Pose,
        minimum_move_inches: float,
    ) -> Self:
        valid_model = _validate_model("AircraftBaseMovementWitness model", model)
        end_pose = validate_pose("AircraftBaseMovementWitness movement_end_pose", movement_end_pose)
        point_distances = tuple(
            BasePointDistanceWitness.from_points(
                point_id=point_id,
                start_x_inches=start_x,
                start_y_inches=start_y,
                end_x_inches=end_x,
                end_y_inches=end_y,
            )
            for point_id, start_x, start_y, end_x, end_y in _base_point_movements(
                base=valid_model.base,
                start_pose=valid_model.pose,
                movement_end_pose=end_pose,
            )
        )
        return cls(
            model_id=valid_model.model_id,
            base=valid_model.base,
            start_pose=valid_model.pose,
            movement_end_pose=end_pose,
            minimum_move_inches=minimum_move_inches,
            used_circular_center_shortcut=type(valid_model.base) is CircularBase,
            point_distances=point_distances,
        )

    @property
    def minimum_point_distance_inches(self) -> float:
        return min(point.distance_inches for point in self.point_distances)

    @property
    def minimum_move_satisfied(self) -> bool:
        return self.minimum_point_distance_inches + 1e-9 >= self.minimum_move_inches

    def to_payload(self) -> AircraftBaseMovementWitnessPayload:
        return {
            "model_id": self.model_id,
            "base": self.base.to_payload(),
            "start_pose": self.start_pose.to_payload(),
            "movement_end_pose": self.movement_end_pose.to_payload(),
            "minimum_move_inches": self.minimum_move_inches,
            "used_circular_center_shortcut": self.used_circular_center_shortcut,
            "point_distances": [point.to_payload() for point in self.point_distances],
            "minimum_point_distance_inches": self.minimum_point_distance_inches,
            "minimum_move_satisfied": self.minimum_move_satisfied,
        }

    @classmethod
    def from_payload(cls, payload: AircraftBaseMovementWitnessPayload) -> Self:
        witness = cls(
            model_id=payload["model_id"],
            base=base_shape_from_payload(payload["base"]),
            start_pose=Pose.from_payload(payload["start_pose"]),
            movement_end_pose=Pose.from_payload(payload["movement_end_pose"]),
            minimum_move_inches=payload["minimum_move_inches"],
            used_circular_center_shortcut=payload["used_circular_center_shortcut"],
            point_distances=tuple(
                BasePointDistanceWitness.from_payload(point) for point in payload["point_distances"]
            ),
        )
        payload_minimum = _validate_non_negative_number(
            "AircraftBaseMovementWitness minimum_point_distance_inches",
            payload["minimum_point_distance_inches"],
        )
        if not math.isclose(
            payload_minimum,
            witness.minimum_point_distance_inches,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise GeometryError("AircraftBaseMovementWitness minimum distance drift.")
        _validate_bool(
            "AircraftBaseMovementWitness minimum_move_satisfied",
            payload["minimum_move_satisfied"],
        )
        if payload["minimum_move_satisfied"] != witness.minimum_move_satisfied:
            raise GeometryError("AircraftBaseMovementWitness satisfaction drift.")
        return witness


@dataclass(frozen=True, slots=True)
class MovementSegment:
    model_id: str
    segment_index: int
    start_pose: Pose
    end_pose: Pose
    measurement_point: str
    distance_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_id",
            _validate_identifier("MovementSegment model_id", self.model_id),
        )
        object.__setattr__(
            self,
            "segment_index",
            _validate_non_negative_int("MovementSegment segment_index", self.segment_index),
        )
        object.__setattr__(
            self,
            "start_pose",
            validate_pose("MovementSegment start_pose", self.start_pose),
        )
        object.__setattr__(
            self,
            "end_pose",
            validate_pose("MovementSegment end_pose", self.end_pose),
        )
        object.__setattr__(
            self,
            "measurement_point",
            _validate_segment_measurement_point(self.measurement_point),
        )
        distance = _validate_non_negative_number(
            "MovementSegment distance_inches",
            self.distance_inches,
        )
        expected_distance = _same_point_segment_distance(self.start_pose, self.end_pose)
        if not math.isclose(distance, expected_distance, rel_tol=0.0, abs_tol=1e-9):
            raise GeometryError("MovementSegment distance_inches must match same-point distance.")
        object.__setattr__(self, "distance_inches", distance)

    @classmethod
    def from_poses(
        cls,
        *,
        model_id: str,
        segment_index: int,
        start_pose: Pose,
        end_pose: Pose,
    ) -> Self:
        return cls(
            model_id=model_id,
            segment_index=segment_index,
            start_pose=start_pose,
            end_pose=end_pose,
            measurement_point=_SEGMENT_MEASUREMENT_POINT,
            distance_inches=_same_point_segment_distance(start_pose, end_pose),
        )

    def to_payload(self) -> MovementSegmentPayload:
        return {
            "model_id": self.model_id,
            "segment_index": self.segment_index,
            "start_pose": self.start_pose.to_payload(),
            "end_pose": self.end_pose.to_payload(),
            "measurement_point": self.measurement_point,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: MovementSegmentPayload) -> Self:
        return cls(
            model_id=payload["model_id"],
            segment_index=payload["segment_index"],
            start_pose=Pose.from_payload(payload["start_pose"]),
            end_pose=Pose.from_payload(payload["end_pose"]),
            measurement_point=payload["measurement_point"],
            distance_inches=payload["distance_inches"],
        )


@dataclass(frozen=True, slots=True)
class PivotEvent:
    model_id: str
    pivot_index: int
    start_pose: Pose
    end_pose: Pose
    pivot_value_inches: float
    applied_cost_inches: float
    first_pivot_for_model: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_id",
            _validate_identifier("PivotEvent model_id", self.model_id),
        )
        object.__setattr__(
            self,
            "pivot_index",
            _validate_non_negative_int("PivotEvent pivot_index", self.pivot_index),
        )
        object.__setattr__(
            self,
            "start_pose",
            validate_pose("PivotEvent start_pose", self.start_pose),
        )
        object.__setattr__(
            self,
            "end_pose",
            validate_pose("PivotEvent end_pose", self.end_pose),
        )
        if self.start_pose.facing == self.end_pose.facing:
            raise GeometryError("PivotEvent requires a facing change.")
        pivot_value = _validate_non_negative_number(
            "PivotEvent pivot_value_inches",
            self.pivot_value_inches,
        )
        applied_cost = _validate_non_negative_number(
            "PivotEvent applied_cost_inches",
            self.applied_cost_inches,
        )
        _validate_bool("PivotEvent first_pivot_for_model", self.first_pivot_for_model)
        if applied_cost > pivot_value:
            raise GeometryError(
                "PivotEvent applied_cost_inches must not exceed pivot_value_inches."
            )
        if not self.first_pivot_for_model and applied_cost != 0.0:
            raise GeometryError("Only the first pivot for a model may apply pivot cost.")
        object.__setattr__(self, "pivot_value_inches", pivot_value)
        object.__setattr__(self, "applied_cost_inches", applied_cost)

    def to_payload(self) -> PivotEventPayload:
        return {
            "model_id": self.model_id,
            "pivot_index": self.pivot_index,
            "start_pose": self.start_pose.to_payload(),
            "end_pose": self.end_pose.to_payload(),
            "pivot_value_inches": self.pivot_value_inches,
            "applied_cost_inches": self.applied_cost_inches,
            "first_pivot_for_model": self.first_pivot_for_model,
        }

    @classmethod
    def from_payload(cls, payload: PivotEventPayload) -> Self:
        return cls(
            model_id=payload["model_id"],
            pivot_index=payload["pivot_index"],
            start_pose=Pose.from_payload(payload["start_pose"]),
            end_pose=Pose.from_payload(payload["end_pose"]),
            pivot_value_inches=payload["pivot_value_inches"],
            applied_cost_inches=payload["applied_cost_inches"],
            first_pivot_for_model=payload["first_pivot_for_model"],
        )


@dataclass(frozen=True, slots=True)
class MovementDistanceBudget:
    max_distance_inches: float
    straight_line_distance_inches: float
    pivot_cost_inches: float
    total_distance_inches: float
    remaining_distance_inches: float
    exceeded_by_inches: float

    def __post_init__(self) -> None:
        max_distance = _validate_non_negative_number(
            "MovementDistanceBudget max_distance_inches",
            self.max_distance_inches,
        )
        straight_line_distance = _validate_non_negative_number(
            "MovementDistanceBudget straight_line_distance_inches",
            self.straight_line_distance_inches,
        )
        pivot_cost = _validate_non_negative_number(
            "MovementDistanceBudget pivot_cost_inches",
            self.pivot_cost_inches,
        )
        total_distance = _validate_non_negative_number(
            "MovementDistanceBudget total_distance_inches",
            self.total_distance_inches,
        )
        remaining = _validate_non_negative_number(
            "MovementDistanceBudget remaining_distance_inches",
            self.remaining_distance_inches,
        )
        exceeded_by = _validate_non_negative_number(
            "MovementDistanceBudget exceeded_by_inches",
            self.exceeded_by_inches,
        )
        if not math.isclose(
            total_distance,
            straight_line_distance + pivot_cost,
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise GeometryError("MovementDistanceBudget total must equal segment plus pivot cost.")
        expected_remaining = max(max_distance - total_distance, 0.0)
        expected_exceeded = max(total_distance - max_distance, 0.0)
        if not math.isclose(remaining, expected_remaining, rel_tol=0.0, abs_tol=1e-9):
            raise GeometryError("MovementDistanceBudget remaining distance is inconsistent.")
        if not math.isclose(exceeded_by, expected_exceeded, rel_tol=0.0, abs_tol=1e-9):
            raise GeometryError("MovementDistanceBudget exceeded distance is inconsistent.")
        object.__setattr__(self, "max_distance_inches", max_distance)
        object.__setattr__(self, "straight_line_distance_inches", straight_line_distance)
        object.__setattr__(self, "pivot_cost_inches", pivot_cost)
        object.__setattr__(self, "total_distance_inches", total_distance)
        object.__setattr__(self, "remaining_distance_inches", remaining)
        object.__setattr__(self, "exceeded_by_inches", exceeded_by)

    @classmethod
    def from_totals(
        cls,
        *,
        max_distance_inches: float,
        straight_line_distance_inches: float,
        pivot_cost_inches: float,
    ) -> Self:
        total_distance = straight_line_distance_inches + pivot_cost_inches
        return cls(
            max_distance_inches=max_distance_inches,
            straight_line_distance_inches=straight_line_distance_inches,
            pivot_cost_inches=pivot_cost_inches,
            total_distance_inches=total_distance,
            remaining_distance_inches=max(max_distance_inches - total_distance, 0.0),
            exceeded_by_inches=max(total_distance - max_distance_inches, 0.0),
        )

    @property
    def is_within_budget(self) -> bool:
        return self.exceeded_by_inches == 0.0

    def to_payload(self) -> MovementDistanceBudgetPayload:
        return {
            "max_distance_inches": self.max_distance_inches,
            "straight_line_distance_inches": self.straight_line_distance_inches,
            "pivot_cost_inches": self.pivot_cost_inches,
            "total_distance_inches": self.total_distance_inches,
            "remaining_distance_inches": self.remaining_distance_inches,
            "exceeded_by_inches": self.exceeded_by_inches,
        }

    @classmethod
    def from_payload(cls, payload: MovementDistanceBudgetPayload) -> Self:
        return cls(
            max_distance_inches=payload["max_distance_inches"],
            straight_line_distance_inches=payload["straight_line_distance_inches"],
            pivot_cost_inches=payload["pivot_cost_inches"],
            total_distance_inches=payload["total_distance_inches"],
            remaining_distance_inches=payload["remaining_distance_inches"],
            exceeded_by_inches=payload["exceeded_by_inches"],
        )


@dataclass(frozen=True, slots=True)
class PivotCostPolicy:
    non_round_pivot_cost_inches: float = 1.0
    vehicle_or_monster_pivot_cost_inches: float = 2.0
    round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches: float = 2.0
    aircraft_pivot_cost_inches: float = 0.0
    round_base_large_vehicle_threshold_mm: float = 32.0
    vehicle_or_monster_model_ids: tuple[str, ...] = ()
    aircraft_model_ids: tuple[str, ...] = ()
    round_base_flying_stem_or_hover_stand_vehicle_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "non_round_pivot_cost_inches",
            _validate_non_negative_number(
                "PivotCostPolicy non_round_pivot_cost_inches",
                self.non_round_pivot_cost_inches,
            ),
        )
        object.__setattr__(
            self,
            "vehicle_or_monster_pivot_cost_inches",
            _validate_non_negative_number(
                "PivotCostPolicy vehicle_or_monster_pivot_cost_inches",
                self.vehicle_or_monster_pivot_cost_inches,
            ),
        )
        object.__setattr__(
            self,
            "round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches",
            _validate_non_negative_number(
                "PivotCostPolicy "
                "round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches",
                self.round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches,
            ),
        )
        object.__setattr__(
            self,
            "aircraft_pivot_cost_inches",
            _validate_non_negative_number(
                "PivotCostPolicy aircraft_pivot_cost_inches",
                self.aircraft_pivot_cost_inches,
            ),
        )
        object.__setattr__(
            self,
            "round_base_large_vehicle_threshold_mm",
            _validate_positive_number(
                "PivotCostPolicy round_base_large_vehicle_threshold_mm",
                self.round_base_large_vehicle_threshold_mm,
            ),
        )
        object.__setattr__(
            self,
            "vehicle_or_monster_model_ids",
            _validate_identifier_tuple(
                "PivotCostPolicy vehicle_or_monster_model_ids",
                self.vehicle_or_monster_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "aircraft_model_ids",
            _validate_identifier_tuple(
                "PivotCostPolicy aircraft_model_ids",
                self.aircraft_model_ids,
            ),
        )
        object.__setattr__(
            self,
            "round_base_flying_stem_or_hover_stand_vehicle_model_ids",
            _validate_identifier_tuple(
                "PivotCostPolicy round_base_flying_stem_or_hover_stand_vehicle_model_ids",
                self.round_base_flying_stem_or_hover_stand_vehicle_model_ids,
            ),
        )

    def pivot_value_for_model(self, model: Model) -> float:
        valid_model = _validate_model("PivotCostPolicy model", model)
        if valid_model.model_id in self.aircraft_model_ids:
            return self.aircraft_pivot_cost_inches
        if type(valid_model.base) is CircularBase:
            if (
                valid_model.model_id in self.round_base_flying_stem_or_hover_stand_vehicle_model_ids
                and _circular_base_diameter_mm(valid_model.base)
                > self.round_base_large_vehicle_threshold_mm
            ):
                return self.round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches
            return 0.0
        if valid_model.model_id in self.vehicle_or_monster_model_ids:
            return self.vehicle_or_monster_pivot_cost_inches
        return self.non_round_pivot_cost_inches

    def to_payload(self) -> PivotCostPolicyPayload:
        return {
            "non_round_pivot_cost_inches": self.non_round_pivot_cost_inches,
            "vehicle_or_monster_pivot_cost_inches": self.vehicle_or_monster_pivot_cost_inches,
            "round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches": (
                self.round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches
            ),
            "aircraft_pivot_cost_inches": self.aircraft_pivot_cost_inches,
            "round_base_large_vehicle_threshold_mm": self.round_base_large_vehicle_threshold_mm,
            "vehicle_or_monster_model_ids": list(self.vehicle_or_monster_model_ids),
            "aircraft_model_ids": list(self.aircraft_model_ids),
            "round_base_flying_stem_or_hover_stand_vehicle_model_ids": list(
                self.round_base_flying_stem_or_hover_stand_vehicle_model_ids
            ),
        }

    @classmethod
    def from_payload(cls, payload: PivotCostPolicyPayload) -> Self:
        return cls(
            non_round_pivot_cost_inches=payload["non_round_pivot_cost_inches"],
            vehicle_or_monster_pivot_cost_inches=payload["vehicle_or_monster_pivot_cost_inches"],
            round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches=payload[
                "round_base_large_flying_stem_or_hover_stand_vehicle_pivot_cost_inches"
            ],
            aircraft_pivot_cost_inches=payload["aircraft_pivot_cost_inches"],
            round_base_large_vehicle_threshold_mm=payload["round_base_large_vehicle_threshold_mm"],
            vehicle_or_monster_model_ids=tuple(payload["vehicle_or_monster_model_ids"]),
            aircraft_model_ids=tuple(payload["aircraft_model_ids"]),
            round_base_flying_stem_or_hover_stand_vehicle_model_ids=tuple(
                payload["round_base_flying_stem_or_hover_stand_vehicle_model_ids"]
            ),
        )


@dataclass(frozen=True, slots=True)
class MovementDistanceWitness:
    model_id: str
    segments: tuple[MovementSegment, ...]
    pivot_events: tuple[PivotEvent, ...] = ()
    budget: MovementDistanceBudget | None = None

    def __post_init__(self) -> None:
        model_id = _validate_identifier("MovementDistanceWitness model_id", self.model_id)
        segments = _validate_movement_segments("MovementDistanceWitness segments", self.segments)
        pivot_events = _validate_pivot_events(
            "MovementDistanceWitness pivot_events",
            self.pivot_events,
        )
        if not segments:
            raise GeometryError("MovementDistanceWitness segments must not be empty.")
        if any(segment.model_id != model_id for segment in segments):
            raise GeometryError("MovementDistanceWitness segments must match model_id.")
        if any(event.model_id != model_id for event in pivot_events):
            raise GeometryError("MovementDistanceWitness pivot events must match model_id.")
        expected_segment_indexes = tuple(range(len(segments)))
        if tuple(segment.segment_index for segment in segments) != expected_segment_indexes:
            raise GeometryError("MovementDistanceWitness segment indexes must be contiguous.")
        if tuple(sorted(event.pivot_index for event in pivot_events)) != tuple(
            event.pivot_index for event in pivot_events
        ):
            raise GeometryError("MovementDistanceWitness pivot events must be ordered.")
        _validate_segments_form_contiguous_path(segments)
        _validate_pivot_events_match_segments(
            model_id=model_id,
            segments=segments,
            pivot_events=pivot_events,
        )
        if self.budget is not None:
            if type(self.budget) is not MovementDistanceBudget:
                raise GeometryError("MovementDistanceWitness budget must be a budget.")
            if not math.isclose(
                self.budget.straight_line_distance_inches,
                sum(segment.distance_inches for segment in segments),
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise GeometryError("MovementDistanceWitness budget segment distance drift.")
            if not math.isclose(
                self.budget.pivot_cost_inches,
                sum(event.applied_cost_inches for event in pivot_events),
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise GeometryError("MovementDistanceWitness budget pivot distance drift.")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "segments", segments)
        object.__setattr__(self, "pivot_events", pivot_events)

    @classmethod
    def for_model_path(
        cls,
        *,
        model: Model,
        poses: tuple[Pose, ...],
        pivot_cost_policy: PivotCostPolicy,
        max_distance_inches: float | None = None,
    ) -> Self:
        valid_model = _validate_model("MovementDistanceWitness model", model)
        path = _validate_pose_path("MovementDistanceWitness poses", poses)
        if type(pivot_cost_policy) is not PivotCostPolicy:
            raise GeometryError("MovementDistanceWitness pivot_cost_policy must be a policy.")
        pivot_value = pivot_cost_policy.pivot_value_for_model(valid_model)
        segments = tuple(
            MovementSegment.from_poses(
                model_id=valid_model.model_id,
                segment_index=segment_index,
                start_pose=start_pose,
                end_pose=end_pose,
            )
            for segment_index, (start_pose, end_pose) in enumerate(pairwise(path))
        )
        pivot_events: list[PivotEvent] = []
        pivot_already_paid = False
        for pivot_index, (start_pose, end_pose) in enumerate(pairwise(path)):
            if start_pose.facing == end_pose.facing:
                continue
            first_pivot = not pivot_already_paid
            pivot_events.append(
                PivotEvent(
                    model_id=valid_model.model_id,
                    pivot_index=pivot_index,
                    start_pose=start_pose,
                    end_pose=end_pose,
                    pivot_value_inches=pivot_value,
                    applied_cost_inches=pivot_value if first_pivot else 0.0,
                    first_pivot_for_model=first_pivot,
                )
            )
            pivot_already_paid = True
        straight_line_distance = sum(segment.distance_inches for segment in segments)
        pivot_cost = sum(event.applied_cost_inches for event in pivot_events)
        budget = (
            None
            if max_distance_inches is None
            else MovementDistanceBudget.from_totals(
                max_distance_inches=max_distance_inches,
                straight_line_distance_inches=straight_line_distance,
                pivot_cost_inches=pivot_cost,
            )
        )
        return cls(
            model_id=valid_model.model_id,
            segments=segments,
            pivot_events=tuple(pivot_events),
            budget=budget,
        )

    @property
    def straight_line_distance_inches(self) -> float:
        return sum(segment.distance_inches for segment in self.segments)

    @property
    def pivot_cost_inches(self) -> float:
        return sum(event.applied_cost_inches for event in self.pivot_events)

    @property
    def total_distance_inches(self) -> float:
        return self.straight_line_distance_inches + self.pivot_cost_inches

    @property
    def is_within_budget(self) -> bool:
        return self.budget is None or self.budget.is_within_budget

    def to_payload(self) -> MovementDistanceWitnessPayload:
        return {
            "model_id": self.model_id,
            "segments": [segment.to_payload() for segment in self.segments],
            "pivot_events": [event.to_payload() for event in self.pivot_events],
            "budget": None if self.budget is None else self.budget.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MovementDistanceWitnessPayload) -> Self:
        budget_payload = payload["budget"]
        return cls(
            model_id=payload["model_id"],
            segments=tuple(
                MovementSegment.from_payload(segment) for segment in payload["segments"]
            ),
            pivot_events=tuple(PivotEvent.from_payload(event) for event in payload["pivot_events"]),
            budget=(
                None
                if budget_payload is None
                else MovementDistanceBudget.from_payload(budget_payload)
            ),
        )


def _new_pivot_cost_policy() -> PivotCostPolicy:
    return PivotCostPolicy()


@dataclass(frozen=True, slots=True)
class MovementEnvelope:
    max_distance_inches: float
    sample_interval_inches: float = 1.0
    coherency_horizontal_inches: float = 2.0
    coherency_vertical_inches: float = 5.0
    required_coherency_neighbors: int = 1
    engagement_horizontal_inches: float = 1.0
    engagement_vertical_inches: float = 5.0
    pivot_cost_policy: PivotCostPolicy = field(default_factory=_new_pivot_cost_policy)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "max_distance_inches",
            _validate_positive_number(
                "MovementEnvelope max_distance_inches",
                self.max_distance_inches,
            ),
        )
        object.__setattr__(
            self,
            "sample_interval_inches",
            _validate_positive_number(
                "MovementEnvelope sample_interval_inches",
                self.sample_interval_inches,
            ),
        )
        object.__setattr__(
            self,
            "coherency_horizontal_inches",
            _validate_non_negative_number(
                "MovementEnvelope coherency_horizontal_inches",
                self.coherency_horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "coherency_vertical_inches",
            _validate_non_negative_number(
                "MovementEnvelope coherency_vertical_inches",
                self.coherency_vertical_inches,
            ),
        )
        object.__setattr__(
            self,
            "engagement_horizontal_inches",
            _validate_non_negative_number(
                "MovementEnvelope engagement_horizontal_inches",
                self.engagement_horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "engagement_vertical_inches",
            _validate_non_negative_number(
                "MovementEnvelope engagement_vertical_inches",
                self.engagement_vertical_inches,
            ),
        )
        object.__setattr__(
            self,
            "required_coherency_neighbors",
            _validate_positive_int(
                "MovementEnvelope required_coherency_neighbors",
                self.required_coherency_neighbors,
            ),
        )
        if type(self.pivot_cost_policy) is not PivotCostPolicy:
            raise GeometryError("MovementEnvelope pivot_cost_policy must be a PivotCostPolicy.")

    def path_distance(self, poses: tuple[Pose, ...], *, model: Model | None = None) -> float:
        path = _validate_pose_path("poses", poses)
        if model is not None:
            return self.movement_distance_witness(model=model, poses=path).total_distance_inches
        distance = 0.0
        previous = path[0]
        for pose in path[1:]:
            distance += _same_point_segment_distance(previous, pose)
            previous = pose
        return distance

    def movement_distance_witness(
        self,
        *,
        model: Model,
        poses: tuple[Pose, ...],
    ) -> MovementDistanceWitness:
        return MovementDistanceWitness.for_model_path(
            model=model,
            poses=poses,
            pivot_cost_policy=self.pivot_cost_policy,
            max_distance_inches=self.max_distance_inches,
        )

    def sampled_path(self, poses: tuple[Pose, ...]) -> tuple[Pose, ...]:
        path = _validate_pose_path("poses", poses)
        sampled: list[Pose] = [path[0]]
        previous = path[0]
        for pose in path[1:]:
            distance = previous.distance_3d_to(pose)
            steps = max(1, math.ceil(distance / self.sample_interval_inches))
            for step in range(1, steps + 1):
                sampled.append(_interpolate_pose(previous, pose, step / steps))
            previous = pose
        return tuple(sampled)

    def models_are_coherent(self, models: tuple[Model, ...]) -> bool:
        if type(models) is not tuple:
            raise GeometryError("MovementEnvelope models must be a tuple.")
        valid_models = tuple(_validate_model("MovementEnvelope model", model) for model in models)
        if len(valid_models) < 2:
            return True

        for model in valid_models:
            coherent_neighbors = sum(
                model.model_id != other.model_id and self._models_are_coherent_pair(model, other)
                for other in valid_models
            )
            if coherent_neighbors < self.required_coherency_neighbors:
                return False
        return True

    def to_payload(self) -> MovementEnvelopePayload:
        return {
            "max_distance_inches": self.max_distance_inches,
            "sample_interval_inches": self.sample_interval_inches,
            "coherency_horizontal_inches": self.coherency_horizontal_inches,
            "coherency_vertical_inches": self.coherency_vertical_inches,
            "required_coherency_neighbors": self.required_coherency_neighbors,
            "engagement_horizontal_inches": self.engagement_horizontal_inches,
            "engagement_vertical_inches": self.engagement_vertical_inches,
            "pivot_cost_policy": self.pivot_cost_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MovementEnvelopePayload) -> Self:
        return cls(
            max_distance_inches=payload["max_distance_inches"],
            sample_interval_inches=payload["sample_interval_inches"],
            coherency_horizontal_inches=payload["coherency_horizontal_inches"],
            coherency_vertical_inches=payload["coherency_vertical_inches"],
            required_coherency_neighbors=payload["required_coherency_neighbors"],
            engagement_horizontal_inches=payload["engagement_horizontal_inches"],
            engagement_vertical_inches=payload["engagement_vertical_inches"],
            pivot_cost_policy=PivotCostPolicy.from_payload(payload["pivot_cost_policy"]),
        )

    def _models_are_coherent_pair(self, first: Model, second: Model) -> bool:
        return (
            first.base_distance_to(second) <= self.coherency_horizontal_inches
            and first.volume.vertical_gap_to(first.pose, second.volume, second.pose)
            <= self.coherency_vertical_inches
        )


def _validate_pose_path(field_name: str, value: object) -> tuple[Pose, ...]:
    if type(value) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple of Pose values.")
    pose_values = cast(tuple[object, ...], value)
    path = tuple(validate_pose(f"{field_name} pose", pose) for pose in pose_values)
    if len(path) < 2:
        raise GeometryError(f"{field_name} must contain at least two poses.")
    return path


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_base_point_distance_witnesses(
    field_name: str,
    values: object,
) -> tuple[BasePointDistanceWitness, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    witnesses: list[BasePointDistanceWitness] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not BasePointDistanceWitness:
            raise GeometryError(f"{field_name} must contain BasePointDistanceWitness values.")
        if value.point_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate point IDs.")
        seen.add(value.point_id)
        witnesses.append(value)
    if not witnesses:
        raise GeometryError(f"{field_name} must not be empty.")
    return tuple(witnesses)


def _validate_movement_segments(
    field_name: str,
    values: object,
) -> tuple[MovementSegment, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_movement_segment(f"{field_name} segment", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_movement_segment(field_name: str, value: object) -> MovementSegment:
    if type(value) is not MovementSegment:
        raise GeometryError(f"{field_name} must be a MovementSegment.")
    return value


def _validate_pivot_events(field_name: str, values: object) -> tuple[PivotEvent, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_pivot_event(f"{field_name} pivot_event", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_pivot_event(field_name: str, value: object) -> PivotEvent:
    if type(value) is not PivotEvent:
        raise GeometryError(f"{field_name} must be a PivotEvent.")
    return value


def _validate_segments_form_contiguous_path(segments: tuple[MovementSegment, ...]) -> None:
    for previous, current in pairwise(segments):
        if previous.end_pose != current.start_pose:
            raise GeometryError("MovementDistanceWitness segments must form a contiguous path.")


def _validate_pivot_events_match_segments(
    *,
    model_id: str,
    segments: tuple[MovementSegment, ...],
    pivot_events: tuple[PivotEvent, ...],
) -> None:
    pivot_by_index = {event.pivot_index: event for event in pivot_events}
    if len(pivot_by_index) != len(pivot_events):
        raise GeometryError(
            "MovementDistanceWitness pivot events must not contain duplicate indexes."
        )
    expected_indexes = tuple(
        segment.segment_index
        for segment in segments
        if segment.start_pose.facing != segment.end_pose.facing
    )
    if tuple(event.pivot_index for event in pivot_events) != expected_indexes:
        raise GeometryError(
            "MovementDistanceWitness pivot events must match facing-change segments."
        )
    for event in pivot_events:
        if event.pivot_index >= len(segments):
            raise GeometryError("MovementDistanceWitness pivot event index is out of range.")
        segment = segments[event.pivot_index]
        if event.model_id != model_id:
            raise GeometryError("MovementDistanceWitness pivot event model_id mismatch.")
        if event.start_pose != segment.start_pose or event.end_pose != segment.end_pose:
            raise GeometryError(
                "MovementDistanceWitness pivot event poses must match segment poses."
            )
    if not pivot_events:
        return
    first = pivot_events[0]
    if not first.first_pivot_for_model:
        raise GeometryError("First pivot event must be marked first_pivot_for_model.")
    if not math.isclose(
        first.applied_cost_inches,
        first.pivot_value_inches,
        rel_tol=0.0,
        abs_tol=1e-9,
    ):
        raise GeometryError("First pivot event must apply the full pivot value.")
    for event in pivot_events[1:]:
        if event.first_pivot_for_model:
            raise GeometryError("Only one pivot event may be first_pivot_for_model.")
        if event.applied_cost_inches != 0.0:
            raise GeometryError("Only first pivot event may apply pivot cost.")


def _validate_positive_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return number


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number < 0.0:
        raise GeometryError(f"{field_name} must not be negative.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 1:
        raise GeometryError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 0:
        raise GeometryError(f"{field_name} must not be negative.")
    return value


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GeometryError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GeometryError(f"{field_name} must not be empty.")
    return stripped


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    identifiers: list[str] = []
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GeometryError(f"{field_name} must not contain duplicate identifiers.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_bool(field_name: str, value: object) -> None:
    if type(value) is not bool:
        raise GeometryError(f"{field_name} must be a bool.")


def _validate_segment_measurement_point(value: object) -> str:
    measurement_point = _validate_identifier("MovementSegment measurement_point", value)
    if measurement_point != _SEGMENT_MEASUREMENT_POINT:
        raise GeometryError("MovementSegment measurement_point must be pose_anchor.")
    return measurement_point


def _same_point_segment_distance(start: Pose, end: Pose) -> float:
    start_pose = validate_pose("start", start)
    end_pose = validate_pose("end", end)
    return start_pose.distance_3d_to(end_pose)


def _base_point_movements(
    *,
    base: BaseShape,
    start_pose: Pose,
    movement_end_pose: Pose,
) -> tuple[tuple[str, float, float, float, float], ...]:
    valid_base = validate_base_shape("base", base)
    start = validate_pose("start_pose", start_pose)
    end = validate_pose("movement_end_pose", movement_end_pose)
    movements: list[tuple[str, float, float, float, float]] = []
    for point_id, local_x, local_y in _base_point_offsets(valid_base):
        start_x, start_y = _world_point_from_local_offset(
            pose=start,
            local_x=local_x,
            local_y=local_y,
        )
        end_x, end_y = _world_point_from_local_offset(
            pose=end,
            local_x=local_x,
            local_y=local_y,
        )
        movements.append((point_id, start_x, start_y, end_x, end_y))
    return tuple(movements)


def _base_point_offsets(base: BaseShape) -> tuple[tuple[str, float, float], ...]:
    valid_base = validate_base_shape("base", base)
    if type(valid_base) is CircularBase:
        return (("center", 0.0, 0.0),)
    if type(valid_base) is RectangularBase:
        half_length = valid_base.length / 2.0
        half_width = valid_base.width / 2.0
        fixed_offsets = (
            ("corner_back_left", -half_length, -half_width),
            ("corner_back_right", -half_length, half_width),
            ("corner_front_left", half_length, -half_width),
            ("corner_front_right", half_length, half_width),
            ("edge_back", -half_length, 0.0),
            ("edge_front", half_length, 0.0),
            ("edge_left", 0.0, -half_width),
            ("edge_right", 0.0, half_width),
            ("center", 0.0, 0.0),
        )
        radial_offsets = tuple(
            _radial_base_point_offset(base=valid_base, angle_degrees=angle_degrees)
            for angle_degrees in _AIRCRAFT_BASE_POINT_SAMPLE_DEGREES
        )
        return (*fixed_offsets, *radial_offsets)
    radial_offsets = tuple(
        _radial_base_point_offset(base=valid_base, angle_degrees=angle_degrees)
        for angle_degrees in _AIRCRAFT_BASE_POINT_SAMPLE_DEGREES
    )
    return (("center", 0.0, 0.0), *radial_offsets)


def _radial_base_point_offset(
    *,
    base: BaseShape,
    angle_degrees: int,
) -> tuple[str, float, float]:
    angle = validate_finite_number("angle_degrees", angle_degrees)
    angle_radians = math.radians(angle)
    if type(base) is OvalBase:
        local_x = (base.length / 2.0) * math.cos(angle_radians)
        local_y = (base.width / 2.0) * math.sin(angle_radians)
    else:
        radius = base.radius_at_angle(angle, Facing(0.0))
        local_x = radius * math.cos(angle_radians)
        local_y = radius * math.sin(angle_radians)
    return (f"radial_{angle_degrees:03d}", local_x, local_y)


def _world_point_from_local_offset(
    *,
    pose: Pose,
    local_x: float,
    local_y: float,
) -> tuple[float, float]:
    valid_pose = validate_pose("pose", pose)
    valid_local_x = validate_finite_number("local_x", local_x)
    valid_local_y = validate_finite_number("local_y", local_y)
    facing_radians = math.radians(valid_pose.facing.degrees)
    cos_facing = math.cos(facing_radians)
    sin_facing = math.sin(facing_radians)
    return (
        valid_pose.position.x + (valid_local_x * cos_facing) - (valid_local_y * sin_facing),
        valid_pose.position.y + (valid_local_x * sin_facing) + (valid_local_y * cos_facing),
    )


def _circular_base_diameter_mm(base: CircularBase) -> float:
    return base.radius * 2.0 * MILLIMETERS_PER_INCH


def _interpolate_pose(start: Pose, end: Pose, t: float) -> Pose:
    return Pose(
        position=Point3(
            x=_interpolate(start.position.x, end.position.x, t),
            y=_interpolate(start.position.y, end.position.y, t),
            z=_interpolate(start.position.z, end.position.z, t),
        ),
        facing=Facing(
            _interpolate(start.facing.degrees, end.facing.degrees, t),
        ),
    )


def _interpolate(start: float, end: float, t: float) -> float:
    return start + ((end - start) * t)
