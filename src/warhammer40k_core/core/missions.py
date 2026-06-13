from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.battlefield_regions import (
    BattlefieldRegion,
    BattlefieldRegionKind,
    BattlefieldRegionPayload,
)
from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZonePayload,
    DeploymentZoneShape,
)
from warhammer40k_core.core.objectives import Objective, ObjectiveMarker
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    PlacedTerrainAreaPayload,
    TerrainAreaFootprintTemplate,
    TerrainAreaFootprintTemplatePayload,
    polygon_bounds,
    transform_polygon,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayPoint
from warhammer40k_core.core.terrain_layouts import (
    TerrainLayoutTemplate,
    TerrainLayoutTemplatePayload,
)


class MissionPackError(ValueError):
    """Raised when mission pack data violates CORE V2 invariants."""


_GEOMETRY_EPSILON = 1e-6
type _Point2D = tuple[float, float]


class SecondaryMissionAvailability(StrEnum):
    TACTICAL = "tactical"
    FIXED = "fixed"
    BOTH = "both"


class MissionSourceStatus(StrEnum):
    IMPLEMENTED = "implemented"
    UNSUPPORTED = "unsupported"
    AWAITING_SOURCE = "awaiting_source"


class ObjectiveMarkerRole(StrEnum):
    HOME = "home"
    ATTACKER_HOME = "attacker_home"
    DEFENDER_HOME = "defender_home"
    CENTRAL = "central"
    EXPANSION = "expansion"


class MissionSourcePackageDefinitionPayload(TypedDict):
    edition_id: str
    mission_pack_id: str
    source_package_id: str
    source_title: str
    source_version: str
    source_commit_or_import_hash: str
    imported_at_schema_version: str


class ChapterApprovedMissionSequencePayload(TypedDict):
    sequence_id: str
    steps: list[str]
    source_id: str


class ObjectiveMarkerDefinitionPayload(TypedDict):
    objective_marker_id: str
    name: str
    objective_role: str
    x_inches: float
    y_inches: float
    z_inches: float
    marker_diameter_mm: float
    measurement_anchor: str
    is_flat: bool
    blocks_movement: bool
    blocks_placement: bool
    source_id: str


class DeploymentMapDefinitionPayload(TypedDict):
    deployment_map_id: str
    name: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    objective_markers: list[ObjectiveMarkerDefinitionPayload]
    deployment_zones: list[DeploymentZonePayload]
    source_id: str


class BattlefieldLayoutDefinitionPayload(TypedDict):
    battlefield_layout_id: str
    name: str
    deployment_map_id: str
    terrain_layout_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    coordinate_origin: str
    coordinate_orientation: str
    attacker_edge: str
    defender_edge: str
    objective_markers: list[ObjectiveMarkerDefinitionPayload]
    deployment_zones: list[DeploymentZonePayload]
    battlefield_regions: list[BattlefieldRegionPayload]
    terrain_areas: list[PlacedTerrainAreaPayload]
    source_id: str


class PrimaryMissionDefinitionPayload(TypedDict):
    primary_mission_id: str
    name: str
    source_id: str
    max_vp_per_turn: int | None
    scoring_kind: str | None
    vp_per_controlled_objective: int | None
    scoring_rules: list[MissionScoringRuleDefinitionPayload]


class SecondaryMissionDefinitionPayload(TypedDict):
    secondary_mission_id: str
    name: str
    availability: str
    tournament_fixed_allowed: bool
    source_id: str
    scoring_rules: list[MissionScoringRuleDefinitionPayload]


class MissionScoringRuleDefinitionPayload(TypedDict):
    rule_id: str
    timing: str
    source_kind: str
    victory_points: int | None
    cap: int | None
    condition: str
    source_id: str


class MissionActionDefinitionPayload(TypedDict):
    mission_action_id: str
    mission_id: str
    mission_kind: str
    name: str
    start_phase: str
    start_timing: str
    completion_timing: str
    eligible_unit_policy: str
    target_policy: str
    interruption_conditions: list[str]
    victory_points: int
    scoring_source_id: str
    source_id: str


class ChallengerCardDefinitionPayload(TypedDict):
    challenger_card_id: str
    name: str
    source_id: str


class MissionDeckDefinitionPayload(TypedDict):
    mission_deck_id: str
    primary_mission_ids: list[str]
    secondary_mission_ids: list[str]
    challenger_card_ids: list[str]
    deployment_map_ids: list[str]
    source_id: str


class ForceDispositionDefinitionPayload(TypedDict):
    force_disposition_id: str
    name: str
    source_id: str


class PrimaryMissionMatrixCellPayload(TypedDict):
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    primary_mission_id: str
    battlefield_layout_ids: list[str]
    source_status: str
    source_id: str


class MissionPoolEntryPayload(TypedDict):
    mission_pool_entry_id: str
    primary_mission_id: str
    deployment_map_id: str
    terrain_layout_ids: list[str]
    source_id: str


class TournamentScoringCapsPayload(TypedDict):
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
    source_id: str


class MissionPackScoringDefinitionPayload(TypedDict):
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: str
    secondary_vp_per_score: int
    mission_action_vp: int
    primary_vp_cap: int
    secondary_vp_cap: int
    total_vp_cap: int
    end_of_round_scoring_windows: list[str]
    end_of_game_scoring_windows: list[str]
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    source_id: str


class MissionPackDefinitionPayload(TypedDict):
    mission_pack_id: str
    name: str
    source_version: str
    source_id: str
    source_package: MissionSourcePackageDefinitionPayload
    sequence: ChapterApprovedMissionSequencePayload
    deployment_maps: list[DeploymentMapDefinitionPayload]
    terrain_layout_templates: list[TerrainLayoutTemplatePayload]
    terrain_area_footprint_templates: list[TerrainAreaFootprintTemplatePayload]
    battlefield_layouts: list[BattlefieldLayoutDefinitionPayload]
    mission_deck: MissionDeckDefinitionPayload
    primary_missions: list[PrimaryMissionDefinitionPayload]
    secondary_missions: list[SecondaryMissionDefinitionPayload]
    mission_actions: list[MissionActionDefinitionPayload]
    challenger_cards: list[ChallengerCardDefinitionPayload]
    force_dispositions: list[ForceDispositionDefinitionPayload]
    primary_mission_matrix_cells: list[PrimaryMissionMatrixCellPayload]
    mission_pool_entries: list[MissionPoolEntryPayload]
    scoring_caps: TournamentScoringCapsPayload
    scoring: MissionPackScoringDefinitionPayload


type PublicCardPayload = dict[str, bool | str]


