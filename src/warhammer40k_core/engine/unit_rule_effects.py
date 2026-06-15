from __future__ import annotations

from warhammer40k_core.engine.effects import PersistingEffect
from warhammer40k_core.engine.phase import GameLifecycleError


def movement_bonus_inches_from_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> int:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    total = 0
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Movement bonus effect payload must be an object.")
        raw_bonus = payload.get("movement_bonus_inches")
        if raw_bonus is None:
            continue
        if type(raw_bonus) is not int:
            raise GameLifecycleError("movement_bonus_inches effect value must be an int.")
        if raw_bonus < 0:
            raise GameLifecycleError("movement_bonus_inches effect value must not be negative.")
        total += raw_bonus
    return total


def fire_overwatch_forbidden_by_effects(
    effects: tuple[PersistingEffect, ...],
    *,
    owner_player_id: str,
) -> bool:
    requested_owner = _validate_identifier("owner_player_id", owner_player_id)
    for effect in _validated_effects(effects):
        if effect.owner_player_id != requested_owner:
            continue
        payload = effect.effect_payload
        if not isinstance(payload, dict):
            raise GameLifecycleError("Fire Overwatch effect payload must be an object.")
        raw_forbidden = payload.get("fire_overwatch_forbidden")
        if raw_forbidden is None:
            continue
        if type(raw_forbidden) is not bool:
            raise GameLifecycleError("fire_overwatch_forbidden effect value must be a bool.")
        if raw_forbidden:
            return True
    return False


def _validated_effects(effects: tuple[PersistingEffect, ...]) -> tuple[PersistingEffect, ...]:
    if type(effects) is not tuple:
        raise GameLifecycleError("Rule effect helpers require a tuple of effects.")
    for effect in effects:
        if type(effect) is not PersistingEffect:
            raise GameLifecycleError("Rule effect helpers require PersistingEffect values.")
    return effects


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Rule effect {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Rule effect {field_name} must not be empty.")
    return stripped
