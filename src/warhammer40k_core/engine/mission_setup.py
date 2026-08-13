from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.battlefield_regions import (
    BattlefieldRegion,
    BattlefieldRegionPayload,
)
from warhammer40k_core.core.deployment_zones import DeploymentZone, DeploymentZonePayload
from warhammer40k_core.core.missions import (
    BattlefieldLayoutDefinition,
    DeploymentMapDefinition,
    MissionPackDefinition,
    MissionPoolEntry,
    ObjectiveMarkerDefinition,
    ObjectiveMarkerDefinitionPayload,
    ObjectiveTerrainAreaDefinition,
    ObjectiveTerrainAreaDefinitionPayload,
)
from warhammer40k_core.core.objective_terrain_area_references import (
    validate_objective_terrain_area_references,
)
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    PlacedTerrainAreaPayload,
    TerrainAreaError,
    TerrainAreaFootprintTemplate,
    validate_placed_terrain_area_logical_groups,
)
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    TerrainFeaturePreset,
    TerrainLayoutTemplate,
)
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.terrain_feature_factory import TerrainFeatureFactory
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFeatureDefinitionPayload,
)


class PlayerPrimaryMissionAssignmentPayload(TypedDict):
    player_id: str
    force_disposition_id: str
    primary_mission_id: str


class MissionSetupPayload(TypedDict):
    mission_pack_id: str
    source_version: str
    source_id: str
    mission_pool_entry_id: str
    primary_mission_assignments: list[PlayerPrimaryMissionAssignmentPayload]
    battlefield_layout_id: str | None
    deployment_map_id: str
    terrain_layout_id: str
    attacker_player_id: str
    defender_player_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    objective_markers: list[ObjectiveMarkerDefinitionPayload]
    deployment_zones: list[DeploymentZonePayload]
    battlefield_regions: list[BattlefieldRegionPayload]
    terrain_areas: list[PlacedTerrainAreaPayload]
    objective_terrain_areas: list[ObjectiveTerrainAreaDefinitionPayload]
    terrain_features: list[TerrainFeatureDefinitionPayload]


class MissionSetupError(GameLifecycleError):
    """Raised when engine mission setup data violates CORE V2 invariants."""


