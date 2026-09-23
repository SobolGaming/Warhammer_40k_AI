"""Shared terminal authentication before an Action history can be bounded."""

from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.engine.actions import (
    MISSION_ACTION_COMPLETION_CONDITION_FAILED_REASON,
    MissionActionState,
    MissionActionStatus,
)
from warhammer40k_core.engine.event_log import EventRecord, JsonValue
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
