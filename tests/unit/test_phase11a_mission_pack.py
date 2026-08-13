from __future__ import annotations

import json
from dataclasses import FrozenInstanceError, replace
from typing import cast

import pytest

from warhammer40k_core.adapters.battlefield_projection import project_battlefield_view
from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    SecondaryMissionAvailability,
    mission_source_status_from_token,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    ModelPlacement,
    UnitPlacement,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    MissionSetupError,
    MissionSetupPayload,
)
from warhammer40k_core.engine.missions import (
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    supported_mission_packs,
    validate_mission_setup_source_layout,
)
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
)
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    GameLifecycleStage,
    LifecycleStatus,
)
from warhammer40k_core.engine.phases.movement import (
    MovementPhaseHandler,
    MovementPhaseState,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.reserves import (
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReservePlacementViolationCode,
    ReserveState,
)
from warhammer40k_core.engine.scoring import VictoryPointSourceKind
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.engine.wargear_selections import (
    ModelProfileSelection,
)
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.mission_pack_import import (
    chapter_approved_2026_27_mission_pack,
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2026_27 as source_data,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)

PHASE16A_BATTLEFIELD_LAYOUT_ID = "take-and-hold-vs-purge-the-foe-layout-3"
PHASE16A_DEPLOYMENT_MAP_ID = "take-and-hold-vs-purge-the-foe-layout-3-deployment"
PHASE16A_MISSION_POOL_ENTRY_ID = "mission-take-and-hold-vs-purge-the-foe-layout-3"
TYPED_TAKE_AND_HOLD_LAYOUT_C_ID = "take-and-hold-vs-take-and-hold-layout-3"


def test_supported_mission_pack_builders_cache_only_immutable_definition_graphs() -> None:
    chapter_pack = chapter_approved_2026_27_mission_pack()
    event_pack = warhammer_event_companion_2026_07_mission_pack()
    inventory = supported_mission_packs()

    assert chapter_approved_2026_27_mission_pack() is chapter_pack
    assert warhammer_event_companion_2026_07_mission_pack() is event_pack
    assert inventory == (chapter_pack, event_pack)
    assert inventory[0] is chapter_pack
    assert inventory[1] is event_pack
    assert mission_pack_for_id(chapter_pack.mission_pack_id) is chapter_pack
    assert mission_pack_for_id(event_pack.mission_pack_id) is event_pack

    with pytest.raises(FrozenInstanceError):
        type(event_pack).__setattr__(event_pack, "name", "mutated")

    detached_payload = event_pack.to_payload()
    detached_payload["deployment_maps"].clear()

    assert event_pack.deployment_maps
    assert event_pack.to_payload()["deployment_maps"]


def test_chapter_approved_mission_pack_round_trips_without_object_reprs() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()

    payload = mission_pack.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = cast(MissionPackDefinitionPayload, json.loads(encoded))

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionPackDefinition.from_payload(decoded).to_payload() == payload
    assert mission_pack.sequence.steps[0] == "muster_armies"
    assert len(mission_pack.deployment_maps) == 10
    assert len(mission_pack.terrain_layout_templates) == 10
    assert len(mission_pack.battlefield_layouts) == 9
    assert len(mission_pack.terrain_area_footprint_templates) == 5
    assert len(mission_pack.mission_pool_entries) == 1
    assert len(mission_pack.secondary_missions) == 18
    assert tuple(mission.secondary_mission_id for mission in mission_pack.secondary_missions) == (
        "a-grievous-blow",
        "a-tempting-target",
        "assassination",
        "beacon",
        "behind-enemy-lines",
        "bring-it-down",
        "burden-of-trust",
        "centre-ground",
        "cleanse",
        "defend-stronghold",
        "display-of-might",
        "engage-on-all-fronts",
        "forward-position",
        "no-prisoners",
        "outflank",
        "overwhelming-force",
        "plunder",
        "secure-no-mans-land",
    )
    assert {
        mission.secondary_mission_id
        for mission in mission_pack.secondary_missions
        if mission.tournament_fixed_allowed
    } == {
        "a-grievous-blow",
        "assassination",
        "bring-it-down",
        "engage-on-all-fronts",
    }
    assert len(mission_pack.challenger_cards) == 9


def test_chapter_approved_source_package_payload_and_identity_snapshot() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    source_package = mission_pack.source_package

    payload = source_package.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionSourcePackageDefinition.from_payload(payload).to_payload() == payload
    assert payload == {
        "edition_id": "warhammer_40000_11th",
        "mission_pack_id": "11e-chapter-approved-2026-27",
        "source_package_id": "gw-11e-chapter-approved-2026-27",
        "source_title": "Warhammer 40,000 11th Edition Chapter Approved 2026-27",
        "source_version": "2026-27",
        "source_commit_or_import_hash": source_package.source_commit_or_import_hash,
        "imported_at_schema_version": "core-v2-mission-source-v2",
    }
    assert len(source_package.source_commit_or_import_hash) == 64
    assert mission_pack.mission_pack_id == "11e-chapter-approved-2026-27"


def test_phase14j_force_disposition_primary_matrix_is_source_tracked() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    expected_matrix = {
        ("purge-the-foe", "take-and-hold"): ("Unstoppable Force", "primary-unstoppable-force"),
        ("purge-the-foe", "purge-the-foe"): ("Meatgrinder", "primary-meatgrinder"),
        ("purge-the-foe", "priority-assets"): ("Punishment", "primary-punishment"),
        ("purge-the-foe", "reconnaissance"): ("Consecrate", "primary-consecrate"),
        ("purge-the-foe", "disruption"): ("Destroyer's Wrath", "primary-destroyers-wrath"),
        ("take-and-hold", "take-and-hold"): (
            "Battlefield Dominance",
            "primary-battlefield-dominance",
        ),
        ("take-and-hold", "purge-the-foe"): ("Immovable Object", "primary-immovable-object"),
        ("take-and-hold", "priority-assets"): (
            "Determined Acquisition",
            "primary-determined-acquisition",
        ),
        ("take-and-hold", "reconnaissance"): ("Purge and Secure", "primary-purge-and-secure"),
        ("take-and-hold", "disruption"): (
            "Inescapable Dominion",
            "primary-inescapable-dominion",
        ),
        ("priority-assets", "take-and-hold"): ("Secure Asset", "primary-secure-asset"),
        ("priority-assets", "purge-the-foe"): ("Vital Link", "primary-vital-link"),
        ("priority-assets", "priority-assets"): ("Extract Relic", "primary-extract-relic"),
        ("priority-assets", "reconnaissance"): (
            "Vanguard Operation",
            "primary-vanguard-operation",
        ),
        ("priority-assets", "disruption"): ("Sabotage", "primary-sabotage"),
        ("reconnaissance", "take-and-hold"): (
            "Reconnaissance Sweep",
            "primary-reconnaissance-sweep",
        ),
        ("reconnaissance", "purge-the-foe"): ("Triangulation", "primary-triangulation"),
        ("reconnaissance", "priority-assets"): ("Surveil the Foe", "primary-surveil-the-foe"),
        ("reconnaissance", "reconnaissance"): ("Gather Intel", "primary-gather-intel"),
        ("reconnaissance", "disruption"): ("Search and Scour", "primary-search-and-scour"),
        ("disruption", "take-and-hold"): ("Death Trap", "primary-death-trap"),
        ("disruption", "purge-the-foe"): ("Delaying Action", "primary-delaying-action"),
        ("disruption", "priority-assets"): ("Locate and Deny", "primary-locate-and-deny"),
        ("disruption", "reconnaissance"): ("Outmaneuver", "primary-outmaneuver"),
        ("disruption", "disruption"): ("Smoke and Mirrors", "primary-smoke-and-mirrors"),
    }
    source_matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in source_data.primary_mission_matrix_rows()
    }
    imported_matrix = {
        (cell.player_force_disposition_id, cell.opponent_force_disposition_id): cell
        for cell in mission_pack.primary_mission_matrix_cells
    }

    assert [
        disposition.force_disposition_id for disposition in mission_pack.force_dispositions
    ] == [
        "disruption",
        "priority-assets",
        "purge-the-foe",
        "reconnaissance",
        "take-and-hold",
    ]
    assert len(mission_pack.primary_mission_matrix_cells) == 25
    assert len(source_matrix) == 25
    assert len(imported_matrix) == 25
    assert {cell_key: row.primary_mission_name for cell_key, row in source_matrix.items()} == {
        cell_key: expected_name
        for cell_key, (expected_name, _expected_id) in expected_matrix.items()
    }
    assert {cell_key: cell.primary_mission_id for cell_key, cell in imported_matrix.items()} == {
        cell_key: expected_id for cell_key, (_expected_name, expected_id) in expected_matrix.items()
    }

    purge_into_hold = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id="purge-the-foe",
        opponent_force_disposition_id="take-and-hold",
    )
    hold_into_purge = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id="take-and-hold",
        opponent_force_disposition_id="purge-the-foe",
    )
    mirror = mission_pack.primary_mission_matrix_cell(
        player_force_disposition_id="reconnaissance",
        opponent_force_disposition_id="reconnaissance",
    )

    assert purge_into_hold.primary_mission_id == "primary-unstoppable-force"
    assert hold_into_purge.primary_mission_id == "primary-immovable-object"
    assert purge_into_hold.primary_mission_id != hold_into_purge.primary_mission_id
    assert mirror.primary_mission_id == "primary-gather-intel"
    pool_entry = mission_pack.mission_pool_entries[0]
    assert pool_entry.player_force_disposition_id == "take-and-hold"
    assert pool_entry.opponent_force_disposition_id == "purge-the-foe"
    assert pool_entry.player_primary_mission_id == "primary-immovable-object"
    assert pool_entry.opponent_primary_mission_id == "primary-unstoppable-force"
    assert purge_into_hold.source_status is MissionSourceStatus.IMPLEMENTED
    assert hold_into_purge.source_status is MissionSourceStatus.IMPLEMENTED
    assert (
        mission_pack.primary_mission_matrix_cell(
            player_force_disposition_id="disruption",
            opponent_force_disposition_id="take-and-hold",
        ).source_status
        is MissionSourceStatus.IMPLEMENTED
    )
    assert mirror.source_status is MissionSourceStatus.AWAITING_SOURCE
    assert hold_into_purge.battlefield_layout_ids == (
        "take-and-hold-vs-purge-the-foe-layout-1",
        "take-and-hold-vs-purge-the-foe-layout-2",
        PHASE16A_BATTLEFIELD_LAYOUT_ID,
    )
    assert purge_into_hold.battlefield_layout_ids == hold_into_purge.battlefield_layout_ids
    layout_disposition_order = (
        "take-and-hold",
        "purge-the-foe",
        "priority-assets",
        "reconnaissance",
        "disruption",
    )
    assert {cell.battlefield_layout_ids for cell in mission_pack.primary_mission_matrix_cells} == {
        tuple(
            f"{first_disposition_id}-vs-{second_disposition_id}-layout-{layout_number}"
            for layout_number in (1, 2, 3)
        )
        for first_index, first_disposition_id in enumerate(layout_disposition_order)
        for second_disposition_id in layout_disposition_order[first_index:]
    }
    assert tuple(layout.terrain_layout_id for layout in mission_pack.terrain_layout_templates) == (
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-2",
        "disruption-vs-reconnaissance-layout-3",
        "purge-the-foe-vs-purge-the-foe-layout-1",
        "purge-the-foe-vs-purge-the-foe-layout-2",
        "purge-the-foe-vs-purge-the-foe-layout-3",
        PHASE16A_BATTLEFIELD_LAYOUT_ID,
        "take-and-hold-vs-take-and-hold-layout-1",
        "take-and-hold-vs-take-and-hold-layout-2",
        TYPED_TAKE_AND_HOLD_LAYOUT_C_ID,
    )
    assert MissionPackDefinition.from_payload(mission_pack.to_payload()).to_payload() == (
        mission_pack.to_payload()
    )


