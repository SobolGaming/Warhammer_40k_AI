from __future__ import annotations

import json
from dataclasses import replace

import pytest
from tests.core_clause_evidence_helpers import flying_transit_session
from tests.mission_action_history_helpers import (
    finish_primary_turn_end_for_fixture,
    prepare_turn_end_control_for_fixture,
)
from tests.order129_helpers import assert_flight_checkpoint, flight_proposal, submit_flight
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.engine.battle_round_flow import BattleRoundFlow
from warhammer40k_core.engine.decision_request import PARAMETERIZED_DECISION_OPTION_ID
from warhammer40k_core.engine.decision_result import DecisionResult
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.phase import (
    BattlePhase,
    GameLifecycleError,
    LifecycleStatusKind,
    PhaseHandler,
    PlaceholderPhaseHandler,
)
from warhammer40k_core.engine.phases.movement_handler import MovementPhaseHandler
from warhammer40k_core.engine.primary_mission_boundary_checkpoint_evidence import (
    PrimaryMissionBoundaryCheckpoint,
)
from warhammer40k_core.engine.primary_mission_boundary_unit_history_authority import (
    validate_primary_mission_boundary_unit_history_authority,
)
from warhammer40k_core.engine.unit_proximity import unit_within_enemy_engagement_range
from warhammer40k_core.geometry.pathing import PathWitness
from warhammer40k_core.geometry.pose import Pose


def test_original_fly_transit_exact_checkpoint_restores_forks_and_replays() -> None:
    assert_flight_checkpoint(flying_transit_session())


