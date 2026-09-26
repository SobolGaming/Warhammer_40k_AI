"""Physical dice authority shared by model and weapon characteristic evaluations."""

from __future__ import annotations

from warhammer40k_core.core.dice import (
    DiceRollSpec,
    RandomCharacteristicRoll,
    RandomCharacteristicTiming,
)
from warhammer40k_core.core.random_profile_values import RandomProfileValue
from warhammer40k_core.engine.event_log import EventRecord, JsonValue, canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_profile_roll(
    *,
    roll: RandomCharacteristicRoll,
    value: RandomProfileValue,
    scope_id: str,
    timing: RandomCharacteristicTiming,
    actor_id: str,
    reason: str,
    physical_rolls: dict[str, JsonValue],
    random_rolls: set[str],
) -> None:
    original = roll.roll_state.original_result
    expected_spec = DiceRollSpec(
        expression=value.expression,
        reason=reason,
        actor_id=actor_id,
        roll_type=f"random_characteristic.{value.characteristic.value}.{timing.value}.{scope_id}",
    )
    if (
        roll.characteristic is not value.characteristic
        or roll.scope_id != scope_id
        or roll.timing is not timing
        or original.spec != expected_spec
        or physical_rolls.get(original.roll_id) != original.to_payload()
        or canonical_json(roll.to_payload()) not in random_rolls
        or roll.roll_state.rerolls
        or roll.roll_state.result_override is not None
    ):
        raise GameLifecycleError("Random profile physical dice evidence drifted.")


def validate_profile_roll_inventory(events: tuple[EventRecord, ...]) -> None:
    """Every profile die must belong to a recorded engine evaluation, exactly once."""
    physical: set[str] = set()
    characteristic_rolls: set[str] = set()
    consumed: set[str] = set()
    for event in events:
        body = event.payload
        if not isinstance(body, dict):
            continue
        if event.event_type == "dice_rolled":
            spec = body.get("spec")
            if not isinstance(spec, dict):
                continue
            reason, roll_id = spec.get("reason"), body.get("roll_id")
            if type(reason) is str and reason.startswith(("Source profile ", "Weapon profile ")):
                if type(roll_id) is not str or roll_id in physical:
                    raise GameLifecycleError("Random profile physical roll identity is duplicated.")
                physical.add(roll_id)
        elif event.event_type == "random_characteristic_rolled":
            roll_id = _original_roll_id(body)
            if roll_id in physical:
                if roll_id in characteristic_rolls:
                    raise GameLifecycleError("Random profile characteristic roll is duplicated.")
                characteristic_rolls.add(roll_id)
        elif event.event_type in {
            "random_weapon_profile_evaluated",
            "random_weapon_range_evaluated",
            "random_profile_values_evaluated",
        }:
            entries = (
                body.get("entries")
                if event.event_type == "random_profile_values_evaluated"
                else [body]
            )
            if not isinstance(entries, list):
                raise GameLifecycleError("Random profile evaluation roll inventory is malformed.")
            for entry in entries:
                roll = entry.get("roll") if isinstance(entry, dict) else None
                if not isinstance(roll, dict):
                    raise GameLifecycleError("Random profile evaluation roll is missing.")
                roll_id = _original_roll_id(roll)
                if roll_id not in characteristic_rolls:
                    raise GameLifecycleError("Random profile evaluation precedes its dice.")
                consumed.add(roll_id)
    if physical != characteristic_rolls or physical != consumed:
        raise GameLifecycleError("Random profile dice contain an orphan evaluation roll.")


def _original_roll_id(body: dict[str, JsonValue]) -> str:
    state = body.get("roll_state")
    original = state.get("original_result") if isinstance(state, dict) else None
    roll_id = original.get("roll_id") if isinstance(original, dict) else None
    if type(roll_id) is not str:
        raise GameLifecycleError("Random characteristic roll identity is malformed.")
    return roll_id
