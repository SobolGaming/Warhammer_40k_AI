from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import StrEnum

from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.deployment_zones import DeploymentZoneShape
from warhammer40k_core.core.missions import MissionPackError, MissionSourcePackageDefinition
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry, TerrainDisplayPoint
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as chapter_approved,
)

EDITION_ID = "warhammer_40000_11th"
MISSION_PACK_ID = "11e-warhammer-event-companion-2026-06"
SOURCE_PACKAGE_ID = "gw-11e-warhammer-event-companion-v1-0-2026-06"
SOURCE_TITLE = "Warhammer Event Companion v1.0"
SOURCE_VERSION = "1.0"
DOCUMENT_VERSION = "1.0"
SOURCE_KIND = "warhammer_event_companion"
EVENT_MODE = "warhammer_event"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-event-companion-source-v1"
BATTLEFIELD_WIDTH_INCHES = 60.0
BATTLEFIELD_DEPTH_INCHES = 44.0
BATTLEFIELD_SIZE = "44x60_inches"


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
class MissionCardScoringGrammar:
    grammar_id: str
    supported_tokens: tuple[str, ...]
    source_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "grammar_id": self.grammar_id,
            "supported_tokens": list(self.supported_tokens),
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
class EventPolygonSourceRecord:
    polygon_id: str
    role: str
    vertices: tuple[tuple[float, float], ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "polygon_id": self.polygon_id,
            "role": self.role,
            "vertices": [[x, y] for x, y in self.vertices],
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
    deployment_zone_polygons: tuple[EventPolygonSourceRecord, ...]
    no_mans_land_polygon: EventPolygonSourceRecord
    player_territory_polygons: tuple[EventPolygonSourceRecord, ...]
    objective_points: tuple[EventObjectivePointRecord, ...]
    terrain_features: tuple[EventTerrainSourceRecord, ...]
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
            "deployment_zone_polygons": [
                polygon.to_payload() for polygon in self.deployment_zone_polygons
            ],
            "no_mans_land_polygon": self.no_mans_land_polygon.to_payload(),
            "player_territory_polygons": [
                polygon.to_payload() for polygon in self.player_territory_polygons
            ],
            "objective_points": [objective.to_payload() for objective in self.objective_points],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
            "source_page": self.source_page,
            "source_id": self.source_id,
        }


@dataclass(frozen=True, slots=True)
class BaseSizeSourceRecord:
    record_id: str
    faction_name: str
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
    return MissionSourcePackageDefinition(
        edition_id=EDITION_ID,
        mission_pack_id=MISSION_PACK_ID,
        source_package_id=SOURCE_PACKAGE_ID,
        source_title=SOURCE_TITLE,
        source_version=SOURCE_VERSION,
        source_commit_or_import_hash=_import_hash(),
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
        source_id=f"{SOURCE_PACKAGE_ID}:mission-card-scoring-grammar",
    )


def card_amendment_set() -> CardAmendmentSet:
    return CardAmendmentSet(
        amendment_set_id="event-companion-v1-card-amendments",
        amendments=(),
        source_page=4,
        source_id=f"{SOURCE_PACKAGE_ID}:card-amendments",
    )


def primary_mission_rows() -> tuple[chapter_approved.SourcePrimaryMissionRow, ...]:
    implemented_rows = {
        row.primary_mission_id: row for row in chapter_approved.primary_mission_rows()
    }
    rows: list[chapter_approved.SourcePrimaryMissionRow] = []
    for mission_id, mission_name in _event_primary_mission_names():
        existing_row = implemented_rows.get(mission_id)
        if existing_row is not None:
            rows.append(existing_row)
            continue
        rows.append(
            chapter_approved.SourcePrimaryMissionRow(
                primary_mission_id=mission_id,
                name=mission_name,
                max_vp_per_turn=15,
                scoring_kind="event_companion_primary_descriptor",
                vp_per_controlled_objective=None,
                scoring_rules=(
                    chapter_approved.SourceScoringRuleRow(
                        rule_id=f"{mission_id}-event-primary",
                        timing="command_phase",
                        source_kind="event_primary_descriptor",
                        victory_points=1,
                        cap=15,
                        condition=f"{mission_id}-source_condition",
                    ),
                ),
            )
        )
    return tuple(rows)


