from __future__ import annotations

import math

from warhammer40k_core.core.ruleset_descriptor import (
    TerrainFeatureKind,
)
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    TerrainAreaError,
    TerrainAreaFootprintTemplate,
    TerrainAreaLocalTransform,
    logical_terrain_area_group_contains_polygon,
    polygon_bounds,
    transform_terrain_area_local_point,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    TerrainFeaturePreset,
    TerrainFeatureTemplate,
    TerrainFloorTemplate,
    TerrainWallTemplate,
    transform_terrain_feature_local_point,
    transform_terrain_feature_local_rotation,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


class TerrainFeatureFactoryError(GameLifecycleError):
    """Raised when source terrain cannot be instantiated without ambiguity."""


class TerrainFeatureFactory:
    """Instantiates authoritative terrain templates in battlefield coordinates."""

    @staticmethod
    def from_static_template(feature: TerrainFeatureTemplate) -> TerrainFeatureDefinition:
        if type(feature) is not TerrainFeatureTemplate:
            raise TerrainFeatureFactoryError(
                "terrain feature template must be a TerrainFeatureTemplate."
            )
        return TerrainFeatureDefinition(
            feature_id=feature.feature_id,
            feature_kind=feature.feature_kind,
            classification=feature.classification,
            footprint_center_x_inches=feature.footprint_center_x_inches,
            footprint_center_y_inches=feature.footprint_center_y_inches,
            footprint_width_inches=feature.footprint_width_inches,
            footprint_depth_inches=feature.footprint_depth_inches,
            rules_footprint_polygon=feature.rules_footprint_polygon,
            display_geometry=feature.display_geometry,
            walls=tuple(_terrain_wall_from_template(wall) for wall in feature.walls),
            floors=tuple(_terrain_floor_from_template(floor) for floor in feature.floors),
            source_id=feature.source_id,
        )

    @staticmethod
    def from_area_placement(
        *,
        area: PlacedTerrainArea,
        footprint_template: TerrainAreaFootprintTemplate,
        preset: TerrainFeaturePreset,
        placement: TerrainFeatureAreaPlacement,
        terrain_area_group: tuple[PlacedTerrainArea, ...],
    ) -> TerrainFeatureDefinition:
        _validate_area_placement_inputs(
            area=area,
            footprint_template=footprint_template,
            preset=preset,
            placement=placement,
        )
        rules_footprint_polygon = _placed_rules_footprint_polygon(
            area=area,
            footprint_template=footprint_template,
            preset=preset,
            placement=placement,
        )
        if area not in terrain_area_group:
            raise TerrainFeatureFactoryError(
                "Terrain feature logical terrain-area group must contain its referenced area."
            )
        try:
            fits_logical_area = logical_terrain_area_group_contains_polygon(
                "Terrain feature placement footprint",
                rules_footprint_polygon,
                terrain_areas=terrain_area_group,
            )
        except TerrainAreaError as exc:
            raise TerrainFeatureFactoryError(
                "Terrain feature logical terrain-area group is invalid."
            ) from exc
        if not fits_logical_area:
            raise TerrainFeatureFactoryError(
                "Terrain feature preset footprint must fit within its logical terrain area."
            )
        display_geometry = _placed_display_geometry(
            area=area,
            footprint_template=footprint_template,
            preset=preset,
            placement=placement,
        )
        min_x, min_y, max_x, max_y = polygon_bounds(rules_footprint_polygon)
        return TerrainFeatureDefinition(
            feature_id=placement.feature_id,
            feature_kind=preset.feature_kind,
            classification=preset.classification,
            footprint_center_x_inches=(min_x + max_x) / 2.0,
            footprint_center_y_inches=(min_y + max_y) / 2.0,
            footprint_width_inches=max_x - min_x,
            footprint_depth_inches=max_y - min_y,
            rules_footprint_polygon=rules_footprint_polygon,
            display_geometry=display_geometry,
            walls=tuple(
                _placed_terrain_wall_from_template(
                    area=area,
                    footprint_template=footprint_template,
                    wall=wall,
                    placement=placement,
                )
                for wall in preset.walls
            ),
            floors=tuple(
                _placed_terrain_floor_from_template(
                    area=area,
                    footprint_template=footprint_template,
                    floor=floor,
                    placement=placement,
                )
                for floor in preset.floors
            ),
            source_id=(f"{placement.source_id}:terrain-feature-preset-source:{preset.source_id}"),
        )


def _validate_area_placement_inputs(
    *,
    area: object,
    footprint_template: object,
    preset: object,
    placement: object,
) -> None:
    if type(area) is not PlacedTerrainArea:
        raise TerrainFeatureFactoryError("area must be a PlacedTerrainArea.")
    if type(footprint_template) is not TerrainAreaFootprintTemplate:
        raise TerrainFeatureFactoryError(
            "footprint_template must be a TerrainAreaFootprintTemplate."
        )
    if type(preset) is not TerrainFeaturePreset:
        raise TerrainFeatureFactoryError("preset must be a TerrainFeaturePreset.")
    if type(placement) is not TerrainFeatureAreaPlacement:
        raise TerrainFeatureFactoryError("placement must be a TerrainFeatureAreaPlacement.")
    if placement.terrain_area_id != area.terrain_area_id:
        raise TerrainFeatureFactoryError("Terrain feature placement references a different area.")
    if placement.terrain_feature_preset_id != preset.terrain_feature_preset_id:
        raise TerrainFeatureFactoryError("Terrain feature placement references a different preset.")
    if area.footprint_template_id != footprint_template.footprint_template_id:
        raise TerrainFeatureFactoryError("Terrain area references a different footprint template.")
    if preset.footprint_template_id != footprint_template.footprint_template_id:
        raise TerrainFeatureFactoryError("Terrain feature preset references a different footprint.")
    if type(preset.feature_kind) is not TerrainFeatureKind:
        raise TerrainFeatureFactoryError(
            "Terrain feature preset requires a canonical feature kind."
        )


