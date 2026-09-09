from __future__ import annotations

import math
from fractions import Fraction
from typing import Final, cast

from warhammer40k_core.geometry.polygons import Point2D, validate_footprint_polygon
from warhammer40k_core.geometry.pose import GeometryError, Point3, validate_point3
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.visibility_exact import CORRIDOR_RADIUS, corridor_intersects_polygon
from warhammer40k_core.geometry.visibility_shapes import (
    model_visibility_prism,
    rational_point,
    terrain_visibility_prism,
)
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
    radius = CORRIDOR_RADIUS
    return (
        _outward_float(Fraction(min(valid_start.x, valid_end.x)) - radius, lower=True),
        _outward_float(Fraction(min(valid_start.y, valid_end.y)) - radius, lower=True),
        _outward_float(Fraction(max(valid_start.x, valid_end.x)) + radius, lower=False),
        _outward_float(Fraction(max(valid_start.y, valid_end.y)) + radius, lower=False),
        min(valid_start.z, valid_end.z),
        max(valid_start.z, valid_end.z),
    )


def _outward_float(value: Fraction, *, lower: bool) -> float:
    rounded = float(value)
    if (lower and Fraction(rounded) > value) or (not lower and Fraction(rounded) < value):
        return math.nextafter(rounded, -math.inf if lower else math.inf)
    return rounded


def line_of_sight_corridor_intersects_terrain_volume(
    start: Point3,
    end: Point3,
    terrain: TerrainVolume,
) -> bool:
    return terrain_visibility_prism(terrain).intersects_corridor(
        rational_point(start), rational_point(end)
    )


def line_of_sight_corridor_intersects_model(
    start: Point3,
    end: Point3,
    model: Model,
) -> bool:
    return model_visibility_prism(model).intersects_corridor(
        rational_point(start), rational_point(end)
    )


def line_of_sight_corridor_intersects_polygon(
    start: Point3,
    end: Point3,
    polygon: tuple[Point2D, ...],
) -> bool:
    valid_polygon = validate_footprint_polygon("polygon", polygon)
    return corridor_intersects_polygon(
        rational_point(start),
        rational_point(end),
        tuple((Fraction(x), Fraction(y)) for x, y in valid_polygon),
    )


def line_of_sight_corridor_intersects_polygon_union(
    start: Point3,
    end: Point3,
    polygons: tuple[tuple[Point2D, ...], ...],
) -> bool:
    if type(polygons) is not tuple or not polygons:
        raise GeometryError("polygon union must be a non-empty tuple.")
    prepared = tuple(
        tuple(
            (Fraction(x), Fraction(y))
            for x, y in validate_footprint_polygon(
                f"polygon union member {index}",
                polygon,
            )
        )
        for index, polygon in enumerate(cast(tuple[object, ...], polygons))
    )
    first, last = rational_point(start), rational_point(end)
    return any(corridor_intersects_polygon(first, last, polygon) for polygon in prepared)


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
