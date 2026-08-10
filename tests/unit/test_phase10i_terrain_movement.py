from __future__ import annotations

import json
import math
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.datasheet import BaseSizeDefinition
from warhammer40k_core.core.ruleset_descriptor import MovementMode, RulesetDescriptor
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.battlefield_state import ModelDisplacementKind
from warhammer40k_core.engine.endpoint_placement import terrain_endpoint_placement_violation
from warhammer40k_core.engine.mission_setup import MissionSetup
from warhammer40k_core.engine.movement_legality import MovementLegalityContext
from warhammer40k_core.engine.phases.movement import MovementPhaseActionKind
from warhammer40k_core.engine.unit_factory import ModelInstance, UnitInstance
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.model_geometry import ModelGeometry
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
from warhammer40k_core.geometry.terrain_classification import TerrainAreaClassification
from warhammer40k_core.geometry.volume import Model, ModelVolume
from warhammer40k_core.rules.mission_pack_import import (
    warhammer_event_companion_2026_07_mission_pack,
)


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


def test_semantic_permission_moves_over_terrain_features_at_or_below_height_limit() -> None:
    mover = _model("mover", 1.0, 1.0)
    base_context = _normal_legality_context(keywords=("VEHICLE",))
    context = replace(
        base_context,
        capabilities=replace(
            base_context.capabilities,
            can_move_over_friendly_vehicle_monster_models=True,
            terrain_as_if_absent_height_inches=4.0,
        ),
    )
    allowed_wall = ObstacleVolume(
        terrain_id="allowed-wall",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=4.0,
    )
    too_tall_wall = ObstacleVolume(
        terrain_id="too-tall-wall",
        bottom_center=Point3(3.0, 1.0, 0.0),
        width=1.0,
        depth=1.0,
        height=4.1,
    )

    allowed_result = _terrain_context(
        context,
        moving_model=mover,
        terrain=(allowed_wall,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()
    too_tall_result = _terrain_context(
        context,
        moving_model=mover,
        terrain=(too_tall_wall,),
        end_pose=Pose.at(5.0, 1.0),
    ).validate()

    assert allowed_result.is_valid
    assert allowed_result.segments[0].terrain_id == "allowed-wall"
    assert allowed_result.segments[0].traversal_mode.value == "freely_traversable"
    assert not too_tall_result.is_valid
    assert too_tall_result.violations[0].violation_code == "terrain_feature_transit_forbidden"
    assert too_tall_result.violations[0].terrain_id == "too-tall-wall"


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


def test_exact_event_dense_category_allows_horizontal_infantry_transit() -> None:
    mission_setup = _exact_event_companion_meatgrinder_setup()
    dense_feature = next(
        feature
        for feature in mission_setup.terrain_features
        if feature.classification is TerrainAreaClassification.DENSE
        and feature.feature_kind is TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
        and any(wall.height_inches > 2.0 for wall in feature.walls)
    )
    wall = next(wall for wall in dense_feature.walls if wall.height_inches > 2.0)
    start_pose, middle_pose, end_pose = _wall_crossing_poses(wall)

    assert dense_feature.source_id is not None
    assert "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in (
        dense_feature.source_id
    )
    assert wall.height_inches == 3.5

    for keyword in ("INFANTRY", "BEAST", "SWARM", "MOBILE"):
        mover = _model(
            f"dense-{keyword.lower()}-mover",
            start_pose.position.x,
            start_pose.position.y,
        )
        result = _terrain_context(
            _normal_legality_context(keywords=(keyword,)),
            moving_model=mover,
            terrain_features=(dense_feature,),
            middle_pose=middle_pose,
            end_pose=end_pose,
        ).validate()

        assert result.is_valid
        assert any(
            segment.terrain_id == f"{dense_feature.feature_id}:{wall.wall_id}"
            and segment.traversal_mode.value == "through_feature"
            for segment in result.segments
        )

    mounted = _model(
        "dense-mounted-mover",
        start_pose.position.x,
        start_pose.position.y,
    )
    mounted_result = _terrain_context(
        _normal_legality_context(keywords=("MOUNTED",)),
        moving_model=mounted,
        terrain_features=(dense_feature,),
        middle_pose=middle_pose,
        end_pose=end_pose,
    ).validate()
    assert not mounted_result.is_valid
    assert mounted_result.violations[0].violation_code == "terrain_feature_transit_forbidden"
    assert mounted_result.violations[0].terrain_id == (f"{dense_feature.feature_id}:{wall.wall_id}")


def test_exact_event_light_category_uses_two_inch_free_traversal() -> None:
    mission_setup = _exact_event_companion_meatgrinder_setup()
    light_feature = next(
        feature
        for feature in mission_setup.terrain_features
        if feature.classification is TerrainAreaClassification.LIGHT
        and feature.feature_kind is TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
        and any(wall.height_inches == 2.0 and wall.width_inches >= 3.5 for wall in feature.walls)
    )
    wall = next(
        wall
        for wall in light_feature.walls
        if wall.height_inches == 2.0 and wall.width_inches >= 3.5
    )
    start_pose, middle_pose, end_pose = _wall_crossing_poses(wall)
    mover = _model("light-vehicle-mover", start_pose.position.x, start_pose.position.y)

    result = _terrain_context(
        _normal_legality_context(keywords=("VEHICLE",)),
        moving_model=mover,
        terrain_features=(light_feature,),
        middle_pose=middle_pose,
        end_pose=end_pose,
    ).validate()

    assert light_feature.source_id is not None
    assert "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in (
        light_feature.source_id
    )
    assert result.is_valid
    assert any(
        segment.terrain_id == f"{light_feature.feature_id}:{wall.wall_id}"
        and segment.traversal_mode.value == "freely_traversable"
        for segment in result.segments
    )


