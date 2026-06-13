from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from warhammer40k_core.core.deployment_zones import DeploymentZoneShape
from warhammer40k_core.core.missions import MissionPackError, MissionSourcePackageDefinition
from warhammer40k_core.core.terrain_display import (
    TerrainDisplayGeometry,
    TerrainDisplayPoint,
)

EDITION_ID = "warhammer_40000_11th"
MISSION_PACK_ID = "11e-chapter-approved-2026-27"
SOURCE_PACKAGE_ID = "gw-11e-chapter-approved-2026-27"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Chapter Approved 2026-27"
SOURCE_VERSION = "2026-27"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-mission-source-v2"


@dataclass(frozen=True, slots=True)
class SourceScoringRuleRow:
    rule_id: str
    timing: str
    source_kind: str
    victory_points: int | None
    cap: int | None
    condition: str

    def to_payload(self) -> dict[str, int | str | None]:
        return {
            "rule_id": self.rule_id,
            "timing": self.timing,
            "source_kind": self.source_kind,
            "victory_points": self.victory_points,
            "cap": self.cap,
            "condition": self.condition,
        }


@dataclass(frozen=True, slots=True)
class SourcePrimaryMissionRow:
    primary_mission_id: str
    name: str
    max_vp_per_turn: int | None
    scoring_kind: str | None
    vp_per_controlled_objective: int | None
    scoring_rules: tuple[SourceScoringRuleRow, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "primary_mission_id": self.primary_mission_id,
            "name": self.name,
            "max_vp_per_turn": self.max_vp_per_turn,
            "scoring_kind": self.scoring_kind,
            "vp_per_controlled_objective": self.vp_per_controlled_objective,
            "scoring_rules": [rule.to_payload() for rule in self.scoring_rules],
        }


@dataclass(frozen=True, slots=True)
class SourceSecondaryMissionRow:
    secondary_mission_id: str
    name: str
    availability: str
    tournament_fixed_allowed: bool
    scoring_rules: tuple[SourceScoringRuleRow, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "secondary_mission_id": self.secondary_mission_id,
            "name": self.name,
            "availability": self.availability,
            "tournament_fixed_allowed": self.tournament_fixed_allowed,
            "scoring_rules": [rule.to_payload() for rule in self.scoring_rules],
        }


@dataclass(frozen=True, slots=True)
class SourceForceDispositionRow:
    force_disposition_id: str
    name: str

    def to_payload(self) -> dict[str, str]:
        return {
            "force_disposition_id": self.force_disposition_id,
            "name": self.name,
        }


@dataclass(frozen=True, slots=True)
class SourcePrimaryMissionMatrixCellRow:
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    primary_mission_id: str
    primary_mission_name: str
    battlefield_layout_ids: tuple[str, str, str]
    source_status: str

    def to_payload(self) -> dict[str, object]:
        return {
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "primary_mission_id": self.primary_mission_id,
            "primary_mission_name": self.primary_mission_name,
            "battlefield_layout_ids": list(self.battlefield_layout_ids),
            "source_status": self.source_status,
        }


@dataclass(frozen=True, slots=True)
class SourceMissionActionRow:
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

    def to_payload(self) -> dict[str, object]:
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
        }


@dataclass(frozen=True, slots=True)
class SourceMissionPackScoringRow:
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
    reserve_destruction_battle_round: int
    reserve_destruction_excludes_during_battle_strategic_reserves: bool
    reserve_destruction_only_declare_battle_formations: bool

    def to_payload(self) -> dict[str, object]:
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
        }


@dataclass(frozen=True, slots=True)
class SourceBattlefieldObjectiveRow:
    objective_marker_id: str
    name: str
    objective_kind: str
    x_inches: float
    y_inches: float

    def to_payload(self) -> dict[str, object]:
        return {
            "objective_marker_id": self.objective_marker_id,
            "name": self.name,
            "objective_kind": self.objective_kind,
            "x_inches": self.x_inches,
            "y_inches": self.y_inches,
        }


