from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict


class ObjectiveError(ValueError):
    """Raised when objective data violates CORE V2 invariants."""


class ObjectiveAnchorKind(StrEnum):
    POINT = "point"
    TERRAIN = "terrain"


class ObjectiveAnchorPayload(TypedDict):
    kind: str
    x: float | None
    y: float | None
    z: float | None
    terrain_id: str | None


class ObjectivePayload(TypedDict):
    objective_id: str
    name: str
    anchor: ObjectiveAnchorPayload
    control_radius_inches: float


@dataclass(frozen=True, slots=True)
class PointObjectiveAnchor:
    x: float
    y: float
    z: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _validate_finite_number("PointObjectiveAnchor x", self.x))
        object.__setattr__(self, "y", _validate_finite_number("PointObjectiveAnchor y", self.y))
        object.__setattr__(self, "z", _validate_finite_number("PointObjectiveAnchor z", self.z))

    @property
    def kind(self) -> ObjectiveAnchorKind:
        return ObjectiveAnchorKind.POINT

    def distance_2d_to(self, x: float, y: float) -> float:
        target_x = _validate_finite_number("x", x)
        target_y = _validate_finite_number("y", y)
        return math.hypot(self.x - target_x, self.y - target_y)

    def to_payload(self) -> ObjectiveAnchorPayload:
        return {
            "kind": self.kind.value,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "terrain_id": None,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveAnchorPayload) -> Self:
        if payload["kind"] != ObjectiveAnchorKind.POINT.value:
            raise ObjectiveError("PointObjectiveAnchor payload kind must be point.")
        x = payload["x"]
        y = payload["y"]
        z = payload["z"]
        if x is None or y is None or z is None or payload["terrain_id"] is not None:
            raise ObjectiveError("PointObjectiveAnchor payload must include only x, y, and z.")
        return cls(x=x, y=y, z=z)


@dataclass(frozen=True, slots=True)
class TerrainObjectiveAnchor:
    terrain_id: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "terrain_id", _validate_terrain_id(self.terrain_id))

    @property
    def kind(self) -> ObjectiveAnchorKind:
        return ObjectiveAnchorKind.TERRAIN

    def to_payload(self) -> ObjectiveAnchorPayload:
        return {
            "kind": self.kind.value,
            "x": None,
            "y": None,
            "z": None,
            "terrain_id": self.terrain_id,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveAnchorPayload) -> Self:
        if payload["kind"] != ObjectiveAnchorKind.TERRAIN.value:
            raise ObjectiveError("TerrainObjectiveAnchor payload kind must be terrain.")
        if (
            payload["x"] is not None
            or payload["y"] is not None
            or payload["z"] is not None
            or payload["terrain_id"] is None
        ):
            raise ObjectiveError("TerrainObjectiveAnchor payload must include only terrain_id.")
        return cls(terrain_id=payload["terrain_id"])


type ObjectiveAnchor = PointObjectiveAnchor | TerrainObjectiveAnchor


@dataclass(frozen=True, slots=True)
class Objective:
    objective_id: str
    name: str
    anchor: ObjectiveAnchor
    control_radius_inches: float = 3.0

    def __post_init__(self) -> None:
        object.__setattr__(self, "objective_id", _validate_objective_id(self.objective_id))
        object.__setattr__(self, "name", _validate_identifier("Objective name", self.name))
        object.__setattr__(
            self, "anchor", validate_objective_anchor("Objective anchor", self.anchor)
        )
        object.__setattr__(
            self,
            "control_radius_inches",
            _validate_positive_number(
                "Objective control_radius_inches",
                self.control_radius_inches,
            ),
        )

    @classmethod
    def point(
        cls,
        objective_id: str,
        name: str,
        x: float,
        y: float,
        z: float = 0.0,
        control_radius_inches: float = 3.0,
    ) -> Self:
        return cls(
            objective_id=objective_id,
            name=name,
            anchor=PointObjectiveAnchor(x=x, y=y, z=z),
            control_radius_inches=control_radius_inches,
        )

    @classmethod
    def terrain(
        cls,
        objective_id: str,
        name: str,
        terrain_id: str,
        control_radius_inches: float = 3.0,
    ) -> Self:
        return cls(
            objective_id=objective_id,
            name=name,
            anchor=TerrainObjectiveAnchor(terrain_id=terrain_id),
            control_radius_inches=control_radius_inches,
        )

    def stable_identity(self) -> str:
        return f"objective:{self.objective_id}"

    def contains_point(self, x: float, y: float) -> bool:
        if type(self.anchor) is not PointObjectiveAnchor:
            raise ObjectiveError(
                "Terrain-anchored objective control requires a ruleset/geometry control policy."
            )
        return self.anchor.distance_2d_to(x, y) <= self.control_radius_inches

    def to_payload(self) -> ObjectivePayload:
        return {
            "objective_id": self.objective_id,
            "name": self.name,
            "anchor": self.anchor.to_payload(),
            "control_radius_inches": self.control_radius_inches,
        }

    @classmethod
    def from_payload(cls, payload: ObjectivePayload) -> Self:
        return cls(
            objective_id=payload["objective_id"],
            name=payload["name"],
            anchor=objective_anchor_from_payload(payload["anchor"]),
            control_radius_inches=payload["control_radius_inches"],
        )


def objective_anchor_from_payload(payload: ObjectiveAnchorPayload) -> ObjectiveAnchor:
    kind = payload["kind"]
    if type(kind) is not str:
        raise ObjectiveError("ObjectiveAnchor payload kind must be a string.")
    if kind == ObjectiveAnchorKind.POINT.value:
        return PointObjectiveAnchor.from_payload(payload)
    if kind == ObjectiveAnchorKind.TERRAIN.value:
        return TerrainObjectiveAnchor.from_payload(payload)
    raise ObjectiveError(f"Unsupported ObjectiveAnchor payload kind: {kind}.")


def validate_objective_anchor(field_name: str, value: object) -> ObjectiveAnchor:
    if type(value) is PointObjectiveAnchor or type(value) is TerrainObjectiveAnchor:
        return value
    raise ObjectiveError(f"{field_name} must be an ObjectiveAnchor.")


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


def _validate_terrain_id(value: object) -> str:
    identifier = _validate_identifier("TerrainObjectiveAnchor terrain_id", value)
    if identifier.startswith("terrain:"):
        raise ObjectiveError(
            "TerrainObjectiveAnchor terrain_id must not include the stable identity prefix."
        )
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
