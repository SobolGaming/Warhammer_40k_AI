from __future__ import annotations

from collections.abc import Callable

from warhammer40k_core.geometry.polygons import Point2D, point_intersects_polygon

ObjectiveTerrainAreaReferenceRow = tuple[str, object, tuple[str, ...]]
ObjectiveMarkerReferenceRow = tuple[str, object, float, float]
ObjectiveTerrainAreaMembershipReferenceRow = tuple[str, tuple[str, ...]]
TerrainAreaIdentityReferenceRow = tuple[str, str]
TerrainAreaFootprintReferenceRow = tuple[str, str, tuple[Point2D, ...]]


def validate_objective_terrain_area_membership(
    *,
    context_name: str,
    objective_terrain_areas: tuple[ObjectiveTerrainAreaMembershipReferenceRow, ...],
    terrain_areas: tuple[TerrainAreaIdentityReferenceRow, ...],
    error_factory: Callable[[str], ValueError],
) -> None:
    logical_id_by_physical_id = dict(terrain_areas)
    physical_ids_by_logical_id: dict[str, set[str]] = {}
    for physical_id, terrain_logical_id in terrain_areas:
        physical_ids_by_logical_id.setdefault(terrain_logical_id, set()).add(physical_id)
    seen_terrain_area_ids: set[str] = set()
    for _objective_marker_id, terrain_area_ids in objective_terrain_areas:
        referenced_ids = set(terrain_area_ids)
        for terrain_area_id in terrain_area_ids:
            referenced_logical_id = logical_id_by_physical_id.get(terrain_area_id)
            if referenced_logical_id is None:
                raise error_factory(
                    f"{context_name} objective_terrain_areas references unknown terrain area."
                )
            if terrain_area_id in seen_terrain_area_ids:
                raise error_factory(
                    f"{context_name} objective_terrain_areas terrain areas must "
                    "belong to at most one objective."
                )
            seen_terrain_area_ids.add(terrain_area_id)
            if not physical_ids_by_logical_id[referenced_logical_id].issubset(referenced_ids):
                raise error_factory(
                    f"{context_name} objective_terrain_areas must include every physical "
                    "member of each referenced logical terrain area."
                )


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
    terrain_areas_by_id = {
        terrain_area_id: footprint
        for terrain_area_id, _logical_terrain_area_id, footprint in terrain_areas
    }
    validate_objective_terrain_area_membership(
        context_name=context_name,
        objective_terrain_areas=tuple(
            (objective_marker_id, terrain_area_ids)
            for objective_marker_id, _objective_role, terrain_area_ids in objective_terrain_areas
        ),
        terrain_areas=tuple(
            (terrain_area_id, logical_terrain_area_id)
            for terrain_area_id, logical_terrain_area_id, _footprint in terrain_areas
        ),
        error_factory=error_factory,
    )
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