def test_phase14j_mission_source_status_tokens_are_strict() -> None:
    assert mission_source_status_from_token("awaiting_source") is (
        MissionSourceStatus.AWAITING_SOURCE
    )
    assert mission_source_status_from_token(MissionSourceStatus.IMPLEMENTED) is (
        MissionSourceStatus.IMPLEMENTED
    )

    with pytest.raises(MissionPackError, match="MissionSourceStatus token"):
        mission_source_status_from_token(1)
    with pytest.raises(MissionPackError, match="Unsupported MissionSourceStatus"):
        mission_source_status_from_token("legacy")


def test_phase14j_primary_matrix_lookup_and_references_are_strict() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()

    with pytest.raises(MissionPackError, match="force_disposition_id"):
        mission_pack.force_disposition("unknown-disposition")
    with pytest.raises(MissionPackError, match="matrix cell"):
        mission_pack.primary_mission_matrix_cell(
            player_force_disposition_id="purge-the-foe",
            opponent_force_disposition_id="unknown-disposition",
        )

    with pytest.raises(MissionPackError, match="missing cells"):
        replace(
            mission_pack,
            primary_mission_matrix_cells=mission_pack.primary_mission_matrix_cells[:-1],
        )

    implemented_without_primary = replace(
        mission_pack.primary_mission_matrix_cells[0],
        source_status=MissionSourceStatus.IMPLEMENTED,
        primary_mission_id="missing-primary",
    )
    with pytest.raises(MissionPackError, match="must reference a primary mission"):
        replace(
            mission_pack,
            primary_mission_matrix_cells=(
                implemented_without_primary,
                *mission_pack.primary_mission_matrix_cells[1:],
            ),
        )


def test_phase17n_battlefield_graph_completeness_is_explicit_and_fail_closed() -> None:
    chapter_pack = chapter_approved_2026_27_mission_pack()
    event_pack = warhammer_event_companion_2026_07_mission_pack()

    assert chapter_pack.requires_complete_battlefield_graph is False
    assert event_pack.requires_complete_battlefield_graph is True

    with pytest.raises(MissionPackError, match="unknown IDs"):
        replace(event_pack, battlefield_layouts=event_pack.battlefield_layouts[:-1])
    with pytest.raises(MissionPackError, match="cover every directional-matrix"):
        replace(event_pack, mission_pool_entries=event_pack.mission_pool_entries[:-1])

    first_entry = event_pack.mission_pool_entries[0]
    with pytest.raises(MissionPackError, match="resolved identity is duplicated"):
        replace(
            event_pack,
            mission_pool_entries=(
                first_entry,
                replace(first_entry, mission_pool_entry_id="duplicate-source-row"),
                *event_pack.mission_pool_entries[1:],
            ),
        )

    chapter_entry = chapter_pack.mission_pool_entries[0]
    with pytest.raises(MissionPackError, match="terrain layout drifted"):
        replace(
            chapter_pack,
            mission_pool_entries=(
                replace(
                    chapter_entry,
                    terrain_layout_ids=("disruption-vs-reconnaissance-layout-1",),
                ),
            ),
        )


