"""Exact opt-in length precision; this foundation does not activate gameplay."""

from decimal import ROUND_DOWN, ROUND_UP, Decimal, InvalidOperation, localcontext
from fractions import Fraction
from math import nextafter
from typing import cast

import pytest

from warhammer40k_core.geometry.milli_inch import (
    DISTANCE_POLICY_ID,
    DistancePrecisionError,
    DistanceSource,
    UnsupportedExactPathError,
    inches_to_ticks,
    millimeters_to_ticks,
    radius_inches_from_diameter_ticks,
    rational_path_inches_to_ticks,
    squared_inches_to_ticks,
    squared_path_inches_to_ticks,
    ticks_to_inches,
)


def test_milli_inch_signed_rounding_ties_and_exact_neighbors() -> None:
    assert DISTANCE_POLICY_ID == "milli-inch-half-away-v1"
    for lower in (0, 1, 2, 999, 1000, 10**30):
        tie = Fraction(2 * lower + 1, 2000)
        epsilon = Fraction(1, 10**60)
        for sign in (-1, 1):
            assert inches_to_ticks(sign * (tie - epsilon)) == sign * lower
            assert inches_to_ticks(sign * tie) == sign * (lower + 1)
            assert inches_to_ticks(sign * (tie + epsilon)) == sign * (lower + 1)
    assert inches_to_ticks("-0") == 0
    assert inches_to_ticks(-0.0) == 0


def test_milli_inch_exact_sources_and_binary_float_semantics_are_distinct() -> None:
    for source in ("1.0005", Decimal("1.0005"), Fraction(2001, 2000)):
        assert inches_to_ticks(source) == 1001
    # The binary float is below the exact decimal midpoint, despite its spelling.
    assert Fraction.from_float(1.0005) < Fraction(2001, 2000)
    assert inches_to_ticks(1.0005) == 1000
    assert inches_to_ticks(-1.0005) == -1000
    assert inches_to_ticks(nextafter(1.0005, float("inf"))) == 1001
    assert inches_to_ticks(3) == 3000
    assert inches_to_ticks("1e-3") == 1


def test_milli_inch_decimal_context_cannot_change_results() -> None:
    for rounding in (ROUND_DOWN, ROUND_UP):
        with localcontext() as context:
            context.prec = 1
            context.rounding = rounding
            context.traps[InvalidOperation] = False
            assert inches_to_ticks(Decimal("12345.6785")) == 12345679
            assert millimeters_to_ticks("25.4127") == 1001
            with pytest.raises(DistancePrecisionError, match="finite"):
                inches_to_ticks("malformed")


@pytest.mark.parametrize(
    "source",
    [
        True,
        False,
        None,
        [],
        object(),
        float("nan"),
        float("inf"),
        -float("inf"),
        Decimal("NaN"),
        Decimal("sNaN"),
        Decimal("Infinity"),
        "NaN",
        "Infinity",
        "1/2",
        "",
    ],
)
def test_milli_inch_rejects_invalid_sources(source: object) -> None:
    with pytest.raises(DistancePrecisionError):
        inches_to_ticks(cast(DistanceSource, source))


def test_milli_inch_exact_mm_conversion_precedes_single_rounding() -> None:
    assert millimeters_to_ticks("25.4") == 1000
    assert millimeters_to_ticks("32") == 1260
    assert millimeters_to_ticks("0.0127") == 1
    assert millimeters_to_ticks("-0.0127") == -1
    assert millimeters_to_ticks("0.012699999999999999999") == 0
    assert millimeters_to_ticks("0.012700000000000000001") == 1
    assert millimeters_to_ticks(Fraction(127, 10)) == 500
    assert millimeters_to_ticks(Decimal("25.4127")) == 1001