def secondary_mission_rows() -> tuple[chapter_approved.SourceSecondaryMissionRow, ...]:
    return chapter_approved.secondary_mission_rows()


def force_disposition_rows() -> tuple[chapter_approved.SourceForceDispositionRow, ...]:
    return chapter_approved.force_disposition_rows()


def primary_mission_matrix_rows() -> tuple[chapter_approved.SourcePrimaryMissionMatrixCellRow, ...]:
    return tuple(
        chapter_approved.SourcePrimaryMissionMatrixCellRow(
            player_force_disposition_id=row.player_force_disposition_id,
            opponent_force_disposition_id=row.opponent_force_disposition_id,
            primary_mission_id=row.primary_mission_id,
            primary_mission_name=row.primary_mission_name,
            battlefield_layout_ids=row.battlefield_layout_ids,
            source_status="implemented",
        )
        for row in chapter_approved.primary_mission_matrix_rows()
    )


def mission_action_rows() -> tuple[chapter_approved.SourceMissionActionRow, ...]:
    return chapter_approved.mission_action_rows()


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


def battlefield_layout_rows() -> tuple[chapter_approved.SourceBattlefieldLayoutRow, ...]:
    rows: list[chapter_approved.SourceBattlefieldLayoutRow] = []
    for pair_index, (first_id, second_id) in enumerate(_layout_disposition_pairs()):
        matrix_row = _matrix_row(first_id, second_id)
        for layout_number in (1, 2, 3):
            layout_id = f"{first_id}-vs-{second_id}-layout-{layout_number}"
            rows.append(
                _battlefield_layout_row(
                    layout_id=layout_id,
                    name=(
                        f"{_force_disposition_name(first_id)} vs "
                        f"{_force_disposition_name(second_id)} {layout_number}"
                    ),
                    player_force_disposition_id=first_id,
                    opponent_force_disposition_id=second_id,
                    primary_mission_id=matrix_row.primary_mission_id,
                    layout_number=layout_number,
                    source_page=9 + (pair_index * 3) + layout_number - 1,
                )
            )
    return tuple(rows)


def layout_descriptor_rows() -> tuple[WarhammerEventLayoutDescriptor, ...]:
    descriptors: list[WarhammerEventLayoutDescriptor] = []
    for pair_index, (first_id, second_id) in enumerate(_layout_disposition_pairs()):
        player_primary = _matrix_row(first_id, second_id).primary_mission_id
        opponent_primary = _matrix_row(second_id, first_id).primary_mission_id
        for layout_number in (1, 2, 3):
            layout_id = f"{first_id}-vs-{second_id}-layout-{layout_number}"
            source_page = 9 + (pair_index * 3) + layout_number - 1
            descriptors.append(
                WarhammerEventLayoutDescriptor(
                    layout_id=layout_id,
                    player_force_disposition_id=first_id,
                    opponent_force_disposition_id=second_id,
                    player_primary_mission_id=player_primary,
                    opponent_primary_mission_id=opponent_primary,
                    layout_variant=("a", "b", "c")[layout_number - 1],
                    battlefield_width_inches=BATTLEFIELD_WIDTH_INCHES,
                    battlefield_depth_inches=BATTLEFIELD_DEPTH_INCHES,
                    attacker_edge=_attacker_edge(layout_number),
                    defender_edge=_defender_edge(layout_number),
                    deployment_zone_polygons=_descriptor_deployment_polygons(
                        layout_id=layout_id,
                        layout_number=layout_number,
                    ),
                    no_mans_land_polygon=_no_mans_land_polygon(
                        layout_id=layout_id,
                        layout_number=layout_number,
                    ),
                    player_territory_polygons=_territory_polygons(
                        layout_id=layout_id,
                        layout_number=layout_number,
                    ),
                    objective_points=_descriptor_objectives(
                        layout_id=layout_id,
                        layout_number=layout_number,
                    ),
                    terrain_features=_descriptor_terrain(
                        layout_id=layout_id,
                        layout_number=layout_number,
                    ),
                    source_page=source_page,
                    source_id=f"{SOURCE_PACKAGE_ID}:battlefield-layout:{layout_id}:descriptor",
                )
            )
    return tuple(descriptors)


