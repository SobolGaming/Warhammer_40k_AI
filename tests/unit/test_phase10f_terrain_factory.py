from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    SymmetryAxis,
    TerrainAreaClassification,
    TerrainAreaFootprintTemplate,
    TerrainAreaLocalTransform,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    TerrainFeatureLocalTransform,
    TerrainFeaturePreset,
    TerrainFloorTemplate,
    TerrainLayoutTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.engine.battlefield_state import (
    PlacementError,
    SpatialIndexState,
    SpatialIndexStatePayload,
)
from warhammer40k_core.engine.mission_setup import instantiate_terrain_layout_template
from warhammer40k_core.engine.terrain_feature_factory import (
    TerrainFeatureFactory,
    TerrainFeatureFactoryError,
)
from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)
from warhammer40k_core.geometry.terrain_factory import (
    RUINS_FLOOR_HEIGHT_INCHES,
    RUINS_FLOOR_THICKNESS_INCHES,
    RUINS_WALL_THICKNESS_INCHES,
    TerrainFactory,
)


def test_empty_battlefield_terrain_fixture_round_trips_without_object_reprs() -> None:
    features = TerrainFactory.empty_battlefield()

    payload = TerrainFactory.to_payloads(features)
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert TerrainFactory.from_payloads(cast(list[TerrainFeatureDefinitionPayload], decoded)) == ()

    spatial_state = SpatialIndexState.from_terrain_features(features)
    spatial_payload = spatial_state.to_payload()
    spatial_encoded = json.dumps(spatial_payload, sort_keys=True)
    spatial_decoded = json.loads(spatial_encoded)

    assert "<" not in spatial_encoded
    assert "object at 0x" not in spatial_encoded
    assert spatial_state.terrain_revision == 0
    assert spatial_state.terrain_feature_ids == ()
    assert spatial_state.terrain_volume_ids == ()
    assert (
        SpatialIndexState.from_payload(cast(SpatialIndexStatePayload, spatial_decoded))
        == spatial_state
    )


def test_ruins_fixture_round_trips_without_object_reprs() -> None:
    features = TerrainFactory.ruins_fixture()

    payload = TerrainFactory.to_payloads(features)
    encoded = json.dumps(payload, sort_keys=True)
    decoded = json.loads(encoded)
    round_tripped = TerrainFactory.from_payloads(
        cast(list[TerrainFeatureDefinitionPayload], decoded)
    )

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert round_tripped == features
    assert len(round_tripped) == 1
    assert round_tripped[0].feature_kind is TerrainFeatureKind.RUINS
    assert round_tripped[0].walls
    assert round_tripped[0].floors


def test_rules_footprint_polygon_is_required_by_runtime_terrain_loader() -> None:
    payload = dict(TerrainFactory.ruins_fixture()[0].to_payload())
    payload.pop("rules_footprint_polygon")

    with pytest.raises(GeometryError, match="rules_footprint_polygon"):
        TerrainFeatureDefinition.from_payload(payload)


def test_terrain_wall_and_floor_dimensions_are_deterministic() -> None:
    feature = TerrainFactory.ruins_fixture()[0]
    east_wall, north_wall = feature.walls
    ground_floor, upper_floor = feature.floors

    assert feature.feature_id == "ruin-alpha"
    assert feature.footprint_width_inches == 12.0
    assert feature.footprint_depth_inches == 6.0
    assert east_wall.width_inches == RUINS_WALL_THICKNESS_INCHES
    assert east_wall.depth_inches == 6.0
    assert east_wall.height_inches == RUINS_FLOOR_HEIGHT_INCHES
    assert north_wall.width_inches == 12.0
    assert north_wall.depth_inches == RUINS_WALL_THICKNESS_INCHES
    assert ground_floor.width_inches == 12.0
    assert ground_floor.depth_inches == 6.0
    assert ground_floor.thickness_inches == RUINS_FLOOR_THICKNESS_INCHES
    assert upper_floor.bottom_z_inches == RUINS_FLOOR_HEIGHT_INCHES
    assert upper_floor.width_inches == 8.0
    assert upper_floor.depth_inches == 4.0


