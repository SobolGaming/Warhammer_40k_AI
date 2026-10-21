"""Core wargear grant lifetime on native attached physical components."""

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene, destroy, grant_definitions, has_lethal
from warhammer40k_core.engine.decision_controller import DecisionController


def test_bearer_owned_item_survives_other_casualty_but_stops_after_bearer_loss(
    section22_definitions: Section02Definitions,
) -> None:
    # The selected native Lord carries a real bolt pistol; this generic unit-wide
    # keyword grant is an explicit Core Wargear input, not its native pistol rule.
    s = attached_scene(grant_definitions(section22_definitions, "leader", wargear=True))
    decisions = DecisionController()
    assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    destroy(s, decisions, s.body.own_model_ids()[0])
    assert all(has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
    destroy(s, decisions, s.leader.own_model_ids()[0])
    assert len(s.view.alive_models()) == len(s.body.own_models) - 1
    assert all(not has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