def base_size_source_rows() -> tuple[BaseSizeSourceRecord, ...]:
    rows = (
        (
            "adepta-sororitas-battle-sisters-squad",
            "Adepta Sororitas",
            "Battle Sisters Squad",
            "32mm",
            55,
        ),
        (
            "adepta-sororitas-triumph-of-saint-katherine",
            "Adepta Sororitas",
            "Triumph of Saint Katherine",
            "120x92mm Oval Base",
            55,
        ),
        ("adepta-sororitas-castigator", "Adepta Sororitas", "Castigator", "Hull", 55),
        ("aeldari-falcon", "Aeldari", "Falcon", "Large Flying Base", 59),
        ("aeldari-farseer-skyrunner", "Aeldari", "Farseer Skyrunner", "Small Flying Base", 59),
        ("space-marines-intercessor-squad", "Space Marines", "Intercessor Squad", "32mm", 85),
        ("space-marines-land-speeder", "Space Marines", "Land Speeder", "105x70mm Oval Base", 85),
        ("space-marines-vindicator", "Space Marines", "Vindicator", "Hull", 86),
        ("space-marines-thunderhawk-gunship", "Space Marines", "Thunderhawk Gunship", "Unique", 86),
        ("world-eaters-angron", "World Eaters", "Angron", "100mm", 93),
    )
    return tuple(
        _base_size_source_record(
            record_id=record_id,
            faction_name=faction_name,
            unit_name=unit_name,
            source_base_text=base_text,
            source_page=source_page,
        )
        for record_id, faction_name, unit_name, base_text, source_page in rows
    )


def _battlefield_layout_row(
    *,
    layout_id: str,
    name: str,
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
    primary_mission_id: str,
    layout_number: int,
    source_page: int,
) -> chapter_approved.SourceBattlefieldLayoutRow:
    return chapter_approved.SourceBattlefieldLayoutRow(
        battlefield_layout_id=layout_id,
        name=name,
        player_force_disposition_id=player_force_disposition_id,
        opponent_force_disposition_id=opponent_force_disposition_id,
        layout_number=layout_number,
        primary_mission_id=primary_mission_id,
        deployment_map_id=f"{layout_id}-deployment",
        terrain_layout_id=layout_id,
        battlefield_width_inches=BATTLEFIELD_WIDTH_INCHES,
        battlefield_depth_inches=BATTLEFIELD_DEPTH_INCHES,
        coordinate_origin="top_left",
        coordinate_orientation="x_right_along_60_inch_edge_y_down_along_44_inch_edge",
        source_status=f"event_companion_page_{source_page}_coordinate_record",
        objective_markers=_layout_objectives(layout_id=layout_id, layout_number=layout_number),
        deployment_zones=_layout_deployment_zones(
            layout_id=layout_id,
            layout_number=layout_number,
        ),
        terrain_features=_layout_terrain_features(
            layout_id=layout_id,
            layout_number=layout_number,
        ),
    )


