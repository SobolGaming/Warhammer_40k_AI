"""Bounded immutable preparation of the analytic visibility geometry.

The base dimensions and pose coordinates enter as exact binary rationals. The
pose matrix is computed once; its actual inverse is used for ellipse membership.
Circular bases are orientation invariant. Bounds enclose every analytic point.
"""

from __future__ import annotations

import math
from fractions import Fraction
from functools import lru_cache

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import GeometryError, Point3, validate_point3
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.visibility_exact import (
    RationalEllipse,
    RationalPoint2,
    RationalPoint3,
    VisibilityPrism,
)
from warhammer40k_core.geometry.volume import Model


def rational_point(point: Point3) -> RationalPoint3:
    validate_point3("visibility point", point)
    return (Fraction(point.x), Fraction(point.y), Fraction(point.z))


def rational_rotation(degrees: float) -> RationalPoint2:
    normalized = degrees % 360.0
    if normalized == 0:
        return (Fraction(1), Fraction(0))
    if normalized == 90:
        return (Fraction(0), Fraction(1))
    if normalized == 180:
        return (Fraction(-1), Fraction(0))
    if normalized == 270:
        return (Fraction(0), Fraction(-1))
    angle = math.radians(normalized)
    return (Fraction(math.cos(angle)), Fraction(math.sin(angle)))


def _prism(
    center: RationalPoint3,
    first_axis: RationalPoint2,
    second_axis: RationalPoint2,
    height: Fraction,
    *,
    curved: bool,
) -> VisibilityPrism:
    a, b = first_axis, second_axis
    polygon = tuple(
        (center[0] + i * a[0] + j * b[0], center[1] + i * a[1] + j * b[1])
        for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))
    )
    return VisibilityPrism(
        RationalEllipse(center[:2], a, b) if curved else polygon,
        center[2],
        center[2] + height,
        (
            min(x for x, _ in polygon),
            min(y for _, y in polygon),
            max(x for x, _ in polygon),
            max(y for _, y in polygon),
        ),
    )


@lru_cache(maxsize=4096)
def model_visibility_prism(model: Model) -> VisibilityPrism:
    base = model.base
    if isinstance(base, CircularBase):
        a = b = Fraction(base.radius)
        c, s = Fraction(1), Fraction(0)
        curved = True
    elif isinstance(base, OvalBase | RectangularBase):
        a, b = Fraction(base.length) / 2, Fraction(base.width) / 2
        c, s = rational_rotation(model.pose.facing.degrees)
        curved = isinstance(base, OvalBase)
    else:
        raise GeometryError("Visibility requires a supported analytic model base.")
    return _prism(
        rational_point(model.pose.position),
        (a * c, a * s),
        (-b * s, b * c),
        Fraction(model.volume.height),
        curved=curved,
    )


@lru_cache(maxsize=4096)
def terrain_visibility_prism(terrain: TerrainVolume) -> VisibilityPrism:
    a, b = Fraction(terrain.width) / 2, Fraction(terrain.depth) / 2
    c, s = rational_rotation(terrain.rotation_degrees)
    return _prism(
        rational_point(terrain.bottom_center),
        (a * c, a * s),
        (-b * s, b * c),
        Fraction(terrain.height),
        curved=False,
    )
