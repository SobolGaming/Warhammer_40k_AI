"""Shared terminal authentication before an Action history can be bounded."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.actions import (
    MISSION_ACTION_COMPLETION_CONDITION_FAILED_REASON,
    MissionActionState,
    MissionActionStatus,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
from warhammer40k_core.engine.mission_action_options import mission_action_for_state
from warhammer40k_core.engine.objective_control import (
    ObjectiveControlRecord,
    ObjectiveControlTiming,
)
from warhammer40k_core.engine.phase import GameLifecycleError

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


MISSION_ACTION_TERMINAL_EVENT_TYPES = frozenset(
    {
        "mission_action_completed",
        "mission_action_completion_failed",
        "mission_action_interrupted",
    }
)


def validate_mission_action_terminal_event(
    *,
    state: GameState,
    action: MissionActionState,
    start: EventRecord,
    terminals: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
    event_records: tuple[EventRecord, ...],
) -> EventRecord | None:
    if action.status is MissionActionStatus.STARTED:
        if terminals:
            raise GameLifecycleError("Started Mission Action has a terminal event.")
        return None
    if action.status is MissionActionStatus.COMPLETED:
        expected_type = "mission_action_completed"
        terminal_round = action.completed_battle_round
        terminal_phase = action.completed_phase
    elif action.interrupted_reason == MISSION_ACTION_COMPLETION_CONDITION_FAILED_REASON:
        expected_type = "mission_action_completion_failed"
        terminal_round = action.battle_round_started
        terminal_phase = state.battle_phase_sequence[-1].value
    else:
        expected_type = "mission_action_interrupted"
        terminal_round = action.battle_round_started
        terminal_phase = None
    if len(terminals) != 1 or terminals[0].event_type != expected_type:
        raise GameLifecycleError("Mission Action terminal event authentication drifted.")
    terminal = terminals[0]
    if event_index_by_id[start.event_id] >= event_index_by_id[terminal.event_id]:
        raise GameLifecycleError("Mission Action terminal event ordering drifted.")
    payload = _event_payload(terminal)
    if payload.get("mission_action_state") != action.to_payload():
        raise GameLifecycleError("Mission Action terminal event state drifted.")
    if terminal_round is None:
        raise GameLifecycleError("Mission Action terminal battle round is missing.")
    event_phase = payload.get("phase") if terminal_phase is None else terminal_phase
    phase_order = {phase.value: index for index, phase in enumerate(state.battle_phase_sequence)}
    if (
        type(event_phase) is not str
        or event_phase not in phase_order
        or action.phase_started not in phase_order
    ):
        raise GameLifecycleError("Mission Action terminal phase is invalid.")
    if expected_type == "mission_action_interrupted" and (
        phase_order[event_phase] < phase_order[action.phase_started]
    ):
        raise GameLifecycleError("Mission Action interruption precedes its start phase.")
    validate_mission_action_event_context(
        state=state, action=action, event=terminal, battle_round=terminal_round, phase=event_phase
    )
    mission_action_id = payload.get("mission_action_id")
    if (expected_type != "mission_action_interrupted" or mission_action_id is not None) and (
        mission_action_id != action.mission_action_id
    ):
        raise GameLifecycleError("Mission Action terminal source identity drifted.")
    if expected_type != "mission_action_interrupted":
        _validate_completion_timing_and_boundary(
            state=state,
            action=action,
            start=start,
            terminal=terminal,
            terminal_round=terminal_round,
            terminal_phase=event_phase,
            event_records=event_records,
            event_index_by_id=event_index_by_id,
        )
    return terminal


def validate_mission_action_event_context(
    *,
    state: GameState,
    action: MissionActionState,
    event: EventRecord,
    battle_round: int,
    phase: str,
) -> None:
    payload = _event_payload(event)
    if (
        payload.get("game_id") != state.game_id
        or payload.get("battle_round") != battle_round
        or payload.get("phase") != phase
    ):
        raise GameLifecycleError("Mission Action event battle context drifted.")
    player_id = payload.get("player_id")
    if player_id is not None and player_id != action.player_id:
        raise GameLifecycleError("Mission Action event player drifted.")
    action_id = payload.get("action_id")
    if action_id is not None and action_id != action.action_id:
        raise GameLifecycleError("Mission Action event action identity drifted.")


def _event_payload(event: EventRecord) -> dict[str, JsonValue]:
    if type(event.payload) is not dict:
        raise GameLifecycleError("Mission Action event payload must be an object.")
    return event.payload


def _validate_completion_timing_and_boundary(
    *,
    state: GameState,
    action: MissionActionState,
    start: EventRecord,
    terminal: EventRecord,
    terminal_round: int,
    terminal_phase: str,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    source = mission_action_for_state(state=state, mission_action_id=action.mission_action_id)
    if action.completion_timing != source.completion_timing:
        raise GameLifecycleError("Mission Action source completion timing drifted.")
    if terminal_round != action.battle_round_started:
        raise GameLifecycleError("Mission Action completion timing battle round drifted.")
    if source.completion_timing == "immediate":
        if (
            terminal.event_type != "mission_action_completed"
            or terminal_phase != action.phase_started
        ):
            raise GameLifecycleError("Immediate Mission Action completion timing drifted.")
        return
    if source.completion_timing != "turn_end":
        raise GameLifecycleError("Mission Action source completion timing is unsupported.")
    if terminal_phase != state.battle_phase_sequence[-1].value:
        raise GameLifecycleError("Turn-end Mission Action completion timing phase drifted.")
    records = tuple(
        record
        for record in state.objective_control_records
        if record.timing is ObjectiveControlTiming.TURN_END
        and record.game_id == state.game_id
        and record.active_player_id == action.player_id
        and record.battle_round == terminal_round
        and record.phase == terminal_phase
    )
    if len(records) != 1:
        raise GameLifecycleError("Mission Action completion boundary requires one turn-end record.")
    _validate_completion_boundary_event(
        record=records[0],
        start_event=start,
        terminal_event=terminal,
        event_records=event_records,
        event_index_by_id=event_index_by_id,
    )


def _validate_completion_boundary_event(
    *,
    record: ObjectiveControlRecord,
    start_event: EventRecord,
    terminal_event: EventRecord,
    event_records: tuple[EventRecord, ...],
    event_index_by_id: dict[str, int],
) -> None:
    matches = tuple(
        event
        for event in event_records
        if event.event_type == "end_boundary_objective_control_determined"
        and isinstance(event.payload, dict)
        and event.payload.get("record_ids") == [record.record_id]
    )
    if len(matches) != 1:
        raise GameLifecycleError(
            "Mission Action completion boundary lacks one objective boundary event."
        )
    boundary = matches[0]
    payload = _event_payload(boundary)
    expected_payload: dict[str, JsonValue] = {
        "game_id": record.game_id,
        "battle_round": record.battle_round,
        "phase": record.phase,
        "record_ids": [record.record_id],
        "source_rule_id": (
            "gw-11e-rules-and-event-updates-2026-07-22:app-core-rules:14.02.01-control-first"
        ),
    }
    if payload != expected_payload or not (
        event_index_by_id[start_event.event_id]
        < event_index_by_id[boundary.event_id]
        < event_index_by_id[terminal_event.event_id]
    ):
        raise GameLifecycleError("Mission Action objective boundary event ordering drifted.")
