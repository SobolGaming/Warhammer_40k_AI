from __future__ import annotations

import math
from dataclasses import dataclass

from warhammer40k_core.geometry.pose import (
    GeometryError,
    Point3,
    validate_finite_number,
    validate_point3,
)
from warhammer40k_core.geometry.volume import Model

_EPSILON = 1e-9
_Point2 = tuple[float, float]


@dataclass(frozen=True, slots=True)
class TerrainVolume:
    terrain_id: str
    center: Point3
    width: float
    depth: float
    height: float
    blocks_line_of_sight: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "terrain_id", _validate_terrain_id(self.terrain_id))
        validate_point3("TerrainVolume center", self.center)
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
        bottom = self.center.z
        return (bottom, bottom + self.height)

    def horizontal_bounds(self) -> tuple[float, float, float, float]:
        half_width = self.width / 2.0
        half_depth = self.depth / 2.0
        return (
            self.center.x - half_width,
            self.center.y - half_depth,
            self.center.x + half_width,
            self.center.y + half_depth,
        )

    def intersects_model(self, model: Model) -> bool:
        valid_model = _validate_model("model", model)
        if (
            _vertical_gap(
                self.vertical_interval(), valid_model.volume.vertical_interval(valid_model.pose)
            )
            > 0.0
        ):
            return False
        horizontal_distance = _distance_point_to_rectangle(
            (valid_model.pose.position.x, valid_model.pose.position.y),
            self.horizontal_bounds(),
        )
        return horizontal_distance <= valid_model.base.max_radius() + _EPSILON

    def blocks_line_segment(self, start: Point3, end: Point3) -> bool:
        if not self.blocks_line_of_sight:
            return False

        valid_start = validate_point3("start", start)
        valid_end = validate_point3("end", end)
        terrain_bottom, terrain_top = self.vertical_interval()
        segment_bottom = min(valid_start.z, valid_end.z)
        segment_top = max(valid_start.z, valid_end.z)
        if segment_top < terrain_bottom or segment_bottom > terrain_top:
            return False

        return _segment_intersects_rectangle(
            (valid_start.x, valid_start.y),
            (valid_end.x, valid_end.y),
            self.horizontal_bounds(),
        )


@dataclass(frozen=True, slots=True)
class ObstacleVolume(TerrainVolume):
    blocks_line_of_sight: bool = True

    def __post_init__(self) -> None:
        super().__post_init__()
        if self.blocks_line_of_sight is not True:
            raise GeometryError("ObstacleVolume must block line of sight.")


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


def _validate_model(field_name: str, value: object) -> Model:
    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _vertical_gap(
    first_interval: tuple[float, float],
    second_interval: tuple[float, float],
) -> float:
    first_bottom, first_top = first_interval
    second_bottom, second_top = second_interval
    if first_top < second_bottom:
        return second_bottom - first_top
    if second_top < first_bottom:
        return first_bottom - second_top
    return 0.0


def _distance_point_to_rectangle(
    point: _Point2,
    bounds: tuple[float, float, float, float],
) -> float:
    x, y = point
    min_x, min_y, max_x, max_y = bounds
    dx = max(min_x - x, 0.0, x - max_x)
    dy = max(min_y - y, 0.0, y - max_y)
    return math.sqrt(dx * dx + dy * dy)


def _segment_intersects_rectangle(
    start: _Point2,
    end: _Point2,
    bounds: tuple[float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    if _point_in_rectangle(start, bounds) or _point_in_rectangle(end, bounds):
        return True

    edges = (
        ((min_x, min_y), (max_x, min_y)),
        ((max_x, min_y), (max_x, max_y)),
        ((max_x, max_y), (min_x, max_y)),
        ((min_x, max_y), (min_x, min_y)),
    )
    return any(
        _segments_intersect(start, end, edge_start, edge_end) for edge_start, edge_end in edges
    )


def _point_in_rectangle(point: _Point2, bounds: tuple[float, float, float, float]) -> bool:
    x, y = point
    min_x, min_y, max_x, max_y = bounds
    return min_x <= x <= max_x and min_y <= y <= max_y


def _segments_intersect(
    first_start: _Point2,
    first_end: _Point2,
    second_start: _Point2,
    second_end: _Point2,
) -> bool:
    first_orientation = _orientation(first_start, first_end, second_start)
    second_orientation = _orientation(first_start, first_end, second_end)
    third_orientation = _orientation(second_start, second_end, first_start)
    fourth_orientation = _orientation(second_start, second_end, first_end)

    if (
        first_orientation * second_orientation < 0.0
        and third_orientation * fourth_orientation < 0.0
    ):
        return True
    if abs(first_orientation) <= _EPSILON and _point_on_segment(
        second_start, first_start, first_end
    ):
        return True
    if abs(second_orientation) <= _EPSILON and _point_on_segment(
        second_end, first_start, first_end
    ):
        return True
    if abs(third_orientation) <= _EPSILON and _point_on_segment(
        first_start, second_start, second_end
    ):
        return True
    return abs(fourth_orientation) <= _EPSILON and _point_on_segment(
        first_end,
        second_start,
        second_end,
    )


def _orientation(first: _Point2, second: _Point2, third: _Point2) -> float:
    return (second[0] - first[0]) * (third[1] - first[1]) - (second[1] - first[1]) * (
        third[0] - first[0]
    )


def _point_on_segment(point: _Point2, start: _Point2, end: _Point2) -> bool:
    return (
        min(start[0], end[0]) - _EPSILON <= point[0] <= max(start[0], end[0]) + _EPSILON
        and min(start[1], end[1]) - _EPSILON <= point[1] <= max(start[1], end[1]) + _EPSILON
    )
