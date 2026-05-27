from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol, cast

from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose, validate_point3

if TYPE_CHECKING:
    from warhammer40k_core.geometry.base import BaseShape
    from warhammer40k_core.geometry.terrain import TerrainVolume
    from warhammer40k_core.geometry.volume import Model

_FOOTPRINT_QUAD_SEGS = 64
_EPSILON = 1e-9


class _Geometry(Protocol):
    @property
    def bounds(self) -> tuple[float, float, float, float]: ...

    @property
    def is_empty(self) -> bool: ...

    def buffer(self, distance: float, quad_segs: int = _FOOTPRINT_QUAD_SEGS) -> _Geometry: ...

    def distance(self, other: _Geometry) -> float: ...

    def intersection(self, other: _Geometry) -> _Geometry: ...

    def intersects(self, other: _Geometry) -> bool: ...

    def covers(self, other: _Geometry) -> bool: ...


class _GeometryModule(Protocol):
    def Point(self, x: float, y: float) -> _Geometry: ...

    def LineString(
        self, coordinates: tuple[tuple[float, float], tuple[float, float]]
    ) -> _Geometry: ...

    def box(self, min_x: float, min_y: float, max_x: float, max_y: float) -> _Geometry: ...


class _AffinityModule(Protocol):
    def scale(
        self,
        geometry: _Geometry,
        xfact: float,
        yfact: float,
        origin: tuple[float, float],
    ) -> _Geometry: ...

    def rotate(
        self,
        geometry: _Geometry,
        angle: float,
        origin: tuple[float, float],
    ) -> _Geometry: ...


def footprint_for_base(base: BaseShape, pose: Pose) -> _Geometry:
    from warhammer40k_core.geometry.base import (
        CircularBase,
        OvalBase,
        RectangularBase,
        validate_base_shape,
    )
    from warhammer40k_core.geometry.pose import validate_pose

    valid_base = validate_base_shape("base", base)
    valid_pose = validate_pose("pose", pose)
    geometry = _geometry_module()
    origin = (valid_pose.position.x, valid_pose.position.y)

    if type(valid_base) is CircularBase:
        return geometry.Point(*origin).buffer(valid_base.radius, quad_segs=_FOOTPRINT_QUAD_SEGS)
    if type(valid_base) is OvalBase:
        unit_circle = geometry.Point(*origin).buffer(1.0, quad_segs=_FOOTPRINT_QUAD_SEGS)
        scaled = _affinity_module().scale(
            unit_circle,
            xfact=valid_base.length / 2.0,
            yfact=valid_base.width / 2.0,
            origin=origin,
        )
        return _affinity_module().rotate(
            scaled,
            angle=valid_pose.facing.degrees,
            origin=origin,
        )
    if type(valid_base) is RectangularBase:
        half_length = valid_base.length / 2.0
        half_width = valid_base.width / 2.0
        rectangle = geometry.box(
            origin[0] - half_length,
            origin[1] - half_width,
            origin[0] + half_length,
            origin[1] + half_width,
        )
        return _affinity_module().rotate(
            rectangle,
            angle=valid_pose.facing.degrees,
            origin=origin,
        )
    raise GeometryError("Unsupported BaseShape for Shapely footprint.")


def footprint_for_terrain(terrain: TerrainVolume) -> _Geometry:
    valid_terrain = _validate_terrain("terrain", terrain)
    half_width = valid_terrain.width / 2.0
    half_depth = valid_terrain.depth / 2.0
    return _geometry_module().box(
        valid_terrain.bottom_center.x - half_width,
        valid_terrain.bottom_center.y - half_depth,
        valid_terrain.bottom_center.x + half_width,
        valid_terrain.bottom_center.y + half_depth,
    )


