from __future__ import annotations

from typing import cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.battle_shock import BattleShockTestRequest
from warhammer40k_core.engine.phase import GameLifecycleError


def validate_optional_test_request(
    value: object | None,
    *,
    battle_round: int,
    active_player_id: str,
) -> BattleShockTestRequest | None:
    if value is None:
        return None
    if type(value) is not BattleShockTestRequest:
        raise GameLifecycleError(
            "CommandStepState in-flight test must be a BattleShockTestRequest."
        )
    if value.battle_round != battle_round:
        raise GameLifecycleError("CommandStepState in-flight test battle round drift.")
    if value.player_id != active_player_id:
        raise GameLifecycleError("CommandStepState in-flight test active player drift.")
    return value


validate_identifier = IdentifierValidator(GameLifecycleError)


def validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"{field_name} must not contain duplicates.")
        identifiers.append(identifier)
        seen.add(identifier)
    return tuple(identifiers)


def validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return validate_identifier(field_name, value)


def validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value


def validate_non_zero_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value == 0:
        raise GameLifecycleError(f"{field_name} must not be zero.")
    return value


def validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 0:
        raise GameLifecycleError(f"{field_name} must not be negative.")
    return value


def validate_bool(field_name: str, value: object) -> bool:
    if type(value) is not bool:
        raise GameLifecycleError(f"{field_name} must be a bool.")
    return value