def test_invalid_terrain_geometry_fails_fast() -> None:
    with pytest.raises(GeometryError):
        TerrainWallDefinition(
            wall_id="bad-wall",
            center_x_inches=0.0,
            center_y_inches=0.0,
            bottom_z_inches=0.0,
            width_inches=0.0,
            depth_inches=1.0,
            height_inches=3.0,
        )

    with pytest.raises(GeometryError):
        TerrainFeatureDefinition(
            feature_id="terrain:ruin-alpha",
            feature_kind=TerrainFeatureKind.RUINS,
            footprint_center_x_inches=0.0,
            footprint_center_y_inches=0.0,
            footprint_width_inches=12.0,
            footprint_depth_inches=6.0,
            rules_footprint_polygon=_display_geometry(
                center_x_inches=0.0,
                center_y_inches=0.0,
                width_inches=12.0,
                depth_inches=6.0,
            ).footprint_polygon,
            display_geometry=_display_geometry(
                center_x_inches=0.0,
                center_y_inches=0.0,
                width_inches=12.0,
                depth_inches=6.0,
            ),
            walls=TerrainFactory.ruins_fixture()[0].walls,
            floors=TerrainFactory.ruins_fixture()[0].floors,
        )

    wall = TerrainFactory.ruins_fixture()[0].walls[0]
    floor = TerrainFactory.ruins_fixture()[0].floors[0]
    with pytest.raises(GeometryError):
        TerrainFeatureDefinition(
            feature_id="ruin-duplicate-wall",
            feature_kind=TerrainFeatureKind.RUINS,
            footprint_center_x_inches=22.0,
            footprint_center_y_inches=30.0,
            footprint_width_inches=12.0,
            footprint_depth_inches=6.0,
            rules_footprint_polygon=_display_geometry(
                center_x_inches=22.0,
                center_y_inches=30.0,
                width_inches=12.0,
                depth_inches=6.0,
            ).footprint_polygon,
            display_geometry=_display_geometry(
                center_x_inches=22.0,
                center_y_inches=30.0,
                width_inches=12.0,
                depth_inches=6.0,
            ),
            walls=(wall, wall),
            floors=(floor,),
        )

    outside_wall = TerrainWallDefinition(
        wall_id="outside-wall",
        center_x_inches=100.0,
        center_y_inches=30.0,
        bottom_z_inches=0.0,
        width_inches=RUINS_WALL_THICKNESS_INCHES,
        depth_inches=6.0,
        height_inches=3.0,
    )
    with pytest.raises(GeometryError):
        TerrainFeatureDefinition(
            feature_id="ruin-outside-wall",
            feature_kind=TerrainFeatureKind.RUINS,
            footprint_center_x_inches=22.0,
            footprint_center_y_inches=30.0,
            footprint_width_inches=12.0,
            footprint_depth_inches=6.0,
            rules_footprint_polygon=_display_geometry(
                center_x_inches=22.0,
                center_y_inches=30.0,
                width_inches=12.0,
                depth_inches=6.0,
            ).footprint_polygon,
            display_geometry=_display_geometry(
                center_x_inches=22.0,
                center_y_inches=30.0,
                width_inches=12.0,
                depth_inches=6.0,
            ),
            walls=(outside_wall,),
            floors=(floor,),
        )

    with pytest.raises(GeometryError):
        TerrainFloorDefinition(
            floor_id="bad-floor",
            center_x_inches=0.0,
            center_y_inches=0.0,
            bottom_z_inches=-1.0,
            width_inches=1.0,
            depth_inches=1.0,
            thickness_inches=RUINS_FLOOR_THICKNESS_INCHES,
        )

    with pytest.raises(GeometryError, match="rules_footprint_polygon"):
        TerrainFeatureDefinition(
            feature_id="bad-rules-footprint",
            feature_kind=TerrainFeatureKind.WOODS,
            footprint_center_x_inches=0.0,
            footprint_center_y_inches=0.0,
            footprint_width_inches=2.0,
            footprint_depth_inches=2.0,
            rules_footprint_polygon=(
                TerrainDisplayPoint(-1.0, -1.0),
                TerrainDisplayPoint(2.0, -1.0),
                TerrainDisplayPoint(0.0, 1.0),
            ),
            display_geometry=_display_geometry(
                center_x_inches=0.0,
                center_y_inches=0.0,
                width_inches=2.0,
                depth_inches=2.0,
            ),
        )


