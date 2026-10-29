"""Shared immutable source resources never share mutable case graphs."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section17_fixtures import PRINCE, movement_scene


def test_native_case_units_states_and_decisions_are_fresh(
    section17_definitions: Section02Definitions,
) -> None:
    a, state_a, unit_a = movement_scene(section17_definitions, PRINCE)
    b, state_b, unit_b = movement_scene(section17_definitions, PRINCE)
    assert unit_a == unit_b
    assert unit_a is not unit_b
    assert unit_a.own_models[0] is not unit_b.own_models[0]
    assert state_a is not state_b
    assert state_a.army_definitions is not state_b.army_definitions
    assert a.lifecycle.decision_controller is not b.lifecycle.decision_controller
    assert state_a.battlefield_state is not state_b.battlefield_state
    assert state_a.to_payload() == state_b.to_payload()
