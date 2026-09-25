"""Shared source-backed quarter occupancy for primary and secondary scoring."""

from __future__ import annotations

from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.table_quarters import wholly_within_table_quarter
from warhammer40k_core.geometry.volume import Model
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_table_quarters_2026_09 as quarter_source,
)


def scoring_table_quarter_id_or_none(
    *,
    geometry_models: tuple[Model, ...],
    center_x: float,
    center_y: float,
) -> str | None:
    """Reconnaissance Sweep and Engage require the entire unit beyond six inches."""
    quarter_id = wholly_within_table_quarter(
        models=geometry_models,
        center_x=center_x,
        center_y=center_y,
        divider_width_inches=quarter_source.DIVIDER_WIDTH_INCHES,
    )
    if quarter_id is None:
        return None
    if any(
        shapely_backend.base_footprint_distance_to_point(
            model.base, model.pose, x=center_x, y=center_y
        )
        <= 6.0
        for model in geometry_models
    ):
        return None
    return quarter_id
