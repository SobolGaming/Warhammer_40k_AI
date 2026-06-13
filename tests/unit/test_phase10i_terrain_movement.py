from __future__ import annotations

import json
from typing import cast

from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import (
    PathWitness,
    TerrainEndpointViolationCode,
    TerrainPathLegalityContext,
    TerrainPathLegalityContextPayload,
    TerrainPathLegalityResult,
    TerrainPathLegalityResultPayload,
)
from warhammer40k_core.geometry.pose import Point3, Pose
from warhammer40k_core.geometry.terrain import (
    ObstacleVolume,
    TerrainFeatureDefinition,
    TerrainFeatureKind,
    TerrainFloorDefinition,
    TerrainVolume,
    TerrainWallDefinition,
)
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


def test_terrain_path_legality_accepts_explicit_zero_displacement_no_op_witness() -> None:
    mover = _model("mover", 1.0, 1.0)
    witness = PathWitness.for_paths(((mover.model_id, (mover.pose, mover.pose)),))
    context = _normal_legality_context().to_terrain_path_legality_context(
        moving_model=mover,
        witness=witness,
        terrain=(),
        terrain_features=(),
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    )

    result = context.validate()

    assert result.is_valid
    assert result.sampled_pose_count == 2
    assert result.segments == ()


def test_terrain_path_legality_accepts_two_pose_straight_segment() -> None:
    mover = _model("mover", 1.0, 1.0)
    low_terrain = TerrainVolume(
        terrain_id="low-crater",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=2.0,
    )
    witness = PathWitness.for_paths(((mover.model_id, (mover.pose, Pose.at(5.0, 1.0))),))
    context = _normal_legality_context().to_terrain_path_legality_context(
        moving_model=mover,
        witness=witness,
        terrain=(low_terrain,),
        terrain_features=(),
        contact_footprint_available=True,
        sample_interval_inches=0.5,
    )

    result = context.validate()

    assert result.is_valid
    assert result.sampled_pose_count == 9
    assert result.segments[0].terrain_id == "low-crater"


