"""Constructed opaque wall isolates visibility from range."""

from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


def blocking_wall() -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=20,
        center_y_inches=18,
        width_inches=0.2,
        depth_inches=34,
        display_template_id="constructed:section10:wall",
    )
    return TerrainFeatureDefinition(
        feature_id="constructed:section10:wall",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=20,
        footprint_center_y_inches=18,
        footprint_width_inches=0.2,
        footprint_depth_inches=34,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="opaque",
                center_x_inches=20,
                center_y_inches=18,
                bottom_z_inches=0,
                width_inches=0.2,
                depth_inches=34,
                height_inches=12,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=20,
                center_y_inches=18,
                bottom_z_inches=0,
                width_inches=0.2,
                depth_inches=34,
                thickness_inches=0.1,
            ),
        ),
    )
