from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, LORD_EXULTANT, Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from warhammer40k_core.core.ruleset_descriptor import TerrainFeatureKind
from warhammer40k_core.core.terrain_display import TerrainDisplayGeometry
from warhammer40k_core.engine.shooting_targets import (
    ShootingTargetViolationCode,
    shooting_target_candidate_for_model,
)
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.terrain import (
    TerrainFeatureDefinition,
    TerrainFloorDefinition,
    TerrainWallDefinition,
)


def wall(*, x: float, depth: float) -> TerrainFeatureDefinition:
    display = TerrainDisplayGeometry.axis_aligned_rectangle(
        center_x_inches=x,
        center_y_inches=10,
        width_inches=0.2,
        depth_inches=depth,
        display_template_id="section04:wall",
    )
    return TerrainFeatureDefinition(
        feature_id="section04:ruin",
        feature_kind=TerrainFeatureKind.RUINS,
        footprint_center_x_inches=x,
        footprint_center_y_inches=10,
        footprint_width_inches=0.2,
        footprint_depth_inches=depth,
        rules_footprint_polygon=display.footprint_polygon,
        display_geometry=display,
        walls=(
            TerrainWallDefinition(
                wall_id="solid",
                center_x_inches=x,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=0.2,
                depth_inches=depth,
                height_inches=8,
            ),
        ),
        floors=(
            TerrainFloorDefinition(
                floor_id="ground",
                center_x_inches=x,
                center_y_inches=10,
                bottom_z_inches=0,
                width_inches=0.2,
                depth_inches=depth,
                thickness_inches=0.1,
            ),
        ),
    )


@pytest.mark.parametrize("blocked", [False, True])
def test_faq03_in_range_does_not_imply_visible(
    section04_definitions: Section02Definitions, blocked: bool
) -> None:
    d = section04_definitions
    attacker = d.unit(LORD_EXULTANT)
    target = d.unit(LORD_EXULTANT, army_id="enemy", identity="target")
    state = native_state(
        d, attacker, (Pose.at(10, 10),), enemy=target, enemy_poses=(Pose.at(18, 10),)
    )
    terrain = (wall(x=14, depth=8),) if blocked else ()
    assert state.battlefield_state is not None
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=terrain))
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_model_ids()[0],
        weapon_profile=d.weapon(f"{LORD_EXULTANT}:bolt-pistol"),
        target_unit_id=target.unit_instance_id,
        terrain_features=terrain,
    )
    assert result.target_in_range_model_ids == target.own_model_ids()
    assert result.is_legal is not blocked
    assert result.target_visible_model_ids == (() if blocked else target.own_model_ids())
    assert result.violation_code is (ShootingTargetViolationCode.NOT_VISIBLE if blocked else None)


def test_faq30_different_native_models_supply_range_and_visibility(
    section04_definitions: Section02Definitions,
) -> None:
    d = section04_definitions
    attacker = d.unit(LORD_EXULTANT)
    target = d.unit(CHAOS_SPAWN, army_id="enemy", identity="target")
    state = native_state(
        d,
        attacker,
        (Pose.at(10, 10),),
        enemy=target,
        enemy_poses=(Pose.at(23, 10), Pose.at(24.2, 13)),
    )
    terrain = (wall(x=21, depth=2.4),)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(replace(state.battlefield_state, terrain_features=terrain))
    result = shooting_target_candidate_for_model(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        attacker_unit=attacker,
        attacker_model_instance_id=attacker.own_model_ids()[0],
        weapon_profile=d.weapon(f"{LORD_EXULTANT}:bolt-pistol"),
        target_unit_id=target.unit_instance_id,
        terrain_features=terrain,
    )
    assert result.is_legal, result
    assert result.target_in_range_model_ids == (target.own_model_ids()[0],)
    assert result.target_visible_model_ids == (target.own_model_ids()[1],)
    assert set(result.target_visible_model_ids).isdisjoint(result.target_in_range_model_ids)
    assert result.line_of_sight_witness is not None
