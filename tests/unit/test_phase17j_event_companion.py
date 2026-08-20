from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from itertools import pairwise, permutations
from pathlib import Path
from typing import Any, cast

import msgspec
import pytest

from warhammer40k_core.core.deployment_zones import (
    DeploymentZonePoint,
    DeploymentZonePolygon,
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
from warhammer40k_core.core.ruleset_descriptor import LineOfSightPolicy, RulesetDescriptor
from warhammer40k_core.core.terrain_areas import (
    TerrainAreaClassification,
    TerrainAreaLocalTransform,
)
from warhammer40k_core.core.terrain_display import TerrainDisplayPoint
from warhammer40k_core.engine import mission_action_policies
from warhammer40k_core.engine.final_scoring import FinalScoringResult
from warhammer40k_core.engine.mission_setup import MissionSetup, MissionSetupError
from warhammer40k_core.engine.missions import (
    deterministic_tactical_secondary_draw,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    validate_mission_setup_source_layout,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.scoring import (
    ScoringWindowKind,
    ScoringWindowState,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
)
from warhammer40k_core.engine.shooting_terrain_visibility import (
    model_within_solid_terrain,
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.polygons import polygon_overlap_area
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.visibility import (
    BenefitOfCoverResult,
    CoverSourceReason,
    TerrainAreaCoverSourceRecord,
    TerrainVisibilityContext,
    VisibilityBlockerKind,
)
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_2026_06 as event_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_base_size_rows,
    event_companion_patches,
    july_rules_updates_2026_07,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_layouts_2026_06 as event_layouts,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    event_companion_primary_scoring_2026_06 as event_primary_scoring,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.event_companion_layout_geometry_2026_06 import (  # noqa: E501
    event_no_mans_land_shape,
    event_territory_vertices,
    terrain_area_classifications_by_suffix,
    terrain_feature_placements_from_specs,
)


def test_phase17j_event_companion_package_identity_and_payload_round_trip() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    source_package = mission_pack.source_package
    payload = mission_pack.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = cast(MissionPackDefinitionPayload, json.loads(encoded))

    assert mission_pack.mission_pack_id == "11e-warhammer-event-companion-2026-07"
    assert source_package.source_commit_or_import_hash == (
        "9e86c81513efe6f0842db2ff14df8a026d085818cc2df3abf9fbff7662d8e9e5"
    )
    assert source_package.to_payload() == {
        "edition_id": "warhammer_40000_11th",
        "mission_pack_id": "11e-warhammer-event-companion-2026-07",
        "source_package_id": "gw-11e-warhammer-event-companion-v1-1-2026-07",
        "source_title": "Warhammer Event Companion v1.1",
        "source_version": "1.1",
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
        "document_version": "1.1",
        "event_mode": "warhammer_event",
        "battlefield_size": "44x60_inches",
        "excludes_deployment_cards": True,
        "excludes_twist_cards": True,
        "source_id": "gw-11e-warhammer-event-companion-v1-1-2026-07:package-identity",
    }


def test_phase17j_v1_1_layout_revisions_preserve_deployment_zone_templates() -> None:
    rows = july_rules_updates_2026_07.changed_event_layouts()

    assert {
        row.layout_id: (row.source_page, row.deployment_zone_template_number) for row in rows
    } == {
        "take-and-hold-vs-purge-the-foe-layout-1": (12, 4),
        "take-and-hold-vs-purge-the-foe-layout-2": (13, 3),
        "take-and-hold-vs-purge-the-foe-layout-3": (14, 5),
        "purge-the-foe-vs-disruption-layout-1": (27, 3),
        "purge-the-foe-vs-disruption-layout-2": (28, 1),
        "purge-the-foe-vs-disruption-layout-3": (29, 4),
        "disruption-vs-reconnaissance-layout-1": (39, 1),
        "disruption-vs-reconnaissance-layout-3": (41, 3),
    }
    assert all(row.terrain_changed for row in rows)
    assert all(not row.deployment_zones_changed for row in rows)


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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    artifact_layouts_by_id = {
        layout.layout_id: layout for layout in event_layouts.battlefield_artifact().layouts
    }
    layout_ids = {layout.terrain_layout_id for layout in mission_pack.terrain_layout_templates}
    deployment_map_ids = {
        deployment.deployment_map_id for deployment in mission_pack.deployment_maps
    }
    pool_layout_ids = {entry.terrain_layout_ids[0] for entry in mission_pack.mission_pool_entries}

    assert len(mission_pack.primary_missions) == 25
    assert len(mission_pack.primary_mission_matrix_cells) == 25
    assert all(
        cell.source_status is MissionSourceStatus.IMPLEMENTED
        for cell in mission_pack.primary_mission_matrix_cells
    )
    assert len(layout_ids) == 45
    assert layout_ids == event_layouts.BATTLEFIELD_LAYOUT_IDS
    assert len(mission_pack.battlefield_layouts) == 45
    assert len(mission_pack.terrain_area_footprint_templates) == 5
    assert len(mission_pack.terrain_feature_presets) == 14
    assert {
        preset.terrain_feature_preset_id for preset in mission_pack.terrain_feature_presets
    } == {
        f"event-companion-exact-{archetype.archetype_id}"
        for archetype in event_layouts.battlefield_artifact().feature_archetypes
    }
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
            attacker_force_disposition_id=entry.player_force_disposition_id,
            defender_player_id="player-beta",
            defender_force_disposition_id=entry.opponent_force_disposition_id,
        )
        assert setup.battlefield_width_inches == 44.0
        assert setup.battlefield_depth_inches == 60.0
        terrain_layout_id = entry.terrain_layout_ids[0]
        artifact_layout = artifact_layouts_by_id[terrain_layout_id]
        assert setup.battlefield_layout_id == terrain_layout_id
        assert len(setup.terrain_features) == len(artifact_layout.terrain_components)
        assert len(setup.terrain_areas) == 16
        assert len(setup.battlefield_regions) == 5
        assert len(setup.objective_markers) == len(artifact_layout.objectives)
        assert len(setup.deployment_zones) == 2

    assert Counter(row.source_status for row in event_source.battlefield_layout_rows()) == Counter(
        {"event_companion_source_hashed_battlefield_artifact": 45}
    )
    assert Counter(
        descriptor.geometry_extraction_status
        for descriptor in event_source.layout_descriptor_rows()
    ) == Counter({"source_hashed_battlefield_artifact_geometry": 45})


def test_phase17n_event_layout_rejects_missing_component_placements() -> None:
    with pytest.raises(MissionPackError, match="requires explicit terrain component placements"):
        terrain_feature_placements_from_specs(
            layout_id="event-layout",
            source_layout_id="source-layout",
            source_package_id="source-package",
            terrain_areas=(),
            specs=(),
        )
    with pytest.raises(MissionPackError, match="requires polygons"):
        event_no_mans_land_shape(explicit_polygons=())
    with pytest.raises(MissionPackError, match="require source polygons"):
        event_territory_vertices(explicit_specs=())
    with pytest.raises(MissionPackError, match="must cover every explicit area"):
        terrain_area_classifications_by_suffix(
            explicit_specs=(("terrain-area", "FOOTPRINT_6X4", 0.0, 0.0, 0.0),),
            classification_specs=(),
        )


def test_phase17n_primary_scoring_artifact_is_source_hashed_strict_and_consumed() -> None:
    artifact = event_primary_scoring.event_companion_primary_scoring_artifact()
    repository_root = Path(__file__).resolve().parents[2]
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_2026_06_artifacts/primary-scoring.json"
    )
    raw = artifact_path.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        event_primary_scoring.PRIMARY_SCORING_ARTIFACT_SHA256
    )
    assert artifact.package_hash == event_primary_scoring.PRIMARY_SCORING_PACKAGE_HASH
    assert artifact.authoritative_source.source_kind == (
        "project_owner_supplied_official_source_transcription"
    )
    assert artifact.authoritative_source.official_source_binary_status == (
        "not_committed_transcription_review_only"
    )
    assert tuple(
        (review.pull_request, review.commit)
        for review in artifact.authoritative_source.review_records
    ) == (
        (107, "c0fe665249a4a39e5bf5ca19c38bb18b4a9dc56a"),
        (134, "35b9ddaf5a49ad947177712a883fd0c76e3db224"),
        (136, "34e05f19886c8c483fb0fa7c3e1ba86626bb89f1"),
        (379, "15af220739679f5aa84dd16981ae3e7dbaa93520"),
    )
    assert artifact.secondary_corroborations[0].authority_status == (
        "secondary_corroboration_not_official_gw_source"
    )
    assert artifact.secondary_corroborations[0].card_image_sha256 == (
        "d4bcc1dfde2d72fb2fc31b095964d1ea7721dcd082967b0063bcfd77c9965c24"
    )
    assert artifact.layout_source_boundary.source_pages == tuple(range(9, 54))
    assert artifact.layout_source_boundary.authority_scope == ("battlefield_and_layout_facts_only")
    assert not artifact.layout_source_boundary.contains_primary_mission_card_scoring_clauses
    assert artifact.scoring_limit_source.source_pdf_filename == (
        "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
    )
    assert artifact.scoring_limit_source.source_pdf_sha256 == (
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
    )
    assert artifact.scoring_limit_source.source_pages == (2, 4)
    assert artifact.scoring_limit_source.primary_max_vp_per_battle_round == 15
    assert artifact.scoring_limit_source.end_of_battle_primary_vp_exempt
    assert len(artifact.primary_missions) == 25
    assert {mission.max_vp_per_turn for mission in artifact.primary_missions} == {15}
    assert sum(len(mission.scoring_rules) for mission in artifact.primary_missions) == 100
    assert len(artifact.primary_mission_actions) == 10
    assert {action.engine_exposure_status for action in artifact.primary_mission_actions} == {
        "engine_implemented"
    }
    assert len(artifact.primary_mission_state_rules) == 2
    assert len(artifact.primary_mission_choice_rules) == 3
    state_rules = {rule.state_rule_id: rule for rule in artifact.primary_mission_state_rules}
    assert msgspec.to_builtins(state_rules["surveil-remove-operation-markers-after-move"]) == {
        "state_rule_id": "surveil-remove-operation-markers-after-move",
        "primary_mission_id": "primary-surveil-the-foe",
        "trigger_timing": "friendly_rules_unit_move_end",
        "subject_policy": (
            "moving_friendly_rules_unit_within_range_of_objective_with_opponent_operation_markers"
        ),
        "effect_descriptor": ("remove_all_opponent_operation_markers_from_each_in_range_objective"),
        "effect_duration": "immediate",
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-state-rule:"
            "surveil-remove-operation-markers-after-move"
        ),
    }
    choice_rules = {rule.choice_rule_id: rule for rule in artifact.primary_mission_choice_rules}
    assert msgspec.to_builtins(choice_rules["consecrate-objective-at-turn-end"]) == {
        "choice_rule_id": "consecrate-objective-at-turn-end",
        "primary_mission_id": "primary-consecrate",
        "trigger_timing": "own_turn_end",
        "subject_policy": "each_friendly_consecration_unit",
        "target_policy": "objective_within_subject_range_excluding_home_not_consecrated",
        "selection_policy": "optional_up_to_one_per_subject",
        "minimum_selections": 0,
        "maximum_selections": 1,
        "fallback_target_policy": None,
        "effect_descriptor": (
            "place_friendly_operation_marker_consecrate_objective_and_consume_unit_status"
        ),
        "effect_duration": "persistent",
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-choice-rule:"
            "consecrate-objective-at-turn-end"
        ),
    }
    assert msgspec.to_builtins(choice_rules["locate-and-deny-operation-marker-setup"]) == {
        "choice_rule_id": "locate-and-deny-operation-marker-setup",
        "primary_mission_id": "primary-locate-and-deny",
        "trigger_timing": "battle_start",
        "subject_policy": None,
        "target_policy": "terrain_area_outside_own_deployment_zone",
        "selection_policy": "exactly_five_or_all_available_when_fewer",
        "minimum_selections": 0,
        "maximum_selections": 5,
        "fallback_target_policy": None,
        "effect_descriptor": "place_one_friendly_operation_marker_in_each_selected_terrain_area",
        "effect_duration": "persistent",
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-choice-rule:"
            "locate-and-deny-operation-marker-setup"
        ),
    }
    punishment_choice = choice_rules["punishment-condemn-enemy-units"]
    assert punishment_choice.minimum_selections == 1
    assert punishment_choice.maximum_selections == 3
    assert punishment_choice.fallback_target_policy == "enemy_battlefield_unit"
    assert punishment_choice.effect_duration == "until_start_of_own_next_turn"
    assert Counter(
        mission.engine_support_status for mission in artifact.primary_missions
    ) == Counter({"engine_implemented": 25})
    all_scoring_rules = tuple(
        rule for mission in artifact.primary_missions for rule in mission.scoring_rules
    )
    assert {rule.timing for rule in all_scoring_rules} == {
        "battle_round_four_onwards_turn_end",
        "battle_rounds_two_and_three_command_phase",
        "command_phase",
        "command_phase_or_round_five_turn_end",
        "end_of_battle",
        "first_and_second_battle_round_turn_end",
        "first_battle_round_turn_end",
        "turn_end",
        "turn_end_from_battle_round_two",
    }
    assert Counter(rule.resolution_mode for rule in all_scoring_rules) == Counter(
        {"independent": 86, "cumulative": 10, "exclusive_highest": 4}
    )
    assert {
        mission.primary_mission_id
        for mission in artifact.primary_missions
        if mission.engine_support_status == "engine_implemented"
    } == {
        "primary-battlefield-dominance",
        "primary-consecrate",
        "primary-death-trap",
        "primary-delaying-action",
        "primary-destroyers-wrath",
        "primary-determined-acquisition",
        "primary-extract-relic",
        "primary-gather-intel",
        "primary-immovable-object",
        "primary-inescapable-dominion",
        "primary-locate-and-deny",
        "primary-meatgrinder",
        "primary-outmaneuver",
        "primary-punishment",
        "primary-purge-and-secure",
        "primary-reconnaissance-sweep",
        "primary-sabotage",
        "primary-search-and-scour",
        "primary-secure-asset",
        "primary-smoke-and-mirrors",
        "primary-surveil-the-foe",
        "primary-triangulation",
        "primary-unstoppable-force",
        "primary-vanguard-operation",
        "primary-vital-link",
    }
    grouped_rule_ids: dict[str, tuple[str, ...]] = {}
    for group_id in sorted(
        {
            rule.resolution_group_id
            for rule in all_scoring_rules
            if rule.resolution_group_id is not None
        }
    ):
        grouped_rule_ids[group_id] = tuple(
            rule.rule_id for rule in all_scoring_rules if rule.resolution_group_id == group_id
        )
    assert grouped_rule_ids == {
        "battlefield-dominance-command-primary": (
            "battlefield-dominance-each-objective",
            "battlefield-dominance-home-controlled-non-home-bonus",
        ),
        "determined-acquisition-command-primary": (
            "determined-acquisition-each-objective",
            "determined-acquisition-opponent-territory-bonus",
        ),
        "purge-and-secure-destruction-primary": (
            "purge-and-secure-destroyed-by-objective-unit-turn-end",
            "purge-and-secure-started-objective-destroyed-turn-end",
        ),
        "reconnaissance-sweep-quarters-primary": (
            "reconnaissance-sweep-three-quarters-turn-end",
            "reconnaissance-sweep-four-quarters-turn-end",
        ),
        "sabotage-turn-end-primary": (
            "sabotage-each-unit-turn-end",
            "sabotage-opponent-territory-bonus-turn-end",
        ),
        "vital-link-command-primary": (
            "vital-link-objective-control",
            "vital-link-central-objective-bonus",
        ),
        "vital-link-turn-end-primary": (
            "vital-link-central-objective-turn-end",
            "vital-link-operation-marker-central-bonus-turn-end",
        ),
    }

    artifact_missions = {
        mission.primary_mission_id: mission for mission in artifact.primary_missions
    }
    meatgrinder = artifact_missions["primary-meatgrinder"]
    assert tuple(rule.canonical_text for rule in meatgrinder.scoring_rules) == (
        "One or more enemy units were destroyed this turn.",
        "You control one or more objectives (excluding your home objective).",
        (
            "More enemy units were destroyed this turn than friendly units were "
            "destroyed in the previous turn."
        ),
        "You control your opponent's home objective.",
    )
    assert {
        mission.primary_mission_id
        for mission in artifact.primary_missions
        if any(rule.canonical_text is not None for rule in mission.scoring_rules)
    } == {"primary-meatgrinder"}

    runtime_rows = {row.primary_mission_id: row for row in event_source.primary_mission_rows()}
    assert set(runtime_rows) == set(artifact_missions)
    for mission_id, artifact_mission in artifact_missions.items():
        runtime_row = runtime_rows[mission_id]
        assert runtime_row.name == artifact_mission.mission_name
        assert runtime_row.scoring_kind == artifact_mission.scoring_kind
        assert runtime_row.max_vp_per_turn == artifact_mission.max_vp_per_turn == 15
        assert tuple(rule.to_payload() for rule in runtime_row.scoring_rules) == tuple(
            {
                "rule_id": rule.rule_id,
                "timing": rule.timing,
                "source_kind": rule.source_kind,
                "victory_points": rule.victory_points,
                "cap": rule.cap,
                "condition": rule.condition,
                "resolution_mode": rule.resolution_mode,
                "resolution_group_id": rule.resolution_group_id,
            }
            for rule in artifact_mission.scoring_rules
        )
    assert tuple(
        row.to_payload() for row in event_source.primary_mission_action_source_rows()
    ) == tuple(msgspec.to_builtins(row) for row in artifact.primary_mission_actions)
    event_primary_scoring.validate_event_companion_primary_scoring_artifact_bytes(raw)

    with pytest.raises(ValueError, match="artifact bytes drifted"):
        event_primary_scoring.validate_event_companion_primary_scoring_artifact_bytes(raw + b"\n")

    unknown_field_payload = json.loads(raw)
    unknown_field_payload["primary_missions"][0]["scoring_rules"][0]["unexpected"] = True
    with pytest.raises(ValueError, match="artifact is invalid"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(unknown_field_payload).encode()
        )

    missing_resolution_payload = json.loads(raw)
    del missing_resolution_payload["primary_missions"][0]["scoring_rules"][0]["resolution_mode"]
    with pytest.raises(ValueError, match="artifact is invalid"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(missing_resolution_payload).encode()
        )

    unsupported_timing_payload = json.loads(raw)
    unsupported_timing_payload["primary_missions"][0]["scoring_rules"][0]["timing"] = (
        "forged_timing"
    )
    with pytest.raises(ValueError, match="timing grammar is unsupported"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(unsupported_timing_payload).encode()
        )

    scoring_limit_drift_payload = json.loads(raw)
    scoring_limit_drift_payload["scoring_limit_source"]["primary_max_vp_per_battle_round"] = 16
    with pytest.raises(ValueError, match="scoring-limit provenance drifted"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(scoring_limit_drift_payload).encode()
        )

    mission_limit_drift_payload = json.loads(raw)
    mission_limit_drift_payload["primary_missions"][0]["max_vp_per_turn"] = 16
    with pytest.raises(ValueError, match="source-backed 15VP per-battle-round cap"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(mission_limit_drift_payload).encode()
        )

    independent_group_payload = json.loads(raw)
    independent_group_payload["primary_missions"][0]["scoring_rules"][0]["resolution_group_id"] = (
        "forged-resolution-group"
    )
    with pytest.raises(ValueError, match=r"Independent .* cannot declare a resolution group"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(independent_group_payload).encode()
        )

    unsupported_resolution_payload = json.loads(raw)
    unsupported_resolution_payload["primary_missions"][0]["scoring_rules"][0]["resolution_mode"] = (
        "forged_resolution"
    )
    with pytest.raises(ValueError, match="resolution mode is unsupported"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(unsupported_resolution_payload).encode()
        )

    stale_hash_payload = json.loads(raw)
    stale_hash_payload["primary_missions"][11]["scoring_rules"][2]["canonical_text"] += " Drift."
    with pytest.raises(ValueError, match="package hash is stale"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(stale_hash_payload).encode()
        )

    rehashed_drift_payload = stale_hash_payload
    rehashed_drift_payload["package_hash"] = ""
    rehashed_drift_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            rehashed_drift_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="drifted from its reviewed pin"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(rehashed_drift_payload).encode()
        )

    demoted_status_payload = json.loads(raw)
    demoted_status_payload["primary_missions"][0]["engine_support_status"] = (
        "source_known_engine_pending"
    )
    with pytest.raises(ValueError, match="engine support truth drifted"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(demoted_status_payload).encode()
        )

    grammar_drift_payload = json.loads(raw)
    grammar_drift_payload["primary_missions"][0]["scoring_rules"][1]["resolution_group_id"] = (
        "forged-resolution-group"
    )
    with pytest.raises(ValueError, match="resolution group"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(grammar_drift_payload).encode()
        )

    demoted_action_payload = json.loads(raw)
    demoted_action_payload["primary_mission_actions"][0]["engine_exposure_status"] = (
        "source_known_engine_pending"
    )
    with pytest.raises(ValueError, match="must be engine-implemented"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(demoted_action_payload).encode()
        )

    state_rule_drift_payload = json.loads(raw)
    state_rule_drift_payload["primary_mission_state_rules"][0]["effect_descriptor"] = (
        "forged_state_effect"
    )
    with pytest.raises(ValueError, match="state-rule clauses drifted"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(state_rule_drift_payload).encode()
        )

    choice_rule_drift_payload = json.loads(raw)
    choice_rule_drift_payload["primary_mission_choice_rules"][1]["maximum_selections"] = 4
    with pytest.raises(ValueError, match="choice-rule clauses drifted"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(choice_rule_drift_payload).encode()
        )


