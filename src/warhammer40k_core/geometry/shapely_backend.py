from __future__ import annotations

import importlib
from functools import lru_cache
from typing import TYPE_CHECKING, Protocol, cast

from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose, validate_point3

if TYPE_CHECKING:
    from warhammer40k_core.core.deployment_zones import DeploymentZone, DeploymentZoneShape
    from warhammer40k_core.geometry.base import BaseShape
    from warhammer40k_core.geometry.terrain import TerrainVolume
    from warhammer40k_core.geometry.volume import Model

_FOOTPRINT_QUAD_SEGS = 64
_EPSILON = 1e-9
_cached_geometry_module: _GeometryModule | None = None
_cached_affinity_module: _AffinityModule | None = None


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

    def difference(self, other: _Geometry) -> _Geometry: ...

    def union(self, other: _Geometry) -> _Geometry: ...


class _GeometryModule(Protocol):
    def Point(self, x: float, y: float) -> _Geometry: ...

    def LineString(
        self, coordinates: tuple[tuple[float, float], tuple[float, float]]
    ) -> _Geometry: ...

    def Polygon(self, coordinates: tuple[tuple[float, float], ...]) -> _Geometry: ...

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
    rectangle = _box(
        valid_terrain.bottom_center.x - half_width,
        valid_terrain.bottom_center.y - half_depth,
        valid_terrain.bottom_center.x + half_width,
        valid_terrain.bottom_center.y + half_depth,
    )
    return _affinity_module().rotate(
        rectangle,
        angle=valid_terrain.rotation_degrees,
        origin=(valid_terrain.bottom_center.x, valid_terrain.bottom_center.y),
    )


def footprint_for_deployment_zone(deployment_zone: DeploymentZone) -> _Geometry:
    valid_zone = _validate_deployment_zone("deployment_zone", deployment_zone)
    return footprint_for_deployment_zone_shape(valid_zone.shape)


def footprint_for_deployment_zone_shape(shape: DeploymentZoneShape) -> _Geometry:
    valid_shape = _validate_deployment_zone_shape("shape", shape)
    zone_parts = tuple(
        _deployment_zone_polygon_footprint(polygon) for polygon in valid_shape.polygons
    )
    cutouts = tuple(_deployment_zone_cutout_footprint(cutout) for cutout in valid_shape.cutouts)
    adjusted_parts: list[_Geometry] = []
    for zone_part in zone_parts:
        adjusted_part = zone_part
        for cutout in cutouts:
            adjusted_part = adjusted_part.difference(cutout)
        adjusted_parts.append(adjusted_part)
    zone_footprint = adjusted_parts[0]
    for adjusted_part in adjusted_parts[1:]:
        zone_footprint = zone_footprint.union(adjusted_part)
    return zone_footprint


def deployment_zone_shapes_cover_bounds(
    *,
    shapes: tuple[DeploymentZoneShape, ...],
    bounds: tuple[float, float, float, float],
) -> bool:
    if type(shapes) is not tuple or not shapes:
        raise GeometryError("deployment-zone shapes must be a non-empty tuple.")
    zone_footprint = footprint_for_deployment_zone_shape(shapes[0])
    for shape in shapes[1:]:
        zone_footprint = zone_footprint.union(footprint_for_deployment_zone_shape(shape))
    min_x, min_y, max_x, max_y = bounds
    if min_x >= max_x or min_y >= max_y:
        raise GeometryError("covered bounds must have positive width and depth.")
    return zone_footprint.covers(_box(min_x, min_y, max_x, max_y))


