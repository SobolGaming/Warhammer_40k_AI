from __future__ import annotations

from typing import TYPE_CHECKING

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.actions import (
    MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
    MissionActionStatus,
)
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
) -> None:
    requested_attached_unit_id = _validate_identifier(
        "attached_unit_instance_id",
        attached_unit_instance_id,
    )
    for action_state in tuple(state.mission_action_states):
        if action_state.unit_instance_id != requested_attached_unit_id:
            continue
        if action_state.status is not MissionActionStatus.STARTED:
            continue
        if (
            MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON
            not in action_state.interruption_conditions
        ):
            continue
        state.replace_mission_action_state(
            action_state.interrupt(
                reason=MISSION_ACTION_UNIT_DESTROYED_INTERRUPTION_REASON,
            )
        )


_validate_identifier = IdentifierValidator(GameLifecycleError)
