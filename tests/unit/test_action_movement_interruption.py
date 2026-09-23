"""Core 16.01: completed moves interrupt Actions even with equal endpoint poses."""

from __future__ import annotations

import json
from copy import deepcopy
from dataclasses import replace
from typing import cast

import pytest
from tests.action_movement_interruption_helpers import (
    MovementCase,
    action_movement_session,
    request_action_move,
)
from tests.phase17n_step6g_secondary_certification_helpers import (
    lifecycle_row,
    secondary_certification_session,
)

from warhammer40k_core.adapters.event_stream import EventStreamCursor
from warhammer40k_core.adapters.local_session import LocalGameSession
from warhammer40k_core.engine.actions import (
    MissionActionState,
    MissionActionStatePayload,
    MissionActionStatus,
)
from warhammer40k_core.engine.event_log import JsonValue
from warhammer40k_core.engine.lifecycle import GameLifecycle
from warhammer40k_core.engine.mission_action_eligibility import (
    mission_action_prevents_rules_unit_from_shooting_this_phase,
    rules_unit_started_mission_action_this_turn,
)
from warhammer40k_core.engine.mission_action_terminal_integrity import (
    validate_mission_action_terminal_event,
)
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError, LifecycleStatusKind
from warhammer40k_core.engine.primary_mission_action_interruptions import (
    reconcile_primary_mission_action_interruptions,
    validate_primary_mission_action_interruption_evidence,
)
from warhammer40k_core.engine.replay import ReplayArtifact, ReplayRunner, ReplayRunStatus
from warhammer40k_core.engine.triggered_movement import DECLINE_TRIGGERED_MOVEMENT_OPTION_ID


@pytest.mark.parametrize(
    ("case", "attached", "mission_action_id"),
    [
        ("translation", False, "maintain-control"),
        ("return", False, "maintain-control"),
        ("zero", False, "maintain-control"),
        ("rotation", False, "maintain-control"),
        ("rotation_return", False, "maintain-control"),
        ("return", True, "maintain-control"),
        ("return", False, "cleanse-objective"),
        ("return", True, "cleanse-objective"),
    ],
)
def test_completed_reactive_move_interrupts_action_through_facade(
    case: MovementCase,
    attached: bool,
    mission_action_id: str,
) -> None:
    session, unit_id = action_movement_session(
        attached=attached, mission_action_id=mission_action_id
    )
    request = request_action_move(session, unit_id, case)
    lifecycle = session.lifecycle
    state = lifecycle.state
    assert state is not None
    decisions = lifecycle.decision_controller
    initial = lifecycle.to_payload()
    cursor = EventStreamCursor(session.event_record_count())
    option = next(o for o in request.options if o.option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID)

    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order77-move"
    )

    assert status.status_kind is not LifecycleStatusKind.INVALID
    action = state.mission_action_states[-1]
    assert action.status is MissionActionStatus.INTERRUPTED
    assert action.interrupted_reason == "unit_moved"
    assert rules_unit_started_mission_action_this_turn(
        state=state, player_id=action.player_id, unit_instance_id=action.unit_instance_id
    ) == (
        state.active_player_id == action.player_id
        and state.battle_round == action.battle_round_started
    )
    completion = next(
        e for e in decisions.event_log.records if e.event_type == "triggered_movement_resolved"
    )
    assert isinstance(completion.payload, dict)
    batch = completion.payload["transition_batch"]
    assert isinstance(batch, dict)
    displacements = batch["displacements"]
    assert isinstance(displacements, list)
    assert len(displacements) == (5 if case in {"translation", "rotation"} else 0)
    history = [m for m in state.model_movement_history if m.event_id == completion.event_id]
    assert len(history) == (6 if attached else 5)
    assert {m.distance_inches for m in history} == (
        {0.25} if case in {"translation", "return"} else {0.0}
    )
    assert reconcile_primary_mission_action_interruptions(state=state, decisions=decisions) == ()
    assert not any(e.event_type == "mission_action_completed" for e in decisions.event_log.records)
    pending = lifecycle.pending_decision_request()
    assert pending is not None
    assert not any(o.option_id.startswith("next:primary-action:") for o in pending.options)
    for viewer in state.player_ids:
        delta = session.events_since(cursor, viewer_player_id=viewer)
        interruptions = [
            e for e in delta["events"] if e["event_type"] == "mission_action_interrupted"
        ]
        assert len(interruptions) == 1
        json.dumps(session.view(viewer_player_id=viewer), allow_nan=False)
        json.dumps(delta, allow_nan=False)
    restored = LocalGameSession.from_persistence_payload(
        json.loads(json.dumps(session.to_persistence_payload()))
    )
    assert restored.lifecycle.to_payload() == lifecycle.to_payload()
    artifact = ReplayArtifact.capture(
        artifact_id=f"order77-{case}", initial_lifecycle_payload=initial, final_lifecycle=lifecycle
    )
    assert (
        ReplayRunner.from_payload(artifact.to_payload()).run().status is ReplayRunStatus.REPRODUCED
    )


