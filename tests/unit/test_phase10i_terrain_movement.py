from __future__ import annotations

import json
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    TerrainPathLegalityContext,
    TerrainPathLegalityContextPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import ObstacleVolume, TerrainVolume
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_model_can_move_freely_over_terrain_at_or_below_threshold() -> None:
    mover = _model("mover", 1.0, 1.0)
    low_terrain = TerrainVolume(
        terrain_id="low-crater",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=2.0,
    )

    context = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain=(low_terrain,),
        end_pose=Pose.at(5.0, 1.0),
    )
    result = context.validate()

    assert result.is_valid
    assert result.segments[0].terrain_id == "low-crater"
    assert result.segments[0].traversal_mode.value == "freely_traversable"
    assert result.segments[0].vertical_distance_inches == 0.0
    assert (
        result.segments[0].counted_distance_inches == result.segments[0].horizontal_distance_inches
    )


def test_model_cannot_pass_through_wall_without_traversal_permission() -> None:
    mover = _model("vehicle-mover", 1.0, 1.0)
    wall = _ruins_wall("ruins-wall")

    result = _terrain_context(
        _normal_legality_context(keywords=("VEHICLE",)),
        moving_model=mover,
        terrain=(wall,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "terrain_feature_transit_forbidden"
    assert result.violations[0].terrain_id == "ruins-wall"


def test_model_can_climb_tall_terrain_by_paying_vertical_distance() -> None:
    mover = _model("mover", 1.0, 1.0)
    tall_terrain = TerrainVolume(
        terrain_id="container-stack",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=3.0,
    )

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain=(tall_terrain,),
        middle_pose=Pose.at(3.0, 1.0, 3.0),
        end_pose=Pose.at(5.0, 1.0, 3.0),
    ).validate()

    assert result.is_valid
    assert result.segments[0].traversal_mode.value == "climb"
    assert result.segments[0].vertical_distance_inches == 3.0
    assert (
        result.segments[0].counted_distance_inches > result.segments[0].horizontal_distance_inches
    )


def test_model_cannot_end_mid_climb() -> None:
    mover = _model("mover", 1.0, 1.0)
    tall_terrain = TerrainVolume(
        terrain_id="container-stack",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=3.0,
    )

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain=(tall_terrain,),
        middle_pose=Pose.at(2.0, 1.0, 0.0),
        end_pose=Pose.at(3.0, 1.0, 1.5),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "terrain_mid_climb_endpoint_forbidden"
    assert result.violations[0].terrain_id == "container-stack"


def test_infantry_and_beast_can_traverse_ruins_wall() -> None:
    wall = _ruins_wall("ruins-wall")

    for keywords in (("INFANTRY",), ("BEAST",)):
        mover = _model(f"{keywords[0].lower()}-mover", 1.0, 1.0)
        result = _terrain_context(
            _normal_legality_context(keywords=keywords),
            moving_model=mover,
            terrain=(wall,),
            end_pose=Pose.at(5.0, 1.0),
        ).validate()

        assert result.is_valid
        assert result.segments[0].traversal_mode.value == "through_feature"


def test_fly_terrain_movement_records_air_path_measurement_hook() -> None:
    mover = _model("fly-mover", 1.0, 1.0)
    wall = _ruins_wall("ruins-wall")

    result = _terrain_context(
        _normal_legality_context(keywords=("FLY", "INFANTRY")),
        moving_model=mover,
        terrain=(wall,),
        middle_pose=Pose.at(3.0, 1.0, 3.0),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert result.is_valid
    assert result.segments[0].traversal_mode.value == "air_path"
    assert result.segments[0].air_path_measurement_pending
    assert result.segments[0].vertical_distance_inches == 6.0


def test_terrain_traversal_payloads_round_trip_without_object_reprs() -> None:
    mover = _model("mover", 1.0, 1.0)
    low_terrain = TerrainVolume(
        terrain_id="low-crater",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=2.0,
    )
    context = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain=(low_terrain,),
        end_pose=Pose.at(5.0, 1.0),
    )
    result = context.validate()

    context_payload = cast(
        TerrainPathLegalityContextPayload,
        json.loads(json.dumps(context.to_payload(), sort_keys=True)),
    )
    result_payload = cast(
        TerrainPathLegalityResultPayload,
        json.loads(json.dumps(result.to_payload(), sort_keys=True)),
    )
    for payload in (context_payload, result_payload):
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob

    assert TerrainPathLegalityContext.from_payload(context_payload).to_payload() == context_payload
    assert TerrainPathLegalityResult.from_payload(result_payload).to_payload() == result_payload


def _model(model_id: str, x: float, y: float) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x, y),
        base=CircularBase(radius=0.5),
        volume=ModelVolume(height=2.0),
    )


def _ruins_wall(terrain_id: str) -> ObstacleVolume:
    return ObstacleVolume(
        terrain_id=terrain_id,
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=3.0,
    )


def _normal_legality_context(
    *,
    keywords: tuple[str, ...] = ("INFANTRY",),
) -> MovementLegalityContext:
    return MovementLegalityContext.from_keywords(
        keywords=keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_tenth(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )


def _terrain_context(
    legality_context: MovementLegalityContext,
    *,
    moving_model: Model,
    terrain: tuple[TerrainVolume, ...],
    middle_pose: Pose | None = None,
    end_pose: Pose,
) -> TerrainPathLegalityContext:
    witness = PathWitness.for_paths(
        (
            (
                moving_model.model_id,
                (
                    moving_model.pose,
                    Pose.at(3.0, 1.0) if middle_pose is None else middle_pose,
                    end_pose,
                ),
            ),
        )
    )
    return legality_context.to_terrain_path_legality_context(
        moving_model=moving_model,
        witness=witness,
        terrain=terrain,
        sample_interval_inches=0.5,
    )
