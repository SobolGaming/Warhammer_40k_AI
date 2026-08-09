from __future__ import annotations

import hashlib
import json
import math
import subprocess
import sys
from collections import Counter
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest

from warhammer40k_core.core.deployment_zones import (
    DeploymentZone,
    DeploymentZoneCircleCutout,
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
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.core.terrain_areas import (
    TerrainAreaClassification,
    TerrainAreaLocalTransform,
)
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
from warhammer40k_core.engine.shooting_terrain_visibility import (
    model_within_solid_terrain,
    terrain_visibility_areas_from_placements,
)
from warhammer40k_core.geometry import shapely_backend
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.visibility import (
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


def test_phase17j_event_companion_package_identity_and_payload_round_trip() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    source_package = mission_pack.source_package
    payload = mission_pack.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = cast(MissionPackDefinitionPayload, json.loads(encoded))

    assert mission_pack.mission_pack_id == "11e-warhammer-event-companion-2026-07"
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
    assert {
        row.layout_id for row in rows if row.layout_id in event_layouts.EXTRACTED_LAYOUT_IDS
    } == {
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-3",
    }


def test_phase17j_v1_1_extracted_layouts_use_revised_terrain_transforms() -> None:
    layout_a = event_layouts.EXTRACTED_LAYOUTS_BY_ID["disruption-vs-reconnaissance-layout-1"]
    layout_c = event_layouts.EXTRACTED_LAYOUTS_BY_ID["disruption-vs-reconnaissance-layout-3"]
    layout_a_specs = {spec[0]: spec[1:] for spec in layout_a.terrain_area_specs}
    layout_c_specs = {spec[0]: spec[1:] for spec in layout_c.terrain_area_specs}

    assert layout_a_specs["7x11-5-attacker-home"] == (
        "FOOTPRINT_7X11_5",
        21.09,
        42.59,
        180.0,
    )
    assert layout_a_specs["6x2-east-midfield"] == (
        "FOOTPRINT_6X2",
        32.74,
        31.55,
        -8.0,
    )
    assert layout_a_specs["6x4-east-midfield"] == (
        "FOOTPRINT_6X4",
        29.08,
        22.14,
        82.0,
    )
    assert layout_a_specs["8x11-5-polygon-north-center"] == (
        "FOOTPRINT_8X11_5_POLYGON",
        30.8,
        39.5,
        -125.0,
    )
    assert layout_c_specs["8x11-5-polygon-north-east"] == (
        "FOOTPRINT_8X11_5_POLYGON",
        34.09,
        43.83,
        142.0,
    )
    assert layout_c_specs["6x4-south-west-midfield"] == (
        "FOOTPRINT_6X4",
        9.52,
        24.32,
        -37.5,
    )


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
        "purge-the-foe-vs-purge-the-foe-layout-1",
        "purge-the-foe-vs-purge-the-foe-layout-2",
        "purge-the-foe-vs-purge-the-foe-layout-3",
    }
    disruption_reconnaissance_layout_ids = {
        "disruption-vs-reconnaissance-layout-1",
        "disruption-vs-reconnaissance-layout-2",
        "disruption-vs-reconnaissance-layout-3",
    }
    exact_slice_layout_ids = set(event_layouts.EXACT_SLICE_LAYOUT_IDS)

    assert len(mission_pack.primary_missions) == 25
    assert len(mission_pack.primary_mission_matrix_cells) == 25
    assert all(
        cell.source_status is MissionSourceStatus.IMPLEMENTED
        for cell in mission_pack.primary_mission_matrix_cells
    )
    assert len(layout_ids) == 45
    assert len(mission_pack.battlefield_layouts) == 9
    assert len(mission_pack.terrain_area_footprint_templates) == 5
    assert len(mission_pack.terrain_feature_presets) == 19
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
            assert len(setup.terrain_features) == (
                30 if terrain_layout_id in exact_slice_layout_ids else 16
            )
            assert len(setup.terrain_areas) == 16
            assert len(setup.battlefield_regions) == 5
        else:
            assert setup.battlefield_layout_id is None
            assert setup.terrain_areas == ()
            assert setup.battlefield_regions == ()
            assert setup.terrain_features == ()
        expected_objective_count = (
            6
            if terrain_layout_id in disruption_reconnaissance_layout_ids | exact_slice_layout_ids
            else 5
        )
        assert len(setup.objective_markers) == expected_objective_count
        assert len(setup.deployment_zones) == 2


def test_phase17n_meatgrinder_scoring_artifact_is_source_hashed_strict_and_consumed() -> None:
    artifact = event_primary_scoring.meatgrinder_primary_scoring_artifact()
    repository_root = Path(__file__).resolve().parents[2]
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_2026_06_artifacts/primary-meatgrinder-scoring.json"
    )
    raw = artifact_path.read_bytes()

    assert hashlib.sha256(raw).hexdigest() == (
        event_primary_scoring.MEATGRINDER_SCORING_ARTIFACT_SHA256
    )
    assert artifact.package_hash == event_primary_scoring.MEATGRINDER_SCORING_PACKAGE_HASH
    assert artifact.authoritative_source.source_kind == (
        "project_owner_supplied_official_source_transcription"
    )
    assert artifact.authoritative_source.review_pull_request == 134
    assert artifact.authoritative_source.review_commit == "35b9ddaf5"
    assert artifact.secondary_corroboration.authority_status == (
        "secondary_corroboration_not_official_gw_source"
    )
    assert artifact.secondary_corroboration.card_image_sha256 == (
        "d4bcc1dfde2d72fb2fc31b095964d1ea7721dcd082967b0063bcfd77c9965c24"
    )
    assert artifact.layout_source_boundary.source_pages == (24, 25, 26)
    assert artifact.layout_source_boundary.authority_scope == ("battlefield_and_layout_facts_only")
    assert not artifact.layout_source_boundary.contains_meatgrinder_scoring_clauses
    assert tuple(rule.canonical_text for rule in artifact.scoring_rules) == (
        "One or more enemy units were destroyed this turn.",
        "You control one or more objectives (excluding your home objective).",
        (
            "More enemy units were destroyed this turn than friendly units were "
            "destroyed in the previous turn."
        ),
        "You control your opponent's home objective.",
    )

    runtime_row = next(
        row
        for row in event_source.primary_mission_rows()
        if row.primary_mission_id == artifact.primary_mission_id
    )
    assert runtime_row.name == artifact.mission_name
    assert runtime_row.scoring_kind == artifact.scoring_kind
    assert tuple(rule.to_payload() for rule in runtime_row.scoring_rules) == tuple(
        {
            "rule_id": rule.rule_id,
            "timing": rule.timing,
            "source_kind": rule.source_kind,
            "victory_points": rule.victory_points,
            "cap": rule.cap,
            "condition": rule.condition,
        }
        for rule in artifact.scoring_rules
    )
    event_primary_scoring.validate_meatgrinder_primary_scoring_artifact_bytes(raw)

    with pytest.raises(ValueError, match="artifact bytes drifted"):
        event_primary_scoring.validate_meatgrinder_primary_scoring_artifact_bytes(raw + b"\n")

    unknown_field_payload = json.loads(raw)
    unknown_field_payload["scoring_rules"][0]["unexpected"] = True
    with pytest.raises(ValueError, match="artifact is invalid"):
        event_primary_scoring.event_companion_primary_scoring_artifact_from_json_bytes(
            json.dumps(unknown_field_payload).encode()
        )

    stale_hash_payload = json.loads(raw)
    stale_hash_payload["scoring_rules"][2]["canonical_text"] += " Drift."
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


