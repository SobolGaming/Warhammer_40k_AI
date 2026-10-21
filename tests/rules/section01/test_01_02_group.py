"""A rules-group movement witness must include all and only its physical members."""

import pytest

from tests.support.section01_fixtures import minimal_state, place_units
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.engine.fight_movement_witness import (
    validate_fight_witness_matches_unit,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.geometry.pathing import PathWitness


@pytest.mark.parametrize("inventory", ["complete", "missing", "foreign"])
def test_01_02_group_move_uses_exact_model_inventory(
    section01_definitions: Section02Definitions, inventory: str
) -> None:
    unit = section01_definitions.unit()
    state = minimal_state(section01_definitions, unit)
    place_units(state)
    assert state.battlefield_state is not None
    placement = state.battlefield_state.unit_placement_by_id(unit.unit_instance_id)
    paths = tuple((m.model_instance_id, (m.pose, m.pose)) for m in placement.model_placements)
    if inventory == "missing":
        paths = paths[:-1]
    elif inventory == "foreign":
        paths = (*paths, ("not-a-member", paths[0][1]))
    witness = PathWitness.for_paths(paths)
    if inventory == "complete":
        validate_fight_witness_matches_unit(witness=witness, unit_placement=placement)
    else:
        with pytest.raises(GameLifecycleError):
            validate_fight_witness_matches_unit(witness=witness, unit_placement=placement)
