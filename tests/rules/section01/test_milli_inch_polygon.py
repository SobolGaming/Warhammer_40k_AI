from __future__ import annotations

import copy
import hashlib
import json
from dataclasses import FrozenInstanceError
from decimal import Decimal, localcontext
from fractions import Fraction
from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch import DISTANCE_POLICY_ID, DistancePrecisionError
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    POLYGON_SCHEMA,
    CanonicalPolygon,
    CanonicalPolygonError,
)


def test_canonical_ring_rounds_signed_sources_once_and_preserves_order() -> None:
    ring = CanonicalPolygon.from_inches(
        (("-0.0005", "-0.0005"), ("1.0005", "-0.0005"), ("0", "1.0005"))
    )
    assert ring.vertices == ((-1, -1), (1001, -1), (0, 1001))
    assert CanonicalPolygon(tuple(reversed(ring.vertices))).vertices == tuple(
        reversed(ring.vertices)
    )
    with pytest.raises(FrozenInstanceError):
        ring.vertices = ()  # type: ignore[misc]
    # Straight continuation is valid; it is retained, never silently simplified.
    assert CanonicalPolygon(((0, 0), (1, 0), (2, 0), (2, 2), (0, 2))).vertices[1] == (1, 0)


def test_canonical_ring_exact_units_decimal_context_and_float_interpretation() -> None:
    with localcontext() as context:
        context.prec = 2
        millimeters = CanonicalPolygon.from_millimeters(
            ((0, 0), (Decimal("25.4127"), 0), (0, Fraction(127, 5)))
        )
    assert millimeters.vertices == ((0, 0), (1001, 0), (0, 1000))
    # Float 1.0005 is below the exact decimal tie on this binary ratio.
    assert CanonicalPolygon.from_inches(((0, 0), (1.0005, 0), (0, 1))).vertices[1] == (1000, 0)
    assert CanonicalPolygon.from_inches(((0, 0), ("1.0005", 0), (0, 1))).vertices[1] == (1001, 0)
    assert CanonicalPolygon.from_inches((("-0", 0), (1, 0), (0, 1))).vertices[0] == (0, 0)


def test_canonical_ring_rejects_invalid_sources_before_snapping_can_repair_them() -> None:
    invalid: Any = (
        (),
        ((0, 0), (1, 0)),
        ((0, 0), (1, 0), (1, 1), (0, 0)),
        ((0, 0), (1, 0), (2, 0)),
        # Invalid source would snap to the valid triangle (0,0), (1,0), (1,1).
        ((0, 0), ("0.0006", "0.0003"), ("0.0012", "0.0006")),
        ((0, 0), (2, 2), (0, 2), (2, 0)),
        ((0, 0), (3, 0), (2, 0), (2, 2), (0, 2)),
        ((0, 0), (2, 0), (2, 2), (1, 0), (0, 2)),
        [(0, 0), (1, 0), (0, 1)],
        ((0, 0), (1,), (0, 1)),
    )
    for source in invalid:
        with pytest.raises(CanonicalPolygonError):
            CanonicalPolygon.from_inches(source)
    invalid_coordinates: tuple[Any, ...] = (True, "NaN", float("inf"), "not-a-number", object())
    for coordinate in invalid_coordinates:
        with pytest.raises(DistancePrecisionError):
            CanonicalPolygon.from_inches(((0, 0), (coordinate, 0), (0, 1)))


def test_canonical_ring_rejects_quantization_collapse_and_new_edge_contacts() -> None:
    for source in (
        ((0, 0), ("0.0004", 0), (0, 1)),
        ((0, 0), (1, "0.0004"), (2, 0)),
        # Both triangles are simple but snapping reverses their winding.
        (("0.00049", "0.00049"), ("0.00051", "-0.00049"), ("-0.00049", "0.00051")),
        # A simple sub-tick protrusion snaps into overlapping edges.
        ((0, 0), (2, 0), (2, 2), ("0.0004", 2), ("-0.0004", 1), (0, 1)),
        # A valid narrow channel snaps closed and makes nonadjacent edges touch.
        ((0, 0), (2, 0), (2, 2), (1, 2), (1, "0.0004"), ("0.9996", 1), (0, 1)),
    ):
        with pytest.raises(CanonicalPolygonError):
            CanonicalPolygon.from_inches(source)