def _layout_objectives(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[chapter_approved.SourceBattlefieldObjectiveRow, ...]:
    template = {
        1: (
            (9.0, 22.0, "attacker_home"),
            (51.0, 22.0, "defender_home"),
            (30.0, 22.0, "center"),
            (24.0, 10.0, "central"),
            (36.0, 34.0, "central"),
        ),
        2: (
            (10.0, 10.0, "attacker_home"),
            (50.0, 34.0, "defender_home"),
            (30.0, 22.0, "center"),
            (18.0, 30.0, "central"),
            (42.0, 14.0, "central"),
        ),
        3: (
            (9.5, 10.5, "attacker_home"),
            (52.5, 34.5, "defender_home"),
            (28.5, 8.5, "central"),
            (30.0, 22.0, "center"),
            (28.5, 35.5, "central"),
        ),
    }[layout_number]
    return tuple(
        chapter_approved.SourceBattlefieldObjectiveRow(
            objective_marker_id=f"{layout_id}-objective-{index}-{kind}",
            name=_title_from_slug(kind),
            objective_kind=kind,
            x_inches=x,
            y_inches=y,
        )
        for index, (x, y, kind) in enumerate(template, start=1)
    )


def _layout_deployment_zones(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[chapter_approved.SourceBattlefieldDeploymentZoneRow, ...]:
    if layout_number == 2:
        attacker = DeploymentZoneShape.rectangle(min_x=0.0, min_y=0.0, max_x=18.0, max_y=18.0)
        defender = DeploymentZoneShape.rectangle(min_x=42.0, min_y=26.0, max_x=60.0, max_y=44.0)
    else:
        attacker = DeploymentZoneShape.rectangle(min_x=0.0, min_y=0.0, max_x=18.0, max_y=44.0)
        defender = DeploymentZoneShape.rectangle(min_x=42.0, min_y=0.0, max_x=60.0, max_y=44.0)
    return (
        chapter_approved.SourceBattlefieldDeploymentZoneRow(
            deployment_zone_id=f"{layout_id}-attacker",
            player_role="attacker",
            shape=attacker,
        ),
        chapter_approved.SourceBattlefieldDeploymentZoneRow(
            deployment_zone_id=f"{layout_id}-defender",
            player_role="defender",
            shape=defender,
        ),
    )


def _layout_terrain_features(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[chapter_approved.SourceBattlefieldTerrainFeatureRow, ...]:
    templates = {
        1: (
            ("attacker-home-ruin", "ruins", 10.0, 22.0, 8.0, 14.0, "dense"),
            ("defender-home-ruin", "ruins", 50.0, 22.0, 8.0, 14.0, "dense"),
            ("midfield-north-ruin", "ruins", 29.0, 9.0, 9.0, 10.0, "dense"),
            ("midfield-south-ruin", "ruins", 31.0, 35.0, 9.0, 10.0, "dense"),
            ("center-debris", "battlefield_debris_and_statuary", 30.0, 22.0, 6.0, 5.0, "light"),
            ("north-barricade", "barricade_and_fuel_pipes", 38.0, 10.0, 1.5, 8.0, "light"),
            ("south-barricade", "barricade_and_fuel_pipes", 22.0, 34.0, 1.5, 8.0, "light"),
        ),
        2: (
            ("attacker-corner-ruin", "ruins", 11.0, 10.0, 9.0, 12.0, "dense"),
            ("defender-corner-ruin", "ruins", 49.0, 34.0, 9.0, 12.0, "dense"),
            ("north-east-ruin", "ruins", 43.0, 12.0, 9.0, 10.0, "dense"),
            ("south-west-ruin", "ruins", 17.0, 32.0, 9.0, 10.0, "dense"),
            ("central-crater", "crater_and_rubble", 30.0, 22.0, 8.0, 8.0, "light"),
            ("north-barricade", "barricade_and_fuel_pipes", 26.0, 8.0, 1.5, 8.0, "light"),
            ("south-barricade", "barricade_and_fuel_pipes", 34.0, 36.0, 1.5, 8.0, "light"),
        ),
        3: (
            ("left-home-ruin", "ruins", 10.5, 11.0, 7.0, 12.0, "dense"),
            ("right-home-ruin", "ruins", 52.5, 36.5, 7.0, 13.0, "dense"),
            ("center-ruin", "ruins", 31.0, 23.5, 8.0, 13.0, "dense"),
            ("upper-flank-ruin", "ruins", 22.0, 36.5, 6.5, 11.0, "dense"),
            ("lower-flank-ruin", "ruins", 38.0, 7.5, 8.0, 15.0, "dense"),
            (
                "left-midfield-debris",
                "battlefield_debris_and_statuary",
                24.0,
                10.5,
                6.0,
                5.0,
                "light",
            ),
            (
                "right-midfield-debris",
                "battlefield_debris_and_statuary",
                37.0,
                35.5,
                6.0,
                5.0,
                "light",
            ),
            (
                "left-no-mans-barricade",
                "barricade_and_fuel_pipes",
                28.0,
                7.5,
                1.5,
                8.0,
                "light",
            ),
            (
                "right-no-mans-barricade",
                "barricade_and_fuel_pipes",
                30.5,
                38.0,
                1.5,
                8.0,
                "light",
            ),
        ),
    }[layout_number]
    return tuple(
        chapter_approved.SourceBattlefieldTerrainFeatureRow(
            feature_id=f"{layout_id}-{feature_suffix}",
            feature_kind=feature_kind,
            footprint_center_x_inches=x,
            footprint_center_y_inches=y,
            footprint_width_inches=width,
            footprint_depth_inches=depth,
            source_note=f"event companion {density} terrain footprint",
            display_geometry=_axis_aligned_display(
                x=x,
                y=y,
                width=width,
                depth=depth,
                display_template_id=f"{feature_kind}_{width:g}x{depth:g}",
            ),
        )
        for feature_suffix, feature_kind, x, y, width, depth, density in templates
    )


def _descriptor_deployment_polygons(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[EventPolygonSourceRecord, ...]:
    return tuple(
        EventPolygonSourceRecord(
            polygon_id=zone.deployment_zone_id,
            role=zone.player_role,
            vertices=_shape_vertices(zone.shape),
        )
        for zone in _layout_deployment_zones(layout_id=layout_id, layout_number=layout_number)
    )


def _no_mans_land_polygon(*, layout_id: str, layout_number: int) -> EventPolygonSourceRecord:
    vertices: tuple[tuple[float, float], ...]
    if layout_number == 2:
        vertices = (
            (18.0, 0.0),
            (60.0, 0.0),
            (60.0, 26.0),
            (42.0, 26.0),
            (42.0, 44.0),
            (0.0, 44.0),
            (0.0, 18.0),
            (18.0, 18.0),
        )
    else:
        vertices = ((18.0, 0.0), (42.0, 0.0), (42.0, 44.0), (18.0, 44.0))
    return EventPolygonSourceRecord(
        polygon_id=f"{layout_id}-no-mans-land",
        role="no_mans_land",
        vertices=vertices,
    )


def _territory_polygons(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[EventPolygonSourceRecord, ...]:
    if layout_number == 2:
        territories = (
            ("attacker_territory", ((0.0, 0.0), (30.0, 0.0), (30.0, 22.0), (0.0, 22.0))),
            ("defender_territory", ((30.0, 22.0), (60.0, 22.0), (60.0, 44.0), (30.0, 44.0))),
        )
    else:
        territories = (
            ("attacker_territory", ((0.0, 0.0), (30.0, 0.0), (30.0, 44.0), (0.0, 44.0))),
            ("defender_territory", ((30.0, 0.0), (60.0, 0.0), (60.0, 44.0), (30.0, 44.0))),
        )
    return tuple(
        EventPolygonSourceRecord(
            polygon_id=f"{layout_id}-{role}",
            role=role,
            vertices=vertices,
        )
        for role, vertices in territories
    )


def _descriptor_objectives(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[EventObjectivePointRecord, ...]:
    return tuple(
        EventObjectivePointRecord(
            objective_marker_id=objective.objective_marker_id,
            objective_kind=objective.objective_kind,
            x_inches=objective.x_inches,
            y_inches=objective.y_inches,
        )
        for objective in _layout_objectives(layout_id=layout_id, layout_number=layout_number)
    )


def _descriptor_terrain(
    *,
    layout_id: str,
    layout_number: int,
) -> tuple[EventTerrainSourceRecord, ...]:
    terrain: list[EventTerrainSourceRecord] = []
    for feature in _layout_terrain_features(layout_id=layout_id, layout_number=layout_number):
        density = "dense" if feature.feature_kind == "ruins" else "light"
        terrain.append(
            EventTerrainSourceRecord(
                feature_id=feature.feature_id,
                feature_kind=feature.feature_kind,
                density=density,
                x_inches=feature.footprint_center_x_inches,
                y_inches=feature.footprint_center_y_inches,
                width_inches=feature.footprint_width_inches,
                depth_inches=feature.footprint_depth_inches,
            )
        )
    return tuple(terrain)


def _axis_aligned_display(
    *,
    x: float,
    y: float,
    width: float,
    depth: float,
    display_template_id: str,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry(
        display_template_id=display_template_id,
        footprint_polygon=(
            TerrainDisplayPoint(x - width / 2.0, y - depth / 2.0),
            TerrainDisplayPoint(x + width / 2.0, y - depth / 2.0),
            TerrainDisplayPoint(x + width / 2.0, y + depth / 2.0),
            TerrainDisplayPoint(x - width / 2.0, y + depth / 2.0),
        ),
    )


def _shape_vertices(shape: DeploymentZoneShape) -> tuple[tuple[float, float], ...]:
    if len(shape.polygons) != 1:
        raise MissionPackError("Event Companion deployment shape must have one polygon.")
    return tuple((point.x, point.y) for point in shape.polygons[0].vertices)


def _base_size_source_record(
    *,
    record_id: str,
    faction_name: str,
    unit_name: str,
    source_base_text: str,
    source_page: int,
) -> BaseSizeSourceRecord:
    base_source_kind, status, base_size = _base_source_kind_and_geometry(source_base_text)
    return BaseSizeSourceRecord(
        record_id=record_id,
        faction_name=faction_name,
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


def _event_primary_mission_names() -> tuple[tuple[str, str], ...]:
    seen: dict[str, str] = {}
    for row in chapter_approved.primary_mission_matrix_rows():
        seen[row.primary_mission_id] = row.primary_mission_name
    return tuple(sorted(seen.items()))


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


def _layout_disposition_pairs() -> tuple[tuple[str, str], ...]:
    ordered = (
        "take-and-hold",
        "purge-the-foe",
        "priority-assets",
        "reconnaissance",
        "disruption",
    )
    return tuple(
        (first_id, second_id)
        for first_index, first_id in enumerate(ordered)
        for second_id in ordered[first_index:]
    )


def _force_disposition_name(force_disposition_id: str) -> str:
    for row in force_disposition_rows():
        if row.force_disposition_id == force_disposition_id:
            return row.name
    raise MissionPackError("Event Companion force disposition was not found.")


def _attacker_edge(layout_number: int) -> str:
    return "north_west_corner" if layout_number == 2 else "west_long_edge"


def _defender_edge(layout_number: int) -> str:
    return "south_east_corner" if layout_number == 2 else "east_long_edge"


def _title_from_slug(value: str) -> str:
    return " ".join(part.capitalize() for part in value.split("_"))


def _import_hash() -> str:
    payload = {
        "package_identity": package_identity().to_payload(),
        "mission_sequence": mission_sequence_descriptor().to_payload(),
        "primary_missions": [row.to_payload() for row in primary_mission_rows()],
        "secondary_missions": [row.to_payload() for row in secondary_mission_rows()],
        "force_dispositions": [row.to_payload() for row in force_disposition_rows()],
        "matrix": [row.to_payload() for row in primary_mission_matrix_rows()],
        "layouts": [row.to_payload() for row in battlefield_layout_rows()],
        "layout_descriptors": [row.to_payload() for row in layout_descriptor_rows()],
        "scoring": mission_pack_scoring_row().to_payload(),
        "tactical_secondary": tactical_secondary_procedure().to_payload(),
        "fixed_secondary": fixed_secondary_procedure().to_payload(),
        "card_amendments": card_amendment_set().to_payload(),
        "base_sizes": [row.to_payload() for row in base_size_source_rows()],
        "schema": IMPORTED_AT_SCHEMA_VERSION,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
