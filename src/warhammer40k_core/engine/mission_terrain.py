from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    TerrainAreaError,
    validate_placed_terrain_area_logical_groups,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.volume import Model as GeometryModel


@dataclass(frozen=True, slots=True)
class MissionLogicalTerrainArea:
    """One rules terrain area, including every source-linked physical polygon member."""

    logical_terrain_area_id: str
    members: tuple[PlacedTerrainArea, ...]

    def __post_init__(self) -> None:
        logical_id = _validate_identifier(
            "MissionLogicalTerrainArea logical_terrain_area_id",
            self.logical_terrain_area_id,
        )
        if type(self.members) is not tuple or not self.members:
            raise GameLifecycleError("MissionLogicalTerrainArea members must be non-empty.")
        members: list[PlacedTerrainArea] = []
        for value in cast(tuple[object, ...], self.members):
            if type(value) is not PlacedTerrainArea:
                raise GameLifecycleError(
                    "MissionLogicalTerrainArea members must contain PlacedTerrainArea values."
                )
            if value.logical_terrain_area_id != logical_id:
                raise GameLifecycleError(
                    "MissionLogicalTerrainArea members must share the logical terrain-area ID."
                )
            members.append(value)
        object.__setattr__(self, "logical_terrain_area_id", logical_id)
        object.__setattr__(
            self,
            "members",
            tuple(sorted(members, key=lambda member: member.terrain_area_id)),
        )

    def footprint_polygons(self) -> tuple[tuple[tuple[float, float], ...], ...]:
        return tuple(
            tuple((point.x_inches, point.y_inches) for point in member.footprint_polygon)
            for member in self.members
        )

    def bounds(self) -> tuple[float, float, float, float]:
        points = tuple(point for polygon in self.footprint_polygons() for point in polygon)
        return (
            min(point[0] for point in points),
            min(point[1] for point in points),
            max(point[0] for point in points),
            max(point[1] for point in points),
        )


def mission_logical_terrain_areas(
    mission_setup: MissionSetup,
) -> tuple[MissionLogicalTerrainArea, ...]:
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Logical terrain-area lookup requires MissionSetup.")
    try:
        physical_areas = validate_placed_terrain_area_logical_groups(
            "MissionSetup terrain_areas",
            mission_setup.terrain_areas,
        )
    except TerrainAreaError as exc:
        raise GameLifecycleError("MissionSetup terrain-area graph is invalid.") from exc
    members_by_logical_id: dict[str, list[PlacedTerrainArea]] = {}
    for area in physical_areas:
        members_by_logical_id.setdefault(area.logical_terrain_area_id, []).append(area)
    return tuple(
        MissionLogicalTerrainArea(
            logical_terrain_area_id=logical_id,
            members=tuple(members),
        )
        for logical_id, members in sorted(members_by_logical_id.items())
    )


def optional_mission_logical_terrain_areas(
    mission_setup: MissionSetup | None,
) -> tuple[MissionLogicalTerrainArea, ...]:
    if mission_setup is None:
        return ()
    return mission_logical_terrain_areas(mission_setup)


def mission_logical_terrain_area_by_id(
    mission_setup: MissionSetup,
    *,
    logical_terrain_area_id: str,
) -> MissionLogicalTerrainArea:
    requested_id = _validate_identifier("logical_terrain_area_id", logical_terrain_area_id)
    for area in mission_logical_terrain_areas(mission_setup):
        if area.logical_terrain_area_id == requested_id:
            return area
    raise GameLifecycleError("Logical terrain-area lookup references an unknown terrain area.")


def logical_terrain_area_within_player_deployment_zone(
    area: MissionLogicalTerrainArea,
    *,
    mission_setup: MissionSetup,
    player_id: str,
) -> bool:
    _require_logical_terrain_area(area)
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Deployment-zone terrain target check requires MissionSetup.")
    _validate_logical_area_matches_setup(area, mission_setup=mission_setup)
    requested_player = _validate_identifier("player_id", player_id)
    zones = tuple(
        zone for zone in mission_setup.deployment_zones if zone.player_id == requested_player
    )
    if not zones:
        raise GameLifecycleError("Deployment-zone terrain target check requires player zone.")
    return all(
        shapely_backend.deployment_zone_shapes_cover_polygon(
            shapes=tuple(zone.shape for zone in zones),
            polygon=polygon,
        )
        for polygon in area.footprint_polygons()
    )


