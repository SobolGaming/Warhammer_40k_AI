from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.pose import (
    Facing,
    GeometryError,
    Point3,
    Pose,
    validate_finite_number,
    validate_pose,
)
from warhammer40k_core.geometry.volume import Model


class MovementEnvelopePayload(TypedDict):
    max_distance_inches: float
    sample_interval_inches: float
    coherency_horizontal_inches: float
    coherency_vertical_inches: float
    required_coherency_neighbors: int
    engagement_horizontal_inches: float
    engagement_vertical_inches: float


@dataclass(frozen=True, slots=True)
class MovementEnvelope:
    max_distance_inches: float
    sample_interval_inches: float = 1.0
    coherency_horizontal_inches: float = 2.0
    coherency_vertical_inches: float = 5.0
    required_coherency_neighbors: int = 1
    engagement_horizontal_inches: float = 1.0
    engagement_vertical_inches: float = 5.0

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

    def path_distance(self, poses: tuple[Pose, ...]) -> float:
        path = _validate_pose_path("poses", poses)
        distance = 0.0
        previous = path[0]
        for pose in path[1:]:
            distance += previous.distance_3d_to(pose)
            previous = pose
        return distance

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
