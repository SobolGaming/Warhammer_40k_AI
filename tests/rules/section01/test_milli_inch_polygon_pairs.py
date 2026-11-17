from __future__ import annotations

from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    CanonicalPolygon,
    CanonicalPolygonError,
)
from warhammer40k_core.geometry.milli_inch_polygon_pairs import (
    PolygonRelation,
    polygon_polygon_distance_ticks,
    polygon_polygon_relation,
)


def _assert_pair(
    first: CanonicalPolygon, second: CanonicalPolygon, relation: PolygonRelation, distance: int
) -> None:
    for left, right in ((first, second), (second, first)):
        assert polygon_polygon_relation(left, right) == relation
        assert polygon_polygon_distance_ticks(left, right) == distance


def test_polygon_pairs_distinguish_separation_contact_and_overlap() -> None:
    square = CanonicalPolygon(((0, 0), (4, 0), (4, 4), (0, 4)))
    for vertices, relation, distance in (
        (((6, 0), (8, 0), (8, 4), (6, 4)), PolygonRelation.SEPARATED, 2),
        (((4, 0), (8, 0), (8, 4), (4, 4)), PolygonRelation.CONTACT, 0),
        (((4, 4), (8, 4), (8, 8), (4, 8)), PolygonRelation.CONTACT, 0),
        (((2, -1), (6, -1), (6, 3), (2, 3)), PolygonRelation.INTERIOR_OVERLAP, 0),
        (((1, 1), (3, 1), (3, 3), (1, 3)), PolygonRelation.INTERIOR_OVERLAP, 0),
        (((0, 0), (4, 0), (4, 4), (0, 4)), PolygonRelation.INTERIOR_OVERLAP, 0),
    ):
        _assert_pair(square, CanonicalPolygon(vertices), relation, distance)


def test_polygon_pair_boundary_vertices_do_not_hide_interior_overlap() -> None:
    square = CanonicalPolygon(((0, 0), (6, 0), (6, 6), (0, 6)))
    # Every triangle/diamond vertex lies on the square boundary. Neither has a
    # proper edge crossing or a vertex strictly inside the other polygon.
    for ring in (
        ((0, 0), (6, 0), (0, 6)),
        ((3, 0), (6, 3), (3, 6), (0, 3)),
        ((0, 0), (3, 0), (6, 0), (6, 6), (0, 6)),
    ):
        _assert_pair(square, CanonicalPolygon(ring), PolygonRelation.INTERIOR_OVERLAP, 0)


def test_polygon_pairs_classify_shared_edges_by_interior_side() -> None:
    square = CanonicalPolygon(((0, 0), (6, 0), (6, 6), (0, 6)))
    for ring, relation in (
        (((1, 0), (5, 0), (5, 2), (1, 2)), PolygonRelation.INTERIOR_OVERLAP),
        (((1, 0), (1, -2), (5, -2), (5, 0)), PolygonRelation.CONTACT),
        (((0, 0), (6, 0), (6, -2), (0, -2)), PolygonRelation.CONTACT),
    ):
        for variant in (ring, tuple(reversed(ring)), (*ring[1:], ring[0])):
            _assert_pair(square, CanonicalPolygon(variant), relation, 0)


def test_polygon_pairs_handle_concavity_t_junctions_and_split_boundary_edges() -> None:
    cup = CanonicalPolygon(((0, 0), (6, 0), (6, 6), (4, 6), (4, 2), (2, 2), (2, 6), (0, 6)))
    for ring, relation, distance in (
        (((2, 3), (4, 3), (4, 5), (2, 5)), PolygonRelation.CONTACT, 0),
        (((2, 2), (4, 2), (4, 6), (2, 6)), PolygonRelation.CONTACT, 0),
        (((2, 6), (4, 6), (3, 8)), PolygonRelation.CONTACT, 0),
        (((1, 4), (5, 4), (3, 6)), PolygonRelation.INTERIOR_OVERLAP, 0),
        (((2, 1), (4, 1), (3, 5)), PolygonRelation.INTERIOR_OVERLAP, 0),
        (((2, 8), (4, 8), (3, 9)), PolygonRelation.SEPARATED, 2),
    ):
        _assert_pair(cup, CanonicalPolygon(ring), relation, distance)
    # The long triangle edge has two foreign vertices on it. Its midpoint is
    # outside the cup, but the open intervals near its endpoints enter the arms.
    triangle = CanonicalPolygon(((0, 4), (6, 4), (3, 8)))
    _assert_pair(cup, triangle, PolygonRelation.INTERIOR_OVERLAP, 0)


