from __future__ import annotations

import json
import math
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZoneCircleCutout,
    DeploymentZoneShape,
)
from warhammer40k_core.core.missions import (
    BattlefieldLayoutDefinition,
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    ObjectiveMarkerDefinitionPayload,
    ObjectiveMarkerRole,
    objective_marker_role_from_token,
)
from warhammer40k_core.core.terrain_areas import TerrainAreaLocalTransform
from warhammer40k_core.core.terrain_display import TerrainDisplayPoint
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_pack_for_id,
    mission_scoring_policy_from_setup,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    FinalScoringResult,
    ScoringWindowKind,
    ScoringWindowState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
)
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_06_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_patches,
)


def test_phase17j_event_companion_package_identity_and_payload_round_trip() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    source_package = mission_pack.source_package
    payload = mission_pack.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = cast(MissionPackDefinitionPayload, json.loads(encoded))

    assert mission_pack.mission_pack_id == "11e-warhammer-event-companion-2026-06"
    assert source_package.to_payload() == {
        "edition_id": "warhammer_40000_11th",
        "mission_pack_id": "11e-warhammer-event-companion-2026-06",
        "source_package_id": "gw-11e-warhammer-event-companion-v1-0-2026-06",
        "source_title": "Warhammer Event Companion v1.0",
        "source_version": "1.0",
        "source_commit_or_import_hash": source_package.source_commit_or_import_hash,
        "imported_at_schema_version": "core-v2-event-companion-source-v1",
    }
    assert MissionSourcePackageDefinition.from_payload(source_package.to_payload()) == (
        source_package
    )
    assert MissionPackDefinition.from_payload(decoded).to_payload() == payload
    assert "<" not in encoded
    assert "object at 0x" not in encoded

    assert event_source.package_identity().to_payload() == {
        "source_kind": "warhammer_event_companion",
        "document_version": "1.0",
        "event_mode": "warhammer_event",
        "battlefield_size": "44x60_inches",
        "excludes_deployment_cards": True,
        "excludes_twist_cards": True,
        "source_id": "gw-11e-warhammer-event-companion-v1-0-2026-06:package-identity",
    }


def test_phase17j_event_sequence_and_secondary_procedure_are_explicit() -> None:
    sequence = event_source.mission_sequence_descriptor()
    tactical = event_source.tactical_secondary_procedure()
    fixed = event_source.fixed_secondary_procedure()

    assert tuple(step.step_id for step in sequence.steps) == (
        "muster_armies",
        "determine_primary_missions",
        "determine_layout",
        "create_the_battlefield",
        "determine_attacker_and_defender",
        "select_secondary_missions",
        "declare_battle_formations",
        "deploy_armies",
        "redeploy_units",
        "determine_first_turn",
        "resolve_prebattle_rules",
        "begin_battle",
        "end_battle",
        "determine_victor",
    )
    assert sequence.steps[7].actor_policy == "defender_first_alternating"
    assert sequence.steps[8].actor_policy == "attacker_first_alternating"
    assert sequence.steps[9].actor_policy == "roll_off_winner_takes_first"
    assert sequence.steps[10].actor_policy == "first_turn_player_first"
    assert sequence.steps[12].actor_policy == "after_five_battle_rounds_continue_tabled_players"
    assert sequence.steps[13].actor_policy == "battle_ready_then_vp_total_then_draw_if_tied"

    assert tactical.draw_timing == "start_of_command_phase"
    assert tactical.draw_count == 2
    assert tactical.drawn_cards_become_active is True
    assert tactical.once_per_battle_replacement_timing == "end_of_command_phase"
    assert tactical.replacement_cost_cp == 1
    assert tactical.replacement_discard_count == 1
    assert tactical.replacement_draw_count == 1
    assert tactical.end_turn_scoring_order == "active_player_first"
    assert tactical.achieved_discard_requires_vp is True
    assert tactical.own_turn_cp_discard_minimum == 1
    assert tactical.own_turn_cp_reward == 1

    assert fixed.selected_count == 2
    assert fixed.hidden_until_reveal is True
    assert fixed.revealed_face_up is True
    assert fixed.discardable is False
    assert fixed.active_duration == "whole_battle"


def test_phase17j_mission_card_scoring_grammar_records_official_rules() -> None:
    grammar = event_source.mission_card_scoring_grammar()
    rules = {rule.token: rule for rule in grammar.rules}
    payload = grammar.to_payload()

    assert tuple(rules) == grammar.supported_tokens
    assert rules["cumulative_condition"].semantics == (
        "score_normal_and_cumulative_vp_when_cumulative_condition_is_achieved"
    )
    assert rules["exclusive_or_condition"].engine_contract == (
        "do_not_sum_exclusive_or_branches_for_the_same_card"
    )
    assert rules["exactly_one_condition"].semantics == (
        "underlined_one_means_exactly_one_not_one_or_more"
    )
    assert rules["leaves_battlefield_event"].semantics == (
        "unit_destroyed_embarks_or_is_removed_from_battlefield_by_rule"
    )
    assert rules["vp_up_to_limit"].engine_contract == (
        "apply_rule_cap_before_adding_award_to_the_vp_ledger"
    )
    assert rules["when_drawn_tactical_only"].engine_contract == (
        "ignore_when_drawn_sections_for_fixed_secondary_mode"
    )
    assert payload["rules"] == [rule.to_payload() for rule in grammar.rules]
    assert "<" not in json.dumps(payload, sort_keys=True)


def test_phase17j_matrix_layouts_and_setups_are_complete() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout_ids = {layout.terrain_layout_id for layout in mission_pack.terrain_layout_templates}
    deployment_map_ids = {
        deployment.deployment_map_id for deployment in mission_pack.deployment_maps
    }
    pool_layout_ids = {entry.terrain_layout_ids[0] for entry in mission_pack.mission_pool_entries}
    extracted_layout_ids = {
        "take-and-hold-vs-take-and-hold-layout-1",
        "take-and-hold-vs-take-and-hold-layout-2",
        "take-and-hold-vs-take-and-hold-layout-3",
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-2",
        "disruption-vs-reconnaissance-layout-3",
    }
    disruption_reconnaissance_layout_ids = {
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-2",
        "disruption-vs-reconnaissance-layout-3",
    }

    assert len(mission_pack.primary_missions) == 25
    assert len(mission_pack.primary_mission_matrix_cells) == 25
    assert all(
        cell.source_status is MissionSourceStatus.IMPLEMENTED
        for cell in mission_pack.primary_mission_matrix_cells
    )
    assert len(layout_ids) == 45
    assert len(mission_pack.battlefield_layouts) == 6
    assert len(mission_pack.terrain_area_footprint_templates) == 5
    assert len(deployment_map_ids) == 45
    assert len(mission_pack.mission_pool_entries) == 45
    assert pool_layout_ids == layout_ids
    assert all(
        len(cell.battlefield_layout_ids) == 3 for cell in mission_pack.primary_mission_matrix_cells
    )
    assert all(
        layout_id in layout_ids
        for cell in mission_pack.primary_mission_matrix_cells
        for layout_id in cell.battlefield_layout_ids
    )

    for entry in mission_pack.mission_pool_entries:
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=entry.mission_pool_entry_id,
            attacker_player_id="player-alpha",
            defender_player_id="player-beta",
        )
        assert setup.battlefield_width_inches == 44.0
        assert setup.battlefield_depth_inches == 60.0
        terrain_layout_id = entry.terrain_layout_ids[0]
        if terrain_layout_id in extracted_layout_ids:
            assert setup.battlefield_layout_id == entry.terrain_layout_ids[0]
            assert setup.terrain_features == ()
            assert len(setup.terrain_areas) == 16
            assert len(setup.battlefield_regions) == 5
        else:
            assert setup.battlefield_layout_id is None
            assert setup.terrain_areas == ()
            assert setup.battlefield_regions == ()
            assert setup.terrain_features == ()
        expected_objective_count = (
            6 if terrain_layout_id in disruption_reconnaissance_layout_ids else 5
        )
        assert len(setup.objective_markers) == expected_objective_count
        assert len(setup.deployment_zones) == 2


