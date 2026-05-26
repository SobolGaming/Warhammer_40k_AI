from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from math import isfinite
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


class AbilityKind(StrEnum):
    SUSTAINED_HITS = "sustained_hits"
    MELTA = "melta"
    RAPID_FIRE = "rapid_fire"
    HEAVY = "heavy"


class AbilityTiming(StrEnum):
    ATTACK_SEQUENCE = "attack_sequence"
    MOVEMENT_CONDITIONED = "movement_conditioned"


class AbilityCondition(StrEnum):
    STATIONARY_OR_POLICY_DEFINED = "stationary_or_policy_defined"


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


AbilityParameterValue = int | float | str | bool


class AbilityParameterPayload(TypedDict):
    name: str
    value: AbilityParameterValue


class AbilityDescriptorPayload(TypedDict):
    ability_id: str
    name: str
    ability_kind: str
    parameters: list[AbilityParameterPayload]
    timing: str | None
    condition: str | None


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
    abilities: list[AbilityDescriptorPayload]


@dataclass(frozen=True, slots=True)
class AbilityParameter:
    name: str
    value: AbilityParameterValue

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validate_identifier("AbilityParameter name", self.name))
        _validate_ability_parameter_value(self.value)

    @classmethod
    def integer(cls, value: int) -> Self:
        return cls(name="value", value=value)

    def to_payload(self) -> AbilityParameterPayload:
        return {
            "name": self.name,
            "value": self.value,
        }

    @classmethod
    def from_payload(cls, payload: AbilityParameterPayload) -> Self:
        return cls(name=payload["name"], value=payload["value"])


