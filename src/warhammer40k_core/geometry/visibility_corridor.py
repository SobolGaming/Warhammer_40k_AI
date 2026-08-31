from __future__ import annotations

from typing import Final

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.polygons import Point2D
from warhammer40k_core.geometry.pose import Point3, validate_point3
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.volume import Model

MILLIMETERS_PER_INCH: Final = 25.4
LINE_OF_SIGHT_CORRIDOR_WIDTH_MILLIMETERS: Final = 1.0
LINE_OF_SIGHT_CORRIDOR_WIDTH_INCHES: Final = (
    LINE_OF_SIGHT_CORRIDOR_WIDTH_MILLIMETERS / MILLIMETERS_PER_INCH
)
LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES: Final = LINE_OF_SIGHT_CORRIDOR_WIDTH_INCHES / 2.0


def line_of_sight_corridor_bounds(
    start: Point3,
    end: Point3,
) -> tuple[float, float, float, float, float, float]:
    valid_start = validate_point3("line of sight corridor start", start)
    valid_end = validate_point3("line of sight corridor end", end)
    radius = LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES
    return (
        min(valid_start.x, valid_end.x) - radius,
        min(valid_start.y, valid_end.y) - radius,
        max(valid_start.x, valid_end.x) + radius,
        max(valid_start.y, valid_end.y) + radius,
        min(valid_start.z, valid_end.z),
        max(valid_start.z, valid_end.z),
    )


def line_of_sight_corridor_intersects_terrain_volume(
    start: Point3,
    end: Point3,
    terrain: TerrainVolume,
) -> bool:
    return shapely_backend.segment_corridor_intersects_terrain_footprint(
        start,
        end,
        terrain,
        radius_inches=LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES,
    )


def line_of_sight_corridor_intersects_model(
    start: Point3,
    end: Point3,
    model: Model,
) -> bool:
    return shapely_backend.segment_corridor_intersects_model_footprint(
        start,
        end,
        model,
        radius_inches=LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES,
    )


def line_of_sight_corridor_intersects_polygon(
    start: Point3,
    end: Point3,
    polygon: tuple[Point2D, ...],
) -> bool:
    return shapely_backend.segment_corridor_intersects_polygon(
        start,
        end,
        polygon,
        radius_inches=LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES,
    )


def line_of_sight_corridor_intersects_polygon_union(
    start: Point3,
    end: Point3,
    polygons: tuple[tuple[Point2D, ...], ...],
) -> bool:
    return shapely_backend.segment_corridor_intersects_polygon_union(
        start,
        end,
        polygons,
        radius_inches=LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES,
    )


__all__ = (
    "LINE_OF_SIGHT_CORRIDOR_RADIUS_INCHES",
    "LINE_OF_SIGHT_CORRIDOR_WIDTH_INCHES",
    "LINE_OF_SIGHT_CORRIDOR_WIDTH_MILLIMETERS",
    "line_of_sight_corridor_bounds",
    "line_of_sight_corridor_intersects_model",
    "line_of_sight_corridor_intersects_polygon",
    "line_of_sight_corridor_intersects_polygon_union",
    "line_of_sight_corridor_intersects_terrain_volume",
)
