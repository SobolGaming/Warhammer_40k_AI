from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptorError,
)
from warhammer40k_core.core.ruleset_descriptor import (
    TerrainFeatureKind as TerrainFeatureKind,
)
from warhammer40k_core.core.ruleset_descriptor import (
    terrain_feature_kind_from_token as core_terrain_feature_kind_from_token,
)
from warhammer40k_core.core.terrain_display import (
    TerrainDisplayGeometry,
    TerrainDisplayGeometryPayload,
)
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


class TerrainWallDefinitionPayload(TypedDict):
    wall_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    height_inches: float


class TerrainFloorDefinitionPayload(TypedDict):
    floor_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    thickness_inches: float


class TerrainSupportSurfacePayload(TypedDict):
    surface_id: str
    terrain_feature_id: str
    z_inches: float
    center_x_inches: float
    center_y_inches: float
    width_inches: float
    depth_inches: float
    no_overhang_required: bool


class TerrainFeatureDefinitionPayload(TypedDict):
    feature_id: str
    feature_kind: str
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    display_geometry: TerrainDisplayGeometryPayload
    walls: list[TerrainWallDefinitionPayload]
    floors: list[TerrainFloorDefinitionPayload]
    source_id: str | None


class TerrainFeatureRulesGeometryPayload(TypedDict):
    feature_id: str
    feature_kind: str
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    walls: list[TerrainWallDefinitionPayload]
    floors: list[TerrainFloorDefinitionPayload]


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

    def top_z_inches(self) -> float:
        return self.bottom_center.z + self.height

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


