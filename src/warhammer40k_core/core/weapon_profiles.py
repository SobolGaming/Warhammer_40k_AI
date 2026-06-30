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
    CLEAVE = "Cleave"
    TWIN_LINKED = "Twin-linked"
    IGNORES_COVER = "Ignores Cover"
    INDIRECT_FIRE = "Indirect Fire"
    EXTRA_ATTACKS = "Extra Attacks"
    LANCE = "Lance"
    RAPID_FIRE = "Rapid Fire"
    PRECISION = "Precision"
    HAZARDOUS = "Hazardous"
    ASSAULT = "Assault"
    TORRENT = "Torrent"
    PSYCHIC = "Psychic"
    PISTOL = "Pistol"
    CLOSE_QUARTERS = "Close-quarters"
    HEAVY = "Heavy"
    BLAST = "Blast"
    MELTA = "Melta"
    ONE_SHOT = "One Shot"
    HUNTER = "Hunter"


class AbilityKind(StrEnum):
    DEVASTATING_WOUNDS = "devastating_wounds"
    SUSTAINED_HITS = "sustained_hits"
    LETHAL_HITS = "lethal_hits"
    CLEAVE = "cleave"
    MELTA = "melta"
    RAPID_FIRE = "rapid_fire"
    ANTI_KEYWORD = "anti_keyword"
    HEAVY = "heavy"
    HUNTER = "hunter"


class AbilityTiming(StrEnum):
    ATTACK_SEQUENCE = "attack_sequence"
    TARGET_DECLARATION = "target_declaration"
    MOVEMENT_CONDITIONED = "movement_conditioned"


class AbilityCondition(StrEnum):
    STATIONARY_OR_POLICY_DEFINED = "stationary_or_policy_defined"


class DevastatingWoundsEffect(StrEnum):
    MORTAL_WOUNDS = "mortal_wounds"
    NO_SAVES = "no_saves"


class AntiKeywordMatchMode(StrEnum):
    HAS_KEYWORD = "has_keyword"
    MISSING_KEYWORD = "missing_keyword"


class TargetKeywordMatchMode(StrEnum):
    HAS_KEYWORD = "has_keyword"
    MISSING_KEYWORD = "missing_keyword"


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
TARGET_KEYWORD_MATCH_MODE_PARAMETER = "target_keyword_match_mode"


class AbilityParameterPayload(TypedDict):
    name: str
    value: AbilityParameterValue