def test_model_cannot_pass_through_wall_without_traversal_permission() -> None:
    mover = _model("vehicle-mover", 1.0, 1.0)
    ruins = _ruins_blocking_wall_feature()

    result = _terrain_context(
        _normal_legality_context(keywords=("VEHICLE",)),
        moving_model=mover,
        terrain_features=(ruins,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert result.violations[0].violation_code == "terrain_feature_transit_forbidden"
    assert result.violations[0].terrain_id == "ruin-wall-test:center-wall"


def test_low_wall_can_be_moved_over_as_if_not_there() -> None:
    mover = _model("mover", 1.0, 1.0)
    low_wall = ObstacleVolume(
        terrain_id="low-wall",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=2.0,
    )

    result = _terrain_context(
        _normal_legality_context(keywords=("VEHICLE",)),
        moving_model=mover,
        terrain=(low_wall,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert result.is_valid
    assert result.segments[0].traversal_mode.value == "freely_traversable"


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
    assert result.violations[0].violation_code == TerrainEndpointViolationCode.ENDS_MID_CLIMB.value
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


def test_infantry_can_move_through_ruins_wall_but_cannot_end_inside_wall() -> None:
    mover = _model("infantry-mover", 1.0, 1.0)
    ruins = _ruins_blocking_wall_feature()

    result = _terrain_context(
        _normal_legality_context(keywords=("INFANTRY",)),
        moving_model=mover,
        terrain_features=(ruins,),
        middle_pose=Pose.at(2.0, 1.0),
        end_pose=Pose.at(3.0, 1.0),
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value
    )
    assert result.violations[0].terrain_id == "ruin-wall-test:center-wall"


def test_model_cannot_end_embedded_in_ruins_floor_volume() -> None:
    mover = _model("infantry-floor-embedded", 1.0, 1.0)
    ruins = _ruins_feature(upper_width_inches=4.0, upper_depth_inches=4.0)

    result = _terrain_context(
        _normal_legality_context(keywords=("INFANTRY",)),
        moving_model=mover,
        terrain_features=(ruins,),
        middle_pose=Pose.at(2.0, 1.0, 0.06),
        end_pose=Pose.at(3.0, 1.0, 0.06),
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value
    )
    assert result.violations[0].terrain_id == "ruin-alpha:ground"


def test_model_cannot_end_on_barricade_or_debris_top() -> None:
    for feature_kind in (
        TerrainFeatureKind.BARRICADE_AND_FUEL_PIPES,
        TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
    ):
        mover = _model(f"{feature_kind.value}-mover", 1.0, 1.0)
        feature = _support_feature(
            feature_id=feature_kind.value,
            feature_kind=feature_kind,
            z_inches=1.0,
            width_inches=4.0,
            depth_inches=4.0,
        )

        result = _terrain_context(
            _normal_legality_context(),
            moving_model=mover,
            terrain_features=(feature,),
            middle_pose=Pose.at(2.0, 1.0, 1.0),
            end_pose=Pose.at(3.0, 1.0, 1.0),
        ).validate()

        assert not result.is_valid
        assert (
            result.violations[0].violation_code
            == TerrainEndpointViolationCode.END_ON_FORBIDDEN_TERRAIN.value
        )


def test_model_can_end_on_hill_top_when_base_is_fully_supported() -> None:
    mover = _model("hill-mover", 1.0, 1.0)
    hill = _support_feature(
        feature_id="hill-alpha",
        feature_kind=TerrainFeatureKind.HILLS,
        z_inches=3.0,
        width_inches=4.0,
        depth_inches=4.0,
    )

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain_features=(hill,),
        middle_pose=Pose.at(2.0, 1.0, 3.0),
        end_pose=Pose.at(3.0, 1.0, 3.0),
    ).validate()

    assert result.is_valid


def test_model_cannot_end_on_hill_top_when_base_overhangs() -> None:
    mover = _model("hill-overhang-mover", 1.0, 1.0)
    hill = _support_feature(
        feature_id="hill-alpha",
        feature_kind=TerrainFeatureKind.HILLS,
        z_inches=3.0,
        width_inches=0.75,
        depth_inches=0.75,
    )

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain_features=(hill,),
        middle_pose=Pose.at(2.0, 1.0, 3.0),
        end_pose=Pose.at(3.0, 1.0, 3.0),
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.BASE_OVERHANGS_SUPPORT_SURFACE.value
    )


def test_eligible_keywords_can_end_on_upper_ruins_floor_without_overhang() -> None:
    ruins = _ruins_feature(upper_width_inches=4.0, upper_depth_inches=4.0)

    for keywords in (("INFANTRY",), ("BEAST",), ("FLY",)):
        mover = _model(f"{keywords[0].lower()}-upper-ruins-mover", 1.0, 1.0)
        result = _terrain_context(
            _normal_legality_context(keywords=keywords),
            moving_model=mover,
            terrain_features=(ruins,),
            middle_pose=Pose.at(2.0, 1.0, 3.0),
            end_pose=Pose.at(3.0, 1.0, 3.0),
        ).validate()

        assert result.is_valid


def test_non_eligible_model_cannot_end_on_upper_ruins_floor() -> None:
    mover = _model("vehicle-upper-ruins-mover", 1.0, 1.0)
    ruins = _ruins_feature(upper_width_inches=4.0, upper_depth_inches=4.0)

    result = _terrain_context(
        _normal_legality_context(keywords=("VEHICLE",)),
        moving_model=mover,
        terrain_features=(ruins,),
        middle_pose=Pose.at(2.0, 1.0, 3.0),
        end_pose=Pose.at(3.0, 1.0, 3.0),
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.UPPER_FLOOR_KEYWORD_FORBIDDEN.value
    )


def test_upper_ruins_floor_endpoint_fails_when_base_overhangs() -> None:
    mover = _model("infantry-upper-ruins-overhang", 1.0, 1.0)
    ruins = _ruins_feature(upper_width_inches=0.75, upper_depth_inches=0.75)

    result = _terrain_context(
        _normal_legality_context(keywords=("INFANTRY",)),
        moving_model=mover,
        terrain_features=(ruins,),
        middle_pose=Pose.at(2.0, 1.0, 3.0),
        end_pose=Pose.at(3.0, 1.0, 3.0),
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.BASE_OVERHANGS_SUPPORT_SURFACE.value
    )


def test_missing_contact_footprint_returns_manual_geometry_required_for_no_overhang() -> None:
    mover = _model("manual-contact-mover", 1.0, 1.0)
    hill = _support_feature(
        feature_id="hill-alpha",
        feature_kind=TerrainFeatureKind.HILLS,
        z_inches=3.0,
        width_inches=4.0,
        depth_inches=4.0,
    )

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain_features=(hill,),
        middle_pose=Pose.at(2.0, 1.0, 3.0),
        end_pose=Pose.at(3.0, 1.0, 3.0),
        contact_footprint_available=False,
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.MANUAL_GEOMETRY_REQUIRED.value
    )


def test_model_cannot_end_on_elevated_feature_without_support_surface() -> None:
    mover = _model("unsupported-hill-mover", 1.0, 1.0)
    hill = TerrainFeatureDefinition(
        feature_id="hill-no-floor",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=3.0,
        footprint_center_y_inches=1.0,
        footprint_width_inches=4.0,
        footprint_depth_inches=4.0,
        display_geometry=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=4.0,
            depth_inches=4.0,
        ),
    )

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain_features=(hill,),
        middle_pose=Pose.at(2.0, 1.0, 3.0),
        end_pose=Pose.at(3.0, 1.0, 3.0),
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.MODEL_CANNOT_BE_PLACED_AT_ENDPOINT.value
    )
    assert result.violations[0].terrain_id == "hill-no-floor"


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


