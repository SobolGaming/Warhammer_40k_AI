from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.geometry.polygons import Point2D, point_intersects_polygon

ObjectiveTerrainAreaReferenceRow = tuple[str, object, tuple[str, ...]]
ObjectiveMarkerReferenceRow = tuple[str, object, float, float]
TerrainAreaFootprintReferenceRow = tuple[str, tuple[Point2D, ...]]


def validate_objective_terrain_area_references(
    *,
    context_name: str,
    objective_terrain_areas: tuple[ObjectiveTerrainAreaReferenceRow, ...],
    objective_markers: tuple[ObjectiveMarkerReferenceRow, ...],
    terrain_areas: tuple[TerrainAreaFootprintReferenceRow, ...],
    error_factory: Callable[[str], ValueError],
) -> None:
    markers_by_id = {
        objective_marker_id: (objective_role, x_inches, y_inches)
        for objective_marker_id, objective_role, x_inches, y_inches in objective_markers
    }
    terrain_areas_by_id = dict(terrain_areas)
    seen_terrain_area_ids: set[str] = set()
    for objective_marker_id, objective_role, terrain_area_ids in objective_terrain_areas:
        marker = markers_by_id.get(objective_marker_id)
        if marker is None:
            raise error_factory(
                f"{context_name} objective_terrain_areas references unknown objective marker."
            )
        marker_role, marker_x, marker_y = marker
        if marker_role is not objective_role:
            raise error_factory(
                f"{context_name} objective_terrain_areas objective_role must "
                "match the referenced objective marker."
            )
        for terrain_area_id in terrain_area_ids:
            if terrain_area_id not in terrain_areas_by_id:
                raise error_factory(
                    f"{context_name} objective_terrain_areas references unknown terrain area."
                )
            if terrain_area_id in seen_terrain_area_ids:
                raise error_factory(
                    f"{context_name} objective_terrain_areas terrain areas must "
                    "belong to at most one objective."
                )
            seen_terrain_area_ids.add(terrain_area_id)
        if not any(
            point_intersects_polygon(
                (marker_x, marker_y),
                terrain_areas_by_id[terrain_area_id],
            )
            for terrain_area_id in terrain_area_ids
        ):
            raise error_factory(
                f"{context_name} objective marker must intersect one of its linked terrain areas."
            )
