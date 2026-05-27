from __future__ import annotations

import json
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.army_mustering import ArmyDefinition, ArmyMusterRequest
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldRuntimeState,
    BattlefieldRuntimeStatePayload,
    BattlefieldScenario,
    BattlefieldScenarioPayload,
    ModelPlacement,
    PlacedArmy,
    PlacementError,
    UnitPlacement,
)
from warhammer40k_core.engine.game_state import GameConfig, GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.phase import LifecycleStatusKind, SetupStep
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.engine.setup_flow import SECONDARY_MISSION_DECISION_TYPE
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.integration
def test_phase10a_placement_uses_mustered_armies_from_lifecycle_state() -> None:
    state = _mustered_lifecycle_state()
    assert state.current_setup_step is SetupStep.SELECT_SECONDARY_MISSIONS
    assert state.missing_army_player_ids() == ()

    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10a-smoke-battlefield",
        armies=tuple(state.army_definitions),
    )
    placement_state = scenario.battlefield_state

    assert placement_state.battlefield_id == "phase10a-smoke-battlefield"
    assert len(placement_state.placed_armies) == 2
    assert len(placement_state.placed_model_ids()) == 10
    assert placement_state.placed_army_for_player("player-a").army_id == "army-alpha"
    assert placement_state.placed_army_for_player("player-b").army_id == "army-beta"

    player_a_unit = placement_state.placed_army_for_player("player-a").unit_placements[0]
    player_b_unit = placement_state.placed_army_for_player("player-b").unit_placements[0]
    assert player_a_unit.model_placements[0].pose.to_payload() == {
        "position": {"x": 6.0, "y": 6.0, "z": 0.0},
        "facing": {"degrees": 0.0},
    }
    assert player_b_unit.model_placements[0].pose.to_payload() == {
        "position": {"x": 42.0, "y": 6.0, "z": 0.0},
        "facing": {"degrees": 180.0},
    }

    for placed_army in placement_state.placed_armies:
        army = scenario.army_by_id(placed_army.army_id)
        assert placed_army.player_id == army.player_id
        for unit_placement in placed_army.unit_placements:
            unit = scenario.unit_instance_for_placement(unit_placement)
            assert unit.unit_instance_id == unit_placement.unit_instance_id
            assert len(unit_placement.model_placements) == len(unit.own_models)
            for model_placement in unit_placement.model_placements:
                model = scenario.model_instance_for_placement(model_placement)
                characteristics = {
                    value.characteristic: value.final for value in model.characteristics
                }
                assert model.model_instance_id == model_placement.model_instance_id
                assert model.datasheet_id == unit.datasheet_id
                assert model.base_size.diameter_mm == 32.0
                assert characteristics[Characteristic.MOVEMENT] == 6
                assert characteristics[Characteristic.OBJECTIVE_CONTROL] == 2

    placement_payload = cast(
        BattlefieldRuntimeStatePayload,
        json.loads(json.dumps(placement_state.to_payload(), sort_keys=True)),
    )
    scenario_payload = cast(
        BattlefieldScenarioPayload,
        json.loads(json.dumps(scenario.to_payload(), sort_keys=True)),
    )
    placement_blob = json.dumps(placement_payload, sort_keys=True)
    scenario_blob = json.dumps(scenario_payload, sort_keys=True)

    assert "<" not in placement_blob
    assert "object at 0x" not in placement_blob
    assert "<" not in scenario_blob
    assert "object at 0x" not in scenario_blob
    assert BattlefieldRuntimeState.from_payload(placement_payload).to_payload() == (
        placement_state.to_payload()
    )
    assert BattlefieldScenario.from_payload(scenario_payload).to_payload() == (
        scenario.to_payload()
    )


