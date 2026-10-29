"""19.01 and its nested override: one persistent rules unit and frozen strength."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section19_fixtures import attached_scene
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id, rules_unit_views_for_state


@pytest.mark.parametrize("support", [False, True])
@pytest.mark.parametrize("body_alive", [0, 1, 5])
def test_component_aliases_keep_one_unit_and_original_strength_after_bodyguard_loss(
    section19_definitions: Section02Definitions,
    support: bool,
    body_alive: int,
) -> None:
    s = attached_scene(section19_definitions, support=support)
    original = s.state.starting_strength_record_for_unit(s.view.unit_instance_id)
    frozen = s.state.starting_attached_unit_records[0]
    s.set_living("bodyguard", body_alive)
    expected = body_alive + 1 + int(support)
    for alias in (s.view.unit_instance_id, *s.view.component_unit_instance_ids):
        view = rules_unit_view_by_id(state=s.state, unit_instance_id=alias)
        assert view.unit_instance_id == frozen.attached_unit_instance_id
        assert len(view.alive_models()) == expected
        assert view.attached_unit == s.formation
    assert (
        len([v for v in rules_unit_views_for_state(state=s.state) if v.owner_player_id == "owner"])
        == 1
    )
    assert s.state.starting_strength_record_for_unit(s.view.unit_instance_id) == original
    assert original.starting_model_count == 6 + int(support)
    assert s.state.starting_attached_unit_records == [frozen]
    # Typed GameState boundary only: no claim of complete native lifecycle restore.
    restored = GameState.from_payload(s.state.to_payload())
    assert restored.to_payload() == s.state.to_payload()
    assert (
        rules_unit_view_by_id(
            state=restored, unit_instance_id=s.leader.unit_instance_id
        ).unit_instance_id
        == s.view.unit_instance_id
    )


def test_cases_share_only_definitions_and_create_fresh_mutable_graphs(
    section19_definitions: Section02Definitions,
) -> None:
    a, b = (
        attached_scene(section19_definitions, support=True),
        attached_scene(section19_definitions, support=True),
    )
    assert a.state.to_payload() == b.state.to_payload()
    assert a.state is not b.state
    assert a.body is not b.body
    assert a.body.own_models[0] is not b.body.own_models[0]
    a.set_living("bodyguard", 0)
    assert len(b.view.alive_models()) == 7
