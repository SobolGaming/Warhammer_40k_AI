from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from warhammer40k_core.core.battlefield_regions import BattlefieldRegion, BattlefieldRegionKind
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
)
from warhammer40k_core.core.missions import (
    BattlefieldLayoutDefinition,
    MissionPackError,
    MissionSourcePackageDefinition,
    ObjectiveMarkerDefinition,
    ObjectiveTerrainAreaDefinition,
    objective_marker_role_from_token,
)
from warhammer40k_core.core.terrain_areas import (
    PlacedTerrainArea,
    SymmetryAxis,
    TerrainAreaClassification,
    TerrainAreaFootprintTemplate,
    TerrainAreaLocalTransform,
    mirror_placed_terrain_area,
    rotate_point,
    terrain_area_local_transform_from_token,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayPoint
from warhammer40k_core.core.terrain_layouts import (
    TerrainFeatureAreaPlacement,
    TerrainFeaturePreset,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as chapter_approved,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_base_size_rows,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layout_geometry_2026_06 import (  # noqa: E501
    deployment_zone_rows_from_specs,
    event_no_mans_land_shape,
    event_territory_vertices,
    terrain_area_classifications_by_suffix,
    terrain_area_group_ids_by_suffix,
    terrain_feature_placements_from_specs,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_primary_scoring_2026_06 import (  # noqa: E501
    PRIMARY_SCORING_PACKAGE_HASH,
    engine_implemented_primary_mission_ids,
    event_companion_primary_scoring_artifact,
)

EDITION_ID = "warhammer_40000_11th"
MISSION_PACK_ID = "11e-warhammer-event-companion-2026-07"
SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-1-2026-07"
SOURCE_TITLE = "Warhammer Event Companion v1.1"
SOURCE_VERSION = "1.1"
DOCUMENT_VERSION = "1.1"
SOURCE_KIND = "warhammer_event_companion"
EVENT_MODE = "warhammer_event"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-event-companion-source-v1"
EXPECTED_SOURCE_IMPORT_HASH = "281c1a62b7b0d6aa61ac03095642cd7a85b8ff8907c94d6424c3a01aeacf0dcc"
BATTLEFIELD_WIDTH_INCHES = 44.0
BATTLEFIELD_DEPTH_INCHES = 60.0
BATTLEFIELD_SIZE = "44x60_inches"
TERRAIN_AREA_FEATURE_KIND = "terrain_layout_area"
LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES = 9.0
LAYOUT_C_ARC_SEGMENTS = 16
type DeploymentZoneLayoutTemplateId = Literal[
    "deployment-zone-layout-1-staggered",
    "deployment-zone-layout-2-long-edge-strip",
    "deployment-zone-layout-3-quarter-circle-cutout",
    "deployment-zone-layout-4-stepped-long-edge",
    "deployment-zone-layout-5-short-edge-strip",
    "deployment-zone-layout-6-triangle",
]
type DeploymentZoneLayoutTemplateNumber = Literal[1, 2, 3, 4, 5, 6]
type DeploymentZoneLayoutTemplateTriplet = tuple[
    DeploymentZoneLayoutTemplateNumber,
    DeploymentZoneLayoutTemplateNumber,
    DeploymentZoneLayoutTemplateNumber,
]
DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED: DeploymentZoneLayoutTemplateId = (
    "deployment-zone-layout-1-staggered"
)
DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP: DeploymentZoneLayoutTemplateId = (
    "deployment-zone-layout-2-long-edge-strip"
)
DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT: DeploymentZoneLayoutTemplateId = (
    "deployment-zone-layout-3-quarter-circle-cutout"
)
DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE: DeploymentZoneLayoutTemplateId = (
    "deployment-zone-layout-4-stepped-long-edge"
)
DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP: DeploymentZoneLayoutTemplateId = (
    "deployment-zone-layout-5-short-edge-strip"
)
DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE: DeploymentZoneLayoutTemplateId = (
    "deployment-zone-layout-6-triangle"
)
_DEPLOYMENT_ZONE_LAYOUT_TEMPLATE_IDS: tuple[DeploymentZoneLayoutTemplateId, ...] = (
    DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED,
    DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP,
    DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT,
    DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE,
    DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP,
    DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE,
)
_DEPLOYMENT_ZONE_LAYOUT_TEMPLATE_NUMBERS_BY_SOURCE_PAIR: Mapping[
    tuple[str, str], DeploymentZoneLayoutTemplateTriplet
] = {
    ("take-and-hold", "take-and-hold"): (1, 2, 3),
    ("take-and-hold", "purge-the-foe"): (4, 3, 5),
    ("take-and-hold", "disruption"): (4, 6, 5),
    ("take-and-hold", "reconnaissance"): (1, 2, 3),
    ("take-and-hold", "priority-assets"): (6, 5, 2),
    ("purge-the-foe", "purge-the-foe"): (3, 1, 4),
    ("purge-the-foe", "disruption"): (3, 1, 4),
    ("purge-the-foe", "reconnaissance"): (5, 2, 6),
    ("purge-the-foe", "priority-assets"): (2, 3, 5),
    ("disruption", "disruption"): (6, 1, 4),
    ("disruption", "reconnaissance"): (1, 2, 3),
    ("disruption", "priority-assets"): (4, 1, 3),
    ("reconnaissance", "reconnaissance"): (4, 6, 1),
    ("reconnaissance", "priority-assets"): (6, 1, 4),
    ("priority-assets", "priority-assets"): (4, 6, 1),
}


class GeometryResolutionStatus(StrEnum):
    CANONICAL_GEOMETRY_AVAILABLE = "canonical_geometry_available"
    REQUIRES_PROJECT_GEOMETRY_OVERRIDE = "requires_project_geometry_override"
    REQUIRES_EVENT_ORGANIZER_OVERRIDE = "requires_event_organizer_override"
    UNSUPPORTED_FOR_PHYSICAL_GEOMETRY = "unsupported_for_physical_geometry"


@dataclass(frozen=True, slots=True)
class EventCompanionPackageIdentity:
    source_kind: str
    document_version: str
    event_mode: str
    battlefield_size: str
    excludes_deployment_cards: bool
    excludes_twist_cards: bool
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source_kind": self.source_kind,
            "document_version": self.document_version,
            "event_mode": self.event_mode,
            "battlefield_size": self.battlefield_size,
            "excludes_deployment_cards": self.excludes_deployment_cards,
            "excludes_twist_cards": self.excludes_twist_cards,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class WarhammerEventMissionSequenceStep:
    order_index: int
    step_id: str
    actor_policy: str
    source_page: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "order_index": self.order_index,
            "step_id": self.step_id,
            "actor_policy": self.actor_policy,
            "source_page": self.source_page,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class WarhammerEventMissionSequenceDescriptor:
    sequence_id: str
    steps: tuple[WarhammerEventMissionSequenceStep, ...]
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "sequence_id": self.sequence_id,
            "steps": [step.to_payload() for step in self.steps],
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class TacticalSecondaryProcedureDescriptor:
    draw_timing: str
    draw_count: int
    drawn_cards_become_active: bool
    once_per_battle_replacement_timing: str
    replacement_cost_cp: int
    replacement_discard_count: int
    replacement_draw_count: int
    end_turn_scoring_order: str
    achieved_discard_requires_vp: bool
    own_turn_cp_discard_timing: str
    own_turn_cp_discard_minimum: int
    own_turn_cp_reward: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "draw_timing": self.draw_timing,
            "draw_count": self.draw_count,
            "drawn_cards_become_active": self.drawn_cards_become_active,
            "once_per_battle_replacement_timing": self.once_per_battle_replacement_timing,
            "replacement_cost_cp": self.replacement_cost_cp,
            "replacement_discard_count": self.replacement_discard_count,
            "replacement_draw_count": self.replacement_draw_count,
            "end_turn_scoring_order": self.end_turn_scoring_order,
            "achieved_discard_requires_vp": self.achieved_discard_requires_vp,
            "own_turn_cp_discard_timing": self.own_turn_cp_discard_timing,
            "own_turn_cp_discard_minimum": self.own_turn_cp_discard_minimum,
            "own_turn_cp_reward": self.own_turn_cp_reward,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class FixedSecondaryProcedureDescriptor:
    selection_timing: str
    selected_count: int
    hidden_until_reveal: bool
    revealed_face_up: bool
    discardable: bool
    active_duration: str
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "selection_timing": self.selection_timing,
            "selected_count": self.selected_count,
            "hidden_until_reveal": self.hidden_until_reveal,
            "revealed_face_up": self.revealed_face_up,
            "discardable": self.discardable,
            "active_duration": self.active_duration,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class MissionCardScoringGrammarRule:
    rule_id: str
    token: str
    semantics: str
    engine_contract: str
    source_id: str

    def to_payload(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "token": self.token,
            "semantics": self.semantics,
            "engine_contract": self.engine_contract,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class MissionCardScoringGrammar:
    grammar_id: str
    supported_tokens: tuple[str, ...]
    rules: tuple[MissionCardScoringGrammarRule, ...]
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "grammar_id": self.grammar_id,
            "supported_tokens": list(self.supported_tokens),
            "rules": [rule.to_payload() for rule in self.rules],
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class EventPrimaryMissionMatrixSourceRow:
    source_left_force_disposition_id: str
    source_right_force_disposition_id: str
    source_left_primary_mission_id: str
    source_left_primary_mission_name: str
    source_right_primary_mission_id: str
    source_right_primary_mission_name: str
    layout_pair_id: str
    layout_source_page_start: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "source_left_force_disposition_id": self.source_left_force_disposition_id,
            "source_right_force_disposition_id": self.source_right_force_disposition_id,
            "source_left_primary_mission_id": self.source_left_primary_mission_id,
            "source_left_primary_mission_name": self.source_left_primary_mission_name,
            "source_right_primary_mission_id": self.source_right_primary_mission_id,
            "source_right_primary_mission_name": self.source_right_primary_mission_name,
            "layout_pair_id": self.layout_pair_id,
            "layout_source_page_start": self.layout_source_page_start,
            "source_id": self.source_id,
        }


class PrimaryMissionScoringCoverageStatus(StrEnum):
    ENGINE_IMPLEMENTED = "engine_implemented"
    SOURCE_KNOWN_ENGINE_PENDING = "source_known_engine_pending"
    AWAITING_SOURCE = "awaiting_source"


@dataclass(frozen=True, slots=True)
class EventPrimaryMissionActionSourceRow:
    mission_action_id: str
    primary_mission_id: str
    name: str
    start_phase: str
    start_timing: str
    completion_timing: str
    eligible_unit_policy: str
    target_policy: str
    use_limit: str
    effect_descriptor: str
    engine_exposure_status: str
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "mission_action_id": self.mission_action_id,
            "primary_mission_id": self.primary_mission_id,
            "name": self.name,
            "start_phase": self.start_phase,
            "start_timing": self.start_timing,
            "completion_timing": self.completion_timing,
            "eligible_unit_policy": self.eligible_unit_policy,
            "target_policy": self.target_policy,
            "use_limit": self.use_limit,
            "effect_descriptor": self.effect_descriptor,
            "engine_exposure_status": self.engine_exposure_status,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class EventPrimaryMissionScoringCoverageRow:
    primary_mission_id: str
    primary_mission_name: str
    status: PrimaryMissionScoringCoverageStatus
    scoring_rule_count: int
    mission_action_count: int
    needed_work: tuple[str, ...]
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "primary_mission_id": self.primary_mission_id,
            "primary_mission_name": self.primary_mission_name,
            "status": self.status.value,
            "scoring_rule_count": self.scoring_rule_count,
            "mission_action_count": self.mission_action_count,
            "needed_work": list(self.needed_work),
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class CardAmendmentSet:
    amendment_set_id: str
    amendments: tuple[str, ...]
    source_page: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "amendment_set_id": self.amendment_set_id,
            "amendments": list(self.amendments),
            "source_page": self.source_page,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class EventShapeSourceRecord:
    shape_id: str
    role: str
    polygons: tuple[tuple[tuple[float, float], ...], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "shape_id": self.shape_id,
            "role": self.role,
            "polygons": [
                [[x, y] for x, y in polygon_vertices] for polygon_vertices in self.polygons
            ],
        }


@dataclass(frozen=True, slots=True)
class EventObjectivePointRecord:
    objective_marker_id: str
    objective_kind: str
    x_inches: float
    y_inches: float

    def to_payload(self) -> dict[str, object]:
        return {
            "objective_marker_id": self.objective_marker_id,
            "objective_kind": self.objective_kind,
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
        }


@dataclass(frozen=True, slots=True)
class EventTerrainSourceRecord:
    feature_id: str
    feature_kind: str
    density: str
    x_inches: float
    y_inches: float
    width_inches: float
    depth_inches: float

    def to_payload(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "feature_kind": self.feature_kind,
            "density": self.density,
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
            "width_inches": self.width_inches,
            "depth_inches": self.depth_inches,
        }


@dataclass(frozen=True, slots=True)
class WarhammerEventLayoutDescriptor:
    layout_id: str
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    player_primary_mission_id: str
    opponent_primary_mission_id: str
    layout_variant: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    attacker_edge: str
    defender_edge: str
    deployment_zone_shapes: tuple[EventShapeSourceRecord, ...]
    no_mans_land_shape: EventShapeSourceRecord
    player_territory_shapes: tuple[EventShapeSourceRecord, ...]
    objective_points: tuple[EventObjectivePointRecord, ...]
    terrain_features: tuple[EventTerrainSourceRecord, ...]
    geometry_extraction_status: str
    source_page: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "layout_id": self.layout_id,
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "player_primary_mission_id": self.player_primary_mission_id,
            "opponent_primary_mission_id": self.opponent_primary_mission_id,
            "layout_variant": self.layout_variant,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "attacker_edge": self.attacker_edge,
            "defender_edge": self.defender_edge,
            "deployment_zone_shapes": [shape.to_payload() for shape in self.deployment_zone_shapes],
            "no_mans_land_shape": self.no_mans_land_shape.to_payload(),
            "player_territory_shapes": [
                shape.to_payload() for shape in self.player_territory_shapes
            ],
            "objective_points": [objective.to_payload() for objective in self.objective_points],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
            "geometry_extraction_status": self.geometry_extraction_status,
            "source_page": self.source_page,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class BaseSizeSourceRecord:
    record_id: str
    faction_name: str
    source_section_name: str | None
    unit_name: str
    source_base_text: str
    base_source_kind: str
    geometry_resolution_status: GeometryResolutionStatus
    canonical_base_size: BaseSizeDefinition | None
    source_page: int
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "record_id": self.record_id,
            "faction_name": self.faction_name,
            "source_section_name": self.source_section_name,
            "unit_name": self.unit_name,
            "source_base_text": self.source_base_text,
            "base_source_kind": self.base_source_kind,
            "geometry_resolution_status": self.geometry_resolution_status.value,
            "canonical_base_size": (
                None if self.canonical_base_size is None else self.canonical_base_size.to_payload()
            ),
            "source_page": self.source_page,
            "source_id": self.source_id,
        }


def source_package_definition() -> MissionSourcePackageDefinition:
    source_import_hash = _import_hash()
    if source_import_hash != EXPECTED_SOURCE_IMPORT_HASH:
        raise MissionPackError(
            "Event Companion mission source import hash drifted from its reviewed pin."
        )
    return MissionSourcePackageDefinition(
        edition_id=EDITION_ID,
        mission_pack_id=MISSION_PACK_ID,
        source_package_id=SOURCE_PACKAGE_ID,
        source_title=SOURCE_TITLE,
        source_version=SOURCE_VERSION,
        source_commit_or_import_hash=source_import_hash,
        imported_at_schema_version=IMPORTED_AT_SCHEMA_VERSION,
    )


def package_identity() -> EventCompanionPackageIdentity:
    return EventCompanionPackageIdentity(
        source_kind=SOURCE_KIND,
        document_version=DOCUMENT_VERSION,
        event_mode=EVENT_MODE,
        battlefield_size=BATTLEFIELD_SIZE,
        excludes_deployment_cards=True,
        excludes_twist_cards=True,
        source_id=f"{SOURCE_PACKAGE_ID}:package-identity",
    )


def mission_sequence_descriptor() -> WarhammerEventMissionSequenceDescriptor:
    steps = (
        ("muster_armies", "both_players_roster_source", 1),
        ("determine_primary_missions", "force_disposition_matrix", 1),
        ("determine_layout", "organizer_or_random_abc_layout", 1),
        ("create_the_battlefield", "source_backed_layout", 1),
        ("determine_attacker_and_defender", "roll_off", 2),
        ("select_secondary_missions", "secret_mode_then_reveal_fixed", 2),
        ("declare_battle_formations", "embarked_then_reserves_then_reveal", 2),
        ("deploy_armies", "defender_first_alternating", 2),
        ("redeploy_units", "attacker_first_alternating", 2),
        ("determine_first_turn", "roll_off_winner_takes_first", 2),
        ("resolve_prebattle_rules", "first_turn_player_first", 2),
        ("begin_battle", "battle_round_one", 2),
        ("end_battle", "after_five_battle_rounds_continue_tabled_players", 2),
        ("determine_victor", "battle_ready_then_vp_total_then_draw_if_tied", 2),
    )
    return WarhammerEventMissionSequenceDescriptor(
        sequence_id="warhammer-event-mission-sequence",
        steps=tuple(
            WarhammerEventMissionSequenceStep(
                order_index=index,
                step_id=step_id,
                actor_policy=actor_policy,
                source_page=source_page,
                source_id=f"{SOURCE_PACKAGE_ID}:mission-sequence:{step_id}",
            )
            for index, (step_id, actor_policy, source_page) in enumerate(steps, start=1)
        ),
        source_id=f"{SOURCE_PACKAGE_ID}:mission-sequence",
    )


def tactical_secondary_procedure() -> TacticalSecondaryProcedureDescriptor:
    return TacticalSecondaryProcedureDescriptor(
        draw_timing="start_of_command_phase",
        draw_count=2,
        drawn_cards_become_active=True,
        once_per_battle_replacement_timing="end_of_command_phase",
        replacement_cost_cp=1,
        replacement_discard_count=1,
        replacement_draw_count=1,
        end_turn_scoring_order="active_player_first",
        achieved_discard_requires_vp=True,
        own_turn_cp_discard_timing="after_end_turn_secondary_scoring",
        own_turn_cp_discard_minimum=1,
        own_turn_cp_reward=1,
        source_id=f"{SOURCE_PACKAGE_ID}:secondary:tactical-procedure",
    )


def fixed_secondary_procedure() -> FixedSecondaryProcedureDescriptor:
    return FixedSecondaryProcedureDescriptor(
        selection_timing="select_secondary_missions",
        selected_count=2,
        hidden_until_reveal=True,
        revealed_face_up=True,
        discardable=False,
        active_duration="whole_battle",
        source_id=f"{SOURCE_PACKAGE_ID}:secondary:fixed-procedure",
    )


def mission_card_scoring_grammar() -> MissionCardScoringGrammar:
    return MissionCardScoringGrammar(
        grammar_id="event-companion-mission-card-scoring-grammar-v1",
        supported_tokens=(
            "cumulative_condition",
            "exclusive_or_condition",
            "exactly_one_condition",
            "leaves_battlefield_event",
            "vp_up_to_limit",
            "when_drawn_tactical_only",
        ),
        rules=(
            MissionCardScoringGrammarRule(
                rule_id="cumulative-condition",
                token="cumulative_condition",
                semantics="score_normal_and_cumulative_vp_when_cumulative_condition_is_achieved",
                engine_contract="sum_achieved_cumulative_rules_for_the_same_card",
                source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar:cumulative-condition",
            ),
            MissionCardScoringGrammarRule(
                rule_id="exclusive-or-condition",
                token="exclusive_or_condition",
                semantics="score_only_one_of_the_normal_or_or_conditions",
                engine_contract="do_not_sum_exclusive_or_branches_for_the_same_card",
                source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar:exclusive-or-condition",
            ),
            MissionCardScoringGrammarRule(
                rule_id="exactly-one-condition",
                token="exactly_one_condition",
                semantics="underlined_one_means_exactly_one_not_one_or_more",
                engine_contract="score_count_must_equal_one_for_exactly_one_conditions",
                source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar:exactly-one-condition",
            ),
            MissionCardScoringGrammarRule(
                rule_id="leaves-battlefield-event",
                token="leaves_battlefield_event",
                semantics="unit_destroyed_embarks_or_is_removed_from_battlefield_by_rule",
                engine_contract=(
                    "leaves_battlefield_evidence_must_include_destroyed_embarked_and_rule_removed"
                ),
                source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar:leaves-battlefield-event",
            ),
            MissionCardScoringGrammarRule(
                rule_id="vp-up-to-limit",
                token="vp_up_to_limit",
                semantics="ignore_vp_scored_in_excess_of_the_stated_limit",
                engine_contract="apply_rule_cap_before_adding_award_to_the_vp_ledger",
                source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar:vp-up-to-limit",
            ),
            MissionCardScoringGrammarRule(
                rule_id="when-drawn-tactical-only",
                token="when_drawn_tactical_only",
                semantics="when_drawn_sections_apply_only_to_tactical_secondary_missions",
                engine_contract="ignore_when_drawn_sections_for_fixed_secondary_mode",
                source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar:when-drawn-tactical-only",
            ),
        ),
        source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar",
    )


def card_amendment_set() -> CardAmendmentSet:
    return CardAmendmentSet(
        amendment_set_id="event-companion-v1-card-amendments",
        amendments=(),
        source_page=4,
        source_id=f"{SOURCE_PACKAGE_ID}:card-amendments",
    )


def event_primary_mission_matrix_source_rows() -> tuple[EventPrimaryMissionMatrixSourceRow, ...]:
    return tuple(
        _event_matrix_source_row(
            source_left_force_disposition_id=left_force_disposition_id,
            source_right_force_disposition_id=right_force_disposition_id,
            source_left_primary_mission_id=left_primary_mission_id,
            source_left_primary_mission_name=left_primary_mission_name,
            source_right_primary_mission_id=right_primary_mission_id,
            source_right_primary_mission_name=right_primary_mission_name,
            layout_source_page_start=layout_source_page_start,
        )
        for (
            left_force_disposition_id,
            right_force_disposition_id,
            left_primary_mission_id,
            left_primary_mission_name,
            right_primary_mission_id,
            right_primary_mission_name,
            layout_source_page_start,
        ) in (
            (
                "take-and-hold",
                "take-and-hold",
                "primary-battlefield-dominance",
                "Battlefield Dominance",
                "primary-battlefield-dominance",
                "Battlefield Dominance",
                9,
            ),
            (
                "take-and-hold",
                "purge-the-foe",
                "primary-immovable-object",
                "Immovable Object",
                "primary-unstoppable-force",
                "Unstoppable Force",
                12,
            ),
            (
                "take-and-hold",
                "disruption",
                "primary-determined-acquisition",
                "Determined Acquisition",
                "primary-death-trap",
                "Death Trap",
                15,
            ),
            (
                "take-and-hold",
                "reconnaissance",
                "primary-purge-and-secure",
                "Purge and Secure",
                "primary-reconnaissance-sweep",
                "Reconnaissance Sweep",
                18,
            ),
            (
                "take-and-hold",
                "priority-assets",
                "primary-inescapable-dominion",
                "Inescapable Dominion",
                "primary-secure-asset",
                "Secure Asset",
                21,
            ),
            (
                "purge-the-foe",
                "purge-the-foe",
                "primary-meatgrinder",
                "Meatgrinder",
                "primary-meatgrinder",
                "Meatgrinder",
                24,
            ),
            (
                "purge-the-foe",
                "disruption",
                "primary-punishment",
                "Punishment",
                "primary-delaying-action",
                "Delaying Action",
                27,
            ),
            (
                "purge-the-foe",
                "reconnaissance",
                "primary-consecrate",
                "Consecrate",
                "primary-triangulation",
                "Triangulation",
                30,
            ),
            (
                "purge-the-foe",
                "priority-assets",
                "primary-destroyers-wrath",
                "Destroyer's Wrath",
                "primary-vital-link",
                "Vital Link",
                33,
            ),
            (
                "disruption",
                "disruption",
                "primary-outmaneuver",
                "Outmanoeuvre",
                "primary-outmaneuver",
                "Outmanoeuvre",
                36,
            ),
            (
                "disruption",
                "reconnaissance",
                "primary-smoke-and-mirrors",
                "Smoke and Mirrors",
                "primary-surveil-the-foe",
                "Surveil the Foe",
                39,
            ),
            (
                "disruption",
                "priority-assets",
                "primary-locate-and-deny",
                "Locate and Deny",
                "primary-extract-relic",
                "Extract Relic",
                42,
            ),
            (
                "reconnaissance",
                "reconnaissance",
                "primary-gather-intel",
                "Gather Intel",
                "primary-gather-intel",
                "Gather Intel",
                45,
            ),
            (
                "reconnaissance",
                "priority-assets",
                "primary-search-and-scour",
                "Search and Scour",
                "primary-vanguard-operation",
                "Vanguard Operation",
                48,
            ),
            (
                "priority-assets",
                "priority-assets",
                "primary-sabotage",
                "Sabotage",
                "primary-sabotage",
                "Sabotage",
                51,
            ),
        )
    )


def primary_mission_action_source_rows() -> tuple[EventPrimaryMissionActionSourceRow, ...]:
    artifact = event_companion_primary_scoring_artifact()
    return tuple(
        EventPrimaryMissionActionSourceRow(
            mission_action_id=row.mission_action_id,
            primary_mission_id=row.primary_mission_id,
            name=row.name,
            start_phase=row.start_phase,
            start_timing=row.start_timing,
            completion_timing=row.completion_timing,
            eligible_unit_policy=row.eligible_unit_policy,
            target_policy=row.target_policy,
            use_limit=row.use_limit,
            effect_descriptor=row.effect_descriptor,
            engine_exposure_status=row.engine_exposure_status,
            source_id=row.source_id,
        )
        for row in artifact.primary_mission_actions
    )


def primary_mission_scoring_coverage_rows() -> tuple[EventPrimaryMissionScoringCoverageRow, ...]:
    primary_rows = {row.primary_mission_id: row for row in primary_mission_rows()}
    action_ids_by_primary_mission: dict[str, set[str]] = {}
    for action in mission_action_rows():
        if action.mission_kind != "primary":
            continue
        action_ids_by_primary_mission.setdefault(action.mission_id, set()).add(
            action.mission_action_id
        )
    for source_action in primary_mission_action_source_rows():
        action_ids_by_primary_mission.setdefault(source_action.primary_mission_id, set()).add(
            source_action.mission_action_id
        )
    rows: list[EventPrimaryMissionScoringCoverageRow] = []
    for mission_id, mission_name in _event_primary_mission_names():
        primary = primary_rows[mission_id]
        scoring_rule_count = len(primary.scoring_rules)
        mission_action_count = len(action_ids_by_primary_mission.get(mission_id, set()))
        needed_work = _primary_mission_needed_work(mission_id)
        if mission_id in _ENGINE_IMPLEMENTED_PRIMARY_MISSION_IDS:
            status = PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED
        elif scoring_rule_count > 0 or mission_action_count > 0:
            status = PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
        else:
            status = PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE
        rows.append(
            EventPrimaryMissionScoringCoverageRow(
                primary_mission_id=mission_id,
                primary_mission_name=mission_name,
                status=status,
                scoring_rule_count=scoring_rule_count,
                mission_action_count=mission_action_count,
                needed_work=needed_work,
                source_id=f"{SOURCE_PACKAGE_ID}:primary-scoring-coverage:{mission_id}",
            )
        )
    return tuple(rows)


def primary_mission_rows() -> tuple[chapter_approved.SourcePrimaryMissionRow, ...]:
    return _validated_primary_mission_rows(
        artifact_rows=_event_primary_mission_rows_by_id(),
        matrix_names=_event_primary_mission_names(),
    )


def _validated_primary_mission_rows(
    *,
    artifact_rows: Mapping[str, chapter_approved.SourcePrimaryMissionRow],
    matrix_names: tuple[tuple[str, str], ...],
) -> tuple[chapter_approved.SourcePrimaryMissionRow, ...]:
    matrix_ids = tuple(mission_id for mission_id, _mission_name in matrix_names)
    if set(artifact_rows) != set(matrix_ids):
        raise MissionPackError(
            "Event Companion Primary scoring artifact inventory drifted from the matrix."
        )
    rows: list[chapter_approved.SourcePrimaryMissionRow] = []
    for mission_id, mission_name in matrix_names:
        artifact_row = artifact_rows[mission_id]
        if artifact_row.name != mission_name:
            raise MissionPackError(
                "Event Companion Primary scoring artifact name drifted from the matrix."
            )
        rows.append(artifact_row)
    return tuple(rows)


def secondary_mission_rows() -> tuple[chapter_approved.SourceSecondaryMissionRow, ...]:
    return chapter_approved.secondary_mission_rows()


def force_disposition_rows() -> tuple[chapter_approved.SourceForceDispositionRow, ...]:
    return chapter_approved.force_disposition_rows()


def primary_mission_matrix_rows() -> tuple[chapter_approved.SourcePrimaryMissionMatrixCellRow, ...]:
    rows: list[chapter_approved.SourcePrimaryMissionMatrixCellRow] = []
    for source_row in event_primary_mission_matrix_source_rows():
        rows.append(_matrix_cell_from_event_source_row(source_row, use_left=True))
        if (
            source_row.source_left_force_disposition_id
            != source_row.source_right_force_disposition_id
        ):
            rows.append(_matrix_cell_from_event_source_row(source_row, use_left=False))
    return tuple(rows)


def mission_action_rows() -> tuple[chapter_approved.SourceMissionActionRow, ...]:
    return (*chapter_approved.mission_action_rows(), *_event_primary_mission_action_rows())


def _event_primary_mission_action_rows() -> tuple[chapter_approved.SourceMissionActionRow, ...]:
    rows: list[chapter_approved.SourceMissionActionRow] = []
    for source_row in primary_mission_action_source_rows():
        if source_row.engine_exposure_status != "engine_implemented":
            raise MissionPackError(
                "Event Companion Primary Mission Action runtime exposure status drifted."
            )
        if source_row.completion_timing == "immediate":
            interruption_conditions: tuple[str, ...] = ()
        elif source_row.completion_timing == "turn_end":
            interruption_conditions = (
                "unit_moved",
                "unit_destroyed",
                "unit_left_battlefield",
            )
        else:
            raise MissionPackError(
                "Event Companion Primary Mission Action completion timing is unsupported."
            )
        rows.append(
            chapter_approved.SourceMissionActionRow(
                mission_action_id=source_row.mission_action_id,
                mission_id=source_row.primary_mission_id,
                mission_kind="primary",
                name=source_row.name,
                start_phase=source_row.start_phase,
                start_timing=source_row.start_timing,
                completion_timing=source_row.completion_timing,
                eligible_unit_policy=source_row.eligible_unit_policy,
                target_policy=source_row.target_policy,
                interruption_conditions=interruption_conditions,
                victory_points=0,
                scoring_source_id=source_row.primary_mission_id,
            )
        )
    return tuple(rows)


def mission_pack_scoring_row() -> chapter_approved.SourceMissionPackScoringRow:
    chapter_approved_scoring = chapter_approved.mission_pack_scoring_row()
    return chapter_approved.SourceMissionPackScoringRow(
        game_length_battle_rounds=5,
        primary_scoring_phase=chapter_approved_scoring.primary_scoring_phase,
        primary_scoring_timing=chapter_approved_scoring.primary_scoring_timing,
        secondary_vp_per_score=chapter_approved_scoring.secondary_vp_per_score,
        mission_action_vp=chapter_approved_scoring.mission_action_vp,
        primary_vp_cap=45,
        secondary_vp_cap=45,
        total_vp_cap=100,
        end_of_round_scoring_windows=chapter_approved_scoring.end_of_round_scoring_windows,
        end_of_game_scoring_windows=chapter_approved_scoring.end_of_game_scoring_windows,
        reserve_destruction_timing=chapter_approved_scoring.reserve_destruction_timing,
        reserve_destruction_battle_round=chapter_approved_scoring.reserve_destruction_battle_round,
        reserve_destruction_excludes_during_battle_strategic_reserves=(
            chapter_approved_scoring.reserve_destruction_excludes_during_battle_strategic_reserves
        ),
        reserve_destruction_only_declare_battle_formations=(
            chapter_approved_scoring.reserve_destruction_only_declare_battle_formations
        ),
    )


_ENGINE_IMPLEMENTED_PRIMARY_MISSION_IDS = engine_implemented_primary_mission_ids()


_SOURCE_KNOWN_ENGINE_PENDING_WORK: dict[str, tuple[str, ...]] = {
    "primary-consecrate": (
        "engine_primary_marker_state:consecrated_objective",
        "engine_primary_condition:consecrated_objective_thresholds",
        "engine_primary_condition:enemy_home_objective_consecrated",
    ),
    "primary-extract-relic": (
        "engine_primary_action:sensor-sweep-extract-relic",
        "engine_primary_marker_state:opponent_operation_marker",
        "engine_primary_condition:friendly_unit_performed_sensor_sweep_this_turn",
        "engine_primary_condition:single_opponent_operation_marker_terrain_area_state",
    ),
    "primary-gather-intel": (
        "engine_primary_action:extract-intelligence",
        "engine_primary_marker_state:gather_intel_operation_marker",
        "engine_primary_condition:control_one_or_more_central_objectives_first_battle_round",
        "engine_primary_condition:each_friendly_unit_extracted_intelligence_this_turn",
        "engine_primary_condition:gather_intel_operation_marker_end_of_battle",
    ),
    "primary-locate-and-deny": (
        "engine_primary_start_battle_setup:locate_and_deny_operation_markers",
        "engine_primary_action:sensor-sweep-locate-and-deny",
        "engine_primary_marker_state:operation_marker_terrain_area",
        "engine_primary_condition:single_friendly_operation_marker_terrain_area_state",
    ),
    "primary-punishment": (
        "engine_primary_start_turn_choice:condemned_enemy_units",
        "engine_primary_condition:condemned_enemy_units_left_battlefield",
    ),
    "primary-sabotage": (
        "engine_primary_action:commit-sabotage",
        "engine_primary_condition:each_friendly_unit_committed_sabotage_this_turn",
        "engine_primary_condition:sabotage_opponent_territory_objective_bonus",
        "engine_primary_scoring_grammar:cumulative_condition",
    ),
    "primary-secure-asset": (
        "engine_primary_action:secure-asset",
        "engine_primary_condition:friendly_unit_secured_asset_this_turn",
    ),
    "primary-smoke-and-mirrors": (
        "engine_primary_action:decoy-objective",
        "engine_primary_marker_state:decoy_objective",
        "engine_primary_condition:decoy_objective_scoring",
        "engine_primary_condition:opponent_territory_objective_bonus",
    ),
    "primary-surveil-the-foe": (
        "engine_primary_action:surveil-enemy-unit",
        "engine_primary_marker_state:enemy_operation_marker",
        "engine_primary_movement_effect:remove_enemy_operation_markers_from_objective",
        "engine_primary_condition:enemy_unit_surveilled_marker_exception",
        "engine_primary_condition:no_enemy_operation_markers_on_battlefield",
    ),
    "primary-triangulation": (
        "engine_primary_action:triangulate-objective",
        "engine_primary_marker_state:triangulated_objective",
        "engine_primary_condition:triangulated_objective_thresholds",
        "engine_primary_condition:control_four_or_more_objectives",
    ),
    "primary-vanguard-operation": (
        "engine_primary_action:vanguard-operation",
        "engine_primary_condition:friendly_unit_performed_vanguard_operation_this_turn",
        "engine_primary_condition:enemy_territory_terrain_area_control",
    ),
    "primary-vital-link": (
        "engine_primary_action:maintain-control",
        "engine_primary_marker_state:vital_link_operation_marker",
        "engine_primary_condition:central_objective_operation_marker_bonus",
        "engine_primary_condition:controlled_central_objective_bonus",
        "engine_primary_scoring_grammar:cumulative_condition",
    ),
}


def _event_primary_mission_rows_by_id() -> dict[str, chapter_approved.SourcePrimaryMissionRow]:
    artifact = event_companion_primary_scoring_artifact()
    return {
        mission.primary_mission_id: chapter_approved.SourcePrimaryMissionRow(
            primary_mission_id=mission.primary_mission_id,
            name=mission.mission_name,
            max_vp_per_turn=mission.max_vp_per_turn,
            scoring_kind=mission.scoring_kind,
            vp_per_controlled_objective=mission.vp_per_controlled_objective,
            scoring_rules=tuple(
                _event_primary_rule(
                    rule.rule_id,
                    rule.timing,
                    rule.victory_points,
                    rule.condition,
                    rule.resolution_mode,
                    rule.resolution_group_id,
                )
                for rule in mission.scoring_rules
            ),
        )
        for mission in artifact.primary_missions
    }


def _event_primary_rule(
    rule_id: str,
    timing: str,
    victory_points: int,
    condition: str,
    resolution_mode: str,
    resolution_group_id: str | None,
) -> chapter_approved.SourceScoringRuleRow:
    return chapter_approved.SourceScoringRuleRow(
        rule_id=rule_id,
        timing=timing,
        source_kind="primary",
        victory_points=victory_points,
        cap=None,
        condition=condition,
        resolution_mode=resolution_mode,
        resolution_group_id=resolution_group_id,
    )


def _primary_mission_needed_work(primary_mission_id: str) -> tuple[str, ...]:
    if primary_mission_id in _ENGINE_IMPLEMENTED_PRIMARY_MISSION_IDS:
        return ()
    pending = _SOURCE_KNOWN_ENGINE_PENDING_WORK.get(primary_mission_id)
    if pending is not None:
        return pending
    return ("source_primary_scoring_text",)


def battlefield_layout_rows() -> tuple[chapter_approved.SourceBattlefieldLayoutRow, ...]:
    rows: list[chapter_approved.SourceBattlefieldLayoutRow] = []
    for first_id, second_id, _source_start_page in _LAYOUT_SOURCE_PAGES:
        matrix_row = _matrix_row(first_id, second_id)
        for layout_number in (1, 2, 3):
            layout_id = f"{first_id}-vs-{second_id}-layout-{layout_number}"
            rows.append(
                _battlefield_layout_row(
                    layout_id=layout_id,
                    player_force_disposition_id=first_id,
                    opponent_force_disposition_id=second_id,
                    primary_mission_id=matrix_row.primary_mission_id,
                    layout_number=layout_number,
                )
            )
    return tuple(rows)


def layout_descriptor_rows() -> tuple[WarhammerEventLayoutDescriptor, ...]:
    descriptors: list[WarhammerEventLayoutDescriptor] = []
    for first_id, second_id, _source_start_page in _LAYOUT_SOURCE_PAGES:
        player_primary = _matrix_row(first_id, second_id).primary_mission_id
        opponent_primary = _matrix_row(second_id, first_id).primary_mission_id
        for layout_number in (1, 2, 3):
            layout_id = f"{first_id}-vs-{second_id}-layout-{layout_number}"
            descriptors.append(
                WarhammerEventLayoutDescriptor(
                    layout_id=layout_id,
                    player_force_disposition_id=first_id,
                    opponent_force_disposition_id=second_id,
                    player_primary_mission_id=player_primary,
                    opponent_primary_mission_id=opponent_primary,
                    layout_variant=("a", "b", "c")[layout_number - 1],
                    battlefield_width_inches=_layout_battlefield_width(layout_id),
                    battlefield_depth_inches=_layout_battlefield_depth(layout_id),
                    attacker_edge=_layout_attacker_edge(layout_id, layout_number),
                    defender_edge=_layout_defender_edge(layout_id, layout_number),
                    deployment_zone_shapes=_descriptor_deployment_shapes(
                        layout_id=layout_id,
                    ),
                    no_mans_land_shape=_no_mans_land_shape(
                        layout_id=layout_id,
                    ),
                    player_territory_shapes=_territory_shapes(
                        layout_id=layout_id,
                    ),
                    objective_points=_descriptor_objectives(
                        layout_id=layout_id,
                    ),
                    terrain_features=_descriptor_terrain(
                        layout_id=layout_id,
                    ),
                    geometry_extraction_status=_layout_geometry_status(layout_id),
                    source_page=_battlefield_layout_source_page(layout_id),
                    source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{layout_id}:descriptor",
                )
            )
    return tuple(descriptors)


def terrain_area_footprint_templates() -> tuple[TerrainAreaFootprintTemplate, ...]:
    source_id = f"{SOURCE_PACKAGE_ID}:terrain-area-footprints-pdf"
    return (
        _footprint_template(
            template_id=event_layouts.FOOTPRINT_6X4,
            name='6" x 4" Terrain Area Footprint',
            width=6.5,
            depth=4.5,
            vertices=(
                (-3.25, 2.25),
                (2.75, 2.25),
                (2.75, 0.95),
                (3.25, 0.25),
                (2.85, -0.45),
                (3.05, -0.75),
                (2.75, -0.95),
                (2.75, -1.75),
                (0.05, -1.75),
                (-0.05, -1.95),
                (-0.45, -1.85),
                (-1.25, -2.25),
                (-2.05, -1.75),
                (-3.25, -1.75),
            ),
            source_id=source_id,
        ),
        _footprint_template(
            template_id=event_layouts.FOOTPRINT_10X2_5,
            name='10" x 2.5" Terrain Area Footprint',
            width=10.0,
            depth=3.6,
            vertices=(
                (-5.0, 1.2),
                (-4.5, 1.2),
                (-4.5, 1.3),
                (-3.0, 1.8),
                (-2.5, 1.2),
                (2.4, 1.2),
                (2.6, 1.45),
                (3.3, 1.2),
                (5.0, 1.2),
                (5.0, -1.3),
                (2.15, -1.3),
                (1.85, -1.6),
                (0.85, -1.8),
                (0.5, -1.3),
                (-5.0, -1.3),
            ),
            source_id=source_id,
        ),
        _footprint_template(
            template_id=event_layouts.FOOTPRINT_6X2,
            name='6" x 2" Terrain Area Footprint',
            width=6.1,
            depth=2.7,
            vertices=(
                (-3.05, 1.15),
                (-2.05, 1.15),
                (-2.05, 1.35),
                (-1.05, 1.35),
                (-1.05, 1.15),
                (3.05, 1.15),
                (3.05, -0.85),
                (2.15, -0.85),
                (1.3, -1.35),
                (0.45, -0.85),
                (-3.05, -0.85),
            ),
            source_id=source_id,
        ),
        _footprint_template(
            template_id=event_layouts.FOOTPRINT_7X11_5,
            name='7" x 11.5" Terrain Area Footprint',
            width=7.6,
            depth=11.5,
            vertices=(
                (-3.8, 5.75),
                (3.2, 5.75),
                (3.2, 4.65),
                (3.5, 4.05),
                (3.45, 3.75),
                (3.8, 2.75),
                (3.2, 2.25),
                (3.2, 1.45),
                (3.3, 0.75),
                (3.2, 0.05),
                (3.7, -1.15),
                (3.2, -2.25),
                (3.2, -5.75),
                (-3.8, -5.75),
            ),
            source_id=source_id,
        ),
        _footprint_template(
            template_id=event_layouts.FOOTPRINT_8X11_5_POLYGON,
            name='8" x 11.5" Polygon Terrain Area Footprint',
            width=12.0,
            depth=8.0,
            vertices=(
                (-5.5, 4.0),
                (6.0, 4.0),
                (6.0, 2.0),
                (5.5, 2.0),
                (-5.0, -4.0),
                (-5.5, -4.0),
                (-5.5, -1.8),
                (-6.0, -0.6),
                (-5.5, 0.0),
            ),
            source_id=source_id,
        ),
    )


def terrain_feature_presets() -> tuple[TerrainFeaturePreset, ...]:
    return event_layouts.BATTLEFIELD_TERRAIN_FEATURE_PRESETS


def deployment_zone_layout_template_shapes() -> tuple[
    tuple[DeploymentZoneLayoutTemplateId, DeploymentZoneShape],
    ...,
]:
    return tuple(
        (template_id, _deployment_zone_template_base_shape(template_id))
        for template_id in _DEPLOYMENT_ZONE_LAYOUT_TEMPLATE_IDS
    )


def battlefield_layout_definitions() -> tuple[BattlefieldLayoutDefinition, ...]:
    return tuple(
        _battlefield_layout_definition(layout_id=layout_id)
        for layout_id in sorted(event_layouts.BATTLEFIELD_LAYOUT_IDS)
    )


def _battlefield_layout_definition(
    *,
    layout_id: str,
) -> BattlefieldLayoutDefinition:
    layout_source = _battlefield_layout_source(layout_id)
    objective_markers = _battlefield_objective_definitions(layout_id=layout_id)
    terrain_areas = _battlefield_terrain_areas(layout_id)
    return BattlefieldLayoutDefinition(
        battlefield_layout_id=layout_id,
        name=layout_source.name,
        deployment_map_id=f"{layout_id}-deployment",
        terrain_layout_id=layout_id,
        battlefield_width_inches=BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=BATTLEFIELD_DEPTH_INCHES,
        coordinate_origin="bottom_left",
        coordinate_orientation="x_right_along_44_inch_edge_y_up_along_60_inch_edge",
        attacker_edge=_layout_attacker_edge(layout_id, _layout_number_from_layout_id(layout_id)),
        defender_edge=_layout_defender_edge(layout_id, _layout_number_from_layout_id(layout_id)),
        objective_markers=objective_markers,
        deployment_zones=tuple(
            DeploymentZone(
                deployment_zone_id=zone.deployment_zone_id,
                player_id=zone.player_role,
                shape=zone.shape,
            )
            for zone in _battlefield_deployment_zones(layout_id=layout_id)
        ),
        battlefield_regions=_battlefield_regions(layout_id=layout_id),
        terrain_areas=terrain_areas,
        terrain_feature_placements=_terrain_feature_area_placements(
            layout_id=layout_id,
            terrain_areas=terrain_areas,
        ),
        objective_role_counts=layout_source.objective_role_counts,
        source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{layout_source.source_layout_id}",
        objective_terrain_areas=_battlefield_objective_terrain_area_definitions(
            layout_id=layout_id,
            objective_markers=objective_markers,
            terrain_areas=terrain_areas,
        ),
    )


def _battlefield_layout_source(layout_id: str) -> event_layouts.EventBattlefieldLayoutSource:
    layout_source = event_layouts.BATTLEFIELD_LAYOUTS_BY_ID.get(layout_id)
    if layout_source is None:
        raise MissionPackError("Unsupported battlefield layout ID.")
    return layout_source


def _battlefield_layout_source_page(layout_id: str) -> int:
    source_page = _battlefield_layout_source(layout_id).source_page
    if source_page is None:
        raise MissionPackError("Battlefield layout source page is required.")
    return source_page


def base_size_source_rows() -> tuple[BaseSizeSourceRecord, ...]:
    return tuple(
        _base_size_source_record(
            record_id=record_id,
            faction_name=faction_name,
            source_section_name=source_section_name,
            unit_name=unit_name,
            source_base_text=base_text,
            source_page=source_page,
        )
        for record_id, source_page, faction_name, source_section_name, unit_name, base_text in (
            event_companion_base_size_rows.BASE_SIZE_SOURCE_ROWS
        )
    )


def _battlefield_layout_row(
    *,
    layout_id: str,
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
    primary_mission_id: str,
    layout_number: int,
) -> chapter_approved.SourceBattlefieldLayoutRow:
    layout_source = _battlefield_layout_source(layout_id)
    return chapter_approved.SourceBattlefieldLayoutRow(
        battlefield_layout_id=layout_id,
        name=layout_source.name,
        player_force_disposition_id=player_force_disposition_id,
        opponent_force_disposition_id=opponent_force_disposition_id,
        layout_number=layout_number,
        primary_mission_id=primary_mission_id,
        deployment_map_id=f"{layout_id}-deployment",
        terrain_layout_id=layout_id,
        battlefield_width_inches=BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=BATTLEFIELD_DEPTH_INCHES,
        coordinate_origin="bottom_left",
        coordinate_orientation="x_right_along_44_inch_edge_y_up_along_60_inch_edge",
        source_status="event_companion_source_hashed_battlefield_artifact",
        objective_markers=_battlefield_objectives(layout_id=layout_id),
        deployment_zones=_battlefield_deployment_zones(layout_id=layout_id),
        terrain_features=(),
    )


def _battlefield_objectives(
    *,
    layout_id: str,
) -> tuple[chapter_approved.SourceBattlefieldObjectiveRow, ...]:
    return tuple(
        chapter_approved.SourceBattlefieldObjectiveRow(
            f"{layout_id}-{suffix}",
            name,
            objective_kind,
            x_inches,
            y_inches,
        )
        for suffix, name, objective_kind, x_inches, y_inches, _terrain_area_suffixes in (
            _battlefield_layout_source(layout_id).objective_terrain_area_specs
        )
    )


def _battlefield_deployment_zones(
    *,
    layout_id: str,
) -> tuple[chapter_approved.SourceBattlefieldDeploymentZoneRow, ...]:
    return deployment_zone_rows_from_specs(
        layout_id=layout_id,
        specs=_battlefield_layout_source(layout_id).deployment_zone_shape_specs,
    )


def _deployment_zone_layout_template_id(
    *,
    layout_id: str,
    layout_number: int,
) -> DeploymentZoneLayoutTemplateId:
    if layout_number not in (1, 2, 3):
        raise MissionPackError("Unsupported battlefield layout number.")
    if _layout_number_from_layout_id(layout_id) != layout_number:
        raise MissionPackError("Battlefield layout number does not match layout ID.")

    force_disposition_pair = _layout_force_disposition_pair_from_layout_id(layout_id)
    template_numbers = _DEPLOYMENT_ZONE_LAYOUT_TEMPLATE_NUMBERS_BY_SOURCE_PAIR.get(
        force_disposition_pair
    )
    if template_numbers is None:
        template_numbers = _DEPLOYMENT_ZONE_LAYOUT_TEMPLATE_NUMBERS_BY_SOURCE_PAIR.get(
            (force_disposition_pair[1], force_disposition_pair[0])
        )
    if template_numbers is None:
        raise MissionPackError("Unsupported deployment-zone layout matchup.")
    return _deployment_zone_layout_template_id_from_number(template_numbers[layout_number - 1])


def _deployment_zone_layout_template_id_from_number(
    template_number: DeploymentZoneLayoutTemplateNumber,
) -> DeploymentZoneLayoutTemplateId:
    if template_number == 1:
        return DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED
    if template_number == 2:
        return DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP
    if template_number == 3:
        return DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT
    if template_number == 4:
        return DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE
    if template_number == 5:
        return DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP
    if template_number == 6:
        return DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE
    raise MissionPackError("Unsupported battlefield layout number.")


def _deployment_zone_template_base_shape(
    template_id: DeploymentZoneLayoutTemplateId,
) -> DeploymentZoneShape:
    if template_id == DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED:
        return _shape_from_vertices(
            (
                (0.0, 0.0),
                (44.0, 0.0),
                (44.0, 12.0),
                (22.0, 12.0),
                (22.0, 20.0),
                (0.0, 20.0),
            )
        )
    if template_id == DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP:
        return DeploymentZoneShape.rectangle(
            min_x=0.0,
            min_y=0.0,
            max_x=12.0,
            max_y=60.0,
        )
    if template_id == DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT:
        return _shape_from_vertices(
            _rectangle_with_quarter_circle_cutout_vertices(
                min_x=0.0,
                min_y=0.0,
                max_x=22.0,
                max_y=30.0,
                corner="upper_right",
                radius=LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
            )
        )
    if template_id == DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE:
        return _shape_from_vertices(
            (
                (0.0, 0.0),
                (8.0, 0.0),
                (8.0, 30.0),
                (14.0, 30.0),
                (14.0, 60.0),
                (0.0, 60.0),
            )
        )
    if template_id == DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP:
        return DeploymentZoneShape.rectangle(
            min_x=0.0,
            min_y=42.0,
            max_x=44.0,
            max_y=60.0,
        )
    if template_id == DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE:
        return _shape_from_vertices(((0.0, 60.0), (44.0, 60.0), (0.0, 30.0)))
    raise MissionPackError("Unsupported deployment-zone layout template.")


def _descriptor_deployment_shapes(
    *,
    layout_id: str,
) -> tuple[EventShapeSourceRecord, ...]:
    return tuple(
        EventShapeSourceRecord(
            shape_id=zone.deployment_zone_id,
            role=zone.player_role,
            polygons=_shape_polygons(zone.shape),
        )
        for zone in _battlefield_deployment_zones(layout_id=layout_id)
    )


def _no_mans_land_shape(*, layout_id: str) -> EventShapeSourceRecord:
    return EventShapeSourceRecord(
        shape_id=f"{layout_id}-no-mans-land",
        role="no_mans_land",
        polygons=_shape_polygons(_battlefield_no_mans_land_shape(layout_id)),
    )


def _territory_shapes(
    *,
    layout_id: str,
) -> tuple[EventShapeSourceRecord, ...]:
    territories = _battlefield_territory_vertices(layout_id)
    return tuple(
        EventShapeSourceRecord(
            shape_id=f"{layout_id}-{role}",
            role=role,
            polygons=(vertices,),
        )
        for role, vertices in territories
    )


def _descriptor_objectives(
    *,
    layout_id: str,
) -> tuple[EventObjectivePointRecord, ...]:
    return tuple(
        EventObjectivePointRecord(
            objective_marker_id=objective.objective_marker_id,
            objective_kind=objective.objective_kind,
            x_inches=objective.x_inches,
            y_inches=objective.y_inches,
        )
        for objective in _battlefield_objectives(layout_id=layout_id)
    )


def _descriptor_terrain(
    *,
    layout_id: str,
) -> tuple[EventTerrainSourceRecord, ...]:
    artifact = event_layouts.battlefield_artifact()
    layout = {candidate.layout_id: candidate for candidate in artifact.layouts}.get(layout_id)
    if layout is None:
        raise MissionPackError("Unsupported battlefield layout ID.")
    archetypes = {archetype.archetype_id: archetype for archetype in artifact.feature_archetypes}
    spans = {
        archetype.archetype_id: (
            max(point.x_inches for point in archetype.rules_footprint_polygon)
            - min(point.x_inches for point in archetype.rules_footprint_polygon),
            max(point.y_inches for point in archetype.rules_footprint_polygon)
            - min(point.y_inches for point in archetype.rules_footprint_polygon),
        )
        for archetype in artifact.feature_archetypes
    }
    return tuple(
        EventTerrainSourceRecord(
            feature_id=component.component_id,
            feature_kind=archetypes[component.archetype_id].feature_kind,
            density=archetypes[component.archetype_id].classification,
            x_inches=component.battlefield_center_x_inches,
            y_inches=component.battlefield_center_y_inches,
            width_inches=spans[component.archetype_id][0],
            depth_inches=spans[component.archetype_id][1],
        )
        for component in layout.terrain_components
    )


def _battlefield_objective_definitions(
    *,
    layout_id: str,
) -> tuple[ObjectiveMarkerDefinition, ...]:
    return tuple(
        ObjectiveMarkerDefinition(
            objective_marker_id=objective.objective_marker_id,
            name=objective.name,
            objective_role=objective_marker_role_from_token(objective.objective_kind),
            x_inches=objective.x_inches,
            y_inches=objective.y_inches,
            source_id=(
                f"{SOURCE_PACKAGE_ID}:battlefield-layout:{layout_id}:"
                f"objective:{objective.objective_marker_id}"
            ),
        )
        for objective in _battlefield_objectives(layout_id=layout_id)
    )


def _battlefield_objective_terrain_area_definitions(
    *,
    layout_id: str,
    objective_markers: tuple[ObjectiveMarkerDefinition, ...],
    terrain_areas: tuple[PlacedTerrainArea, ...],
) -> tuple[ObjectiveTerrainAreaDefinition, ...]:
    layout_source = _battlefield_layout_source(layout_id)
    objective_markers_by_suffix = {
        marker.objective_marker_id.removeprefix(f"{layout_id}-"): marker
        for marker in objective_markers
    }
    terrain_area_ids_by_suffix = {
        area.terrain_area_id.removeprefix(f"{layout_id}-"): area.terrain_area_id
        for area in terrain_areas
    }
    terrain_areas_by_id = {area.terrain_area_id: area for area in terrain_areas}
    terrain_area_ids_by_logical_id: dict[str, list[str]] = {}
    for area in terrain_areas:
        terrain_area_ids_by_logical_id.setdefault(area.logical_terrain_area_id, []).append(
            area.terrain_area_id
        )
    objective_terrain_areas: list[ObjectiveTerrainAreaDefinition] = []
    for (
        objective_suffix,
        _name,
        _objective_kind,
        _x_inches,
        _y_inches,
        terrain_area_suffixes,
    ) in layout_source.objective_terrain_area_specs:
        if not terrain_area_suffixes:
            continue
        marker = objective_markers_by_suffix.get(objective_suffix)
        if marker is None:
            raise MissionPackError("Objective terrain area spec references unknown objective.")
        logical_terrain_area_ids: set[str] = set()
        for terrain_area_suffix in terrain_area_suffixes:
            terrain_area_id = terrain_area_ids_by_suffix.get(terrain_area_suffix)
            if terrain_area_id is None:
                raise MissionPackError(
                    "Objective terrain area spec references unknown terrain area."
                )
            logical_terrain_area_ids.add(
                terrain_areas_by_id[terrain_area_id].logical_terrain_area_id
            )
        terrain_area_ids = tuple(
            sorted(
                terrain_area_id
                for logical_terrain_area_id in logical_terrain_area_ids
                for terrain_area_id in terrain_area_ids_by_logical_id[logical_terrain_area_id]
            )
        )
        objective_terrain_areas.append(
            ObjectiveTerrainAreaDefinition(
                objective_marker_id=marker.objective_marker_id,
                objective_role=marker.objective_role,
                terrain_area_ids=terrain_area_ids,
                source_id=(
                    f"{SOURCE_PACKAGE_ID}:battlefield-layout:{layout_source.source_layout_id}:"
                    f"objective-terrain-area:{objective_suffix}"
                ),
            )
        )
    return tuple(objective_terrain_areas)


def _battlefield_regions(*, layout_id: str) -> tuple[BattlefieldRegion, ...]:
    attacker_zone, defender_zone = _battlefield_deployment_zones(layout_id=layout_id)
    source_layout_id = _battlefield_layout_source(layout_id).source_layout_id
    layout_number = _layout_number_from_layout_id(layout_id)
    attacker_edge = _layout_attacker_edge(layout_id, layout_number)
    defender_edge = _layout_defender_edge(layout_id, layout_number)
    territories = dict(_battlefield_territory_vertices(layout_id))
    return (
        BattlefieldRegion(
            region_id=f"{layout_id}-attacker-deployment-region",
            region_kind=BattlefieldRegionKind.DEPLOYMENT_ZONE,
            owner_role="attacker",
            shape=attacker_zone.shape,
            derived_from=(attacker_zone.deployment_zone_id,),
            source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:region:attacker-deployment",
        ),
        BattlefieldRegion(
            region_id=f"{layout_id}-defender-deployment-region",
            region_kind=BattlefieldRegionKind.DEPLOYMENT_ZONE,
            owner_role="defender",
            shape=defender_zone.shape,
            derived_from=(defender_zone.deployment_zone_id,),
            source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:region:defender-deployment",
        ),
        BattlefieldRegion(
            region_id=f"{layout_id}-no-mans-land",
            region_kind=BattlefieldRegionKind.NO_MANS_LAND,
            owner_role=None,
            shape=_battlefield_no_mans_land_shape(layout_id),
            derived_from=(attacker_zone.deployment_zone_id, defender_zone.deployment_zone_id),
            source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:region:no-mans-land",
        ),
        BattlefieldRegion(
            region_id=f"{layout_id}-attacker-territory",
            region_kind=BattlefieldRegionKind.TERRITORY,
            owner_role="attacker",
            shape=_shape_from_vertices(territories["attacker_territory"]),
            derived_from=(f"attacker_edge_{attacker_edge}",),
            source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:region:attacker-territory",
        ),
        BattlefieldRegion(
            region_id=f"{layout_id}-defender-territory",
            region_kind=BattlefieldRegionKind.TERRITORY,
            owner_role="defender",
            shape=_shape_from_vertices(territories["defender_territory"]),
            derived_from=(f"defender_edge_{defender_edge}",),
            source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:region:defender-territory",
        ),
    )


def _battlefield_no_mans_land_shape(layout_id: str) -> DeploymentZoneShape:
    source = _battlefield_layout_source(layout_id)
    return event_no_mans_land_shape(
        explicit_polygons=source.no_mans_land_shape_polygons,
    )


def _battlefield_territory_vertices(
    layout_id: str,
) -> tuple[tuple[str, tuple[tuple[float, float], ...]], ...]:
    return event_territory_vertices(
        explicit_specs=_battlefield_layout_source(layout_id).territory_shape_specs,
    )


def _battlefield_terrain_areas(
    layout_id: str,
) -> tuple[PlacedTerrainArea, ...]:
    layout_source = _battlefield_layout_source(layout_id)
    return _placed_terrain_areas_from_specs(
        layout_id=layout_id,
        source_layout_id=layout_source.source_layout_id,
        explicit_specs=layout_source.terrain_area_specs,
        mirrored_pairs=layout_source.terrain_area_mirror_pairs,
        local_transform_specs=layout_source.terrain_area_local_transform_specs,
        classification_specs=layout_source.terrain_area_classification_specs,
        group_specs=layout_source.terrain_area_group_specs,
    )


def _terrain_feature_area_placements(
    *,
    layout_id: str,
    terrain_areas: tuple[PlacedTerrainArea, ...],
) -> tuple[TerrainFeatureAreaPlacement, ...]:
    layout_source = _battlefield_layout_source(layout_id)
    if not layout_source.terrain_feature_placement_specs:
        raise MissionPackError(
            "Event Companion battlefield layout requires explicit terrain component placements."
        )
    return terrain_feature_placements_from_specs(
        layout_id=layout_id,
        source_layout_id=layout_source.source_layout_id,
        source_package_id=SOURCE_PACKAGE_ID,
        terrain_areas=terrain_areas,
        specs=layout_source.terrain_feature_placement_specs,
    )


def _placed_terrain_areas_from_specs(
    *,
    layout_id: str,
    source_layout_id: str,
    explicit_specs: tuple[event_layouts.EventTerrainAreaSpec, ...],
    mirrored_pairs: tuple[event_layouts.EventTerrainAreaMirrorPair, ...],
    local_transform_specs: tuple[event_layouts.EventTerrainAreaLocalTransformSpec, ...],
    classification_specs: tuple[event_layouts.EventTerrainAreaClassificationSpec, ...],
    group_specs: tuple[event_layouts.EventTerrainAreaGroupSpec, ...],
) -> tuple[PlacedTerrainArea, ...]:
    templates = {
        template.footprint_template_id: template for template in terrain_area_footprint_templates()
    }
    local_transforms_by_area_id = _terrain_area_local_transforms_by_area_id(
        explicit_specs=explicit_specs,
        local_transform_specs=local_transform_specs,
    )
    classifications_by_area_id = terrain_area_classifications_by_suffix(
        explicit_specs=explicit_specs,
        classification_specs=classification_specs,
    )
    all_area_suffixes = tuple(area_id for area_id, *_rest in explicit_specs) + tuple(
        target_suffix for _source_suffix, target_suffix in mirrored_pairs
    )
    logical_group_ids_by_area_id = terrain_area_group_ids_by_suffix(
        area_suffixes=all_area_suffixes,
        group_specs=group_specs,
    )
    explicit_areas = tuple(
        _placed_terrain_area_from_anchor_spec(
            layout_id=layout_id,
            source_layout_id=source_layout_id,
            area_id=area_id,
            template=templates[template_id],
            anchor_x_inches=anchor_x,
            anchor_y_inches=anchor_y,
            rotation_degrees=rotation,
            local_transform=local_transforms_by_area_id[area_id],
            classification=classifications_by_area_id[area_id],
            logical_terrain_area_id=logical_group_ids_by_area_id[area_id],
        )
        for area_id, template_id, anchor_x, anchor_y, rotation in explicit_specs
    )
    explicit_by_suffix = {
        area.terrain_area_id.removeprefix(f"{layout_id}-"): area for area in explicit_areas
    }
    mirrored = tuple(
        mirror_placed_terrain_area(
            explicit_by_suffix[source_suffix],
            battlefield_width_inches=BATTLEFIELD_WIDTH_INCHES,
            battlefield_depth_inches=BATTLEFIELD_DEPTH_INCHES,
            terrain_area_id=f"{layout_id}-{target_suffix}",
            source_id=(
                f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:"
                f"terrain-area:{target_suffix}"
            ),
            symmetry_axis=SymmetryAxis.POINT_CENTER,
            logical_terrain_area_id=(f"{layout_id}-{logical_group_ids_by_area_id[target_suffix]}"),
        )
        for source_suffix, target_suffix in mirrored_pairs
    )
    return tuple(sorted((*explicit_areas, *mirrored), key=lambda area: area.terrain_area_id))


def _terrain_area_local_transforms_by_area_id(
    *,
    explicit_specs: tuple[event_layouts.EventTerrainAreaSpec, ...],
    local_transform_specs: tuple[event_layouts.EventTerrainAreaLocalTransformSpec, ...],
) -> dict[str, TerrainAreaLocalTransform]:
    explicit_area_ids = tuple(area_id for area_id, *_ in explicit_specs)
    local_transforms: dict[str, TerrainAreaLocalTransform] = {}
    for area_id in explicit_area_ids:
        local_transforms[area_id] = TerrainAreaLocalTransform.IDENTITY
    for area_id, local_transform_token in local_transform_specs:
        if area_id not in local_transforms:
            raise MissionPackError("Terrain area local transform references unknown area ID.")
        if local_transforms[area_id] is not TerrainAreaLocalTransform.IDENTITY:
            raise MissionPackError("Terrain area local transform must not duplicate area IDs.")
        local_transform = terrain_area_local_transform_from_token(local_transform_token)
        local_transforms[area_id] = local_transform
    return local_transforms


def _placed_terrain_area_from_anchor_spec(
    *,
    layout_id: str,
    source_layout_id: str,
    area_id: str,
    template: TerrainAreaFootprintTemplate,
    anchor_x_inches: float,
    anchor_y_inches: float,
    rotation_degrees: float,
    local_transform: TerrainAreaLocalTransform,
    classification: TerrainAreaClassification,
    logical_terrain_area_id: str,
) -> PlacedTerrainArea:
    center_x, center_y = _terrain_area_center_from_anchor(
        template,
        anchor_x_inches=anchor_x_inches,
        anchor_y_inches=anchor_y_inches,
        rotation_degrees=rotation_degrees,
    )
    return PlacedTerrainArea.from_template(
        terrain_area_id=f"{layout_id}-{area_id}",
        template=template,
        terrain_feature_kind=TERRAIN_AREA_FEATURE_KIND,
        classification=classification,
        center_x_inches=center_x,
        center_y_inches=center_y,
        rotation_degrees=rotation_degrees,
        local_transform=local_transform,
        source_layout_id=source_layout_id,
        source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{source_layout_id}:terrain-area:{area_id}",
        logical_terrain_area_id=f"{layout_id}-{logical_terrain_area_id}",
    )


def _terrain_area_center_from_anchor(
    template: TerrainAreaFootprintTemplate,
    *,
    anchor_x_inches: float,
    anchor_y_inches: float,
    rotation_degrees: float,
) -> tuple[float, float]:
    anchor_local_point = template.polygon_vertices_inches[0]
    rotated_anchor_point = rotate_point(anchor_local_point, rotation_degrees)
    return (
        anchor_x_inches - rotated_anchor_point.x_inches,
        anchor_y_inches - rotated_anchor_point.y_inches,
    )


def _footprint_template(
    *,
    template_id: str,
    name: str,
    width: float,
    depth: float,
    vertices: tuple[tuple[float, float], ...],
    source_id: str,
) -> TerrainAreaFootprintTemplate:
    return TerrainAreaFootprintTemplate(
        footprint_template_id=template_id,
        name=name,
        bounding_width_inches=width,
        bounding_depth_inches=depth,
        polygon_vertices_inches=tuple(
            TerrainDisplayPoint(x_inches=x, y_inches=y) for x, y in vertices
        ),
        source_id=f"{source_id}:{template_id.lower()}",
    )


def _shape_from_vertices(vertices: tuple[tuple[float, float], ...]) -> DeploymentZoneShape:
    return _shape_from_polygons((vertices,))


def _shape_from_polygons(
    polygons: tuple[tuple[tuple[float, float], ...], ...],
) -> DeploymentZoneShape:
    return DeploymentZoneShape(
        polygons=tuple(
            DeploymentZonePolygon(
                vertices=tuple(DeploymentZonePoint(x=x, y=y) for x, y in vertices)
            )
            for vertices in polygons
        )
    )


def _rectangle_with_quarter_circle_cutout_vertices(
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    corner: str,
    radius: float,
) -> tuple[tuple[float, float], ...]:
    if corner == "lower_right":
        return (
            (min_x, min_y),
            *_arc_points(
                center_x=max_x,
                center_y=min_y,
                radius=radius,
                start_degrees=180.0,
                end_degrees=90.0,
            ),
            (max_x, max_y),
            (min_x, max_y),
        )
    if corner == "upper_left":
        return (
            (min_x, min_y),
            (max_x, min_y),
            (max_x, max_y),
            *_arc_points(
                center_x=min_x,
                center_y=max_y,
                radius=radius,
                start_degrees=0.0,
                end_degrees=-90.0,
            ),
        )
    if corner == "upper_right":
        return (
            (min_x, min_y),
            (max_x, min_y),
            *_arc_points(
                center_x=max_x,
                center_y=max_y,
                radius=radius,
                start_degrees=-90.0,
                end_degrees=-180.0,
            ),
            (min_x, max_y),
        )
    raise MissionPackError("Unsupported quarter-circle cutout corner.")


def _arc_points(
    *,
    center_x: float,
    center_y: float,
    radius: float,
    start_degrees: float,
    end_degrees: float,
) -> tuple[tuple[float, float], ...]:
    return tuple(
        (
            round(center_x + radius * math.cos(math.radians(degrees)), 6),
            round(center_y + radius * math.sin(math.radians(degrees)), 6),
        )
        for degrees in (
            start_degrees + (end_degrees - start_degrees) * index / LAYOUT_C_ARC_SEGMENTS
            for index in range(LAYOUT_C_ARC_SEGMENTS + 1)
        )
    )


def _layout_battlefield_width(layout_id: str) -> float:
    return BATTLEFIELD_WIDTH_INCHES


def _layout_battlefield_depth(layout_id: str) -> float:
    return BATTLEFIELD_DEPTH_INCHES


def _layout_attacker_edge(layout_id: str, layout_number: int) -> str:
    template_id = _deployment_zone_layout_template_id(
        layout_id=layout_id,
        layout_number=layout_number,
    )
    return _deployment_zone_layout_edges(template_id)[0]


def _layout_defender_edge(layout_id: str, layout_number: int) -> str:
    template_id = _deployment_zone_layout_template_id(
        layout_id=layout_id,
        layout_number=layout_number,
    )
    return _deployment_zone_layout_edges(template_id)[1]


def _deployment_zone_layout_edges(template_id: DeploymentZoneLayoutTemplateId) -> tuple[str, str]:
    if template_id == DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED:
        return "north", "south"
    if template_id == DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP:
        return "west", "east"
    if template_id == DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT:
        return "west", "east"
    if template_id == DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE:
        return "west", "east"
    if template_id == DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP:
        return "north", "south"
    if template_id == DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE:
        return "north_west_corner", "south_east_corner"
    raise MissionPackError("Unsupported deployment-zone layout template.")


def _layout_geometry_status(layout_id: str) -> str:
    if layout_id not in event_layouts.BATTLEFIELD_LAYOUT_IDS:
        raise MissionPackError("Unsupported battlefield layout ID.")
    return "source_hashed_battlefield_artifact_geometry"


def _layout_number_from_layout_id(layout_id: str) -> int:
    suffix = layout_id.rsplit("-", maxsplit=1)[-1]
    if suffix not in {"1", "2", "3"}:
        raise MissionPackError("Battlefield layout ID must end in layout number.")
    return int(suffix)


def _layout_force_disposition_pair_from_layout_id(layout_id: str) -> tuple[str, str]:
    pair_id = layout_id.rsplit("-layout-", maxsplit=1)[0]
    first_id, separator, second_id = pair_id.partition("-vs-")
    if separator == "" or first_id == "" or second_id == "":
        raise MissionPackError("Battlefield layout ID must include force disposition pair.")
    return (first_id, second_id)


def _shape_polygons(shape: DeploymentZoneShape) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple((point.x, point.y) for point in polygon.vertices) for polygon in shape.polygons
    )


def _base_size_source_record(
    *,
    record_id: str,
    faction_name: str,
    source_section_name: str | None,
    unit_name: str,
    source_base_text: str,
    source_page: int,
) -> BaseSizeSourceRecord:
    base_source_kind, status, base_size = _base_source_kind_and_geometry(source_base_text)
    return BaseSizeSourceRecord(
        record_id=record_id,
        faction_name=faction_name,
        source_section_name=source_section_name,
        unit_name=unit_name,
        source_base_text=source_base_text,
        base_source_kind=base_source_kind,
        geometry_resolution_status=status,
        canonical_base_size=base_size,
        source_page=source_page,
        source_id=f"{SOURCE_PACKAGE_ID}:base-size:{record_id}",
    )


def _base_source_kind_and_geometry(
    base_text: str,
) -> tuple[str, GeometryResolutionStatus, BaseSizeDefinition | None]:
    if base_text == "Hull":
        return (
            "hull",
            GeometryResolutionStatus.REQUIRES_PROJECT_GEOMETRY_OVERRIDE,
            None,
        )
    if base_text == "Unique":
        return (
            "unique",
            GeometryResolutionStatus.REQUIRES_EVENT_ORGANIZER_OVERRIDE,
            None,
        )
    if base_text == "Small Flying Base":
        return (
            "small_flying_base",
            GeometryResolutionStatus.REQUIRES_PROJECT_GEOMETRY_OVERRIDE,
            None,
        )
    if base_text == "Large Flying Base":
        return (
            "large_flying_base",
            GeometryResolutionStatus.REQUIRES_PROJECT_GEOMETRY_OVERRIDE,
            None,
        )
    if base_text == "Use model":
        return (
            "use_model",
            GeometryResolutionStatus.REQUIRES_PROJECT_GEOMETRY_OVERRIDE,
            None,
        )
    if base_text == "No official base size":
        return (
            "no_official_base_size",
            GeometryResolutionStatus.UNSUPPORTED_FOR_PHYSICAL_GEOMETRY,
            None,
        )
    if base_text.endswith(" Oval Base"):
        dimensions = base_text.removesuffix(" Oval Base").removesuffix("mm")
        length_text, width_text = dimensions.split("x")
        return (
            "oval",
            GeometryResolutionStatus.CANONICAL_GEOMETRY_AVAILABLE,
            BaseSizeDefinition.oval(length_mm=float(length_text), width_mm=float(width_text)),
        )
    if base_text.endswith("mm"):
        return (
            "round",
            GeometryResolutionStatus.CANONICAL_GEOMETRY_AVAILABLE,
            BaseSizeDefinition.circular(float(base_text.removesuffix("mm"))),
        )
    return (
        "unresolved_source_shape",
        GeometryResolutionStatus.UNSUPPORTED_FOR_PHYSICAL_GEOMETRY,
        None,
    )


def _event_matrix_source_row(
    *,
    source_left_force_disposition_id: str,
    source_right_force_disposition_id: str,
    source_left_primary_mission_id: str,
    source_left_primary_mission_name: str,
    source_right_primary_mission_id: str,
    source_right_primary_mission_name: str,
    layout_source_page_start: int,
) -> EventPrimaryMissionMatrixSourceRow:
    layout_pair_id = f"{source_left_force_disposition_id}-vs-{source_right_force_disposition_id}"
    return EventPrimaryMissionMatrixSourceRow(
        source_left_force_disposition_id=source_left_force_disposition_id,
        source_right_force_disposition_id=source_right_force_disposition_id,
        source_left_primary_mission_id=source_left_primary_mission_id,
        source_left_primary_mission_name=source_left_primary_mission_name,
        source_right_primary_mission_id=source_right_primary_mission_id,
        source_right_primary_mission_name=source_right_primary_mission_name,
        layout_pair_id=layout_pair_id,
        layout_source_page_start=layout_source_page_start,
        source_id=f"{SOURCE_PACKAGE_ID}:primary-mission-matrix-source:{layout_pair_id}",
    )


def _matrix_cell_from_event_source_row(
    source_row: EventPrimaryMissionMatrixSourceRow,
    *,
    use_left: bool,
) -> chapter_approved.SourcePrimaryMissionMatrixCellRow:
    if use_left:
        player_force_disposition_id = source_row.source_left_force_disposition_id
        opponent_force_disposition_id = source_row.source_right_force_disposition_id
        primary_mission_id = source_row.source_left_primary_mission_id
        primary_mission_name = source_row.source_left_primary_mission_name
    else:
        player_force_disposition_id = source_row.source_right_force_disposition_id
        opponent_force_disposition_id = source_row.source_left_force_disposition_id
        primary_mission_id = source_row.source_right_primary_mission_id
        primary_mission_name = source_row.source_right_primary_mission_name
    return chapter_approved.SourcePrimaryMissionMatrixCellRow(
        player_force_disposition_id=player_force_disposition_id,
        opponent_force_disposition_id=opponent_force_disposition_id,
        primary_mission_id=primary_mission_id,
        primary_mission_name=primary_mission_name,
        battlefield_layout_ids=(
            f"{source_row.layout_pair_id}-layout-1",
            f"{source_row.layout_pair_id}-layout-2",
            f"{source_row.layout_pair_id}-layout-3",
        ),
        source_status="implemented",
    )


def _event_primary_mission_names() -> tuple[tuple[str, str], ...]:
    seen: dict[str, str] = {}
    for row in event_primary_mission_matrix_source_rows():
        seen[row.source_left_primary_mission_id] = row.source_left_primary_mission_name
        seen[row.source_right_primary_mission_id] = row.source_right_primary_mission_name
    return tuple(sorted(seen.items()))


_LAYOUT_SOURCE_PAGES: tuple[tuple[str, str, int], ...] = tuple(
    (
        row.source_left_force_disposition_id,
        row.source_right_force_disposition_id,
        row.layout_source_page_start,
    )
    for row in event_primary_mission_matrix_source_rows()
)


def _matrix_row(
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
) -> chapter_approved.SourcePrimaryMissionMatrixCellRow:
    for row in primary_mission_matrix_rows():
        if (
            row.player_force_disposition_id == player_force_disposition_id
            and row.opponent_force_disposition_id == opponent_force_disposition_id
        ):
            return row
    raise MissionPackError("Event Companion matrix row was not found.")


def _import_hash() -> str:
    payload = {
        "package_identity": package_identity().to_payload(),
        "mission_sequence": mission_sequence_descriptor().to_payload(),
        "primary_missions": [row.to_payload() for row in primary_mission_rows()],
        "primary_scoring_artifact_hashes": {
            "all-primary-missions-actions-state-and-choice-rules": PRIMARY_SCORING_PACKAGE_HASH,
        },
        "primary_mission_action_sources": [
            row.to_payload() for row in primary_mission_action_source_rows()
        ],
        "primary_mission_scoring_coverage": [
            row.to_payload() for row in primary_mission_scoring_coverage_rows()
        ],
        "secondary_missions": [row.to_payload() for row in secondary_mission_rows()],
        "force_dispositions": [row.to_payload() for row in force_disposition_rows()],
        "matrix": [row.to_payload() for row in primary_mission_matrix_rows()],
        "layouts": [row.to_payload() for row in battlefield_layout_rows()],
        "layout_descriptors": [row.to_payload() for row in layout_descriptor_rows()],
        "terrain_area_footprint_templates": [
            template.to_payload() for template in terrain_area_footprint_templates()
        ],
        "terrain_feature_presets": [preset.to_payload() for preset in terrain_feature_presets()],
        "battlefield_layout_definitions": [
            layout.to_payload() for layout in battlefield_layout_definitions()
        ],
        "scoring": mission_pack_scoring_row().to_payload(),
        "tactical_secondary": tactical_secondary_procedure().to_payload(),
        "fixed_secondary": fixed_secondary_procedure().to_payload(),
        "card_amendments": card_amendment_set().to_payload(),
        "base_sizes": [row.to_payload() for row in base_size_source_rows()],
        "schema": IMPORTED_AT_SCHEMA_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
