"""Reproduce the Order 83 phase-start revival-anchor defect on merged Order 82.

Run against an exported 03fd10e6 runtime, not this branch:
PYTHONPATH=/tmp/order83-base/src:. uv run --no-sync python scripts/probe_order83_revival_anchors.py
This bounded diagnostic expects the unfixed defect, not correct gameplay.
The two generic healing grants are explicit fixture inputs, not faction certification.
Each grant has its own replay root; the second retains the first's physical history.
"""

from __future__ import annotations

import argparse
import json
from copy import deepcopy
from pathlib import Path

from tests.destruction_occurrence_fixture_helpers import destroy_rule_model_for_fixture
from tests.phase15c_fight_order_helpers import fight_lifecycle

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import (
    BattlefieldPlacementKind,
    ModelPlacement,
    UnitPlacement,
    geometry_model_for_placement,
)
from warhammer40k_core.engine.damage_allocation import model_by_id
from warhammer40k_core.engine.decision_request import (
    PARAMETERIZED_DECISION_OPTION_ID,
    DecisionRequest,
)
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.healing import HealingEffect, resolve_healing_until_blocked
from warhammer40k_core.engine.healing_geometry import healing_phase_start_model_ids
from warhammer40k_core.engine.healing_revival import _validated_healing_revival_submission
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
from warhammer40k_core.geometry.pose import Pose


