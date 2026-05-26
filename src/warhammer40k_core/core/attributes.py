from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict


class CharacteristicError(ValueError):
    """Raised when characteristic domain data is invalid."""


class Characteristic(StrEnum):
    MOVEMENT = "movement"
    TOUGHNESS = "toughness"
    SAVE = "save"
    INVULNERABLE_SAVE = "invulnerable_save"
    WOUNDS = "wounds"
    LEADERSHIP = "leadership"
    OBJECTIVE_CONTROL = "objective_control"
    WEAPON_SKILL = "weapon_skill"
    BALLISTIC_SKILL = "ballistic_skill"
    STRENGTH = "strength"
    ATTACKS = "attacks"
    ARMOR_PENETRATION = "armor_penetration"
    DAMAGE = "damage"
    RANGE = "range"


class CharacteristicValuePayload(TypedDict):
    characteristic: str
    raw: int
    base: int
    final: int
    applied_modifier_ids: list[str]


_NON_NEGATIVE_CHARACTERISTICS = frozenset(
    characteristic
    for characteristic in Characteristic
    if characteristic is not Characteristic.ARMOR_PENETRATION
)


@dataclass(frozen=True, slots=True)
class CharacteristicValue:
    characteristic: Characteristic
    raw: int
    base: int
    final: int
    applied_modifier_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        characteristic = _ensure_characteristic(self.characteristic)
        _validate_characteristic_number(characteristic, "raw", self.raw)
        _validate_characteristic_number(characteristic, "base", self.base)
        _validate_characteristic_number(characteristic, "final", self.final)

        ids = _validate_identifier_tuple(
            "CharacteristicValue applied_modifier_ids",
            self.applied_modifier_ids,
        )
        if ids != self.applied_modifier_ids:
            object.__setattr__(self, "applied_modifier_ids", ids)

    @classmethod
    def from_raw(cls, characteristic: Characteristic, raw: int) -> Self:
        return cls(
            characteristic=characteristic,
            raw=raw,
            base=raw,
            final=raw,
        )

    def to_payload(self) -> CharacteristicValuePayload:
        return {
            "characteristic": self.characteristic.value,
            "raw": self.raw,
            "base": self.base,
            "final": self.final,
            "applied_modifier_ids": list(self.applied_modifier_ids),
        }

    @classmethod
    def from_payload(cls, payload: CharacteristicValuePayload) -> Self:
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            raw=payload["raw"],
            base=payload["base"],
            final=payload["final"],
            applied_modifier_ids=tuple(payload["applied_modifier_ids"]),
        )


def characteristic_from_token(token: object) -> Characteristic:
    if type(token) is not str:
        raise CharacteristicError("Characteristic token must be a string.")
    try:
        return Characteristic(token)
    except ValueError as exc:
        raise CharacteristicError(f"Unsupported characteristic token: {token}.") from exc


def validate_characteristic_value(
    characteristic: object,
    field_name: str,
    value: object,
) -> int:
    return _validate_characteristic_number(
        _ensure_characteristic(characteristic),
        field_name,
        value,
    )


def validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise CharacteristicError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise CharacteristicError(f"{field_name} must not be empty.")
    return stripped


def validate_optional_identifier(field_name: str, value: object | None) -> str | None:
    if value is None:
        return None
    return validate_identifier(field_name, value)


def _ensure_characteristic(value: object) -> Characteristic:
    if type(value) is not Characteristic:
        raise CharacteristicError("Expected a Characteristic.")
    return value


def _validate_characteristic_number(
    characteristic: Characteristic,
    field_name: str,
    value: object,
) -> int:
    if type(value) is not int:
        raise CharacteristicError(f"Characteristic {field_name} value must be an integer.")
    if characteristic in _NON_NEGATIVE_CHARACTERISTICS and value < 0:
        raise CharacteristicError(
            f"Characteristic {field_name} value must not be negative for {characteristic.value}."
        )
    return value


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        identifier = validate_identifier(field_name, value)
        if identifier in seen:
            raise CharacteristicError(f"{field_name} must not contain duplicate IDs.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)
