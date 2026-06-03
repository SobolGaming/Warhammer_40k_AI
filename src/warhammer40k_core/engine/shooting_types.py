from __future__ import annotations

from enum import StrEnum
from typing import cast

from warhammer40k_core.engine.phase import GameLifecycleError


class ShootingType(StrEnum):
    NORMAL = "normal"
    ASSAULT = "assault"
    CLOSE_QUARTERS = "close_quarters"
    INDIRECT = "indirect"
    SNAP = "snap"


def shooting_type_from_token(token: object) -> ShootingType:
    if type(token) is ShootingType:
        return token
    if type(token) is not str:
        raise GameLifecycleError("ShootingType token must be a string.")
    try:
        return ShootingType(token)
    except ValueError as exc:
        raise GameLifecycleError(f"Unsupported shooting type token: {token}.") from exc


def validate_shooting_type_tuple(
    field_name: str,
    values: object,
) -> tuple[ShootingType, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    values_tuple = cast(tuple[object, ...], values)
    shooting_types = tuple(shooting_type_from_token(value) for value in values_tuple)
    if len(set(shooting_types)) != len(shooting_types):
        raise GameLifecycleError(f"{field_name} must not contain duplicates.")
    return tuple(sorted(shooting_types, key=lambda shooting_type: shooting_type.value))
