from __future__ import annotations

import math
from collections.abc import Generator
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from fractions import Fraction
from itertools import pairwise
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.geometry.milli_inch import (
    DistancePrecisionError,
    inches_to_ticks,
    squared_inches_to_ticks,
    ticks_to_inches,
)
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


class MovementDistanceUnresolvedError(GeometryError):
    """A bounded full-path measurement could not certify its budget value."""


class MovementSegmentPayload(TypedDict):
    model_id: str
    segment_index: int
    start_pose: PosePayload
    end_pose: PosePayload
    measurement_point: str
    distance_inches: float


class RotationEventPayload(TypedDict):
    model_id: str
    rotation_index: int
    start_pose: PosePayload
    end_pose: PosePayload
    facing_delta_degrees: float


class MovementDistanceBudgetPayload(TypedDict):
    max_distance_inches: float
    straight_line_distance_inches: float
    total_distance_inches: float
    remaining_distance_inches: float
    exceeded_by_inches: float


class MovementDistanceWitnessPayload(TypedDict):
    model_id: str
    segments: list[MovementSegmentPayload]
    rotation_events: list[RotationEventPayload]
    budget: MovementDistanceBudgetPayload | None


class MovementEnvelopePayload(TypedDict):
    max_distance_inches: float
    sample_interval_inches: float
    coherency_horizontal_inches: float
    coherency_vertical_inches: float
    required_coherency_neighbors: int
    engagement_horizontal_inches: float
    engagement_vertical_inches: float


def _movement_budget_components(
    *,
    max_distance: float,
    total_distance: float,
) -> tuple[float, float]:
    return max(0.0, max_distance - total_distance), max(0.0, total_distance - max_distance)


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
class RotationEvent:
    model_id: str
    rotation_index: int
    start_pose: Pose
    end_pose: Pose
    facing_delta_degrees: float

    def __post_init__(self) -> None:
        model_id = _validate_identifier("RotationEvent model_id", self.model_id)
        rotation_index = _validate_non_negative_int(
            "RotationEvent rotation_index",
            self.rotation_index,
        )
        start_pose = validate_pose("RotationEvent start_pose", self.start_pose)
        end_pose = validate_pose("RotationEvent end_pose", self.end_pose)
        if start_pose.facing == end_pose.facing:
            raise GeometryError("RotationEvent requires a facing change.")
        facing_delta = _validate_non_negative_number(
            "RotationEvent facing_delta_degrees",
            self.facing_delta_degrees,
        )
        expected_delta = _facing_delta_degrees(start_pose, end_pose)
        if not math.isclose(facing_delta, expected_delta, rel_tol=0.0, abs_tol=1e-9):
            raise GeometryError("RotationEvent facing_delta_degrees drift.")
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "rotation_index", rotation_index)
        object.__setattr__(self, "start_pose", start_pose)
        object.__setattr__(self, "end_pose", end_pose)
        object.__setattr__(self, "facing_delta_degrees", facing_delta)

    def to_payload(self) -> RotationEventPayload:
        return {
            "model_id": self.model_id,
            "rotation_index": self.rotation_index,
            "start_pose": self.start_pose.to_payload(),
            "end_pose": self.end_pose.to_payload(),
            "facing_delta_degrees": self.facing_delta_degrees,
        }

    @classmethod
    def from_payload(cls, payload: RotationEventPayload) -> Self:
        return cls(
            model_id=payload["model_id"],
            rotation_index=payload["rotation_index"],
            start_pose=Pose.from_payload(payload["start_pose"]),
            end_pose=Pose.from_payload(payload["end_pose"]),
            facing_delta_degrees=payload["facing_delta_degrees"],
        )


