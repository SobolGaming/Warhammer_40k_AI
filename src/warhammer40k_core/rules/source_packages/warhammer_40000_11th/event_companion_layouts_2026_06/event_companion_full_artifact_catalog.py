from __future__ import annotations

from collections import Counter
from functools import cache
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
from .event_companion_full_artifact_types import (
    BattlefieldLayoutArtifact,
    BattlefieldShapeArtifact,
    EventCompanionBattlefieldArtifact,
    PointArtifact,
    TerrainFeatureArchetypeArtifact,
)
from .event_companion_full_artifact_validation import (
    EventCompanionBattlefieldArtifactError,
    event_companion_battlefield_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/event-companion-battlefields.json"
_ARTIFACT_PACKAGE: Final = (
    "warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layouts_2026_06"
)
_OBJECTIVE_ROLE_ORDER: Final = (
    ObjectiveMarkerRole.ATTACKER_HOME,
    ObjectiveMarkerRole.DEFENDER_HOME,
    ObjectiveMarkerRole.CENTRAL,
    ObjectiveMarkerRole.EXPANSION,
    ObjectiveMarkerRole.HOME,
)

__all__ = (
    "event_companion_battlefield_artifact",
    "event_companion_battlefield_layouts",
    "event_companion_terrain_feature_presets",
)


@cache
def event_companion_battlefield_artifact() -> EventCompanionBattlefieldArtifact:
    """Load and strictly validate the complete Event Companion battlefield artifact."""
    try:
        raw = package_artifact_bytes(_ARTIFACT_PACKAGE, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise EventCompanionBattlefieldArtifactError(
            "Complete Event Companion battlefield artifact could not be loaded."
        ) from exc
    return event_companion_battlefield_artifact_from_json_bytes(raw)


def _point(point: PointArtifact) -> TerrainDisplayPoint:
    return TerrainDisplayPoint(x_inches=point.x_inches, y_inches=point.y_inches)


def _terrain_feature_preset_id(archetype_id: str) -> str:
    # Keep the established IDs so the full artifact replaces, rather than forks,
    # the shared presets introduced by the exact Meatgrinder slice.
    return f"event-companion-exact-{archetype_id}"


def _terrain_feature_preset(
    *,
    artifact: EventCompanionBattlefieldArtifact,
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
            f"{artifact.source_package_id}:full-battlefield-layouts:"
            f"terrain-archetype:{archetype.archetype_id}:{artifact.package_hash}"
        ),
    )


@cache
def event_companion_terrain_feature_presets() -> tuple[TerrainFeaturePreset, ...]:
    artifact = event_companion_battlefield_artifact()
    return tuple(
        _terrain_feature_preset(artifact=artifact, archetype=archetype)
        for archetype in artifact.feature_archetypes
    )


def _suffix(layout_id: str, stable_id: str) -> str:
    prefix = f"{layout_id}-"
    if not stable_id.startswith(prefix):
        raise EventCompanionBattlefieldArtifactError(
            "Event Companion battlefield stable ID does not belong to its layout."
        )
    return stable_id.removeprefix(prefix)


def _shape_polygons(
    shape: BattlefieldShapeArtifact,
) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple((point.x_inches, point.y_inches) for point in polygon) for polygon in shape.polygons
    )


def _terrain_area_local_transform_specs(
    layout: BattlefieldLayoutArtifact,
) -> tuple[tuple[str, TerrainAreaLocalTransform], ...]:
    specs: list[tuple[str, TerrainAreaLocalTransform]] = []
    for area in layout.terrain_areas:
        local_transform = TerrainAreaLocalTransform(area.local_transform)
        if local_transform is TerrainAreaLocalTransform.IDENTITY:
            continue
        specs.append((_suffix(layout.layout_id, area.area_id), local_transform))
    return tuple(specs)


def _terrain_area_group_specs(
    layout: BattlefieldLayoutArtifact,
) -> tuple[tuple[str, tuple[str, ...]], ...]:
    specs: list[tuple[str, tuple[str, ...]]] = []
    for contact in layout.terrain_area_contacts:
        if contact.kind == "separate":
            continue
        if contact.kind != "single" or len(contact.source_icon_ids) != 1:
            raise EventCompanionBattlefieldArtifactError(
                "Event Companion single-terrain-area contact identity is malformed."
            )
        source_icon_suffix = _suffix(layout.layout_id, contact.source_icon_ids[0])
        specs.append(
            (
                f"logical-{source_icon_suffix}",
                tuple(
                    _suffix(layout.layout_id, terrain_area_id)
                    for terrain_area_id in contact.terrain_area_ids
                ),
            )
        )
    return tuple(sorted(specs))


def _objective_role_counts(
    layout: BattlefieldLayoutArtifact,
) -> tuple[tuple[ObjectiveMarkerRole, int], ...]:
    counts = Counter(ObjectiveMarkerRole(objective.role) for objective in layout.objectives)
    return tuple((role, counts[role]) for role in _OBJECTIVE_ROLE_ORDER if counts[role] > 0)


def _layout_source(layout: BattlefieldLayoutArtifact) -> EventBattlefieldLayoutSource:
    return EventBattlefieldLayoutSource(
        layout_id=layout.layout_id,
        name=layout.name,
        source_layout_id=layout.source_layout_id,
        objective_role_counts=_objective_role_counts(layout),
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
        # Every reviewed area pose is explicit in the full artifact. This field is
        # a runtime synthesis instruction, not mirror-link metadata; populating it
        # would duplicate the artifact's 16 areas. Mirror links remain available
        # on the strict artifact returned by event_companion_battlefield_artifact.
        terrain_area_mirror_pairs=(),
        terrain_area_local_transform_specs=_terrain_area_local_transform_specs(layout),
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
        terrain_area_group_specs=_terrain_area_group_specs(layout),
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


@cache
def event_companion_battlefield_layouts() -> tuple[EventBattlefieldLayoutSource, ...]:
    artifact = event_companion_battlefield_artifact()
    return tuple(_layout_source(layout) for layout in artifact.layouts)
