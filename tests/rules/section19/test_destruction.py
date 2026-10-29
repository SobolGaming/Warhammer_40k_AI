"""19.02: actual casualty production only completes the frozen attached unit last."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene, destroy
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_destroyed_hooks import (
    physical_component_destruction_completion_events_for_phase,
    unit_destruction_completion_events_for_phase,
)


@pytest.mark.parametrize("first", ["bodyguard", "leader", "support"])
def test_destroyed_trigger_waits_for_last_starting_attached_model_in_any_component_order(
    section19_definitions: Section02Definitions,
    first: str,
) -> None:
    s = attached_scene(section19_definitions, support=True)
    decisions = DecisionController()
    starting = s.state.starting_attached_unit_records[0]
    order = (first, *[r for r in ("bodyguard", "leader", "support") if r != first])
    model_order = tuple(mid for role in order for mid in s.component(role).own_model_ids())
    for i, mid in enumerate(model_order, 1):
        destroy(s, decisions, mid)
        completed = unit_destruction_completion_events_for_phase(
            state=s.state, event_log=decisions.event_log, completed_phase=BattlePhase.SHOOTING
        )
        assert len(completed) == int(i == len(model_order))
        if completed:
            assert completed[0][1]["target_unit_instance_id"] == starting.attached_unit_instance_id
            assert completed[0][1]["model_instance_id"] == mid
        else:
            assert s.view.attached_unit == s.formation
    components = physical_component_destruction_completion_events_for_phase(
        state=s.state, event_log=decisions.event_log, completed_phase=BattlePhase.SHOOTING
    )
    assert len(components) == 3
    assert s.state.starting_attached_unit_records == [starting]
    assert s.view.alive_models() == ()
