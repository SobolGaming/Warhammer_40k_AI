from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.engine.battlefield_state import (
    PlacementError,
    SpatialIndexState,
    SpatialIndexStatePayload,
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