@pytest.mark.integration
def test_phase10a_placement_rejects_duplicate_and_cross_army_drift() -> None:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10a-smoke-battlefield",
        armies=tuple(_mustered_lifecycle_state().army_definitions),
    )

    duplicate_payload = _placement_payload_copy(scenario)
    first_model = duplicate_payload["placed_armies"][0]["unit_placements"][0]["model_placements"][
        0
    ]["model_instance_id"]
    duplicate_payload["placed_armies"][0]["unit_placements"][0]["model_placements"][1][
        "model_instance_id"
    ] = first_model
    with pytest.raises(PlacementError, match="placed twice"):
        BattlefieldRuntimeState.from_payload(duplicate_payload)

    missing_unit_payload = _placement_payload_copy(scenario)
    first_unit = missing_unit_payload["placed_armies"][0]["unit_placements"][0]
    first_unit["unit_instance_id"] = "army-alpha:missing-unit"
    for model_placement in first_unit["model_placements"]:
        model_placement["unit_instance_id"] = "army-alpha:missing-unit"
        model_placement["model_instance_id"] = (
            f"army-alpha:missing-unit:{model_placement['model_instance_id'].rsplit(':', 1)[1]}"
        )
    missing_unit_state = BattlefieldRuntimeState.from_payload(missing_unit_payload)
    with pytest.raises(PlacementError, match="existing UnitInstance"):
        BattlefieldScenario(armies=scenario.armies, battlefield_state=missing_unit_state)

    missing_model_payload = _placement_payload_copy(scenario)
    first_model_placement = missing_model_payload["placed_armies"][0]["unit_placements"][0][
        "model_placements"
    ][0]
    first_model_placement["model_instance_id"] = (
        f"{first_model_placement['unit_instance_id']}:missing-model:999"
    )
    missing_model_state = BattlefieldRuntimeState.from_payload(missing_model_payload)
    with pytest.raises(PlacementError, match="existing ModelInstance"):
        BattlefieldScenario(armies=scenario.armies, battlefield_state=missing_model_state)

    wrong_player_payload = _placement_payload_copy(scenario)
    wrong_player_payload["placed_armies"] = [wrong_player_payload["placed_armies"][0]]
    wrong_player_payload["placed_armies"][0]["player_id"] = "player-b"
    for unit_placement in wrong_player_payload["placed_armies"][0]["unit_placements"]:
        unit_placement["player_id"] = "player-b"
        for model_placement in unit_placement["model_placements"]:
            model_placement["player_id"] = "player-b"
    wrong_player_state = BattlefieldRuntimeState.from_payload(wrong_player_payload)
    with pytest.raises(PlacementError, match="wrong player"):
        BattlefieldScenario(armies=scenario.armies, battlefield_state=wrong_player_state)