def _display_geometry(
    *,
    center_x_inches: float,
    center_y_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainDisplayGeometry:
    return TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=center_x_inches,
        center_y_inches=center_y_inches,
        width_inches=width_inches,
        depth_inches=depth_inches,
        display_template_id="test_axis_aligned_terrain",
    )


def _support_feature(
    *,
    feature_id: str,
    feature_kind: TerrainFeatureKind,
    z_inches: float,
    width_inches: float,
    depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id=feature_id,
        feature_kind=feature_kind,
        footprint_center_x_inches=3.0,
        footprint_center_y_inches=1.0,
        footprint_width_inches=width_inches,
        footprint_depth_inches=depth_inches,
        display_geometry=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=width_inches,
            depth_inches=depth_inches,
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="top",
                center_x_inches=3.0,
                center_y_inches=1.0,
                bottom_z_inches=z_inches,
                width_inches=width_inches,
                depth_inches=depth_inches,
                thickness_inches=0.12,
            ),
        ),
    )


def _ruins_feature(
    *,
    upper_width_inches: float,
    upper_depth_inches: float,
) -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="ruin-alpha",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=3.0,
        footprint_center_y_inches=1.0,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        display_geometry=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=6.0,
            depth_inches=6.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="north-wall",
                center_x_inches=3.0,
                center_y_inches=3.94,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=0.12,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=3.0,
                center_y_inches=1.0,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
            TerrainFloorDefinition(
                floor_id="upper",
                center_x_inches=3.0,
                center_y_inches=1.0,
                bottom_z_inches=3.0,
                width_inches=upper_width_inches,
                depth_inches=upper_depth_inches,
                thickness_inches=0.12,
            ),
        ),
    )


def _ruins_blocking_wall_feature() -> TerrainFeatureDefinition:
    return TerrainFeatureDefinition(
        feature_id="ruin-wall-test",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=3.0,
        footprint_center_y_inches=1.0,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        display_geometry=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=6.0,
            depth_inches=6.0,
        ),
        walls=(
            TerrainWallDefinition(
                wall_id="center-wall",
                center_x_inches=3.0,
                center_y_inches=1.0,
                bottom_z_inches=0.0,
                width_inches=1.0,
                depth_inches=1.0,
                height_inches=3.0,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=3.0,
                center_y_inches=1.0,
                bottom_z_inches=0.0,
                width_inches=6.0,
                depth_inches=6.0,
                thickness_inches=0.12,
            ),
        ),
    )


def _normal_legality_context(
    *,
    keywords: tuple[str, ...] = ("INFANTRY",),
) -> MovementLegalityContext:
    return MovementLegalityContext.from_keywords(
        keywords=keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=MovementMode.NORMAL,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE,
        displacement_kind=ModelDisplacementKind.NORMAL_MOVE,
    )


def _terrain_context(
    legality_context: MovementLegalityContext,
    *,
    moving_model: Model,
    terrain: tuple[TerrainVolume, ...] = (),
    terrain_features: tuple[TerrainFeatureDefinition, ...] = (),
    middle_pose: Pose | None = None,
    end_pose: Pose,
    contact_footprint_available: bool = True,
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
        terrain_features=terrain_features,
        contact_footprint_available=contact_footprint_available,
        sample_interval_inches=0.5,
    )
