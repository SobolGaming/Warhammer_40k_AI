"""Shared engagement numerical edge reaches the real Charge selection consumer."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import axis_endpoint_within_range, geometry
from tests.support.section11_fixtures import begin, move_target, session_for, state_case
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("origin", [2, 10])
@pytest.mark.parametrize("delta", [-0.001, 0, 0.001])
def test_inclusive_engagement_prevents_charge_at_translated_native_edge(
    section11_definitions: Section02Definitions,
    origin: float,
    delta: float,
) -> None:
    state, unit, enemy = state_case(section11_definitions, origin=origin, gap=2 + delta)
    first = geometry(unit, (Pose.at(origin, 10),))[0]
    second = geometry(enemy, (Pose.at(origin, 10),), enemy=True)[0]
    x = axis_endpoint_within_range(
        origin, first.base.max_radius(), second.base.max_radius(), 2 + delta
    )
    move_target(state, enemy, Pose.at(x, 10))
    request = begin(session_for(section11_definitions, state))
    assert (unit.unit_instance_id in {o.option_id for o in request.options}) is (delta > 0)
