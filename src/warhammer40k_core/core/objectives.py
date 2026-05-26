from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict


class ObjectiveError(ValueError):
    """Raised when objective data violates CORE V2 invariants."""


class ObjectivePayload(TypedDict):
    objective_id: str
    name: str
    x: float
    y: float
    z: float
    control_radius_inches: float


@dataclass(frozen=True, slots=True)
class Objective:
    objective_id: str
    name: str
    x: float
    y: float
    z: float = 0.0
    control_radius_inches: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective_id", _validate_objective_id(self.objective_id))
        object.__setattr__(self, "name", _validate_identifier("Objective name", self.name))
        object.__setattr__(self, "x", _validate_finite_number("Objective x", self.x))
        object.__setattr__(self, "y", _validate_finite_number("Objective y", self.y))
        object.__setattr__(self, "z", _validate_finite_number("Objective z", self.z))
        object.__setattr__(
            self,
            "control_radius_inches",
            _validate_positive_number(
                "Objective control_radius_inches",
                self.control_radius_inches,
            ),
        )

    def stable_identity(self) -> str:
        return f"objective:{self.objective_id}"

    def distance_2d_to(self, x: float, y: float) -> float:
        target_x = _validate_finite_number("x", x)
        target_y = _validate_finite_number("y", y)
        return math.hypot(self.x - target_x, self.y - target_y)

    def contains_point(self, x: float, y: float) -> bool:
        return self.distance_2d_to(x, y) <= self.control_radius_inches

    def to_payload(self) -> ObjectivePayload:
        return {
            "objective_id": self.objective_id,
            "name": self.name,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "control_radius_inches": self.control_radius_inches,
        }

    @classmethod
    def from_payload(cls, payload: ObjectivePayload) -> Self:
        return cls(
            objective_id=payload["objective_id"],
            name=payload["name"],
            x=payload["x"],
            y=payload["y"],
            z=payload["z"],
            control_radius_inches=payload["control_radius_inches"],
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise ObjectiveError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ObjectiveError(f"{field_name} must not be empty.")
    return stripped


def _validate_objective_id(value: object) -> str:
    identifier = _validate_identifier("Objective objective_id", value)
    if identifier.startswith("objective:"):
        raise ObjectiveError("Objective objective_id must not include the stable identity prefix.")
    return identifier


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise ObjectiveError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise ObjectiveError(f"{field_name} must be finite.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise ObjectiveError(f"{field_name} must be greater than 0.")
    return number
