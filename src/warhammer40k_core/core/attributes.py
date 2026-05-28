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


class CharacteristicBoundPolicyPayload(TypedDict):
    characteristic: str
    minimum: int | None
    maximum: int | None
    damage_zero_permitted: bool


class BoundedCharacteristicValuePayload(TypedDict):
    characteristic: str
    raw: int
    base: int
    unbounded_final: int
    final: int
    applied_modifier_ids: list[str]
    bound_policy: CharacteristicBoundPolicyPayload


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


@dataclass(frozen=True, slots=True)
class CharacteristicBoundPolicy:
    characteristic: Characteristic
    minimum: int | None
    maximum: int | None
    damage_zero_permitted: bool = False

    def __post_init__(self) -> None:
        characteristic = _ensure_characteristic(self.characteristic)
        object.__setattr__(self, "characteristic", characteristic)
        object.__setattr__(
            self,
            "minimum",
            _validate_optional_bound(characteristic, "minimum", self.minimum),
        )
        object.__setattr__(
            self,
            "maximum",
            _validate_optional_bound(characteristic, "maximum", self.maximum),
        )
        if type(self.damage_zero_permitted) is not bool:
            raise CharacteristicError(
                "CharacteristicBoundPolicy damage_zero_permitted must be bool."
            )
        if self.damage_zero_permitted and characteristic is not Characteristic.DAMAGE:
            raise CharacteristicError("Only Damage bound policies can permit Damage 0.")
        minimum = self.minimum
        maximum = self.maximum
        if minimum is not None and maximum is not None and minimum > maximum:
            raise CharacteristicError("CharacteristicBoundPolicy minimum cannot exceed maximum.")

    @classmethod
    def for_characteristic(
        cls,
        characteristic: Characteristic,
        *,
        damage_zero_permitted: bool = False,
    ) -> Self:
        valid_characteristic = _ensure_characteristic(characteristic)
        minimum = _DEFAULT_MINIMUMS.get(valid_characteristic)
        maximum = _DEFAULT_MAXIMUMS.get(valid_characteristic)
        if valid_characteristic is Characteristic.DAMAGE and damage_zero_permitted:
            minimum = 0
        return cls(
            characteristic=valid_characteristic,
            minimum=minimum,
            maximum=maximum,
            damage_zero_permitted=damage_zero_permitted,
        )

    def apply(self, value: int) -> int:
        if type(value) is not int:
            raise CharacteristicError("CharacteristicBoundPolicy value must be an integer.")
        bounded = value
        if self.minimum is not None:
            bounded = max(bounded, self.minimum)
        if self.maximum is not None:
            bounded = min(bounded, self.maximum)
        return bounded

    def to_payload(self) -> CharacteristicBoundPolicyPayload:
        return {
            "characteristic": self.characteristic.value,
            "minimum": self.minimum,
            "maximum": self.maximum,
            "damage_zero_permitted": self.damage_zero_permitted,
        }

    @classmethod
    def from_payload(cls, payload: CharacteristicBoundPolicyPayload) -> Self:
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            minimum=payload["minimum"],
            maximum=payload["maximum"],
            damage_zero_permitted=payload["damage_zero_permitted"],
        )


@dataclass(frozen=True, slots=True)
class BoundedCharacteristicValue:
    characteristic: Characteristic
    raw: int
    base: int
    unbounded_final: int
    final: int
    applied_modifier_ids: tuple[str, ...]
    bound_policy: CharacteristicBoundPolicy

    def __post_init__(self) -> None:
        characteristic = _ensure_characteristic(self.characteristic)
        object.__setattr__(self, "characteristic", characteristic)
        _validate_characteristic_number(characteristic, "raw", self.raw)
        _validate_characteristic_number(characteristic, "base", self.base)
        if type(self.unbounded_final) is not int:
            raise CharacteristicError("BoundedCharacteristicValue unbounded_final must be int.")
        _validate_characteristic_number(characteristic, "final", self.final)
        ids = _validate_identifier_tuple(
            "BoundedCharacteristicValue applied_modifier_ids",
            self.applied_modifier_ids,
        )
        if ids != self.applied_modifier_ids:
            object.__setattr__(self, "applied_modifier_ids", ids)
        if type(self.bound_policy) is not CharacteristicBoundPolicy:
            raise CharacteristicError(
                "BoundedCharacteristicValue bound_policy must be a CharacteristicBoundPolicy."
            )
        if self.bound_policy.characteristic is not characteristic:
            raise CharacteristicError(
                "BoundedCharacteristicValue bound_policy must match characteristic."
            )
        if self.bound_policy.apply(self.unbounded_final) != self.final:
            raise CharacteristicError(
                "BoundedCharacteristicValue final must match bound policy application."
            )

    @classmethod
    def from_values(
        cls,
        *,
        characteristic: Characteristic,
        raw: int,
        base: int,
        unbounded_final: int,
        applied_modifier_ids: tuple[str, ...] = (),
        bound_policy: CharacteristicBoundPolicy | None = None,
    ) -> Self:
        valid_characteristic = _ensure_characteristic(characteristic)
        policy = (
            CharacteristicBoundPolicy.for_characteristic(valid_characteristic)
            if bound_policy is None
            else bound_policy
        )
        return cls(
            characteristic=valid_characteristic,
            raw=raw,
            base=base,
            unbounded_final=unbounded_final,
            final=policy.apply(unbounded_final),
            applied_modifier_ids=applied_modifier_ids,
            bound_policy=policy,
        )

    def to_characteristic_value(self) -> CharacteristicValue:
        return CharacteristicValue(
            characteristic=self.characteristic,
            raw=self.raw,
            base=self.base,
            final=self.final,
            applied_modifier_ids=self.applied_modifier_ids,
        )

    def to_payload(self) -> BoundedCharacteristicValuePayload:
        return {
            "characteristic": self.characteristic.value,
            "raw": self.raw,
            "base": self.base,
            "unbounded_final": self.unbounded_final,
            "final": self.final,
            "applied_modifier_ids": list(self.applied_modifier_ids),
            "bound_policy": self.bound_policy.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: BoundedCharacteristicValuePayload) -> Self:
        return cls(
            characteristic=characteristic_from_token(payload["characteristic"]),
            raw=payload["raw"],
            base=payload["base"],
            unbounded_final=payload["unbounded_final"],
            final=payload["final"],
            applied_modifier_ids=tuple(payload["applied_modifier_ids"]),
            bound_policy=CharacteristicBoundPolicy.from_payload(payload["bound_policy"]),
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


def _validate_optional_bound(
    characteristic: Characteristic,
    field_name: str,
    value: object | None,
) -> int | None:
    if value is None:
        return None
    return _validate_characteristic_number(characteristic, field_name, value)


_DEFAULT_MINIMUMS = {
    Characteristic.MOVEMENT: 1,
    Characteristic.TOUGHNESS: 1,
    Characteristic.SAVE: 2,
    Characteristic.INVULNERABLE_SAVE: 2,
    Characteristic.LEADERSHIP: 4,
    Characteristic.OBJECTIVE_CONTROL: 0,
    Characteristic.WEAPON_SKILL: 2,
    Characteristic.BALLISTIC_SKILL: 2,
    Characteristic.STRENGTH: 1,
    Characteristic.ATTACKS: 1,
    Characteristic.DAMAGE: 1,
    Characteristic.RANGE: 1,
}

_DEFAULT_MAXIMUMS = {
    Characteristic.LEADERSHIP: 9,
    Characteristic.ARMOR_PENETRATION: 0,
}
