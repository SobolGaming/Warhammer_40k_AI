"""Current 18.07 uses ordinary setup and never produces a forced Fight response."""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from types import FrameType
from typing import cast

import pytest
from tests.disembark_eligibility_helpers import PASSENGER_ID
from tests.order62_shock_helpers import shock_proposal, shock_session
from tests.psychic_modifier_helpers import pending_request
from tests.v963_shock_helpers import tactical_shock_session

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.charge_eligibility import charge_unit_ineligibility_reason
from warhammer40k_core.engine.charge_phase_state import ChargePhaseState
from warhammer40k_core.engine.event_log import validate_json_value
from warhammer40k_core.engine.game_state import GameState
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.phase import LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload
from warhammer40k_core.geometry.pose import Pose


def test_v963_shock_unengaged_setup_has_no_queue_and_restores_exactly() -> None:
    session = shock_session(enemy_x=13)
    initial = session.lifecycle.to_payload()
    request, proposal = shock_proposal(session)
    assert proposal.attempted_placement is not None
    poses = (
        Pose.at(6.9, 8.5),
        Pose.at(6.0, 9.8),
        Pose.at(6.0, 11.2),
        Pose.at(6.9, 12.5),
        Pose.at(7.2, 10.5),
    )
    proposal = replace(
        proposal,
        attempted_placement=replace(
            proposal.attempted_placement,
            model_placements=tuple(
                replace(model, pose=pose)
                for model, pose in zip(
                    proposal.attempted_placement.model_placements, poses, strict=True
                )
            ),
        ),
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="v963:legal-setup",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    state = session.lifecycle.state
    assert state is not None
    assert state.fight_phase_state is None
    disembarked = state.disembarked_unit_state_for_unit(
        player_id="player-a", battle_round=1, unit_instance_id=PASSENGER_ID
    )
    assert disembarked is not None
    assert not disembarked.can_declare_charge
    assert not disembarked.can_move_further
    assert not any(
        event.event_type.startswith("forced_fight_activation_queue_")
        for event in session.lifecycle.decision_controller.event_log.records
    )
    payload = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    restored = LocalGameSession(GameLifecycle.from_payload(payload))
    assert restored.lifecycle.to_payload() == payload
    for viewer in ("player-a", "player-b"):
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
            session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        )
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="v963:legal-setup",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("fault", ["missing_snapshot", "stale_proposal", "wrong_transport"])
def test_v963_shock_malformed_and_stale_proposals_do_not_pop_or_mutate(fault: str) -> None:
    session = shock_session(enemy_x=18)
    request, proposal = shock_proposal(session)
    submission = dict(proposal.to_payload())
    if fault == "missing_snapshot":
        submission.pop("start_engaged_enemy_unit_instance_ids")
    elif fault == "stale_proposal":
        submission["proposal_request_id"] = "v963:stale-proposal"
    else:
        submission["transport_unit_instance_id"] = "v963:wrong-transport"
    before = session.lifecycle.to_payload()
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id=f"v963:{fault}",
        payload=validate_json_value(submission),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert pending_request(session) == request
    assert session.lifecycle.to_payload() == before


def _charge_reason(state: GameState) -> str | None:
    return charge_unit_ineligibility_reason(
        state=state,
        unit_instance_id=PASSENGER_ID,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        charge_state=ChargePhaseState(battle_round=state.battle_round, active_player_id="player-a"),
        ignore_already_selected=False,
    )


