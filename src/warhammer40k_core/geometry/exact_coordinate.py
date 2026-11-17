"""Inactive canonical quadratic coordinates, in inches, with exact arithmetic.

A quadratic irrational has the unique form a + sign*sqrt(q), with rational a,
positive nonsquare rational q and sign in {-1, 1}. Rational values use sign=q=0.
There is no float decoding, snapping, or gameplay enrollment at this boundary.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import isqrt
from typing import Self, TypedDict, cast

from warhammer40k_core.geometry.milli_inch import DistancePrecisionError

COORDINATE_REPRESENTATION_ID = "rational-quadratic-coordinate-v1"
MAX_COMPONENT_BITS = 256


class ExactCoordinateError(DistancePrecisionError):
    """Malformed or noncanonical exact coordinate."""


class UnsupportedExactCoordinateError(ExactCoordinateError):
    """The bounded quadratic domain cannot represent this exact calculation."""


class CoordinatePayload(TypedDict):
    rational: list[int]
    root_sign: int
    squared_root: list[int]


def _sqrt_fraction(value: Fraction) -> Fraction | None:
    numerator, denominator = isqrt(value.numerator), isqrt(value.denominator)
    if numerator * numerator == value.numerator and denominator * denominator == value.denominator:
        return Fraction(numerator, denominator)
    return None


def _fraction(value: object) -> Fraction:
    if type(value) is not Fraction:
        raise ExactCoordinateError("Exact coordinate components must be Fractions.")
    if max(abs(value.numerator).bit_length(), value.denominator.bit_length()) > MAX_COMPONENT_BITS:
        raise UnsupportedExactCoordinateError("Exact coordinate component exceeds 256 bits.")
    return value


def _read_fraction(value: object) -> Fraction:
    if type(value) is not list:
        raise ExactCoordinateError("A rational payload requires an integer list.")
    items = cast(list[object], value)
    if len(items) != 2 or any(type(item) is not int for item in items):
        raise ExactCoordinateError("A rational payload requires two integers.")
    numerator, denominator = cast(list[int], items)
    if denominator <= 0:
        raise ExactCoordinateError("A rational denominator must be positive.")
    if max(abs(numerator).bit_length(), denominator.bit_length()) > MAX_COMPONENT_BITS:
        raise UnsupportedExactCoordinateError("Exact coordinate component exceeds 256 bits.")
    result = Fraction(numerator, denominator)
    if [result.numerator, result.denominator] != items:
        raise ExactCoordinateError("A rational payload must be reduced, including unique zero.")
    return result


@dataclass(frozen=True, slots=True)
class ExactCoordinate:
    rational: Fraction
    root_sign: int = 0
    squared_root: Fraction = Fraction(0)

    def __post_init__(self) -> None:
        _fraction(self.rational)
        _fraction(self.squared_root)
        if type(self.root_sign) is not int or self.root_sign not in (-1, 0, 1):
            raise ExactCoordinateError("Root selection must be -1, 0 or 1.")
        if self.root_sign == 0:
            if self.squared_root != 0:
                raise ExactCoordinateError("A rational coordinate has zero radicand.")
        elif self.squared_root <= 0 or _sqrt_fraction(self.squared_root) is not None:
            raise ExactCoordinateError(
                "A selected quadratic root must have positive nonsquare radicand."
            )

    @classmethod
    def from_root(cls, rational: Fraction, coefficient: Fraction, radicand: Fraction) -> Self:
        """Normalize a + b*sqrt(q); a negative radicand is never a real coordinate."""
        _fraction(rational)
        _fraction(coefficient)
        _fraction(radicand)
        if radicand < 0:
            raise ExactCoordinateError("A real root requires a nonnegative radicand.")
        square = coefficient * coefficient * radicand
        root = _sqrt_fraction(square)
        sign = (coefficient > 0) - (coefficient < 0)
        if root is not None:
            return cls(rational + sign * root)
        return cls(rational, sign, square)

    def to_payload(self) -> CoordinatePayload:
        return {
            "rational": [self.rational.numerator, self.rational.denominator],
            "root_sign": self.root_sign,
            "squared_root": [self.squared_root.numerator, self.squared_root.denominator],
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if type(payload) is not dict:
            raise ExactCoordinateError("An exact coordinate payload must be an object.")
        data = cast(dict[str, object], payload)
        if set(data) != {"rational", "root_sign", "squared_root"}:
            raise ExactCoordinateError(
                "An exact coordinate payload requires the exact declared keys."
            )
        canonical = cast(CoordinatePayload, data)
        return cls(
            _read_fraction(canonical["rational"]),
            canonical["root_sign"],
            _read_fraction(canonical["squared_root"]),
        )

    def sign(self) -> int:
        """Select the real root exactly; no isolating-interval identity ambiguity."""
        return self.compare_rational(Fraction(0))

    def compare_rational(self, value: Fraction) -> int:
        """Compare with a rational boundary, without storing the derived difference."""
        if type(value) is not Fraction:
            raise ExactCoordinateError("An exact comparison boundary must be a Fraction.")
        a, s, q = self.rational - value, self.root_sign, self.squared_root
        if s == 0 or a == 0 or (a > 0) == (s > 0):
            return s if a == 0 else (a > 0) - (a < 0)
        difference = a * a - q
        return ((difference > 0) - (difference < 0)) * ((a > 0) - (a < 0))

    def _field(self, other: ExactCoordinate) -> tuple[Fraction, Fraction, Fraction]:
        if type(other) is not ExactCoordinate:
            raise ExactCoordinateError("Exact arithmetic requires exact coordinates.")
        q = self.squared_root or other.squared_root
        if not q:
            return Fraction(0), Fraction(0), Fraction(0)
        first = Fraction(self.root_sign)
        second = Fraction(other.root_sign)
        if self.root_sign and other.root_sign:
            ratio = _sqrt_fraction(other.squared_root / q)
            if ratio is None:
                raise UnsupportedExactCoordinateError("Mixed quadratic fields are unsupported.")
            second *= ratio
        return first, second, q

    def __neg__(self) -> ExactCoordinate:
        return ExactCoordinate(-self.rational, -self.root_sign, self.squared_root)

    def __add__(self, other: ExactCoordinate) -> ExactCoordinate:
        first, second, q = self._field(other)
        return ExactCoordinate.from_root(self.rational + other.rational, first + second, q)

    def __sub__(self, other: ExactCoordinate) -> ExactCoordinate:
        if type(other) is not ExactCoordinate:
            raise ExactCoordinateError("Exact arithmetic requires exact coordinates.")
        return self + (-other)

    def __mul__(self, other: ExactCoordinate) -> ExactCoordinate:
        first, second, q = self._field(other)
        return ExactCoordinate.from_root(
            self.rational * other.rational + first * second * q,
            self.rational * second + other.rational * first,
            q,
        )

    def reciprocal(self) -> ExactCoordinate:
        denominator = self.rational * self.rational - self.squared_root
        if denominator == 0:
            raise ExactCoordinateError("Zero has no reciprocal.")
        return ExactCoordinate.from_root(
            self.rational / denominator,
            Fraction(-self.root_sign, 1) / denominator,
            self.squared_root,
        )

    def __truediv__(self, other: ExactCoordinate) -> ExactCoordinate:
        if type(other) is not ExactCoordinate:
            raise ExactCoordinateError("Exact arithmetic requires exact coordinates.")
        return self * other.reciprocal()


def rational_coordinate(value: Fraction) -> ExactCoordinate:
    return ExactCoordinate(value)
