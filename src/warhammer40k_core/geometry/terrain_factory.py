from __future__ import annotations

from typing import cast

from warhammer40k_core.geometry.pose import GeometryError
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)

RUINS_FLOOR_HEIGHT_INCHES = 3.0
RUINS_FLOOR_THICKNESS_INCHES = 0.12
RUINS_WALL_THICKNESS_INCHES = 0.12


class TerrainFactory:
    @staticmethod
    def empty_battlefield() -> tuple[TerrainFeatureDefinition, ...]:
        return ()

    @staticmethod
    def ruins_fixture(
        *,
        feature_id: str = "ruin-alpha",
        center_x_inches: float = 22.0,
        center_y_inches: float = 30.0,
    ) -> tuple[TerrainFeatureDefinition, ...]:
        half_width = 6.0
        half_depth = 3.0
        wall_thickness = RUINS_WALL_THICKNESS_INCHES
        half_wall_thickness = wall_thickness / 2.0
        walls = (
            TerrainWallDefinition(
                wall_id="east-wall-ground",
                center_x_inches=center_x_inches + half_width - half_wall_thickness,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=wall_thickness,
                depth_inches=half_depth * 2.0,
                height_inches=RUINS_FLOOR_HEIGHT_INCHES,
            ),
            TerrainWallDefinition(
                wall_id="north-wall-ground",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches + half_depth - half_wall_thickness,
                bottom_z_inches=0.0,
                width_inches=half_width * 2.0,
                depth_inches=wall_thickness,
                height_inches=RUINS_FLOOR_HEIGHT_INCHES,
            ),
        )
        floors = (
            TerrainFloorDefinition(
                floor_id="floor-ground",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=0.0,
                width_inches=half_width * 2.0,
                depth_inches=half_depth * 2.0,
                thickness_inches=RUINS_FLOOR_THICKNESS_INCHES,
            ),
            TerrainFloorDefinition(
                floor_id="floor-upper",
                center_x_inches=center_x_inches,
                center_y_inches=center_y_inches,
                bottom_z_inches=RUINS_FLOOR_HEIGHT_INCHES,
                width_inches=8.0,
                depth_inches=4.0,
                thickness_inches=RUINS_FLOOR_THICKNESS_INCHES,
            ),
        )
        return (
            TerrainFeatureDefinition(
                feature_id=feature_id,
                feature_kind=TerrainFeatureKind.RUINS,
                footprint_center_x_inches=center_x_inches,
                footprint_center_y_inches=center_y_inches,
                footprint_width_inches=half_width * 2.0,
                footprint_depth_inches=half_depth * 2.0,
                walls=walls,
                floors=floors,
                source_id="phase10f_deterministic_ruins_fixture",
            ),
        )

    @staticmethod
    def woods_fixture(
        *,
        feature_id: str = "woods-alpha",
        center_x_inches: float = 22.0,
        center_y_inches: float = 30.0,
    ) -> tuple[TerrainFeatureDefinition, ...]:
        return (
            TerrainFeatureDefinition(
                feature_id=feature_id,
                feature_kind=TerrainFeatureKind.WOODS,
                footprint_center_x_inches=center_x_inches,
                footprint_center_y_inches=center_y_inches,
                footprint_width_inches=7.0,
                footprint_depth_inches=5.0,
                walls=(),
                floors=(),
                source_id="phase13a_deterministic_woods_fixture",
            ),
        )

    @staticmethod
    def to_payloads(
        features: tuple[TerrainFeatureDefinition, ...],
    ) -> list[TerrainFeatureDefinitionPayload]:
        return [feature.to_payload() for feature in _validate_feature_tuple(features)]

    @staticmethod
    def from_payloads(
        payloads: object,
    ) -> tuple[TerrainFeatureDefinition, ...]:
        if type(payloads) is not list:
            raise GeometryError("Terrain feature payloads must be a list.")
        raw_payloads = cast(list[TerrainFeatureDefinitionPayload], payloads)
        features = tuple(TerrainFeatureDefinition.from_payload(payload) for payload in raw_payloads)
        return _validate_feature_tuple(features)


def _validate_feature_tuple(
    features: tuple[TerrainFeatureDefinition, ...],
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(features) is not tuple:
        raise GeometryError("Terrain features must be a tuple.")
    feature_ids: set[str] = set()
    for feature in features:
        if type(feature) is not TerrainFeatureDefinition:
            raise GeometryError("Terrain features must contain TerrainFeatureDefinition values.")
        if feature.feature_id in feature_ids:
            raise GeometryError(f"Duplicate terrain feature ID: {feature.feature_id}.")
        feature_ids.add(feature.feature_id)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))
