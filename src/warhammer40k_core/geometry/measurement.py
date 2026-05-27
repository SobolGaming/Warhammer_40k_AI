from __future__ import annotations

from warhammer40k_core.geometry.pose import GeometryError, validate_finite_number

MILLIMETERS_PER_INCH = 25.4


def millimeters_to_inches(value_mm: object) -> float:
    millimeters = validate_finite_number("millimeters", value_mm)
    if millimeters <= 0.0:
        raise GeometryError("millimeters must be greater than 0.")
    return millimeters / MILLIMETERS_PER_INCH
