"""Reproduce C09-03 on merged Order 79; a bounded audit, not a complete game.

Copy this file into scripts/ in a separate checkout of reviewed base
dc01911f57024ae69b565a0e965db65abf5fbdbe, then run from that checkout root:
PYTHONPATH=.:src uv run --no-sync python scripts/probe_order80_normal_move.py.
Its assertions intentionally expect the old defect and API; use the collected
Order 80 tests on the repaired runtime. The generic reactive permission is an
explicit fixture input, not a claim about any faction's 11th Edition rules.
"""

from __future__ import annotations

import json
from dataclasses import replace

from tests.phase15a_charge_test_support import _charge_lifecycle, _compact_test_unit_poses

from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_presence import battlefield_scenario_for_state
from warhammer40k_core.engine.phase import BattlePhase, LifecycleStatusKind
from warhammer40k_core.engine.reaction_windows import ReactionWindow, ReactionWindowKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.triggered_movement import (
    DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
    TriggeredMovementDescriptor,
    TriggeredMovementHandler,
    TriggeredMovementKind,
)
from warhammer40k_core.engine.triggered_movement_resolution import resolve_triggered_movement
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def probe(*, take_reaction: bool) -> dict[str, object]:
    lifecycle, units = _charge_lifecycle(
        alpha_unit_ids=("mover",),
        enemy_model_poses=_compact_test_unit_poses(origin=Pose.at(30, 20), model_count=5),
        game_id=f"order80-normal-turn-{take_reaction}",
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    # Initial fixture only. Every subsequent move and boundary uses the facade.
    state.battle_phase_index = state.battle_phase_sequence.index(BattlePhase.MOVEMENT)
    unit_id = units["enemy"].unit_instance_id
    placement = state.battlefield_state.unit_placement_by_id(unit_id)
    witness = PathWitness.for_straight_line_endpoints(
        tuple(
            (
                model.model_instance_id,
                model.pose,
                Pose.at(
                    model.pose.position.x + 0.25,
                    model.pose.position.y,
                    model.pose.position.z,
                    facing_degrees=model.pose.facing.degrees,
                ),
            )
            for model in placement.model_placements
        )
    )
    descriptor = TriggeredMovementDescriptor(
        movement_kind=TriggeredMovementKind.TRIGGERED,
        source_rule_id="test:order80:reactive-normal-move",
        trigger_timing=ReactionWindow(
            phase=BattlePhase.MOVEMENT,
            window_kind=ReactionWindowKind.RULE_TRIGGER,
            source_step="order80-normal-move-audit",
            source_event_id=None,
        ),
        max_distance_inches=1.0,
    )
    request = TriggeredMovementHandler(
        ruleset_descriptor=state.runtime_ruleset_descriptor()
    ).request_from_state(
        state=state,
        unit_instance_id=unit_id,
        descriptor=descriptor,
        candidate_witnesses=(witness,),
    )
    lifecycle.decision_controller.request_decision(request)
    session = LocalGameSession(lifecycle)
    status = session.advance_until_decision_or_terminal()
    assert status.decision_request == request
    option_id = (
        next(
            o.option_id
            for o in request.options
            if o.option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID
        )
        if take_reaction
        else DECLINE_TRIGGERED_MOVEMENT_OPTION_ID
    )
    status = session.submit_option(
        request_id=request.request_id,
        option_id=option_id,
        result_id="order80-reactive-normal",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.active_player_id == "player-a"
    history_after_reaction = [row.to_payload() for row in state.normal_move_states]
    assert len(history_after_reaction) == int(take_reaction)
    placement = state.battlefield_state.unit_placement_by_id(unit_id)
    second_witness = PathWitness.for_paths(
        tuple(
            (model.model_instance_id, (model.pose, model.pose))
            for model in placement.model_placements
        )
    )

    def restriction_codes(phase: BattlePhase) -> list[str]:
        result = resolve_triggered_movement(
            scenario=battlefield_scenario_for_state(state=state),
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            unit_placement=placement,
            descriptor=replace(
                descriptor, trigger_timing=replace(descriptor.trigger_timing, phase=phase)
            ),
            path_witness=second_witness,
            battle_round=state.battle_round,
            normal_move_states=tuple(state.normal_move_states),
        )
        return [row.violation_code.value for row in result.restriction_violations]

    same_phase_codes = restriction_codes(BattlePhase.MOVEMENT)
    different_phase_codes = restriction_codes(BattlePhase.SHOOTING)
    assert same_phase_codes == (["normal_move_already_used_this_phase"] if take_reaction else [])
    assert different_phase_codes == []
    trace: list[dict[str, object]] = []
    for index in range(20):
        request = status.decision_request
        assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
        assert request is not None
        trace.append(
            {
                "turn_player_id": state.active_player_id,
                "battle_round": state.battle_round,
                "phase": state.current_battle_phase.value,
                "decision_type": request.decision_type,
                "option_ids": [option.option_id for option in request.options],
            }
        )
        if (
            state.active_player_id == "player-b"
            and request.decision_type == "select_movement_action"
        ):
            break
        candidates = [
            option
            for option in request.options
            if option.option_id
            in {
                "remain_stationary",
                "complete_shooting_phase",
                "complete_charge_phase",
                "complete_fight_phase",
            }
        ]
        if not candidates:
            candidates = [
                option
                for option in request.options
                if option.option_id in {units["mover"].unit_instance_id, unit_id}
            ]
        assert len(candidates) == 1, request.decision_type
        status = session.submit_option(
            request_id=request.request_id,
            option_id=candidates[0].option_id,
            result_id=f"order80-probe-{index}",
        )
    else:
        raise AssertionError("Bounded probe did not reach the next player's Movement phase.")
    assert state.battle_round == 1
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    options = [option.option_id for option in request.options]
    assert ("normal_move" in options) is not take_reaction
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    views: dict[str, object] = {}
    for viewer in state.player_ids:
        view = session.view(viewer_player_id=viewer)
        assert view == restored.view(viewer_player_id=viewer)
        views[viewer] = view["pending_decision"]
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id="order80-preflight"))
    result = replay.run()
    assert result.status is ReplayRunStatus.REPRODUCED
    return {
        "case": "accepted_reaction" if take_reaction else "declined_reaction_control",
        "reacting_unit": unit_id,
        "reacting_unit_owner": "player-b",
        "reaction_turn_owner": "player-a",
        "reaction_distance_inches": 0.25 if take_reaction else 0,
        "normal_move_history": history_after_reaction,
        "same_phase_restriction_codes": same_phase_codes,
        "different_phase_restriction_codes": different_phase_codes,
        "next_turn_normal_move_offered": "normal_move" in options,
        "expected_next_turn_normal_move_offered": True,
        "decision_trace": trace,
        "checkpoint_round_trip_exact": True,
        "replay_status": result.status.value,
        "viewer_pending_decisions": views,
    }


if __name__ == "__main__":
    print(json.dumps({"cases": [probe(take_reaction=True), probe(take_reaction=False)]}, indent=2))
