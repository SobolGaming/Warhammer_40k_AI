from __future__ import annotations

import copy
import json
from collections.abc import Callable
from dataclasses import FrozenInstanceError
from fractions import Fraction as F
from typing import Any

import pytest

from warhammer40k_core.geometry.exact_contact import (
    ExactDisk,
    certify_straight_contact,
    rational_anchor_contact_centers,
    squared_exact_inches_to_ticks,
)
from warhammer40k_core.geometry.exact_coordinate import (
    COORDINATE_REPRESENTATION_ID,
    ExactCoordinateError,
    UnsupportedExactCoordinateError,
)
from warhammer40k_core.geometry.exact_coordinate import (
    ExactCoordinate as C,
)
from warhammer40k_core.geometry.milli_inch import squared_inches_to_ticks
from warhammer40k_core.geometry.milli_inch_circle import CanonicalCircle, CircleRelation


def disk(x: F, y: F, diameter: int) -> ExactDisk:
    return ExactDisk((C(x), C(y)), diameter)


def test_exact_contact_rational_tangency_and_once_rounded_approach_controls() -> None:
    stationary = disk(F(0), F(0), 1000)
    end = disk(F(2001, 2000), F(0), 1001)
    assert stationary.relation_to(end) is CircleRelation.EXTERNAL_CONTACT
    assert squared_exact_inches_to_ticks(C(F(2001, 2000) ** 2)) == 1001
    for x, travel in ((F(2), 1000), (F(2001, 1000), 1001)):
        proof = certify_straight_contact(disk(x, F(0), 1001), end, (stationary,))
        assert proof.travel_ticks == travel
        assert (proof.travel_ticks <= 1000) == (x == 2)
    assert (
        CanonicalCircle((1000, 0), 1001).relation_to(CanonicalCircle((0, 0), 1000))
        is CircleRelation.INTERIOR_OVERLAP
    )


def test_exact_contact_irrational_and_simultaneous_contacts_have_full_segment_proofs() -> None:
    height = C.from_root(F(0), F(1, 2000), F(4001))
    moving = ExactDisk((C(F(0)), height), 1001)
    obstacles = (disk(F(-1), F(0), 1000), disk(F(1), F(0), 1000))
    assert all(
        moving.relation_to(obstacle) is CircleRelation.EXTERNAL_CONTACT for obstacle in obstacles
    )
    assert obstacles[0].relation_to(obstacles[1]) is CircleRelation.SEPARATED
    assert rational_anchor_contact_centers(*obstacles, 1001) == (
        moving,
        ExactDisk((C(F(0)), -height), 1001),
    )
    start = disk(F(0), F(2), 1001)
    proof = certify_straight_contact(start, moving, obstacles)
    assert proof.travel_ticks == 1968
    assert proof == certify_straight_contact(start, moving, tuple(reversed(obstacles)))
    off_axis = ExactDisk((C(F(1)), height), 1001)
    assert off_axis.relation_to(disk(F(0), F(0), 1000)) is CircleRelation.EXTERNAL_CONTACT
    # Reflection must select the negative root without rounding it into the same pose.
    reflected = ExactDisk((C(F(0)), -height), 1001)
    assert reflected.content_hash != moving.content_hash
    assert all(
        reflected.relation_to(obstacle) is CircleRelation.EXTERNAL_CONTACT for obstacle in obstacles
    )


def test_exact_contact_rejects_endpoint_only_path_and_illegal_endpoint() -> None:
    obstacle = disk(F(0), F(0), 1000)
    end = disk(F(1), F(0), 1000)
    assert disk(F(-2), F(0), 1000).relation_to(obstacle) is CircleRelation.SEPARATED
    with pytest.raises(ExactCoordinateError, match="segment overlaps"):
        certify_straight_contact(disk(F(-2), F(0), 1000), end, (obstacle,))
    with pytest.raises(ExactCoordinateError, match="externally contact"):
        certify_straight_contact(end, disk(F(10001, 10000), F(0), 1000), (obstacle,))
    with pytest.raises(ExactCoordinateError, match="externally contact"):
        certify_straight_contact(end, disk(F(9999, 10000), F(0), 1000), (obstacle,))
    # Tangent zero travel is valid geometry and does not invent a movement action.
    assert certify_straight_contact(end, end, (obstacle,)).travel_ticks == 0