def test_chapter_approved_11th_edition_scoring_action_source_snapshot() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    take_and_hold = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "take-and-hold"
    )
    immovable_object = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "primary-immovable-object"
    )
    unstoppable_force = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "primary-unstoppable-force"
    )
    death_trap = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "primary-death-trap"
    )
    bring_it_down = mission_pack.secondary_mission("bring-it-down")
    a_grievous_blow = mission_pack.secondary_mission("a-grievous-blow")
    assassination = mission_pack.secondary_mission("assassination")
    no_prisoners = mission_pack.secondary_mission("no-prisoners")
    overwhelming_force = mission_pack.secondary_mission("overwhelming-force")
    secure_no_mans_land = mission_pack.secondary_mission("secure-no-mans-land")
    cleanse = mission_pack.secondary_mission("cleanse")
    plunder = mission_pack.secondary_mission("plunder")
    cleanse_action = mission_pack.mission_action("cleanse-objective")
    plunder_action = mission_pack.mission_action("plunder-terrain")
    booby_trap = mission_pack.mission_action("booby-trap-terrain")

    assert take_and_hold.scoring_kind == "control_objectives"
    assert take_and_hold.vp_per_controlled_objective == 5
    assert take_and_hold.max_vp_per_turn == 15
    assert take_and_hold.scoring_rules[0].to_payload() == {
        "rule_id": "take-and-hold-control",
        "timing": "command_phase",
        "source_kind": "primary",
        "victory_points": 5,
        "cap": 15,
        "condition": "each_controlled_objective_from_battle_round_two",
        "source_id": (
            "gw-11e-chapter-approved-2026-27:primary:take-and-hold:"
            "scoring-rule:take-and-hold-control"
        ),
    }
    assert {rule.rule_id: rule.to_payload() for rule in bring_it_down.scoring_rules} == {
        "bring-it-down-fixed": {
            "rule_id": "bring-it-down-fixed",
            "timing": "turn_end",
            "source_kind": "fixed_secondary",
            "victory_points": 4,
            "cap": 5,
            "condition": "each_enemy_model_w10_or_more_destroyed_this_turn",
            "source_id": (
                "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
                "scoring-rule:bring-it-down-fixed"
            ),
        },
        "bring-it-down-tactical": {
            "rule_id": "bring-it-down-tactical",
            "timing": "turn_end",
            "source_kind": "tactical_secondary",
            "victory_points": 5,
            "cap": 5,
            "condition": "each_enemy_model_w10_or_more_destroyed_this_turn",
            "source_id": (
                "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
                "scoring-rule:bring-it-down-tactical"
            ),
        },
        "bring-it-down-when-drawn": {
            "rule_id": "bring-it-down-when-drawn",
            "timing": "when_drawn",
            "source_kind": "secondary",
            "victory_points": None,
            "cap": None,
            "condition": "may_discard_if_no_enemy_models_w10_or_more_on_battlefield",
            "source_id": (
                "gw-11e-chapter-approved-2026-27:secondary:bring-it-down:"
                "scoring-rule:bring-it-down-when-drawn"
            ),
        },
    }
    assert {rule.rule_id: rule.condition for rule in a_grievous_blow.scoring_rules} == {
        "a-grievous-blow-fixed": (
            "each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn"
        ),
        "a-grievous-blow-tactical": (
            "each_enemy_unit_starting_strength_13_or_more_destroyed_this_turn"
        ),
        "a-grievous-blow-when-drawn": (
            "may_discard_if_no_enemy_units_starting_strength_13_or_more_on_battlefield"
        ),
    }
    assert {rule.rule_id: rule.condition for rule in no_prisoners.scoring_rules} == {
        "no-prisoners-tactical": "each_enemy_unit_destroyed_this_turn",
    }
    assert {rule.rule_id: rule.condition for rule in overwhelming_force.scoring_rules} == {
        "overwhelming-force-tactical": (
            "each_enemy_unit_started_turn_in_range_of_objective_destroyed"
        ),
    }
    assert {rule.rule_id: rule.condition for rule in secure_no_mans_land.scoring_rules} == {
        "secure-no-mans-land-tactical": (
            "control_two_or_more_no_mans_land_objectives_excluding_home"
        ),
    }
    assert {
        rule.rule_id for rule in assassination.scoring_rules if rule.source_kind == "secondary"
    } == {
        "assassination-fixed-character-w4-plus",
        "assassination-fixed-character-w3-or-less",
        "assassination-tactical-all-characters-destroyed",
        "assassination-tactical-character-destroyed",
    }
    assert cleanse.availability is SecondaryMissionAvailability.TACTICAL
    assert cleanse.tournament_fixed_allowed is False
    assert {rule.rule_id for rule in cleanse.scoring_rules} == {
        "cleanse-tactical-one-objective",
        "cleanse-tactical-two-objectives",
    }
    assert {rule.rule_id for rule in plunder.scoring_rules} == {"plunder-tactical"}
    assert cleanse_action.start_phase == "shooting"
    assert cleanse_action.target_policy == "objective_marker"
    assert cleanse_action.victory_points == 0
    assert plunder_action.start_phase == "shooting"
    assert plunder_action.completion_timing == "immediate"
    assert plunder_action.target_policy == "plunderable_terrain_area"
    assert plunder_action.victory_points == 0
    immovable_rules = {rule.rule_id: rule.to_payload() for rule in immovable_object.scoring_rules}
    assert immovable_rules == {
        "immovable-object-central-turn-end": {
            "rule_id": "immovable-object-central-turn-end",
            "timing": "turn_end",
            "source_kind": "primary",
            "victory_points": 3,
            "cap": None,
            "condition": "control_one_or_more_central_objectives",
            "source_id": (
                "gw-11e-chapter-approved-2026-27:primary:primary-immovable-object:"
                "scoring-rule:immovable-object-central-turn-end"
            ),
        },
        "immovable-object-rounds-two-to-four-command": {
            "rule_id": "immovable-object-rounds-two-to-four-command",
            "timing": "command_phase",
            "source_kind": "primary",
            "victory_points": 5,
            "cap": None,
            "condition": "each_non_home_objective_controlled_battle_rounds_two_to_four",
            "source_id": (
                "gw-11e-chapter-approved-2026-27:primary:primary-immovable-object:"
                "scoring-rule:immovable-object-rounds-two-to-four-command"
            ),
        },
        "immovable-object-round-five-turn-end": {
            "rule_id": "immovable-object-round-five-turn-end",
            "timing": "turn_end",
            "source_kind": "primary",
            "victory_points": 5,
            "cap": None,
            "condition": "each_non_home_objective_controlled_round_five",
            "source_id": (
                "gw-11e-chapter-approved-2026-27:primary:primary-immovable-object:"
                "scoring-rule:immovable-object-round-five-turn-end"
            ),
        },
    }
    assert {rule.rule_id for rule in unstoppable_force.scoring_rules} == {
        "unstoppable-force-enemy-destroyed-turn-end",
        "unstoppable-force-objectives",
        "unstoppable-force-new-objective-turn-end",
        "unstoppable-force-central-end-battle",
    }
    assert {rule.rule_id for rule in death_trap.scoring_rules} == {
        "death-trap-terrain-trapped-turn-end",
        "death-trap-objective-terrain-bonus-turn-end",
        "death-trap-destroyed-in-trapped-terrain-turn-end",
        "death-trap-objective-control",
    }
    assert booby_trap.mission_id == "primary-death-trap"
    assert booby_trap.mission_kind == "primary"
    assert booby_trap.start_phase == "shooting"
    assert booby_trap.completion_timing == "immediate"
    assert booby_trap.target_policy == "trappable_terrain_area"
    assert booby_trap.victory_points == 0
    assert "unit_left_battlefield" in cleanse_action.interruption_conditions
    assert mission_pack.scoring.end_of_game_scoring_windows == (
        "turn_end_round_five_going_second",
        "end_of_battle",
    )


