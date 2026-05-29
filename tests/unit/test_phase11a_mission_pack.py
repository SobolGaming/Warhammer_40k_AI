from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.missions import MissionPackDefinition, MissionPackDefinitionPayload
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
    instantiate_terrain_layout_template,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleStage, LifecycleStatus
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
from warhammer40k_core.rules.mission_pack_import import chapter_approved_2025_26_mission_pack


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


def test_terrain_layout_template_instantiates_deterministic_features() -> None:
    mission_pack = chapter_approved_2025_26_mission_pack()
    template = mission_pack.terrain_layout_template("layout-1")

    first = instantiate_terrain_layout_template(template)
    second = instantiate_terrain_layout_template(type(template).from_payload(template.to_payload()))

    assert [feature.to_payload() for feature in first] == [
        feature.to_payload() for feature in second
    ]
    assert {feature.feature_kind for feature in first} == {
        TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        TerrainFeatureKind.RUINS,
    }
    assert first[0].source_id is not None


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


def test_live_reinforcements_use_mission_deployment_zones_for_round_2_restriction() -> None:
    state, reserve_state = _battle_state_with_mission_setup(
        attacker_player_id="player-b",
        defender_player_id="player-a",
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
) -> tuple[GameState, ReserveState]:
    mission_setup = MissionSetup.from_mission_pack(
        mission_pack=chapter_approved_2025_26_mission_pack(),
        mission_pool_entry_id="mission-a",
        terrain_layout_id="layout-1",
        attacker_player_id=attacker_player_id,
        defender_player_id=defender_player_id,
    )
    config = _config(mission_setup=mission_setup)
    armies = _mustered_armies(config)
    armies = _with_single_model_reserve_unit(armies)
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


def _config(*, mission_setup: MissionSetup) -> GameConfig:
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
    return RulesetDescriptor.warhammer_40000_tenth_chapter_approved_2025_26(
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
) -> tuple[ArmyDefinition, ...]:
    updated_armies: list[ArmyDefinition] = []
    for army in armies:
        if army.army_id != "army-alpha":
            updated_armies.append(army)
            continue
        reserve_unit = army.unit_by_id("army-alpha:intercessor-unit-1")
        updated_unit = _single_model_unit(reserve_unit)
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


def _single_model_unit(unit: UnitInstance) -> UnitInstance:
    base_size = BaseSizeDefinition.circular(32.0)
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
