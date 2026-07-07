from __future__ import annotations

import json
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.geometry.base import CircularBase, OvalBase
from warhammer40k_core.geometry.pathing import (
    PathValidationContext,
    PathValidationContextPayload,
    PathValidationResult,
    PathValidationResultPayload,
    PathWitness,
)
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import TerrainVolume
from warhammer40k_core.geometry.volume import Model, ModelVolume


def test_circular_infantry_can_transit_friendly_infantry_but_not_end_overlapping() -> None:
    mover = _model("mover", 1.0, 1.0)
    friendly = _model("friendly-infantry", 3.0, 1.0)
    transit_context = _path_context(
        _normal_legality_context(),
        moving_model=mover,
        friendly_models=(friendly,),
        end_pose=Pose.at(5.0, 1.0),
    )
    overlap_context = _path_context(
        _normal_legality_context(),
        moving_model=mover,
        friendly_models=(friendly,),
        end_pose=friendly.pose,
    )

    transit_result = transit_context.validate()
    overlap_result = overlap_context.validate()

    assert transit_result.is_valid
    assert overlap_result.violations[0].violation_code == "end_on_model_overlap"
    assert overlap_result.violations[0].blocker_id == "friendly-infantry"

    context_payload = cast(
        PathValidationContextPayload,
        json.loads(json.dumps(transit_context.to_payload(), sort_keys=True)),
    )
    result_payload = cast(
        PathValidationResultPayload,
        json.loads(json.dumps(transit_result.to_payload(), sort_keys=True)),
    )
    for payload in (context_payload, result_payload):
        blob = json.dumps(payload, sort_keys=True)
        assert "<" not in blob
        assert "object at 0x" not in blob
    assert PathValidationContext.from_payload(context_payload).to_payload() == context_payload
    assert PathValidationResult.from_payload(result_payload).to_payload() == result_payload


def test_infantry_can_transit_friendly_vehicle_but_not_end_overlapping() -> None:
    mover = _model("infantry-mover", 1.0, 1.0, radius=0.7)
    friendly_vehicle = _model("friendly-vehicle", 3.0, 1.0, radius=0.9)
    context = _normal_legality_context(keywords=("INFANTRY",))

    transit_context = _path_context(
        context,
        moving_model=mover,
        friendly_models=(friendly_vehicle,),
        friendly_vehicle_monster_model_ids=("friendly-vehicle",),
        end_pose=Pose.at(5.0, 1.0),
    )
    overlap_context = _path_context(
        context,
        moving_model=mover,
        friendly_models=(friendly_vehicle,),
        friendly_vehicle_monster_model_ids=("friendly-vehicle",),
        middle_pose=Pose.at(2.0, 1.0),
        end_pose=friendly_vehicle.pose,
        sample_interval_inches=10.0,
    )

    transit_result = transit_context.validate()
    overlap_result = overlap_context.validate()

    assert not context.capabilities.blocks_friendly_vehicle_monster_pass_through
    assert transit_context.friendly_vehicle_monster_model_ids == ()
    assert transit_result.is_valid
    assert not overlap_result.is_valid
    assert overlap_result.violations[0].violation_code == "end_on_model_overlap"
    assert overlap_result.violations[0].blocker_id == "friendly-vehicle"


