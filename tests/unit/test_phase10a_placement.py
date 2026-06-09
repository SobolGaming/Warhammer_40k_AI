from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

import pytest

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.army_mustering import (
    ArmyDefinition,
    ArmyMusterRequest,
    muster_army,
)
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
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    ModelProfileSelection,
    UnitMusterSelection,
)
from warhammer40k_core.engine.placement import create_deterministic_battlefield_scenario
from warhammer40k_core.geometry.pose import Pose


def test_deterministic_placement_uses_real_mustered_runtime_models() -> None:
    scenario = _scenario()
    placement_state = scenario.battlefield_state

    assert placement_state.battlefield_id == "phase10a-unit-battlefield"
    assert tuple(army.player_id for army in scenario.armies) == ("player-a", "player-b")
    assert tuple(army.player_id for army in placement_state.placed_armies) == (
        "player-a",
        "player-b",
    )
    assert len(placement_state.placed_model_ids()) == 10

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
            assert placement_state.unit_placement_by_id(unit.unit_instance_id) == unit_placement
            for model_placement in unit_placement.model_placements:
                model = scenario.model_instance_for_placement(model_placement)
                characteristics = {
                    value.characteristic: value.final for value in model.characteristics
                }
                assert placement_state.model_placement_by_id(model.model_instance_id) == (
                    model_placement
                )
                assert model.model_instance_id == model_placement.model_instance_id
                assert model.datasheet_id == unit.datasheet_id
                assert model.base_size.diameter_mm == 32.0
                assert characteristics[Characteristic.MOVEMENT] == 6
                assert characteristics[Characteristic.OBJECTIVE_CONTROL] == 2


def test_placement_payloads_round_trip_without_object_reprs() -> None:
    scenario = _scenario()
    placement_payload = cast(
        BattlefieldRuntimeStatePayload,
        json.loads(json.dumps(scenario.battlefield_state.to_payload(), sort_keys=True)),
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
        scenario.battlefield_state.to_payload()
    )
    assert BattlefieldScenario.from_payload(scenario_payload).to_payload() == (
        scenario.to_payload()
    )


def test_battlefield_scenario_reports_unplaced_mustered_models() -> None:
    scenario = _scenario()
    placed_army = scenario.battlefield_state.placed_armies[0]
    other_army = scenario.battlefield_state.placed_armies[1]
    unit_placement = placed_army.unit_placements[0]
    removed_model_id = unit_placement.model_placements[-1].model_instance_id
    partial_unit_placement = replace(
        unit_placement,
        model_placements=unit_placement.model_placements[:-1],
    )
    partial_scenario = BattlefieldScenario(
        armies=scenario.armies,
        battlefield_state=replace(
            scenario.battlefield_state,
            placed_armies=(
                replace(placed_army, unit_placements=(partial_unit_placement,)),
                other_army,
            ),
        ),
    )

    assert scenario.unplaced_model_ids() == ()
    scenario.assert_all_mustered_models_placed()
    assert partial_scenario.unplaced_model_ids() == (removed_model_id,)
    with pytest.raises(PlacementError, match="unplaced model IDs"):
        partial_scenario.assert_all_mustered_models_placed()


def test_placement_rejects_duplicate_and_unknown_runtime_references() -> None:
    scenario = _scenario()

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
        f"{first_model_placement['unit_instance_id']}:missing-model"
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


