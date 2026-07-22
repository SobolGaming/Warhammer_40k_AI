from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
)
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeaturePreset,
    TerrainFeatureTemplate,
    TerrainFloorTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.geometry.pose import GeometryError, Point3
from warhammer40k_core.geometry.terrain import (
    ObstacleVolume,
    TerrainFloorDefinition,
    TerrainFloorDefinitionPayload,
    TerrainSupportSurface,
    TerrainSupportSurfacePayload,
    TerrainVolumePayload,
    TerrainWallDefinition,
    TerrainWallDefinitionPayload,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


def test_event_companion_area_placed_terrain_features_resolve_from_source_data() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    layout = mission_pack.battlefield_layout(layout_id)
    area = next(
        terrain_area
        for terrain_area in layout.terrain_areas
        if terrain_area.terrain_area_id == f"{layout_id}-6x4-east-midfield"
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
        if terrain_feature.feature_id == area.terrain_area_id
    )
    center_wall = next(wall for wall in feature.walls if wall.wall_id == "center-wall")

    assert len(layout.terrain_feature_placements) == len(layout.terrain_areas)
    assert len(setup.terrain_features) == len(layout.terrain_areas)
    assert feature.feature_kind is TerrainFeatureKind.RUINS
    assert feature.display_geometry.footprint_polygon == area.footprint_polygon
    assert math.isclose(center_wall.center_x_inches, area.center_x_inches, abs_tol=1e-9)
    assert math.isclose(center_wall.center_y_inches, area.center_y_inches, abs_tol=1e-9)
    assert center_wall.rotation_degrees == 270.0
    assert feature.wall_volumes()[0].blocks_line_segment(
        Point3(center_wall.center_x_inches - 2.0, center_wall.center_y_inches, 1.0),
        Point3(center_wall.center_x_inches + 2.0, center_wall.center_y_inches, 1.0),
    )


def test_mirrored_asymmetric_preset_uses_terrain_area_local_transform_anchor() -> None:
    base_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    layout = base_pack.battlefield_layout(layout_id)
    area = next(
        terrain_area
        for terrain_area in layout.terrain_areas
        if terrain_area.terrain_area_id == f"{layout_id}-6x2-upper-center"
    )
    footprint_template = next(
        template
        for template in base_pack.terrain_area_footprint_templates
        if template.footprint_template_id == area.footprint_template_id
    )
    source_preset = next(
        preset
        for preset in base_pack.terrain_feature_presets
        if preset.footprint_template_id == area.footprint_template_id
    )
    custom_preset = TerrainFeaturePreset(
        terrain_feature_preset_id=source_preset.terrain_feature_preset_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_template_id=footprint_template.footprint_template_id,
        footprint_width_inches=footprint_template.bounding_width_inches,
        footprint_depth_inches=footprint_template.bounding_depth_inches,
        walls=(
            TerrainWallTemplate(
                wall_id="asymmetric-wall",
                center_x_inches=1.0,
                center_y_inches=0.25,
                bottom_z_inches=0.0,
                width_inches=0.25,
                depth_inches=1.5,
                height_inches=3.0,
                rotation_degrees=30.0,
            ),
        ),
        floors=(
            TerrainFloorTemplate(
                floor_id="ground-floor",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=footprint_template.bounding_width_inches - 2.0,
                depth_inches=footprint_template.bounding_depth_inches - 2.0,
                thickness_inches=0.12,
            ),
        ),
        source_id="test:terrain-feature-preset:asymmetric-6x2",
    )
    mission_pack = replace(
        base_pack,
        terrain_feature_presets=tuple(
            custom_preset
            if preset.terrain_feature_preset_id == custom_preset.terrain_feature_preset_id
            else preset
            for preset in base_pack.terrain_feature_presets
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
        if terrain_feature.feature_id == area.terrain_area_id
    )
    wall = feature.walls[0]
    mirror_anchor_x = footprint_template.polygon_vertices_inches[0].x_inches
    mirrored_local_x = (2.0 * mirror_anchor_x) - custom_preset.walls[0].center_x_inches

    assert feature.display_geometry.footprint_polygon == area.footprint_polygon
    assert math.isclose(
        wall.center_x_inches,
        area.center_x_inches + mirrored_local_x,
        abs_tol=1e-9,
    )
    assert math.isclose(
        wall.center_y_inches,
        area.center_y_inches + custom_preset.walls[0].center_y_inches,
        abs_tol=1e-9,
    )
    assert wall.rotation_degrees == 150.0


def test_mission_pack_rejects_area_placement_feature_kind_mismatch() -> None:
    base_pack = warhammer_event_companion_2026_07_mission_pack()
    source_preset = base_pack.terrain_feature_presets[0]
    mismatched_preset = replace(source_preset, feature_kind=TerrainFeatureKind.WOODS)

    with pytest.raises(MissionPackError, match="preset feature kind"):
        replace(
            base_pack,
            terrain_feature_presets=(
                mismatched_preset,
                *base_pack.terrain_feature_presets[1:],
            ),
        )


def test_mission_pack_rejects_area_placement_static_feature_id_collision() -> None:
    base_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    battlefield_layout = base_pack.battlefield_layout(layout_id)
    terrain_layout = base_pack.terrain_layout_template(layout_id)
    colliding_feature_id = battlefield_layout.terrain_feature_placements[0].feature_id
    static_feature = TerrainFeatureTemplate(
        feature_id=colliding_feature_id,
        feature_kind=TerrainFeatureKind.WOODS,
        footprint_center_x_inches=4.0,
        footprint_center_y_inches=4.0,
        footprint_width_inches=2.0,
        footprint_depth_inches=2.0,
        display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=4.0,
            center_y_inches=4.0,
            width_inches=2.0,
            depth_inches=2.0,
            display_template_id="test-static-feature",
        ),
        source_id="test:static-feature:id-collision",
    )
    drifted_terrain_layout = replace(terrain_layout, terrain_features=(static_feature,))

    with pytest.raises(MissionPackError, match="collide with static terrain feature IDs"):
        replace(
            base_pack,
            terrain_layout_templates=tuple(
                drifted_terrain_layout
                if candidate.terrain_layout_id == drifted_terrain_layout.terrain_layout_id
                else candidate
                for candidate in base_pack.terrain_layout_templates
            ),
        )


def test_area_placed_terrain_feature_payloads_round_trip_and_preserve_rotation() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    round_tripped_pack = MissionPackDefinition.from_payload(
        cast(
            MissionPackDefinitionPayload,
            json.loads(json.dumps(mission_pack.to_payload())),
        )
    )
    layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    mission_pool_entry = next(
        entry
        for entry in round_tripped_pack.mission_pool_entries
        if layout_id in entry.terrain_layout_ids
    )
    setup = MissionSetup.from_mission_pack(
        mission_pack=round_tripped_pack,
        mission_pool_entry_id=mission_pool_entry.mission_pool_entry_id,
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    round_tripped_setup = MissionSetup.from_payload(setup.to_payload())
    rotated_feature = next(
        feature
        for feature in round_tripped_setup.terrain_features
        if feature.feature_id == f"{layout_id}-6x4-east-midfield"
    )
    wall_rotations = tuple(wall.rotation_degrees for wall in rotated_feature.walls)
    floor_rotations = tuple(floor.rotation_degrees for floor in rotated_feature.floors)
    volume_rotations = tuple(
        volume.rotation_degrees for volume in rotated_feature.terrain_volumes()
    )
    surface_rotations = tuple(
        surface.rotation_degrees
        for surface in rotated_feature.support_surfaces(no_overhang_required=True)
    )

    assert round_tripped_pack.to_payload() == mission_pack.to_payload()
    assert round_tripped_setup.to_payload() == setup.to_payload()
    assert wall_rotations == (270.0,)
    assert floor_rotations == (270.0, 270.0)
    assert volume_rotations == (270.0, 270.0, 270.0)
    assert surface_rotations == (270.0, 270.0)


def test_rotation_payload_fields_are_required_with_typed_errors() -> None:
    obstacle_payload = dict(
        ObstacleVolume(
            terrain_id="rotated-wall",
            bottom_center=Point3(0.0, 0.0, 0.0),
            width=6.0,
            depth=1.0,
            height=3.0,
            rotation_degrees=45.0,
        ).to_payload()
    )
    wall_payload = dict(
        TerrainWallDefinition(
            wall_id="wall",
            center_x_inches=0.0,
            center_y_inches=0.0,
            bottom_z_inches=0.0,
            width_inches=1.0,
            depth_inches=1.0,
            height_inches=3.0,
            rotation_degrees=45.0,
        ).to_payload()
    )
    floor_payload = dict(
        TerrainFloorDefinition(
            floor_id="floor",
            center_x_inches=0.0,
            center_y_inches=0.0,
            bottom_z_inches=0.0,
            width_inches=1.0,
            depth_inches=1.0,
            thickness_inches=0.12,
            rotation_degrees=45.0,
        ).to_payload()
    )
    surface_payload = dict(
        TerrainSupportSurface(
            surface_id="surface",
            terrain_feature_id="feature",
            z_inches=0.0,
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=1.0,
            depth_inches=1.0,
            rotation_degrees=45.0,
            no_overhang_required=True,
        ).to_payload()
    )

    obstacle_payload.pop("rotation_degrees")
    wall_payload.pop("rotation_degrees")
    floor_payload.pop("rotation_degrees")
    surface_payload.pop("rotation_degrees")

    with pytest.raises(GeometryError, match="rotation_degrees"):
        ObstacleVolume.from_payload(cast(TerrainVolumePayload, obstacle_payload))
    with pytest.raises(GeometryError, match="rotation_degrees"):
        TerrainWallDefinition.from_payload(cast(TerrainWallDefinitionPayload, wall_payload))
    with pytest.raises(GeometryError, match="rotation_degrees"):
        TerrainFloorDefinition.from_payload(cast(TerrainFloorDefinitionPayload, floor_payload))
    with pytest.raises(GeometryError, match="rotation_degrees"):
        TerrainSupportSurface.from_payload(cast(TerrainSupportSurfacePayload, surface_payload))


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