def test_terrain_revision_changes_when_terrain_changes() -> None:
    empty_state = SpatialIndexState.from_terrain_features(TerrainFactory.empty_battlefield())
    ruins_state = SpatialIndexState.from_terrain_features(TerrainFactory.ruins_fixture())
    alternate_ruins_state = SpatialIndexState.from_terrain_features(
        TerrainFactory.ruins_fixture(feature_id="ruin-beta")
    )

    assert empty_state.terrain_revision != ruins_state.terrain_revision
    assert ruins_state.terrain_revision != alternate_ruins_state.terrain_revision
    assert empty_state.los_cache_key() != ruins_state.los_cache_key()
    assert ruins_state.pathing_cache_key() != alternate_ruins_state.pathing_cache_key()


def test_spatial_index_state_can_be_rebuilt_deterministically() -> None:
    features = TerrainFactory.ruins_fixture()
    spatial_state = SpatialIndexState.from_terrain_features(features)

    first_index = spatial_state.rebuild_spatial_index(features)
    second_index = SpatialIndexState.from_payload(spatial_state.to_payload()).rebuild_spatial_index(
        features
    )

    assert first_index.to_payload() == second_index.to_payload()
    assert first_index.generation == spatial_state.terrain_revision
    assert (
        tuple(volume.terrain_id for volume in first_index.terrain)
        == spatial_state.terrain_volume_ids
    )
    assert any(volume.blocks_line_of_sight for volume in first_index.terrain)
    assert any(not volume.blocks_line_of_sight for volume in first_index.terrain)

    with pytest.raises(PlacementError):
        spatial_state.rebuild_spatial_index(TerrainFactory.empty_battlefield())


def test_spatial_cache_keys_ignore_display_only_terrain_geometry_changes() -> None:
    base_feature = TerrainFactory.ruins_fixture()[0]
    display_only_change = TerrainFeatureDefinition(
        feature_id=base_feature.feature_id,
        feature_kind=base_feature.feature_kind,
        classification=base_feature.classification,
        footprint_center_x_inches=base_feature.footprint_center_x_inches,
        footprint_center_y_inches=base_feature.footprint_center_y_inches,
        footprint_width_inches=base_feature.footprint_width_inches,
        footprint_depth_inches=base_feature.footprint_depth_inches,
        rules_footprint_polygon=base_feature.rules_footprint_polygon,
        display_geometry=TerrainDisplayGeometry(
            display_template_id="ruins_display_only_diamond",
            footprint_polygon=(
                _display_point(
                    base_feature.footprint_center_x_inches,
                    base_feature.footprint_center_y_inches
                    - (base_feature.footprint_depth_inches / 2.0),
                ),
                _display_point(
                    base_feature.footprint_center_x_inches
                    + (base_feature.footprint_width_inches / 2.0),
                    base_feature.footprint_center_y_inches,
                ),
                _display_point(
                    base_feature.footprint_center_x_inches,
                    base_feature.footprint_center_y_inches
                    + (base_feature.footprint_depth_inches / 2.0),
                ),
                _display_point(
                    base_feature.footprint_center_x_inches
                    - (base_feature.footprint_width_inches / 2.0),
                    base_feature.footprint_center_y_inches,
                ),
            ),
        ),
        walls=base_feature.walls,
        floors=base_feature.floors,
        source_id=base_feature.source_id,
    )

    base_state = SpatialIndexState.from_terrain_features((base_feature,))
    changed_state = SpatialIndexState.from_terrain_features((display_only_change,))

    assert changed_state.terrain_revision == base_state.terrain_revision
    assert changed_state.los_cache_key() == base_state.los_cache_key()
    assert changed_state.pathing_cache_key() == base_state.pathing_cache_key()


def test_spatial_cache_keys_include_terrain_feature_classification() -> None:
    base_feature = TerrainFactory.ruins_fixture()[0]
    classification_change = replace(
        base_feature,
        classification=TerrainAreaClassification.LIGHT,
    )

    base_state = SpatialIndexState.from_terrain_features((base_feature,))
    changed_state = SpatialIndexState.from_terrain_features((classification_change,))

    assert changed_state.terrain_revision != base_state.terrain_revision
    assert changed_state.los_cache_key() != base_state.los_cache_key()
    assert changed_state.pathing_cache_key() != base_state.pathing_cache_key()
    assert classification_change.to_rules_geometry_payload()["classification"] == "light"


