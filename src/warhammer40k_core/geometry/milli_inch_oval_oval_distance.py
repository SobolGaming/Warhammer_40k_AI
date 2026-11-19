"""Staged Euclidean surface gap between two filled canonical ovals."""

from __future__ import annotations

from itertools import zip_longest
from math import gcd, isqrt

from warhammer40k_core.geometry.milli_inch_circle import CircleRelation
from warhammer40k_core.geometry.milli_inch_oval import (
    CanonicalOval,
    _ellipse_coefficients,  # pyright: ignore[reportPrivateUsage]
    _round_distance_ticks,  # pyright: ignore[reportPrivateUsage]
)
from warhammer40k_core.geometry.milli_inch_oval_oval import oval_oval_relation


def oval_oval_distance_ticks(first: CanonicalOval, second: CanonicalOval) -> int:
    """Round the Euclidean surface gap once, with exact half ticks rounding up."""
    if oval_oval_relation(first, second) is not CircleRelation.SEPARATED:
        return 0

    dx = second.center[0] - first.center[0]
    dy = second.center[1] - first.center[1]
    center_squared = dx**2 + dy**2
    # Inscribed and circumscribed disks give bounds on the gap. The floor
    # of twice the center distance suffices to round both bounds exactly.
    center_floor = isqrt(4 * center_squared)
    low = max(0, (center_floor + 1 - first.length_ticks - second.length_ticks) // 2)
    high = (center_floor + 1 - first.width_ticks - second.width_ticks) // 2

    first_support = _support_squared(first, dx, dy)
    second_support = _support_squared(second, dx, dy)
    return low + _round_distance_ticks(
        high - low,
        lambda midpoint: (
            not _gap_at_least(
                8 * center_squared**2,
                first_support,
                second_support,
                2 * center_squared * (midpoint + 2 * low) ** 2,
            )
        ),
    )


# Integer coefficients in ascending degree order, with () representing zero.
type _Polynomial = tuple[int, ...]


def _support_squared(oval: CanonicalOval, dx: int, dy: int) -> _Polynomial:
    """Square the support of n(s) = (dx - dy*s, dy + dx*s) in scaled tick units."""
    xx, xy, yy, _ = _ellipse_coefficients(oval)
    # The inverse of the normalized ellipse quadratic gives its squared
    # support. The following coefficients absorb the common scale 2*sqrt(2).
    nx2, nxny, ny2 = yy // 2, -xy // 2, xx // 2
    return (
        nx2 * dx**2 + nxny * dx * dy + ny2 * dy**2,
        2 * (ny2 - nx2) * dx * dy + nxny * (dx**2 - dy**2),
        nx2 * dy**2 - nxny * dx * dy + ny2 * dx**2,
    )


def _gap_at_least(
    projection_squared: int,
    first: _Polynomial,
    second: _Polynomial,
    threshold_squared: int,
) -> bool:
    # Every normal with positive center projection scales to n(s) for a
    # unique real s. The projection L is constant and positive on this line.
    # A, B are squared supports and C is the squared threshold times |n|².
    # Feasibility of sqrt(A)+sqrt(B)+sqrt(C) <= L is equivalent to
    # equality somewhere, since the sum is continuous and tends to infinity.
    c = (threshold_squared, 0, threshold_squared)
    beyond_disk = (projection_squared - threshold_squared, 0, -threshold_squared)
    # Isolate sqrt(A)+sqrt(B), then square with the retained signs.
    # At equality, D = 2L*sqrt(C) + 2*sqrt(A*B)
    # and E = D² - 4L²C - 4AB = 8L*sqrt(ABC).
    d = _add((projection_squared,), c, _scale(first, -1), _scale(second, -1))
    ab = _multiply(first, second)
    e = _add(_multiply(d, d), _scale(c, -4 * projection_squared), _scale(ab, -4))
    f = _add(_multiply(e, e), _scale(_multiply(ab, c), -64 * projection_squared))

    guards = (beyond_disk, d, e)
    # The center direction itself can certify the inequality without root work.
    if all(guard and guard[0] > 0 for guard in guards) and f[0] >= 0:
        return True

    # Count distinct real roots of F with all three guards strictly positive.
    # For a guard g, (sgn(g) + sgn(g²))/2 is its positivity indicator.
    # Expand the product of those indicators into eight Sturm-Tarski queries.
    derivative = tuple(i * coeff for i, coeff in enumerate(f) if i)
    numerators = [derivative]
    for guard in guards:
        weighted: list[_Polynomial] = []
        for numerator in numerators:
            once = _remainder(_multiply(numerator, guard), f)
            twice = _remainder(_multiply(once, guard), f)
            weighted.extend((once, twice))
        numerators = weighted
    return sum(_cauchy_index(f, numerator) for numerator in numerators) > 0


def _add(*polynomials: _Polynomial) -> _Polynomial:
    return _trim([sum(terms) for terms in zip_longest(*polynomials, fillvalue=0)])


def _scale(polynomial: _Polynomial, factor: int) -> _Polynomial:
    return tuple(factor * coefficient for coefficient in polynomial)


def _multiply(first: _Polynomial, second: _Polynomial) -> _Polynomial:
    if not first or not second:
        return ()
    coefficients = [0] * (len(first) + len(second) - 1)
    for i, a in enumerate(first):
        for j, b in enumerate(second):
            coefficients[i + j] += a * b
    return tuple(coefficients)


def _trim(coefficients: list[int]) -> _Polynomial:
    while coefficients and coefficients[-1] == 0:
        coefficients.pop()
    return tuple(coefficients)


def _remainder(dividend: _Polynomial, divisor: _Polynomial) -> _Polynomial:
    """Return a positive rescaling of the rational polynomial remainder."""
    leading = divisor[-1]
    while dividend and len(dividend) >= len(divisor):
        offset = len(dividend) - len(divisor)
        factor = dividend[-1] if leading > 0 else -dividend[-1]
        coefficients = [abs(leading) * term for term in dividend]
        for i, term in enumerate(divisor, offset):
            coefficients[i] -= factor * term
        dividend = _trim(coefficients)
        content = gcd(*dividend)
        if content > 1:
            dividend = tuple(term // content for term in dividend)
    return dividend


def _cauchy_index(denominator: _Polynomial, numerator: _Polynomial) -> int:
    # The signed remainder sequence gives V(-infinity) - V(+infinity).
    # Adjacent terms of the same degree parity contribute zero to the difference.
    # For numerator F'*weight, each real root contributes sgn(weight) even
    # at a multiple root: the positive multiplicity only scales the residue.
    difference = 0
    while numerator:
        if (len(denominator) - len(numerator)) % 2:
            difference += 1 if denominator[-1] * numerator[-1] > 0 else -1
        denominator, numerator = numerator, _scale(_remainder(denominator, numerator), -1)
    return difference