def test_declined_reactive_move_preserves_action_completion() -> None:
    session, unit_id = action_movement_session()
    request = request_action_move(session, unit_id, "return")
    status = session.submit_option(
        request_id=request.request_id,
        option_id=DECLINE_TRIGGERED_MOVEMENT_OPTION_ID,
        result_id="order77-decline",
    )
    assert status.status_kind is not LifecycleStatusKind.INVALID
    state = session.lifecycle.state
    assert state is not None
    assert state.mission_action_states[-1].status is MissionActionStatus.STARTED
    pending = session.lifecycle.pending_decision_request()
    assert pending is not None
    request = pending
    option = next(o for o in request.options if o.option_id.startswith("next:primary-action:"))
    session.submit_option(
        request_id=request.request_id,
        option_id=option.option_id,
        result_id="order77-complete-unmoved-action",
    )
    assert (
        state.mission_action_state_by_id("mission-action:order77-start-action").status
        is MissionActionStatus.COMPLETED
    )


@pytest.fixture(scope="module")
def interrupted_return_session() -> LocalGameSession:
    session, unit_id = action_movement_session(pause_after_move=True)
    request = request_action_move(session, unit_id, "return")
    option = next(o for o in request.options if o.option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID)
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="order77-evidence-move"
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    return session


def test_interruption_preserves_shooting_and_charge_locks(
    interrupted_return_session: LocalGameSession,
) -> None:
    restored = GameLifecycle.from_payload(interrupted_return_session.lifecycle.to_payload())
    state = restored.state
    assert state is not None
    action = state.mission_action_states[-1]
    assert action.status is MissionActionStatus.INTERRUPTED
    assert state.current_battle_phase is BattlePhase.SHOOTING
    assert mission_action_prevents_rules_unit_from_shooting_this_phase(
        state=state,
        player_id=action.player_id,
        unit_instance_id=action.unit_instance_id,
    )
    assert rules_unit_started_mission_action_this_turn(
        state=state,
        player_id=action.player_id,
        unit_instance_id=action.unit_instance_id,
    )


@pytest.mark.parametrize(
    ("event_type", "kind", "allowed"),
    [
        ("movement_activation_completed", "normal_move", False),
        ("movement_activation_completed", "advance", False),
        ("movement_activation_completed", "fall_back", False),
        ("movement_activation_completed", "remain_stationary", True),
        ("charge_move_completed", "charge_move", False),
        ("catalog_setup_reactive_charge_move_completed", "charge_move", False),
        ("triggered_movement_resolved", "surge_move", False),
        ("fight_movement_completed", "pile_in", True),
        ("fight_movement_completed", "consolidate", True),
    ],
)
def test_action_evidence_classifies_completed_move_not_net_displacement(
    interrupted_return_session: LocalGameSession,
    event_type: str,
    kind: str,
    allowed: bool,
) -> None:
    """Exercise the shared evidence parser with real validated return-path model rows."""
    lifecycle = interrupted_return_session.lifecycle
    state = lifecycle.state
    assert state is not None
    event = next(
        e
        for e in lifecycle.decision_controller.event_log.records
        if e.event_type == "triggered_movement_resolved"
    )
    payload = deepcopy(cast(dict[str, JsonValue], event.payload))
    payload["movement_phase_action"] = kind
    payload["displacement_kind"] = kind
    if event_type == "fight_movement_completed":
        payload["resolution"] = {"proposal_kind": kind}
    classified = replace(event, event_type=event_type, payload=payload)
    if allowed:
        with pytest.raises(GameLifecycleError, match="evidence reason drifted"):
            validate_primary_mission_action_interruption_evidence(
                state=state,
                action=state.mission_action_states[-1],
                evidence_event=classified,
            )
    else:
        validate_primary_mission_action_interruption_evidence(
            state=state,
            action=state.mission_action_states[-1],
            evidence_event=classified,
        )