def test_phase17n_primary_scoring_artifact_names_cannot_drift_from_matrix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rows = event_source.primary_mission_rows()
    artifact_rows = {row.primary_mission_id: row for row in rows}
    first = rows[0]
    artifact_rows[first.primary_mission_id] = replace(first, name="Drifted Primary Name")

    monkeypatch.setattr(event_source, "_event_primary_mission_rows_by_id", lambda: artifact_rows)

    with pytest.raises(MissionPackError, match="artifact name drifted from the matrix"):
        event_source.primary_mission_rows()


def test_phase17n_battlefield_artifact_is_source_hashed_and_strict() -> None:
    artifact = event_layouts.battlefield_artifact()
    repository_root = Path(__file__).resolve().parents[2]
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_layouts_2026_06/artifacts"
        / "event-companion-battlefields.json"
    )
    source_pdf_path = (
        repository_root
        / "docs/source_rules"
        / "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
    )
    raw = artifact_path.read_bytes()

    assert artifact.source_pages == tuple(range(8, 54))
    assert len(artifact.source_extraction_payload_sha256) == 64
    assert artifact.source_pdf_sha256 == (
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
    )
    assert hashlib.sha256(source_pdf_path.read_bytes()).hexdigest() == artifact.source_pdf_sha256
    assert artifact.source_pdf_sha256 == event_layouts.BATTLEFIELD_SOURCE_PDF_SHA256
    assert hashlib.sha256(raw).hexdigest() == event_layouts.BATTLEFIELD_ARTIFACT_SHA256
    assert artifact.package_hash == event_layouts.BATTLEFIELD_PACKAGE_HASH
    assert len(artifact.feature_archetypes) == 14
    assert len(artifact.layouts) == 45
    assert frozenset(layout.layout_id for layout in artifact.layouts) == (
        event_layouts.BATTLEFIELD_LAYOUT_IDS
    )
    assert sum(len(layout.terrain_areas) for layout in artifact.layouts) == 720
    assert sum(len(layout.terrain_components) for layout in artifact.layouts) == 1_349
    page_9_layout_id = "take-and-hold-vs-take-and-hold-layout-1"
    assert {layout.layout_id: len(layout.terrain_components) for layout in artifact.layouts}[
        page_9_layout_id
    ] == 29
    assert all(
        len(layout.terrain_areas) == 16
        and len(layout.terrain_components) == (29 if layout.layout_id == page_9_layout_id else 30)
        for layout in artifact.layouts
    )

    increment = artifact.source_coordinate_frame.terrain_placement_increment_inches
    assert increment == 0.05
    assert (
        artifact.source_coordinate_frame.runtime_exact_seam_closure_precision_decimal_places == 12
    )
    assert all(
        math.isclose(
            coordinate / increment,
            round(coordinate / increment),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for layout in artifact.layouts
        for area in layout.terrain_areas
        if area.pose_basis != "reviewed_source_pose_with_exact_seam_closure"
        for coordinate in (area.anchor_x_inches, area.anchor_y_inches)
    )
    assert all(
        math.isclose(
            coordinate / increment,
            round(coordinate / increment),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for layout in artifact.layouts
        for area in layout.terrain_areas
        for coordinate in (area.source_anchor_x_inches, area.source_anchor_y_inches)
    )
    assert all(
        math.isclose(
            coordinate / increment,
            round(coordinate / increment),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        for layout in artifact.layouts
        for component in layout.terrain_components
        for coordinate in (
            component.battlefield_center_x_inches,
            component.battlefield_center_y_inches,
        )
    )

    meatgrinder_layouts = _meatgrinder_artifact_layouts()
    assert {
        area.area_id: (area.anchor_x_inches, area.anchor_y_inches)
        for layout in meatgrinder_layouts
        for area in layout.terrain_areas
        if area.footprint_template_id == "FOOTPRINT_8X11_5_POLYGON"
    } == {
        "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-02": (
            27.05,
            50.2,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-15": (
            16.95,
            9.8,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-03": (
            15.9,
            44.1,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-14": (
            28.1,
            15.9,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-05": (
            32.05,
            43.0,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-12": (
            11.95,
            17.0,
        ),
    }
    assert tuple(
        asset.source_pdf_image_xref
        for archetype in artifact.feature_archetypes
        if archetype.archetype_id == "dense-tall-crates"
        for asset in archetype.source_assets
    ) == (
        5486,
        5675,
        5519,
        5558,
        5678,
        5680,
        1014,
        1556,
        2073,
        3151,
        3153,
        3415,
        3417,
        3835,
        3968,
        4648,
        4900,
    )
    event_layouts.validate_battlefield_artifact_bytes(raw)

    unknown_field_payload = json.loads(raw)
    unknown_field_payload["unexpected"] = True
    with pytest.raises(ValueError, match="artifact is invalid"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(unknown_field_payload).encode()
        )

    missing_source_assets_payload = json.loads(raw)
    missing_source_assets_payload["feature_archetypes"][0]["source_assets"] = []
    with pytest.raises(ValueError, match="feature-archetype identity or semantics drifted"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(missing_source_assets_payload).encode()
        )

    duplicate_logical_member_payload = json.loads(raw)
    single_contacts = [
        contact
        for contact in duplicate_logical_member_payload["layouts"][0]["terrain_area_contacts"]
        if contact["kind"] == "single"
    ]
    single_contacts[1]["terrain_area_ids"][0] = single_contacts[0]["terrain_area_ids"][0]
    single_contacts[1]["source_terrain_area_ids"][0] = single_contacts[0][
        "source_terrain_area_ids"
    ][0]
    with pytest.raises(ValueError, match="belongs to multiple logical areas"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(duplicate_logical_member_payload).encode()
        )

    open_runtime_seam_payload = json.loads(raw)
    open_single_contact = next(
        contact
        for layout in open_runtime_seam_payload["layouts"]
        for contact in layout["terrain_area_contacts"]
        if contact["kind"] == "single"
    )
    open_single_contact["runtime_pair_gap_inches"] = 0.05001
    with pytest.raises(ValueError, match="source-contact record is invalid"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(open_runtime_seam_payload).encode()
        )

    open_separate_seam_payload = json.loads(raw)
    open_separate_contact = next(
        contact
        for layout in open_separate_seam_payload["layouts"]
        for contact in layout["terrain_area_contacts"]
        if contact["kind"] == "separate"
    )
    open_separate_contact["runtime_pair_gap_inches"] = 0.05001
    with pytest.raises(ValueError, match="source-contact record is invalid"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(open_separate_seam_payload).encode()
        )

    overlapping_runtime_seam_payload = json.loads(raw)
    overlapping_runtime_seam_payload["layouts"][0]["terrain_area_contacts"][0][
        "runtime_pair_overlap_square_inches"
    ] = 0.000002
    with pytest.raises(ValueError, match="source-contact record is invalid"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(overlapping_runtime_seam_payload).encode()
        )

    reviewed_adjustment_drift_payload = json.loads(raw)
    page_29_payload = next(
        layout
        for layout in reviewed_adjustment_drift_payload["layouts"]
        if layout["source_page"] == 29
    )
    reviewed_adjustment_area = next(
        area
        for area in page_29_payload["terrain_areas"]
        if area["source_area_id"].endswith("terrain-area-04")
    )
    reviewed_adjustment_area["runtime_adjustment_y_inches"] = 0.35
    reviewed_adjustment_area["anchor_y_inches"] = (
        reviewed_adjustment_area["source_anchor_y_inches"] + 0.35
    )
    with pytest.raises(ValueError, match="source adjustment exceeds its reviewed bound"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(reviewed_adjustment_drift_payload).encode()
        )

    reviewed_candidate_drift_payload = json.loads(raw)
    reviewed_candidate_area = next(
        area
        for layout in reviewed_candidate_drift_payload["layouts"]
        for area in layout["terrain_areas"]
        if area["source_area_id"] == "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-02"
    )
    reviewed_candidate_area["source_pose_candidate_index"] = 0
    reviewed_candidate_drift_payload["package_hash"] = ""
    reviewed_candidate_drift_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            reviewed_candidate_drift_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="source adjustment exceeds its reviewed bound"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(reviewed_candidate_drift_payload).encode()
        )

    exact_seam_drift_payload = json.loads(raw)
    exact_seam_area = next(
        area
        for layout in exact_seam_drift_payload["layouts"]
        for area in layout["terrain_areas"]
        if area["source_area_id"] == "disruption-vs-disruption-layout-1-terrain-area-10"
    )
    exact_seam_area["runtime_adjustment_x_inches"] += 0.000001
    exact_seam_area["anchor_x_inches"] += 0.000001
    with pytest.raises(ValueError, match="source adjustment exceeds its reviewed bound"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(exact_seam_drift_payload).encode()
        )

    component_adjustment_drift_payload = json.loads(raw)
    component_adjustment = next(
        component
        for layout in component_adjustment_drift_payload["layouts"]
        for component in layout["terrain_components"]
        if component["source_component_id"]
        == "purge-the-foe-vs-disruption-layout-3-terrain-area-04-component-01"
    )
    component_adjustment["runtime_adjustment_x_inches"] = -0.05
    component_adjustment["battlefield_center_x_inches"] = (
        component_adjustment["source_battlefield_center_x_inches"] - 0.05
    )
    with pytest.raises(ValueError, match="component containment adjustment drifted"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(component_adjustment_drift_payload).encode()
        )

    pipe_basis_drift_payload = json.loads(raw)
    pipe_component = next(
        component
        for layout in pipe_basis_drift_payload["layouts"]
        if layout["source_page"] not in {24, 25, 26}
        for component in layout["terrain_components"]
        if component["archetype_id"] == "dense-long-pipes"
    )
    pipe_component["pose_basis"] = "reviewed_source_quantized_pose"
    with pytest.raises(ValueError, match="component pose basis drifted"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(pipe_basis_drift_payload).encode()
        )

    pipe_pose_drift_payload = json.loads(raw)
    pipe_layout = next(
        layout
        for layout in pipe_pose_drift_payload["layouts"]
        if layout["source_page"] not in {24, 25, 26}
        and any(
            component["pose_basis"] == "reviewed_parent_footprint_centered_pipe_pose"
            for component in layout["terrain_components"]
        )
    )
    pipe_component = next(
        component
        for component in pipe_layout["terrain_components"]
        if component["pose_basis"] == "reviewed_parent_footprint_centered_pipe_pose"
    )
    pipe_area = next(
        area
        for area in pipe_layout["terrain_areas"]
        if area["area_id"] == pipe_component["terrain_area_id"]
    )
    first_vertex_x, first_vertex_y = (-3.05, 1.15)
    area_radians = math.radians(pipe_area["rotation_degrees"])
    area_cosine = math.cos(area_radians)
    area_sine = math.sin(area_radians)
    area_center_x = pipe_area["anchor_x_inches"] - (
        first_vertex_x * area_cosine - first_vertex_y * area_sine
    )
    area_center_y = pipe_area["anchor_y_inches"] - (
        first_vertex_x * area_sine + first_vertex_y * area_cosine
    )
    mirrored_center_x = (
        2.0 * first_vertex_x if pipe_area["local_transform"] == "mirror_y_axis" else 0.0
    )
    centered_x = round(
        round(
            (area_center_x + mirrored_center_x * area_cosine) / 0.05,
        )
        * 0.05,
        6,
    )
    current_center_x = pipe_component["battlefield_center_x_inches"]
    alternative_center_x = round(
        current_center_x + (-0.05 if current_center_x - centered_x >= 0.05 else 0.05),
        6,
    )
    pipe_component["battlefield_center_x_inches"] = alternative_center_x
    pipe_component["runtime_adjustment_x_inches"] = round(
        alternative_center_x - pipe_component["source_battlefield_center_x_inches"],
        6,
    )
    delta_x = alternative_center_x - area_center_x
    delta_y = pipe_component["battlefield_center_y_inches"] - area_center_y
    transformed_x = delta_x * area_cosine + delta_y * area_sine
    pipe_component["local_offset_y_inches"] = round(
        -delta_x * area_sine + delta_y * area_cosine,
        6,
    )
    pipe_component["local_offset_x_inches"] = round(
        2.0 * first_vertex_x - transformed_x
        if pipe_area["local_transform"] == "mirror_y_axis"
        else transformed_x,
        6,
    )
    pipe_pose_drift_payload["package_hash"] = ""
    pipe_pose_drift_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            pipe_pose_drift_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="parent-centered pipe pose drifted"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(pipe_pose_drift_payload).encode()
        )

    stale_hash_payload = json.loads(raw)
    stale_hash_payload["layouts"][0]["objectives"][0]["x_inches"] = 8.59
    with pytest.raises(ValueError, match="package hash is stale"):
        event_layouts.validate_battlefield_artifact_bytes(json.dumps(stale_hash_payload).encode())

    rehashed_coordinate_payload = json.loads(raw)
    rehashed_coordinate_payload["layouts"][0]["objectives"][0]["x_inches"] = 8.59
    rehashed_coordinate_payload["package_hash"] = ""
    rehashed_coordinate_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            rehashed_coordinate_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="drifted from its reviewed pin"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(rehashed_coordinate_payload).encode()
        )

    unreflected_source_affine_payload = json.loads(raw)
    meatgrinder_a_payload = next(
        layout
        for layout in unreflected_source_affine_payload["layouts"]
        if layout["source_page"] == 24
    )
    meatgrinder_a_payload["terrain_areas"][3]["local_transform"] = "identity"
    unreflected_source_affine_payload["package_hash"] = ""
    unreflected_source_affine_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            unreflected_source_affine_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="reflection must match its source affine"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(unreflected_source_affine_payload).encode()
        )

    asymmetric_component_payload = json.loads(raw)
    meatgrinder_a_payload = next(
        layout for layout in asymmetric_component_payload["layouts"] if layout["source_page"] == 24
    )
    asymmetric_component = next(
        component
        for component in meatgrinder_a_payload["terrain_components"]
        if component["component_id"].endswith("terrain-area-11-component-02")
    )
    asymmetric_component["battlefield_rotation_degrees"] += 1.0
    asymmetric_component["runtime_rotation_adjustment_degrees"] += 1.0
    asymmetric_component["local_rotation_degrees"] += 1.0
    asymmetric_component_payload["package_hash"] = ""
    asymmetric_component_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            asymmetric_component_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="point symmetry"):
        event_layouts.validate_battlefield_artifact_bytes(
            json.dumps(asymmetric_component_payload).encode()
        )


