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
from warhammer40k_core.geometry.milli_inch_circle import (
    CIRCLE_SCHEMA,
    MAX_CENTER_TICKS,
    MAX_DIAMETER_TICKS,
    MIN_CENTER_TICKS,
    CanonicalCircle,
    CanonicalCircleError,
    CircleRelation,
)


def test_circle_canonicalizes_signed_centers_and_full_diameter_once() -> None:
    circle = CanonicalCircle.from_inches(x="-0.0005", y="0.0005", diameter="1.0005")
    assert circle.center == (-1, 1)
    assert circle.diameter_ticks == 1001
    assert circle.radius_inches == Fraction(1001, 2000)
    assert CanonicalCircle.from_inches(x="-0", y=0, diameter=1).center == (0, 0)
    with pytest.raises(FrozenInstanceError):
        circle.diameter_ticks = 1000  # type: ignore[misc]
    with localcontext() as context:
        context.prec = 2
        metric = CanonicalCircle.from_millimeters(
            x=Decimal("-0.0127"), y=Fraction(127, 5), diameter=Decimal("25.4127")
        )
    assert metric == CanonicalCircle((-1, 1000), 1001)
    # A decoded float retains its binary ratio, not its decimal-looking spelling.
    assert CanonicalCircle.from_inches(x=0, y=0, diameter=1.0005).diameter_ticks == 1000


def test_circle_rejects_invalid_and_collapsed_sources() -> None:
    invalid: tuple[Any, ...] = (True, "NaN", float("inf"), "not-a-number", object())
    for value in invalid:
        for factory in (CanonicalCircle.from_inches, CanonicalCircle.from_millimeters):
            with pytest.raises(DistancePrecisionError):
                factory(x=value, y=0, diameter=1)
            with pytest.raises(DistancePrecisionError):
                factory(x=0, y=value, diameter=1)
            with pytest.raises(DistancePrecisionError):
                factory(x=0, y=0, diameter=value)
    for diameter in (0, -1, "0.00049", "-0.00001"):
        with pytest.raises(CanonicalCircleError, match="diameter"):
            CanonicalCircle.from_inches(x=0, y=0, diameter=diameter)
    with pytest.raises(CanonicalCircleError, match="diameter"):
        CanonicalCircle.from_millimeters(x=0, y=0, diameter="0.0126")
    assert CanonicalCircle.from_inches(x=0, y=0, diameter="0.0005").diameter_ticks == 1


def test_circle_rejects_malformed_canonical_values_and_queries() -> None:
    invalid_centers: tuple[Any, ...] = ([], [0, 0], (), (0,), (0, 0, 0), (True, 0), (0, 1.0))
    for center in invalid_centers:
        with pytest.raises(CanonicalCircleError):
            CanonicalCircle(center, 1000)
    invalid_diameters: tuple[Any, ...] = (True, 0, -1, 1.0, "1", None)
    for diameter in invalid_diameters:
        with pytest.raises(CanonicalCircleError):
            CanonicalCircle((0, 0), diameter)
    circle = CanonicalCircle((0, 0), 1000)
    invalid: Any = object()
    with pytest.raises(CanonicalCircleError):
        circle.relation_to(invalid)
    with pytest.raises(CanonicalCircleError):
        circle.surface_gap_ticks(invalid)


def test_circle_topology_distinguishes_external_contact_overlap_and_containment() -> None:
    for offset in (0, 10**15, -(10**15)):
        first = CanonicalCircle((offset, offset), 1000)
        cases = (
            ((1001, 0), 1000, CircleRelation.SEPARATED),
            ((1000, 0), 1000, CircleRelation.EXTERNAL_CONTACT),
            ((600, 800), 1000, CircleRelation.EXTERNAL_CONTACT),
            ((999, 0), 1000, CircleRelation.INTERIOR_OVERLAP),
            ((0, 0), 1000, CircleRelation.INTERIOR_OVERLAP),
            ((0, 0), 200, CircleRelation.INTERIOR_OVERLAP),
            # Internally tangent disks share interior; this is not legal base contact.
            ((400, 0), 200, CircleRelation.INTERIOR_OVERLAP),
        )
        for (x, y), diameter, expected in cases:
            second = CanonicalCircle((offset + x, offset + y), diameter)
            assert first.relation_to(second) is expected
            assert second.relation_to(first) is expected
            if expected is not CircleRelation.SEPARATED:
                assert first.surface_gap_ticks(second) == 0