@pytest.mark.parametrize("tamper", ["reference", "type", "reason", "missing", "suppressed"])
def test_restore_rejects_forged_completed_move_interruption(
    interrupted_return_session: LocalGameSession,
    tamper: str,
) -> None:
    payload = deepcopy(interrupted_return_session.lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    terminal = next(e for e in events if e["event_type"] == "mission_action_interrupted")
    terminal_payload = cast(dict[str, JsonValue], terminal["payload"])
    if tamper == "reference":
        terminal_payload["source_evidence_event_id"] = "event:missing"
    elif tamper == "type":
        terminal_payload["source_evidence_event_type"] = "movement_activation_completed"
    elif tamper == "reason":
        terminal_payload["interrupted_reason"] = "unit_left_battlefield"
    elif tamper == "missing":
        del terminal_payload["source_evidence_event_id"]
    else:
        terminal["event_type"] = "forged_unrelated_event"
        terminal["payload"] = {}
        action = payload["state"]["mission_action_states"][-1]
        action["status"] = "started"
        action["interrupted_reason"] = None
    with pytest.raises(
        GameLifecycleError, match=("continued after" if tamper == "suppressed" else None)
    ):
        GameLifecycle.from_payload(payload)


@pytest.fixture(scope="module")
def interrupted_secondary_return_session() -> LocalGameSession:
    session, unit_id = action_movement_session(mission_action_id="cleanse-objective")
    # Preserve event IDs when replacing this benign pre-move marker in forgery tests.
    session.lifecycle.decision_controller.event_log.append("r77_001_before_move", {})
    request = request_action_move(session, unit_id, "return")
    option = next(o for o in request.options if o.option_id != DECLINE_TRIGGERED_MOVEMENT_OPTION_ID)
    status = session.submit_option(
        request_id=request.request_id, option_id=option.option_id, result_id="r77-001-move"
    )
    assert status.status_kind is LifecycleStatusKind.WAITING_FOR_DECISION
    saved = session.lifecycle.to_payload()
    assert GameLifecycle.from_payload(saved).to_payload() == saved
    return session


@pytest.mark.parametrize(
    "terminal_type",
    ["mission_action_completion_failed", "mission_action_completed", "mission_action_interrupted"],
)
def test_secondary_terminal_cannot_hide_suppressed_move_interruption(
    interrupted_secondary_return_session: LocalGameSession,
    terminal_type: str,
) -> None:
    """R77-001: an unauthenticated terminal must never truncate the movement scan."""
    payload = deepcopy(interrupted_secondary_return_session.lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    terminal = next(e for e in events if e["event_type"] == "mission_action_interrupted")
    terminal["event_type"] = "forged_unrelated_event"
    terminal["payload"] = {}
    action = payload["state"]["mission_action_states"][-1]
    action["status"] = "started"
    action["interrupted_reason"] = None
    forged = next(e for e in events if e["event_type"] == "r77_001_before_move")
    forged["event_type"] = terminal_type
    forged["payload"] = {"mission_action_state": cast(JsonValue, deepcopy(action))}

    with pytest.raises(GameLifecycleError, match="Started Mission Action has a terminal event"):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("phase", "timing", "failed", "substitute_source", "diagnostic"),
    [
        ("shooting", "turn_end", False, "none", "completion timing"),
        ("fight", "turn_end", False, "none", "completion boundary"),
        ("shooting", "immediate", False, "none", "Mission Action start event state"),
        ("fight", "turn_end", True, "none", "completion boundary"),
        (
            "shooting",
            "immediate",
            False,
            "saved_and_start",
            "Activity restriction Action decision subject or timing",
        ),
        ("shooting", "immediate", False, "saved_only", "Mission Action start event state"),
    ],
)
def test_coordinated_secondary_completion_cannot_hide_move_interruption(
    interrupted_secondary_return_session: LocalGameSession,
    phase: str,
    timing: str,
    failed: bool,
    substitute_source: str,
    diagnostic: str,
) -> None:
    """R77-001: matching saved state and terminal fields do not prove completion."""
    original = interrupted_secondary_return_session.lifecycle.to_payload()
    payload = deepcopy(original)
    events = payload["decisions"]["event_log"]
    terminal = next(e for e in events if e["event_type"] == "mission_action_interrupted")
    terminal["event_type"] = "forged_unrelated_event"
    terminal["payload"] = {}
    action = payload["state"]["mission_action_states"][-1]
    action["status"] = "interrupted" if failed else "completed"
    action["interrupted_reason"] = "completion_condition_failed" if failed else None
    action["completed_battle_round"] = None if failed else action["battle_round_started"]
    action["completed_phase"] = None if failed else phase
    action["completion_timing"] = timing
    if substitute_source != "none":
        action["mission_action_id"] = "plunder-terrain"
        action["mission_id"] = "plunder"
        action["scoring_source_id"] = "plunder"
    if substitute_source == "saved_and_start":
        start = next(e for e in events if e["event_type"] == "mission_action_started")
        start_payload = cast(dict[str, JsonValue], start["payload"])
        start_payload["mission_action_id"] = action["mission_action_id"]
        started = cast(dict[str, JsonValue], start_payload["mission_action_state"])
        started["mission_action_id"] = action["mission_action_id"]
        started["mission_id"] = action["mission_id"]
        started["scoring_source_id"] = action["scoring_source_id"]
        started["completion_timing"] = timing
    forged = next(e for e in events if e["event_type"] == "r77_001_before_move")
    forged["event_type"] = (
        "mission_action_completion_failed" if failed else "mission_action_completed"
    )
    forged["payload"] = {
        "game_id": payload["state"]["game_id"],
        "player_id": action["player_id"],
        "battle_round": action["battle_round_started"],
        "phase": phase,
        "mission_action_id": action["mission_action_id"],
        "mission_action_state": cast(JsonValue, deepcopy(action)),
    }
    if substitute_source != "saved_and_start":
        assert next(e for e in events if e["event_type"] == "mission_action_started") == next(
            e
            for e in original["decisions"]["event_log"]
            if e["event_type"] == "mission_action_started"
        )
    assert [e for e in events if e["event_type"] == "triggered_movement_resolved"] == [
        e
        for e in original["decisions"]["event_log"]
        if e["event_type"] == "triggered_movement_resolved"
    ]
    assert payload["decisions"]["records"] == original["decisions"]["records"]
    assert payload["state"]["model_movement_history"] == original["state"]["model_movement_history"]
    with pytest.raises(GameLifecycleError, match=diagnostic):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize("started", [False, True])
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("mission_id", "forged-mission"),
        ("target_id", "forged-target"),
        ("condition_target_id", "forged-condition"),
        ("start_timing", "forged-window"),
        ("completion_timing", "immediate"),
        ("interruption_conditions", []),
        ("scoring_source_id", "forged-source"),
        ("victory_points", 10),
    ],
)
def test_secondary_history_binds_immutable_start_fields_before_status_policy(
    interrupted_secondary_return_session: LocalGameSession,
    started: bool,
    field: str,
    value: JsonValue,
) -> None:
    lifecycle = interrupted_secondary_return_session.lifecycle
    state = lifecycle.state
    assert state is not None
    action = state.mission_action_states[-1]
    if started:
        action = replace(action, status=MissionActionStatus.STARTED, interrupted_reason=None)
    forged_payload = cast(dict[str, JsonValue], action.to_payload())
    forged_payload[field] = value
    forged = MissionActionState.from_payload(cast(MissionActionStatePayload, forged_payload))
    events = lifecycle.decision_controller.event_log.records
    start = next(e for e in events if e.event_type == "mission_action_started")
    terminal = next(e for e in events if e.event_type == "mission_action_interrupted")
    terminal_payload = deepcopy(cast(dict[str, JsonValue], terminal.payload))
    terminal_payload["mission_action_state"] = cast(JsonValue, forged.to_payload())
    terminal = replace(terminal, payload=terminal_payload)
    with pytest.raises(GameLifecycleError, match="Mission Action start event state"):
        validate_mission_action_terminal_event(
            state=state,
            action=forged,
            start=start,
            terminals=() if started else (terminal,),
            event_index_by_id={e.event_id: i for i, e in enumerate(events)},
            event_records=events,
        )


