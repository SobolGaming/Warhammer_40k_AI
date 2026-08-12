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
from warhammer40k_core.core.terrain_display import (
    TerrainDisplayGeometry,
    canonical_terrain_area_transform_coordinate,
    canonical_terrain_feature_transform_coordinate,
)
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    TerrainFeatureLocalTransform,
    TerrainFeaturePreset,
    TerrainFeatureTemplate,
    TerrainFloorTemplate,
    TerrainLayoutError,
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
    area_placements = tuple(
        placement
        for placement in layout.terrain_feature_placements
        if placement.terrain_area_id == area.terrain_area_id
    )
    feature = next(
        terrain_feature
        for terrain_feature in setup.terrain_features
        if terrain_feature.feature_id == f"{area.terrain_area_id}-component-01"
    )
    solid_body = next(wall for wall in feature.walls if wall.wall_id == "solid-body")

    assert len(layout.terrain_feature_placements) == 29
    assert len(setup.terrain_features) == len(layout.terrain_feature_placements)
    assert len(area_placements) == 2
    assert feature.feature_kind is TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
    assert feature.display_geometry.footprint_polygon == feature.rules_footprint_polygon
    assert feature.display_geometry.footprint_polygon != area.footprint_polygon
    assert math.isclose(solid_body.center_x_inches, 34.3, abs_tol=1e-9)
    assert math.isclose(solid_body.center_y_inches, 25.0, abs_tol=1e-9)
    assert math.isclose(feature.footprint_width_inches, 1.4, abs_tol=1e-9)
    assert math.isclose(feature.footprint_depth_inches, 4.25, abs_tol=1e-9)
    assert solid_body.rotation_degrees == 90.0
    assert feature.wall_volumes()[0].blocks_line_segment(
        Point3(solid_body.center_x_inches - 2.0, solid_body.center_y_inches, 1.0),
        Point3(solid_body.center_x_inches + 2.0, solid_body.center_y_inches, 1.0),
    )


