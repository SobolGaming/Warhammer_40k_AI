from __future__ import annotations

from warhammer40k_core.core.battlefield_regions import BattlefieldRegionKind
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition


def terrain_feature_within_player_deployment_zone(
    feature: TerrainFeatureDefinition,
    *,
    mission_setup: MissionSetup,
    player_id: str,
) -> bool:
    if type(feature) is not TerrainFeatureDefinition:
        raise GameLifecycleError("terrain feature target requires TerrainFeatureDefinition.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Deployment-zone terrain target check requires MissionSetup.")
    requested_player = _validate_identifier("player_id", player_id)
    zones = tuple(
        zone for zone in mission_setup.deployment_zones if zone.player_id == requested_player
    )
    if not zones:
        raise GameLifecycleError("Deployment-zone terrain target check requires player zone.")
    return shapely_backend.deployment_zone_shapes_cover_bounds(
        shapes=tuple(zone.shape for zone in zones),
        bounds=feature.bounds(),
    )


def terrain_feature_within_player_territory(
    feature: TerrainFeatureDefinition,
    *,
    mission_setup: MissionSetup,
    player_id: str,
) -> bool:
    if type(feature) is not TerrainFeatureDefinition:
        raise GameLifecycleError("terrain feature target requires TerrainFeatureDefinition.")
    if type(mission_setup) is not MissionSetup:
        raise GameLifecycleError("Territory terrain target check requires MissionSetup.")
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
    return shapely_backend.deployment_zone_shapes_cover_bounds(
        shapes=(territory.shape,),
        bounds=feature.bounds(),
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
