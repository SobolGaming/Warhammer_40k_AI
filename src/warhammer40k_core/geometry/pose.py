from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Self


class GeometryError(ValueError):
    """Raised when geometry data violates CORE V2 invariants."""


@dataclass(frozen=True, slots=True)
class Point3:
    x: float
    y: float
    z: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", validate_finite_number("Point3 x", self.x))
        object.__setattr__(self, "y", validate_finite_number("Point3 y", self.y))
        object.__setattr__(self, "z", validate_finite_number("Point3 z", self.z))

    @classmethod
    def origin(cls) -> Self:
        return cls(x=0.0, y=0.0, z=0.0)

    def distance_2d_to(self, other: Point3) -> float:
        other_point = validate_point3("other", other)
        return math.hypot(self.x - other_point.x, self.y - other_point.y)

    def distance_3d_to(self, other: Point3) -> float:
        other_point = validate_point3("other", other)
        return math.dist((self.x, self.y, self.z), (other_point.x, other_point.y, other_point.z))


@dataclass(frozen=True, slots=True)
class Facing:
    degrees: float

    def __post_init__(self) -> None:
        degrees = validate_finite_number("Facing degrees", self.degrees) % 360.0
        object.__setattr__(self, "degrees", degrees)

    @classmethod
    def from_degrees(cls, degrees: float) -> Self:
        return cls(degrees=degrees)

    def radians(self) -> float:
        return math.radians(self.degrees)


@dataclass(frozen=True, slots=True)
class Pose:
    position: Point3
    facing: Facing = field(default_factory=lambda: Facing(0.0))

    def __post_init__(self) -> None:
        validate_point3("Pose position", self.position)
        validate_facing("Pose facing", self.facing)

    @classmethod
    def at(cls, x: float, y: float, z: float = 0.0, facing_degrees: float = 0.0) -> Self:
        return cls(
            position=Point3(x=x, y=y, z=z),
            facing=Facing.from_degrees(facing_degrees),
        )

    def distance_2d_to(self, other: Pose) -> float:
        other_pose = validate_pose("other", other)
        return self.position.distance_2d_to(other_pose.position)

    def distance_3d_to(self, other: Pose) -> float:
        other_pose = validate_pose("other", other)
        return self.position.distance_3d_to(other_pose.position)


def validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GeometryError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GeometryError(f"{field_name} must be finite.")
    return number


def validate_point3(field_name: str, value: object) -> Point3:
    if type(value) is not Point3:
        raise GeometryError(f"{field_name} must be a Point3.")
    return value


def validate_facing(field_name: str, value: object) -> Facing:
    if type(value) is not Facing:
        raise GeometryError(f"{field_name} must be a Facing.")
    return value


def validate_pose(field_name: str, value: object) -> Pose:
    if type(value) is not Pose:
        raise GeometryError(f"{field_name} must be a Pose.")
    return value
