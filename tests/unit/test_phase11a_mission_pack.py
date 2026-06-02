from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.missions import (
    MissionPackDefinition,
    MissionPackDefinitionPayload,
    MissionSourcePackageDefinition,
)
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor, TerrainFeatureKind
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest, muster_army
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.mission_setup import (
    MissionSetup,
    MissionSetupError,
    instantiate_terrain_layout_template,
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
from warhammer40k_core.engine.unit_factory import UnitInstance
from warhammer40k_core.geometry.model_geometry import ModelGeometry
from warhammer40k_core.geometry.terrain import TerrainFeatureDefinition, TerrainWallDefinition
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chapter_approved_2025_26 as source_data,
)


def test_chapter_approved_mission_pack_round_trips_without_object_reprs() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()

    payload = mission_pack.to_payload()
    encoded = json.dumps(payload, sort_keys=True)
    decoded = cast(MissionPackDefinitionPayload, json.loads(encoded))

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionPackDefinition.from_payload(decoded).to_payload() == payload
    assert mission_pack.sequence.steps[0] == "muster_armies"
    assert len(mission_pack.mission_pool_entries) == 20
    assert len(mission_pack.secondary_missions) == 19
    assert len(mission_pack.challenger_cards) == 9


def test_chapter_approved_source_package_payload_and_identity_snapshot() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    source_package = mission_pack.source_package

    payload = source_package.to_payload()
    encoded = json.dumps(payload, sort_keys=True)

    assert "<" not in encoded
    assert "object at 0x" not in encoded
    assert MissionSourcePackageDefinition.from_payload(payload).to_payload() == payload
    assert payload == {
        "edition_id": "warhammer_40000_11th",
        "mission_pack_id": "11e-chapter-approved-2025-26",
        "source_package_id": "gw-11e-chapter-approved-2025-26",
        "source_title": "Warhammer 40,000 11th Edition Chapter Approved 2025-26",
        "source_version": "2025-26",
        "source_commit_or_import_hash": source_package.source_commit_or_import_hash,
        "imported_at_schema_version": "core-v2-mission-source-v1",
    }
    assert len(source_package.source_commit_or_import_hash) == 64
    assert mission_pack.mission_pack_id == "11e-chapter-approved-2025-26"


def test_chapter_approved_11th_edition_scoring_action_source_snapshot() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    take_and_hold = next(
        mission
        for mission in mission_pack.primary_missions
        if mission.primary_mission_id == "take-and-hold"
    )
    cleanse = mission_pack.secondary_mission("cleanse")
    cleanse_action = mission_pack.mission_action("cleanse-objective")

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
            "gw-11e-chapter-approved-2025-26:primary:take-and-hold:"
            "scoring-rule:take-and-hold-control"
        ),
    }
    assert {(rule.source_kind, rule.victory_points) for rule in cleanse.scoring_rules} >= {
        ("fixed_secondary", 4),
        ("tactical_secondary", 5),
    }
    assert cleanse_action.start_phase == "shooting"
    assert cleanse_action.target_policy == "objective_marker"
    assert "unit_left_battlefield" in cleanse_action.interruption_conditions
    assert cleanse_action.victory_points == 5
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


def test_deployment_map_and_objective_marker_policy_round_trip() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    deployment_map = mission_pack.deployment_map("tipping-point")
    payload = deployment_map.to_payload()
    round_tripped = type(deployment_map).from_payload(payload)

    assert round_tripped.to_payload() == payload
    assert all(marker.measurement_anchor == "center" for marker in deployment_map.objective_markers)
    assert all(marker.marker_diameter_mm == 40.0 for marker in deployment_map.objective_markers)
    assert all(marker.is_flat for marker in deployment_map.objective_markers)
    assert not any(marker.blocks_movement for marker in deployment_map.objective_markers)
    assert not any(marker.blocks_placement for marker in deployment_map.objective_markers)