def test_spatial_cache_keys_include_exact_rules_footprint_polygon() -> None:
    base_feature = TerrainFactory.ruins_fixture()[0]
    exact_polygon_change = replace(
        base_feature,
        rules_footprint_polygon=(
            _display_point(
                base_feature.footprint_center_x_inches,
                base_feature.footprint_center_y_inches
                - (base_feature.footprint_depth_inches / 2.0),
            ),
            _display_point(
                base_feature.footprint_center_x_inches
                + (base_feature.footprint_width_inches / 2.0),
                base_feature.footprint_center_y_inches,
            ),
            _display_point(
                base_feature.footprint_center_x_inches,
                base_feature.footprint_center_y_inches
                + (base_feature.footprint_depth_inches / 2.0),
            ),
            _display_point(
                base_feature.footprint_center_x_inches
                - (base_feature.footprint_width_inches / 2.0),
                base_feature.footprint_center_y_inches,
            ),
        ),
    )

    base_state = SpatialIndexState.from_terrain_features((base_feature,))
    changed_state = SpatialIndexState.from_terrain_features((exact_polygon_change,))

    assert changed_state.terrain_revision != base_state.terrain_revision
    assert changed_state.los_cache_key() != base_state.los_cache_key()
    assert changed_state.pathing_cache_key() != base_state.pathing_cache_key()
    assert (
        exact_polygon_change.to_rules_geometry_payload()["rules_footprint_polygon"]
        != base_feature.to_rules_geometry_payload()["rules_footprint_polygon"]
    )


def test_area_factory_composes_mixed_dense_ruins_and_light_obstacle_features() -> None:
    footprint_template = _component_area_template()
    area = _component_area(
        footprint_template,
        classification=TerrainAreaClassification.DENSE,
        rotation_degrees=90.0,
        local_transform=TerrainAreaLocalTransform.MIRROR_Y_AXIS,
    )
    ruins_preset = _three_level_ruins_component_preset(footprint_template)
    light_preset = _light_obstacle_component_preset(footprint_template)

    ruins = TerrainFeatureFactory.from_area_placement(
        area=area,
        footprint_template=footprint_template,
        preset=ruins_preset,
        terrain_area_group=(area,),
        placement=_component_placement(
            area=area,
            preset=ruins_preset,
            feature_id="mixed-area-ruins",
        ),
    )
    light = TerrainFeatureFactory.from_area_placement(
        area=area,
        footprint_template=footprint_template,
        preset=light_preset,
        terrain_area_group=(area,),
        placement=_component_placement(
            area=area,
            preset=light_preset,
            feature_id="mixed-area-light-obstacle",
        ),
    )

    assert ruins.feature_kind is TerrainFeatureKind.RUINS
    assert light.feature_kind is TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
    assert ruins.display_geometry.footprint_polygon != area.footprint_polygon
    assert light.display_geometry.footprint_polygon != area.footprint_polygon
    assert ruins.display_geometry.footprint_polygon != light.display_geometry.footprint_polygon
    assert tuple(floor.bottom_z_inches for floor in ruins.floors) == (0.0, 3.0, 6.0)
    assert tuple(wall.bottom_z_inches for wall in ruins.walls) == (0.0, 3.0, 6.0)
    assert tuple(wall.height_inches for wall in ruins.walls) == (3.0, 3.0, 2.0)
    assert light.walls[0].height_inches == 2.0
    assert light.wall_volumes()[0].top_z_inches() == 2.0
    assert {ruins.feature_id, light.feature_id} == {
        "mixed-area-ruins",
        "mixed-area-light-obstacle",
    }