def test_exact_coordinate_normalizes_equivalent_constructions_and_exact_arithmetic() -> None:
    root = C.from_root(F(1, 3), F(2, 3), F(3, 5))
    assert root == C.from_root(F(1, 3), F(1), F(4, 15))
    assert root == C.from_root(F(1, 3), F(4, 3), F(3, 20))
    assert C.from_root(F(1, 3), F(-2), F(1, 9)) == C(F(-1, 3))
    assert C.from_root(F(5), F(0), F(3)) == C(F(5))
    assert root + (-root) == C(F(0))
    assert root * root.reciprocal() == C(F(1))
    assert root / root == C(F(1))
    assert (root + C(F(7))) - C(F(7)) == root
    assert C(F(2)) * root == root + root
    assert C(F(2)) / C(F(4)) == C(F(1, 2))
    assert C.from_root(F(0), F(1), F(2)) * C.from_root(F(0), F(1), F(8)) == C(F(4))


def test_exact_coordinate_root_selection_sign_and_midpoint_measurement_are_exact() -> None:
    for a in (F(-2), F(-1), F(0), F(1), F(2)):
        for sign in (-1, 1):
            value = C.from_root(a, F(sign), F(2))
            expected = sign if abs(a) < 2 else (1 if a > 0 else -1)
            assert value.sign() == expected
    assert C(F(0)).sign() == 0
    for midpoint in (F(1, 2000), F(1999, 2000), F(2001, 2000)):
        result = (midpoint * 1000).__floor__() + 1
        assert squared_exact_inches_to_ticks(C(midpoint**2)) == result
        assert squared_exact_inches_to_ticks(C((midpoint - F(1, 10**9)) ** 2)) == result - 1
        assert squared_exact_inches_to_ticks(C((midpoint + F(1, 10**9)) ** 2)) == result
    assert squared_exact_inches_to_ticks(C(F(0))) == 0
    assert squared_exact_inches_to_ticks(C.from_root(F(2), F(1), F(2))) == 1848
    assert squared_exact_inches_to_ticks(C(F(2**255))) == squared_inches_to_ticks(F(2**255))


def test_exact_coordinate_rejects_noncanonical_malformed_and_unbounded_inputs() -> None:
    invalid: tuple[Any, ...] = (True, 1, 1.0, "1", None)
    for value in invalid:
        with pytest.raises(ExactCoordinateError):
            C(value)
    for a, sign, q in (
        (F(0), True, F(2)),
        (F(0), 2, F(2)),
        (F(0), 0, F(2)),
        (F(0), 1, F(0)),
        (F(0), 1, F(4)),
        (F(0), 1, F(-2)),
    ):
        with pytest.raises(ExactCoordinateError):
            C(a, sign, q)
    with pytest.raises(UnsupportedExactCoordinateError, match="256 bits"):
        C(F(2**256))
    with pytest.raises(ExactCoordinateError, match="nonnegative"):
        C.from_root(F(0), F(0), F(-1))
    with pytest.raises(ExactCoordinateError, match="reciprocal"):
        C(F(0)).reciprocal()
    with pytest.raises(ExactCoordinateError, match="nonnegative"):
        squared_exact_inches_to_ticks(C(F(-1)))
    with pytest.raises(FrozenInstanceError):
        C(F(0)).rational = F(1)  # type: ignore[misc]


def test_exact_coordinate_mixed_fields_fail_closed_without_approximation() -> None:
    two, three = (C.from_root(F(0), F(1), F(q)) for q in (2, 3))
    operations: tuple[Callable[[], C], ...] = (
        lambda: two + three,
        lambda: two * three,
        lambda: two / three,
    )
    for operation in operations:
        with pytest.raises(UnsupportedExactCoordinateError, match="Mixed quadratic"):
            operation()
    with pytest.raises(UnsupportedExactCoordinateError):
        ExactDisk((two, three), 1000).relation_to(disk(F(1), F(1), 1000))