@dataclass(frozen=True, slots=True)
class MovementDistanceBudget:
    max_distance_inches: float
    straight_line_distance_inches: float
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
        if total_distance != float(ticks_to_inches(inches_to_ticks(total_distance))):
            raise GeometryError("MovementDistanceBudget total must be in whole milli-inches.")
        # A rounded path budget can straddle a midpoint with its raw float sum.
        # Allow float error from the component differences, norms and sum here.
        tolerance = 4 * max(math.ulp(straight_line_distance), math.ulp(total_distance))
        if abs(straight_line_distance - total_distance) > 0.0005 + tolerance:
            raise GeometryError("MovementDistanceBudget total does not match the scalar distance.")
        expected_remaining, expected_exceeded = _movement_budget_components(
            max_distance=max_distance,
            total_distance=total_distance,
        )
        if remaining != expected_remaining:
            raise GeometryError("MovementDistanceBudget remaining distance is inconsistent.")
        if exceeded_by != expected_exceeded:
            raise GeometryError("MovementDistanceBudget exceeded distance is inconsistent.")
        object.__setattr__(self, "max_distance_inches", max_distance)
        object.__setattr__(self, "straight_line_distance_inches", straight_line_distance)
        object.__setattr__(self, "total_distance_inches", total_distance)
        object.__setattr__(self, "remaining_distance_inches", remaining)
        object.__setattr__(self, "exceeded_by_inches", exceeded_by)

    @classmethod
    def for_segments(
        cls,
        *,
        max_distance_inches: float,
        segments: tuple[MovementSegment, ...],
    ) -> Self:
        return cls._from_measurement(
            max_distance_inches=max_distance_inches,
            straight_line_distance_inches=sum(segment.distance_inches for segment in segments),
            total_distance_inches=_rounded_path_inches(segments),
        )

    @classmethod
    def from_totals(
        cls, *, max_distance_inches: float, straight_line_distance_inches: float
    ) -> Self:
        """Build a budget from a supplied complete scalar measurement."""
        return cls._from_measurement(
            max_distance_inches=max_distance_inches,
            straight_line_distance_inches=straight_line_distance_inches,
            total_distance_inches=float(
                ticks_to_inches(inches_to_ticks(straight_line_distance_inches))
            ),
        )

    @classmethod
    def _from_measurement(
        cls,
        *,
        max_distance_inches: float,
        straight_line_distance_inches: float,
        total_distance_inches: float,
    ) -> Self:
        remaining, exceeded = _movement_budget_components(
            max_distance=max_distance_inches,
            total_distance=total_distance_inches,
        )
        return cls(
            max_distance_inches=max_distance_inches,
            straight_line_distance_inches=straight_line_distance_inches,
            total_distance_inches=total_distance_inches,
            remaining_distance_inches=remaining,
            exceeded_by_inches=exceeded,
        )

    @property
    def is_within_budget(self) -> bool:
        return self.exceeded_by_inches == 0.0

    def to_payload(self) -> MovementDistanceBudgetPayload:
        return {
            "max_distance_inches": self.max_distance_inches,
            "straight_line_distance_inches": self.straight_line_distance_inches,
            "total_distance_inches": self.total_distance_inches,
            "remaining_distance_inches": self.remaining_distance_inches,
            "exceeded_by_inches": self.exceeded_by_inches,
        }

    @classmethod
    def from_payload(cls, payload: MovementDistanceBudgetPayload) -> Self:
        if type(cast(object, payload)) is not dict or set(payload) != set(
            MovementDistanceBudgetPayload.__annotations__
        ):
            raise GeometryError("MovementDistanceBudget has incompatible fields.")
        return cls(
            max_distance_inches=payload["max_distance_inches"],
            straight_line_distance_inches=payload["straight_line_distance_inches"],
            total_distance_inches=payload["total_distance_inches"],
            remaining_distance_inches=payload["remaining_distance_inches"],
            exceeded_by_inches=payload["exceeded_by_inches"],
        )


