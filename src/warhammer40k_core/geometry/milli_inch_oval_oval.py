"""Staged exact topology between two filled canonical ovals."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_oval import (
    CanonicalOval,
    CanonicalOvalError,
    _ellipse_coefficients,  # pyright: ignore[reportPrivateUsage]
)


def oval_oval_relation(first: CanonicalOval, second: CanonicalOval) -> CircleRelation:
    """Classify separation, external contact, or shared interior at canonical facings."""
    if not isinstance(cast(object, first), CanonicalOval) or not isinstance(
        cast(object, second), CanonicalOval
    ):
        raise CanonicalOvalError("Oval pair queries require canonical ovals.")

    axx, axy, ayy, a_bound = _ellipse_coefficients(first)
    bxx, bxy, byy, b_bound = _ellipse_coefficients(second)
    dx = second.center[0] - first.center[0]
    dy = second.center[1] - first.center[1]
    a_offset = axx * dx**2 + axy * dx * dy + ayy * dy**2
    b_offset = bxx * dx**2 + bxy * dx * dy + byy * dy**2

    # A and B are the symmetric quadratic matrices. Their off-diagonal entries
    # are half the (even) mixed coefficients. Expand det(A + t B).
    a_mixed, b_mixed = axy // 2, bxy // 2
    a_det = axx * ayy - a_mixed**2
    b_det = bxx * byy - b_mixed**2
    cross = axx * byy + ayy * bxx - 2 * a_mixed * b_mixed

    # Negate the conic-pencil determinant so both end coefficients are positive.
    cubic = b_bound * b_det
    quadratic = b_bound * cross + (a_bound - a_offset) * b_det
    linear = a_bound * cross + (b_bound - b_offset) * a_det
    constant = a_bound * a_det
    if quadratic >= 0 and linear >= 0:
        return CircleRelation.INTERIOR_OVERLAP

    # With a negative middle coefficient, three real roots counted with
    # multiplicity must consist of one negative and two positive roots.
    discriminant = (
        quadratic**2 * linear**2
        - 4 * cubic * linear**3
        - 4 * quadratic**3 * constant
        - 27 * cubic**2 * constant**2
        + 18 * cubic * quadratic * linear * constant
    )
    if discriminant > 0:
        return CircleRelation.SEPARATED
    if discriminant == 0:
        return CircleRelation.EXTERNAL_CONTACT
    return CircleRelation.INTERIOR_OVERLAP