def test_phase17j_terrain_area_footprint_templates_match_source_polygons() -> None:
    templates = {
        template.footprint_template_id: template
        for template in event_source.terrain_area_footprint_templates()
    }
    expected_templates = {
        "FOOTPRINT_6X2": (
            6.1,
            2.7,
            (
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
        ),
        "FOOTPRINT_6X4": (
            6.5,
            4.5,
            (
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
        ),
        "FOOTPRINT_10X2_5": (
            10.0,
            3.6,
            (
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
        ),
        "FOOTPRINT_7X11_5": (
            7.6,
            11.5,
            (
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
        ),
        "FOOTPRINT_8X11_5_POLYGON": (
            12.0,
            8.0,
            (
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
        ),
    }

    assert set(templates) == set(expected_templates)
    for template_id, (width, depth, expected_vertices) in expected_templates.items():
        template = templates[template_id]
        assert template.bounding_width_inches == width
        assert template.bounding_depth_inches == depth
        assert _terrain_display_points(template.polygon_vertices_inches) == expected_vertices


def test_phase17j_take_and_hold_layout_a_terrain_area_specs_are_corner_anchored() -> None:
    source = cast(
        event_layouts.EventBattlefieldLayoutSource,
        _source_extracted_layout_source("take-and-hold-vs-take-and-hold-layout-1"),
    )
    expected_anchors = {
        "7x11-5-upper-right": ("FOOTPRINT_7X11_5", 40.0, 35.5, 180.0),
        "7x11-5-upper-left": ("FOOTPRINT_7X11_5", 14.0, 54.0, 0.0),
        "10x2-5-upper-left": ("FOOTPRINT_10X2_5", 12.0, 43.5, 180.0),
        "6x2-upper-center": ("FOOTPRINT_6X2", 27.0, 42.5, 0.0),
        "6x2-east-midfield": ("FOOTPRINT_6X2", 40.0, 28.0, 180.0),
        "6x4-lower-left": ("FOOTPRINT_6X4", 11.0, 13.0, 0.0),
        "6x4-east-midfield": ("FOOTPRINT_6X4", 36.0, 28.0, -90.0),
        "8x11-5-polygon-central-north": (
            "FOOTPRINT_8X11_5_POLYGON",
            16.25,
            35.0,
            0.0,
        ),
    }
    source_anchors = {
        area_id: (template_id, anchor_x, anchor_y, rotation)
        for area_id, template_id, anchor_x, anchor_y, rotation in (source.terrain_area_specs)
    }
    layout = warhammer_event_companion_2026_06_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-1"
    )
    placed_areas = {
        area.terrain_area_id.removeprefix("take-and-hold-vs-take-and-hold-layout-1-"): area
        for area in layout.terrain_areas
        if area.source_transform == "explicit"
    }

    assert source_anchors == expected_anchors
    assert source.terrain_area_local_transform_specs == (
        ("6x2-upper-center", TerrainAreaLocalTransform.MIRROR_Y_AXIS),
    )
    assert source.objective_terrain_area_specs == (
        (
            "attacker-home",
            "Attacker Home Objective",
            "attacker_home",
            16.49,
            49.82,
            ("7x11-5-upper-left",),
        ),
        (
            "defender-home",
            "Defender Home Objective",
            "defender_home",
            25.76,
            12.72,
            ("7x11-5-lower-right",),
        ),
        (
            "central",
            "Central Objective",
            "central",
            22.02,
            30.0,
            (
                "8x11-5-polygon-central-north",
                "8x11-5-polygon-central-south",
            ),
        ),
        (
            "expansion-west",
            "West Expansion Objective",
            "expansion",
            7.4,
            19.16,
            ("7x11-5-lower-left",),
        ),
        (
            "expansion-east",
            "East Expansion Objective",
            "expansion",
            36.72,
            41.87,
            ("7x11-5-upper-right",),
        ),
    )
    assert set(placed_areas) == set(expected_anchors)
    for area_id, (_, anchor_x, anchor_y, _) in expected_anchors.items():
        first_point = placed_areas[area_id].footprint_polygon[0]
        assert _rounded_terrain_display_point(first_point) == (anchor_x, anchor_y)
    assert placed_areas["6x2-upper-center"].local_transform.value == "mirror_y_axis"


def test_phase17j_take_and_hold_layout_b_terrain_area_specs_are_corner_anchored() -> None:
    source = cast(
        event_layouts.EventBattlefieldLayoutSource,
        _source_extracted_layout_source("take-and-hold-vs-take-and-hold-layout-2"),
    )
    expected_anchors = {
        "7x11-5-left-home": ("FOOTPRINT_7X11_5", 11.0, 24.0, 180.0),
        "8x11-5-polygon-central-north": (
            "FOOTPRINT_8X11_5_POLYGON",
            17.0,
            24.25,
            90.0,
        ),
        "7x11-5-north-expansion": (
            "FOOTPRINT_7X11_5",
            19.5,
            46.0,
            90.0,
        ),
        "10x2-5-north-west": (
            "FOOTPRINT_10X2_5",
            12.5,
            48.75,
            246.0,
        ),
        "6x4-north-east": ("FOOTPRINT_6X4", 41.0, 50.0, 210.0),
        "6x4-north-west": ("FOOTPRINT_6X4", 29.75, 17.0, 210.0),
        "6x2-north-east": ("FOOTPRINT_6X2", 37.5, 41.0, 125.0),
        "6x2-north-west": ("FOOTPRINT_6X2", 10.25, 49.75, 145.0),
    }
    source_anchors = {
        area_id: (template_id, anchor_x, anchor_y, rotation)
        for area_id, template_id, anchor_x, anchor_y, rotation in (source.terrain_area_specs)
    }
    layout = warhammer_event_companion_2026_06_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-2"
    )
    placed_areas = {
        area.terrain_area_id.removeprefix("take-and-hold-vs-take-and-hold-layout-2-"): area
        for area in layout.terrain_areas
        if area.source_transform == "explicit"
    }

    assert source_anchors == expected_anchors
    assert source.objective_terrain_area_specs == (
        (
            "attacker-home",
            "Attacker Home Objective",
            "attacker_home",
            6.76,
            31.2,
            ("7x11-5-left-home",),
        ),
        (
            "defender-home",
            "Defender Home Objective",
            "defender_home",
            37.24,
            28.67,
            ("7x11-5-right-home",),
        ),
        (
            "central",
            "Central Objective",
            "central",
            22.16,
            30.04,
            (
                "8x11-5-polygon-central-north",
                "8x11-5-polygon-central-south",
            ),
        ),
        (
            "expansion-south",
            "South Expansion Objective",
            "expansion",
            19.2,
            10.28,
            ("7x11-5-south-expansion",),
        ),
        (
            "expansion-north",
            "North Expansion Objective",
            "expansion",
            24.92,
            50.61,
            ("7x11-5-north-expansion",),
        ),
    )
    assert set(placed_areas) == set(expected_anchors)
    for area_id, (_, anchor_x, anchor_y, _) in expected_anchors.items():
        first_point = placed_areas[area_id].footprint_polygon[0]
        assert _rounded_terrain_display_point(first_point) == (anchor_x, anchor_y)


def test_phase17j_take_and_hold_layout_c_terrain_area_specs_are_corner_anchored() -> None:
    source = cast(
        event_layouts.EventBattlefieldLayoutSource,
        _source_extracted_layout_source("take-and-hold-vs-take-and-hold-layout-3"),
    )
    expected_anchors = {
        "7x11-5-north-west": ("FOOTPRINT_7X11_5", 11.25, 56.75, 315.0),
        "7x11-5-south-west": ("FOOTPRINT_7X11_5", 6.0, 16.5, 0.0),
        "8x11-5-polygon-central-north-west": (
            "FOOTPRINT_8X11_5_POLYGON",
            16.25,
            35.0,
            0.0,
        ),
        "10x2-5-north-center": (
            "FOOTPRINT_10X2_5",
            15.75,
            44.25,
            35.0,
        ),
        "6x4-north-west": ("FOOTPRINT_6X4", 11.0, 37.25, 90.0),
        "6x4-central-east": ("FOOTPRINT_6X4", 31.0, 30.75, 90.0),
        "6x2-west-midfield": ("FOOTPRINT_6X2", 2.75, 37.25, 0.0),
        "6x2-south-west": ("FOOTPRINT_6X2", 4.25, 24.5, 0.0),
    }
    source_anchors = {
        area_id: (template_id, anchor_x, anchor_y, rotation)
        for area_id, template_id, anchor_x, anchor_y, rotation in (source.terrain_area_specs)
    }
    layout = warhammer_event_companion_2026_06_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-3"
    )
    placed_areas = {
        area.terrain_area_id.removeprefix("take-and-hold-vs-take-and-hold-layout-3-"): area
        for area in layout.terrain_areas
        if area.source_transform == "explicit"
    }

    assert source_anchors == expected_anchors
    assert source.objective_terrain_area_specs == (
        (
            "attacker-home",
            "Attacker Home Objective",
            "attacker_home",
            9.45,
            50.3,
            ("7x11-5-north-west",),
        ),
        (
            "defender-home",
            "Defender Home Objective",
            "defender_home",
            34.55,
            9.7,
            ("7x11-5-south-east",),
        ),
        (
            "central",
            "Central Objective",
            "central",
            22.0,
            30.0,
            (
                "8x11-5-polygon-central-north-west",
                "8x11-5-polygon-central-south-east",
            ),
        ),
        (
            "expansion-south-west",
            "South-west Expansion Objective",
            "expansion",
            9.7,
            10.55,
            ("7x11-5-south-west",),
        ),
        (
            "expansion-north-east",
            "North-east Expansion Objective",
            "expansion",
            34.3,
            49.45,
            ("7x11-5-north-east",),
        ),
    )
    assert set(placed_areas) == set(expected_anchors)
    for area_id, (_, anchor_x, anchor_y, _) in expected_anchors.items():
        first_point = placed_areas[area_id].footprint_polygon[0]
        assert _rounded_terrain_display_point(first_point) == (anchor_x, anchor_y)


def test_phase17j_extracted_terrain_area_specs_anchor_first_vertices() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    for source in event_layouts.EXTRACTED_LAYOUTS:
        assert not any(
            area_id.startswith(("dense-", "light-")) for area_id, *_ in source.terrain_area_specs
        )
        assert not any(
            terrain_area_id.startswith(("dense-", "light-"))
            for objective_spec in source.objective_terrain_area_specs
            for terrain_area_id in objective_spec[-1]
        )
        layout = mission_pack.battlefield_layout(source.layout_id)
        placed_areas = {
            area.terrain_area_id.removeprefix(f"{source.layout_id}-"): area
            for area in layout.terrain_areas
            if area.source_transform == "explicit"
        }

        assert len(placed_areas) == len(source.terrain_area_specs)
        for area_id, _, anchor_x, anchor_y, _ in source.terrain_area_specs:
            first_point = placed_areas[area_id].footprint_polygon[0]
            assert _rounded_terrain_display_point(first_point) == (
                round(anchor_x, 6),
                round(anchor_y, 6),
            )


def test_phase17j_event_matrix_uses_pdf_source_pairings_not_chapter_approved_order() -> None:
    source_rows = event_source.event_primary_mission_matrix_source_rows()
    matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in event_source.primary_mission_matrix_rows()
    }

    assert len(source_rows) == 15
    assert len(matrix) == 25
    assert (
        source_rows[10].source_left_force_disposition_id,
        source_rows[10].source_right_force_disposition_id,
        source_rows[10].layout_source_page_start,
    ) == ("disruption", "reconnaissance", 39)
    assert (
        source_rows[11].source_left_force_disposition_id,
        source_rows[11].source_right_force_disposition_id,
        source_rows[11].layout_source_page_start,
    ) == ("disruption", "priority-assets", 42)
    assert (
        source_rows[13].source_left_force_disposition_id,
        source_rows[13].source_right_force_disposition_id,
        source_rows[13].layout_source_page_start,
    ) == ("reconnaissance", "priority-assets", 48)

    assert matrix[("take-and-hold", "disruption")].primary_mission_id == (
        "primary-determined-acquisition"
    )
    assert matrix[("disruption", "take-and-hold")].primary_mission_id == "primary-death-trap"
    assert matrix[("take-and-hold", "priority-assets")].primary_mission_id == (
        "primary-inescapable-dominion"
    )
    assert matrix[("priority-assets", "take-and-hold")].primary_mission_id == (
        "primary-secure-asset"
    )
    assert matrix[("purge-the-foe", "disruption")].primary_mission_id == "primary-punishment"
    assert matrix[("disruption", "purge-the-foe")].primary_mission_id == ("primary-delaying-action")
    assert matrix[("purge-the-foe", "priority-assets")].primary_mission_id == (
        "primary-destroyers-wrath"
    )
    assert matrix[("priority-assets", "purge-the-foe")].primary_mission_id == ("primary-vital-link")
    assert matrix[("disruption", "disruption")].primary_mission_id == "primary-outmaneuver"
    assert matrix[("disruption", "disruption")].primary_mission_name == "Outmanoeuvre"
    assert matrix[("disruption", "reconnaissance")].primary_mission_id == (
        "primary-smoke-and-mirrors"
    )
    assert matrix[("reconnaissance", "disruption")].primary_mission_id == (
        "primary-surveil-the-foe"
    )
    assert matrix[("reconnaissance", "priority-assets")].primary_mission_id == (
        "primary-search-and-scour"
    )
    assert matrix[("priority-assets", "reconnaissance")].primary_mission_id == (
        "primary-vanguard-operation"
    )
    assert matrix[("priority-assets", "priority-assets")].primary_mission_id == ("primary-sabotage")
    assert matrix[("reconnaissance", "disruption")].battlefield_layout_ids == (
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-2",
        "disruption-vs-reconnaissance-layout-3",
    )
    assert matrix[("priority-assets", "disruption")].battlefield_layout_ids == (
        "disruption-vs-priority-assets-layout-1",
        "disruption-vs-priority-assets-layout-2",
        "disruption-vs-priority-assets-layout-3",
    )
    assert matrix[("priority-assets", "reconnaissance")].battlefield_layout_ids == (
        "reconnaissance-vs-priority-assets-layout-1",
        "reconnaissance-vs-priority-assets-layout-2",
        "reconnaissance-vs-priority-assets-layout-3",
    )

    source_row_payload = source_rows[0].to_payload()
    assert source_row_payload == {
        "source_left_force_disposition_id": "take-and-hold",
        "source_right_force_disposition_id": "take-and-hold",
        "source_left_primary_mission_id": "primary-battlefield-dominance",
        "source_left_primary_mission_name": "Battlefield Dominance",
        "source_right_primary_mission_id": "primary-battlefield-dominance",
        "source_right_primary_mission_name": "Battlefield Dominance",
        "layout_pair_id": "take-and-hold-vs-take-and-hold",
        "layout_source_page_start": 9,
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-0-2026-06:"
            "primary-mission-matrix-source:take-and-hold-vs-take-and-hold"
        ),
    }
    assert "<" not in json.dumps(source_row_payload, sort_keys=True)


