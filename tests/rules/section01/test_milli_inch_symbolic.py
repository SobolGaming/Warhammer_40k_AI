"""Inactive exact path sums and shared rule-distance bins, independent of topology."""

from decimal import Decimal
from fractions import Fraction
from typing import cast

import pytest

from warhammer40k_core.geometry.milli_inch import (
    DistancePrecisionError,
    DistanceSource,
    UnsupportedExactPathError,
    squared_inches_to_ticks,
    squared_path_inches_to_ticks,
)
from warhammer40k_core.geometry.milli_inch_symbolic import (
    DistanceRelation,
    UnresolvedDistanceMeasurementError,
    rounded_length_constraint,
    symbolic_squared_path_inches_to_ticks,
)
from warhammer40k_core.geometry.visibility_algebra import RealTerm, both, decide, variable


def test_symbolic_path_measures_complete_mixed_sum_once() -> None:
    assert symbolic_squared_path_inches_to_ticks([2, 9, Fraction(1, 2)]) == 5121
    assert symbolic_squared_path_inches_to_ticks([2] * 3) == 4243
    assert sum(squared_inches_to_ticks(2) for _ in range(3)) == 4242
    assert symbolic_squared_path_inches_to_ticks([]) == 0
    assert symbolic_squared_path_inches_to_ticks([0, 9, 16]) == 7000
    assert symbolic_squared_path_inches_to_ticks([Fraction(1, 16_000_000)] * 2) == 1
    assert symbolic_squared_path_inches_to_ticks(["2", 9.0, Fraction(1, 2)]) == 5121
    assert symbolic_squared_path_inches_to_ticks([Decimal("1.00100025")]) == 1001
    assert symbolic_squared_path_inches_to_ticks(["1.00100025"]) == 1001
    assert Fraction.from_float(1.00100025) < Fraction("1.00100025")
    assert symbolic_squared_path_inches_to_ticks([1.00100025]) == 1000
    # Preserve the retained Decimal source grammar, including accepted underscores.
    for source, expected in (("1__0", 3162), ("_1", 1000), ("1_.0", 1000)):
        assert squared_inches_to_ticks(source) == expected
        assert symbolic_squared_path_inches_to_ticks([source]) == expected
    # A short ordinary path formerly exhausted blind root-sum search. Independent
    # integer-root enclosures place its complete length strictly in the 6714 bin.
    assert (
        symbolic_squared_path_inches_to_ticks(
            [
                Fraction(532, 1095),
                Fraction(227, 137),
                Fraction(2614, 355),
                Fraction(4363, 3455),
                Fraction(3595, 4509),
            ]
        )
        == 6714
    )
    with pytest.raises(UnsupportedExactPathError):
        squared_path_inches_to_ticks([2])


def test_symbolic_path_subdivision_and_segment_order_preserve_total() -> None:
    original = [2, 3, 9]
    split = [Fraction(2, 9)] * 3 + [Fraction(3, 4)] * 2 + [1] * 3
    expected = symbolic_squared_path_inches_to_ticks(original)
    assert expected == 6146
    assert symbolic_squared_path_inches_to_ticks(split) == expected
    assert symbolic_squared_path_inches_to_ticks(reversed(split)) == expected


def test_symbolic_path_exact_ties_and_irrational_neighbors_at_any_scale() -> None:
    for tick in (0, 1, 1000, 10**30):
        midpoint = Fraction(2 * tick + 1, 2000)
        epsilon = Fraction(1, 10**70)
        assert symbolic_squared_path_inches_to_ticks([midpoint**2]) == tick + 1
        assert symbolic_squared_path_inches_to_ticks([midpoint**2 - epsilon]) == tick
        assert symbolic_squared_path_inches_to_ticks([midpoint**2 + epsilon]) == tick + 1
    # A tiny irrational addend crosses a tie; it cannot be rounded away first.
    assert symbolic_squared_path_inches_to_ticks([Fraction(1, 4_000_000), Fraction(2, 10**80)]) == 1