@dataclass(frozen=True, slots=True)
class MovementDistanceWitness:
    model_id: str
    segments: tuple[MovementSegment, ...]
    rotation_events: tuple[RotationEvent, ...] = ()
    max_distance_inches: float | None = None
    budget: MovementDistanceBudget | None = field(init=False)

    def __post_init__(self) -> None:
        model_id = _validate_identifier("MovementDistanceWitness model_id", self.model_id)
        segments = _validate_movement_segments("MovementDistanceWitness segments", self.segments)
        rotation_events = _validate_rotation_events(
            "MovementDistanceWitness rotation_events",
            self.rotation_events,
        )
        if not segments:
            raise GeometryError("MovementDistanceWitness segments must not be empty.")
        if any(segment.model_id != model_id for segment in segments):
            raise GeometryError("MovementDistanceWitness segments must match model_id.")
        if any(event.model_id != model_id for event in rotation_events):
            raise GeometryError("MovementDistanceWitness rotation events must match model_id.")
        expected_segment_indexes = tuple(range(len(segments)))
        if tuple(segment.segment_index for segment in segments) != expected_segment_indexes:
            raise GeometryError("MovementDistanceWitness segment indexes must be contiguous.")
        if tuple(sorted(event.rotation_index for event in rotation_events)) != tuple(
            event.rotation_index for event in rotation_events
        ):
            raise GeometryError("MovementDistanceWitness rotation events must be ordered.")
        _validate_segments_form_contiguous_path(segments)
        _validate_rotation_events_match_segments(
            model_id=model_id,
            segments=segments,
            rotation_events=rotation_events,
        )
        budget = (
            None
            if self.max_distance_inches is None
            else MovementDistanceBudget.for_segments(
                max_distance_inches=self.max_distance_inches, segments=segments
            )
        )
        object.__setattr__(
            self, "max_distance_inches", None if budget is None else budget.max_distance_inches
        )
        object.__setattr__(self, "budget", budget)
        object.__setattr__(self, "model_id", model_id)
        object.__setattr__(self, "segments", segments)
        object.__setattr__(self, "rotation_events", rotation_events)

    @classmethod
    def for_model_path(
        cls,
        *,
        model: Model,
        poses: tuple[Pose, ...],
        max_distance_inches: float | None = None,
    ) -> Self:
        valid_model = _validate_model("MovementDistanceWitness model", model)
        path = _validate_pose_path("MovementDistanceWitness poses", poses)
        scope = _CERTIFICATES.get() if len(path) > 2 else None
        cache = None if scope is None else scope.witnesses
        key = None
        if cache is not None and max_distance_inches is not None:
            limit = _validate_non_negative_number(
                "MovementDistanceWitness max_distance_inches", max_distance_inches
            )
            key = (valid_model.model_id, path, limit)
            if key in cache:
                return cast(Self, cache[key])
        segments = tuple(
            MovementSegment.from_poses(
                model_id=valid_model.model_id,
                segment_index=segment_index,
                start_pose=start_pose,
                end_pose=end_pose,
            )
            for segment_index, (start_pose, end_pose) in enumerate(pairwise(path))
        )
        rotation_events: list[RotationEvent] = []
        for rotation_index, (start_pose, end_pose) in enumerate(pairwise(path)):
            if start_pose.facing == end_pose.facing:
                continue
            rotation_events.append(
                RotationEvent(
                    model_id=valid_model.model_id,
                    rotation_index=rotation_index,
                    start_pose=start_pose,
                    end_pose=end_pose,
                    facing_delta_degrees=_facing_delta_degrees(start_pose, end_pose),
                )
            )
        witness = cls(
            model_id=valid_model.model_id,
            segments=segments,
            rotation_events=tuple(rotation_events),
            max_distance_inches=max_distance_inches,
        )
        if cache is not None and key is not None:
            cache[key] = witness
        return witness

    @property
    def straight_line_distance_inches(self) -> float:
        return sum(segment.distance_inches for segment in self.segments)

    @property
    def total_distance_inches(self) -> float:
        return self.straight_line_distance_inches

    @property
    def is_within_budget(self) -> bool:
        return self.budget is None or self.budget.is_within_budget

    def to_payload(self) -> MovementDistanceWitnessPayload:
        return {
            "model_id": self.model_id,
            "segments": [segment.to_payload() for segment in self.segments],
            "rotation_events": [event.to_payload() for event in self.rotation_events],
            "budget": None if self.budget is None else self.budget.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MovementDistanceWitnessPayload) -> Self:
        witness = cls.from_certified_payload(payload)
        if witness.budget is not None and witness.budget != MovementDistanceBudget.for_segments(
            max_distance_inches=witness.budget.max_distance_inches, segments=witness.segments
        ):
            raise GeometryError("MovementDistanceWitness budget does not match the measured path.")
        return witness

    @classmethod
    def from_certified_payload(cls, payload: MovementDistanceWitnessPayload) -> Self:
        """Read an engine-certified witness from a live continuation or event."""
        witness = cls(
            model_id=payload["model_id"],
            segments=tuple(
                MovementSegment.from_payload(segment) for segment in payload["segments"]
            ),
            rotation_events=tuple(
                RotationEvent.from_payload(event) for event in payload["rotation_events"]
            ),
        )
        if (budget_payload := payload["budget"]) is not None:
            budget = MovementDistanceBudget.from_payload(budget_payload)
            if budget.straight_line_distance_inches != witness.straight_line_distance_inches:
                raise GeometryError(
                    "MovementDistanceWitness budget does not match the segment sum."
                )
            object.__setattr__(witness, "max_distance_inches", budget.max_distance_inches)
            object.__setattr__(witness, "budget", budget)
        return witness


