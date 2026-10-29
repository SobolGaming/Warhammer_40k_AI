"""19.04 native leading grant spans components, persists after bodyguard death."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene, has_lethal


@pytest.mark.parametrize("support", [False, True])
@pytest.mark.parametrize("body_alive", [0, 1, 5])
def test_native_leading_ability_applies_to_every_living_component_after_bodyguard_loss(
    section19_definitions: Section02Definitions,
    support: bool,
    body_alive: int,
) -> None:
    s = attached_scene(section19_definitions, support=support)
    s.set_living("bodyguard", body_alive)
    living = s.view.alive_models()
    assert living
    assert all(has_lethal(s, m.model_instance_id) for m in living)
    assert not section19_definitions.weapon("000004078:bolt-pistol").abilities


@pytest.mark.parametrize("support", [False, True])
def test_native_grant_stops_when_source_is_destroyed_outside_attack(
    section19_definitions: Section02Definitions, support: bool
) -> None:
    s = attached_scene(section19_definitions, support=support)
    assert has_lethal(s, s.body.own_model_ids()[0])
    s.set_living("leader", 0)
    assert all(not has_lethal(s, m.model_instance_id) for m in s.view.alive_models())
