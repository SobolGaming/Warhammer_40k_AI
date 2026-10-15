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
        "resolution_mode": "independent",
        "resolution_group_id": None,
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
            "resolution_mode": "independent",
            "resolution_group_id": None,
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
            "resolution_mode": "independent",
            "resolution_group_id": None,
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
            "resolution_mode": "independent",
            "resolution_group_id": None,
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
    assert {rule.rule_id for rule in assassination.scoring_rules} == {
        "assassination-fixed-character-destroyed",
        "assassination-fixed-character-w4-plus",
        "assassination-tactical-all-characters-destroyed",
        "assassination-tactical-character-destroyed",
    }
    assert cleanse.availability is SecondaryMissionAvailability.TACTICAL
    assert cleanse.tournament_fixed_allowed is False
    assert {rule.rule_id for rule in cleanse.scoring_rules} == {
        "cleanse-when-drawn-plunder-active",
        "cleanse-tactical-one-objective",
        "cleanse-tactical-two-objectives",
    }
    assert {rule.rule_id: rule.victory_points for rule in cleanse.scoring_rules} == {
        "cleanse-when-drawn-plunder-active": None,
        "cleanse-tactical-one-objective": 2,
        "cleanse-tactical-two-objectives": 5,
    }
    assert {rule.rule_id for rule in plunder.scoring_rules} == {
        "plunder-when-drawn-cleanse-active",
        "plunder-tactical",
    }
    defend_stronghold = mission_pack.secondary_mission("defend-stronghold")
    assert {rule.rule_id: rule.condition for rule in defend_stronghold.scoring_rules} == {
        "defend-stronghold-when-drawn-first-round": (
            "first_battle_round_must_shuffle_card_back_and_draw_one"
        ),
        "defend-stronghold-home-objective": "control_home_objective",
        "defend-stronghold-no-enemy-in-deployment-zone": (
            "no_enemy_units_within_own_deployment_zone"
        ),
    }
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
            "resolution_mode": "independent",
            "resolution_group_id": None,
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
            "resolution_mode": "independent",
            "resolution_group_id": None,
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
            "resolution_mode": "independent",
            "resolution_group_id": None,
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
        _submit_reserve_ingress_action(
            handler=handler,
            state=state,
            decisions=decisions,
            selection_request=selection_request,
            unit_instance_id=reserve_state.unit_instance_id,
            result_id_prefix="phase11a-terrain",
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


__all__: list[str] = []
__all__ += ["ArmyCatalog", "ArmyDefinition", "ArmyMusterRequest", "BaseSizeDefinition"]
__all__ += ["BattlePhase", "DecisionController", "DecisionRequest", "DecisionResult"]
__all__ += ["DetachmentSelection", "FrozenInstanceError", "GameLifecycleStage", "JsonValue"]
__all__ += ["LifecycleStatus", "MissionPackDefinition", "MissionPackDefinitionPayload"]
__all__ += ["MissionSourceStatus", "ModelGeometry", "ModelPlacement", "ModelProfileSelection"]
__all__ += ["MovementPhaseActionKind", "MovementPhaseHandler", "MovementPhaseState"]
__all__ += ["PARAMETERIZED_DECISION_OPTION_ID", "MovementProposalRequest"]
__all__ += ["PlacementProposalPayload", "Pose", "ReserveDestructionTimingPolicy", "ReserveKind"]
__all__ += ["TYPED_TAKE_AND_HOLD_LAYOUT_C_ID", "ReserveState", "RulesetDescriptor"]
__all__ += ["TerrainDisplayGeometry", "TerrainFeatureDefinition", "TerrainFeatureKind"]
__all__ += ["TerrainWallDefinition", "UnitInstance", "UnitMusterSelection", "UnitPlacement"]
__all__ += ["VictoryPointSourceKind", "_army_muster_request", "_base_radius_inches"]
__all__ += ["_battle_state_without_mission_setup", "_custom_layoutless_mission_setup"]
__all__ += ["_custom_layoutless_state_and_battlefield", "_display_geometry"]
__all__ += ["_enemy_deployment_zone_center_pose", "_ruleset", "_single_model_unit"]
__all__ += ["_submit_handler_decision", "_submit_parameterized_handler_payload"]
__all__ += ["_with_single_model_reserve_unit", "mission_pack_for_id"]
__all__ += ["mission_scoring_policies_from_setup", "mission_source_status_from_token"]
__all__ += ["muster_army", "source_data", "supported_mission_packs", "validate_json_value"]
__all__ += ["validate_mission_setup_source_layout"]
