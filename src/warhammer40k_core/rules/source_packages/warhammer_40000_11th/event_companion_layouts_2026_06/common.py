from __future__ import annotations

from dataclasses import dataclass

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.terrain_areas import TerrainAreaClassification

FOOTPRINT_6X4 = "FOOTPRINT_6X4"
FOOTPRINT_10X2_5 = "FOOTPRINT_10X2_5"
FOOTPRINT_6X2 = "FOOTPRINT_6X2"
FOOTPRINT_7X11_5 = "FOOTPRINT_7X11_5"
FOOTPRINT_8X11_5_POLYGON = "FOOTPRINT_8X11_5_POLYGON"

type EventObjectiveSpec = tuple[str, str, str, float, float]
type EventObjectiveRoleCountSpec = tuple[ObjectiveMarkerRole, int]
type EventTerrainAreaSpec = tuple[
    str,
    str,
    TerrainAreaClassification,
    float,
    float,
    float,
]
type EventTerrainAreaMirrorPair = tuple[str, str]


@dataclass(frozen=True, slots=True)
class EventBattlefieldLayoutSource:
    layout_id: str
    name: str
    source_layout_id: str
    objective_specs: tuple[EventObjectiveSpec, ...]
    objective_role_counts: tuple[EventObjectiveRoleCountSpec, ...]
    terrain_area_specs: tuple[EventTerrainAreaSpec, ...]
    terrain_area_mirror_pairs: tuple[EventTerrainAreaMirrorPair, ...]
