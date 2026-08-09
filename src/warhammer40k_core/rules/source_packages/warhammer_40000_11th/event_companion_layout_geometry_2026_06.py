from __future__ import annotations

import math
from collections.abc import Callable

from warhammer40k_core.core.deployment_zones import (
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
)
from warhammer40k_core.core.missions import MissionPackError
from warhammer40k_core.core.terrain_areas import PlacedTerrainArea, TerrainAreaClassification
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    terrain_feature_local_transform_from_token,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as chapter_approved,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layouts_2026_06 import (  # noqa: E501
    EventDeploymentZoneShapeSpec,
    EventShapePolygonsSpec,
    EventTerrainAreaClassificationSpec,
    EventTerrainAreaSpec,
    EventTerrainFeaturePlacementSpec,
    EventTerritoryShapeSpec,
)

_DEPLOYMENT_CUTOUT_RADIUS_INCHES = 9.0
_ARC_SEGMENTS = 16


def shape_from_polygon_specs(polygons: EventShapePolygonsSpec) -> DeploymentZoneShape:
    if not polygons:
        raise MissionPackError("Explicit Event Companion battlefield shape requires polygons.")
    return DeploymentZoneShape(
        polygons=tuple(
            DeploymentZonePolygon(vertices=tuple(DeploymentZonePoint(x=x, y=y) for x, y in polygon))
            for polygon in polygons
        )
    )


def event_no_mans_land_shape(
    *,
    explicit_polygons: EventShapePolygonsSpec,
    layout_number: int,
) -> DeploymentZoneShape:
    if explicit_polygons:
        return shape_from_polygon_specs(explicit_polygons)
    if layout_number == 1:
        return shape_from_polygon_specs(
            (
                (
                    (0.0, 12.0),
                    (22.0, 12.0),
                    (22.0, 20.0),
                    (44.0, 20.0),
                    (44.0, 48.0),
                    (22.0, 48.0),
                    (22.0, 40.0),
                    (0.0, 40.0),
                ),
            )
        )
    if layout_number == 2:
        return DeploymentZoneShape.rectangle(min_x=12.0, min_y=0.0, max_x=32.0, max_y=60.0)
    if layout_number == 3:
        return shape_from_polygon_specs(
            (
                ((0.0, 0.0), (22.0, 0.0), (22.0, 30.0), (0.0, 30.0)),
                ((22.0, 30.0), (44.0, 30.0), (44.0, 60.0), (22.0, 60.0)),
                _quarter_circle_sector_vertices(start_degrees=90.0, end_degrees=180.0),
                _quarter_circle_sector_vertices(start_degrees=-90.0, end_degrees=0.0),
            )
        )
    raise MissionPackError("Unsupported extracted battlefield layout number.")


def event_territory_vertices(
    *,
    explicit_specs: tuple[EventTerritoryShapeSpec, ...],
    layout_number: int,
) -> tuple[tuple[str, tuple[tuple[float, float], ...]], ...]:
    if explicit_specs:
        return territory_vertices_from_specs(explicit_specs)
    if layout_number == 1:
        return (
            ("attacker_territory", ((0.0, 30.0), (44.0, 30.0), (44.0, 60.0), (0.0, 60.0))),
            ("defender_territory", ((0.0, 0.0), (44.0, 0.0), (44.0, 30.0), (0.0, 30.0))),
        )
    if layout_number == 2:
        return (
            ("attacker_territory", ((0.0, 0.0), (22.0, 0.0), (22.0, 60.0), (0.0, 60.0))),
            ("defender_territory", ((22.0, 0.0), (44.0, 0.0), (44.0, 60.0), (22.0, 60.0))),
        )
    if layout_number == 3:
        return (
            ("attacker_territory", ((0.0, 0.0), (44.0, 60.0), (0.0, 60.0))),
            ("defender_territory", ((0.0, 0.0), (44.0, 0.0), (44.0, 60.0))),
        )
    raise MissionPackError("Unsupported extracted battlefield layout number.")


