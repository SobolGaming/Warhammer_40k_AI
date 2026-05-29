from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.geometry.measurement import (
    objective_marker_controls_model,
    objective_marker_endpoint_is_clear,
)
from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose, validate_point3
from warhammer40k_core.geometry.terrain import (
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload


class SpatialIndexPayload(TypedDict):
    models: list[ModelPayload]
    terrain: list[TerrainVolumePayload]
    generation: int


@dataclass(frozen=True, slots=True)
class SpatialIndex:
    models: tuple[Model, ...] = ()
    terrain: tuple[TerrainVolume, ...] = ()
    generation: int = 0

    def __post_init__(self) -> None:
        if type(self.models) is not tuple:
            raise GeometryError("SpatialIndex models must be a tuple.")
        if type(self.terrain) is not tuple:
            raise GeometryError("SpatialIndex terrain must be a tuple.")
        models = tuple(_validate_model("SpatialIndex model", model) for model in self.models)
        terrain = tuple(
            _validate_terrain_volume("SpatialIndex terrain", volume) for volume in self.terrain
        )
        _validate_unique_model_ids(models)
        _validate_unique_terrain_ids(terrain)
        object.__setattr__(self, "models", tuple(sorted(models, key=lambda model: model.model_id)))
        object.__setattr__(
            self,
            "terrain",
            tuple(sorted(terrain, key=lambda volume: volume.terrain_id)),
        )
        if type(self.generation) is not int:
            raise GeometryError("SpatialIndex generation must be an integer.")
        if self.generation < 0:
            raise GeometryError("SpatialIndex generation must not be negative.")

    @classmethod
    def empty(cls) -> Self:
        return cls()

    def with_model(self, model: Model) -> Self:
        valid_model = _validate_model("model", model)
        if any(existing.model_id == valid_model.model_id for existing in self.models):
            raise GeometryError("SpatialIndex model IDs must be unique.")
        return type(self)(
            models=(*self.models, valid_model),
            terrain=self.terrain,
            generation=self.generation + 1,
        )

    def with_terrain(self, terrain: TerrainVolume) -> Self:
        valid_terrain = _validate_terrain_volume("terrain", terrain)
        if any(existing.terrain_id == valid_terrain.terrain_id for existing in self.terrain):
            raise GeometryError("SpatialIndex terrain IDs must be unique.")
        return type(self)(
            models=self.models,
            terrain=(*self.terrain, valid_terrain),
            generation=self.generation + 1,
        )

    def models_intersecting_terrain(self, terrain: TerrainVolume) -> tuple[Model, ...]:
        valid_terrain = _validate_terrain_volume("terrain", terrain)
        return tuple(model for model in self.models if valid_terrain.intersects_model(model))

    def line_of_sight_blockers(self, start: Point3, end: Point3) -> tuple[TerrainVolume, ...]:
        valid_start = validate_point3("start", start)
        valid_end = validate_point3("end", end)
        blockers: list[TerrainVolume] = []
        for volume in self.terrain:
            if not volume.blocks_line_of_sight:
                continue
            if volume.blocks_line_segment(valid_start, valid_end):
                blockers.append(volume)
        return tuple(sorted(blockers, key=lambda volume: volume.terrain_id))

    def has_clear_line_of_sight(self, start: Point3, end: Point3) -> bool:
        return not self.line_of_sight_blockers(start, end)

    def models_controlling_objective_marker(
        self,
        objective_marker: ObjectiveMarker,
    ) -> tuple[Model, ...]:
        marker = _validate_objective_marker("objective_marker", objective_marker)
        marker_pose = Pose.at(marker.x_inches, marker.y_inches, marker.z_inches)
        return tuple(
            model
            for model in self.models
            if objective_marker_controls_model(
                marker_pose,
                model,
                marker_id=marker.objective_marker_id,
                horizontal_inches=marker.control_horizontal_inches,
                vertical_inches=marker.control_vertical_inches,
                marker_diameter_inches=marker.marker_diameter_inches,
            )
        )

    def models_overlapping_objective_marker_endpoint(
        self,
        objective_marker: ObjectiveMarker,
    ) -> tuple[Model, ...]:
        marker = _validate_objective_marker("objective_marker", objective_marker)
        marker_pose = Pose.at(marker.x_inches, marker.y_inches, marker.z_inches)
        return tuple(
            model
            for model in self.models
            if not objective_marker_endpoint_is_clear(
                marker_pose,
                model,
                marker_id=marker.objective_marker_id,
                marker_diameter_inches=marker.marker_diameter_inches,
            )
        )

    def to_payload(self) -> SpatialIndexPayload:
        return {
            "models": [model.to_payload() for model in self.models],
            "terrain": [volume.to_payload() for volume in self.terrain],
            "generation": self.generation,
        }

    @classmethod
    def from_payload(cls, payload: SpatialIndexPayload) -> Self:
        return cls(
            models=tuple(Model.from_payload(model) for model in payload["models"]),
            terrain=tuple(terrain_volume_from_payload(volume) for volume in payload["terrain"]),
            generation=payload["generation"],
        )


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_objective_marker(field_name: str, value: object) -> ObjectiveMarker:
    if type(value) is not ObjectiveMarker:
        raise GeometryError(f"{field_name} must be an ObjectiveMarker.")
    return value


def _validate_terrain_volume(field_name: str, value: object) -> TerrainVolume:
    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


def _validate_unique_model_ids(models: tuple[Model, ...]) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError("SpatialIndex model IDs must be unique.")
        seen.add(model.model_id)


def _validate_unique_terrain_ids(terrain: tuple[TerrainVolume, ...]) -> None:
    seen: set[str] = set()
    for volume in terrain:
        if volume.terrain_id in seen:
            raise GeometryError("SpatialIndex terrain IDs must be unique.")
        seen.add(volume.terrain_id)
