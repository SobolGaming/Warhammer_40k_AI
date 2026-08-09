from __future__ import annotations

from typing import cast

from warhammer40k_core.core.missions import ObjectiveTerrainAreaDefinition
from warhammer40k_core.core.objectives import Objective, ObjectiveAnchorKind, ObjectiveMarker
from warhammer40k_core.core.ruleset_descriptor import (
    RulesetDescriptor,
    TerrainObjectiveControlPolicy,
)
from warhammer40k_core.core.terrain_areas import PlacedTerrainArea
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition


def resolve_objective_control_sources(
    *,
    objective_markers: tuple[ObjectiveMarker, ...],
    terrain_features: tuple[TerrainFeatureDefinition, ...],
    ruleset_descriptor: RulesetDescriptor | None,
    explicit_terrain_objectives: tuple[Objective, ...],
    objective_terrain_areas: tuple[ObjectiveTerrainAreaDefinition, ...],
) -> tuple[
    tuple[ObjectiveMarker, ...],
    tuple[Objective, ...],
    tuple[ObjectiveTerrainAreaDefinition, ...],
]:
    markers = validate_objective_marker_tuple("objective_markers", objective_markers)
    features = validate_terrain_feature_tuple("terrain_features", terrain_features)
    terrain_objectives = validate_objective_tuple(
        "terrain_objectives",
        explicit_terrain_objectives,
    )
    linked_objectives = validate_objective_terrain_area_tuple(
        "objective_terrain_areas",
        objective_terrain_areas,
    )
    if terrain_objectives and linked_objectives:
        raise GameLifecycleError(
            "Explicit terrain_objectives and source-linked objective_terrain_areas are "
            "mutually exclusive."
        )
    if terrain_objectives or ruleset_descriptor is None:
        return markers, terrain_objectives, ()
    if type(ruleset_descriptor) is not RulesetDescriptor:
        raise GameLifecycleError("ruleset_descriptor must be a RulesetDescriptor.")
    if not ruleset_descriptor.mission_policy.terrain_objective_missions_supported:
        return markers, terrain_objectives, ()
    if (
        ObjectiveAnchorKind.TERRAIN
        not in ruleset_descriptor.objective_policy.supported_anchor_kinds
    ):
        return markers, terrain_objectives, ()
    if (
        ruleset_descriptor.objective_policy.terrain_objective_control_policy
        is TerrainObjectiveControlPolicy.UNSUPPORTED
    ):
        return markers, terrain_objectives, ()
    links_by_marker_id = {
        definition.objective_marker_id: definition for definition in linked_objectives
    }
    unknown_linked_marker_ids = set(links_by_marker_id) - {
        marker.objective_marker_id for marker in markers
    }
    if unknown_linked_marker_ids:
        raise GameLifecycleError("objective_terrain_areas references an unknown objective marker.")
    fallback_markers: list[ObjectiveMarker] = []
    derived_objectives: list[Objective] = []
    resolved_linked_objectives: list[ObjectiveTerrainAreaDefinition] = []
    for marker in markers:
        linked_objective = links_by_marker_id.get(marker.objective_marker_id)
        if linked_objective is not None:
            resolved_linked_objectives.append(linked_objective)
            continue
        matching_features = tuple(
            feature for feature in features if _terrain_feature_contains_marker(feature, marker)
        )
        if len(matching_features) > 1:
            raise GameLifecycleError("Objective marker coincides with multiple terrain areas.")
        if not matching_features:
            fallback_markers.append(marker)
            continue
        derived_objectives.append(
            Objective.terrain(
                objective_id=marker.objective_marker_id,
                name=marker.name,
                terrain_id=matching_features[0].feature_id,
            )
        )
    return (
        tuple(fallback_markers),
        tuple(sorted(derived_objectives, key=lambda objective: objective.objective_id)),
        tuple(
            sorted(
                resolved_linked_objectives,
                key=lambda definition: definition.objective_marker_id,
            )
        ),
    )


