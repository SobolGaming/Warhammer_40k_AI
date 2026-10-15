from __future__ import annotations

from typing import cast

from tests.shared.category_migration.phase11a_mission_pack import (
    PARAMETERIZED_DECISION_OPTION_ID,
    PHASE16A_BATTLEFIELD_LAYOUT_ID,
    PHASE16A_DEPLOYMENT_MAP_ID,
    PHASE16A_MISSION_POOL_ENTRY_ID,
    TYPED_TAKE_AND_HOLD_LAYOUT_C_ID,
    ArmyCatalog,
    ArmyDefinition,
    ArmyMusterRequest,
    BaseSizeDefinition,
    BattlefieldPlacementKind,
    BattlefieldRuntimeState,
    BattlePhase,
    DecisionController,
    DecisionRequest,
    DecisionResult,
    DetachmentSelection,
    FrozenInstanceError,
    GameConfig,
    GameLifecycleError,
    GameLifecycleStage,
    GameState,
    JsonValue,
    LifecycleStatus,
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionPackError,
    MissionSetup,
    MissionSetupError,
    MissionSetupPayload,
    MissionSourcePackageDefinition,
    MissionSourceStatus,
    ModelGeometry,
    ModelPlacement,
    ModelProfileSelection,
    MovementPhaseActionKind,
    MovementPhaseHandler,
    MovementPhaseState,
    MovementProposalRequest,
    PlacementProposalPayload,
    Pose,
    ReserveDestructionTimingPolicy,
    ReserveKind,
    ReservePlacementViolationCode,
    ReserveState,
    RulesetDescriptor,
    SecondaryMissionAvailability,
    TerrainDisplayGeometry,
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainWallDefinition,
    UnitInstance,
    UnitMusterSelection,
    UnitPlacement,
    VictoryPointSourceKind,
    _army_muster_request,
    _base_radius_inches,
    _battle_state_with_mission_setup,
    _battle_state_without_mission_setup,
    _blocking_terrain_feature,
    _config,
    _custom_layoutless_mission_setup,
    _custom_layoutless_state_and_battlefield,
    _decision_request,
    _display_geometry,
    _enemy_deployment_zone_center_pose,
    _enter_reinforcements_choice,
    _first_placement_pose,
    _mustered_armies,
    _objective_coordinate_snapshot,
    _reserve_unit,
    _ruleset,
    _single_model_reserve_placement,
    _single_model_unit,
    _south_edge_touching_pose,
    _submit_handler_decision,
    _submit_parameterized_handler_payload,
    _submit_reserve_ingress_action,
    _submit_reserve_placement_payload,
    _violation_codes,
    _with_single_model_reserve_unit,
    chapter_approved_2026_27_mission_pack,
    create_deterministic_battlefield_scenario,
    event_layouts,
    json,
    mission_pack_for_id,
    mission_scoring_policies_from_setup,
    mission_source_status_from_token,
    muster_army,
    project_battlefield_view,
    pytest,
    replace,
    source_data,
    supported_mission_packs,
    validate_json_value,
    validate_mission_setup_source_layout,
    warhammer_event_companion_2026_07_mission_pack,
)


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
        ("reconnaissance", "disruption"),
        ("disruption", "reconnaissance"),
    ],
)
def test_mission_scoring_policies_support_both_disruption_reconnaissance_primaries(
    attacker_force_disposition_id: str,
    defender_force_disposition_id: str,
) -> None:
    setup = MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-disruption-vs-reconnaissance-layout-1",
        attacker_player_id="player-a",
        attacker_force_disposition_id=attacker_force_disposition_id,
        defender_player_id="player-b",
        defender_force_disposition_id=defender_force_disposition_id,
    )

    policies = mission_scoring_policies_from_setup(setup)
    mission_ids = {
        policy.primary_mission_id
        for policy in policies.player_policies
        if policy.primary_scoring_supported
    }

    assert mission_ids == {"primary-smoke-and-mirrors", "primary-surveil-the-foe"}
    for policy in policies.player_policies:
        assert (
            policy.cap_bucket_for_victory_point_source(
                source_kind=VictoryPointSourceKind.PRIMARY,
                source_id=policy.primary_mission_id,
            ).value
            == "primary"
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
        _submit_reserve_ingress_action(
            handler=handler,
            state=state,
            decisions=decisions,
            selection_request=selection_request,
            unit_instance_id=reserve_state.unit_instance_id,
            result_id_prefix="phase11a-missing-setup",
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
        _submit_reserve_ingress_action(
            handler=handler,
            state=state,
            decisions=decisions,
            selection_request=selection_request,
            unit_instance_id=reserve_state.unit_instance_id,
            result_id_prefix="phase11a-reserve",
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


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["BattlePhase", "DecisionController", "DecisionRequest", "DecisionResult"]
__all__ += ["DetachmentSelection", "GameLifecycleStage", "JsonValue", "LifecycleStatus"]
__all__ += ["MissionSetupPayload", "ModelGeometry", "ModelPlacement", "ModelProfileSelection"]
__all__ += ["MovementPhaseActionKind", "MovementPhaseHandler", "MovementPhaseState"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "MovementProposalRequest"]
__all__ += ["PlacementProposalPayload", "Pose", "ReserveDestructionTimingPolicy", "ReserveKind"]
__all__ += ["ReserveState", "RulesetDescriptor", "SecondaryMissionAvailability"]
__all__ += ["TerrainDisplayGeometry", "TerrainFeatureDefinition", "TerrainFeatureKind"]
__all__ += ["TerrainWallDefinition", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["_army_muster_request", "_base_radius_inches", "_custom_layoutless_mission_setup"]
__all__ += ["_display_geometry", "_first_placement_pose", "_mustered_armies"]
__all__ += ["_objective_coordinate_snapshot", "_ruleset", "_single_model_unit"]
__all__ += ["_south_edge_touching_pose", "_submit_handler_decision"]
__all__ += ["_submit_parameterized_handler_payload", "_with_single_model_reserve_unit"]
__all__ += ["create_deterministic_battlefield_scenario", "event_layouts"]
__all__ += ["project_battlefield_view", "validate_json_value"]
