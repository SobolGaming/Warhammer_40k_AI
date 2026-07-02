from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptorError,
    TerrainFeatureKind,
    terrain_feature_kind_from_token,
)
from warhammer40k_core.core.terrain_display import (
    TerrainDisplayGeometry,
    TerrainDisplayGeometryPayload,
)
from warhammer40k_core.core.validation import IdentifierValidator


class TerrainLayoutError(ValueError):
    """Raised when terrain layout template data violates CORE V2 invariants."""


class TerrainWallTemplatePayload(TypedDict):
    wall_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    height_inches: float
    rotation_degrees: float


class TerrainFloorTemplatePayload(TypedDict):
    floor_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    thickness_inches: float
    rotation_degrees: float


class TerrainFeatureTemplatePayload(TypedDict):
    feature_id: str
    feature_kind: str
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    display_geometry: TerrainDisplayGeometryPayload
    walls: list[TerrainWallTemplatePayload]
    floors: list[TerrainFloorTemplatePayload]
    source_id: str


class TerrainFeaturePresetPayload(TypedDict):
    terrain_feature_preset_id: str
    feature_kind: str
    footprint_template_id: str
    footprint_width_inches: float
    footprint_depth_inches: float
    walls: list[TerrainWallTemplatePayload]
    floors: list[TerrainFloorTemplatePayload]
    source_id: str


class TerrainFeatureAreaPlacementPayload(TypedDict):
    feature_id: str
    terrain_area_id: str
    terrain_feature_preset_id: str
    source_id: str


class TerrainLayoutTemplatePayload(TypedDict):
    terrain_layout_id: str
    name: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    terrain_features: list[TerrainFeatureTemplatePayload]
    source_id: str


