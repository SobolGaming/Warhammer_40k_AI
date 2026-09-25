"""Whole-base containment in the four rectangles outside a finite centre divider."""

from __future__ import annotations

from fractions import Fraction

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

    Dimensions, positions and rotation coefficients retain their exact binary
    rational values, matching the analytic visibility shapes. No rounded bounds,
    polygonal approximation or tolerance determines contact with a quarter edge.
    The caller owns rules-unit membership and any mission-specific restrictions.
    """
    center_x = validate_finite_number("quarter center_x", center_x)
    center_y = validate_finite_number("quarter center_y", center_y)
    width = validate_finite_number("quarter divider width", divider_width_inches)
    cx, cy, half = Fraction(center_x), Fraction(center_y), Fraction(width) / 2
    if half <= 0 or min(cx, cy) <= half:
        raise GeometryError("Table quarters require positive rectangles and divider width.")
    if type(models) is not tuple or any(type(model) is not Model for model in models):
        raise GeometryError("Table quarters require a tuple of geometry models.")
    if not models:
        return None
    # Every supported footprint contains its centre. Its centre therefore selects
    # the only possible quarter; the exact predicates still check every model.
    first = models[0].pose.position
    west, south = first.x < center_x, first.y < center_y
    left, right = (Fraction(0), cx - half) if west else (cx + half, 2 * cx)
    bottom, top = (Fraction(0), cy - half) if south else (cy + half, 2 * cy)
    if not all(_model_within_rectangle(model, left, bottom, right, top) for model in models):
        return None
    return (
        (TABLE_QUARTER_SOUTH_WEST if west else TABLE_QUARTER_SOUTH_EAST)
        if south
        else (TABLE_QUARTER_NORTH_WEST if west else TABLE_QUARTER_NORTH_EAST)
    )


def _model_within_rectangle(
    model: Model, left: Fraction, bottom: Fraction, right: Fraction, top: Fraction
) -> bool:
    x, y = Fraction(model.pose.position.x), Fraction(model.pose.position.y)
    margin_x, margin_y = min(x - left, right - x), min(y - bottom, top - y)
    # Squaring an outside centre's negative clearance must never admit a shape.
    if margin_x < 0 or margin_y < 0:
        return False
    base = model.base
    if isinstance(base, CircularBase):
        radius = Fraction(base.radius)
        return radius <= margin_x and radius <= margin_y
    if isinstance(base, OvalBase | RectangularBase):
        cosine, sine = rational_rotation(model.pose.facing.degrees)
        a, b = Fraction(base.length) / 2, Fraction(base.width) / 2
        ax, ay, bx, by = a * cosine, a * sine, b * sine, b * cosine
        if isinstance(base, OvalBase):
            return (
                ax * ax + bx * bx <= margin_x * margin_x
                and ay * ay + by * by <= margin_y * margin_y
            )
        return abs(ax) + abs(bx) <= margin_x and abs(ay) + abs(by) <= margin_y
    raise GeometryError("Table quarters require a supported analytic base or hull.")