@dataclass(frozen=True, slots=True)
class ChapterApprovedMissionSequence:
    sequence_id: str
    steps: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "sequence_id",
            _validate_unprefixed_identifier(
                "ChapterApprovedMissionSequence sequence_id",
                self.sequence_id,
                reserved_prefix="mission-sequence:",
            ),
        )
        object.__setattr__(
            self,
            "steps",
            _validate_identifier_tuple(
                "ChapterApprovedMissionSequence steps",
                self.steps,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ChapterApprovedMissionSequence source_id", self.source_id),
        )

    def to_payload(self) -> ChapterApprovedMissionSequencePayload:
        return {
            "sequence_id": self.sequence_id,
            "steps": list(self.steps),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ChapterApprovedMissionSequencePayload) -> Self:
        return cls(
            sequence_id=payload["sequence_id"],
            steps=tuple(payload["steps"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ObjectiveMarkerDefinition:
    objective_marker_id: str
    name: str
    objective_role: ObjectiveMarkerRole
    x_inches: float
    y_inches: float
    z_inches: float = 0.0
    marker_diameter_mm: float = 40.0
    measurement_anchor: str = "center"
    is_flat: bool = True
    blocks_movement: bool = False
    blocks_placement: bool = False
    source_id: str = "chapter_approved_2026_27"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "objective_marker_id",
            _validate_unprefixed_identifier(
                "ObjectiveMarkerDefinition objective_marker_id",
                self.objective_marker_id,
                reserved_prefix="objective:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("ObjectiveMarkerDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "objective_role",
            objective_marker_role_from_token(self.objective_role),
        )
        object.__setattr__(
            self,
            "x_inches",
            _validate_finite_number("ObjectiveMarkerDefinition x_inches", self.x_inches),
        )
        object.__setattr__(
            self,
            "y_inches",
            _validate_finite_number("ObjectiveMarkerDefinition y_inches", self.y_inches),
        )
        object.__setattr__(
            self,
            "z_inches",
            _validate_finite_number("ObjectiveMarkerDefinition z_inches", self.z_inches),
        )
        object.__setattr__(
            self,
            "marker_diameter_mm",
            _validate_positive_number(
                "ObjectiveMarkerDefinition marker_diameter_mm",
                self.marker_diameter_mm,
            ),
        )
        object.__setattr__(
            self,
            "measurement_anchor",
            _validate_required_token(
                "ObjectiveMarkerDefinition measurement_anchor",
                self.measurement_anchor,
                expected_token="center",
            ),
        )
        _validate_bool("ObjectiveMarkerDefinition is_flat", self.is_flat)
        _validate_bool("ObjectiveMarkerDefinition blocks_movement", self.blocks_movement)
        _validate_bool("ObjectiveMarkerDefinition blocks_placement", self.blocks_placement)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ObjectiveMarkerDefinition source_id", self.source_id),
        )
        if self.marker_diameter_mm != 40.0:
            raise MissionPackError("Chapter Approved objective markers must be 40mm.")
        if self.source_id.startswith("chapter_approved_2026_27") and (
            not self.is_flat or self.blocks_movement or self.blocks_placement
        ):
            raise MissionPackError("Chapter Approved objective markers must be flat/non-blocking.")

    def to_objective(self) -> Objective:
        return Objective.point(
            objective_id=self.objective_marker_id,
            name=self.name,
            x=self.x_inches,
            y=self.y_inches,
            z=self.z_inches,
        )

    def to_objective_marker(self) -> ObjectiveMarker:
        return ObjectiveMarker(
            objective_marker_id=self.objective_marker_id,
            name=self.name,
            x_inches=self.x_inches,
            y_inches=self.y_inches,
            z_inches=self.z_inches,
            marker_diameter_mm=self.marker_diameter_mm,
            measurement_anchor=self.measurement_anchor,
            is_flat=self.is_flat,
            blocks_movement=self.blocks_movement,
            blocks_placement=self.blocks_placement,
            source_id=self.source_id,
        )

    def to_payload(self) -> ObjectiveMarkerDefinitionPayload:
        return {
            "objective_marker_id": self.objective_marker_id,
            "name": self.name,
            "objective_role": self.objective_role.value,
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
            "z_inches": self.z_inches,
            "marker_diameter_mm": self.marker_diameter_mm,
            "measurement_anchor": self.measurement_anchor,
            "is_flat": self.is_flat,
            "blocks_movement": self.blocks_movement,
            "blocks_placement": self.blocks_placement,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ObjectiveMarkerDefinitionPayload) -> Self:
        if "objective_role" not in payload:
            raise MissionPackError("ObjectiveMarkerDefinition payload missing objective_role.")
        return cls(
            objective_marker_id=payload["objective_marker_id"],
            name=payload["name"],
            objective_role=objective_marker_role_from_token(payload["objective_role"]),
            x_inches=payload["x_inches"],
            y_inches=payload["y_inches"],
            z_inches=payload["z_inches"],
            marker_diameter_mm=payload["marker_diameter_mm"],
            measurement_anchor=payload["measurement_anchor"],
            is_flat=payload["is_flat"],
            blocks_movement=payload["blocks_movement"],
            blocks_placement=payload["blocks_placement"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class DeploymentMapDefinition:
    deployment_map_id: str
    name: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    objective_markers: tuple[ObjectiveMarkerDefinition, ...]
    deployment_zones: tuple[DeploymentZone, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "deployment_map_id",
            _validate_unprefixed_identifier(
                "DeploymentMapDefinition deployment_map_id",
                self.deployment_map_id,
                reserved_prefix="deployment-map:",
            ),
        )
        object.__setattr__(
            self, "name", _validate_identifier("DeploymentMapDefinition name", self.name)
        )
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "DeploymentMapDefinition battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "DeploymentMapDefinition battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        markers = _validate_objective_marker_tuple(self.objective_markers)
        zones = _validate_deployment_zone_tuple(
            "DeploymentMapDefinition deployment_zones",
            self.deployment_zones,
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
        object.__setattr__(self, "objective_markers", markers)
        object.__setattr__(self, "deployment_zones", zones)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DeploymentMapDefinition source_id", self.source_id),
        )

    def objectives(self) -> tuple[Objective, ...]:
        return tuple(marker.to_objective() for marker in self.objective_markers)

    def deployment_zones_for_players(
        self,
        *,
        attacker_player_id: str,
        defender_player_id: str,
    ) -> tuple[DeploymentZone, ...]:
        attacker = _validate_identifier("attacker_player_id", attacker_player_id)
        defender = _validate_identifier("defender_player_id", defender_player_id)
        if attacker == defender:
            raise MissionPackError("Attacker and defender player IDs must differ.")
        zones: list[DeploymentZone] = []
        for zone in self.deployment_zones:
            player_id = zone.player_id
            if player_id == "attacker":
                player_id = attacker
            elif player_id == "defender":
                player_id = defender
            zones.append(zone.with_player_id(player_id))
        return tuple(sorted(zones, key=lambda item: item.deployment_zone_id))

    def to_payload(self) -> DeploymentMapDefinitionPayload:
        return {
            "deployment_map_id": self.deployment_map_id,
            "name": self.name,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "objective_markers": [marker.to_payload() for marker in self.objective_markers],
            "deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: DeploymentMapDefinitionPayload) -> Self:
        return cls(
            deployment_map_id=payload["deployment_map_id"],
            name=payload["name"],
            battlefield_width_inches=payload["battlefield_width_inches"],
            battlefield_depth_inches=payload["battlefield_depth_inches"],
            objective_markers=tuple(
                ObjectiveMarkerDefinition.from_payload(marker)
                for marker in payload["objective_markers"]
            ),
            deployment_zones=tuple(
                DeploymentZone.from_payload(zone) for zone in payload["deployment_zones"]
            ),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class BattlefieldLayoutDefinition:
    battlefield_layout_id: str
    name: str
    deployment_map_id: str
    terrain_layout_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    coordinate_origin: str
    coordinate_orientation: str
    attacker_edge: str
    defender_edge: str
    objective_markers: tuple[ObjectiveMarkerDefinition, ...]
    deployment_zones: tuple[DeploymentZone, ...]
    battlefield_regions: tuple[BattlefieldRegion, ...]
    terrain_areas: tuple[PlacedTerrainArea, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "battlefield_layout_id",
            _validate_unprefixed_identifier(
                "BattlefieldLayoutDefinition battlefield_layout_id",
                self.battlefield_layout_id,
                reserved_prefix="battlefield-layout:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("BattlefieldLayoutDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "deployment_map_id",
            _validate_identifier(
                "BattlefieldLayoutDefinition deployment_map_id",
                self.deployment_map_id,
            ),
        )
        object.__setattr__(
            self,
            "terrain_layout_id",
            _validate_identifier(
                "BattlefieldLayoutDefinition terrain_layout_id",
                self.terrain_layout_id,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "BattlefieldLayoutDefinition battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "BattlefieldLayoutDefinition battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "coordinate_origin",
            _validate_identifier(
                "BattlefieldLayoutDefinition coordinate_origin",
                self.coordinate_origin,
            ),
        )
        object.__setattr__(
            self,
            "coordinate_orientation",
            _validate_identifier(
                "BattlefieldLayoutDefinition coordinate_orientation",
                self.coordinate_orientation,
            ),
        )
        object.__setattr__(
            self,
            "attacker_edge",
            _validate_identifier("BattlefieldLayoutDefinition attacker_edge", self.attacker_edge),
        )
        object.__setattr__(
            self,
            "defender_edge",
            _validate_identifier("BattlefieldLayoutDefinition defender_edge", self.defender_edge),
        )
        markers = _validate_objective_marker_tuple(self.objective_markers)
        zones = _validate_deployment_zone_tuple(
            "BattlefieldLayoutDefinition deployment_zones",
            self.deployment_zones,
        )
        regions = _validate_battlefield_regions(self.battlefield_regions)
        terrain_areas = _validate_placed_terrain_areas(self.terrain_areas)
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
        _validate_regions_within_battlefield(
            regions=regions,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        _validate_terrain_areas_within_battlefield(
            terrain_areas=terrain_areas,
            width=self.battlefield_width_inches,
            depth=self.battlefield_depth_inches,
        )
        _validate_battlefield_layout_region_invariants(
            objective_markers=markers,
            deployment_zones=zones,
            battlefield_regions=regions,
            battlefield_width_inches=self.battlefield_width_inches,
            battlefield_depth_inches=self.battlefield_depth_inches,
        )
        object.__setattr__(self, "objective_markers", markers)
        object.__setattr__(self, "deployment_zones", zones)
        object.__setattr__(self, "battlefield_regions", regions)
        object.__setattr__(self, "terrain_areas", terrain_areas)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("BattlefieldLayoutDefinition source_id", self.source_id),
        )

    def to_payload(self) -> BattlefieldLayoutDefinitionPayload:
        return {
            "battlefield_layout_id": self.battlefield_layout_id,
            "name": self.name,
            "deployment_map_id": self.deployment_map_id,
            "terrain_layout_id": self.terrain_layout_id,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "coordinate_origin": self.coordinate_origin,
            "coordinate_orientation": self.coordinate_orientation,
            "attacker_edge": self.attacker_edge,
            "defender_edge": self.defender_edge,
            "objective_markers": [marker.to_payload() for marker in self.objective_markers],
            "deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "battlefield_regions": [region.to_payload() for region in self.battlefield_regions],
            "terrain_areas": [terrain_area.to_payload() for terrain_area in self.terrain_areas],
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise MissionPackError("Battlefield layout definition payload must be a mapping.")
        raw_payload = cast(BattlefieldLayoutDefinitionPayload, payload)
        return cls(
            battlefield_layout_id=raw_payload["battlefield_layout_id"],
            name=raw_payload["name"],
            deployment_map_id=raw_payload["deployment_map_id"],
            terrain_layout_id=raw_payload["terrain_layout_id"],
            battlefield_width_inches=raw_payload["battlefield_width_inches"],
            battlefield_depth_inches=raw_payload["battlefield_depth_inches"],
            coordinate_origin=raw_payload["coordinate_origin"],
            coordinate_orientation=raw_payload["coordinate_orientation"],
            attacker_edge=raw_payload["attacker_edge"],
            defender_edge=raw_payload["defender_edge"],
            objective_markers=tuple(
                ObjectiveMarkerDefinition.from_payload(marker)
                for marker in raw_payload["objective_markers"]
            ),
            deployment_zones=tuple(
                DeploymentZone.from_payload(zone) for zone in raw_payload["deployment_zones"]
            ),
            battlefield_regions=tuple(
                BattlefieldRegion.from_payload(region)
                for region in raw_payload["battlefield_regions"]
            ),
            terrain_areas=tuple(
                PlacedTerrainArea.from_payload(area) for area in raw_payload["terrain_areas"]
            ),
            source_id=raw_payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionSourcePackageDefinition:
    edition_id: str
    mission_pack_id: str
    source_package_id: str
    source_title: str
    source_version: str
    source_commit_or_import_hash: str
    imported_at_schema_version: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "edition_id",
            _validate_identifier("MissionSourcePackageDefinition edition_id", self.edition_id),
        )
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_identifier(
                "MissionSourcePackageDefinition mission_pack_id",
                self.mission_pack_id,
            ),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier(
                "MissionSourcePackageDefinition source_package_id",
                self.source_package_id,
            ),
        )
        object.__setattr__(
            self,
            "source_title",
            _validate_identifier(
                "MissionSourcePackageDefinition source_title",
                self.source_title,
            ),
        )
        object.__setattr__(
            self,
            "source_version",
            _validate_identifier(
                "MissionSourcePackageDefinition source_version",
                self.source_version,
            ),
        )
        object.__setattr__(
            self,
            "source_commit_or_import_hash",
            _validate_identifier(
                "MissionSourcePackageDefinition source_commit_or_import_hash",
                self.source_commit_or_import_hash,
            ),
        )
        object.__setattr__(
            self,
            "imported_at_schema_version",
            _validate_identifier(
                "MissionSourcePackageDefinition imported_at_schema_version",
                self.imported_at_schema_version,
            ),
        )

    def source_namespace_key(self) -> str:
        return f"{self.edition_id}:{self.source_package_id}:{self.mission_pack_id}"

    def to_payload(self) -> MissionSourcePackageDefinitionPayload:
        return {
            "edition_id": self.edition_id,
            "mission_pack_id": self.mission_pack_id,
            "source_package_id": self.source_package_id,
            "source_title": self.source_title,
            "source_version": self.source_version,
            "source_commit_or_import_hash": self.source_commit_or_import_hash,
            "imported_at_schema_version": self.imported_at_schema_version,
        }

    @classmethod
    def from_payload(cls, payload: MissionSourcePackageDefinitionPayload) -> Self:
        return cls(
            edition_id=payload["edition_id"],
            mission_pack_id=payload["mission_pack_id"],
            source_package_id=payload["source_package_id"],
            source_title=payload["source_title"],
            source_version=payload["source_version"],
            source_commit_or_import_hash=payload["source_commit_or_import_hash"],
            imported_at_schema_version=payload["imported_at_schema_version"],
        )


@dataclass(frozen=True, slots=True)
class MissionScoringRuleDefinition:
    rule_id: str
    timing: str
    source_kind: str
    victory_points: int | None
    cap: int | None
    condition: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "rule_id",
            _validate_identifier("MissionScoringRuleDefinition rule_id", self.rule_id),
        )
        object.__setattr__(
            self,
            "timing",
            _validate_identifier("MissionScoringRuleDefinition timing", self.timing),
        )
        object.__setattr__(
            self,
            "source_kind",
            _validate_identifier("MissionScoringRuleDefinition source_kind", self.source_kind),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_optional_positive_int(
                "MissionScoringRuleDefinition victory_points",
                self.victory_points,
            ),
        )
        object.__setattr__(
            self,
            "cap",
            _validate_optional_positive_int("MissionScoringRuleDefinition cap", self.cap),
        )
        object.__setattr__(
            self,
            "condition",
            _validate_identifier("MissionScoringRuleDefinition condition", self.condition),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionScoringRuleDefinition source_id", self.source_id),
        )

    def to_payload(self) -> MissionScoringRuleDefinitionPayload:
        return {
            "rule_id": self.rule_id,
            "timing": self.timing,
            "source_kind": self.source_kind,
            "victory_points": self.victory_points,
            "cap": self.cap,
            "condition": self.condition,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionScoringRuleDefinitionPayload) -> Self:
        return cls(
            rule_id=payload["rule_id"],
            timing=payload["timing"],
            source_kind=payload["source_kind"],
            victory_points=payload["victory_points"],
            cap=payload["cap"],
            condition=payload["condition"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionDefinition:
    primary_mission_id: str
    name: str
    source_id: str
    max_vp_per_turn: int | None = None
    scoring_kind: str | None = None
    vp_per_controlled_objective: int | None = None
    scoring_rules: tuple[MissionScoringRuleDefinition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_unprefixed_identifier(
                "PrimaryMissionDefinition primary_mission_id",
                self.primary_mission_id,
                reserved_prefix="primary-mission:",
            ),
        )
        object.__setattr__(
            self, "name", _validate_identifier("PrimaryMissionDefinition name", self.name)
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryMissionDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "max_vp_per_turn",
            _validate_optional_positive_int(
                "PrimaryMissionDefinition max_vp_per_turn",
                self.max_vp_per_turn,
            ),
        )
        object.__setattr__(
            self,
            "scoring_kind",
            _validate_optional_identifier(
                "PrimaryMissionDefinition scoring_kind",
                self.scoring_kind,
            ),
        )
        object.__setattr__(
            self,
            "vp_per_controlled_objective",
            _validate_optional_positive_int(
                "PrimaryMissionDefinition vp_per_controlled_objective",
                self.vp_per_controlled_objective,
            ),
        )
        if self.scoring_kind is None and self.vp_per_controlled_objective is not None:
            raise MissionPackError("PrimaryMissionDefinition scoring kind is required for VP data.")
        if self.scoring_kind == "control_objectives" and self.vp_per_controlled_objective is None:
            raise MissionPackError(
                "PrimaryMissionDefinition control-objective scoring requires VP data."
            )
        object.__setattr__(
            self,
            "scoring_rules",
            _validate_scoring_rule_tuple(
                "PrimaryMissionDefinition scoring_rules",
                self.scoring_rules,
            ),
        )

    def to_payload(self) -> PrimaryMissionDefinitionPayload:
        return {
            "primary_mission_id": self.primary_mission_id,
            "name": self.name,
            "source_id": self.source_id,
            "max_vp_per_turn": self.max_vp_per_turn,
            "scoring_kind": self.scoring_kind,
            "vp_per_controlled_objective": self.vp_per_controlled_objective,
            "scoring_rules": [rule.to_payload() for rule in self.scoring_rules],
        }

    @classmethod
    def from_payload(cls, payload: PrimaryMissionDefinitionPayload) -> Self:
        return cls(
            primary_mission_id=payload["primary_mission_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            max_vp_per_turn=payload["max_vp_per_turn"],
            scoring_kind=payload["scoring_kind"],
            vp_per_controlled_objective=payload["vp_per_controlled_objective"],
            scoring_rules=tuple(
                MissionScoringRuleDefinition.from_payload(rule) for rule in payload["scoring_rules"]
            ),
        )


@dataclass(frozen=True, slots=True)
class SecondaryMissionDefinition:
    secondary_mission_id: str
    name: str
    availability: SecondaryMissionAvailability
    tournament_fixed_allowed: bool
    source_id: str
    scoring_rules: tuple[MissionScoringRuleDefinition, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "secondary_mission_id",
            _validate_unprefixed_identifier(
                "SecondaryMissionDefinition secondary_mission_id",
                self.secondary_mission_id,
                reserved_prefix="secondary-mission:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("SecondaryMissionDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "availability",
            secondary_mission_availability_from_token(self.availability),
        )
        _validate_bool(
            "SecondaryMissionDefinition tournament_fixed_allowed",
            self.tournament_fixed_allowed,
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("SecondaryMissionDefinition source_id", self.source_id),
        )
        object.__setattr__(
            self,
            "scoring_rules",
            _validate_scoring_rule_tuple(
                "SecondaryMissionDefinition scoring_rules",
                self.scoring_rules,
            ),
        )

    def to_public_payload(
        self,
        *,
        owner_player_id: str,
        viewer_player_id: str,
        revealed: bool,
    ) -> PublicCardPayload:
        owner = _validate_identifier("owner_player_id", owner_player_id)
        viewer = _validate_identifier("viewer_player_id", viewer_player_id)
        if owner != viewer and not _validate_bool("revealed", revealed):
            return {
                "owner_player_id": owner,
                "hidden": True,
                "card_kind": "secondary",
            }
        return {
            "owner_player_id": owner,
            "hidden": False,
            "card_kind": "secondary",
            "secondary_mission_id": self.secondary_mission_id,
            "name": self.name,
            "availability": self.availability.value,
        }

    def to_payload(self) -> SecondaryMissionDefinitionPayload:
        return {
            "secondary_mission_id": self.secondary_mission_id,
            "name": self.name,
            "availability": self.availability.value,
            "tournament_fixed_allowed": self.tournament_fixed_allowed,
            "source_id": self.source_id,
            "scoring_rules": [rule.to_payload() for rule in self.scoring_rules],
        }

    @classmethod
    def from_payload(cls, payload: SecondaryMissionDefinitionPayload) -> Self:
        return cls(
            secondary_mission_id=payload["secondary_mission_id"],
            name=payload["name"],
            availability=secondary_mission_availability_from_token(payload["availability"]),
            tournament_fixed_allowed=payload["tournament_fixed_allowed"],
            source_id=payload["source_id"],
            scoring_rules=tuple(
                MissionScoringRuleDefinition.from_payload(rule) for rule in payload["scoring_rules"]
            ),
        )


@dataclass(frozen=True, slots=True)
class MissionActionDefinition:
    mission_action_id: str
    mission_id: str
    mission_kind: str
    name: str
    start_phase: str
    start_timing: str
    completion_timing: str
    eligible_unit_policy: str
    target_policy: str
    interruption_conditions: tuple[str, ...]
    victory_points: int
    scoring_source_id: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_action_id",
            _validate_unprefixed_identifier(
                "MissionActionDefinition mission_action_id",
                self.mission_action_id,
                reserved_prefix="mission-action:",
            ),
        )
        object.__setattr__(
            self,
            "mission_id",
            _validate_identifier("MissionActionDefinition mission_id", self.mission_id),
        )
        object.__setattr__(
            self,
            "mission_kind",
            _validate_identifier("MissionActionDefinition mission_kind", self.mission_kind),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("MissionActionDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "start_phase",
            _validate_identifier("MissionActionDefinition start_phase", self.start_phase),
        )
        object.__setattr__(
            self,
            "start_timing",
            _validate_identifier("MissionActionDefinition start_timing", self.start_timing),
        )
        object.__setattr__(
            self,
            "completion_timing",
            _validate_identifier(
                "MissionActionDefinition completion_timing",
                self.completion_timing,
            ),
        )
        object.__setattr__(
            self,
            "eligible_unit_policy",
            _validate_identifier(
                "MissionActionDefinition eligible_unit_policy",
                self.eligible_unit_policy,
            ),
        )
        object.__setattr__(
            self,
            "target_policy",
            _validate_identifier("MissionActionDefinition target_policy", self.target_policy),
        )
        object.__setattr__(
            self,
            "interruption_conditions",
            _validate_identifier_tuple(
                "MissionActionDefinition interruption_conditions",
                self.interruption_conditions,
                min_length=0,
                sort_values=True,
            ),
        )
        object.__setattr__(
            self,
            "victory_points",
            _validate_non_negative_int(
                "MissionActionDefinition victory_points", self.victory_points
            ),
        )
        object.__setattr__(
            self,
            "scoring_source_id",
            _validate_identifier(
                "MissionActionDefinition scoring_source_id",
                self.scoring_source_id,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionActionDefinition source_id", self.source_id),
        )

    def to_payload(self) -> MissionActionDefinitionPayload:
        return {
            "mission_action_id": self.mission_action_id,
            "mission_id": self.mission_id,
            "mission_kind": self.mission_kind,
            "name": self.name,
            "start_phase": self.start_phase,
            "start_timing": self.start_timing,
            "completion_timing": self.completion_timing,
            "eligible_unit_policy": self.eligible_unit_policy,
            "target_policy": self.target_policy,
            "interruption_conditions": list(self.interruption_conditions),
            "victory_points": self.victory_points,
            "scoring_source_id": self.scoring_source_id,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionActionDefinitionPayload) -> Self:
        return cls(
            mission_action_id=payload["mission_action_id"],
            mission_id=payload["mission_id"],
            mission_kind=payload["mission_kind"],
            name=payload["name"],
            start_phase=payload["start_phase"],
            start_timing=payload["start_timing"],
            completion_timing=payload["completion_timing"],
            eligible_unit_policy=payload["eligible_unit_policy"],
            target_policy=payload["target_policy"],
            interruption_conditions=tuple(payload["interruption_conditions"]),
            victory_points=payload["victory_points"],
            scoring_source_id=payload["scoring_source_id"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ChallengerCardDefinition:
    challenger_card_id: str
    name: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "challenger_card_id",
            _validate_unprefixed_identifier(
                "ChallengerCardDefinition challenger_card_id",
                self.challenger_card_id,
                reserved_prefix="challenger-card:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("ChallengerCardDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ChallengerCardDefinition source_id", self.source_id),
        )

    def to_public_payload(
        self,
        *,
        owner_player_id: str,
        viewer_player_id: str,
        revealed: bool,
    ) -> PublicCardPayload:
        owner = _validate_identifier("owner_player_id", owner_player_id)
        viewer = _validate_identifier("viewer_player_id", viewer_player_id)
        if owner != viewer and not _validate_bool("revealed", revealed):
            return {
                "owner_player_id": owner,
                "hidden": True,
                "card_kind": "challenger",
            }
        return {
            "owner_player_id": owner,
            "hidden": False,
            "card_kind": "challenger",
            "challenger_card_id": self.challenger_card_id,
            "name": self.name,
        }

    def to_payload(self) -> ChallengerCardDefinitionPayload:
        return {
            "challenger_card_id": self.challenger_card_id,
            "name": self.name,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ChallengerCardDefinitionPayload) -> Self:
        return cls(
            challenger_card_id=payload["challenger_card_id"],
            name=payload["name"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionDeckDefinition:
    mission_deck_id: str
    primary_mission_ids: tuple[str, ...]
    secondary_mission_ids: tuple[str, ...]
    challenger_card_ids: tuple[str, ...]
    deployment_map_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_deck_id",
            _validate_unprefixed_identifier(
                "MissionDeckDefinition mission_deck_id",
                self.mission_deck_id,
                reserved_prefix="mission-deck:",
            ),
        )
        object.__setattr__(
            self,
            "primary_mission_ids",
            _validate_identifier_tuple(
                "MissionDeckDefinition primary_mission_ids",
                self.primary_mission_ids,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "secondary_mission_ids",
            _validate_identifier_tuple(
                "MissionDeckDefinition secondary_mission_ids",
                self.secondary_mission_ids,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "challenger_card_ids",
            _validate_identifier_tuple(
                "MissionDeckDefinition challenger_card_ids",
                self.challenger_card_ids,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "deployment_map_ids",
            _validate_identifier_tuple(
                "MissionDeckDefinition deployment_map_ids",
                self.deployment_map_ids,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionDeckDefinition source_id", self.source_id),
        )

    def to_payload(self) -> MissionDeckDefinitionPayload:
        return {
            "mission_deck_id": self.mission_deck_id,
            "primary_mission_ids": list(self.primary_mission_ids),
            "secondary_mission_ids": list(self.secondary_mission_ids),
            "challenger_card_ids": list(self.challenger_card_ids),
            "deployment_map_ids": list(self.deployment_map_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionDeckDefinitionPayload) -> Self:
        return cls(
            mission_deck_id=payload["mission_deck_id"],
            primary_mission_ids=tuple(payload["primary_mission_ids"]),
            secondary_mission_ids=tuple(payload["secondary_mission_ids"]),
            challenger_card_ids=tuple(payload["challenger_card_ids"]),
            deployment_map_ids=tuple(payload["deployment_map_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class ForceDispositionDefinition:
    force_disposition_id: str
    name: str
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_unprefixed_identifier(
                "ForceDispositionDefinition force_disposition_id",
                self.force_disposition_id,
                reserved_prefix="force-disposition:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("ForceDispositionDefinition name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("ForceDispositionDefinition source_id", self.source_id),
        )

    def to_payload(self) -> ForceDispositionDefinitionPayload:
        return {
            "force_disposition_id": self.force_disposition_id,
            "name": self.name,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: ForceDispositionDefinitionPayload) -> Self:
        return cls(
            force_disposition_id=payload["force_disposition_id"],
            name=payload["name"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class PrimaryMissionMatrixCell:
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    primary_mission_id: str
    battlefield_layout_ids: tuple[str, ...]
    source_status: MissionSourceStatus
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "player_force_disposition_id",
            _validate_identifier(
                "PrimaryMissionMatrixCell player_force_disposition_id",
                self.player_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "opponent_force_disposition_id",
            _validate_identifier(
                "PrimaryMissionMatrixCell opponent_force_disposition_id",
                self.opponent_force_disposition_id,
            ),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier(
                "PrimaryMissionMatrixCell primary_mission_id", self.primary_mission_id
            ),
        )
        object.__setattr__(
            self,
            "battlefield_layout_ids",
            _validate_identifier_tuple(
                "PrimaryMissionMatrixCell battlefield_layout_ids",
                self.battlefield_layout_ids,
                min_length=3,
                sort_values=False,
            ),
        )
        if len(self.battlefield_layout_ids) != 3:
            raise MissionPackError("PrimaryMissionMatrixCell requires exactly three layouts.")
        object.__setattr__(
            self,
            "source_status",
            mission_source_status_from_token(self.source_status),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("PrimaryMissionMatrixCell source_id", self.source_id),
        )

    def to_payload(self) -> PrimaryMissionMatrixCellPayload:
        return {
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "primary_mission_id": self.primary_mission_id,
            "battlefield_layout_ids": list(self.battlefield_layout_ids),
            "source_status": self.source_status.value,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: PrimaryMissionMatrixCellPayload) -> Self:
        return cls(
            player_force_disposition_id=payload["player_force_disposition_id"],
            opponent_force_disposition_id=payload["opponent_force_disposition_id"],
            primary_mission_id=payload["primary_mission_id"],
            battlefield_layout_ids=tuple(payload["battlefield_layout_ids"]),
            source_status=mission_source_status_from_token(payload["source_status"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionPoolEntry:
    mission_pool_entry_id: str
    primary_mission_id: str
    deployment_map_id: str
    terrain_layout_ids: tuple[str, ...]
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_pool_entry_id",
            _validate_unprefixed_identifier(
                "MissionPoolEntry mission_pool_entry_id",
                self.mission_pool_entry_id,
                reserved_prefix="mission-pool-entry:",
            ),
        )
        object.__setattr__(
            self,
            "primary_mission_id",
            _validate_identifier("MissionPoolEntry primary_mission_id", self.primary_mission_id),
        )
        object.__setattr__(
            self,
            "deployment_map_id",
            _validate_identifier("MissionPoolEntry deployment_map_id", self.deployment_map_id),
        )
        object.__setattr__(
            self,
            "terrain_layout_ids",
            _validate_identifier_tuple(
                "MissionPoolEntry terrain_layout_ids",
                self.terrain_layout_ids,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionPoolEntry source_id", self.source_id),
        )

    def to_payload(self) -> MissionPoolEntryPayload:
        return {
            "mission_pool_entry_id": self.mission_pool_entry_id,
            "primary_mission_id": self.primary_mission_id,
            "deployment_map_id": self.deployment_map_id,
            "terrain_layout_ids": list(self.terrain_layout_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionPoolEntryPayload) -> Self:
        return cls(
            mission_pool_entry_id=payload["mission_pool_entry_id"],
            primary_mission_id=payload["primary_mission_id"],
            deployment_map_id=payload["deployment_map_id"],
            terrain_layout_ids=tuple(payload["terrain_layout_ids"]),
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class TournamentScoringCaps:
    primary_vp_cap: int
    secondary_vp_cap: int
    battle_ready_vp: int
    total_vp_cap: int
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "primary_vp_cap",
            _validate_positive_int("TournamentScoringCaps primary_vp_cap", self.primary_vp_cap),
        )
        object.__setattr__(
            self,
            "secondary_vp_cap",
            _validate_positive_int(
                "TournamentScoringCaps secondary_vp_cap",
                self.secondary_vp_cap,
            ),
        )
        object.__setattr__(
            self,
            "battle_ready_vp",
            _validate_non_negative_int(
                "TournamentScoringCaps battle_ready_vp",
                self.battle_ready_vp,
            ),
        )
        object.__setattr__(
            self,
            "total_vp_cap",
            _validate_positive_int("TournamentScoringCaps total_vp_cap", self.total_vp_cap),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("TournamentScoringCaps source_id", self.source_id),
        )
        if self.primary_vp_cap + self.secondary_vp_cap + self.battle_ready_vp > self.total_vp_cap:
            raise MissionPackError("Tournament scoring caps exceed total VP cap.")

    def to_payload(self) -> TournamentScoringCapsPayload:
        return {
            "primary_vp_cap": self.primary_vp_cap,
            "secondary_vp_cap": self.secondary_vp_cap,
            "battle_ready_vp": self.battle_ready_vp,
            "total_vp_cap": self.total_vp_cap,
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: TournamentScoringCapsPayload) -> Self:
        return cls(
            primary_vp_cap=payload["primary_vp_cap"],
            secondary_vp_cap=payload["secondary_vp_cap"],
            battle_ready_vp=payload["battle_ready_vp"],
            total_vp_cap=payload["total_vp_cap"],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionPackScoringDefinition:
    game_length_battle_rounds: int
    primary_scoring_phase: str
    primary_scoring_timing: str
    secondary_vp_per_score: int
    mission_action_vp: int
    primary_vp_cap: int
    secondary_vp_cap: int
    total_vp_cap: int
    end_of_round_scoring_windows: tuple[str, ...]
    end_of_game_scoring_windows: tuple[str, ...]
    reserve_destruction_timing: str
    reserve_destruction_battle_round: int | None
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool
    source_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "game_length_battle_rounds",
            _validate_positive_int(
                "MissionPackScoringDefinition game_length_battle_rounds",
                self.game_length_battle_rounds,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_phase",
            _validate_identifier(
                "MissionPackScoringDefinition primary_scoring_phase",
                self.primary_scoring_phase,
            ),
        )
        object.__setattr__(
            self,
            "primary_scoring_timing",
            _validate_identifier(
                "MissionPackScoringDefinition primary_scoring_timing",
                self.primary_scoring_timing,
            ),
        )
        object.__setattr__(
            self,
            "secondary_vp_per_score",
            _validate_positive_int(
                "MissionPackScoringDefinition secondary_vp_per_score",
                self.secondary_vp_per_score,
            ),
        )
        object.__setattr__(
            self,
            "mission_action_vp",
            _validate_positive_int(
                "MissionPackScoringDefinition mission_action_vp",
                self.mission_action_vp,
            ),
        )
        object.__setattr__(
            self,
            "primary_vp_cap",
            _validate_positive_int(
                "MissionPackScoringDefinition primary_vp_cap",
                self.primary_vp_cap,
            ),
        )
        object.__setattr__(
            self,
            "secondary_vp_cap",
            _validate_positive_int(
                "MissionPackScoringDefinition secondary_vp_cap",
                self.secondary_vp_cap,
            ),
        )
        object.__setattr__(
            self,
            "total_vp_cap",
            _validate_positive_int(
                "MissionPackScoringDefinition total_vp_cap",
                self.total_vp_cap,
            ),
        )
        object.__setattr__(
            self,
            "end_of_round_scoring_windows",
            _validate_identifier_tuple(
                "MissionPackScoringDefinition end_of_round_scoring_windows",
                self.end_of_round_scoring_windows,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "end_of_game_scoring_windows",
            _validate_identifier_tuple(
                "MissionPackScoringDefinition end_of_game_scoring_windows",
                self.end_of_game_scoring_windows,
                min_length=1,
                sort_values=False,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_timing",
            _validate_identifier(
                "MissionPackScoringDefinition reserve_destruction_timing",
                self.reserve_destruction_timing,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_battle_round",
            _validate_optional_positive_int(
                "MissionPackScoringDefinition reserve_destruction_battle_round",
                self.reserve_destruction_battle_round,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_excludes_during_battle_strategic_reserves",
            _validate_bool(
                "MissionPackScoringDefinition "
                "reserve_destruction_excludes_during_battle_strategic_reserves",
                self.reserve_destruction_excludes_during_battle_strategic_reserves,
            ),
        )
        object.__setattr__(
            self,
            "reserve_destruction_only_declare_battle_formations",
            _validate_bool(
                "MissionPackScoringDefinition reserve_destruction_only_declare_battle_formations",
                self.reserve_destruction_only_declare_battle_formations,
            ),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionPackScoringDefinition source_id", self.source_id),
        )

    def to_payload(self) -> MissionPackScoringDefinitionPayload:
        return {
            "game_length_battle_rounds": self.game_length_battle_rounds,
            "primary_scoring_phase": self.primary_scoring_phase,
            "primary_scoring_timing": self.primary_scoring_timing,
            "secondary_vp_per_score": self.secondary_vp_per_score,
            "mission_action_vp": self.mission_action_vp,
            "primary_vp_cap": self.primary_vp_cap,
            "secondary_vp_cap": self.secondary_vp_cap,
            "total_vp_cap": self.total_vp_cap,
            "end_of_round_scoring_windows": list(self.end_of_round_scoring_windows),
            "end_of_game_scoring_windows": list(self.end_of_game_scoring_windows),
            "reserve_destruction_timing": self.reserve_destruction_timing,
            "reserve_destruction_battle_round": self.reserve_destruction_battle_round,
            "reserve_destruction_excludes_during_battle_strategic_reserves": (
                self.reserve_destruction_excludes_during_battle_strategic_reserves
            ),
            "reserve_destruction_only_declare_battle_formations": (
                self.reserve_destruction_only_declare_battle_formations
            ),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: MissionPackScoringDefinitionPayload) -> Self:
        return cls(
            game_length_battle_rounds=payload["game_length_battle_rounds"],
            primary_scoring_phase=payload["primary_scoring_phase"],
            primary_scoring_timing=payload["primary_scoring_timing"],
            secondary_vp_per_score=payload["secondary_vp_per_score"],
            mission_action_vp=payload["mission_action_vp"],
            primary_vp_cap=payload["primary_vp_cap"],
            secondary_vp_cap=payload["secondary_vp_cap"],
            total_vp_cap=payload["total_vp_cap"],
            end_of_round_scoring_windows=tuple(payload["end_of_round_scoring_windows"]),
            end_of_game_scoring_windows=tuple(payload["end_of_game_scoring_windows"]),
            reserve_destruction_timing=payload["reserve_destruction_timing"],
            reserve_destruction_battle_round=payload["reserve_destruction_battle_round"],
            reserve_destruction_excludes_during_battle_strategic_reserves=payload[
                "reserve_destruction_excludes_during_battle_strategic_reserves"
            ],
            reserve_destruction_only_declare_battle_formations=payload[
                "reserve_destruction_only_declare_battle_formations"
            ],
            source_id=payload["source_id"],
        )


@dataclass(frozen=True, slots=True)
class MissionPackDefinition:
    mission_pack_id: str
    name: str
    source_version: str
    source_id: str
    source_package: MissionSourcePackageDefinition
    sequence: ChapterApprovedMissionSequence
    deployment_maps: tuple[DeploymentMapDefinition, ...]
    terrain_layout_templates: tuple[TerrainLayoutTemplate, ...]
    terrain_area_footprint_templates: tuple[TerrainAreaFootprintTemplate, ...]
    battlefield_layouts: tuple[BattlefieldLayoutDefinition, ...]
    mission_deck: MissionDeckDefinition
    primary_missions: tuple[PrimaryMissionDefinition, ...]
    secondary_missions: tuple[SecondaryMissionDefinition, ...]
    mission_actions: tuple[MissionActionDefinition, ...]
    challenger_cards: tuple[ChallengerCardDefinition, ...]
    force_dispositions: tuple[ForceDispositionDefinition, ...]
    primary_mission_matrix_cells: tuple[PrimaryMissionMatrixCell, ...]
    mission_pool_entries: tuple[MissionPoolEntry, ...]
    scoring_caps: TournamentScoringCaps
    scoring: MissionPackScoringDefinition

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "mission_pack_id",
            _validate_unprefixed_identifier(
                "MissionPackDefinition mission_pack_id",
                self.mission_pack_id,
                reserved_prefix="mission-pack:",
            ),
        )
        object.__setattr__(
            self, "name", _validate_identifier("MissionPackDefinition name", self.name)
        )
        object.__setattr__(
            self,
            "source_version",
            _validate_identifier("MissionPackDefinition source_version", self.source_version),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("MissionPackDefinition source_id", self.source_id),
        )
        if type(self.source_package) is not MissionSourcePackageDefinition:
            raise MissionPackError("MissionPackDefinition source_package must be source package.")
        if self.source_package.mission_pack_id != self.mission_pack_id:
            raise MissionPackError("MissionPackDefinition source_package mission_pack_id drift.")
        if self.source_package.source_package_id != self.source_id:
            raise MissionPackError("MissionPackDefinition source_package source_id drift.")
        if self.source_package.source_version != self.source_version:
            raise MissionPackError("MissionPackDefinition source_package source_version drift.")
        if type(self.sequence) is not ChapterApprovedMissionSequence:
            raise MissionPackError("MissionPackDefinition sequence must be a sequence.")
        deployment_maps = _validate_deployment_maps(self.deployment_maps)
        terrain_layouts = _validate_terrain_layout_templates(self.terrain_layout_templates)
        terrain_area_footprint_templates = _validate_terrain_area_footprint_templates(
            self.terrain_area_footprint_templates
        )
        battlefield_layouts = _validate_battlefield_layouts(self.battlefield_layouts)
        if type(self.mission_deck) is not MissionDeckDefinition:
            raise MissionPackError("MissionPackDefinition mission_deck must be a deck.")
        primary_missions = _validate_primary_missions(self.primary_missions)
        secondary_missions = _validate_secondary_missions(self.secondary_missions)
        mission_actions = _validate_mission_actions(self.mission_actions)
        challenger_cards = _validate_challenger_cards(self.challenger_cards)
        force_dispositions = _validate_force_dispositions(self.force_dispositions)
        primary_mission_matrix_cells = _validate_primary_mission_matrix_cells(
            self.primary_mission_matrix_cells
        )
        mission_pool_entries = _validate_mission_pool_entries(self.mission_pool_entries)
        if type(self.scoring_caps) is not TournamentScoringCaps:
            raise MissionPackError("MissionPackDefinition scoring_caps must be scoring caps.")
        if type(self.scoring) is not MissionPackScoringDefinition:
            raise MissionPackError("MissionPackDefinition scoring must be a scoring definition.")
        _validate_deck_references(
            mission_deck=self.mission_deck,
            deployment_maps=deployment_maps,
            primary_missions=primary_missions,
            secondary_missions=secondary_missions,
            challenger_cards=challenger_cards,
        )
        _validate_primary_mission_matrix_references(
            force_dispositions=force_dispositions,
            primary_mission_matrix_cells=primary_mission_matrix_cells,
            primary_missions=primary_missions,
        )
        _validate_mission_pool_references(
            mission_pool_entries=mission_pool_entries,
            deployment_maps=deployment_maps,
            primary_missions=primary_missions,
            terrain_layouts=terrain_layouts,
        )
        _validate_battlefield_layout_references(
            battlefield_layouts=battlefield_layouts,
            deployment_maps=deployment_maps,
            terrain_layouts=terrain_layouts,
            terrain_area_footprint_templates=terrain_area_footprint_templates,
        )
        object.__setattr__(self, "deployment_maps", deployment_maps)
        object.__setattr__(self, "terrain_layout_templates", terrain_layouts)
        object.__setattr__(
            self,
            "terrain_area_footprint_templates",
            terrain_area_footprint_templates,
        )
        object.__setattr__(self, "battlefield_layouts", battlefield_layouts)
        object.__setattr__(self, "primary_missions", primary_missions)
        object.__setattr__(self, "secondary_missions", secondary_missions)
        object.__setattr__(self, "mission_actions", mission_actions)
        object.__setattr__(self, "challenger_cards", challenger_cards)
        object.__setattr__(self, "force_dispositions", force_dispositions)
        object.__setattr__(self, "primary_mission_matrix_cells", primary_mission_matrix_cells)
        object.__setattr__(self, "mission_pool_entries", mission_pool_entries)

    def deployment_map(self, deployment_map_id: str) -> DeploymentMapDefinition:
        requested_id = _validate_identifier("deployment_map_id", deployment_map_id)
        for deployment_map in self.deployment_maps:
            if deployment_map.deployment_map_id == requested_id:
                return deployment_map
        raise MissionPackError("MissionPackDefinition does not contain deployment_map_id.")

    def terrain_layout_template(self, terrain_layout_id: str) -> TerrainLayoutTemplate:
        requested_id = _validate_identifier("terrain_layout_id", terrain_layout_id)
        for template in self.terrain_layout_templates:
            if template.terrain_layout_id == requested_id:
                return template
        raise MissionPackError("MissionPackDefinition does not contain terrain_layout_id.")

    def battlefield_layout(self, battlefield_layout_id: str) -> BattlefieldLayoutDefinition:
        requested_id = _validate_identifier("battlefield_layout_id", battlefield_layout_id)
        for layout in self.battlefield_layouts:
            if layout.battlefield_layout_id == requested_id:
                return layout
        raise MissionPackError("MissionPackDefinition does not contain battlefield_layout_id.")

    def secondary_mission(self, secondary_mission_id: str) -> SecondaryMissionDefinition:
        requested_id = _validate_identifier("secondary_mission_id", secondary_mission_id)
        for mission in self.secondary_missions:
            if mission.secondary_mission_id == requested_id:
                return mission
        raise MissionPackError("MissionPackDefinition does not contain secondary_mission_id.")

    def mission_action(self, mission_action_id: str) -> MissionActionDefinition:
        requested_id = _validate_identifier("mission_action_id", mission_action_id)
        for action in self.mission_actions:
            if action.mission_action_id == requested_id:
                return action
        raise MissionPackError("MissionPackDefinition does not contain mission_action_id.")

    def challenger_card(self, challenger_card_id: str) -> ChallengerCardDefinition:
        requested_id = _validate_identifier("challenger_card_id", challenger_card_id)
        for card in self.challenger_cards:
            if card.challenger_card_id == requested_id:
                return card
        raise MissionPackError("MissionPackDefinition does not contain challenger_card_id.")

    def force_disposition(self, force_disposition_id: str) -> ForceDispositionDefinition:
        requested_id = _validate_identifier("force_disposition_id", force_disposition_id)
        for disposition in self.force_dispositions:
            if disposition.force_disposition_id == requested_id:
                return disposition
        raise MissionPackError("MissionPackDefinition does not contain force_disposition_id.")

    def primary_mission_matrix_cell(
        self,
        *,
        player_force_disposition_id: str,
        opponent_force_disposition_id: str,
    ) -> PrimaryMissionMatrixCell:
        player_disposition_id = _validate_identifier(
            "player_force_disposition_id",
            player_force_disposition_id,
        )
        opponent_disposition_id = _validate_identifier(
            "opponent_force_disposition_id",
            opponent_force_disposition_id,
        )
        for cell in self.primary_mission_matrix_cells:
            if (
                cell.player_force_disposition_id == player_disposition_id
                and cell.opponent_force_disposition_id == opponent_disposition_id
            ):
                return cell
        raise MissionPackError("MissionPackDefinition does not contain matrix cell.")

    def deterministic_mission_pool_order(self, *, seed: str) -> tuple[MissionPoolEntry, ...]:
        seed_value = _validate_identifier("seed", seed)
        return tuple(
            sorted(
                self.mission_pool_entries,
                key=lambda entry: _stable_order_key(
                    seed=seed_value, entry_id=entry.mission_pool_entry_id
                ),
            )
        )

    def select_mission_pool_entry(self, *, seed: str, index: int = 0) -> MissionPoolEntry:
        requested_index = _validate_non_negative_int("index", index)
        order = self.deterministic_mission_pool_order(seed=seed)
        if requested_index >= len(order):
            raise MissionPackError("Mission pool index is outside the deterministic pool.")
        return order[requested_index]

    def to_payload(self) -> MissionPackDefinitionPayload:
        return {
            "mission_pack_id": self.mission_pack_id,
            "name": self.name,
            "source_version": self.source_version,
            "source_id": self.source_id,
            "source_package": self.source_package.to_payload(),
            "sequence": self.sequence.to_payload(),
            "deployment_maps": [
                deployment_map.to_payload() for deployment_map in self.deployment_maps
            ],
            "terrain_layout_templates": [
                template.to_payload() for template in self.terrain_layout_templates
            ],
            "terrain_area_footprint_templates": [
                template.to_payload() for template in self.terrain_area_footprint_templates
            ],
            "battlefield_layouts": [layout.to_payload() for layout in self.battlefield_layouts],
            "mission_deck": self.mission_deck.to_payload(),
            "primary_missions": [mission.to_payload() for mission in self.primary_missions],
            "secondary_missions": [mission.to_payload() for mission in self.secondary_missions],
            "mission_actions": [action.to_payload() for action in self.mission_actions],
            "challenger_cards": [card.to_payload() for card in self.challenger_cards],
            "force_dispositions": [
                disposition.to_payload() for disposition in self.force_dispositions
            ],
            "primary_mission_matrix_cells": [
                cell.to_payload() for cell in self.primary_mission_matrix_cells
            ],
            "mission_pool_entries": [entry.to_payload() for entry in self.mission_pool_entries],
            "scoring_caps": self.scoring_caps.to_payload(),
            "scoring": self.scoring.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: MissionPackDefinitionPayload) -> Self:
        return cls(
            mission_pack_id=payload["mission_pack_id"],
            name=payload["name"],
            source_version=payload["source_version"],
            source_id=payload["source_id"],
            source_package=MissionSourcePackageDefinition.from_payload(payload["source_package"]),
            sequence=ChapterApprovedMissionSequence.from_payload(payload["sequence"]),
            deployment_maps=tuple(
                DeploymentMapDefinition.from_payload(deployment_map)
                for deployment_map in payload["deployment_maps"]
            ),
            terrain_layout_templates=tuple(
                TerrainLayoutTemplate.from_payload(template)
                for template in payload["terrain_layout_templates"]
            ),
            terrain_area_footprint_templates=tuple(
                TerrainAreaFootprintTemplate.from_payload(template)
                for template in payload["terrain_area_footprint_templates"]
            ),
            battlefield_layouts=tuple(
                BattlefieldLayoutDefinition.from_payload(layout)
                for layout in payload["battlefield_layouts"]
            ),
            mission_deck=MissionDeckDefinition.from_payload(payload["mission_deck"]),
            primary_missions=tuple(
                PrimaryMissionDefinition.from_payload(mission)
                for mission in payload["primary_missions"]
            ),
            secondary_missions=tuple(
                SecondaryMissionDefinition.from_payload(mission)
                for mission in payload["secondary_missions"]
            ),
            mission_actions=tuple(
                MissionActionDefinition.from_payload(action)
                for action in payload["mission_actions"]
            ),
            challenger_cards=tuple(
                ChallengerCardDefinition.from_payload(card) for card in payload["challenger_cards"]
            ),
            force_dispositions=tuple(
                ForceDispositionDefinition.from_payload(disposition)
                for disposition in payload["force_dispositions"]
            ),
            primary_mission_matrix_cells=tuple(
                PrimaryMissionMatrixCell.from_payload(cell)
                for cell in payload["primary_mission_matrix_cells"]
            ),
            mission_pool_entries=tuple(
                MissionPoolEntry.from_payload(entry) for entry in payload["mission_pool_entries"]
            ),
            scoring_caps=TournamentScoringCaps.from_payload(payload["scoring_caps"]),
            scoring=MissionPackScoringDefinition.from_payload(payload["scoring"]),
        )


def secondary_mission_availability_from_token(token: object) -> SecondaryMissionAvailability:
    if type(token) is SecondaryMissionAvailability:
        return token
    if type(token) is not str:
        raise MissionPackError("SecondaryMissionAvailability token must be a string.")
    try:
        return SecondaryMissionAvailability(token)
    except ValueError as exc:
        raise MissionPackError(f"Unsupported SecondaryMissionAvailability token: {token}.") from exc


def mission_source_status_from_token(token: object) -> MissionSourceStatus:
    if type(token) is MissionSourceStatus:
        return token
    if type(token) is not str:
        raise MissionPackError("MissionSourceStatus token must be a string.")
    try:
        return MissionSourceStatus(token)
    except ValueError as exc:
        raise MissionPackError(f"Unsupported MissionSourceStatus token: {token}.") from exc


def objective_marker_role_from_token(token: object) -> ObjectiveMarkerRole:
    if type(token) is ObjectiveMarkerRole:
        return token
    if type(token) is not str:
        raise MissionPackError("ObjectiveMarkerRole token must be a string.")
    if token in {"center", "centre"}:
        return ObjectiveMarkerRole.CENTRAL
    try:
        return ObjectiveMarkerRole(token)
    except ValueError as exc:
        raise MissionPackError(f"Unsupported ObjectiveMarkerRole token: {token}.") from exc


def _stable_order_key(*, seed: str, entry_id: str) -> str:
    encoded = json.dumps(
        {"seed": seed, "mission_pool_entry_id": entry_id},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _validate_objective_marker_tuple(
    values: object,
) -> tuple[ObjectiveMarkerDefinition, ...]:
    if type(values) is not tuple:
        raise MissionPackError("DeploymentMapDefinition objective_markers must be a tuple.")
    markers: list[ObjectiveMarkerDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not ObjectiveMarkerDefinition:
            raise MissionPackError(
                "objective_markers must contain ObjectiveMarkerDefinition values."
            )
        if value.objective_marker_id in seen:
            raise MissionPackError("objective_markers must not contain duplicate marker IDs.")
        seen.add(value.objective_marker_id)
        markers.append(value)
    return tuple(sorted(markers, key=lambda marker: marker.objective_marker_id))


def _validate_deployment_zone_tuple(
    field_name: str,
    values: object,
) -> tuple[DeploymentZone, ...]:
    if type(values) is not tuple:
        raise MissionPackError(f"{field_name} must be a tuple.")
    zones: list[DeploymentZone] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not DeploymentZone:
            raise MissionPackError(f"{field_name} must contain DeploymentZone values.")
        if value.deployment_zone_id in seen:
            raise MissionPackError(f"{field_name} must not contain duplicate zone IDs.")
        seen.add(value.deployment_zone_id)
        zones.append(value)
    return tuple(sorted(zones, key=lambda zone: zone.deployment_zone_id))


def _validate_battlefield_regions(values: object) -> tuple[BattlefieldRegion, ...]:
    if type(values) is not tuple:
        raise MissionPackError("BattlefieldLayoutDefinition battlefield_regions must be a tuple.")
    regions: list[BattlefieldRegion] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not BattlefieldRegion:
            raise MissionPackError(
                "BattlefieldLayoutDefinition battlefield_regions must contain "
                "BattlefieldRegion values."
            )
        if value.region_id in seen:
            raise MissionPackError(
                "BattlefieldLayoutDefinition battlefield_regions must not contain duplicates."
            )
        seen.add(value.region_id)
        regions.append(value)
    if not regions:
        raise MissionPackError("BattlefieldLayoutDefinition battlefield_regions must not be empty.")
    return tuple(sorted(regions, key=lambda region: region.region_id))


def _validate_placed_terrain_areas(values: object) -> tuple[PlacedTerrainArea, ...]:
    if type(values) is not tuple:
        raise MissionPackError("BattlefieldLayoutDefinition terrain_areas must be a tuple.")
    terrain_areas: list[PlacedTerrainArea] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PlacedTerrainArea:
            raise MissionPackError(
                "BattlefieldLayoutDefinition terrain_areas must contain PlacedTerrainArea values."
            )
        if value.terrain_area_id in seen:
            raise MissionPackError(
                "BattlefieldLayoutDefinition terrain_areas must not contain duplicates."
            )
        seen.add(value.terrain_area_id)
        terrain_areas.append(value)
    if not terrain_areas:
        raise MissionPackError("BattlefieldLayoutDefinition terrain_areas must not be empty.")
    return tuple(sorted(terrain_areas, key=lambda area: area.terrain_area_id))


def _validate_deployment_maps(
    values: object,
) -> tuple[DeploymentMapDefinition, ...]:
    if type(values) is not tuple:
        raise MissionPackError("MissionPackDefinition deployment_maps must be a tuple.")
    return _validate_unique_values(
        field_name="MissionPackDefinition deployment_maps",
        values=cast(tuple[object, ...], values),
        expected_type=DeploymentMapDefinition,
        identity=lambda item: item.deployment_map_id,
    )


def _validate_terrain_layout_templates(
    values: object,
) -> tuple[TerrainLayoutTemplate, ...]:
    if type(values) is not tuple:
        raise MissionPackError("MissionPackDefinition terrain_layout_templates must be a tuple.")
    return _validate_unique_values(
        field_name="MissionPackDefinition terrain_layout_templates",
        values=cast(tuple[object, ...], values),
        expected_type=TerrainLayoutTemplate,
        identity=lambda item: item.terrain_layout_id,
    )


def _validate_terrain_area_footprint_templates(
    values: object,
) -> tuple[TerrainAreaFootprintTemplate, ...]:
    if type(values) is not tuple:
        raise MissionPackError(
            "MissionPackDefinition terrain_area_footprint_templates must be a tuple."
        )
    entries: list[TerrainAreaFootprintTemplate] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not TerrainAreaFootprintTemplate:
            raise MissionPackError(
                "MissionPackDefinition terrain_area_footprint_templates must contain "
                "TerrainAreaFootprintTemplate values."
            )
        if value.footprint_template_id in seen:
            raise MissionPackError(
                "MissionPackDefinition terrain_area_footprint_templates must not duplicate IDs."
            )
        seen.add(value.footprint_template_id)
        entries.append(value)
    return tuple(sorted(entries, key=lambda item: item.footprint_template_id))


def _validate_battlefield_layouts(
    values: object,
) -> tuple[BattlefieldLayoutDefinition, ...]:
    if type(values) is not tuple:
        raise MissionPackError("MissionPackDefinition battlefield_layouts must be a tuple.")
    entries: list[BattlefieldLayoutDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not BattlefieldLayoutDefinition:
            raise MissionPackError(
                "MissionPackDefinition battlefield_layouts must contain "
                "BattlefieldLayoutDefinition values."
            )
        if value.battlefield_layout_id in seen:
            raise MissionPackError(
                "MissionPackDefinition battlefield_layouts must not duplicate IDs."
            )
        seen.add(value.battlefield_layout_id)
        entries.append(value)
    return tuple(sorted(entries, key=lambda item: item.battlefield_layout_id))


def _validate_primary_missions(values: object) -> tuple[PrimaryMissionDefinition, ...]:
    return _validate_unique_values(
        field_name="MissionPackDefinition primary_missions",
        values=values,
        expected_type=PrimaryMissionDefinition,
        identity=lambda item: item.primary_mission_id,
    )


def _validate_secondary_missions(values: object) -> tuple[SecondaryMissionDefinition, ...]:
    return _validate_unique_values(
        field_name="MissionPackDefinition secondary_missions",
        values=values,
        expected_type=SecondaryMissionDefinition,
        identity=lambda item: item.secondary_mission_id,
    )


def _validate_scoring_rule_tuple(
    field_name: str,
    values: object,
) -> tuple[MissionScoringRuleDefinition, ...]:
    if type(values) is not tuple:
        raise MissionPackError(f"{field_name} must be a tuple.")
    entries: list[MissionScoringRuleDefinition] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not MissionScoringRuleDefinition:
            raise MissionPackError(f"{field_name} must contain scoring rule values.")
        if value.rule_id in seen:
            raise MissionPackError(f"{field_name} must not contain duplicate rule IDs.")
        seen.add(value.rule_id)
        entries.append(value)
    return tuple(sorted(entries, key=lambda item: item.rule_id))


def _validate_mission_actions(values: object) -> tuple[MissionActionDefinition, ...]:
    return _validate_unique_values(
        field_name="MissionPackDefinition mission_actions",
        values=values,
        expected_type=MissionActionDefinition,
        identity=lambda item: item.mission_action_id,
    )


def _validate_challenger_cards(values: object) -> tuple[ChallengerCardDefinition, ...]:
    return _validate_unique_values(
        field_name="MissionPackDefinition challenger_cards",
        values=values,
        expected_type=ChallengerCardDefinition,
        identity=lambda item: item.challenger_card_id,
    )


def _validate_force_dispositions(values: object) -> tuple[ForceDispositionDefinition, ...]:
    return _validate_unique_values(
        field_name="MissionPackDefinition force_dispositions",
        values=values,
        expected_type=ForceDispositionDefinition,
        identity=lambda item: item.force_disposition_id,
    )


def _validate_primary_mission_matrix_cells(
    values: object,
) -> tuple[PrimaryMissionMatrixCell, ...]:
    if type(values) is not tuple:
        raise MissionPackError(
            "MissionPackDefinition primary_mission_matrix_cells must be a tuple."
        )
    entries: list[PrimaryMissionMatrixCell] = []
    seen: set[tuple[str, str]] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not PrimaryMissionMatrixCell:
            raise MissionPackError(
                "MissionPackDefinition primary_mission_matrix_cells must contain cells."
            )
        key = (value.player_force_disposition_id, value.opponent_force_disposition_id)
        if key in seen:
            raise MissionPackError(
                "MissionPackDefinition primary_mission_matrix_cells must not duplicate cells."
            )
        seen.add(key)
        entries.append(value)
    if not entries:
        raise MissionPackError(
            "MissionPackDefinition primary_mission_matrix_cells must not be empty."
        )
    return tuple(
        sorted(
            entries,
            key=lambda cell: (
                cell.player_force_disposition_id,
                cell.opponent_force_disposition_id,
            ),
        )
    )


def _validate_mission_pool_entries(values: object) -> tuple[MissionPoolEntry, ...]:
    return _validate_unique_values(
        field_name="MissionPackDefinition mission_pool_entries",
        values=values,
        expected_type=MissionPoolEntry,
        identity=lambda item: item.mission_pool_entry_id,
    )


def _validate_unique_values[T](
    *,
    field_name: str,
    values: object,
    expected_type: type[T],
    identity: Callable[[T], str],
) -> tuple[T, ...]:
    if type(values) is not tuple:
        raise MissionPackError(f"{field_name} must be a tuple.")
    entries: list[T] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        if type(value) is not expected_type:
            raise MissionPackError(f"{field_name} must contain {expected_type.__name__} values.")
        typed_value = value
        entry_id = identity(typed_value)
        if entry_id in seen:
            raise MissionPackError(f"{field_name} must not contain duplicate IDs.")
        seen.add(entry_id)
        entries.append(typed_value)
    if not entries:
        raise MissionPackError(f"{field_name} must not be empty.")
    return tuple(sorted(entries, key=identity))


def _validate_deck_references(
    *,
    mission_deck: MissionDeckDefinition,
    deployment_maps: tuple[DeploymentMapDefinition, ...],
    primary_missions: tuple[PrimaryMissionDefinition, ...],
    secondary_missions: tuple[SecondaryMissionDefinition, ...],
    challenger_cards: tuple[ChallengerCardDefinition, ...],
) -> None:
    _validate_known_ids(
        "MissionDeckDefinition primary_mission_ids",
        mission_deck.primary_mission_ids,
        {mission.primary_mission_id for mission in primary_missions},
    )
    _validate_known_ids(
        "MissionDeckDefinition secondary_mission_ids",
        mission_deck.secondary_mission_ids,
        {mission.secondary_mission_id for mission in secondary_missions},
    )
    _validate_known_ids(
        "MissionDeckDefinition challenger_card_ids",
        mission_deck.challenger_card_ids,
        {card.challenger_card_id for card in challenger_cards},
    )
    _validate_known_ids(
        "MissionDeckDefinition deployment_map_ids",
        mission_deck.deployment_map_ids,
        {deployment_map.deployment_map_id for deployment_map in deployment_maps},
    )


def _validate_primary_mission_matrix_references(
    *,
    force_dispositions: tuple[ForceDispositionDefinition, ...],
    primary_mission_matrix_cells: tuple[PrimaryMissionMatrixCell, ...],
    primary_missions: tuple[PrimaryMissionDefinition, ...],
) -> None:
    disposition_ids = {disposition.force_disposition_id for disposition in force_dispositions}
    primary_mission_ids = {mission.primary_mission_id for mission in primary_missions}
    expected_cells = {
        (player_disposition_id, opponent_disposition_id)
        for player_disposition_id in disposition_ids
        for opponent_disposition_id in disposition_ids
    }
    actual_cells = {
        (cell.player_force_disposition_id, cell.opponent_force_disposition_id)
        for cell in primary_mission_matrix_cells
    }
    unknown_disposition_ids = {
        disposition_id
        for cell in primary_mission_matrix_cells
        for disposition_id in (
            cell.player_force_disposition_id,
            cell.opponent_force_disposition_id,
        )
        if disposition_id not in disposition_ids
    }
    if unknown_disposition_ids:
        raise MissionPackError(
            "PrimaryMissionMatrixCell references unknown force dispositions: "
            f"{', '.join(sorted(unknown_disposition_ids))}."
        )
    missing_cells = expected_cells - actual_cells
    if missing_cells:
        missing_text = ", ".join(
            f"{player_id}/{opponent_id}" for player_id, opponent_id in sorted(missing_cells)
        )
        raise MissionPackError(f"Primary mission matrix is missing cells: {missing_text}.")
    extra_cells = actual_cells - expected_cells
    if extra_cells:
        extra_text = ", ".join(
            f"{player_id}/{opponent_id}" for player_id, opponent_id in sorted(extra_cells)
        )
        raise MissionPackError(f"Primary mission matrix has unexpected cells: {extra_text}.")
    for cell in primary_mission_matrix_cells:
        if (
            cell.source_status is MissionSourceStatus.IMPLEMENTED
            and cell.primary_mission_id not in primary_mission_ids
        ):
            raise MissionPackError("Implemented matrix cell must reference a primary mission.")


def _validate_mission_pool_references(
    *,
    mission_pool_entries: tuple[MissionPoolEntry, ...],
    deployment_maps: tuple[DeploymentMapDefinition, ...],
    primary_missions: tuple[PrimaryMissionDefinition, ...],
    terrain_layouts: tuple[TerrainLayoutTemplate, ...],
) -> None:
    deployment_map_ids = {deployment_map.deployment_map_id for deployment_map in deployment_maps}
    primary_mission_ids = {mission.primary_mission_id for mission in primary_missions}
    terrain_layout_ids = {layout.terrain_layout_id for layout in terrain_layouts}
    for entry in mission_pool_entries:
        _validate_known_ids(
            "MissionPoolEntry primary_mission_id",
            (entry.primary_mission_id,),
            primary_mission_ids,
        )
        _validate_known_ids(
            "MissionPoolEntry deployment_map_id",
            (entry.deployment_map_id,),
            deployment_map_ids,
        )
        _validate_known_ids(
            "MissionPoolEntry terrain_layout_ids",
            entry.terrain_layout_ids,
            terrain_layout_ids,
        )


def _validate_battlefield_layout_references(
    *,
    battlefield_layouts: tuple[BattlefieldLayoutDefinition, ...],
    deployment_maps: tuple[DeploymentMapDefinition, ...],
    terrain_layouts: tuple[TerrainLayoutTemplate, ...],
    terrain_area_footprint_templates: tuple[TerrainAreaFootprintTemplate, ...],
) -> None:
    deployment_maps_by_id = {
        deployment_map.deployment_map_id: deployment_map for deployment_map in deployment_maps
    }
    terrain_layouts_by_id = {layout.terrain_layout_id: layout for layout in terrain_layouts}
    terrain_area_templates_by_id = {
        template.footprint_template_id: template for template in terrain_area_footprint_templates
    }
    for layout in battlefield_layouts:
        deployment_map = deployment_maps_by_id.get(layout.deployment_map_id)
        if deployment_map is None:
            raise MissionPackError("BattlefieldLayoutDefinition references unknown deployment map.")
        terrain_layout = terrain_layouts_by_id.get(layout.terrain_layout_id)
        if terrain_layout is None:
            raise MissionPackError("BattlefieldLayoutDefinition references unknown terrain layout.")
        if deployment_map.battlefield_width_inches != layout.battlefield_width_inches:
            raise MissionPackError("Battlefield layout and deployment map widths differ.")
        if deployment_map.battlefield_depth_inches != layout.battlefield_depth_inches:
            raise MissionPackError("Battlefield layout and deployment map depths differ.")
        _validate_battlefield_layout_matches_deployment_map_geometry(
            layout=layout,
            deployment_map=deployment_map,
        )
        if terrain_layout.battlefield_width_inches != layout.battlefield_width_inches:
            raise MissionPackError("Battlefield layout and terrain layout widths differ.")
        if terrain_layout.battlefield_depth_inches != layout.battlefield_depth_inches:
            raise MissionPackError("Battlefield layout and terrain layout depths differ.")
        _validate_known_ids(
            "BattlefieldLayoutDefinition terrain_area footprint_template_id",
            tuple(area.footprint_template_id for area in layout.terrain_areas),
            set(terrain_area_templates_by_id),
        )
        _validate_placed_terrain_areas_match_templates(
            terrain_areas=layout.terrain_areas,
            templates_by_id=terrain_area_templates_by_id,
        )


def _validate_placed_terrain_areas_match_templates(
    *,
    terrain_areas: tuple[PlacedTerrainArea, ...],
    templates_by_id: dict[str, TerrainAreaFootprintTemplate],
) -> None:
    for terrain_area in terrain_areas:
        template = templates_by_id[terrain_area.footprint_template_id]
        expected_polygon = transform_polygon(
            template.polygon_vertices_inches,
            center_x_inches=terrain_area.center_x_inches,
            center_y_inches=terrain_area.center_y_inches,
            rotation_degrees=terrain_area.rotation_degrees,
        )
        if not _terrain_area_polygons_close(terrain_area.footprint_polygon, expected_polygon):
            raise MissionPackError(
                "Placed terrain area footprint polygon must match its template transform."
            )
        if not _geometry_bounds_close(terrain_area.bounds(), polygon_bounds(expected_polygon)):
            raise MissionPackError(
                "Placed terrain area bounds must match its transformed template bounds."
            )


def _validate_battlefield_layout_region_invariants(
    *,
    objective_markers: tuple[ObjectiveMarkerDefinition, ...],
    deployment_zones: tuple[DeploymentZone, ...],
    battlefield_regions: tuple[BattlefieldRegion, ...],
    battlefield_width_inches: float,
    battlefield_depth_inches: float,
) -> None:
    zones_by_role = _deployment_zones_by_role(deployment_zones)
    attacker_deployment_region = _single_battlefield_region(
        battlefield_regions,
        region_kind=BattlefieldRegionKind.DEPLOYMENT_ZONE,
        owner_role="attacker",
    )
    defender_deployment_region = _single_battlefield_region(
        battlefield_regions,
        region_kind=BattlefieldRegionKind.DEPLOYMENT_ZONE,
        owner_role="defender",
    )
    attacker_territory = _single_battlefield_region(
        battlefield_regions,
        region_kind=BattlefieldRegionKind.TERRITORY,
        owner_role="attacker",
    )
    defender_territory = _single_battlefield_region(
        battlefield_regions,
        region_kind=BattlefieldRegionKind.TERRITORY,
        owner_role="defender",
    )
    no_mans_land = _single_battlefield_region(
        battlefield_regions,
        region_kind=BattlefieldRegionKind.NO_MANS_LAND,
        owner_role=None,
    )
    _validate_region_shape_matches_zone(
        region=attacker_deployment_region,
        zone=zones_by_role["attacker"],
    )
    _validate_region_shape_matches_zone(
        region=defender_deployment_region,
        zone=zones_by_role["defender"],
    )

    battlefield_area = battlefield_width_inches * battlefield_depth_inches
    attacker_deployment_area = _deployment_zone_shape_area(zones_by_role["attacker"].shape)
    defender_deployment_area = _deployment_zone_shape_area(zones_by_role["defender"].shape)
    if _deployment_zone_shapes_overlap_by_positive_area(
        zones_by_role["attacker"].shape,
        zones_by_role["defender"].shape,
    ):
        raise MissionPackError("Battlefield deployment zones must not overlap by positive area.")
    if set(no_mans_land.derived_from) != {
        zones_by_role["attacker"].deployment_zone_id,
        zones_by_role["defender"].deployment_zone_id,
    }:
        raise MissionPackError(
            "Battlefield no-man's-land region must derive from both deployment zones."
        )
    no_mans_land_area = _deployment_zone_shape_area(no_mans_land.shape)
    if (
        _deployment_zone_shapes_overlap_by_positive_area(
            no_mans_land.shape,
            zones_by_role["attacker"].shape,
        )
        or _deployment_zone_shapes_overlap_by_positive_area(
            no_mans_land.shape,
            zones_by_role["defender"].shape,
        )
        or not math.isclose(
            attacker_deployment_area + defender_deployment_area + no_mans_land_area,
            battlefield_area,
            rel_tol=0.0,
            abs_tol=_GEOMETRY_EPSILON,
        )
    ):
        raise MissionPackError(
            "Battlefield no-man's-land region must equal the battlefield outside deployment zones."
        )

    if _deployment_zone_shapes_overlap_by_positive_area(
        attacker_territory.shape,
        defender_territory.shape,
    ):
        raise MissionPackError("Battlefield territories must not overlap by positive area.")
    if not _deployment_zone_shape_covers_shape(
        attacker_territory.shape,
        zones_by_role["attacker"].shape,
    ):
        raise MissionPackError("Attacker territory must contain attacker deployment.")
    if not _deployment_zone_shape_covers_shape(
        defender_territory.shape,
        zones_by_role["defender"].shape,
    ):
        raise MissionPackError("Defender territory must contain defender deployment.")
    if not math.isclose(
        _deployment_zone_shape_area(attacker_territory.shape)
        + _deployment_zone_shape_area(defender_territory.shape),
        battlefield_area,
        rel_tol=0.0,
        abs_tol=_GEOMETRY_EPSILON,
    ):
        raise MissionPackError("Battlefield territories must cover the battlefield.")
    _validate_battlefield_layout_objective_roles(
        objective_markers=objective_markers,
        attacker_deployment_zone=zones_by_role["attacker"],
        defender_deployment_zone=zones_by_role["defender"],
    )


def _validate_battlefield_layout_objective_roles(
    *,
    objective_markers: tuple[ObjectiveMarkerDefinition, ...],
    attacker_deployment_zone: DeploymentZone,
    defender_deployment_zone: DeploymentZone,
) -> None:
    expected_counts = {
        ObjectiveMarkerRole.ATTACKER_HOME: 1,
        ObjectiveMarkerRole.DEFENDER_HOME: 1,
        ObjectiveMarkerRole.CENTRAL: 1,
        ObjectiveMarkerRole.EXPANSION: 2,
    }
    actual_counts = {
        role: sum(1 for marker in objective_markers if marker.objective_role is role)
        for role in expected_counts
    }
    if actual_counts != expected_counts:
        raise MissionPackError(
            "Battlefield layout objective roles must include one attacker home, one defender "
            "home, one central, and two expansion markers."
        )
    attacker_home = _single_objective_marker_by_role(
        objective_markers,
        ObjectiveMarkerRole.ATTACKER_HOME,
    )
    defender_home = _single_objective_marker_by_role(
        objective_markers,
        ObjectiveMarkerRole.DEFENDER_HOME,
    )
    if not attacker_deployment_zone.contains_point(
        attacker_home.x_inches,
        attacker_home.y_inches,
    ):
        raise MissionPackError("Attacker home objective must be in attacker deployment.")
    if not defender_deployment_zone.contains_point(
        defender_home.x_inches,
        defender_home.y_inches,
    ):
        raise MissionPackError("Defender home objective must be in defender deployment.")


def _deployment_zones_by_role(
    deployment_zones: tuple[DeploymentZone, ...],
) -> dict[str, DeploymentZone]:
    zones_by_role = {zone.player_id: zone for zone in deployment_zones}
    if set(zones_by_role) != {"attacker", "defender"}:
        raise MissionPackError("Battlefield layout deployment zones must be attacker/defender.")
    if len(zones_by_role) != len(deployment_zones):
        raise MissionPackError("Battlefield layout deployment zones must not duplicate roles.")
    return zones_by_role


def _single_battlefield_region(
    battlefield_regions: tuple[BattlefieldRegion, ...],
    *,
    region_kind: BattlefieldRegionKind,
    owner_role: str | None,
) -> BattlefieldRegion:
    matches = tuple(
        region
        for region in battlefield_regions
        if region.region_kind is region_kind and region.owner_role == owner_role
    )
    if len(matches) != 1:
        raise MissionPackError(
            "Battlefield layout regions must include exactly one required region."
        )
    return matches[0]


def _validate_region_shape_matches_zone(
    *,
    region: BattlefieldRegion,
    zone: DeploymentZone,
) -> None:
    if region.shape.to_payload() != zone.shape.to_payload():
        raise MissionPackError("Battlefield deployment region must match its deployment zone.")
    if region.derived_from != (zone.deployment_zone_id,):
        raise MissionPackError("Battlefield deployment region must derive from its zone ID.")


def _single_objective_marker_by_role(
    objective_markers: tuple[ObjectiveMarkerDefinition, ...],
    role: ObjectiveMarkerRole,
) -> ObjectiveMarkerDefinition:
    matches = tuple(marker for marker in objective_markers if marker.objective_role is role)
    if len(matches) != 1:
        raise MissionPackError("Battlefield layout objective role must be unique.")
    return matches[0]


def _validate_battlefield_layout_matches_deployment_map_geometry(
    *,
    layout: BattlefieldLayoutDefinition,
    deployment_map: DeploymentMapDefinition,
) -> None:
    if _objective_marker_payloads(layout.objective_markers) != _objective_marker_payloads(
        deployment_map.objective_markers
    ):
        raise MissionPackError(
            "Battlefield layout objective markers must match its deployment map."
        )
    if _deployment_zone_payloads(layout.deployment_zones) != _deployment_zone_payloads(
        deployment_map.deployment_zones
    ):
        raise MissionPackError("Battlefield layout deployment zones must match its deployment map.")


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


def _deployment_zone_shape_area(shape: DeploymentZoneShape) -> float:
    polygons = _deployment_zone_shape_polygon_points(shape)
    _validate_shape_polygons_do_not_overlap(polygons)
    return sum(abs(_signed_polygon_area(polygon)) for polygon in polygons)


def _deployment_zone_shapes_overlap_by_positive_area(
    first: DeploymentZoneShape,
    second: DeploymentZoneShape,
) -> bool:
    first_polygons = _deployment_zone_shape_polygon_points(first)
    second_polygons = _deployment_zone_shape_polygon_points(second)
    for first_polygon in first_polygons:
        for second_polygon in second_polygons:
            if _polygon_overlap_area(first_polygon, second_polygon) > _GEOMETRY_EPSILON:
                return True
    return False


def _deployment_zone_shape_covers_shape(
    container: DeploymentZoneShape,
    contained: DeploymentZoneShape,
) -> bool:
    contained_area = _deployment_zone_shape_area(contained)
    overlap_area = 0.0
    for container_polygon in _deployment_zone_shape_polygon_points(container):
        for contained_polygon in _deployment_zone_shape_polygon_points(contained):
            overlap_area += _polygon_overlap_area(container_polygon, contained_polygon)
    return math.isclose(
        overlap_area,
        contained_area,
        rel_tol=0.0,
        abs_tol=_GEOMETRY_EPSILON,
    )


def _deployment_zone_shape_polygon_points(
    shape: DeploymentZoneShape,
) -> tuple[tuple[_Point2D, ...], ...]:
    if shape.cutouts:
        raise MissionPackError(
            "Battlefield layout region invariant validation does not support cutout shapes."
        )
    return tuple(
        tuple((vertex.x, vertex.y) for vertex in polygon.vertices) for polygon in shape.polygons
    )


def _validate_shape_polygons_do_not_overlap(polygons: tuple[tuple[_Point2D, ...], ...]) -> None:
    for first_index, first_polygon in enumerate(polygons):
        for second_polygon in polygons[first_index + 1 :]:
            if _polygon_overlap_area(first_polygon, second_polygon) > _GEOMETRY_EPSILON:
                raise MissionPackError(
                    "Battlefield layout region shape polygons must not overlap by positive area."
                )


def _polygon_overlap_area(first: tuple[_Point2D, ...], second: tuple[_Point2D, ...]) -> float:
    total_area = 0.0
    for first_triangle in _triangulate_polygon(first):
        for second_triangle in _triangulate_polygon(second):
            total_area += _convex_polygon_intersection_area(first_triangle, second_triangle)
    return total_area


def _triangulate_polygon(vertices: tuple[_Point2D, ...]) -> tuple[tuple[_Point2D, ...], ...]:
    if len(vertices) < 3:
        raise MissionPackError("Battlefield layout region polygon must have at least 3 vertices.")
    remaining = list(vertices)
    if _signed_polygon_area(tuple(remaining)) < 0.0:
        remaining.reverse()

    triangles: list[tuple[_Point2D, ...]] = []
    guard = len(remaining) * len(remaining)
    while len(remaining) > 3:
        ear_index = _find_ear_index(tuple(remaining))
        if ear_index is None:
            raise MissionPackError("Battlefield layout region polygon must be simple.")
        previous_point = remaining[ear_index - 1]
        current_point = remaining[ear_index]
        next_point = remaining[(ear_index + 1) % len(remaining)]
        triangles.append((previous_point, current_point, next_point))
        del remaining[ear_index]
        guard -= 1
        if guard <= 0:
            raise MissionPackError("Battlefield layout region polygon triangulation failed.")
    triangles.append((remaining[0], remaining[1], remaining[2]))
    return tuple(triangles)


def _find_ear_index(vertices: tuple[_Point2D, ...]) -> int | None:
    for index, current_point in enumerate(vertices):
        previous_index = (index - 1) % len(vertices)
        next_index = (index + 1) % len(vertices)
        previous_point = vertices[previous_index]
        next_point = vertices[next_index]
        if _cross(previous_point, current_point, next_point) <= _GEOMETRY_EPSILON:
            continue
        triangle = (previous_point, current_point, next_point)
        if any(
            _point_in_triangle(point, triangle)
            for point_index, point in enumerate(vertices)
            if point_index not in {previous_index, index, next_index}
        ):
            continue
        return index
    return None


def _convex_polygon_intersection_area(
    first: tuple[_Point2D, ...],
    second: tuple[_Point2D, ...],
) -> float:
    clipped = list(_ensure_counter_clockwise(first))
    clip_polygon = _ensure_counter_clockwise(second)
    clip_edges = zip(clip_polygon, (*clip_polygon[1:], clip_polygon[0]), strict=True)
    for clip_start, clip_end in clip_edges:
        clipped = _clip_convex_polygon(clipped, clip_start, clip_end)
        if len(clipped) < 3:
            return 0.0
    return abs(_signed_polygon_area(tuple(clipped)))


def _clip_convex_polygon(
    subject: list[_Point2D],
    clip_start: _Point2D,
    clip_end: _Point2D,
) -> list[_Point2D]:
    if not subject:
        return []
    output: list[_Point2D] = []
    previous = subject[-1]
    previous_inside = _left_of_or_on_edge(previous, clip_start, clip_end)
    for current in subject:
        current_inside = _left_of_or_on_edge(current, clip_start, clip_end)
        if current_inside:
            if not previous_inside:
                output.append(_line_intersection(previous, current, clip_start, clip_end))
            output.append(current)
        elif previous_inside:
            output.append(_line_intersection(previous, current, clip_start, clip_end))
        previous = current
        previous_inside = current_inside
    return output


def _line_intersection(
    first_start: _Point2D,
    first_end: _Point2D,
    second_start: _Point2D,
    second_end: _Point2D,
) -> _Point2D:
    first_dx = first_end[0] - first_start[0]
    first_dy = first_end[1] - first_start[1]
    second_dx = second_end[0] - second_start[0]
    second_dy = second_end[1] - second_start[1]
    denominator = (first_dx * second_dy) - (first_dy * second_dx)
    if abs(denominator) <= _GEOMETRY_EPSILON:
        return first_end
    numerator = ((second_start[0] - first_start[0]) * second_dy) - (
        (second_start[1] - first_start[1]) * second_dx
    )
    ratio = numerator / denominator
    return (first_start[0] + (ratio * first_dx), first_start[1] + (ratio * first_dy))


def _ensure_counter_clockwise(vertices: tuple[_Point2D, ...]) -> tuple[_Point2D, ...]:
    if _signed_polygon_area(vertices) < 0.0:
        return tuple(reversed(vertices))
    return vertices


def _point_in_triangle(point: _Point2D, triangle: tuple[_Point2D, ...]) -> bool:
    first, second, third = triangle
    return (
        _cross(first, second, point) >= -_GEOMETRY_EPSILON
        and _cross(second, third, point) >= -_GEOMETRY_EPSILON
        and _cross(third, first, point) >= -_GEOMETRY_EPSILON
    )


def _left_of_or_on_edge(point: _Point2D, edge_start: _Point2D, edge_end: _Point2D) -> bool:
    return _cross(edge_start, edge_end, point) >= -_GEOMETRY_EPSILON


def _cross(first: _Point2D, second: _Point2D, third: _Point2D) -> float:
    return ((second[0] - first[0]) * (third[1] - first[1])) - (
        (second[1] - first[1]) * (third[0] - first[0])
    )


def _signed_polygon_area(vertices: tuple[_Point2D, ...]) -> float:
    area = 0.0
    previous = vertices[-1]
    for current in vertices:
        area += (previous[0] * current[1]) - (current[0] * previous[1])
        previous = current
    return area / 2.0


def _terrain_area_polygons_close(
    first: tuple[TerrainDisplayPoint, ...],
    second: tuple[TerrainDisplayPoint, ...],
) -> bool:
    if len(first) != len(second):
        return False
    for first_point, second_point in zip(first, second, strict=True):
        if not (
            math.isclose(
                first_point.x_inches,
                second_point.x_inches,
                rel_tol=0.0,
                abs_tol=_GEOMETRY_EPSILON,
            )
            and math.isclose(
                first_point.y_inches,
                second_point.y_inches,
                rel_tol=0.0,
                abs_tol=_GEOMETRY_EPSILON,
            )
        ):
            return False
    return True


def _geometry_bounds_close(
    first: tuple[float, float, float, float],
    second: tuple[float, float, float, float],
) -> bool:
    return all(
        math.isclose(
            first_value,
            second_value,
            rel_tol=0.0,
            abs_tol=_GEOMETRY_EPSILON,
        )
        for first_value, second_value in zip(first, second, strict=True)
    )


def _validate_known_ids(
    field_name: str, requested_ids: tuple[str, ...], known_ids: set[str]
) -> None:
    unknown_ids = set(requested_ids) - known_ids
    if unknown_ids:
        raise MissionPackError(
            f"{field_name} references unknown IDs: {', '.join(sorted(unknown_ids))}."
        )


def _validate_markers_within_battlefield(
    *,
    markers: tuple[ObjectiveMarkerDefinition, ...],
    width: float,
    depth: float,
) -> None:
    for marker in markers:
        if marker.x_inches < 0.0 or marker.x_inches > width:
            raise MissionPackError("Objective marker x must be within the battlefield.")
        if marker.y_inches < 0.0 or marker.y_inches > depth:
            raise MissionPackError("Objective marker y must be within the battlefield.")


def _validate_zones_within_battlefield(
    *,
    zones: tuple[DeploymentZone, ...],
    width: float,
    depth: float,
) -> None:
    for zone in zones:
        if zone.min_x < 0.0 or zone.max_x > width:
            raise MissionPackError("Deployment zone x bounds must be within the battlefield.")
        if zone.min_y < 0.0 or zone.max_y > depth:
            raise MissionPackError("Deployment zone y bounds must be within the battlefield.")


def _validate_regions_within_battlefield(
    *,
    regions: tuple[BattlefieldRegion, ...],
    width: float,
    depth: float,
) -> None:
    for region in regions:
        min_x, min_y, max_x, max_y = region.bounds()
        if min_x < 0.0 or max_x > width:
            raise MissionPackError("Battlefield region x bounds must be within the battlefield.")
        if min_y < 0.0 or max_y > depth:
            raise MissionPackError("Battlefield region y bounds must be within the battlefield.")


def _validate_terrain_areas_within_battlefield(
    *,
    terrain_areas: tuple[PlacedTerrainArea, ...],
    width: float,
    depth: float,
) -> None:
    for terrain_area in terrain_areas:
        if not terrain_area.is_within_battlefield(width=width, depth=depth):
            raise MissionPackError("Terrain area footprint must be within the battlefield.")


def _validate_unprefixed_identifier(
    field_name: str,
    value: object,
    *,
    reserved_prefix: str,
) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(reserved_prefix):
        raise MissionPackError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise MissionPackError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise MissionPackError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise MissionPackError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise MissionPackError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise MissionPackError(f"{field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return _validate_identifier(field_name, value)


def _validate_required_token(field_name: str, value: object, *, expected_token: str) -> str:
    token = _validate_identifier(field_name, value)
    if token != expected_token:
        raise MissionPackError(f"{field_name} must be {expected_token}.")
    return token


def _validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise MissionPackError(f"{field_name} must be a bool.")
    return value


def _validate_finite_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise MissionPackError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise MissionPackError(f"{field_name} must be finite.")
    return number


def _validate_positive_number(field_name: str, value: object) -> float:
    number = _validate_finite_number(field_name, value)
    if number <= 0.0:
        raise MissionPackError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise MissionPackError(f"{field_name} must be an integer.")
    if value < 1:
        raise MissionPackError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise MissionPackError(f"{field_name} must be an integer.")
    if value < 0:
        raise MissionPackError(f"{field_name} must not be negative.")
    return value


def _validate_optional_positive_int(field_name: str, value: object | None) -> int | None:
    if value is None:
        return None
    return _validate_positive_int(field_name, value)
