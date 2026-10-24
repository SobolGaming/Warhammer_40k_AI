"""09.05/06/07 witnessed budgets, endpoints and real Advance die results."""

from typing import TypedDict, cast

import pytest

from tests.support.section02_fixtures import Section02Definitions
from tests.support.section03_fixtures import grid, native_state, paths, scenario
from tests.support.section09_fixtures import choose, events, movement_case, propose, select
from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.ruleset_descriptor import RulesetDescriptor
from warhammer40k_core.engine.advance_roll import (
    AdvanceRollRequest,
    AdvanceRollResult,
    AdvanceRollResultPayload,
)
from warhammer40k_core.engine.battlefield_state import BattlefieldScenario, UnitPlacement
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.phases.movement import (
    FallBackModeKind,
    resolve_advance_move,
    resolve_fall_back_move,
    resolve_normal_move,
)
from warhammer40k_core.engine.phases.movement_state import (
    AdvanceMoveResolution,
    FallBackActionResult,
    NormalMoveResolution,
)
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


class MoveInputs(TypedDict):
    scenario: BattlefieldScenario
    ruleset_descriptor: RulesetDescriptor
    unit_placement: UnitPlacement
    path_witness: PathWitness


@pytest.mark.parametrize("datasheet", ["000004090", "000000968"])
@pytest.mark.parametrize("delta", [-0.001, 0, 0.001])
@pytest.mark.parametrize("action", ["normal", "advance", "fall_back"])
def test_each_native_model_uses_m_plus_only_its_advance_roll(
    section09_definitions: Section02Definitions,
    datasheet: str,
    delta: float,
    action: str,
) -> None:
    unit = section09_definitions.unit(datasheet)
    starts = grid(unit)
    value = unit.own_models[0].characteristic(Characteristic.MOVEMENT)
    assert isinstance(value, CharacteristicValue)
    distance = float(value.final) + (4 if action == "advance" else 0) + delta
    ends = tuple(Pose.at(p.position.x, p.position.y + distance) for p in starts)
    state = native_state(section09_definitions, unit, starts)
    board = scenario(state)
    kwargs: MoveInputs = {
        "scenario": board,
        "ruleset_descriptor": state.runtime_ruleset_descriptor(),
        "unit_placement": board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        "path_witness": paths(unit, starts, ends),
    }
    before = state.to_payload()
    result: NormalMoveResolution | AdvanceMoveResolution | FallBackActionResult
    if action == "advance":
        request = AdvanceRollRequest.for_unit(
            request_id="constructed:advance",
            game_id=state.game_id,
            battle_round=1,
            player_id="owner",
            unit_instance_id=unit.unit_instance_id,
        )
        roll = AdvanceRollResult.from_roll_state(
            request=request,
            roll_state=DiceRollManager(state.game_id).roll_fixed(request.spec, (4,)),
        )
        result = resolve_advance_move(**kwargs, advance_roll=roll)
        assert result.advance_roll.value == 4
    elif action == "fall_back":
        # Budget evaluator boundary; eligibility has a separate real engaged scene.
        result = resolve_fall_back_move(**kwargs, fall_back_mode=FallBackModeKind.ORDERED_RETREAT)
    else:
        result = resolve_normal_move(**kwargs)
    assert result.is_valid is (delta <= 0)
    assert state.to_payload() == before
    if delta > 0:
        assert any(
            v.violation_code == "movement_distance_exceeded"
            for r in result.path_validation_results
            for v in r.violations
        )


@pytest.mark.parametrize("action", ["normal_move", "advance", "fall_back:ordered_retreat"])
def test_public_path_rejection_preserves_geometry_and_legal_retry_finishes(
    section09_definitions: Section02Definitions,
    action: str,
) -> None:
    session, state, unit = movement_case(
        section09_definitions, engaged=action.startswith("fall_back")
    )
    request = choose(session, select(session, unit), action)
    assert request.decision_type == "submit_movement_proposal"
    original = state.battlefield_state
    illegal = (Pose.at(10, 35), Pose.at(12.5, 35))
    status = propose(session, request, unit, illegal, result_id="too-far")
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == original
    assert state.movement_phase_state is not None
    assert tuple(state.movement_phase_state.moved_unit_ids) == ()
    retry = session.lifecycle.decision_controller.queue.pending_requests[0]
    ends = (
        (Pose.at(10, 6), Pose.at(12.5, 6))
        if action.startswith("fall_back")
        else (Pose.at(10, 11), Pose.at(12.5, 11))
    )
    legal = propose(session, retry, unit, ends, result_id="legal-path")
    assert legal.status_kind is not LifecycleStatusKind.INVALID
    assert unit.unit_instance_id in state.movement_phase_state.moved_unit_ids
    assert state.battlefield_state is not None
    assert (
        tuple(
            p.pose
            for p in state.battlefield_state.unit_placement_by_id(
                unit.unit_instance_id
            ).model_placements
        )
        == ends
    )
    assert len(events(session, "movement_activation_completed")) == 1


