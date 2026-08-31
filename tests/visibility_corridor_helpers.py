from __future__ import annotations

from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


def one_millimeter_visibility_gap_ruins(
    *,
    fixture_id: str,
    center_x_inches: float,
    gap_center_y_inches: float,
    min_y_inches: float,
    max_y_inches: float,
) -> tuple[TerrainFeatureDefinition, TerrainFeatureDefinition]:
    """Return two rules footprints with a 0.02in slit: clear to a ray, closed to 1mm LOS."""
    gap_half_width_inches = 0.01
    lower_max_y = gap_center_y_inches - gap_half_width_inches
    upper_min_y = gap_center_y_inches + gap_half_width_inches
    if not min_y_inches < lower_max_y < upper_min_y < max_y_inches:
        raise AssertionError("Visibility-gap fixture bounds must contain the gap.")

    spans = (
        ("lower", min_y_inches, lower_max_y),
        ("upper", upper_min_y, max_y_inches),
    )
    features: list[TerrainFeatureDefinition] = []
    for member_id, min_y, max_y in spans:
        center_y = (min_y + max_y) / 2.0
        depth = max_y - min_y
        display_geometry = TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=center_x_inches,
            center_y_inches=center_y,
            width_inches=1.0,
            depth_inches=depth,
            display_template_id=f"{fixture_id}:{member_id}:display",
        )
        features.append(
            TerrainFeatureDefinition(
                feature_id=f"{fixture_id}:{member_id}",
                feature_kind=TerrainFeatureKind.RUINS,
                footprint_center_x_inches=center_x_inches,
                footprint_center_y_inches=center_y,
                footprint_width_inches=1.0,
                footprint_depth_inches=depth,
                rules_footprint_polygon=display_geometry.footprint_polygon,
                display_geometry=display_geometry,
                walls=(
                    TerrainWallDefinition(
                        wall_id=f"{fixture_id}:{member_id}:wall",
                        center_x_inches=center_x_inches,
                        center_y_inches=center_y,
                        bottom_z_inches=0.0,
                        width_inches=0.2,
                        depth_inches=depth,
                        height_inches=6.0,
                    ),
                ),
                floors=(
                    TerrainFloorDefinition(
                        floor_id=f"{fixture_id}:{member_id}:floor",
                        center_x_inches=center_x_inches,
                        center_y_inches=center_y,
                        bottom_z_inches=0.0,
                        width_inches=1.0,
                        depth_inches=depth,
                        thickness_inches=0.1,
                    ),
                ),
                source_id="gw-11e-core-rules:other-concepts:visibility",
            )
        )
    return (features[0], features[1])


__all__ = ("one_millimeter_visibility_gap_ruins",)