def _quarter_circle_sector_vertices(
    *,
    start_degrees: float,
    end_degrees: float,
) -> tuple[tuple[float, float], ...]:
    return (
        (22.0, 30.0),
        *tuple(
            (
                round(
                    22.0 + (_DEPLOYMENT_CUTOUT_RADIUS_INCHES * math.cos(math.radians(degrees))),
                    6,
                ),
                round(
                    30.0 + (_DEPLOYMENT_CUTOUT_RADIUS_INCHES * math.sin(math.radians(degrees))),
                    6,
                ),
            )
            for degrees in (
                start_degrees + ((end_degrees - start_degrees) * index / _ARC_SEGMENTS)
                for index in range(_ARC_SEGMENTS + 1)
            )
        ),
    )


def deployment_zone_rows_from_specs(
    *,
    layout_id: str,
    specs: tuple[EventDeploymentZoneShapeSpec, ...],
) -> tuple[chapter_approved.SourceBattlefieldDeploymentZoneRow, ...]:
    rows = tuple(
        chapter_approved.SourceBattlefieldDeploymentZoneRow(
            deployment_zone_id=f"{layout_id}-{role}",
            player_role=role,
            shape=shape_from_polygon_specs(polygons),
        )
        for role, polygons in specs
    )
    if tuple(row.player_role for row in rows) != ("attacker", "defender"):
        raise MissionPackError(
            "Explicit Event Companion deployment zones require attacker then defender."
        )
    return rows


def territory_vertices_from_specs(
    specs: tuple[EventTerritoryShapeSpec, ...],
) -> tuple[tuple[str, tuple[tuple[float, float], ...]], ...]:
    rows: list[tuple[str, tuple[tuple[float, float], ...]]] = []
    for role, polygons in specs:
        if len(polygons) != 1:
            raise MissionPackError(
                "Event Companion territory vertex consumers require one polygon per territory."
            )
        rows.append((role, polygons[0]))
    if tuple(role for role, _vertices in rows) != (
        "attacker_territory",
        "defender_territory",
    ):
        raise MissionPackError(
            "Explicit Event Companion territories require attacker then defender."
        )
    return tuple(rows)


def terrain_feature_placements_from_specs(
    *,
    layout_id: str,
    source_layout_id: str,
    source_package_id: str,
    terrain_areas: tuple[PlacedTerrainArea, ...],
    specs: tuple[EventTerrainFeaturePlacementSpec, ...],
) -> tuple[TerrainFeatureAreaPlacement, ...]:
    area_ids_by_suffix = {
        area.terrain_area_id.removeprefix(f"{layout_id}-"): area.terrain_area_id
        for area in terrain_areas
    }
    rows: list[TerrainFeatureAreaPlacement] = []
    for (
        feature_suffix,
        area_suffix,
        preset_id,
        offset_x,
        offset_y,
        rotation,
        local_transform,
    ) in specs:
        terrain_area_id = area_ids_by_suffix.get(area_suffix)
        if terrain_area_id is None:
            raise MissionPackError(
                "Event Companion terrain feature placement references unknown terrain area."
            )
        rows.append(
            TerrainFeatureAreaPlacement(
                feature_id=f"{layout_id}-{feature_suffix}",
                terrain_area_id=terrain_area_id,
                terrain_feature_preset_id=preset_id,
                local_offset_x_inches=offset_x,
                local_offset_y_inches=offset_y,
                local_rotation_degrees=rotation,
                local_transform=terrain_feature_local_transform_from_token(local_transform),
                source_id=(
                    f"{source_package_id}:battlefield-layout:{source_layout_id}:"
                    f"terrain-feature-placement:{feature_suffix}"
                ),
            )
        )
    return tuple(rows)


def terrain_area_classifications_by_suffix(
    *,
    explicit_specs: tuple[EventTerrainAreaSpec, ...],
    classification_specs: tuple[EventTerrainAreaClassificationSpec, ...],
    default_for_template: Callable[[str], TerrainAreaClassification],
) -> dict[str, TerrainAreaClassification]:
    classifications = {
        area_id: default_for_template(template_id)
        for area_id, template_id, _x, _y, _rotation in explicit_specs
    }
    seen: set[str] = set()
    for area_id, token in classification_specs:
        if area_id not in classifications:
            raise MissionPackError(
                "Event Companion terrain-area classification references unknown area."
            )
        if area_id in seen:
            raise MissionPackError(
                "Event Companion terrain-area classifications must not duplicate areas."
            )
        try:
            classification = TerrainAreaClassification(token)
        except ValueError as exc:
            raise MissionPackError(
                "Event Companion terrain-area classification is unsupported."
            ) from exc
        classifications[area_id] = classification
        seen.add(area_id)
    return classifications