def test_polygon_pair_zero_rounded_gap_does_not_establish_contact() -> None:
    first = CanonicalPolygon(((0, 0), (4, 1), (0, 4)))
    second = CanonicalPolygon(((1, 0), (2, 0), (1, -1)))
    _assert_pair(first, second, PolygonRelation.SEPARATED, 0)
    # The closest point is inside the diagonal segment; no projected point is snapped.
    third = CanonicalPolygon(((1, -1), (2, -1), (1, -2)))
    _assert_pair(first, third, PolygonRelation.SEPARATED, 1)


def test_polygon_pair_distance_uses_exact_minimum_and_squared_rounding() -> None:
    square = CanonicalPolygon(((0, 0), (1, 0), (1, 1), (0, 1)))
    for x, y, expected in ((2, 2, 1), (3, 3, 3), (10**16 + 1, 10**8 + 1, 10**16)):
        other = CanonicalPolygon(((x, y), (x + 1, y), (x, y + 1)))
        _assert_pair(square, other, PolygonRelation.SEPARATED, expected)
    x, y = 3 * 10**16, 3 * 10**8 + 1
    other = CanonicalPolygon(((x, y), (x + 1, y), (x, y + 1)))
    _assert_pair(square, other, PolygonRelation.SEPARATED, 3 * 10**16 + 1)


def test_polygon_pairs_preserve_translation_ring_order_payload_and_hash() -> None:
    first = ((0, 0), (4, 1), (0, 4))
    second = ((1, 0), (2, 0), (1, -1))
    for offset in (0, 10**15, -(10**15)):
        translated = tuple((x + offset, y - offset) for x, y in first)
        other = CanonicalPolygon(tuple((x + offset, y - offset) for x, y in second))
        for ring in (translated, tuple(reversed(translated)), (*translated[1:], translated[0])):
            polygon = CanonicalPolygon(ring)
            payload, identity = polygon.to_payload(), polygon.content_hash
            restored = CanonicalPolygon.from_payload(payload)
            _assert_pair(restored, other, PolygonRelation.SEPARATED, 0)
            assert polygon.to_payload() == payload
            assert polygon.content_hash == restored.content_hash == identity


def test_polygon_pairs_coordinate_extremes_keep_unbounded_derived_lengths() -> None:
    low, high = MIN_COORDINATE_TICKS, MAX_COORDINATE_TICKS
    left = CanonicalPolygon(((low, 0), (low + 1, 0), (low, 1)))
    right = CanonicalPolygon(((high, 0), (high, 1), (high - 1, 0)))
    _assert_pair(left, right, PolygonRelation.SEPARATED, 2**64 - 3)
    wide = CanonicalPolygon(((low, 0), (high, 0), (high, 2), (low, 2)))
    _assert_pair(wide, left, PolygonRelation.INTERIOR_OVERLAP, 0)


def test_polygon_pair_queries_reject_noncanonical_inputs() -> None:
    polygon = CanonicalPolygon(((0, 0), (4, 0), (0, 4)))
    invalid: tuple[Any, ...] = (None, True, [], polygon.vertices, polygon.to_payload(), object())
    for query in (polygon_polygon_relation, polygon_polygon_distance_ticks):
        for other in invalid:
            with pytest.raises(CanonicalPolygonError, match="canonical polygon"):
                query(polygon, other)
            with pytest.raises(CanonicalPolygonError, match="canonical polygon"):
                query(other, polygon)