def test_source_terrain_transforms_publish_six_decimal_canonical_coordinates() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "take-and-hold-vs-purge-the-foe-layout-3"
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
        if terrain_feature.feature_id
        == "take-and-hold-vs-purge-the-foe-layout-3-terrain-area-03-component-01"
    )
    wall = next(candidate for candidate in feature.walls if candidate.wall_id == "long-solid-arm")

    assert wall.center_x_inches == 31.088806
    assert wall.center_y_inches == 46.891621
    assert canonical_terrain_feature_transform_coordinate(31.088806397420253) == 31.088806
    assert canonical_terrain_feature_transform_coordinate(31.08880639742025) == 31.088806
    assert canonical_terrain_feature_transform_coordinate(-1e-15) == 0.0
    assert canonical_terrain_area_transform_coordinate(31.088806397420253) == 31.088806397
    assert canonical_terrain_area_transform_coordinate(31.08880639742025) == 31.088806397
    assert all(
        coordinate == round(coordinate, 9)
        for layout in mission_pack.battlefield_layouts
        for area in layout.terrain_areas
        for point in area.footprint_polygon
        for coordinate in (point.x_inches, point.y_inches)
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
    source_placement = next(
        placement
        for placement in layout.terrain_feature_placements
        if placement.terrain_area_id == area.terrain_area_id
    )
    custom_preset_id = "test-asymmetric-6x2"
    custom_preset = TerrainFeaturePreset(
        terrain_feature_preset_id=custom_preset_id,
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_template_id=footprint_template.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=footprint_template.bounding_width_inches,
        footprint_depth_inches=footprint_template.bounding_depth_inches,
        local_rules_footprint_polygon=footprint_template.polygon_vertices_inches,
        local_display_geometry=TerrainDisplayGeometry(
            display_template_id=footprint_template.footprint_template_id,
            footprint_polygon=footprint_template.polygon_vertices_inches,
        ),
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
    custom_placement = replace(
        source_placement,
        terrain_feature_preset_id=custom_preset_id,
        local_offset_x_inches=0.0,
        local_offset_y_inches=0.0,
        local_rotation_degrees=0.0,
        local_transform=TerrainFeatureLocalTransform.IDENTITY,
        source_id="test:terrain-feature-placement:asymmetric-6x2",
    )
    custom_layout = replace(
        layout,
        terrain_feature_placements=tuple(
            custom_placement if placement.feature_id == source_placement.feature_id else placement
            for placement in layout.terrain_feature_placements
        ),
    )
    mission_pack = replace(
        base_pack,
        terrain_feature_presets=(*base_pack.terrain_feature_presets, custom_preset),
        battlefield_layouts=tuple(
            custom_layout
            if candidate.battlefield_layout_id == custom_layout.battlefield_layout_id
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
        if terrain_feature.feature_id == source_placement.feature_id
    )
    wall = feature.walls[0]
    mirror_anchor_x = footprint_template.polygon_vertices_inches[0].x_inches
    mirrored_local_x = (2.0 * mirror_anchor_x) - custom_preset.walls[0].center_x_inches

    assert tuple(
        (
            point.x_inches,
            point.y_inches,
        )
        for point in feature.display_geometry.footprint_polygon
    ) == tuple(
        (
            canonical_terrain_feature_transform_coordinate(point.x_inches),
            canonical_terrain_feature_transform_coordinate(point.y_inches),
        )
        for point in area.footprint_polygon
    )
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


def test_mission_pack_uses_component_kind_independently_of_coarse_area_kind() -> None:
    base_pack = warhammer_event_companion_2026_07_mission_pack()
    source_layout = base_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    source_placement = source_layout.terrain_feature_placements[0]
    source_preset = next(
        preset
        for preset in base_pack.terrain_feature_presets
        if preset.terrain_feature_preset_id == source_placement.terrain_feature_preset_id
    )
    woods_component_preset = replace(source_preset, feature_kind=TerrainFeatureKind.WOODS)
    mission_pack = replace(
        base_pack,
        terrain_feature_presets=tuple(
            woods_component_preset
            if preset.terrain_feature_preset_id == woods_component_preset.terrain_feature_preset_id
            else preset
            for preset in base_pack.terrain_feature_presets
        ),
    )
    layout = mission_pack.battlefield_layout(source_layout.battlefield_layout_id)
    placement = next(
        candidate
        for candidate in layout.terrain_feature_placements
        if candidate.terrain_feature_preset_id == woods_component_preset.terrain_feature_preset_id
    )
    mission_pool_entry = next(
        entry
        for entry in mission_pack.mission_pool_entries
        if layout.battlefield_layout_id in entry.terrain_layout_ids
    )

    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=mission_pool_entry.mission_pool_entry_id,
        terrain_layout_id=layout.terrain_layout_id,
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )

    feature = next(
        candidate
        for candidate in setup.terrain_features
        if candidate.feature_id == placement.feature_id
    )
    assert feature.feature_kind is TerrainFeatureKind.WOODS


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
        rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=4.0,
            center_y_inches=4.0,
            width_inches=2.0,
            depth_inches=2.0,
            display_template_id=None,
        ).footprint_polygon,
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


def test_mission_pack_rejects_component_transform_outside_referenced_area() -> None:
    base_pack = warhammer_event_companion_2026_07_mission_pack()
    layout = base_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    source_placement = layout.terrain_feature_placements[0]
    drifted_placement = replace(source_placement, local_offset_x_inches=100.0)
    drifted_layout = replace(
        layout,
        terrain_feature_placements=(
            drifted_placement,
            *layout.terrain_feature_placements[1:],
        ),
    )

    with pytest.raises(MissionPackError, match="placement footprint must fit"):
        replace(
            base_pack,
            battlefield_layouts=tuple(
                drifted_layout
                if candidate.battlefield_layout_id == drifted_layout.battlefield_layout_id
                else candidate
                for candidate in base_pack.battlefield_layouts
            ),
        )


def test_component_rules_polygon_is_required_by_source_preset_loader() -> None:
    source_preset = warhammer_event_companion_2026_07_mission_pack().terrain_feature_presets[0]
    payload = dict(source_preset.to_payload())
    payload.pop("local_rules_footprint_polygon")

    with pytest.raises(TerrainLayoutError, match="local_rules_footprint_polygon"):
        TerrainFeaturePreset.from_payload(payload)


def test_component_transform_fields_are_required_by_placement_loader() -> None:
    payload = dict(
        TerrainFeatureAreaPlacement(
            feature_id="strict-feature",
            terrain_area_id="strict-area",
            terrain_feature_preset_id="strict-preset",
            local_offset_x_inches=0.0,
            local_offset_y_inches=0.0,
            local_rotation_degrees=90.0,
            local_transform=TerrainFeatureLocalTransform.MIRROR_Y_AXIS,
            source_id="test:strict-feature-placement",
        ).to_payload()
    )
    payload.pop("local_rotation_degrees")

    with pytest.raises(TerrainLayoutError, match="local_rotation_degrees"):
        TerrainFeatureAreaPlacement.from_payload(payload)


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
        if feature.feature_id == f"{layout_id}-8x11-5-polygon-central-north-component-02"
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
    assert wall_rotations == (270.0, 0.0, 270.0, 0.0, 270.0, 0.0)
    assert floor_rotations == (270.0, 270.0, 270.0)
    assert volume_rotations == (270.0, 270.0, 0.0, 270.0, 270.0, 0.0, 270.0, 270.0, 0.0)
    assert surface_rotations == (270.0, 270.0, 270.0)


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