@pytest.mark.parametrize("native", [False, True])
def test_fly_transit_pending_rejected_retry_and_post_cleanup_history(native: bool) -> None:
    session, proposal = flight_proposal(native=native)
    assert_flight_checkpoint(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.battlefield_state is not None
    before = state.battlefield_state
    # An engaged endpoint is prohibited even though transit is permitted.
    engaged = replace(
        proposal,
        witness=PathWitness.for_paths(
            tuple((model, (poses[0], poses[1])) for model, poses in proposal.witness.model_paths)
        ),
    )
    status = submit_flight(session, engaged, "engaged-endpoint")
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert not state.model_movement_history
    assert_flight_checkpoint(session)
    request = session.lifecycle.decision_controller.queue.pending_requests[0]
    submit_flight(session, replace(proposal, proposal_request_id=request.request_id), "legal-retry")
    assert state.model_movement_history
    assert not unit_within_enemy_engagement_range(state=state, unit_instance_id="army-alpha:mover")
    enemy = "army-beta:mover" if native else "army-beta:enemy"
    assert not unit_within_enemy_engagement_range(state=state, unit_instance_id=enemy)
    assert_flight_checkpoint(session)


@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("flight", [False, True])
def test_ordinary_and_flight_modes_keep_complete_post_cleanup_authority(
    action: str, flight: bool
) -> None:
    session, proposal = flight_proposal(action=action, flight=flight, transit=False)
    submit_flight(session, proposal, "move")
    assert_flight_checkpoint(session)


def test_ground_advance_cannot_borrow_fly_transit_and_can_retry_away() -> None:
    session, proposal = flight_proposal(flight=False)
    state = session.lifecycle.state
    assert state is not None
    before = state.battlefield_state
    status = submit_flight(session, proposal, "ground-transit")
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before
    assert not state.model_movement_history
    assert_flight_checkpoint(session)
    request = session.lifecycle.decision_controller.queue.pending_requests[0]
    away = replace(
        proposal,
        proposal_request_id=request.request_id,
        witness=PathWitness.for_paths(
            tuple(
                (model, (poses[0], Pose.at(poses[0].position.x, poses[0].position.y - 1)))
                for model, poses in proposal.witness.model_paths
            )
        ),
    )
    submit_flight(session, away, "ground-legal-retry")
    assert_flight_checkpoint(session)


@pytest.mark.parametrize("corruption", ["mode", "witness", "cleanup"])
def test_post_cleanup_commit_still_authenticates_movement_and_cleanup(corruption: str) -> None:
    session = flying_transit_session()
    state = session.lifecycle.state
    assert state is not None
    controller = session.lifecycle.decision_controller
    events = controller.event_log.records
    index, event = next(
        (i, e)
        for i, e in enumerate(events)
        if e.event_type == "primary_scoring_commit_checkpoint_recorded"
    )
    assert isinstance(event.payload, dict)
    checkpoint = PrimaryMissionBoundaryCheckpoint.from_payload(event.payload["checkpoint"])
    if corruption == "cleanup":
        state.end_turn_cleanup_states = []
    else:
        movement = next(e for e in events if e.event_type == "movement_activation_completed")
        assert isinstance(movement.payload, dict)
        payload = dict(movement.payload)
        payload["movement_mode" if corruption == "mode" else "witness"] = (
            "advance" if corruption == "mode" else {"model_paths": []}
        )
        events = tuple(replace(e, payload=payload) if e == movement else e for e in events)
    with pytest.raises(GameLifecycleError, match=r"authority|semantics"):
        validate_primary_mission_boundary_unit_history_authority(
            state=state,
            event_records=events,
            decision_records=controller.records,
            checkpoint_index=index,
            checkpoint=checkpoint,
        )


@pytest.mark.parametrize("flight", [False, True])
def test_fall_back_modes_restore_after_the_same_native_turn_cleanup(flight: bool) -> None:
    session, proposal = flight_proposal(action="fall_back", flight=flight)
    state = session.lifecycle.state
    assert state is not None
    assert unit_within_enemy_engagement_range(state=state, unit_instance_id="army-alpha:mover")
    submit_flight(session, proposal, "fall-back")
    assert state.model_movement_history
    assert not unit_within_enemy_engagement_range(state=state, unit_instance_id="army-alpha:mover")
    assert state.end_turn_cleanup_states
    assert not state.fell_back_unit_states
    assert_flight_checkpoint(session)


@pytest.mark.parametrize("flight", [False, True])
def test_pending_movement_mode_omission_is_rejected_atomically(flight: bool) -> None:
    session, proposal = flight_proposal(flight=flight, transit=False)
    before = session.to_persistence_payload()
    status = submit_flight(session, replace(proposal, movement_mode=None), "omitted-mode")
    assert status.status_kind is LifecycleStatusKind.INVALID
    assert session.to_persistence_payload() == before


@pytest.mark.parametrize("action", ["advance", "fall_back"])
@pytest.mark.parametrize("flight", [False, True])
def test_pre_cleanup_scoring_history_survives_later_native_turn_completion(
    action: str, flight: bool
) -> None:
    session, proposal = flight_proposal(action=action, flight=flight, transit=False)
    lifecycle = session.lifecycle
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    request = pending_request(session)
    result = DecisionResult(
        result_id="pre-cleanup-accepted-movement",
        request_id=request.request_id,
        decision_type=request.decision_type,
        actor_id=request.actor_id,
        selected_option_id=PARAMETERIZED_DECISION_OPTION_ID,
        payload=validate_json_value(proposal.to_payload()),
    )
    decisions.submit_result(result)
    movement_handler = MovementPhaseHandler(
        ruleset_descriptor=lifecycle.config.ruleset_descriptor,
        army_catalog=lifecycle.config.army_catalog,
        parameterized_proposals=lifecycle.parameterized_movement_proposals,
    )
    movement_handler.apply_decision(
        state=state, decisions=decisions, result=result, reaction_queue=lifecycle.reaction_queue
    )
    assert state.advanced_unit_states or state.fell_back_unit_states
    assert not state.end_turn_cleanup_states
    assert not decisions.queue.pending_requests
    # Existing fixture convention: real boundaries around intervening phase bodies.
    # Actual native flow completes the turn below; history payloads are never edited.
    handlers: dict[BattlePhase, PhaseHandler] = {
        phase: PlaceholderPhaseHandler(phase) for phase in state.battle_phase_sequence
    }
    handlers[BattlePhase.MOVEMENT] = movement_handler
    fixture_flow = BattleRoundFlow(phase_handlers=handlers)
    while state.current_battle_phase is not BattlePhase.FIGHT:
        fixture_flow.advance(state=state, decisions=decisions)
        assert not decisions.queue.pending_requests
    prepare_turn_end_control_for_fixture(state=state, decisions=decisions)
    finish_primary_turn_end_for_fixture(state=state, decisions=decisions)
    checkpoints_before = tuple(
        event
        for event in decisions.event_log.records
        if event.event_type == "primary_scoring_commit_checkpoint_recorded"
    )
    retained_checkpoints = tuple(
        PrimaryMissionBoundaryCheckpoint.from_payload(event.payload["checkpoint"])
        for event in checkpoints_before
        if isinstance(event.payload, dict)
    )
    assert any(
        checkpoint.advanced_unit_state_jsons or checkpoint.fell_back_unit_state_jsons
        for checkpoint in retained_checkpoints
    )
    before = json.loads(json.dumps(lifecycle.to_payload()))
    assert GameLifecycle.from_payload(before).to_payload() == before
    lifecycle.advance_until_decision_or_terminal()
    assert state.active_player_id == "player-b"
    assert state.end_turn_cleanup_states
    assert not state.advanced_unit_states
    assert not state.fell_back_unit_states
    assert (
        tuple(
            event
            for event in decisions.event_log.records
            if event.event_type == "primary_scoring_commit_checkpoint_recorded"
        )[: len(checkpoints_before)]
        == checkpoints_before
    )
    after = json.loads(json.dumps(lifecycle.to_payload()))
    assert GameLifecycle.from_payload(after).to_payload() == after