def base_footprint_within_bounds(
    base: BaseShape,
    pose: Pose,
    bounds: tuple[float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    surface = _geometry_module().box(min_x, min_y, max_x, max_y)
    return surface.covers(footprint_for_base(base, pose))


def base_footprint_intersects_bounds(
    base: BaseShape,
    pose: Pose,
    bounds: tuple[float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    surface = _geometry_module().box(min_x, min_y, max_x, max_y)
    return surface.intersects(footprint_for_base(base, pose))


def base_footprint_distance(
    first: BaseShape,
    first_pose: Pose,
    second: BaseShape,
    second_pose: Pose,
) -> float:
    return footprint_for_base(first, first_pose).distance(footprint_for_base(second, second_pose))


def base_footprints_intersect(
    first: BaseShape,
    first_pose: Pose,
    second: BaseShape,
    second_pose: Pose,
) -> bool:
    return footprint_for_base(first, first_pose).intersects(footprint_for_base(second, second_pose))


def terrain_footprint_intersects_model(terrain: TerrainVolume, model: Model) -> bool:
    valid_terrain = _validate_terrain("terrain", terrain)
    valid_model = _validate_model("model", model)
    if _vertical_gap(
        valid_terrain.vertical_interval(), valid_model.volume.vertical_interval(valid_model.pose)
    ):
        return False
    return footprint_for_terrain(valid_terrain).intersects(
        footprint_for_base(valid_model.base, valid_model.pose)
    )


def segment_intersects_terrain_footprint(
    start: Point3,
    end: Point3,
    terrain: TerrainVolume,
) -> bool:
    valid_start = validate_point3("start", start)
    valid_end = validate_point3("end", end)
    valid_terrain = _validate_terrain("terrain", terrain)
    terrain_bottom, terrain_top = valid_terrain.vertical_interval()
    segment_bottom = min(valid_start.z, valid_end.z)
    segment_top = max(valid_start.z, valid_end.z)
    if segment_top < terrain_bottom or segment_bottom > terrain_top:
        return False

    intersection_interval = _segment_rectangle_intersection_interval(
        valid_start,
        valid_end,
        valid_terrain.horizontal_bounds(),
    )
    if intersection_interval is None:
        return False

    start_t, end_t = intersection_interval
    start_z = _interpolate(valid_start.z, valid_end.z, start_t)
    end_z = _interpolate(valid_start.z, valid_end.z, end_t)
    crossing_bottom = min(start_z, end_z)
    crossing_top = max(start_z, end_z)
    return crossing_top >= terrain_bottom and crossing_bottom <= terrain_top


def segment_intersects_model_footprint(
    start: Point3,
    end: Point3,
    model: Model,
) -> bool:
    valid_start = validate_point3("start", start)
    valid_end = validate_point3("end", end)
    valid_model = _validate_model("model", model)
    return _segment_intersects_footprint_with_vertical_interval(
        valid_start,
        valid_end,
        footprint_for_base(valid_model.base, valid_model.pose),
        valid_model.volume.vertical_interval(valid_model.pose),
    )


def _geometry_module() -> _GeometryModule:
    return cast(_GeometryModule, importlib.import_module("shapely.geometry"))


def _affinity_module() -> _AffinityModule:
    return cast(_AffinityModule, importlib.import_module("shapely.affinity"))


def _validate_terrain(field_name: str, value: object) -> TerrainVolume:
    from warhammer40k_core.geometry.terrain import TerrainVolume

    if not isinstance(value, TerrainVolume):
        raise GeometryError(f"{field_name} must be a TerrainVolume.")
    return value


def _validate_model(field_name: str, value: object) -> Model:
    from warhammer40k_core.geometry.volume import Model

    if type(value) is not Model:
        raise GeometryError(f"{field_name} must be a Model.")
    return value


def _vertical_gap(
    first_interval: tuple[float, float],
    second_interval: tuple[float, float],
) -> bool:
    first_bottom, first_top = first_interval
    second_bottom, second_top = second_interval
    return first_top < second_bottom or second_top < first_bottom


def _segment_rectangle_intersection_interval(
    start: Point3,
    end: Point3,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float] | None:
    min_x, min_y, max_x, max_y = bounds
    dx = end.x - start.x
    dy = end.y - start.y
    start_t = 0.0
    end_t = 1.0

    for edge_delta, edge_distance in (
        (-dx, start.x - min_x),
        (dx, max_x - start.x),
        (-dy, start.y - min_y),
        (dy, max_y - start.y),
    ):
        if abs(edge_delta) <= _EPSILON:
            if edge_distance < 0.0:
                return None
            continue

        edge_t = edge_distance / edge_delta
        if edge_delta < 0.0:
            if edge_t > end_t:
                return None
            start_t = max(start_t, edge_t)
        else:
            if edge_t < start_t:
                return None
            end_t = min(end_t, edge_t)

    return (start_t, end_t)


def _segment_intersects_footprint_with_vertical_interval(
    start: Point3,
    end: Point3,
    footprint: _Geometry,
    vertical_interval: tuple[float, float],
) -> bool:
    segment_bottom = min(start.z, end.z)
    segment_top = max(start.z, end.z)
    interval_bottom, interval_top = vertical_interval
    if segment_top < interval_bottom or segment_bottom > interval_top:
        return False

    geometry = _geometry_module()
    if start.x == end.x and start.y == end.y:
        if not geometry.Point(start.x, start.y).intersects(footprint):
            return False
        return segment_top >= interval_bottom and segment_bottom <= interval_top

    line = geometry.LineString(((start.x, start.y), (end.x, end.y)))
    intersection = line.intersection(footprint)
    if intersection.is_empty:
        return False

    start_t, end_t = _intersection_bounds_to_segment_interval(start, end, intersection.bounds)
    start_z = _interpolate(start.z, end.z, start_t)
    end_z = _interpolate(start.z, end.z, end_t)
    crossing_bottom = min(start_z, end_z)
    crossing_top = max(start_z, end_z)
    return crossing_top >= interval_bottom and crossing_bottom <= interval_top


def _intersection_bounds_to_segment_interval(
    start: Point3,
    end: Point3,
    bounds: tuple[float, float, float, float],
) -> tuple[float, float]:
    min_x, min_y, max_x, max_y = bounds
    dx = end.x - start.x
    dy = end.y - start.y
    if abs(dx) > _EPSILON:
        start_t = (min_x - start.x) / dx
        end_t = (max_x - start.x) / dx
    else:
        start_t = (min_y - start.y) / dy
        end_t = (max_y - start.y) / dy
    return (max(0.0, min(start_t, end_t)), min(1.0, max(start_t, end_t)))


def _interpolate(start: float, end: float, t: float) -> float:
    return start + ((end - start) * t)