def test_phase17j_layout_descriptors_cover_source_pages_and_geometry_roles() -> None:
    descriptors = event_source.layout_descriptor_rows()
    layout_a = _layout_descriptor("take-and-hold", "take-and-hold", "a")
    layout_b = _layout_descriptor("take-and-hold", "take-and-hold", "b")
    layout_c = _layout_descriptor("take-and-hold", "take-and-hold", "c")
    disruption_layout_a = _layout_descriptor("disruption", "reconnaissance", "a")
    disruption_layout_b = _layout_descriptor("disruption", "reconnaissance", "b")
    disruption_layout_c = _layout_descriptor("disruption", "reconnaissance", "c")
    extracted_layout_ids = {
        layout_a.layout_id,
        layout_b.layout_id,
        layout_c.layout_id,
        disruption_layout_a.layout_id,
        disruption_layout_b.layout_id,
        disruption_layout_c.layout_id,
    }
    pending_descriptors = tuple(
        descriptor for descriptor in descriptors if descriptor.layout_id not in extracted_layout_ids
    )

    assert len(descriptors) == 45
    assert {descriptor.layout_variant for descriptor in descriptors} == {"a", "b", "c"}
    assert {descriptor.source_page for descriptor in descriptors} == set(range(9, 54))
    assert layout_a.battlefield_width_inches == 44.0
    assert layout_a.battlefield_depth_inches == 60.0
    assert layout_a.attacker_edge == "north"
    assert layout_a.defender_edge == "south"
    assert layout_b.battlefield_width_inches == 44.0
    assert layout_b.battlefield_depth_inches == 60.0
    assert layout_b.attacker_edge == "west"
    assert layout_b.defender_edge == "east"
    assert layout_c.battlefield_width_inches == 44.0
    assert layout_c.battlefield_depth_inches == 60.0
    assert layout_c.attacker_edge == "west"
    assert layout_c.defender_edge == "east"
    assert disruption_layout_a.battlefield_width_inches == 44.0
    assert disruption_layout_a.battlefield_depth_inches == 60.0
    assert disruption_layout_a.attacker_edge == "north"
    assert disruption_layout_a.defender_edge == "south"
    assert disruption_layout_b.battlefield_width_inches == 44.0
    assert disruption_layout_b.battlefield_depth_inches == 60.0
    assert disruption_layout_b.attacker_edge == "west"
    assert disruption_layout_b.defender_edge == "east"
    assert disruption_layout_c.battlefield_width_inches == 44.0
    assert disruption_layout_c.battlefield_depth_inches == 60.0
    assert disruption_layout_c.attacker_edge == "west"
    assert disruption_layout_c.defender_edge == "east"
    assert all(descriptor.battlefield_width_inches == 44.0 for descriptor in pending_descriptors)
    assert all(descriptor.battlefield_depth_inches == 60.0 for descriptor in pending_descriptors)
    assert all(len(descriptor.deployment_zone_shapes) == 2 for descriptor in descriptors)
    assert all(len(descriptor.player_territory_shapes) == 2 for descriptor in descriptors)
    assert all(
        len(shape.polygons) == 1
        for descriptor in descriptors
        for shape in (*descriptor.deployment_zone_shapes, *descriptor.player_territory_shapes)
    )
    for extracted_layout_c in (layout_c, disruption_layout_c):
        assert len(extracted_layout_c.no_mans_land_shape.polygons) == 4
        layout_c_payload = extracted_layout_c.to_payload()
        assert "no_mans_land_polygon" not in layout_c_payload
        assert cast(dict[str, object], layout_c_payload["no_mans_land_shape"])["polygons"] == [
            [[x, y] for x, y in polygon]
            for polygon in extracted_layout_c.no_mans_land_shape.polygons
        ]
    assert len(pending_descriptors) == 39
    assert all(len(descriptor.objective_points) == 5 for descriptor in pending_descriptors)
    assert all(
        len(descriptor.objective_points) == 5 for descriptor in (layout_a, layout_b, layout_c)
    )
    assert all(
        len(descriptor.objective_points) == 6
        for descriptor in (disruption_layout_a, disruption_layout_b, disruption_layout_c)
    )
    assert all(
        {"dense", "light"} <= {feature.density for feature in descriptor.terrain_features}
        for descriptor in (
            layout_a,
            layout_b,
            layout_c,
            disruption_layout_a,
            disruption_layout_b,
            disruption_layout_c,
        )
    )
    assert all(descriptor.terrain_features == () for descriptor in pending_descriptors)
    assert all(
        objective.objective_kind
        in {"attacker_home", "defender_home", "center", "central", "expansion"}
        for descriptor in descriptors
        for objective in descriptor.objective_points
    )
    assert layout_a.geometry_extraction_status == "layout_geometry_extracted"
    assert layout_b.geometry_extraction_status == "layout_geometry_extracted"
    assert layout_c.geometry_extraction_status == "layout_geometry_extracted"
    assert disruption_layout_a.geometry_extraction_status == "layout_geometry_extracted"
    assert disruption_layout_b.geometry_extraction_status == "layout_geometry_extracted"
    assert disruption_layout_c.geometry_extraction_status == "layout_geometry_extracted"
    assert all(
        descriptor.geometry_extraction_status
        == "layout_identity_source_page_bound_coordinates_pending"
        for descriptor in pending_descriptors
    )
    assert _layout_descriptor("take-and-hold", "disruption", "a").source_page == 15
    assert _layout_descriptor("take-and-hold", "reconnaissance", "a").source_page == 18
    assert _layout_descriptor("take-and-hold", "priority-assets", "a").source_page == 21
    assert _layout_descriptor("disruption", "reconnaissance", "a").source_page == 39
    assert _layout_descriptor("disruption", "priority-assets", "a").source_page == 42
    assert _layout_descriptor("reconnaissance", "priority-assets", "a").source_page == 48
    assert all(
        next(
            row
            for row in event_source.battlefield_layout_rows()
            if row.battlefield_layout_id == layout_id
        ).source_status
        == "event_companion_layout_geometry_extracted"
        for layout_id in extracted_layout_ids
    )
    assert all(
        row.source_status.endswith("layout_identity_coordinate_extraction_pending")
        for row in event_source.battlefield_layout_rows()
        if row.battlefield_layout_id not in extracted_layout_ids
    )


def test_phase17j_deployment_zone_layout_templates_match_source_shapes() -> None:
    template_shapes = dict(event_source.deployment_zone_layout_template_shapes())

    assert set(template_shapes) == {
        event_source.DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED,
        event_source.DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP,
        event_source.DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT,
        event_source.DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE,
        event_source.DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP,
        event_source.DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE,
    }
    assert _shape_polygons(template_shapes[event_source.DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED]) == (
        ((0.0, 0.0), (44.0, 0.0), (44.0, 12.0), (22.0, 12.0), (22.0, 20.0), (0.0, 20.0)),
    )
    assert _shape_polygons(
        template_shapes[event_source.DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP]
    ) == (((0.0, 0.0), (12.0, 0.0), (12.0, 60.0), (0.0, 60.0)),)
    assert _shape_polygons(
        template_shapes[event_source.DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE]
    ) == (((0.0, 0.0), (8.0, 0.0), (8.0, 30.0), (14.0, 30.0), (14.0, 60.0), (0.0, 60.0)),)
    assert _shape_polygons(
        template_shapes[event_source.DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP]
    ) == (((0.0, 0.0), (44.0, 0.0), (44.0, 18.0), (0.0, 18.0)),)
    assert _shape_polygons(template_shapes[event_source.DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE]) == (
        ((0.0, 60.0), (44.0, 60.0), (0.0, 30.0)),
    )

    quarter_cutout = template_shapes[event_source.DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT]
    assert quarter_cutout.contains_point(8.0, 8.0)
    assert not quarter_cutout.contains_point(22.0, 30.0)
    assert not quarter_cutout.contains_point(18.0, 28.0)
    assert len(quarter_cutout.polygons[0].vertices) > 4


def test_phase17j_deployment_zone_layout_matrix_matches_event_companion_source() -> None:
    expected_template_numbers: dict[tuple[str, str], tuple[int, int, int]] = {
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
    source_pairs = tuple(
        (row.source_left_force_disposition_id, row.source_right_force_disposition_id)
        for row in event_source.event_primary_mission_matrix_source_rows()
    )
    primary_matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in event_source.primary_mission_matrix_rows()
    }

    assert source_pairs == tuple(expected_template_numbers)
    for (left_id, right_id), template_numbers in expected_template_numbers.items():
        expected_layout_ids = tuple(
            f"{left_id}-vs-{right_id}-layout-{layout_number}" for layout_number in (1, 2, 3)
        )
        assert primary_matrix[(left_id, right_id)].battlefield_layout_ids == expected_layout_ids
        assert primary_matrix[(right_id, left_id)].battlefield_layout_ids == expected_layout_ids
        for layout_number, template_number in enumerate(template_numbers, start=1):
            assert _source_deployment_zone_layout_template_id(
                layout_id=f"{left_id}-vs-{right_id}-layout-{layout_number}",
                layout_number=layout_number,
            ) == _source_deployment_zone_layout_template_id_from_number(template_number)


