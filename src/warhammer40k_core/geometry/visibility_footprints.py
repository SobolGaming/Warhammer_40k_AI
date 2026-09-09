"""Analytic model/terrain occupancy used by visibility policy exceptions.

Intersections use exact disk/polygon primitives. Union containment asks whether
an analytic model point exists outside every exact polygon triangle; an empty
complement certifies containment, including shared boundaries and union holes.
"""

from __future__ import annotations

from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.polygons import Point2D, validate_footprint_polygon
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.visibility_algebra import (
    Formula,
    RealTerm,
    both,
    decide,
    either,
    negate,
    term,
    variable,
)
from warhammer40k_core.geometry.visibility_exact import (
    RationalPolygon,
    VisibilityPrism,
    convex_polygon_parts,
    footprint_intersects_polygon,
)
from warhammer40k_core.geometry.visibility_formulas import ModelDomain
from warhammer40k_core.geometry.visibility_shapes import model_visibility_prism
from warhammer40k_core.geometry.volume import Model


@lru_cache(maxsize=4096)
def rational_polygon(polygon: tuple[Point2D, ...]) -> RationalPolygon:
    validate_footprint_polygon("Visibility polygon", polygon)
    return tuple((Fraction(x), Fraction(y)) for x, y in polygon)


def polygon_visibility_prism(
    polygon: tuple[Point2D, ...], lower: Fraction, upper: Fraction
) -> VisibilityPrism:
    points = rational_polygon(polygon)
    return VisibilityPrism(
        points,
        lower,
        upper,
        (
            min(x for x, _ in points),
            min(y for _, y in points),
            max(x for x, _ in points),
            max(y for _, y in points),
        ),
    )


@lru_cache(maxsize=4096)
def model_intersects_visibility_polygon(model: Model, polygon: tuple[Point2D, ...]) -> bool:
    return footprint_intersects_polygon(
        model_visibility_prism(model).footprint, rational_polygon(polygon)
    )


@lru_cache(maxsize=4096)
def model_within_visibility_polygons(
    model: Model, polygons: tuple[tuple[Point2D, ...], ...]
) -> bool:
    if type(polygons) is not tuple or not polygons:
        raise GeometryError("Visibility containment requires a non-empty polygon tuple.")
    prepared = tuple(rational_polygon(polygon) for polygon in polygons)
    domain = ModelDomain.from_prism(model_visibility_prism(model))
    x, y = variable("x"), variable("y")
    covered = either(*(_polygon_member(polygon, x, y) for polygon in prepared))
    return not decide(both(domain.member((x, y, term(domain.lower))), negate(covered)), ("x", "y"))


def _polygon_member(polygon: RationalPolygon, x: RealTerm, y: RealTerm) -> Formula:
    return either(
        *(
            both(
                *(
                    ((term(b[0] - a[0]) * (y - a[1])) - (term(b[1] - a[1]) * (x - a[0]))).ge(0)
                    for a, b in zip(part, (*part[1:], part[0]), strict=True)
                )
            )
            for part in convex_polygon_parts(polygon)
        )
    )


@lru_cache(maxsize=4096)
def visibility_polygon_within_union(
    polygon: tuple[Point2D, ...], polygons: tuple[tuple[Point2D, ...], ...]
) -> bool:
    candidate = rational_polygon(polygon)
    if type(polygons) is not tuple or not polygons:
        raise GeometryError("Visibility containment requires a non-empty polygon tuple.")
    prepared = tuple(rational_polygon(member) for member in polygons)
    x, y = variable("x"), variable("y")
    return not decide(
        both(
            _polygon_member(candidate, x, y),
            negate(either(*(_polygon_member(member, x, y) for member in prepared))),
        ),
        ("x", "y"),
    )