def test_future_edition_source_identity_cannot_collide_with_eleventh_edition() -> None:
    eleventh = source_data.source_package_definition()
    future = MissionSourcePackageDefinition(
        edition_id="warhammer_40000_future",
        mission_pack_id=eleventh.mission_pack_id,
        source_package_id=eleventh.source_package_id,
        source_title="Warhammer 40,000 Future Edition",
        source_version=eleventh.source_version,
        source_commit_or_import_hash=eleventh.source_commit_or_import_hash,
        imported_at_schema_version=eleventh.imported_at_schema_version,
    )

    assert eleventh.source_namespace_key() != future.source_namespace_key()
    source_data.assert_distinct_source_package_identity(eleventh, future)
    with pytest.raises(MissionPackError, match="Source package identities"):
        source_data.assert_distinct_source_package_identity(eleventh, eleventh)


def test_deployment_map_and_objective_marker_policy_round_trip() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    deployment_map = mission_pack.deployment_map(PHASE16A_DEPLOYMENT_MAP_ID)
    payload = deployment_map.to_payload()
    round_tripped = type(deployment_map).from_payload(payload)

    assert round_tripped.to_payload() == payload
    assert all(marker.measurement_anchor == "center" for marker in deployment_map.objective_markers)
    assert all(marker.marker_diameter_mm == 40.0 for marker in deployment_map.objective_markers)
    assert all(marker.is_flat for marker in deployment_map.objective_markers)
    assert not any(marker.blocks_movement for marker in deployment_map.objective_markers)
    assert not any(marker.blocks_placement for marker in deployment_map.objective_markers)


def test_deployment_map_objective_marker_coordinates_match_source_snapshot() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()

    assert _objective_coordinate_snapshot(mission_pack)[PHASE16A_DEPLOYMENT_MAP_ID] == {
        "take-and-hold-vs-purge-the-foe-layout-3-center-central": (30.0, 22.0),
        "take-and-hold-vs-purge-the-foe-layout-3-left-home": (9.5, 10.5),
        "take-and-hold-vs-purge-the-foe-layout-3-lower-central": (28.5, 35.5),
        "take-and-hold-vs-purge-the-foe-layout-3-right-home": (52.5, 34.5),
        "take-and-hold-vs-purge-the-foe-layout-3-upper-central": (28.5, 8.5),
    }


def test_chapter_approved_exposes_typed_event_companion_battlefield_layouts() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    layout = mission_pack.battlefield_layout(TYPED_TAKE_AND_HOLD_LAYOUT_C_ID)
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    terrain_layout = mission_pack.terrain_layout_template(layout.terrain_layout_id)

    assert layout.battlefield_width_inches == 44.0
    assert layout.battlefield_depth_inches == 60.0
    assert len(layout.terrain_areas) == 16
    assert len(layout.objective_terrain_areas) == 5
    assert deployment_map.objective_markers == layout.objective_markers
    assert deployment_map.deployment_zones == layout.deployment_zones
    assert terrain_layout.battlefield_width_inches == 44.0
    assert terrain_layout.battlefield_depth_inches == 60.0
    assert terrain_layout.terrain_features == ()


def test_typed_event_layout_instantiates_source_area_placements() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "purge-the-foe-vs-purge-the-foe-layout-1"
    mission_pool_entry_id = f"mission-{layout_id}"
    template = mission_pack.terrain_layout_template(layout_id)
    layout = mission_pack.battlefield_layout(layout_id)
    first = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=mission_pool_entry_id,
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    second = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=mission_pool_entry_id,
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )

    assert first.to_payload() == second.to_payload()
    assert template.terrain_features == ()
    assert len(layout.terrain_feature_placements) == 30
    assert len(first.terrain_features) == 30
    assert {feature.feature_id for feature in first.terrain_features} == {
        placement.feature_id for placement in layout.terrain_feature_placements
    }


def test_phase16a_battlefield_layout_template_matches_source_snapshot() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    layout_row = source_data.battlefield_layout_rows()[0]
    deployment_map = mission_pack.deployment_map(layout_row.deployment_map_id)
    terrain_layout = mission_pack.terrain_layout_template(layout_row.terrain_layout_id)
    objective_kinds = {
        objective.objective_marker_id: objective.objective_kind
        for objective in layout_row.objective_markers
    }
    attacker_zone = deployment_map.deployment_zones[0]
    defender_zone = deployment_map.deployment_zones[1]

    assert layout_row.battlefield_layout_id == PHASE16A_BATTLEFIELD_LAYOUT_ID
    assert layout_row.coordinate_origin == "top_left"
    assert layout_row.coordinate_orientation == (
        "x_right_along_60_inch_edge_y_down_along_44_inch_edge"
    )
    assert deployment_map.battlefield_width_inches == 60.0
    assert deployment_map.battlefield_depth_inches == 44.0
    assert attacker_zone.min_x == 0.0
    assert attacker_zone.max_x == 18.0
    assert defender_zone.min_x == 42.0
    assert defender_zone.max_x == 60.0
    assert defender_zone.min_x - attacker_zone.max_x == 24.0
    assert layout_row.deployment_zones[0].to_payload()["shape"] == {
        "polygons": [
            {
                "vertices": [
                    {"x": 0.0, "y": 0.0},
                    {"x": 18.0, "y": 0.0},
                    {"x": 18.0, "y": 44.0},
                    {"x": 0.0, "y": 44.0},
                ],
            },
        ],
        "cutouts": [],
    }
    assert tuple(sorted(objective_kinds.values())) == (
        "attacker_home",
        "central",
        "central",
        "central",
        "defender_home",
    )
    assert layout_row.source_status == "layout_identity_coordinate_extraction_pending"
    assert terrain_layout.terrain_features == ()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    assert setup.terrain_features == ()
    assert setup.terrain_areas == ()


def test_phase16a_battlefield_layout_identifiers_are_cross_platform_file_safe() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    layout_row = source_data.battlefield_layout_rows()[0]
    identifiers = {
        layout_row.battlefield_layout_id,
        layout_row.deployment_map_id,
        layout_row.terrain_layout_id,
        *mission_pack.primary_mission_matrix_cell(
            player_force_disposition_id="take-and-hold",
            opponent_force_disposition_id="purge-the-foe",
        ).battlefield_layout_ids,
        *(entry.mission_pool_entry_id for entry in mission_pack.mission_pool_entries),
        *(objective.objective_marker_id for objective in layout_row.objective_markers),
        *(zone.deployment_zone_id for zone in layout_row.deployment_zones),
        *(feature.feature_id for feature in layout_row.terrain_features),
    }
    safe_characters = set("abcdefghijklmnopqrstuvwxyz0123456789-")

    assert identifiers
    for identifier in identifiers:
        assert identifier == identifier.strip()
        assert not identifier.endswith(".")
        assert set(identifier) <= safe_characters


def test_mission_pool_selection_is_deterministic() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()

    first_order = mission_pack.deterministic_mission_pool_order(seed="event-round-1")
    second_order = mission_pack.deterministic_mission_pool_order(seed="event-round-1")
    alternate_order = mission_pack.deterministic_mission_pool_order(seed="event-round-2")

    assert tuple(entry.mission_pool_entry_id for entry in first_order) == tuple(
        entry.mission_pool_entry_id for entry in second_order
    )
    assert tuple(entry.mission_pool_entry_id for entry in first_order) == (
        PHASE16A_MISSION_POOL_ENTRY_ID,
    )
    assert tuple(entry.mission_pool_entry_id for entry in alternate_order) == (
        PHASE16A_MISSION_POOL_ENTRY_ID,
    )


