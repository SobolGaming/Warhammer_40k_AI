from __future__ import annotations

import math
from dataclasses import replace

from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    TerrainFeaturePreset,
    TerrainFloorTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.geometry.pose import Point3
from warhammer40k_core.geometry.terrain import ObstacleVolume
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_06_mission_pack,
)


def test_area_placed_terrain_feature_resolves_to_battlefield_coordinates() -> None:
    base_pack = warhammer_event_companion_2026_06_mission_pack()
    layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    layout = base_pack.battlefield_layout(layout_id)
    area = next(
        terrain_area
        for terrain_area in layout.terrain_areas
        if terrain_area.terrain_area_id == f"{layout_id}-6x4-east-midfield"
    )
    footprint_template = next(
        template
        for template in base_pack.terrain_area_footprint_templates
        if template.footprint_template_id == area.footprint_template_id
    )
    preset = TerrainFeaturePreset(
        terrain_feature_preset_id="test-ruins-on-6x4-area",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_template_id=footprint_template.footprint_template_id,
        footprint_width_inches=footprint_template.bounding_width_inches,
        footprint_depth_inches=footprint_template.bounding_depth_inches,
        display_geometry=TerrainDisplayGeometry(
            display_template_id=footprint_template.footprint_template_id,
            footprint_polygon=footprint_template.polygon_vertices_inches,
        ),
        walls=(
            TerrainWallTemplate(
                wall_id="center-wall",
                center_x_inches=1.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=2.5,
                depth_inches=0.25,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorTemplate(
                floor_id="ground-floor",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=footprint_template.bounding_width_inches,
                depth_inches=footprint_template.bounding_depth_inches,
                thickness_inches=0.12,
            ),
        ),
        source_id="test:terrain-feature-preset:ruins-on-6x4",
    )
    placement = TerrainFeatureAreaPlacement(
        feature_id="placed-east-midfield-ruin",
        terrain_area_id=area.terrain_area_id,
        terrain_feature_preset_id=preset.terrain_feature_preset_id,
        source_id="test:terrain-feature-placement:east-midfield",
    )
    placed_layout = replace(layout, terrain_feature_placements=(placement,))
    mission_pack = replace(
        base_pack,
        terrain_feature_presets=(preset,),
        battlefield_layouts=tuple(
            placed_layout
            if candidate.battlefield_layout_id == placed_layout.battlefield_layout_id
            else candidate
            for candidate in base_pack.battlefield_layouts
        ),
    )
    mission_pool_entry = next(
        entry
        for entry in mission_pack.mission_pool_entries
        if layout_id in entry.terrain_layout_ids
    )

    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=mission_pool_entry.mission_pool_entry_id,
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    feature = next(
        terrain_feature
        for terrain_feature in setup.terrain_features
        if terrain_feature.feature_id == placement.feature_id
    )
    wall = feature.walls[0]

    assert feature.display_geometry.footprint_polygon == area.footprint_polygon
    assert math.isclose(wall.center_x_inches, area.center_x_inches, abs_tol=1e-9)
    assert math.isclose(wall.center_y_inches, area.center_y_inches - 1.0, abs_tol=1e-9)
    assert wall.rotation_degrees == 270.0
    assert feature.wall_volumes()[0].blocks_line_segment(
        Point3(wall.center_x_inches - 2.0, wall.center_y_inches, 1.0),
        Point3(wall.center_x_inches + 2.0, wall.center_y_inches, 1.0),
    )


def test_rotated_obstacle_line_of_sight_uses_rotated_footprint_not_aabb() -> None:
    obstacle = ObstacleVolume(
        terrain_id="rotated-wall",
        bottom_center=Point3(0.0, 0.0, 0.0),
        width=6.0,
        depth=1.0,
        height=3.0,
        rotation_degrees=45.0,
    )

    assert obstacle.blocks_line_segment(Point3(-3.0, -3.0, 1.0), Point3(3.0, 3.0, 1.0))
    assert not obstacle.blocks_line_segment(Point3(0.0, 1.0, 1.0), Point3(0.0, 2.4, 1.0))