def test_light_classification_allows_mounted_through_three_inch_feature() -> None:
    feature = replace(
        _ruins_blocking_wall_feature(),
        feature_id="tall-light-policy-feature",
        feature_kind=TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY,
        classification=TerrainAreaClassification.LIGHT,
    )
    wall = feature.walls[0]
    start_pose = Pose.at(wall.center_x_inches - 4.0, wall.center_y_inches)
    middle_pose = Pose.at(wall.center_x_inches, wall.center_y_inches, 1.5)
    end_pose = Pose.at(wall.center_x_inches + 4.0, wall.center_y_inches)
    mover = _model("tall-light-mounted-mover", start_pose.position.x, start_pose.position.y)

    result = _terrain_context(
        _normal_legality_context(keywords=("MOUNTED",)),
        moving_model=mover,
        terrain_features=(feature,),
        middle_pose=middle_pose,
        end_pose=end_pose,
    ).validate()

    assert result.is_valid
    assert any(
        segment.terrain_id == f"{feature.feature_id}:{wall.wall_id}"
        and segment.traversal_mode.value == "through_feature"
        and segment.vertical_distance_inches > 0.0
        for segment in result.segments
    )


def test_exact_event_companion_ruins_apply_keyword_specific_wall_traversal() -> None:
    mission_setup = _exact_event_companion_meatgrinder_setup()
    ruins = next(
        feature
        for feature in mission_setup.terrain_features
        if feature.feature_kind is TerrainFeatureKind.RUINS
        and len(feature.floors) == 3
        and any(
            wall.wall_id == "ground-long-solid-wall" and wall.width_inches >= 2.5
            for wall in feature.walls
        )
    )
    wall = next(wall for wall in ruins.walls if wall.wall_id == "ground-long-solid-wall")
    middle_wall = next(
        candidate for candidate in ruins.walls if candidate.wall_id == "first-long-solid-wall"
    )
    start_pose, middle_pose, end_pose = _wall_crossing_poses(wall)

    assert ruins.feature_id.startswith("purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-")
    assert ruins.source_id is not None
    assert "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in (
        ruins.source_id
    )
    assert wall.bottom_z_inches + wall.height_inches == middle_wall.bottom_z_inches

    for keywords in (
        ("INFANTRY",),
        ("BEAST",),
        ("SWARM",),
        ("MOBILE",),
    ):
        mover = _model(
            f"{keywords[0].lower()}-mover",
            start_pose.position.x,
            start_pose.position.y,
        )
        result = _terrain_context(
            _normal_legality_context(keywords=keywords),
            moving_model=mover,
            terrain_features=mission_setup.terrain_features,
            middle_pose=middle_pose,
            end_pose=end_pose,
        ).validate()

        assert result.is_valid
        assert any(segment.traversal_mode.value == "through_feature" for segment in result.segments)

    for keywords in (
        ("MOUNTED",),
        ("VEHICLE",),
        ("MONSTER",),
        ("BELISARIUS_CAWL",),
        ("IMPERIUM_PRIMARCH",),
    ):
        mover = _model(
            f"{keywords[0].lower()}-mover",
            start_pose.position.x,
            start_pose.position.y,
        )
        result = _terrain_context(
            _normal_legality_context(keywords=keywords),
            moving_model=mover,
            terrain_features=mission_setup.terrain_features,
            middle_pose=middle_pose,
            end_pose=end_pose,
        ).validate()

        assert not result.is_valid
        assert result.violations[0].violation_code == "terrain_feature_transit_forbidden"
        assert result.violations[0].terrain_id == f"{ruins.feature_id}:{middle_wall.wall_id}"