def test_mission_setup_from_components_rejects_source_inconsistent_components() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    deployment_map = mission_pack.deployment_map(PHASE16A_DEPLOYMENT_MAP_ID)
    terrain_layout = mission_pack.terrain_layout_template(PHASE16A_BATTLEFIELD_LAYOUT_ID)

    with pytest.raises(MissionSetupError, match="Force disposition is not present"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
            attacker_player_id="player-a",
            attacker_force_disposition_id="not-a-disposition",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        )

    with pytest.raises(MissionSetupError, match="Deployment map is not present"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            deployment_map=replace(deployment_map, deployment_map_id="foreign-map"),
            terrain_layout=terrain_layout,
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        )

    with pytest.raises(MissionSetupError, match="Terrain layout is not present"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            deployment_map=deployment_map,
            terrain_layout=replace(terrain_layout, terrain_layout_id="layout-99"),
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="purge-the-foe",
        )


def test_mission_setup_from_components_rejects_illegal_pool_combination() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()

    with pytest.raises(MissionSetupError, match="not a legal Chapter Approved mission pool row"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            deployment_map=mission_pack.deployment_map(PHASE16A_DEPLOYMENT_MAP_ID),
            terrain_layout=mission_pack.terrain_layout_template(PHASE16A_BATTLEFIELD_LAYOUT_ID),
            attacker_player_id="player-a",
            attacker_force_disposition_id="take-and-hold",
            defender_player_id="player-b",
            defender_force_disposition_id="take-and-hold",
        )


def test_mission_setup_payload_preserves_mission_pool_entry_id() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        deployment_map=mission_pack.deployment_map(PHASE16A_DEPLOYMENT_MAP_ID),
        terrain_layout=mission_pack.terrain_layout_template(PHASE16A_BATTLEFIELD_LAYOUT_ID),
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )

    assert setup.mission_pool_entry_id == PHASE16A_MISSION_POOL_ENTRY_ID
    assert setup.primary_mission_id_for_player("player-a") == "primary-immovable-object"
    assert setup.primary_mission_id_for_player("player-b") == "primary-unstoppable-force"
    assert MissionSetup.from_payload(setup.to_payload()).to_payload() == setup.to_payload()
    legacy_payload = cast(dict[str, object], setup.to_payload())
    legacy_payload["primary_mission_id"] = "primary-immovable-object"
    legacy_payload.pop("primary_mission_assignments")
    with pytest.raises(MissionSetupError, match="payload fields are invalid"):
        MissionSetup.from_payload(cast(MissionSetupPayload, legacy_payload))


def test_game_config_rejects_mission_assignment_muster_disposition_drift() -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    config_without_setup = _config(mission_setup=None)

    with pytest.raises(
        GameLifecycleError,
        match=("mission Primary assignment Force Disposition does not match ArmyMusterRequest"),
    ):
        replace(config_without_setup, mission_setup=setup)


def test_game_state_rejects_mustered_army_disposition_drift_at_every_boundary() -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    config = _config(mission_setup=setup)
    player_a_request = next(
        request for request in config.army_muster_requests if request.player_id == "player-a"
    )
    player_a_army = muster_army(catalog=config.army_catalog, request=player_a_request)
    drifted_army = replace(player_a_army, force_disposition_id="purge-the-foe")
    expected_error = "mission Primary assignment Force Disposition does not match ArmyDefinition"

    state = GameState.from_config(config)
    with pytest.raises(GameLifecycleError, match=expected_error):
        state.record_army_definition(drifted_army)
    with pytest.raises(GameLifecycleError, match=expected_error):
        state.replace_army_definitions([drifted_army])

    payload = state.to_payload()
    payload["army_definitions"] = [drifted_army.to_payload()]
    with pytest.raises(GameLifecycleError, match=expected_error):
        GameState.from_payload(payload)

    state_without_setup = GameState.from_config(_config(mission_setup=None))
    state_without_setup.record_army_definition(drifted_army)
    with pytest.raises(GameLifecycleError, match=expected_error):
        state_without_setup.record_mission_setup(setup)


def test_mission_setup_assigns_directional_primaries_independently_of_battlefield_roles() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )

    assert setup.primary_mission_id_for_player("player-a") == "primary-unstoppable-force"
    assert setup.primary_mission_id_for_player("player-b") == "primary-immovable-object"
    validate_mission_setup_source_layout(setup)


def test_mission_scoring_policies_resolve_asymmetric_player_primaries() -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="take-and-hold",
    )

    policies = mission_scoring_policies_from_setup(setup)

    assert policies.source_id == f"{setup.source_id}:scoring"
    assert policies.policy_for_player("player-a").primary_mission_id == (
        "primary-unstoppable-force"
    )
    assert policies.policy_for_player("player-b").primary_mission_id == ("primary-immovable-object")
    assert frozenset(
        rule.rule_id for rule in policies.policy_for_player("player-a").primary_scoring_rules
    ) == frozenset(
        (
            "unstoppable-force-enemy-destroyed-turn-end",
            "unstoppable-force-objectives",
            "unstoppable-force-new-objective-turn-end",
            "unstoppable-force-central-end-battle",
        )
    )
    assert frozenset(
        rule.rule_id for rule in policies.policy_for_player("player-b").primary_scoring_rules
    ) == frozenset(
        (
            "immovable-object-central-turn-end",
            "immovable-object-rounds-two-to-four-command",
            "immovable-object-round-five-turn-end",
        )
    )
    assert policies.policy_for_player("player-a").source_id == (
        f"{setup.source_id}:scoring:player-a:primary-unstoppable-force"
    )
    assert policies.policy_for_player("player-b").source_id == (
        f"{setup.source_id}:scoring:player-b:primary-immovable-object"
    )


@pytest.mark.parametrize(
    ("attacker_force_disposition_id", "defender_force_disposition_id"),
    [
        ("take-and-hold", "disruption"),
        ("disruption", "take-and-hold"),
    ],
)
def test_mission_scoring_policies_defer_pending_primary_failure_to_owning_path(
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
) -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-take-and-hold-vs-disruption-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_player_id="player-b",
        defender_force_disposition_id=defender_force_disposition_id,
    )

    policies = mission_scoring_policies_from_setup(setup)
    implemented = next(
        policy for policy in policies.player_policies if policy.primary_scoring_supported
    )
    pending = next(
        policy for policy in policies.player_policies if not policy.primary_scoring_supported
    )

    assert implemented.primary_mission_id == "primary-death-trap"
    assert pending.primary_mission_id == "primary-determined-acquisition"
    assert (
        implemented.cap_bucket_for_victory_point_source(
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=implemented.primary_mission_id,
        ).value
        == "primary"
    )
    with pytest.raises(
        GameLifecycleError,
        match="Primary mission scoring source is known but engine implementation is pending",
    ):
        pending.cap_bucket_for_victory_point_source(
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=pending.primary_mission_id,
        )


