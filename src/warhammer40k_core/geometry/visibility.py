from __future__ import annotations

from dataclasses import dataclass, field
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.pose import (
    GeometryError,
    Point3,
    Point3Payload,
    validate_point3,
)
from warhammer40k_core.geometry.terrain import (
    TerrainVolume,
    TerrainVolumePayload,
    terrain_volume_from_payload,
)
from warhammer40k_core.geometry.volume import Model, ModelPayload

type VisibilityRay = tuple[Point3, Point3]


class VisibilityRayPayload(TypedDict):
    start: Point3Payload
    end: Point3Payload


class VisibilityQueryPayload(TypedDict):
    rays: list[VisibilityRayPayload]
    static_terrain: list[TerrainVolumePayload]
    dynamic_model_blockers: list[ModelPayload]


class VisibilityResultPayload(TypedDict):
    has_line_of_sight: bool
    checked_ray_count: int
    clear_ray_index: int | None
    blocking_terrain_ids: list[str]
    blocking_model_ids: list[str]
    checked_terrain_ids: list[str]
    checked_model_ids: list[str]
    metrics: VisibilityMetricsPayload


class VisibilityMetricsPayload(TypedDict):
    terrain_candidate_count: int
    model_candidate_count: int
    exact_terrain_check_count: int
    exact_model_check_count: int


@dataclass(frozen=True, slots=True)
class VisibilityQuery:
    rays: tuple[VisibilityRay, ...]
    static_terrain: tuple[TerrainVolume, ...] = ()
    dynamic_model_blockers: tuple[Model, ...] = ()

    def __post_init__(self) -> None:
        if type(self.rays) is not tuple:
            raise GeometryError("VisibilityQuery rays must be a tuple.")
        if not self.rays:
            raise GeometryError("VisibilityQuery rays must not be empty.")
        if type(self.static_terrain) is not tuple:
            raise GeometryError("VisibilityQuery static_terrain must be a tuple.")
        if type(self.dynamic_model_blockers) is not tuple:
            raise GeometryError("VisibilityQuery dynamic_model_blockers must be a tuple.")

        rays = tuple(_validate_ray(ray) for ray in self.rays)
        terrain = tuple(
            _validate_terrain("VisibilityQuery static terrain", volume)
            for volume in self.static_terrain
        )
        models = tuple(
            _validate_model("VisibilityQuery dynamic model blocker", model)
            for model in self.dynamic_model_blockers
        )
        _validate_unique_terrain_ids(terrain)
        _validate_unique_model_ids(models)
        object.__setattr__(self, "rays", rays)
        object.__setattr__(
            self,
            "static_terrain",
            tuple(sorted(terrain, key=lambda volume: volume.terrain_id)),
        )
        object.__setattr__(
            self,
            "dynamic_model_blockers",
            tuple(sorted(models, key=lambda model: model.model_id)),
        )

    @classmethod
    def from_segment(
        cls,
        start: Point3,
        end: Point3,
        static_terrain: tuple[TerrainVolume, ...] = (),
        dynamic_model_blockers: tuple[Model, ...] = (),
    ) -> Self:
        return cls(
            rays=((start, end),),
            static_terrain=static_terrain,
            dynamic_model_blockers=dynamic_model_blockers,
        )

    def resolve(self) -> VisibilityResult:
        checked_terrain_ids: set[str] = set()
        checked_model_ids: set[str] = set()
        blocking_terrain_ids: set[str] = set()
        blocking_model_ids: set[str] = set()
        terrain_candidate_count = 0
        model_candidate_count = 0
        exact_terrain_check_count = 0
        exact_model_check_count = 0

        for ray_index, ray in enumerate(self.rays):
            start, end = ray
            terrain_candidates = tuple(
                terrain
                for terrain in self.static_terrain
                if terrain.blocks_line_of_sight and _terrain_broad_phase_intersects(ray, terrain)
            )
            model_candidates = tuple(
                model
                for model in self.dynamic_model_blockers
                if _model_broad_phase_intersects(ray, model)
            )
            terrain_candidate_count += len(terrain_candidates)
            model_candidate_count += len(model_candidates)

            checked_terrain_ids.update(terrain.terrain_id for terrain in terrain_candidates)
            checked_model_ids.update(model.model_id for model in model_candidates)

            exact_terrain_check_count += len(terrain_candidates)
            terrain_blockers = tuple(
                terrain.terrain_id
                for terrain in terrain_candidates
                if terrain.blocks_line_segment(start, end)
            )
            exact_model_check_count += len(model_candidates)
            model_blockers = tuple(
                model.model_id
                for model in model_candidates
                if shapely_backend.segment_intersects_model_footprint(start, end, model)
            )
            if not terrain_blockers and not model_blockers:
                return VisibilityResult(
                    has_line_of_sight=True,
                    checked_ray_count=ray_index + 1,
                    clear_ray_index=ray_index,
                    checked_terrain_ids=tuple(sorted(checked_terrain_ids)),
                    checked_model_ids=tuple(sorted(checked_model_ids)),
                    metrics=VisibilityMetrics(
                        terrain_candidate_count=terrain_candidate_count,
                        model_candidate_count=model_candidate_count,
                        exact_terrain_check_count=exact_terrain_check_count,
                        exact_model_check_count=exact_model_check_count,
                    ),
                )

            blocking_terrain_ids.update(terrain_blockers)
            blocking_model_ids.update(model_blockers)

        return VisibilityResult(
            has_line_of_sight=False,
            checked_ray_count=len(self.rays),
            clear_ray_index=None,
            blocking_terrain_ids=tuple(sorted(blocking_terrain_ids)),
            blocking_model_ids=tuple(sorted(blocking_model_ids)),
            checked_terrain_ids=tuple(sorted(checked_terrain_ids)),
            checked_model_ids=tuple(sorted(checked_model_ids)),
            metrics=VisibilityMetrics(
                terrain_candidate_count=terrain_candidate_count,
                model_candidate_count=model_candidate_count,
                exact_terrain_check_count=exact_terrain_check_count,
                exact_model_check_count=exact_model_check_count,
            ),
        )

    def to_payload(self) -> VisibilityQueryPayload:
        return {
            "rays": [
                {"start": start.to_payload(), "end": end.to_payload()} for start, end in self.rays
            ],
            "static_terrain": [terrain.to_payload() for terrain in self.static_terrain],
            "dynamic_model_blockers": [model.to_payload() for model in self.dynamic_model_blockers],
        }

    @classmethod
    def from_payload(cls, payload: VisibilityQueryPayload) -> Self:
        return cls(
            rays=tuple(
                (
                    Point3.from_payload(ray["start"]),
                    Point3.from_payload(ray["end"]),
                )
                for ray in payload["rays"]
            ),
            static_terrain=tuple(
                terrain_volume_from_payload(terrain) for terrain in payload["static_terrain"]
            ),
            dynamic_model_blockers=tuple(
                Model.from_payload(model) for model in payload["dynamic_model_blockers"]
            ),
        )


