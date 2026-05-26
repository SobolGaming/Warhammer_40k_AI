from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.geometry.base import (
    BaseShape,
    BaseShapePayload,
    base_shape_from_payload,
    validate_base_shape,
)
from warhammer40k_core.geometry.pose import (
    GeometryError,
    Pose,
    PosePayload,
    validate_finite_number,
    validate_pose,
)


class ModelVolumePayload(TypedDict):
    height: float


class ModelPayload(TypedDict):
    model_id: str
    pose: PosePayload
    base: BaseShapePayload
    volume: ModelVolumePayload


@dataclass(frozen=True, slots=True)
class ModelVolume:
    height: float

    def __post_init__(self) -> None:
        height = validate_finite_number("ModelVolume height", self.height)
        if height <= 0.0:
            raise GeometryError("ModelVolume height must be greater than 0.")
        object.__setattr__(self, "height", height)

    def vertical_interval(self, pose: Pose) -> tuple[float, float]:
        valid_pose = validate_pose("pose", pose)
        bottom = valid_pose.position.z
        return (bottom, bottom + self.height)

    def vertical_gap_to(
        self,
        own_pose: Pose,
        other: ModelVolume,
        other_pose: Pose,
    ) -> float:
        own_interval = self.vertical_interval(own_pose)
        other_interval = _validate_model_volume("other", other).vertical_interval(other_pose)
        return _vertical_gap(own_interval, other_interval)

    def to_payload(self) -> ModelVolumePayload:
        return {"height": self.height}

    @classmethod
    def from_payload(cls, payload: ModelVolumePayload) -> Self:
        return cls(height=payload["height"])


@dataclass(frozen=True, slots=True)
class Model:
    model_id: str
    pose: Pose
    base: BaseShape
    volume: ModelVolume

    def __post_init__(self) -> None:
        object.__setattr__(self, "model_id", _validate_model_id(self.model_id))
        validate_pose("Model pose", self.pose)
        validate_base_shape("Model base", self.base)
        _validate_model_volume("Model volume", self.volume)

    def stable_identity(self) -> str:
        return f"model:{self.model_id}"

    def base_distance_to(self, other: Model) -> float:
        other_model = _validate_model("other", other)
        return self.base.distance_to(self.pose, other_model.base, other_model.pose)

    def base_overlaps(self, other: Model) -> bool:
        other_model = _validate_model("other", other)
        return self.base.overlaps(self.pose, other_model.base, other_model.pose)

    def range_to(self, other: Model) -> float:
        other_model = _validate_model("other", other)
        horizontal_gap = self.base_distance_to(other_model)
        vertical_gap = self.volume.vertical_gap_to(
            self.pose,
            other_model.volume,
            other_model.pose,
        )
        return math.hypot(horizontal_gap, vertical_gap)

    def is_within_engagement_range(
        self,
        other: Model,
        horizontal_inches: float = 1.0,
        vertical_inches: float = 5.0,
    ) -> bool:
        other_model = _validate_model("other", other)
        horizontal_limit = _validate_non_negative_number("horizontal_inches", horizontal_inches)
        vertical_limit = _validate_non_negative_number("vertical_inches", vertical_inches)
        return (
            self.base_distance_to(other_model) <= horizontal_limit
            and self.volume.vertical_gap_to(self.pose, other_model.volume, other_model.pose)
            <= vertical_limit
        )

    def to_payload(self) -> ModelPayload:
        return {
            "model_id": self.model_id,
            "pose": self.pose.to_payload(),
            "base": self.base.to_payload(),
            "volume": self.volume.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: ModelPayload) -> Self:
        return cls(
            model_id=payload["model_id"],
            pose=Pose.from_payload(payload["pose"]),
            base=base_shape_from_payload(payload["base"]),
            volume=ModelVolume.from_payload(payload["volume"]),
        )


def _validate_model_id(value: object) -> str:
    if type(value) is not str:
        raise GeometryError("Model model_id must be a string.")
    model_id = value.strip()
    if not model_id:
        raise GeometryError("Model model_id must not be empty.")
    if model_id.startswith("model:"):
        raise GeometryError("Model model_id must not include the stable identity prefix.")
    return model_id


def _validate_model_volume(field_name: str, value: object) -> ModelVolume:
    if type(value) is not ModelVolume:
        raise GeometryError(f"{field_name} must be a ModelVolume.")
    return value


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number < 0.0:
        raise GeometryError(f"{field_name} must not be negative.")
    return number


def _vertical_gap(
    first_interval: tuple[float, float],
    second_interval: tuple[float, float],
) -> float:
    first_bottom, first_top = first_interval
    second_bottom, second_top = second_interval
    if first_top < second_bottom:
        return second_bottom - first_top
    if second_top < first_bottom:
        return first_bottom - second_top
    return 0.0