@pytest.mark.parametrize("action", ["normal_move", "advance"])
def test_unengaged_start_does_not_allow_engaged_endpoint(
    section09_definitions: Section02Definitions,
    action: str,
) -> None:
    unit = section09_definitions.unit("000004090")
    enemy = section09_definitions.unit("000004090", army_id="enemy", identity="enemy")
    state = native_state(section09_definitions, unit, enemy=enemy)
    assert state.battlefield_state is not None
    from dataclasses import replace

    enemy = next(a for a in state.army_definitions if a.player_id == "opponent").units[0]
    enemy_placement = state.battlefield_state.unit_placement_by_id(enemy.unit_instance_id)
    # The typed evaluator below uses a newly constructed scene, not a stale request.
    state.replace_battlefield_state(
        state.battlefield_state.with_unit_placement(
            replace(
                enemy_placement,
                model_placements=tuple(
                    replace(p, pose=Pose.at(10 + i * 2.5, 17))
                    for i, p in enumerate(enemy_placement.model_placements)
                ),
            )
        )
    )
    board = scenario(state)
    starts = grid(unit)
    ends = (Pose.at(10, 13.2), Pose.at(12.5, 13.2))
    kwargs: MoveInputs = {
        "scenario": board,
        "ruleset_descriptor": state.runtime_ruleset_descriptor(),
        "unit_placement": board.battlefield_state.unit_placement_by_id(unit.unit_instance_id),
        "path_witness": paths(unit, starts, ends),
    }
    result: NormalMoveResolution | AdvanceMoveResolution | FallBackActionResult
    if action == "advance":
        r = AdvanceRollRequest.for_unit(
            request_id="edge",
            game_id=state.game_id,
            battle_round=1,
            player_id="owner",
            unit_instance_id=unit.unit_instance_id,
        )
        result = resolve_advance_move(
            **kwargs,
            advance_roll=AdvanceRollResult.from_roll_state(
                request=r, roll_state=DiceRollManager(state.game_id).roll_fixed(r.spec, (1,))
            ),
        )
    else:
        result = resolve_normal_move(**kwargs)
    assert not result.is_valid
    assert any(
        v.violation_code == "enemy_engagement_range_end_forbidden"
        for r in result.path_validation_results
        for v in r.violations
    )


@pytest.mark.parametrize("game_suffix", ["one", "two", "three"])
def test_native_advance_roll_is_one_d6_and_does_not_repeat_on_path_retry(
    section09_definitions: Section02Definitions,
    game_suffix: str,
) -> None:
    session, state, unit = movement_case(section09_definitions)
    state.game_id += game_suffix
    request = choose(session, select(session, unit), "advance")
    rolls = events(session, "advance_roll_resolved")
    assert len(rolls) == 1
    roll = rolls[0]["advance_roll"]
    assert isinstance(roll, dict)
    parsed = AdvanceRollResult.from_payload(cast(AdvanceRollResultPayload, roll))
    assert parsed.request.spec.expression.quantity == 1
    assert parsed.request.spec.expression.sides == 6
    assert 1 <= parsed.value <= 6
    propose(session, request, unit, (Pose.at(10, 35), Pose.at(12.5, 35)), result_id="bad")
    retry = session.lifecycle.decision_controller.queue.pending_requests[0]
    propose(session, retry, unit, (Pose.at(10, 11), Pose.at(12.5, 11)), result_id="good")
    assert events(session, "advance_roll_resolved") == rolls
    restriction = state.advanced_unit_states[0]
    assert restriction.unit_instance_id == unit.unit_instance_id
    assert not restriction.can_declare_charge
    assert restriction.cleanup_point == "end_of_turn"
