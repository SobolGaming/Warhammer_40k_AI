from __future__ import annotations

from typing import Final

from warhammer40k_core.core.missions import ObjectiveMarkerRole
from warhammer40k_core.core.ruleset_descriptor import terrain_feature_kind_from_token
from warhammer40k_core.core.terrain_areas import (
    TerrainAreaLocalTransform,
    terrain_area_classification_from_token,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureLocalTransform,
    TerrainFeaturePreset,
    TerrainFloorTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from .common import EventBattlefieldLayoutSource
from .exact_slice_artifact import (
    EXPECTED_ARTIFACT_SHA256,
    BattlefieldShapeArtifact,
    EventCompanionExactSliceArtifact,
    EventCompanionExactSliceArtifactError,
    ExactBattlefieldLayoutArtifact,
    PointArtifact,
    TerrainFeatureArchetypeArtifact,
    event_companion_exact_slice_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/purge-the-foe-vs-purge-the-foe-meatgrinder.json"
_ARTIFACT_PACKAGE: Final = (
    "warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layouts_2026_06"
)

__all__ = (
    "EXACT_SLICE_ARTIFACT_SHA256",
    "EXACT_SLICE_LAYOUT_IDS",
    "EXACT_SLICE_PACKAGE_HASH",
    "EXACT_SLICE_SOURCE_PDF_SHA256",
    "LAYOUTS",
    "TERRAIN_FEATURE_PRESETS",
    "exact_slice_artifact",
    "validate_exact_slice_artifact_bytes",
)


def _load_artifact() -> EventCompanionExactSliceArtifact:
    try:
        raw = package_artifact_bytes(_ARTIFACT_PACKAGE, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise EventCompanionExactSliceArtifactError(
            "Event Companion Phase 17N exact-slice artifact could not be loaded."
        ) from exc
    return event_companion_exact_slice_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
EXACT_SLICE_ARTIFACT_SHA256: Final = EXPECTED_ARTIFACT_SHA256
EXACT_SLICE_PACKAGE_HASH: Final = _ARTIFACT.package_hash
EXACT_SLICE_SOURCE_PDF_SHA256: Final = _ARTIFACT.source_pdf_sha256
EXACT_SLICE_LAYOUT_IDS: Final = frozenset(layout.layout_id for layout in _ARTIFACT.layouts)


def exact_slice_artifact() -> EventCompanionExactSliceArtifact:
    return _ARTIFACT


def validate_exact_slice_artifact_bytes(raw: bytes) -> None:
    event_companion_exact_slice_artifact_from_json_bytes(raw)


def _point(point: PointArtifact) -> TerrainDisplayPoint:
    return TerrainDisplayPoint(x_inches=point.x_inches, y_inches=point.y_inches)


def _terrain_feature_preset_id(archetype_id: str) -> str:
    return f"event-companion-exact-{archetype_id}"


def _terrain_feature_preset(
    archetype: TerrainFeatureArchetypeArtifact,
) -> TerrainFeaturePreset:
    polygon = tuple(_point(point) for point in archetype.rules_footprint_polygon)
    x_values = tuple(point.x_inches for point in polygon)
    y_values = tuple(point.y_inches for point in polygon)
    return TerrainFeaturePreset(
        terrain_feature_preset_id=_terrain_feature_preset_id(archetype.archetype_id),
        feature_kind=terrain_feature_kind_from_token(archetype.feature_kind),
        classification=terrain_area_classification_from_token(archetype.classification),
        footprint_template_id=archetype.footprint_template_id,
        footprint_center_x_inches=0.0,
        footprint_center_y_inches=0.0,
        footprint_width_inches=max(x_values) - min(x_values),
        footprint_depth_inches=max(y_values) - min(y_values),
        local_rules_footprint_polygon=polygon,
        local_display_geometry=TerrainDisplayGeometry(
            display_template_id=f"event-companion-exact-{archetype.archetype_id}",
            footprint_polygon=polygon,
        ),
        walls=tuple(
            TerrainWallTemplate(
                wall_id=wall.wall_id,
                center_x_inches=wall.center_x_inches,
                center_y_inches=wall.center_y_inches,
                bottom_z_inches=wall.bottom_z_inches,
                width_inches=wall.width_inches,
                depth_inches=wall.depth_inches,
                height_inches=wall.height_inches,
                rotation_degrees=wall.rotation_degrees,
            )
            for wall in archetype.walls
        ),
        floors=tuple(
            TerrainFloorTemplate(
                floor_id=floor.floor_id,
                center_x_inches=floor.center_x_inches,
                center_y_inches=floor.center_y_inches,
                bottom_z_inches=floor.bottom_z_inches,
                width_inches=floor.width_inches,
                depth_inches=floor.depth_inches,
                thickness_inches=floor.thickness_inches,
                rotation_degrees=floor.rotation_degrees,
            )
            for floor in archetype.floors
        ),
        source_id=(
            f"{_ARTIFACT.source_package_id}:phase17n-exact-slice:"
            f"terrain-archetype:{archetype.archetype_id}:{_ARTIFACT.package_hash}"
        ),
    )


TERRAIN_FEATURE_PRESETS: Final = tuple(
    _terrain_feature_preset(archetype) for archetype in _ARTIFACT.feature_archetypes
)


def _suffix(layout_id: str, stable_id: str) -> str:
    prefix = f"{layout_id}-"
    if not stable_id.startswith(prefix):
        raise EventCompanionExactSliceArtifactError(
            "Event Companion exact-slice stable ID does not belong to its layout."
        )
    return stable_id.removeprefix(prefix)


def _shape_polygons(
    shape: BattlefieldShapeArtifact,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple((point.x_inches, point.y_inches) for point in polygon) for polygon in shape.polygons
    )


def _layout_source(
    layout: ExactBattlefieldLayoutArtifact,
) -> EventBattlefieldLayoutSource:
    role_counts: list[tuple[ObjectiveMarkerRole, int]] = []
    for role, count in (
        (ObjectiveMarkerRole.ATTACKER_HOME, 1),
        (ObjectiveMarkerRole.DEFENDER_HOME, 1),
        (ObjectiveMarkerRole.CENTRAL, 2),
        (ObjectiveMarkerRole.EXPANSION, 2),
    ):
        role_counts.append((role, count))
    return EventBattlefieldLayoutSource(
        layout_id=layout.layout_id,
        name=layout.name,
        source_layout_id=layout.source_layout_id,
        objective_role_counts=tuple(role_counts),
        terrain_area_specs=tuple(
            (
                _suffix(layout.layout_id, area.area_id),
                area.footprint_template_id,
                area.anchor_x_inches,
                area.anchor_y_inches,
                area.rotation_degrees,
            )
            for area in layout.terrain_areas
        ),
        terrain_area_mirror_pairs=(),
        terrain_area_local_transform_specs=tuple(
            (
                _suffix(layout.layout_id, area.area_id),
                TerrainAreaLocalTransform.MIRROR_Y_AXIS,
            )
            for area in layout.terrain_areas
            if area.local_transform == "mirror_y_axis"
        ),
        objective_terrain_area_specs=tuple(
            (
                _suffix(layout.layout_id, objective.objective_id),
                objective.name,
                objective.role,
                objective.x_inches,
                objective.y_inches,
                tuple(_suffix(layout.layout_id, area_id) for area_id in objective.terrain_area_ids),
            )
            for objective in layout.objectives
        ),
        terrain_area_classification_specs=tuple(
            (_suffix(layout.layout_id, area.area_id), area.classification)
            for area in layout.terrain_areas
        ),
        terrain_feature_placement_specs=tuple(
            (
                _suffix(layout.layout_id, component.component_id),
                _suffix(layout.layout_id, component.terrain_area_id),
                _terrain_feature_preset_id(component.archetype_id),
                component.local_offset_x_inches,
                component.local_offset_y_inches,
                component.local_rotation_degrees,
                TerrainFeatureLocalTransform(component.local_transform),
            )
            for component in layout.terrain_components
        ),
        deployment_zone_shape_specs=tuple(
            (zone.role, _shape_polygons(zone)) for zone in layout.deployment_zones
        ),
        no_mans_land_shape_polygons=_shape_polygons(layout.no_mans_land),
        territory_shape_specs=tuple(
            (territory.role, _shape_polygons(territory)) for territory in layout.territories
        ),
        source_page=layout.source_page,
    )


LAYOUTS: Final = tuple(_layout_source(layout) for layout in _ARTIFACT.layouts)