def test_milli_inch_canonical_dimensions_derive_exact_half_tick_radii() -> None:
    diameter = inches_to_ticks("1.001")
    radius = radius_inches_from_diameter_ticks(diameter)
    assert radius == Fraction(1001, 2000)
    assert radius * 2 == ticks_to_inches(diameter)
    assert radius * 2 != 2 * ticks_to_inches(inches_to_ticks(radius))
    for ticks in (-(10**30), -1, 0, 1, 10**30):
        assert inches_to_ticks(ticks_to_inches(ticks)) == ticks
    for invalid in (True, 1.0, "1"):
        with pytest.raises(DistancePrecisionError, match="integer"):
            ticks_to_inches(cast(int, invalid))
        with pytest.raises(DistancePrecisionError, match="integer"):
            radius_inches_from_diameter_ticks(cast(int, invalid))
    for collapsed in (0, -1):
        with pytest.raises(DistancePrecisionError, match="positive"):
            radius_inches_from_diameter_ticks(collapsed)


def test_milli_inch_squared_measurements_compare_exact_midpoints() -> None:
    for lower in (0, 1, 999, 1000, 10**30):
        squared_tie = Fraction(2 * lower + 1, 2000) ** 2
        epsilon = Fraction(1, 10**90)
        assert squared_inches_to_ticks(squared_tie - epsilon) == lower
        assert squared_inches_to_ticks(squared_tie) == lower + 1
        assert squared_inches_to_ticks(squared_tie + epsilon) == lower + 1
    assert squared_inches_to_ticks(0) == 0
    assert squared_inches_to_ticks(2) == 1414
    assert squared_inches_to_ticks(25) == 5000
    # Square inches are not themselves quantized with the length quantum.
    assert squared_inches_to_ticks("0.00000025") == 1
    with pytest.raises(DistancePrecisionError, match="nonnegative"):
        squared_inches_to_ticks(Fraction(-1, 10**90))


def test_milli_inch_threshold_strictness_uses_rounded_length_without_epsilon() -> None:
    threshold = inches_to_ticks(1)
    for raw, expected in (
        ("0.999499999", 999),
        ("0.9995", 1000),
        ("1", 1000),
        ("1.000499999", 1000),
        ("1.0005", 1001),
    ):
        measured = squared_inches_to_ticks(Fraction(raw) ** 2)
        assert measured == expected
        assert (measured <= threshold) is (expected <= 1000)
        assert (measured < threshold) is (expected < 1000)
        assert (measured >= threshold) is (expected >= 1000)
        assert (measured > threshold) is (expected > 1000)


def test_milli_inch_zero_rounded_gap_is_not_a_topology_predicate() -> None:
    radius = radius_inches_from_diameter_ticks(1001)
    for signed_gap in (Fraction(-1, 10000), Fraction(0), Fraction(1, 10000)):
        centers = 2 * radius + signed_gap
        raw_gap = centers - 2 * radius
        assert inches_to_ticks(raw_gap) == 0
        assert (centers == 2 * radius) is (signed_gap == 0)
        assert (centers < 2 * radius) is (signed_gap < 0)


def test_milli_inch_path_rounds_total_once_and_is_partition_invariant() -> None:
    segments = [Fraction(3, 5000)] * 10
    assert sum(inches_to_ticks(length) for length in segments) == 10
    assert rational_path_inches_to_ticks(iter(segments)) == 6
    assert rational_path_inches_to_ticks([sum(segments)]) == 6
    assert squared_path_inches_to_ticks(length**2 for length in segments) == 6
    assert rational_path_inches_to_ticks([]) == squared_path_inches_to_ticks([]) == 0
    assert rational_path_inches_to_ticks(["0.00025", "0.00025"]) == 1
    assert squared_path_inches_to_ticks([Fraction(1, 16_000_000)] * 2) == 1
    assert squared_path_inches_to_ticks([9, 16]) == 7000


def test_milli_inch_path_rejects_negative_and_unsupported_irrational_segments() -> None:
    for source in (-1, True, "NaN"):
        with pytest.raises(DistancePrecisionError):
            rational_path_inches_to_ticks([0, source])
        with pytest.raises(DistancePrecisionError):
            squared_path_inches_to_ticks([0, source])
    for squared in (2, Fraction(1, 2), Fraction(2, 9)):
        with pytest.raises(UnsupportedExactPathError, match="symbolic"):
            squared_path_inches_to_ticks([1, squared])
