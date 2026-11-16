"""Exact, opt-in distance primitives; existing gameplay does not use this policy yet.

Canonical signed coordinates and lengths use integer ticks of 0.001 inch, rounded
to nearest with exact ties away from zero. Decimal strings/Decimal/Fraction inputs
retain their exact values. Floats retain their exact *binary* ratio, not the value
suggested by their printed decimal spelling. No ambient Decimal context, float
square root or epsilon participates in a rounding decision.

These operations are dimensional: they do not quantize angles, areas, squared
lengths or dimensionless values as lengths. Full dimensions are canonicalized
before deriving radii, which may consequently be half a tick. Rounded zero distance
does not establish contact or overlap; topology requires its own exact predicates.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from decimal import Decimal, InvalidOperation
from fractions import Fraction

DISTANCE_POLICY_ID = "milli-inch-half-away-v1"
TICKS_PER_INCH = 1000
type DistanceSource = int | float | Decimal | Fraction | str


class DistancePrecisionError(ValueError):
    """The distance source is outside the precision policy's supported domain."""


class UnsupportedExactPathError(DistancePrecisionError):
    """An irrational segment needs the future symbolic path-sum implementation."""


def inches_to_ticks(value: DistanceSource) -> int:
    """Quantize a signed inch coordinate or length to nearest integer ticks."""
    return _round_ticks(_exact_value(value) * TICKS_PER_INCH)


def millimeters_to_ticks(value: DistanceSource) -> int:
    """Convert by exact 25.4 mm/inch (127/5), then round only once."""
    return _round_ticks(_exact_value(value) * Fraction(5 * TICKS_PER_INCH, 127))


def ticks_to_inches(ticks: int) -> Fraction:
    """Recover the exact inch value, without a binary-float round trip."""
    _validate_ticks(ticks)
    return Fraction(ticks, TICKS_PER_INCH)


def radius_inches_from_diameter_ticks(diameter_ticks: int) -> Fraction:
    """Derive an exact radius from a positive, already canonical full diameter.

    A source dimension that rounds to zero cannot define a physical base. Odd
    diameter ticks intentionally yield half-tick radii, not a second rounding.
    """
    _validate_ticks(diameter_ticks)
    if diameter_ticks <= 0:
        raise DistancePrecisionError("A canonical diameter must be positive.")
    return Fraction(diameter_ticks, 2 * TICKS_PER_INCH)


def squared_inches_to_ticks(squared_inches: DistanceSource) -> int:
    """Round sqrt(nonnegative squared inches) exactly, including irrational roots.

    Find the lower integer tick by integer square root; compare the squared value
    to the exact half-tick boundary to choose its nearest neighbor. This does not
    round an area or the squared length itself onto the length grid.
    """
    squared_ticks = _nonnegative_value(squared_inches) * TICKS_PER_INCH**2
    lower = math.isqrt(squared_ticks.numerator // squared_ticks.denominator)
    at_or_above_half = (
        4 * squared_ticks.numerator >= (2 * lower + 1) ** 2 * squared_ticks.denominator
    )
    return lower + int(at_or_above_half)


def rational_path_inches_to_ticks(segment_lengths: Iterable[DistanceSource]) -> int:
    """Sum exact nonnegative rational lengths, then round the whole path once.

    Inputs must be actual rational lengths, not approximated irrational geometry
    measurements. A float is its exact binary rational value, not certification
    of the computation that produced it. For squared geometric segments use
    squared_path_inches_to_ticks, which rejects unsupported irrational sums.
    """
    total = sum((_nonnegative_value(value) for value in segment_lengths), Fraction(0))
    return _round_ticks(total * TICKS_PER_INCH)


def squared_path_inches_to_ticks(squared_segment_lengths: Iterable[DistanceSource]) -> int:
    """Sum rational square roots exactly, then round once; reject irrational roots.

    Even a path containing one irrational segment is explicitly unsupported here;
    isolated derived distances can use squared_inches_to_ticks. No rounded segment
    sum or approximate float fallback stands in for the future symbolic path sum.
    """
    total = Fraction(0)
    for value in squared_segment_lengths:
        squared = _nonnegative_value(value)
        numerator = math.isqrt(squared.numerator)
        denominator = math.isqrt(squared.denominator)
        if numerator**2 != squared.numerator or denominator**2 != squared.denominator:
            raise UnsupportedExactPathError("Irrational path segments require symbolic summation.")
        total += Fraction(numerator, denominator)
    return _round_ticks(total * TICKS_PER_INCH)


def _round_ticks(value: Fraction) -> int:
    quotient, remainder = divmod(abs(value.numerator), value.denominator)
    magnitude = quotient + int(2 * remainder >= value.denominator)
    return -magnitude if value < 0 else magnitude


def _validate_ticks(value: int) -> None:
    if type(value) is not int:
        raise DistancePrecisionError("Canonical ticks must be an integer, not a boolean.")


def _nonnegative_value(value: DistanceSource) -> Fraction:
    exact = _exact_value(value)
    if exact < 0:
        raise DistancePrecisionError("A length or squared length must be nonnegative.")
    return exact


def _exact_value(value: DistanceSource) -> Fraction:
    if type(value) is int or isinstance(value, Fraction):
        return Fraction(value)
    if type(value) is float:
        if not math.isfinite(value):
            raise DistancePrecisionError("A distance source must be finite.")
        return Fraction.from_float(value)
    if isinstance(value, str):
        try:
            value = Decimal(value)
        except InvalidOperation as exc:
            raise DistancePrecisionError(
                "A distance string must contain a decimal number."
            ) from exc
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise DistancePrecisionError("A distance source must be finite.")
        return Fraction(value)
    raise DistancePrecisionError("A distance source must be int, float, Decimal, Fraction or str.")