def test_phase17j_known_layouts_use_canonical_deployment_zone_helpers() -> None:
    rows = {row.battlefield_layout_id: row for row in event_source.battlefield_layout_rows()}
    layout_a = rows["take-and-hold-vs-take-and-hold-layout-1"]
    layout_b = rows["take-and-hold-vs-take-and-hold-layout-2"]
    layout_c = rows["take-and-hold-vs-take-and-hold-layout-3"]
    take_vs_purge_a = rows["take-and-hold-vs-purge-the-foe-layout-1"]
    take_vs_purge_c = rows["take-and-hold-vs-purge-the-foe-layout-3"]
    take_vs_priority_a = rows["take-and-hold-vs-priority-assets-layout-1"]

    assert _shape_polygons(layout_a.deployment_zones[0].shape) == (
        ((0.0, 40.0), (22.0, 40.0), (22.0, 48.0), (44.0, 48.0), (44.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(layout_a.deployment_zones[1].shape) == (
        ((44.0, 20.0), (22.0, 20.0), (22.0, 12.0), (0.0, 12.0), (0.0, 0.0), (44.0, 0.0)),
    )
    assert _shape_polygons(layout_b.deployment_zones[0].shape) == (
        ((0.0, 0.0), (12.0, 0.0), (12.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(layout_b.deployment_zones[1].shape) == (
        ((44.0, 0.0), (32.0, 0.0), (32.0, 60.0), (44.0, 60.0)),
    )
    assert not layout_c.deployment_zones[0].shape.contains_point(22.0, 30.0)
    assert not layout_c.deployment_zones[1].shape.contains_point(22.0, 30.0)
    assert _shape_polygons(take_vs_purge_a.deployment_zones[0].shape) == (
        ((0.0, 0.0), (8.0, 0.0), (8.0, 30.0), (14.0, 30.0), (14.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(take_vs_purge_a.deployment_zones[1].shape) == (
        ((44.0, 0.0), (30.0, 0.0), (30.0, 30.0), (36.0, 30.0), (36.0, 60.0), (44.0, 60.0)),
    )
    assert _shape_polygons(take_vs_purge_c.deployment_zones[0].shape) == (
        ((0.0, 0.0), (44.0, 0.0), (44.0, 18.0), (0.0, 18.0)),
    )
    assert _shape_polygons(take_vs_purge_c.deployment_zones[1].shape) == (
        ((44.0, 42.0), (0.0, 42.0), (0.0, 60.0), (44.0, 60.0)),
    )
    assert _shape_polygons(take_vs_priority_a.deployment_zones[0].shape) == (
        ((0.0, 60.0), (44.0, 60.0), (0.0, 30.0)),
    )
    assert _shape_polygons(take_vs_priority_a.deployment_zones[1].shape) == (
        ((44.0, 30.0), (0.0, 0.0), (44.0, 0.0)),
    )
    assert take_vs_purge_c.terrain_features == ()

    descriptor = _layout_descriptor("take-and-hold", "purge-the-foe", "c")
    assert descriptor.attacker_edge == "south"
    assert descriptor.defender_edge == "north"


def test_phase17j_unmapped_deployment_zone_templates_keep_canonical_edges() -> None:
    assert _source_deployment_zone_layout_edges(
        event_source.DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE
    ) == ("west", "east")
    assert _source_deployment_zone_layout_edges(event_source.DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE) == (
        "north_west_corner",
        "south_east_corner",
    )

    stepped_shape = _source_deployment_zone_template_base_shape(
        event_source.DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE
    )
    triangle_shape = _source_deployment_zone_template_base_shape(
        event_source.DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE
    )

    assert _shape_polygons(
        _source_transform_deployment_zone_shape(
            stepped_shape,
            "point_reflection",
        )
    ) == (
        (
            (44.0, 0.0),
            (30.0, 0.0),
            (30.0, 30.0),
            (36.0, 30.0),
            (36.0, 60.0),
            (44.0, 60.0),
        ),
    )
    assert _shape_polygons(
        _source_transform_deployment_zone_shape(
            triangle_shape,
            "point_reflection",
        )
    ) == (((44.0, 30.0), (0.0, 0.0), (44.0, 0.0)),)


def test_phase17j_deployment_zone_helpers_fail_closed_for_unknown_shapes() -> None:
    unsupported_template = cast(
        event_source.DeploymentZoneLayoutTemplateId,
        "deployment-zone-layout-unsupported",
    )
    unsupported_transform = cast(
        event_source.DeploymentZoneShapeTransform,
        "diagonal_reflection",
    )
    base_shape = _source_deployment_zone_template_base_shape(
        event_source.DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP
    )
    cutout_shape = DeploymentZoneShape(
        polygons=base_shape.polygons,
        cutouts=(DeploymentZoneCircleCutout(center_x=1.0, center_y=1.0, radius=0.5),),
    )

    with pytest.raises(MissionPackError, match="Unsupported battlefield layout number"):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-vs-purge-the-foe-layout-9",
            layout_number=9,
        )
    with pytest.raises(
        MissionPackError,
        match="Battlefield layout number does not match layout ID",
    ):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-vs-purge-the-foe-layout-2",
            layout_number=1,
        )
    with pytest.raises(
        MissionPackError,
        match="Battlefield layout ID must include force disposition pair",
    ):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-layout-1",
            layout_number=1,
        )
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout matchup"):
        _source_deployment_zone_layout_template_id(
            layout_id="take-and-hold-vs-unknown-layout-1",
            layout_number=1,
        )
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout template"):
        _source_deployment_zone_shape_transforms(unsupported_template)
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout template"):
        _source_deployment_zone_template_base_shape(unsupported_template)
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout template"):
        _source_deployment_zone_layout_edges(unsupported_template)
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone shape transform"):
        _source_transform_deployment_zone_shape(
            base_shape,
            unsupported_transform,
        )
    with pytest.raises(MissionPackError, match="Battlefield layout ID must end in layout number"):
        _source_layout_number_from_layout_id("take-and-hold-vs-purge-the-foe-layout-z")
    with pytest.raises(MissionPackError, match="Unsupported extracted battlefield layout ID"):
        _source_extracted_deployment_zones(layout_id="take-and-hold-vs-purge-the-foe-layout-1")
    with pytest.raises(
        MissionPackError,
        match="Deployment-zone layout template transforms require polygons",
    ):
        _source_map_deployment_zone_shape(
            cutout_shape,
            lambda x, y: (x, y),
        )


def test_phase17j_quarter_circle_cutout_vertices_cover_supported_corners() -> None:
    lower_right = _source_rectangle_with_quarter_circle_cutout_vertices(
        min_x=0.0,
        min_y=0.0,
        max_x=22.0,
        max_y=30.0,
        corner="lower_right",
        radius=event_source.LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
    )
    upper_left = _source_rectangle_with_quarter_circle_cutout_vertices(
        min_x=0.0,
        min_y=0.0,
        max_x=22.0,
        max_y=30.0,
        corner="upper_left",
        radius=event_source.LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
    )

    assert lower_right[0] == (0.0, 0.0)
    assert lower_right[-2:] == ((22.0, 30.0), (0.0, 30.0))
    assert upper_left[:3] == ((0.0, 0.0), (22.0, 0.0), (22.0, 30.0))
    assert upper_left[-1] == (0.0, 21.0)

    with pytest.raises(MissionPackError, match="Unsupported quarter-circle cutout corner"):
        _source_rectangle_with_quarter_circle_cutout_vertices(
            min_x=0.0,
            min_y=0.0,
            max_x=22.0,
            max_y=30.0,
            corner="upper_center",
            radius=event_source.LAYOUT_C_DEPLOYMENT_CUTOUT_RADIUS_INCHES,
        )


def test_phase17j_base_size_source_kinds_cover_noncanonical_entries() -> None:
    assert _source_base_source_kind_and_geometry("Use model") == (
        "use_model",
        event_source.GeometryResolutionStatus.REQUIRES_PROJECT_GEOMETRY_OVERRIDE,
        None,
    )
    assert _source_base_source_kind_and_geometry("No official base size") == (
        "no_official_base_size",
        event_source.GeometryResolutionStatus.UNSUPPORTED_FOR_PHYSICAL_GEOMETRY,
        None,
    )
    assert _source_base_source_kind_and_geometry("Tactical Rock") == (
        "unresolved_source_shape",
        event_source.GeometryResolutionStatus.UNSUPPORTED_FOR_PHYSICAL_GEOMETRY,
        None,
    )


def test_phase17j_unmapped_primary_missions_remain_source_descriptor_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unknown_primary_names() -> tuple[tuple[str, str], ...]:
        return (("primary-source-pending", "Source Pending"),)

    monkeypatch.setattr(event_source, "_event_primary_mission_names", unknown_primary_names)

    primary_row = event_source.primary_mission_rows()[0]
    coverage_row = event_source.primary_mission_scoring_coverage_rows()[0]

    assert primary_row.primary_mission_id == "primary-source-pending"
    assert primary_row.scoring_kind == "event_companion_primary_source_descriptor_only"
    assert coverage_row.status is event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE
    assert coverage_row.needed_work == ("source_primary_scoring_text",)


def test_phase17j_source_lookup_helpers_fail_closed_for_unknown_ids() -> None:
    with pytest.raises(MissionPackError, match="Unsupported extracted battlefield layout ID"):
        _source_extracted_layout_source("unknown-layout")
    with pytest.raises(MissionPackError, match="Event Companion matrix row was not found"):
        _source_matrix_row(
            player_force_disposition_id="unknown-force",
            opponent_force_disposition_id="take-and-hold",
        )
    with pytest.raises(MissionPackError, match="Event Companion force disposition was not found"):
        _source_force_disposition_name("unknown-force")


def test_phase17j_take_and_hold_layout_a_encodes_terrain_areas_and_regions() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    terrain_layout = mission_pack.terrain_layout_template(layout.terrain_layout_id)
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    assert layout.name == "Take and Hold vs Take and Hold - Battlefield Dominance - Layout A"
    assert layout.battlefield_width_inches == 44.0
    assert layout.battlefield_depth_inches == 60.0
    assert layout.coordinate_origin == "bottom_left"
    assert layout.attacker_edge == "north"
    assert layout.defender_edge == "south"
    assert terrain_layout.terrain_features == ()
    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert setup.terrain_features == ()
    assert len(setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5
    assert setup.objective_markers == layout.objective_markers
    assert setup.objective_terrain_areas == layout.objective_terrain_areas
    assert (
        MissionSetup.from_payload(setup.to_payload()).objective_terrain_areas
        == setup.objective_terrain_areas
    )
    assert setup.deployment_zones == _deployment_zones_for_players(
        layout,
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    assert deployment_map.battlefield_width_inches == layout.battlefield_width_inches
    assert deployment_map.battlefield_depth_inches == layout.battlefield_depth_inches

    assert Counter(area.footprint_template_id for area in layout.terrain_areas) == {
        "FOOTPRINT_6X4": 4,
        "FOOTPRINT_10X2_5": 2,
        "FOOTPRINT_6X2": 4,
        "FOOTPRINT_7X11_5": 4,
        "FOOTPRINT_8X11_5_POLYGON": 2,
    }
    assert len(layout.terrain_areas) == 16
    assert sum(area.source_transform == "explicit" for area in layout.terrain_areas) == 8
    assert (
        sum(area.source_transform.startswith("mirrored_from:") for area in layout.terrain_areas)
        == 8
    )
    assert all(
        0.0 <= point.x_inches <= 44.0 and 0.0 <= point.y_inches <= 60.0
        for area in layout.terrain_areas
        for point in area.footprint_polygon
    )

    assert Counter(marker.objective_role.value for marker in layout.objective_markers) == {
        "attacker_home": 1,
        "defender_home": 1,
        "central": 1,
        "expansion": 2,
    }
    objective_terrain_by_suffix = {
        objective_terrain_area.objective_marker_id.removeprefix(
            "take-and-hold-vs-take-and-hold-layout-1-"
        ): (
            objective_terrain_area.objective_role.value,
            tuple(
                terrain_area_id.removeprefix("take-and-hold-vs-take-and-hold-layout-1-")
                for terrain_area_id in objective_terrain_area.terrain_area_ids
            ),
        )
        for objective_terrain_area in layout.objective_terrain_areas
    }
    assert objective_terrain_by_suffix == {
        "attacker-home": ("attacker_home", ("7x11-5-upper-left",)),
        "defender-home": ("defender_home", ("7x11-5-lower-right",)),
        "central": (
            "central",
            (
                "8x11-5-polygon-central-north",
                "8x11-5-polygon-central-south",
            ),
        ),
        "expansion-west": ("expansion", ("7x11-5-lower-left",)),
        "expansion-east": ("expansion", ("7x11-5-upper-right",)),
    }
    objective_by_role = {marker.objective_role.value: marker for marker in layout.objective_markers}
    attacker_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "attacker")
    defender_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "defender")
    assert attacker_zone.contains_point(
        objective_by_role["attacker_home"].x_inches,
        objective_by_role["attacker_home"].y_inches,
    )
    assert defender_zone.contains_point(
        objective_by_role["defender_home"].x_inches,
        objective_by_role["defender_home"].y_inches,
    )

    regions = {region.region_id: region for region in layout.battlefield_regions}
    attacker_territory = regions["take-and-hold-vs-take-and-hold-layout-1-attacker-territory"]
    defender_territory = regions["take-and-hold-vs-take-and-hold-layout-1-defender-territory"]
    no_mans_land = regions["take-and-hold-vs-take-and-hold-layout-1-no-mans-land"]
    assert attacker_territory.contains_point(22.0, 45.0)
    assert not attacker_territory.contains_point(22.0, 15.0)
    assert defender_territory.contains_point(22.0, 15.0)
    assert not defender_territory.contains_point(22.0, 45.0)
    assert no_mans_land.contains_point(objective_by_role["central"].x_inches, 30.0)
    assert (
        _shape_area(attacker_zone.shape)
        + _shape_area(defender_zone.shape)
        + _shape_area(no_mans_land.shape)
        == 44.0 * 60.0
    )
    assert _shape_area(attacker_territory.shape) + _shape_area(defender_territory.shape) == (
        44.0 * 60.0
    )


def test_phase17j_mission_setup_components_resolve_matching_battlefield_layout() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-1",
        primary_mission_id="primary-battlefield-dominance",
        deployment_map=mission_pack.deployment_map(layout.deployment_map_id),
        terrain_layout=mission_pack.terrain_layout_template(layout.terrain_layout_id),
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert setup.terrain_features == ()
    assert len(setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5


def test_phase17j_take_and_hold_layout_b_encodes_terrain_areas_and_regions() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-2")
    terrain_layout = mission_pack.terrain_layout_template(layout.terrain_layout_id)
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-2",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    assert layout.name == "Take and Hold vs Take and Hold - Battlefield Dominance - Layout B"
    assert layout.battlefield_width_inches == 44.0
    assert layout.battlefield_depth_inches == 60.0
    assert layout.coordinate_origin == "bottom_left"
    assert layout.attacker_edge == "west"
    assert layout.defender_edge == "east"
    assert terrain_layout.terrain_features == ()
    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert setup.terrain_features == ()
    assert len(setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5
    assert setup.objective_markers == layout.objective_markers
    assert setup.objective_terrain_areas == layout.objective_terrain_areas
    assert (
        MissionSetup.from_payload(setup.to_payload()).objective_terrain_areas
        == setup.objective_terrain_areas
    )
    assert setup.deployment_zones == _deployment_zones_for_players(
        layout,
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    assert deployment_map.battlefield_width_inches == layout.battlefield_width_inches
    assert deployment_map.battlefield_depth_inches == layout.battlefield_depth_inches

    assert Counter(area.footprint_template_id for area in layout.terrain_areas) == {
        "FOOTPRINT_6X4": 4,
        "FOOTPRINT_10X2_5": 2,
        "FOOTPRINT_6X2": 4,
        "FOOTPRINT_7X11_5": 4,
        "FOOTPRINT_8X11_5_POLYGON": 2,
    }
    assert len(layout.terrain_areas) == 16
    assert sum(area.source_transform == "explicit" for area in layout.terrain_areas) == 8
    assert (
        sum(area.source_transform.startswith("mirrored_from:") for area in layout.terrain_areas)
        == 8
    )
    assert all(
        0.0 <= point.x_inches <= 44.0 and 0.0 <= point.y_inches <= 60.0
        for area in layout.terrain_areas
        for point in area.footprint_polygon
    )

    assert Counter(marker.objective_role.value for marker in layout.objective_markers) == {
        "attacker_home": 1,
        "defender_home": 1,
        "central": 1,
        "expansion": 2,
    }
    objective_terrain_by_suffix = {
        objective_terrain_area.objective_marker_id.removeprefix(
            "take-and-hold-vs-take-and-hold-layout-2-"
        ): (
            objective_terrain_area.objective_role.value,
            tuple(
                terrain_area_id.removeprefix("take-and-hold-vs-take-and-hold-layout-2-")
                for terrain_area_id in objective_terrain_area.terrain_area_ids
            ),
        )
        for objective_terrain_area in layout.objective_terrain_areas
    }
    assert objective_terrain_by_suffix == {
        "attacker-home": ("attacker_home", ("7x11-5-left-home",)),
        "defender-home": ("defender_home", ("7x11-5-right-home",)),
        "central": (
            "central",
            (
                "8x11-5-polygon-central-north",
                "8x11-5-polygon-central-south",
            ),
        ),
        "expansion-south": ("expansion", ("7x11-5-south-expansion",)),
        "expansion-north": ("expansion", ("7x11-5-north-expansion",)),
    }
    objective_by_role = {marker.objective_role.value: marker for marker in layout.objective_markers}
    attacker_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "attacker")
    defender_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "defender")
    assert attacker_zone.contains_point(
        objective_by_role["attacker_home"].x_inches,
        objective_by_role["attacker_home"].y_inches,
    )
    assert defender_zone.contains_point(
        objective_by_role["defender_home"].x_inches,
        objective_by_role["defender_home"].y_inches,
    )

    regions = {region.region_id: region for region in layout.battlefield_regions}
    attacker_territory = regions["take-and-hold-vs-take-and-hold-layout-2-attacker-territory"]
    defender_territory = regions["take-and-hold-vs-take-and-hold-layout-2-defender-territory"]
    no_mans_land = regions["take-and-hold-vs-take-and-hold-layout-2-no-mans-land"]
    assert attacker_territory.contains_point(11.0, 30.0)
    assert not attacker_territory.contains_point(33.0, 30.0)
    assert defender_territory.contains_point(33.0, 30.0)
    assert not defender_territory.contains_point(11.0, 30.0)
    assert no_mans_land.contains_point(objective_by_role["central"].x_inches, 30.0)
    assert (
        _shape_area(attacker_zone.shape)
        + _shape_area(defender_zone.shape)
        + _shape_area(no_mans_land.shape)
        == 44.0 * 60.0
    )
    assert _shape_area(attacker_territory.shape) + _shape_area(defender_territory.shape) == (
        44.0 * 60.0
    )


def test_phase17j_take_and_hold_layout_c_encodes_cutout_deployments_and_terrain_areas() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-3")
    terrain_layout = mission_pack.terrain_layout_template(layout.terrain_layout_id)
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-3",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    direct_setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-take-and-hold-layout-3",
        primary_mission_id="primary-battlefield-dominance",
        deployment_map=mission_pack.deployment_map(layout.deployment_map_id),
        terrain_layout=terrain_layout,
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    assert layout.name == "Take and Hold vs Take and Hold - Battlefield Dominance - Layout C"
    assert layout.battlefield_width_inches == 44.0
    assert layout.battlefield_depth_inches == 60.0
    assert layout.coordinate_origin == "bottom_left"
    assert layout.attacker_edge == "west"
    assert layout.defender_edge == "east"
    assert terrain_layout.terrain_features == ()
    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert direct_setup.battlefield_layout_id == layout.battlefield_layout_id
    assert setup.terrain_features == ()
    assert direct_setup.terrain_features == ()
    assert len(setup.terrain_areas) == 16
    assert len(direct_setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5
    assert len(direct_setup.battlefield_regions) == 5
    assert setup.objective_markers == layout.objective_markers
    assert setup.objective_terrain_areas == layout.objective_terrain_areas
    assert direct_setup.objective_terrain_areas == layout.objective_terrain_areas
    assert (
        MissionSetup.from_payload(setup.to_payload()).objective_terrain_areas
        == setup.objective_terrain_areas
    )
    assert setup.deployment_zones == _deployment_zones_for_players(
        layout,
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    assert Counter(area.footprint_template_id for area in layout.terrain_areas) == {
        "FOOTPRINT_6X4": 4,
        "FOOTPRINT_10X2_5": 2,
        "FOOTPRINT_6X2": 4,
        "FOOTPRINT_7X11_5": 4,
        "FOOTPRINT_8X11_5_POLYGON": 2,
    }
    assert sum(area.source_transform == "explicit" for area in layout.terrain_areas) == 8
    assert (
        sum(area.source_transform.startswith("mirrored_from:") for area in layout.terrain_areas)
        == 8
    )
    assert all(
        0.0 <= point.x_inches <= 44.0 and 0.0 <= point.y_inches <= 60.0
        for area in layout.terrain_areas
        for point in area.footprint_polygon
    )

    objective_terrain_by_suffix = {
        objective_terrain_area.objective_marker_id.removeprefix(
            "take-and-hold-vs-take-and-hold-layout-3-"
        ): (
            objective_terrain_area.objective_role.value,
            tuple(
                terrain_area_id.removeprefix("take-and-hold-vs-take-and-hold-layout-3-")
                for terrain_area_id in objective_terrain_area.terrain_area_ids
            ),
        )
        for objective_terrain_area in layout.objective_terrain_areas
    }
    assert objective_terrain_by_suffix == {
        "attacker-home": ("attacker_home", ("7x11-5-north-west",)),
        "defender-home": ("defender_home", ("7x11-5-south-east",)),
        "central": (
            "central",
            (
                "8x11-5-polygon-central-north-west",
                "8x11-5-polygon-central-south-east",
            ),
        ),
        "expansion-south-west": ("expansion", ("7x11-5-south-west",)),
        "expansion-north-east": ("expansion", ("7x11-5-north-east",)),
    }
    objective_by_role = {marker.objective_role.value: marker for marker in layout.objective_markers}
    attacker_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "attacker")
    defender_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "defender")
    assert len(attacker_zone.shape.polygons[0].vertices) > 4
    assert len(defender_zone.shape.polygons[0].vertices) > 4
    assert attacker_zone.contains_point(
        objective_by_role["attacker_home"].x_inches,
        objective_by_role["attacker_home"].y_inches,
    )
    assert defender_zone.contains_point(
        objective_by_role["defender_home"].x_inches,
        objective_by_role["defender_home"].y_inches,
    )
    assert not attacker_zone.contains_point(18.0, 34.0)
    assert not defender_zone.contains_point(26.0, 26.0)
    assert not attacker_zone.contains_point(22.0, 30.0)
    assert not defender_zone.contains_point(22.0, 30.0)

    regions = {region.region_id: region for region in layout.battlefield_regions}
    attacker_territory = regions["take-and-hold-vs-take-and-hold-layout-3-attacker-territory"]
    defender_territory = regions["take-and-hold-vs-take-and-hold-layout-3-defender-territory"]
    no_mans_land = regions["take-and-hold-vs-take-and-hold-layout-3-no-mans-land"]
    assert attacker_territory.derived_from == ("attacker_edge_west",)
    assert defender_territory.derived_from == ("defender_edge_east",)
    assert len(no_mans_land.shape.polygons) == 4
    assert attacker_territory.contains_point(10.0, 50.0)
    assert not attacker_territory.contains_point(34.0, 10.0)
    assert defender_territory.contains_point(34.0, 10.0)
    assert not defender_territory.contains_point(10.0, 50.0)
    assert no_mans_land.contains_point(objective_by_role["central"].x_inches, 30.0)
    assert no_mans_land.contains_point(18.0, 34.0)
    assert no_mans_land.contains_point(26.0, 26.0)
    assert math.isclose(
        _shape_area(attacker_zone.shape)
        + _shape_area(defender_zone.shape)
        + _shape_area(no_mans_land.shape),
        44.0 * 60.0,
        rel_tol=0.0,
        abs_tol=2e-6,
    )
    assert math.isclose(
        _shape_area(attacker_territory.shape) + _shape_area(defender_territory.shape),
        44.0 * 60.0,
        rel_tol=0.0,
        abs_tol=1e-6,
    )


@pytest.mark.parametrize(
    ("layout_id", "layout_name", "attacker_edge", "defender_edge", "no_mans_land_polygons"),
    [
        (
            "disruption-vs-reconnaissance-layout-1",
            "Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout A",
            "north",
            "south",
            1,
        ),
        (
            "disruption-vs-reconnaissance-layout-2",
            "Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout B",
            "west",
            "east",
            1,
        ),
        (
            "disruption-vs-reconnaissance-layout-3",
            "Disruption vs Reconnaissance - Smoke and Mirrors / Surveil the Foe - Layout C",
            "west",
            "east",
            4,
        ),
    ],
)
def test_phase17j_disruption_vs_reconnaissance_layouts_encode_geometry(
    layout_id: str,
    layout_name: str,
    attacker_edge: str,
    defender_edge: str,
    no_mans_land_polygons: int,
) -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout(layout_id)
    terrain_layout = mission_pack.terrain_layout_template(layout.terrain_layout_id)
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    direct_setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        primary_mission_id="primary-smoke-and-mirrors",
        deployment_map=deployment_map,
        terrain_layout=terrain_layout,
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    expected_objectives = {
        "disruption-vs-reconnaissance-layout-1": {
            "attacker-home": ("attacker_home", 16.98, 49.88),
            "defender-home": ("defender_home", 26.31, 9.65),
            "central-south": ("central", 23.0, 25.7),
            "central-north": ("central", 20.9, 34.1),
            "expansion-east": ("expansion", 37.65, 41.4),
            "expansion-west": ("expansion", 6.21, 18.9),
        },
        "disruption-vs-reconnaissance-layout-2": {
            "attacker-home": ("attacker_home", 7.55, 44.17),
            "defender-home": ("defender_home", 36.53, 16.02),
            "central-west": ("central", 14.31, 28.95),
            "central-east": ("central", 29.24, 31.45),
            "expansion-north": ("expansion", 24.0, 51.43),
            "expansion-south": ("expansion", 20.05, 8.6),
        },
        "disruption-vs-reconnaissance-layout-3": {
            "attacker-home": ("attacker_home", 6.45, 45.39),
            "defender-home": ("defender_home", 37.4, 14.91),
            "central-north-west": ("central", 18.49, 33.93),
            "central-south-east": ("central", 25.52, 26.0),
            "expansion-north-east": ("expansion", 35.62, 50.96),
            "expansion-south-west": ("expansion", 8.75, 9.07),
        },
    }

    assert layout.name == layout_name
    assert layout.battlefield_width_inches == 44.0
    assert layout.battlefield_depth_inches == 60.0
    assert layout.coordinate_origin == "bottom_left"
    assert layout.attacker_edge == attacker_edge
    assert layout.defender_edge == defender_edge
    assert terrain_layout.terrain_features == ()
    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert direct_setup.battlefield_layout_id == layout.battlefield_layout_id
    assert setup.terrain_features == ()
    assert direct_setup.terrain_features == ()
    assert len(setup.terrain_areas) == 16
    assert len(direct_setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5
    assert len(direct_setup.battlefield_regions) == 5
    assert setup.objective_markers == layout.objective_markers
    assert setup.deployment_zones == _deployment_zones_for_players(
        layout,
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    assert Counter(area.footprint_template_id for area in layout.terrain_areas) == {
        "FOOTPRINT_6X4": 4,
        "FOOTPRINT_10X2_5": 2,
        "FOOTPRINT_6X2": 4,
        "FOOTPRINT_7X11_5": 4,
        "FOOTPRINT_8X11_5_POLYGON": 2,
    }
    assert sum(area.source_transform == "explicit" for area in layout.terrain_areas) == 8
    assert (
        sum(area.source_transform.startswith("mirrored_from:") for area in layout.terrain_areas)
        == 8
    )
    assert all(
        0.0 <= point.x_inches <= 44.0 and 0.0 <= point.y_inches <= 60.0
        for area in layout.terrain_areas
        for point in area.footprint_polygon
    )

    assert dict(layout.objective_role_counts) == {
        ObjectiveMarkerRole.ATTACKER_HOME: 1,
        ObjectiveMarkerRole.DEFENDER_HOME: 1,
        ObjectiveMarkerRole.CENTRAL: 2,
        ObjectiveMarkerRole.EXPANSION: 2,
    }
    assert Counter(marker.objective_role.value for marker in layout.objective_markers) == {
        "attacker_home": 1,
        "defender_home": 1,
        "central": 2,
        "expansion": 2,
    }
    actual_objectives = {
        marker.objective_marker_id.removeprefix(f"{layout_id}-"): (
            marker.objective_role.value,
            round(marker.x_inches, 2),
            round(marker.y_inches, 2),
        )
        for marker in layout.objective_markers
    }
    assert actual_objectives == expected_objectives[layout_id]

    objective_by_role = {marker.objective_role: marker for marker in layout.objective_markers}
    central_objectives = tuple(
        marker
        for marker in layout.objective_markers
        if marker.objective_role is ObjectiveMarkerRole.CENTRAL
    )
    attacker_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "attacker")
    defender_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "defender")
    assert attacker_zone.contains_point(
        objective_by_role[ObjectiveMarkerRole.ATTACKER_HOME].x_inches,
        objective_by_role[ObjectiveMarkerRole.ATTACKER_HOME].y_inches,
    )
    assert defender_zone.contains_point(
        objective_by_role[ObjectiveMarkerRole.DEFENDER_HOME].x_inches,
        objective_by_role[ObjectiveMarkerRole.DEFENDER_HOME].y_inches,
    )

    regions = {region.region_id: region for region in layout.battlefield_regions}
    attacker_territory = regions[f"{layout_id}-attacker-territory"]
    defender_territory = regions[f"{layout_id}-defender-territory"]
    no_mans_land = regions[f"{layout_id}-no-mans-land"]
    assert attacker_territory.derived_from == (f"attacker_edge_{attacker_edge}",)
    assert defender_territory.derived_from == (f"defender_edge_{defender_edge}",)
    assert len(no_mans_land.shape.polygons) == no_mans_land_polygons
    assert all(
        no_mans_land.contains_point(marker.x_inches, marker.y_inches)
        for marker in central_objectives
    )
    if no_mans_land_polygons == 4:
        assert len(attacker_zone.shape.polygons[0].vertices) > 4
        assert len(defender_zone.shape.polygons[0].vertices) > 4
        assert not attacker_zone.contains_point(22.0, 30.0)
        assert not defender_zone.contains_point(22.0, 30.0)
    assert math.isclose(
        _shape_area(attacker_zone.shape)
        + _shape_area(defender_zone.shape)
        + _shape_area(no_mans_land.shape),
        44.0 * 60.0,
        rel_tol=0.0,
        abs_tol=2e-6,
    )
    assert math.isclose(
        _shape_area(attacker_territory.shape) + _shape_area(defender_territory.shape),
        44.0 * 60.0,
        rel_tol=0.0,
        abs_tol=1e-6,
    )


def test_phase17j_objective_role_payload_is_required() -> None:
    marker = (
        warhammer_event_companion_2026_06_mission_pack()
        .battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
        .objective_markers[0]
    )
    payload = dict(marker.to_payload())
    payload.pop("objective_role")

    with pytest.raises(MissionPackError, match="objective_role"):
        type(marker).from_payload(cast(ObjectiveMarkerDefinitionPayload, payload))


def test_phase17j_centre_and_center_objective_roles_normalize_to_central() -> None:
    assert objective_marker_role_from_token("center") is ObjectiveMarkerRole.CENTRAL
    assert objective_marker_role_from_token("centre") is ObjectiveMarkerRole.CENTRAL


def test_phase17j_placed_terrain_area_payload_must_match_template_transform() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    first_area, second_area, *remaining_areas = layout.terrain_areas
    drifted_area = replace(
        first_area,
        footprint_polygon=second_area.footprint_polygon,
    )
    drifted_layout = replace(
        layout,
        terrain_areas=(drifted_area, second_area, *remaining_areas),
    )

    with pytest.raises(MissionPackError, match="template transform"):
        replace(
            mission_pack,
            battlefield_layouts=tuple(
                drifted_layout
                if candidate.battlefield_layout_id == drifted_layout.battlefield_layout_id
                else candidate
                for candidate in mission_pack.battlefield_layouts
            ),
        )


def test_phase17j_layout_region_invariants_fail_closed() -> None:
    layout = warhammer_event_companion_2026_06_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-2"
    )
    attacker_zone = next(zone for zone in layout.deployment_zones if zone.player_id == "attacker")
    no_mans_land = next(
        region for region in layout.battlefield_regions if region.region_id.endswith("no-mans-land")
    )
    drifted_no_mans_land = replace(no_mans_land, shape=attacker_zone.shape)

    with pytest.raises(MissionPackError, match="no-man's-land"):
        BattlefieldLayoutDefinition(
            battlefield_layout_id=layout.battlefield_layout_id,
            name=layout.name,
            deployment_map_id=layout.deployment_map_id,
            terrain_layout_id=layout.terrain_layout_id,
            battlefield_width_inches=layout.battlefield_width_inches,
            battlefield_depth_inches=layout.battlefield_depth_inches,
            coordinate_origin=layout.coordinate_origin,
            coordinate_orientation=layout.coordinate_orientation,
            attacker_edge=layout.attacker_edge,
            defender_edge=layout.defender_edge,
            objective_markers=layout.objective_markers,
            deployment_zones=layout.deployment_zones,
            battlefield_regions=tuple(
                drifted_no_mans_land
                if region.region_id == drifted_no_mans_land.region_id
                else region
                for region in layout.battlefield_regions
            ),
            terrain_areas=layout.terrain_areas,
            objective_role_counts=layout.objective_role_counts,
            source_id=layout.source_id,
        )


def test_phase17j_layout_must_match_deployment_map_objective_geometry() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-1")
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    first_marker, *remaining_markers = deployment_map.objective_markers
    drifted_marker = replace(
        first_marker,
        x_inches=first_marker.x_inches + 0.25,
    )
    drifted_map = replace(
        deployment_map,
        objective_markers=(drifted_marker, *remaining_markers),
    )

    with pytest.raises(MissionPackError, match="objective markers"):
        replace(
            mission_pack,
            deployment_maps=tuple(
                drifted_map
                if candidate.deployment_map_id == drifted_map.deployment_map_id
                else candidate
                for candidate in mission_pack.deployment_maps
            ),
        )


def test_phase17j_layout_must_match_deployment_map_zone_geometry() -> None:
    mission_pack = warhammer_event_companion_2026_06_mission_pack()
    layout = mission_pack.battlefield_layout("take-and-hold-vs-take-and-hold-layout-2")
    deployment_map = mission_pack.deployment_map(layout.deployment_map_id)
    defender_zone = next(
        zone for zone in deployment_map.deployment_zones if zone.player_id == "defender"
    )
    drifted_zone = replace(
        defender_zone,
        shape=DeploymentZoneShape.rectangle(
            min_x=31.0,
            min_y=0.0,
            max_x=44.0,
            max_y=60.0,
        ),
    )
    drifted_map = replace(
        deployment_map,
        deployment_zones=tuple(
            drifted_zone if zone.deployment_zone_id == drifted_zone.deployment_zone_id else zone
            for zone in deployment_map.deployment_zones
        ),
    )

    with pytest.raises(MissionPackError, match="deployment zones"):
        replace(
            mission_pack,
            deployment_maps=tuple(
                drifted_map
                if candidate.deployment_map_id == drifted_map.deployment_map_id
                else candidate
                for candidate in mission_pack.deployment_maps
            ),
        )


def test_phase17j_territories_must_contain_their_deployment_zones() -> None:
    layout = warhammer_event_companion_2026_06_mission_pack().battlefield_layout(
        "take-and-hold-vs-take-and-hold-layout-1"
    )
    attacker_territory = next(
        region
        for region in layout.battlefield_regions
        if region.region_id.endswith("attacker-territory")
    )
    defender_territory = next(
        region
        for region in layout.battlefield_regions
        if region.region_id.endswith("defender-territory")
    )
    swapped_attacker_territory = replace(
        attacker_territory,
        shape=defender_territory.shape,
    )
    swapped_defender_territory = replace(
        defender_territory,
        shape=attacker_territory.shape,
    )

    with pytest.raises(MissionPackError, match="Attacker territory"):
        BattlefieldLayoutDefinition(
            battlefield_layout_id=layout.battlefield_layout_id,
            name=layout.name,
            deployment_map_id=layout.deployment_map_id,
            terrain_layout_id=layout.terrain_layout_id,
            battlefield_width_inches=layout.battlefield_width_inches,
            battlefield_depth_inches=layout.battlefield_depth_inches,
            coordinate_origin=layout.coordinate_origin,
            coordinate_orientation=layout.coordinate_orientation,
            attacker_edge=layout.attacker_edge,
            defender_edge=layout.defender_edge,
            objective_markers=layout.objective_markers,
            deployment_zones=layout.deployment_zones,
            battlefield_regions=tuple(
                swapped_attacker_territory
                if region.region_id == swapped_attacker_territory.region_id
                else swapped_defender_territory
                if region.region_id == swapped_defender_territory.region_id
                else region
                for region in layout.battlefield_regions
            ),
            terrain_areas=layout.terrain_areas,
            objective_role_counts=layout.objective_role_counts,
            source_id=layout.source_id,
        )


def test_phase17j_card_amendments_are_separate_from_faq_patch_rows() -> None:
    amendment_set = event_source.card_amendment_set()
    faq_patches = event_companion_patches.faq_patch_rows()

    assert amendment_set.amendments == ()
    assert amendment_set.source_page == 4
    assert {patch.patch_id for patch in faq_patches} == {
        "faq-operation-marker-removal-requires-card-permission",
        "faq-death-trap-trapped-area-scoring-window",
        "faq-surveil-the-foe-same-turn-marker-removal",
        "faq-vital-link-multiple-central-objectives",
    }
    assert {patch.behavior_descriptor for patch in faq_patches} == {
        "operation_marker_removal_requires_primary_card_permission",
        "death_trap_trapped_area_checked_at_scoring_not_destruction_time",
        "surveil_the_foe_same_turn_marker_removal_allows_scoring",
        "vital_link_multiple_central_objectives_marker_control_allows_cumulative_vp",
    }
    assert all(patch.source_page == 4 for patch in faq_patches)
    assert all(
        patch.source_id.startswith("gw-11e-warhammer-event-companion-v1-0-2026-06:faq:")
        for patch in faq_patches
    )


def test_phase17j_base_size_source_rows_fail_closed_for_noncanonical_shapes() -> None:
    rows = event_source.base_size_source_rows()
    rows_by_kind = {row.base_source_kind: row for row in rows}

    assert len(rows) == 1083
    assert {row.source_page for row in rows} == set(range(55, 94))
    assert len({row.record_id for row in rows}) == len(rows)
    assert {
        "round",
        "oval",
        "hull",
        "small_flying_base",
        "large_flying_base",
        "unique",
    } <= set(rows_by_kind)
    assert rows_by_kind["round"].canonical_base_size is not None
    assert rows_by_kind["oval"].canonical_base_size is not None
    assert rows_by_kind["hull"].canonical_base_size is None
    assert rows_by_kind["small_flying_base"].canonical_base_size is None
    assert rows_by_kind["large_flying_base"].canonical_base_size is None
    assert rows_by_kind["unique"].canonical_base_size is None
    assert rows_by_kind["hull"].geometry_resolution_status.value == (
        "requires_project_geometry_override"
    )
    assert rows_by_kind["small_flying_base"].geometry_resolution_status.value == (
        "requires_project_geometry_override"
    )
    assert rows_by_kind["large_flying_base"].geometry_resolution_status.value == (
        "requires_project_geometry_override"
    )
    assert rows_by_kind["unique"].geometry_resolution_status.value == (
        "requires_event_organizer_override"
    )


def test_phase17j_primary_source_descriptor_rows_do_not_create_placeholder_scoring() -> None:
    descriptor_rows = tuple(
        row
        for row in event_source.primary_mission_rows()
        if row.scoring_kind == "event_companion_primary_source_descriptor_only"
    )

    assert descriptor_rows == ()


def test_phase17j_primary_scoring_coverage_tracks_known_pending_and_missing_rows() -> None:
    primary_rows = {row.primary_mission_id: row for row in event_source.primary_mission_rows()}
    coverage_rows = {
        row.primary_mission_id: row for row in event_source.primary_mission_scoring_coverage_rows()
    }
    status_counts = {
        status: sum(1 for row in coverage_rows.values() if row.status is status)
        for status in event_source.PrimaryMissionScoringCoverageStatus
    }

    assert len(coverage_rows) == 25
    assert status_counts == {
        event_source.PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED: 3,
        event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING: 22,
        event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE: 0,
    }
    assert {
        row.primary_mission_id
        for row in coverage_rows.values()
        if row.status is event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE
    } == set()
    assert {
        mission_id: len(primary_rows[mission_id].scoring_rules)
        for mission_id in (
            "primary-unstoppable-force",
            "primary-battlefield-dominance",
            "primary-meatgrinder",
            "primary-punishment",
            "primary-consecrate",
            "primary-destroyers-wrath",
            "primary-determined-acquisition",
            "primary-outmaneuver",
            "primary-delaying-action",
            "primary-locate-and-deny",
            "primary-smoke-and-mirrors",
            "primary-reconnaissance-sweep",
            "primary-surveil-the-foe",
            "primary-triangulation",
            "primary-gather-intel",
            "primary-search-and-scour",
            "primary-purge-and-secure",
            "primary-inescapable-dominion",
            "primary-extract-relic",
            "primary-sabotage",
            "primary-secure-asset",
            "primary-vanguard-operation",
            "primary-vital-link",
        )
    } == {
        "primary-unstoppable-force": 4,
        "primary-battlefield-dominance": 3,
        "primary-meatgrinder": 4,
        "primary-punishment": 4,
        "primary-consecrate": 5,
        "primary-destroyers-wrath": 4,
        "primary-determined-acquisition": 3,
        "primary-outmaneuver": 4,
        "primary-delaying-action": 3,
        "primary-locate-and-deny": 4,
        "primary-smoke-and-mirrors": 4,
        "primary-reconnaissance-sweep": 4,
        "primary-surveil-the-foe": 4,
        "primary-triangulation": 5,
        "primary-gather-intel": 5,
        "primary-search-and-scour": 4,
        "primary-purge-and-secure": 4,
        "primary-inescapable-dominion": 4,
        "primary-extract-relic": 5,
        "primary-sabotage": 3,
        "primary-secure-asset": 4,
        "primary-vanguard-operation": 4,
        "primary-vital-link": 5,
    }
    assert primary_rows["primary-meatgrinder"].scoring_kind == (
        "event_companion_primary_source_known_engine_pending"
    )
    assert primary_rows["primary-battlefield-dominance"].scoring_kind == (
        "event_companion_primary_source_known_engine_pending"
    )
    assert coverage_rows["primary-unstoppable-force"].needed_work == ()
    assert coverage_rows["primary-death-trap"].mission_action_count == 1
    assert coverage_rows["primary-smoke-and-mirrors"].mission_action_count == 1
    assert coverage_rows["primary-gather-intel"].mission_action_count == 1
    assert coverage_rows["primary-surveil-the-foe"].mission_action_count == 1
    assert coverage_rows["primary-locate-and-deny"].mission_action_count == 1
    assert coverage_rows["primary-extract-relic"].mission_action_count == 1
    assert coverage_rows["primary-sabotage"].mission_action_count == 1
    assert coverage_rows["primary-secure-asset"].mission_action_count == 1
    assert coverage_rows["primary-vanguard-operation"].mission_action_count == 1
    assert coverage_rows["primary-vital-link"].mission_action_count == 1
    assert "engine_primary_action:decoy-objective" in (
        coverage_rows["primary-smoke-and-mirrors"].needed_work
    )
    assert "engine_primary_action:extract-intelligence" in (
        coverage_rows["primary-gather-intel"].needed_work
    )
    assert "engine_primary_action:surveil-enemy-unit" in (
        coverage_rows["primary-surveil-the-foe"].needed_work
    )
    assert "engine_primary_scoring_grammar:cumulative_condition" in (
        coverage_rows["primary-battlefield-dominance"].needed_work
    )
    assert "engine_primary_action:maintain-control" in (
        coverage_rows["primary-vital-link"].needed_work
    )
    assert "source_objective_role:expansion_objective" in (
        coverage_rows["primary-delaying-action"].needed_work
    )


def test_phase17j_primary_source_only_actions_are_not_exposed_as_runtime_actions() -> None:
    action_sources = {
        row.mission_action_id: row for row in event_source.primary_mission_action_source_rows()
    }
    mission_pack = warhammer_event_companion_2026_06_mission_pack()

    assert set(action_sources) == {
        "commit-sabotage",
        "decoy-objective",
        "extract-intelligence",
        "maintain-control",
        "sensor-sweep-extract-relic",
        "sensor-sweep-locate-and-deny",
        "secure-asset",
        "surveil-enemy-unit",
        "triangulate-objective",
        "vanguard-operation",
    }
    assert action_sources["decoy-objective"].to_payload() == {
        "mission_action_id": "decoy-objective",
        "primary_mission_id": "primary-smoke-and-mirrors",
        "name": "Decoy",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start",
        "completion_timing": "turn_end",
        "eligible_unit_policy": "active_player_unit",
        "target_policy": "objective_marker_excluding_home_not_decoy",
        "use_limit": "unlimited_different_objective_per_unit_this_phase",
        "effect_descriptor": "objective_becomes_decoy_if_action_unit_controls_target_at_turn_end",
        "engine_exposure_status": "source_known_engine_pending",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-0-2026-06:primary-action:decoy-objective"
        ),
    }
    assert action_sources["triangulate-objective"].start_timing == (
        "shooting_phase_action_start_from_battle_round_two"
    )
    assert action_sources["extract-intelligence"].to_payload() == {
        "mission_action_id": "extract-intelligence",
        "primary_mission_id": "primary-gather-intel",
        "name": "Extract Intelligence",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start_from_battle_round_two",
        "completion_timing": "turn_end",
        "eligible_unit_policy": "active_player_unit",
        "target_policy": "objective_marker_excluding_home_without_friendly_operation_marker",
        "use_limit": "unlimited_different_objective_per_unit_this_phase",
        "effect_descriptor": (
            "objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end"
        ),
        "engine_exposure_status": "source_known_engine_pending",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-0-2026-06:primary-action:extract-intelligence"
        ),
    }
    assert action_sources["surveil-enemy-unit"].to_payload() == {
        "mission_action_id": "surveil-enemy-unit",
        "primary_mission_id": "primary-surveil-the-foe",
        "name": "Surveil the Foe",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start",
        "completion_timing": "immediate",
        "eligible_unit_policy": "active_player_unit",
        "target_policy": "visible_enemy_unit_within_18_not_surveilled_this_turn",
        "use_limit": "unlimited",
        "effect_descriptor": "enemy_unit_becomes_surveilled_until_turn_end",
        "engine_exposure_status": "source_known_engine_pending",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-0-2026-06:primary-action:surveil-enemy-unit"
        ),
    }
    assert action_sources["sensor-sweep-locate-and-deny"].target_policy == (
        "operation_marker_requires_more_than_one_marker_remaining"
    )
    assert action_sources["sensor-sweep-extract-relic"].effect_descriptor == (
        "remove_one_opponent_operation_marker_if_action_unit_controls_central_objective_at_turn_end"
    )
    assert action_sources["commit-sabotage"].use_limit == (
        "unlimited_different_objective_per_unit_this_phase"
    )
    assert action_sources["secure-asset"].to_payload() == {
        "mission_action_id": "secure-asset",
        "primary_mission_id": "primary-secure-asset",
        "name": "Secure Asset",
        "start_phase": "shooting",
        "start_timing": "shooting_phase_action_start",
        "completion_timing": "turn_end",
        "eligible_unit_policy": "active_player_unit_within_range_of_non_home_objective",
        "target_policy": "objective_marker_excluding_home",
        "use_limit": "once_per_turn",
        "effect_descriptor": "unit_secures_asset_if_action_unit_controls_target_at_turn_end",
        "engine_exposure_status": "source_known_engine_pending",
        "source_id": ("gw-11e-warhammer-event-companion-v1-0-2026-06:primary-action:secure-asset"),
    }
    assert action_sources["vanguard-operation"].eligible_unit_policy == (
        "active_player_unit_within_terrain_area_in_enemy_territory"
    )
    assert action_sources["maintain-control"].effect_descriptor == (
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end"
    )
    for action_id in action_sources:
        with pytest.raises(MissionPackError, match="mission_action_id"):
            mission_pack.mission_action(action_id)


def test_phase17j_source_known_engine_pending_primary_scoring_fails_closed() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    with pytest.raises(
        GameLifecycleError,
        match="Primary mission scoring source is known but engine implementation is pending",
    ):
        mission_scoring_policy_from_setup(setup)


def test_phase17j_event_pack_resolves_scoring_and_tactical_draw_by_pack_id() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    policy = mission_scoring_policy_from_setup(setup)
    tactical_draw = deterministic_tactical_secondary_draw(
        mission_setup=setup,
        player_id="player-alpha",
        battle_round=1,
        draw_count=2,
    )

    assert policy.mission_pack_id == mission_pack.mission_pack_id
    assert policy.game_length_battle_rounds == 5
    assert policy.primary_vp_cap == 45
    assert policy.secondary_vp_cap == 45
    assert policy.total_vp_cap == 100
    assert len(tactical_draw) == 2

    with pytest.raises(GameLifecycleError):
        mission_pack_for_id("unsupported-pack")


def test_phase17j_final_scoring_uses_event_caps_battle_ready_and_draw_rules() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-06")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    policy = mission_scoring_policy_from_setup(setup)
    player_alpha_ledger, _ = VictoryPointLedger.initial(player_id="player-alpha").award(
        VictoryPointAward(
            player_id="player-alpha",
            battle_round=5,
            phase="command",
            amount=55,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=setup.primary_mission_id,
            scoring_timing="phase_end",
            metadata={"scoring_rule_id": "phase17j-primary-cap"},
        )
    )
    player_alpha_ledger, _ = player_alpha_ledger.award(
        VictoryPointAward(
            player_id="player-alpha",
            battle_round=5,
            phase="command",
            amount=12,
            source_kind=VictoryPointSourceKind.BATTLE_READY,
            source_id="battle-ready",
            scoring_timing="game_end",
            metadata={"scoring_rule_id": "phase17j-battle-ready-cap"},
        )
    )
    player_beta_ledger, _ = VictoryPointLedger.initial(player_id="player-beta").award(
        VictoryPointAward(
            player_id="player-beta",
            battle_round=5,
            phase="command",
            amount=45,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=setup.primary_mission_id,
            scoring_timing="phase_end",
            metadata={"scoring_rule_id": "phase17j-opponent-primary"},
        )
    )
    player_beta_ledger, _ = player_beta_ledger.award(
        VictoryPointAward(
            player_id="player-beta",
            battle_round=5,
            phase="command",
            amount=10,
            source_kind=VictoryPointSourceKind.BATTLE_READY,
            source_id="battle-ready",
            scoring_timing="game_end",
            metadata={"scoring_rule_id": "phase17j-opponent-battle-ready"},
        )
    )
    result = FinalScoringResult.from_ledgers(
        game_id="phase17j-event-final-scoring",
        battle_round=5,
        policy=policy,
        ledgers=(player_alpha_ledger, player_beta_ledger),
        scoring_windows=_event_final_scoring_windows(
            game_id="phase17j-event-final-scoring",
            battle_round=5,
            policy_source_id=policy.source_id,
        ),
    )

    payload = result.to_payload()
    audit = cast(dict[str, object], payload["scoring_audit"])

    assert payload["winner_player_ids"] == ["player-alpha", "player-beta"]
    assert payload["is_draw"] is True
    assert payload["final_scores"] == [
        {"player_id": "player-alpha", "victory_points": 55},
        {"player_id": "player-beta", "victory_points": 55},
    ]
    assert audit["battle_ready_vp_cap"] == 10


def _source_deployment_zone_layout_template_id(
    *,
    layout_id: str,
    layout_number: int,
) -> event_source.DeploymentZoneLayoutTemplateId:
    function = cast(
        Callable[..., event_source.DeploymentZoneLayoutTemplateId],
        vars(event_source)["_deployment_zone_layout_template_id"],
    )
    return function(layout_id=layout_id, layout_number=layout_number)


def _source_deployment_zone_layout_edges(
    template_id: event_source.DeploymentZoneLayoutTemplateId,
) -> tuple[str, str]:
    function = cast(
        Callable[[event_source.DeploymentZoneLayoutTemplateId], tuple[str, str]],
        vars(event_source)["_deployment_zone_layout_edges"],
    )
    return function(template_id)


def _source_deployment_zone_layout_template_id_from_number(
    template_number: int,
) -> event_source.DeploymentZoneLayoutTemplateId:
    template_ids_by_number: dict[int, event_source.DeploymentZoneLayoutTemplateId] = {
        1: event_source.DEPLOYMENT_ZONE_LAYOUT_1_STAGGERED,
        2: event_source.DEPLOYMENT_ZONE_LAYOUT_2_LONG_EDGE_STRIP,
        3: event_source.DEPLOYMENT_ZONE_LAYOUT_3_QUARTER_CIRCLE_CUTOUT,
        4: event_source.DEPLOYMENT_ZONE_LAYOUT_4_STEPPED_LONG_EDGE,
        5: event_source.DEPLOYMENT_ZONE_LAYOUT_5_SHORT_EDGE_STRIP,
        6: event_source.DEPLOYMENT_ZONE_LAYOUT_6_TRIANGLE,
    }
    return template_ids_by_number[template_number]


def _source_deployment_zone_shape_transforms(
    template_id: event_source.DeploymentZoneLayoutTemplateId,
) -> tuple[event_source.DeploymentZoneShapeTransform, event_source.DeploymentZoneShapeTransform]:
    function = cast(
        Callable[
            [event_source.DeploymentZoneLayoutTemplateId],
            tuple[
                event_source.DeploymentZoneShapeTransform,
                event_source.DeploymentZoneShapeTransform,
            ],
        ],
        vars(event_source)["_deployment_zone_shape_transforms"],
    )
    return function(template_id)


def _source_deployment_zone_template_base_shape(
    template_id: event_source.DeploymentZoneLayoutTemplateId,
) -> DeploymentZoneShape:
    function = cast(
        Callable[[event_source.DeploymentZoneLayoutTemplateId], DeploymentZoneShape],
        vars(event_source)["_deployment_zone_template_base_shape"],
    )
    return function(template_id)


def _source_transform_deployment_zone_shape(
    shape: DeploymentZoneShape,
    transform: event_source.DeploymentZoneShapeTransform,
) -> DeploymentZoneShape:
    function = cast(
        Callable[
            [DeploymentZoneShape, event_source.DeploymentZoneShapeTransform], DeploymentZoneShape
        ],
        vars(event_source)["_transform_deployment_zone_shape"],
    )
    return function(shape, transform)


def _source_layout_number_from_layout_id(layout_id: str) -> int:
    function = cast(
        Callable[[str], int],
        vars(event_source)["_layout_number_from_layout_id"],
    )
    return function(layout_id)


def _source_extracted_deployment_zones(
    *,
    layout_id: str,
) -> tuple[object, ...]:
    function = cast(
        Callable[..., tuple[object, ...]],
        vars(event_source)["_extracted_deployment_zones"],
    )
    return function(layout_id=layout_id)


def _source_map_deployment_zone_shape(
    shape: DeploymentZoneShape,
    transform: Callable[[float, float], tuple[float, float]],
) -> DeploymentZoneShape:
    function = cast(
        Callable[
            [DeploymentZoneShape, Callable[[float, float], tuple[float, float]]],
            DeploymentZoneShape,
        ],
        vars(event_source)["_map_deployment_zone_shape"],
    )
    return function(shape, transform)


def _source_rectangle_with_quarter_circle_cutout_vertices(
    *,
    min_x: float,
    min_y: float,
    max_x: float,
    max_y: float,
    corner: str,
    radius: float,
) -> tuple[tuple[float, float], ...]:
    function = cast(
        Callable[..., tuple[tuple[float, float], ...]],
        vars(event_source)["_rectangle_with_quarter_circle_cutout_vertices"],
    )
    return function(
        min_x=min_x,
        min_y=min_y,
        max_x=max_x,
        max_y=max_y,
        corner=corner,
        radius=radius,
    )


def _source_base_source_kind_and_geometry(
    base_text: str,
) -> tuple[str, event_source.GeometryResolutionStatus, object | None]:
    function = cast(
        Callable[..., tuple[str, event_source.GeometryResolutionStatus, object | None]],
        vars(event_source)["_base_source_kind_and_geometry"],
    )
    return function(base_text)


def _source_extracted_layout_source(layout_id: str) -> object:
    function = cast(
        Callable[[str], object],
        vars(event_source)["_extracted_layout_source"],
    )
    return function(layout_id)


def _source_matrix_row(
    *,
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
) -> object:
    function = cast(
        Callable[..., object],
        vars(event_source)["_matrix_row"],
    )
    return function(
        player_force_disposition_id=player_force_disposition_id,
        opponent_force_disposition_id=opponent_force_disposition_id,
    )


def _source_force_disposition_name(force_disposition_id: str) -> str:
    function = cast(
        Callable[[str], str],
        vars(event_source)["_force_disposition_name"],
    )
    return function(force_disposition_id)


def _layout_descriptor(
    player_force_disposition_id: str,
    opponent_force_disposition_id: str,
    layout_variant: str,
) -> event_source.WarhammerEventLayoutDescriptor:
    for descriptor in event_source.layout_descriptor_rows():
        if (
            descriptor.player_force_disposition_id == player_force_disposition_id
            and descriptor.opponent_force_disposition_id == opponent_force_disposition_id
            and descriptor.layout_variant == layout_variant
        ):
            return descriptor
    raise AssertionError("Layout descriptor was not found.")


def _shape_area(shape: DeploymentZoneShape) -> float:
    total = 0.0
    for polygon in shape.polygons:
        vertices = polygon.vertices
        previous = vertices[-1]
        area = 0.0
        for current in vertices:
            area += previous.x * current.y - current.x * previous.y
            previous = current
        total += abs(area) / 2.0
    return round(total, 6)


def _shape_polygons(shape: DeploymentZoneShape) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple((point.x, point.y) for point in polygon.vertices) for polygon in shape.polygons
    )


def _terrain_display_points(
    points: tuple[TerrainDisplayPoint, ...],
) -> tuple[tuple[float, float], ...]:
    return tuple((point.x_inches, point.y_inches) for point in points)


def _rounded_terrain_display_point(point: TerrainDisplayPoint) -> tuple[float, float]:
    return (round(point.x_inches, 6), round(point.y_inches, 6))


def _deployment_zones_for_players(
    layout: BattlefieldLayoutDefinition,
    *,
    attacker_player_id: str,
    defender_player_id: str,
) -> tuple[DeploymentZone, ...]:
    zones: list[DeploymentZone] = []
    for zone in layout.deployment_zones:
        if zone.player_id == "attacker":
            zones.append(zone.with_player_id(attacker_player_id))
        elif zone.player_id == "defender":
            zones.append(zone.with_player_id(defender_player_id))
        else:
            zones.append(zone)
    return tuple(sorted(zones, key=lambda item: item.deployment_zone_id))


def _event_final_scoring_windows(
    *,
    game_id: str,
    battle_round: int,
    policy_source_id: str,
) -> tuple[ScoringWindowState, ...]:
    return (
        ScoringWindowState(
            window_id="phase17j-event-final-round",
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_ROUND,
            window="battle_round_end",
            source_id=f"{policy_source_id}:end-of-round",
        ),
        ScoringWindowState(
            window_id="phase17j-event-final-turn-end",
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="turn_end_round_five_going_second",
            source_id=f"{policy_source_id}:turn-end-round-five",
        ),
        ScoringWindowState(
            window_id="phase17j-event-final-end-battle",
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="end_of_battle",
            source_id=f"{policy_source_id}:end-of-battle",
        ),
    )