def test_deployment_map_objective_marker_coordinates_match_source_snapshot() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()

    assert _objective_coordinate_snapshot(mission_pack) == {
        "crucible-of-battle": {
            "center": (30.0, 22.0),
            "northeast": (46.0, 10.0),
            "northwest": (20.0, 8.0),
            "southeast": (40.0, 36.0),
            "southwest": (14.0, 34.0),
        },
        "dawn-of-war": {
            "center": (30.0, 22.0),
            "east": (50.0, 22.0),
            "north": (30.0, 6.0),
            "south": (30.0, 38.0),
            "west": (10.0, 22.0),
        },
        "hammer-and-anvil": {
            "center": (30.0, 22.0),
            "east": (50.0, 22.0),
            "north": (30.0, 6.0),
            "south": (30.0, 38.0),
            "west": (10.0, 22.0),
        },
        "search-and-destroy": {
            "center": (30.0, 22.0),
            "northeast": (46.0, 10.0),
            "northwest": (14.0, 10.0),
            "southeast": (46.0, 34.0),
            "southwest": (14.0, 34.0),
        },
        "sweeping-engagement": {
            "center": (30.0, 22.0),
            "northeast": (42.0, 6.0),
            "northwest": (10.0, 18.0),
            "southeast": (50.0, 26.0),
            "southwest": (18.0, 38.0),
        },
        "tipping-point": {
            "center": (30.0, 22.0),
            "northeast": (46.0, 10.0),
            "northwest": (22.0, 8.0),
            "southeast": (38.0, 36.0),
            "southwest": (14.0, 34.0),
        },
    }


def test_terrain_layout_template_instantiates_deterministic_features() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    template = mission_pack.terrain_layout_template("layout-1")

    first = instantiate_terrain_layout_template(template)
    second = instantiate_terrain_layout_template(type(template).from_payload(template.to_payload()))

    assert [feature.to_payload() for feature in first] == [
        feature.to_payload() for feature in second
    ]
    assert {feature.feature_kind for feature in first} == {TerrainFeatureKind.RUINS}
    assert len(first) == 12
    assert first[0].source_id is not None


def test_terrain_layout_templates_match_source_slot_snapshot() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()

    assert _terrain_slot_source_snapshot(mission_pack) == _EXPECTED_TERRAIN_SLOT_SNAPSHOT


def test_mission_pool_selection_is_deterministic() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()

    first_order = mission_pack.deterministic_mission_pool_order(seed="event-round-1")
    second_order = mission_pack.deterministic_mission_pool_order(seed="event-round-1")
    alternate_order = mission_pack.deterministic_mission_pool_order(seed="event-round-2")

    assert tuple(entry.mission_pool_entry_id for entry in first_order) == tuple(
        entry.mission_pool_entry_id for entry in second_order
    )
    assert tuple(entry.mission_pool_entry_id for entry in first_order) != tuple(
        entry.mission_pool_entry_id for entry in alternate_order
    )


def test_mission_setup_from_components_rejects_source_inconsistent_components() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    deployment_map = mission_pack.deployment_map("tipping-point")
    terrain_layout = mission_pack.terrain_layout_template("layout-1")

    with pytest.raises(MissionSetupError, match="Primary mission is not present"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            primary_mission_id="not-a-primary",
            deployment_map=deployment_map,
            terrain_layout=terrain_layout,
            attacker_player_id="player-a",
            defender_player_id="player-b",
        )

    with pytest.raises(MissionSetupError, match="Deployment map is not present"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            primary_mission_id="take-and-hold",
            deployment_map=replace(deployment_map, deployment_map_id="foreign-map"),
            terrain_layout=terrain_layout,
            attacker_player_id="player-a",
            defender_player_id="player-b",
        )

    with pytest.raises(MissionSetupError, match="Terrain layout is not present"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            primary_mission_id="take-and-hold",
            deployment_map=deployment_map,
            terrain_layout=replace(terrain_layout, terrain_layout_id="layout-99"),
            attacker_player_id="player-a",
            defender_player_id="player-b",
        )


def test_mission_setup_from_components_rejects_illegal_pool_combination() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()

    with pytest.raises(MissionSetupError, match="not a legal Chapter Approved mission pool row"):
        MissionSetup.from_components(
            mission_pack=mission_pack,
            primary_mission_id="take-and-hold",
            deployment_map=mission_pack.deployment_map("hammer-and-anvil"),
            terrain_layout=mission_pack.terrain_layout_template("layout-2"),
            attacker_player_id="player-a",
            defender_player_id="player-b",
        )


def test_mission_setup_payload_preserves_mission_pool_entry_id() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    setup = MissionSetup.from_components(
        mission_pack=mission_pack,
        primary_mission_id="take-and-hold",
        deployment_map=mission_pack.deployment_map("tipping-point"),
        terrain_layout=mission_pack.terrain_layout_template("layout-1"),
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )

    assert setup.mission_pool_entry_id == "mission-a"
    assert MissionSetup.from_payload(setup.to_payload()).to_payload() == setup.to_payload()


