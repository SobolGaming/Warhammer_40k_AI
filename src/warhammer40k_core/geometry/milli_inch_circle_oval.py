"""Staged exact queries between filled canonical disks and ellipses."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.geometry.milli_inch_circle import (
    CanonicalCircle,
    CanonicalCircleError,
    CircleRelation,
)
from warhammer40k_core.geometry.milli_inch_oval import (
    CanonicalOval,
    _compare_oval_point_distance,  # pyright: ignore[reportPrivateUsage]
    _doubled_local_squares,  # pyright: ignore[reportPrivateUsage]
    _point_offset,  # pyright: ignore[reportPrivateUsage]
    _round_distance_ticks,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.geometry.milli_inch_polygon import TickVertex


def circle_oval_relation(circle: CanonicalCircle, oval: CanonicalOval) -> CircleRelation:
    """Classify separation, external tangency, or shared interior exactly."""
    _, axes, local_squares = _circle_center_distance_terms(circle, oval)
    # The diameter is exactly the radius in doubled tick units.
    comparison = _compare_oval_point_distance(axes, local_squares, circle.diameter_ticks)
    if comparison > 0:
        return CircleRelation.SEPARATED
    if comparison == 0:
        return CircleRelation.EXTERNAL_CONTACT
    return CircleRelation.INTERIOR_OVERLAP


def circle_oval_distance_ticks(circle: CanonicalCircle, oval: CanonicalOval) -> int:
    """Round the nonnegative Euclidean surface gap once, with half ticks rounding up."""
    upper_bound, axes, local_squares = _circle_center_distance_terms(circle, oval)
    return _round_distance_ticks(
        upper_bound,
        lambda midpoint: (
            _compare_oval_point_distance(axes, local_squares, circle.diameter_ticks + midpoint) < 0
        ),
    )


def _circle_center_distance_terms(
    circle: CanonicalCircle, oval: CanonicalOval
) -> tuple[int, TickVertex, TickVertex]:
    if not isinstance(cast(object, circle), CanonicalCircle):
        raise CanonicalCircleError("Circle-oval queries require a canonical circle.")
    offset = _point_offset(oval, circle.center)
    dx, dy = offset
    axes = oval.length_ticks**2, oval.width_ticks**2
    return abs(dx) + abs(dy), axes, _doubled_local_squares(oval, offset)
