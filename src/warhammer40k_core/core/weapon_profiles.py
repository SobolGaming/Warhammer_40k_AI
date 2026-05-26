from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
    CharacteristicValuePayload,
)
from warhammer40k_core.core.dice import DiceExpression, DiceExpressionPayload, DiceRollSpecError


class WeaponProfileError(ValueError):
    """Raised when weapon profile data violates CORE V2 invariants."""


class WeaponKeyword(StrEnum):
    DEVASTATING_WOUNDS = "Devastating Wounds"
    FEEL_NO_PAIN = "Feel No Pain"
    SUSTAINED_HITS = "Sustained Hits"
    LETHAL_HITS = "Lethal Hits"
    TWIN_LINKED = "Twin-linked"
    IGNORES_COVER = "Ignores Cover"
    INDIRECT_FIRE = "Indirect Fire"
    EXTRA_ATTACKS = "Extra Attacks"
    RAPID_FIRE = "Rapid Fire"
    PRECISION = "Precision"
    HAZARDOUS = "Hazardous"
    ASSAULT = "Assault"
    TORRENT = "Torrent"
    PSYCHIC = "Psychic"
    PISTOL = "Pistol"
    HEAVY = "Heavy"
    BLAST = "Blast"
    MELTA = "Melta"


class RangeProfileKind(StrEnum):
    DISTANCE = "distance"
    MELEE = "melee"


class RangeProfilePayload(TypedDict):
    kind: str
    distance_inches: int | None


class AttackProfilePayload(TypedDict):
    fixed_attacks: int | None
    dice_expression: DiceExpressionPayload | None


class DamageProfilePayload(TypedDict):
    fixed_damage: int | None
    dice_expression: DiceExpressionPayload | None


class WeaponProfilePayload(TypedDict):
    profile_id: str
    name: str
    range_profile: RangeProfilePayload
    attack_profile: AttackProfilePayload
    skill: CharacteristicValuePayload
    strength: CharacteristicValuePayload
    armor_penetration: CharacteristicValuePayload
    damage_profile: DamageProfilePayload
    keywords: list[str]


@dataclass(frozen=True, slots=True)
class RangeProfile:
    kind: RangeProfileKind
    distance_inches: int | None = None

    def __post_init__(self) -> None:
        kind = _validate_range_kind(self.kind)
        if kind != self.kind:
            object.__setattr__(self, "kind", kind)

        if kind is RangeProfileKind.DISTANCE:
            if type(self.distance_inches) is not int:
                raise WeaponProfileError("RangeProfile distance_inches must be an integer.")
            if self.distance_inches < 0:
                raise WeaponProfileError("RangeProfile distance_inches must not be negative.")
            return

        if self.distance_inches is not None:
            raise WeaponProfileError("Melee RangeProfile must not include distance_inches.")

    @classmethod
    def distance(cls, distance_inches: int) -> Self:
        return cls(kind=RangeProfileKind.DISTANCE, distance_inches=distance_inches)

    @classmethod
    def melee(cls) -> Self:
        return cls(kind=RangeProfileKind.MELEE)

    def to_payload(self) -> RangeProfilePayload:
        return {
            "kind": self.kind.value,
            "distance_inches": self.distance_inches,
        }

    @classmethod
    def from_payload(cls, payload: RangeProfilePayload) -> Self:
        return cls(
            kind=range_profile_kind_from_token(payload["kind"]),
            distance_inches=payload["distance_inches"],
        )


@dataclass(frozen=True, slots=True)
class AttackProfile:
    fixed_attacks: int | None = None
    dice_expression: DiceExpression | None = None

    def __post_init__(self) -> None:
        _validate_exactly_one_expression(
            "AttackProfile",
            self.fixed_attacks,
            self.dice_expression,
        )
        if self.fixed_attacks is not None:
            _validate_positive_int("AttackProfile fixed_attacks", self.fixed_attacks)
        if self.dice_expression is not None:
            _validate_dice_expression("AttackProfile dice_expression", self.dice_expression)

    @classmethod
    def fixed(cls, attacks: int) -> Self:
        return cls(fixed_attacks=attacks)

    @classmethod
    def dice(cls, expression: DiceExpression) -> Self:
        return cls(dice_expression=expression)

    def to_payload(self) -> AttackProfilePayload:
        dice_payload = None
        if self.dice_expression is not None:
            dice_payload = self.dice_expression.to_payload()
        return {
            "fixed_attacks": self.fixed_attacks,
            "dice_expression": dice_payload,
        }

    @classmethod
    def from_payload(cls, payload: AttackProfilePayload) -> Self:
        dice_payload = payload["dice_expression"]
        try:
            return cls(
                fixed_attacks=payload["fixed_attacks"],
                dice_expression=(
                    None if dice_payload is None else DiceExpression.from_payload(dice_payload)
                ),
            )
        except DiceRollSpecError as exc:
            raise WeaponProfileError("AttackProfile dice_expression payload is invalid.") from exc