def test_mission_setup_from_payload_rejects_out_of_bounds_terrain() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    setup = MissionSetup.from_mission_pack(
        mission_pack=mission_pack,
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    payload = setup.to_payload()
    payload["terrain_features"][0]["footprint_width_inches"] = 1000.0

    with pytest.raises(MissionSetupError, match="terrain feature x is outside"):
        MissionSetup.from_payload(payload)


def test_game_state_round_trips_populated_mission_setup() -> None:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )
    state = GameState.from_config(_config(mission_setup=mission_setup))

    assert GameState.from_payload(state.to_payload()).to_payload() == state.to_payload()


def test_hidden_secondary_and_challenger_cards_do_not_leak_to_opponent_payload() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
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
    placement_request = _decision_request(
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=selection_request,
            option_id=reserve_state.unit_instance_id,
            result_id="phase11a-select-missing-setup",
        )
    )

    with pytest.raises(GameLifecycleError, match="Live Reinforcements requires MissionSetup"):
        _submit_handler_decision(
            handler=handler,
            state=state,
            decisions=decisions,
            request=placement_request,
            option_id=BattlefieldPlacementKind.STRATEGIC_RESERVES.value,
            result_id="phase11a-place-missing-setup",
        )


def test_live_reinforcements_use_mission_deployment_zones_for_round_2_restriction() -> None:
    state, reserve_state = _battle_state_with_mission_setup(
        attacker_player_id="player-b",
        defender_player_id="player-a",
        mission_pool_entry_id="mission-s",
        terrain_layout_id="layout-5",
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

    invalid_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        option_id=BattlefieldPlacementKind.STRATEGIC_RESERVES.value,
        result_id="phase11a-place-reserve",
    )

    assert invalid_status is not None
    assert (
        ReservePlacementViolationCode.STRATEGIC_RESERVES_ENEMY_DEPLOYMENT_ZONE.value
        in _violation_codes(invalid_status)
    )


