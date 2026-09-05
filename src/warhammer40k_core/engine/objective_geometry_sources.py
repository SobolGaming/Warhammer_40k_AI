"""Resolve mission objective identities to the shared measurement geometry."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.missions import ObjectiveTerrainAreaDefinition
from warhammer40k_core.core.objectives import Objective, TerrainObjectiveAnchor
from warhammer40k_core.core.terrain_areas import PlacedTerrainArea
from warhammer40k_core.engine.objective_control_sources import (
    resolve_objective_control_sources,
    validate_objective_control_source_references,
)
from warhammer40k_core.engine.objective_geometry import ObjectiveGeometry
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def terrain_objective_geometry(
    objective: Objective, *, terrain_features: tuple[TerrainFeatureDefinition, ...]
) -> ObjectiveGeometry:
    if type(objective) is not Objective or type(objective.anchor) is not TerrainObjectiveAnchor:
        raise GameLifecycleError("Terrain geometry requires a terrain-anchored Objective.")
    for feature in terrain_features:
        if feature.feature_id == objective.anchor.terrain_id:
            return ObjectiveGeometry.from_terrain(
                objective_id=objective.objective_id,
                footprint_polygons=(feature.rules_footprint_points(),),
            )
    raise GameLifecycleError("Terrain objective references an unknown terrain feature.")


def linked_objective_geometry(
    definition: ObjectiveTerrainAreaDefinition, *, terrain_areas: tuple[PlacedTerrainArea, ...]
) -> ObjectiveGeometry:
    if type(definition) is not ObjectiveTerrainAreaDefinition:
        raise GameLifecycleError(
            "Linked objective geometry requires ObjectiveTerrainAreaDefinition."
        )
    areas_by_id = {area.terrain_area_id: area for area in terrain_areas}
    if not set(definition.terrain_area_ids).issubset(areas_by_id):
        raise GameLifecycleError("Linked objective geometry references an unknown terrain area.")
    return ObjectiveGeometry.from_terrain(
        objective_id=definition.objective_marker_id,
        footprint_polygons=tuple(
            tuple(
                (point.x_inches, point.y_inches) for point in areas_by_id[area_id].footprint_polygon
            )
            for area_id in definition.terrain_area_ids
        ),
    )


def mission_objective_geometries(state: GameState) -> tuple[ObjectiveGeometry, ...]:
    from warhammer40k_core.engine.game_state import GameState

    if type(state) is not GameState:
        raise GameLifecycleError("Mission objective geometry requires GameState.")
    setup = state.mission_setup
    battlefield = state.battlefield_state
    if setup is None or battlefield is None:
        raise GameLifecycleError(
            "Mission objective geometry requires mission and battlefield state."
        )
    all_markers = tuple(definition.to_objective_marker() for definition in setup.objective_markers)
    markers, terrain, linked = resolve_objective_control_sources(
        objective_markers=all_markers,
        terrain_features=battlefield.terrain_features,
        ruleset_descriptor=state.ruleset_descriptor_for_runtime_policy(),
        explicit_terrain_objectives=(),
        objective_terrain_areas=setup.objective_terrain_areas,
    )
    linked_ids = {definition.objective_marker_id for definition in linked}
    validate_objective_control_source_references(
        objective_markers=markers,
        terrain_objectives=terrain,
        objective_terrain_areas=linked,
        objective_terrain_area_markers=tuple(
            marker for marker in all_markers if marker.objective_marker_id in linked_ids
        ),
        terrain_areas=setup.terrain_areas,
    )
    geometries = (
        *(ObjectiveGeometry.from_marker(marker) for marker in markers),
        *(
            terrain_objective_geometry(objective, terrain_features=battlefield.terrain_features)
            for objective in terrain
        ),
        *(
            linked_objective_geometry(definition, terrain_areas=setup.terrain_areas)
            for definition in linked
        ),
    )
    return tuple(sorted(geometries, key=lambda geometry: geometry.objective_id))