def test_layout_instantiation_allows_multiple_typed_features_in_one_terrain_area() -> None:
    footprint_template = _component_area_template()
    area = _component_area(
        footprint_template,
        classification=TerrainAreaClassification.DENSE,
        rotation_degrees=0.0,
        local_transform=TerrainAreaLocalTransform.IDENTITY,
    )
    ruins_preset = _three_level_ruins_component_preset(footprint_template)
    light_preset = _light_obstacle_component_preset(footprint_template)
    layout = TerrainLayoutTemplate(
        terrain_layout_id="mixed-component-layout",
        name="Mixed component layout",
        battlefield_width_inches=44.0,
        battlefield_depth_inches=60.0,
        terrain_features=(),
        source_id="test:event-companion:mixed-component-layout",
    )

    features = instantiate_terrain_layout_template(
        layout,
        terrain_areas=(area,),
        terrain_area_footprint_templates=(footprint_template,),
        terrain_feature_presets=(ruins_preset, light_preset),
        terrain_feature_placements=(
            _component_placement(
                area=area,
                preset=ruins_preset,
                feature_id="mixed-area-ruins",
            ),
            _component_placement(
                area=area,
                preset=light_preset,
                feature_id="mixed-area-light-obstacle",
            ),
        ),
    )

    assert tuple(feature.feature_id for feature in features) == (
        "mixed-area-light-obstacle",
        "mixed-area-ruins",
    )
    assert tuple(feature.feature_kind for feature in features) == (
        TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        TerrainFeatureKind.RUINS,
    )


def test_area_factory_rotates_and_mirrors_asymmetric_component_geometry() -> None:
    footprint_template = _component_area_template()
    area = _component_area(
        footprint_template,
        classification=TerrainAreaClassification.DENSE,
        rotation_degrees=90.0,
        local_transform=TerrainAreaLocalTransform.MIRROR_Y_AXIS,
    )
    preset = _dense_non_ruin_component_preset(footprint_template)

    feature = TerrainFeatureFactory.from_area_placement(
        area=area,
        footprint_template=footprint_template,
        preset=preset,
        terrain_area_group=(area,),
        placement=_component_placement(
            area=area,
            preset=preset,
            feature_id="mirrored-dense-obstacle",
        ),
    )
    wall = feature.walls[0]

    assert feature.feature_kind is TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
    assert math.isclose(wall.center_x_inches, 22.0, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(wall.center_y_inches, 18.0, rel_tol=0.0, abs_tol=1e-9)
    assert wall.rotation_degrees == 270.0
    assert wall.height_inches == 4.0


def test_area_factory_applies_source_component_offset_rotation_and_mirror() -> None:
    footprint_template = _component_area_template()
    area = _component_area(
        footprint_template,
        classification=TerrainAreaClassification.DENSE,
        rotation_degrees=90.0,
        local_transform=TerrainAreaLocalTransform.MIRROR_Y_AXIS,
    )
    preset = _dense_non_ruin_component_preset(footprint_template)

    feature = TerrainFeatureFactory.from_area_placement(
        area=area,
        footprint_template=footprint_template,
        preset=preset,
        terrain_area_group=(area,),
        placement=_component_placement(
            area=area,
            preset=preset,
            feature_id="source-transformed-dense-obstacle",
            local_offset_x_inches=1.0,
            local_offset_y_inches=2.0,
            local_rotation_degrees=90.0,
            local_transform=TerrainFeatureLocalTransform.MIRROR_Y_AXIS,
        ),
    )

    wall = feature.walls[0]
    assert math.isclose(wall.center_x_inches, 20.0, rel_tol=0.0, abs_tol=1e-9)
    assert math.isclose(wall.center_y_inches, 17.0, rel_tol=0.0, abs_tol=1e-9)
    assert wall.rotation_degrees == 0.0
    assert tuple(
        (round(x_inches, 9), round(y_inches, 9))
        for x_inches, y_inches in feature.rules_footprint_points()
    ) == (
        (18.5, 16.0),
        (21.5, 16.0),
        (21.5, 18.0),
        (18.5, 18.0),
    )


def test_area_factory_rejects_component_outside_area_and_reference_drift() -> None:
    footprint_template = _component_area_template()
    area = _component_area(
        footprint_template,
        classification=TerrainAreaClassification.LIGHT,
        rotation_degrees=0.0,
        local_transform=TerrainAreaLocalTransform.IDENTITY,
    )
    preset = _light_obstacle_component_preset(footprint_template)
    placement = _component_placement(
        area=area,
        preset=preset,
        feature_id="strict-light-obstacle",
    )

    with pytest.raises(TerrainFeatureFactoryError, match="different area"):
        TerrainFeatureFactory.from_area_placement(
            area=area,
            footprint_template=footprint_template,
            preset=preset,
            terrain_area_group=(area,),
            placement=TerrainFeatureAreaPlacement(
                feature_id=placement.feature_id,
                terrain_area_id="drifted-area",
                terrain_feature_preset_id=placement.terrain_feature_preset_id,
                local_offset_x_inches=placement.local_offset_x_inches,
                local_offset_y_inches=placement.local_offset_y_inches,
                local_rotation_degrees=placement.local_rotation_degrees,
                local_transform=placement.local_transform,
                source_id=placement.source_id,
            ),
        )

    outside_preset = TerrainFeaturePreset(
        terrain_feature_preset_id="outside-component",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        footprint_template_id=footprint_template.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=3.0,
        footprint_depth_inches=2.0,
        local_rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=3.0,
            depth_inches=2.0,
            display_template_id=None,
        ).footprint_polygon,
        local_display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=3.0,
            depth_inches=2.0,
            display_template_id="outside-component-display",
        ),
        walls=(
            TerrainWallTemplate(
                wall_id="outside-body",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=3.0,
                depth_inches=2.0,
                height_inches=2.0,
            ),
        ),
        source_id="test:event-companion:outside-component",
    )
    with pytest.raises(TerrainFeatureFactoryError, match="fit within"):
        TerrainFeatureFactory.from_area_placement(
            area=area,
            footprint_template=footprint_template,
            preset=outside_preset,
            terrain_area_group=(area,),
            placement=_component_placement(
                area=area,
                preset=outside_preset,
                feature_id="outside-component-feature",
                local_offset_x_inches=5.5,
            ),
        )