def test_circle_rounded_zero_does_not_establish_contact_or_permit_overlap() -> None:
    first = CanonicalCircle((0, 0), 1000)
    for center, relation in (
        ((1000, 1), CircleRelation.SEPARATED),
        ((1000, 0), CircleRelation.EXTERNAL_CONTACT),
        ((999, 0), CircleRelation.INTERIOR_OVERLAP),
    ):
        second = CanonicalCircle(center, 1000)
        assert first.surface_gap_ticks(second) == 0
        assert first.relation_to(second) is relation
    # Irrational centre distance sqrt(2) ticks, less two half-tick radii:
    # rounding the centre first would lose the true 0.414... tick gap.
    assert CanonicalCircle((0, 0), 1).surface_gap_ticks(CanonicalCircle((1, 1), 1)) == 0
    assert CanonicalCircle((0, 0), 1).surface_gap_ticks(CanonicalCircle((2, 2), 1)) == 2


def test_circle_surface_gap_rounds_half_ticks_once_and_preserves_scalar_operators() -> None:
    first = CanonicalCircle((0, 0), 1000)
    # The radii sum is 1000.5 ticks. Round the gap, never the centres or radii first.
    for center, expected, comparisons in (
        ((1001, 0), 1, (True, False, True, False)),  # exact lower half-tick -> 1
        ((1001, 1), 1, (True, False, True, False)),  # irrational, inside the bin
        ((1002, 0), 2, (False, False, True, True)),  # exact upper half-tick -> 2
    ):
        second = CanonicalCircle(center, 1001)
        result = first.surface_gap_ticks(second)
        assert result == expected
        assert (result <= 1, result < 1, result >= 1, result > 1) == comparisons
        assert second.surface_gap_ticks(first) == expected
    # Even diameter sum, irrational centre distance just below/above 0.5-tick gap.
    assert first.surface_gap_ticks(CanonicalCircle((1000, 31), 1000)) == 0
    assert first.surface_gap_ticks(CanonicalCircle((1000, 32), 1000)) == 1


def test_circle_gap_bin_certificates_cover_even_odd_diagonal_and_contained_disks() -> None:
    # Independently certify the defining interval of every returned tick, including
    # irrational distances. These squared inequalities are exact because all
    # boundaries compared here are nonnegative.
    for diameter in (1, 2, 3, 10):
        first = CanonicalCircle((0, 0), diameter)
        for other_diameter in (1, 2, 3, 10):
            radius_sum = Fraction(diameter + other_diameter, 2)
            for x in range(-12, 13):
                for y in range(-12, 13):
                    result = first.surface_gap_ticks(CanonicalCircle((x, y), other_diameter))
                    squared_distance = x * x + y * y
                    if squared_distance <= radius_sum**2:
                        assert result == 0
                    else:
                        assert squared_distance < (radius_sum + result + Fraction(1, 2)) ** 2
                        if result:
                            assert squared_distance >= (radius_sum + result - Fraction(1, 2)) ** 2


def test_circle_mixed_parity_contact_remains_unrepresentable_on_integer_grid() -> None:
    # Contact requires 4*(dx**2+dy**2) == (d1+d2)**2. For unlike diameter parity,
    # the left side is divisible by four and the right side is congruent to one.
    first = CanonicalCircle((0, 0), 1000)
    second = CanonicalCircle((1000, 0), 1001)
    assert (first.diameter_ticks + second.diameter_ticks) ** 2 % 4 == 1
    assert first.relation_to(second) is CircleRelation.INTERIOR_OVERLAP
    next_tick = CanonicalCircle((1001, 0), 1001)
    assert first.relation_to(next_tick) is CircleRelation.SEPARATED
    # Same odd parity can represent real contact and keeps exact half-tick radii.
    odd = CanonicalCircle((0, 0), 1001)
    assert odd.relation_to(CanonicalCircle((1001, 0), 1001)) is CircleRelation.EXTERNAL_CONTACT