def test_exact_event_dense_ruin_mobile_vertical_path_climbs_instead_of_passing_through() -> None:
    mission_setup = _exact_event_companion_meatgrinder_setup()
    ruins = next(
        feature
        for feature in mission_setup.terrain_features
        if feature.classification is TerrainAreaClassification.DENSE
        and feature.feature_kind is TerrainFeatureKind.RUINS
        and len(feature.floors) == 3
        and any(wall.wall_id == "ground-long-solid-wall" for wall in feature.walls)
    )
    wall = next(wall for wall in ruins.walls if wall.wall_id == "ground-long-solid-wall")
    aligned_walls = tuple(
        candidate for candidate in ruins.walls if candidate.wall_id.endswith("long-solid-wall")
    )
    wall_stack_top = max(
        candidate.bottom_z_inches + candidate.height_inches for candidate in aligned_walls
    )
    assert wall_stack_top == 8.0
    rotation_radians = math.radians(wall.rotation_degrees)
    normal_x = -math.sin(rotation_radians)
    normal_y = math.cos(rotation_radians)
    clearance_inches = 3.0
    start_pose = Pose.at(
        wall.center_x_inches - normal_x * clearance_inches,
        wall.center_y_inches - normal_y * clearance_inches,
    )
    middle_pose = Pose.at(wall.center_x_inches, wall.center_y_inches, wall_stack_top)
    end_pose = Pose.at(
        wall.center_x_inches + normal_x * clearance_inches,
        wall.center_y_inches + normal_y * clearance_inches,
    )
    mover = _model("dense-mobile-vertical-mover", start_pose.position.x, start_pose.position.y)

    result = _terrain_context(
        _normal_legality_context(keywords=("MOBILE",)),
        moving_model=mover,
        terrain_features=(ruins,),
        middle_pose=middle_pose,
        end_pose=end_pose,
    ).validate()

    assert result.is_valid
    matching_segments = tuple(
        segment
        for segment in result.segments
        if segment.terrain_id
        in {f"{ruins.feature_id}:{candidate.wall_id}" for candidate in aligned_walls}
    )
    assert matching_segments
    assert any(segment.traversal_mode.value == "climb" for segment in matching_segments)
    assert all(
        segment.traversal_mode.value in {"climb", "freely_traversable"}
        for segment in matching_segments
    )
    assert all(segment.vertical_distance_inches > 0.0 for segment in matching_segments)


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


def test_rotated_floor_rejects_25mm_base_inside_aabb_but_overhanging_surface() -> None:
    mover, feature, floor, end_pose, base_radius_inches = _rotated_floor_overhang_case()
    surface = feature.support_surfaces(no_overhang_required=True)[0]
    min_x, min_y, max_x, max_y = surface.bounds()

    assert min_x <= end_pose.position.x - base_radius_inches
    assert end_pose.position.x + base_radius_inches <= max_x
    assert min_y <= end_pose.position.y - base_radius_inches
    assert end_pose.position.y + base_radius_inches <= max_y

    result = _terrain_context(
        _normal_legality_context(),
        moving_model=mover,
        terrain_features=(feature,),
        middle_pose=Pose.at(floor.center_x_inches, floor.center_y_inches, 3.0),
        end_pose=end_pose,
    ).validate()

    assert not result.is_valid
    assert (
        result.violations[0].violation_code
        == TerrainEndpointViolationCode.BASE_OVERHANGS_SUPPORT_SURFACE.value
    )
    assert result.violations[0].surface_id == floor.floor_id