class AbilityDescriptorPayload(TypedDict):
    ability_id: str
    name: str
    ability_kind: str
    parameters: list[AbilityParameterPayload]
    target_keywords: list[str]
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
    source_ids: list[str]


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
    target_keywords: tuple[str, ...] = ()
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

        raw_parameters = _canonical_ability_parameters(self.parameters)
        target_keywords, target_keyword_match_mode = _canonical_target_keyword_gate(
            self.target_keywords,
            explicit_match_mode=_optional_target_keyword_match_mode(raw_parameters),
        )
        if target_keywords != self.target_keywords:
            object.__setattr__(self, "target_keywords", target_keywords)
        parameters = _parameters_with_target_keyword_match_mode(
            raw_parameters,
            target_keyword_match_mode=target_keyword_match_mode,
            target_keywords=target_keywords,
        )
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
            target_keywords=target_keywords,
            timing=timing,
            condition=condition,
        )

    @classmethod
    def sustained_hits(
        cls,
        value: int | str,
        *,
        target_keywords: tuple[str, ...] = (),
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        resolved_value = _validate_sustained_hits_value(value)
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"sustained-hits:{resolved_value}{id_suffix}",
            name=f"Sustained Hits {resolved_value}{name_suffix}",
            ability_kind=AbilityKind.SUSTAINED_HITS,
            parameters=_parameters_with_target_keyword_match_mode(
                (AbilityParameter(name="value", value=resolved_value),),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def lethal_hits(
        cls,
        *,
        target_keywords: tuple[str, ...] = (),
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"lethal-hits{id_suffix}",
            name=f"Lethal Hits{name_suffix}",
            ability_kind=AbilityKind.LETHAL_HITS,
            parameters=_parameters_with_target_keyword_match_mode(
                (),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def hunter(
        cls,
        *,
        target_keywords: tuple[str, ...],
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"hunter{id_suffix}",
            name=f"Hunter{name_suffix}",
            ability_kind=AbilityKind.HUNTER,
            parameters=_parameters_with_target_keyword_match_mode(
                (),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
            timing=AbilityTiming.TARGET_DECLARATION,
        )

    @classmethod
    def cleave(
        cls,
        value: int,
        *,
        target_keywords: tuple[str, ...] = (),
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"cleave:{value}{id_suffix}",
            name=f"Cleave {value}{name_suffix}",
            ability_kind=AbilityKind.CLEAVE,
            parameters=_parameters_with_target_keyword_match_mode(
                (AbilityParameter.integer(value),),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def melta(
        cls,
        value: int,
        *,
        target_keywords: tuple[str, ...] = (),
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"melta:{value}{id_suffix}",
            name=f"Melta {value}{name_suffix}",
            ability_kind=AbilityKind.MELTA,
            parameters=_parameters_with_target_keyword_match_mode(
                (AbilityParameter.integer(value),),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def rapid_fire(
        cls,
        value: int,
        *,
        target_keywords: tuple[str, ...] = (),
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"rapid-fire:{value}{id_suffix}",
            name=f"Rapid Fire {value}{name_suffix}",
            ability_kind=AbilityKind.RAPID_FIRE,
            parameters=_parameters_with_target_keyword_match_mode(
                (AbilityParameter.integer(value),),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def anti_keyword(
        cls,
        keyword: str,
        threshold: int,
        *,
        match_mode: AntiKeywordMatchMode = AntiKeywordMatchMode.HAS_KEYWORD,
    ) -> Self:
        canonical_keywords = _canonical_rule_keyword_group(keyword)
        resolved_match_mode = anti_keyword_match_mode_from_token(match_mode)
        _validate_d6_critical_threshold("Anti keyword threshold", threshold)
        ability_id_prefix = (
            "anti-keyword"
            if resolved_match_mode is AntiKeywordMatchMode.HAS_KEYWORD
            else "anti-non-keyword"
        )
        name_prefix = (
            "Anti" if resolved_match_mode is AntiKeywordMatchMode.HAS_KEYWORD else "Anti-Non"
        )
        keyword_name = "/".join(
            canonical_keyword.replace("_", " ").title() for canonical_keyword in canonical_keywords
        )
        parameters = [
            AbilityParameter(name="keyword", value="/".join(canonical_keywords)),
            AbilityParameter(name="threshold", value=threshold),
        ]
        if resolved_match_mode is not AntiKeywordMatchMode.HAS_KEYWORD:
            parameters.append(AbilityParameter(name="match_mode", value=resolved_match_mode.value))
        return cls(
            ability_id=(
                f"{ability_id_prefix}:{'/'.join(keyword.lower() for keyword in canonical_keywords)}"
                f":{threshold}"
            ),
            name=f"{name_prefix}-{keyword_name} {threshold}+",
            ability_kind=AbilityKind.ANTI_KEYWORD,
            parameters=tuple(parameters),
            timing=AbilityTiming.ATTACK_SEQUENCE,
        )

    @classmethod
    def devastating_wounds(
        cls,
        effect: DevastatingWoundsEffect = DevastatingWoundsEffect.MORTAL_WOUNDS,
        *,
        target_keywords: tuple[str, ...] = (),
        target_keyword_match_mode: TargetKeywordMatchMode | None = None,
    ) -> Self:
        resolved_effect = devastating_wounds_effect_from_token(effect)
        canonical_target_keywords, resolved_match_mode = _canonical_target_keyword_gate(
            target_keywords,
            explicit_match_mode=target_keyword_match_mode,
        )
        id_suffix = _target_keyword_ability_id_suffix(
            canonical_target_keywords,
            resolved_match_mode,
        )
        name_suffix = _target_keyword_name_suffix(canonical_target_keywords, resolved_match_mode)
        return cls(
            ability_id=f"devastating-wounds:{resolved_effect.value}{id_suffix}",
            name=f"Devastating Wounds{name_suffix}",
            ability_kind=AbilityKind.DEVASTATING_WOUNDS,
            parameters=_parameters_with_target_keyword_match_mode(
                (AbilityParameter(name="effect", value=resolved_effect.value),),
                target_keyword_match_mode=resolved_match_mode,
                target_keywords=canonical_target_keywords,
            ),
            target_keywords=canonical_target_keywords,
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
            "target_keywords": list(self.target_keywords),
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
            target_keywords=tuple(payload["target_keywords"]),
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
    source_ids: tuple[str, ...] = ()

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
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple(
                "WeaponProfile source_ids",
                self.source_ids,
                min_length=0,
                sort_values=True,
            ),
        )

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
            "source_ids": list(self.source_ids),
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
            source_ids=tuple(payload["source_ids"]),
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


def devastating_wounds_effect_from_token(token: object) -> DevastatingWoundsEffect:
    if type(token) is DevastatingWoundsEffect:
        return token
    if type(token) is not str:
        raise WeaponProfileError("DevastatingWoundsEffect token must be a string.")
    try:
        return DevastatingWoundsEffect(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported DevastatingWoundsEffect token: {token}.") from exc


def anti_keyword_match_mode_from_token(token: object) -> AntiKeywordMatchMode:
    if type(token) is AntiKeywordMatchMode:
        return token
    if type(token) is not str:
        raise WeaponProfileError("AntiKeywordMatchMode token must be a string.")
    try:
        return AntiKeywordMatchMode(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported AntiKeywordMatchMode token: {token}.") from exc


def target_keyword_match_mode_from_token(token: object) -> TargetKeywordMatchMode:
    if type(token) is TargetKeywordMatchMode:
        return token
    if type(token) is not str:
        raise WeaponProfileError("TargetKeywordMatchMode token must be a string.")
    try:
        return TargetKeywordMatchMode(token)
    except ValueError as exc:
        raise WeaponProfileError(f"Unsupported TargetKeywordMatchMode token: {token}.") from exc


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


def _validate_identifier_tuple(
    field_name: str,
    values: tuple[str, ...],
    *,
    min_length: int,
    sort_values: bool,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise WeaponProfileError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise WeaponProfileError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise WeaponProfileError(f"{field_name} must contain at least {min_length} values.")
    if sort_values:
        return tuple(sorted(validated))
    return tuple(validated)


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
    validate_weapon_ability_descriptor_multiplicity(validated)
    return tuple(sorted(validated, key=lambda ability: ability.ability_id))


def validate_weapon_ability_descriptor_multiplicity(
    abilities: tuple[AbilityDescriptor, ...],
) -> None:
    if type(abilities) is not tuple:
        raise WeaponProfileError("Weapon ability descriptor multiplicity requires a tuple.")
    seen_non_selectable_kinds: set[AbilityKind] = set()
    for ability in abilities:
        _validate_ability_descriptor(ability)
        if ability.ability_kind is AbilityKind.ANTI_KEYWORD:
            continue
        if ability.ability_kind in seen_non_selectable_kinds:
            raise WeaponProfileError(
                "WeaponProfile abilities must not contain duplicate non-Anti ability kinds."
            )
        seen_non_selectable_kinds.add(ability.ability_kind)


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


def _canonical_target_keyword_gate(
    values: tuple[str, ...],
    *,
    explicit_match_mode: TargetKeywordMatchMode | None,
) -> tuple[tuple[str, ...], TargetKeywordMatchMode]:
    if type(values) is not tuple:
        raise WeaponProfileError("AbilityDescriptor target_keywords must be a tuple.")
    keywords: list[str] = []
    seen: set[str] = set()
    inferred_match_mode: TargetKeywordMatchMode | None = None
    for value in values:
        if type(value) is not str:
            raise WeaponProfileError("AbilityDescriptor target keyword must be a string.")
        match_mode, keyword_group = _target_keyword_condition_group(value)
        if inferred_match_mode is None:
            inferred_match_mode = match_mode
        elif inferred_match_mode is not match_mode:
            raise WeaponProfileError(
                "AbilityDescriptor target keyword gate must not mix positive and non- conditions."
            )
        for part in keyword_group.split("/"):
            keyword = _canonical_rule_keyword(part)
            if keyword in seen:
                raise WeaponProfileError(
                    "AbilityDescriptor target_keywords must not contain duplicates."
                )
            seen.add(keyword)
            keywords.append(keyword)
    resolved_match_mode = _resolve_target_keyword_match_mode(
        explicit_match_mode=explicit_match_mode,
        inferred_match_mode=inferred_match_mode,
    )
    if not keywords and resolved_match_mode is TargetKeywordMatchMode.MISSING_KEYWORD:
        raise WeaponProfileError("AbilityDescriptor non- target keyword gate requires keywords.")
    return tuple(keywords), resolved_match_mode


def _target_keyword_condition_group(value: str) -> tuple[TargetKeywordMatchMode, str]:
    stripped = _validate_identifier("AbilityDescriptor target keyword", value)
    for prefix in ("non-", "non_", "non "):
        if stripped.casefold().startswith(prefix):
            keyword_group = stripped[len(prefix) :].strip()
            if not keyword_group:
                raise WeaponProfileError(
                    "AbilityDescriptor non- target keyword gate requires keywords."
                )
            return TargetKeywordMatchMode.MISSING_KEYWORD, keyword_group
    return TargetKeywordMatchMode.HAS_KEYWORD, stripped


def _resolve_target_keyword_match_mode(
    *,
    explicit_match_mode: TargetKeywordMatchMode | None,
    inferred_match_mode: TargetKeywordMatchMode | None,
) -> TargetKeywordMatchMode:
    if explicit_match_mode is None:
        return (
            TargetKeywordMatchMode.HAS_KEYWORD
            if inferred_match_mode is None
            else inferred_match_mode
        )
    resolved_explicit = target_keyword_match_mode_from_token(explicit_match_mode)
    if (
        inferred_match_mode is not None
        and inferred_match_mode is not TargetKeywordMatchMode.HAS_KEYWORD
        and inferred_match_mode is not resolved_explicit
    ):
        raise WeaponProfileError(
            "AbilityDescriptor explicit target keyword match mode conflicts with non- keywords."
        )
    return resolved_explicit


def _optional_target_keyword_match_mode(
    parameters: tuple[AbilityParameter, ...],
) -> TargetKeywordMatchMode | None:
    for parameter in parameters:
        if parameter.name == TARGET_KEYWORD_MATCH_MODE_PARAMETER:
            return target_keyword_match_mode_from_token(parameter.value)
    return None


def _parameters_with_target_keyword_match_mode(
    parameters: tuple[AbilityParameter, ...],
    *,
    target_keyword_match_mode: TargetKeywordMatchMode,
    target_keywords: tuple[str, ...],
) -> tuple[AbilityParameter, ...]:
    if not target_keywords:
        if target_keyword_match_mode is TargetKeywordMatchMode.MISSING_KEYWORD:
            raise WeaponProfileError(
                "AbilityDescriptor non- target keyword gate requires keywords."
            )
        return tuple(
            parameter
            for parameter in parameters
            if parameter.name != TARGET_KEYWORD_MATCH_MODE_PARAMETER
        )
    retained = tuple(
        parameter
        for parameter in parameters
        if parameter.name != TARGET_KEYWORD_MATCH_MODE_PARAMETER
    )
    if target_keyword_match_mode is TargetKeywordMatchMode.HAS_KEYWORD:
        return _canonical_ability_parameters(retained)
    return _canonical_ability_parameters(
        (
            *retained,
            AbilityParameter(
                name=TARGET_KEYWORD_MATCH_MODE_PARAMETER,
                value=target_keyword_match_mode.value,
            ),
        )
    )


def _target_keyword_ability_id_suffix(
    target_keywords: tuple[str, ...],
    target_keyword_match_mode: TargetKeywordMatchMode,
) -> str:
    if not target_keywords:
        return ""
    prefix = "non-" if target_keyword_match_mode is TargetKeywordMatchMode.MISSING_KEYWORD else ""
    return ":" + prefix + "/".join(keyword.lower() for keyword in target_keywords)


def _target_keyword_name_suffix(
    target_keywords: tuple[str, ...],
    target_keyword_match_mode: TargetKeywordMatchMode,
) -> str:
    if not target_keywords:
        return ""
    prefix = "non-" if target_keyword_match_mode is TargetKeywordMatchMode.MISSING_KEYWORD else ""
    return (
        ": " + prefix + "/".join(keyword.replace("_", " ").title() for keyword in target_keywords)
    )


def _validate_supported_ability_shape(
    *,
    ability_kind: AbilityKind,
    parameters: tuple[AbilityParameter, ...],
    target_keywords: tuple[str, ...],
    timing: AbilityTiming | None,
    condition: AbilityCondition | None,
) -> None:
    if ability_kind in {
        AbilityKind.CLEAVE,
        AbilityKind.MELTA,
        AbilityKind.RAPID_FIRE,
    }:
        _validate_single_positive_int_parameter(ability_kind, parameters)
        _validate_target_keyword_match_mode_parameter(parameters, target_keywords=target_keywords)
        if timing is not AbilityTiming.ATTACK_SEQUENCE:
            raise WeaponProfileError("Parameterized weapon abilities must use attack timing.")
        if condition is not None:
            raise WeaponProfileError("Parameterized weapon abilities must not include a condition.")
        return

    if ability_kind is AbilityKind.SUSTAINED_HITS:
        _validate_sustained_hits_value_parameter(parameters)
        _validate_target_keyword_match_mode_parameter(parameters, target_keywords=target_keywords)
        if timing is not AbilityTiming.ATTACK_SEQUENCE:
            raise WeaponProfileError("Parameterized weapon abilities must use attack timing.")
        if condition is not None:
            raise WeaponProfileError("Parameterized weapon abilities must not include a condition.")
        return

    if ability_kind is AbilityKind.LETHAL_HITS:
        _validate_parameter_names(
            "Lethal Hits ability",
            parameters,
            allowed_names=frozenset({TARGET_KEYWORD_MATCH_MODE_PARAMETER}),
        )
        _validate_target_keyword_match_mode_parameter(parameters, target_keywords=target_keywords)
        if timing is not AbilityTiming.ATTACK_SEQUENCE:
            raise WeaponProfileError("Lethal Hits ability must use attack timing.")
        if condition is not None:
            raise WeaponProfileError("Lethal Hits ability must not include a condition.")
        return

    if ability_kind is AbilityKind.HUNTER:
        _validate_parameter_names(
            "Hunter ability",
            parameters,
            allowed_names=frozenset({TARGET_KEYWORD_MATCH_MODE_PARAMETER}),
        )
        _validate_target_keyword_match_mode_parameter(parameters, target_keywords=target_keywords)
        if not target_keywords:
            raise WeaponProfileError("Hunter ability requires target keywords.")
        if timing is not AbilityTiming.TARGET_DECLARATION:
            raise WeaponProfileError("Hunter ability must use target declaration timing.")
        if condition is not None:
            raise WeaponProfileError("Hunter ability must not include a condition.")
        return

    if ability_kind is AbilityKind.ANTI_KEYWORD:
        _validate_anti_keyword_parameters(parameters, target_keywords=target_keywords)
        if timing is not AbilityTiming.ATTACK_SEQUENCE:
            raise WeaponProfileError("Anti keyword ability must use attack timing.")
        if condition is not None:
            raise WeaponProfileError("Anti keyword ability must not include a condition.")
        return

    if ability_kind is AbilityKind.DEVASTATING_WOUNDS:
        _validate_devastating_wounds_parameters(parameters)
        _validate_target_keyword_match_mode_parameter(parameters, target_keywords=target_keywords)
        if timing is not AbilityTiming.ATTACK_SEQUENCE:
            raise WeaponProfileError("Devastating Wounds ability must use attack timing.")
        if condition is not None:
            raise WeaponProfileError("Devastating Wounds ability must not include a condition.")
        return

    if ability_kind is AbilityKind.HEAVY:
        if parameters:
            raise WeaponProfileError("Heavy ability must not include parameters.")
        if target_keywords:
            raise WeaponProfileError("Heavy ability must not include target keywords.")
        if timing is not AbilityTiming.MOVEMENT_CONDITIONED:
            raise WeaponProfileError("Heavy ability must use movement-conditioned timing.")
        if condition is not AbilityCondition.STATIONARY_OR_POLICY_DEFINED:
            raise WeaponProfileError("Heavy ability must include the stationary policy condition.")
        return

    raise WeaponProfileError("Unsupported weapon ability kind.")


def _validate_single_positive_int_parameter(
    ability_kind: AbilityKind,
    parameters: tuple[AbilityParameter, ...],
) -> None:
    _validate_parameter_names(
        f"{ability_kind.value} ability",
        parameters,
        allowed_names=frozenset({"value", TARGET_KEYWORD_MATCH_MODE_PARAMETER}),
    )
    value_parameters = tuple(parameter for parameter in parameters if parameter.name == "value")
    if len(value_parameters) != 1:
        raise WeaponProfileError(f"{ability_kind.value} ability must include one value parameter.")
    value = value_parameters[0].value
    if type(value) is not int or value < 1:
        raise WeaponProfileError(f"{ability_kind.value} ability value parameter must be positive.")


def _validate_sustained_hits_value_parameter(parameters: tuple[AbilityParameter, ...]) -> None:
    _validate_parameter_names(
        "sustained_hits ability",
        parameters,
        allowed_names=frozenset({"value", TARGET_KEYWORD_MATCH_MODE_PARAMETER}),
    )
    value_parameters = tuple(parameter for parameter in parameters if parameter.name == "value")
    if len(value_parameters) != 1:
        raise WeaponProfileError("sustained_hits ability must include one value parameter.")
    _validate_sustained_hits_value(value_parameters[0].value)


def _validate_sustained_hits_value(value: object) -> int | str:
    if type(value) is int and value >= 1:
        return value
    if type(value) is str and value == "D3":
        return value
    raise WeaponProfileError("sustained_hits ability value parameter must be positive or D3.")


def _validate_parameter_names(
    ability_label: str,
    parameters: tuple[AbilityParameter, ...],
    *,
    allowed_names: frozenset[str],
) -> None:
    names = {parameter.name for parameter in parameters}
    if not names.issubset(allowed_names):
        raise WeaponProfileError(f"{ability_label} includes unsupported parameters.")


def _validate_target_keyword_match_mode_parameter(
    parameters: tuple[AbilityParameter, ...],
    *,
    target_keywords: tuple[str, ...],
) -> None:
    match_mode = _optional_target_keyword_match_mode(parameters)
    if match_mode is None:
        return
    if not target_keywords:
        raise WeaponProfileError("target_keyword_match_mode parameter requires target keywords.")


def _validate_anti_keyword_parameters(
    parameters: tuple[AbilityParameter, ...],
    *,
    target_keywords: tuple[str, ...],
) -> None:
    by_name = {parameter.name: parameter for parameter in parameters}
    allowed_names = {"keyword", "threshold", "match_mode", TARGET_KEYWORD_MATCH_MODE_PARAMETER}
    if not {"keyword", "threshold"}.issubset(by_name) or not set(by_name).issubset(allowed_names):
        raise WeaponProfileError(
            "anti_keyword ability must include keyword and threshold, "
            "and may include optional match modes."
        )
    keyword = by_name["keyword"].value
    if type(keyword) is not str:
        raise WeaponProfileError("anti_keyword keyword parameter must be a string.")
    if "/".join(_canonical_rule_keyword_group(keyword)) != keyword:
        raise WeaponProfileError("anti_keyword keyword parameter must be canonical.")
    if "match_mode" in by_name:
        anti_keyword_match_mode_from_token(by_name["match_mode"].value)
    _validate_target_keyword_match_mode_parameter(parameters, target_keywords=target_keywords)
    _validate_d6_critical_threshold(
        "anti_keyword threshold parameter",
        by_name["threshold"].value,
    )


def _validate_devastating_wounds_parameters(parameters: tuple[AbilityParameter, ...]) -> None:
    _validate_parameter_names(
        "devastating_wounds ability",
        parameters,
        allowed_names=frozenset({"effect", TARGET_KEYWORD_MATCH_MODE_PARAMETER}),
    )
    effect_parameters = tuple(parameter for parameter in parameters if parameter.name == "effect")
    if len(effect_parameters) != 1:
        raise WeaponProfileError("devastating_wounds ability must include one effect parameter.")
    devastating_wounds_effect_from_token(effect_parameters[0].value)


def _canonical_rule_keyword(keyword: object) -> str:
    if type(keyword) is not str:
        raise WeaponProfileError("Rule keyword must be a string.")
    stripped = keyword.strip()
    if not stripped:
        raise WeaponProfileError("Rule keyword must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _canonical_rule_keyword_group(keyword: object) -> tuple[str, ...]:
    if type(keyword) is not str:
        raise WeaponProfileError("Rule keyword must be a string.")
    keywords: list[str] = []
    seen: set[str] = set()
    for part in keyword.split("/"):
        canonical = _canonical_rule_keyword(part)
        if canonical in seen:
            raise WeaponProfileError("Rule keyword group must not contain duplicates.")
        seen.add(canonical)
        keywords.append(canonical)
    return tuple(keywords)


def _validate_d6_critical_threshold(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise WeaponProfileError(f"{field_name} must be an integer.")
    if value < 2 or value > 6:
        raise WeaponProfileError(f"{field_name} must be between 2 and 6.")
    return value