@dataclass(frozen=True, slots=True)
class TerrainWallTemplate:
    wall_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    height_inches: float
    rotation_degrees: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wall_id",
            _validate_unprefixed_identifier(
                "TerrainWallTemplate wall_id",
                self.wall_id,
                reserved_prefix="wall:",
            ),
        )
        object.__setattr__(
            self,
            "center_x_inches",
            _validate_finite_number("TerrainWallTemplate center_x_inches", self.center_x_inches),
        )
        object.__setattr__(
            self,
            "center_y_inches",
            _validate_finite_number("TerrainWallTemplate center_y_inches", self.center_y_inches),
        )
        object.__setattr__(
            self,
            "bottom_z_inches",
            _validate_non_negative_number(
                "TerrainWallTemplate bottom_z_inches",
                self.bottom_z_inches,
            ),
        )
        object.__setattr__(
            self,
            "width_inches",
            _validate_positive_number("TerrainWallTemplate width_inches", self.width_inches),
        )
        object.__setattr__(
            self,
            "depth_inches",
            _validate_positive_number("TerrainWallTemplate depth_inches", self.depth_inches),
        )
        object.__setattr__(
            self,
            "height_inches",
            _validate_positive_number("TerrainWallTemplate height_inches", self.height_inches),
        )
        object.__setattr__(
            self,
            "rotation_degrees",
            _validate_finite_number(
                "TerrainWallTemplate rotation_degrees",
                self.rotation_degrees,
            ),
        )

    def bounds(self) -> tuple[float, float, float, float]:
        return _rotated_rectangle_bounds(
            center_x_inches=self.center_x_inches,
            center_y_inches=self.center_y_inches,
            width_inches=self.width_inches,
            depth_inches=self.depth_inches,
            rotation_degrees=self.rotation_degrees,
        )

    def to_payload(self) -> TerrainWallTemplatePayload:
        return {
            "wall_id": self.wall_id,
            "center_x_inches": self.center_x_inches,
            "center_y_inches": self.center_y_inches,
            "bottom_z_inches": self.bottom_z_inches,
            "width_inches": self.width_inches,
            "depth_inches": self.depth_inches,
            "height_inches": self.height_inches,
            "rotation_degrees": self.rotation_degrees,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainLayoutError("Terrain wall template payload must be a mapping.")
        raw_payload = cast(TerrainWallTemplatePayload, payload)
        return cls(
            wall_id=raw_payload["wall_id"],
            center_x_inches=raw_payload["center_x_inches"],
            center_y_inches=raw_payload["center_y_inches"],
            bottom_z_inches=raw_payload["bottom_z_inches"],
            width_inches=raw_payload["width_inches"],
            depth_inches=raw_payload["depth_inches"],
            height_inches=raw_payload["height_inches"],
            rotation_degrees=raw_payload["rotation_degrees"],
        )


@dataclass(frozen=True, slots=True)
class TerrainFloorTemplate:
    floor_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    thickness_inches: float
    rotation_degrees: float = 0.0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "floor_id",
            _validate_unprefixed_identifier(
                "TerrainFloorTemplate floor_id",
                self.floor_id,
                reserved_prefix="floor:",
            ),
        )
        object.__setattr__(
            self,
            "center_x_inches",
            _validate_finite_number("TerrainFloorTemplate center_x_inches", self.center_x_inches),
        )
        object.__setattr__(
            self,
            "center_y_inches",
            _validate_finite_number("TerrainFloorTemplate center_y_inches", self.center_y_inches),
        )
        object.__setattr__(
            self,
            "bottom_z_inches",
            _validate_non_negative_number(
                "TerrainFloorTemplate bottom_z_inches",
                self.bottom_z_inches,
            ),
        )
        object.__setattr__(
            self,
            "width_inches",
            _validate_positive_number("TerrainFloorTemplate width_inches", self.width_inches),
        )
        object.__setattr__(
            self,
            "depth_inches",
            _validate_positive_number("TerrainFloorTemplate depth_inches", self.depth_inches),
        )
        object.__setattr__(
            self,
            "thickness_inches",
            _validate_positive_number(
                "TerrainFloorTemplate thickness_inches",
                self.thickness_inches,
            ),
        )
        object.__setattr__(
            self,
            "rotation_degrees",
            _validate_finite_number(
                "TerrainFloorTemplate rotation_degrees",
                self.rotation_degrees,
            ),
        )

    def bounds(self) -> tuple[float, float, float, float]:
        return _rotated_rectangle_bounds(
            center_x_inches=self.center_x_inches,
            center_y_inches=self.center_y_inches,
            width_inches=self.width_inches,
            depth_inches=self.depth_inches,
            rotation_degrees=self.rotation_degrees,
        )

    def to_payload(self) -> TerrainFloorTemplatePayload:
        return {
            "floor_id": self.floor_id,
            "center_x_inches": self.center_x_inches,
            "center_y_inches": self.center_y_inches,
            "bottom_z_inches": self.bottom_z_inches,
            "width_inches": self.width_inches,
            "depth_inches": self.depth_inches,
            "thickness_inches": self.thickness_inches,
            "rotation_degrees": self.rotation_degrees,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainLayoutError("Terrain floor template payload must be a mapping.")
        raw_payload = cast(TerrainFloorTemplatePayload, payload)
        return cls(
            floor_id=raw_payload["floor_id"],
            center_x_inches=raw_payload["center_x_inches"],
            center_y_inches=raw_payload["center_y_inches"],
            bottom_z_inches=raw_payload["bottom_z_inches"],
            width_inches=raw_payload["width_inches"],
            depth_inches=raw_payload["depth_inches"],
            thickness_inches=raw_payload["thickness_inches"],
            rotation_degrees=raw_payload["rotation_degrees"],
        )


@dataclass(frozen=True, slots=True)
class TerrainFeatureTemplate:
    feature_id: str
    feature_kind: TerrainFeatureKind
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    display_geometry: TerrainDisplayGeometry
    walls: tuple[TerrainWallTemplate, ...] = ()
    floors: tuple[TerrainFloorTemplate, ...] = ()
    source_id: str = "chapter_approved_2026_27"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "feature_id",
            _validate_unprefixed_identifier(
                "TerrainFeatureTemplate feature_id",
                self.feature_id,
                reserved_prefix="terrain:",
            ),
        )
        object.__setattr__(
            self,
            "feature_kind",
            _terrain_feature_kind_from_token(self.feature_kind),
        )
        object.__setattr__(
            self,
            "footprint_center_x_inches",
            _validate_finite_number(
                "TerrainFeatureTemplate footprint_center_x_inches",
                self.footprint_center_x_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_center_y_inches",
            _validate_finite_number(
                "TerrainFeatureTemplate footprint_center_y_inches",
                self.footprint_center_y_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_width_inches",
            _validate_positive_number(
                "TerrainFeatureTemplate footprint_width_inches",
                self.footprint_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_depth_inches",
            _validate_positive_number(
                "TerrainFeatureTemplate footprint_depth_inches",
                self.footprint_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "display_geometry",
            _validate_display_geometry(
                "TerrainFeatureTemplate display_geometry",
                self.display_geometry,
                feature_bounds=self.bounds(),
            ),
        )
        object.__setattr__(
            self,
            "walls",
            _validate_wall_templates("TerrainFeatureTemplate walls", self.walls),
        )
        object.__setattr__(
            self,
            "floors",
            _validate_floor_templates("TerrainFeatureTemplate floors", self.floors),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TerrainFeatureTemplate source_id", self.source_id),
        )
        self._validate_parts_within_footprint()

    def bounds(self) -> tuple[float, float, float, float]:
        half_width = self.footprint_width_inches / 2.0
        half_depth = self.footprint_depth_inches / 2.0
        return (
            self.footprint_center_x_inches - half_width,
            self.footprint_center_y_inches - half_depth,
            self.footprint_center_x_inches + half_width,
            self.footprint_center_y_inches + half_depth,
        )

    def to_payload(self) -> TerrainFeatureTemplatePayload:
        return {
            "feature_id": self.feature_id,
            "feature_kind": self.feature_kind.value,
            "footprint_center_x_inches": self.footprint_center_x_inches,
            "footprint_center_y_inches": self.footprint_center_y_inches,
            "footprint_width_inches": self.footprint_width_inches,
            "footprint_depth_inches": self.footprint_depth_inches,
            "display_geometry": self.display_geometry.to_payload(),
            "walls": [wall.to_payload() for wall in self.walls],
            "floors": [floor.to_payload() for floor in self.floors],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainLayoutError("Terrain feature template payload must be a mapping.")
        raw_payload = cast(TerrainFeatureTemplatePayload, payload)
        return cls(
            feature_id=raw_payload["feature_id"],
            feature_kind=_terrain_feature_kind_from_token(raw_payload["feature_kind"]),
            footprint_center_x_inches=raw_payload["footprint_center_x_inches"],
            footprint_center_y_inches=raw_payload["footprint_center_y_inches"],
            footprint_width_inches=raw_payload["footprint_width_inches"],
            footprint_depth_inches=raw_payload["footprint_depth_inches"],
            display_geometry=TerrainDisplayGeometry.from_payload(raw_payload["display_geometry"]),
            walls=tuple(
                TerrainWallTemplate.from_payload(wall_payload)
                for wall_payload in raw_payload["walls"]
            ),
            floors=tuple(
                TerrainFloorTemplate.from_payload(floor_payload)
                for floor_payload in raw_payload["floors"]
            ),
            source_id=raw_payload["source_id"],
        )

    def _validate_parts_within_footprint(self) -> None:
        feature_bounds = self.bounds()
        for wall in self.walls:
            _validate_part_bounds_within_feature(
                part_id=wall.wall_id,
                part_bounds=wall.bounds(),
                feature_bounds=feature_bounds,
            )
        for floor in self.floors:
            _validate_part_bounds_within_feature(
                part_id=floor.floor_id,
                part_bounds=floor.bounds(),
                feature_bounds=feature_bounds,
            )


@dataclass(frozen=True, slots=True)
class TerrainFeaturePreset:
    terrain_feature_preset_id: str
    feature_kind: TerrainFeatureKind
    footprint_template_id: str
    footprint_width_inches: float
    footprint_depth_inches: float
    walls: tuple[TerrainWallTemplate, ...] = ()
    floors: tuple[TerrainFloorTemplate, ...] = ()
    source_id: str = "chapter_approved_2026_27"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_feature_preset_id",
            _validate_unprefixed_identifier(
                "TerrainFeaturePreset terrain_feature_preset_id",
                self.terrain_feature_preset_id,
                reserved_prefix="terrain-feature-preset:",
            ),
        )
        object.__setattr__(
            self,
            "feature_kind",
            _terrain_feature_kind_from_token(self.feature_kind),
        )
        object.__setattr__(
            self,
            "footprint_template_id",
            _validate_identifier(
                "TerrainFeaturePreset footprint_template_id",
                self.footprint_template_id,
            ),
        )
        object.__setattr__(
            self,
            "footprint_width_inches",
            _validate_positive_number(
                "TerrainFeaturePreset footprint_width_inches",
                self.footprint_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_depth_inches",
            _validate_positive_number(
                "TerrainFeaturePreset footprint_depth_inches",
                self.footprint_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "walls",
            _validate_wall_templates("TerrainFeaturePreset walls", self.walls),
        )
        object.__setattr__(
            self,
            "floors",
            _validate_floor_templates("TerrainFeaturePreset floors", self.floors),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TerrainFeaturePreset source_id", self.source_id),
        )
        self._validate_parts_within_footprint()

    def bounds(self) -> tuple[float, float, float, float]:
        half_width = self.footprint_width_inches / 2.0
        half_depth = self.footprint_depth_inches / 2.0
        return (-half_width, -half_depth, half_width, half_depth)

    def to_payload(self) -> TerrainFeaturePresetPayload:
        return {
            "terrain_feature_preset_id": self.terrain_feature_preset_id,
            "feature_kind": self.feature_kind.value,
            "footprint_template_id": self.footprint_template_id,
            "footprint_width_inches": self.footprint_width_inches,
            "footprint_depth_inches": self.footprint_depth_inches,
            "walls": [wall.to_payload() for wall in self.walls],
            "floors": [floor.to_payload() for floor in self.floors],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainLayoutError("Terrain feature preset payload must be a mapping.")
        raw_payload = cast(TerrainFeaturePresetPayload, payload)
        return cls(
            terrain_feature_preset_id=raw_payload["terrain_feature_preset_id"],
            feature_kind=_terrain_feature_kind_from_token(raw_payload["feature_kind"]),
            footprint_template_id=raw_payload["footprint_template_id"],
            footprint_width_inches=raw_payload["footprint_width_inches"],
            footprint_depth_inches=raw_payload["footprint_depth_inches"],
            walls=tuple(
                TerrainWallTemplate.from_payload(wall_payload)
                for wall_payload in raw_payload["walls"]
            ),
            floors=tuple(
                TerrainFloorTemplate.from_payload(floor_payload)
                for floor_payload in raw_payload["floors"]
            ),
            source_id=raw_payload["source_id"],
        )

    def _validate_parts_within_footprint(self) -> None:
        feature_bounds = self.bounds()
        for wall in self.walls:
            _validate_part_bounds_within_feature(
                part_id=wall.wall_id,
                part_bounds=wall.bounds(),
                feature_bounds=feature_bounds,
            )
        for floor in self.floors:
            _validate_part_bounds_within_feature(
                part_id=floor.floor_id,
                part_bounds=floor.bounds(),
                feature_bounds=feature_bounds,
            )


@dataclass(frozen=True, slots=True)
class TerrainFeatureAreaPlacement:
    feature_id: str
    terrain_area_id: str
    terrain_feature_preset_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "feature_id",
            _validate_unprefixed_identifier(
                "TerrainFeatureAreaPlacement feature_id",
                self.feature_id,
                reserved_prefix="terrain:",
            ),
        )
        object.__setattr__(
            self,
            "terrain_area_id",
            _validate_identifier(
                "TerrainFeatureAreaPlacement terrain_area_id",
                self.terrain_area_id,
            ),
        )
        object.__setattr__(
            self,
            "terrain_feature_preset_id",
            _validate_identifier(
                "TerrainFeatureAreaPlacement terrain_feature_preset_id",
                self.terrain_feature_preset_id,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TerrainFeatureAreaPlacement source_id", self.source_id),
        )

    def to_payload(self) -> TerrainFeatureAreaPlacementPayload:
        return {
            "feature_id": self.feature_id,
            "terrain_area_id": self.terrain_area_id,
            "terrain_feature_preset_id": self.terrain_feature_preset_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise TerrainLayoutError("Terrain feature area placement payload must be a mapping.")
        raw_payload = cast(TerrainFeatureAreaPlacementPayload, payload)
        return cls(
            feature_id=raw_payload["feature_id"],
            terrain_area_id=raw_payload["terrain_area_id"],
            terrain_feature_preset_id=raw_payload["terrain_feature_preset_id"],
            source_id=raw_payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class TerrainLayoutTemplate:
    terrain_layout_id: str
    name: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    terrain_features: tuple[TerrainFeatureTemplate, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_layout_id",
            _validate_unprefixed_identifier(
                "TerrainLayoutTemplate terrain_layout_id",
                self.terrain_layout_id,
                reserved_prefix="terrain-layout:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("TerrainLayoutTemplate name", self.name),
        )
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "TerrainLayoutTemplate battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "TerrainLayoutTemplate battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        features = _validate_feature_templates(
            "TerrainLayoutTemplate terrain_features",
            self.terrain_features,
        )
        _validate_features_within_battlefield(
            features=features,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        object.__setattr__(self, "terrain_features", features)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TerrainLayoutTemplate source_id", self.source_id),
        )

    def terrain_feature_ids(self) -> tuple[str, ...]:
        return tuple(feature.feature_id for feature in self.terrain_features)

    def to_payload(self) -> TerrainLayoutTemplatePayload:
        return {
            "terrain_layout_id": self.terrain_layout_id,
            "name": self.name,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: TerrainLayoutTemplatePayload) -> Self:
        return cls(
            terrain_layout_id=payload["terrain_layout_id"],
            name=payload["name"],
            battlefield_width_inches=payload["battlefield_width_inches"],
            battlefield_depth_inches=payload["battlefield_depth_inches"],
            terrain_features=tuple(
                TerrainFeatureTemplate.from_payload(feature_payload)
                for feature_payload in payload["terrain_features"]
            ),
            source_id=payload["source_id"],
        )


def _terrain_feature_kind_from_token(token: object) -> TerrainFeatureKind:
    try:
        return terrain_feature_kind_from_token(token)
    except RulesetDescriptorError as exc:
        raise TerrainLayoutError("Unsupported terrain feature kind token.") from exc


def _validate_feature_templates(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureTemplate, ...]:
    if type(values) is not tuple:
        raise TerrainLayoutError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureTemplate] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureTemplate:
            raise TerrainLayoutError(f"{field_name} must contain TerrainFeatureTemplate values.")
        if value.feature_id in seen:
            raise TerrainLayoutError(f"{field_name} must not contain duplicate feature IDs.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_wall_templates(
    field_name: str,
    values: object,
) -> tuple[TerrainWallTemplate, ...]:
    if type(values) is not tuple:
        raise TerrainLayoutError(f"{field_name} must be a tuple.")
    walls: list[TerrainWallTemplate] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainWallTemplate:
            raise TerrainLayoutError(f"{field_name} must contain TerrainWallTemplate values.")
        if value.wall_id in seen:
            raise TerrainLayoutError(f"{field_name} must not contain duplicate wall IDs.")
        seen.add(value.wall_id)
        walls.append(value)
    return tuple(sorted(walls, key=lambda wall: wall.wall_id))


def _validate_floor_templates(
    field_name: str,
    values: object,
) -> tuple[TerrainFloorTemplate, ...]:
    if type(values) is not tuple:
        raise TerrainLayoutError(f"{field_name} must be a tuple.")
    floors: list[TerrainFloorTemplate] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFloorTemplate:
            raise TerrainLayoutError(f"{field_name} must contain TerrainFloorTemplate values.")
        if value.floor_id in seen:
            raise TerrainLayoutError(f"{field_name} must not contain duplicate floor IDs.")
        seen.add(value.floor_id)
        floors.append(value)
    return tuple(sorted(floors, key=lambda floor: floor.floor_id))


def _rotated_rectangle_bounds(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
    rotation_degrees: float,
) -> tuple[float, float, float, float]:
    center_x = _validate_finite_number("rotated rectangle center_x_inches", center_x_inches)
    center_y = _validate_finite_number("rotated rectangle center_y_inches", center_y_inches)
    width = _validate_positive_number("rotated rectangle width_inches", width_inches)
    depth = _validate_positive_number("rotated rectangle depth_inches", depth_inches)
    rotation = _validate_finite_number("rotated rectangle rotation_degrees", rotation_degrees)
    half_width = width / 2.0
    half_depth = depth / 2.0
    corners = tuple(
        _rotate_local_point(
            x_inches=x,
            y_inches=y,
            rotation_degrees=rotation,
            origin_x_inches=center_x,
            origin_y_inches=center_y,
        )
        for x, y in (
            (-half_width, -half_depth),
            (half_width, -half_depth),
            (half_width, half_depth),
            (-half_width, half_depth),
        )
    )
    x_values = tuple(point[0] for point in corners)
    y_values = tuple(point[1] for point in corners)
    return (min(x_values), min(y_values), max(x_values), max(y_values))


def _rotate_local_point(
    *,
    x_inches: float,
    y_inches: float,
    rotation_degrees: float,
    origin_x_inches: float,
    origin_y_inches: float,
) -> tuple[float, float]:
    x = _validate_finite_number("rotate local point x_inches", x_inches)
    y = _validate_finite_number("rotate local point y_inches", y_inches)
    rotation = _validate_finite_number("rotate local point rotation_degrees", rotation_degrees)
    origin_x = _validate_finite_number("rotate local point origin_x_inches", origin_x_inches)
    origin_y = _validate_finite_number("rotate local point origin_y_inches", origin_y_inches)
    radians = math.radians(rotation)
    cosine = math.cos(radians)
    sine = math.sin(radians)
    return (
        origin_x + (x * cosine) - (y * sine),
        origin_y + (x * sine) + (y * cosine),
    )


def _validate_display_geometry(
    field_name: str,
    value: object,
    *,
    feature_bounds: tuple[float, float, float, float],
) -> TerrainDisplayGeometry:
    if type(value) is not TerrainDisplayGeometry:
        raise TerrainLayoutError(f"{field_name} must be a TerrainDisplayGeometry.")
    if not value.is_within_bounds(feature_bounds):
        raise TerrainLayoutError(f"{field_name} polygon must fit its footprint.")
    return value


def _validate_features_within_battlefield(
    *,
    features: tuple[TerrainFeatureTemplate, ...],
    width: float,
    depth: float,
) -> None:
    for feature in features:
        min_x, min_y, max_x, max_y = feature.bounds()
        if min_x < 0.0 or max_x > width or min_y < 0.0 or max_y > depth:
            raise TerrainLayoutError("Terrain feature footprint must be within the battlefield.")


def _validate_part_bounds_within_feature(
    *,
    part_id: str,
    part_bounds: tuple[float, float, float, float],
    feature_bounds: tuple[float, float, float, float],
) -> None:
    part_min_x, part_min_y, part_max_x, part_max_y = part_bounds
    feature_min_x, feature_min_y, feature_max_x, feature_max_y = feature_bounds
    if (
        part_min_x < feature_min_x
        or part_min_y < feature_min_y
        or part_max_x > feature_max_x
        or part_max_y > feature_max_y
    ):
        raise TerrainLayoutError(f"Terrain template part {part_id} must fit its footprint.")


def _validate_unprefixed_identifier(
    field_name: str,
    value: object,
    *,
    reserved_prefix: str,
) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(reserved_prefix):
        raise TerrainLayoutError(f"{field_name} must not include the stable identity prefix.")
    return identifier


_validate_identifier = IdentifierValidator(TerrainLayoutError)


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise TerrainLayoutError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise TerrainLayoutError(f"{field_name} must be finite.")
    return number


def _validate_non_negative_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number < 0.0:
        raise TerrainLayoutError(f"{field_name} must not be negative.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise TerrainLayoutError(f"{field_name} must be greater than 0.")
    return number
