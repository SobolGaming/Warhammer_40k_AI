"""Whole-base containment in the four rectangles outside a finite centre divider."""

from __future__ import annotations

import math

from warhammer40k_core.geometry.base import CircularBase, OvalBase, RectangularBase
from warhammer40k_core.geometry.pose import GeometryError, validate_finite_number
from warhammer40k_core.geometry.visibility_shapes import rational_rotation
from warhammer40k_core.geometry.volume import Model

TABLE_QUARTER_NORTH_WEST = "table-quarter:north-west"
TABLE_QUARTER_NORTH_EAST = "table-quarter:north-east"
TABLE_QUARTER_SOUTH_WEST = "table-quarter:south-west"
TABLE_QUARTER_SOUTH_EAST = "table-quarter:south-east"
TABLE_QUARTER_IDS = (
    TABLE_QUARTER_NORTH_WEST,
    TABLE_QUARTER_NORTH_EAST,
    TABLE_QUARTER_SOUTH_WEST,
    TABLE_QUARTER_SOUTH_EAST,
)


def wholly_within_table_quarter(
    *,
    models: tuple[Model, ...],
    center_x: float,
    center_y: float,
    divider_width_inches: float,
) -> str | None:
    """Return one quarter only when every base fits, including the rectangle's border.

    Analytic axis extrema preserve rotated ellipses and hulls; a polygonal
    approximation could accept a curved base that overlaps the thin divider.
    The caller owns rules-unit membership and any mission-specific restrictions.
    """
    center_x = validate_finite_number("quarter center_x", center_x)
    center_y = validate_finite_number("quarter center_y", center_y)
    width = validate_finite_number("quarter divider width", divider_width_inches)
    if width <= 0 or min(center_x, center_y) <= width / 2:
        raise GeometryError("Table quarters require positive rectangles and divider width.")
    if type(models) is not tuple or any(type(model) is not Model for model in models):
        raise GeometryError("Table quarters require a tuple of geometry models.")
    if not models:
        return None
    half = width / 2
    quarter_bounds = (
        (TABLE_QUARTER_NORTH_WEST, (0.0, center_y + half, center_x - half, 2 * center_y)),
        (TABLE_QUARTER_NORTH_EAST, (center_x + half, center_y + half, 2 * center_x, 2 * center_y)),
        (TABLE_QUARTER_SOUTH_WEST, (0.0, 0.0, center_x - half, center_y - half)),
        (TABLE_QUARTER_SOUTH_EAST, (center_x + half, 0.0, 2 * center_x, center_y - half)),
    )
    bounds = tuple(_model_bounds(model) for model in models)
    for quarter_id, (left, bottom, right, top) in quarter_bounds:
        if all(
            left <= x0 and bottom <= y0 and x1 <= right and y1 <= top for x0, y0, x1, y1 in bounds
        ):
            return quarter_id
    return None


def _model_bounds(model: Model) -> tuple[float, float, float, float]:
    base = model.base
    if isinstance(base, CircularBase):
        half_x = half_y = base.radius
    elif isinstance(base, OvalBase | RectangularBase):
        cosine, sine = (float(value) for value in rational_rotation(model.pose.facing.degrees))
        a, b = base.length / 2, base.width / 2
        if isinstance(base, OvalBase):
            half_x, half_y = math.hypot(a * cosine, b * sine), math.hypot(a * sine, b * cosine)
        else:
            half_x, half_y = abs(a * cosine) + abs(b * sine), abs(a * sine) + abs(b * cosine)
    else:
        raise GeometryError("Table quarters require a supported analytic base or hull.")
    x, y = model.pose.position.x, model.pose.position.y
    return x - half_x, y - half_y, x + half_x, y + half_y