def test_area_factory_accepts_component_across_one_logical_terrain_area_seam() -> None:
    footprint_template = _component_area_template()
    logical_area_id = "event-logical-component-area"
    first_area = PlacedTerrainArea.from_template(
        terrain_area_id="event-component-area-west",
        logical_terrain_area_id=logical_area_id,
        template=footprint_template,
        terrain_feature_kind="ruins",
        classification=TerrainAreaClassification.MIXED,
        center_x_inches=16.0,
        center_y_inches=30.0,
        rotation_degrees=0.0,
        source_layout_id="event-layout-a",
        source_id="test:event-companion:event-layout-a:component-area-west",
    )
    second_area = PlacedTerrainArea.from_template(
        terrain_area_id="event-component-area-east",
        logical_terrain_area_id=logical_area_id,
        template=footprint_template,
        terrain_feature_kind="ruins",
        classification=TerrainAreaClassification.MIXED,
        center_x_inches=28.0,
        center_y_inches=30.0,
        rotation_degrees=0.0,
        source_layout_id="event-layout-a",
        source_id="test:event-companion:event-layout-a:component-area-east",
    )
    preset = _light_obstacle_component_preset(footprint_template)

    feature = TerrainFeatureFactory.from_area_placement(
        area=first_area,
        footprint_template=footprint_template,
        preset=preset,
        placement=_component_placement(
            area=first_area,
            preset=preset,
            feature_id="seam-spanning-light-obstacle",
            local_offset_x_inches=6.0,
        ),
        terrain_area_group=(first_area, second_area),
    )

    assert feature.rules_footprint_points() == (
        (20.0, 29.0),
        (24.0, 29.0),
        (24.0, 31.0),
        (20.0, 31.0),
    )


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _display_point(x_inches: float, y_inches: float) -> TerrainDisplayPoint:
    return TerrainDisplayPoint(x_inches=x_inches, y_inches=y_inches)


def _component_area_template() -> TerrainAreaFootprintTemplate:
    return TerrainAreaFootprintTemplate(
        footprint_template_id="event-component-area-12x8",
        name="Event component area 12x8",
        bounding_width_inches=12.0,
        bounding_depth_inches=8.0,
        polygon_vertices_inches=(
            TerrainDisplayPoint(-6.0, -4.0),
            TerrainDisplayPoint(6.0, -4.0),
            TerrainDisplayPoint(6.0, 4.0),
            TerrainDisplayPoint(-6.0, 4.0),
        ),
        source_id="test:event-companion:component-area-template",
    )