@pytest.mark.parametrize("tactical", [False, True])
def test_v963_shock_charge_lock_includes_all_turn_end_rules_then_expires(tactical: bool) -> None:
    session = tactical_shock_session() if tactical else shock_session(enemy_x=18)
    initial = session.lifecycle.to_payload()
    request, proposal = shock_proposal(session)
    session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="v963:duration-setup",
        payload=validate_json_value(proposal.to_payload()),
    )
    state = session.lifecycle.state
    assert state is not None
    observations: list[tuple[str, str | None]] = []
    restored_mission_pause = False

    def observe(frame: FrameType, event: str, _argument: object) -> None:
        # Observe real boundary entries without replacing or mocking an engine owner.
        if event != "call" or frame.f_code.co_name not in {
            "request_end_rules",
            "request_mission_turn_end_rules",
        }:
            return
        observed_state = frame.f_locals.get("state")
        if not isinstance(observed_state, GameState) or observed_state is not state:
            return
        if observed_state.active_player_id != "player-a":
            return
        if (
            frame.f_code.co_name == "request_end_rules"
            and str(frame.f_locals["trigger_kind"]) != "end_turn"
        ):
            return
        observations.append((frame.f_code.co_name, _charge_reason(observed_state)))

    previous_profile = sys.getprofile()
    sys.setprofile(observe)
    try:
        for index in range(40):
            if state.active_player_id != "player-a":
                break
            request = pending_request(session)
            options = tuple(option.option_id for option in request.options)
            if request.decision_type == "submit_stratagem_target_proposal":
                session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id=f"v963:duration:{index}",
                    payload=stratagem_decline_payload(),
                )
                continue
            if request.decision_type == "select_charging_unit":
                assert PASSENGER_ID not in options
                assert _charge_reason(state) == "charge_unit_disembarked"
                restored = LocalGameSession.from_persistence_payload(
                    json.loads(json.dumps(session.to_persistence_payload()))
                )
                assert restored.to_persistence_payload() == session.to_persistence_payload()
            if request.decision_type == "score_tactical_secondary_mission":
                assert _charge_reason(state) == "charge_unit_disembarked"
                assert any(
                    row.active_player_id == "player-a" and row.battle_round == 1
                    for row in state.end_turn_cleanup_states
                )
                payload = json.loads(json.dumps(session.to_persistence_payload()))
                restored = LocalGameSession.from_persistence_payload(payload)
                assert restored.to_persistence_payload() == payload
                for viewer in state.player_ids:
                    assert restored.view(viewer_player_id=viewer) == session.view(
                        viewer_player_id=viewer
                    )
                    assert restored.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
                        session.events_since(EventStreamCursor(), viewer_player_id=viewer)
                    )
                session = restored
                state = session.lifecycle.state
                assert state is not None
                assert _charge_reason(state) == "charge_unit_disembarked"
                restored_mission_pause = True
                selected = tuple(option for option in options if option.startswith("retain:"))
            elif request.decision_type == "select_movement_unit":
                selected = options[:1]
            elif request.decision_type == "select_movement_action":
                selected = tuple(option for option in options if option == "remain_stationary")
            else:
                selected = tuple(
                    option
                    for option in options
                    if any(
                        token in option for token in ("complete", "end", "done", "decline", "skip")
                    )
                    or option == "pass"
                )
            assert len(selected) == 1, (request.decision_type, options)
            outcome = session.submit_option(
                request_id=request.request_id,
                result_id=f"v963:duration:{index}",
                option_id=selected[0],
            )
            assert outcome.status_kind is not LifecycleStatusKind.INVALID, outcome
    finally:
        sys.setprofile(previous_profile)
    assert ("request_end_rules", "charge_unit_disembarked") in observations
    assert ("request_mission_turn_end_rules", "charge_unit_disembarked") in observations
    assert restored_mission_pause is tactical
    assert state.active_player_id == "player-b"
    assert not state.disembarked_unit_states
    assert _charge_reason(state) is None
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    for viewer in state.player_ids:
        assert restored.view(viewer_player_id=viewer) == session.view(viewer_player_id=viewer)
        assert restored.events_since(EventStreamCursor(), viewer_player_id=viewer) == (
            session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        )
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="v963:duration",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay


@pytest.mark.parametrize("other_engagement", [False, True])
def test_v963_shock_rejects_passenger_engagement_without_mutation(
    other_engagement: bool,
) -> None:
    session = shock_session(enemy_x=15.8, other_engagement=other_engagement)
    initial = session.lifecycle.to_payload()
    request, proposal = shock_proposal(session)
    state = session.lifecycle.state
    assert state is not None
    battlefield = state.battlefield_state
    cargo = tuple(state.transport_cargo_states)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="v963:engaged-setup",
        payload=validate_json_value(proposal.to_payload()),
    )
    assert state.battlefield_state == battlefield
    assert tuple(state.transport_cargo_states) == cargo
    assert state.fight_phase_state is None
    assert not state.disembarked_unit_states
    events = session.lifecycle.decision_controller.event_log.records
    assert any("enemy_engagement_range" in json.dumps(event.payload) for event in events)
    assert result.status_kind is LifecycleStatusKind.INVALID
    request = pending_request(session)
    assert PASSENGER_ID in {option.option_id for option in request.options}
    payload = cast(GameLifecyclePayload, json.loads(json.dumps(session.lifecycle.to_payload())))
    assert GameLifecycle.from_payload(payload).to_payload() == payload
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="v963:engaged-setup",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