def logical_terrain_area_within_player_territory(
    area: MissionLogicalTerrainArea,
    *,
    mission_setup: MissionSetup,
    player_id: str,
) -> bool:
    _require_logical_terrain_area(area)
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Territory terrain target check requires MissionSetup.")
    _validate_logical_area_matches_setup(area, mission_setup=mission_setup)
    requested_player = _validate_identifier("player_id", player_id)
    if requested_player == mission_setup.attacker_player_id:
        owner_role = "attacker"
    elif requested_player == mission_setup.defender_player_id:
        owner_role = "defender"
    else:
        raise GameLifecycleError("Territory terrain target player has no mission role.")
    territories = tuple(
        region
        for region in mission_setup.battlefield_regions
        if region.region_kind is BattlefieldRegionKind.TERRITORY and region.owner_role == owner_role
    )
    if len(territories) != 1:
        raise GameLifecycleError("Territory terrain target check requires one player territory.")
    territory = territories[0]
    return all(
        shapely_backend.deployment_zone_shapes_cover_polygon(
            shapes=(territory.shape,),
            polygon=polygon,
        )
        for polygon in area.footprint_polygons()
    )


def model_intersects_logical_terrain_area(
    model: GeometryModel,
    *,
    area: MissionLogicalTerrainArea,
) -> bool:
    if type(model) is not GeometryModel:
        raise GameLifecycleError("Terrain-area occupancy requires a GeometryModel.")
    _require_logical_terrain_area(area)
    return shapely_backend.base_footprint_intersects_polygon_union(
        model.base,
        model.pose,
        area.footprint_polygons(),
    )


def logical_terrain_area_is_objective(
    area: MissionLogicalTerrainArea,
    *,
    mission_setup: MissionSetup,
) -> bool:
    """Return whether the source-linked area-to-marker association marks this area."""
    _require_logical_terrain_area(area)
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Terrain objective lookup requires MissionSetup.")
    _validate_logical_area_matches_setup(area, mission_setup=mission_setup)
    member_ids = {member.terrain_area_id for member in area.members}
    return any(
        member_ids.intersection(association.terrain_area_ids)
        for association in mission_setup.objective_terrain_areas
    )


def objective_logical_terrain_area_ids(
    mission_setup: MissionSetup | None,
) -> frozenset[str]:
    return frozenset(
        area.logical_terrain_area_id
        for area in optional_mission_logical_terrain_areas(mission_setup)
        if mission_setup is not None
        and logical_terrain_area_is_objective(area, mission_setup=mission_setup)
    )


def _require_logical_terrain_area(value: object) -> MissionLogicalTerrainArea:
    if type(value) is not MissionLogicalTerrainArea:
        raise GameLifecycleError("Terrain-area target requires MissionLogicalTerrainArea.")
    return value


def _validate_logical_area_matches_setup(
    area: MissionLogicalTerrainArea,
    *,
    mission_setup: MissionSetup,
) -> None:
    canonical_area = mission_logical_terrain_area_by_id(
        mission_setup,
        logical_terrain_area_id=area.logical_terrain_area_id,
    )
    if area != canonical_area:
        raise GameLifecycleError("Logical terrain-area target drifted from MissionSetup.")


_validate_identifier = IdentifierValidator(GameLifecycleError)


__all__ = (
    "MissionLogicalTerrainArea",
    "logical_terrain_area_is_objective",
    "logical_terrain_area_within_player_deployment_zone",
    "logical_terrain_area_within_player_territory",
    "mission_logical_terrain_area_by_id",
    "mission_logical_terrain_areas",
    "model_intersects_logical_terrain_area",
    "objective_logical_terrain_area_ids",
    "optional_mission_logical_terrain_areas",
)