@dataclass(frozen=True, slots=True)
class PlayerPrimaryMissionAssignment:
    player_id: str
    force_disposition_id: str
    primary_mission_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier(
                "PlayerPrimaryMissionAssignment player_id",
                self.player_id,
            ),
        )
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_identifier(
                "PlayerPrimaryMissionAssignment force_disposition_id",
                self.force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier(
                "PlayerPrimaryMissionAssignment primary_mission_id",
                self.primary_mission_id,
            ),
        )

    def to_payload(self) -> PlayerPrimaryMissionAssignmentPayload:
        return {
            "player_id": self.player_id,
            "force_disposition_id": self.force_disposition_id,
            "primary_mission_id": self.primary_mission_id,
        }

    @classmethod
    def from_payload(cls, payload: PlayerPrimaryMissionAssignmentPayload) -> Self:
        if set(payload) != {"player_id", "force_disposition_id", "primary_mission_id"}:
            raise MissionSetupError("PlayerPrimaryMissionAssignment payload fields are invalid.")
        return cls(
            player_id=payload["player_id"],
            force_disposition_id=payload["force_disposition_id"],
            primary_mission_id=payload["primary_mission_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionSetup:
    mission_pack_id: str
    source_version: str
    source_id: str
    mission_pool_entry_id: str
    primary_mission_assignments: tuple[PlayerPrimaryMissionAssignment, ...]
    battlefield_layout_id: str | None
    deployment_map_id: str
    terrain_layout_id: str
    attacker_player_id: str
    defender_player_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    objective_markers: tuple[ObjectiveMarkerDefinition, ...]
    deployment_zones: tuple[DeploymentZone, ...]
    battlefield_regions: tuple[BattlefieldRegion, ...]
    terrain_areas: tuple[PlacedTerrainArea, ...]
    terrain_features: tuple[TerrainFeatureDefinition, ...]
    objective_terrain_areas: tuple[ObjectiveTerrainAreaDefinition, ...] = ()

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
            "battlefield_layout_id",
            _validate_optional_identifier(
                "MissionSetup battlefield_layout_id",
                self.battlefield_layout_id,
            ),
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
            "primary_mission_assignments",
            _validate_player_primary_mission_assignments(
                self.primary_mission_assignments,
                player_ids=(attacker, defender),
            ),
        )
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
        regions = _validate_battlefield_regions(self.battlefield_regions)
        terrain_areas = _validate_terrain_areas(self.terrain_areas)
        features = _validate_terrain_features(self.terrain_features)
        objective_terrain_areas = _validate_objective_terrain_areas(self.objective_terrain_areas)
        if self.battlefield_layout_id is None and (terrain_areas or objective_terrain_areas):
            raise MissionSetupError(
                "MissionSetup source-backed battlefield geometry requires battlefield_layout_id."
            )
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
        _validate_battlefield_regions_within_battlefield(
            regions=regions,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        _validate_terrain_areas_within_battlefield(
            terrain_areas=terrain_areas,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        _validate_terrain_features_within_battlefield(
            features=features,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        validate_objective_terrain_area_references(
            context_name="MissionSetup",
            objective_terrain_areas=tuple(
                (
                    definition.objective_marker_id,
                    definition.objective_role,
                    definition.terrain_area_ids,
                )
                for definition in objective_terrain_areas
            ),
            objective_markers=tuple(
                (
                    marker.objective_marker_id,
                    marker.objective_role,
                    marker.x_inches,
                    marker.y_inches,
                )
                for marker in markers
            ),
            terrain_areas=tuple(
                (
                    area.terrain_area_id,
                    area.logical_terrain_area_id,
                    tuple((point.x_inches, point.y_inches) for point in area.footprint_polygon),
                )
                for area in terrain_areas
            ),
            error_factory=MissionSetupError,
        )
        object.__setattr__(self, "objective_markers", markers)
        object.__setattr__(self, "deployment_zones", zones)
        object.__setattr__(self, "battlefield_regions", regions)
        object.__setattr__(self, "terrain_areas", terrain_areas)
        object.__setattr__(self, "terrain_features", features)
        object.__setattr__(self, "objective_terrain_areas", objective_terrain_areas)

    @classmethod
    def from_mission_pack(
        cls,
        *,
        mission_pack: MissionPackDefinition,
        mission_pool_entry_id: str,
        terrain_layout_id: str | None = None,
        attacker_player_id: str,
        attacker_force_disposition_id: str,
        defender_player_id: str,
        defender_force_disposition_id: str,
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
        battlefield_layout = _battlefield_layout_for_components(
            mission_pack=mission_pack,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
        )
        return cls.from_components(
            mission_pack=mission_pack,
            mission_pool_entry_id=pool_entry.mission_pool_entry_id,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
            battlefield_layout=battlefield_layout,
            attacker_player_id=attacker_player_id,
            attacker_force_disposition_id=attacker_force_disposition_id,
            defender_player_id=defender_player_id,
            defender_force_disposition_id=defender_force_disposition_id,
        )

    @classmethod
    def from_components(
        cls,
        *,
        mission_pack: MissionPackDefinition,
        mission_pool_entry_id: str | None = None,
        deployment_map: DeploymentMapDefinition,
        terrain_layout: TerrainLayoutTemplate,
        battlefield_layout: BattlefieldLayoutDefinition | None = None,
        attacker_player_id: str,
        attacker_force_disposition_id: str,
        defender_player_id: str,
        defender_force_disposition_id: str,
    ) -> Self:
        if type(mission_pack) is not MissionPackDefinition:
            raise MissionSetupError("mission_pack must be a MissionPackDefinition.")
        if type(deployment_map) is not DeploymentMapDefinition:
            raise MissionSetupError("deployment_map must be a DeploymentMapDefinition.")
        if type(terrain_layout) is not TerrainLayoutTemplate:
            raise MissionSetupError("terrain_layout must be a TerrainLayoutTemplate.")
        if (
            battlefield_layout is not None
            and type(battlefield_layout) is not BattlefieldLayoutDefinition
        ):
            raise MissionSetupError(
                "battlefield_layout must be a BattlefieldLayoutDefinition or None."
            )
        pool_entry = _mission_pool_entry_for_components(
            mission_pack=mission_pack,
            mission_pool_entry_id=mission_pool_entry_id,
            attacker_force_disposition_id=attacker_force_disposition_id,
            defender_force_disposition_id=defender_force_disposition_id,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
        )
        primary_assignments = _player_primary_mission_assignments(
            mission_pack=mission_pack,
            attacker_player_id=attacker_player_id,
            attacker_force_disposition_id=attacker_force_disposition_id,
            defender_player_id=defender_player_id,
            defender_force_disposition_id=defender_force_disposition_id,
        )
        if deployment_map.battlefield_width_inches != terrain_layout.battlefield_width_inches:
            raise MissionSetupError("Deployment map and terrain layout battlefield widths differ.")
        if deployment_map.battlefield_depth_inches != terrain_layout.battlefield_depth_inches:
            raise MissionSetupError("Deployment map and terrain layout battlefield depths differ.")
        if battlefield_layout is None:
            battlefield_layout = _battlefield_layout_for_components(
                mission_pack=mission_pack,
                deployment_map=deployment_map,
                terrain_layout=terrain_layout,
            )
        if battlefield_layout is not None:
            _validate_battlefield_layout_matches_components(
                mission_pack=mission_pack,
                battlefield_layout=battlefield_layout,
                deployment_map=deployment_map,
                terrain_layout=terrain_layout,
            )
            _validate_battlefield_layout_matches_force_dispositions(
                mission_pack=mission_pack,
                battlefield_layout=battlefield_layout,
                attacker_force_disposition_id=attacker_force_disposition_id,
                defender_force_disposition_id=defender_force_disposition_id,
            )
        objective_markers = (
            deployment_map.objective_markers
            if battlefield_layout is None
            else battlefield_layout.objective_markers
        )
        deployment_zones = (
            deployment_map.deployment_zones_for_players(
                attacker_player_id=attacker_player_id,
                defender_player_id=defender_player_id,
            )
            if battlefield_layout is None
            else _deployment_zones_for_players(
                battlefield_layout.deployment_zones,
                attacker_player_id=attacker_player_id,
                defender_player_id=defender_player_id,
            )
        )
        return cls(
            mission_pack_id=mission_pack.mission_pack_id,
            source_version=mission_pack.source_version,
            source_id=mission_pack.source_id,
            mission_pool_entry_id=pool_entry.mission_pool_entry_id,
            primary_mission_assignments=primary_assignments,
            battlefield_layout_id=(
                None if battlefield_layout is None else battlefield_layout.battlefield_layout_id
            ),
            deployment_map_id=deployment_map.deployment_map_id,
            terrain_layout_id=terrain_layout.terrain_layout_id,
            attacker_player_id=attacker_player_id,
            defender_player_id=defender_player_id,
            battlefield_width_inches=deployment_map.battlefield_width_inches,
            battlefield_depth_inches=deployment_map.battlefield_depth_inches,
            objective_markers=objective_markers,
            deployment_zones=deployment_zones,
            battlefield_regions=(
                () if battlefield_layout is None else battlefield_layout.battlefield_regions
            ),
            terrain_areas=(() if battlefield_layout is None else battlefield_layout.terrain_areas),
            terrain_features=instantiate_terrain_layout_template(
                terrain_layout,
                terrain_areas=(
                    () if battlefield_layout is None else battlefield_layout.terrain_areas
                ),
                terrain_area_footprint_templates=mission_pack.terrain_area_footprint_templates,
                terrain_feature_presets=mission_pack.terrain_feature_presets,
                terrain_feature_placements=(
                    ()
                    if battlefield_layout is None
                    else battlefield_layout.terrain_feature_placements
                ),
            ),
            objective_terrain_areas=(
                () if battlefield_layout is None else battlefield_layout.objective_terrain_areas
            ),
        )

    def enemy_deployment_zones_for_player(self, player_id: str) -> tuple[DeploymentZone, ...]:
        requested_player_id = _validate_identifier("player_id", player_id)
        if requested_player_id not in {self.attacker_player_id, self.defender_player_id}:
            raise MissionSetupError("player_id is not part of this mission setup.")
        return tuple(
            zone for zone in self.deployment_zones if zone.player_id != requested_player_id
        )

    def primary_mission_assignment_for_player(
        self,
        player_id: str,
    ) -> PlayerPrimaryMissionAssignment:
        requested_player_id = _validate_identifier("player_id", player_id)
        for assignment in self.primary_mission_assignments:
            if assignment.player_id == requested_player_id:
                return assignment
        raise MissionSetupError("player_id is not part of this mission setup.")

    def primary_mission_id_for_player(self, player_id: str) -> str:
        return self.primary_mission_assignment_for_player(player_id).primary_mission_id

    def force_disposition_id_for_player(self, player_id: str) -> str:
        return self.primary_mission_assignment_for_player(player_id).force_disposition_id

    def to_payload(self) -> MissionSetupPayload:
        return {
            "mission_pack_id": self.mission_pack_id,
            "source_version": self.source_version,
            "source_id": self.source_id,
            "mission_pool_entry_id": self.mission_pool_entry_id,
            "primary_mission_assignments": [
                assignment.to_payload() for assignment in self.primary_mission_assignments
            ],
            "battlefield_layout_id": self.battlefield_layout_id,
            "deployment_map_id": self.deployment_map_id,
            "terrain_layout_id": self.terrain_layout_id,
            "attacker_player_id": self.attacker_player_id,
            "defender_player_id": self.defender_player_id,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "objective_markers": [marker.to_payload() for marker in self.objective_markers],
            "deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "battlefield_regions": [region.to_payload() for region in self.battlefield_regions],
            "terrain_areas": [area.to_payload() for area in self.terrain_areas],
            "objective_terrain_areas": [
                objective_terrain_area.to_payload()
                for objective_terrain_area in self.objective_terrain_areas
            ],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
        }

    @classmethod
    def from_payload(cls, payload: MissionSetupPayload) -> Self:
        if set(payload) != {
            "mission_pack_id",
            "source_version",
            "source_id",
            "mission_pool_entry_id",
            "primary_mission_assignments",
            "battlefield_layout_id",
            "deployment_map_id",
            "terrain_layout_id",
            "attacker_player_id",
            "defender_player_id",
            "battlefield_width_inches",
            "battlefield_depth_inches",
            "objective_markers",
            "deployment_zones",
            "battlefield_regions",
            "terrain_areas",
            "objective_terrain_areas",
            "terrain_features",
        }:
            raise MissionSetupError("MissionSetup payload fields are invalid.")
        return cls(
            mission_pack_id=payload["mission_pack_id"],
            source_version=payload["source_version"],
            source_id=payload["source_id"],
            mission_pool_entry_id=payload["mission_pool_entry_id"],
            primary_mission_assignments=tuple(
                PlayerPrimaryMissionAssignment.from_payload(assignment)
                for assignment in payload["primary_mission_assignments"]
            ),
            battlefield_layout_id=payload["battlefield_layout_id"],
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
            battlefield_regions=tuple(
                BattlefieldRegion.from_payload(region) for region in payload["battlefield_regions"]
            ),
            terrain_areas=tuple(
                _placed_terrain_area_from_payload(area) for area in payload["terrain_areas"]
            ),
            objective_terrain_areas=tuple(
                ObjectiveTerrainAreaDefinition.from_payload(objective_terrain_area)
                for objective_terrain_area in payload["objective_terrain_areas"]
            ),
            terrain_features=tuple(
                TerrainFeatureDefinition.from_payload(feature)
                for feature in payload["terrain_features"]
            ),
        )


def validate_mission_setup_source_layout_identity(
    mission_setup: MissionSetup,
    *,
    battlefield_layout: BattlefieldLayoutDefinition,
    source_terrain_features: tuple[TerrainFeatureDefinition, ...],
) -> None:
    if type(mission_setup) is not MissionSetup:
        raise MissionSetupError("Source-layout validation requires MissionSetup.")
    if type(battlefield_layout) is not BattlefieldLayoutDefinition:
        raise MissionSetupError("Source-layout validation requires BattlefieldLayoutDefinition.")
    canonical_terrain_features = _validate_terrain_features(source_terrain_features)
    actual_source_geometry = (
        mission_setup.battlefield_layout_id,
        mission_setup.deployment_map_id,
        mission_setup.terrain_layout_id,
        mission_setup.battlefield_width_inches,
        mission_setup.battlefield_depth_inches,
        mission_setup.objective_markers,
        mission_setup.deployment_zones,
        mission_setup.battlefield_regions,
        mission_setup.terrain_areas,
        mission_setup.objective_terrain_areas,
        mission_setup.terrain_features,
    )
    canonical_source_geometry = (
        battlefield_layout.battlefield_layout_id,
        battlefield_layout.deployment_map_id,
        battlefield_layout.terrain_layout_id,
        battlefield_layout.battlefield_width_inches,
        battlefield_layout.battlefield_depth_inches,
        battlefield_layout.objective_markers,
        _deployment_zones_for_players(
            battlefield_layout.deployment_zones,
            attacker_player_id=mission_setup.attacker_player_id,
            defender_player_id=mission_setup.defender_player_id,
        ),
        battlefield_layout.battlefield_regions,
        battlefield_layout.terrain_areas,
        battlefield_layout.objective_terrain_areas,
        canonical_terrain_features,
    )
    if actual_source_geometry != canonical_source_geometry:
        raise MissionSetupError("MissionSetup battlefield geometry drifted from source layout.")


def _placed_terrain_area_from_payload(
    payload: PlacedTerrainAreaPayload,
) -> PlacedTerrainArea:
    try:
        return PlacedTerrainArea.from_payload(payload)
    except TerrainAreaError as exc:
        raise MissionSetupError("MissionSetup terrain-area payload is invalid.") from exc


def instantiate_terrain_layout_template(
    terrain_layout: TerrainLayoutTemplate,
    *,
    terrain_areas: tuple[PlacedTerrainArea, ...] = (),
    terrain_area_footprint_templates: tuple[TerrainAreaFootprintTemplate, ...] = (),
    terrain_feature_presets: tuple[TerrainFeaturePreset, ...] = (),
    terrain_feature_placements: tuple[TerrainFeatureAreaPlacement, ...] = (),
) -> tuple[TerrainFeatureDefinition, ...]:
    if type(terrain_layout) is not TerrainLayoutTemplate:
        raise MissionSetupError("terrain_layout must be a TerrainLayoutTemplate.")
    area_features = _terrain_features_from_area_placements(
        terrain_areas=terrain_areas,
        terrain_area_footprint_templates=terrain_area_footprint_templates,
        terrain_feature_presets=terrain_feature_presets,
        terrain_feature_placements=terrain_feature_placements,
    )
    return _validate_terrain_features(
        tuple(
            sorted(
                (
                    *(
                        TerrainFeatureFactory.from_static_template(feature)
                        for feature in terrain_layout.terrain_features
                    ),
                    *area_features,
                ),
                key=lambda feature: feature.feature_id,
            )
        )
    )


def _terrain_features_from_area_placements(
    *,
    terrain_areas: tuple[PlacedTerrainArea, ...],
    terrain_area_footprint_templates: tuple[TerrainAreaFootprintTemplate, ...],
    terrain_feature_presets: tuple[TerrainFeaturePreset, ...],
    terrain_feature_placements: tuple[TerrainFeatureAreaPlacement, ...],
) -> tuple[TerrainFeatureDefinition, ...]:
    areas = _validate_terrain_areas(terrain_areas)
    footprint_templates = _validate_terrain_area_footprint_templates(
        terrain_area_footprint_templates
    )
    presets = _validate_terrain_feature_presets(terrain_feature_presets)
    placements = _validate_terrain_feature_area_placements(terrain_feature_placements)
    areas_by_id = {area.terrain_area_id: area for area in areas}
    areas_by_logical_id: dict[str, list[PlacedTerrainArea]] = {}
    for member_area in areas:
        areas_by_logical_id.setdefault(member_area.logical_terrain_area_id, []).append(member_area)
    footprint_templates_by_id = {
        template.footprint_template_id: template for template in footprint_templates
    }
    presets_by_id = {preset.terrain_feature_preset_id: preset for preset in presets}
    features: list[TerrainFeatureDefinition] = []
    for placement in placements:
        area = areas_by_id.get(placement.terrain_area_id)
        if area is None:
            raise MissionSetupError("Terrain feature area placement references unknown area.")
        preset = presets_by_id.get(placement.terrain_feature_preset_id)
        if preset is None:
            raise MissionSetupError("Terrain feature area placement references unknown preset.")
        if preset.footprint_template_id != area.footprint_template_id:
            raise MissionSetupError(
                "Terrain feature area placement preset footprint does not match terrain area."
            )
        footprint_template = footprint_templates_by_id.get(area.footprint_template_id)
        if footprint_template is None:
            raise MissionSetupError(
                "Terrain feature area placement references unknown footprint template."
            )
        features.append(
            TerrainFeatureFactory.from_area_placement(
                area=area,
                footprint_template=footprint_template,
                preset=preset,
                placement=placement,
                terrain_area_group=tuple(areas_by_logical_id[area.logical_terrain_area_id]),
            )
        )
    return tuple(sorted(features, key=lambda feature: feature.feature_id))


def _player_primary_mission_assignments(
    *,
    mission_pack: MissionPackDefinition,
    attacker_player_id: str,
    attacker_force_disposition_id: str,
    defender_player_id: str,
    defender_force_disposition_id: str,
) -> tuple[PlayerPrimaryMissionAssignment, ...]:
    attacker = _validate_identifier("attacker_player_id", attacker_player_id)
    defender = _validate_identifier("defender_player_id", defender_player_id)
    if attacker == defender:
        raise MissionSetupError("Attacker and defender player IDs must differ.")
    attacker_disposition = _validate_identifier(
        "attacker_force_disposition_id",
        attacker_force_disposition_id,
    )
    defender_disposition = _validate_identifier(
        "defender_force_disposition_id",
        defender_force_disposition_id,
    )
    known_disposition_ids = {
        disposition.force_disposition_id for disposition in mission_pack.force_dispositions
    }
    if attacker_disposition not in known_disposition_ids:
        raise MissionSetupError("Attacker Force Disposition is not present in the mission pack.")
    if defender_disposition not in known_disposition_ids:
        raise MissionSetupError("Defender Force Disposition is not present in the mission pack.")
    attacker_primary = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id=attacker_disposition,
        opponent_force_disposition_id=defender_disposition,
    ).primary_mission_id
    defender_primary = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id=defender_disposition,
        opponent_force_disposition_id=attacker_disposition,
    ).primary_mission_id
    return tuple(
        sorted(
            (
                PlayerPrimaryMissionAssignment(
                    player_id=attacker,
                    force_disposition_id=attacker_disposition,
                    primary_mission_id=attacker_primary,
                ),
                PlayerPrimaryMissionAssignment(
                    player_id=defender,
                    force_disposition_id=defender_disposition,
                    primary_mission_id=defender_primary,
                ),
            ),
            key=lambda assignment: assignment.player_id,
        )
    )


def _mission_pool_entry_for_components(
    *,
    mission_pack: MissionPackDefinition,
    mission_pool_entry_id: str | None,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> MissionPoolEntry:
    attacker_disposition_id = _validate_identifier(
        "attacker_force_disposition_id",
        attacker_force_disposition_id,
    )
    defender_disposition_id = _validate_identifier(
        "defender_force_disposition_id",
        defender_force_disposition_id,
    )
    _validate_component_belongs_to_mission_pack(
        mission_pack=mission_pack,
        force_disposition_ids=(attacker_disposition_id, defender_disposition_id),
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
                    attacker_force_disposition_id=attacker_disposition_id,
                    defender_force_disposition_id=defender_disposition_id,
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
            attacker_force_disposition_id=attacker_disposition_id,
            defender_force_disposition_id=defender_disposition_id,
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
    force_disposition_ids: tuple[str, str],
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> None:
    known_force_disposition_ids = {
        disposition.force_disposition_id for disposition in mission_pack.force_dispositions
    }
    if any(
        force_disposition_id not in known_force_disposition_ids
        for force_disposition_id in force_disposition_ids
    ):
        raise MissionSetupError("Force disposition is not present in the mission pack.")
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


def _battlefield_layout_for_components(
    *,
    mission_pack: MissionPackDefinition,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> BattlefieldLayoutDefinition | None:
    matches = [
        layout
        for layout in mission_pack.battlefield_layouts
        if layout.deployment_map_id == deployment_map.deployment_map_id
        and layout.terrain_layout_id == terrain_layout.terrain_layout_id
    ]
    if not matches:
        return None
    if len(matches) > 1:
        raise MissionSetupError("Mission setup components match multiple battlefield layouts.")
    return matches[0]


def _validate_battlefield_layout_matches_components(
    *,
    mission_pack: MissionPackDefinition,
    battlefield_layout: BattlefieldLayoutDefinition,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> None:
    source_layout = next(
        (
            candidate
            for candidate in mission_pack.battlefield_layouts
            if candidate.battlefield_layout_id == battlefield_layout.battlefield_layout_id
        ),
        None,
    )
    if source_layout is None:
        raise MissionSetupError("Battlefield layout is not present in the mission pack.")
    if source_layout.to_payload() != battlefield_layout.to_payload():
        raise MissionSetupError(
            "Battlefield layout payload does not match the mission pack source."
        )
    if battlefield_layout.deployment_map_id != deployment_map.deployment_map_id:
        raise MissionSetupError("Battlefield layout and deployment map IDs differ.")
    if battlefield_layout.terrain_layout_id != terrain_layout.terrain_layout_id:
        raise MissionSetupError("Battlefield layout and terrain layout IDs differ.")
    if battlefield_layout.battlefield_width_inches != deployment_map.battlefield_width_inches:
        raise MissionSetupError("Battlefield layout and deployment map widths differ.")
    if battlefield_layout.battlefield_depth_inches != deployment_map.battlefield_depth_inches:
        raise MissionSetupError("Battlefield layout and deployment map depths differ.")
    if battlefield_layout.battlefield_width_inches != terrain_layout.battlefield_width_inches:
        raise MissionSetupError("Battlefield layout and terrain layout widths differ.")
    if battlefield_layout.battlefield_depth_inches != terrain_layout.battlefield_depth_inches:
        raise MissionSetupError("Battlefield layout and terrain layout depths differ.")
    if _objective_marker_payloads(battlefield_layout.objective_markers) != (
        _objective_marker_payloads(deployment_map.objective_markers)
    ):
        raise MissionSetupError(
            "Battlefield layout objective markers do not match the deployment map."
        )
    if _deployment_zone_payloads(battlefield_layout.deployment_zones) != _deployment_zone_payloads(
        deployment_map.deployment_zones
    ):
        raise MissionSetupError(
            "Battlefield layout deployment zones do not match the deployment map."
        )


def _validate_battlefield_layout_matches_force_dispositions(
    *,
    mission_pack: MissionPackDefinition,
    battlefield_layout: BattlefieldLayoutDefinition,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
) -> None:
    attacker_cell = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id=attacker_force_disposition_id,
        opponent_force_disposition_id=defender_force_disposition_id,
    )
    defender_cell = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id=defender_force_disposition_id,
        opponent_force_disposition_id=attacker_force_disposition_id,
    )
    if battlefield_layout.battlefield_layout_id not in attacker_cell.battlefield_layout_ids:
        raise MissionSetupError(
            "Battlefield layout is not legal for the attacker Force Disposition matchup."
        )
    if battlefield_layout.battlefield_layout_id not in defender_cell.battlefield_layout_ids:
        raise MissionSetupError(
            "Battlefield layout is not legal for the defender Force Disposition matchup."
        )


def _mission_pool_entry_matches_components(
    *,
    entry: MissionPoolEntry,
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
    deployment_map: DeploymentMapDefinition,
    terrain_layout: TerrainLayoutTemplate,
) -> bool:
    dispositions_match = (
        entry.player_force_disposition_id == attacker_force_disposition_id
        and entry.opponent_force_disposition_id == defender_force_disposition_id
    ) or (
        entry.player_force_disposition_id == defender_force_disposition_id
        and entry.opponent_force_disposition_id == attacker_force_disposition_id
    )
    return (
        dispositions_match
        and entry.deployment_map_id == deployment_map.deployment_map_id
        and terrain_layout.terrain_layout_id in entry.terrain_layout_ids
    )


def _validate_player_primary_mission_assignments(
    values: object,
    *,
    player_ids: tuple[str, str],
) -> tuple[PlayerPrimaryMissionAssignment, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup primary_mission_assignments must be a tuple.")
    assignments: list[PlayerPrimaryMissionAssignment] = []
    seen_player_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlayerPrimaryMissionAssignment:
            raise MissionSetupError(
                "MissionSetup primary_mission_assignments must contain "
                "PlayerPrimaryMissionAssignment values."
            )
        if value.player_id in seen_player_ids:
            raise MissionSetupError(
                "MissionSetup primary_mission_assignments must be unique by player."
            )
        seen_player_ids.add(value.player_id)
        assignments.append(value)
    if seen_player_ids != set(player_ids):
        raise MissionSetupError(
            "MissionSetup primary_mission_assignments must match attacker and defender."
        )
    return tuple(sorted(assignments, key=lambda assignment: assignment.player_id))


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


def _deployment_zones_for_players(
    zones: tuple[DeploymentZone, ...],
    *,
    attacker_player_id: str,
    defender_player_id: str,
) -> tuple[DeploymentZone, ...]:
    attacker = _validate_identifier("attacker_player_id", attacker_player_id)
    defender = _validate_identifier("defender_player_id", defender_player_id)
    if attacker == defender:
        raise MissionSetupError("Attacker and defender player IDs must differ.")
    assigned_zones: list[DeploymentZone] = []
    for zone in zones:
        if zone.player_id == "attacker":
            assigned_zones.append(zone.with_player_id(attacker))
        elif zone.player_id == "defender":
            assigned_zones.append(zone.with_player_id(defender))
        else:
            assigned_zones.append(zone)
    return tuple(sorted(assigned_zones, key=lambda item: item.deployment_zone_id))


def _objective_marker_payloads(
    markers: tuple[ObjectiveMarkerDefinition, ...],
) -> tuple[ObjectiveMarkerDefinitionPayload, ...]:
    return tuple(
        marker.to_payload() for marker in sorted(markers, key=lambda item: item.objective_marker_id)
    )


def _deployment_zone_payloads(
    zones: tuple[DeploymentZone, ...],
) -> tuple[DeploymentZonePayload, ...]:
    return tuple(
        zone.to_payload() for zone in sorted(zones, key=lambda item: item.deployment_zone_id)
    )


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


def _validate_battlefield_regions(values: object) -> tuple[BattlefieldRegion, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup battlefield_regions must be a tuple.")
    regions: list[BattlefieldRegion] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not BattlefieldRegion:
            raise MissionSetupError(
                "MissionSetup battlefield_regions must contain BattlefieldRegion values."
            )
        if value.region_id in seen:
            raise MissionSetupError("MissionSetup battlefield_regions must not contain duplicates.")
        seen.add(value.region_id)
        regions.append(value)
    return tuple(sorted(regions, key=lambda region: region.region_id))


def _validate_terrain_areas(values: object) -> tuple[PlacedTerrainArea, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup terrain_areas must be a tuple.")
    terrain_areas: list[PlacedTerrainArea] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlacedTerrainArea:
            raise MissionSetupError(
                "MissionSetup terrain_areas must contain PlacedTerrainArea values."
            )
        if value.terrain_area_id in seen:
            raise MissionSetupError("MissionSetup terrain_areas must not contain duplicates.")
        seen.add(value.terrain_area_id)
        terrain_areas.append(value)
    try:
        return validate_placed_terrain_area_logical_groups(
            "MissionSetup terrain_areas",
            tuple(terrain_areas),
        )
    except TerrainAreaError as exc:
        raise MissionSetupError(str(exc)) from exc


def _validate_terrain_area_footprint_templates(
    values: object,
) -> tuple[TerrainAreaFootprintTemplate, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("terrain_area_footprint_templates must be a tuple.")
    templates: list[TerrainAreaFootprintTemplate] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainAreaFootprintTemplate:
            raise MissionSetupError(
                "terrain_area_footprint_templates must contain TerrainAreaFootprintTemplate values."
            )
        if value.footprint_template_id in seen:
            raise MissionSetupError("terrain_area_footprint_templates must not contain duplicates.")
        seen.add(value.footprint_template_id)
        templates.append(value)
    return tuple(sorted(templates, key=lambda template: template.footprint_template_id))


def _validate_terrain_feature_presets(values: object) -> tuple[TerrainFeaturePreset, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("terrain_feature_presets must be a tuple.")
    presets: list[TerrainFeaturePreset] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeaturePreset:
            raise MissionSetupError(
                "terrain_feature_presets must contain TerrainFeaturePreset values."
            )
        if value.terrain_feature_preset_id in seen:
            raise MissionSetupError("terrain_feature_presets must not contain duplicates.")
        seen.add(value.terrain_feature_preset_id)
        presets.append(value)
    return tuple(sorted(presets, key=lambda preset: preset.terrain_feature_preset_id))


def _validate_terrain_feature_area_placements(
    values: object,
) -> tuple[TerrainFeatureAreaPlacement, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("terrain_feature_placements must be a tuple.")
    placements: list[TerrainFeatureAreaPlacement] = []
    seen_feature_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainFeatureAreaPlacement:
            raise MissionSetupError(
                "terrain_feature_placements must contain TerrainFeatureAreaPlacement values."
            )
        if value.feature_id in seen_feature_ids:
            raise MissionSetupError("terrain_feature_placements must not duplicate feature IDs.")
        seen_feature_ids.add(value.feature_id)
        placements.append(value)
    return tuple(sorted(placements, key=lambda placement: placement.feature_id))


def _validate_objective_terrain_areas(
    values: object,
) -> tuple[ObjectiveTerrainAreaDefinition, ...]:
    if type(values) is not tuple:
        raise MissionSetupError("MissionSetup objective_terrain_areas must be a tuple.")
    objective_terrain_areas: list[ObjectiveTerrainAreaDefinition] = []
    seen_objective_ids: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveTerrainAreaDefinition:
            raise MissionSetupError(
                "MissionSetup objective_terrain_areas must contain "
                "ObjectiveTerrainAreaDefinition values."
            )
        if value.objective_marker_id in seen_objective_ids:
            raise MissionSetupError(
                "MissionSetup objective_terrain_areas must not contain duplicate "
                "objective marker IDs."
            )
        seen_objective_ids.add(value.objective_marker_id)
        objective_terrain_areas.append(value)
    return tuple(
        sorted(
            objective_terrain_areas,
            key=lambda objective_terrain_area: objective_terrain_area.objective_marker_id,
        )
    )


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


def _validate_battlefield_regions_within_battlefield(
    *,
    regions: tuple[BattlefieldRegion, ...],
    width: float,
    depth: float,
) -> None:
    for region in regions:
        min_x, min_y, max_x, max_y = region.bounds()
        if min_x < 0.0 or max_x > width:
            raise MissionSetupError("MissionSetup battlefield region x is outside the battlefield.")
        if min_y < 0.0 or max_y > depth:
            raise MissionSetupError("MissionSetup battlefield region y is outside the battlefield.")


def _validate_terrain_areas_within_battlefield(
    *,
    terrain_areas: tuple[PlacedTerrainArea, ...],
    width: float,
    depth: float,
) -> None:
    for terrain_area in terrain_areas:
        if not terrain_area.is_within_battlefield(width=width, depth=depth):
            raise MissionSetupError("MissionSetup terrain area is outside the battlefield.")


_validate_identifier = IdentifierValidator(MissionSetupError)


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise MissionSetupError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise MissionSetupError(f"{field_name} must be finite.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise MissionSetupError(f"{field_name} must be greater than 0.")
    return number