@pytest.mark.parametrize(
    "mutation_kind",
    [
        "source_identity",
        "primary_mission",
        "dimensions",
        "objective_markers",
        "deployment_zones",
        "terrain_features",
    ],
)
def test_canonical_layoutless_mission_setup_rejects_complete_source_drift(
    mutation_kind: str,
) -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    assert setup.battlefield_layout_id is None
    validate_mission_setup_source_layout(setup)
    payload = _config(mission_setup=setup).to_payload()
    setup_payload = payload["mission_setup"]
    assert setup_payload is not None

    if mutation_kind == "source_identity":
        setup_payload["source_id"] = "substituted-source"
        setup_payload["source_version"] = "substituted-version"
    elif mutation_kind == "primary_mission":
        setup_payload["primary_mission_assignments"][0]["primary_mission_id"] = (
            "primary-meatgrinder"
        )
    elif mutation_kind == "dimensions":
        setup_payload["battlefield_width_inches"] = 65.0
    elif mutation_kind == "objective_markers":
        central_marker = next(
            marker
            for marker in setup_payload["objective_markers"]
            if marker["objective_marker_id"].endswith("center-central")
        )
        central_marker["x_inches"] = 35.0
    elif mutation_kind == "deployment_zones":
        setup_payload["deployment_zones"].pop()
    else:
        setup_payload["terrain_features"].append(
            _blocking_terrain_feature(x=30.0, y=22.0).to_payload()
        )

    expected_error = {
        "source_identity": "source package identity drifted",
        "primary_mission": "Primary mission assignment drifted",
    }.get(mutation_kind, "canonical layoutless setup drifted from source")
    with pytest.raises(GameLifecycleError, match=expected_error):
        GameConfig.from_payload(payload)


def test_canonical_layoutless_setup_rejects_runtime_battlefield_dimension_drift() -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    state = GameState.from_config(_config(mission_setup=setup))
    battlefield = BattlefieldRuntimeState(
        battlefield_id="phase11a-canonical-layoutless-runtime",
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        placed_armies=(),
        terrain_features=setup.terrain_features,
    )
    drifted_battlefield = replace(battlefield, battlefield_width_inches=99.0)

    with pytest.raises(GameLifecycleError, match="battlefield runtime geometry drifted"):
        state.record_battlefield_state(drifted_battlefield)


@pytest.mark.parametrize("mutation_path", ["record", "replace"])
def test_custom_layoutless_setup_rejects_runtime_battlefield_dimension_drift(
    mutation_path: str,
) -> None:
    state, battlefield = _custom_layoutless_state_and_battlefield()
    if mutation_path == "replace":
        state.record_battlefield_state(battlefield)
    drifted_battlefield = replace(
        battlefield,
        battlefield_width_inches=99.0,
        battlefield_depth_inches=77.0,
    )
    mutate_battlefield = (
        state.record_battlefield_state
        if mutation_path == "record"
        else state.replace_battlefield_state
    )

    with pytest.raises(GameLifecycleError, match="battlefield runtime geometry drifted"):
        mutate_battlefield(drifted_battlefield)


def test_custom_layoutless_setup_rejects_runtime_battlefield_dimension_drift_from_payload() -> None:
    state, battlefield = _custom_layoutless_state_and_battlefield()
    state.record_battlefield_state(battlefield)
    payload = state.to_payload()
    battlefield_payload = payload["battlefield_state"]
    assert battlefield_payload is not None
    battlefield_payload["battlefield_width_inches"] = 99.0
    battlefield_payload["battlefield_depth_inches"] = 77.0

    with pytest.raises(GameLifecycleError, match="battlefield runtime geometry drifted"):
        GameState.from_payload(payload)


@pytest.mark.parametrize("mutation_path", ["record", "replace"])
def test_canonical_layoutless_setup_rejects_runtime_battlefield_terrain_drift(
    mutation_path: str,
) -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    state = GameState.from_config(_config(mission_setup=setup))
    battlefield = BattlefieldRuntimeState(
        battlefield_id="phase11a-canonical-layoutless-runtime-terrain",
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        placed_armies=(),
        terrain_features=setup.terrain_features,
    )
    if mutation_path == "replace":
        state, _reserve_state = _battle_state_with_mission_setup(
            attacker_player_id="player-a",
            defender_player_id="player-b",
        )
        assert state.battlefield_state is not None
        battlefield = state.battlefield_state
    drifted_battlefield = replace(
        battlefield,
        terrain_features=(_blocking_terrain_feature(x=30.0, y=22.0),),
    )
    mutate_battlefield = (
        state.record_battlefield_state
        if mutation_path == "record"
        else state.replace_battlefield_state
    )

    with pytest.raises(GameLifecycleError, match="battlefield runtime geometry drifted"):
        mutate_battlefield(drifted_battlefield)


def test_battlefield_layout_and_mission_setup_reject_orphan_logical_terrain_group() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "purge-the-foe-vs-purge-the-foe-layout-1"
    layout = mission_pack.battlefield_layout(layout_id)
    grouped_layout_area = next(
        area
        for area in layout.terrain_areas
        if area.logical_terrain_area_id != area.terrain_area_id
    )
    invalid_layout_areas = (
        *(
            replace(area, logical_terrain_area_id="orphan-logical-terrain-area")
            if area.terrain_area_id == grouped_layout_area.terrain_area_id
            else area
            for area in layout.terrain_areas
        ),
    )

    with pytest.raises(MissionPackError, match="at least two physical areas"):
        replace(layout, terrain_areas=invalid_layout_areas)

    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    invalid_setup_areas = (
        *(
            replace(area, logical_terrain_area_id="orphan-logical-terrain-area")
            if area.terrain_area_id == grouped_layout_area.terrain_area_id
            else area
            for area in setup.terrain_areas
        ),
    )

    with pytest.raises(MissionSetupError, match="at least two physical areas"):
        replace(setup, terrain_areas=invalid_setup_areas)


def test_mission_setup_from_payload_rejects_out_of_bounds_terrain() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    setup = replace(setup, terrain_features=(_blocking_terrain_feature(x=30.0, y=22.0),))
    payload = setup.to_payload()
    payload["terrain_features"][0]["footprint_width_inches"] = 1000.0
    payload["terrain_features"][0]["rules_footprint_polygon"] = [
        {"x_inches": -470.0, "y_inches": 20.0},
        {"x_inches": 530.0, "y_inches": 20.0},
        {"x_inches": 530.0, "y_inches": 24.0},
        {"x_inches": -470.0, "y_inches": 24.0},
    ]

    with pytest.raises(MissionSetupError, match="terrain feature x is outside"):
        MissionSetup.from_payload(payload)


def test_mission_setup_from_payload_wraps_invalid_logical_terrain_identity() -> None:
    layout_id = "purge-the-foe-vs-purge-the-foe-layout-1"
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id=f"mission-{layout_id}",
        terrain_layout_id=layout_id,
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    payload = setup.to_payload()
    cast(dict[str, object], payload["terrain_areas"][0]).pop("logical_terrain_area_id")

    with pytest.raises(MissionSetupError, match="terrain-area payload is invalid"):
        MissionSetup.from_payload(payload)


def test_game_state_round_trips_populated_mission_setup() -> None:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    state = GameState.from_config(_config(mission_setup=mission_setup))

    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_phase17n_battlefield_provenance_survives_config_and_projection() -> None:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    config = _config(mission_setup=mission_setup)
    round_tripped = GameConfig.from_payload(config.to_payload())

    assert round_tripped.to_payload() == config.to_payload()
    assert round_tripped.mission_setup is not None
    assert all(
        feature.source_id is not None
        and event_layouts.BATTLEFIELD_PACKAGE_HASH in feature.source_id
        for feature in round_tripped.mission_setup.terrain_features
    )

    state = GameState.from_config(round_tripped)
    armies = _mustered_armies(round_tripped)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase17n-provenance-battlefield",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=round_tripped.mission_setup.terrain_features,
    )
    state.record_battlefield_state(scenario.battlefield_state)
    projection = project_battlefield_view(
        state=state,
        visible_model_ids=frozenset(),
        pending_request_id=None,
        selected_entity_ids=(),
        legal_option_ids=(),
    )

    assert projection is not None
    projected_features = projection["authoritative"]["terrain_features_by_id"].values()
    assert {feature["classification"] for feature in projected_features} == {
        "dense",
        "light",
    }
    assert all(
        feature["source_id"] is not None
        and event_layouts.BATTLEFIELD_PACKAGE_HASH in feature["source_id"]
        for feature in projected_features
    )