def test_vehicle_cannot_transit_friendly_vehicle_or_monster_blocker() -> None:
    mover = _model("mover", 1.0, 1.0, radius=0.7)
    friendly_vehicle = _model("friendly-vehicle", 3.0, 1.0, radius=0.9)

    result = _path_context(
        _normal_legality_context(keywords=("VEHICLE",)),
        moving_model=mover,
        friendly_models=(friendly_vehicle,),
        friendly_vehicle_monster_model_ids=("friendly-vehicle",),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "friendly_vehicle_monster_transit_forbidden"
    assert result.violations[0].blocker_id == "friendly-vehicle"


def test_semantic_permission_allows_vehicle_to_move_over_friendly_vehicle_blocker() -> None:
    mover = _model("mover", 1.0, 1.0, radius=0.7)
    friendly_vehicle = _model("friendly-vehicle", 3.0, 1.0, radius=0.9)
    base_context = _normal_legality_context(keywords=("VEHICLE",))
    context = replace(
        base_context,
        capabilities=replace(
            base_context.capabilities,
            can_move_over_friendly_vehicle_monster_models=True,
            terrain_as_if_absent_height_inches=4.0,
        ),
    )

    path_context = _path_context(
        context,
        moving_model=mover,
        friendly_models=(friendly_vehicle,),
        friendly_vehicle_monster_model_ids=("friendly-vehicle",),
        end_pose=Pose.at(5.0, 1.0),
    )
    result = path_context.validate()

    assert context.capabilities.blocks_friendly_vehicle_monster_pass_through
    assert context.capabilities.can_move_over_friendly_vehicle_monster_models
    assert path_context.friendly_vehicle_monster_model_ids == ()
    assert result.is_valid


def test_semantic_permission_moves_through_models_but_rejects_excluded_titanic_blocker() -> None:
    mover = _model("mover", 1.0, 1.0, radius=0.7)
    enemy_infantry = _model("enemy-infantry", 3.0, 1.0, radius=0.9)
    enemy_titanic = _model("enemy-titanic", 3.0, 1.0, radius=0.9)
    base_context = _normal_legality_context()
    context = replace(
        base_context,
        capabilities=replace(
            base_context.capabilities,
            can_move_through_models=True,
            can_move_through_enemy_models=True,
            can_transit_enemy_engagement_range=True,
            enemy_model_transit_blocker_keywords=("TITANIC",),
        ),
    )

    transit_result = _path_context(
        context,
        moving_model=mover,
        enemy_models=(enemy_infantry,),
        end_pose=Pose.at(8.0, 1.0),
    ).validate()
    blocked_result = _path_context(
        context,
        moving_model=mover,
        enemy_models=(enemy_titanic,),
        enemy_model_transit_blocker_ids=("enemy-titanic",),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()
    endpoint_result = _path_context(
        context,
        moving_model=mover,
        enemy_models=(_model("enemy-engagement", 5.0, 2.5),),
        middle_pose=Pose.at(3.0, 1.0),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert transit_result.is_valid
    assert not blocked_result.is_valid
    assert blocked_result.violations[0].violation_code == "enemy_model_transit_forbidden"
    assert blocked_result.violations[0].blocker_id == "enemy-titanic"
    assert not endpoint_result.is_valid
    assert endpoint_result.violations[0].violation_code == "enemy_engagement_range_end_forbidden"


def test_semantic_permission_rejects_excluded_friendly_model_blocker() -> None:
    mover = _model("mover", 1.0, 1.0, radius=0.7)
    friendly_titanic = _model("friendly-titanic", 3.0, 1.0, radius=0.9)
    base_context = _normal_legality_context()
    context = replace(
        base_context,
        capabilities=replace(
            base_context.capabilities,
            can_move_through_models=True,
            can_move_through_friendly_models=True,
            friendly_model_transit_blocker_keywords=("TITANIC",),
        ),
    )

    result = _path_context(
        context,
        moving_model=mover,
        friendly_models=(friendly_titanic,),
        friendly_model_transit_blocker_ids=("friendly-titanic",),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "friendly_model_transit_forbidden"
    assert result.violations[0].blocker_id == "friendly-titanic"


def test_fly_normal_move_can_transit_enemy_models_and_engagement_range() -> None:
    mover = _model("fly-mover", 1.0, 1.0)
    enemy_base_blocker = _model("enemy-base-blocker", 3.0, 1.0)
    enemy_engagement_blocker = _model("enemy-engagement-blocker", 3.0, 2.5)
    context = _normal_legality_context(keywords=("FLY", "INFANTRY"))

    enemy_base_context = _path_context(
        context,
        moving_model=mover,
        enemy_models=(enemy_base_blocker,),
        end_pose=Pose.at(6.2, 1.0),
    )
    enemy_engagement_context = _path_context(
        context,
        moving_model=mover,
        enemy_models=(enemy_engagement_blocker,),
        end_pose=Pose.at(6.2, 1.0),
    )
    enemy_base_result = enemy_base_context.validate()
    enemy_engagement_result = enemy_engagement_context.validate()

    assert context.capabilities.can_move_through_models
    assert enemy_base_context.may_transit_enemy_models
    assert enemy_engagement_context.may_transit_enemy_engagement
    assert enemy_base_result.is_valid
    assert enemy_engagement_result.is_valid


def test_fly_take_to_the_skies_can_transit_enemy_models_and_engagement_range() -> None:
    mover = _model("fly-mover", 1.0, 1.0)
    enemy_base_blocker = _model("enemy-base-blocker", 3.0, 1.0)
    enemy_engagement_blocker = _model("enemy-engagement-blocker", 3.0, 2.5)
    context = _legality_context(
        keywords=("FLY", "INFANTRY"),
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )

    enemy_base_context = _path_context(
        context,
        moving_model=mover,
        enemy_models=(enemy_base_blocker,),
        end_pose=Pose.at(6.2, 1.0),
    )
    enemy_engagement_context = _path_context(
        context,
        moving_model=mover,
        enemy_models=(enemy_engagement_blocker,),
        end_pose=Pose.at(6.2, 1.0),
    )

    assert context.capabilities.can_move_through_models
    assert enemy_base_context.may_transit_enemy_models
    assert enemy_engagement_context.may_transit_enemy_engagement
    assert enemy_base_context.validate().is_valid
    assert enemy_engagement_context.validate().is_valid


def test_fly_normal_move_still_cannot_end_in_enemy_engagement_range_or_on_model() -> None:
    mover = _model("fly-mover", 1.0, 1.0)
    engagement_blocker = _model("enemy-engagement-blocker", 3.0, 2.5)
    model_blocker = _model("enemy-model-blocker", 3.0, 1.0)
    context = _normal_legality_context(keywords=("FLY", "INFANTRY"))

    engagement_result = _path_context(
        context,
        moving_model=mover,
        enemy_models=(engagement_blocker,),
        middle_pose=Pose.at(1.5, 1.0),
        end_pose=Pose.at(3.0, 1.0),
        sample_interval_inches=10.0,
    ).validate()
    model_overlap_result = _path_context(
        context,
        moving_model=mover,
        enemy_models=(model_blocker,),
        middle_pose=Pose.at(2.0, 1.0),
        end_pose=model_blocker.pose,
    ).validate()

    assert not engagement_result.is_valid
    assert engagement_result.violations[0].violation_code == "enemy_engagement_range_end_forbidden"
    assert engagement_result.violations[0].blocker_id == "enemy-engagement-blocker"
    assert not model_overlap_result.is_valid
    assert model_overlap_result.violations[0].violation_code == "end_on_model_overlap"
    assert model_overlap_result.violations[0].blocker_id == "enemy-model-blocker"


def test_fly_vehicle_can_transit_friendly_vehicle_monster_blocker() -> None:
    mover = _model("fly-vehicle-mover", 1.0, 1.0, radius=0.7)
    friendly_vehicle = _model("friendly-vehicle", 3.0, 1.0, radius=0.9)
    context = _normal_legality_context(keywords=("FLY", "VEHICLE"))

    result = _path_context(
        context,
        moving_model=mover,
        friendly_models=(friendly_vehicle,),
        friendly_vehicle_monster_model_ids=("friendly-vehicle",),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert context.capabilities.can_move_through_models
    assert context.capabilities.blocks_friendly_vehicle_monster_pass_through
    assert result.is_valid


def test_model_cannot_cross_battlefield_edge() -> None:
    mover = _model("mover", 1.0, 1.0)

    result = _path_context(
        _normal_legality_context(),
        moving_model=mover,
        middle_pose=Pose.at(0.6, 1.0),
        end_pose=Pose.at(0.4, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "battlefield_edge_crossed"


def test_non_fly_normal_and_advance_cannot_transit_enemy_model_base() -> None:
    mover = _model("mover", 1.0, 1.0)
    enemy = _model("enemy", 3.0, 1.0)

    for context in (
        _normal_legality_context(),
        _legality_context(
            movement_mode=MovementMode.ADVANCE,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            displacement_kind=ModelDisplacementKind.ADVANCE,
        ),
    ):
        path_context = _path_context(
            context,
            moving_model=mover,
            enemy_models=(enemy,),
            end_pose=Pose.at(5.0, 1.0),
        )
        result = path_context.validate()

        assert not path_context.may_transit_enemy_models
        assert not result.is_valid
        assert result.violations[0].violation_code == "enemy_model_base_crossed"
        assert result.violations[0].blocker_id == "enemy"


def test_vehicle_or_monster_normal_and_advance_can_transit_enemy_non_vehicle_models() -> None:
    mover = _model("vehicle-mover", 1.0, 1.0, radius=0.7)
    enemy_infantry = _model("enemy-infantry", 3.0, 1.0)

    for context in (
        _normal_legality_context(keywords=("VEHICLE",)),
        _legality_context(
            keywords=("MONSTER",),
            movement_mode=MovementMode.ADVANCE,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            displacement_kind=ModelDisplacementKind.ADVANCE,
        ),
    ):
        path_context = _path_context(
            context,
            moving_model=mover,
            enemy_models=(enemy_infantry,),
            end_pose=Pose.at(7.0, 1.0),
        )
        result = path_context.validate()

        assert path_context.may_transit_enemy_models
        assert result.is_valid


def test_vehicle_or_monster_normal_and_advance_cannot_transit_enemy_vehicle_or_monster() -> None:
    mover = _model("vehicle-mover", 1.0, 1.0, radius=0.7)
    enemy_vehicle = _model("enemy-vehicle", 3.0, 1.0, radius=0.9)

    for context in (
        _normal_legality_context(keywords=("VEHICLE",)),
        _legality_context(
            keywords=("MONSTER",),
            movement_mode=MovementMode.ADVANCE,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            displacement_kind=ModelDisplacementKind.ADVANCE,
        ),
    ):
        path_context = _path_context(
            context,
            moving_model=mover,
            enemy_models=(enemy_vehicle,),
            enemy_vehicle_monster_model_ids=(enemy_vehicle.model_id,),
            end_pose=Pose.at(7.0, 1.0),
        )
        result = path_context.validate()

        assert not result.is_valid
        assert result.violations[0].violation_code == "enemy_vehicle_monster_transit_forbidden"
        assert result.violations[0].blocker_id == enemy_vehicle.model_id


def test_model_cannot_path_through_terrain_smoke_blocker() -> None:
    mover = _model("mover", 1.0, 1.0)
    terrain = TerrainVolume(
        terrain_id="ruin-wall",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=3.0,
    )

    result = _path_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain=(terrain,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "terrain_collision"
    assert result.violations[0].blocker_id == "ruin-wall"


def test_normal_move_and_advance_cannot_transit_enemy_engagement_range() -> None:
    mover = _model("mover", 1.0, 1.0)
    enemy = _model("enemy", 3.0, 2.5)

    for context in (
        _normal_legality_context(),
        _legality_context(
            movement_mode=MovementMode.ADVANCE,
            movement_phase_action=MovementPhaseActionKind.ADVANCE,
            displacement_kind=ModelDisplacementKind.ADVANCE,
        ),
    ):
        result = _path_context(
            context,
            moving_model=mover,
            enemy_models=(enemy,),
            end_pose=Pose.at(5.0, 1.0),
        ).validate()

        assert not result.is_valid
        assert result.violations[0].violation_code == ("enemy_engagement_range_transit_forbidden")
        assert result.violations[0].blocker_id == "enemy"


def test_fall_back_can_transit_enemy_engagement_range_but_cannot_end_there() -> None:
    mover = _model("mover", 1.0, 1.0)
    enemy = _model("enemy", 5.0, 2.5)

    result = _path_context(
        _legality_context(
            movement_mode=MovementMode.FALL_BACK,
            movement_phase_action=MovementPhaseActionKind.FALL_BACK,
            displacement_kind=ModelDisplacementKind.FALL_BACK,
        ),
        moving_model=mover,
        enemy_models=(enemy,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "enemy_engagement_range_end_forbidden"
    assert result.violations[0].blocker_id == "enemy"


def test_normal_move_cannot_end_in_enemy_engagement_range() -> None:
    mover = _model("mover", 1.0, 1.0)
    enemy = _model("enemy", 5.0, 1.0)

    result = _path_context(
        _normal_legality_context(),
        moving_model=mover,
        enemy_models=(enemy,),
        middle_pose=Pose.at(1.5, 1.0),
        end_pose=Pose.at(3.0, 1.0),
        sample_interval_inches=10.0,
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "enemy_engagement_range_end_forbidden"


def test_charge_policy_allows_transit_and_ending_in_enemy_engagement_range() -> None:
    mover = _model("mover", 1.0, 1.0)
    enemy = _model("enemy", 3.0, 2.5)

    result = _path_context(
        _legality_context(
            movement_mode=MovementMode.CHARGE,
            movement_phase_action=None,
            displacement_kind=ModelDisplacementKind.CHARGE_MOVE,
        ),
        moving_model=mover,
        enemy_models=(enemy,),
        middle_pose=Pose.at(2.0, 1.0),
        end_pose=Pose.at(3.0, 1.0),
    ).validate()

    assert result.is_valid
    assert result.engagement_check_count > 0


def test_non_circular_base_movement_records_cost_free_rotation() -> None:
    mover = _model("oval-mover", 2.0, 2.0, base=OvalBase(length=2.0, width=1.0))
    result = _path_context(
        _normal_legality_context(),
        moving_model=mover,
        middle_pose=Pose.at(3.0, 2.0, facing_degrees=90.0),
        end_pose=Pose.at(4.0, 2.0, facing_degrees=90.0),
    ).validate()

    assert result.is_valid
    assert result.movement_distance_witness is not None
    assert result.movement_distance_witness.total_distance_inches == 2.0
    assert len(result.movement_distance_witness.rotation_events) == 1
    assert result.movement_distance_witness.rotation_events[0].facing_delta_degrees == 90.0


def _model(
    model_id: str,
    x: float,
    y: float,
    *,
    radius: float = 0.5,
    base: CircularBase | OvalBase | None = None,
) -> Model:
    return Model(
        model_id=model_id,
        pose=Pose.at(x, y),
        base=CircularBase(radius=radius) if base is None else base,
        volume=ModelVolume(height=2.0),
    )


def _normal_legality_context(
    *,
    keywords: tuple[str, ...] = ("INFANTRY",),
) -> MovementLegalityContext:
    return _legality_context(
        keywords=keywords,
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )


def _legality_context(
    *,
    movement_mode: MovementMode,
    movement_phase_action: MovementPhaseActionKind | None,
    displacement_kind: ModelDisplacementKind,
    keywords: tuple[str, ...] = ("INFANTRY",),
) -> MovementLegalityContext:
    return MovementLegalityContext.from_keywords(
        keywords=keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=movement_mode,
        movement_phase_action=None
        if movement_phase_action is None
        else movement_phase_action.value,
        displacement_kind=displacement_kind,
    )


def _path_context(
    legality_context: MovementLegalityContext,
    *,
    moving_model: Model,
    friendly_models: tuple[Model, ...] = (),
    enemy_models: tuple[Model, ...] = (),
    terrain: tuple[TerrainVolume, ...] = (),
    friendly_vehicle_monster_model_ids: tuple[str, ...] = (),
    enemy_vehicle_monster_model_ids: tuple[str, ...] = (),
    friendly_model_transit_blocker_ids: tuple[str, ...] = (),
    enemy_model_transit_blocker_ids: tuple[str, ...] = (),
    middle_pose: Pose | None = None,
    end_pose: Pose,
    sample_interval_inches: float = 0.5,
) -> PathValidationContext:
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
    return legality_context.to_path_validation_context(
        moving_model=moving_model,
        witness=witness,
        battlefield_width_inches=10.0,
        battlefield_depth_inches=10.0,
        friendly_models=friendly_models,
        enemy_models=enemy_models,
        terrain=terrain,
        friendly_vehicle_monster_model_ids=friendly_vehicle_monster_model_ids,
        enemy_vehicle_monster_model_ids=enemy_vehicle_monster_model_ids,
        friendly_model_transit_blocker_ids=friendly_model_transit_blocker_ids,
        enemy_model_transit_blocker_ids=enemy_model_transit_blocker_ids,
        sample_interval_inches=sample_interval_inches,
    )