@dataclass(frozen=True, slots=True)
class SourceBattlefieldDeploymentZoneRow:
    deployment_zone_id: str
    player_role: str
    shape: DeploymentZoneShape

    def to_payload(self) -> dict[str, object]:
        return {
            "deployment_zone_id": self.deployment_zone_id,
            "player_role": self.player_role,
            "shape": self.shape.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class SourceBattlefieldTerrainFeatureRow:
    feature_id: str
    feature_kind: str
    footprint_center_x_inches: float
    footprint_center_y_inches: float
    footprint_width_inches: float
    footprint_depth_inches: float
    source_note: str
    display_geometry: TerrainDisplayGeometry

    def to_payload(self) -> dict[str, object]:
        return {
            "feature_id": self.feature_id,
            "feature_kind": self.feature_kind,
            "footprint_center_x_inches": self.footprint_center_x_inches,
            "footprint_center_y_inches": self.footprint_center_y_inches,
            "footprint_width_inches": self.footprint_width_inches,
            "footprint_depth_inches": self.footprint_depth_inches,
            "source_note": self.source_note,
            "display_geometry": self.display_geometry.to_payload(),
        }


@dataclass(frozen=True, slots=True)
class SourceBattlefieldLayoutRow:
    battlefield_layout_id: str
    name: str
    player_force_disposition_id: str
    opponent_force_disposition_id: str
    layout_number: int
    primary_mission_id: str
    deployment_map_id: str
    terrain_layout_id: str
    battlefield_width_inches: float
    battlefield_depth_inches: float
    coordinate_origin: str
    coordinate_orientation: str
    source_status: str
    objective_markers: tuple[SourceBattlefieldObjectiveRow, ...]
    deployment_zones: tuple[SourceBattlefieldDeploymentZoneRow, ...]
    terrain_features: tuple[SourceBattlefieldTerrainFeatureRow, ...]

    def to_payload(self) -> dict[str, object]:
        return {
            "battlefield_layout_id": self.battlefield_layout_id,
            "name": self.name,
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "layout_number": self.layout_number,
            "primary_mission_id": self.primary_mission_id,
            "deployment_map_id": self.deployment_map_id,
            "terrain_layout_id": self.terrain_layout_id,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "coordinate_origin": self.coordinate_origin,
            "coordinate_orientation": self.coordinate_orientation,
            "source_status": self.source_status,
            "objective_markers": [objective.to_payload() for objective in self.objective_markers],
            "deployment_zones": [zone.to_payload() for zone in self.deployment_zones],
            "terrain_features": [feature.to_payload() for feature in self.terrain_features],
        }


def _axis_aligned_display(
    *,
    x: float,
    y: float,
    width: float,
    depth: float,
    display_template_id: str,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=x,
        center_y_inches=y,
        width_inches=width,
        depth_inches=depth,
        display_template_id=display_template_id,
    )


def _diagonal_display(
    *,
    x: float,
    y: float,
    width: float,
    depth: float,
    display_template_id: str,
    slope: str,
) -> TerrainDisplayGeometry:
    min_x = x - (width / 2.0)
    max_x = x + (width / 2.0)
    min_y = y - (depth / 2.0)
    max_y = y + (depth / 2.0)
    inset = min(width, depth) / 4.0
    if slope == "down_right":
        polygon = (
            TerrainDisplayPoint(min_x, min_y + inset),
            TerrainDisplayPoint(min_x + inset, min_y),
            TerrainDisplayPoint(max_x, max_y - inset),
            TerrainDisplayPoint(max_x - inset, max_y),
        )
    elif slope == "up_right":
        polygon = (
            TerrainDisplayPoint(min_x + inset, min_y),
            TerrainDisplayPoint(max_x, min_y + inset),
            TerrainDisplayPoint(max_x - inset, max_y),
            TerrainDisplayPoint(min_x, max_y - inset),
        )
    else:
        raise MissionPackError("Unsupported diagonal terrain display slope.")
    return TerrainDisplayGeometry(
        display_template_id=display_template_id,
        footprint_polygon=polygon,
    )


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


def primary_mission_rows() -> tuple[SourcePrimaryMissionRow, ...]:
    return (
        SourcePrimaryMissionRow(
            primary_mission_id="primary-immovable-object",
            name="Immovable Object",
            max_vp_per_turn=None,
            scoring_kind="immovable_object",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "immovable-object-central-turn-end",
                    "turn_end",
                    "primary",
                    3,
                    None,
                    "control_one_or_more_central_objectives",
                ),
                _rule(
                    "immovable-object-rounds-two-to-four-command",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "each_non_home_objective_controlled_battle_rounds_two_to_four",
                ),
                _rule(
                    "immovable-object-round-five-turn-end",
                    "turn_end",
                    "primary",
                    5,
                    None,
                    "each_non_home_objective_controlled_round_five",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="primary-unstoppable-force",
            name="Unstoppable Force",
            max_vp_per_turn=None,
            scoring_kind="unstoppable_force",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "unstoppable-force-enemy-destroyed-turn-end",
                    "turn_end",
                    "primary",
                    3,
                    None,
                    "one_or_more_enemy_units_destroyed_this_turn",
                ),
                _rule(
                    "unstoppable-force-objectives",
                    "command_phase_or_round_five_turn_end",
                    "primary",
                    4,
                    None,
                    "each_non_home_objective_controlled_from_battle_round_two",
                ),
                _rule(
                    "unstoppable-force-new-objective-turn-end",
                    "turn_end",
                    "primary",
                    3,
                    None,
                    "control_one_or_more_new_non_home_objectives",
                ),
                _rule(
                    "unstoppable-force-central-end-battle",
                    "end_of_battle",
                    "primary",
                    5,
                    None,
                    "control_one_or_more_central_objectives_end_of_battle",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="primary-death-trap",
            name="Death Trap",
            max_vp_per_turn=None,
            scoring_kind="death_trap",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "death-trap-terrain-trapped-turn-end",
                    "turn_end",
                    "primary",
                    2,
                    None,
                    "each_terrain_area_trapped_this_turn",
                ),
                _rule(
                    "death-trap-objective-terrain-bonus-turn-end",
                    "turn_end",
                    "primary",
                    3,
                    None,
                    "each_trapped_objective_terrain_area_this_turn",
                ),
                _rule(
                    "death-trap-destroyed-in-trapped-terrain-turn-end",
                    "turn_end",
                    "primary",
                    3,
                    None,
                    "one_or_more_enemy_units_destroyed_after_starting_turn_in_trapped_terrain",
                ),
                _rule(
                    "death-trap-objective-control",
                    "command_phase_or_round_five_turn_end",
                    "primary",
                    4,
                    None,
                    "control_one_or_more_non_home_objectives_from_battle_round_two",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="burden-of-trust",
            name="Burden of Trust",
            max_vp_per_turn=15,
            scoring_kind="burden_of_trust",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "burden-of-trust-command",
                    "command_phase",
                    "primary",
                    4,
                    15,
                    "each_non_deployment_zone_objective_controlled",
                ),
                _rule(
                    "burden-of-trust-opponent-turn-end",
                    "opponent_turn_end",
                    "primary",
                    2,
                    None,
                    "each_guarded_no_mans_land_objective",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="hidden-supplies",
            name="Hidden Supplies",
            max_vp_per_turn=15,
            scoring_kind="control_objective_thresholds",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "hidden-supplies-one-objective",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "control_one_or_more_objectives",
                ),
                _rule(
                    "hidden-supplies-two-objectives",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "control_two_or_more_objectives",
                ),
                _rule(
                    "hidden-supplies-more-than-opponent",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "control_more_objectives_than_opponent",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="linchpin",
            name="Linchpin",
            max_vp_per_turn=15,
            scoring_kind="linchpin_objective_control",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "linchpin-home", "command_phase", "primary", 3, None, "control_home_objective"
                ),
                _rule(
                    "linchpin-non-home",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "each_other_objective_controlled_if_home_controlled",
                ),
                _rule(
                    "linchpin-no-home",
                    "command_phase",
                    "primary",
                    3,
                    None,
                    "each_other_objective_controlled_if_home_not_controlled",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="purge-the-foe",
            name="Purge the Foe",
            max_vp_per_turn=16,
            scoring_kind="purge_the_foe",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "purge-one-destroyed",
                    "battle_round_end",
                    "primary",
                    4,
                    None,
                    "one_or_more_enemy_units_destroyed",
                ),
                _rule(
                    "purge-more-destroyed",
                    "battle_round_end",
                    "primary",
                    4,
                    None,
                    "more_enemy_units_destroyed_than_opponent",
                ),
                _rule(
                    "purge-control-one",
                    "command_phase",
                    "primary",
                    4,
                    None,
                    "control_one_or_more_objectives",
                ),
                _rule(
                    "purge-control-more",
                    "command_phase",
                    "primary",
                    4,
                    None,
                    "control_more_objectives_than_opponent",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="scorched-earth",
            name="Scorched Earth",
            max_vp_per_turn=10,
            scoring_kind="control_objectives",
            vp_per_controlled_objective=5,
            scoring_rules=(
                _rule(
                    "scorched-earth-control",
                    "command_phase",
                    "primary",
                    5,
                    10,
                    "each_controlled_objective",
                ),
                _rule(
                    "scorched-earth-action",
                    "end_of_battle",
                    "primary",
                    5,
                    None,
                    "burn_objective_action_completed",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="supply-drop",
            name="Supply Drop",
            max_vp_per_turn=15,
            scoring_kind="supply_drop_objective_control",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "supply-drop-round-two-three",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "each_active_no_mans_land_objective_round_two_or_three",
                ),
                _rule(
                    "supply-drop-round-four",
                    "command_phase",
                    "primary",
                    8,
                    None,
                    "each_active_no_mans_land_objective_round_four",
                ),
                _rule(
                    "supply-drop-round-five",
                    "command_phase",
                    "primary",
                    15,
                    None,
                    "each_active_no_mans_land_objective_round_five",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="take-and-hold",
            name="Take and Hold",
            max_vp_per_turn=15,
            scoring_kind="control_objectives",
            vp_per_controlled_objective=5,
            scoring_rules=(
                _rule(
                    "take-and-hold-control",
                    "command_phase",
                    "primary",
                    5,
                    15,
                    "each_controlled_objective_from_battle_round_two",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="terraform",
            name="Terraform",
            max_vp_per_turn=12,
            scoring_kind="control_objectives",
            vp_per_controlled_objective=4,
            scoring_rules=(
                _rule(
                    "terraform-control",
                    "command_phase",
                    "primary",
                    4,
                    12,
                    "each_controlled_objective",
                ),
                _rule(
                    "terraform-action",
                    "turn_end",
                    "mission_action",
                    1,
                    None,
                    "terraform_objective_action_completed",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="the-ritual",
            name="The Ritual",
            max_vp_per_turn=15,
            scoring_kind="control_objectives",
            vp_per_controlled_objective=5,
            scoring_rules=(
                _rule(
                    "ritual-control",
                    "command_phase",
                    "primary",
                    5,
                    15,
                    "each_no_mans_land_objective_controlled",
                ),
            ),
        ),
        SourcePrimaryMissionRow(
            primary_mission_id="unexploded-ordnance",
            name="Unexploded Ordnance",
            max_vp_per_turn=15,
            scoring_kind="unexploded_ordnance",
            vp_per_controlled_objective=None,
            scoring_rules=(
                _rule(
                    "unexploded-near-enemy",
                    "command_phase",
                    "primary",
                    8,
                    None,
                    "objective_in_opponent_deployment_zone",
                ),
                _rule(
                    "unexploded-no-mans-land",
                    "command_phase",
                    "primary",
                    5,
                    None,
                    "objective_in_no_mans_land",
                ),
                _rule(
                    "unexploded-own-zone",
                    "command_phase",
                    "primary",
                    2,
                    None,
                    "objective_in_own_deployment_zone",
                ),
            ),
        ),
    )


def secondary_mission_rows() -> tuple[SourceSecondaryMissionRow, ...]:
    return (
        _secondary(
            "a-grievous-blow",
            "A Grievous Blow",
            "both",
            True,
            fixed_vp=4,
            tactical_vp=5,
            cap=5,
        ),
        _secondary("a-tempting-target", "A Tempting Target", "tactical", False, tactical_vp=5),
        _secondary(
            "assassination",
            "Assassination",
            "both",
            True,
            fixed_vp=4,
            tactical_vp=5,
        ),
        _secondary("beacon", "Beacon", "tactical", False, tactical_vp=5),
        _secondary(
            "behind-enemy-lines",
            "Behind Enemy Lines",
            "tactical",
            False,
            tactical_vp=3,
            cap=5,
        ),
        _secondary_bring_it_down(),
        _secondary("burden-of-trust", "Burden of Trust", "tactical", False, tactical_vp=2, cap=5),
        _secondary("centre-ground", "Centre Ground", "tactical", False, tactical_vp=5),
        _secondary_cleanse(),
        _secondary_defend_stronghold(),
        _secondary("display-of-might", "Display of Might", "tactical", False, tactical_vp=5),
        _secondary(
            "engage-on-all-fronts",
            "Engage on All Fronts",
            "both",
            True,
            fixed_vp=4,
            tactical_vp=5,
        ),
        _secondary("forward-position", "Forward Position", "tactical", False, tactical_vp=5),
        _secondary("no-prisoners", "No Prisoners", "tactical", False, tactical_vp=2, cap=5),
        _secondary("outflank", "Outflank", "tactical", False, tactical_vp=5),
        _secondary_overwhelming_force(),
        _secondary_plunder(),
        _secondary(
            "secure-no-mans-land",
            "Secure No Man's Land",
            "tactical",
            False,
            tactical_vp=5,
        ),
    )


def force_disposition_rows() -> tuple[SourceForceDispositionRow, ...]:
    return (
        SourceForceDispositionRow("purge-the-foe", "Purge The Foe"),
        SourceForceDispositionRow("take-and-hold", "Take And Hold"),
        SourceForceDispositionRow("disruption", "Disruption"),
        SourceForceDispositionRow("reconnaissance", "Reconnaissance"),
        SourceForceDispositionRow("priority-assets", "Priority Assets"),
    )


_LAYOUT_FORCE_DISPOSITION_ORDER = {
    "take-and-hold": 0,
    "purge-the-foe": 1,
    "priority-assets": 2,
    "reconnaissance": 3,
    "disruption": 4,
}


def _battlefield_layout_id_prefix(
    player_force_disposition_id: str, opponent_force_disposition_id: str
) -> str:
    ordered_disposition_ids = tuple(
        sorted(
            (player_force_disposition_id, opponent_force_disposition_id),
            key=lambda disposition_id: _LAYOUT_FORCE_DISPOSITION_ORDER[disposition_id],
        )
    )
    return f"{ordered_disposition_ids[0]}-vs-{ordered_disposition_ids[1]}"


def primary_mission_matrix_rows() -> tuple[SourcePrimaryMissionMatrixCellRow, ...]:
    implemented_mission_ids = frozenset(
        {
            "primary-death-trap",
            "primary-immovable-object",
            "primary-unstoppable-force",
        }
    )
    primary_mission_names = {
        "purge-the-foe": {
            "take-and-hold": "Unstoppable Force",
            "purge-the-foe": "Meatgrinder",
            "priority-assets": "Punishment",
            "reconnaissance": "Consecrate",
            "disruption": "Destroyer's Wrath",
        },
        "take-and-hold": {
            "take-and-hold": "Battlefield Dominance",
            "purge-the-foe": "Immovable Object",
            "priority-assets": "Determined Acquisition",
            "reconnaissance": "Purge and Secure",
            "disruption": "Inescapable Dominion",
        },
        "priority-assets": {
            "take-and-hold": "Secure Asset",
            "purge-the-foe": "Vital Link",
            "priority-assets": "Extract Relic",
            "reconnaissance": "Vanguard Operation",
            "disruption": "Sabotage",
        },
        "reconnaissance": {
            "take-and-hold": "Reconnaissance Sweep",
            "purge-the-foe": "Triangulation",
            "priority-assets": "Surveil the Foe",
            "reconnaissance": "Gather Intel",
            "disruption": "Search and Scour",
        },
        "disruption": {
            "take-and-hold": "Death Trap",
            "purge-the-foe": "Delaying Action",
            "priority-assets": "Locate and Deny",
            "reconnaissance": "Outmaneuver",
            "disruption": "Smoke and Mirrors",
        },
    }
    rows: list[SourcePrimaryMissionMatrixCellRow] = []
    for player_disposition in force_disposition_rows():
        for opponent_disposition in force_disposition_rows():
            primary_mission_name = primary_mission_names[player_disposition.force_disposition_id][
                opponent_disposition.force_disposition_id
            ]
            primary_mission_id = f"primary-{_mission_name_slug(primary_mission_name)}"
            source_status = (
                "implemented"
                if primary_mission_id in implemented_mission_ids
                else "awaiting_source"
            )
            battlefield_layout_id_prefix = _battlefield_layout_id_prefix(
                player_disposition.force_disposition_id,
                opponent_disposition.force_disposition_id,
            )
            rows.append(
                SourcePrimaryMissionMatrixCellRow(
                    player_force_disposition_id=player_disposition.force_disposition_id,
                    opponent_force_disposition_id=opponent_disposition.force_disposition_id,
                    primary_mission_id=primary_mission_id,
                    primary_mission_name=primary_mission_name,
                    battlefield_layout_ids=(
                        f"{battlefield_layout_id_prefix}-layout-1",
                        f"{battlefield_layout_id_prefix}-layout-2",
                        f"{battlefield_layout_id_prefix}-layout-3",
                    ),
                    source_status=source_status,
                )
            )
    return tuple(rows)


def battlefield_layout_rows() -> tuple[SourceBattlefieldLayoutRow, ...]:
    return (
        SourceBattlefieldLayoutRow(
            battlefield_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            name="Take and Hold vs Purge the Foe 3",
            player_force_disposition_id="take-and-hold",
            opponent_force_disposition_id="purge-the-foe",
            layout_number=3,
            primary_mission_id="primary-immovable-object",
            deployment_map_id="take-and-hold-vs-purge-the-foe-layout-3-deployment",
            terrain_layout_id="take-and-hold-vs-purge-the-foe-layout-3",
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            coordinate_origin="top_left",
            coordinate_orientation="x_right_along_60_inch_edge_y_down_along_44_inch_edge",
            source_status="image_estimate",
            objective_markers=(
                SourceBattlefieldObjectiveRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-home",
                    "Left Home Objective",
                    "home",
                    9.5,
                    10.5,
                ),
                SourceBattlefieldObjectiveRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-home",
                    "Right Home Objective",
                    "home",
                    52.5,
                    34.5,
                ),
                SourceBattlefieldObjectiveRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-upper-central",
                    "Upper Central Objective",
                    "central",
                    28.5,
                    8.5,
                ),
                SourceBattlefieldObjectiveRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-center-central",
                    "Center Central Objective",
                    "central",
                    30.0,
                    22.0,
                ),
                SourceBattlefieldObjectiveRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-lower-central",
                    "Lower Central Objective",
                    "central",
                    28.5,
                    35.5,
                ),
            ),
            deployment_zones=(
                SourceBattlefieldDeploymentZoneRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-attacker",
                    "attacker",
                    DeploymentZoneShape.rectangle(
                        min_x=0.0,
                        min_y=0.0,
                        max_x=18.0,
                        max_y=44.0,
                    ),
                ),
                SourceBattlefieldDeploymentZoneRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-defender",
                    "defender",
                    DeploymentZoneShape.rectangle(
                        min_x=42.0,
                        min_y=0.0,
                        max_x=60.0,
                        max_y=44.0,
                    ),
                ),
            ),
            terrain_features=(
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-home-ruin",
                    "ruins",
                    10.5,
                    11.0,
                    7.0,
                    12.0,
                    "left home objective ruin footprint",
                    _axis_aligned_display(
                        x=10.5,
                        y=11.0,
                        width=7.0,
                        depth=12.0,
                        display_template_id="ruins_rect_7x12",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-home-ruin",
                    "ruins",
                    52.5,
                    36.5,
                    7.0,
                    13.0,
                    "right home objective ruin footprint",
                    _axis_aligned_display(
                        x=52.5,
                        y=36.5,
                        width=7.0,
                        depth=13.0,
                        display_template_id="ruins_rect_7x13",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-center-ruin",
                    "ruins",
                    31.0,
                    23.5,
                    8.0,
                    13.0,
                    "central ruin footprint",
                    _axis_aligned_display(
                        x=31.0,
                        y=23.5,
                        width=8.0,
                        depth=13.0,
                        display_template_id="ruins_rect_8x13",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-upper-flank-ruin",
                    "ruins",
                    22.0,
                    36.5,
                    6.5,
                    11.0,
                    "upper flank central objective ruin footprint",
                    _axis_aligned_display(
                        x=22.0,
                        y=36.5,
                        width=6.5,
                        depth=11.0,
                        display_template_id="ruins_rect_6_5x11",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-lower-flank-ruin",
                    "ruins",
                    38.0,
                    7.5,
                    8.0,
                    15.0,
                    "lower flank central objective ruin footprint",
                    _axis_aligned_display(
                        x=38.0,
                        y=7.5,
                        width=8.0,
                        depth=15.0,
                        display_template_id="ruins_rect_8x15",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-midfield-debris",
                    "battlefield_debris_and_statuary",
                    24.0,
                    10.5,
                    6.0,
                    5.0,
                    "left midfield debris footprint",
                    _axis_aligned_display(
                        x=24.0,
                        y=10.5,
                        width=6.0,
                        depth=5.0,
                        display_template_id="debris_rect_6x5",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-midfield-debris",
                    "battlefield_debris_and_statuary",
                    37.0,
                    35.5,
                    6.0,
                    5.0,
                    "right midfield debris footprint",
                    _axis_aligned_display(
                        x=37.0,
                        y=35.5,
                        width=6.0,
                        depth=5.0,
                        display_template_id="debris_rect_6x5",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-no-mans-barricade",
                    "barricade_and_fuel_pipes",
                    28.0,
                    7.5,
                    1.5,
                    8.0,
                    "left no man's land barricade footprint",
                    _axis_aligned_display(
                        x=28.0,
                        y=7.5,
                        width=1.5,
                        depth=8.0,
                        display_template_id="barricade_rect_1_5x8",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-no-mans-barricade",
                    "barricade_and_fuel_pipes",
                    30.5,
                    38.0,
                    1.5,
                    8.0,
                    "right no man's land barricade footprint",
                    _axis_aligned_display(
                        x=30.5,
                        y=38.0,
                        width=1.5,
                        depth=8.0,
                        display_template_id="barricade_rect_1_5x8",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-midline-wall",
                    "barricade_and_fuel_pipes",
                    18.0,
                    22.0,
                    1.0,
                    12.0,
                    "left deployment edge wall footprint",
                    _axis_aligned_display(
                        x=18.0,
                        y=22.0,
                        width=1.0,
                        depth=12.0,
                        display_template_id="barricade_rect_1x12",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-midline-wall",
                    "barricade_and_fuel_pipes",
                    42.0,
                    22.0,
                    1.0,
                    12.0,
                    "right deployment edge wall footprint",
                    _axis_aligned_display(
                        x=42.0,
                        y=22.0,
                        width=1.0,
                        depth=12.0,
                        display_template_id="barricade_rect_1x12",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-pipe-field",
                    "barricade_and_fuel_pipes",
                    49.0,
                    8.0,
                    8.0,
                    12.0,
                    "left deployment pipe and rubble footprint",
                    _axis_aligned_display(
                        x=49.0,
                        y=8.0,
                        width=8.0,
                        depth=12.0,
                        display_template_id="barricade_rect_8x12",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-pipe-field",
                    "barricade_and_fuel_pipes",
                    11.0,
                    37.0,
                    8.0,
                    10.0,
                    "right deployment pipe and rubble footprint",
                    _axis_aligned_display(
                        x=11.0,
                        y=37.0,
                        width=8.0,
                        depth=10.0,
                        display_template_id="barricade_rect_8x10",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-left-diagonal-ruin",
                    "ruins",
                    49.0,
                    17.0,
                    8.0,
                    9.0,
                    "left deployment diagonal ruin footprint",
                    _diagonal_display(
                        x=49.0,
                        y=17.0,
                        width=8.0,
                        depth=9.0,
                        display_template_id="ruins_diagonal_down_right_estimate_v1",
                        slope="down_right",
                    ),
                ),
                SourceBattlefieldTerrainFeatureRow(
                    "take-and-hold-vs-purge-the-foe-layout-3-right-diagonal-ruin",
                    "ruins",
                    12.5,
                    29.0,
                    7.0,
                    8.0,
                    "right deployment diagonal ruin footprint",
                    _diagonal_display(
                        x=12.5,
                        y=29.0,
                        width=7.0,
                        depth=8.0,
                        display_template_id="ruins_diagonal_up_right_estimate_v1",
                        slope="up_right",
                    ),
                ),
            ),
        ),
    )


def mission_action_rows() -> tuple[SourceMissionActionRow, ...]:
    return (
        SourceMissionActionRow(
            mission_action_id="booby-trap-terrain",
            mission_id="primary-death-trap",
            mission_kind="primary",
            name="Booby Trap",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="immediate",
            eligible_unit_policy="active_player_unit",
            target_policy="trappable_terrain_area",
            interruption_conditions=(),
            victory_points=0,
            scoring_source_id="primary-death-trap",
        ),
        SourceMissionActionRow(
            mission_action_id="cleanse-objective",
            mission_id="cleanse",
            mission_kind="secondary",
            name="Cleanse",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="turn_end",
            eligible_unit_policy="active_player_infantry_or_battleline_unit",
            target_policy="objective_marker",
            interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
            victory_points=0,
            scoring_source_id="cleanse",
        ),
        SourceMissionActionRow(
            mission_action_id="plunder-terrain",
            mission_id="plunder",
            mission_kind="secondary",
            name="Plunder",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="immediate",
            eligible_unit_policy="active_player_unit",
            target_policy="plunderable_terrain_area",
            interruption_conditions=(),
            victory_points=0,
            scoring_source_id="plunder",
        ),
        SourceMissionActionRow(
            mission_action_id="terraform-objective",
            mission_id="terraform",
            mission_kind="primary",
            name="Terraform",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="turn_end",
            eligible_unit_policy="active_player_unit",
            target_policy="objective_marker",
            interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
            victory_points=1,
            scoring_source_id="terraform",
        ),
    )


def mission_pack_scoring_row() -> SourceMissionPackScoringRow:
    return SourceMissionPackScoringRow(
        game_length_battle_rounds=5,
        primary_scoring_phase="command",
        primary_scoring_timing="phase_end",
        secondary_vp_per_score=5,
        mission_action_vp=5,
        primary_vp_cap=45,
        secondary_vp_cap=45,
        total_vp_cap=100,
        end_of_round_scoring_windows=("battle_round_end",),
        end_of_game_scoring_windows=("turn_end_round_five_going_second", "end_of_battle"),
        reserve_destruction_timing="end_of_battle_round_n",
        reserve_destruction_battle_round=3,
        reserve_destruction_excludes_during_battle_strategic_reserves=True,
        reserve_destruction_only_declare_battle_formations=True,
    )


def _secondary(
    secondary_mission_id: str,
    name: str,
    availability: str,
    tournament_fixed_allowed: bool,
    *,
    tactical_vp: int,
    fixed_vp: int | None = None,
    alternate_vp: int | None = None,
    cap: int | None = None,
) -> SourceSecondaryMissionRow:
    rules: list[SourceScoringRuleRow] = []
    if fixed_vp is not None:
        rules.append(
            _rule(
                f"{secondary_mission_id}-fixed",
                "mission_condition_met",
                "fixed_secondary",
                fixed_vp,
                cap,
                "fixed_secondary_condition",
            )
        )
    rules.append(
        _rule(
            f"{secondary_mission_id}-tactical",
            "mission_condition_met",
            "tactical_secondary",
            tactical_vp,
            cap,
            "tactical_secondary_condition",
        )
    )
    if alternate_vp is not None:
        rules.append(
            _rule(
                f"{secondary_mission_id}-alternate",
                "mission_condition_met",
                "secondary",
                alternate_vp,
                cap,
                "alternate_or_partial_condition",
            )
        )
    return SourceSecondaryMissionRow(
        secondary_mission_id=secondary_mission_id,
        name=name,
        availability=availability,
        tournament_fixed_allowed=tournament_fixed_allowed,
        scoring_rules=tuple(rules),
    )


def _secondary_bring_it_down() -> SourceSecondaryMissionRow:
    return SourceSecondaryMissionRow(
        secondary_mission_id="bring-it-down",
        name="Bring It Down",
        availability="both",
        tournament_fixed_allowed=True,
        scoring_rules=(
            _rule(
                "bring-it-down-fixed",
                "turn_end",
                "fixed_secondary",
                4,
                None,
                "each_enemy_model_w10_or_more_destroyed_this_turn",
            ),
            _rule(
                "bring-it-down-tactical",
                "turn_end",
                "tactical_secondary",
                5,
                5,
                "each_enemy_model_w10_or_more_destroyed_this_turn",
            ),
        ),
    )


def _secondary_cleanse() -> SourceSecondaryMissionRow:
    rules: list[SourceScoringRuleRow] = []
    for suffix, victory_points, condition in (
        ("one-objective", 2, "one_or_more_objectives_cleansed_this_turn"),
        ("two-objectives", 3, "two_or_more_objectives_cleansed_this_turn"),
    ):
        rules.append(
            _rule(
                f"cleanse-tactical-{suffix}",
                "your_turn_end",
                "tactical_secondary",
                victory_points,
                None,
                condition,
            )
        )
    return SourceSecondaryMissionRow(
        secondary_mission_id="cleanse",
        name="Cleanse",
        availability="tactical",
        tournament_fixed_allowed=False,
        scoring_rules=tuple(rules),
    )


def _secondary_defend_stronghold() -> SourceSecondaryMissionRow:
    return SourceSecondaryMissionRow(
        secondary_mission_id="defend-stronghold",
        name="Defend Stronghold",
        availability="tactical",
        tournament_fixed_allowed=False,
        scoring_rules=(
            _rule(
                "defend-stronghold-home-objective",
                "opponent_turn_end_or_round_five_turn_end",
                "tactical_secondary",
                3,
                None,
                "control_home_objective",
            ),
            _rule(
                "defend-stronghold-no-enemy-in-deployment-zone",
                "opponent_turn_end_or_round_five_turn_end",
                "tactical_secondary",
                2,
                None,
                "no_enemy_units_within_own_deployment_zone",
            ),
        ),
    )


def _secondary_overwhelming_force() -> SourceSecondaryMissionRow:
    return SourceSecondaryMissionRow(
        secondary_mission_id="overwhelming-force",
        name="Overwhelming Force",
        availability="tactical",
        tournament_fixed_allowed=False,
        scoring_rules=(
            _rule(
                "overwhelming-force-tactical",
                "turn_end",
                "tactical_secondary",
                3,
                5,
                "each_enemy_unit_started_turn_on_objective_destroyed",
            ),
        ),
    )


def _secondary_plunder() -> SourceSecondaryMissionRow:
    return SourceSecondaryMissionRow(
        secondary_mission_id="plunder",
        name="Plunder",
        availability="tactical",
        tournament_fixed_allowed=False,
        scoring_rules=(
            _rule(
                "plunder-tactical",
                "your_turn_end",
                "tactical_secondary",
                5,
                None,
                "one_or_more_terrain_areas_plundered_this_turn",
            ),
        ),
    )


def _mission_name_slug(name: str) -> str:
    return name.lower().replace("'", "").replace(" ", "-")


def _rule(
    rule_id: str,
    timing: str,
    source_kind: str,
    victory_points: int | None,
    cap: int | None,
    condition: str,
) -> SourceScoringRuleRow:
    return SourceScoringRuleRow(
        rule_id=rule_id,
        timing=timing,
        source_kind=source_kind,
        victory_points=victory_points,
        cap=cap,
        condition=condition,
    )


def _import_hash() -> str:
    encoded = json.dumps(
        _source_payload_for_hash(),
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _source_payload_for_hash() -> dict[str, object]:
    return {
        "edition_id": EDITION_ID,
        "mission_pack_id": MISSION_PACK_ID,
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "imported_at_schema_version": IMPORTED_AT_SCHEMA_VERSION,
        "primary_missions": [row.to_payload() for row in primary_mission_rows()],
        "secondary_missions": [row.to_payload() for row in secondary_mission_rows()],
        "force_dispositions": [row.to_payload() for row in force_disposition_rows()],
        "primary_mission_matrix": [row.to_payload() for row in primary_mission_matrix_rows()],
        "battlefield_layouts": [row.to_payload() for row in battlefield_layout_rows()],
        "mission_actions": [row.to_payload() for row in mission_action_rows()],
        "scoring": mission_pack_scoring_row().to_payload(),
    }


def assert_distinct_source_package_identity(
    left: MissionSourcePackageDefinition,
    right: MissionSourcePackageDefinition,
) -> None:
    if type(left) is not MissionSourcePackageDefinition:
        raise MissionPackError("left must be a MissionSourcePackageDefinition.")
    if type(right) is not MissionSourcePackageDefinition:
        raise MissionPackError("right must be a MissionSourcePackageDefinition.")
    if left.source_namespace_key() == right.source_namespace_key():
        raise MissionPackError(
            "Source package identities must include edition, package, and pack IDs."
        )