def test_phase17n_all_layout_geometry_closes_declared_seams_and_region_holes() -> None:
    artifact = event_layouts.battlefield_artifact()
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    board = shapely_backend.footprint_for_polygon(
        ((0.0, 0.0), (44.0, 0.0), (44.0, 60.0), (0.0, 60.0))
    )
    checked_area_contacts = 0
    checked_component_contacts = 0
    checked_component_containment = 0
    checked_objective_bindings = 0
    area_contact_kinds: Counter[str] = Counter()
    logical_terrain_area_ids: set[str] = set()

    def shape_footprint(shape: DeploymentZoneShape) -> Any:
        polygons = tuple(
            shapely_backend.footprint_for_polygon(polygon) for polygon in _shape_polygons(shape)
        )
        result = polygons[0]
        for polygon in polygons[1:]:
            result = result.union(polygon)
        return result

    for source_layout in artifact.layouts:
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=f"mission-{source_layout.layout_id}",
            attacker_player_id="player-alpha",
            attacker_force_disposition_id=source_layout.force_disposition_pair[0],
            defender_player_id="player-beta",
            defender_force_disposition_id=source_layout.force_disposition_pair[1],
        )
        areas_by_id = {area.terrain_area_id: area for area in setup.terrain_areas}
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        objectives_by_id = {
            objective.objective_marker_id: objective for objective in setup.objective_markers
        }

        for contact in source_layout.terrain_area_contacts:
            first_id, second_id = contact.terrain_area_ids
            first_points = _terrain_display_points(areas_by_id[first_id].footprint_polygon)
            second_points = _terrain_display_points(areas_by_id[second_id].footprint_polygon)
            first = shapely_backend.footprint_for_polygon(first_points)
            second = shapely_backend.footprint_for_polygon(second_points)
            runtime_overlap = first.intersection(second).area
            runtime_gap = first.distance(second)
            assert runtime_overlap <= 1e-6
            assert runtime_gap <= 0.05 + 1e-6
            assert math.isclose(
                contact.runtime_pair_overlap_square_inches,
                runtime_overlap,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            assert math.isclose(
                contact.runtime_pair_gap_inches,
                runtime_gap,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            first_group_id = areas_by_id[first_id].logical_terrain_area_id
            second_group_id = areas_by_id[second_id].logical_terrain_area_id
            assert (first_group_id == second_group_id) is (contact.kind == "single")
            checked_area_contacts += 1
            area_contact_kinds[contact.kind] += 1

        for first_id, second_id in source_layout.terrain_component_contact_pairs:
            first_points = _terrain_display_points(features_by_id[first_id].rules_footprint_polygon)
            second_points = _terrain_display_points(
                features_by_id[second_id].rules_footprint_polygon
            )
            first = shapely_backend.footprint_for_polygon(first_points)
            second = shapely_backend.footprint_for_polygon(second_points)
            assert first.distance(second) <= 1e-9
            checked_component_contacts += 1

        areas_by_logical_id: dict[str, list[Any]] = {}
        for area in setup.terrain_areas:
            areas_by_logical_id.setdefault(area.logical_terrain_area_id, []).append(area)
        for component in source_layout.terrain_components:
            parent = areas_by_id[component.terrain_area_id]
            logical_members = areas_by_logical_id[parent.logical_terrain_area_id]
            logical_footprint = shapely_backend.footprint_for_polygon(
                _terrain_display_points(logical_members[0].footprint_polygon)
            )
            for member in logical_members[1:]:
                logical_footprint = logical_footprint.union(
                    shapely_backend.footprint_for_polygon(
                        _terrain_display_points(member.footprint_polygon)
                    )
                )
            component_footprint = shapely_backend.footprint_for_polygon(
                _terrain_display_points(
                    features_by_id[component.component_id].rules_footprint_polygon
                )
            )
            assert component_footprint.difference(logical_footprint).area <= 1e-6
            checked_component_containment += 1

        layout_logical_ids = {area.logical_terrain_area_id for area in setup.terrain_areas}
        assert len(layout_logical_ids) == 16 - sum(
            contact.kind == "single" for contact in source_layout.terrain_area_contacts
        )
        logical_terrain_area_ids.update(layout_logical_ids)

        assert {binding.objective_marker_id for binding in setup.objective_terrain_areas} == {
            objective.objective_id
            for objective in source_layout.objectives
            if objective.terrain_area_ids
        }
        source_objectives_by_id = {
            objective.objective_id: objective for objective in source_layout.objectives
        }
        for binding in setup.objective_terrain_areas:
            objective = objectives_by_id[binding.objective_marker_id]
            source_objective = source_objectives_by_id[binding.objective_marker_id]
            expected_logical_ids = {
                areas_by_id[area_id].logical_terrain_area_id
                for area_id in source_objective.terrain_area_ids
            }
            assert binding.terrain_area_ids == tuple(
                sorted(
                    area.terrain_area_id
                    for logical_area_id in expected_logical_ids
                    for area in areas_by_logical_id[logical_area_id]
                )
            )
            assert binding.terrain_area_ids
            checked_objective_bindings += len(binding.terrain_area_ids)
            for area_id in source_objective.terrain_area_ids:
                area_polygon = tuple(
                    (point.x_inches, point.y_inches)
                    for point in areas_by_id[area_id].footprint_polygon
                )
                assert (
                    shapely_backend.point_distance_to_polygon(
                        objective.x_inches,
                        objective.y_inches,
                        area_polygon,
                    )
                    <= 0.05 + 1e-9
                )

        regions_by_suffix = {
            region.region_id.removeprefix(f"{source_layout.layout_id}-"): region
            for region in setup.battlefield_regions
        }
        attacker_zone = shape_footprint(regions_by_suffix["attacker-deployment-region"].shape)
        defender_zone = shape_footprint(regions_by_suffix["defender-deployment-region"].shape)
        no_mans_land = shape_footprint(regions_by_suffix["no-mans-land"].shape)
        attacker_territory = shape_footprint(regions_by_suffix["attacker-territory"].shape)
        defender_territory = shape_footprint(regions_by_suffix["defender-territory"].shape)

        assert attacker_zone.intersection(defender_zone).area <= 1e-6
        assert attacker_zone.intersection(no_mans_land).area <= 1e-6
        assert defender_zone.intersection(no_mans_land).area <= 1e-6
        assert (
            board.symmetric_difference(attacker_zone.union(defender_zone).union(no_mans_land)).area
            <= 1e-6
        )
        assert attacker_territory.intersection(defender_territory).area <= 1e-6
        assert board.symmetric_difference(attacker_territory.union(defender_territory)).area <= 1e-6
        assert attacker_territory.covers(attacker_zone)
        assert defender_territory.covers(defender_zone)

    assert checked_area_contacts == 224
    assert area_contact_kinds == Counter({"single": 112, "separate": 112})
    assert checked_component_contacts == 269
    assert checked_component_containment == 1_349
    assert checked_objective_bindings == 264
    assert len(logical_terrain_area_ids) == 608


def test_phase17n_runtime_layout_names_preserve_canonical_source_metadata() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact_layouts = {
        layout.layout_id: layout for layout in event_layouts.battlefield_artifact().layouts
    }
    runtime_layouts = event_layouts.BATTLEFIELD_LAYOUTS_BY_ID
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    expected_names_by_id: dict[str, str] = {}

    for source_layout in extraction["layouts"]:
        layout_id = source_layout["layout_id"]
        variant = source_layout["variant"].upper()
        force_names = tuple(source_layout["force_disposition_pair"])
        mission_names = tuple(source_layout["primary_missions"])
        printed_metadata = source_layout["source_printed_left_to_right"]
        printed_force_names = tuple(printed_metadata["force_dispositions"])
        printed_mission_names = tuple(printed_metadata["primary_missions"])
        printed_label = printed_metadata["layout_label"]

        assert printed_force_names == force_names
        assert printed_mission_names == mission_names
        assert printed_label == f"Layout {variant}"
        assert source_layout["printed_title"] == (
            f"{printed_force_names[0]} vs {printed_force_names[1]} | "
            f"{printed_mission_names[0]} / {printed_mission_names[1]} | "
            f"{printed_label}"
        )

        expected_name = (
            f"{force_names[0]} vs {force_names[1]} - "
            f"{mission_names[0]} / {mission_names[1]} - "
            f"Layout {variant}"
        )
        expected_names_by_id[layout_id] = expected_name
        assert artifact_layouts[layout_id].name == expected_name
        assert runtime_layouts[layout_id].name == expected_name
        assert mission_pack.battlefield_layout(layout_id).name == expected_name

    assert expected_names_by_id["purge-the-foe-vs-priority-assets-layout-1"] == (
        "Purge the Foe vs Priority Assets - Destroyer's Wrath / Vital Link - Layout A"
    )
    assert expected_names_by_id["disruption-vs-disruption-layout-1"] == (
        "Disruption vs Disruption - Outmanoeuvre / Outmanoeuvre - Layout A"
    )


def test_phase17n_territory_dividers_match_all_45_source_layout_pages() -> None:
    expected_polygons_by_template = {
        1: {
            "attacker_territory": (((0.0, 26.0), (44.0, 34.0), (44.0, 60.0), (0.0, 60.0)),),
            "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 34.0), (0.0, 26.0)),),
        },
        2: {
            "attacker_territory": (((0.0, 0.0), (22.0, 0.0), (22.0, 60.0), (0.0, 60.0)),),
            "defender_territory": (((22.0, 0.0), (44.0, 0.0), (44.0, 60.0), (22.0, 60.0)),),
        },
        3: {
            "attacker_territory": (((0.0, 0.0), (44.0, 60.0), (0.0, 60.0)),),
            "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 60.0)),),
        },
        4: {
            "attacker_territory": (((0.0, 0.0), (19.0, 0.0), (25.0, 60.0), (0.0, 60.0)),),
            "defender_territory": (((19.0, 0.0), (44.0, 0.0), (44.0, 60.0), (25.0, 60.0)),),
        },
        5: {
            "attacker_territory": (((0.0, 30.0), (44.0, 30.0), (44.0, 60.0), (0.0, 60.0)),),
            "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 30.0), (0.0, 30.0)),),
        },
        6: {
            "attacker_territory": (((0.0, 15.0), (44.0, 45.0), (44.0, 60.0), (0.0, 60.0)),),
            "defender_territory": (((0.0, 0.0), (44.0, 0.0), (44.0, 45.0), (0.0, 15.0)),),
        },
    }
    layouts = event_layouts.battlefield_artifact().layouts

    assert len(layouts) == 45
    assert Counter(layout.deployment_zone_template_number for layout in layouts) == Counter(
        {1: 10, 2: 6, 3: 8, 4: 9, 5: 5, 6: 7}
    )
    for layout in layouts:
        actual_polygons_by_role = {
            territory.role: tuple(
                tuple((point.x_inches, point.y_inches) for point in polygon)
                for polygon in territory.polygons
            )
            for territory in layout.territories
        }

        assert (
            actual_polygons_by_role
            == expected_polygons_by_template[layout.deployment_zone_template_number]
        )
        assert all(
            territory.source_kind == "source_page_territory_boundary"
            for territory in layout.territories
        )


def test_phase17n_full_artifact_preserves_all_source_extraction_records() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction_path = (
        repository_root
        / "data/source_audits/event_companion_2026_06"
        / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
    )
    extraction_raw = extraction_path.read_bytes()
    extraction = json.loads(extraction_raw)
    stable_identity_map = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_event_companion_stable_runtime_identity_map.json"
        ).read_text(encoding="utf-8")
    )
    terrain_area_id_map = stable_identity_map["terrain_area_id_map"]
    objective_id_map = stable_identity_map["objective_id_map"]
    source_layout_id_map = stable_identity_map["source_layout_id_map"]
    artifact = event_layouts.battlefield_artifact()
    artifact_layouts = {layout.layout_id: layout for layout in artifact.layouts}

    assert hashlib.sha256(extraction_raw).hexdigest() == (artifact.source_extraction_payload_sha256)
    assert (
        json.loads(msgspec.json.encode(artifact.feature_archetypes))
        == extraction["reviewed_feature_archetypes"]
    )
    assert len(extraction["layouts"]) == 45
    checked_area_count = 0
    checked_component_count = 0
    checked_objective_count = 0
    reviewed_alternate_candidate_count = 0
    reviewed_area_pose_witnesses: dict[str, tuple[int, float, float]] = {}
    extended_area_adjustments: dict[str, tuple[float, float]] = {}
    exact_seam_adjustments: dict[str, tuple[float, float]] = {}
    component_containment_adjustments: dict[str, tuple[float, float]] = {}
    parent_centered_pipe_count = 0
    expected_component_containment_adjustments = {
        "purge-the-foe-vs-disruption-layout-3-terrain-area-04-component-01": (-0.1, 0.0),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-07-component-01": (0.0, 0.05),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-13-component-01": (0.05, -0.05),
        "disruption-vs-disruption-layout-3-terrain-area-02-component-01": (0.0, -0.05),
        "reconnaissance-vs-reconnaissance-layout-1-terrain-area-02-component-01": (0.0, -0.05),
        "take-and-hold-vs-priority-assets-layout-3-terrain-area-08-component-03": (
            0.0,
            -0.05,
        ),
        "take-and-hold-vs-priority-assets-layout-3-terrain-area-09-component-02": (
            0.0,
            0.05,
        ),
    }
    expected_reviewed_area_pose_witnesses = {
        "disruption-vs-disruption-layout-1-terrain-area-07": (2, 0.15, -0.1),
        "disruption-vs-disruption-layout-1-terrain-area-10": (
            2,
            -0.194559638906,
            0.110510105572,
        ),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-02": (1, 0.1, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-04": (2, -0.1, 0.3),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-13": (2, 0.05, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-15": (1, -0.05, 0.3),
        "purge-the-foe-vs-reconnaissance-layout-1-terrain-area-13": (0, 0.0, 0.05),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07": (2, 0.15, -0.1),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (
            2,
            -0.194559638906,
            0.110510105572,
        ),
        "disruption-vs-disruption-layout-2-terrain-area-06": (2, 0.0, 0.1),
        "disruption-vs-disruption-layout-2-terrain-area-11": (2, -0.2, 0.05),
        "reconnaissance-vs-reconnaissance-layout-3-terrain-area-06": (2, 0.0, 0.1),
        "reconnaissance-vs-reconnaissance-layout-3-terrain-area-11": (2, -0.2, 0.05),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-02": (1, 0.2, -0.05),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-04": (2, -0.2, 0.0),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-13": (2, 0.2, -0.05),
        "take-and-hold-vs-purge-the-foe-layout-1-terrain-area-15": (1, -0.2, 0.05),
        "take-and-hold-vs-take-and-hold-layout-3-terrain-area-08": (2, 0.1, 0.0),
        "take-and-hold-vs-take-and-hold-layout-3-terrain-area-09": (2, -0.15, 0.0),
        "take-and-hold-vs-take-and-hold-layout-3-terrain-area-11": (1, 0.0, -0.05),
    }

    for source_layout in extraction["layouts"]:
        layout = artifact_layouts[source_layout["layout_id"]]
        areas_by_source_id = {area.source_area_id: area for area in layout.terrain_areas}
        components_by_source_id = {
            component.source_component_id: component for component in layout.terrain_components
        }
        objectives_by_source_id = {
            objective.source_objective_id: objective for objective in layout.objectives
        }
        assert layout.source_page == source_layout["source_pdf_page_number"]
        if source_layout["layout_id"] in source_layout_id_map:
            assert layout.source_layout_id == source_layout_id_map[source_layout["layout_id"]]
        elif source_layout["layout_id"].startswith("purge-the-foe-vs-purge-the-foe"):
            assert layout.source_layout_id == (
                "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_"
                f"layout_{'abc'[int(source_layout['layout_id'][-1]) - 1]}"
            )
        else:
            assert layout.source_layout_id == (
                f"gw_event_companion_v1_{source_layout['layout_id'].replace('-', '_')}"
            )
        icons_by_id = {icon["icon_id"]: icon for icon in source_layout["eye_contact_icons"]}
        assert len(layout.terrain_area_contacts) == len(source_layout["source_contact_pairs"])
        for contact, source_pair in zip(
            layout.terrain_area_contacts,
            source_layout["source_contact_pairs"],
            strict=True,
        ):
            assert contact.source_terrain_area_ids == tuple(source_pair["area_ids"])
            assert contact.terrain_area_ids == tuple(
                terrain_area_id_map.get(area_id, area_id) for area_id in source_pair["area_ids"]
            )
            assert contact.kind == source_pair["kinds"][0]
            assert contact.source_icon_ids == tuple(source_pair["icon_ids"])
            assert contact.source_pair_gap_inches == source_pair["source_pair_gap_inches"]
            source_icon = icons_by_id[contact.source_icon_ids[0]]
            assert contact.source_pdf_drawing_indices_zero_based == tuple(
                source_icon["source_drawing_indices_zero_based"]
            )
            assert contact.source_pdf_seqnos == tuple(source_icon["source_seqnos"])
            assert (
                contact.source_icon_x_inches,
                contact.source_icon_y_inches,
            ) == tuple(source_icon["battlefield_center_quantized_0_05_inches"])

        for source_area in source_layout["terrain_areas"]:
            area = areas_by_source_id[source_area["area_id"]]
            vector_path = source_area["source_vector_path"]
            source_image = source_area["source_area_image"]
            source_pose = source_area["pose_recipe"]
            assert area.area_id == terrain_area_id_map.get(
                source_area["area_id"], source_area["area_id"]
            )
            assert area.source_area_id == source_area["area_id"]
            assert area.footprint_template_id == source_area["footprint_template_id"]
            assert area.classification == source_area["classification"]
            assert (
                area.local_transform == source_area["runtime_orientation_review"]["local_transform"]
            )
            assert (
                area.local_transform_basis
                == source_area["runtime_orientation_review"]["local_transform_basis"]
            )
            assert area.source_mirror_area_id == source_area["point_symmetry_partner_area_id"]
            assert area.mirror_area_id == terrain_area_id_map.get(
                source_area["point_symmetry_partner_area_id"],
                source_area["point_symmetry_partner_area_id"],
            )
            source_candidate = next(
                candidate
                for candidate in source_pose["candidates"]
                if candidate["candidate_index"] == area.source_pose_candidate_index
            )
            assert (
                area.source_anchor_x_inches,
                area.source_anchor_y_inches,
                area.source_rotation_degrees,
                area.source_pose_fit_residual_inches,
            ) == (
                source_candidate["anchor_x_inches"],
                source_candidate["anchor_y_inches"],
                source_candidate["rotation_degrees"],
                source_candidate["fit_residual_inches"],
            )
            if area.source_pose_candidate_index != source_pose["selected_candidate_index"]:
                reviewed_alternate_candidate_count += 1
                assert area.pose_basis in {
                    "reviewed_source_pose_candidate_with_bounded_seam_adjustment",
                    "reviewed_source_pose_with_exact_seam_closure",
                }
            assert math.isclose(
                area.anchor_x_inches,
                area.source_anchor_x_inches + area.runtime_adjustment_x_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                area.anchor_y_inches,
                area.source_anchor_y_inches + area.runtime_adjustment_y_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                (area.rotation_degrees - area.source_rotation_degrees + 180.0) % 360.0 - 180.0,
                area.runtime_rotation_adjustment_degrees,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            if (
                abs(area.runtime_adjustment_x_inches) > 0.2
                or abs(area.runtime_adjustment_y_inches) > 0.2
            ):
                extended_area_adjustments[area.source_area_id] = (
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            if area.pose_basis == "reviewed_source_pose_with_exact_seam_closure":
                exact_seam_adjustments[area.source_area_id] = (
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            if area.source_area_id in expected_reviewed_area_pose_witnesses:
                reviewed_area_pose_witnesses[area.source_area_id] = (
                    area.source_pose_candidate_index,
                    area.runtime_adjustment_x_inches,
                    area.runtime_adjustment_y_inches,
                )
            assert (
                area.source_pdf_extended_drawing_index_zero_based
                == (vector_path["extended_drawing_index_zero_based"])
            )
            assert area.source_pdf_seqno == vector_path["seqno"]
            assert area.source_pdf_vector_item_count == vector_path["item_count"]
            assert area.source_pdf_image_xref == source_image["xref"]
            assert area.source_image_sha256 == source_image["source_image_sha256"]
            assert area.source_soft_mask_sha256 == source_image["source_soft_mask_sha256"]
            assert (
                area.source_pdf_bounds.x0_points,
                area.source_pdf_bounds.y0_points,
                area.source_pdf_bounds.x1_points,
                area.source_pdf_bounds.y1_points,
            ) == tuple(source_image["bbox_points"])
            assert (
                area.source_pdf_affine.a,
                area.source_pdf_affine.b,
                area.source_pdf_affine.c,
                area.source_pdf_affine.d,
                area.source_pdf_affine.e,
                area.source_pdf_affine.f,
            ) == tuple(source_image["affine_normalized_image_to_points"])
            checked_area_count += 1

        for source_component in source_layout["terrain_components"]:
            component = components_by_source_id[source_component["component_id"]]
            assert not source_component["inferred"]
            expected_parent_id = terrain_area_id_map.get(
                source_component["parent_area_id"], source_component["parent_area_id"]
            )
            component_ordinal = source_component["component_id"].rsplit("-component-", 1)[1]
            assert component.component_id == f"{expected_parent_id}-component-{component_ordinal}"
            assert component.source_component_id == source_component["component_id"]
            assert component.terrain_area_id == expected_parent_id
            assert component.archetype_id == source_component["archetype_id"]
            assert (
                component.source_mirror_component_id
                == source_component["point_symmetry_partner_component_id"]
            )
            expected_mirror_source_id = source_component["point_symmetry_partner_component_id"]
            if expected_mirror_source_id is None:
                assert component.mirror_component_id is None
            else:
                expected_mirror_parent = terrain_area_id_map.get(
                    expected_mirror_source_id.rsplit("-component-", 1)[0],
                    expected_mirror_source_id.rsplit("-component-", 1)[0],
                )
                expected_mirror_ordinal = expected_mirror_source_id.rsplit("-component-", 1)[1]
                assert component.mirror_component_id == (
                    f"{expected_mirror_parent}-component-{expected_mirror_ordinal}"
                )
            assert (
                component.local_transform
                == source_component["local_orientation_relative_to_parent"]["local_transform"]
            )
            assert (
                component.local_transform_basis
                == source_component["local_orientation_relative_to_parent"]["local_transform_basis"]
            )
            assert component.source_pdf_image_xref == source_component["source_xref"]
            assert (
                component.source_battlefield_center_x_inches,
                component.source_battlefield_center_y_inches,
            ) == tuple(source_component["battlefield_center_quantized_0_05_inches"])
            assert (
                component.source_battlefield_rotation_degrees
                == source_component["battlefield_image_x_axis_rotation_degrees"]
            )
            assert math.isclose(
                component.battlefield_center_x_inches,
                component.source_battlefield_center_x_inches
                + component.runtime_adjustment_x_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                component.battlefield_center_y_inches,
                component.source_battlefield_center_y_inches
                + component.runtime_adjustment_y_inches,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                (
                    component.battlefield_rotation_degrees
                    - component.source_battlefield_rotation_degrees
                    + 180.0
                )
                % 360.0
                - 180.0,
                component.runtime_rotation_adjustment_degrees,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            if layout.source_page not in {24, 25, 26}:
                if component.archetype_id == "dense-long-pipes":
                    assert component.pose_basis == "reviewed_parent_footprint_centered_pipe_pose"
                    assert math.isclose(
                        component.runtime_rotation_adjustment_degrees,
                        (
                            component.battlefield_rotation_degrees
                            - component.source_battlefield_rotation_degrees
                            + 180.0
                        )
                        % 360.0
                        - 180.0,
                        rel_tol=0.0,
                        abs_tol=1e-9,
                    )
                    parent_centered_pipe_count += 1
                elif component.source_component_id in expected_component_containment_adjustments:
                    assert (
                        component.pose_basis
                        == "reviewed_source_quantization_containment_adjustment"
                    )
                    component_containment_adjustments[component.source_component_id] = (
                        component.runtime_adjustment_x_inches,
                        component.runtime_adjustment_y_inches,
                    )
                    assert component.runtime_rotation_adjustment_degrees == 0.0
                else:
                    assert (
                        component.battlefield_center_x_inches,
                        component.battlefield_center_y_inches,
                        component.battlefield_rotation_degrees,
                    ) == (
                        component.source_battlefield_center_x_inches,
                        component.source_battlefield_center_y_inches,
                        component.source_battlefield_rotation_degrees,
                    )
                    assert (
                        component.runtime_adjustment_x_inches,
                        component.runtime_adjustment_y_inches,
                        component.runtime_rotation_adjustment_degrees,
                    ) == (0.0, 0.0, 0.0)
            assert (
                component.source_pdf_bounds.x0_points,
                component.source_pdf_bounds.y0_points,
                component.source_pdf_bounds.x1_points,
                component.source_pdf_bounds.y1_points,
            ) == tuple(source_component["source_bbox_points"])
            assert (
                component.source_pdf_affine.a,
                component.source_pdf_affine.b,
                component.source_pdf_affine.c,
                component.source_pdf_affine.d,
                component.source_pdf_affine.e,
                component.source_pdf_affine.f,
            ) == tuple(source_component["source_affine_normalized_image_to_points"])
            checked_component_count += 1

        for source_objective in source_layout["objectives"]:
            objective = objectives_by_source_id[source_objective["objective_id"]]
            assert objective.objective_id == objective_id_map.get(
                source_objective["objective_id"], source_objective["objective_id"]
            )
            assert objective.source_objective_id == source_objective["objective_id"]
            assert objective.role == source_objective["role"]
            assert (objective.x_inches, objective.y_inches) == tuple(
                source_objective["battlefield_center_quantized_0_01_inches"]
            )
            source_distances = source_objective["distances_to_area_polygons_inches"]
            source_nearby_area_ids = (
                set(source_objective["nearest_area_ids"])
                if not source_distances
                else {
                    area_id
                    for area_id, distance in zip(
                        source_objective["nearest_area_ids"],
                        source_distances,
                        strict=True,
                    )
                    if distance <= 0.05
                }
            )
            assert set(objective.terrain_area_ids) == {
                terrain_area_id_map.get(area_id, area_id) for area_id in source_nearby_area_ids
            }
            checked_objective_count += 1

    assert checked_area_count == 720
    assert checked_component_count == 1_349
    assert checked_objective_count == 246
    assert reviewed_alternate_candidate_count > 0
    assert reviewed_area_pose_witnesses == expected_reviewed_area_pose_witnesses
    assert parent_centered_pipe_count == 84
    assert component_containment_adjustments == expected_component_containment_adjustments
    assert exact_seam_adjustments == {
        "disruption-vs-disruption-layout-1-terrain-area-07": (0.15, -0.1),
        "disruption-vs-disruption-layout-1-terrain-area-10": (
            -0.194559638906,
            0.110510105572,
        ),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-07": (0.15, -0.1),
        "reconnaissance-vs-reconnaissance-layout-2-terrain-area-10": (
            -0.194559638906,
            0.110510105572,
        ),
    }
    assert extended_area_adjustments == {
        "purge-the-foe-vs-disruption-layout-3-terrain-area-02": (0.1, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-04": (-0.1, 0.3),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-13": (0.05, -0.35),
        "purge-the-foe-vs-disruption-layout-3-terrain-area-15": (-0.05, 0.3),
    }


def test_phase17n_ruin_wall_joints_follow_source_image_registration() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact = event_layouts.battlefield_artifact()
    archetypes_by_xref = {
        archetype.source_assets[0].source_pdf_image_xref: archetype
        for archetype in artifact.feature_archetypes
        if archetype.model_kind == "ruin"
    }
    placements_by_id = {
        component.component_id: component
        for layout in _meatgrinder_artifact_layouts()
        for component in layout.terrain_components
    }

    assert set(archetypes_by_xref) == {5470, 5472, 5474, 5476}
    for archetype in archetypes_by_xref.values():
        minimum_x = min(point.x_inches for point in archetype.rules_footprint_polygon)
        minimum_y = min(point.y_inches for point in archetype.rules_footprint_polygon)
        ground_walls = {
            wall.wall_id: wall for wall in archetype.walls if wall.bottom_z_inches == 0.0
        }
        assert math.isclose(
            ground_walls["ground-long-solid-wall"].center_y_inches,
            minimum_y + 0.07,
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        assert math.isclose(
            ground_walls["ground-short-solid-wall"].center_x_inches,
            minimum_x + 0.07,
            rel_tol=0.0,
            abs_tol=1e-9,
        )

    checked_component_ids: set[str] = set()
    for source_layout in extraction_payload["layouts"]:
        for source_component in source_layout["terrain_components"]:
            area_index = int(source_component["terrain_area_id"].rsplit("-", maxsplit=1)[-1])
            if area_index > 8:
                continue
            source_image = source_component["source_image"]
            source_xref = source_image["xref"]
            source_archetype = archetypes_by_xref.get(source_xref)
            if source_archetype is None:
                continue
            placement = placements_by_id[source_component["component_id"]]
            assert placement.local_transform == "identity"
            minimum_x = min(point.x_inches for point in source_archetype.rules_footprint_polygon)
            minimum_y = min(point.y_inches for point in source_archetype.rules_footprint_polygon)
            radians = math.radians(placement.battlefield_rotation_degrees)
            modeled_joint_x = (
                placement.battlefield_center_x_inches
                + (minimum_x * math.cos(radians))
                - (minimum_y * math.sin(radians))
            )
            modeled_joint_y = (
                placement.battlefield_center_y_inches
                + (minimum_x * math.sin(radians))
                + (minimum_y * math.cos(radians))
            )
            source_joint_x, source_joint_y = source_image[
                "battlefield_quad_inches_top_left_top_right_bottom_right_bottom_left"
            ][3]
            assert (
                math.dist(
                    (modeled_joint_x, modeled_joint_y),
                    (source_joint_x, source_joint_y),
                )
                <= 0.4
            )
            checked_component_ids.add(source_component["component_id"])

    assert len(checked_component_ids) == 12


def test_phase17n_ruin_floors_preserve_source_visible_wall_only_tails() -> None:
    artifact = event_layouts.battlefield_artifact()
    expected_geometry = {
        "ruins-cd": (3.5, 2.96, 2.48, 0.02),
        "ruins-gh": (2.96, 3.5, 0.02, 2.48),
        "ruins-ef": (3.5, 3.5, 2.48, 0.98),
        "ruins-ab": (3.5, 3.5, 0.48, 0.98),
    }

    for archetype in artifact.feature_archetypes:
        if archetype.archetype_id not in expected_geometry:
            continue
        minimum_x = min(point.x_inches for point in archetype.rules_footprint_polygon)
        maximum_x = max(point.x_inches for point in archetype.rules_footprint_polygon)
        minimum_y = min(point.y_inches for point in archetype.rules_footprint_polygon)
        maximum_y = max(point.y_inches for point in archetype.rules_footprint_polygon)
        expected_width, expected_depth, expected_x_tail, expected_y_tail = expected_geometry[
            archetype.archetype_id
        ]
        for floor in archetype.floors:
            assert (floor.width_inches, floor.depth_inches) == (
                expected_width,
                expected_depth,
            )
            assert math.isclose(
                floor.center_x_inches - (floor.width_inches / 2.0),
                minimum_x + 0.02,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                floor.center_y_inches - (floor.depth_inches / 2.0),
                minimum_y + 0.02,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                maximum_x - (floor.center_x_inches + (floor.width_inches / 2.0)),
                expected_x_tail,
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                maximum_y - (floor.center_y_inches + (floor.depth_inches / 2.0)),
                expected_y_tail,
                rel_tol=0.0,
                abs_tol=1e-9,
            )


def test_phase17n_shared_non_ruin_archetypes_expand_to_legal_source_proportions_and_touch() -> None:
    artifact = event_layouts.battlefield_artifact()
    meatgrinder_layouts = _meatgrinder_artifact_layouts()
    expected_axis_spans = {
        "dense-downed-hovercraft": (4.25, 1.4),
        "light-long-barricade": (4.8, 1.0),
        "dense-industrial-crates": (3.45, 1.95),
        "light-end-barricade": (3.5, 1.25),
        "light-corner-ab": (1.65, 1.7),
        "light-corner-cd": (2.2, 1.3),
        "light-corner-ef": (1.85, 2.95),
        "light-corner-gh": (2.9, 1.15),
        "dense-tall-crates": (1.5, 2.7),
        "dense-long-pipes": (6.0, 1.7),
    }
    expected_usage_counts = {
        "dense-downed-hovercraft": 6,
        "light-long-barricade": 6,
        "dense-industrial-crates": 6,
        "light-end-barricade": 12,
        "ruins-cd": 6,
        "ruins-gh": 6,
        "ruins-ef": 6,
        "ruins-ab": 6,
        "light-corner-ab": 6,
        "light-corner-cd": 6,
        "light-corner-ef": 6,
        "light-corner-gh": 6,
        "dense-tall-crates": 6,
        "dense-long-pipes": 6,
    }
    archetypes_by_id = {
        archetype.archetype_id: archetype for archetype in artifact.feature_archetypes
    }

    assert Counter(
        component.archetype_id
        for layout in meatgrinder_layouts
        for component in layout.terrain_components
    ) == Counter(expected_usage_counts)
    assert sum(len(layout.terrain_component_contact_pairs) for layout in meatgrinder_layouts) == 18
    for archetype_id, expected_span in expected_axis_spans.items():
        polygon = archetypes_by_id[archetype_id].rules_footprint_polygon
        assert (
            max(point.x_inches for point in polygon) - min(point.x_inches for point in polygon),
            max(point.y_inches for point in polygon) - min(point.y_inches for point in polygon),
        ) == expected_span

    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    reviewed_multi_piece_xrefs = {5462, 5466, 5468, 5486, 5675}
    primary_xrefs = {5462, 5466}
    checked_companion_count = 0
    for layout in meatgrinder_layouts:
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=f"mission-{layout.layout_id}",
            attacker_player_id="player-alpha",
            attacker_force_disposition_id=layout.force_disposition_pair[0],
            defender_player_id="player-beta",
            defender_force_disposition_id=layout.force_disposition_pair[1],
        )
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        components_by_area = {
            component.terrain_area_id: tuple(
                candidate
                for candidate in layout.terrain_components
                if candidate.terrain_area_id == component.terrain_area_id
                and candidate.source_pdf_image_xref in reviewed_multi_piece_xrefs
            )
            for component in layout.terrain_components
            if component.source_pdf_image_xref in primary_xrefs
        }
        for components in components_by_area.values():
            primary = next(
                component
                for component in components
                if component.source_pdf_image_xref in primary_xrefs
            )
            primary_feature = features_by_id[primary.component_id]
            primary_footprint = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in primary_feature.rules_footprint_polygon
                )
            )
            for companion in components:
                if companion is primary:
                    continue
                companion_feature = features_by_id[companion.component_id]
                companion_footprint = shapely_backend.footprint_for_polygon(
                    tuple(
                        (point.x_inches, point.y_inches)
                        for point in companion_feature.rules_footprint_polygon
                    )
                )
                assert primary_footprint.distance(companion_footprint) <= 1e-9
                checked_companion_count += 1

    assert checked_companion_count == 18


def test_phase17n_light_corner_wall_joints_follow_source_image_registration() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact = event_layouts.battlefield_artifact()
    archetypes_by_xref = {
        archetype.source_assets[0].source_pdf_image_xref: archetype
        for archetype in artifact.feature_archetypes
        if archetype.archetype_id.startswith("light-corner-")
    }

    assert set(archetypes_by_xref) == {5478, 5480, 5482, 5484}
    for archetype in archetypes_by_xref.values():
        minimum_x = min(point.x_inches for point in archetype.rules_footprint_polygon)
        maximum_x = max(point.x_inches for point in archetype.rules_footprint_polygon)
        minimum_y = min(point.y_inches for point in archetype.rules_footprint_polygon)
        maximum_y = max(point.y_inches for point in archetype.rules_footprint_polygon)
        arm_thickness = min(maximum_x - minimum_x, maximum_y - minimum_y) * 0.35
        walls = {wall.wall_id: wall for wall in archetype.walls}
        assert math.isclose(
            walls["long-solid-arm"].center_y_inches,
            minimum_y + (arm_thickness / 2.0),
            rel_tol=0.0,
            abs_tol=1e-9,
        )
        assert math.isclose(
            walls["short-solid-arm"].center_x_inches,
            minimum_x + (arm_thickness / 2.0),
            rel_tol=0.0,
            abs_tol=1e-9,
        )

    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    checked_component_ids: set[str] = set()
    for source_layout in extraction_payload["layouts"]:
        layout_id = source_layout["layout_id"]
        mission_pool_entry = next(
            entry
            for entry in mission_pack.mission_pool_entries
            if layout_id in entry.terrain_layout_ids
        )
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=mission_pool_entry.mission_pool_entry_id,
            attacker_player_id="player-alpha",
            attacker_force_disposition_id=mission_pool_entry.player_force_disposition_id,
            defender_player_id="player-beta",
            defender_force_disposition_id=mission_pool_entry.opponent_force_disposition_id,
        )
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        for source_component in source_layout["terrain_components"]:
            area_index = int(source_component["terrain_area_id"].rsplit("-", maxsplit=1)[-1])
            if area_index > 8:
                continue
            source_image = source_component["source_image"]
            if source_image["xref"] not in archetypes_by_xref:
                continue
            modeled_joint = features_by_id[
                source_component["component_id"]
            ].rules_footprint_polygon[0]
            source_joint_x, source_joint_y = source_image[
                "battlefield_quad_inches_top_left_top_right_bottom_right_bottom_left"
            ][3]
            assert (
                math.dist(
                    (modeled_joint.x_inches, modeled_joint.y_inches),
                    (source_joint_x, source_joint_y),
                )
                <= 0.85
            )
            checked_component_ids.add(source_component["component_id"])

    assert len(checked_component_ids) == 12


def test_phase17n_battlefield_builder_reproduces_committed_artifact(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    builder_path = repository_root / "tools/build_event_companion_battlefields.py"
    extraction_path = (
        repository_root
        / "data/source_audits/event_companion_2026_06"
        / "phase17n_event_companion_battlefields_pages_9_53_extraction.json"
    )
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_layouts_2026_06/artifacts"
        / "event-companion-battlefields.json"
    )
    modified_at_before_check = artifact_path.stat().st_mtime_ns
    result = subprocess.run(
        [
            sys.executable,
            str(builder_path),
            "--check",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert artifact_path.stat().st_mtime_ns == modified_at_before_check

    stale_output = tmp_path / "stale-battlefields.json"
    stale_output.write_bytes(artifact_path.read_bytes() + b"\n")
    stale_bytes = stale_output.read_bytes()
    stale_result = subprocess.run(
        [
            sys.executable,
            str(builder_path),
            str(extraction_path),
            str(stale_output),
            "--check",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert stale_result.returncode != 0
    assert "battlefield artifact is stale" in stale_result.stderr
    assert stale_output.read_bytes() == stale_bytes

    modified_extraction = tmp_path / "modified-extraction.json"
    modified_extraction.write_bytes(extraction_path.read_bytes() + b"\n")
    guarded_output = tmp_path / "must-not-be-written.json"
    extraction_result = subprocess.run(
        [
            sys.executable,
            str(builder_path),
            str(modified_extraction),
            str(guarded_output),
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )
    assert extraction_result.returncode != 0
    assert "source extraction bytes drifted" in extraction_result.stderr
    assert not guarded_output.exists()


def test_phase17n_exact_terrain_area_reflections_follow_source_affine_orientation() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    source_orientation_reversing_ids = {
        area["terrain_area_id"]
        for layout in extraction_payload["layouts"]
        for area in layout["terrain_areas"]
        if (
            area["source_image"]["pdf_page_affine_normalized_image_to_points"][0]
            * area["source_image"]["pdf_page_affine_normalized_image_to_points"][3]
        )
        - (
            area["source_image"]["pdf_page_affine_normalized_image_to_points"][1]
            * area["source_image"]["pdf_page_affine_normalized_image_to_points"][2]
        )
        < 0.0
    }
    artifact_mirrored_ids = {
        area.area_id
        for layout in _meatgrinder_artifact_layouts()
        for area in layout.terrain_areas
        if area.local_transform == "mirror_y_axis"
    }

    assert len(source_orientation_reversing_ids) == 12
    assert artifact_mirrored_ids == source_orientation_reversing_ids
    assert Counter(
        area.pose_basis
        for layout in _meatgrinder_artifact_layouts()
        for area in layout.terrain_areas
    ) == Counter(
        {
            "accepted_meatgrinder_exemplar_source_pose": 24,
            "accepted_meatgrinder_exemplar_exact_point_symmetry": 24,
        }
    )

    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    layout_a_area_04 = next(
        area
        for area in setup.terrain_areas
        if area.terrain_area_id == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-04"
    )

    assert layout_a_area_04.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS
    assert tuple(
        (round(point.x_inches, 9), round(point.y_inches, 9))
        for point in layout_a_area_04.footprint_polygon
    ) == (
        (34.0, 41.1),
        (40.0, 41.1),
        (40.0, 42.4),
        (40.5, 43.1),
        (40.1, 43.8),
        (40.3, 44.1),
        (40.0, 44.3),
        (40.0, 45.1),
        (37.3, 45.1),
        (37.2, 45.3),
        (36.8, 45.2),
        (36.0, 45.6),
        (35.2, 45.1),
        (34.0, 45.1),
    )


def test_phase17n_terrain_placements_use_reviewed_grid_symmetry_and_contacts() -> None:
    artifact = event_layouts.battlefield_artifact()
    meatgrinder_layouts = _meatgrinder_artifact_layouts()
    increment = artifact.source_coordinate_frame.terrain_placement_increment_inches

    assert increment == 0.05
    for layout in meatgrinder_layouts:
        areas_by_id = {area.area_id: area for area in layout.terrain_areas}
        components_by_id = {
            component.component_id: component for component in layout.terrain_components
        }
        for area in layout.terrain_areas:
            assert math.isclose(
                area.anchor_x_inches / increment,
                round(area.anchor_x_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                area.anchor_y_inches / increment,
                round(area.anchor_y_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            area_index = int(area.area_id.rsplit("-", maxsplit=1)[-1])
            if area_index > 8:
                continue
            mirror_area = areas_by_id[area.mirror_area_id]
            assert area.anchor_x_inches + mirror_area.anchor_x_inches == 44.0
            assert area.anchor_y_inches + mirror_area.anchor_y_inches == 60.0
            assert (mirror_area.rotation_degrees - area.rotation_degrees) % 360.0 == 180.0
            assert mirror_area.local_transform == area.local_transform
        for component in layout.terrain_components:
            assert math.isclose(
                component.battlefield_center_x_inches / increment,
                round(component.battlefield_center_x_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            assert math.isclose(
                component.battlefield_center_y_inches / increment,
                round(component.battlefield_center_y_inches / increment),
                rel_tol=0.0,
                abs_tol=1e-9,
            )
            area_index_text, _component_ordinal = component.component_id.rsplit(
                "-terrain-area-",
                maxsplit=1,
            )[1].split("-component-", maxsplit=1)
            area_index = int(area_index_text)
            if area_index > 8:
                continue
            expected_mirror_center = (
                44.0 - component.battlefield_center_x_inches,
                60.0 - component.battlefield_center_y_inches,
            )
            mirror_components = tuple(
                candidate
                for candidate in components_by_id.values()
                if candidate.terrain_area_id.endswith(f"area-{17 - area_index:02d}")
                and candidate.archetype_id == component.archetype_id
                and math.isclose(
                    candidate.battlefield_center_x_inches,
                    expected_mirror_center[0],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
                and math.isclose(
                    candidate.battlefield_center_y_inches,
                    expected_mirror_center[1],
                    rel_tol=0.0,
                    abs_tol=1e-9,
                )
            )
            assert len(mirror_components) == 1
            mirror_component = mirror_components[0]
            assert math.isclose(
                (
                    mirror_component.battlefield_rotation_degrees
                    - component.battlefield_rotation_degrees
                )
                % 360.0,
                180.0,
                rel_tol=0.0,
                abs_tol=1e-9,
            )

    reviewed_anchors_by_layout = {
        1: {
            "04": (34.0, 41.1),
            "06": (16.85, 41.0),
            "07": (23.0, 42.5),
            "08": (4.85, 35.55),
        },
        2: {"02": (31.0, 50.0), "07": (17.55, 39.05)},
        3: {"02": (22.8, 50.05), "06": (9.5, 39.6)},
    }
    contact_pairs_by_layout = {
        1: (("04", "05"), ("06", "08"), ("09", "11"), ("12", "13")),
        2: (("01", "02"), ("05", "07"), ("10", "12"), ("15", "16")),
        3: (("02", "04"), ("06", "09"), ("08", "11"), ("13", "15")),
    }
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    for layout_number, reviewed_anchors in reviewed_anchors_by_layout.items():
        source_layout = meatgrinder_layouts[layout_number - 1]
        artifact_areas = {
            area.area_id.rsplit("-", maxsplit=1)[-1]: area for area in source_layout.terrain_areas
        }
        assert {
            area_suffix: (
                artifact_areas[area_suffix].anchor_x_inches,
                artifact_areas[area_suffix].anchor_y_inches,
            )
            for area_suffix in reviewed_anchors
        } == reviewed_anchors
        assert {
            frozenset(area_id.rsplit("-", maxsplit=1)[-1] for area_id in contact.terrain_area_ids)
            for contact in source_layout.terrain_area_contacts
        } == {frozenset(contact_pair) for contact_pair in contact_pairs_by_layout[layout_number]}

        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=(
                f"mission-purge-the-foe-vs-purge-the-foe-layout-{layout_number}"
            ),
            attacker_player_id="player-alpha",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-beta",
            defender_force_disposition_id="purge-the-foe",
        )
        runtime_areas = {
            area.terrain_area_id.rsplit("-", maxsplit=1)[-1]: area for area in setup.terrain_areas
        }
        for first_suffix, second_suffix in contact_pairs_by_layout[layout_number]:
            first = tuple(
                (point.x_inches, point.y_inches)
                for point in runtime_areas[first_suffix].footprint_polygon
            )
            second = tuple(
                (point.x_inches, point.y_inches)
                for point in runtime_areas[second_suffix].footprint_polygon
            )
            assert polygon_overlap_area(first, second) <= 1e-6
            assert (
                shapely_backend.footprint_for_polygon(first).distance(
                    shapely_backend.footprint_for_polygon(second)
                )
                <= increment
            )

        if layout_number == 1:
            light_pipe = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in runtime_areas["08"].footprint_polygon
                )
            )
            mirrored_light_pipe = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in runtime_areas["09"].footprint_polygon
                )
            )
            mixed = shapely_backend.footprint_for_polygon(
                tuple(
                    (point.x_inches, point.y_inches)
                    for point in runtime_areas["06"].footprint_polygon
                )
            )
            assert math.isclose(light_pipe.bounds[0], 4.0, rel_tol=0.0, abs_tol=0.05)
            assert math.isclose(
                44.0 - mirrored_light_pipe.bounds[2],
                4.0,
                rel_tol=0.0,
                abs_tol=0.05,
            )
            assert light_pipe.distance(mixed) <= 0.01
            assert light_pipe.intersection(mixed).is_empty


def test_phase17n_component_source_instances_bind_to_nearest_generated_placement() -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction_payload = json.loads(
        (
            repository_root
            / "data/source_audits/event_companion_2026_06"
            / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
        ).read_text(encoding="utf-8")
    )
    artifact_layouts = {layout.layout_id: layout for layout in _meatgrinder_artifact_layouts()}
    duplicate_source_group_count = 0
    source_instance_count = 0

    for source_layout in extraction_payload["layouts"]:
        artifact_components_by_id = {
            component.component_id: component
            for component in artifact_layouts[source_layout["layout_id"]].terrain_components
        }
        source_groups: dict[tuple[str, int], list[dict[str, Any]]] = {}
        for source_component in source_layout["terrain_components"]:
            source_instance_count += 1
            source_image = source_component["source_image"]
            artifact_component = artifact_components_by_id[source_component["component_id"]]
            source_bounds = source_image["pdf_page_bbox_points"]
            source_affine = source_image["pdf_page_affine_normalized_image_to_points"]
            assert artifact_component.source_pdf_image_xref == source_image["xref"]
            assert (
                artifact_component.source_pdf_bounds.x0_points,
                artifact_component.source_pdf_bounds.y0_points,
                artifact_component.source_pdf_bounds.x1_points,
                artifact_component.source_pdf_bounds.y1_points,
            ) == tuple(source_bounds)
            assert (
                artifact_component.source_pdf_affine.a,
                artifact_component.source_pdf_affine.b,
                artifact_component.source_pdf_affine.c,
                artifact_component.source_pdf_affine.d,
                artifact_component.source_pdf_affine.e,
                artifact_component.source_pdf_affine.f,
            ) == tuple(source_affine)
            source_groups.setdefault(
                (
                    source_component["terrain_area_id"],
                    source_component["source_image"]["xref"],
                ),
                [],
            ).append(source_component)

        for source_components in source_groups.values():
            if len(source_components) == 1:
                continue
            duplicate_source_group_count += 1
            ordered_source_components = sorted(
                source_components,
                key=lambda component: component["component_id"],
            )
            artifact_candidates = tuple(
                artifact_components_by_id[source_component["component_id"]]
                for source_component in ordered_source_components
            )
            scored_assignments: list[tuple[float, tuple[str, ...]]] = []
            for assignment in permutations(artifact_candidates):
                score = sum(
                    math.dist(
                        tuple(source_component["source_image"]["battlefield_image_center_inches"]),
                        (
                            artifact_component.battlefield_center_x_inches,
                            artifact_component.battlefield_center_y_inches,
                        ),
                    )
                    ** 2
                    for source_component, artifact_component in zip(
                        ordered_source_components,
                        assignment,
                        strict=True,
                    )
                )
                scored_assignments.append(
                    (score, tuple(component.component_id for component in assignment))
                )
            scored_assignments.sort()
            assert scored_assignments[0][1] == tuple(
                component["component_id"] for component in ordered_source_components
            )
            assert not math.isclose(
                scored_assignments[0][0],
                scored_assignments[1][0],
                rel_tol=0.0,
                abs_tol=1e-9,
            )

    assert duplicate_source_group_count == 6
    assert source_instance_count == 90


def test_phase17n_meatgrinder_exact_layouts_build_all_source_components() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    artifact = event_layouts.battlefield_artifact()
    artifact_layouts = {layout.layout_id: layout for layout in _meatgrinder_artifact_layouts()}
    archetypes_by_id = {
        archetype.archetype_id: archetype for archetype in artifact.feature_archetypes
    }
    terrain_area_templates = {
        template.footprint_template_id: template
        for template in mission_pack.terrain_area_footprint_templates
    }
    expected_objective_coordinates = {
        1: (
            (8.58, 50.32),
            (36.08, 9.01),
            (26.51, 37.47),
            (17.82, 22.31),
            (32.15, 52.67),
            (12.36, 8.33),
        ),
        2: (
            (9.90, 47.73),
            (33.63, 12.05),
            (11.39, 29.61),
            (32.92, 30.55),
            (37.23, 42.98),
            (6.86, 17.11),
        ),
        3: (
            (9.08, 51.19),
            (34.81, 9.01),
            (22.33, 35.93),
            (21.23, 23.67),
            (29.28, 51.31),
            (15.25, 8.98),
        ),
    }

    for layout_number in (1, 2, 3):
        layout_id = f"purge-the-foe-vs-purge-the-foe-layout-{layout_number}"
        setup = MissionSetup.from_mission_pack(
            mission_pack=mission_pack,
            mission_pool_entry_id=f"mission-{layout_id}",
            attacker_player_id="player-alpha",
            attacker_force_disposition_id="purge-the-foe",
            defender_player_id="player-beta",
            defender_force_disposition_id="purge-the-foe",
        )
        source_layout = artifact_layouts[layout_id]
        battlefield_layout = mission_pack.battlefield_layout(layout_id)
        areas_by_id = {area.terrain_area_id: area for area in setup.terrain_areas}
        placements_by_id = {
            placement.feature_id: placement
            for placement in battlefield_layout.terrain_feature_placements
        }
        features_by_id = {feature.feature_id: feature for feature in setup.terrain_features}
        objective_markers_by_id = {
            marker.objective_marker_id: marker for marker in setup.objective_markers
        }
        ruins = tuple(
            feature for feature in setup.terrain_features if feature.feature_kind.value == "ruins"
        )
        light = tuple(
            feature
            for feature in setup.terrain_features
            if feature.classification is TerrainAreaClassification.LIGHT
        )
        dense = tuple(
            feature
            for feature in setup.terrain_features
            if feature.classification is TerrainAreaClassification.DENSE
        )

        assert len(setup.terrain_areas) == 16
        assert {area.terrain_feature_kind for area in setup.terrain_areas} == {
            "terrain_layout_area"
        }
        assert Counter(area.classification.value for area in setup.terrain_areas) == Counter(
            {"dense": 6, "mixed": 6, "light": 4}
        )
        assert len(setup.terrain_features) == 30
        assert (len(ruins), len(dense), len(light)) == (8, 16, 14)
        assert Counter(len(ruin.floors) for ruin in ruins) == Counter({2: 4, 3: 4})
        assert all(
            tuple(sorted(floor.bottom_z_inches for floor in ruin.floors))
            in {(0.0, 3.0), (0.0, 3.0, 6.0)}
            for ruin in ruins
        )
        for ruin in ruins:
            floor_levels = tuple(sorted(floor.bottom_z_inches for floor in ruin.floors))
            top_floor_level = floor_levels[-1]
            assert all(
                wall.height_inches == (2.0 if wall.bottom_z_inches == top_floor_level else 3.0)
                for wall in ruin.walls
            )
            assert all(
                any(
                    wall.bottom_z_inches == floor_level
                    and wall.bottom_z_inches + wall.height_inches == next_floor_level
                    for wall in ruin.walls
                )
                for floor_level, next_floor_level in pairwise(floor_levels)
            )
        assert {(marker.x_inches, marker.y_inches) for marker in setup.objective_markers} == set(
            expected_objective_coordinates[layout_number]
        )
        for objective_terrain_area in setup.objective_terrain_areas:
            objective = objective_markers_by_id[objective_terrain_area.objective_marker_id]
            for terrain_area_id in objective_terrain_area.terrain_area_ids:
                terrain_area = areas_by_id[terrain_area_id]
                terrain_polygon = DeploymentZonePolygon(
                    vertices=tuple(
                        DeploymentZonePoint(x=point.x_inches, y=point.y_inches)
                        for point in terrain_area.footprint_polygon
                    )
                )
                assert terrain_polygon.contains_point(
                    objective.x_inches,
                    objective.y_inches,
                    include_boundary=True,
                )
        for source_component in source_layout.terrain_components:
            area = areas_by_id[source_component.terrain_area_id]
            placement = placements_by_id[source_component.component_id]
            feature = features_by_id[source_component.component_id]
            template = terrain_area_templates[area.footprint_template_id]
            local_x = placement.local_offset_x_inches
            if area.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS:
                local_x = (2.0 * template.polygon_vertices_inches[0].x_inches) - local_x
            radians = math.radians(area.rotation_degrees)
            battlefield_x = (
                area.center_x_inches
                + (local_x * math.cos(radians))
                - (placement.local_offset_y_inches * math.sin(radians))
            )
            battlefield_y = (
                area.center_y_inches
                + (local_x * math.sin(radians))
                + (placement.local_offset_y_inches * math.cos(radians))
            )
            assert math.isclose(
                battlefield_x,
                source_component.battlefield_center_x_inches,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            assert math.isclose(
                battlefield_y,
                source_component.battlefield_center_y_inches,
                rel_tol=0.0,
                abs_tol=1e-6,
            )
            component_rotation = placement.local_rotation_degrees
            if placement.local_transform.value == "mirror_y_axis":
                component_rotation += 180.0
            battlefield_rotation = (
                area.rotation_degrees + 180.0 - component_rotation
                if area.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS
                else area.rotation_degrees + component_rotation
            ) % 360.0
            rotation_delta = (
                battlefield_rotation - source_component.battlefield_rotation_degrees + 180.0
            ) % 360.0 - 180.0
            assert math.isclose(rotation_delta, 0.0, rel_tol=0.0, abs_tol=1e-6)
            assert feature.classification.value == (
                archetypes_by_id[source_component.archetype_id].classification
            )
            assert feature.to_rules_geometry_payload()["classification"] == (
                feature.classification.value
            )
            assert feature.source_id is not None
            assert (
                f"terrain-feature-placement:"
                f"{source_component.component_id.removeprefix(f'{layout_id}-')}"
            ) in feature.source_id
            assert event_layouts.BATTLEFIELD_PACKAGE_HASH in feature.source_id
            assert feature.source_id.endswith(f":{event_layouts.BATTLEFIELD_PACKAGE_HASH}")


def test_phase17n_exact_terrain_areas_drive_visibility_cover_and_typed_evidence() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="phase17n-exact-terrain-visibility",
    )
    areas = {area.terrain_area_id: area for area in setup.terrain_areas}
    dense_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-01"]
    mixed_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-02"]
    light_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-08"]
    visibility_areas = {
        area.terrain_area_id: area
        for area in terrain_visibility_areas_from_placements(setup.terrain_areas)
    }
    dense_visibility_area = visibility_areas[dense_area.logical_terrain_area_id]
    mixed_visibility_area = visibility_areas[mixed_area.logical_terrain_area_id]
    light_visibility_area = visibility_areas[light_area.logical_terrain_area_id]

    def model(model_id: str, x: float, y: float) -> Model:
        return Model(
            model_id=model_id,
            pose=Pose.at(x=x, y=y),
            base=CircularBase(radius=0.35),
            volume=ModelVolume(height=2.0),
        )

    target_in_dense_gap = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-dense-gap",
        observer_model=model("observer", 29.0, 51.6),
        target_models=(model("target", 31.5, 51.6),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_features=setup.terrain_features,
        terrain_areas=tuple(visibility_areas.values()),
    )
    round_tripped = TerrainVisibilityContext.from_payload(target_in_dense_gap.to_payload())
    dense_witness = round_tripped.resolve_line_of_sight()
    dense_cover = round_tripped.benefit_of_cover(dense_witness)

    assert round_tripped == target_in_dense_gap
    assert dense_witness.unit_visible
    assert dense_witness.unit_fully_visible
    assert dense_cover.has_benefit
    assert dense_cover.source_feature_ids == ()
    assert dense_cover.source_terrain_area_ids == (dense_area.terrain_area_id,)
    assert any(
        record.blocker_kind is VisibilityBlockerKind.TERRAIN_AREA
        and record.terrain_area_id == dense_area.terrain_area_id
        and record.exception_applied == "target_intersects_area"
        for record in dense_witness.all_blocker_records()
    )

    blocked_through_dense = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-through-dense",
        observer_model=model("observer", 28.0, 53.0),
        target_models=(model("target", 39.0, 53.0),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(dense_visibility_area,),
    ).resolve_line_of_sight()
    assert not blocked_through_dense.unit_visible
    assert any(
        record.blocker_kind is VisibilityBlockerKind.TERRAIN_AREA
        and record.terrain_area_classification is TerrainAreaClassification.DENSE
        and record.blocks_model_visibility
        for record in blocked_through_dense.all_blocker_records()
    )

    for observer_xy, target_xy, expected_exception in (
        ((31.5, 51.6), (29.0, 51.6), "observer_intersects_area"),
        ((29.0, 51.6), (31.5, 51.6), "target_intersects_area"),
    ):
        exception_witness = TerrainVisibilityContext.from_ruleset_descriptor(
            ruleset_descriptor=ruleset,
            los_cache_key=f"los:phase17n-{expected_exception}",
            observer_model=model("observer", *observer_xy),
            target_models=(model("target", *target_xy),),
            target_model_keywords=(("target", ("INFANTRY",)),),
            terrain_areas=(dense_visibility_area,),
        ).resolve_line_of_sight()
        assert exception_witness.unit_visible
        assert any(
            record.exception_applied == expected_exception
            for record in exception_witness.all_blocker_records()
        )

    mixed_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-mixed",
        observer_model=model("observer", 17.5, 45.3),
        target_models=(model("target", 18.1, 45.3),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(mixed_visibility_area,),
    )
    mixed_witness = mixed_context.resolve_line_of_sight()
    mixed_cover = mixed_context.benefit_of_cover(mixed_witness)
    assert mixed_witness.unit_visible
    assert mixed_cover.has_benefit
    assert mixed_cover.source_terrain_area_ids == (mixed_area.terrain_area_id,)
    assert any(
        record.terrain_area_classification is TerrainAreaClassification.MIXED
        for record in mixed_witness.all_blocker_records()
    )

    light_context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-light",
        observer_model=model("observer", 2.0, 33.0),
        target_models=(model("target", 7.0, 33.0),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(light_visibility_area,),
    )
    light_witness = light_context.resolve_line_of_sight()
    light_cover = light_context.benefit_of_cover(light_witness)
    assert light_witness.unit_visible
    assert light_cover.has_benefit
    assert light_cover.source_terrain_area_ids == (light_area.terrain_area_id,)
    assert any(
        record.terrain_area_classification is TerrainAreaClassification.LIGHT
        and record.exception_applied == "target_intersects_area"
        for record in light_witness.all_blocker_records()
    )

    blocked_through_light = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=ruleset,
        los_cache_key="los:phase17n-through-light",
        observer_model=model("observer", 2.0, 33.0),
        target_models=(model("target", 13.0, 33.0),),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(light_visibility_area,),
    ).resolve_line_of_sight()
    assert not blocked_through_light.unit_visible
    assert any(
        record.terrain_area_classification is TerrainAreaClassification.LIGHT
        and record.blocks_model_visibility
        for record in blocked_through_light.all_blocker_records()
    )

    assert model_within_solid_terrain(
        ruleset_descriptor=ruleset,
        model=model("dense-model", 31.5, 51.6),
        terrain_features=(),
        terrain_areas=(dense_area,),
    )
    assert model_within_solid_terrain(
        ruleset_descriptor=ruleset,
        model=model("mixed-model", 18.1, 45.3),
        terrain_features=(),
        terrain_areas=(mixed_area,),
    )
    assert not model_within_solid_terrain(
        ruleset_descriptor=ruleset,
        model=model("light-model", 7.0, 33.0),
        terrain_features=(),
        terrain_areas=(light_area,),
    )


def test_phase17n_unknown_terrain_area_classification_does_not_gate_membership_cover() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    physical_light_area = next(
        area
        for area in setup.terrain_areas
        if area.terrain_area_id == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-08"
    )
    exact_light_area = next(
        area
        for area in terrain_visibility_areas_from_placements(setup.terrain_areas)
        if area.terrain_area_id == physical_light_area.logical_terrain_area_id
    )
    unknown_area = replace(
        exact_light_area,
        classification=TerrainAreaClassification.UNKNOWN,
    )
    context = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17n-unknown-area-membership-cover",
        ),
        los_cache_key="los:phase17n-unknown-area-membership-cover",
        observer_model=Model(
            model_id="observer",
            pose=Pose.at(x=2.0, y=33.0),
            base=CircularBase(radius=0.35),
            volume=ModelVolume(height=2.0),
        ),
        target_models=(
            Model(
                model_id="target",
                pose=Pose.at(x=7.0, y=33.0),
                base=CircularBase(radius=0.35),
                volume=ModelVolume(height=2.0),
            ),
        ),
        target_model_keywords=(("target", ("INFANTRY",)),),
        terrain_areas=(unknown_area,),
    )

    witness = context.resolve_line_of_sight()
    cover = context.benefit_of_cover(witness)

    assert witness.unit_visible
    assert witness.unit_fully_visible
    assert witness.all_blocker_records() == ()
    assert cover.has_benefit
    assert cover.source_terrain_area_ids == (unknown_area.terrain_area_id,)
    assert len(cover.source_records) == 1
    source_record = cover.source_records[0]
    assert type(source_record) is TerrainAreaCoverSourceRecord
    assert source_record.classification is TerrainAreaClassification.UNKNOWN
    assert source_record.policy_kind is LineOfSightPolicy.TRUE_LINE_OF_SIGHT
    assert source_record.reason is CoverSourceReason.WITHIN_TERRAIN_AREA
    disabled_cover_policy = replace(
        context.terrain_visibility_policy,
        cover_policy=replace(
            context.terrain_visibility_policy.cover_policy,
            grants_benefit_of_cover=False,
        ),
    )
    assert not BenefitOfCoverResult.from_cover_sources(
        witness=witness,
        terrain_visibility_policy=disabled_cover_policy,
        source_records=cover.source_records,
    ).has_benefit


def test_phase17n_visibility_resolves_feature_area_associations_once_per_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="purge-the-foe",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    visibility_areas = terrain_visibility_areas_from_placements(setup.terrain_areas)
    terrain_features = setup.terrain_features[:2]
    original_polygon_within_polygon_union = shapely_backend.polygon_within_polygon_union
    association_check_count = 0

    def counting_polygon_within_polygon_union(
        inner: tuple[tuple[float, float], ...],
        outers: tuple[tuple[tuple[float, float], ...], ...],
    ) -> bool:
        nonlocal association_check_count
        association_check_count += 1
        return original_polygon_within_polygon_union(inner, outers)

    monkeypatch.setattr(
        shapely_backend,
        "polygon_within_polygon_union",
        counting_polygon_within_polygon_union,
    )

    witness = TerrainVisibilityContext.from_ruleset_descriptor(
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(
            descriptor_version="phase17n-feature-area-association-cache",
        ),
        los_cache_key="los:phase17n-feature-area-association-cache",
        observer_model=Model(
            model_id="observer",
            pose=Pose.at(x=2.0, y=2.0),
            base=CircularBase(radius=0.35),
            volume=ModelVolume(height=2.0),
        ),
        target_models=(
            Model(
                model_id="target-a",
                pose=Pose.at(x=42.0, y=58.0),
                base=CircularBase(radius=0.35),
                volume=ModelVolume(height=2.0),
            ),
            Model(
                model_id="target-b",
                pose=Pose.at(x=40.0, y=56.0),
                base=CircularBase(radius=0.35),
                volume=ModelVolume(height=2.0),
            ),
        ),
        target_model_keywords=(
            ("target-a", ("INFANTRY",)),
            ("target-b", ("INFANTRY",)),
        ),
        terrain_features=terrain_features,
        terrain_areas=visibility_areas,
    ).resolve_line_of_sight()

    assert witness.target_model_ids == ("target-a", "target-b")
    assert 0 < association_check_count <= (len(terrain_features) * len(visibility_areas))


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


def test_phase17j_event_matrix_uses_pdf_source_pairings_not_chapter_approved_order() -> None:
    source_rows = event_source.event_primary_mission_matrix_source_rows()
    executable_primary_ids = event_primary_scoring.engine_implemented_primary_mission_ids()
    matrix = {
        (row.player_force_disposition_id, row.opponent_force_disposition_id): row
        for row in event_source.primary_mission_matrix_rows()
    }

    assert len(source_rows) == 15
    assert len(matrix) == 25
    complete_pair_ids = {
        row.layout_pair_id
        for row in source_rows
        if row.source_left_primary_mission_id in executable_primary_ids
        and row.source_right_primary_mission_id in executable_primary_ids
    }
    assert complete_pair_ids == {
        "disruption-vs-disruption",
        "disruption-vs-priority-assets",
        "disruption-vs-reconnaissance",
        "priority-assets-vs-priority-assets",
        "purge-the-foe-vs-disruption",
        "purge-the-foe-vs-priority-assets",
        "purge-the-foe-vs-purge-the-foe",
        "purge-the-foe-vs-reconnaissance",
        "reconnaissance-vs-priority-assets",
        "reconnaissance-vs-reconnaissance",
        "take-and-hold-vs-disruption",
        "take-and-hold-vs-priority-assets",
        "take-and-hold-vs-purge-the-foe",
        "take-and-hold-vs-reconnaissance",
        "take-and-hold-vs-take-and-hold",
    }
    assert (
        sum(
            len(row.battlefield_layout_ids)
            for row in event_source.primary_mission_matrix_rows()
            if row.player_force_disposition_id <= row.opponent_force_disposition_id
            and row.primary_mission_id in executable_primary_ids
            and matrix[
                (row.opponent_force_disposition_id, row.player_force_disposition_id)
            ].primary_mission_id
            in executable_primary_ids
        )
        == 45
    )
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
            "gw-11e-warhammer-event-companion-v1-1-2026-07:"
            "primary-mission-matrix-source:take-and-hold-vs-take-and-hold"
        ),
    }
    assert "<" not in json.dumps(source_row_payload, sort_keys=True)


def test_phase17j_layout_descriptors_cover_all_source_hashed_battlefields() -> None:
    descriptors = event_source.layout_descriptor_rows()
    artifact_layouts_by_id = {
        layout.layout_id: layout for layout in event_layouts.battlefield_artifact().layouts
    }

    assert len(descriptors) == 45
    assert {descriptor.layout_variant for descriptor in descriptors} == {"a", "b", "c"}
    assert {descriptor.source_page for descriptor in descriptors} == set(range(9, 54))
    assert all(
        descriptor.geometry_extraction_status == "source_hashed_battlefield_artifact_geometry"
        for descriptor in descriptors
    )
    for descriptor in descriptors:
        source_layout = artifact_layouts_by_id[descriptor.layout_id]
        assert descriptor.source_page == source_layout.source_page
        assert descriptor.battlefield_width_inches == 44.0
        assert descriptor.battlefield_depth_inches == 60.0
        assert descriptor.attacker_edge == source_layout.attacker_edge
        assert descriptor.defender_edge == source_layout.defender_edge
        assert len(descriptor.terrain_features) == len(source_layout.terrain_components)
        assert len(descriptor.objective_points) == len(source_layout.objectives)


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
        ((0.0, 60.0), (44.0, 60.0), (44.0, 48.0), (22.0, 48.0), (22.0, 40.0), (0.0, 40.0)),
    )
    assert _shape_polygons(layout_a.deployment_zones[1].shape) == (
        ((44.0, 0.0), (0.0, 0.0), (0.0, 12.0), (22.0, 12.0), (22.0, 20.0), (44.0, 20.0)),
    )
    assert _shape_polygons(layout_b.deployment_zones[0].shape) == (
        ((0.0, 0.0), (12.0, 0.0), (12.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(layout_b.deployment_zones[1].shape) == (
        ((32.0, 0.0), (44.0, 0.0), (44.0, 60.0), (32.0, 60.0)),
    )
    assert not layout_c.deployment_zones[0].shape.contains_point(22.0, 30.0)
    assert not layout_c.deployment_zones[1].shape.contains_point(22.0, 30.0)
    assert _shape_polygons(take_vs_purge_a.deployment_zones[0].shape) == (
        ((0.0, 0.0), (8.0, 0.0), (8.0, 30.0), (14.0, 30.0), (14.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(take_vs_purge_a.deployment_zones[1].shape) == (
        ((44.0, 60.0), (36.0, 60.0), (36.0, 30.0), (30.0, 30.0), (30.0, 0.0), (44.0, 0.0)),
    )
    assert _shape_polygons(take_vs_purge_c.deployment_zones[0].shape) == (
        ((0.0, 42.0), (44.0, 42.0), (44.0, 60.0), (0.0, 60.0)),
    )
    assert _shape_polygons(take_vs_purge_c.deployment_zones[1].shape) == (
        ((0.0, 0.0), (44.0, 0.0), (44.0, 18.0), (0.0, 18.0)),
    )
    assert _shape_polygons(take_vs_priority_a.deployment_zones[0].shape) == (
        ((0.0, 60.0), (44.0, 60.0), (0.0, 30.0)),
    )
    assert _shape_polygons(take_vs_priority_a.deployment_zones[1].shape) == (
        ((44.0, 0.0), (0.0, 0.0), (44.0, 30.0)),
    )
    descriptor = _layout_descriptor("take-and-hold", "purge-the-foe", "c")
    assert descriptor.attacker_edge == "north"
    assert descriptor.defender_edge == "south"


def test_phase17j_deployment_zone_helpers_fail_closed_for_unknown_shapes() -> None:
    unsupported_template = cast(
        event_source.DeploymentZoneLayoutTemplateId,
        "deployment-zone-layout-unsupported",
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
        _source_deployment_zone_template_base_shape(unsupported_template)
    with pytest.raises(MissionPackError, match="Unsupported deployment-zone layout template"):
        _source_deployment_zone_layout_edges(unsupported_template)
    with pytest.raises(MissionPackError, match="Battlefield layout ID must end in layout number"):
        _source_layout_number_from_layout_id("take-and-hold-vs-purge-the-foe-layout-z")


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


def test_phase17j_primary_matrix_inventory_drift_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unknown_primary_names() -> tuple[tuple[str, str], ...]:
        return (("primary-source-pending", "Source Pending"),)

    monkeypatch.setattr(event_source, "_event_primary_mission_names", unknown_primary_names)

    with pytest.raises(MissionPackError, match="artifact inventory drifted from the matrix"):
        event_source.primary_mission_rows()


def test_phase17j_source_lookup_helpers_fail_closed_for_unknown_ids() -> None:
    with pytest.raises(MissionPackError, match="Event Companion matrix row was not found"):
        _source_matrix_row(
            player_force_disposition_id="unknown-force",
            opponent_force_disposition_id="take-and-hold",
        )
    with pytest.raises(
        MissionPackError,
        match="MissionPackDefinition does not contain force_disposition_id",
    ):
        warhammer_event_companion_2026_07_mission_pack().force_disposition("unknown-force")


@pytest.mark.parametrize(
    ("layout_number", "expected_feature_count", "expects_multi_polygon_region"),
    [(1, 29, False), (3, 30, True)],
)
def test_phase17j_mission_setup_components_resolve_matching_battlefield_layout(
    layout_number: int,
    expected_feature_count: int,
    expects_multi_polygon_region: bool,
) -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = f"take-and-hold-vs-take-and-hold-layout-{layout_number}"
    layout = mission_pack.battlefield_layout(layout_id)
    setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        deployment_map=mission_pack.deployment_map(layout.deployment_map_id),
        terrain_layout=mission_pack.terrain_layout_template(layout.terrain_layout_id),
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="take-and-hold",
    )

    assert setup.battlefield_layout_id == layout.battlefield_layout_id
    assert len(setup.terrain_features) == expected_feature_count
    assert len(setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5
    assert any(len(region.shape.polygons) > 1 for region in setup.battlefield_regions) is (
        expects_multi_polygon_region
    )
    assert {
        (binding.objective_marker_id, binding.terrain_area_ids)
        for binding in setup.objective_terrain_areas
    } == {
        (binding.objective_marker_id, binding.terrain_area_ids)
        for binding in layout.objective_terrain_areas
    }


def test_phase17n_objective_bindings_require_complete_logical_terrain_areas() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    layout_id = "take-and-hold-vs-take-and-hold-layout-2"
    layout = mission_pack.battlefield_layout(layout_id)
    complete_binding = next(
        binding for binding in layout.objective_terrain_areas if len(binding.terrain_area_ids) > 1
    )
    partial_binding = replace(
        complete_binding,
        terrain_area_ids=complete_binding.terrain_area_ids[1:],
    )
    partial_layout_bindings = tuple(
        partial_binding if binding == complete_binding else binding
        for binding in layout.objective_terrain_areas
    )

    with pytest.raises(MissionPackError, match="every physical member"):
        replace(layout, objective_terrain_areas=partial_layout_bindings)

    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id=f"mission-{layout_id}",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="take-and-hold",
    )
    with pytest.raises(MissionSetupError, match="every physical member"):
        replace(
            setup,
            objective_terrain_areas=tuple(
                partial_binding if binding == complete_binding else binding
                for binding in setup.objective_terrain_areas
            ),
        )

    retained_area_id = complete_binding.terrain_area_ids[-1]
    relabelled_setup = replace(
        setup,
        terrain_areas=tuple(
            replace(area, logical_terrain_area_id=retained_area_id)
            if area.terrain_area_id == retained_area_id
            else area
            for area in setup.terrain_areas
            if area.terrain_area_id not in complete_binding.terrain_area_ids[:-1]
        ),
        objective_terrain_areas=tuple(
            replace(binding, terrain_area_ids=(retained_area_id,))
            if binding.objective_marker_id == complete_binding.objective_marker_id
            else binding
            for binding in setup.objective_terrain_areas
        ),
    )
    with pytest.raises(MissionSetupError, match="battlefield geometry drifted from source"):
        validate_mission_setup_source_layout(relabelled_setup)

    with pytest.raises(MissionSetupError, match="requires battlefield_layout_id"):
        replace(setup, battlefield_layout_id=None)

    layoutless_source_components = replace(
        setup,
        battlefield_layout_id=None,
        battlefield_regions=(),
        terrain_areas=(),
        terrain_features=(),
        objective_terrain_areas=(),
    )
    with pytest.raises(GameLifecycleError, match="component identities require"):
        validate_mission_setup_source_layout(layoutless_source_components)

    drifted_assignments = tuple(
        replace(assignment, primary_mission_id="primary-meatgrinder")
        if assignment.player_id == setup.attacker_player_id
        else assignment
        for assignment in setup.primary_mission_assignments
    )
    with pytest.raises(GameLifecycleError, match="Primary mission assignment drifted"):
        validate_mission_setup_source_layout(
            replace(setup, primary_mission_assignments=drifted_assignments)
        )

    bound_area_ids = {
        terrain_area_id
        for binding in setup.objective_terrain_areas
        for terrain_area_id in binding.terrain_area_ids
    }
    unbound_area = next(
        area for area in setup.terrain_areas if area.terrain_area_id not in bound_area_ids
    )
    x_shift = 0.05 if unbound_area.center_x_inches < 22.0 else -0.05
    shifted_area = replace(
        unbound_area,
        center_x_inches=unbound_area.center_x_inches + x_shift,
        footprint_polygon=tuple(
            replace(point, x_inches=point.x_inches + x_shift)
            for point in unbound_area.footprint_polygon
        ),
    )
    shifted_setup = replace(
        setup,
        terrain_areas=tuple(
            shifted_area if area == unbound_area else area for area in setup.terrain_areas
        ),
    )
    with pytest.raises(MissionSetupError, match="battlefield geometry drifted from source"):
        validate_mission_setup_source_layout(shifted_setup)

    with pytest.raises(MissionSetupError, match="battlefield geometry drifted from source"):
        validate_mission_setup_source_layout(replace(setup, terrain_features=()))

    canonical_feature = setup.terrain_features[0]
    custom_setup = replace(
        setup,
        battlefield_layout_id=None,
        deployment_map_id="custom-event-companion-deployment-map",
        terrain_layout_id="custom-event-companion-terrain-layout",
        terrain_areas=(),
        objective_terrain_areas=(),
        terrain_features=(canonical_feature,),
    )
    validate_mission_setup_source_layout(custom_setup)
    with pytest.raises(GameLifecycleError, match="Primary mission assignment drifted"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                primary_mission_assignments=tuple(
                    replace(assignment, primary_mission_id="primary-death-trap")
                    for assignment in custom_setup.primary_mission_assignments
                ),
            )
        )
    with pytest.raises(GameLifecycleError, match="source package identity drifted"):
        validate_mission_setup_source_layout(replace(custom_setup, source_version="drifted"))
    custom_meatgrinder_setup = replace(
        custom_setup,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-2",
        primary_mission_assignments=tuple(
            replace(
                assignment,
                force_disposition_id="purge-the-foe",
                primary_mission_id="primary-meatgrinder",
            )
            for assignment in custom_setup.primary_mission_assignments
        ),
    )
    validate_mission_setup_source_layout(custom_meatgrinder_setup)

    with pytest.raises(GameLifecycleError, match="canonical battlefield region identity drifted"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                battlefield_regions=(
                    replace(
                        custom_setup.battlefield_regions[0],
                        source_id="test:drifted-event-companion-region",
                    ),
                    *custom_setup.battlefield_regions[1:],
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="canonical terrain feature identity drifted"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                terrain_features=(
                    replace(
                        canonical_feature,
                        classification=TerrainAreaClassification.UNKNOWN,
                    ),
                ),
            )
        )

    with pytest.raises(GameLifecycleError, match="must not reuse source-backed provenance"):
        validate_mission_setup_source_layout(
            replace(
                custom_setup,
                terrain_features=(
                    replace(
                        canonical_feature,
                        feature_id="custom-event-companion-feature",
                        classification=TerrainAreaClassification.UNKNOWN,
                        source_id=mission_pack.terrain_feature_presets[0].source_id,
                    ),
                ),
            )
        )


def test_phase17j_objective_role_payload_is_required() -> None:
    marker = (
        warhammer_event_companion_2026_07_mission_pack()
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
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
            terrain_feature_placements=layout.terrain_feature_placements,
            objective_role_counts=layout.objective_role_counts,
            source_id=layout.source_id,
        )


def test_phase17j_layout_must_match_deployment_map_objective_geometry() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
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
            terrain_feature_placements=layout.terrain_feature_placements,
            objective_role_counts=layout.objective_role_counts,
            source_id=layout.source_id,
        )


def test_phase17j_card_amendments_are_separate_from_faq_patch_rows() -> None:
    amendment_set = event_source.card_amendment_set()
    faq_patches = event_companion_patches.faq_patch_rows()

    assert amendment_set.amendments == ()
    assert amendment_set.source_page == 4
    assert {patch.patch_id for patch in faq_patches} == {
        "faq-end-of-battle-vp-round-cap-exemption",
        "faq-operation-marker-removal-clears-status",
        "faq-operation-marker-removal-requires-card-permission",
        "faq-death-trap-trapped-area-scoring-window",
        "faq-surveil-the-foe-same-turn-marker-removal",
        "faq-vital-link-multiple-central-objectives",
    }
    assert {patch.behavior_descriptor for patch in faq_patches} == {
        "end_of_battle_vp_exempt_from_battle_round_cap",
        "operation_marker_removal_clears_applied_status",
        "operation_marker_removal_requires_primary_card_permission",
        "death_trap_trapped_area_checked_at_scoring_not_destruction_time",
        "surveil_the_foe_same_turn_marker_removal_allows_scoring",
        "vital_link_multiple_central_objectives_marker_control_allows_cumulative_vp",
    }
    assert all(patch.source_page == 4 for patch in faq_patches)
    assert all(
        patch.source_id.startswith("gw-11e-warhammer-event-companion-v1-1-2026-07:faq:")
        for patch in faq_patches
    )


def test_phase17j_base_size_source_rows_fail_closed_for_noncanonical_shapes() -> None:
    rows = event_source.base_size_source_rows()
    rows_by_kind = {row.base_source_kind: row for row in rows}

    assert len(event_companion_base_size_rows.BASE_SIZE_SOURCE_ROWS) == len(rows)
    assert event_companion_base_size_rows.BASE_SIZE_SOURCE_ROWS[0] == (
        "page-55-adepta-sororitas-aestred-thurga-and-agathae-dolan-aestred-thurga",
        55,
        "Adepta Sororitas",
        None,
        "Aestred Thurga and Agathae Dolan: Aestred Thurga",
        "32mm",
    )
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
        event_source.PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED: 25,
        event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING: 0,
        event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE: 0,
    }
    assert {
        row.primary_mission_id
        for row in coverage_rows.values()
        if row.status is event_source.PrimaryMissionScoringCoverageStatus.AWAITING_SOURCE
    } == set()
    assert {
        row.primary_mission_id
        for row in coverage_rows.values()
        if row.status
        is event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
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
    assert primary_rows["primary-meatgrinder"].scoring_kind == ("meatgrinder")
    assert primary_rows["primary-battlefield-dominance"].scoring_kind == ("battlefield_dominance")
    assert primary_rows["primary-purge-and-secure"].scoring_kind == ("purge_and_secure")
    assert primary_rows["primary-consecrate"].scoring_kind == "consecrate"
    assert primary_rows["primary-smoke-and-mirrors"].scoring_kind == "smoke_and_mirrors"
    assert primary_rows["primary-triangulation"].scoring_kind == "triangulation"
    assert primary_rows["primary-sabotage"].scoring_kind == "sabotage"
    assert primary_rows["primary-secure-asset"].scoring_kind == "secure_asset"
    assert primary_rows["primary-vanguard-operation"].scoring_kind == "vanguard_operation"
    assert primary_rows["primary-punishment"].scoring_kind == "punishment"
    assert primary_rows["primary-extract-relic"].scoring_kind == "extract_relic"
    assert primary_rows["primary-gather-intel"].scoring_kind == "gather_intel"
    assert primary_rows["primary-locate-and-deny"].scoring_kind == "locate_and_deny"
    assert primary_rows["primary-vital-link"].scoring_kind == "vital_link"
    assert primary_rows["primary-surveil-the-foe"].scoring_kind == "surveil_the_foe"
    assert coverage_rows["primary-unstoppable-force"].needed_work == ()
    assert coverage_rows["primary-meatgrinder"].needed_work == ()
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
    for implemented_mission_id in (
        "primary-battlefield-dominance",
        "primary-consecrate",
        "primary-delaying-action",
        "primary-destroyers-wrath",
        "primary-determined-acquisition",
        "primary-inescapable-dominion",
        "primary-outmaneuver",
        "primary-purge-and-secure",
        "primary-reconnaissance-sweep",
        "primary-search-and-scour",
        "primary-smoke-and-mirrors",
        "primary-triangulation",
        "primary-sabotage",
        "primary-secure-asset",
        "primary-vanguard-operation",
        "primary-punishment",
        "primary-extract-relic",
        "primary-gather-intel",
        "primary-locate-and-deny",
        "primary-vital-link",
        "primary-surveil-the-foe",
    ):
        assert coverage_rows[implemented_mission_id].needed_work == ()
    assert {
        mission_id: row.needed_work
        for mission_id, row in coverage_rows.items()
        if row.status
        is event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING
    } == {}


def test_phase17n_primary_actions_are_exposed_with_source_backed_policies() -> None:
    action_sources = {
        row.mission_action_id: row for row in event_source.primary_mission_action_source_rows()
    }
    mission_pack = warhammer_event_companion_2026_07_mission_pack()

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
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:decoy-objective"
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
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:extract-intelligence"
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
        "engine_exposure_status": "engine_implemented",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:surveil-enemy-unit"
        ),
    }
    assert action_sources["sensor-sweep-locate-and-deny"].target_policy == (
        "central_objective_and_friendly_operation_marker_requires_more_than_one_"
        "friendly_marker_remaining"
    )
    assert action_sources["sensor-sweep-extract-relic"].effect_descriptor == (
        "remove_one_opponent_operation_marker_if_action_unit_controls_selected_central_"
        "objective_at_turn_end"
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
        "engine_exposure_status": "engine_implemented",
        "source_id": ("gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:secure-asset"),
    }
    assert action_sources["vanguard-operation"].eligible_unit_policy == (
        "active_player_unit_within_terrain_area_in_enemy_territory"
    )
    assert action_sources["maintain-control"].effect_descriptor == (
        "central_objective_gains_operation_marker_if_action_unit_controls_target_at_turn_end"
    )
    assert len(mission_pack.mission_actions) == 14
    for action_id, source_row in action_sources.items():
        runtime_action = mission_pack.mission_action(action_id)
        policy = mission_action_policies.mission_action_policy_for_identity(
            mission_action_id=action_id,
            source_id=source_row.source_id,
        )
        assert runtime_action.mission_id == source_row.primary_mission_id
        assert runtime_action.mission_kind == "primary"
        assert runtime_action.source_id == (
            f"gw-11e-warhammer-event-companion-v1-1-2026-07:action:{action_id}"
        )
        assert policy.source_id == source_row.source_id
        assert runtime_action.victory_points == 0
        assert policy.primary_mission_id == runtime_action.mission_id
        assert policy.use_limit == source_row.use_limit
        assert policy.effect_descriptor == source_row.effect_descriptor
        assert policy.target_policy == runtime_action.target_policy
        assert policy.interruption_conditions == runtime_action.interruption_conditions


def test_phase17n_primary_state_and_choice_rules_have_strict_runtime_lookups() -> None:
    consecrate_state = mission_action_policies.primary_mission_state_rule_for_id(
        "consecrate-destroyer-becomes-consecration-unit"
    )
    surveil_state = mission_action_policies.primary_mission_state_rule_for_id(
        "surveil-remove-operation-markers-after-move"
    )
    punishment_choice = mission_action_policies.primary_mission_choice_rule_for_id(
        "punishment-condemn-enemy-units"
    )
    locate_choice = mission_action_policies.primary_mission_choice_rule_for_id(
        "locate-and-deny-operation-marker-setup"
    )

    assert consecrate_state.effect_descriptor == "unit_becomes_consecration_unit"
    assert consecrate_state.effect_duration == "until_consumed"
    assert surveil_state.trigger_timing == "friendly_rules_unit_move_end"
    assert surveil_state.effect_descriptor == (
        "remove_all_opponent_operation_markers_from_each_in_range_objective"
    )
    assert punishment_choice.selection_policy == (
        "one_to_three_or_exactly_one_fallback_when_no_primary_targets"
    )
    assert punishment_choice.fallback_target_policy == "enemy_battlefield_unit"
    assert locate_choice.selection_policy == "exactly_five_or_all_available_when_fewer"
    assert locate_choice.maximum_selections == 5
    assert tuple(
        rule.choice_rule_id
        for rule in mission_action_policies.primary_mission_choice_rules_for_mission(
            "primary-consecrate"
        )
    ) == ("consecrate-objective-at-turn-end",)
    assert tuple(
        rule.state_rule_id
        for rule in mission_action_policies.primary_mission_state_rules_for_mission(
            "primary-surveil-the-foe"
        )
    ) == ("surveil-remove-operation-markers-after-move",)
    with pytest.raises(
        mission_action_policies.MissionActionPolicyError,
        match="policy is not registered",
    ):
        mission_action_policies.mission_action_policy_for_id("forged-action")
    with pytest.raises(
        mission_action_policies.MissionActionPolicyError,
        match="identify different rules",
    ):
        mission_action_policies.mission_action_policy_for_identity(
            mission_action_id="commit-sabotage",
            source_id=(
                "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:decoy-objective"
            ),
        )


def test_phase17j_surveil_primary_scoring_is_supported_on_primary_path() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="reconnaissance",
        defender_player_id="player-beta",
        defender_force_disposition_id="disruption",
    )

    policies = mission_scoring_policies_from_setup(setup)

    attacker_policy = policies.policy_for_player("player-alpha")
    defender_policy = policies.policy_for_player("player-beta")

    assert attacker_policy.primary_mission_id == "primary-surveil-the-foe"
    assert attacker_policy.primary_scoring_supported
    assert defender_policy.primary_mission_id == "primary-smoke-and-mirrors"
    assert defender_policy.primary_scoring_supported
    assert (
        attacker_policy.cap_bucket_for_victory_point_source(
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=attacker_policy.primary_mission_id,
        ).value
        == "primary"
    )


def test_phase17j_event_pack_resolves_scoring_and_tactical_draw_by_pack_id() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    policies = mission_scoring_policies_from_setup(setup)
    policy = policies.common_policy
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
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        attacker_force_disposition_id="take-and-hold",
        defender_player_id="player-beta",
        defender_force_disposition_id="purge-the-foe",
    )
    policies = mission_scoring_policies_from_setup(setup)
    player_alpha_ledger, _ = VictoryPointLedger.initial(player_id="player-alpha").award(
        VictoryPointAward(
            player_id="player-alpha",
            battle_round=5,
            phase="command",
            amount=55,
            source_kind=VictoryPointSourceKind.PRIMARY,
            source_id=setup.primary_mission_id_for_player("player-alpha"),
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
            source_id=setup.primary_mission_id_for_player("player-beta"),
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
        policies=policies,
        ledgers=(player_alpha_ledger, player_beta_ledger),
        scoring_windows=_event_final_scoring_windows(
            game_id="phase17j-event-final-scoring",
            battle_round=5,
            policy_source_id=policies.source_id,
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


def _meatgrinder_artifact_layouts() -> tuple[Any, ...]:
    layouts = tuple(
        layout
        for layout in event_layouts.battlefield_artifact().layouts
        if layout.source_page in {24, 25, 26}
    )
    assert tuple(layout.source_page for layout in layouts) == (24, 25, 26)
    return layouts


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


def _source_deployment_zone_template_base_shape(
    template_id: event_source.DeploymentZoneLayoutTemplateId,
) -> DeploymentZoneShape:
    function = cast(
        Callable[[event_source.DeploymentZoneLayoutTemplateId], DeploymentZoneShape],
        vars(event_source)["_deployment_zone_template_base_shape"],
    )
    return function(template_id)


def _source_layout_number_from_layout_id(layout_id: str) -> int:
    function = cast(
        Callable[[str], int],
        vars(event_source)["_layout_number_from_layout_id"],
    )
    return function(layout_id)


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


def _shape_polygons(shape: DeploymentZoneShape) -> tuple[tuple[tuple[float, float], ...], ...]:
    return tuple(
        tuple((point.x, point.y) for point in polygon.vertices) for polygon in shape.polygons
    )


def _terrain_display_points(
    points: tuple[TerrainDisplayPoint, ...],
) -> tuple[tuple[float, float], ...]:
    return tuple((point.x_inches, point.y_inches) for point in points)


def _event_final_scoring_windows(
    *,
    game_id: str,
    battle_round: int,
    policy_source_id: str,
) -> tuple[ScoringWindowState, ...]:
    return (
        ScoringWindowState(
            window_id=(
                f"scoring-window:{game_id}:round-{battle_round:02d}:end_of_round:battle_round_end"
            ),
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_ROUND,
            window="battle_round_end",
            source_id=f"{policy_source_id}:window:end_of_round:battle_round_end",
        ),
        ScoringWindowState(
            window_id=(
                f"scoring-window:{game_id}:round-{battle_round:02d}:"
                "end_of_game:turn_end_round_five_going_second"
            ),
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="turn_end_round_five_going_second",
            source_id=(f"{policy_source_id}:window:end_of_game:turn_end_round_five_going_second"),
        ),
        ScoringWindowState(
            window_id=(
                f"scoring-window:{game_id}:round-{battle_round:02d}:end_of_game:end_of_battle"
            ),
            game_id=game_id,
            battle_round=battle_round,
            window_kind=ScoringWindowKind.END_OF_GAME,
            window="end_of_battle",
            source_id=f"{policy_source_id}:window:end_of_game:end_of_battle",
        ),
    )
