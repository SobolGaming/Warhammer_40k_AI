from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.actions import (
    MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
    MissionActionState,
    MissionActionStatus,
)
from warhammer40k_core.engine.event_log import EventLog
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.rules_units import rules_unit_is_battle_shocked

if TYPE_CHECKING:
    from warhammer40k_core.engine.game_state import GameState


def is_battle_shocked(state: GameState, unit_instance_id: str) -> bool:
    return rules_unit_is_battle_shocked(
        state=state,
        unit_instance_id=unit_instance_id,
    )


def interrupt_for_attached_unit_split(
    state: GameState,
    attached_unit_instance_id: str,
) -> tuple[MissionActionState, ...]:
    requested_attached_unit_id = _validate_identifier(
        "attached_unit_instance_id",
        attached_unit_instance_id,
    )
    interrupted_states: list[MissionActionState] = []
    for action_state in _attached_split_interruption_candidates(
        state,
        requested_attached_unit_id,
    ):
        interrupted = action_state.interrupt(
            reason=MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
        )
        state.replace_mission_action_state(interrupted)
        interrupted_states.append(interrupted)
    return tuple(sorted(interrupted_states, key=lambda action_state: action_state.action_id))


def interrupt_and_emit_attached_unit_split(
    state: GameState,
    event_log: EventLog,
    attached_unit_instance_id: str,
    surviving_unit_instance_ids: tuple[str, ...],
) -> tuple[MissionActionState, ...]:
    if type(event_log) is not EventLog:
        raise GameLifecycleError("Attached-unit split Action interruption requires an EventLog.")
    requested_attached_unit_id = _validate_identifier(
        "attached_unit_instance_id",
        attached_unit_instance_id,
    )
    if type(surviving_unit_instance_ids) is not tuple or not surviving_unit_instance_ids:
        raise GameLifecycleError(
            "Attached-unit split Action interruption requires surviving unit IDs."
        )
    surviving_ids = tuple(
        _validate_identifier("surviving_unit_instance_id", unit_id)
        for unit_id in surviving_unit_instance_ids
    )
    if len(set(surviving_ids)) != len(surviving_ids):
        raise GameLifecycleError(
            "Attached-unit split Action interruption survivor IDs must be unique."
        )
    if surviving_ids != tuple(sorted(surviving_ids)):
        raise GameLifecycleError(
            "Attached-unit split Action interruption survivor IDs must be sorted."
        )
    if not _attached_split_interruption_candidates(state, requested_attached_unit_id):
        return ()
    current_phase = state.current_battle_phase
    if current_phase is None or state.active_player_id is None:
        raise GameLifecycleError(
            "Attached-unit split Action interruption requires an active battle phase."
        )
    interrupted_states = interrupt_for_attached_unit_split(
        state,
        requested_attached_unit_id,
    )
    for action_state in interrupted_states:
        event_log.append(
            "mission_action_interrupted",
            {
                "game_id": state.game_id,
                "battle_round": state.battle_round,
                "active_player_id": state.active_player_id,
                "player_id": action_state.player_id,
                "phase": current_phase.value,
                "action_id": action_state.action_id,
                "unit_instance_id": requested_attached_unit_id,
                "surviving_unit_instance_ids": list(surviving_ids),
                "mission_action_state": action_state.to_payload(),
                "interrupted_reason": action_state.interrupted_reason,
            },
        )
    return interrupted_states


def _attached_split_interruption_candidates(
    state: GameState,
    attached_unit_instance_id: str,
) -> tuple[MissionActionState, ...]:
    return tuple(
        sorted(
            (
                action_state
                for action_state in state.mission_action_states
                if action_state.unit_instance_id == attached_unit_instance_id
                and action_state.status is MissionActionStatus.STARTED
                and MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
                in action_state.interruption_conditions
            ),
            key=lambda action_state: action_state.action_id,
        )
    )


_validate_identifier = IdentifierValidator(GameLifecycleError)
