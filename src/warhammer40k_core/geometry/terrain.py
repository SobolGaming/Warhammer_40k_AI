from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import (
    GeometryError,
    Point3,
    Point3Payload,
    validate_finite_number,
    validate_point3,
)
from warhammer40k_core.geometry.volume import Model


class TerrainVolumePayload(TypedDict):
    kind: str
    terrain_id: str
    bottom_center: Point3Payload
    width: float
    depth: float
    height: float
    blocks_line_of_sight: bool


@dataclass(frozen=True, slots=True)
class TerrainVolume:
    terrain_id: str
    bottom_center: Point3
    width: float
    depth: float
    height: float
    blocks_line_of_sight: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "terrain_id", _validate_terrain_id(self.terrain_id))
        validate_point3("TerrainVolume bottom_center", self.bottom_center)
        object.__setattr__(
            self, "width", _validate_positive_number("TerrainVolume width", self.width)
        )
        object.__setattr__(
            self, "depth", _validate_positive_number("TerrainVolume depth", self.depth)
        )
        object.__setattr__(
            self,
            "height",
            _validate_positive_number("TerrainVolume height", self.height),
        )
        if type(self.blocks_line_of_sight) is not bool:
            raise GeometryError("TerrainVolume blocks_line_of_sight must be a bool.")

    def stable_identity(self) -> str:
        return f"terrain:{self.terrain_id}"

    def vertical_interval(self) -> tuple[float, float]:
        bottom = self.bottom_center.z
        return (bottom, bottom + self.height)

    def horizontal_bounds(self) -> tuple[float, float, float, float]:
        half_width = self.width / 2.0
        half_depth = self.depth / 2.0
        return (
            self.bottom_center.x - half_width,
            self.bottom_center.y - half_depth,
            self.bottom_center.x + half_width,
            self.bottom_center.y + half_depth,
        )

    def intersects_model(self, model: Model) -> bool:
        return shapely_backend.terrain_footprint_intersects_model(self, model)

    def blocks_line_segment(self, start: Point3, end: Point3) -> bool:
        if not self.blocks_line_of_sight:
            return False
        return shapely_backend.segment_intersects_terrain_footprint(start, end, self)

    def to_payload(self) -> TerrainVolumePayload:
        return {
            "kind": "terrain",
            "terrain_id": self.terrain_id,
            "bottom_center": self.bottom_center.to_payload(),
            "width": self.width,
            "depth": self.depth,
            "height": self.height,
            "blocks_line_of_sight": self.blocks_line_of_sight,
        }

    @classmethod
    def from_payload(cls, payload: TerrainVolumePayload) -> TerrainVolume:
        return terrain_volume_from_payload(payload)


@dataclass(frozen=True, slots=True)
class ObstacleVolume(TerrainVolume):
    blocks_line_of_sight: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.blocks_line_of_sight is not True:
            raise GeometryError("ObstacleVolume must block line of sight.")

    def to_payload(self) -> TerrainVolumePayload:
        return {
            "kind": "obstacle",
            "terrain_id": self.terrain_id,
            "bottom_center": self.bottom_center.to_payload(),
            "width": self.width,
            "depth": self.depth,
            "height": self.height,
            "blocks_line_of_sight": self.blocks_line_of_sight,
        }

    @classmethod
    def from_payload(cls, payload: TerrainVolumePayload) -> Self:
        volume = terrain_volume_from_payload(payload)
        if type(volume) is not cls:
            raise GeometryError("ObstacleVolume payload kind must be obstacle.")
        return volume


def terrain_volume_from_payload(payload: TerrainVolumePayload) -> TerrainVolume:
    kind = payload["kind"]
    if type(kind) is not str:
        raise GeometryError("TerrainVolume payload kind must be a string.")
    if kind == "terrain":
        return TerrainVolume(
            terrain_id=payload["terrain_id"],
            bottom_center=Point3.from_payload(payload["bottom_center"]),
            width=payload["width"],
            depth=payload["depth"],
            height=payload["height"],
            blocks_line_of_sight=payload["blocks_line_of_sight"],
        )
    if kind == "obstacle":
        return ObstacleVolume(
            terrain_id=payload["terrain_id"],
            bottom_center=Point3.from_payload(payload["bottom_center"]),
            width=payload["width"],
            depth=payload["depth"],
            height=payload["height"],
            blocks_line_of_sight=payload["blocks_line_of_sight"],
        )
    raise GeometryError(f"Unsupported TerrainVolume payload kind: {kind}.")


def _validate_terrain_id(value: object) -> str:
    if type(value) is not str:
        raise GeometryError("TerrainVolume terrain_id must be a string.")
    terrain_id = value.strip()
    if not terrain_id:
        raise GeometryError("TerrainVolume terrain_id must not be empty.")
    if terrain_id.startswith("terrain:"):
        raise GeometryError("TerrainVolume terrain_id must not include the stable identity prefix.")
    return terrain_id


def _validate_positive_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return number
