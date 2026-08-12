from __future__ import annotations

from typing import Final

from .common import (
    FOOTPRINT_6X2,
    FOOTPRINT_6X4,
    FOOTPRINT_7X11_5,
    FOOTPRINT_8X11_5_POLYGON,
    FOOTPRINT_10X2_5,
    EventBattlefieldLayoutSource,
    EventDeploymentZoneShapeSpec,
    EventObjectiveRoleCountSpec,
    EventObjectiveTerrainAreaSpec,
    EventShapePolygonSpec,
    EventShapePolygonsSpec,
    EventTerrainAreaClassificationSpec,
    EventTerrainAreaGroupSpec,
    EventTerrainAreaLocalTransformSpec,
    EventTerrainAreaMirrorPair,
    EventTerrainAreaSpec,
    EventTerrainFeaturePlacementSpec,
    EventTerritoryShapeSpec,
)
from .event_companion_full_artifact_catalog import (
    event_companion_battlefield_artifact,
    event_companion_battlefield_layouts,
    event_companion_terrain_feature_presets,
)
from .event_companion_full_artifact_types import EventCompanionBattlefieldArtifact
from .event_companion_full_artifact_validation import (
    EXPECTED_ARTIFACT_SHA256,
    event_companion_battlefield_artifact_from_json_bytes,
)

__all__ = (
    "BATTLEFIELD_ARTIFACT_SHA256",
    "BATTLEFIELD_LAYOUTS",
    "BATTLEFIELD_LAYOUTS_BY_ID",
    "BATTLEFIELD_LAYOUT_IDS",
    "BATTLEFIELD_PACKAGE_HASH",
    "BATTLEFIELD_SOURCE_PDF_SHA256",
    "BATTLEFIELD_TERRAIN_FEATURE_PRESETS",
    "FOOTPRINT_6X2",
    "FOOTPRINT_6X4",
    "FOOTPRINT_7X11_5",
    "FOOTPRINT_8X11_5_POLYGON",
    "FOOTPRINT_10X2_5",
    "EventBattlefieldLayoutSource",
    "EventDeploymentZoneShapeSpec",
    "EventObjectiveRoleCountSpec",
    "EventObjectiveTerrainAreaSpec",
    "EventShapePolygonSpec",
    "EventShapePolygonsSpec",
    "EventTerrainAreaClassificationSpec",
    "EventTerrainAreaGroupSpec",
    "EventTerrainAreaLocalTransformSpec",
    "EventTerrainAreaMirrorPair",
    "EventTerrainAreaSpec",
    "EventTerrainFeaturePlacementSpec",
    "EventTerritoryShapeSpec",
    "battlefield_artifact",
    "validate_battlefield_artifact_bytes",
)


def _index_layouts(
    layouts: tuple[EventBattlefieldLayoutSource, ...],
) -> dict[str, EventBattlefieldLayoutSource]:
    indexed: dict[str, EventBattlefieldLayoutSource] = {}
    for layout in layouts:
        if layout.layout_id in indexed:
            raise ValueError(f"Duplicate Event Companion layout ID: {layout.layout_id}")
        indexed[layout.layout_id] = layout
    return indexed


_BATTLEFIELD_ARTIFACT: Final = event_companion_battlefield_artifact()
BATTLEFIELD_ARTIFACT_SHA256: Final = EXPECTED_ARTIFACT_SHA256
BATTLEFIELD_PACKAGE_HASH: Final = _BATTLEFIELD_ARTIFACT.package_hash
BATTLEFIELD_SOURCE_PDF_SHA256: Final = _BATTLEFIELD_ARTIFACT.source_pdf_sha256
BATTLEFIELD_TERRAIN_FEATURE_PRESETS: Final = event_companion_terrain_feature_presets()
BATTLEFIELD_LAYOUTS: Final = event_companion_battlefield_layouts()
BATTLEFIELD_LAYOUTS_BY_ID: Final = _index_layouts(BATTLEFIELD_LAYOUTS)
BATTLEFIELD_LAYOUT_IDS: Final = frozenset(BATTLEFIELD_LAYOUTS_BY_ID)


def battlefield_artifact() -> EventCompanionBattlefieldArtifact:
    return _BATTLEFIELD_ARTIFACT


def validate_battlefield_artifact_bytes(raw: bytes) -> None:
    event_companion_battlefield_artifact_from_json_bytes(raw)
