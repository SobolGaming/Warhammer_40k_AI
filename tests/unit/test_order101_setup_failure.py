"""03.02/03.02.01 failed move-type setups preserve location and selection rights."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from typing import cast

import pytest
from tests.disembark_eligibility_helpers import PASSENGER_ID, TRANSPORT_ID
from tests.large_model_disembark_helpers import (
    large_disembark_placement,
    large_disembark_session,
)
from tests.order101_failed_setup_helpers import (
    corrupt_failed_setup_authority,
    emergency_component_omission_session,
    failed_setup_automatic_record_session,
    failed_setup_before_offboard_revival_session,
    forge_failed_disembark_transport,
    reserve_inventory_session,
    swap_terminal_cargo_membership,
    two_carrier_disembark_session,
)
from tests.psychic_modifier_helpers import pending_request

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.battlefield_state import BattlefieldPlacementKind
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.lifecycle import GameLifecycle, GameLifecyclePayload
from warhammer40k_core.engine.movement_proposals import (
    MovementProposalRequest,
    PlacementProposalPayload,
    ProposalKind,
)
from warhammer40k_core.engine.phase import GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner
from warhammer40k_core.engine.transports import DisembarkModeKind, TransportMovementStatus


def _select_disembark(session: LocalGameSession, *, prefix: str) -> PlacementProposalPayload:
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id=f"{prefix}:unit", option_id=PASSENGER_ID
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id=f"{prefix}:action", option_id="disembark"
    )
    request = pending_request(session)
    return PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=PASSENGER_ID,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_placement=large_disembark_placement(session, gap=1.01),
        transport_unit_instance_id=TRANSPORT_ID,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
        restriction_overrides=(),
    )


@pytest.mark.parametrize("diameter", [5, 100])
def test_failed_disembark_restores_selected_to_move_and_prior_location(diameter: float) -> None:
    session = large_disembark_session(diameter=diameter)
    state = session.lifecycle.state
    assert state is not None
    before_battlefield = state.battlefield_state
    before_cargo = tuple(state.transport_cargo_states)
    submission = _select_disembark(session, prefix="order101")
    rejected = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    assert tuple(state.transport_cargo_states) == before_cargo
    assert state.movement_phase_state is not None
    assert PASSENGER_ID not in state.movement_phase_state.selected_unit_ids
    assert PASSENGER_ID not in state.movement_phase_state.moved_unit_ids
    assert state.movement_phase_state.active_selection is None
    receipt_event = next(
        event
        for event in session.lifecycle.decision_controller.event_log.records
        if event.event_type == "movement_setup_failed"
    )
    receipt = receipt_event.payload
    assert isinstance(receipt, dict)
    sources = json.loads(Path("data/source_audits/order97/selected-sources.json").read_text())
    source = next(row for row in sources if row["row_id"] == "rule:03:03.02.01:1")
    assert receipt["source_observation_row_id"] == source["row_id"]
    assert receipt["source_observation_sha256"] == source["source_sha256"]
    request = pending_request(session)
    assert request.decision_type == "select_movement_unit"
    assert PASSENGER_ID in {option.option_id for option in request.options}
    session.submit_option(
        request_id=request.request_id, result_id="order101:reselect", option_id=PASSENGER_ID
    )
    request = pending_request(session)
    assert {"remain_stationary", "disembark"} <= {option.option_id for option in request.options}


def _assert_restore_and_exact_replay(
    session: LocalGameSession, initial: GameLifecyclePayload
) -> None:
    restored = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
    )
    state = session.lifecycle.state
    assert state is not None
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        events = session.events_since(EventStreamCursor(), viewer_player_id=viewer)
        assert events == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
        public_json = json.dumps(events, sort_keys=True)
        assert "movement_phase_state_before" not in public_json
        assert "movement_phase_state_after" not in public_json
    replay = ReplayRunner(
        ReplayArtifact.capture(
            artifact_id="order101",
            initial_lifecycle_payload=initial,
            final_lifecycle=session.lifecycle,
        )
    ).run()
    assert replay.reproduced_exactly, replay
    assert "object at 0x" not in json.dumps(session.lifecycle.to_payload(), sort_keys=True)


@pytest.mark.parametrize("continuation", ["pending", "other_selection", "shooting"])
def test_failed_setup_binds_terminal_carrier_after_later_selection_or_phase(
    continuation: str,
) -> None:
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

    carrier_id = "army-alpha:other-transport"
    session = two_carrier_disembark_session(carrier_id=carrier_id)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = replace(
        _select_disembark(session, prefix="order101:terminal-carrier"),
        transport_unit_instance_id=carrier_id,
    )
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:terminal-carrier:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    if continuation == "other_selection":
        request = pending_request(session)
        session.submit_option(
            request_id=request.request_id,
            result_id="order101:terminal-carrier:other-unit",
            option_id=TRANSPORT_ID,
        )
    elif continuation == "shooting":
        for index in range(30):
            request = pending_request(session)
            state = session.lifecycle.state
            assert state is not None
            if state.current_battle_phase is BattlePhase.SHOOTING:
                break
            if request.decision_type == "submit_stratagem_target_proposal":
                result = session.submit_parameterized_payload(
                    request_id=request.request_id,
                    result_id=f"order101:terminal-carrier:advance:{index}",
                    payload=stratagem_decline_payload(),
                )
            else:
                assert request.decision_type in {"select_movement_unit", "select_movement_action"}
                result = session.submit_option(
                    request_id=request.request_id,
                    result_id=f"order101:terminal-carrier:advance:{index}",
                    option_id=request.options[0].option_id
                    if request.decision_type == "select_movement_unit"
                    else "remain_stationary",
                )
            assert result.status_kind is not LifecycleStatusKind.INVALID
        else:
            raise AssertionError("Failed to leave Movement through recorded choices.")
    _assert_restore_and_exact_replay(session, initial)
    snapshot = session.lifecycle.to_payload()
    forged = deepcopy(snapshot)
    swap_terminal_cargo_membership(forged)
    assert forged["decisions"] == snapshot["decisions"]
    origin = snapshot.get("modifier_evaluation_history_origin")
    assert origin is not None
    assert forged.get("modifier_evaluation_history_origin") == origin
    with pytest.raises(GameLifecycleError, match="terminal cargo location authority drift"):
        GameLifecycle.from_payload(forged)


def test_failed_setup_terminal_cargo_accepts_later_real_embark() -> None:
    from tests.movement_submission_helpers import straight_line_witness_for_state

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.movement_proposals import MovementProposalPayload

    session = two_carrier_disembark_session(nearby_embarking_unit=True)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101:later-embark")
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:later-embark:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    for index, option in enumerate(("army-alpha:remaining-unit", "normal_move")):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id=f"order101:later-embark:{index}",
            option_id=option,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:later-embark:path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id="army-alpha:remaining-unit",
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL,
                witness=straight_line_witness_for_state(
                    state, unit_instance_id="army-alpha:remaining-unit"
                ),
            ).to_payload()
        ),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    assert request.decision_type == "select_embark_transport"
    result = session.submit_option(
        request_id=request.request_id,
        result_id="order101:later-embark:accepted",
        option_id=TRANSPORT_ID,
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    _assert_restore_and_exact_replay(session, initial)
    forged = deepcopy(session.lifecycle.to_payload())
    swap_terminal_cargo_membership(forged)
    with pytest.raises(GameLifecycleError, match="terminal cargo location authority drift"):
        GameLifecycle.from_payload(forged)


def _assert_rejected_proposal_cannot_authorize_completion(session: LocalGameSession) -> None:
    from warhammer40k_core.engine.movement_decision_authority import (
        validate_movement_completion_decision_authority,
    )

    controller = session.lifecycle.decision_controller
    events = controller.event_log.records
    rejected = next(event for event in events if event.event_type == "movement_proposal_invalid")
    assert isinstance(rejected.payload, dict)
    record = next(
        record
        for record in controller.records
        if record.request.request_id == rejected.payload["request_id"]
        and record.result.result_id == rejected.payload["result_id"]
    )
    assert isinstance(record.result.payload, dict)
    index, completed = next(
        (index, event)
        for index, event in enumerate(events)
        if event.event_type == "movement_activation_completed"
    )
    assert isinstance(completed.payload, dict)
    # This is a hand-edited pure owner negative, not a generated lifecycle state.
    changed = deepcopy(completed.payload)
    changed["proposal_request_id"] = record.request.request_id
    changed["witness"] = record.result.payload["witness"]
    with pytest.raises(GameLifecycleError, match="movement proposal authority drifted"):
        validate_movement_completion_decision_authority(
            event_records=events,
            decision_records=controller.records,
            mutation_index=index,
            payload=changed,
        )


@pytest.mark.parametrize("action", ["normal_move", "advance"])
@pytest.mark.parametrize("failed_setup", [False, True])
def test_movement_retries_then_embark_restore_and_replay(action: str, failed_setup: bool) -> None:
    from tests.movement_submission_helpers import straight_line_witness_for_state

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.movement_proposals import MovementProposalPayload

    session = two_carrier_disembark_session(nearby_embarking_unit=True)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    if failed_setup:
        submission = _select_disembark(session, prefix="order101:retry-chain")
        result = session.submit_parameterized_payload(
            request_id=submission.proposal_request_id,
            result_id="order101:retry-chain:failed-setup",
            payload=validate_json_value(submission.to_payload()),
        )
        assert result.status_kind is LifecycleStatusKind.INVALID
    unit_id = "army-alpha:remaining-unit"
    for index, option in enumerate((unit_id, action)):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id=f"order101:retry-chain:select:{index}",
            option_id=option,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    state = session.lifecycle.state
    assert state is not None
    requests: list[str] = []
    for index, dx in enumerate((100, 80, 0)):
        request = pending_request(session)
        requests.append(request.request_id)
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        result = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"order101:retry-chain:path:{index}",
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=unit_id,
                    movement_phase_action=action,
                    movement_mode=MovementMode.NORMAL
                    if action == "normal_move"
                    else MovementMode.ADVANCE,
                    witness=straight_line_witness_for_state(state, unit_instance_id=unit_id, dx=dx),
                ).to_payload()
            ),
        )
        assert (result.status_kind is LifecycleStatusKind.INVALID) == (index < 2), result
    assert len(set(requests)) == 3
    request = pending_request(session)
    assert request.decision_type == "select_embark_transport"
    result = session.submit_option(
        request_id=request.request_id,
        result_id="order101:retry-chain:embark",
        option_id=TRANSPORT_ID,
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    _assert_restore_and_exact_replay(session, initial)
    assert session.lifecycle.to_payload() == snapshot
    assert {
        record["result"]["result_id"]
        for record in snapshot["decisions"]["records"]
        if record["request"]["request_id"] in requests
    } == {f"order101:retry-chain:path:{index}" for index in range(3)}
    _assert_rejected_proposal_cannot_authorize_completion(session)


@pytest.mark.parametrize("rejections", [1, 2])
def test_fall_back_retries_then_embark_restore_and_replay(rejections: int) -> None:
    from tests.disembark_eligibility_helpers import disembark_session
    from tests.movement_submission_helpers import straight_line_witness_for_state

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.movement_proposals import MovementProposalPayload
    from warhammer40k_core.engine.phases.movement_model import FallBackModeKind
    from warhammer40k_core.geometry.pose import Pose

    session = disembark_session(
        embarked_passenger=False,
        unit_poses={
            PASSENGER_ID: tuple(
                Pose.at(x, y) for x, y in ((2.6, 9), (4, 9), (5.4, 9), (3.3, 10.2), (4.7, 10.2))
            ),
            TRANSPORT_ID: (Pose.at(4, 19),),
            "army-beta:enemy-unit": tuple(
                Pose.at(x, y) for x, y in ((2.6, 7.5), (4, 7.5), (5.4, 7.5), (3.3, 6.3), (4.7, 6.3))
            ),
            "army-alpha:remaining-unit": tuple(Pose.at(30 + 2 * index, 30) for index in range(5)),
        },
    )
    pending_request(session)
    initial = session.lifecycle.to_payload()
    for index, option in enumerate((PASSENGER_ID, "fall_back:ordered_retreat")):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id=f"order101:fall-back-retry:select:{index}",
            option_id=option,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    state = session.lifecycle.state
    assert state is not None
    for index in range(rejections + 1):
        request = pending_request(session)
        proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
        result = session.submit_parameterized_payload(
            request_id=request.request_id,
            result_id=f"order101:fall-back-retry:path:{index}",
            payload=validate_json_value(
                MovementProposalPayload(
                    proposal_request_id=request.request_id,
                    proposal_kind=proposal.proposal_kind,
                    unit_instance_id=PASSENGER_ID,
                    movement_phase_action="fall_back",
                    movement_mode=MovementMode.FALL_BACK,
                    fall_back_mode=FallBackModeKind.ORDERED_RETREAT.value,
                    witness=straight_line_witness_for_state(
                        state, unit_instance_id=PASSENGER_ID, dy=0 if index < rejections else 6
                    ),
                ).to_payload()
            ),
        )
        assert (result.status_kind is LifecycleStatusKind.INVALID) == (index < rejections), result
    request = pending_request(session)
    assert request.decision_type == "select_embark_transport"
    result = session.submit_option(
        request_id=request.request_id,
        result_id="order101:fall-back-retry:embark",
        option_id=TRANSPORT_ID,
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(snapshot).to_payload() == snapshot
    _assert_restore_and_exact_replay(session, initial)
    assert session.lifecycle.to_payload() == snapshot
    _assert_rejected_proposal_cannot_authorize_completion(session)


def test_failed_setup_terminal_cargo_accepts_later_passenger_transfer() -> None:
    from tests.movement_submission_helpers import straight_line_witness_for_state

    from warhammer40k_core.core.ruleset_descriptor import MovementMode
    from warhammer40k_core.engine.movement_proposals import MovementProposalPayload
    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload
    from warhammer40k_core.geometry.pose import Pose

    session = two_carrier_disembark_session(close_carriers=True, diameter=1)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101:passenger-transfer")
    rejected = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:passenger-transfer:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert rejected.status_kind is LifecycleStatusKind.INVALID
    for index, option in enumerate((PASSENGER_ID, "disembark")):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id=f"order101:passenger-transfer:retry:{index}",
            option_id=option,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    placement = large_disembark_placement(session)
    accepted = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:passenger-transfer:disembarked",
        payload=validate_json_value(
            replace(
                submission,
                proposal_request_id=request.request_id,
                attempted_placement=replace(
                    placement,
                    model_placements=tuple(
                        replace(row, pose=Pose.at(7.2 + index * 1.4, 13.25))
                        for index, row in enumerate(placement.model_placements)
                    ),
                ),
            ).to_payload()
        ),
    )
    assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
    request = pending_request(session)
    assert request.decision_type == "select_movement_action", request
    result = session.submit_option(
        request_id=request.request_id,
        result_id="order101:passenger-transfer:finish-disembark-action",
        option_id="normal_move",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:passenger-transfer:finish-disembark-path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=PASSENGER_ID,
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL,
                witness=straight_line_witness_for_state(state, unit_instance_id=PASSENGER_ID),
            ).to_payload()
        ),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    for index in range(80):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if (
            state.battle_round == 2
            and state.active_player_id == "player-a"
            and state.current_battle_phase is BattlePhase.MOVEMENT
        ):
            break
        if request.decision_type == "submit_stratagem_target_proposal":
            result = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"order101:passenger-transfer:advance:{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            options = {
                "select_movement_unit": request.options[0].option_id,
                "select_movement_action": "remain_stationary",
                "select_shooting_unit": "complete_shooting_phase",
                "select_charging_unit": "complete_charge_phase",
            }
            assert request.decision_type in options, request
            result = session.submit_option(
                request_id=request.request_id,
                result_id=f"order101:passenger-transfer:advance:{index}",
                option_id=options[request.decision_type],
            )
        assert result.status_kind is not LifecycleStatusKind.INVALID, result
    else:
        raise AssertionError("Failed to reach the passenger's next Movement phase.")
    for index, option in enumerate((PASSENGER_ID, "normal_move")):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id=f"order101:passenger-transfer:move:{index}",
            option_id=option,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:passenger-transfer:path",
        payload=validate_json_value(
            MovementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=PASSENGER_ID,
                movement_phase_action="normal_move",
                movement_mode=MovementMode.NORMAL,
                witness=straight_line_witness_for_state(
                    state, unit_instance_id=PASSENGER_ID, dx=4.5
                ),
            ).to_payload()
        ),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    request = pending_request(session)
    assert request.decision_type == "select_embark_transport", request
    result = session.submit_option(
        request_id=request.request_id,
        result_id="order101:passenger-transfer:embarked",
        option_id="army-alpha:other-transport",
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    cargo = state.transport_cargo_state_for_embarked_unit(PASSENGER_ID)
    assert cargo is not None
    assert cargo.transport_unit_instance_id == "army-alpha:other-transport"
    _assert_restore_and_exact_replay(session, initial)
    drifted_completion = deepcopy(session.lifecycle.to_payload())
    completion = next(
        event
        for event in drifted_completion["decisions"]["event_log"]
        if event["event_type"] == "movement_activation_completed"
        and isinstance(event["payload"], dict)
        and event["payload"].get("result_id") == "order101:passenger-transfer:move:1"
    )
    completion_payload = completion["payload"]
    assert isinstance(completion_payload, dict)
    transition = completion_payload["transition_batch"]
    assert isinstance(transition, dict)
    displacements = transition["displacements"]
    assert isinstance(displacements, list)
    assert len(displacements) == 5
    displacements.pop()
    with pytest.raises(GameLifecycleError, match="Embark completion context drift"):
        GameLifecycle.from_payload(drifted_completion)
    forged = deepcopy(session.lifecycle.to_payload())
    swap_terminal_cargo_membership(forged)
    with pytest.raises(GameLifecycleError, match="terminal cargo location authority drift"):
        GameLifecycle.from_payload(forged)


@pytest.mark.parametrize("attached", [False, True])
def test_cargo_suffix_validator_accepts_real_emergency_disembark(attached: bool) -> None:
    """Validate an actual emergency owner suffix; this is not a failed-prefix replay."""
    from tests.emergency_geometry_helpers import emergency_geometry_session

    from warhammer40k_core.engine.transport_cargo_location_history import (
        validate_transport_cargo_location_suffix,
    )

    session, submission = emergency_geometry_session(attached=attached, rectangular=False)
    state = session.lifecycle.state
    assert state is not None
    boundary_state = deepcopy(state)
    initial_event_count = len(session.lifecycle.decision_controller.event_log.records)
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:emergency-owner:accepted",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    events = session.lifecycle.decision_controller.event_log.records
    disembarked = next(event for event in events if event.event_type == "unit_disembarked")
    assert isinstance(disembarked.payload, dict)
    assert disembarked.payload["active_player_id"] == "player-a"
    assert pending_request(session).actor_id in state.player_ids
    validate_transport_cargo_location_suffix(
        boundary_state=boundary_state,
        state=state,
        event_records=events,
        decision_records=session.lifecycle.decision_controller.records,
        initial_event_count=initial_event_count,
        affected_unit_instance_ids=frozenset({submission.unit_instance_id}),
    )


def test_cargo_suffix_validator_accepts_emergency_component_omission() -> None:
    """Validate a genuine emergency suffix that destroys an omitted physical component."""
    from warhammer40k_core.engine.destroyed_transport_rules_unit_disembark import (
        emergency_disembark_omitted_model_evidence_from_event_payload,
    )
    from warhammer40k_core.engine.transport_cargo_location_history import (
        validate_transport_cargo_location_suffix,
    )

    session, submission = emergency_component_omission_session()
    state = session.lifecycle.state
    assert state is not None
    boundary_state = deepcopy(state)
    initial_event_count = len(session.lifecycle.decision_controller.event_log.records)
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:emergency-component:accepted",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID, result
    events = session.lifecycle.decision_controller.event_log.records
    disembarked = next(event for event in events if event.event_type == "unit_disembarked")
    assert isinstance(disembarked.payload, dict)
    evidence = emergency_disembark_omitted_model_evidence_from_event_payload(disembarked.payload)
    assert evidence is not None
    assert evidence.destroyed_model_instance_ids == (
        "army-beta:leader-unit:core-character-leader:001",
    )
    assert len(evidence.placed_model_instance_ids) == 5
    assert disembarked.payload["active_player_id"] == "player-a"
    validate_transport_cargo_location_suffix(
        boundary_state=boundary_state,
        state=state,
        event_records=events,
        decision_records=session.lifecycle.decision_controller.records,
        initial_event_count=initial_event_count,
        affected_unit_instance_ids=frozenset({submission.unit_instance_id}),
    )


@pytest.mark.parametrize("finish", ["retry", "stationary", "other_unit"])
def test_failed_setup_reselection_restore_both_viewers_and_exact_replay(finish: str) -> None:
    session = large_disembark_session()
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101")
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    _assert_restore_and_exact_replay(session, initial)
    restored = LocalGameSession(
        lifecycle=GameLifecycle.from_payload(session.lifecycle.to_payload())
    )
    for target in (session, restored):
        request = pending_request(target)
        unit_id = "army-alpha:remaining-unit" if finish == "other_unit" else PASSENGER_ID
        target.submit_option(
            request_id=request.request_id, result_id="order101:reselect", option_id=unit_id
        )
        request = pending_request(target)
        target.submit_option(
            request_id=request.request_id,
            result_id="order101:new-action",
            option_id="disembark" if finish == "retry" else "remain_stationary",
        )
        if finish == "retry":
            request = pending_request(target)
            accepted = target.submit_parameterized_payload(
                request_id=request.request_id,
                result_id="order101:valid-retry",
                payload=validate_json_value(
                    replace(
                        submission,
                        proposal_request_id=request.request_id,
                        attempted_placement=large_disembark_placement(target),
                    ).to_payload()
                ),
            )
            assert accepted.status_kind is not LifecycleStatusKind.INVALID, accepted
        state = target.lifecycle.state
        assert state is not None
        assert state.movement_phase_state is not None
        assert unit_id in state.movement_phase_state.selected_unit_ids
        if finish != "retry":
            assert unit_id in state.movement_phase_state.moved_unit_ids
        if finish == "other_unit":
            assert PASSENGER_ID not in state.movement_phase_state.selected_unit_ids
    assert session.lifecycle.to_payload() == restored.lifecycle.to_payload()
    _assert_restore_and_exact_replay(session, initial)


@pytest.mark.parametrize("malformation", ["missing", "stale", "wrong_transport"])
def test_malformed_or_stale_setup_preserves_selection_and_pending_proposal(
    malformation: str,
) -> None:
    session = large_disembark_session()
    submission = _select_disembark(session, prefix="order101")
    state = session.lifecycle.state
    assert state is not None
    before = state.to_payload()
    records = tuple(session.lifecycle.decision_controller.records)
    request = pending_request(session)
    payload = validate_json_value(submission.to_payload())
    assert isinstance(payload, dict)
    if malformation == "missing":
        del payload["disembark_mode"]
    elif malformation == "stale":
        payload["proposal_request_id"] = "obsolete-request"
    else:
        payload["transport_unit_instance_id"] = "wrong-transport"
    result = session.submit_parameterized_payload(
        request_id=request.request_id, result_id="order101:malformed", payload=payload
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before
    assert tuple(session.lifecycle.decision_controller.records) == records
    assert pending_request(session) == request
    assert state.movement_phase_state is not None
    assert PASSENGER_ID in state.movement_phase_state.selected_unit_ids


@pytest.mark.parametrize("model_index", [0, -1])
def test_failed_setup_historical_inventory_survives_later_recorded_casualty(
    model_index: int,
) -> None:
    from tests.destruction_occurrence_fixture_helpers import (
        destroy_rule_model_for_fixture,
        finish_core_destructions_for_fixture,
    )

    from warhammer40k_core.engine.damage_allocation import model_by_id

    session = large_disembark_session()
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101:later-casualty")
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:later-casualty:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:later-casualty:reselect",
        option_id=PASSENGER_ID,
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:later-casualty:retry-action",
        option_id="disembark",
    )
    request = pending_request(session)
    accepted_placement = large_disembark_placement(session)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:later-casualty:accepted",
        payload=validate_json_value(
            replace(
                submission,
                proposal_request_id=request.request_id,
                attempted_placement=accepted_placement,
            ).to_payload()
        ),
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    _assert_restore_and_exact_replay(session, initial)
    state = session.lifecycle.state
    assert state is not None
    model_id = accepted_placement.model_placements[model_index].model_instance_id
    destroy_rule_model_for_fixture(
        state=state,
        decisions=session.lifecycle.decision_controller,
        model_id=model_id,
        destroying_player_id="player-b",
        source_unit_id=None,
        source_model_id=None,
    )
    finish_core_destructions_for_fixture(
        state=state, decisions=session.lifecycle.decision_controller
    )
    assert not model_by_id(state=state, model_instance_id=model_id).is_alive
    snapshot = session.lifecycle.to_payload()
    restored = LocalGameSession(GameLifecycle.from_payload(deepcopy(snapshot)))
    assert restored.lifecycle.to_payload() == snapshot
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)
    corrupted = deepcopy(snapshot)
    corrupt_failed_setup_authority(corrupted, tamper="missing_model")
    with pytest.raises(GameLifecycleError, match="physical inventory authority drift"):
        GameLifecycle.from_payload(corrupted)


@pytest.mark.parametrize(
    "transport_id",
    [
        "army-alpha:nonexistent-forged-transport",
        "army-alpha:other-transport",
    ],
)
def test_failed_setup_rejects_coherent_historical_wrong_carrier(transport_id: str) -> None:
    session = two_carrier_disembark_session()
    submission = _select_disembark(session, prefix="order101:carrier-proof")
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:carrier-proof:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(deepcopy(snapshot)).to_payload() == snapshot
    corrupted = deepcopy(snapshot)
    forge_failed_disembark_transport(corrupted, transport_id=transport_id)
    assert corrupted["state"] == snapshot["state"]
    assert "modifier_evaluation_history_origin" in corrupted
    assert "modifier_evaluation_history_origin" in snapshot
    assert (
        corrupted["modifier_evaluation_history_origin"]
        == snapshot["modifier_evaluation_history_origin"]
    )
    with pytest.raises(GameLifecycleError, match=r"historical prior-location .*drift"):
        GameLifecycle.from_payload(corrupted)


@pytest.mark.parametrize("tamper", ["missing", "late", "prefix", "config"])
def test_failed_setup_rejects_missing_or_unbound_cargo_origin(tamper: str) -> None:
    session = large_disembark_session()
    submission = _select_disembark(session, prefix="order101:origin-proof")
    session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:origin-proof:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(deepcopy(snapshot)).to_payload() == snapshot
    corrupted = deepcopy(snapshot)
    assert "modifier_evaluation_history_origin" in corrupted
    origin = corrupted["modifier_evaluation_history_origin"]
    if tamper == "missing":
        del corrupted["modifier_evaluation_history_origin"]
    elif tamper == "late":
        del corrupted["modifier_evaluation_history_origin"]
        late = deepcopy(corrupted)
        corrupted["modifier_evaluation_history_origin"] = cast(dict[str, JsonValue], late)
    elif tamper == "config":
        config = origin["config"]
        assert isinstance(config, dict)
        config["game_id"] = "forged-origin-game"
    else:
        decisions = origin["decisions"]
        assert isinstance(decisions, dict)
        event_log = decisions["event_log"]
        assert isinstance(event_log, list)
        event = event_log[0]
        assert isinstance(event, dict)
        event["event_type"] = "forged-origin-event"
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(corrupted)


@pytest.mark.parametrize(
    "tamper",
    [
        "missing_model_and_diagnostic",
        "missing_diagnostic_model",
        "foreign_diagnostic_blocker",
        "failure_arrived_reserve",
    ],
)
def test_failed_reserve_setup_authenticates_complete_inventory_after_movement_ends(
    tamper: str,
) -> None:
    from tests.order63_reserve_transport_helpers import placement

    from warhammer40k_core.engine.phase import BattlePhase
    from warhammer40k_core.engine.stratagems_requests import stratagem_decline_payload

    session = reserve_inventory_session()
    pending_request(session)
    initial = session.lifecycle.to_payload()
    for index, choice in enumerate((PASSENGER_ID, "ingress")):
        request = pending_request(session)
        result = session.submit_option(
            request_id=request.request_id,
            result_id=f"reserve-inventory:{index}",
            option_id=choice,
        )
        assert result.status_kind is not LifecycleStatusKind.INVALID
    request = pending_request(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="reserve-inventory:failed",
        payload=validate_json_value(
            PlacementProposalPayload(
                proposal_request_id=request.request_id,
                proposal_kind=proposal.proposal_kind,
                unit_instance_id=PASSENGER_ID,
                placement_kind=BattlefieldPlacementKind.STRATEGIC_RESERVES,
                attempted_placement=placement(session, PASSENGER_ID, x=12, y=12),
            ).to_payload()
        ),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    for index in range(30):
        request = pending_request(session)
        state = session.lifecycle.state
        assert state is not None
        if state.current_battle_phase is not BattlePhase.MOVEMENT:
            break
        if request.decision_type == "submit_stratagem_target_proposal":
            result = session.submit_parameterized_payload(
                request_id=request.request_id,
                result_id=f"reserve-inventory:advance:{index}",
                payload=stratagem_decline_payload(),
            )
        else:
            assert request.decision_type in {"select_movement_unit", "select_movement_action"}
            result = session.submit_option(
                request_id=request.request_id,
                result_id=f"reserve-inventory:advance:{index}",
                option_id=request.options[0].option_id
                if request.decision_type == "select_movement_unit"
                else "remain_stationary",
            )
        assert result.status_kind is not LifecycleStatusKind.INVALID
    else:
        raise AssertionError("Failed to leave Movement through recorded choices.")
    assert state.current_battle_phase is BattlePhase.SHOOTING
    _assert_restore_and_exact_replay(session, initial)
    snapshot = session.lifecycle.to_payload()
    corrupted = deepcopy(snapshot)
    corrupt_failed_setup_authority(corrupted, tamper=tamper)
    assert corrupted["state"] == snapshot["state"]
    assert "modifier_evaluation_history_origin" in corrupted
    assert "modifier_evaluation_history_origin" in snapshot
    assert (
        corrupted["modifier_evaluation_history_origin"]
        == snapshot["modifier_evaluation_history_origin"]
    )
    with pytest.raises(GameLifecycleError, match=r"authority drift|reconstruction drift"):
        GameLifecycle.from_payload(corrupted)


@pytest.mark.parametrize("reserves", [False, True])
def test_failed_setup_historical_inventory_survives_later_offboard_leader_revival(
    reserves: bool,
) -> None:
    from warhammer40k_core.engine.damage_allocation import model_by_id
    from warhammer40k_core.engine.healing import resolve_healing_until_blocked

    session, effect, returned_id, attempted_ids = failed_setup_before_offboard_revival_session(
        reserves=reserves
    )
    assert returned_id not in attempted_ids
    snapshot = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(deepcopy(snapshot)).to_payload() == snapshot
    state = session.lifecycle.state
    assert state is not None
    _, healing = resolve_healing_until_blocked(
        state=state,
        decisions=session.lifecycle.decision_controller,
        ruleset_descriptor=state.runtime_ruleset_descriptor(),
        effect=effect,
    )
    assert healing is not None
    request = pending_request(session)
    assert request.decision_type == "select_movement_unit"
    session.submit_option(
        request_id=request.request_id,
        result_id="late-revival:transport-selection",
        option_id=TRANSPORT_ID,
    )
    request = pending_request(session)
    assert request.request_id == healing.request_id
    assert state.movement_phase_state is not None
    selection_before = state.movement_phase_state.to_payload()
    result = session.submit_option(
        request_id=request.request_id,
        result_id="late-revival:return",
        option_id=request.options[0].option_id,
    )
    assert result.status_kind is not LifecycleStatusKind.INVALID
    assert model_by_id(state=state, model_instance_id=returned_id).is_alive
    if reserves:
        reserve = state.reserve_state_for_unit("army-alpha:passengers")
        assert reserve is not None
        assert reserve.is_unarrived
        assert state.battlefield_state is not None
        assert returned_id not in state.battlefield_state.placed_model_ids()
    else:
        assert returned_id in state.embarked_model_ids()
    assert state.movement_phase_state.to_payload() == selection_before
    snapshot = session.lifecycle.to_payload()
    restored = LocalGameSession(GameLifecycle.from_payload(deepcopy(snapshot)))
    assert restored.lifecycle.to_payload() == snapshot
    for viewer in state.player_ids:
        assert session.view(viewer_player_id=viewer) == restored.view(viewer_player_id=viewer)
        assert session.events_since(
            EventStreamCursor(), viewer_player_id=viewer
        ) == restored.events_since(EventStreamCursor(), viewer_player_id=viewer)


def test_failed_setup_history_accepts_real_automatic_attack_records_between_attempts() -> None:
    session, initial = failed_setup_automatic_record_session()
    events = session.lifecycle.decision_controller.event_log.records
    assert sum(event.event_type == "movement_setup_failed" for event in events) == 2
    assert {"select_resolve_target_unit", "select_attack_weapon_group"} <= {
        record.request.decision_type for record in session.lifecycle.decision_controller.records
    }
    _assert_restore_and_exact_replay(session, initial)


@pytest.mark.parametrize("deep_strike", [False, True])
def test_failed_ingress_restores_reserve_and_loaded_cargo_reselection(deep_strike: bool) -> None:
    from tests.order63_reserve_transport_helpers import placement, reserve_transport_session

    session = reserve_transport_session(deep_strike=deep_strike)
    request = pending_request(session)
    initial = session.lifecycle.to_payload()
    session.submit_option(
        request_id=request.request_id, result_id="order101:carrier", option_id=TRANSPORT_ID
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="order101:ingress", option_id="ingress"
    )
    request = pending_request(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    submission = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=proposal.proposal_kind,
        unit_instance_id=TRANSPORT_ID,
        placement_kind=BattlefieldPlacementKind.DEEP_STRIKE
        if deep_strike
        else BattlefieldPlacementKind.STRATEGIC_RESERVES,
        attempted_placement=placement(session, TRANSPORT_ID, x=100, y=100),
    )
    state = session.lifecycle.state
    assert state is not None
    before = (
        state.battlefield_state,
        tuple(state.reserve_states),
        tuple(state.transport_cargo_states),
    )
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:failed-ingress",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert (
        state.battlefield_state,
        tuple(state.reserve_states),
        tuple(state.transport_cargo_states),
    ) == before
    assert state.movement_phase_state is not None
    assert TRANSPORT_ID not in state.movement_phase_state.selected_unit_ids
    _assert_restore_and_exact_replay(session, initial)
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="order101:reselect-carrier", option_id=TRANSPORT_ID
    )
    request = pending_request(session)
    assert {"remain_stationary", "ingress"} <= {option.option_id for option in request.options}
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:carrier-stationary",
        option_id="remain_stationary",
    )
    assert state.reserve_state_for_unit(TRANSPORT_ID) is not None
    assert state.battlefield_state is not None
    assert state.battlefield_state.unit_placement_or_none(TRANSPORT_ID) is None
    _assert_restore_and_exact_replay(session, initial)


@pytest.mark.parametrize(
    "corruption",
    ["source", "invalid_event", "selection", "after", "current_selection", "missing_receipt"],
)
def test_restore_rejects_forged_failed_setup_authority(corruption: str) -> None:
    session = large_disembark_session()
    submission = _select_disembark(session, prefix="order101")
    session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    snapshot = deepcopy(session.lifecycle.to_payload())
    events = snapshot["decisions"]["event_log"]
    receipt_event = next(
        event for event in events if event["event_type"] == "movement_setup_failed"
    )
    receipt = receipt_event["payload"]
    assert isinstance(receipt, dict)
    if corruption == "source":
        receipt["source_observation_sha256"] = "0" * 64
    elif corruption == "invalid_event":
        receipt["invalid_event_id"] = "event-000001"
    elif corruption == "selection":
        receipt["selection_result_id"] = "unrecorded-selection"
    elif corruption == "after":
        after = receipt["movement_phase_state_after"]
        assert isinstance(after, dict)
        after["selected_unit_ids"] = [PASSENGER_ID]
    elif corruption == "current_selection":
        state = snapshot["state"]
        assert state is not None
        movement = state["movement_phase_state"]
        assert movement is not None
        movement["selected_unit_ids"] = [PASSENGER_ID]
        movement["moved_unit_ids"] = [PASSENGER_ID]
    else:
        events.remove(receipt_event)
        for index, event in enumerate(events, 1):
            event["event_id"] = f"event-{index:06d}"
    with pytest.raises(GameLifecycleError, match=r"Failed setup|Failed move-type setup|Movement"):
        GameLifecycle.from_payload(snapshot)


def test_failed_setup_keeps_another_units_completed_activation() -> None:
    session = large_disembark_session()
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:other",
        option_id="army-alpha:remaining-unit",
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:other-stationary",
        option_id="remain_stationary",
    )
    state = session.lifecycle.state
    assert state is not None
    assert state.movement_phase_state is not None
    before = state.movement_phase_state
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101")
    session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    after = state.movement_phase_state
    assert after is not None
    assert after.selected_unit_ids == before.selected_unit_ids
    assert after.moved_unit_ids == before.moved_unit_ids
    assert after.movement_distance_records == before.movement_distance_records
    _assert_restore_and_exact_replay(session, initial)
    snapshot = deepcopy(session.lifecycle.to_payload())
    receipt_event = next(
        event
        for event in snapshot["decisions"]["event_log"]
        if event["event_type"] == "movement_setup_failed"
    )
    receipt = receipt_event["payload"]
    assert isinstance(receipt, dict)
    current_state = snapshot["state"]
    assert current_state is not None
    current_movement = current_state["movement_phase_state"]
    assert current_movement is not None
    for movement in (
        receipt["movement_phase_state_before"],
        receipt["movement_phase_state_after"],
        cast(dict[str, JsonValue], current_movement),
    ):
        assert isinstance(movement, dict)
        for field in ("selected_unit_ids", "moved_unit_ids", "movement_distance_records"):
            values = movement[field]
            assert isinstance(values, list)
            movement[field] = [
                value
                for value in values
                if value != "army-alpha:remaining-unit"
                and not (
                    isinstance(value, dict)
                    and value.get("unit_instance_id") == "army-alpha:remaining-unit"
                )
            ]
    with pytest.raises(GameLifecycleError, match="selection projection drift"):
        GameLifecycle.from_payload(snapshot)


@pytest.mark.parametrize("forgery", ["selection", "rejected_decision"])
def test_repeated_failure_cannot_reuse_previous_selection_or_rejection(forgery: str) -> None:
    session = large_disembark_session()
    request = pending_request(session)
    initial = session.lifecycle.to_payload()
    for index in range(2):
        submission = _select_disembark(session, prefix=f"order101:{index}")
        result = session.submit_parameterized_payload(
            request_id=submission.proposal_request_id,
            result_id=f"order101:{index}:failed",
            payload=validate_json_value(submission.to_payload()),
        )
        assert result.status_kind is LifecycleStatusKind.INVALID
        request = pending_request(session)
        assert request.decision_type == "select_movement_unit"
    _assert_restore_and_exact_replay(session, initial)
    snapshot = deepcopy(session.lifecycle.to_payload())
    events = snapshot["decisions"]["event_log"]
    receipts = [event for event in events if event["event_type"] == "movement_setup_failed"]
    first, second = (event["payload"] for event in receipts)
    assert isinstance(first, dict)
    assert isinstance(second, dict)
    if forgery == "selection":
        first_before, second_before = (
            receipt["movement_phase_state_before"] for receipt in (first, second)
        )
        assert isinstance(first_before, dict)
        assert isinstance(second_before, dict)
        second_before["active_selection"] = first_before["active_selection"]
        second["selection_request_id"] = first["selection_request_id"]
        second["selection_result_id"] = first["selection_result_id"]
    else:
        invalids = [
            event for event in events if event["event_type"] == "disembark_placement_invalid"
        ]
        invalids[1]["payload"] = deepcopy(invalids[0]["payload"])
        copied = deepcopy(first)
        copied["invalid_event_id"] = invalids[1]["event_id"]
        receipts[1]["payload"] = copied
    with pytest.raises(
        GameLifecycleError, match=r"selection projection drift|decision closure drift"
    ):
        GameLifecycle.from_payload(snapshot)


@pytest.mark.parametrize("impossible", [False, True])
def test_combat_failed_setup_and_tactical_available_have_distinct_continuations(
    impossible: bool,
) -> None:
    session = large_disembark_session(diameter=100 if impossible else 5)
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101:combat")
    submission = replace(
        submission,
        disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
        attempted_placement=large_disembark_placement(session),
    )
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:combat-rejected",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    request = pending_request(session)
    state = session.lifecycle.state
    assert state is not None
    assert state.movement_phase_state is not None
    if impossible:
        assert request.decision_type == "select_movement_unit"
        assert PASSENGER_ID not in state.movement_phase_state.selected_unit_ids
    else:
        assert request.decision_type == "submit_placement_proposal"
        assert PASSENGER_ID in state.movement_phase_state.selected_unit_ids
        assert not any(
            event.event_type == "movement_setup_failed"
            for event in session.lifecycle.decision_controller.event_log.records
        )
    _assert_restore_and_exact_replay(session, initial)


@pytest.mark.parametrize("missing_event", ["decision_requested", "decision_recorded"])
def test_failed_setup_requires_exact_action_events(missing_event: str) -> None:
    session = large_disembark_session()
    submission = _select_disembark(session, prefix="order101")
    session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    snapshot = deepcopy(session.lifecycle.to_payload())
    record = next(
        record
        for record in snapshot["decisions"]["records"]
        if record["request"]["decision_type"] == "select_movement_action"
    )
    expected = record["request"] if missing_event == "decision_requested" else record
    event = next(
        event
        for event in snapshot["decisions"]["event_log"]
        if event["event_type"] == missing_event and event["payload"] == expected
    )
    event["event_type"] = "unrelated_action_event"
    with pytest.raises(GameLifecycleError, match="exact decision"):
        GameLifecycle.from_payload(snapshot)


@pytest.mark.parametrize("forgery", ["actor", "game", "round", "unit"])
def test_failed_setup_rejects_coordinated_action_context_forgery(forgery: str) -> None:
    session = large_disembark_session()
    submission = _select_disembark(session, prefix="order101")
    session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:failed",
        payload=validate_json_value(submission.to_payload()),
    )
    snapshot = deepcopy(session.lifecycle.to_payload())
    record = next(
        record
        for record in snapshot["decisions"]["records"]
        if record["request"]["decision_type"] == "select_movement_action"
    )
    request = record["request"]
    if forgery == "actor":
        request["actor_id"] = "player-b"
        record["result"]["actor_id"] = "player-b"
    else:
        payload = request["payload"]
        assert isinstance(payload, dict)
        if forgery == "game":
            payload["game_id"] = "unrelated-game"
        elif forgery == "round":
            payload["battle_round"] = 99
        else:
            payload["unit_instance_id"] = "army-alpha:remaining-unit"
    for event in snapshot["decisions"]["event_log"]:
        event_payload = event["payload"]
        if not isinstance(event_payload, dict):
            continue
        if (
            event["event_type"] == "decision_requested"
            and event_payload.get("request_id") == request["request_id"]
        ):
            event["payload"] = cast(JsonValue, deepcopy(request))
        elif (
            event["event_type"] == "decision_recorded"
            and event_payload.get("record_id") == record["record_id"]
        ):
            event["payload"] = cast(JsonValue, deepcopy(record))
    with pytest.raises(
        GameLifecycleError, match=r"selected action actor drift|selected action context drift"
    ):
        GameLifecycle.from_payload(snapshot)


def test_failed_attached_setup_preserves_every_embarked_component_and_replays() -> None:
    from tests.core_stratagem_helpers import (
        _complete_current_command_for_fixture,  # pyright: ignore[reportPrivateUsage]
    )
    from tests.support.ability_presence_fixtures import ability_presence_fixture

    from warhammer40k_core.engine.battlefield_state import ModelPlacement, UnitPlacement
    from warhammer40k_core.engine.reaction_queue import ReactionQueue
    from warhammer40k_core.engine.rules_unit_placement import RulesUnitPlacement
    from warhammer40k_core.engine.rules_units import rules_unit_view_by_id
    from warhammer40k_core.geometry.pose import Pose

    config, fixture_state, decisions = ability_presence_fixture(embarked=True, attached=True)
    lifecycle = GameLifecycle.from_payload(
        {
            "config": config.to_payload(),
            "parameterized_movement_proposals": True,
            "state": fixture_state.to_payload(),
            "decisions": decisions.to_payload(),
            "reaction_queue": ReactionQueue().to_payload(),
        }
    )
    session = LocalGameSession(_complete_current_command_for_fixture(lifecycle))
    state = session.lifecycle.state
    assert state is not None
    view = rules_unit_view_by_id(state=state, unit_instance_id="army-alpha:passengers")
    assert len(view.component_unit_instance_ids) == 2
    request = pending_request(session)
    initial = session.lifecycle.to_payload()
    before_battlefield = state.battlefield_state
    before_cargo = tuple(state.transport_cargo_states)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:attached-unit",
        option_id=view.unit_instance_id,
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id, result_id="order101:attached-action", option_id="disembark"
    )
    request = pending_request(session)
    proposal = MovementProposalRequest.from_decision_request_payload(request.payload)
    assert proposal.context is not None
    placement = RulesUnitPlacement(
        rules_unit_instance_id=view.unit_instance_id,
        component_unit_placements=tuple(
            UnitPlacement(
                army_id="army-alpha",
                player_id=view.owner_player_id,
                unit_instance_id=component.unit.unit_instance_id,
                model_placements=tuple(
                    ModelPlacement(
                        army_id="army-alpha",
                        player_id=view.owner_player_id,
                        unit_instance_id=component.unit.unit_instance_id,
                        model_instance_id=model.model_instance_id,
                        pose=Pose.at(100 + index * 2, 100),
                    )
                    for index, model in enumerate(component.unit.alive_own_models())
                ),
            )
            for component in view.living_components
        ),
    )
    submission = PlacementProposalPayload(
        proposal_request_id=request.request_id,
        proposal_kind=ProposalKind.DISEMBARK,
        unit_instance_id=view.unit_instance_id,
        placement_kind=BattlefieldPlacementKind.DISEMBARK,
        attempted_rules_unit_placement=placement,
        transport_unit_instance_id="army-alpha:transport",
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        transport_movement_status=TransportMovementStatus.NOT_MOVED,
    )
    before_malformed = state.to_payload()
    before_records = session.lifecycle.decision_controller.records
    missing_component = replace(
        submission,
        attempted_rules_unit_placement=replace(
            placement, component_unit_placements=placement.component_unit_placements[:1]
        ),
    )
    malformed = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:attached-missing-component",
        payload=validate_json_value(missing_component.to_payload()),
    )
    assert malformed.status_kind is LifecycleStatusKind.INVALID
    assert state.to_payload() == before_malformed
    assert session.lifecycle.decision_controller.records == before_records
    assert pending_request(session) == request
    result = session.submit_parameterized_payload(
        request_id=request.request_id,
        result_id="order101:attached-failed",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert state.battlefield_state == before_battlefield
    assert tuple(state.transport_cargo_states) == before_cargo
    assert state.battlefield_state is not None
    assert all(
        state.battlefield_state.unit_placement_or_none(component_id) is None
        for component_id in view.component_unit_instance_ids
    )
    assert state.movement_phase_state is not None
    assert view.unit_instance_id not in state.movement_phase_state.selected_unit_ids
    request = pending_request(session)
    assert view.unit_instance_id in {option.option_id for option in request.options}
    assert not set(view.component_unit_instance_ids) & {
        option.option_id for option in request.options
    }
    _assert_restore_and_exact_replay(session, initial)
    corrupted = deepcopy(session.lifecycle.to_payload())
    corrupt_failed_setup_authority(corrupted, tamper="missing_component")
    with pytest.raises(GameLifecycleError, match="physical inventory authority drift"):
        GameLifecycle.from_payload(corrupted)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:attached-reselected",
        option_id=view.unit_instance_id,
    )
    request = pending_request(session)
    session.submit_option(
        request_id=request.request_id,
        result_id="order101:attached-stationary",
        option_id="remain_stationary",
    )
    assert tuple(state.transport_cargo_states) == before_cargo
    _assert_restore_and_exact_replay(session, initial)


@pytest.mark.parametrize("combat", [False, True])
@pytest.mark.parametrize(
    "tamper",
    [
        "missing_predecessor",
        "predecessor_authority",
        "predecessor_order",
        "missing_invalid_event",
        "invalid_event_authority",
        "invalid_event_order",
        "empty_violations",
        "missing_source_event",
        "extra_proposal_context",
        "malformed_violations",
        "physical_model_ids",
        "physical_owner",
        "outer_request_id",
        "missing_model",
        "foreign_diagnostic_model",
        "foreign_diagnostic_unit",
        "failure_tactical_available",
        "failure_firing_deck",
        "failure_emergency",
        "missing_diagnostic_model",
        "foreign_diagnostic_blocker",
        "foreign_diagnostic_source",
    ],
)
def test_failed_disembark_rejects_historical_authority_tamper(combat: bool, tamper: str) -> None:
    session = large_disembark_session(diameter=100 if combat else 5)
    submission = _select_disembark(session, prefix="order101:source-proof")
    if combat:
        submission = replace(submission, disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK)
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:source-proof:rejected",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    snapshot = deepcopy(session.lifecycle.to_payload())
    assert GameLifecycle.from_payload(deepcopy(snapshot)).to_payload() == snapshot
    corrupt_failed_setup_authority(snapshot, tamper=tamper)
    with pytest.raises(GameLifecycleError):
        GameLifecycle.from_payload(snapshot)


@pytest.mark.parametrize("retry_count", [1, 3])
def test_combat_tactical_available_then_failed_setup_restores_and_replays(retry_count: int) -> None:
    session = large_disembark_session()
    pending_request(session)
    initial = session.lifecycle.to_payload()
    submission = _select_disembark(session, prefix="order101:combat-chain")
    for index in range(retry_count):
        submission = replace(
            submission,
            proposal_request_id=pending_request(session).request_id,
            disembark_mode=DisembarkModeKind.COMBAT_DISEMBARK,
            attempted_placement=large_disembark_placement(session),
        )
        result = session.submit_parameterized_payload(
            request_id=submission.proposal_request_id,
            result_id=f"order101:combat-chain:{index}",
            payload=validate_json_value(submission.to_payload()),
        )
        assert result.status_kind is LifecycleStatusKind.INVALID
        assert pending_request(session).decision_type == "submit_placement_proposal"
    submission = replace(
        submission,
        proposal_request_id=pending_request(session).request_id,
        disembark_mode=DisembarkModeKind.TACTICAL_DISEMBARK,
        attempted_placement=large_disembark_placement(session, gap=1.01),
    )
    result = session.submit_parameterized_payload(
        request_id=submission.proposal_request_id,
        result_id="order101:combat-chain:failed-tactical",
        payload=validate_json_value(submission.to_payload()),
    )
    assert result.status_kind is LifecycleStatusKind.INVALID
    assert pending_request(session).decision_type == "select_movement_unit"
    _assert_restore_and_exact_replay(session, initial)
    snapshot = session.lifecycle.to_payload()
    for tamper in (
        "invalid_event_authority",
        "missing_source_event",
        "extra_proposal_context",
        "outer_request_id",
    ):
        corrupted = deepcopy(snapshot)
        corrupt_failed_setup_authority(corrupted, tamper=tamper)
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(corrupted)
    for event_type in ("combat_disembark_tactical_available", "placement_proposal_requested"):
        corrupted = deepcopy(snapshot)
        predecessor_event = next(
            event
            for event in corrupted["decisions"]["event_log"]
            if event["event_type"] == event_type
        )
        predecessor_event["event_type"] = "forged-combat-predecessor"
        with pytest.raises(GameLifecycleError):
            GameLifecycle.from_payload(corrupted)

    corrupted = deepcopy(snapshot)
    diagnostic = next(
        event["payload"]
        for event in corrupted["decisions"]["event_log"]
        if event["event_type"] == "combat_disembark_tactical_available"
    )
    assert isinstance(diagnostic, dict)
    violations = diagnostic["violations"]
    assert isinstance(violations, list)
    assert isinstance(violations[0], dict)
    violations[0]["violation_code"] = "unit_placement_drift"
    with pytest.raises(GameLifecycleError, match="Tactical-available diagnostic authority drift"):
        GameLifecycle.from_payload(corrupted)
    corrupted = deepcopy(snapshot)
    first = next(
        record
        for record in corrupted["decisions"]["records"]
        if record["result"]["result_id"] == "order101:combat-chain:0"
    )
    submitted = first["result"]["payload"]
    assert isinstance(submitted, dict)
    attempted = submitted["attempted_placement"]
    assert isinstance(attempted, dict)
    attempted["player_id"] = "forged-owner"
    models = attempted["model_placements"]
    assert isinstance(models, list)
    for model in models:
        assert isinstance(model, dict)
        model["player_id"] = "forged-owner"
    for event in corrupted["decisions"]["event_log"]:
        event_payload = event["payload"]
        if (
            event["event_type"] == "decision_recorded"
            and isinstance(event_payload, dict)
            and event_payload.get("record_id") == first["record_id"]
        ):
            event["payload"] = cast(JsonValue, deepcopy(first))
    with pytest.raises(GameLifecycleError, match="physical inventory authority drift"):
        GameLifecycle.from_payload(corrupted)
