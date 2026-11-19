"""Staged point queries against filled ellipses at exact 45-degree increments."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from warhammer40k_core.geometry.milli_inch import DistancePrecisionError
from warhammer40k_core.geometry.milli_inch_polygon import (
    MAX_COORDINATE_TICKS,
    MIN_COORDINATE_TICKS,
    TickVertex,
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

    axes = oval.length_ticks**2, oval.width_ticks**2
    local_squares = _doubled_local_squares(oval, (dx, dy))
    return _round_distance_ticks(
        abs(dx) + abs(dy),
        lambda midpoint: _oval_point_below_midpoint(axes, local_squares, midpoint),
    )


def _doubled_local_squares(oval: CanonicalOval, offset: TickVertex) -> TickVertex:
    """Square the coordinates in the ellipse's local frame, in doubled tick units."""
    dx, dy = offset
    match oval.facing_degrees:
        case 0:
            return 4 * dx**2, 4 * dy**2
        case 90:
            return 4 * dy**2, 4 * dx**2
        case 45:
            return 2 * (dx + dy) ** 2, 2 * (dx - dy) ** 2
        case _:
            return 2 * (dx - dy) ** 2, 2 * (dx + dy) ** 2


def _oval_point_below_midpoint(
    squared_axes: TickVertex, local_squares: TickVertex, midpoint: int
) -> bool:
    """Compare a doubled point distance with a positive doubled midpoint exactly."""
    a, b = squared_axes
    u, v = local_squares
    target = midpoint**2
    # The squared-distance dual is t*u/(a+t) + t*v/(b+t) - t for t >= 0.
    # Its maximum equals the primal minimum. Clear the positive denominator
    # of dual(t) - target to obtain -t³ + quadratic*t² + linear*t - constant.
    quadratic = u + v - a - b - target
    linear = u * b + v * a - a * b - target * (a + b)
    constant = target * a * b

    # The cubic starts strictly negative and tends to -infinity. Only its
    # larger stationary point can attain zero on the positive half-line.
    discriminant = quadratic**2 + 3 * linear
    if discriminant <= 0 or (quadratic < 0 and discriminant <= quadratic**2):
        return True

    # At that point, 27 times the cubic equals
    # 2*discriminant**(3/2) + 2*quadratic**3 + 9*quadratic*linear - 27*constant.
    # A zero is a true midpoint tie and must not count as strictly below it.
    negative_part = 27 * constant - 2 * quadratic**3 - 9 * quadratic * linear
    return negative_part > 0 and negative_part**2 > 4 * discriminant**3


def _round_distance_ticks(upper_bound: int, below_midpoint: Callable[[int], bool]) -> int:
    # The first rounded tick whose upper midpoint is strictly above the
    # distance implements half-up rounding. The callback uses doubled ticks.
    low, high = 0, upper_bound
    while low < high:
        ticks = (low + high) // 2
        if below_midpoint(2 * ticks + 1):
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