class _MovementCertificates:
    def __init__(self) -> None:
        self.witnesses: dict[tuple[str, tuple[Pose, ...], float], MovementDistanceWitness] = {}
        self.lengths: dict[tuple[Point3, ...], float] = {}


_CERTIFICATES: ContextVar[_MovementCertificates | None] = ContextVar(
    "movement_certificates", default=None
)


@contextmanager
def reuse_movement_certificates() -> Generator[None]:
    """Reuse successful certificates only within one prospective decision."""
    token = _CERTIFICATES.set(_MovementCertificates())
    try:
        yield
    finally:
        _CERTIFICATES.reset(token)


def _rounded_path_inches(segments: tuple[MovementSegment, ...]) -> float:
    positions = (
        segments[0].start_pose.position,
        *(segment.end_pose.position for segment in segments),
    )
    scope = _CERTIFICATES.get() if len(segments) > 1 else None
    if scope is None:
        return _measure_path_inches(positions)
    if positions not in scope.lengths:
        scope.lengths[positions] = _measure_path_inches(positions)
    return scope.lengths[positions]


def _measure_path_inches(positions: tuple[Point3, ...]) -> float:
    squares: list[Fraction] = []
    for start, end in pairwise(positions):
        if start != end:
            dx = Fraction(end.x) - Fraction(start.x)
            dy = Fraction(end.y) - Fraction(start.y)
            dz = Fraction(end.z) - Fraction(start.z)
            squares.append(dx * dx + dy * dy + dz * dz)
    if not squares:
        return 0.0
    if len(squares) == 1:
        return float(ticks_to_inches(squared_inches_to_ticks(squares[0])))
    from warhammer40k_core.geometry.milli_inch_symbolic import (
        UnresolvedDistanceMeasurementError,
        symbolic_squared_path_inches_to_ticks,
    )

    try:
        return float(ticks_to_inches(symbolic_squared_path_inches_to_ticks(squares)))
    except UnresolvedDistanceMeasurementError as exc:
        raise MovementDistanceUnresolvedError(
            "Could not certify the whole-path movement budget distance."
        ) from exc
    except DistancePrecisionError as exc:
        raise GeometryError("Could not certify the whole-path movement budget distance.") from exc