def test_symbolic_length_bins_match_all_four_integer_relations() -> None:
    relations: tuple[DistanceRelation, ...] = ("lt", "le", "gt", "ge")
    for threshold in (0, 1, 1000, 10**30):
        boundaries = (Fraction(2 * threshold - 1, 2000), Fraction(2 * threshold + 1, 2000))
        for boundary in boundaries:
            for offset in (-Fraction(1, 10**80), Fraction(0), Fraction(1, 10**80)):
                length = boundary + offset
                if length < 0:
                    continue
                ticks = squared_inches_to_ticks(length**2)
                expected = (
                    ticks < threshold,
                    ticks <= threshold,
                    ticks > threshold,
                    ticks >= threshold,
                )
                for relation, result in zip(relations, expected, strict=True):
                    assert (
                        decide(
                            rounded_length_constraint(RealTerm.number(length), threshold, relation)
                        )
                        is result
                    )
    symbolic_length = variable("measured_length")
    assert decide(
        both(
            symbolic_length.eq(Fraction(2001, 2000)),
            rounded_length_constraint(symbolic_length, 1000, "gt"),
        ),
        ("measured_length",),
    )
    for relation in relations:
        assert not decide(rounded_length_constraint(RealTerm.number(-1), 0, relation))
    # A nonzero positive gap in the zero bin remains nonzero: no contact claim.
    assert decide(rounded_length_constraint(RealTerm.number(Fraction(1, 10000)), 0, "le"))


def test_symbolic_measurement_rejects_invalid_sources_and_contracts() -> None:
    for invalid in (-1, True, "NaN", float("inf"), object()):
        with pytest.raises(DistancePrecisionError):
            symbolic_squared_path_inches_to_ticks([cast(DistanceSource, invalid)])
    for invalid in (0, -1, True, 1.5):
        with pytest.raises(DistancePrecisionError, match="timeout"):
            symbolic_squared_path_inches_to_ticks([], timeout_ms=cast(int, invalid))
    for invalid in (-1, True, "1000", 1000.0):
        with pytest.raises(DistancePrecisionError, match="threshold"):
            rounded_length_constraint(RealTerm.number(1), cast(int, invalid), "le")
    with pytest.raises(DistancePrecisionError, match="relation"):
        rounded_length_constraint(RealTerm.number(1), 1000, cast(DistanceRelation, "equal"))
    with pytest.raises(DistancePrecisionError, match="RealTerm"):
        rounded_length_constraint(cast(RealTerm, 1), 1000, "le")


@pytest.mark.stubbed
def test_symbolic_measurement_deadline_fails_without_approximate_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    times = iter((0.0, 11.0))
    monkeypatch.setattr(
        "warhammer40k_core.geometry.milli_inch_symbolic.time.monotonic", lambda: next(times)
    )
    with pytest.raises(UnresolvedDistanceMeasurementError, match="deadline"):
        symbolic_squared_path_inches_to_ticks([2])


@pytest.mark.stubbed
def test_symbolic_measurement_unknown_is_typed_and_not_a_distance(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    solver_result = "unknown"

    class UnresolvedSolver:
        def set(self, *, timeout: int) -> None:
            assert timeout > 0

        def from_string(self, script: str) -> None:
            assert "QF_LRA" in script

        def check(self) -> object:
            return solver_result

        def reason_unknown(self) -> str:
            return "test resource exhaustion"

    class DummyTactic:
        def solver(self) -> UnresolvedSolver:
            return UnresolvedSolver()

    class Module:
        def Context(self) -> object:
            return object()

        def Tactic(self, name: str, *, ctx: object) -> DummyTactic:
            assert name == "qflra"
            return DummyTactic()

    def import_module(name: str) -> Module:
        assert name == "z3"
        return Module()

    monkeypatch.setattr(
        "warhammer40k_core.geometry.milli_inch_symbolic.importlib.import_module", import_module
    )
    with pytest.raises(UnresolvedDistanceMeasurementError, match="test resource exhaustion"):
        symbolic_squared_path_inches_to_ticks([2])
    solver_result = "sat"
    with pytest.raises(UnresolvedDistanceMeasurementError, match="bin certification failed"):
        symbolic_squared_path_inches_to_ticks([2])
