from __future__ import annotations

from typing import Any

import pytest

from warhammer40k_core.geometry.milli_inch_oval import (
    CanonicalOval,
    CanonicalOvalError,
    OvalPointLocation,
    oval_point_distance_ticks,
    oval_point_location,
)


def test_oval_point_location_handles_axes_and_true_diagonal_rotations() -> None:
    oval = CanonicalOval((10, -20), 10, 6)
    assert oval_point_location(oval, (10, -20)) is OvalPointLocation.INTERIOR
    assert oval_point_location(oval, (15, -20)) is OvalPointLocation.BOUNDARY
    assert oval_point_location(oval, (10, -15)) is OvalPointLocation.EXTERIOR
    quarter_turn = CanonicalOval(oval.center, 10, 6, 90)
    assert oval_point_location(quarter_turn, (10, -15)) is OvalPointLocation.BOUNDARY
    diagonal = CanonicalOval(oval.center, 10, 6, 45)
    assert oval_point_location(diagonal, (14, -19)) is OvalPointLocation.BOUNDARY
    assert oval_point_location(diagonal, (14, -21)) is OvalPointLocation.EXTERIOR
    reflected = CanonicalOval(oval.center, 10, 6, -45)
    assert reflected.facing_degrees == 135
    assert oval_point_location(reflected, (14, -21)) is OvalPointLocation.BOUNDARY
    assert oval_point_location(reflected, (14, -19)) is OvalPointLocation.EXTERIOR


def test_oval_distance_rounds_once_and_keeps_topology_separate() -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    assert oval_point_distance_ticks(oval, (0, 0)) == 0
    assert oval_point_distance_ticks(oval, (5, 0)) == 0
    assert oval_point_location(oval, (5, 1)) is OvalPointLocation.EXTERIOR
    # The boundary point (24/5, 21/25) is less than half a tick from (5, 1).
    assert oval_point_distance_ticks(oval, (5, 1)) == 0
    odd = CanonicalOval((0, 0), 11, 7, 90)
    assert oval_point_location(odd, (0, 6)) is OvalPointLocation.EXTERIOR
    assert oval_point_distance_ticks(odd, (0, 6)) == 1


def test_off_axis_oval_distance_uses_the_euclidean_normal() -> None:
    axis_aligned = CanonicalOval((0, 0), 50, 30)
    # (15, 12) is on the boundary and (9, 20) is an outward normal there.
    assert oval_point_distance_ticks(axis_aligned, (24, 32)) == 22  # sqrt(481)
    diagonal = CanonicalOval((0, 0), 10, 6, 45)
    reflected = CanonicalOval((0, 0), 10, 6, 135)
    # The outward normal at (4, 1) on the diagonal oval is (4, -1).
    assert oval_point_distance_ticks(diagonal, (8, 0)) == 4  # sqrt(17)
    assert oval_point_distance_ticks(reflected, (8, 0)) == 4


def test_oval_accepts_equal_axes_and_distances_beyond_the_coordinate_bound() -> None:
    disk = CanonicalOval((0, 0), 9, 9, 45)
    assert oval_point_distance_ticks(disk, (3, 4)) == 1
    minimum, maximum = -(2**63), 2**63 - 1
    oval = CanonicalOval((minimum, 0), 2, 1)
    assert oval_point_distance_ticks(oval, (maximum, 0)) == maximum - minimum - 1


@pytest.mark.parametrize(
    ("center", "length", "width", "facing"),
    [
        ([0, 0], 10, 6, 0),
        ((False, 0), 10, 6, 0),
        ((2**63, 0), 10, 6, 0),
        ((0, 0), 10, 0, 0),
        ((0, 0), 6, 10, 0),
        ((0, 0), 2**63, 6, 0),
        ((0, 0), 10.0, 6, 0),
        ((0, 0), 10, True, 0),
        ((0, 0), 10, 6, 30),
        ((0, 0), 10, 6, 45.0),
        ((0, 0), 10, 6, False),
    ],
)
def test_oval_rejects_noncanonical_inputs(
    center: Any, length: Any, width: Any, facing: Any
) -> None:
    with pytest.raises(CanonicalOvalError):
        CanonicalOval(center, length, width, facing)


@pytest.mark.parametrize("point", [[0, 0], (0,), (0, 0.0), (True, 0), (0, -(2**63) - 1)])
def test_oval_queries_reject_noncanonical_points(point: Any) -> None:
    oval = CanonicalOval((0, 0), 10, 6)
    with pytest.raises(CanonicalOvalError):
        oval_point_location(oval, point)
    with pytest.raises(CanonicalOvalError):
        oval_point_distance_ticks(oval, point)


def test_oval_queries_require_a_canonical_oval() -> None:
    value: Any = object()
    with pytest.raises(CanonicalOvalError):
        oval_point_location(value, (0, 0))
    with pytest.raises(CanonicalOvalError):
        oval_point_distance_ticks(value, (0, 0))
