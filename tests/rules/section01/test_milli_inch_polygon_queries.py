from __future__ import annotations

from decimal import Decimal
from fractions import Fraction
from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    CanonicalPolygon,
    CanonicalPolygonError,
)
from warhammer40k_core.geometry.milli_inch_polygon_queries import (
    PolygonPointLocation,
    polygon_point_distance_ticks,
    polygon_point_location,
)


def test_closed_filled_polygon_point_queries_cover_edges_vertices_and_interior() -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 0), (4, 4), (0, 4)))
    for point in ((0, 0), (4, 4), (2, 0), (4, 2), (2, 4), (0, 2)):
        assert polygon_point_location(polygon, point) == PolygonPointLocation.BOUNDARY
        assert polygon_point_distance_ticks(polygon, point) == 0
    assert polygon_point_location(polygon, (2, 2)) == PolygonPointLocation.INTERIOR
    assert polygon_point_distance_ticks(polygon, (2, 2)) == 0
    for point in ((-1, 2), (5, 2), (2, -1), (2, 5)):
        assert polygon_point_location(polygon, point) == PolygonPointLocation.EXTERIOR
        assert polygon_point_distance_ticks(polygon, point) == 1


def test_concave_polygon_queries_count_vertex_crossings_once() -> None:
    polygon = CanonicalPolygon(((0, 0), (6, 0), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6)))
    expected = (
        ((3, 3), PolygonPointLocation.EXTERIOR, 1),
        ((3, 2), PolygonPointLocation.BOUNDARY, 0),
        ((4, 2), PolygonPointLocation.BOUNDARY, 0),
        ((1, 2), PolygonPointLocation.INTERIOR, 0),
        ((5, 2), PolygonPointLocation.INTERIOR, 0),
        ((3, 1), PolygonPointLocation.INTERIOR, 0),
        ((-1, 2), PolygonPointLocation.EXTERIOR, 1),
        ((7, 6), PolygonPointLocation.EXTERIOR, 1),
        ((-1, 6), PolygonPointLocation.EXTERIOR, 1),
    )
    for point, location, distance in expected:
        assert polygon_point_location(polygon, point) == location
        assert polygon_point_distance_ticks(polygon, point) == distance


def test_polygon_queries_preserve_translation_winding_start_and_collinear_vertices() -> None:
    vertices = ((0, 0), (2, 0), (4, 0), (4, 4), (0, 4))
    for offset in (0, 10**15, -(10**15)):
        translated = tuple((x + offset, y - offset) for x, y in vertices)
        for ring in (translated, tuple(reversed(translated)), (*translated[2:], *translated[:2])):
            polygon = CanonicalPolygon(ring)
            for point, location, distance in (
                ((2, 0), PolygonPointLocation.BOUNDARY, 0),
                ((1, 1), PolygonPointLocation.INTERIOR, 0),
                ((7, 8), PolygonPointLocation.EXTERIOR, 5),
            ):
                query = (point[0] + offset, point[1] - offset)
                assert polygon_point_location(polygon, query) == location
                assert polygon_point_distance_ticks(polygon, query) == distance


def test_exterior_zero_distance_is_not_contact_and_projection_is_not_snapped() -> None:
    # The point is sqrt(1/17) ticks outside the diagonal. Snapping the projection
    # to an endpoint would invent a one-tick gap instead of the rounded zero.
    polygon = CanonicalPolygon(((0, 0), (4, 1), (0, 4)))
    assert polygon_point_location(polygon, (1, 0)) == PolygonPointLocation.EXTERIOR
    assert polygon_point_distance_ticks(polygon, (1, 0)) == 0
    assert polygon_point_location(polygon, (0, 0)) == PolygonPointLocation.BOUNDARY
    assert polygon_point_distance_ticks(polygon, (0, 0)) == 0
    assert polygon_point_location(polygon, (1, 1)) == PolygonPointLocation.INTERIOR
    assert polygon_point_distance_ticks(polygon, (1, 1)) == 0


def test_polygon_distance_rounds_exact_squared_minimum_without_float_intermediate() -> None:
    square = CanonicalPolygon(((0, 0), (1, 0), (1, 1), (0, 1)))
    assert polygon_point_distance_ticks(square, (2, 2)) == 1  # sqrt(2)
    assert polygon_point_distance_ticks(square, (3, 3)) == 3  # sqrt(8)
    diagonal = CanonicalPolygon(((0, 0), (4, 3), (0, 4)))
    assert polygon_point_distance_ticks(diagonal, (1, 0)) == 1  # 3/5
    assert polygon_point_distance_ticks(diagonal, (3, 2)) == 0  # 1/5
    # For integer n, sqrt(n**2 + n) lies just below n+1/2. Adding one
    # moves above it, at magnitudes where binary floats lose that distinction.
    k = 10**8
    below_n, above_n = k**2, 3 * k**2
    assert polygon_point_distance_ticks(square, (below_n + 1, k + 1)) == below_n
    assert polygon_point_distance_ticks(square, (above_n, 3 * k + 1)) == above_n + 1


def test_polygon_query_coordinate_extremes_use_unbounded_intermediate_arithmetic() -> None:
    polygon = CanonicalPolygon(
        ((MIN_COORDINATE_TICKS, 0), (MAX_COORDINATE_TICKS, 0), (MAX_COORDINATE_TICKS, 2))
    )
    assert polygon_point_location(polygon, (0, 1)) == PolygonPointLocation.INTERIOR
    assert (
        polygon_point_location(polygon, (MIN_COORDINATE_TICKS, 0)) == PolygonPointLocation.BOUNDARY
    )
    square = CanonicalPolygon(
        ((MIN_COORDINATE_TICKS, 0), (MIN_COORDINATE_TICKS + 1, 0), (MIN_COORDINATE_TICKS, 1))
    )
    # Derived lengths need not fit the signed coordinate representation.
    assert polygon_point_distance_ticks(square, (MAX_COORDINATE_TICKS, 0)) == 2**64 - 2


def test_polygon_queries_reject_noncanonical_points_and_objects_with_typed_errors() -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 0), (0, 4)))
    invalid: tuple[Any, ...] = (
        None,
        [],
        [0, 0],
        (),
        (0,),
        (0, 0, 0),
        (True, 0),
        (0, False),
        (0.0, 0),
        (Decimal(0), 0),
        (Fraction(0), 0),
        ("0", 0),
        (object(), 0),
        (MIN_COORDINATE_TICKS - 1, 0),
        (0, MAX_COORDINATE_TICKS + 1),
    )
    for query in (polygon_point_location, polygon_point_distance_ticks):
        for point in invalid:
            with pytest.raises(CanonicalPolygonError):
                query(polygon, point)
        for impostor in (None, polygon.to_payload(), polygon.vertices):
            with pytest.raises(CanonicalPolygonError, match="canonical polygon"):
                query(impostor, (0, 0))  # type: ignore[arg-type]


def test_polygon_queries_preserve_payload_and_identity() -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 1), (0, 4)))
    payload, identity = polygon.to_payload(), polygon.content_hash
    restored = CanonicalPolygon.from_payload(payload)
    for point in ((0, 0), (1, 1), (1, 0), (10, 10)):
        assert polygon_point_location(restored, point) == polygon_point_location(polygon, point)
        assert polygon_point_distance_ticks(restored, point) == polygon_point_distance_ticks(
            polygon, point
        )
    assert polygon.to_payload() == payload
    assert restored.content_hash == polygon.content_hash == identity
