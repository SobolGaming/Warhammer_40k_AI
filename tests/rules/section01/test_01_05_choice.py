"""A minimal authenticated phase boundary drives actual highest/lowest decisions."""

import pytest

from tests.support.section01_fixtures import minimal_state
from tests.support.section02_fixtures import Section02Definitions
from warhammer40k_core.core.dice import DiceExpression, DiceRollSpec
from warhammer40k_core.core.dice_extremum import DiceExtremum, DiceExtremumSelection
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.decision_request import DecisionRequest
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.dice_extremum import request_dice_extremum
from warhammer40k_core.engine.phase_start_sequencing import phase_start_context
from warhammer40k_core.engine.timing_window_events import record_timing_window_boundary


@pytest.mark.parametrize("extremum", list(DiceExtremum))
@pytest.mark.parametrize("selected", [0, 1])
def test_01_05_07_active_player_chooses_tied_physical_die(
    section01_definitions: Section02Definitions, extremum: DiceExtremum, selected: int
) -> None:
    state = minimal_state(section01_definitions)
    decisions = DecisionController()
    record_timing_window_boundary(
        decisions=decisions,
        window=phase_start_context(state).timing_window,
        completed=False,
    )
    values = (5, 5, 2) if extremum is DiceExtremum.HIGHEST else (2, 2, 5)
    roll = DiceRollManager(state.game_id, event_log=decisions.event_log).roll_fixed(
        DiceRollSpec(
            DiceExpression(3, 6),
            reason="Core extreme",
            roll_type="core_dice_reference",
            actor_id="opponent",
        ),
        values,
    )
    request = request_dice_extremum(
        state=state,
        decisions=decisions,
        roll_state=roll,
        extremum=extremum,
        referring_source_rule_id="constructed:Core-reference",
        reference_id="one",
    )
    assert isinstance(request, DecisionRequest)
    assert request.actor_id == "owner"
    assert len(request.options) == 2
    assert request.options[selected].payload == {
        "component_index": selected,
        "component_id": f"{roll.original_result.roll_id}:component-{selected}",
        "value": values[selected],
    }
    decisions.submit_result(
        DecisionResult.for_request(
            result_id="choice",
            request=request,
            selected_option_id=request.options[selected].option_id,
        )
    )
    resolved = request_dice_extremum(
        state=state,
        decisions=decisions,
        roll_state=roll,
        extremum=extremum,
        referring_source_rule_id="constructed:Core-reference",
        reference_id="one",
    )
    assert isinstance(resolved, DiceExtremumSelection)
    assert resolved.component_index == selected