@dataclass(frozen=True, slots=True)
class VisibilityMetrics:
    terrain_candidate_count: int = 0
    model_candidate_count: int = 0
    exact_terrain_check_count: int = 0
    exact_model_check_count: int = 0

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "terrain_candidate_count",
            _validate_non_negative_int(
                "VisibilityMetrics terrain_candidate_count",
                self.terrain_candidate_count,
            ),
        )
        object.__setattr__(
            self,
            "model_candidate_count",
            _validate_non_negative_int(
                "VisibilityMetrics model_candidate_count",
                self.model_candidate_count,
            ),
        )
        object.__setattr__(
            self,
            "exact_terrain_check_count",
            _validate_non_negative_int(
                "VisibilityMetrics exact_terrain_check_count",
                self.exact_terrain_check_count,
            ),
        )
        object.__setattr__(
            self,
            "exact_model_check_count",
            _validate_non_negative_int(
                "VisibilityMetrics exact_model_check_count",
                self.exact_model_check_count,
            ),
        )

    def to_payload(self) -> VisibilityMetricsPayload:
        return {
            "terrain_candidate_count": self.terrain_candidate_count,
            "model_candidate_count": self.model_candidate_count,
            "exact_terrain_check_count": self.exact_terrain_check_count,
            "exact_model_check_count": self.exact_model_check_count,
        }

    @classmethod
    def from_payload(cls, payload: VisibilityMetricsPayload) -> Self:
        return cls(
            terrain_candidate_count=payload["terrain_candidate_count"],
            model_candidate_count=payload["model_candidate_count"],
            exact_terrain_check_count=payload["exact_terrain_check_count"],
            exact_model_check_count=payload["exact_model_check_count"],
        )