def test_shared_endpoint_placement_rejects_rotated_floor_aabb_overhang() -> None:
    mover, feature, floor, end_pose, _base_radius_inches = _rotated_floor_overhang_case()
    unit = _endpoint_placement_unit(
        unit_instance_id="rotated-floor-endpoint-unit",
        model_instance_id=mover.model_id,
        keywords=("VEHICLE",),
    )

    violation = terrain_endpoint_placement_violation(
        model=replace(mover, pose=end_pose),
        unit=unit,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        terrain_features=(feature,),
        violation_code="rotated_floor_overhang",
        placement_label="Test placement",
    )

    assert violation is not None
    assert violation.violation_code == "rotated_floor_overhang"
    assert violation.message == "Test placement base overhangs support surface."
    assert violation.model_instance_id == mover.model_id
    assert violation.blocker_id == floor.floor_id


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
        rules_footprint_polygon=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=4.0,
            depth_inches=4.0,
        ).footprint_polygon,
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


def test_take_to_the_skies_flies_over_exact_event_companion_dense_non_ruin() -> None:
    mission_setup = _exact_event_companion_meatgrinder_setup()
    dense_non_ruin = next(
        feature
        for feature in mission_setup.terrain_features
        if feature.feature_kind is TerrainFeatureKind.BATTLEFIELD_DEBRIS_AND_STATUARY
        and len(feature.walls) == 1
        and feature.walls[0].height_inches == 3.5
        and feature.walls[0].width_inches >= 3.5
    )
    wall = dense_non_ruin.walls[0]
    start_pose, _, end_pose = _wall_crossing_poses(wall)
    middle_pose = Pose.at(wall.center_x_inches, wall.center_y_inches, wall.height_inches)
    mover = _model("fly-mover", start_pose.position.x, start_pose.position.y)

    assert dense_non_ruin.feature_id.startswith(
        "purge-the-foe-vs-purge-the-foe-layout-1-terrain-area-"
    )
    assert dense_non_ruin.source_id is not None
    assert "gw_event_companion_v1_purge_the_foe_vs_purge_the_foe_meatgrinder_layout_a" in (
        dense_non_ruin.source_id
    )

    result = _terrain_context(
        _normal_legality_context(
            keywords=("FLY", "INFANTRY"),
            movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        ),
        moving_model=mover,
        terrain_features=mission_setup.terrain_features,
        middle_pose=middle_pose,
        end_pose=end_pose,
    ).validate()

    assert result.is_valid
    air_path_segments = tuple(
        segment for segment in result.segments if segment.traversal_mode.value == "air_path"
    )
    assert air_path_segments
    assert all(segment.air_path_measurement_pending for segment in air_path_segments)
    assert sum(segment.vertical_distance_inches for segment in air_path_segments) > 0.0


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


def _rotated_floor_overhang_case() -> tuple[
    Model,
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    Pose,
    float,
]:
    base_radius_inches = 25.0 / (2.0 * 25.4)
    mover = Model(
        model_id="rotated-floor-endpoint-unit:model-001",
        pose=Pose.at(1.0, 1.0),
        base=CircularBase(radius=base_radius_inches),
        volume=ModelVolume(height=2.0),
    )
    floor_center_x = 3.0
    floor_center_y = 3.0
    floor = TerrainFloorDefinition(
        floor_id="rotated-upper-floor",
        center_x_inches=floor_center_x,
        center_y_inches=floor_center_y,
        bottom_z_inches=3.0,
        width_inches=4.0,
        depth_inches=2.0,
        thickness_inches=0.12,
        rotation_degrees=45.0,
    )
    feature = TerrainFeatureDefinition(
        feature_id="rotated-floor-feature",
        feature_kind=TerrainFeatureKind.HILLS,
        footprint_center_x_inches=floor_center_x,
        footprint_center_y_inches=floor_center_y,
        footprint_width_inches=6.0,
        footprint_depth_inches=6.0,
        rules_footprint_polygon=_display_geometry(
            center_x_inches=floor_center_x,
            center_y_inches=floor_center_y,
            width_inches=6.0,
            depth_inches=6.0,
        ).footprint_polygon,
        display_geometry=_display_geometry(
            center_x_inches=floor_center_x,
            center_y_inches=floor_center_y,
            width_inches=6.0,
            depth_inches=6.0,
        ),
        floors=(floor,),
    )
    return mover, feature, floor, Pose.at(4.5, 4.5, 3.0), base_radius_inches


