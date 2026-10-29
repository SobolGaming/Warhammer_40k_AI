"""An attached Core contract uses the best living native Leadership profile."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import (
    CHAOS_SPAWN,
    LORD_EXULTANT,
    Section02Definitions,
)
from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.engine.abilities import AbilityCatalogIndex
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.battle_shock import (
    battle_shock_leadership_target_for_rules_unit,
)
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id


@pytest.mark.parametrize("leader_alive", [False, True])
def test_01_06_best_living_member_sets_unit_threshold(
    section01_definitions: Section02Definitions, leader_alive: bool
) -> None:
    body = section01_definitions.unit(CHAOS_SPAWN, identity="body")
    leader = section01_definitions.unit(LORD_EXULTANT, identity="leader")
    assert {m.characteristic(Characteristic.LEADERSHIP).final for m in body.own_models} == {7}
    assert leader.own_models[0].characteristic(Characteristic.LEADERSHIP).final == 6
    if not leader_alive:
        leader = replace(leader, own_models=(replace(leader.own_models[0], wounds_remaining=0),))
    state = minimal_state(section01_definitions, body, leader)
    formation = AttachedUnitFormation(
        "attached-unit:section02:leadership",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:Core-Leadership",
        attachment_source_ids=("constructed:Core-attachment",),
    )
    state.army_definitions[:] = [replace(state.army_definitions[0], attached_units=(formation,))]
    view = rules_unit_view_by_id(state=state, unit_instance_id=formation.attached_unit_instance_id)
    target = battle_shock_leadership_target_for_rules_unit(
        view,
        current_model_ids=tuple(m.model_instance_id for m in view.alive_models()),
        ability_index=AbilityCatalogIndex.from_records(()),
        state=state,
    )
    assert target == (6 if leader_alive else 7)
