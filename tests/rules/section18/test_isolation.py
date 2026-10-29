"""Only immutable selected definitions and mission metadata are shared."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section18_fixtures import transport_scene


def test_cases_own_fresh_units_cargo_state_decisions_and_placements(
    section18_definitions: Section02Definitions,
) -> None:
    a = transport_scene(section18_definitions)
    b = transport_scene(section18_definitions)
    assert a.state.to_payload() == b.state.to_payload()
    assert a.state is not b.state
    assert a.passenger is not b.passenger
    assert a.passenger.own_models[0] is not b.passenger.own_models[0]
    assert a.cargo is not b.cargo
    assert a.state.battlefield_state is not b.state.battlefield_state
    assert a.session.lifecycle.decision_controller is not b.session.lifecycle.decision_controller
