"""The authoritative physical placement owns exact witness membership."""

from typing import cast

import pytest
from tests.phase11c_command_phase_helpers import battle_state

from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pathing import PathWitness


def test_placement_witness_membership_is_order_independent_and_fail_fast() -> None:
    state = battle_state()
    assert state.battlefield_state is not None
    placement = RulesUnitPlacement.from_battlefield(
        view=rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:intercessor-unit-1"),
        battlefield_state=state.battlefield_state,
    )
    paths = tuple((p.model_instance_id, (p.pose, p.pose)) for p in placement.model_placements)
    assert placement.matches_witness_models(PathWitness.for_paths(paths))
    assert placement.matches_witness_models(PathWitness.for_paths(tuple(reversed(paths))))
    assert not placement.matches_witness_models(PathWitness.for_paths(paths[1:]))
    with pytest.raises(GameLifecycleError, match="membership requires PathWitness"):
        placement.matches_witness_models(cast(PathWitness, object()))