def test_circle_payload_is_detached_strict_and_revalidated() -> None:
    circle = CanonicalCircle((-1, 2), 1001)
    payload = circle.to_payload()
    decoded = CanonicalCircle.from_payload(payload)
    payload["center"][0] = 99
    assert decoded == circle
    assert circle.to_payload()["center"] == [-1, 2]
    malformed: list[Any] = [None, [], {}, {**circle.to_payload(), "extra": 1}]
    for key in circle.to_payload():
        missing = dict(circle.to_payload())
        del missing[key]
        malformed.append(missing)
    for key, value in (
        ("schema_version", "old-circle"),
        ("schema_version", 1),
        ("numerical_policy_id", "legacy-binary-inch-v1"),
        ("numerical_policy_id", "unknown"),
        ("numerical_policy_id", None),
        ("center", (0, 0)),
        ("center", [0]),
        ("center", [0, 0, 0]),
        ("center", [True, 0]),
        ("center", [0, 1.0]),
        ("diameter_ticks", True),
        ("diameter_ticks", 0),
        ("diameter_ticks", 1.0),
    ):
        altered = copy.deepcopy(dict(circle.to_payload()))
        altered[key] = value
        malformed.append(altered)
    for item in malformed:
        with pytest.raises(CanonicalCircleError):
            CanonicalCircle.from_payload(item)


def test_circle_identity_binds_policy_version_center_and_full_diameter() -> None:
    circle = CanonicalCircle((-1, 2), 1001)
    payload = circle.to_payload()
    assert payload["schema_version"] == CIRCLE_SCHEMA
    assert payload["numerical_policy_id"] == DISTANCE_POLICY_ID
    assert (
        circle.content_hash
        == hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    )
    assert CanonicalCircle.from_payload(json.loads(json.dumps(payload))).content_hash == (
        circle.content_hash
    )
    assert CanonicalCircle((0, 2), 1001).content_hash != circle.content_hash
    assert CanonicalCircle((-1, 3), 1001).content_hash != circle.content_hash
    assert CanonicalCircle((-1, 2), 1000).content_hash != circle.content_hash


def test_circle_representation_bounds_preserve_json_and_exact_large_distances() -> None:
    first = CanonicalCircle((MIN_CENTER_TICKS, 0), MAX_DIAMETER_TICKS)
    second = CanonicalCircle((MAX_CENTER_TICKS, 0), MAX_DIAMETER_TICKS)
    assert CanonicalCircle.from_payload(json.loads(json.dumps(first.to_payload()))) == first
    assert len(first.content_hash) == 64
    assert first.relation_to(second) is CircleRelation.SEPARATED
    assert first.surface_gap_ticks(second) == 2**63
    # Derived lengths may exceed stored coordinate bounds; Python integer arithmetic
    # is exact, and every result remains small enough for ordinary JSON integers.
    for coordinate in (MIN_CENTER_TICKS - 1, MAX_CENTER_TICKS + 1, 10**5000):
        with pytest.raises(CanonicalCircleError, match="64-bit"):
            CanonicalCircle((coordinate, 0), 1)
        with pytest.raises(CanonicalCircleError, match="64-bit"):
            CanonicalCircle.from_inches(x=coordinate, y=0, diameter=1)
        with pytest.raises(CanonicalCircleError, match="64-bit"):
            CanonicalCircle.from_payload({**first.to_payload(), "center": [coordinate, 0]})
    for diameter in (MAX_DIAMETER_TICKS + 1, 10**5000):
        with pytest.raises(CanonicalCircleError, match="64-bit"):
            CanonicalCircle((0, 0), diameter)
        with pytest.raises(CanonicalCircleError, match="64-bit"):
            CanonicalCircle.from_inches(x=0, y=0, diameter=diameter)
        with pytest.raises(CanonicalCircleError, match="64-bit"):
            CanonicalCircle.from_payload({**first.to_payload(), "diameter_ticks": diameter})