@dataclass(frozen=True, slots=True)
class DamageProfile:
    fixed_damage: int | None = None
    dice_expression: DiceExpression | None = None

    def __post_init__(self) -> None:
        _validate_exactly_one_expression(
            "DamageProfile",
            self.fixed_damage,
            self.dice_expression,
        )
        if self.fixed_damage is not None:
            _validate_positive_int("DamageProfile fixed_damage", self.fixed_damage)
        if self.dice_expression is not None:
            _validate_dice_expression("DamageProfile dice_expression", self.dice_expression)

    @classmethod
    def fixed(cls, damage: int) -> Self:
        return cls(fixed_damage=damage)

    @classmethod
    def dice(cls, expression: DiceExpression) -> Self:
        return cls(dice_expression=expression)

    def to_payload(self) -> DamageProfilePayload:
        dice_payload = None
        if self.dice_expression is not None:
            dice_payload = self.dice_expression.to_payload()
        return {
            "fixed_damage": self.fixed_damage,
            "dice_expression": dice_payload,
        }

    @classmethod
    def from_payload(cls, payload: DamageProfilePayload) -> Self:
        dice_payload = payload["dice_expression"]
        try:
            return cls(
                fixed_damage=payload["fixed_damage"],
                dice_expression=(
                    None if dice_payload is None else DiceExpression.from_payload(dice_payload)
                ),
            )
        except DiceRollSpecError as exc:
            raise WeaponProfileError("DamageProfile dice_expression payload is invalid.") from exc


@dataclass(frozen=True, slots=True)
class WeaponProfile:
    profile_id: str
    name: str
    range_profile: RangeProfile
    attack_profile: AttackProfile
    skill: CharacteristicValue
    strength: CharacteristicValue
    armor_penetration: CharacteristicValue
    damage_profile: DamageProfile
    keywords: tuple[WeaponKeyword, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _validate_identifier("WeaponProfile profile_id", self.profile_id),
        )
        object.__setattr__(self, "name", _validate_identifier("WeaponProfile name", self.name))
        _validate_range_profile(self.range_profile)
        _validate_attack_profile(self.attack_profile)
        _validate_damage_profile(self.damage_profile)
        _validate_characteristic_profile(
            "WeaponProfile skill",
            self.skill,
            frozenset({Characteristic.WEAPON_SKILL, Characteristic.BALLISTIC_SKILL}),
        )
        _validate_characteristic_profile(
            "WeaponProfile strength",
            self.strength,
            frozenset({Characteristic.STRENGTH}),
        )
        _validate_characteristic_profile(
            "WeaponProfile armor_penetration",
            self.armor_penetration,
            frozenset({Characteristic.ARMOR_PENETRATION}),
        )
        keywords = _canonical_keyword_tuple(self.keywords)
        if keywords != self.keywords:
            object.__setattr__(self, "keywords", keywords)

    def stable_identity(self) -> str:
        return f"weapon-profile:{self.profile_id}"

    def to_payload(self) -> WeaponProfilePayload:
        return {
            "profile_id": self.profile_id,
            "name": self.name,
            "range_profile": self.range_profile.to_payload(),
            "attack_profile": self.attack_profile.to_payload(),
            "skill": self.skill.to_payload(),
            "strength": self.strength.to_payload(),
            "armor_penetration": self.armor_penetration.to_payload(),
            "damage_profile": self.damage_profile.to_payload(),
            "keywords": [keyword.value for keyword in self.keywords],
        }

    @classmethod
    def from_payload(cls, payload: WeaponProfilePayload) -> Self:
        return cls(
            profile_id=payload["profile_id"],
            name=payload["name"],
            range_profile=RangeProfile.from_payload(payload["range_profile"]),
            attack_profile=AttackProfile.from_payload(payload["attack_profile"]),
            skill=_characteristic_value_from_payload("WeaponProfile skill", payload["skill"]),
            strength=_characteristic_value_from_payload(
                "WeaponProfile strength",
                payload["strength"],
            ),
            armor_penetration=_characteristic_value_from_payload(
                "WeaponProfile armor_penetration",
                payload["armor_penetration"],
            ),
            damage_profile=DamageProfile.from_payload(payload["damage_profile"]),
            keywords=tuple(weapon_keyword_from_token(keyword) for keyword in payload["keywords"]),
        )


