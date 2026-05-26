from __future__ import annotations

from dataclasses import dataclass
from typing import Self

from warhammer40k_core.geometry.pose import GeometryError, Point3, validate_point3
from warhammer40k_core.geometry.terrain import ObstacleVolume, TerrainVolume
from warhammer40k_core.geometry.volume import Model


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

    def line_of_sight_blockers(self, start: Point3, end: Point3) -> tuple[ObstacleVolume, ...]:
        valid_start = validate_point3("start", start)
        valid_end = validate_point3("end", end)
        blockers: list[ObstacleVolume] = []
        for volume in self.terrain:
            if not isinstance(volume, ObstacleVolume):
                continue
            if volume.blocks_line_segment(valid_start, valid_end):
                blockers.append(volume)
        return tuple(sorted(blockers, key=lambda volume: volume.terrain_id))

    def has_clear_line_of_sight(self, start: Point3, end: Point3) -> bool:
        return not self.line_of_sight_blockers(start, end)


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
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
