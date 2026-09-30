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
from tests.order101_failed_setup_helpers import corrupt_failed_setup_authority
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
