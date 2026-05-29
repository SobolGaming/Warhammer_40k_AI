from __future__ import annotations

import math
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
class CollisionQueryResult:
    blocker_ids: tuple[str, ...]
    broadphase_check_count: int
    exact_check_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "blocker_ids",
            _validate_identifier_tuple("CollisionQueryResult blocker_ids", self.blocker_ids),
        )
        object.__setattr__(
            self,
            "broadphase_check_count",
            _validate_non_negative_int(
                "CollisionQueryResult broadphase_check_count",
                self.broadphase_check_count,
            ),
        )
        object.__setattr__(
            self,
            "exact_check_count",
            _validate_non_negative_int(
                "CollisionQueryResult exact_check_count",
                self.exact_check_count,
            ),
        )
        if self.exact_check_count > self.broadphase_check_count:
            raise GeometryError(
                "CollisionQueryResult exact checks cannot exceed broadphase checks."
            )

    @property
    def broadphase_rejection_count(self) -> int:
        return self.broadphase_check_count - self.exact_check_count


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
        return self.model_collision_query(model).blocker_ids

    def model_collision_query(self, model: Model) -> CollisionQueryResult:
        moving_model = _validate_model("model", model)
        colliding: list[str] = []
        exact_check_count = 0
        for blocker in self.model_blockers:
            if not _model_collision_broadphase_match(moving_model, blocker):
                continue
            exact_check_count += 1
            if (
                moving_model.base_overlaps(blocker)
                and moving_model.volume.vertical_gap_to(
                    moving_model.pose,
                    blocker.volume,
                    blocker.pose,
                )
                == 0.0
            ):
                colliding.append(blocker.model_id)
        return CollisionQueryResult(
            blocker_ids=tuple(sorted(colliding)),
            broadphase_check_count=len(self.model_blockers),
            exact_check_count=exact_check_count,
        )

    def colliding_terrain_ids(self, model: Model) -> tuple[str, ...]:
        return self.terrain_collision_query(model).blocker_ids

    def terrain_collision_query(self, model: Model) -> CollisionQueryResult:
        moving_model = _validate_model("model", model)
        colliding: list[str] = []
        exact_check_count = 0
        for terrain in self.terrain_blockers:
            if not _terrain_collision_broadphase_match(moving_model, terrain):
                continue
            exact_check_count += 1
            if terrain.intersects_model(moving_model):
                colliding.append(terrain.terrain_id)
        return CollisionQueryResult(
            blocker_ids=tuple(sorted(colliding)),
            broadphase_check_count=len(self.terrain_blockers),
            exact_check_count=exact_check_count,
        )

    def engagement_model_ids(
        self,
        model: Model,
        horizontal_inches: float,
        vertical_inches: float,
    ) -> tuple[str, ...]:
        return self.engagement_query(
            model,
            horizontal_inches=horizontal_inches,
            vertical_inches=vertical_inches,
        ).blocker_ids

    def engagement_query(
        self,
        model: Model,
        horizontal_inches: float,
        vertical_inches: float,
    ) -> CollisionQueryResult:
        moving_model = _validate_model("model", model)
        horizontal_limit = _validate_non_negative_number("horizontal_inches", horizontal_inches)
        vertical_limit = _validate_non_negative_number("vertical_inches", vertical_inches)
        engagement: list[str] = []
        exact_check_count = 0
        for blocker in self.engagement_blockers:
            if not _engagement_broadphase_match(
                moving_model,
                blocker,
                horizontal_inches=horizontal_limit,
                vertical_inches=vertical_limit,
            ):
                continue
            exact_check_count += 1
            if moving_model.is_within_engagement_range(
                blocker,
                horizontal_inches=horizontal_limit,
                vertical_inches=vertical_limit,
            ):
                engagement.append(blocker.model_id)
        return CollisionQueryResult(
            blocker_ids=tuple(sorted(engagement)),
            broadphase_check_count=len(self.engagement_blockers),
            exact_check_count=exact_check_count,
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


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 0:
        raise GeometryError(f"{field_name} must not be negative.")
    return value


def _validate_non_negative_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GeometryError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise GeometryError(f"{field_name} must be finite.")
    if number < 0.0:
        raise GeometryError(f"{field_name} must not be negative.")
    return number


def _model_collision_broadphase_match(moving_model: Model, blocker: Model) -> bool:
    if _model_vertical_gap(moving_model, blocker) != 0.0:
        return False
    return _model_center_distance(moving_model, blocker) <= (
        moving_model.base.max_radius() + blocker.base.max_radius()
    )


def _terrain_collision_broadphase_match(moving_model: Model, terrain: TerrainVolume) -> bool:
    if _model_terrain_vertical_gap(moving_model, terrain) != 0.0:
        return False
    min_x, min_y, max_x, max_y = terrain.horizontal_bounds()
    radius = moving_model.base.max_radius()
    model_x = moving_model.pose.position.x
    model_y = moving_model.pose.position.y
    return (
        model_x >= min_x - radius
        and model_x <= max_x + radius
        and model_y >= min_y - radius
        and model_y <= max_y + radius
    )


def _engagement_broadphase_match(
    moving_model: Model,
    blocker: Model,
    *,
    horizontal_inches: float,
    vertical_inches: float,
) -> bool:
    if _model_vertical_gap(moving_model, blocker) > vertical_inches:
        return False
    return _model_center_distance(moving_model, blocker) <= (
        moving_model.base.max_radius() + blocker.base.max_radius() + horizontal_inches
    )


def _model_center_distance(first: Model, second: Model) -> float:
    return math.hypot(
        second.pose.position.x - first.pose.position.x,
        second.pose.position.y - first.pose.position.y,
    )


def _model_vertical_gap(first: Model, second: Model) -> float:
    return first.volume.vertical_gap_to(first.pose, second.volume, second.pose)


def _model_terrain_vertical_gap(model: Model, terrain: TerrainVolume) -> float:
    model_bottom, model_top = model.volume.vertical_interval(model.pose)
    terrain_bottom, terrain_top = terrain.vertical_interval()
    if model_top < terrain_bottom:
        return terrain_bottom - model_top
    if terrain_top < model_bottom:
        return model_bottom - terrain_top
    return 0.0