def test_hidden_secondary_and_challenger_cards_do_not_leak_to_opponent_payload() -> None:
    mission_pack = chapter_approved_2026_27_mission_pack()
    secondary = mission_pack.secondary_mission("bring-it-down")
    challenger = mission_pack.challenger_card("strategic-retreat")

    hidden_secondary = secondary.to_public_payload(
        owner_player_id="player-a",
        viewer_player_id="player-b",
        revealed=False,
    )
    hidden_challenger = challenger.to_public_payload(
        owner_player_id="player-a",
        viewer_player_id="player-b",
        revealed=False,
    )
    own_secondary = secondary.to_public_payload(
        owner_player_id="player-a",
        viewer_player_id="player-a",
        revealed=False,
    )

    assert hidden_secondary == {
        "owner_player_id": "player-a",
        "hidden": True,
        "card_kind": "secondary",
    }
    assert hidden_challenger == {
        "owner_player_id": "player-a",
        "hidden": True,
        "card_kind": "challenger",
    }
    assert own_secondary["secondary_mission_id"] == "bring-it-down"
    assert "name" not in hidden_secondary
    assert "challenger_card_id" not in hidden_challenger


def test_live_reinforcements_without_mission_setup_fails_fast() -> None:
    state, reserve_state = _battle_state_without_mission_setup()
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=3,
    )

    with pytest.raises(
        GameLifecycleError, match="Physical proposal context requires mission setup"
    ):
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11a-select-missing-setup",
        )


def test_live_reinforcements_use_mission_deployment_zones_for_round_2_restriction() -> None:
    state, reserve_state = _battle_state_with_mission_setup(
        attacker_player_id="player-b",
        defender_player_id="player-a",
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
    )
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=2,
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11a-select-reserve",
        )
    )
    reserve_unit = _reserve_unit(state=state, reserve_state=reserve_state)
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_enemy_deployment_zone_center_pose(state=state, player_id="player-a"),
    )

    invalid_status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=placement,
        result_id="phase11a-place-reserve",
    )

    assert invalid_status is not None
    assert (
        ReservePlacementViolationCode.STRATEGIC_RESERVES_ENEMY_DEPLOYMENT_ZONE.value
        in _violation_codes(invalid_status)
    )


def test_live_reinforcements_use_manifested_battlefield_terrain_for_endpoint_validation() -> None:
    state, reserve_state = _battle_state_with_mission_setup(
        attacker_player_id="player-a",
        defender_player_id="player-b",
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        reserve_base_diameter_mm=200.0,
        custom_layoutless=True,
    )
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=3,
    )
    reserve_unit = _reserve_unit(state=state, reserve_state=reserve_state)
    placement = _single_model_reserve_placement(
        reserve_unit=reserve_unit,
        pose=_south_edge_touching_pose(reserve_unit=reserve_unit, x=6.0),
    )
    pose = _first_placement_pose(placement)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            terrain_features=(
                _blocking_terrain_feature(
                    x=pose["x"],
                    y=pose["y"],
                ),
            ),
        )
    )
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11a-select-terrain",
        )
    )

    invalid_status = _submit_reserve_placement_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        reserve_unit=reserve_unit,
        placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=placement,
        result_id="phase11a-place-terrain",
    )

    assert invalid_status is not None
    assert ReservePlacementViolationCode.TERRAIN_ENDPOINT_ILLEGAL.value in _violation_codes(
        invalid_status
    )


def _battle_state_with_mission_setup(
    *,
    attacker_player_id: str,
    defender_player_id: str,
    mission_pool_entry_id: str = PHASE16A_MISSION_POOL_ENTRY_ID,
    terrain_layout_id: str = PHASE16A_BATTLEFIELD_LAYOUT_ID,
    reserve_base_diameter_mm: float = 32.0,
    custom_layoutless: bool = False,
) -> tuple[GameState, ReserveState]:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=mission_pool_entry_id,
        terrain_layout_id=terrain_layout_id,
        attacker_player_id=attacker_player_id,
        attacker_force_disposition_id="take-and-hold",
        defender_player_id=defender_player_id,
        defender_force_disposition_id="purge-the-foe",
    )
    if custom_layoutless:
        mission_setup = replace(
            mission_setup,
            deployment_map_id="phase11a-custom-deployment-map",
            terrain_layout_id="phase11a-custom-terrain-layout",
        )
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    armies = _with_single_model_reserve_unit(
        armies,
        base_diameter_mm=reserve_base_diameter_mm,
    )
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11a-battlefield",
        armies=armies,
        battlefield_width_inches=mission_setup.battlefield_width_inches,
        battlefield_depth_inches=mission_setup.battlefield_depth_inches,
        terrain_features=mission_setup.terrain_features,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _ruleset().mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, reserve_state


def _battle_state_without_mission_setup() -> tuple[GameState, ReserveState]:
    config = _config(mission_setup=None)
    armies = _mustered_armies(config)
    armies = _with_single_model_reserve_unit(armies, base_diameter_mm=32.0)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    placed_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11a-missing-setup-battlefield",
        armies=armies,
    )
    reserve_unit = armies[0].unit_by_id("army-alpha:intercessor-unit-1")
    battlefield_state = placed_scenario.battlefield_state.without_unit_placement(
        reserve_unit.unit_instance_id
    )
    state.record_battlefield_state(battlefield_state)
    state.stage = GameLifecycleStage.BATTLE
    state.setup_step_index = None
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    state.battle_round = 1
    state.active_player_id = "player-a"
    reserve_state = ReserveState.declared_before_battle(
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        reserve_kind=ReserveKind.STRATEGIC_RESERVES,
        destruction_deadline_policy=ReserveDestructionTimingPolicy.from_mission_policy(
            _ruleset().mission_policy
        ),
    )
    state.record_reserve_state(reserve_state)
    return state, reserve_state


def _enter_reinforcements_choice(
    *,
    state: GameState,
    battle_round: int,
) -> tuple[MovementPhaseHandler, DecisionController, DecisionRequest]:
    state.battle_round = battle_round
    state.movement_phase_state = MovementPhaseState(
        battle_round=battle_round,
        active_player_id="player-a",
        selected_unit_ids=("army-alpha:intercessor-unit-2",),
        moved_unit_ids=("army-alpha:intercessor-unit-2",),
    )
    handler = MovementPhaseHandler(ruleset_descriptor=_ruleset())
    decisions = DecisionController()
    status = handler.begin_phase(state=state, decisions=decisions)
    return handler, decisions, _decision_request(status)


def _submit_handler_decision(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    option_id: str,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult.for_request(
        result_id=result_id,
        request=request,
        selected_option_id=option_id,
    )
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _submit_reserve_placement_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    reserve_unit: UnitInstance,
    placement_kind: BattlefieldPlacementKind,
    attempted_placement: UnitPlacement,
    result_id: str,
) -> LifecycleStatus | None:
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    payload = PlacementProposalPayload(
        proposal_request_id=proposal.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=reserve_unit.unit_instance_id,
        placement_kind=placement_kind,
        attempted_placement=attempted_placement,
    ).to_payload()
    return _submit_parameterized_handler_payload(
        handler=handler,
        state=state,
        decisions=decisions,
        request=request,
        payload=validate_json_value(payload),
        result_id=result_id,
    )


