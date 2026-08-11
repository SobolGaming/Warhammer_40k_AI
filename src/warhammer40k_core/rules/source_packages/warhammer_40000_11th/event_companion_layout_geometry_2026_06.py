from __future__ import annotations

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
    EventTerrainAreaGroupSpec,
    EventTerrainAreaSpec,
    EventTerrainFeaturePlacementSpec,
    EventTerritoryShapeSpec,
)


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
) -> DeploymentZoneShape:
    return shape_from_polygon_specs(explicit_polygons)


def event_territory_vertices(
    *,
    explicit_specs: tuple[EventTerritoryShapeSpec, ...],
) -> tuple[tuple[str, tuple[tuple[float, float], ...]], ...]:
    if not explicit_specs:
        raise MissionPackError("Explicit Event Companion territories require source polygons.")
    return territory_vertices_from_specs(explicit_specs)


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
    if not specs:
        raise MissionPackError(
            "Event Companion battlefield layout requires explicit terrain component placements."
        )
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
) -> dict[str, TerrainAreaClassification]:
    expected_area_ids = {area_id for area_id, *_rest in explicit_specs}
    classifications: dict[str, TerrainAreaClassification] = {}
    seen: set[str] = set()
    for area_id, token in classification_specs:
        if area_id not in expected_area_ids:
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
    if seen != expected_area_ids:
        raise MissionPackError(
            "Event Companion terrain-area classifications must cover every explicit area."
        )
    return classifications


def terrain_area_group_ids_by_suffix(
    *,
    area_suffixes: tuple[str, ...],
    group_specs: tuple[EventTerrainAreaGroupSpec, ...],
) -> dict[str, str]:
    group_ids_by_area = {area_suffix: area_suffix for area_suffix in area_suffixes}
    if len(group_ids_by_area) != len(area_suffixes):
        raise MissionPackError("Event Companion terrain areas must not duplicate suffixes.")
    seen_group_ids: set[str] = set()
    grouped_area_suffixes: set[str] = set()
    for group_id, member_area_suffixes in group_specs:
        if group_id in seen_group_ids:
            raise MissionPackError("Event Companion logical terrain-area IDs must be unique.")
        if len(member_area_suffixes) < 2 or len(set(member_area_suffixes)) != len(
            member_area_suffixes
        ):
            raise MissionPackError(
                "Event Companion logical terrain areas require distinct physical members."
            )
        for area_suffix in member_area_suffixes:
            if area_suffix not in group_ids_by_area:
                raise MissionPackError(
                    "Event Companion logical terrain area references an unknown physical area."
                )
            if area_suffix in grouped_area_suffixes:
                raise MissionPackError(
                    "Event Companion physical terrain area belongs to multiple logical areas."
                )
            group_ids_by_area[area_suffix] = group_id
            grouped_area_suffixes.add(area_suffix)
        seen_group_ids.add(group_id)
    return group_ids_by_area
