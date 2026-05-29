from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.deployment_zones import DeploymentZone, DeploymentZonePayload
from warhammer40k_core.core.missions import (
    DeploymentMapDefinition,
    MissionPackDefinition,
    MissionPoolEntry,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerDefinitionPayload,
)
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureTemplate,
    TerrainFloorTemplate,
    TerrainLayoutTemplate,
    TerrainWallTemplate,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


class MissionSetupPayload(TypedDict):
    mission_pack_id: str
    source_version: str
    source_id: str
    mission_pool_entry_id: str
    primary_mission_id: str
    deployment_map_id: str
    terrain_layout_id: str
    attacker_player_id: str
    defender_player_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    objective_markers: list[ObjectiveMarkerDefinitionPayload]
    deployment_zones: list[DeploymentZonePayload]
    terrain_features: list[TerrainFeatureDefinitionPayload]


class MissionSetupError(GameLifecycleError):
    """Raised when engine mission setup data violates CORE V2 invariants."""


@dataclass(frozen=True, slots=True)
class MissionSetup:
    mission_pack_id: str
    source_version: str
    source_id: str
    mission_pool_entry_id: str
    primary_mission_id: str
    deployment_map_id: str
    terrain_layout_id: str
    attacker_player_id: str
    defender_player_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    objective_markers: tuple[ObjectiveMarkerDefinition, ...]
    deployment_zones: tuple[DeploymentZone, ...]
    terrain_features: tuple[TerrainFeatureDefinition, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_identifier("MissionSetup mission_pack_id", self.mission_pack_id),
        )
        object.__setattr__(
            self,
            "source_version",
            _validate_identifier("MissionSetup source_version", self.source_version),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionSetup source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "mission_pool_entry_id",
            _validate_identifier(
                "MissionSetup mission_pool_entry_id",
                self.mission_pool_entry_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier("MissionSetup primary_mission_id", self.primary_mission_id),
        )
        object.__setattr__(
            self,
            "deployment_map_id",
            _validate_identifier("MissionSetup deployment_map_id", self.deployment_map_id),
        )
        object.__setattr__(
            self,
            "terrain_layout_id",
            _validate_identifier("MissionSetup terrain_layout_id", self.terrain_layout_id),
        )
        attacker = _validate_identifier("MissionSetup attacker_player_id", self.attacker_player_id)
        defender = _validate_identifier("MissionSetup defender_player_id", self.defender_player_id)
        if attacker == defender:
            raise MissionSetupError("MissionSetup attacker and defender must differ.")
        object.__setattr__(self, "attacker_player_id", attacker)
        object.__setattr__(self, "defender_player_id", defender)
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "MissionSetup battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "MissionSetup battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        markers = _validate_objective_markers(self.objective_markers)
        zones = _validate_deployment_zones(self.deployment_zones)
        features = _validate_terrain_features(self.terrain_features)
        _validate_markers_within_battlefield(
            markers=markers,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        _validate_zones_within_battlefield(
            zones=zones,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        _validate_terrain_features_within_battlefield(
            features=features,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        object.__setattr__(self, "objective_markers", markers)
        object.__setattr__(self, "deployment_zones", zones)
        object.__setattr__(self, "terrain_features", features)

    @classmethod
    def from_mission_pack(
        cls,
        *,
        mission_pack: MissionPackDefinition,
        mission_pool_entry_id: str,
        terrain_layout_id: str | None = None,
        attacker_player_id: str,
        defender_player_id: str,
    ) -> Self:
        if type(mission_pack) is not MissionPackDefinition:
            raise MissionSetupError("mission_pack must be a MissionPackDefinition.")
        requested_entry_id = _validate_identifier("mission_pool_entry_id", mission_pool_entry_id)
        pool_entry = next(
            (
                entry
                for entry in mission_pack.mission_pool_entries
                if entry.mission_pool_entry_id == requested_entry_id
            ),
            None,
        )
        if pool_entry is None:
            raise MissionSetupError("Mission pool entry is unknown.")
        selected_terrain_layout_id = (
            pool_entry.terrain_layout_ids[0] if terrain_layout_id is None else terrain_layout_id
        )
        if selected_terrain_layout_id not in pool_entry.terrain_layout_ids:
            raise MissionSetupError("Terrain layout is not legal for the mission pool entry.")
        deployment_map = mission_pack.deployment_map(pool_entry.deployment_map_id)
        terrain_layout = mission_pack.terrain_layout_template(selected_terrain_layout_id)
        return cls.from_components(
            mission_pack=mission_pack,
            mission_pool_entry_id=pool_entry.mission_pool_entry_id,
            primary_mission_id=pool_entry.primary_mission_id,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
            attacker_player_id=attacker_player_id,
            defender_player_id=defender_player_id,
        )

    @classmethod
    def from_components(
        cls,
        *,
        mission_pack: MissionPackDefinition,
        mission_pool_entry_id: str | None = None,
        primary_mission_id: str,
        deployment_map: DeploymentMapDefinition,
        terrain_layout: TerrainLayoutTemplate,
        attacker_player_id: str,
        defender_player_id: str,
    ) -> Self:
        if type(mission_pack) is not MissionPackDefinition:
            raise MissionSetupError("mission_pack must be a MissionPackDefinition.")
        if type(deployment_map) is not DeploymentMapDefinition:
            raise MissionSetupError("deployment_map must be a DeploymentMapDefinition.")
        if type(terrain_layout) is not TerrainLayoutTemplate:
            raise MissionSetupError("terrain_layout must be a TerrainLayoutTemplate.")
        pool_entry = _mission_pool_entry_for_components(
            mission_pack=mission_pack,
            mission_pool_entry_id=mission_pool_entry_id,
            primary_mission_id=primary_mission_id,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
        )
        if deployment_map.battlefield_width_inches != terrain_layout.battlefield_width_inches:
            raise MissionSetupError("Deployment map and terrain layout battlefield widths differ.")
        if deployment_map.battlefield_depth_inches != terrain_layout.battlefield_depth_inches:
            raise MissionSetupError("Deployment map and terrain layout battlefield depths differ.")
        return cls(
            mission_pack_id=mission_pack.mission_pack_id,
            source_version=mission_pack.source_version,
            source_id=mission_pack.source_id,
            mission_pool_entry_id=pool_entry.mission_pool_entry_id,
            primary_mission_id=pool_entry.primary_mission_id,
            deployment_map_id=deployment_map.deployment_map_id,
            terrain_layout_id=terrain_layout.terrain_layout_id,
            attacker_player_id=attacker_player_id,
            defender_player_id=defender_player_id,
            battlefield_width_inches=deployment_map.battlefield_width_inches,
            battlefield_depth_inches=deployment_map.battlefield_depth_inches,
            objective_markers=deployment_map.objective_markers,
            deployment_zones=deployment_map.deployment_zones_for_players(
                attacker_player_id=attacker_player_id,
                defender_player_id=defender_player_id,
            ),
            terrain_features=instantiate_terrain_layout_template(terrain_layout),
        )

    def enemy_deployment_zones_for_player(self, player_id: str) -> tuple[DeploymentZone, ...]:
        requested_player_id = _validate_identifier("player_id", player_id)
        if requested_player_id not in {self.attacker_player_id, self.defender_player_id}:
            raise MissionSetupError("player_id is not part of this mission setup.")
        return tuple(
            zone for zone in self.deployment_zones if zone.player_id != requested_player_id
        )

    def to_payload(self) -> MissionSetupPayload:
        return {
            "mission_pack_id": self.mission_pack_id,
            "source_version": self.source_version,
            "source_id": self.source_id,
            "mission_pool_entry_id": self.mission_pool_entry_id,
            "primary_mission_id": self.primary_mission_id,
            "deployment_map_id": self.deployment_map_id,
            "terrain_layout_id": self.terrain_layout_id,
            "attacker_player_id": self.attacker_player_id,
            "defender_player_id": self.defender_player_id,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "objective_markers": [marker.to_payload() for marker in self.objective_markers],
            "deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
        }

    @classmethod
    def from_payload(cls, payload: MissionSetupPayload) -> Self:
        return cls(
            mission_pack_id=payload["mission_pack_id"],
            source_version=payload["source_version"],
            source_id=payload["source_id"],
            mission_pool_entry_id=payload["mission_pool_entry_id"],
            primary_mission_id=payload["primary_mission_id"],
            deployment_map_id=payload["deployment_map_id"],
            terrain_layout_id=payload["terrain_layout_id"],
            attacker_player_id=payload["attacker_player_id"],
            defender_player_id=payload["defender_player_id"],
            battlefield_width_inches=payload["battlefield_width_inches"],
            battlefield_depth_inches=payload["battlefield_depth_inches"],
            objective_markers=tuple(
                ObjectiveMarkerDefinition.from_payload(marker)
                for marker in payload["objective_markers"]
            ),
            deployment_zones=tuple(
                DeploymentZone.from_payload(zone) for zone in payload["deployment_zones"]
            ),
            terrain_features=tuple(
                TerrainFeatureDefinition.from_payload(feature)
                for feature in payload["terrain_features"]
            ),
        )


def instantiate_terrain_layout_template(
    terrain_layout: TerrainLayoutTemplate,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(terrain_layout) is not TerrainLayoutTemplate:
        raise MissionSetupError("terrain_layout must be a TerrainLayoutTemplate.")
    return tuple(
        sorted(
            (
                _terrain_feature_from_template(feature)
                for feature in terrain_layout.terrain_features
            ),
            key=lambda feature: feature.feature_id,
        )
    )


def _terrain_feature_from_template(
    feature: TerrainFeatureTemplate,
) -> TerrainFeatureDefinition:
    if type(feature) is not TerrainFeatureTemplate:
        raise MissionSetupError("terrain feature template must be a TerrainFeatureTemplate.")
    return TerrainFeatureDefinition(
        feature_id=feature.feature_id,
        feature_kind=feature.feature_kind,
        footprint_center_x_inches=feature.footprint_center_x_inches,
        footprint_center_y_inches=feature.footprint_center_y_inches,
        footprint_width_inches=feature.footprint_width_inches,
        footprint_depth_inches=feature.footprint_depth_inches,
        walls=tuple(_terrain_wall_from_template(wall) for wall in feature.walls),
        floors=tuple(_terrain_floor_from_template(floor) for floor in feature.floors),
        source_id=feature.source_id,
    )


def _terrain_wall_from_template(wall: TerrainWallTemplate) -> TerrainWallDefinition:
    if type(wall) is not TerrainWallTemplate:
        raise MissionSetupError("terrain wall template must be a TerrainWallTemplate.")
    return TerrainWallDefinition(
        wall_id=wall.wall_id,
        center_x_inches=wall.center_x_inches,
        center_y_inches=wall.center_y_inches,
        bottom_z_inches=wall.bottom_z_inches,
        width_inches=wall.width_inches,
        depth_inches=wall.depth_inches,
        height_inches=wall.height_inches,
    )


def _terrain_floor_from_template(floor: TerrainFloorTemplate) -> TerrainFloorDefinition:
    if type(floor) is not TerrainFloorTemplate:
        raise MissionSetupError("terrain floor template must be a TerrainFloorTemplate.")
    return TerrainFloorDefinition(
        floor_id=floor.floor_id,
        center_x_inches=floor.center_x_inches,
        center_y_inches=floor.center_y_inches,
        bottom_z_inches=floor.bottom_z_inches,
        width_inches=floor.width_inches,
        depth_inches=floor.depth_inches,
        thickness_inches=floor.thickness_inches,
    )


def _mission_pool_entry_for_components(
    *,
    mission_pack: MissionPackDefinition,
    mission_pool_entry_id: str | None,
    primary_mission_id: str,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> MissionPoolEntry:
    primary_id = _validate_identifier("primary_mission_id", primary_mission_id)
    _validate_component_belongs_to_mission_pack(
        mission_pack=mission_pack,
        primary_mission_id=primary_id,
        deployment_map=deployment_map,
        terrain_layout=terrain_layout,
    )
    if mission_pool_entry_id is not None:
        requested_entry_id = _validate_identifier(
            "mission_pool_entry_id",
            mission_pool_entry_id,
        )
        for entry in mission_pack.mission_pool_entries:
            if entry.mission_pool_entry_id == requested_entry_id:
                if not _mission_pool_entry_matches_components(
                    entry=entry,
                    primary_mission_id=primary_id,
                    deployment_map=deployment_map,
                    terrain_layout=terrain_layout,
                ):
                    raise MissionSetupError(
                        "Mission pool entry does not match the requested setup components."
                    )
                return entry
        raise MissionSetupError("Mission pool entry is unknown.")

    matches = [
        entry
        for entry in mission_pack.mission_pool_entries
        if _mission_pool_entry_matches_components(
            entry=entry,
            primary_mission_id=primary_id,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
        )
    ]
    if not matches:
        raise MissionSetupError(
            "Mission setup components are not a legal Chapter Approved mission pool row."
        )
    if len(matches) > 1:
        raise MissionSetupError("Mission setup components match multiple mission pool rows.")
    return matches[0]


def _validate_component_belongs_to_mission_pack(
    *,
    mission_pack: MissionPackDefinition,
    primary_mission_id: str,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> None:
    if primary_mission_id not in {
        mission.primary_mission_id for mission in mission_pack.primary_missions
    }:
        raise MissionSetupError("Primary mission is not present in the mission pack.")
    source_deployment_map = next(
        (
            candidate
            for candidate in mission_pack.deployment_maps
            if candidate.deployment_map_id == deployment_map.deployment_map_id
        ),
        None,
    )
    if source_deployment_map is None:
        raise MissionSetupError("Deployment map is not present in the mission pack.")
    if source_deployment_map.to_payload() != deployment_map.to_payload():
        raise MissionSetupError("Deployment map payload does not match the mission pack source.")
    source_terrain_layout = next(
        (
            candidate
            for candidate in mission_pack.terrain_layout_templates
            if candidate.terrain_layout_id == terrain_layout.terrain_layout_id
        ),
        None,
    )
    if source_terrain_layout is None:
        raise MissionSetupError("Terrain layout is not present in the mission pack.")
    if source_terrain_layout.to_payload() != terrain_layout.to_payload():
        raise MissionSetupError("Terrain layout payload does not match the mission pack source.")


def _mission_pool_entry_matches_components(
    *,
    entry: MissionPoolEntry,
    primary_mission_id: str,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> bool:
    return (
        entry.primary_mission_id == primary_mission_id
        and entry.deployment_map_id == deployment_map.deployment_map_id
        and terrain_layout.terrain_layout_id in entry.terrain_layout_ids
    )


def _validate_objective_markers(
    values: object,
) -> tuple[ObjectiveMarkerDefinition, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup objective_markers must be a tuple.")
    markers: list[ObjectiveMarkerDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarkerDefinition:
            raise MissionSetupError(
                "MissionSetup objective_markers must contain ObjectiveMarkerDefinition values."
            )
        if value.objective_marker_id in seen:
            raise MissionSetupError("MissionSetup objective_markers must not contain duplicates.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def _validate_deployment_zones(values: object) -> tuple[DeploymentZone, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup deployment_zones must be a tuple.")
    zones: list[DeploymentZone] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeploymentZone:
            raise MissionSetupError(
                "MissionSetup deployment_zones must contain DeploymentZone values."
            )
        if value.deployment_zone_id in seen:
            raise MissionSetupError("MissionSetup deployment_zones must not contain duplicates.")
        seen.add(value.deployment_zone_id)
        zones.append(value)
    return tuple(sorted(zones, key=lambda zone: zone.deployment_zone_id))


def _validate_terrain_features(
    values: object,
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup terrain_features must be a tuple.")
    features: list[TerrainFeatureDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureDefinition:
            raise MissionSetupError(
                "MissionSetup terrain_features must contain TerrainFeatureDefinition values."
            )
        if value.feature_id in seen:
            raise MissionSetupError("MissionSetup terrain_features must not contain duplicates.")
        seen.add(value.feature_id)
        features.append(value)
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _validate_markers_within_battlefield(
    *,
    markers: tuple[ObjectiveMarkerDefinition, ...],
    width: float,
    depth: float,
) -> None:
    for marker in markers:
        if marker.x_inches < 0.0 or marker.x_inches > width:
            raise MissionSetupError("MissionSetup objective marker x is outside the battlefield.")
        if marker.y_inches < 0.0 or marker.y_inches > depth:
            raise MissionSetupError("MissionSetup objective marker y is outside the battlefield.")


def _validate_zones_within_battlefield(
    *,
    zones: tuple[DeploymentZone, ...],
    width: float,
    depth: float,
) -> None:
    for zone in zones:
        if zone.min_x < 0.0 or zone.max_x > width:
            raise MissionSetupError("MissionSetup deployment zone x is outside the battlefield.")
        if zone.min_y < 0.0 or zone.max_y > depth:
            raise MissionSetupError("MissionSetup deployment zone y is outside the battlefield.")


def _validate_terrain_features_within_battlefield(
    *,
    features: tuple[TerrainFeatureDefinition, ...],
    width: float,
    depth: float,
) -> None:
    for feature in features:
        min_x, min_y, max_x, max_y = feature.bounds()
        if min_x < 0.0 or max_x > width:
            raise MissionSetupError("MissionSetup terrain feature x is outside the battlefield.")
        if min_y < 0.0 or max_y > depth:
            raise MissionSetupError("MissionSetup terrain feature y is outside the battlefield.")


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise MissionSetupError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise MissionSetupError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise MissionSetupError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise MissionSetupError(f"{field_name} must be finite.")
    if number <= 0.0:
        raise MissionSetupError(f"{field_name} must be greater than 0.")
    return number