def base_footprint_within_bounds(
    base: BaseShape,
    pose: Pose,
    bounds: tuple[float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    surface = _box(min_x, min_y, max_x, max_y)
    return surface.covers(footprint_for_base(base, pose))


def base_footprint_intersects_bounds(
    base: BaseShape,
    pose: Pose,
    bounds: tuple[float, float, float, float],
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    surface = _box(min_x, min_y, max_x, max_y)
    return surface.intersects(footprint_for_base(base, pose))


def base_footprint_intersects_deployment_zone(
    base: BaseShape,
    pose: Pose,
    deployment_zone: DeploymentZone,
) -> bool:
    return footprint_for_deployment_zone(deployment_zone).intersects(footprint_for_base(base, pose))


def base_footprint_intersects_no_mans_land(
    base: BaseShape,
    pose: Pose,
    *,
    battlefield_bounds: tuple[float, float, float, float],
    deployment_zones: tuple[DeploymentZone, ...],
) -> bool:
    return footprint_for_no_mans_land(
        battlefield_bounds=battlefield_bounds,
        deployment_zones=deployment_zones,
    ).intersects(footprint_for_base(base, pose))


def base_footprint_within_no_mans_land(
    base: BaseShape,
    pose: Pose,
    *,
    battlefield_bounds: tuple[float, float, float, float],
    deployment_zones: tuple[DeploymentZone, ...],
) -> bool:
    return footprint_for_no_mans_land(
        battlefield_bounds=battlefield_bounds,
        deployment_zones=deployment_zones,
    ).covers(footprint_for_base(base, pose))


def footprint_for_no_mans_land(
    *,
    battlefield_bounds: tuple[float, float, float, float],
    deployment_zones: tuple[DeploymentZone, ...],
) -> _Geometry:
    min_x, min_y, max_x, max_y = battlefield_bounds
    no_mans_land = _box(min_x, min_y, max_x, max_y)
    for deployment_zone in deployment_zones:
        no_mans_land = no_mans_land.difference(footprint_for_deployment_zone(deployment_zone))
    return no_mans_land


def base_footprint_within_deployment_zone(
    base: BaseShape,
    pose: Pose,
    deployment_zone: DeploymentZone,
) -> bool:
    return footprint_for_deployment_zone(deployment_zone).covers(footprint_for_base(base, pose))


def base_footprint_distance_to_deployment_zone(
    base: BaseShape,
    pose: Pose,
    deployment_zone: DeploymentZone,
) -> float:
    return footprint_for_deployment_zone(deployment_zone).distance(footprint_for_base(base, pose))


def base_footprint_distance_to_bounds(
    base: BaseShape,
    pose: Pose,
    bounds: tuple[float, float, float, float],
) -> float:
    min_x, min_y, max_x, max_y = bounds
    surface = _box(min_x, min_y, max_x, max_y)
    return surface.distance(footprint_for_base(base, pose))


def base_footprint_distance(
    first: BaseShape,
    first_pose: Pose,
    second: BaseShape,
    second_pose: Pose,
) -> float:
    return footprint_for_base(first, first_pose).distance(footprint_for_base(second, second_pose))


def bounds_have_point_clear_of_model_footprints(
    *,
    bounds: tuple[float, float, float, float],
    blocked_models: tuple[Model, ...],
    clear_distance_inches: float,
    marker_radius_inches: float,
) -> bool:
    min_x, min_y, max_x, max_y = bounds
    surface = _box(min_x, min_y, max_x, max_y)
    clearance = _validate_non_negative_number(
        "clear_distance_inches",
        clear_distance_inches,
    ) + _validate_non_negative_number("marker_radius_inches", marker_radius_inches)
    legal_area = surface
    for model in blocked_models:
        valid_model = _validate_model("blocked_model", model)
        legal_area = legal_area.difference(
            footprint_for_base(valid_model.base, valid_model.pose).buffer(
                clearance,
                quad_segs=_FOOTPRINT_QUAD_SEGS,
            )
        )
        if legal_area.is_empty:
            return False
    return not legal_area.is_empty


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

    return _segment_intersects_footprint_with_vertical_interval(
        valid_start,
        valid_end,
        footprint_for_terrain(valid_terrain),
        (terrain_bottom, terrain_top),
    )


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
    global _cached_geometry_module
    if _cached_geometry_module is None:
        _cached_geometry_module = cast(
            _GeometryModule,
            importlib.import_module("shapely.geometry"),
        )
    return _cached_geometry_module


def _affinity_module() -> _AffinityModule:
    global _cached_affinity_module
    if _cached_affinity_module is None:
        _cached_affinity_module = cast(
            _AffinityModule,
            importlib.import_module("shapely.affinity"),
        )
    return _cached_affinity_module


@lru_cache(maxsize=4096)
def _box(min_x: float, min_y: float, max_x: float, max_y: float) -> _Geometry:
    return _geometry_module().box(min_x, min_y, max_x, max_y)


def _deployment_zone_polygon_footprint(
    polygon: object,
) -> _Geometry:
    from warhammer40k_core.core.deployment_zones import DeploymentZonePolygon

    if type(polygon) is not DeploymentZonePolygon:
        raise GeometryError("deployment-zone polygon must be a DeploymentZonePolygon.")
    return _geometry_module().Polygon(tuple((vertex.x, vertex.y) for vertex in polygon.vertices))


def _deployment_zone_cutout_footprint(
    cutout: object,
) -> _Geometry:
    from warhammer40k_core.core.deployment_zones import (
        DeploymentZoneCircleCutout,
        DeploymentZonePolygonCutout,
    )

    if type(cutout) is DeploymentZoneCircleCutout:
        return (
            _geometry_module()
            .Point(cutout.center_x, cutout.center_y)
            .buffer(
                cutout.radius,
                quad_segs=_FOOTPRINT_QUAD_SEGS,
            )
        )
    if type(cutout) is DeploymentZonePolygonCutout:
        return _geometry_module().Polygon(tuple((vertex.x, vertex.y) for vertex in cutout.vertices))
    raise GeometryError("deployment-zone cutout must be a supported cutout value.")


def _validate_deployment_zone(field_name: str, value: object) -> DeploymentZone:
    from warhammer40k_core.core.deployment_zones import DeploymentZone

    if type(value) is not DeploymentZone:
        raise GeometryError(f"{field_name} must be a DeploymentZone.")
    return value


def _validate_deployment_zone_shape(
    field_name: str,
    value: object,
) -> DeploymentZoneShape:
    from warhammer40k_core.core.deployment_zones import DeploymentZoneShape

    if type(value) is not DeploymentZoneShape:
        raise GeometryError(f"{field_name} must be a DeploymentZoneShape.")
    return value


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


def _validate_non_negative_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise GeometryError(f"{field_name} must be a number.")
    number = float(value)
    if number < 0.0:
        raise GeometryError(f"{field_name} must be non-negative.")
    return number


def _vertical_gap(
    first_interval: tuple[float, float],
    second_interval: tuple[float, float],
) -> bool:
    first_bottom, first_top = first_interval
    second_bottom, second_top = second_interval
    return first_top < second_bottom or second_top < first_bottom


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
