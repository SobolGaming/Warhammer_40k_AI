"""03.02.02 ordinary and oversized disembark at the production geometry evaluator."""

from dataclasses import replace

import pytest

from tests.support.section02_fixtures import CHAOS_SPAWN, MAULERFIEND, Section02Definitions
from tests.support.section03_fixtures import native_state, placement, scenario
from warhammer40k_core.engine.transport_disembark_geometry import (
    append_disembark_endpoint_violations,
)
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportOperationViolation
from warhammer40k_core.geometry.base import CircularBase
from warhammer40k_core.geometry.pose import Pose
from warhammer40k_core.geometry.volume import Model, ModelVolume


@pytest.mark.parametrize(
    ("radius", "gap", "engaged", "valid"),
    [
        (0.5, 2, False, True),
        (0.5, 2.001, False, False),
        (2, 1, False, True),
        (2, 1.001, False, False),
        (2, 1, True, False),
    ],
)
def test_disembark_ordinary_whole_three_or_proven_large_one_and_unengaged(
    section03_definitions: Section02Definitions,
    radius: float,
    gap: float,
    engaged: bool,
    valid: bool,
) -> None:
    # Explicit constructed geometry values, using native identity/ownership only.
    unit = section03_definitions.unit(MAULERFIEND)
    enemy = section03_definitions.unit(CHAOS_SPAWN, identity="enemy", army_id="enemy")
    x = 10 + 2 + radius + gap
    state = native_state(
        section03_definitions,
        unit,
        enemy=enemy,
        enemy_poses=(Pose.at(x + radius + 2, 20), Pose.at(x + radius + 2, 22.5))
        if engaged
        else (Pose.at(40, 20), Pose.at(40, 22.5)),
    )
    assert state.battlefield_state is not None
    state.battlefield_state = replace(
        state.battlefield_state,
        placed_armies=tuple(
            a for a in state.battlefield_state.placed_armies if a.player_id == "opponent"
        ),
    )
    model = Model(unit.own_model_ids()[0], Pose.at(x, 20), CircularBase(radius), ModelVolume(2))
    transport = Model("constructed-transport", Pose.at(10, 20), CircularBase(2), ModelVolume(3))
    violations: list[TransportOperationViolation] = []
    append_disembark_endpoint_violations(
        violations=violations,
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit=unit,
        attempted_placement=placement(unit, (model.pose,)),
        models=(model,),
        transport_models=(transport,),
        distance_inches=3,
        battlefield_width_inches=60,
        battlefield_depth_inches=44,
        terrain_features=(),
        objective_markers=(),
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
    )
    assert (not violations) is valid
    if not valid:
        assert {v.violation_code.value for v in violations} == {
            "enemy_engagement_range" if engaged else "disembark_distance"
        }
