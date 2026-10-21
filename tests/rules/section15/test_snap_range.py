"""15.09 unit range policy: real native envelopes and explicit visibility input."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import axis_endpoint_within_range, native_state, scenario
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.phases.shooting_targeting import (
    _snap_shooting_type_allowed_for_unit_target,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(
    ("extra", "visible", "expected"),
    [(0, True, True), (0.001, True, False), (0, False, False), (0.001, False, False)],
)
def test_snap_requires_visible_target_within_inclusive_twenty_four_inches(
    section15_definitions: Section02Definitions, extra: float, visible: bool, expected: bool
) -> None:
    d = section15_definitions
    unit = d.unit("000004078")
    enemy = d.unit("000004078", identity="enemy", army_id="enemy")
    geometry = unit.own_models[0].geometry
    assert len(geometry.parts) == 1
    assert geometry.parts[0].footprint_kind.value == "circular"
    radius = geometry.parts[0].radius_x_inches
    edge = axis_endpoint_within_range(10, radius, radius, 24)
    state = native_state(
        d, unit, (Pose.at(10, 10),), enemy=enemy, enemy_poses=(Pose.at(edge + extra, 10),)
    )
    # This isolates range admission from native LOS production, which the public
    # Overwatch declaration separately exercises. No visible model is invented.
    candidate: dict[str, JsonValue] = {
        "target_visible_model_ids": list(enemy.own_model_ids()) if visible else []
    }
    actual = _snap_shooting_type_allowed_for_unit_target(
        scenario=scenario(state),
        candidate=candidate,
        rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=unit.unit_instance_id),
        target_unit_id=enemy.unit_instance_id,
    )
    assert actual is expected
