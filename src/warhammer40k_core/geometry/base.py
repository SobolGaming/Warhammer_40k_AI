from __future__ import annotations

import math
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TypedDict

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import (
    Facing,
    GeometryError,
    Pose,
    validate_facing,
    validate_finite_number,
    validate_pose,
)


class BaseShapePayload(TypedDict):
    kind: str
    radius: float | None
    length: float | None
    width: float | None


class BaseShape(ABC):
    @abstractmethod
    def radius_at_angle(self, angle_degrees: float, facing: Facing) -> float:
        raise NotImplementedError

    @abstractmethod
    def max_radius(self) -> float:
        raise NotImplementedError

    @abstractmethod
    def to_payload(self) -> BaseShapePayload:
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

    def to_payload(self) -> BaseShapePayload:
        return {
            "kind": "circular",
            "radius": self.radius,
            "length": None,
            "width": None,
        }


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

    def to_payload(self) -> BaseShapePayload:
        return {
            "kind": "oval",
            "radius": None,
            "length": self.length,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class RectangularBase(BaseShape):
    length: float
    width: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "length", _validate_positive_number("RectangularBase length", self.length)
        )
        object.__setattr__(
            self, "width", _validate_positive_number("RectangularBase width", self.width)
        )

    def radius_at_angle(self, angle_degrees: float, facing: Facing) -> float:
        angle = validate_finite_number("angle_degrees", angle_degrees)
        validate_facing("facing", facing)
        relative_radians = math.radians(angle - facing.degrees)
        cos_angle = abs(math.cos(relative_radians))
        sin_angle = abs(math.sin(relative_radians))
        half_length = self.length / 2.0
        half_width = self.width / 2.0

        candidates: list[float] = []
        if cos_angle > 0.0:
            candidates.append(half_length / cos_angle)
        if sin_angle > 0.0:
            candidates.append(half_width / sin_angle)
        if not candidates:
            raise GeometryError("RectangularBase angle produced no finite ray intersection.")
        return min(candidates)

    def max_radius(self) -> float:
        return math.hypot(self.length / 2.0, self.width / 2.0)

    def to_payload(self) -> BaseShapePayload:
        return {
            "kind": "rectangular",
            "radius": None,
            "length": self.length,
            "width": self.width,
        }


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
    return shapely_backend.base_footprint_distance(
        first_base,
        first_valid_pose,
        second_base,
        second_valid_pose,
    )


def bases_overlap(
    first: BaseShape,
    first_pose: Pose,
    second: BaseShape,
    second_pose: Pose,
) -> bool:
    first_base = validate_base_shape("first", first)
    first_valid_pose = validate_pose("first_pose", first_pose)
    second_base = validate_base_shape("second", second)
    second_valid_pose = validate_pose("second_pose", second_pose)
    return shapely_backend.base_footprints_intersect(
        first_base,
        first_valid_pose,
        second_base,
        second_valid_pose,
    )


def base_shape_from_payload(payload: BaseShapePayload) -> BaseShape:
    kind = payload["kind"]
    if type(kind) is not str:
        raise GeometryError("BaseShape payload kind must be a string.")
    if kind == "circular":
        radius = payload["radius"]
        if radius is None or payload["length"] is not None or payload["width"] is not None:
            raise GeometryError("CircularBase payload must include only radius.")
        return CircularBase(radius=radius)
    if kind == "oval":
        length = payload["length"]
        width = payload["width"]
        if length is None or width is None or payload["radius"] is not None:
            raise GeometryError("OvalBase payload must include only length and width.")
        return OvalBase(length=length, width=width)
    if kind == "rectangular":
        length = payload["length"]
        width = payload["width"]
        if length is None or width is None or payload["radius"] is not None:
            raise GeometryError("RectangularBase payload must include only length and width.")
        return RectangularBase(length=length, width=width)
    raise GeometryError(f"Unsupported BaseShape payload kind: {kind}.")


def validate_base_shape(field_name: str, value: object) -> BaseShape:
    if not isinstance(value, BaseShape):
        raise GeometryError(f"{field_name} must be a BaseShape.")
    return value


def _validate_positive_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return number