@dataclass(frozen=True, slots=True)
class TerrainWallDefinition:
    wall_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    height_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wall_id",
            _validate_definition_id(
                "TerrainWallDefinition wall_id",
                self.wall_id,
                reserved_prefix="wall:",
            ),
        )
        object.__setattr__(
            self,
            "center_x_inches",
            _validate_finite_coordinate(
                "TerrainWallDefinition center_x_inches",
                self.center_x_inches,
            ),
        )
        object.__setattr__(
            self,
            "center_y_inches",
            _validate_finite_coordinate(
                "TerrainWallDefinition center_y_inches",
                self.center_y_inches,
            ),
        )
        object.__setattr__(
            self,
            "bottom_z_inches",
            _validate_non_negative_coordinate(
                "TerrainWallDefinition bottom_z_inches",
                self.bottom_z_inches,
            ),
        )
        object.__setattr__(
            self,
            "width_inches",
            _validate_positive_number(
                "TerrainWallDefinition width_inches",
                self.width_inches,
            ),
        )
        object.__setattr__(
            self,
            "depth_inches",
            _validate_positive_number(
                "TerrainWallDefinition depth_inches",
                self.depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "height_inches",
            _validate_positive_number(
                "TerrainWallDefinition height_inches",
                self.height_inches,
            ),
        )

    def bounds(self) -> tuple[float, float, float, float]:
        half_width = self.width_inches / 2.0
        half_depth = self.depth_inches / 2.0
        return (
            self.center_x_inches - half_width,
            self.center_y_inches - half_depth,
            self.center_x_inches + half_width,
            self.center_y_inches + half_depth,
        )

    def to_terrain_volume(self, *, feature_id: str) -> ObstacleVolume:
        terrain_feature_id = _validate_definition_id(
            "TerrainWallDefinition feature_id",
            feature_id,
            reserved_prefix="terrain:",
        )
        return ObstacleVolume(
            terrain_id=f"{terrain_feature_id}:{self.wall_id}",
            bottom_center=Point3(
                self.center_x_inches,
                self.center_y_inches,
                self.bottom_z_inches,
            ),
            width=self.width_inches,
            depth=self.depth_inches,
            height=self.height_inches,
        )

    def to_payload(self) -> TerrainWallDefinitionPayload:
        return {
            "wall_id": self.wall_id,
            "center_x_inches": self.center_x_inches,
            "center_y_inches": self.center_y_inches,
            "bottom_z_inches": self.bottom_z_inches,
            "width_inches": self.width_inches,
            "depth_inches": self.depth_inches,
            "height_inches": self.height_inches,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GeometryError("Terrain wall payload must be a mapping.")
        raw_payload = cast(TerrainWallDefinitionPayload, payload)
        return cls(
            wall_id=raw_payload["wall_id"],
            center_x_inches=raw_payload["center_x_inches"],
            center_y_inches=raw_payload["center_y_inches"],
            bottom_z_inches=raw_payload["bottom_z_inches"],
            width_inches=raw_payload["width_inches"],
            depth_inches=raw_payload["depth_inches"],
            height_inches=raw_payload["height_inches"],
        )


@dataclass(frozen=True, slots=True)
class TerrainFloorDefinition:
    floor_id: str
    center_x_inches: float
    center_y_inches: float
    bottom_z_inches: float
    width_inches: float
    depth_inches: float
    thickness_inches: float

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "floor_id",
            _validate_definition_id(
                "TerrainFloorDefinition floor_id",
                self.floor_id,
                reserved_prefix="floor:",
            ),
        )
        object.__setattr__(
            self,
            "center_x_inches",
            _validate_finite_coordinate(
                "TerrainFloorDefinition center_x_inches",
                self.center_x_inches,
            ),
        )
        object.__setattr__(
            self,
            "center_y_inches",
            _validate_finite_coordinate(
                "TerrainFloorDefinition center_y_inches",
                self.center_y_inches,
            ),
        )
        object.__setattr__(
            self,
            "bottom_z_inches",
            _validate_non_negative_coordinate(
                "TerrainFloorDefinition bottom_z_inches",
                self.bottom_z_inches,
            ),
        )
        object.__setattr__(
            self,
            "width_inches",
            _validate_positive_number(
                "TerrainFloorDefinition width_inches",
                self.width_inches,
            ),
        )
        object.__setattr__(
            self,
            "depth_inches",
            _validate_positive_number(
                "TerrainFloorDefinition depth_inches",
                self.depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "thickness_inches",
            _validate_positive_number(
                "TerrainFloorDefinition thickness_inches",
                self.thickness_inches,
            ),
        )

    def bounds(self) -> tuple[float, float, float, float]:
        half_width = self.width_inches / 2.0
        half_depth = self.depth_inches / 2.0
        return (
            self.center_x_inches - half_width,
            self.center_y_inches - half_depth,
            self.center_x_inches + half_width,
            self.center_y_inches + half_depth,
        )

    def to_terrain_volume(self, *, feature_id: str) -> TerrainVolume:
        terrain_feature_id = _validate_definition_id(
            "TerrainFloorDefinition feature_id",
            feature_id,
            reserved_prefix="terrain:",
        )
        return TerrainVolume(
            terrain_id=f"{terrain_feature_id}:{self.floor_id}",
            bottom_center=Point3(
                self.center_x_inches,
                self.center_y_inches,
                self.bottom_z_inches,
            ),
            width=self.width_inches,
            depth=self.depth_inches,
            height=self.thickness_inches,
            blocks_line_of_sight=False,
        )

    def to_payload(self) -> TerrainFloorDefinitionPayload:
        return {
            "floor_id": self.floor_id,
            "center_x_inches": self.center_x_inches,
            "center_y_inches": self.center_y_inches,
            "bottom_z_inches": self.bottom_z_inches,
            "width_inches": self.width_inches,
            "depth_inches": self.depth_inches,
            "thickness_inches": self.thickness_inches,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GeometryError("Terrain floor payload must be a mapping.")
        raw_payload = cast(TerrainFloorDefinitionPayload, payload)
        return cls(
            floor_id=raw_payload["floor_id"],
            center_x_inches=raw_payload["center_x_inches"],
            center_y_inches=raw_payload["center_y_inches"],
            bottom_z_inches=raw_payload["bottom_z_inches"],
            width_inches=raw_payload["width_inches"],
            depth_inches=raw_payload["depth_inches"],
            thickness_inches=raw_payload["thickness_inches"],
        )


@dataclass(frozen=True, slots=True)
class TerrainSupportSurface:
    surface_id: str
    terrain_feature_id: str
    z_inches: float
    center_x_inches: float
    center_y_inches: float
    width_inches: float
    depth_inches: float
    no_overhang_required: bool

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "surface_id",
            _validate_definition_id(
                "TerrainSupportSurface surface_id",
                self.surface_id,
                reserved_prefix="surface:",
            ),
        )
        object.__setattr__(
            self,
            "terrain_feature_id",
            _validate_definition_id(
                "TerrainSupportSurface terrain_feature_id",
                self.terrain_feature_id,
                reserved_prefix="terrain:",
            ),
        )
        object.__setattr__(
            self,
            "z_inches",
            _validate_non_negative_coordinate("TerrainSupportSurface z_inches", self.z_inches),
        )
        object.__setattr__(
            self,
            "center_x_inches",
            _validate_finite_coordinate(
                "TerrainSupportSurface center_x_inches",
                self.center_x_inches,
            ),
        )
        object.__setattr__(
            self,
            "center_y_inches",
            _validate_finite_coordinate(
                "TerrainSupportSurface center_y_inches",
                self.center_y_inches,
            ),
        )
        object.__setattr__(
            self,
            "width_inches",
            _validate_positive_number(
                "TerrainSupportSurface width_inches",
                self.width_inches,
            ),
        )
        object.__setattr__(
            self,
            "depth_inches",
            _validate_positive_number(
                "TerrainSupportSurface depth_inches",
                self.depth_inches,
            ),
        )
        if type(self.no_overhang_required) is not bool:
            raise GeometryError("TerrainSupportSurface no_overhang_required must be a bool.")

    def bounds(self) -> tuple[float, float, float, float]:
        half_width = self.width_inches / 2.0
        half_depth = self.depth_inches / 2.0
        return (
            self.center_x_inches - half_width,
            self.center_y_inches - half_depth,
            self.center_x_inches + half_width,
            self.center_y_inches + half_depth,
        )

    def to_payload(self) -> TerrainSupportSurfacePayload:
        return {
            "surface_id": self.surface_id,
            "terrain_feature_id": self.terrain_feature_id,
            "z_inches": self.z_inches,
            "center_x_inches": self.center_x_inches,
            "center_y_inches": self.center_y_inches,
            "width_inches": self.width_inches,
            "depth_inches": self.depth_inches,
            "no_overhang_required": self.no_overhang_required,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GeometryError("Terrain support surface payload must be a mapping.")
        raw_payload = cast(TerrainSupportSurfacePayload, payload)
        return cls(
            surface_id=raw_payload["surface_id"],
            terrain_feature_id=raw_payload["terrain_feature_id"],
            z_inches=raw_payload["z_inches"],
            center_x_inches=raw_payload["center_x_inches"],
            center_y_inches=raw_payload["center_y_inches"],
            width_inches=raw_payload["width_inches"],
            depth_inches=raw_payload["depth_inches"],
            no_overhang_required=raw_payload["no_overhang_required"],
        )


@dataclass(frozen=True, slots=True)
class TerrainFeatureDefinition:
    feature_id: str
    feature_kind: TerrainFeatureKind
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    display_geometry: TerrainDisplayGeometry
    walls: tuple[TerrainWallDefinition, ...] = ()
    floors: tuple[TerrainFloorDefinition, ...] = ()
    source_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "feature_id",
            _validate_definition_id(
                "TerrainFeatureDefinition feature_id",
                self.feature_id,
                reserved_prefix="terrain:",
            ),
        )
        object.__setattr__(
            self,
            "feature_kind",
            terrain_feature_kind_from_token(self.feature_kind),
        )
        object.__setattr__(
            self,
            "footprint_center_x_inches",
            _validate_finite_coordinate(
                "TerrainFeatureDefinition footprint_center_x_inches",
                self.footprint_center_x_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_center_y_inches",
            _validate_finite_coordinate(
                "TerrainFeatureDefinition footprint_center_y_inches",
                self.footprint_center_y_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_width_inches",
            _validate_positive_number(
                "TerrainFeatureDefinition footprint_width_inches",
                self.footprint_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "footprint_depth_inches",
            _validate_positive_number(
                "TerrainFeatureDefinition footprint_depth_inches",
                self.footprint_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "display_geometry",
            _validate_display_geometry(
                "TerrainFeatureDefinition display_geometry",
                self.display_geometry,
                feature_bounds=self.bounds(),
            ),
        )
        object.__setattr__(self, "walls", _validate_wall_tuple(self.walls))
        object.__setattr__(self, "floors", _validate_floor_tuple(self.floors))
        object.__setattr__(self, "source_id", _validate_optional_source_id(self.source_id))
        if self.feature_kind is TerrainFeatureKind.RUINS and (not self.walls or not self.floors):
            raise GeometryError("Ruins terrain features require explicit walls and floors.")
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

    def wall_volumes(self) -> tuple[ObstacleVolume, ...]:
        return tuple(wall.to_terrain_volume(feature_id=self.feature_id) for wall in self.walls)

    def floor_volumes(self) -> tuple[TerrainVolume, ...]:
        return tuple(floor.to_terrain_volume(feature_id=self.feature_id) for floor in self.floors)

    def terrain_volumes(self) -> tuple[TerrainVolume, ...]:
        volumes = (*self.floor_volumes(), *self.wall_volumes())
        return tuple(sorted(volumes, key=lambda volume: volume.terrain_id))

    def support_surfaces(self, *, no_overhang_required: bool) -> tuple[TerrainSupportSurface, ...]:
        surfaces = tuple(
            TerrainSupportSurface(
                surface_id=floor.floor_id,
                terrain_feature_id=self.feature_id,
                z_inches=floor.bottom_z_inches,
                center_x_inches=floor.center_x_inches,
                center_y_inches=floor.center_y_inches,
                width_inches=floor.width_inches,
                depth_inches=floor.depth_inches,
                no_overhang_required=no_overhang_required,
            )
            for floor in self.floors
        )
        return tuple(sorted(surfaces, key=lambda surface: surface.surface_id))

    def to_payload(self) -> TerrainFeatureDefinitionPayload:
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

    def to_rules_geometry_payload(self) -> TerrainFeatureRulesGeometryPayload:
        return {
            "feature_id": self.feature_id,
            "feature_kind": self.feature_kind.value,
            "footprint_center_x_inches": self.footprint_center_x_inches,
            "footprint_center_y_inches": self.footprint_center_y_inches,
            "footprint_width_inches": self.footprint_width_inches,
            "footprint_depth_inches": self.footprint_depth_inches,
            "walls": [wall.to_payload() for wall in self.walls],
            "floors": [floor.to_payload() for floor in self.floors],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GeometryError("Terrain feature payload must be a mapping.")
        raw_payload = cast(TerrainFeatureDefinitionPayload, payload)
        walls = tuple(
            TerrainWallDefinition.from_payload(wall_payload)
            for wall_payload in raw_payload["walls"]
        )
        floors = tuple(
            TerrainFloorDefinition.from_payload(floor_payload)
            for floor_payload in raw_payload["floors"]
        )
        return cls(
            feature_id=raw_payload["feature_id"],
            feature_kind=terrain_feature_kind_from_token(raw_payload["feature_kind"]),
            footprint_center_x_inches=raw_payload["footprint_center_x_inches"],
            footprint_center_y_inches=raw_payload["footprint_center_y_inches"],
            footprint_width_inches=raw_payload["footprint_width_inches"],
            footprint_depth_inches=raw_payload["footprint_depth_inches"],
            display_geometry=TerrainDisplayGeometry.from_payload(raw_payload["display_geometry"]),
            walls=walls,
            floors=floors,
            source_id=raw_payload["source_id"],
        )

    def _validate_parts_within_footprint(self) -> None:
        feature_min_x, feature_min_y, feature_max_x, feature_max_y = self.bounds()
        for wall in self.walls:
            _validate_part_bounds_within_feature(
                part_id=wall.wall_id,
                part_bounds=wall.bounds(),
                feature_bounds=(feature_min_x, feature_min_y, feature_max_x, feature_max_y),
            )
        for floor in self.floors:
            _validate_part_bounds_within_feature(
                part_id=floor.floor_id,
                part_bounds=floor.bounds(),
                feature_bounds=(feature_min_x, feature_min_y, feature_max_x, feature_max_y),
            )


def terrain_feature_kind_from_token(token: object) -> TerrainFeatureKind:
    try:
        return core_terrain_feature_kind_from_token(token)
    except RulesetDescriptorError as exc:
        raise GeometryError("Unsupported terrain feature kind token.") from exc


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


def _validate_definition_id(
    field_name: str,
    value: object,
    *,
    reserved_prefix: str,
) -> str:
    if type(value) is not str:
        raise GeometryError(f"{field_name} must be a string.")
    identifier = value.strip()
    if not identifier:
        raise GeometryError(f"{field_name} must not be empty.")
    if identifier.startswith(reserved_prefix):
        raise GeometryError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_optional_source_id(value: object) -> str | None:
    if value is None:
        return None
    return _validate_definition_id(
        "TerrainFeatureDefinition source_id",
        value,
        reserved_prefix="source:",
    )


def _validate_display_geometry(
    field_name: str,
    value: object,
    *,
    feature_bounds: tuple[float, float, float, float],
) -> TerrainDisplayGeometry:
    if type(value) is not TerrainDisplayGeometry:
        raise GeometryError(f"{field_name} must be a TerrainDisplayGeometry.")
    if not value.is_within_bounds(feature_bounds):
        raise GeometryError(f"{field_name} polygon must fit feature footprint.")
    return value


def _validate_finite_coordinate(field_name: str, value: object) -> float:
    return validate_finite_number(field_name, value)


def _validate_non_negative_coordinate(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number < 0.0:
        raise GeometryError(f"{field_name} must be non-negative.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = validate_finite_number(field_name, value)
    if number <= 0.0:
        raise GeometryError(f"{field_name} must be greater than 0.")
    return number


def _validate_wall_tuple(
    walls: tuple[TerrainWallDefinition, ...],
) -> tuple[TerrainWallDefinition, ...]:
    if type(walls) is not tuple:
        raise GeometryError("TerrainFeatureDefinition walls must be a tuple.")
    wall_ids: set[str] = set()
    for wall in walls:
        if type(wall) is not TerrainWallDefinition:
            raise GeometryError(
                "TerrainFeatureDefinition walls must contain TerrainWallDefinition values."
            )
        if wall.wall_id in wall_ids:
            raise GeometryError(f"Duplicate terrain wall ID: {wall.wall_id}.")
        wall_ids.add(wall.wall_id)
    return tuple(sorted(walls, key=lambda wall: wall.wall_id))


def _validate_floor_tuple(
    floors: tuple[TerrainFloorDefinition, ...],
) -> tuple[TerrainFloorDefinition, ...]:
    if type(floors) is not tuple:
        raise GeometryError("TerrainFeatureDefinition floors must be a tuple.")
    floor_ids: set[str] = set()
    for floor in floors:
        if type(floor) is not TerrainFloorDefinition:
            raise GeometryError(
                "TerrainFeatureDefinition floors must contain TerrainFloorDefinition values."
            )
        if floor.floor_id in floor_ids:
            raise GeometryError(f"Duplicate terrain floor ID: {floor.floor_id}.")
        floor_ids.add(floor.floor_id)
    return tuple(sorted(floors, key=lambda floor: floor.floor_id))


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
        raise GeometryError(f"Terrain part {part_id} must be contained within feature footprint.")