def validate_objective_control_source_references(
    *,
    objective_markers: tuple[ObjectiveMarker, ...],
    terrain_objectives: tuple[Objective, ...],
    objective_terrain_areas: tuple[ObjectiveTerrainAreaDefinition, ...],
    objective_terrain_area_markers: tuple[ObjectiveMarker, ...],
    terrain_areas: tuple[PlacedTerrainArea, ...],
) -> None:
    point_ids = {marker.objective_marker_id for marker in objective_markers}
    explicit_ids = {objective.objective_id for objective in terrain_objectives}
    linked_ids = {definition.objective_marker_id for definition in objective_terrain_areas}
    if point_ids & explicit_ids or point_ids & linked_ids or explicit_ids & linked_ids:
        raise GameLifecycleError("Objective control sources must not duplicate objective IDs.")
    linked_marker_ids = {marker.objective_marker_id for marker in objective_terrain_area_markers}
    if linked_marker_ids != linked_ids:
        raise GameLifecycleError(
            "ObjectiveControlContext source-linked terrain objectives require their exact "
            "objective markers."
        )
    terrain_areas_by_id = {area.terrain_area_id: area for area in terrain_areas}
    markers_by_id = {
        marker.objective_marker_id: marker for marker in objective_terrain_area_markers
    }
    for definition in objective_terrain_areas:
        if any(area_id not in terrain_areas_by_id for area_id in definition.terrain_area_ids):
            raise GameLifecycleError(
                "ObjectiveControlContext objective_terrain_areas references an unknown "
                "terrain area."
            )
        marker = markers_by_id[definition.objective_marker_id]
        if not any(
            shapely_backend.point_intersects_polygon(
                marker.x_inches,
                marker.y_inches,
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in terrain_areas_by_id[area_id].footprint_polygon
                ),
            )
            for area_id in definition.terrain_area_ids
        ):
            raise GameLifecycleError(
                "ObjectiveControlContext source-linked objective marker must intersect one "
                "of its terrain areas."
            )


def validate_objective_marker_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveMarker, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    markers: list[ObjectiveMarker] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarker:
            raise GameLifecycleError(f"{field_name} must contain ObjectiveMarker values.")
        if value.objective_marker_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def validate_objective_tuple(field_name: str, values: object) -> tuple[Objective, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    objectives: list[Objective] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not Objective:
            raise GameLifecycleError(f"{field_name} must contain Objective values.")
        if value.objective_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate objectives.")
        seen.add(value.objective_id)
        objectives.append(value)
    return tuple(sorted(objectives, key=lambda objective: objective.objective_id))


def validate_terrain_feature_tuple(
    field_name: str,
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise GameLifecycleError(f"{field_name} must contain TerrainFeatureDefinition values.")
        if value.feature_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def validate_objective_terrain_area_tuple(
    field_name: str,
    values: object,
) -> tuple[ObjectiveTerrainAreaDefinition, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    definitions: list[ObjectiveTerrainAreaDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveTerrainAreaDefinition:
            raise GameLifecycleError(
                f"{field_name} must contain ObjectiveTerrainAreaDefinition values."
            )
        if value.objective_marker_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicate objectives.")
        seen.add(value.objective_marker_id)
        definitions.append(value)
    return tuple(sorted(definitions, key=lambda value: value.objective_marker_id))


def validate_placed_terrain_area_tuple(
    field_name: str,
    values: object,
) -> tuple[PlacedTerrainArea, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    areas: list[PlacedTerrainArea] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlacedTerrainArea:
            raise GameLifecycleError(f"{field_name} must contain PlacedTerrainArea values.")
        if value.terrain_area_id in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        seen.add(value.terrain_area_id)
        areas.append(value)
    return tuple(sorted(areas, key=lambda value: value.terrain_area_id))


def _terrain_feature_contains_marker(
    feature: TerrainFeatureDefinition,
    marker: ObjectiveMarker,
) -> bool:
    return shapely_backend.point_intersects_polygon(
        marker.x_inches,
        marker.y_inches,
        feature.rules_footprint_points(),
    )
