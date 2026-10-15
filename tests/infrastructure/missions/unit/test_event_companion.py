from __future__ import annotations

from typing import Any, cast

from tests.shared.category_migration.phase17j_event_companion import (
    BattlefieldLayoutDefinition,
    BenefitOfCoverResult,
    Callable,
    CircularBase,
    Counter,
    CoverSourceReason,
    DeploymentZonePoint,
    DeploymentZonePolygon,
    DeploymentZoneShape,
    FinalScoringResult,
    GameLifecycleError,
    LineOfSightPolicy,
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSetup,
    MissionSetupError,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    Model,
    ModelVolume,
    ObjectiveMarkerDefinitionPayload,
    ObjectiveMarkerRole,
    Path,
    Pose,
    RulesetDescriptor,
    ScoringWindowKind,
    ScoringWindowState,
    TerrainAreaClassification,
    TerrainAreaCoverSourceRecord,
    TerrainAreaLocalTransform,
    TerrainDisplayPoint,
    TerrainVisibilityContext,
    VictoryPointAward,
    VictoryPointLedger,
    VictoryPointSourceKind,
    VisibilityBlockerKind,
    _event_final_scoring_windows,
    _layout_descriptor,
    _meatgrinder_artifact_layouts,
    _shape_polygons,
    _source_base_source_kind_and_geometry,
    _source_deployment_zone_layout_edges,
    _source_deployment_zone_layout_template_id,
    _source_deployment_zone_layout_template_id_from_number,
    _source_deployment_zone_template_base_shape,
    _source_layout_number_from_layout_id,
    _source_matrix_row,
    _source_rectangle_with_quarter_circle_cutout_vertices,
    _terrain_display_points,
    deterministic_tactical_secondary_draw,
    event_companion_base_size_rows,
    event_companion_patches,
    event_layouts,
    event_no_mans_land_shape,
    event_primary_scoring,
    event_source,
    event_territory_vertices,
    hashlib,
    importlib,
    json,
    july_rules_updates_2026_07,
    math,
    mission_action_policies,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    model_within_solid_terrain,
    msgspec,
    objective_marker_role_from_token,
    pairwise,
    permutations,
    polygon_overlap_area,
    pytest,
    replace,
    shapely_backend,
    subprocess,
    sys,
    terrain_area_classifications_by_suffix,
    terrain_area_visibility,
    terrain_feature_placements_from_specs,
    terrain_visibility_areas_from_placements,
    validate_mission_setup_source_layout,
    visibility_polygon_within_union,
    warhammer_event_companion_2026_07_mission_pack,
)
from tests.shared.repository_root import REPOSITORY_ROOT


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


def test_phase17n_primary_scoring_artifact_is_source_hashed_strict_and_consumed() -> None:
    artifact = event_primary_scoring.event_companion_primary_scoring_artifact()
    repository_root = REPOSITORY_ROOT
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
    repository_root = REPOSITORY_ROOT
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


def test_phase17n_ruin_wall_joints_follow_source_image_registration() -> None:
    repository_root = REPOSITORY_ROOT
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


__all__: list[str] = []
__all__ += ["Any", "BattlefieldLayoutDefinition", "BenefitOfCoverResult", "Callable"]
__all__ += ["CircularBase", "CoverSourceReason", "DeploymentZonePoint", "DeploymentZonePolygon"]
__all__ += ["DeploymentZoneShape", "FinalScoringResult", "GameLifecycleError"]
__all__ += ["LineOfSightPolicy", "MissionSetupError", "Model", "ModelVolume"]
__all__ += ["ObjectiveMarkerDefinitionPayload", "ObjectiveMarkerRole", "Path", "Pose"]
__all__ += ["RulesetDescriptor", "ScoringWindowKind", "ScoringWindowState"]
__all__ += ["TerrainAreaClassification", "TerrainAreaCoverSourceRecord"]
__all__ += ["TerrainAreaLocalTransform", "TerrainDisplayPoint", "TerrainVisibilityContext"]
__all__ += ["VictoryPointAward", "VictoryPointLedger", "VictoryPointSourceKind"]
__all__ += ["VisibilityBlockerKind", "_event_final_scoring_windows", "_layout_descriptor"]
__all__ += ["_shape_polygons", "_source_base_source_kind_and_geometry"]
__all__ += ["_source_deployment_zone_layout_edges", "_source_deployment_zone_layout_template_id"]
__all__ += ["_source_deployment_zone_layout_template_id_from_number"]
__all__ += ["_source_deployment_zone_template_base_shape", "_source_layout_number_from_layout_id"]
__all__ += ["_source_matrix_row", "_source_rectangle_with_quarter_circle_cutout_vertices"]
__all__ += ["_terrain_display_points", "deterministic_tactical_secondary_draw"]
__all__ += ["event_companion_base_size_rows", "event_companion_patches"]
__all__ += ["event_no_mans_land_shape", "event_territory_vertices", "importlib"]
__all__ += ["july_rules_updates_2026_07", "mission_action_policies", "mission_pack_for_id"]
__all__ += ["mission_scoring_policies_from_setup", "model_within_solid_terrain"]
__all__ += ["objective_marker_role_from_token", "pairwise", "permutations"]
__all__ += ["polygon_overlap_area", "subprocess", "sys", "terrain_area_classifications_by_suffix"]
__all__ += ["terrain_area_visibility", "terrain_feature_placements_from_specs"]
__all__ += ["terrain_visibility_areas_from_placements", "validate_mission_setup_source_layout"]
__all__ += ["visibility_polygon_within_union"]
