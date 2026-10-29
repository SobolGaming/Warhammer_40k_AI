"""Two current FAQ clauses: units and model OC are not exclusive to one objective."""

from dataclasses import replace

from tests.order109_helpers import SOURCE, control_session

from warhammer40k_core.core.objectives import ObjectiveMarker
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlContext,
    ObjectiveControlTiming,
    resolve_objective_control,
)
from warhammer40k_core.engine.phase import BattlePhase
from warhammer40k_core.engine.unit_objective_control import current_unit_objective_control


def test_same_model_contributes_its_complete_oc_to_each_objective_in_range() -> None:
    # A direct definition query uses canonical real models. Existing Order109
    # facade families separately verify frozen control and mission consumers.
    session = control_session(source_oc=2)
    state = session.lifecycle.state
    assert state is not None
    context = ObjectiveControlContext.from_game_state(
        state, timing=ObjectiveControlTiming.PHASE_END, phase=BattlePhase.FIGHT
    )
    placement = context.scenario.battlefield_state.unit_placement_by_id(SOURCE)
    model = placement.model_placements[0]
    markers = tuple(
        ObjectiveMarker(
            objective_marker_id=f"order135:objective:{i}",
            name=f"Objective {i}",
            x_inches=model.pose.position.x + dx,
            y_inches=model.pose.position.y,
        )
        for i, dx in enumerate((-3.2, 3.2))
    )
    record = resolve_objective_control(
        replace(
            context,
            objective_markers=markers,
            terrain_objectives=(),
            objective_terrain_areas=(),
            state=None,
        )
    )
    assert len(record.results) == 2
    contributions = tuple(
        {c.model_instance_id: c.effective_objective_control for c in r.contributors}
        for r in record.results
    )
    assert contributions[0][model.model_instance_id] == 2
    assert contributions[1][model.model_instance_id] == 2
    assert all(
        next(s.score for s in r.scores if s.player_id == "player-a")
        == sum(c.effective_objective_control for c in r.contributors if c.player_id == "player-a")
        for r in record.results
    )
    control = current_unit_objective_control(state=state, unit_instance_id=SOURCE)
    assert all(r.controlled_by_player_id == "player-a" for r in record.results)
    assert all(control.controls(r) for r in record.results)