def test_phase17n_meatgrinder_exact_slice_artifact_is_source_hashed_and_strict() -> None:
    artifact = event_layouts.exact_slice_artifact()
    repository_root = Path(__file__).resolve().parents[2]
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_layouts_2026_06/artifacts"
        / "purge-the-foe-vs-purge-the-foe-meatgrinder.json"
    )
    source_pdf_path = (
        repository_root
        / "docs/source_rules"
        / "eng_22-07_warhammer40000_event_companion-alyapl19us-b2drgwkji4.pdf"
    )
    raw = artifact_path.read_bytes()

    assert artifact.source_pages == (24, 25, 26)
    assert artifact.source_extraction_payload_sha256 == (
        "8d0082df6516b8927cf8666042a9a679863b81205d41377a85c1823cf8e35b30"
    )
    assert artifact.source_pdf_sha256 == (
        "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
    )
    assert hashlib.sha256(source_pdf_path.read_bytes()).hexdigest() == artifact.source_pdf_sha256
    assert hashlib.sha256(raw).hexdigest() == event_layouts.EXACT_SLICE_ARTIFACT_SHA256
    assert artifact.package_hash == event_layouts.EXACT_SLICE_PACKAGE_HASH
    assert len(artifact.feature_archetypes) == 14
    assert tuple(len(layout.terrain_areas) for layout in artifact.layouts) == (16, 16, 16)
    assert tuple(len(layout.terrain_components) for layout in artifact.layouts) == (30, 30, 30)
    assert {
        area.area_id: (area.anchor_x_inches, area.anchor_y_inches)
        for layout in artifact.layouts
        for area in layout.terrain_areas
        if area.footprint_template_id == "FOOTPRINT_8X11_5_POLYGON"
    } == {
        "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-02": (
            27.042098342,
            50.182832221,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-15": (
            16.697859026,
            9.700151112,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-03": (
            15.891604839,
            44.107128805,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-2-terrain-area-14": (
            28.146336111,
            15.825812322,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-05": (
            32.027815928,
            43.018007668,
        ),
        "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-12": (
            12.014226239,
            15.866469927,
        ),
    }
    assert {
        asset.source_pdf_image_xref
        for archetype in artifact.feature_archetypes
        if archetype.archetype_id == "dense-tall-crates"
        for asset in archetype.source_assets
    } == {5486, 5675}
    event_layouts.validate_exact_slice_artifact_bytes(raw)

    unknown_field_payload = json.loads(raw)
    unknown_field_payload["unexpected"] = True
    with pytest.raises(ValueError, match="artifact is invalid"):
        event_layouts.validate_exact_slice_artifact_bytes(
            json.dumps(unknown_field_payload).encode()
        )

    missing_source_assets_payload = json.loads(raw)
    missing_source_assets_payload["feature_archetypes"][0]["source_assets"] = []
    with pytest.raises(ValueError, match="require source-image assets"):
        event_layouts.validate_exact_slice_artifact_bytes(
            json.dumps(missing_source_assets_payload).encode()
        )

    stale_hash_payload = json.loads(raw)
    stale_hash_payload["layouts"][0]["objectives"][0]["x_inches"] = 8.59
    with pytest.raises(ValueError, match="package hash is stale"):
        event_layouts.validate_exact_slice_artifact_bytes(json.dumps(stale_hash_payload).encode())

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
        event_layouts.validate_exact_slice_artifact_bytes(
            json.dumps(rehashed_coordinate_payload).encode()
        )

    wrong_area_payload = json.loads(raw)
    wrong_area_payload["layouts"][2]["objectives"][4]["terrain_area_ids"] = [
        "purge-the-foe-vs-purge-the-foe-layout-3-terrain-area-05"
    ]
    wrong_area_payload["package_hash"] = ""
    wrong_area_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            wrong_area_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="objective terrain-area mapping drifted"):
        event_layouts.validate_exact_slice_artifact_bytes(json.dumps(wrong_area_payload).encode())

    unreflected_source_affine_payload = json.loads(raw)
    unreflected_source_affine_payload["layouts"][0]["terrain_areas"][3]["local_transform"] = (
        "identity"
    )
    unreflected_source_affine_payload["package_hash"] = ""
    unreflected_source_affine_payload["package_hash"] = hashlib.sha256(
        json.dumps(
            unreflected_source_affine_payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    with pytest.raises(ValueError, match="local reflection must match its source affine"):
        event_layouts.validate_exact_slice_artifact_bytes(
            json.dumps(unreflected_source_affine_payload).encode()
        )


def test_phase17n_meatgrinder_exact_slice_builder_reproduces_committed_artifact(
    tmp_path: Path,
) -> None:
    repository_root = Path(__file__).resolve().parents[2]
    extraction_path = (
        repository_root
        / "data/source_audits/event_companion_2026_06"
        / "phase17n_purge_the_foe_meatgrinder_pages_24_26_extraction.json"
    )
    artifact_path = (
        repository_root
        / "src/warhammer40k_core/rules/source_packages/warhammer_40000_11th"
        / "event_companion_layouts_2026_06/artifacts"
        / "purge-the-foe-vs-purge-the-foe-meatgrinder.json"
    )
    extraction_payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    pose_reviews = tuple(
        area["accepted_pose_review"]
        for layout in extraction_payload["layouts"]
        for area in layout["terrain_areas"]
    )
    assert extraction_payload["status"] == ("reviewed_source_registration_ready_for_exact_runtime")
    assert extraction_payload["placement_pose_review"] == {
        "accepted_area_count": 48,
        "rendered_overlays_authoritative": False,
        "reviewed_on": "2026-08-09",
        "reviewed_source_pdf_pages": [24, 25, 26],
        "reviewed_source_pdf_sha256": (
            "97ae5591be2e58bdb636e97127eac0877f9bf28b29fc607ed4ead4d377fb8f20"
        ),
        "source_page_raster_overlay_registration_review_count": 42,
        "status": "accepted_for_exact_runtime",
        "vector_edge_correction_plus_raster_review_count": 6,
    }
    assert len(pose_reviews) == 48
    assert Counter(review["method"] for review in pose_reviews) == Counter(
        {
            "source_page_raster_overlay_registration_review": 42,
            "pdf_vector_edge_correction_plus_source_page_raster_overlay_review": 6,
        }
    )
    assert all(review["status"] == "accepted_for_exact_runtime" for review in pose_reviews)
    assert all(not review["rendered_overlay_authoritative"] for review in pose_reviews)
    modified_at_before_check = artifact_path.stat().st_mtime_ns
    result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "tools/build_phase17n_event_companion_exact_slice.py"),
            "--check",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert artifact_path.stat().st_mtime_ns == modified_at_before_check

    stale_output_path = tmp_path / "stale-phase17n-artifact.json"
    stale_output_path.write_text("{}\n", encoding="utf-8")
    stale_bytes = stale_output_path.read_bytes()
    stale_result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "tools/build_phase17n_event_companion_exact_slice.py"),
            str(extraction_path),
            str(stale_output_path),
            "--check",
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert stale_result.returncode != 0
    assert "exact-slice artifact is stale" in stale_result.stderr
    assert stale_output_path.read_bytes() == stale_bytes

    unreviewed_payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    unreviewed_payload["layouts"][0]["terrain_areas"][0]["accepted_pose_review"]["status"] = (
        "pending_source_page_review"
    )
    unreviewed_extraction_path = tmp_path / "unreviewed-phase17n-extraction.json"
    unreviewed_extraction_path.write_text(
        json.dumps(unreviewed_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    unreviewed_result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "tools/build_phase17n_event_companion_exact_slice.py"),
            str(unreviewed_extraction_path),
            str(tmp_path / "unreviewed-output.json"),
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert unreviewed_result.returncode != 0
    assert "pose review is not accepted for exact runtime use" in unreviewed_result.stderr

    drifted_raster_payload = json.loads(extraction_path.read_text(encoding="utf-8"))
    drifted_raster_payload["layouts"][0]["terrain_areas"][0]["accepted_pose_review"][
        "accepted_anchor_inches"
    ][0] += 0.25
    drifted_raster_path = tmp_path / "drifted-raster-phase17n-extraction.json"
    drifted_raster_path.write_text(
        json.dumps(drifted_raster_payload, indent=2) + "\n",
        encoding="utf-8",
    )
    drifted_raster_result = subprocess.run(
        [
            sys.executable,
            str(repository_root / "tools/build_phase17n_event_companion_exact_slice.py"),
            str(drifted_raster_path),
            str(tmp_path / "drifted-raster-output.json"),
        ],
        cwd=repository_root,
        check=False,
        capture_output=True,
        text=True,
    )

    assert drifted_raster_result.returncode != 0
    assert "raster-reviewed pose must pin the reviewed estimate" in (drifted_raster_result.stderr)


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
    artifact = event_layouts.exact_slice_artifact()
    artifact_mirrored_ids = {
        area.area_id
        for layout in artifact.layouts
        for area in layout.terrain_areas
        if area.local_transform == "mirror_y_axis"
    }

    assert len(source_orientation_reversing_ids) == 12
    assert artifact_mirrored_ids == source_orientation_reversing_ids

    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    layout_a_area_04 = next(
        area
        for area in setup.terrain_areas
        if area.terrain_area_id == "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-04"
    )

    assert layout_a_area_04.local_transform is TerrainAreaLocalTransform.MIRROR_Y_AXIS
    assert tuple(
        (point.x_inches, point.y_inches) for point in layout_a_area_04.footprint_polygon
    ) == (
        (40.5, 46.0),
        (34.5, 46.0),
        (34.5, 44.7),
        (34.0, 44.0),
        (34.4, 43.3),
        (34.2, 43.0),
        (34.5, 42.8),
        (34.5, 42.0),
        (37.2, 42.0),
        (37.3, 41.8),
        (37.7, 41.9),
        (38.5, 41.5),
        (39.3, 42.0),
        (40.5, 42.0),
    )


def test_phase17n_meatgrinder_exact_layouts_build_all_source_components() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    artifact = event_layouts.exact_slice_artifact()
    artifact_layouts = {layout.layout_id: layout for layout in artifact.layouts}
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
            defender_player_id="player-beta",
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
        assert all(
            wall.height_inches == (3.0 if wall.bottom_z_inches == 0.0 else 2.0)
            for ruin in ruins
            for wall in ruin.walls
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
            assert event_layouts.EXACT_SLICE_PACKAGE_HASH in feature.source_id
            assert feature.source_id.endswith(f":{event_layouts.EXACT_SLICE_PACKAGE_HASH}")


def test_phase17n_exact_terrain_areas_drive_visibility_cover_and_typed_evidence() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    ruleset = RulesetDescriptor.warhammer_40000_eleventh(
        descriptor_version="phase17n-exact-terrain-visibility",
    )
    areas = {area.terrain_area_id: area for area in setup.terrain_areas}
    dense_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-01"]
    mixed_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-02"]
    light_area = areas["purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-04"]
    visibility_areas = {
        area.terrain_area_id: area
        for area in terrain_visibility_areas_from_placements(setup.terrain_areas)
    }
    dense_visibility_area = visibility_areas[dense_area.terrain_area_id]
    mixed_visibility_area = visibility_areas[mixed_area.terrain_area_id]
    light_visibility_area = visibility_areas[light_area.terrain_area_id]

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
        observer_model=model("observer", 32.0, 43.0),
        target_models=(model("target", 36.0, 43.0),),
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
        observer_model=model("observer", 32.0, 43.0),
        target_models=(model("target", 43.0, 43.0),),
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
        model=model("light-model", 36.0, 43.0),
        terrain_features=(),
        terrain_areas=(light_area,),
    )


def test_phase17n_visibility_resolves_feature_area_associations_once_per_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    visibility_areas = terrain_visibility_areas_from_placements(setup.terrain_areas)
    terrain_features = setup.terrain_features[:2]
    original_polygon_within_polygon = shapely_backend.polygon_within_polygon
    association_check_count = 0

    def counting_polygon_within_polygon(
        inner: tuple[tuple[float, float], ...],
        outer: tuple[tuple[float, float], ...],
    ) -> bool:
        nonlocal association_check_count
        association_check_count += 1
        return original_polygon_within_polygon(inner, outer)

    monkeypatch.setattr(
        shapely_backend,
        "polygon_within_polygon",
        counting_polygon_within_polygon,
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
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
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
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
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
    layout = warhammer_event_companion_2026_07_mission_pack().battlefield_layout(
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
            "gw-11e-warhammer-event-companion-v1-1-2026-07:"
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
    meatgrinder_layouts = tuple(
        _layout_descriptor("purge-the-foe", "purge-the-foe", variant) for variant in ("a", "b", "c")
    )
    extracted_layout_ids = {
        layout_a.layout_id,
        layout_b.layout_id,
        layout_c.layout_id,
        disruption_layout_a.layout_id,
        disruption_layout_b.layout_id,
        disruption_layout_c.layout_id,
        *(layout.layout_id for layout in meatgrinder_layouts),
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
    assert len(pending_descriptors) == 36
    assert all(len(descriptor.objective_points) == 5 for descriptor in pending_descriptors)
    assert all(
        len(descriptor.objective_points) == 5 for descriptor in (layout_a, layout_b, layout_c)
    )
    assert all(
        len(descriptor.objective_points) == 6
        for descriptor in (
            disruption_layout_a,
            disruption_layout_b,
            disruption_layout_c,
            *meatgrinder_layouts,
        )
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
            *meatgrinder_layouts,
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
        descriptor.geometry_extraction_status == "source_hashed_exact_layout_geometry"
        for descriptor in meatgrinder_layouts
    )
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
        for layout_id in extracted_layout_ids - set(event_layouts.EXACT_SLICE_LAYOUT_IDS)
    )
    assert all(
        next(
            row
            for row in event_source.battlefield_layout_rows()
            if row.battlefield_layout_id == layout_id
        ).source_status
        == "event_companion_source_hashed_exact_slice"
        for layout_id in event_layouts.EXACT_SLICE_LAYOUT_IDS
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    assert len(layout.terrain_feature_placements) == 16
    assert len(setup.terrain_features) == 16
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    assert len(setup.terrain_features) == 16
    assert len(setup.terrain_areas) == 16
    assert len(setup.battlefield_regions) == 5


def test_phase17j_take_and_hold_layout_b_encodes_terrain_areas_and_regions() -> None:
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    assert len(layout.terrain_feature_placements) == 16
    assert len(setup.terrain_features) == 16
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
    assert len(layout.terrain_feature_placements) == 16
    assert len(setup.terrain_features) == 16
    assert len(direct_setup.terrain_features) == 16
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
    mission_pack = warhammer_event_companion_2026_07_mission_pack()
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
            "attacker-home": ("attacker_home", 17.25, 49.25),
            "defender-home": ("defender_home", 26.75, 10.75),
            "central-south": ("central", 17.7, 23.6),
            "central-north": ("central", 26.3, 36.4),
            "expansion-east": ("expansion", 37.65, 41.4),
            "expansion-west": ("expansion", 6.35, 18.6),
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
            "defender-home": ("defender_home", 37.55, 14.61),
            "central-north-west": ("central", 20.15, 34.65),
            "central-south-east": ("central", 23.85, 25.35),
            "expansion-north-east": ("expansion", 31.9, 50.9),
            "expansion-south-west": ("expansion", 12.1, 9.1),
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
    assert len(layout.terrain_feature_placements) == 16
    assert len(setup.terrain_features) == 16
    assert len(direct_setup.terrain_features) == 16
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
        event_source.PrimaryMissionScoringCoverageStatus.ENGINE_IMPLEMENTED: 4,
        event_source.PrimaryMissionScoringCoverageStatus.SOURCE_KNOWN_ENGINE_PENDING: 21,
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
    assert primary_rows["primary-meatgrinder"].scoring_kind == ("meatgrinder")
    assert primary_rows["primary-battlefield-dominance"].scoring_kind == (
        "event_companion_primary_source_known_engine_pending"
    )
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
    assert coverage_rows["primary-destroyers-wrath"].needed_work == (
        "engine_primary_condition:control_more_objectives_than_opponent",
    )
    assert coverage_rows["primary-punishment"].needed_work == (
        "engine_primary_start_turn_choice:condemned_enemy_units",
        "engine_primary_condition:condemned_enemy_units_left_battlefield",
        "engine_primary_condition:control_more_objectives_than_opponent",
        "engine_primary_condition:control_opponent_home_objective_end_of_battle",
    )
    assert coverage_rows["primary-inescapable-dominion"].needed_work == (
        "engine_primary_condition:control_three_or_more_objectives",
        "engine_primary_condition:control_two_or_more_objectives_from_battle_round_two",
        "engine_primary_condition:control_more_objectives_than_opponent",
        "engine_primary_condition:control_opponent_home_objective_end_of_battle",
    )
    assert coverage_rows["primary-vanguard-operation"].needed_work == (
        "engine_primary_action:vanguard-operation",
        "engine_primary_condition:friendly_unit_performed_vanguard_operation_this_turn",
        "engine_primary_condition:enemy_territory_terrain_area_control",
        "engine_primary_condition:control_opponent_home_objective_end_of_battle",
    )


def test_phase17j_primary_source_only_actions_are_not_exposed_as_runtime_actions() -> None:
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
        "engine_exposure_status": "source_known_engine_pending",
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
        "engine_exposure_status": "source_known_engine_pending",
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
        "engine_exposure_status": "source_known_engine_pending",
        "source_id": (
            "gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:surveil-enemy-unit"
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
        "source_id": ("gw-11e-warhammer-event-companion-v1-1-2026-07:primary-action:secure-asset"),
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
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-purge-the-foe-vs-disruption-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )

    with pytest.raises(
        GameLifecycleError,
        match="Primary mission scoring source is known but engine implementation is pending",
    ):
        mission_scoring_policy_from_setup(setup)


def test_phase17j_event_pack_resolves_scoring_and_tactical_draw_by_pack_id() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
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


def test_phase17j_end_of_battle_vp_is_exempt_from_round_five_primary_cap() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-take-and-hold-vs-purge-the-foe-layout-1",
        attacker_player_id="player-alpha",
        defender_player_id="player-beta",
    )
    policy = mission_scoring_policy_from_setup(setup)
    ledger = VictoryPointLedger.initial(player_id="player-alpha")
    round_five_award = VictoryPointAward(
        player_id="player-alpha",
        battle_round=5,
        phase="command",
        amount=15,
        source_kind=VictoryPointSourceKind.PRIMARY,
        source_id=setup.primary_mission_id,
        scoring_timing="phase_end",
        metadata={"scoring_rule_id": "phase17j-round-five-primary"},
    )
    applied_amount, metadata = policy.capped_award_for_ledger(
        ledger=ledger,
        award=round_five_award,
    )
    ledger, _ = ledger.award(
        round_five_award,
        applied_amount=applied_amount,
        metadata=metadata,
    )
    end_of_battle_award = VictoryPointAward(
        player_id="player-alpha",
        battle_round=5,
        phase="battle_end",
        amount=10,
        source_kind=VictoryPointSourceKind.PRIMARY,
        source_id=setup.primary_mission_id,
        scoring_timing="end_of_battle",
        metadata={"scoring_rule_id": "phase17j-end-of-battle-primary"},
    )

    applied_amount, _ = policy.capped_award_for_ledger(
        ledger=ledger,
        award=end_of_battle_award,
    )

    assert applied_amount == 10


def test_phase17j_final_scoring_uses_event_caps_battle_ready_and_draw_rules() -> None:
    mission_pack = mission_pack_for_id("11e-warhammer-event-companion-2026-07")
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