def test_rational_contact_constructor_handles_rational_roots_degeneracy_and_rotation() -> None:
    for anchors in (
        (disk(F(0), F(0), 1000), disk(F(6, 5), F(0), 1000)),
        (disk(F(2), F(3), 1000), disk(F(2), F(21, 5), 1000)),
        (disk(F(2), F(3), 1000), disk(F(16, 5), F(23, 5), 1000)),
    ):
        solutions = rational_anchor_contact_centers(*anchors, 1000)
        assert solutions
        assert all(
            solution.relation_to(anchor) is CircleRelation.EXTERNAL_CONTACT
            for solution in solutions
            for anchor in anchors
        )
    assert rational_anchor_contact_centers(
        disk(F(0), F(0), 1000), disk(F(2), F(0), 1000), 1000
    ) == (disk(F(1), F(0), 1000),)
    assert (
        rational_anchor_contact_centers(disk(F(0), F(0), 1000), disk(F(3), F(0), 1000), 1000) == ()
    )
    with pytest.raises(UnsupportedExactCoordinateError, match="Coincident"):
        rational_anchor_contact_centers(disk(F(0), F(0), 1000), disk(F(0), F(0), 1001), 1000)
    with pytest.raises(UnsupportedExactCoordinateError, match="rational anchor"):
        rational_anchor_contact_centers(
            ExactDisk((C.from_root(F(0), F(1), F(2)), C(F(0))), 1000), disk(F(0), F(0), 1000), 1000
        )
    with pytest.raises(ExactCoordinateError):
        rational_anchor_contact_centers(disk(F(0), F(0), 1000), disk(F(1), F(0), 1000), True)


def test_exact_disk_restore_preserves_witness_identity_and_rejects_cross_profiles() -> None:
    height = C.from_root(F(0), F(1, 2000), F(4001))
    original = ExactDisk((C(F(2001, 2000)), height), 1001)
    payload = original.to_payload()
    restored = ExactDisk.from_payload(json.loads(json.dumps(payload)))
    assert restored == original
    assert restored.content_hash == original.content_hash
    assert payload["coordinate_representation_id"] == COORDINATE_REPRESENTATION_ID
    payload["center"][0]["rational"][0] = 7
    assert restored == original
    invalid: list[Any] = [None, {}, {**original.to_payload(), "extra": 1}]
    for key in original.to_payload():
        changed = dict(original.to_payload())
        del changed[key]
        invalid.append(changed)
    changes: tuple[tuple[str, Any], ...] = (
        ("schema_version", "old"),
        ("numerical_policy_id", "legacy-binary-inch-v1"),
        ("coordinate_representation_id", "unknown"),
        ("center", []),
        ("diameter_ticks", True),
        ("diameter_ticks", 0),
    )
    for key, value in changes:
        invalid.append({**original.to_payload(), key: value})
    for value in invalid:
        with pytest.raises(ExactCoordinateError):
            ExactDisk.from_payload(value)
    invalid_fractions: tuple[Any, ...] = (
        [0, 2],
        [2, 4],
        [1, -2],
        [True, 1],
        [1.0, 1],
        [1, 0],
        [2**256, 1],
    )
    for raw in invalid_fractions:
        altered = copy.deepcopy(original.to_payload())
        altered["center"][0]["rational"] = raw
        with pytest.raises(ExactCoordinateError):
            ExactDisk.from_payload(altered)
    for malformed in (None, {}, {**height.to_payload(), "extra": 1}):
        with pytest.raises(ExactCoordinateError):
            C.from_payload(malformed)


def test_exact_disk_queries_validate_types_and_keep_topology_separate_from_rounding() -> None:
    first = disk(F(0), F(0), 1000)
    for x, relation in (
        (F(1, 10000), CircleRelation.INTERIOR_OVERLAP),
        (F(1), CircleRelation.EXTERNAL_CONTACT),
        (F(10001, 10000), CircleRelation.SEPARATED),
    ):
        assert first.relation_to(disk(x, F(0), 1000)) is relation
    invalid_points: tuple[Any, ...] = ([], (), (C(F(0)),), (F(0), F(0)))
    for point in invalid_points:
        with pytest.raises(ExactCoordinateError):
            ExactDisk(point, 1000)
    with pytest.raises(ExactCoordinateError):
        first.relation_to(object())  # type: ignore[arg-type]
    with pytest.raises(ExactCoordinateError):
        certify_straight_contact(first, disk(F(0), F(0), 1001), (first,))
    with pytest.raises(ExactCoordinateError):
        certify_straight_contact(first, first, ())