def _endpoint_placement_unit(
    *,
    unit_instance_id: str,
    model_instance_id: str,
    keywords: tuple[str, ...],
) -> UnitInstance:
    datasheet_id = "endpoint-placement-datasheet"
    model_profile_id = f"{datasheet_id}-profile"
    base_size = BaseSizeDefinition.circular(25.0)
    model = ModelInstance(
        model_instance_id=model_instance_id,
        datasheet_id=datasheet_id,
        model_profile_id=model_profile_id,
        name="Endpoint placement model",
        characteristics=(
            CharacteristicValue.from_raw(Characteristic.WOUNDS, 1),
            CharacteristicValue.from_raw(Characteristic.LEADERSHIP, 7),
        ),
        base_size=base_size,
        geometry=ModelGeometry.from_base_size(
            base_size,
            keywords=keywords,
            geometry_source_id=model_profile_id,
        ),
        starting_wounds=1,
        wounds_remaining=1,
        wargear_ids=(),
        source_ids=(f"source:{model_profile_id}",),
    )
    return UnitInstance(
        unit_instance_id=unit_instance_id,
        datasheet_id=datasheet_id,
        name="Endpoint placement unit",
        keywords=keywords,
        faction_keywords=(),
        datasheet_abilities=(),
        datasheet_source_ids=(f"source:{datasheet_id}",),
        own_models=(model,),
        wargear_selections=(),
    )


def _exact_event_companion_meatgrinder_setup() -> MissionSetup:
    return MissionSetup.from_mission_pack(
        mission_pack=warhammer_event_companion_2026_07_mission_pack(),
        mission_pool_entry_id="mission-purge-the-foe-vs-purge-the-foe-layout-1",
        terrain_layout_id="purge-the-foe-vs-purge-the-foe-layout-1",
        attacker_player_id="player-a",
        defender_player_id="player-b",
    )


def _wall_crossing_poses(
    wall: TerrainWallDefinition,
) -> tuple[Pose, Pose, Pose]:
    rotation_radians = math.radians(wall.rotation_degrees)
    normal_x = -math.sin(rotation_radians)
    normal_y = math.cos(rotation_radians)
    clearance_inches = max(wall.depth_inches / 2.0 + 0.75, 1.25)
    start_pose = Pose.at(
        wall.center_x_inches - normal_x * clearance_inches,
        wall.center_y_inches - normal_y * clearance_inches,
    )
    middle_pose = Pose.at(wall.center_x_inches, wall.center_y_inches)
    end_pose = Pose.at(
        wall.center_x_inches + normal_x * clearance_inches,
        wall.center_y_inches + normal_y * clearance_inches,
    )
    return start_pose, middle_pose, end_pose


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
        rules_footprint_polygon=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=width_inches,
            depth_inches=depth_inches,
        ).footprint_polygon,
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
        rules_footprint_polygon=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=6.0,
            depth_inches=6.0,
        ).footprint_polygon,
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
        rules_footprint_polygon=_display_geometry(
            center_x_inches=3.0,
            center_y_inches=1.0,
            width_inches=6.0,
            depth_inches=6.0,
        ).footprint_polygon,
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
    movement_mode: MovementMode = MovementMode.NORMAL,
) -> MovementLegalityContext:
    return MovementLegalityContext.from_keywords(
        keywords=keywords,
        ruleset_descriptor=RulesetDescriptor.warhammer_40000_eleventh(),
        movement_mode=movement_mode,
        movement_phase_action=MovementPhaseActionKind.NORMAL_MOVE.value,
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
