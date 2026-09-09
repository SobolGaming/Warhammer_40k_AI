"""Exact fixed-corridor predicates over rational polygons and analytic ellipses.

Every input coordinate is an exact rational. Nonvertical strip coordinates live
in Q(sqrt(dx²+dy²)); sign tests eliminate the radical algebraically. Height clips
the segment parameter BEFORE XY intersection, preserving flat caps. The vertical
case is a disk, including closed contact. No polygon approximation or tolerance
decides a visibility answer. This module has no model/rules/engine dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from functools import lru_cache
from itertools import pairwise
from math import isqrt
from typing import cast

type RationalPoint2 = tuple[Fraction, Fraction]
type RationalPoint3 = tuple[Fraction, Fraction, Fraction]
type RationalPolygon = tuple[RationalPoint2, ...]

CORRIDOR_RADIUS = Fraction(5, 254)


def _validate_rational_point(point: object, count: int) -> None:
    if type(point) is not tuple:
        raise ValueError("Visibility coordinates must be immutable exact rational tuples.")
    values = cast(tuple[object, ...], point)
    if len(values) != count or any(type(value) is not Fraction for value in values):
        raise ValueError("Visibility coordinates must be immutable exact rational tuples.")


def _validate_rational_polygon(polygon: RationalPolygon) -> None:
    if type(polygon) is not tuple or len(polygon) < 3:
        raise ValueError("Visibility footprint must be a nondegenerate rational polygon.")
    for point in polygon:
        _validate_rational_point(point, 2)
    _validate_simple_rational_polygon(polygon)


@lru_cache(maxsize=4096)
def _validate_simple_rational_polygon(polygon: RationalPolygon) -> None:
    edges = tuple(zip(polygon, (*polygon[1:], polygon[0]), strict=True))
    if len(set(polygon)) != len(polygon) or sum(a[0] * b[1] - a[1] * b[0] for a, b in edges) == 0:
        raise ValueError("Visibility footprint must have distinct vertices and nonzero area.")
    for index, (a, b) in enumerate(edges):
        for other, (c, d) in enumerate(edges[index + 1 :], index + 1):
            if other == index + 1 or (index == 0 and other == len(edges) - 1):
                continue
            if (
                max(a[0], b[0]) >= min(c[0], d[0])
                and max(c[0], d[0]) >= min(a[0], b[0])
                and max(a[1], b[1]) >= min(c[1], d[1])
                and max(c[1], d[1]) >= min(a[1], b[1])
                and _rational_turn(a, b, c) * _rational_turn(a, b, d) <= 0
                and _rational_turn(c, d, a) * _rational_turn(c, d, b) <= 0
            ):
                raise ValueError("Visibility footprint must be a simple polygon.")


@lru_cache(maxsize=4096)
def rational_sqrt_bounds(value: Fraction) -> tuple[Fraction, Fraction]:
    """Outward bounds used only by one-way proof enclosures, never shape mutation."""
    if value < 0:
        raise ValueError("A real square-root enclosure requires a nonnegative argument.")
    denominator = value.denominator * (1 << 32)
    square = value.numerator * value.denominator * (1 << 64)
    numerator = isqrt(square)
    return (
        Fraction(numerator, denominator),
        Fraction(numerator if numerator * numerator == square else numerator + 1, denominator),
    )


def _rational_turn(a: RationalPoint2, b: RationalPoint2, c: RationalPoint2) -> Fraction:
    return (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])


@lru_cache(maxsize=4096)
def convex_polygon_parts(polygon: RationalPolygon) -> tuple[RationalPolygon, ...]:
    """Exact ear decomposition of a validated simple polygon, including concavity."""
    points = list(polygon)
    area = sum(
        (a[0] * b[1] - a[1] * b[0] for a, b in zip(points, (*points[1:], points[0]), strict=True)),
        Fraction(0),
    )
    if area == 0:
        raise ValueError("A visibility polygon must have positive area.")
    if area < 0:
        points.reverse()
    while len(points) > 3:
        collinear = next(
            (
                i
                for i in range(len(points))
                if _rational_turn(points[i - 1], points[i], points[(i + 1) % len(points)]) == 0
            ),
            None,
        )
        if collinear is None:
            break
        points.pop(collinear)
    if all(
        _rational_turn(points[i - 1], points[i], points[(i + 1) % len(points)]) > 0
        for i in range(len(points))
    ):
        return (tuple(points),)
    pieces: list[RationalPolygon] = []
    while len(points) > 3:
        for i in range(len(points)):
            a, b, c = points[i - 1], points[i], points[(i + 1) % len(points)]
            if _rational_turn(a, b, c) <= 0:
                continue
            if any(
                all(
                    turn >= 0
                    for turn in (
                        _rational_turn(a, b, p),
                        _rational_turn(b, c, p),
                        _rational_turn(c, a, p),
                    )
                )
                for p in points
                if p not in (a, b, c)
            ):
                continue
            pieces.append((a, b, c))
            points.pop(i)
            break
        else:
            raise ValueError("Visibility polygon could not be decomposed as a simple polygon.")
    pieces.append(tuple(points))
    return tuple(pieces)


@dataclass(frozen=True, slots=True)
class RationalEllipse:
    center: RationalPoint2
    first_axis: RationalPoint2
    second_axis: RationalPoint2

    def __post_init__(self) -> None:
        for point in (self.center, self.first_axis, self.second_axis):
            _validate_rational_point(point, 2)
        a, b = self.first_axis, self.second_axis
        if a[0] * b[1] == a[1] * b[0]:
            raise ValueError("An ellipse must have independent axes.")

    def local(self, point: RationalPoint2) -> RationalPoint2:
        x, y = point[0] - self.center[0], point[1] - self.center[1]
        a, b = self.first_axis, self.second_axis
        determinant = a[0] * b[1] - a[1] * b[0]
        if determinant == 0:
            raise ValueError("An ellipse must have independent axes.")
        return ((b[1] * x - b[0] * y) / determinant, (-a[1] * x + a[0] * y) / determinant)

    def local_vector(self, point: RationalPoint2) -> RationalPoint2:
        return self.local((point[0] + self.center[0], point[1] + self.center[1]))


@dataclass(frozen=True, slots=True)
class VisibilityPrism:
    footprint: RationalEllipse | RationalPolygon
    lower: Fraction
    upper: Fraction
    bounds: tuple[Fraction, Fraction, Fraction, Fraction]

    def __post_init__(self) -> None:
        _validate_rational_point(self.bounds, 4)
        if (
            type(self.lower) is not Fraction
            or type(self.upper) is not Fraction
            or self.upper < self.lower
        ):
            raise ValueError("Visibility prism heights must be ordered rational coordinates.")
        if isinstance(self.footprint, RationalEllipse):
            for axis in (0, 1):
                support2 = (
                    self.footprint.first_axis[axis] ** 2 + self.footprint.second_axis[axis] ** 2
                )
                for margin in (
                    self.footprint.center[axis] - self.bounds[axis],
                    self.bounds[axis + 2] - self.footprint.center[axis],
                ):
                    if margin < 0 or margin * margin < support2:
                        raise ValueError(
                            "Visibility prism bounds must enclose its analytic footprint."
                        )
        else:
            _validate_rational_polygon(self.footprint)
            if any(
                not (
                    self.bounds[0] <= x <= self.bounds[2] and self.bounds[1] <= y <= self.bounds[3]
                )
                for x, y in self.footprint
            ):
                raise ValueError("Visibility prism bounds must enclose its polygon footprint.")

    def contains_point(self, point: RationalPoint3) -> bool:
        if point[2] < self.lower or point[2] > self.upper:
            return False
        if isinstance(self.footprint, RationalEllipse):
            u, v = self.footprint.local(point[:2])
            return u * u + v * v <= 1
        return any(
            all(
                _rational_turn(a, b, point[:2]) >= 0
                for a, b in zip(part, (*part[1:], part[0]), strict=True)
            )
            for part in convex_polygon_parts(self.footprint)
        )

    def intersects_corridor(self, start: RationalPoint3, end: RationalPoint3) -> bool:
        if not self.corridor_bounds_overlap(start, end):
            return False
        if isinstance(self.footprint, RationalEllipse):
            return corridor_intersects_ellipse(start, end, self.footprint, (self.lower, self.upper))
        return corridor_intersects_polygon(start, end, self.footprint, (self.lower, self.upper))

    def corridor_bounds_overlap(self, start: RationalPoint3, end: RationalPoint3) -> bool:
        min_x, min_y, max_x, max_y = self.bounds
        return (
            min(start[0], end[0]) - CORRIDOR_RADIUS <= max_x
            and max(start[0], end[0]) + CORRIDOR_RADIUS >= min_x
            and min(start[1], end[1]) - CORRIDOR_RADIUS <= max_y
            and max(start[1], end[1]) + CORRIDOR_RADIUS >= min_y
            and min(start[2], end[2]) <= self.upper
            and max(start[2], end[2]) >= self.lower
        )


@dataclass(frozen=True, slots=True)
class _Surd:
    a: Fraction
    b: Fraction
    radicand: Fraction

    def __add__(self, other: _Surd) -> _Surd:
        self._same_field(other)
        return _Surd(self.a + other.a, self.b + other.b, self.radicand)

    def __sub__(self, other: _Surd) -> _Surd:
        self._same_field(other)
        return _Surd(self.a - other.a, self.b - other.b, self.radicand)

    def __mul__(self, other: _Surd) -> _Surd:
        self._same_field(other)
        return _Surd(
            self.a * other.a + self.b * other.b * self.radicand,
            self.a * other.b + self.b * other.a,
            self.radicand,
        )

    def _same_field(self, other: _Surd) -> None:
        if self.radicand != other.radicand:
            raise ValueError("Visibility arithmetic requires one quadratic field.")

    def constant(self, value: Fraction | int) -> _Surd:
        return _Surd(Fraction(value), Fraction(0), self.radicand)

    def sign(self) -> int:
        if self.b == 0 or self.radicand == 0:
            return _sign(self.a)
        if self.a == 0 or _sign(self.a) == _sign(self.b):
            return _sign(self.b)
        difference = self.a * self.a - self.b * self.b * self.radicand
        return _sign(difference) * _sign(self.a)


type _Point = tuple[_Surd, _Surd]
type _Polygon = tuple[_Point, ...]


def _sign(value: Fraction) -> int:
    return (value > 0) - (value < 0)


def _difference(a: _Point, b: _Point) -> _Point:
    return (a[0] - b[0], a[1] - b[1])


def _dot(a: _Point, b: _Point) -> _Surd:
    return a[0] * b[0] + a[1] * b[1]


def _cross(a: _Point, b: _Point) -> _Surd:
    return a[0] * b[1] - a[1] * b[0]


def _edges(polygon: _Polygon) -> tuple[tuple[_Point, _Point], ...]:
    return tuple(zip(polygon, (*polygon[1:], polygon[0]), strict=True))


def _point_in_polygon(point: _Point, polygon: _Polygon) -> bool:
    winding = 0
    for start, end in _edges(polygon):
        orientation = _cross(_difference(end, start), _difference(point, start)).sign()
        if (
            orientation == 0
            and _dot(_difference(point, start), _difference(point, end)).sign() <= 0
        ):
            return True
        start_y, end_y = (start[1] - point[1]).sign(), (end[1] - point[1]).sign()
        if start_y <= 0 < end_y and orientation > 0:
            winding += 1
        elif end_y <= 0 < start_y and orientation < 0:
            winding -= 1
    return winding != 0


def _segments_intersect(a: _Point, b: _Point, c: _Point, d: _Point) -> bool:
    ab, cd = _difference(b, a), _difference(d, c)
    signs = (
        _cross(ab, _difference(c, a)).sign(),
        _cross(ab, _difference(d, a)).sign(),
        _cross(cd, _difference(a, c)).sign(),
        _cross(cd, _difference(b, c)).sign(),
    )
    for orientation, point, start, end in (
        (signs[0], c, a, b),
        (signs[1], d, a, b),
        (signs[2], a, c, d),
        (signs[3], b, c, d),
    ):
        if (
            orientation == 0
            and _dot(_difference(point, start), _difference(point, end)).sign() <= 0
        ):
            return True
    return signs[0] * signs[1] < 0 and signs[2] * signs[3] < 0


def _polygons_intersect(first: _Polygon, second: _Polygon) -> bool:
    if _point_in_polygon(first[0], second) or _point_in_polygon(second[0], first):
        return True
    return any(_segments_intersect(a, b, c, d) for a, b in _edges(first) for c, d in _edges(second))


def _unit_disk_intersects_polygon(polygon: _Polygon) -> bool:
    zero, one = polygon[0][0].constant(0), polygon[0][0].constant(1)
    if _point_in_polygon((zero, zero), polygon):
        return True
    for start, end in _edges(polygon):
        if (_dot(start, start) - one).sign() <= 0:
            return True
        edge = _difference(end, start)
        length2 = _dot(edge, edge)
        projection = zero - _dot(start, edge)
        if projection.sign() > 0 and (length2 - projection).sign() > 0:
            area = _cross(start, edge)
            if (area * area - length2).sign() <= 0:
                return True
    return False


def footprint_intersects_polygon(
    footprint: RationalEllipse | RationalPolygon, polygon: RationalPolygon
) -> bool:
    """Closed analytic footprint intersection; no corridor expansion is applied."""
    zero = Fraction(0)

    def lifted(points: RationalPolygon) -> _Polygon:
        return tuple((_Surd(x, zero, zero), _Surd(y, zero, zero)) for x, y in points)

    if isinstance(footprint, RationalEllipse):
        return _unit_disk_intersects_polygon(lifted(tuple(footprint.local(p) for p in polygon)))
    return _polygons_intersect(lifted(footprint), lifted(polygon))


def _clip_height(
    start: RationalPoint3,
    end: RationalPoint3,
    lower: Fraction,
    upper: Fraction,
) -> tuple[RationalPoint2, RationalPoint2] | None:
    dz = end[2] - start[2]
    if dz == 0:
        return (start[:2], end[:2]) if lower <= start[2] <= upper else None
    first, last = sorted(((lower - start[2]) / dz, (upper - start[2]) / dz))
    first, last = max(Fraction(0), first), min(Fraction(1), last)
    if first > last:
        return None
    dx, dy = end[0] - start[0], end[1] - start[1]
    return (
        (start[0] + first * dx, start[1] + first * dy),
        (start[0] + last * dx, start[1] + last * dy),
    )


def _strip(
    start: RationalPoint2,
    end: RationalPoint2,
    direction: RationalPoint2,
    ellipse: RationalEllipse | None = None,
) -> _Polygon:
    dx, dy = direction
    length2 = dx * dx + dy * dy
    if length2 == 0:
        raise ValueError("A strip requires nonzero horizontal displacement.")
    lateral = (-dy * CORRIDOR_RADIUS / length2, dx * CORRIDOR_RADIUS / length2)
    if ellipse is not None:
        start, end = ellipse.local(start), ellipse.local(end)
        lateral = ellipse.local_vector(lateral)
    return tuple(
        (_Surd(point[0], sign * lateral[0], length2), _Surd(point[1], sign * lateral[1], length2))
        for point, sign in ((start, -1), (end, -1), (end, 1), (start, 1))
    )


def corridor_intersects_polygon(
    start: RationalPoint3,
    end: RationalPoint3,
    polygon: RationalPolygon,
    vertical_interval: tuple[Fraction, Fraction] | None = None,
) -> bool:
    if len(polygon) < 3:
        raise ValueError("A visibility polygon requires at least three vertices.")
    clipped = (
        (start[:2], end[:2])
        if vertical_interval is None
        else _clip_height(start, end, *vertical_interval)
    )
    if clipped is None:
        return False
    direction = (end[0] - start[0], end[1] - start[1])
    if direction[0] == 0 and direction[1] == 0:
        normalized = tuple(
            (
                _Surd((x - start[0]) / CORRIDOR_RADIUS, Fraction(0), Fraction(0)),
                _Surd((y - start[1]) / CORRIDOR_RADIUS, Fraction(0), Fraction(0)),
            )
            for x, y in polygon
        )
        return _unit_disk_intersects_polygon(normalized)
    strip = _strip(*clipped, direction)
    constant_polygon = tuple((strip[0][0].constant(x), strip[0][0].constant(y)) for x, y in polygon)
    return _polygons_intersect(strip, constant_polygon)


def corridor_intersects_ellipse(
    start: RationalPoint3,
    end: RationalPoint3,
    ellipse: RationalEllipse,
    vertical_interval: tuple[Fraction, Fraction],
) -> bool:
    clipped = _clip_height(start, end, *vertical_interval)
    if clipped is None:
        return False
    direction = (end[0] - start[0], end[1] - start[1])
    if direction[0] == 0 and direction[1] == 0:
        return _circle_intersects_ellipse(start[:2], ellipse)
    return _unit_disk_intersects_polygon(_strip(*clipped, direction, ellipse))


def _circle_intersects_ellipse(center: RationalPoint2, ellipse: RationalEllipse) -> bool:
    x, y = ellipse.local(center)
    if x * x + y * y <= 1:
        return True
    dx, dy = center[0] - ellipse.center[0], center[1] - ellipse.center[1]
    if dx * dx + dy * dy <= CORRIDOR_RADIUS * CORRIDOR_RADIUS:
        return True
    # Circle parameterization ((1-t²)/(1+t²), 2t/(1+t²)) covers all but (-1,0).
    # Substitution into the ellipse equation produces a rational quartic. Sturm
    # counts its real roots, including repeated/tangent roots, without sampling.
    first = ellipse.local((center[0] + CORRIDOR_RADIUS, center[1]))
    middle = ellipse.local_vector((Fraction(0), 2 * CORRIDOR_RADIUS))
    last = ellipse.local((center[0] - CORRIDOR_RADIUS, center[1]))
    if last[0] * last[0] + last[1] * last[1] == 1:
        return True
    polynomial = [Fraction(0)] * 5
    for coordinate in (0, 1):
        coefficients = (first[coordinate], middle[coordinate], last[coordinate])
        for i, a in enumerate(coefficients):
            for j, b in enumerate(coefficients):
                polynomial[i + j] += a * b
    for index, coefficient in ((0, 1), (2, 2), (4, 1)):
        polynomial[index] -= coefficient
    return _has_real_root(tuple(polynomial))


def _trim(polynomial: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    while polynomial and polynomial[-1] == 0:
        polynomial = polynomial[:-1]
    return polynomial


def _remainder(first: tuple[Fraction, ...], second: tuple[Fraction, ...]) -> tuple[Fraction, ...]:
    result = list(first)
    while len(result) >= len(second):
        factor = result[-1] / second[-1]
        shift = len(result) - len(second)
        for index, coefficient in enumerate(second):
            result[index + shift] -= factor * coefficient
        while result and result[-1] == 0:
            result.pop()
    return tuple(result)


def _has_real_root(polynomial: tuple[Fraction, ...]) -> bool:
    polynomial = _trim(polynomial)
    if not polynomial:
        return True
    if len(polynomial) == 1:
        return False
    sequence = [polynomial, tuple(index * value for index, value in enumerate(polynomial) if index)]
    while True:
        remainder = _remainder(sequence[-2], sequence[-1])
        if not remainder:
            break
        sequence.append(tuple(-value for value in remainder))
    positive = [_sign(row[-1]) for row in sequence]
    negative = [_sign(row[-1]) * (-1 if len(row) % 2 == 0 else 1) for row in sequence]
    positive_changes = sum(a != b for a, b in pairwise(positive))
    negative_changes = sum(a != b for a, b in pairwise(negative))
    return negative_changes > positive_changes
