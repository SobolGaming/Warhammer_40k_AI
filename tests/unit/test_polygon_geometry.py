from __future__ import annotations

import math

import pytest
from hypothesis import given
from hypothesis import strategies as st

from warhammer40k_core.geometry import polygons
from warhammer40k_core.geometry.polygons import (
    convex_polygon_intersection_area,
    point_intersects_polygon,
    polygon_bounds,
    polygon_distance,
    polygon_overlap_area,
    polygon_self_intersects,
    signed_polygon_area,
    triangulate_polygon,
)
from warhammer40k_core.geometry.pose import GeometryError


@pytest.mark.stubbed
def test_overlap_triangulates_each_input_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated triangles must not multiply the input-validation/triangulation work."""
    triangulations: list[tuple[polygons.Point2D, ...]] = []
    original = polygons.triangulate_polygon

    def measured(
        vertices: tuple[polygons.Point2D, ...],
    ) -> tuple[tuple[polygons.Point2D, ...], ...]:
        triangulations.append(vertices)
        return original(vertices)

    monkeypatch.setattr(polygons, "triangulate_polygon", measured)
    concave = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (2.0, 2.0), (0.0, 4.0))
    rectangle = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (0.0, 4.0))

    assert polygon_overlap_area(concave, rectangle) == 12.0
    assert triangulations == [concave, rectangle]


@given(
    x=st.integers(-100, 100),
    y=st.integers(-100, 100),
    width=st.integers(1, 20),
    height=st.integers(1, 20),
    offset=st.integers(0, 25),
)
def test_overlap_preserves_exact_rectangle_area_and_winding(
    x: int, y: int, width: int, height: int, offset: int
) -> None:
    first = ((x, y), (x + width, y), (x + width, y + height), (x, y + height))
    second = tuple((px + offset, py) for px, py in first)
    expected = max(width - offset, 0) * height

    assert math.isclose(polygon_overlap_area(first, second), expected, abs_tol=1e-9)
    assert math.isclose(
        polygon_overlap_area(tuple(reversed(first)), second), expected, abs_tol=1e-9
    )
    assert math.isclose(polygon_overlap_area(second, first), expected, abs_tol=1e-9)


@pytest.mark.parametrize("invalid", [math.nan, math.inf, -math.inf, True])
@pytest.mark.parametrize("invalid_first", [False, True])
def test_overlap_validates_both_inputs_even_after_repeated_valid_calls(
    invalid: float, invalid_first: bool
) -> None:
    valid = ((0.0, 0.0), (2.0, 0.0), (0.0, 2.0))
    malformed = ((0.0, 0.0), (invalid, 0.0), (0.0, 2.0))
    assert polygon_overlap_area(valid, valid) == 2.0
    with pytest.raises(GeometryError):
        polygon_overlap_area(malformed, valid) if invalid_first else polygon_overlap_area(
            valid, malformed
        )


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


def test_polygon_distance_handles_separation_touching_and_containment() -> None:
    first = ((0.0, 0.0), (2.0, 0.0), (2.0, 2.0), (0.0, 2.0))
    separated = ((2.05, 0.0), (4.05, 0.0), (4.05, 2.0), (2.05, 2.0))
    touching = ((2.0, 0.0), (4.0, 0.0), (4.0, 2.0), (2.0, 2.0))
    contained = ((0.5, 0.5), (1.5, 0.5), (1.5, 1.5), (0.5, 1.5))

    assert math.isclose(
        polygon_distance(first, separated),
        0.05,
        rel_tol=0.0,
        abs_tol=1e-12,
    )
    assert polygon_distance(first, touching) == 0.0
    assert polygon_distance(first, contained) == 0.0


def test_polygon_self_intersection_and_degenerate_inputs_are_strict() -> None:
    bowtie = ((0.0, 0.0), (4.0, 4.0), (0.0, 4.0), (4.0, 0.0))

    assert polygon_self_intersects(bowtie)
    with pytest.raises(GeometryError, match="at least three points"):
        signed_polygon_area(((0.0, 0.0), (1.0, 1.0)))
    with pytest.raises(GeometryError, match="finite"):
        polygon_bounds(((0.0, 0.0), (math.nan, 0.0), (1.0, 1.0)))


def test_point_intersection_supports_concave_polygons_and_their_boundaries() -> None:
    concave = ((0.0, 0.0), (4.0, 0.0), (4.0, 4.0), (2.0, 2.0), (0.0, 4.0))

    assert point_intersects_polygon((1.0, 1.0), concave)
    assert point_intersects_polygon((2.0, 2.0), concave)
    assert not point_intersects_polygon((2.0, 3.0), concave)
    with pytest.raises(GeometryError, match="point must be a Point2D"):
        point_intersects_polygon((1.0,), concave)  # type: ignore[arg-type]


def _triangle_area_sum(triangles: tuple[tuple[tuple[float, float], ...], ...]) -> float:
    return sum(abs(signed_polygon_area(triangle)) for triangle in triangles)
