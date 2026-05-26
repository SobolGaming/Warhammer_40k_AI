from __future__ import annotations

import json

import pytest

from warhammer40k_core.core.battlefield import (
    Battlefield,
    BattlefieldError,
    SpatialModelState,
    SpatialState,
    TerrainLayout,
)
from warhammer40k_core.core.deployment_zones import DeploymentZone, DeploymentZoneError
from warhammer40k_core.core.objectives import Objective, ObjectiveError


def test_spatial_state_indexes_battlefield_models_by_stable_id() -> None:
    state = SpatialState(
        model_states=(
            SpatialModelState("model-b", "player-a", x=6.0, y=4.0),
            SpatialModelState("model-a", "player-a", x=1.0, y=2.0),
        )
    )

    assert state.model_ids() == ("model-a", "model-b")
    assert state.model_state("model-a").stable_identity() == "model:model-a"

    with pytest.raises(BattlefieldError):
        SpatialState(
            model_states=(
                SpatialModelState("model-a", "player-a", x=1.0, y=2.0),
                SpatialModelState("model-a", "player-b", x=3.0, y=4.0),
            )
        )


def test_spatial_state_generation_increments_on_authoritative_model_updates() -> None:
    initial = SpatialState.empty()
    added = initial.with_model_state(SpatialModelState("model-a", "player-a", x=1.0, y=1.0))
    moved = added.with_model_position("model-a", x=3.0, y=4.0)
    destroyed = moved.with_model_alive_status("model-a", False)
    removed = destroyed.without_model("model-a")

    assert initial.generation == 0
    assert added.generation == 1
    assert moved.generation == 2
    assert destroyed.generation == 3
    assert removed.generation == 4
    assert added.model_state("model-a").x == 1.0
    assert moved.model_state("model-a").x == 3.0
    assert not destroyed.model_state("model-a").is_alive

    with pytest.raises(BattlefieldError):
        added.with_model_position("missing", x=1.0, y=1.0)


def test_objective_control_derives_from_current_spatial_state() -> None:
    battlefield = Battlefield(
        battlefield_id="table",
        width=44.0,
        depth=60.0,
        objectives=(Objective("center", "Center", x=22.0, y=30.0),),
        spatial_state=SpatialState(
            model_states=(
                SpatialModelState("alpha", "player-a", x=22.0, y=30.0, objective_control=1),
                SpatialModelState("bravo", "player-b", x=30.0, y=30.0, objective_control=2),
            )
        ),
    )

    moved = battlefield.with_model_position("alpha", x=10.0, y=10.0).with_model_position(
        "bravo",
        x=22.0,
        y=30.0,
    )

    assert battlefield.controlled_player_for_objective("center") == "player-a"
    assert battlefield.objective_control_scores("center") == (("player-a", 1),)
    assert moved.controlled_player_for_objective("center") == "player-b"
    assert moved.objective_control_scores("center") == (("player-b", 2),)


def test_objective_control_tie_is_explicitly_uncontrolled() -> None:
    battlefield = Battlefield(
        battlefield_id="table",
        width=44.0,
        depth=60.0,
        objectives=(Objective("center", "Center", x=22.0, y=30.0),),
        spatial_state=SpatialState(
            model_states=(
                SpatialModelState("alpha", "player-a", x=22.0, y=30.0),
                SpatialModelState("bravo", "player-b", x=22.0, y=30.0),
            )
        ),
    )

    assert battlefield.controlled_player_for_objective("center") is None
    assert battlefield.objective_control_payloads() == (
        {
            "objective_id": "center",
            "controlled_by_player_id": None,
            "scores": [
                {"player_id": "player-a", "score": 1},
                {"player_id": "player-b", "score": 1},
            ],
        },
    )


def test_battlefield_rejects_spatial_state_without_battlefield_bounds() -> None:
    with pytest.raises(BattlefieldError):
        Battlefield(
            battlefield_id="table",
            width=44.0,
            depth=60.0,
            spatial_state=SpatialState(
                model_states=(SpatialModelState("outside", "player-a", x=45.0, y=30.0),)
            ),
        )


def test_terrain_layout_generation_increments_and_rejects_duplicate_ids() -> None:
    layout = TerrainLayout.empty()
    with_ruin = layout.with_terrain_id("ruin")
    with_forest = with_ruin.with_terrain_id("forest")
    removed_ruin = with_forest.without_terrain_id("ruin")

    assert layout.generation == 0
    assert with_ruin.terrain_ids == ("ruin",)
    assert with_forest.terrain_ids == ("forest", "ruin")
    assert with_forest.generation == 2
    assert removed_ruin.terrain_ids == ("forest",)
    assert removed_ruin.generation == 3

    with pytest.raises(BattlefieldError):
        with_ruin.with_terrain_id("ruin")


def test_deployment_zone_contains_points_and_validates_bounds() -> None:
    zone = DeploymentZone(
        deployment_zone_id="player-a-zone",
        player_id="player-a",
        min_x=0.0,
        min_y=0.0,
        max_x=10.0,
        max_y=20.0,
    )

    assert zone.stable_identity() == "deployment-zone:player-a-zone"
    assert zone.contains_point(5.0, 10.0)
    assert not zone.contains_point(11.0, 10.0)

    with pytest.raises(DeploymentZoneError):
        DeploymentZone("bad", "player-a", min_x=10.0, min_y=0.0, max_x=10.0, max_y=20.0)


def test_phase_8_payloads_round_trip_without_object_reprs() -> None:
    battlefield = Battlefield(
        battlefield_id="table",
        width=44.0,
        depth=60.0,
        terrain_layout=TerrainLayout(terrain_ids=("ruin",), generation=1),
        objectives=(Objective("center", "Center", x=22.0, y=30.0),),
        deployment_zones=(
            DeploymentZone(
                deployment_zone_id="player-a-zone",
                player_id="player-a",
                min_x=0.0,
                min_y=0.0,
                max_x=44.0,
                max_y=12.0,
            ),
        ),
        spatial_state=SpatialState(
            model_states=(
                SpatialModelState("alpha", "player-a", x=22.0, y=30.0, objective_control=2),
            ),
            generation=3,
        ),
    )
    payloads = (
        (battlefield.to_payload(), Battlefield.from_payload),
        (battlefield.terrain_layout.to_payload(), TerrainLayout.from_payload),
        (battlefield.spatial_state.to_payload(), SpatialState.from_payload),
        (battlefield.objectives[0].to_payload(), Objective.from_payload),
        (battlefield.deployment_zones[0].to_payload(), DeploymentZone.from_payload),
    )

    for payload, loader in payloads:
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob
        assert loader(json.loads(blob)).to_payload() == payload


def test_stable_identity_prefixes_are_rejected_for_phase_8_ids() -> None:
    with pytest.raises(ObjectiveError):
        Objective("objective:center", "Center", x=1.0, y=1.0)
    with pytest.raises(DeploymentZoneError):
        DeploymentZone("deployment-zone:a", "player-a", 0.0, 0.0, 1.0, 1.0)
    with pytest.raises(BattlefieldError):
        SpatialModelState("model:alpha", "player-a", x=1.0, y=1.0)
    with pytest.raises(BattlefieldError):
        TerrainLayout(terrain_ids=("terrain:ruin",))
