"""Typed rational-polynomial construction and a complete NRA decision boundary.

Only real arithmetic is emitted. Z3's nlqsat procedure decides quantified real
polynomials; the generic SMT quantifier heuristics are deliberately not used.
The solver is the reference authority after sufficient geometric certificates.
An unsuccessful calculation raises a domain error; it never becomes visibility.
"""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from fractions import Fraction
from functools import cache
from typing import Protocol, cast

from warhammer40k_core.geometry.pose import GeometryError


class VisibilityComputationError(GeometryError):
    """The exact visibility calculation did not produce a proved result."""


def _number(value: Fraction) -> str:
    numerator = str(value.numerator) if value >= 0 else f"(- {-value.numerator})"
    return numerator if value.denominator == 1 else f"(/ {numerator} {value.denominator})"


@dataclass(frozen=True, slots=True)
class RealTerm:
    text: str
    constant: Fraction | None = None

    @classmethod
    def number(cls, value: Fraction | int) -> RealTerm:
        rational = Fraction(value)
        return cls(_number(rational), rational)

    def __add__(self, other: RealTerm | Fraction | int) -> RealTerm:
        value = term(other)
        if self.constant is not None and value.constant is not None:
            return RealTerm.number(self.constant + value.constant)
        if self.constant == 0:
            return value
        if value.constant == 0:
            return self
        return RealTerm(f"(+ {self.text} {value.text})")

    def __sub__(self, other: RealTerm | Fraction | int) -> RealTerm:
        return self + (-term(other))

    def __neg__(self) -> RealTerm:
        if self.constant is not None:
            return RealTerm.number(-self.constant)
        return RealTerm(f"(- {self.text})")

    def __mul__(self, other: RealTerm | Fraction | int) -> RealTerm:
        value = term(other)
        if self.constant is not None and value.constant is not None:
            return RealTerm.number(self.constant * value.constant)
        if self.constant == 0 or value.constant == 0:
            return RealTerm.number(0)
        if self.constant == 1:
            return value
        if value.constant == 1:
            return self
        return RealTerm(f"(* {self.text} {value.text})")

    def __pow__(self, exponent: int) -> RealTerm:
        if exponent < 0:
            raise VisibilityComputationError("Visibility algebra requires polynomial powers.")
        result = RealTerm.number(1)
        for _ in range(exponent):
            result = result * self
        return result

    def eq(self, other: RealTerm | Fraction | int) -> Formula:
        return _comparison("=", self, term(other))

    def gt(self, other: RealTerm | Fraction | int) -> Formula:
        return _comparison(">", self, term(other))

    def ge(self, other: RealTerm | Fraction | int) -> Formula:
        return _comparison(">=", self, term(other))

    def lt(self, other: RealTerm | Fraction | int) -> Formula:
        return term(other).gt(self)

    def le(self, other: RealTerm | Fraction | int) -> Formula:
        return term(other).ge(self)


def term(value: RealTerm | Fraction | int) -> RealTerm:
    return value if isinstance(value, RealTerm) else RealTerm.number(value)


def variable(name: str) -> RealTerm:
    if not name.isidentifier() or not name.isascii():
        raise VisibilityComputationError("Visibility variable must be an ASCII identifier.")
    return RealTerm(name)


@dataclass(frozen=True, slots=True)
class Formula:
    text: str


TRUE = Formula("true")
FALSE = Formula("false")


def _comparison(operator: str, first: RealTerm, second: RealTerm) -> Formula:
    if first.constant is not None and second.constant is not None:
        if operator == "=":
            result = first.constant == second.constant
        elif operator == ">":
            result = first.constant > second.constant
        elif operator == ">=":
            result = first.constant >= second.constant
        else:
            raise VisibilityComputationError("Unsupported visibility comparison.")
        return TRUE if result else FALSE
    if first.text == second.text:
        return FALSE if operator == ">" else TRUE
    return Formula(f"({operator} {first.text} {second.text})")


def both(*formulas: Formula) -> Formula:
    if FALSE in formulas:
        return FALSE
    texts = tuple(dict.fromkeys(formula.text for formula in formulas if formula != TRUE))
    return (
        TRUE if not texts else Formula(texts[0] if len(texts) == 1 else f"(and {' '.join(texts)})")
    )


def either(*formulas: Formula) -> Formula:
    if TRUE in formulas:
        return TRUE
    texts = tuple(dict.fromkeys(formula.text for formula in formulas if formula != FALSE))
    return (
        FALSE if not texts else Formula(texts[0] if len(texts) == 1 else f"(or {' '.join(texts)})")
    )


def negate(formula: Formula) -> Formula:
    if formula == TRUE:
        return FALSE
    if formula == FALSE:
        return TRUE
    return Formula(f"(not {formula.text})")


def implies(premise: Formula, conclusion: Formula) -> Formula:
    return either(negate(premise), conclusion)


def quantified(kind: str, variables: tuple[str, ...], formula: Formula) -> Formula:
    if kind not in {"exists", "forall"}:
        raise VisibilityComputationError("Unsupported visibility quantifier.")
    if not variables or formula in {TRUE, FALSE}:
        return formula
    declarations = " ".join(f"({variable(name).text} Real)" for name in variables)
    return Formula(f"({kind} ({declarations}) {formula.text})")


class _Solver(Protocol):
    def from_string(self, script: str) -> None: ...
    def check(self) -> object: ...
    def reason_unknown(self) -> str: ...


class _Tactic(Protocol):
    def solver(self) -> _Solver: ...


class _SolverModule(Protocol):
    def Context(self) -> object: ...
    def Tactic(self, name: str, *, ctx: object) -> _Tactic: ...


@cache
def _solver_module() -> _SolverModule:
    return cast(_SolverModule, importlib.import_module("z3"))


def decide(formula: Formula, free_variables: tuple[str, ...] = ()) -> bool:
    if formula in {TRUE, FALSE}:
        return formula == TRUE
    module = _solver_module()
    context = module.Context()
    tactic = "nlqsat" if "(forall " in formula.text or "(exists " in formula.text else "qfnra-nlsat"
    solver = module.Tactic(tactic, ctx=context).solver()
    declarations = "\n".join(
        f"(declare-const {variable(name).text} Real)" for name in free_variables
    )
    solver.from_string(f"(set-logic NRA)\n{declarations}\n(assert {formula.text})")
    result = str(solver.check())
    if result == "sat":
        return True
    if result == "unsat":
        return False
    raise VisibilityComputationError(
        f"Exact visibility calculation unresolved: {solver.reason_unknown()}"
    )