@dataclass(frozen=True, slots=True)
class AbilityDescriptor:
    ability_id: str
    name: str
    ability_kind: AbilityKind
    parameters: tuple[AbilityParameter, ...] = ()
    timing: AbilityTiming | None = None
    condition: AbilityCondition | None = None

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_id",
            _validate_ability_id(self.ability_id),
        )
        object.__setattr__(self, "name", _validate_identifier("AbilityDescriptor name", self.name))

        ability_kind = _validate_ability_kind(self.ability_kind)
        if ability_kind != self.ability_kind:
            object.__setattr__(self, "ability_kind", ability_kind)

        parameters = _canonical_ability_parameters(self.parameters)
        if parameters != self.parameters:
            object.__setattr__(self, "parameters", parameters)

        timing = _validate_optional_ability_timing(self.timing)
        if timing != self.timing:
            object.__setattr__(self, "timing", timing)

        condition = _validate_optional_ability_condition(self.condition)
        if condition != self.condition:
            object.__setattr__(self, "condition", condition)

        _validate_supported_ability_shape(
            ability_kind=ability_kind,
            parameters=parameters,
            condition=condition,
        )

    @classmethod
    def sustained_hits(cls, value: int) -> Self:
        return cls(
            ability_id=f"sustained-hits:{value}",
            name=f"Sustained Hits {value}",
            ability_kind=AbilityKind.SUSTAINED_HITS,
            parameters=(AbilityParameter.integer(value),),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def melta(cls, value: int) -> Self:
        return cls(
            ability_id=f"melta:{value}",
            name=f"Melta {value}",
            ability_kind=AbilityKind.MELTA,
            parameters=(AbilityParameter.integer(value),),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def rapid_fire(cls, value: int) -> Self:
        return cls(
            ability_id=f"rapid-fire:{value}",
            name=f"Rapid Fire {value}",
            ability_kind=AbilityKind.RAPID_FIRE,
            parameters=(AbilityParameter.integer(value),),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def heavy(cls) -> Self:
        return cls(
            ability_id="heavy:stationary-or-policy-defined",
            name="Heavy",
            ability_kind=AbilityKind.HEAVY,
            timing=AbilityTiming.MOVEMENT_CONDITIONED,
            condition=AbilityCondition.STATIONARY_OR_POLICY_DEFINED,
        )

    def to_payload(self) -> AbilityDescriptorPayload:
        return {
            "ability_id": self.ability_id,
            "name": self.name,
            "ability_kind": self.ability_kind.value,
            "parameters": [parameter.to_payload() for parameter in self.parameters],
            "timing": None if self.timing is None else self.timing.value,
            "condition": None if self.condition is None else self.condition.value,
        }

    @classmethod
    def from_payload(cls, payload: AbilityDescriptorPayload) -> Self:
        return cls(
            ability_id=payload["ability_id"],
            name=payload["name"],
            ability_kind=ability_kind_from_token(payload["ability_kind"]),
            parameters=tuple(
                AbilityParameter.from_payload(parameter) for parameter in payload["parameters"]
            ),
            timing=ability_timing_from_token(payload["timing"]),
            condition=ability_condition_from_token(payload["condition"]),
        )


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
            if self.distance_inches < 1:
                raise WeaponProfileError("RangeProfile distance_inches must be at least 1.")
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
    abilities: tuple[AbilityDescriptor, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "profile_id",
            _validate_profile_id(self.profile_id),
        )
        object.__setattr__(self, "name", _validate_identifier("WeaponProfile name", self.name))
        _validate_range_profile(self.range_profile)
        _validate_attack_profile(self.attack_profile)
        _validate_damage_profile(self.damage_profile)
        _validate_unmodified_characteristic_profile(
            "WeaponProfile skill",
            self.skill,
            frozenset({Characteristic.WEAPON_SKILL, Characteristic.BALLISTIC_SKILL}),
        )
        _validate_unmodified_characteristic_profile(
            "WeaponProfile strength",
            self.strength,
            frozenset({Characteristic.STRENGTH}),
        )
        _validate_unmodified_characteristic_profile(
            "WeaponProfile armor_penetration",
            self.armor_penetration,
            frozenset({Characteristic.ARMOR_PENETRATION}),
        )
        keywords = _canonical_keyword_tuple(self.keywords)
        if keywords != self.keywords:
            object.__setattr__(self, "keywords", keywords)
        abilities = _canonical_ability_tuple(self.abilities)
        if abilities != self.abilities:
            object.__setattr__(self, "abilities", abilities)

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
            "abilities": [ability.to_payload() for ability in self.abilities],
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
            abilities=tuple(
                AbilityDescriptor.from_payload(ability) for ability in payload["abilities"]
            ),
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


def ability_kind_from_token(token: object) -> AbilityKind:
    if type(token) is AbilityKind:
        return token
    if type(token) is not str:
        raise WeaponProfileError("AbilityKind token must be a string.")
    try:
        return AbilityKind(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported ability kind token: {token}.") from exc


def ability_timing_from_token(token: object | None) -> AbilityTiming | None:
    if token is None:
        return None
    if type(token) is AbilityTiming:
        return token
    if type(token) is not str:
        raise WeaponProfileError("AbilityTiming token must be a string.")
    try:
        return AbilityTiming(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported ability timing token: {token}.") from exc


def ability_condition_from_token(token: object | None) -> AbilityCondition | None:
    if token is None:
        return None
    if type(token) is AbilityCondition:
        return token
    if type(token) is not str:
        raise WeaponProfileError("AbilityCondition token must be a string.")
    try:
        return AbilityCondition(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported ability condition token: {token}.") from exc


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


def _validate_ability_id(value: object) -> str:
    identifier = _validate_identifier("AbilityDescriptor ability_id", value)
    if identifier.startswith("ability:"):
        raise WeaponProfileError(
            "AbilityDescriptor ability_id must not include the stable identity prefix."
        )
    return identifier


def _validate_profile_id(value: object) -> str:
    identifier = _validate_identifier("WeaponProfile profile_id", value)
    if identifier.startswith("weapon-profile:"):
        raise WeaponProfileError(
            "WeaponProfile profile_id must not include the stable identity prefix."
        )
    return identifier


def _validate_range_kind(kind: object) -> RangeProfileKind:
    if type(kind) is not RangeProfileKind:
        raise WeaponProfileError("RangeProfile kind must be a RangeProfileKind.")
    return kind


def _validate_ability_kind(kind: object) -> AbilityKind:
    if type(kind) is not AbilityKind:
        raise WeaponProfileError("AbilityDescriptor ability_kind must be an AbilityKind.")
    return kind


def _validate_optional_ability_timing(timing: object | None) -> AbilityTiming | None:
    if timing is None:
        return None
    if type(timing) is not AbilityTiming:
        raise WeaponProfileError("AbilityDescriptor timing must be an AbilityTiming.")
    return timing


def _validate_optional_ability_condition(condition: object | None) -> AbilityCondition | None:
    if condition is None:
        return None
    if type(condition) is not AbilityCondition:
        raise WeaponProfileError("AbilityDescriptor condition must be an AbilityCondition.")
    return condition


def _validate_ability_parameter_value(value: object) -> AbilityParameterValue:
    if type(value) is str:
        if not value.strip():
            raise WeaponProfileError("AbilityParameter value string must not be empty.")
        return value
    if type(value) is bool:
        return value
    if type(value) is int:
        return value
    if type(value) is float:
        if not isfinite(value):
            raise WeaponProfileError("AbilityParameter value float must be finite.")
        return value
    raise WeaponProfileError("AbilityParameter value must be JSON-safe scalar data.")


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


def _validate_unmodified_characteristic_profile(
    field_name: str,
    value: object,
    allowed_characteristics: frozenset[Characteristic],
) -> CharacteristicValue:
    characteristic_value = _validate_characteristic_profile(
        field_name,
        value,
        allowed_characteristics,
    )
    if (
        characteristic_value.raw != characteristic_value.base
        or characteristic_value.base != characteristic_value.final
        or characteristic_value.applied_modifier_ids
    ):
        raise WeaponProfileError(f"{field_name} must be an unmodified base profile value.")
    return characteristic_value


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


def _canonical_ability_tuple(
    abilities: tuple[AbilityDescriptor, ...],
) -> tuple[AbilityDescriptor, ...]:
    validated = tuple(_validate_ability_descriptor(ability) for ability in abilities)
    seen: set[str] = set()
    for ability in validated:
        if ability.ability_id in seen:
            raise WeaponProfileError("WeaponProfile abilities must not contain duplicate IDs.")
        seen.add(ability.ability_id)
    return tuple(sorted(validated, key=lambda ability: ability.ability_id))


def _validate_ability_descriptor(ability: object) -> AbilityDescriptor:
    if type(ability) is not AbilityDescriptor:
        raise WeaponProfileError("WeaponProfile abilities must be AbilityDescriptor values.")
    return ability


def _canonical_ability_parameters(
    parameters: tuple[AbilityParameter, ...],
) -> tuple[AbilityParameter, ...]:
    validated = tuple(_validate_ability_parameter(parameter) for parameter in parameters)
    seen: set[str] = set()
    for parameter in validated:
        if parameter.name in seen:
            raise WeaponProfileError("AbilityDescriptor parameters must not contain duplicates.")
        seen.add(parameter.name)
    return tuple(sorted(validated, key=lambda parameter: parameter.name))


def _validate_ability_parameter(parameter: object) -> AbilityParameter:
    if type(parameter) is not AbilityParameter:
        raise WeaponProfileError("AbilityDescriptor parameters must be AbilityParameter values.")
    return parameter


def _validate_supported_ability_shape(
    *,
    ability_kind: AbilityKind,
    parameters: tuple[AbilityParameter, ...],
    condition: AbilityCondition | None,
) -> None:
    if ability_kind in {
        AbilityKind.SUSTAINED_HITS,
        AbilityKind.MELTA,
        AbilityKind.RAPID_FIRE,
    }:
        _validate_single_positive_int_parameter(ability_kind, parameters)
        if condition is not None:
            raise WeaponProfileError("Parameterized weapon abilities must not include a condition.")
        return

    if ability_kind is AbilityKind.HEAVY:
        if parameters:
            raise WeaponProfileError("Heavy ability must not include parameters.")
        if condition is not AbilityCondition.STATIONARY_OR_POLICY_DEFINED:
            raise WeaponProfileError("Heavy ability must include the stationary policy condition.")
        return

    raise WeaponProfileError("Unsupported weapon ability kind.")


def _validate_single_positive_int_parameter(
    ability_kind: AbilityKind,
    parameters: tuple[AbilityParameter, ...],
) -> None:
    if len(parameters) != 1 or parameters[0].name != "value":
        raise WeaponProfileError(f"{ability_kind.value} ability must include one value parameter.")
    value = parameters[0].value
    if type(value) is not int or value < 1:
        raise WeaponProfileError(f"{ability_kind.value} ability value parameter must be positive.")