def test_live_reinforcements_use_instantiated_mission_terrain_for_endpoint_validation() -> None:
    state, reserve_state = _battle_state_with_mission_setup(
        attacker_player_id="player-a",
        defender_player_id="player-b",
        mission_pool_entry_id="mission-s",
        terrain_layout_id="layout-5",
        reserve_base_diameter_mm=200.0,
    )
    handler, decisions, selection_request = _enter_reinforcements_choice(
        state=state,
        battle_round=3,
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
    pose = _strategic_reserves_option_pose(placement_request)
    assert state.mission_setup is not None
    state.mission_setup = replace(
        state.mission_setup,
        terrain_features=(
            _blocking_terrain_feature(
                x=pose["x"],
                y=pose["y"],
            ),
        ),
    )

    invalid_status = _submit_handler_decision(
        handler=handler,
        state=state,
        decisions=decisions,
        request=placement_request,
        option_id=BattlefieldPlacementKind.STRATEGIC_RESERVES.value,
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
    mission_pool_entry_id: str = "mission-a",
    terrain_layout_id: str = "layout-1",
    reserve_base_diameter_mm: float = 32.0,
) -> tuple[GameState, ReserveState]:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id=mission_pool_entry_id,
        terrain_layout_id=terrain_layout_id,
        attacker_player_id=attacker_player_id,
        defender_player_id=defender_player_id,
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


def _decision_request(status: LifecycleStatus | None) -> DecisionRequest:
    assert status is not None
    assert status.decision_request is not None
    return status.decision_request


def _strategic_reserves_option_pose(request: DecisionRequest) -> dict[str, float]:
    payload = request.option_by_id(BattlefieldPlacementKind.STRATEGIC_RESERVES.value).payload
    assert isinstance(payload, dict)
    attempted = payload["attempted_placement"]
    assert isinstance(attempted, dict)
    placements = attempted["model_placements"]
    assert isinstance(placements, list)
    first = placements[0]
    assert isinstance(first, dict)
    pose = first["pose"]
    assert isinstance(pose, dict)
    position = pose["position"]
    assert isinstance(position, dict)
    x = position["x"]
    y = position["y"]
    assert isinstance(x, int | float)
    assert isinstance(y, int | float)
    return {"x": float(x), "y": float(y)}


def _blocking_terrain_feature(*, x: float, y: float) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="phase11a-live-blocking-terrain",
        feature_kind=TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        footprint_center_x_inches=x,
        footprint_center_y_inches=y,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
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


def _terrain_slot_source_snapshot(
    mission_pack: MissionPackDefinition,
) -> dict[str, tuple[str, ...]]:
    snapshot: dict[str, tuple[str, ...]] = {}
    for template in mission_pack.terrain_layout_templates:
        entries: list[str] = []
        for feature in sorted(template.terrain_features, key=lambda item: item.feature_id):
            source_id = feature.source_id
            assert source_id is not None
            prefix, origin = source_id.rsplit(":origin-", maxsplit=1)
            origin_x, origin_y = origin.split("-", maxsplit=1)
            _layout_source, preset, rotation = prefix.rsplit(":", maxsplit=2)
            entries.append(f"{preset}|{rotation.removeprefix('rotation-')}|{origin_x}|{origin_y}")
        snapshot[template.terrain_layout_id] = tuple(entries)
    return snapshot


_EXPECTED_TERRAIN_SLOT_SNAPSHOT: dict[str, tuple[str, ...]] = {
    "layout-1": (
        "ruin_rect_12x6_variant1|90.000000|22.000|28.000",
        "ruin_rect_12x6_variant1|270.000000|38.000|16.000",
        "ruin_rect_12x6_variant2|270.000000|6.000|17.000",
        "ruin_rect_12x6_variant2|90.000000|54.000|27.000",
        "ruin_rect_6x4_variant1|90.000000|32.000|0.000",
        "ruin_rect_6x4_variant1|270.000000|28.000|44.000",
        "ruin_rect_12x6_variant5|0.000000|4.000|22.000",
        "ruin_rect_12x6_variant5|180.000000|56.000|22.000",
        "ruin_rect_6x4_variant1|135.000000|26.600|20.600",
        "ruin_rect_6x4_variant1|315.000000|33.400|23.400",
        "ruin_rect_10x5_variant3|45.000000|23.000|10.000",
        "ruin_rect_10x5_variant3|225.000000|37.000|34.000",
    ),
    "layout-2": (
        "ruin_rect_12x6_variant1|41.633539|17.000|15.500",
        "ruin_rect_12x6_variant1|221.633539|43.000|28.500",
        "ruin_rect_12x6_variant2|270.000000|8.000|40.000",
        "ruin_rect_12x6_variant2|90.000000|52.000|4.000",
        "ruin_rect_12x6_variant4|270.000000|5.000|16.000",
        "ruin_rect_12x6_variant4|90.000000|55.000|28.000",
        "ruin_rect_10x5_variant1|0.000000|20.000|4.000",
        "ruin_rect_10x5_variant1|180.000000|40.000|40.000",
        "ruin_rect_6x4_variant1|0.000000|30.000|9.000",
        "ruin_rect_6x4_variant1|180.000000|30.000|35.000",
        "ruin_rect_6x4_variant1|0.000000|52.000|16.000",
        "ruin_rect_6x4_variant1|180.000000|8.000|28.000",
    ),
    "layout-3": (
        "ruin_rect_12x6_variant1|180.000000|34.000|10.000",
        "ruin_rect_12x6_variant1|0.000000|26.000|34.000",
        "ruin_rect_12x6_variant3|209.981639|14.200|38.000",
        "ruin_rect_12x6_variant3|29.981639|45.800|6.000",
        "ruin_rect_12x6_variant4|311.633539|2.000|19.000",
        "ruin_rect_12x6_variant4|131.633539|58.000|25.000",
        "ruin_rect_10x5_variant3|52.431408|21.000|14.000",
        "ruin_rect_10x5_variant3|232.431408|39.000|30.000",
        "ruin_rect_6x4_variant1|0.000000|10.000|4.000",
        "ruin_rect_6x4_variant1|180.000000|50.000|40.000",
        "ruin_rect_6x4_variant1|232.431408|22.800|31.000",
        "ruin_rect_6x4_variant1|52.431408|37.200|13.000",
    ),
    "layout-4": (
        "ruin_rect_12x6_variant1|41.633539|8.000|27.500",
        "ruin_rect_12x6_variant1|221.633539|52.000|16.500",
        "ruin_rect_12x6_variant2|0.000000|12.000|4.000",
        "ruin_rect_12x6_variant2|180.000000|48.000|40.000",
        "ruin_rect_12x6_variant4|53.615648|35.000|2.500",
        "ruin_rect_12x6_variant4|233.615648|25.000|41.500",
        "ruin_rect_10x5_variant2|229.028264|21.000|27.000",
        "ruin_rect_10x5_variant2|49.028264|39.000|17.000",
        "ruin_rect_6x4_variant1|90.000000|8.000|19.000",
        "ruin_rect_6x4_variant1|270.000000|52.000|25.000",
        "ruin_rect_6x4_variant1|90.000000|12.000|10.000",
        "ruin_rect_6x4_variant1|270.000000|48.000|34.000",
    ),
    "layout-5": (
        "ruin_rect_12x6_variant1|180.000000|36.000|10.000",
        "ruin_rect_12x6_variant1|0.000000|24.000|34.000",
        "ruin_rect_12x6_variant2|-24.443955|5.000|16.000",
        "ruin_rect_12x6_variant2|155.556045|55.000|28.000",
        "ruin_rect_12x6_variant4|29.981639|46.500|2.000",
        "ruin_rect_12x6_variant4|209.981639|13.500|42.000",
        "ruin_rect_10x5_variant3|0.000000|16.000|24.000",
        "ruin_rect_10x5_variant3|180.000000|44.000|20.000",
        "ruin_rect_6x4_variant1|0.000000|12.000|4.000",
        "ruin_rect_6x4_variant1|180.000000|48.000|40.000",
        "ruin_rect_6x4_variant1|0.000000|0.000|24.000",
        "ruin_rect_6x4_variant1|180.000000|60.000|20.000",
    ),
    "layout-6": (
        "ruin_rect_12x6_variant1|48.366461|8.500|27.000",
        "ruin_rect_12x6_variant1|228.366461|51.500|17.000",
        "ruin_rect_12x6_variant2|270.000000|20.000|40.000",
        "ruin_rect_12x6_variant2|90.000000|40.000|4.000",
        "ruin_rect_12x6_variant4|0.000000|10.000|4.000",
        "ruin_rect_12x6_variant4|180.000000|50.000|40.000",
        "ruin_rect_10x5_variant2|48.270488|40.400|18.600",
        "ruin_rect_10x5_variant2|228.270488|19.600|25.400",
        "ruin_rect_6x4_variant1|0.000000|24.000|12.000",
        "ruin_rect_6x4_variant1|180.000000|36.000|32.000",
        "ruin_rect_6x4_variant1|90.000000|10.000|10.000",
        "ruin_rect_6x4_variant1|270.000000|50.000|34.000",
    ),
    "layout-7": (
        "ruin_rect_12x6_variant1|90.000000|29.000|3.000",
        "ruin_rect_12x6_variant1|270.000000|31.000|41.000",
        "ruin_rect_6x4_variant1|0.000000|48.000|0.000",
        "ruin_rect_6x4_variant1|180.000000|12.000|44.000",
        "ruin_rect_12x6_variant5|90.000000|12.000|28.000",
        "ruin_rect_12x6_variant5|270.000000|48.000|16.000",
        "ruin_rect_10x5_variant3|270.000000|37.000|18.000",
        "ruin_rect_10x5_variant3|90.000000|23.000|26.000",
        "ruin_rect_6x4_variant2|90.000000|23.000|20.000",
        "ruin_rect_6x4_variant2|270.000000|37.000|24.000",
        "ruin_rect_12x6_variant6|90.000000|14.000|8.000",
        "ruin_rect_12x6_variant6|270.000000|46.000|36.000",
    ),
    "layout-8": (
        "ruin_rect_12x6_variant1|90.000000|28.000|0.000",
        "ruin_rect_12x6_variant1|270.000000|32.000|44.000",
        "ruin_rect_12x6_variant3|221.633539|15.000|40.000",
        "ruin_rect_12x6_variant3|41.633539|45.000|4.000",
        "ruin_rect_6x4_variant1|90.000000|37.000|10.000",
        "ruin_rect_6x4_variant1|90.000000|37.000|16.000",
        "ruin_rect_6x4_variant1|270.000000|23.000|34.000",
        "ruin_rect_6x4_variant1|270.000000|23.000|28.000",
        "ruin_rect_12x6_variant5|90.000000|19.000|13.000",
        "ruin_rect_12x6_variant5|270.000000|41.000|31.000",
        "ruin_rect_10x5_variant2|323.130102|4.000|10.000",
        "ruin_rect_10x5_variant2|143.130102|56.000|34.000",
    ),
}


def _config(*, mission_setup: MissionSetup | None) -> GameConfig:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return GameConfig(
        game_id="phase11a-game",
        ruleset_descriptor=_ruleset(),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_ids=("intercessor-unit-1", "intercessor-unit-2"),
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_ids=("intercessor-unit-3",),
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=("assassination", "bring_it_down", "cleanse"),
        mission_setup=mission_setup,
    )


def _ruleset() -> RulesetDescriptor:
    return RulesetDescriptor.warhammer_40000_eleventh_chapter_approved_2025_26(
        descriptor_version="core-v2-phase11a-test"
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_ids: tuple[str, ...],
) -> ArmyMusterRequest:
    return ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=DetachmentSelection(
            faction_id="core-marine-force",
            detachment_id="core-combined-arms",
        ),
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
