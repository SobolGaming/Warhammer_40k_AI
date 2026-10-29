"""03.04: reciprocal endpoint engagement; transient paths grant no engagement."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, Section02Definitions
from tests.support.section03_fixtures import geometry, native_state
from warhammer40k_core.engine.phases.movement_model import (
    MovementActionAvailabilityContext,
    MovementPhaseActionKind,
)
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pathing import PathValidationContext, PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("horizontal", "vertical", "engaged"),
    [(2, 0, True), (2.001, 0, False), (2, 5, True), (2, 5.001, False)],
)
def test_one_member_engages_both_units_and_changes_available_actions(
    section03_definitions: Section02Definitions, horizontal: float, vertical: float, engaged: bool
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    a, b = geometry(unit, (Pose.at(10, 10), Pose.at(10, 12.5)))
    assert isinstance(a.base, CircularBase)
    x = 10 + 2 * a.base.radius + horizontal
    z = a.volume.height + vertical if vertical else 0
    state = native_state(
        section03_definitions,
        unit,
        (a.pose, b.pose),
        enemy=enemy,
        enemy_poses=(Pose.at(x, 10, z=z), Pose.at(x + 2.5, 10, z=z)),
    )
    for candidate in (unit, enemy):
        assert (
            unit_within_enemy_engagement_range(
                state=state, unit_instance_id=candidate.unit_instance_id
            )
            is engaged
        )
    result = MovementActionAvailabilityContext(
        state.ruleset_descriptor_hash,
        unit.unit_instance_id,
        "owner",
        enemy_engagement_model_ids=enemy.own_model_ids()[:1] if engaged else (),
    ).evaluate()
    expected = (
        {MovementPhaseActionKind.REMAIN_STATIONARY, MovementPhaseActionKind.FALL_BACK}
        if engaged
        else {
            MovementPhaseActionKind.REMAIN_STATIONARY,
            MovementPhaseActionKind.NORMAL_MOVE,
            MovementPhaseActionKind.ADVANCE,
        }
    )
    assert set(result.available_actions) == expected


def test_faq05_transit_does_not_turn_endpoint_into_engagement(
    section03_definitions: Section02Definitions,
) -> None:
    unit = section03_definitions.unit(CHAOS_SPAWN)
    moving, enemy = geometry(unit, (Pose.at(8, 10), Pose.at(13, 10)))
    end = Pose.at(18, 10)
    result = PathValidationContext(
        moving_model=moving,
        witness=PathWitness.for_paths(((moving.model_id, (moving.pose, end)),)),
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        enemy_models=(enemy,),
        may_transit_enemy_models=True,
        enemy_engagement_horizontal_inches=2,
        enemy_engagement_vertical_inches=5,
    ).validate()
    assert result.is_valid
    assert not moving.is_within_engagement_range(enemy, horizontal_inches=2, vertical_inches=5)
    assert not replace(moving, pose=end).is_within_engagement_range(
        enemy, horizontal_inches=2, vertical_inches=5
    )
