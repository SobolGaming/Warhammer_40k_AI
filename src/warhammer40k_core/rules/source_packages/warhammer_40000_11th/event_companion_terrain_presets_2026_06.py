from __future__ import annotations

from warhammer40k_core.core.missions import MissionPackError
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_areas import TerrainAreaFootprintTemplate
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeaturePreset,
    TerrainFloorTemplate,
    TerrainWallTemplate,
)


def build_default_ruins_feature_preset(
    *,
    template: TerrainAreaFootprintTemplate,
    terrain_feature_preset_id: str,
) -> TerrainFeaturePreset:
    """Build the source package's legacy full-area ruins preset."""
    if type(template) is not TerrainAreaFootprintTemplate:
        raise MissionPackError("Terrain feature preset source must be a footprint template.")
    width = template.bounding_width_inches
    depth = template.bounding_depth_inches
    interior_width = min(0.5, max(0.12, width - 2.0))
    interior_depth = min(0.5, max(0.12, depth - 2.0))
    return TerrainFeaturePreset(
        terrain_feature_preset_id=terrain_feature_preset_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_template_id=template.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=width,
        footprint_depth_inches=depth,
        local_rules_footprint_polygon=template.polygon_vertices_inches,
        local_display_geometry=TerrainDisplayGeometry(
            display_template_id=template.footprint_template_id,
            footprint_polygon=template.polygon_vertices_inches,
        ),
        walls=(
            TerrainWallTemplate(
                wall_id="center-wall",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=interior_width,
                depth_inches=0.12,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorTemplate(
                floor_id="ground-floor",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=interior_width,
                depth_inches=interior_depth,
                thickness_inches=0.12,
            ),
            TerrainFloorTemplate(
                floor_id="upper-floor",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=3.0,
                width_inches=interior_width,
                depth_inches=interior_depth,
                thickness_inches=0.12,
            ),
        ),
        source_id=f"{template.source_id}:terrain-feature-preset:ruins",
    )
