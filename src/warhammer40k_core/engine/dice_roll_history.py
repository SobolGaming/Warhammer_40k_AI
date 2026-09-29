"""Recover a dice result after a suspended engine reroll decision."""

from __future__ import annotations

from typing import cast

from warhammer40k_core.core.dice import (
    D3RollResult,
    D3RollResultPayload,
    DiceRollResult,
    DiceRollResultPayload,
    DiceRollState,
    DiceRollStatePayload,
)
from warhammer40k_core.engine.decision_controller import DecisionController
from warhammer40k_core.engine.dice import DiceRollManager
from warhammer40k_core.engine.phase import GameLifecycleError

DICE_RESULT_OVERRIDE_EVENT_TYPE = "dice_result_overridden"


def roll_or_reuse_d3(
    *,
    manager: DiceRollManager,
    reason: str,
    roll_type: str,
    actor_id: str,
) -> D3RollResult:
    """Resume one logical D3 using its paired physical and derived evidence."""
    spec = manager.d3_source_spec(reason=reason, roll_type=roll_type, actor_id=actor_id)
    sources: list[DiceRollResult] = []
    derived: list[D3RollResult] = []
    for event in manager.event_log.records:
        if event.event_type == "dice_rolled":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("D3 physical dice evidence must be an object.")
            source = DiceRollResult.from_payload(cast(DiceRollResultPayload, event.payload))
            if source.spec == spec:
                sources.append(source)
        elif event.event_type == "d3_roll_resolved":
            if not isinstance(event.payload, dict):
                raise GameLifecycleError("D3 derived evidence must be an object.")
            result = D3RollResult.from_payload(cast(D3RollResultPayload, event.payload))
            if result.source_d6_result.spec == spec:
                derived.append(result)
    if not sources and not derived:
        return manager.roll_d3(reason=reason, roll_type=roll_type, actor_id=actor_id)
    if len(sources) != 1 or len(derived) != 1 or derived[0].source_d6_result != sources[0]:
        raise GameLifecycleError("D3 resume requires exactly one matching physical/derived pair.")
    return derived[0]


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