def test_placement_value_objects_fail_fast_on_invalid_shapes() -> None:
    scenario = _scenario()
    placement_state = scenario.battlefield_state
    placed_army = placement_state.placed_army_for_player("player-a")
    unit_placement = placed_army.unit_placements[0]
    model_placement = unit_placement.model_placements[0]

    with pytest.raises(PlacementError, match="must be a string"):
        ModelPlacement(
            army_id=cast(str, 1),
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=model_placement.model_instance_id,
            pose=model_placement.pose,
        )
    with pytest.raises(PlacementError, match="must not be empty"):
        ModelPlacement(
            army_id=" ",
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=model_placement.model_instance_id,
            pose=model_placement.pose,
        )
    with pytest.raises(PlacementError, match="stable identity prefix"):
        ModelPlacement(
            army_id=f"army:{model_placement.army_id}",
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=model_placement.model_instance_id,
            pose=model_placement.pose,
        )
    with pytest.raises(PlacementError, match="stable identity prefix"):
        ModelPlacement(
            army_id=model_placement.army_id,
            player_id=model_placement.player_id,
            unit_instance_id=f"unit:{model_placement.unit_instance_id}",
            model_instance_id=model_placement.model_instance_id,
            pose=model_placement.pose,
        )
    with pytest.raises(PlacementError, match="stable identity prefix"):
        ModelPlacement(
            army_id=model_placement.army_id,
            player_id=model_placement.player_id,
            unit_instance_id=model_placement.unit_instance_id,
            model_instance_id=f"model:{model_placement.model_instance_id}",
            pose=model_placement.pose,
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

    with pytest.raises(PlacementError, match="model_placements must be a tuple"):
        replace(unit_placement, model_placements=cast(tuple[ModelPlacement, ...], []))
    with pytest.raises(PlacementError, match="model_placements must not be empty"):
        replace(unit_placement, model_placements=())
    with pytest.raises(PlacementError, match="ModelPlacement values"):
        replace(
            unit_placement,
            model_placements=cast(tuple[ModelPlacement, ...], ("bad-placement",)),
        )
    with pytest.raises(PlacementError, match="scoped to army_id"):
        replace(unit_placement, army_id="other-army")
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

    with pytest.raises(PlacementError, match="unit_placements must be a tuple"):
        replace(placed_army, unit_placements=cast(tuple[UnitPlacement, ...], []))
    with pytest.raises(PlacementError, match="unit_placements must not be empty"):
        replace(placed_army, unit_placements=())
    with pytest.raises(PlacementError, match="UnitPlacement values"):
        replace(
            placed_army,
            unit_placements=cast(tuple[UnitPlacement, ...], ("bad-placement",)),
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
        replace(placed_army, unit_placements=(wrong_army_unit,))


def test_battlefield_state_and_scenario_fail_fast_on_invalid_shapes() -> None:
    scenario = _scenario()
    placement_state = scenario.battlefield_state
    placed_army = placement_state.placed_armies[0]
    other_army = placement_state.placed_armies[1]

    with pytest.raises(PlacementError, match="stable identity prefix"):
        BattlefieldRuntimeState(
            battlefield_id="battlefield:bad-id",
            placed_armies=placement_state.placed_armies,
        )
    with pytest.raises(PlacementError, match="placed_armies must be a tuple"):
        replace(placement_state, placed_armies=cast(tuple[PlacedArmy, ...], []))
    with pytest.raises(PlacementError, match="placed_armies must not be empty"):
        replace(placement_state, placed_armies=())
    with pytest.raises(PlacementError, match="PlacedArmy values"):
        replace(placement_state, placed_armies=cast(tuple[PlacedArmy, ...], ("bad-army",)))
    with pytest.raises(PlacementError, match="army_id must not be placed twice"):
        replace(
            placement_state,
            placed_armies=(
                placed_army,
                _placed_army_with_player(placed_army, player_id="other-player"),
            ),
        )
    with pytest.raises(PlacementError, match="player_id must not be placed twice"):
        replace(
            placement_state,
            placed_armies=(
                placed_army,
                _placed_army_with_player(other_army, player_id=placed_army.player_id),
            ),
        )

    with pytest.raises(PlacementError, match="player_id is not placed"):
        placement_state.placed_army_for_player("missing-player")
    with pytest.raises(PlacementError, match="unit_instance_id is not placed"):
        placement_state.unit_placement_by_id("army-alpha:missing-unit")
    with pytest.raises(PlacementError, match="model_instance_id is not placed"):
        placement_state.model_placement_by_id("army-alpha:missing-unit:001")
    with pytest.raises(PlacementError, match="stable identity prefix"):
        placement_state.unit_placement_by_id("unit:army-alpha:unit")
    with pytest.raises(PlacementError, match="stable identity prefix"):
        placement_state.model_placement_by_id("model:army-alpha:unit:001")

    with pytest.raises(PlacementError, match="armies must be a tuple"):
        BattlefieldScenario(
            armies=cast(tuple[ArmyDefinition, ...], []),
            battlefield_state=placement_state,
        )
    with pytest.raises(PlacementError, match="armies must not be empty"):
        BattlefieldScenario(armies=(), battlefield_state=placement_state)
    with pytest.raises(PlacementError, match="ArmyDefinition values"):
        BattlefieldScenario(
            armies=cast(tuple[ArmyDefinition, ...], ("bad-army",)),
            battlefield_state=placement_state,
        )
    with pytest.raises(PlacementError, match="unique army IDs"):
        BattlefieldScenario(
            armies=(scenario.armies[0], scenario.armies[0]),
            battlefield_state=placement_state,
        )
    with pytest.raises(PlacementError, match="unique player IDs"):
        BattlefieldScenario(
            armies=(
                scenario.armies[0],
                replace(scenario.armies[1], player_id=scenario.armies[0].player_id),
            ),
            battlefield_state=placement_state,
        )
    with pytest.raises(PlacementError, match="BattlefieldRuntimeState"):
        BattlefieldScenario(
            armies=scenario.armies,
            battlefield_state=cast(BattlefieldRuntimeState, "bad-state"),
        )
    with pytest.raises(PlacementError, match="army_id was not found"):
        scenario.army_by_id("missing-army")
    with pytest.raises(PlacementError, match="placement must be a UnitPlacement"):
        scenario.unit_instance_for_placement(cast(UnitPlacement, "bad-placement"))
    with pytest.raises(PlacementError, match="placement must be a ModelPlacement"):
        scenario.model_instance_for_placement(cast(ModelPlacement, "bad-placement"))


def test_deterministic_placement_factory_rejects_invalid_inputs() -> None:
    armies = _mustered_armies()

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
    with pytest.raises(PlacementError, match="stable identity prefix"):
        create_deterministic_battlefield_scenario(
            battlefield_id="battlefield:bad-scenario",
            armies=armies,
        )

    reverse_order_scenario = create_deterministic_battlefield_scenario(
        battlefield_id="reverse-order-scenario",
        armies=tuple(reversed(armies)),
    )
    assert tuple(
        placed_army.player_id
        for placed_army in reverse_order_scenario.battlefield_state.placed_armies
    ) == ("player-a", "player-b")


def _scenario() -> BattlefieldScenario:
    return create_deterministic_battlefield_scenario(
        battlefield_id="phase10a-unit-battlefield",
        armies=_mustered_armies(),
    )


def _mustered_armies() -> tuple[ArmyDefinition, ...]:
    catalog = ArmyCatalog.phase9a_canonical_content_pack()
    return (
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-a",
                army_id="army-alpha",
                unit_selection_id="intercessor-unit-1",
            ),
        ),
        muster_army(
            catalog=catalog,
            request=_muster_request(
                catalog=catalog,
                player_id="player-b",
                army_id="army-beta",
                unit_selection_id="intercessor-unit-2",
            ),
        ),
    )


def _muster_request(
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
            detachment_ids=("core-combined-arms",),
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


def _placement_payload_copy(scenario: BattlefieldScenario) -> BattlefieldRuntimeStatePayload:
    return cast(
        BattlefieldRuntimeStatePayload,
        json.loads(json.dumps(scenario.battlefield_state.to_payload(), sort_keys=True)),
    )


def _placed_army_with_player(placed_army: PlacedArmy, *, player_id: str) -> PlacedArmy:
    return PlacedArmy(
        army_id=placed_army.army_id,
        player_id=player_id,
        unit_placements=tuple(
            UnitPlacement(
                army_id=unit_placement.army_id,
                player_id=player_id,
                unit_instance_id=unit_placement.unit_instance_id,
                model_placements=tuple(
                    ModelPlacement(
                        army_id=model_placement.army_id,
                        player_id=player_id,
                        unit_instance_id=model_placement.unit_instance_id,
                        model_instance_id=model_placement.model_instance_id,
                        pose=model_placement.pose,
                    )
                    for model_placement in unit_placement.model_placements
                ),
            )
            for unit_placement in placed_army.unit_placements
        ),
    )
