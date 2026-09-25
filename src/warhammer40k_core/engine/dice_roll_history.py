"""Recover a dice result after a suspended engine reroll decision."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import (
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import GameLifecycleError

DICE_RESULT_OVERRIDE_EVENT_TYPE = "dice_result_overridden"


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


def latest_roll_state(*, decisions: DecisionController, roll_id: str) -> DiceRollState:
    current: DiceRollState | None = None
    for event in decisions.event_log.records:
        if event.event_type == "dice_rolled":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("dice_rolled event payload must be an object.")
            result = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
            if result.roll_id == roll_id:
                current = DiceRollState.from_result(result)
            continue
        if event.event_type == "dice_reroll_resolved":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("dice_reroll_resolved payload must be an object.")
            updated = DiceRollState.from_payload(cast(DiceRollStatePayload, event.payload))
        elif event.event_type in {"command_reroll_resolved", DICE_RESULT_OVERRIDE_EVENT_TYPE}:
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("Dice roll update event payload must be an object.")
            updated_payload = event.payload.get("updated_roll_state")
            if not isinstance(updated_payload, dict):
                raise GameLifecycleError("Dice roll update event missing updated_roll_state.")
            updated = DiceRollState.from_payload(cast(DiceRollStatePayload, updated_payload))
        else:
            continue
        if updated.original_result.roll_id == roll_id:
            current = updated
    if current is None:
        raise GameLifecycleError("Dice result override roll_id has no event-backed state.")
    return current
