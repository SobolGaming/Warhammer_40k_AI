from __future__ import annotations

import math

import pytest

from warhammer40k_core.geometry.polygons import (
    convex_polygon_intersection_area,
    polygon_bounds,
    polygon_overlap_area,
    polygon_self_intersects,
    signed_polygon_area,
    triangulate_polygon,
)
from warhammer40k_core.geometry.pose import GeometryError


def test_signed_area_bounds_and_reversed_winding() -> None:
    rectangle = ((0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0))
    reversed_rectangle = tuple(reversed(rectangle))

    assert signed_polygon_area(rectangle) == 12.0
    assert signed_polygon_area(reversed_rectangle) == -12.0
    assert polygon_bounds(rectangle) == (0.0, 0.0, 4.0, 3.0)
    assert _triangle_area_sum(triangulate_polygon(reversed_rectangle)) == 12.0


def test_triangulates_concave_polygon_without_losing_area() -> None:
    concave = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (2.0, 2.0), (0.0, 4.0))

    triangles = triangulate_polygon(concave)

    assert len(triangles) == 3
    assert _triangle_area_sum(triangles) == abs(signed_polygon_area(concave))


def test_convex_clipping_and_overlap_area() -> None:
    first = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0))
    second = ((2.0, 2.0), (6.0, 2.0), (6.0, 6.0), (2.0, 6.0))

    assert convex_polygon_intersection_area(first, second) == 4.0
    assert polygon_overlap_area(first, second) == 4.0


def test_polygon_self_intersection_and_degenerate_inputs_are_strict() -> None:
    bowtie = ((0.0, 0.0), (4.0, 4.0), (0.0, 4.0), (4.0, 0.0))

    assert polygon_self_intersects(bowtie)
    with pytest.raises(GeometryError, match="at least three points"):
        signed_polygon_area(((0.0, 0.0), (1.0, 1.0)))
    with pytest.raises(GeometryError, match="finite"):
        polygon_bounds(((0.0, 0.0), (math.nan, 0.0), (1.0, 1.0)))


def _triangle_area_sum(triangles: tuple[tuple[tuple[float, float], ...], ...]) -> float:
    return sum(abs(signed_polygon_area(triangle)) for triangle in triangles)
