"""Staged point queries against filled ellipses at exact 45-degree increments."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from warhammer40k_core.geometry.milli_inch import DistancePrecisionError
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    TickVertex,
)
from warhammer40k_core.geometry.milli_inch_symbolic import UnresolvedDistanceMeasurementError
from warhammer40k_core.geometry.visibility_algebra import (
    VisibilityComputationError,
    both,
    decide,
    variable,
)


class CanonicalOvalError(DistancePrecisionError):
    """An oval or point is outside the staged canonical input domain."""


class OvalPointLocation(StrEnum):
    EXTERIOR = "exterior"
    BOUNDARY = "boundary"
    INTERIOR = "interior"


@dataclass(frozen=True, slots=True)
class CanonicalOval:
    """A tick-grid center, full axis lengths in ticks, and an exact major-axis facing."""

    center: TickVertex
    length_ticks: int
    width_ticks: int
    facing_degrees: int = 0

    def __post_init__(self) -> None:
        _validate_tick_pair(self.center)
        if (
            type(self.length_ticks) is not int
            or type(self.width_ticks) is not int
            or not 1 <= self.width_ticks <= self.length_ticks <= MAX_COORDINATE_TICKS
        ):
            raise CanonicalOvalError("Oval axes require positive ticks with width <= length.")
        if type(self.facing_degrees) is not int or self.facing_degrees % 45:
            raise CanonicalOvalError("Oval facing requires an integer multiple of 45 degrees.")
        object.__setattr__(self, "facing_degrees", self.facing_degrees % 180)


def oval_point_location(oval: CanonicalOval, point: TickVertex) -> OvalPointLocation:
    """Classify an integer tick point by exact substitution in the ellipse."""
    dx, dy = _point_offset(oval, point)
    xx, xy, yy, bound = _ellipse_coefficients(oval)
    value = xx * dx**2 + xy * dx * dy + yy * dy**2
    if value == bound:
        return OvalPointLocation.BOUNDARY
    return OvalPointLocation.INTERIOR if value < bound else OvalPointLocation.EXTERIOR


def oval_point_distance_ticks(oval: CanonicalOval, point: TickVertex) -> int:
    """Round Euclidean distance to the filled ellipse once, with half ticks rounding up."""
    dx, dy = _point_offset(oval, point)
    xx, xy, yy, bound = _ellipse_coefficients(oval)
    if xx * dx**2 + xy * dx * dy + yy * dy**2 <= bound:
        return 0

    x, y = variable("oval_x"), variable("oval_y")
    inside_oval = (x**2 * xx + x * y * xy + y**2 * yy).le(bound)
    squared_distance = (x - dx) ** 2 + (y - dy) ** 2
    # Search for the first rounded tick whose upper midpoint is strictly above
    # the distance. The ellipse contains its center, giving an integer upper bound.
    low, high = 0, abs(dx) + abs(dy)
    while low < high:
        ticks = (low + high) // 2
        within_midpoint = (squared_distance * 4).lt((2 * ticks + 1) ** 2)
        try:
            closer = decide(both(inside_oval, within_midpoint), ("oval_x", "oval_y"))
        except VisibilityComputationError as error:
            raise UnresolvedDistanceMeasurementError(
                "Exact oval point distance unresolved."
            ) from error
        if closer:
            high = ticks
        else:
            low = ticks + 1
    return low


def _ellipse_coefficients(oval: CanonicalOval) -> tuple[int, int, int, int]:
    """Return coefficients for xx*x² + xy*x*y + yy*y² <= bound in world offsets."""
    length, width = oval.length_ticks**2, oval.width_ticks**2
    bound = length * width
    if oval.facing_degrees == 0:
        return 4 * width, 0, 4 * length, bound
    if oval.facing_degrees == 90:
        return 4 * length, 0, 4 * width, bound
    # The diagonal local coordinates are (x ± y)/sqrt(2). Expanding their
    # squares clears the irrational factor and retains a Euclidean rotation.
    mixed = 4 * (width - length) if oval.facing_degrees == 45 else 4 * (length - width)
    diagonal = 2 * (length + width)
    return diagonal, mixed, diagonal, bound


def _point_offset(oval: CanonicalOval, point: TickVertex) -> TickVertex:
    if not isinstance(cast(object, oval), CanonicalOval):
        raise CanonicalOvalError("Oval point queries require a canonical oval.")
    _validate_tick_pair(point)
    return point[0] - oval.center[0], point[1] - oval.center[1]


def _validate_tick_pair(point: TickVertex) -> None:
    if (
        type(point) is not tuple
        or len(point) != 2
        or any(type(value) is not int for value in point)
    ):
        raise CanonicalOvalError("A point requires an immutable integer tick pair.")
    if any(not MIN_COORDINATE_TICKS <= value <= MAX_COORDINATE_TICKS for value in point):
        raise CanonicalOvalError("Point coordinates must fit signed 64-bit ticks.")
