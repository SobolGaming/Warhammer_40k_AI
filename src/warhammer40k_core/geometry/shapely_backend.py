from __future__ import annotations

import importlib
from typing import TYPE_CHECKING, Protocol, cast

from warhammer40k_core.geometry.pose import GeometryError, Point3, Pose, validate_point3

if TYPE_CHECKING:
    from warhammer40k_core.geometry.base import BaseShape
    from warhammer40k_core.geometry.terrain import TerrainVolume
    from warhammer40k_core.geometry.volume import Model

_FOOTPRINT_QUAD_SEGS = 64


class _Geometry(Protocol):
    def buffer(self, distance: float, quad_segs: int = _FOOTPRINT_QUAD_SEGS) -> _Geometry: ...

    def distance(self, other: _Geometry) -> float: ...

    def intersects(self, other: _Geometry) -> bool: ...


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

    line = _geometry_module().LineString(
        ((valid_start.x, valid_start.y), (valid_end.x, valid_end.y))
    )
    return line.intersects(footprint_for_terrain(valid_terrain))


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