@dataclass(frozen=True, slots=True)
class VisibilityResult:
    has_line_of_sight: bool
    checked_ray_count: int
    clear_ray_index: int | None
    blocking_terrain_ids: tuple[str, ...] = ()
    blocking_model_ids: tuple[str, ...] = ()
    checked_terrain_ids: tuple[str, ...] = ()
    checked_model_ids: tuple[str, ...] = ()
    metrics: VisibilityMetrics = field(default_factory=VisibilityMetrics)

    def __post_init__(self) -> None:
        if type(self.has_line_of_sight) is not bool:
            raise GeometryError("VisibilityResult has_line_of_sight must be a bool.")
        if type(self.checked_ray_count) is not int or self.checked_ray_count < 1:
            raise GeometryError("VisibilityResult checked_ray_count must be a positive integer.")
        if self.clear_ray_index is not None:
            if type(self.clear_ray_index) is not int:
                raise GeometryError("VisibilityResult clear_ray_index must be an integer.")
            if self.clear_ray_index < 0 or self.clear_ray_index >= self.checked_ray_count:
                raise GeometryError("VisibilityResult clear_ray_index is outside checked rays.")
        if self.has_line_of_sight and self.clear_ray_index is None:
            raise GeometryError("Visible VisibilityResult must include clear_ray_index.")
        if not self.has_line_of_sight and self.clear_ray_index is not None:
            raise GeometryError("Blocked VisibilityResult must not include clear_ray_index.")

        object.__setattr__(
            self,
            "blocking_terrain_ids",
            _validate_identifier_tuple(
                "VisibilityResult blocking_terrain_ids", self.blocking_terrain_ids
            ),
        )
        object.__setattr__(
            self,
            "blocking_model_ids",
            _validate_identifier_tuple(
                "VisibilityResult blocking_model_ids", self.blocking_model_ids
            ),
        )
        object.__setattr__(
            self,
            "checked_terrain_ids",
            _validate_identifier_tuple(
                "VisibilityResult checked_terrain_ids", self.checked_terrain_ids
            ),
        )
        object.__setattr__(
            self,
            "checked_model_ids",
            _validate_identifier_tuple(
                "VisibilityResult checked_model_ids", self.checked_model_ids
            ),
        )
        if type(self.metrics) is not VisibilityMetrics:
            raise GeometryError("VisibilityResult metrics must be VisibilityMetrics.")

    def to_payload(self) -> VisibilityResultPayload:
        return {
            "has_line_of_sight": self.has_line_of_sight,
            "checked_ray_count": self.checked_ray_count,
            "clear_ray_index": self.clear_ray_index,
            "blocking_terrain_ids": list(self.blocking_terrain_ids),
            "blocking_model_ids": list(self.blocking_model_ids),
            "checked_terrain_ids": list(self.checked_terrain_ids),
            "checked_model_ids": list(self.checked_model_ids),
            "metrics": self.metrics.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: VisibilityResultPayload) -> Self:
        return cls(
            has_line_of_sight=payload["has_line_of_sight"],
            checked_ray_count=payload["checked_ray_count"],
            clear_ray_index=payload["clear_ray_index"],
            blocking_terrain_ids=tuple(payload["blocking_terrain_ids"]),
            blocking_model_ids=tuple(payload["blocking_model_ids"]),
            checked_terrain_ids=tuple(payload["checked_terrain_ids"]),
            checked_model_ids=tuple(payload["checked_model_ids"]),
            metrics=VisibilityMetrics.from_payload(payload["metrics"]),
        )


def _validate_ray(value: object) -> VisibilityRay:
    if type(value) is not tuple:
        raise GeometryError("VisibilityQuery rays must contain Point3 pairs.")
    ray = cast(tuple[object, object], value)
    if len(ray) != 2:
        raise GeometryError("VisibilityQuery rays must contain Point3 pairs.")
    start, end = ray
    return (
        validate_point3("VisibilityQuery ray start", start),
        validate_point3("VisibilityQuery ray end", end),
    )


def _validate_terrain(field_name: str, value: object) -> TerrainVolume:
    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _validate_unique_terrain_ids(terrain: tuple[TerrainVolume, ...]) -> None:
    seen: set[str] = set()
    for volume in terrain:
        if volume.terrain_id in seen:
            raise GeometryError("VisibilityQuery static_terrain must not contain duplicate IDs.")
        seen.add(volume.terrain_id)


def _validate_unique_model_ids(models: tuple[Model, ...]) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_id in seen:
            raise GeometryError(
                "VisibilityQuery dynamic_model_blockers must not contain duplicate IDs."
            )
        seen.add(model.model_id)


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
            raise GeometryError(f"{field_name} must not contain duplicate IDs.")
        seen.add(stripped)
        validated.append(stripped)
    return tuple(sorted(validated))


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GeometryError(f"{field_name} must be an integer.")
    if value < 0:
        raise GeometryError(f"{field_name} must not be negative.")
    return value


def _terrain_broad_phase_intersects(ray: VisibilityRay, terrain: TerrainVolume) -> bool:
    start, end = ray
    return _bounds_overlap(
        _segment_bounds(start, end), (*terrain.horizontal_bounds(), *terrain.vertical_interval())
    )


def _model_broad_phase_intersects(ray: VisibilityRay, model: Model) -> bool:
    radius = model.base.max_radius()
    model_bounds = (
        model.pose.position.x - radius,
        model.pose.position.y - radius,
        model.pose.position.x + radius,
        model.pose.position.y + radius,
        *model.volume.vertical_interval(model.pose),
    )
    return _bounds_overlap(_segment_bounds(ray[0], ray[1]), model_bounds)


def _segment_bounds(start: Point3, end: Point3) -> tuple[float, float, float, float, float, float]:
    return (
        min(start.x, end.x),
        min(start.y, end.y),
        max(start.x, end.x),
        max(start.y, end.y),
        min(start.z, end.z),
        max(start.z, end.z),
    )


def _bounds_overlap(
    segment_bounds: tuple[float, float, float, float, float, float],
    obstacle_bounds: tuple[float, float, float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y, min_z, max_z = segment_bounds
    (
        obstacle_min_x,
        obstacle_min_y,
        obstacle_max_x,
        obstacle_max_y,
        obstacle_min_z,
        obstacle_max_z,
    ) = obstacle_bounds
    return (
        max_x >= obstacle_min_x
        and min_x <= obstacle_max_x
        and max_y >= obstacle_min_y
        and min_y <= obstacle_max_y
        and max_z >= obstacle_min_z
        and min_z <= obstacle_max_z
    )
