from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from warhammer40k_core.core.missions import MissionPackError, MissionSourcePackageDefinition

EDITION_ID = "warhammer_40000_11th"
MISSION_PACK_ID = "11e-chapter-approved-2025-26"
SOURCE_PACKAGE_ID = "gw-11e-chapter-approved-2025-26"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Chapter Approved 2025-26"
SOURCE_VERSION = "2025-26"
IMPORTED_AT_SCHEMA_VERSION = "core-v2-mission-source-v1"


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
    battlefield_layout_ids: tuple[str, str, str]
    source_status: str

    def to_payload(self) -> dict[str, object]:
        return {
            "player_force_disposition_id": self.player_force_disposition_id,
            "opponent_force_disposition_id": self.opponent_force_disposition_id,
            "primary_mission_id": self.primary_mission_id,
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
        _secondary("a-tempting-target", "A Tempting Target", "tactical", False, tactical_vp=5),
        _secondary("area-denial", "Area Denial", "tactical", False, tactical_vp=5, alternate_vp=2),
        _secondary(
            "assassination",
            "Assassination",
            "both",
            True,
            fixed_vp=4,
            tactical_vp=5,
            alternate_vp=3,
        ),
        _secondary(
            "behind-enemy-lines",
            "Behind Enemy Lines",
            "tactical",
            False,
            tactical_vp=4,
            alternate_vp=3,
        ),
        _secondary("bring-it-down", "Bring It Down", "both", True, fixed_vp=2, tactical_vp=4),
        _secondary("cleanse", "Cleanse", "both", True, fixed_vp=4, tactical_vp=5, alternate_vp=2),
        _secondary("cull-the-horde", "Cull the Horde", "both", True, fixed_vp=5, tactical_vp=5),
        _secondary("defend-stronghold", "Defend Stronghold", "tactical", False, tactical_vp=3),
        _secondary("display-of-might", "Display of Might", "tactical", False, tactical_vp=4),
        _secondary(
            "engage-on-all-fronts",
            "Engage on All Fronts",
            "tactical",
            False,
            tactical_vp=4,
            alternate_vp=1,
        ),
        _secondary(
            "establish-locus", "Establish Locus", "tactical", False, tactical_vp=4, alternate_vp=2
        ),
        _secondary(
            "extend-battle-lines",
            "Extend Battle Lines",
            "tactical",
            False,
            tactical_vp=4,
            alternate_vp=2,
        ),
        _secondary(
            "marked-for-death", "Marked for Death", "tactical", False, tactical_vp=5, alternate_vp=2
        ),
        _secondary("no-prisoners", "No Prisoners", "both", False, fixed_vp=2, tactical_vp=2, cap=5),
        _secondary(
            "overwhelming-force", "Overwhelming Force", "tactical", False, tactical_vp=3, cap=5
        ),
        _secondary(
            "recover-assets", "Recover Assets", "tactical", False, tactical_vp=5, alternate_vp=3
        ),
        _secondary("sabotage", "Sabotage", "tactical", False, tactical_vp=6, alternate_vp=3),
        _secondary(
            "secure-no-mans-land",
            "Secure No Man's Land",
            "tactical",
            False,
            tactical_vp=5,
            alternate_vp=2,
        ),
        _secondary(
            "storm-hostile-objective", "Storm Hostile Objective", "tactical", False, tactical_vp=4
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


def primary_mission_matrix_rows() -> tuple[SourcePrimaryMissionMatrixCellRow, ...]:
    rows: list[SourcePrimaryMissionMatrixCellRow] = []
    for player_disposition in force_disposition_rows():
        for opponent_disposition in force_disposition_rows():
            primary_mission_id = (
                "primary-"
                f"{player_disposition.force_disposition_id}-vs-"
                f"{opponent_disposition.force_disposition_id}"
            )
            rows.append(
                SourcePrimaryMissionMatrixCellRow(
                    player_force_disposition_id=player_disposition.force_disposition_id,
                    opponent_force_disposition_id=opponent_disposition.force_disposition_id,
                    primary_mission_id=primary_mission_id,
                    battlefield_layout_ids=(
                        f"{primary_mission_id}-layout-1",
                        f"{primary_mission_id}-layout-2",
                        f"{primary_mission_id}-layout-3",
                    ),
                    source_status="awaiting_source",
                )
            )
    return tuple(rows)


def mission_action_rows() -> tuple[SourceMissionActionRow, ...]:
    return (
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
            victory_points=5,
            scoring_source_id="cleanse",
        ),
        SourceMissionActionRow(
            mission_action_id="establish-locus-objective",
            mission_id="establish-locus",
            mission_kind="secondary",
            name="Establish Locus",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="turn_end",
            eligible_unit_policy="active_player_unit",
            target_policy="center_or_enemy_deployment_zone",
            interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
            victory_points=4,
            scoring_source_id="establish-locus",
        ),
        SourceMissionActionRow(
            mission_action_id="recover-assets-objective",
            mission_id="recover-assets",
            mission_kind="secondary",
            name="Recover Assets",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="turn_end",
            eligible_unit_policy="active_player_unit",
            target_policy="table_quarter",
            interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
            victory_points=5,
            scoring_source_id="recover-assets",
        ),
        SourceMissionActionRow(
            mission_action_id="sabotage-terrain",
            mission_id="sabotage",
            mission_kind="secondary",
            name="Sabotage",
            start_phase="shooting",
            start_timing="shooting_phase_action_start",
            completion_timing="opponent_next_turn_end_or_battle_end",
            eligible_unit_policy="active_player_unit",
            target_policy="terrain_feature",
            interruption_conditions=("unit_moved", "unit_destroyed", "unit_left_battlefield"),
            victory_points=6,
            scoring_source_id="sabotage",
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
        primary_vp_cap=50,
        secondary_vp_cap=40,
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
