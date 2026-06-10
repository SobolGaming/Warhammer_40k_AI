from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

TERRAIN_DISPLAY_SCHEMA_VERSION = "terrain-display-v1"
TERRAIN_DISPLAY_COORDINATE_SPACE = "battlefield_inches"
TERRAIN_DISPLAY_FOOTPRINT_KIND = "polygon"
_AREA_EPSILON = 1e-9


class TerrainDisplayError(ValueError):
    """Raised when terrain display geometry violates CORE V2 invariants."""


class TerrainDisplayPointPayload(TypedDict):
    x_inches: float
    y_inches: float


class TerrainDisplayGeometryPayload(TypedDict):
    schema_version: str
    coordinate_space: str
    display_template_id: str | None
    footprint_kind: str
    footprint_polygon: list[TerrainDisplayPointPayload]


@dataclass(frozen=True, slots=True)
class TerrainDisplayPoint:
    x_inches: float
    y_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "x_inches",
            _validate_finite_number("TerrainDisplayPoint x_inches", self.x_inches),
        )
        object.__setattr__(
            self,
            "y_inches",
            _validate_finite_number("TerrainDisplayPoint y_inches", self.y_inches),
        )

    def to_payload(self) -> TerrainDisplayPointPayload:
        return {
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainDisplayError("Terrain display point payload must be a mapping.")
        raw_payload = cast(TerrainDisplayPointPayload, payload)
        return cls(
            x_inches=raw_payload["x_inches"],
            y_inches=raw_payload["y_inches"],
        )


@dataclass(frozen=True, slots=True)
class TerrainDisplayGeometry:
    display_template_id: str | None
    footprint_polygon: tuple[TerrainDisplayPoint, ...]
    schema_version: str = TERRAIN_DISPLAY_SCHEMA_VERSION
    coordinate_space: str = TERRAIN_DISPLAY_COORDINATE_SPACE
    footprint_kind: str = TERRAIN_DISPLAY_FOOTPRINT_KIND

    def __post_init__(self) -> None:
        if self.schema_version != TERRAIN_DISPLAY_SCHEMA_VERSION:
            raise TerrainDisplayError("Terrain display geometry schema_version is unsupported.")
        if self.coordinate_space != TERRAIN_DISPLAY_COORDINATE_SPACE:
            raise TerrainDisplayError("Terrain display geometry coordinate_space is unsupported.")
        if self.footprint_kind != TERRAIN_DISPLAY_FOOTPRINT_KIND:
            raise TerrainDisplayError("Terrain display geometry footprint_kind is unsupported.")
        object.__setattr__(
            self,
            "display_template_id",
            _validate_optional_identifier(
                "TerrainDisplayGeometry display_template_id",
                self.display_template_id,
            ),
        )
        object.__setattr__(
            self,
            "footprint_polygon",
            _validate_polygon(self.footprint_polygon),
        )

    @classmethod
    def axis_aligned_rectangle(
        cls,
        *,
        center_x_inches: float,
        center_y_inches: float,
        width_inches: float,
        depth_inches: float,
        display_template_id: str | None,
    ) -> Self:
        center_x = _validate_finite_number(
            "Terrain display rectangle center_x_inches",
            center_x_inches,
        )
        center_y = _validate_finite_number(
            "Terrain display rectangle center_y_inches",
            center_y_inches,
        )
        width = _validate_positive_number("Terrain display rectangle width_inches", width_inches)
        depth = _validate_positive_number("Terrain display rectangle depth_inches", depth_inches)
        min_x = center_x - (width / 2.0)
        max_x = center_x + (width / 2.0)
        min_y = center_y - (depth / 2.0)
        max_y = center_y + (depth / 2.0)
        return cls(
            display_template_id=display_template_id,
            footprint_polygon=(
                TerrainDisplayPoint(min_x, min_y),
                TerrainDisplayPoint(max_x, min_y),
                TerrainDisplayPoint(max_x, max_y),
                TerrainDisplayPoint(min_x, max_y),
            ),
        )

    def is_within_bounds(self, bounds: tuple[float, float, float, float]) -> bool:
        min_x, min_y, max_x, max_y = _validate_bounds(bounds)
        return all(
            min_x <= point.x_inches <= max_x and min_y <= point.y_inches <= max_y
            for point in self.footprint_polygon
        )

    def to_payload(self) -> TerrainDisplayGeometryPayload:
        return {
            "schema_version": self.schema_version,
            "coordinate_space": self.coordinate_space,
            "display_template_id": self.display_template_id,
            "footprint_kind": self.footprint_kind,
            "footprint_polygon": [point.to_payload() for point in self.footprint_polygon],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainDisplayError("Terrain display geometry payload must be a mapping.")
        raw_payload = cast(TerrainDisplayGeometryPayload, payload)
        return cls(
            schema_version=raw_payload["schema_version"],
            coordinate_space=raw_payload["coordinate_space"],
            display_template_id=raw_payload["display_template_id"],
            footprint_kind=raw_payload["footprint_kind"],
            footprint_polygon=tuple(
                TerrainDisplayPoint.from_payload(point_payload)
                for point_payload in raw_payload["footprint_polygon"]
            ),
        )


def _validate_polygon(values: object) -> tuple[TerrainDisplayPoint, ...]:
    if type(values) is not tuple:
        raise TerrainDisplayError("TerrainDisplayGeometry footprint_polygon must be a tuple.")
    points: list[TerrainDisplayPoint] = []
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainDisplayPoint:
            raise TerrainDisplayError(
                "TerrainDisplayGeometry footprint_polygon must contain TerrainDisplayPoint values."
            )
        points.append(value)
    if len(points) < 3:
        raise TerrainDisplayError(
            "TerrainDisplayGeometry footprint_polygon must contain at least three points."
        )
    if points[0] == points[-1]:
        raise TerrainDisplayError("TerrainDisplayGeometry footprint_polygon must be unclosed.")
    if abs(_polygon_area(tuple(points))) <= _AREA_EPSILON:
        raise TerrainDisplayError(
            "TerrainDisplayGeometry footprint_polygon must have non-zero area."
        )
    return tuple(points)


def _polygon_area(points: tuple[TerrainDisplayPoint, ...]) -> float:
    total = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        total += (point.x_inches * next_point.y_inches) - (next_point.x_inches * point.y_inches)
    return total / 2.0


def _validate_bounds(bounds: object) -> tuple[float, float, float, float]:
    if type(bounds) is not tuple:
        raise TerrainDisplayError("Terrain display bounds must be a 4-tuple.")
    raw_values = cast(tuple[object, ...], bounds)
    if len(raw_values) != 4:
        raise TerrainDisplayError("Terrain display bounds must be a 4-tuple.")
    raw_bounds = raw_values
    min_x = _validate_finite_number("Terrain display bounds min_x", raw_bounds[0])
    min_y = _validate_finite_number("Terrain display bounds min_y", raw_bounds[1])
    max_x = _validate_finite_number("Terrain display bounds max_x", raw_bounds[2])
    max_y = _validate_finite_number("Terrain display bounds max_y", raw_bounds[3])
    if min_x >= max_x or min_y >= max_y:
        raise TerrainDisplayError("Terrain display bounds must have positive area.")
    return (min_x, min_y, max_x, max_y)


def _validate_optional_identifier(field_name: str, value: object) -> str | None:
    if value is None:
        return None
    if type(value) is not str:
        raise TerrainDisplayError(f"{field_name} must be a string or None.")
    stripped = value.strip()
    if not stripped:
        raise TerrainDisplayError(f"{field_name} must not be empty.")
    return stripped


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise TerrainDisplayError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise TerrainDisplayError(f"{field_name} must be finite.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise TerrainDisplayError(f"{field_name} must be greater than 0.")
    return number