def test_canonical_ring_payload_is_detached_strict_and_revalidates_topology() -> None:
    polygon = CanonicalPolygon(((0, 0), (1000, 0), (0, 1000)))
    payload = polygon.to_payload()
    decoded = CanonicalPolygon.from_payload(payload)
    payload["vertices"][0][0] = 99
    assert decoded == polygon
    assert polygon.to_payload()["vertices"][0] == [0, 0]
    malformed: list[Any] = [None, [], {}, {**polygon.to_payload(), "extra": 1}]
    for key in ("schema_version", "numerical_policy_id", "vertices"):
        missing = dict(polygon.to_payload())
        del missing[key]
        malformed.append(missing)
    for key, value in (
        ("schema_version", "old-ring"),
        ("numerical_policy_id", "legacy-binary-inch-v1"),
        ("numerical_policy_id", "unknown"),
        ("vertices", [[0, 0], [True, 0], [0, 1]]),
        ("vertices", [[0, 0], [1.0, 0], [0, 1]]),
        ("vertices", ((0, 0), (1, 0), (0, 1))),
        ("vertices", [[0, 0], [1], [0, 1]]),
        ("vertices", [[0, 0], (1, 0), [0, 1]]),
        ("vertices", [[0, 0], [1, 0], [0, 0]]),
        ("vertices", [[0, 0], [2, 2], [0, 2], [2, 0]]),
    ):
        altered = copy.deepcopy(dict(polygon.to_payload()))
        altered[key] = value
        malformed.append(altered)
    for item in malformed:
        with pytest.raises(CanonicalPolygonError):
            CanonicalPolygon.from_payload(item)
    invalid_vertices: tuple[Any, ...] = (
        [],
        ((0, 0), (True, 0), (0, 1)),
        ((0, 0), (1, 0), (0, 1.0)),
    )
    for vertices in invalid_vertices:
        with pytest.raises(CanonicalPolygonError):
            CanonicalPolygon(vertices)


def test_canonical_ring_identity_binds_policy_version_winding_and_start() -> None:
    polygon = CanonicalPolygon(((0, 0), (1000, 0), (0, 1000)))
    payload = polygon.to_payload()
    assert payload["schema_version"] == POLYGON_SCHEMA
    assert payload["numerical_policy_id"] == DISTANCE_POLICY_ID
    assert (
        polygon.content_hash
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert CanonicalPolygon.from_payload(json.loads(json.dumps(payload))).content_hash == (
        polygon.content_hash
    )
    assert CanonicalPolygon(tuple(reversed(polygon.vertices))).content_hash != polygon.content_hash
    assert CanonicalPolygon((*polygon.vertices[1:], polygon.vertices[0])).content_hash != (
        polygon.content_hash
    )
    assert CanonicalPolygon(((0, 0), (1001, 0), (0, 1000))).content_hash != polygon.content_hash


def test_canonical_ring_topology_has_no_distance_or_coordinate_tolerance() -> None:
    for offset in (0, 10**15, -(10**15)):
        # One tick is a valid physical width; exact translation does not change topology.
        ring = CanonicalPolygon(((offset, 0), (offset + 1, 0), (offset + 1, 1), (offset, 1)))
        assert CanonicalPolygon.from_payload(ring.to_payload()) == ring
    # A source ring can be arbitrarily small yet valid; snapping, rather than an
    # epsilon source validator, is what rejects its unrepresentable canonical form.
    tiny = Fraction(1, 10**30)
    with pytest.raises(CanonicalPolygonError, match="distinct"):
        CanonicalPolygon.from_inches(((0, 0), (tiny, 0), (0, tiny)))


def test_canonical_ring_coordinate_bounds_guarantee_json_identity() -> None:
    polygon = CanonicalPolygon(((MIN_COORDINATE_TICKS, 0), (MAX_COORDINATE_TICKS, 0), (0, 1)))
    assert CanonicalPolygon.from_payload(json.loads(json.dumps(polygon.to_payload()))) == polygon
    assert len(polygon.content_hash) == 64
    for coordinate in (MIN_COORDINATE_TICKS - 1, MAX_COORDINATE_TICKS + 1, 10**5000):
        with pytest.raises(CanonicalPolygonError, match="64-bit"):
            CanonicalPolygon(((0, 0), (coordinate, 0), (0, 1)))
        with pytest.raises(CanonicalPolygonError, match="64-bit"):
            CanonicalPolygon.from_inches(((0, 0), (coordinate, 0), (0, 1)))
        with pytest.raises(CanonicalPolygonError, match="64-bit"):
            CanonicalPolygon.from_payload(
                {**polygon.to_payload(), "vertices": [[0, 0], [coordinate, 0], [0, 1]]}
            )
