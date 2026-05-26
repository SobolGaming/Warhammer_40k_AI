from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass

from warhammer40k_core.geometry.pose import (
    Facing,
    GeometryError,
    Pose,
    validate_facing,
    validate_finite_number,
    validate_pose,
)

_EPSILON = 1e-9


class BaseShape(ABC):
    @abstractmethod
    def radius_at_angle(self, angle_degrees: float, facing: Facing) -> float:
        raise NotImplementedError

    @abstractmethod
    def max_radius(self) -> float:
        raise NotImplementedError

    def distance_to(self, own_pose: Pose, other: BaseShape, other_pose: Pose) -> float:
        return base_distance(self, own_pose, other, other_pose)

    def overlaps(self, own_pose: Pose, other: BaseShape, other_pose: Pose) -> bool:
        return bases_overlap(self, own_pose, other, other_pose)


@dataclass(frozen=True, slots=True)
class CircularBase(BaseShape):
    radius: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "radius", _validate_positive_number("CircularBase radius", self.radius)
        )

    def radius_at_angle(self, angle_degrees: float, facing: Facing) -> float:
        validate_finite_number("angle_degrees", angle_degrees)
        validate_facing("facing", facing)
        return self.radius

    def max_radius(self) -> float:
        return self.radius


@dataclass(frozen=True, slots=True)
class OvalBase(BaseShape):
    length: float
    width: float

    def __post_init__(self) -> None:
        length = _validate_positive_number("OvalBase length", self.length)
        width = _validate_positive_number("OvalBase width", self.width)
        if length < width:
            raise GeometryError("OvalBase length must be greater than or equal to width.")
        object.__setattr__(self, "length", length)
        object.__setattr__(self, "width", width)

    def radius_at_angle(self, angle_degrees: float, facing: Facing) -> float:
        angle = validate_finite_number("angle_degrees", angle_degrees)
        validate_facing("facing", facing)
        relative_radians = math.radians(angle - facing.degrees)
        semi_major = self.length / 2.0
        semi_minor = self.width / 2.0
        cos_angle = math.cos(relative_radians)
        sin_angle = math.sin(relative_radians)
        denominator = math.sqrt(
            (cos_angle * cos_angle) / (semi_major * semi_major)
            + (sin_angle * sin_angle) / (semi_minor * semi_minor)
        )
        return 1.0 / denominator

    def max_radius(self) -> float:
        return self.length / 2.0


def base_distance(
    first: BaseShape,
    first_pose: Pose,
    second: BaseShape,
    second_pose: Pose,
) -> float:
    first_base = validate_base_shape("first", first)
    first_valid_pose = validate_pose("first_pose", first_pose)
    second_base = validate_base_shape("second", second)
    second_valid_pose = validate_pose("second_pose", second_pose)

    dx = second_valid_pose.position.x - first_valid_pose.position.x
    dy = second_valid_pose.position.y - first_valid_pose.position.y
    center_distance = math.hypot(dx, dy)
    if center_distance <= _EPSILON:
        return 0.0

    angle = math.degrees(math.atan2(dy, dx))
    first_radius = first_base.radius_at_angle(angle, first_valid_pose.facing)
    second_radius = second_base.radius_at_angle(angle + 180.0, second_valid_pose.facing)
    return max(0.0, center_distance - first_radius - second_radius)


def bases_overlap(
    first: BaseShape,
    first_pose: Pose,
    second: BaseShape,
    second_pose: Pose,
) -> bool:
    return base_distance(first, first_pose, second, second_pose) <= _EPSILON


def validate_base_shape(field_name: str, value: object) -> BaseShape:
    if not isinstance(value, BaseShape):
        raise GeometryError(f"{field_name} must be a BaseShape.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return number