def _submit_parameterized_handler_payload(
    *,
    handler: MovementPhaseHandler,
    state: GameState,
    decisions: DecisionController,
    request: DecisionRequest,
    payload: JsonValue,
    result_id: str,
) -> LifecycleStatus | None:
    result = DecisionResult(
        result_id=result_id,
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=payload,
    )
    invalid_status = handler.invalid_proposal_submission_status(
        state=state,
        request=request,
        result=result,
        decisions=decisions,
    )
    if invalid_status is not None:
        return invalid_status
    decisions.submit_result(result)
    return handler.apply_decision(state=state, decisions=decisions, result=result)


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.decision_request is not None
    return status.decision_request


def _reserve_unit(*, state: GameState, reserve_state: ReserveState) -> UnitInstance:
    army = state.army_definition_for_player(reserve_state.player_id)
    assert army is not None
    return army.unit_by_id(reserve_state.unit_instance_id)


def _single_model_reserve_placement(*, reserve_unit: UnitInstance, pose: Pose) -> UnitPlacement:
    return UnitPlacement(
        army_id="army-alpha",
        player_id="player-a",
        unit_instance_id=reserve_unit.unit_instance_id,
        model_placements=(
            ModelPlacement(
                army_id="army-alpha",
                player_id="player-a",
                unit_instance_id=reserve_unit.unit_instance_id,
                model_instance_id=reserve_unit.own_models[0].model_instance_id,
                pose=pose,
            ),
        ),
    )


def _south_edge_touching_pose(*, reserve_unit: UnitInstance, x: float) -> Pose:
    return Pose.at(
        x=x,
        y=_base_radius_inches(reserve_unit),
        z=0.0,
        facing_degrees=0.0,
    )


def _enemy_deployment_zone_center_pose(*, state: GameState, player_id: str) -> Pose:
    assert state.mission_setup is not None
    zone = state.mission_setup.enemy_deployment_zones_for_player(player_id)[0]
    return Pose.at(
        x=(zone.min_x + zone.max_x) / 2.0,
        y=(zone.min_y + zone.max_y) / 2.0,
        z=0.0,
        facing_degrees=0.0,
    )


def _first_placement_pose(placement: UnitPlacement) -> dict[str, float]:
    pose = placement.model_placements[0].pose
    return {"x": pose.position.x, "y": pose.position.y}


def _base_radius_inches(reserve_unit: UnitInstance) -> float:
    return reserve_unit.own_models[0].geometry.primary_part().radius_x_inches


def _blocking_terrain_feature(*, x: float, y: float) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase11a-live-blocking-terrain",
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=x,
            center_y_inches=y,
            width_inches=4.0,
            depth_inches=4.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=x,
            center_y_inches=y,
            width_inches=4.0,
            depth_inches=4.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="center-wall",
                center_x_inches=x,
                center_y_inches=y,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
        source_id="phase11a-live-blocking-terrain",
    )


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _violation_codes(status: LifecycleStatus) -> tuple[str, ...]:
    payload = status.payload
    assert isinstance(payload, dict)
    violations = payload["violations"]
    assert isinstance(violations, list)
    codes: list[str] = []
    for violation in violations:
        assert isinstance(violation, dict)
        code = violation["violation_code"]
        assert isinstance(code, str)
        codes.append(code)
    return tuple(sorted(codes))


def _objective_coordinate_snapshot(
    mission_pack: MissionPackDefinition,
) -> dict[str, dict[str, tuple[float, float]]]:
    return {
        deployment_map.deployment_map_id: {
            marker.objective_marker_id.removeprefix(f"{deployment_map.deployment_map_id}-"): (
                marker.x_inches,
                marker.y_inches,
            )
            for marker in deployment_map.objective_markers
        }
        for deployment_map in mission_pack.deployment_maps
    }


def _config(*, mission_setup: MissionSetup | None) -> GameConfig:
    source_catalog = ArmyCatalog.phase9a_canonical_content_pack()
    catalog = replace(
        source_catalog,
        detachments=tuple(
            replace(
                detachment,
                force_disposition_ids=("purge-the-foe", "take-and-hold"),
            )
            if detachment.detachment_id == "core-combined-arms"
            else detachment
            for detachment in source_catalog.detachments
        ),
    )
    player_a_force_disposition_id = (
        "purge-the-foe"
        if mission_setup is None
        else mission_setup.force_disposition_id_for_player("player-a")
    )
    player_b_force_disposition_id = (
        "purge-the-foe"
        if mission_setup is None
        else mission_setup.force_disposition_id_for_player("player-b")
    )
    return GameConfig(
        game_id="phase11a-game",
        allow_legacy_non_strict_rosters=True,
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
                force_disposition_id=player_a_force_disposition_id,
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
                force_disposition_id=player_b_force_disposition_id,
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup,
    )


def _custom_layoutless_mission_setup() -> MissionSetup:
    setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2026_27_mission_pack(),
        mission_pool_entry_id=PHASE16A_MISSION_POOL_ENTRY_ID,
        terrain_layout_id=PHASE16A_BATTLEFIELD_LAYOUT_ID,
        attacker_player_id="player-a",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-b",
        defender_force_disposition_id="purge-the-foe",
    )
    return replace(
        setup,
        deployment_map_id="phase11a-custom-deployment-map",
        terrain_layout_id="phase11a-custom-terrain-layout",
        battlefield_width_inches=60.0,
        battlefield_depth_inches=44.0,
        objective_markers=(),
        deployment_zones=(),
        battlefield_regions=(),
        terrain_areas=(),
        objective_terrain_areas=(),
        terrain_features=(),
    )


def _custom_layoutless_state_and_battlefield() -> tuple[GameState, BattlefieldRuntimeState]:
    setup = _custom_layoutless_mission_setup()
    config = _config(mission_setup=setup)
    armies = _mustered_armies(config)
    state = GameState.from_config(config)
    for army in armies:
        state.record_army_definition(army)
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase11a-custom-layoutless-runtime-dimensions",
        armies=armies,
        battlefield_width_inches=setup.battlefield_width_inches,
        battlefield_depth_inches=setup.battlefield_depth_inches,
        terrain_features=(_blocking_terrain_feature(x=30.0, y=22.0),),
    )
    return state, scenario.battlefield_state


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2026_27(
        descriptor_version="core-v2-phase11a-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
    force_disposition_id: str,
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_ids=("core-combined-arms",),
        ),
        force_disposition_id=force_disposition_id,
        unit_selections=tuple(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            )
            for unit_selection_id in unit_selection_ids
        ),
    )


def _mustered_armies(config: GameConfig) -> tuple[ArmyDefinition, ...]:
    return tuple(
        muster_army(catalog=config.army_catalog, request=request)
        for request in config.army_muster_requests
    )


def _with_single_model_reserve_unit(
    armies: tuple[ArmyDefinition, ...],
    *,
    base_diameter_mm: float,
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id != "army-alpha":
            updated_armies.append(army)
            continue
        reserve_unit = army.unit_by_id("army-alpha:intercessor-unit-1")
        updated_unit = _single_model_unit(reserve_unit, base_diameter_mm=base_diameter_mm)
        updated_armies.append(
            replace(
                army,
                units=tuple(
                    updated_unit if unit.unit_instance_id == updated_unit.unit_instance_id else unit
                    for unit in army.units
                ),
            )
        )
    return tuple(updated_armies)


def _single_model_unit(unit: UnitInstance, *, base_diameter_mm: float) -> UnitInstance:
    base_size = BaseSizeDefinition.circular(base_diameter_mm)
    model = replace(
        unit.own_models[0],
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            geometry_source_id="phase11a-reserve-base",
            keywords=unit.keywords,
        ),
    )
    return replace(unit, own_models=(model,))
