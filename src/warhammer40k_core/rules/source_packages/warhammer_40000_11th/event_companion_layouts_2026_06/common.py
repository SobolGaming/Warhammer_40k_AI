from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.terrain_areas import TerrainAreaLocalTransform
from warhammer40k_core.core.terrain_layouts import TerrainFeatureLocalTransform

FOOTPRINT_6X4 = "FOOTPRINT_6X4"
FOOTPRINT_10X2_5 = "FOOTPRINT_10X2_5"
FOOTPRINT_6X2 = "FOOTPRINT_6X2"
FOOTPRINT_7X11_5 = "FOOTPRINT_7X11_5"
FOOTPRINT_8X11_5_POLYGON = "FOOTPRINT_8X11_5_POLYGON"

type EventObjectiveRoleCountSpec = tuple[ObjectiveMarkerRole, int]
type EventObjectiveTerrainAreaSpec = tuple[str, str, str, float, float, tuple[str, ...]]
# Terrain area specs store battlefield anchor x/y for the footprint template's first vertex.
type EventTerrainAreaSpec = tuple[
    str,
    str,
    float,
    float,
    float,
]
type EventTerrainAreaMirrorPair = tuple[str, str]
type EventTerrainAreaLocalTransformSpec = tuple[str, TerrainAreaLocalTransform]
type EventTerrainAreaClassificationSpec = tuple[str, str]
type EventTerrainFeaturePlacementSpec = tuple[
    str,
    str,
    str,
    float,
    float,
    float,
    TerrainFeatureLocalTransform,
]
type EventShapePolygonSpec = tuple[tuple[float, float], ...]
type EventShapePolygonsSpec = tuple[EventShapePolygonSpec, ...]
type EventDeploymentZoneShapeSpec = tuple[str, EventShapePolygonsSpec]
type EventTerritoryShapeSpec = tuple[str, EventShapePolygonsSpec]


@dataclass(frozen=True, slots=True)
class EventBattlefieldLayoutSource:
    layout_id: str
    name: str
    source_layout_id: str
    objective_role_counts: tuple[EventObjectiveRoleCountSpec, ...]
    terrain_area_specs: tuple[EventTerrainAreaSpec, ...]
    terrain_area_mirror_pairs: tuple[EventTerrainAreaMirrorPair, ...]
    terrain_area_local_transform_specs: tuple[EventTerrainAreaLocalTransformSpec, ...] = ()
    objective_terrain_area_specs: tuple[EventObjectiveTerrainAreaSpec, ...] = ()
    terrain_area_classification_specs: tuple[EventTerrainAreaClassificationSpec, ...] = ()
    terrain_feature_placement_specs: tuple[EventTerrainFeaturePlacementSpec, ...] = ()
    deployment_zone_shape_specs: tuple[EventDeploymentZoneShapeSpec, ...] = ()
    no_mans_land_shape_polygons: EventShapePolygonsSpec = ()
    territory_shape_specs: tuple[EventTerritoryShapeSpec, ...] = ()
    source_page: int | None = None