@pytest.fixture(scope="module")
def completed_secondary_session() -> LocalGameSession:
    session, saved, _expectation = secondary_certification_session(
        lifecycle_row("cleanse", mode="tactical", scoring_player_id="player-a")
    )
    assert GameLifecycle.from_payload(saved).to_payload() == saved
    assert session.lifecycle.state is not None
    assert session.lifecycle.state.mission_action_states[-1].status is MissionActionStatus.COMPLETED
    return session


@pytest.mark.parametrize(
    ("tamper", "diagnostic"),
    [
        ("missing", "completion boundary lacks one"),
        ("unknown_record", "canonical boundary event does not identify exactly one stored record"),
        ("source", "canonical boundary event does not identify exactly one stored record"),
        ("phase", "canonical boundary event does not identify exactly one stored record"),
        ("after_terminal", "objective boundary event ordering"),
    ],
)
def test_secondary_completion_requires_authentic_ordered_boundary(
    completed_secondary_session: LocalGameSession, tamper: str, diagnostic: str
) -> None:
    payload = deepcopy(completed_secondary_session.lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    turn_record_ids = {
        row["record_id"]
        for row in payload["state"]["objective_control_records"]
        if row["timing"] == "turn_end"
    }
    boundary = next(
        event
        for event in events
        if event["event_type"] == "end_boundary_objective_control_determined"
        and isinstance(event["payload"], dict)
        and event["payload"].get("record_ids") == sorted(turn_record_ids)
    )
    boundary_payload = cast(dict[str, JsonValue], boundary["payload"])
    if tamper == "missing":
        boundary["event_type"] = "forged_unrelated_event"
    elif tamper == "unknown_record":
        boundary_payload["record_ids"] = ["record:unknown"]
    elif tamper == "source":
        boundary_payload["source_rule_id"] = "forged-source"
    elif tamper == "phase":
        boundary_payload["phase"] = "shooting"
    else:
        terminal = next(e for e in events if e["event_type"] == "mission_action_completed")
        boundary["event_type"], terminal["event_type"] = (
            terminal["event_type"],
            boundary["event_type"],
        )
        boundary["payload"], terminal["payload"] = terminal["payload"], boundary["payload"]
    with pytest.raises(GameLifecycleError, match=diagnostic):
        GameLifecycle.from_payload(payload)


@pytest.mark.parametrize(
    ("tamper", "diagnostic"),
    [
        ("failed_type", "terminal event authentication"),
        ("completed_type", "terminal event authentication"),
        ("state", "terminal event state"),
        ("game", "event battle context"),
        ("round", "event battle context"),
        ("phase", "interruption precedes its start phase"),
        ("player", "event player"),
        ("source", "terminal source identity"),
        ("missing", "terminal event authentication"),
        ("duplicate", "terminal event authentication"),
        ("before_start", "terminal event ordering"),
    ],
)
def test_secondary_terminal_authenticates_persisted_state_and_context(
    interrupted_secondary_return_session: LocalGameSession,
    tamper: str,
    diagnostic: str,
) -> None:
    payload = deepcopy(interrupted_secondary_return_session.lifecycle.to_payload())
    events = payload["decisions"]["event_log"]
    terminal = next(e for e in events if e["event_type"] == "mission_action_interrupted")
    terminal_payload = cast(dict[str, JsonValue], terminal["payload"])
    if tamper == "failed_type":
        terminal["event_type"] = "mission_action_completion_failed"
    elif tamper == "completed_type":
        terminal["event_type"] = "mission_action_completed"
    elif tamper == "state":
        nested = cast(dict[str, JsonValue], terminal_payload["mission_action_state"])
        nested["target_id"] = "forged-target"
    elif tamper == "game":
        terminal_payload["game_id"] = "forged-game"
    elif tamper == "round":
        terminal_payload["battle_round"] = 2
    elif tamper == "phase":
        terminal_payload["phase"] = "command"
    elif tamper == "player":
        terminal_payload["player_id"] = "player-a"
    elif tamper == "source":
        terminal_payload["mission_action_id"] = "forged-source"
    elif tamper == "missing":
        terminal["event_type"] = "forged_unrelated_event"
    else:
        replacement = next(
            e
            for e in events
            if e["event_type"]
            == (
                "primary_mission_boundary_checkpoint_recorded"
                if tamper == "before_start"
                else "r77_001_before_move"
            )
        )
        replacement["event_type"] = terminal["event_type"]
        replacement["payload"] = deepcopy(terminal_payload)
        if tamper == "before_start":
            terminal["event_type"] = "forged_unrelated_event"

    with pytest.raises(GameLifecycleError, match=diagnostic):
        GameLifecycle.from_payload(payload)