def _request(
    lifecycle: GameLifecycle,
    removed: ModelPlacement,
    anchors: tuple[str, ...],
    index: int,
) -> DecisionRequest:
    state = lifecycle.state
    assert state is not None
    effect = HealingEffect(
        effect_id=f"order83-heal-{index}",
        target_unit_instance_id=removed.unit_instance_id,
        amount=1,
        opposing_player_id="player-b",
        phase_start_model_ids=anchors,
        source_context={
            "revive_model_full_health": True,
            "revive_destroyed_models_only": True,
            "eligible_revival_model_ids": [removed.model_instance_id],
        },
    )
    _, request = resolve_healing_until_blocked(
        state=state,
        decisions=lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert request is not None
    return request


def _proposal(request: DecisionRequest, removed: ModelPlacement, pose: Pose) -> JsonValue:
    placement = removed.with_pose(pose)
    return {
        "proposal_request_id": request.request_id,
        "proposal_kind": "healing_revival_placement",
        "unit_instance_id": placement.unit_instance_id,
        "placement_kind": BattlefieldPlacementKind.RETURN_TO_BATTLEFIELD.value,
        "attempted_placement": validate_json_value(
            UnitPlacement(
                army_id=placement.army_id,
                player_id=placement.player_id,
                unit_instance_id=placement.unit_instance_id,
                model_placements=(placement,),
            ).to_payload()
        ),
    }


def _checkpoint_and_replay(session: LocalGameSession, artifact_id: str) -> dict[str, object]:
    checkpoint = session.to_persistence_payload()
    restored = LocalGameSession.from_persistence_payload(json.loads(json.dumps(checkpoint)))
    assert restored.to_persistence_payload() == checkpoint
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
    replay = ReplayRunner.from_payload(session.replay_artifact(artifact_id=artifact_id)).run()
    assert replay.status is ReplayRunStatus.REPRODUCED
    return {"checkpoint_exact": True, "both_viewers_exact": True, "replay": replay.status.value}


def probe(*, correct_anchors: bool, original_anchor_endpoint: bool = False) -> dict[str, object]:
    lifecycle, units = fight_lifecycle(
        alpha_unit_ids=("recipient",),
        enemy_unit_ids=("enemy",),
        origins={},
        poses_by_unit_key={
            "recipient": tuple(Pose.at(10, 10 + 1.5 * i) for i in range(5)),
            "enemy": tuple(Pose.at(40, 30 + 1.5 * i) for i in range(5)),
        },
        game_id="order83-revival-anchors",
        battle_phase=BattlePhase.FIGHT,
        record_deployment=True,
    )
    state = lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    removed = tuple(
        state.battlefield_state.model_placement_by_id(model.model_instance_id)
        for model in units["recipient"].own_models[-2:]
    )
    # Both casualties precede the next player's Command and Movement phases.
    for placement in removed:
        destroy_rule_model_for_fixture(
            state=state,
            decisions=lifecycle.decision_controller,
            model_id=placement.model_instance_id,
            destroying_player_id="player-b",
            source_unit_id=units["enemy"].unit_instance_id,
            source_model_id=units["enemy"].own_models[0].model_instance_id,
        )
    LocalGameSession(lifecycle).advance_until_decision_or_terminal()
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    assert state.active_player_id == "player-b"
    phase_entry = next(
        event
        for event in lifecycle.decision_controller.event_log.records
        if event.event_type == "movement_phase_entered"
    )
    target_id = units["recipient"].unit_instance_id
    original_anchors = healing_phase_start_model_ids(
        state=state, rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=target_id)
    )
    assert len(original_anchors) == 3
    assert not set(original_anchors).intersection(p.model_instance_id for p in removed)
    request = _request(lifecycle, removed[0], original_anchors, 1)
    first = LocalGameSession(lifecycle)
    status = first.advance_until_decision_or_terminal()
    movement = status.decision_request
    assert movement is not None
    assert movement.decision_type == "select_movement_unit"
    # Leave the real movement-action decision behind the healing placement in the queue.
    status = first.submit_option(
        request_id=movement.request_id,
        option_id=units["enemy"].unit_instance_id,
        result_id="order83-select-movement-unit",
    )
    assert status.decision_request == request
    status = first.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order83-first-revival",
        payload=_proposal(request, removed[0], Pose.at(10, 16)),
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    assert state.current_battle_phase is BattlePhase.MOVEMENT
    first_evidence = _checkpoint_and_replay(first, "order83-first-revival")
    current_anchors = healing_phase_start_model_ids(
        state=state, rules_unit=rules_unit_view_by_id(state=state, unit_instance_id=target_id)
    )
    assert set(current_anchors) - set(original_anchors) == {removed[0].model_instance_id}

    request = _request(
        lifecycle, removed[1], original_anchors if correct_anchors else current_anchors, 2
    )
    second = LocalGameSession(lifecycle)
    second.advance_until_decision_or_terminal()
    # The next generic grant is a fixture input; retain a separate exact replay segment.
    second._initial_replay_lifecycle_payload = deepcopy(lifecycle.to_payload())  # pyright: ignore[reportPrivateUsage]
    action = lifecycle.decision_controller.queue.peek_next()
    assert action.decision_type == "select_movement_action"
    option = next(option for option in action.options if "stationary" in option.option_id)
    status = second.submit_option(
        request_id=action.request_id,
        option_id=option.option_id,
        result_id="order83-enemy-remain-stationary",
    )
    assert status.decision_request == request
    for viewer in ("player-a", "player-b"):
        assert second.view(viewer_player_id=viewer)["pending_proposal"] is not None
    pose = Pose.at(8.5, 14) if original_anchor_endpoint else Pose.at(10, 19)
    proposal = _proposal(request, removed[1], pose)
    candidate = geometry_model_for_placement(
        model=model_by_id(state=state, model_instance_id=removed[1].model_instance_id),
        placement=removed[1].with_pose(pose),
    )
    distances = {
        model_id: candidate.base_distance_to(
            geometry_model_for_placement(
                model=model_by_id(state=state, model_instance_id=model_id),
                placement=state.battlefield_state.model_placement_by_id(model_id),
            )
        )
        for model_id in current_anchors
    }
    before = lifecycle.to_payload()
    try:
        _validated_healing_revival_submission(
            state=state,
            ruleset_descriptor=state.runtime_ruleset_descriptor(),
            request=request,
            result=DecisionResult(
                request_id=request.request_id,
                result_id="order83-read-only-validation",
                decision_type=request.decision_type,
                actor_id=request.actor_id,
                selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
                payload=proposal,
            ),
        )
    except GameLifecycleError as exc:
        diagnostic = str(exc)
    else:
        diagnostic = "accepted"
    assert lifecycle.to_payload() == before
    status = second.submit_parameterized_payload(
        request_id=request.request_id, result_id="order83-second-revival", payload=proposal
    )
    expected_rejection = correct_anchors and not original_anchor_endpoint
    assert (status.status_kind is LifecycleStatusKind.INVALID) == expected_rejection
    assert (lifecycle.to_payload() == before) == expected_rejection
    assert diagnostic == (
        "Revived model is not coherent with phase-start models."
        if expected_rejection
        else "accepted"
    )
    evidence = _checkpoint_and_replay(second, "order83-second-revival")
    event_counts = {
        viewer: sum(
            event["event_type"] == "healing_step_resolved"
            for event in second.events_since(EventStreamCursor(), viewer_player_id=viewer)["events"]
        )
        for viewer in ("player-a", "player-b")
    }
    retry = None
    if expected_rejection:
        for viewer in ("player-a", "player-b"):
            assert second.view(viewer_player_id=viewer)["pending_proposal"] is not None
        status = second.submit_parameterized_payload(
            request_id=request.request_id,
            result_id="order83-legal-retry",
            payload=_proposal(request, removed[1], Pose.at(8.5, 14)),
        )
        assert status.status_kind is not LifecycleStatusKind.INVALID
        retry = _checkpoint_and_replay(second, "order83-legal-retry")
    return {
        "correct_phase_start_anchors": correct_anchors,
        "original_anchor_endpoint": original_anchor_endpoint,
        "phase_entry_event_id": phase_entry.event_id,
        "phase_start_model_ids": original_anchors,
        "second_helper_model_ids": current_anchors,
        "first_revival": first_evidence,
        "second_revival_pose": pose.to_payload(),
        "base_distances_inches": distances,
        "expected_legal": original_anchor_endpoint,
        "observed_accepted": not expected_rejection,
        "validator_diagnostic": diagnostic,
        "invalid_submission_atomic": expected_rejection,
        "second_revival": evidence,
        "viewer_healing_event_counts": event_counts,
        "legal_retry": retry,
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    rendered = (
        json.dumps(
            {
                "reviewed_commit": "03fd10e6d859743205c0c26bb653bc0b77b4bd85",
                "scope": "bounded generic revival diagnostic; separate per-grant replay roots",
                "cases": [
                    probe(correct_anchors=False),
                    probe(correct_anchors=True),
                    probe(correct_anchors=False, original_anchor_endpoint=True),
                ],
            },
            indent=2,
        )
        + "\n"
    )
    if args.output is not None:
        args.output.write_text(rendered)
    else:
        print(rendered, end="")