def _component_area(
    template: TerrainAreaFootprintTemplate,
    *,
    classification: TerrainAreaClassification,
    rotation_degrees: float,
    local_transform: TerrainAreaLocalTransform,
) -> PlacedTerrainArea:
    return PlacedTerrainArea.from_template(
        terrain_area_id="event-component-area",
        logical_terrain_area_id="event-component-area",
        template=template,
        terrain_feature_kind="ruins",
        classification=classification,
        center_x_inches=22.0,
        center_y_inches=30.0,
        rotation_degrees=rotation_degrees,
        local_transform=local_transform,
        source_layout_id="event-layout-a",
        source_id="test:event-companion:event-layout-a:component-area",
        symmetry_axis=SymmetryAxis.NONE,
    )


def _component_placement(
    *,
    area: PlacedTerrainArea,
    preset: TerrainFeaturePreset,
    feature_id: str,
    local_offset_x_inches: float = 0.0,
    local_offset_y_inches: float = 0.0,
    local_rotation_degrees: float = 0.0,
    local_transform: TerrainFeatureLocalTransform = TerrainFeatureLocalTransform.IDENTITY,
) -> TerrainFeatureAreaPlacement:
    return TerrainFeatureAreaPlacement(
        feature_id=feature_id,
        terrain_area_id=area.terrain_area_id,
        terrain_feature_preset_id=preset.terrain_feature_preset_id,
        local_offset_x_inches=local_offset_x_inches,
        local_offset_y_inches=local_offset_y_inches,
        local_rotation_degrees=local_rotation_degrees,
        local_transform=local_transform,
        source_id=f"test:event-companion:placement:{feature_id}",
    )


def _three_level_ruins_component_preset(
    template: TerrainAreaFootprintTemplate,
) -> TerrainFeaturePreset:
    return TerrainFeaturePreset(
        terrain_feature_preset_id="event-dense-three-level-ruins",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_template_id=template.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=6.0,
        footprint_depth_inches=4.0,
        local_rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=6.0,
            depth_inches=4.0,
            display_template_id=None,
        ).footprint_polygon,
        local_display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=6.0,
            depth_inches=4.0,
            display_template_id="event-dense-three-level-ruins-display",
        ),
        walls=tuple(
            TerrainWallTemplate(
                wall_id=f"wall-level-{level}",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=float(level * 3),
                width_inches=0.12,
                depth_inches=4.0,
                height_inches=2.0 if level == 2 else 3.0,
            )
            for level in range(3)
        ),
        floors=tuple(
            TerrainFloorTemplate(
                floor_id=f"floor-level-{level}",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=float(level * 3),
                width_inches=6.0,
                depth_inches=4.0,
                thickness_inches=0.12,
            )
            for level in range(3)
        ),
        source_id="test:event-companion:dense-three-level-ruins",
    )


def _dense_non_ruin_component_preset(
    template: TerrainAreaFootprintTemplate,
) -> TerrainFeaturePreset:
    return TerrainFeaturePreset(
        terrain_feature_preset_id="event-dense-non-ruin-obstacle",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        footprint_template_id=template.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=3.0,
        footprint_depth_inches=2.0,
        local_rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=3.0,
            depth_inches=2.0,
            display_template_id=None,
        ).footprint_polygon,
        local_display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=3.0,
            depth_inches=2.0,
            display_template_id="event-dense-non-ruin-obstacle-display",
        ),
        walls=(
            TerrainWallTemplate(
                wall_id="solid-body",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=3.0,
                depth_inches=2.0,
                height_inches=4.0,
            ),
        ),
        source_id="test:event-companion:dense-non-ruin-obstacle",
    )


def _light_obstacle_component_preset(
    template: TerrainAreaFootprintTemplate,
) -> TerrainFeaturePreset:
    return TerrainFeaturePreset(
        terrain_feature_preset_id="event-light-obstacle",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        footprint_template_id=template.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=2.0,
        local_rules_footprint_polygon=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=4.0,
            depth_inches=2.0,
            display_template_id=None,
        ).footprint_polygon,
        local_display_geometry=TerrainDisplayGeometry.axis_aligned_rectangle(
            center_x_inches=0.0,
            center_y_inches=0.0,
            width_inches=4.0,
            depth_inches=2.0,
            display_template_id="event-light-obstacle-display",
        ),
        walls=(
            TerrainWallTemplate(
                wall_id="light-body",
                center_x_inches=0.0,
                center_y_inches=0.0,
                bottom_z_inches=0.0,
                width_inches=4.0,
                depth_inches=2.0,
                height_inches=2.0,
            ),
        ),
        source_id="test:event-companion:light-obstacle",
    )
