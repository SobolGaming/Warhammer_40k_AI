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


class ObjectiveMarkerPayload(TypedDict):
    objective_marker_id: str
    name: str
    x_inches: float
    y_inches: float
    z_inches: float
    marker_diameter_mm: float
    control_horizontal_inches: float
    control_vertical_inches: float
    measurement_anchor: str
    is_flat: bool
    blocks_movement: bool
    blocks_placement: bool
    source_id: str


MILLIMETERS_PER_INCH = 25.4
DEFAULT_OBJECTIVE_MARKER_DIAMETER_MM = 40.0
DEFAULT_OBJECTIVE_CONTROL_HORIZONTAL_INCHES = 3.0
DEFAULT_OBJECTIVE_CONTROL_VERTICAL_INCHES = 5.0


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
class ObjectiveMarker:
    objective_marker_id: str
    name: str
    x_inches: float
    y_inches: float
    z_inches: float = 0.0
    marker_diameter_mm: float = DEFAULT_OBJECTIVE_MARKER_DIAMETER_MM
    control_horizontal_inches: float = DEFAULT_OBJECTIVE_CONTROL_HORIZONTAL_INCHES
    control_vertical_inches: float = DEFAULT_OBJECTIVE_CONTROL_VERTICAL_INCHES
    measurement_anchor: str = "center"
    is_flat: bool = True
    blocks_movement: bool = False
    blocks_placement: bool = False
    source_id: str = "core-rules"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_marker_id",
            _validate_objective_id(self.objective_marker_id),
        )
        object.__setattr__(self, "name", _validate_identifier("ObjectiveMarker name", self.name))
        object.__setattr__(
            self,
            "x_inches",
            _validate_finite_number("ObjectiveMarker x_inches", self.x_inches),
        )
        object.__setattr__(
            self,
            "y_inches",
            _validate_finite_number("ObjectiveMarker y_inches", self.y_inches),
        )
        object.__setattr__(
            self,
            "z_inches",
            _validate_finite_number("ObjectiveMarker z_inches", self.z_inches),
        )
        object.__setattr__(
            self,
            "marker_diameter_mm",
            _validate_positive_number(
                "ObjectiveMarker marker_diameter_mm",
                self.marker_diameter_mm,
            ),
        )
        object.__setattr__(
            self,
            "control_horizontal_inches",
            _validate_non_negative_number(
                "ObjectiveMarker control_horizontal_inches",
                self.control_horizontal_inches,
            ),
        )
        object.__setattr__(
            self,
            "control_vertical_inches",
            _validate_non_negative_number(
                "ObjectiveMarker control_vertical_inches",
                self.control_vertical_inches,
            ),
        )
        object.__setattr__(
            self,
            "measurement_anchor",
            _validate_required_token(
                "ObjectiveMarker measurement_anchor",
                self.measurement_anchor,
                expected_token="center",
            ),
        )
        _validate_bool("ObjectiveMarker is_flat", self.is_flat)
        _validate_bool("ObjectiveMarker blocks_movement", self.blocks_movement)
        _validate_bool("ObjectiveMarker blocks_placement", self.blocks_placement)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ObjectiveMarker source_id", self.source_id),
        )

    @classmethod
    def from_objective(cls, objective: Objective) -> Self:
        if type(objective) is not Objective:
            raise ObjectiveError("ObjectiveMarker.from_objective requires an Objective.")
        if type(objective.anchor) is not PointObjectiveAnchor:
            raise ObjectiveError("Only point objectives can become ObjectiveMarker values.")
        return cls(
            objective_marker_id=objective.objective_id,
            name=objective.name,
            x_inches=objective.anchor.x,
            y_inches=objective.anchor.y,
            z_inches=objective.anchor.z,
            control_horizontal_inches=objective.control_radius_inches,
            source_id=objective.objective_id,
        )

    @property
    def marker_diameter_inches(self) -> float:
        return self.marker_diameter_mm / MILLIMETERS_PER_INCH

    def stable_identity(self) -> str:
        return f"objective-marker:{self.objective_marker_id}"

    def to_payload(self) -> ObjectiveMarkerPayload:
        return {
            "objective_marker_id": self.objective_marker_id,
            "name": self.name,
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
            "z_inches": self.z_inches,
            "marker_diameter_mm": self.marker_diameter_mm,
            "control_horizontal_inches": self.control_horizontal_inches,
            "control_vertical_inches": self.control_vertical_inches,
            "measurement_anchor": self.measurement_anchor,
            "is_flat": self.is_flat,
            "blocks_movement": self.blocks_movement,
            "blocks_placement": self.blocks_placement,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveMarkerPayload) -> Self:
        return cls(
            objective_marker_id=payload["objective_marker_id"],
            name=payload["name"],
            x_inches=payload["x_inches"],
            y_inches=payload["y_inches"],
            z_inches=payload["z_inches"],
            marker_diameter_mm=payload["marker_diameter_mm"],
            control_horizontal_inches=payload["control_horizontal_inches"],
            control_vertical_inches=payload["control_vertical_inches"],
            measurement_anchor=payload["measurement_anchor"],
            is_flat=payload["is_flat"],
            blocks_movement=payload["blocks_movement"],
            blocks_placement=payload["blocks_placement"],
            source_id=payload["source_id"],
        )


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


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number < 0.0:
        raise ObjectiveError(f"{field_name} must not be negative.")
    return number


def _validate_required_token(field_name: str, value: object, *, expected_token: str) -> str:
    token = _validate_identifier(field_name, value)
    if token != expected_token:
        raise ObjectiveError(f"{field_name} must be {expected_token}.")
    return token


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise ObjectiveError(f"{field_name} must be a bool.")
    return value
