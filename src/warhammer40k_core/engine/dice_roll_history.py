"""Recover a dice result after a suspended engine reroll decision."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import DiceRollState, DiceRollStatePayload
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.dice_result_overrides import DICE_RESULT_OVERRIDE_EVENT_TYPE
from warhammer40k_core.engine.phase import GameLifecycleError


def latest_reroll_state_for_original_roll(
    *,
    manager: DiceRollManager,
    original_state: DiceRollState,
) -> DiceRollState:
    current = original_state
    roll_id = original_state.original_result.roll_id
    for event in manager.event_log.records:
        if event.event_type not in {
            "dice_reroll_resolved",
            "command_reroll_resolved",
            DICE_RESULT_OVERRIDE_EVENT_TYPE,
        }:
            continue
        if not isinstance(event.payload, dict):
            raise GameLifecycleError("Reroll event payload must be an object.")
        if event.event_type in {"command_reroll_resolved", DICE_RESULT_OVERRIDE_EVENT_TYPE}:
            updated_payload = event.payload.get("updated_roll_state")
            if not isinstance(updated_payload, dict):
                raise GameLifecycleError("Command Re-roll event missing updated roll state.")
            updated_state = DiceRollState.from_payload(cast(DiceRollStatePayload, updated_payload))
        else:
            updated_state = DiceRollState.from_payload(cast(DiceRollStatePayload, event.payload))
        if updated_state.original_result.roll_id == roll_id:
            current = updated_state
    return current
