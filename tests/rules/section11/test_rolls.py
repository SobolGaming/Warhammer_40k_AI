"""11.02.01 and FAQ59: native distances consumed by rolled budgets."""

from itertools import product

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section04_fixtures import pending
from tests.support.section11_fixtures import (
    events,
    modifier,
    move_target,
    roll,
    select,
    session_for,
    state_case,
    targets,
)
from warhammer40k_core.engine.charge_declaration import ChargeRollRequest, ChargeRollResult
from warhammer40k_core.engine.charge_targets import charge_target_candidates
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.geometry.pose import Pose


@pytest.mark.parametrize(("a", "b"), list(product(range(1, 7), repeat=2)))
def test_all_physical_two_d6_outcomes_consume_real_native_distance(
    section11_definitions: Section02Definitions,
    a: int,
    b: int,
) -> None:
    state, unit, enemy = state_case(section11_definitions, gap=2.001, origin=2)
    candidate = next(
        c
        for c in charge_target_candidates(
            state=state,
            unit_instance_id=unit.unit_instance_id,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
        )
        if c.target_unit_instance_id == enemy.unit_instance_id
    )
    assert candidate.is_legal
    request = ChargeRollRequest(
        "constructed:roll",
        state.game_id,
        1,
        "owner",
        unit.unit_instance_id,
        "constructed:selection",
        "constructed:result",
    )
    dice = DiceRollManager("constructed:fixed-two-d6").roll_fixed(request.spec, (a, b))
    from warhammer40k_core.engine.phases.charge import (
        _reachable_charge_target_distances,
    )

    reachable = _reachable_charge_target_distances(
        state=state,
        unit_instance_id=unit.unit_instance_id,
        maximum_distance_inches=a + b,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
    )
    result = ChargeRollResult.from_roll_state(
        request=request, roll_state=dice, reachable_target_distances_inches=reachable
    )
    assert result.value == a + b
    assert result.movement_budget.maximum_distance_inches == a + b
    assert result.move_available is (a + b > 2)
    assert result.reachable_target_distances_inches == (
        {} if a + b == 2 else {enemy.unit_instance_id: candidate.closest_distance_inches}
    )
    assert result.roll_state.original_result.values == (a, b)


@pytest.mark.parametrize("delta", [-1, 0, 1])
def test_modified_roll_recomputes_public_target_distance_boundary(
    section11_definitions: Section02Definitions,
    delta: int,
) -> None:
    # Position after learning the immutable roll, then request the next native
    # target choice. This constructed boundary tests the current target producer.
    state, unit, enemy = state_case(section11_definitions, gap=3)
    session = session_for(section11_definitions, state)
    select(session, unit)
    original = roll(session)
    assert state.battlefield_state is not None
    start = (
        state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
        .model_placements[0]
        .pose
    )
    current_gap = 3
    move_target(state, enemy, Pose.at(start.position.x + original.value - current_gap + 0.25, 10))
    modifier(state, unit.unit_instance_id, delta)
    from warhammer40k_core.engine.charge_target_continuation import current_charge_targets

    handler = session.lifecycle._charge_phase_handler  # pyright: ignore[reportPrivateUsage]
    assert handler is not None
    budget, candidates = current_charge_targets(state=state, handler=handler)
    assert budget.maximum_distance_inches == max(0, original.value + delta)
    assert (enemy.unit_instance_id in candidates) is (delta == 1 and original.value < 12)
    assert roll(session).roll_state == original.roll_state


def test_budget_shrink_after_selection_requests_new_targets_then_continues(
    section11_definitions: Section02Definitions,
) -> None:
    state, unit, enemy = state_case(section11_definitions, gap=5)
    modifier(state, unit.unit_instance_id, 12)
    from tests.support.section04_fixtures import add_enemy

    replacement = add_enemy(section11_definitions, state, x=10, y=14.5)
    session = session_for(section11_definitions, state)
    select(session, unit)
    targets(session, (enemy.unit_instance_id,))
    original = roll(session)
    modifier(
        state,
        unit.unit_instance_id,
        4 - original.movement_budget.maximum_distance_inches,
        kind="modify_move_distance",
        identity="constructed:later-distance-loss",
    )
    from tests.support.section11_fixtures import choose, propose, witness

    status = propose(
        session,
        unit.unit_instance_id,
        (enemy.unit_instance_id,),
        witness(state, unit.unit_instance_id, 4.25),
        result_id="stale-budget",
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    assert status.status_kind is LifecycleStatusKind.INVALID
    session.advance_until_decision_or_terminal()
    request = pending(session)
    assert request.decision_type == "select_target_replacement", status
    assert not events(session, "charge_move_completed")
    assert roll(session).roll_state == original.roll_state
    option = next(
        o
        for o in request.options
        if isinstance(o.payload, dict)
        and o.payload.get("target_ids") == [replacement.unit_instance_id]
    )
    choose(session, option.option_id, result_id="replace")
    assert pending(session).decision_type == "submit_movement_proposal"
    status = propose(
        session,
        unit.unit_instance_id,
        (replacement.unit_instance_id,),
        witness(state, unit.unit_instance_id, 0, 2.5),
        result_id="replacement-move",
    )
    from warhammer40k_core.engine.phase import LifecycleStatusKind

    assert status.status_kind is not LifecycleStatusKind.INVALID, status
    assert len(events(session, "charge_move_completed")) == 1
    assert len(events(session, "charge_roll_resolved")) == 1
