"""Inactive milli-inch measurement boundaries for exact real-polynomial consumers.

Lengths are nonnegative; squared segment sources are square inches. No predicate
here defines contact, intersection or overlap, and no gameplay caller opts in.
"""

from __future__ import annotations

import importlib
import math
import time
from collections.abc import Iterable
from fractions import Fraction
from typing import Literal, Protocol, cast

from warhammer40k_core.geometry.milli_inch import (
    DistancePrecisionError,
    DistanceSource,
    inches_to_ticks,
    squared_inches_to_ticks,
)
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    negate,
    variable,
)

type DistanceRelation = Literal["lt", "le", "gt", "ge"]


class UnresolvedDistanceMeasurementError(DistancePrecisionError):
    """The bounded exact calculation did not certify a measurement."""


def rounded_length_constraint(
    length: RealTerm, threshold_ticks: int, relation: DistanceRelation
) -> Formula:
    """Encode Q(length) relation threshold, including the nonnegative domain.

    The upper midpoint is excluded for <= and included for >. The lower
    midpoint is excluded for < and included for >=. In particular Q(d) < 0 is
    false, Q(d) >= 0 is true for d >= 0, and Q(d) == 0 never establishes contact.
    The caller owns declarations and certificates for any free length variables.
    """
    if type(length) is not RealTerm:
        raise DistancePrecisionError("A symbolic length must be a RealTerm.")
    if type(threshold_ticks) is not int or threshold_ticks < 0:
        raise DistancePrecisionError("A distance threshold must be nonnegative integer ticks.")
    if relation not in ("lt", "le", "gt", "ge"):
        raise DistancePrecisionError("A distance relation must be lt, le, gt or ge.")
    offset = 1 if relation in ("le", "gt") else -1
    boundary = Fraction(2 * threshold_ticks + offset, 2000)
    comparison = length.lt(boundary) if relation in ("lt", "le") else length.ge(boundary)
    return both(length.ge(0), comparison)


def symbolic_squared_path_inches_to_ticks(
    squared_segment_lengths: Iterable[DistanceSource], *, timeout_ms: int = 10_000
) -> int:
    """Certify nearest ticks of the entire sum of nonnegative rational square roots.

    Each irrational root has exact nonnegative dyadic enclosures certified by
    integer square root. Refine the enclosures
    until the *whole* sum lies in one half-tick bin, then certify that bin with
    a bounded exact solver. No individual segment is rounded into the result.
    Rational-only inputs use the exact rational total, including midpoint ties.
    An unresolved check or expired shared deadline raises a typed error; there is
    no approximate answer or change to the retained rational-only path API.
    """
    if type(timeout_ms) is not int or timeout_ms <= 0:
        raise DistancePrecisionError("Measurement timeout_ms must be a positive integer.")
    deadline = time.monotonic() + timeout_ms / 1000
    rational_total = Fraction(0)
    names: list[str] = []
    roots: list[RealTerm] = []
    squared_roots: list[Fraction] = []
    for source in squared_segment_lengths:
        _remaining_ms(deadline)
        # The public measurement decoder validates exact source semantics first.
        squared_inches_to_ticks(source)
        squared = Fraction(source)
        numerator = math.isqrt(squared.numerator)
        denominator = math.isqrt(squared.denominator)
        if numerator**2 == squared.numerator and denominator**2 == squared.denominator:
            rational_total += Fraction(numerator, denominator)
        else:
            name = f"path_root_{len(names)}"
            root = variable(name)
            names.append(name)
            roots.append(root)
            squared_roots.append(squared)
    if not roots:
        _remaining_ms(deadline)
        return inches_to_ticks(rational_total)
    total = RealTerm.number(rational_total)
    for root in roots:
        total += root
    precision = 16
    while True:
        _remaining_ms(deadline)
        scale = 1 << precision
        lower = upper = rational_total
        enclosures: list[Formula] = []
        for root, squared in zip(roots, squared_roots, strict=True):
            integer = math.isqrt(squared.numerator * scale**2 // squared.denominator)
            low, high = Fraction(integer, scale), Fraction(integer + 1, scale)
            # These roots are irrational, so both rational enclosure endpoints
            # are strict. The inequalities follow exactly from the integer sqrt.
            if not (low >= 0 and low * low < squared < high * high):
                raise UnresolvedDistanceMeasurementError("Exact root enclosure certificate failed.")
            enclosures.extend((root.gt(low), root.lt(high)))
            lower += low
            upper += high
        ticks = inches_to_ticks(lower)
        if upper <= Fraction(2 * ticks + 1, 2000):
            break
        precision *= 2
    bin_constraint = both(
        rounded_length_constraint(total, ticks, "ge"),
        rounded_length_constraint(total, ticks, "le"),
    )
    # Integer arithmetic already certifies every enclosure. Prove the bin for
    # every real value in those enclosures, so it holds for the actual roots.
    # Redundant quadratic equations would turn this linear implication into an
    # unnecessarily difficult algebraic elimination problem.
    counterexample = both(*enclosures, negate(bin_constraint))
    if _decide(counterexample, tuple(names), _remaining_ms(deadline)):
        raise UnresolvedDistanceMeasurementError("Exact distance bin certification failed.")
    _remaining_ms(deadline)
    return ticks


def _remaining_ms(deadline: float) -> int:
    remaining = math.floor((deadline - time.monotonic()) * 1000)
    if remaining <= 0:
        raise UnresolvedDistanceMeasurementError("Exact distance measurement deadline expired.")
    return remaining


class _Solver(Protocol):
    def set(self, *, timeout: int) -> None: ...
    def from_string(self, script: str) -> None: ...
    def check(self) -> object: ...
    def reason_unknown(self) -> str: ...


class _Tactic(Protocol):
    def solver(self) -> _Solver: ...


class _SolverModule(Protocol):
    def Context(self) -> object: ...
    def Tactic(self, name: str, *, ctx: object) -> _Tactic: ...


def _decide(formula: Formula, names: tuple[str, ...], timeout_ms: int) -> bool:
    module = cast(_SolverModule, importlib.import_module("z3"))
    context = module.Context()
    solver = module.Tactic("qflra", ctx=context).solver()
    solver.set(timeout=timeout_ms)
    declarations = "\n".join(f"(declare-const {name} Real)" for name in names)
    solver.from_string(f"(set-logic QF_LRA)\n{declarations}\n(assert {formula.text})")
    result = str(solver.check())
    if result == "sat":
        return True
    if result == "unsat":
        return False
    raise UnresolvedDistanceMeasurementError(
        f"Exact distance measurement unresolved: {solver.reason_unknown()}"
    )