@pytest.mark.integration
def test_phase10a_placement_value_objects_fail_fast() -> None:
    scenario = create_deterministic_battlefield_scenario(
        battlefield_id="phase10a-smoke-battlefield",
        armies=tuple(_mustered_lifecycle_state().army_definitions),
    )
    placement_state = scenario.battlefield_state
    placed_army = placement_state.placed_army_for_player("player-a")
    unit_placement = placed_army.unit_placements[0]
    model_placement = unit_placement.model_placements[0]

    assert placement_state.unit_placement_by_id(unit_placement.unit_instance_id) == unit_placement
    assert placement_state.model_placement_by_id(model_placement.model_instance_id) == (
        model_placement
    )
    with pytest.raises(PlacementError, match="player_id is not placed"):
        placement_state.placed_army_for_player("missing-player")
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        placement_state.unit_placement_by_id("army-alpha:missing-unit")
    with pytest.raises(PlacementError, match="model_instance_id is not placed"):
        placement_state.model_placement_by_id(
            "army-alpha:intercessor-unit-1:core-intercessor-like:999"
        )
    with pytest.raises(PlacementError, match="army_id was not found"):
        scenario.army_by_id("missing-army")

    with pytest.raises(PlacementError, match="armies must be a tuple"):
        create_deterministic_battlefield_scenario(
            battlefield_id="bad-scenario",
            armies=cast(tuple[ArmyDefinition, ...], []),
        )
    with pytest.raises(PlacementError, match="armies must not be empty"):
        create_deterministic_battlefield_scenario(
            battlefield_id="bad-scenario",
            armies=(),
        )
    with pytest.raises(PlacementError, match="ArmyDefinition"):
        create_deterministic_battlefield_scenario(
            battlefield_id="bad-scenario",
            armies=cast(tuple[ArmyDefinition, ...], ("not-an-army",)),
        )

    with pytest.raises(PlacementError, match="scoped to army_id"):
        ModelPlacement(
            army_id="other-army",
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=model_placement.model_instance_id,
            pose=model_placement.pose,
        )
    with pytest.raises(PlacementError, match="scoped to unit_instance_id"):
        ModelPlacement(
            army_id=model_placement.army_id,
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=f"{model_placement.army_id}:other-unit:001",
            pose=model_placement.pose,
        )
    with pytest.raises(PlacementError, match="pose"):
        ModelPlacement(
            army_id=model_placement.army_id,
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=model_placement.model_instance_id,
            pose=cast(Pose, "bad-pose"),
        )

    with pytest.raises(PlacementError, match="scoped to army_id"):
        UnitPlacement(
            army_id="other-army",
            player_id=unit_placement.player_id,
            unit_instance_id=unit_placement.unit_instance_id,
            model_placements=unit_placement.model_placements,
        )
    with pytest.raises(PlacementError, match="match army_id"):
        UnitPlacement(
            army_id=unit_placement.army_id,
            player_id=unit_placement.player_id,
            unit_instance_id=unit_placement.unit_instance_id,
            model_placements=(
                ModelPlacement(
                    army_id="other-army",
                    player_id=unit_placement.player_id,
                    unit_instance_id="other-army:unit",
                    model_instance_id="other-army:unit:001",
                    pose=model_placement.pose,
                ),
            ),
        )
    with pytest.raises(PlacementError, match="match player_id"):
        UnitPlacement(
            army_id=unit_placement.army_id,
            player_id=unit_placement.player_id,
            unit_instance_id=unit_placement.unit_instance_id,
            model_placements=(
                ModelPlacement(
                    army_id=unit_placement.army_id,
                    player_id="other-player",
                    unit_instance_id=unit_placement.unit_instance_id,
                    model_instance_id=model_placement.model_instance_id,
                    pose=model_placement.pose,
                ),
            ),
        )

    wrong_army_unit = UnitPlacement(
        army_id="other-army",
        player_id=placed_army.player_id,
        unit_instance_id="other-army:unit",
        model_placements=(
            ModelPlacement(
                army_id="other-army",
                player_id=placed_army.player_id,
                unit_instance_id="other-army:unit",
                model_instance_id="other-army:unit:001",
                pose=model_placement.pose,
            ),
        ),
    )
    with pytest.raises(PlacementError, match="match army_id"):
        PlacedArmy(
            army_id=placed_army.army_id,
            player_id=placed_army.player_id,
            unit_placements=(wrong_army_unit,),
        )


def _mustered_lifecycle_state() -> GameState:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    lifecycle = GameLifecycle()
    lifecycle.start(_minimal_two_player_game_config(catalog))

    status = lifecycle.advance_until_decision_or_terminal()

    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    assert status.decision_request is not None
    assert status.decision_request.decision_type == SECONDARY_MISSION_DECISION_TYPE
    assert lifecycle.state is not None
    return lifecycle.state


def _placement_payload_copy(scenario: BattlefieldScenario) -> BattlefieldRuntimeStatePayload:
    return cast(
        BattlefieldRuntimeStatePayload,
        json.loads(json.dumps(scenario.battlefield_state.to_payload(), sort_keys=True)),
    )


def _minimal_two_player_game_config(catalog: ArmyCatalog) -> GameConfig:
    return GameConfig(
        game_id="phase10a-smoke-game",
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_tenth(
            descriptor_version="core-v2-phase10a-smoke"
        ),
        army_catalog=catalog,
        army_muster_requests=(
            _army_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
            _army_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
        player_ids=("player-a", "player-b"),
        turn_order=("player-a", "player-b"),
        fixed_secondary_mission_ids=(
            "assassination",
            "bring_it_down",
            "cleanse",
        ),
    )


def _army_muster_request(
    *,
    catalog: ArmyCatalog,
    player_id: str,
    army_id: str,
    unit_selection_id: str,
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
        unit_selections=(
            UnitMusterSelection(
                unit_selection_id=unit_selection_id,
                datasheet_id="core-intercessor-like-infantry",
                model_profile_selections=(
                    ModelProfileSelection(
                        model_profile_id="core-intercessor-like",
                        model_count=5,
                    ),
                ),
            ),
        ),
    )
