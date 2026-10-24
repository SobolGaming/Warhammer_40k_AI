"""Native physical flight and walker Core input; whole witnessed paths."""

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import native_state, scenario
from tests.support.section24_fixtures import SERPENT
from tests.unit_keyword_helpers import with_unit_keywords
from warhammer40k_core.core.ruleset_descriptor import MovementMode
from warhammer40k_core.engine.phases.movement import resolve_normal_move
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize("hover", [False, True])
@pytest.mark.parametrize("distance", [12, 12.01, 14, 14.01])
def test_hover_keeps_native_flight_budget_without_two_inch_subtraction(
    section24_definitions: Section02Definitions, hover: bool, distance: float
) -> None:
    own = section24_definitions.unit(SERPENT)
    if hover:
        own = with_unit_keywords(own, keywords=(*own.keywords, "HOVER"))
    state = native_state(section24_definitions, own, (Pose.at(10, 10),))
    result = resolve_normal_move(
        scenario=scenario(state),
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        unit_placement=scenario(state).battlefield_state.unit_placement_by_id(own.unit_instance_id),
        state=state,
        movement_mode=MovementMode.FLY_TAKE_TO_SKIES,
        path_witness=PathWitness.for_paths(
            ((own.own_model_ids()[0], (Pose.at(10, 10), Pose.at(10 + distance, 10))),)
        ),
    )
    assert result.is_valid is (distance <= (14 if hover else 12))
    witness = result.path_validation_results[0].movement_distance_witness
    assert witness is not None
    assert witness.budget is not None
    assert witness.budget.max_distance_inches == (14 if hover else 12)
    assert state.battlefield_state == scenario(state).battlefield_state