def canonical_weapon_keyword_tokens() -> tuple[str, ...]:
    return tuple(keyword.value for keyword in WeaponKeyword)


def weapon_keyword_from_token(token: object) -> WeaponKeyword:
    if type(token) is not str:
        raise WeaponProfileError("WeaponKeyword token must be a string.")
    try:
        return WeaponKeyword(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported weapon keyword token: {token}.") from exc


def range_profile_kind_from_token(token: object) -> RangeProfileKind:
    if type(token) is not str:
        raise WeaponProfileError("RangeProfile kind token must be a string.")
    try:
        return RangeProfileKind(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported range profile kind token: {token}.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise WeaponProfileError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise WeaponProfileError(f"{field_name} must not be empty.")
    return stripped


def _validate_range_kind(kind: object) -> RangeProfileKind:
    if type(kind) is not RangeProfileKind:
        raise WeaponProfileError("RangeProfile kind must be a RangeProfileKind.")
    return kind


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise WeaponProfileError(f"{field_name} must be an integer.")
    if value < 1:
        raise WeaponProfileError(f"{field_name} must be at least 1.")
    return value


def _validate_exactly_one_expression(
    field_name: str,
    fixed_value: object | None,
    dice_expression: object | None,
) -> None:
    if fixed_value is None and dice_expression is None:
        raise WeaponProfileError(f"{field_name} must include a parsed value.")
    if fixed_value is not None and dice_expression is not None:
        raise WeaponProfileError(f"{field_name} must not mix fixed and dice values.")


def _validate_dice_expression(field_name: str, expression: object) -> DiceExpression:
    if type(expression) is not DiceExpression:
        raise WeaponProfileError(f"{field_name} must be a DiceExpression.")
    return expression


def _validate_range_profile(profile: object) -> RangeProfile:
    if type(profile) is not RangeProfile:
        raise WeaponProfileError("WeaponProfile range_profile must be a RangeProfile.")
    return profile


def _validate_attack_profile(profile: object) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise WeaponProfileError("WeaponProfile attack_profile must be an AttackProfile.")
    return profile


def _validate_damage_profile(profile: object) -> DamageProfile:
    if type(profile) is not DamageProfile:
        raise WeaponProfileError("WeaponProfile damage_profile must be a DamageProfile.")
    return profile


def _validate_characteristic_profile(
    field_name: str,
    value: object,
    allowed_characteristics: frozenset[Characteristic],
) -> CharacteristicValue:
    if type(value) is not CharacteristicValue:
        raise WeaponProfileError(f"{field_name} must be a CharacteristicValue.")
    if value.characteristic not in allowed_characteristics:
        raise WeaponProfileError(f"{field_name} has the wrong characteristic.")
    return value


def _characteristic_value_from_payload(
    field_name: str,
    payload: CharacteristicValuePayload,
) -> CharacteristicValue:
    try:
        return CharacteristicValue.from_payload(payload)
    except CharacteristicError as exc:
        raise WeaponProfileError(f"{field_name} payload is invalid.") from exc


def _canonical_keyword_tuple(keywords: tuple[WeaponKeyword, ...]) -> tuple[WeaponKeyword, ...]:
    validated = tuple(_validate_weapon_keyword(keyword) for keyword in keywords)
    seen: set[WeaponKeyword] = set()
    for keyword in validated:
        if keyword in seen:
            raise WeaponProfileError("WeaponProfile keywords must not contain duplicates.")
        seen.add(keyword)
    return tuple(sorted(validated, key=lambda keyword: keyword.value))


def _validate_weapon_keyword(keyword: object) -> WeaponKeyword:
    if type(keyword) is not WeaponKeyword:
        raise WeaponProfileError("WeaponProfile keywords must be WeaponKeyword values.")
    return keyword
