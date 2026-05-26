from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.spatial_index import SpatialIndex
from warhammer40k_core.geometry.terrain import (
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload


class CollisionSetPayload(TypedDict):
    model_blockers: list[ModelPayload]
    terrain_blockers: list[TerrainVolumePayload]
    engagement_blockers: list[ModelPayload]


@dataclass(frozen=True, slots=True)
class CollisionSet:
    model_blockers: tuple[Model, ...] = ()
    terrain_blockers: tuple[TerrainVolume, ...] = ()
    engagement_blockers: tuple[Model, ...] = ()

    def __post_init__(self) -> None:
        if type(self.model_blockers) is not tuple:
            raise GeometryError("CollisionSet model_blockers must be a tuple.")
        if type(self.terrain_blockers) is not tuple:
            raise GeometryError("CollisionSet terrain_blockers must be a tuple.")
        if type(self.engagement_blockers) is not tuple:
            raise GeometryError("CollisionSet engagement_blockers must be a tuple.")

        model_blockers = tuple(
            _validate_model("CollisionSet model_blocker", model) for model in self.model_blockers
        )
        terrain_blockers = tuple(
            _validate_terrain("CollisionSet terrain_blocker", terrain)
            for terrain in self.terrain_blockers
        )
        engagement_blockers = tuple(
            _validate_model("CollisionSet engagement_blocker", model)
            for model in self.engagement_blockers
        )
        _validate_unique_model_ids("CollisionSet model_blockers", model_blockers)
        _validate_unique_model_ids("CollisionSet engagement_blockers", engagement_blockers)
        _validate_unique_terrain_ids(terrain_blockers)
        object.__setattr__(
            self,
            "model_blockers",
            tuple(sorted(model_blockers, key=lambda model: model.model_id)),
        )
        object.__setattr__(
            self,
            "terrain_blockers",
            tuple(sorted(terrain_blockers, key=lambda terrain: terrain.terrain_id)),
        )
        object.__setattr__(
            self,
            "engagement_blockers",
            tuple(sorted(engagement_blockers, key=lambda model: model.model_id)),
        )

    @classmethod
    def empty(cls) -> Self:
        return cls()

    @classmethod
    def from_spatial_index(
        cls,
        spatial_index: SpatialIndex,
        moving_model_ids: tuple[str, ...],
        engagement_model_ids: tuple[str, ...] = (),
    ) -> Self:
        valid_index = _validate_spatial_index("spatial_index", spatial_index)
        moving_ids = _validate_identifier_tuple("moving_model_ids", moving_model_ids)
        engagement_ids = _validate_identifier_tuple("engagement_model_ids", engagement_model_ids)
        moving_id_set = set(moving_ids)
        engagement_id_set = set(engagement_ids)
        return cls(
            model_blockers=tuple(
                model for model in valid_index.models if model.model_id not in moving_id_set
            ),
            terrain_blockers=valid_index.terrain,
            engagement_blockers=tuple(
                model for model in valid_index.models if model.model_id in engagement_id_set
            ),
        )

    def colliding_model_ids(self, model: Model) -> tuple[str, ...]:
        moving_model = _validate_model("model", model)
        colliding = [
            blocker.model_id
            for blocker in self.model_blockers
            if moving_model.base_overlaps(blocker)
            and moving_model.volume.vertical_gap_to(
                moving_model.pose,
                blocker.volume,
                blocker.pose,
            )
            == 0.0
        ]
        return tuple(sorted(colliding))

    def colliding_terrain_ids(self, model: Model) -> tuple[str, ...]:
        moving_model = _validate_model("model", model)
        return tuple(
            terrain.terrain_id
            for terrain in self.terrain_blockers
            if terrain.intersects_model(moving_model)
        )

    def engagement_model_ids(
        self,
        model: Model,
        horizontal_inches: float,
        vertical_inches: float,
    ) -> tuple[str, ...]:
        moving_model = _validate_model("model", model)
        return tuple(
            blocker.model_id
            for blocker in self.engagement_blockers
            if moving_model.is_within_engagement_range(
                blocker,
                horizontal_inches=horizontal_inches,
                vertical_inches=vertical_inches,
            )
        )

    def to_payload(self) -> CollisionSetPayload:
        return {
            "model_blockers": [model.to_payload() for model in self.model_blockers],
            "terrain_blockers": [terrain.to_payload() for terrain in self.terrain_blockers],
            "engagement_blockers": [model.to_payload() for model in self.engagement_blockers],
        }

    @classmethod
    def from_payload(cls, payload: CollisionSetPayload) -> Self:
        return cls(
            model_blockers=tuple(Model.from_payload(model) for model in payload["model_blockers"]),
            terrain_blockers=tuple(
                terrain_volume_from_payload(terrain) for terrain in payload["terrain_blockers"]
            ),
            engagement_blockers=tuple(
                Model.from_payload(model) for model in payload["engagement_blockers"]
            ),
        )


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_terrain(field_name: str, value: object) -> TerrainVolume:
    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


def _validate_spatial_index(field_name: str, value: object) -> SpatialIndex:
    if type(value) is not SpatialIndex:
        raise GeometryError(f"{field_name} must be a SpatialIndex.")
    return value


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GeometryError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        if type(value) is not str:
            raise GeometryError(f"{field_name} values must be strings.")
        stripped = value.strip()
        if not stripped:
            raise GeometryError(f"{field_name} values must not be empty.")
        if stripped in seen:
            raise GeometryError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(stripped)
        validated.append(stripped)
    return tuple(validated)


def _validate_unique_model_ids(field_name: str, models: tuple[Model, ...]) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError(f"{field_name} must not contain duplicate model IDs.")
        seen.add(model.model_id)


def _validate_unique_terrain_ids(terrain: tuple[TerrainVolume, ...]) -> None:
    seen: set[str] = set()
    for volume in terrain:
        if volume.terrain_id in seen:
            raise GeometryError("CollisionSet terrain_blockers must not contain duplicate IDs.")
        seen.add(volume.terrain_id)
