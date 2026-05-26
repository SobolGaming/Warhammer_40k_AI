from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict


class DeploymentZoneError(ValueError):
    """Raised when deployment-zone data violates CORE V2 invariants."""


class DeploymentZonePayload(TypedDict):
    deployment_zone_id: str
    player_id: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float


@dataclass(frozen=True, slots=True)
class DeploymentZone:
    deployment_zone_id: str
    player_id: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "deployment_zone_id",
            _validate_deployment_zone_id(self.deployment_zone_id),
        )
        object.__setattr__(self, "player_id", _validate_identifier("player_id", self.player_id))
        min_x = _validate_finite_number("DeploymentZone min_x", self.min_x)
        min_y = _validate_finite_number("DeploymentZone min_y", self.min_y)
        max_x = _validate_finite_number("DeploymentZone max_x", self.max_x)
        max_y = _validate_finite_number("DeploymentZone max_y", self.max_y)
        if min_x >= max_x:
            raise DeploymentZoneError("DeploymentZone min_x must be less than max_x.")
        if min_y >= max_y:
            raise DeploymentZoneError("DeploymentZone min_y must be less than max_y.")
        object.__setattr__(self, "min_x", min_x)
        object.__setattr__(self, "min_y", min_y)
        object.__setattr__(self, "max_x", max_x)
        object.__setattr__(self, "max_y", max_y)

    def stable_identity(self) -> str:
        return f"deployment-zone:{self.deployment_zone_id}"

    def contains_point(self, x: float, y: float) -> bool:
        target_x = _validate_finite_number("x", x)
        target_y = _validate_finite_number("y", y)
        return self.min_x <= target_x <= self.max_x and self.min_y <= target_y <= self.max_y

    def to_payload(self) -> DeploymentZonePayload:
        return {
            "deployment_zone_id": self.deployment_zone_id,
            "player_id": self.player_id,
            "min_x": self.min_x,
            "min_y": self.min_y,
            "max_x": self.max_x,
            "max_y": self.max_y,
        }

    @classmethod
    def from_payload(cls, payload: DeploymentZonePayload) -> Self:
        return cls(
            deployment_zone_id=payload["deployment_zone_id"],
            player_id=payload["player_id"],
            min_x=payload["min_x"],
            min_y=payload["min_y"],
            max_x=payload["max_x"],
            max_y=payload["max_y"],
        )


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DeploymentZoneError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DeploymentZoneError(f"{field_name} must not be empty.")
    return stripped


def _validate_deployment_zone_id(value: object) -> str:
    identifier = _validate_identifier("DeploymentZone deployment_zone_id", value)
    if identifier.startswith("deployment-zone:"):
        raise DeploymentZoneError(
            "DeploymentZone deployment_zone_id must not include the stable identity prefix."
        )
    return identifier


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise DeploymentZoneError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise DeploymentZoneError(f"{field_name} must be finite.")
    return number
