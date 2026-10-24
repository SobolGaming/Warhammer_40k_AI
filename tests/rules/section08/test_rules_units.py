"""Each army rules unit is tested once, including attached/off-board units."""

from dataclasses import replace

import pytest

from tests.support.section01_fixtures import minimal_state, place_units, reserve_unit
from tests.support.section02_fixtures import Section02Definitions
from tests.support.section08_fixtures import command_state, damage_to_count, requests
from warhammer40k_core.engine.attached_unit_formation import AttachedUnitFormation
from warhammer40k_core.engine.command_battle_shock_candidates import (
    command_battle_shock_candidate_inventory,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_strength_inventory import starting_strength_records_for_army


@pytest.mark.parametrize(("body_alive", "required"), [(3, False), (2, True), (1, True)])
def test_attached_components_receive_one_canonical_test_using_combined_strength(
    section08_definitions: Section02Definitions, body_alive: int, required: bool
) -> None:
    body = section08_definitions.unit(identity="body")
    leader = section08_definitions.unit("000004078", identity="leader")
    state = minimal_state(section08_definitions, body, leader)
    formation = AttachedUnitFormation(
        "attached-unit:section02:section08",
        body.unit_instance_id,
        (leader.unit_instance_id,),
        component_unit_instance_ids=tuple(sorted((body.unit_instance_id, leader.unit_instance_id))),
        source_id="constructed:s08:attached-boundary",
        attachment_source_ids=(leader.datasheet_abilities[-2].source_id,),
    )
    army = replace(state.army_definitions[0], attached_units=(formation,))
    state.army_definitions[:] = [army]
    state.starting_strength_records[:] = starting_strength_records_for_army(army)
    place_units(state)
    damage_to_count(state, body_alive)
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.COMMAND)
    actual = requests(state)
    assert len(actual) == int(required)
    inventory = command_battle_shock_candidate_inventory(state, "owner", ())
    assert len(inventory) == 1
    assert inventory[0].unit_instance_id == formation.attached_unit_instance_id
    assert inventory[0].below_half_strength_context.starting_model_count == 6
    assert inventory[0].below_half_strength_context.current_model_count == body_alive + 1
    if actual:
        assert actual[0].unit_instance_id == formation.attached_unit_instance_id


def test_required_reserve_unit_is_not_silently_omitted(
    section08_definitions: Section02Definitions,
) -> None:
    state = command_state(section08_definitions)
    damage_to_count(state, 5)
    unit = next(a for a in state.army_definitions if a.player_id == "owner").units[0]
    reserve_unit(state, unit)
    assert state.battlefield_state is not None
    state.replace_battlefield_state(
        replace(
            state.battlefield_state,
            placed_armies=tuple(
                a for a in state.battlefield_state.placed_armies if a.player_id != "owner"
            ),
        )
    )
    actual = requests(state)
    assert len(actual) == 1
    assert actual[0].unit_instance_id == unit.unit_instance_id