def _placed_display_geometry(
    *,
    area: PlacedTerrainArea,
    footprint_template: TerrainAreaFootprintTemplate,
    preset: TerrainFeaturePreset,
    placement: TerrainFeatureAreaPlacement,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry(
        display_template_id=preset.local_display_geometry.display_template_id,
        footprint_polygon=tuple(
            _place_local_point(
                transform_terrain_feature_local_point(point, placement=placement),
                area=area,
                footprint_template=footprint_template,
            )
            for point in preset.local_display_geometry.footprint_polygon
        ),
    )


def _placed_rules_footprint_polygon(
    *,
    area: PlacedTerrainArea,
    footprint_template: TerrainAreaFootprintTemplate,
    preset: TerrainFeaturePreset,
    placement: TerrainFeatureAreaPlacement,
) -> tuple[TerrainDisplayPoint, ...]:
    return tuple(
        _place_local_point(
            transform_terrain_feature_local_point(point, placement=placement),
            area=area,
            footprint_template=footprint_template,
        )
        for point in preset.local_rules_footprint_polygon
    )


def _placed_terrain_wall_from_template(
    *,
    area: PlacedTerrainArea,
    footprint_template: TerrainAreaFootprintTemplate,
    wall: TerrainWallTemplate,
    placement: TerrainFeatureAreaPlacement,
) -> TerrainWallDefinition:
    center = _place_local_point(
        transform_terrain_feature_local_point(
            TerrainDisplayPoint(wall.center_x_inches, wall.center_y_inches),
            placement=placement,
        ),
        area=area,
        footprint_template=footprint_template,
    )
    return TerrainWallDefinition(
        wall_id=wall.wall_id,
        center_x_inches=center.x_inches,
        center_y_inches=center.y_inches,
        bottom_z_inches=wall.bottom_z_inches,
        width_inches=wall.width_inches,
        depth_inches=wall.depth_inches,
        height_inches=wall.height_inches,
        rotation_degrees=_place_local_rotation(
            transform_terrain_feature_local_rotation(
                wall.rotation_degrees,
                placement=placement,
            ),
            area=area,
        ),
    )


def _placed_terrain_floor_from_template(
    *,
    area: PlacedTerrainArea,
    footprint_template: TerrainAreaFootprintTemplate,
    floor: TerrainFloorTemplate,
    placement: TerrainFeatureAreaPlacement,
) -> TerrainFloorDefinition:
    center = _place_local_point(
        transform_terrain_feature_local_point(
            TerrainDisplayPoint(floor.center_x_inches, floor.center_y_inches),
            placement=placement,
        ),
        area=area,
        footprint_template=footprint_template,
    )
    return TerrainFloorDefinition(
        floor_id=floor.floor_id,
        center_x_inches=center.x_inches,
        center_y_inches=center.y_inches,
        bottom_z_inches=floor.bottom_z_inches,
        width_inches=floor.width_inches,
        depth_inches=floor.depth_inches,
        thickness_inches=floor.thickness_inches,
        rotation_degrees=_place_local_rotation(
            transform_terrain_feature_local_rotation(
                floor.rotation_degrees,
                placement=placement,
            ),
            area=area,
        ),
    )


def _place_local_point(
    point: TerrainDisplayPoint,
    *,
    area: PlacedTerrainArea,
    footprint_template: TerrainAreaFootprintTemplate,
) -> TerrainDisplayPoint:
    try:
        return transform_terrain_area_local_point(
            point,
            area=area,
            template=footprint_template,
        )
    except TerrainAreaError as exc:
        raise TerrainFeatureFactoryError(
            "Terrain feature placement area transform is invalid."
        ) from exc


def _place_local_rotation(
    local_rotation_degrees: float,
    *,
    area: PlacedTerrainArea,
) -> float:
    local_rotation = float(local_rotation_degrees)
    if not math.isfinite(local_rotation):
        raise TerrainFeatureFactoryError("local terrain feature rotation must be finite.")
    if area.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS:
        local_rotation = 180.0 - local_rotation
    elif area.local_transform is not TerrainAreaLocalTransform.IDENTITY:
        raise TerrainFeatureFactoryError(
            "Unsupported terrain area local transform for feature rotation."
        )
    return (area.rotation_degrees + local_rotation) % 360.0


def _terrain_wall_from_template(wall: TerrainWallTemplate) -> TerrainWallDefinition:
    return TerrainWallDefinition(
        wall_id=wall.wall_id,
        center_x_inches=wall.center_x_inches,
        center_y_inches=wall.center_y_inches,
        bottom_z_inches=wall.bottom_z_inches,
        width_inches=wall.width_inches,
        depth_inches=wall.depth_inches,
        height_inches=wall.height_inches,
        rotation_degrees=wall.rotation_degrees,
    )


def _terrain_floor_from_template(floor: TerrainFloorTemplate) -> TerrainFloorDefinition:
    return TerrainFloorDefinition(
        floor_id=floor.floor_id,
        center_x_inches=floor.center_x_inches,
        center_y_inches=floor.center_y_inches,
        bottom_z_inches=floor.bottom_z_inches,
        width_inches=floor.width_inches,
        depth_inches=floor.depth_inches,
        thickness_inches=floor.thickness_inches,
        rotation_degrees=floor.rotation_degrees,
    )