@dataclass(frozen=True, slots=True)
class MovementEnvelope:
    max_distance_inches: float
    coherency_horizontal_inches: float
    coherency_vertical_inches: float
    engagement_horizontal_inches: float
    engagement_vertical_inches: float
    sample_interval_inches: float = 1.0
    required_coherency_neighbors: int = 1

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
        if len(valid_models) - 1 < self.required_coherency_neighbors:
            return False

        coherent_neighbor_counts = [0 for _model in valid_models]
        for index, first in enumerate(valid_models):
            for other_index in range(index + 1, len(valid_models)):
                second = valid_models[other_index]
                if (
                    coherent_neighbor_counts[index] >= self.required_coherency_neighbors
                    and coherent_neighbor_counts[other_index] >= self.required_coherency_neighbors
                ):
                    continue
                if self._models_are_coherent_pair(first, second):
                    coherent_neighbor_counts[index] += 1
                    coherent_neighbor_counts[other_index] += 1
            if coherent_neighbor_counts[index] < self.required_coherency_neighbors:
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
        )

    def _models_are_coherent_pair(self, first: Model, second: Model) -> bool:
        if (
            first.volume.vertical_gap_to(first.pose, second.volume, second.pose)
            > self.coherency_vertical_inches
        ):
            return False
        if not _model_pair_can_be_within_horizontal_distance(
            first,
            second,
            horizontal_inches=self.coherency_horizontal_inches,
        ):
            return False
        return first.base_distance_to(second) <= self.coherency_horizontal_inches


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


def _model_pair_can_be_within_horizontal_distance(
    first: Model,
    second: Model,
    *,
    horizontal_inches: float,
) -> bool:
    center_distance = first.pose.distance_2d_to(second.pose)
    return center_distance <= (
        first.base.max_radius() + second.base.max_radius() + horizontal_inches
    )


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


def _validate_rotation_events(field_name: str, values: object) -> tuple[RotationEvent, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    return tuple(
        _validate_rotation_event(f"{field_name} rotation_event", value)
        for value in cast(tuple[object, ...], values)
    )


def _validate_rotation_event(field_name: str, value: object) -> RotationEvent:
    if type(value) is not RotationEvent:
        raise GeometryError(f"{field_name} must be a RotationEvent.")
    return value


def _validate_segments_form_contiguous_path(segments: tuple[MovementSegment, ...]) -> None:
    for previous, current in pairwise(segments):
        if previous.end_pose != current.start_pose:
            raise GeometryError("MovementDistanceWitness segments must form a contiguous path.")


def _validate_rotation_events_match_segments(
    *,
    model_id: str,
    segments: tuple[MovementSegment, ...],
    rotation_events: tuple[RotationEvent, ...],
) -> None:
    rotation_by_index = {event.rotation_index: event for event in rotation_events}
    if len(rotation_by_index) != len(rotation_events):
        raise GeometryError(
            "MovementDistanceWitness rotation events must not contain duplicate indexes."
        )
    expected_indexes = tuple(
        segment.segment_index
        for segment in segments
        if segment.start_pose.facing != segment.end_pose.facing
    )
    if tuple(event.rotation_index for event in rotation_events) != expected_indexes:
        raise GeometryError(
            "MovementDistanceWitness rotation events must match facing-change segments."
        )
    for event in rotation_events:
        if event.rotation_index >= len(segments):
            raise GeometryError("MovementDistanceWitness rotation event index is out of range.")
        segment = segments[event.rotation_index]
        if event.model_id != model_id:
            raise GeometryError("MovementDistanceWitness rotation event model_id mismatch.")
        if event.start_pose != segment.start_pose or event.end_pose != segment.end_pose:
            raise GeometryError(
                "MovementDistanceWitness rotation event poses must match segment poses."
            )


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


_validate_identifier = IdentifierValidator(GeometryError)


def _validate_segment_measurement_point(value: object) -> str:
    measurement_point = _validate_identifier("MovementSegment measurement_point", value)
    if measurement_point != _SEGMENT_MEASUREMENT_POINT:
        raise GeometryError("MovementSegment measurement_point must be pose_anchor.")
    return measurement_point


def _same_point_segment_distance(start: Pose, end: Pose) -> float:
    start_pose = validate_pose("start", start)
    end_pose = validate_pose("end", end)
    return start_pose.distance_3d_to(end_pose)


def _facing_delta_degrees(start_pose: Pose, end_pose: Pose) -> float:
    start = validate_pose("start_pose", start_pose)
    end = validate_pose("end_pose", end_pose)
    return abs(((end.facing.degrees - start.facing.degrees + 180.0) % 360.0) - 180.0)


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
