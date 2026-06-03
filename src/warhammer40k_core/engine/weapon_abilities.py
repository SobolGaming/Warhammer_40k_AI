from __future__ import annotations

from enum import StrEnum

from warhammer40k_core.core.weapon_profiles import (
    AbilityKind,
    DevastatingWoundsEffect,
    WeaponKeyword,
    WeaponProfile,
    devastating_wounds_effect_from_token,
)
from warhammer40k_core.engine.phase import GameLifecycleError

ASSAULT_RULE_ID = "weapon-ability:assault"
BLAST_RULE_ID = "weapon-ability:blast"
CLEAVE_RULE_ID = "weapon-ability:cleave"
CLOSE_QUARTERS_RULE_ID = "weapon-ability:close-quarters"
DEVASTATING_WOUNDS_RULE_ID = "weapon-ability:devastating-wounds"
FIRE_OVERWATCH_RULE_ID = "core:fire-overwatch"
HAZARDOUS_RULE_ID = "weapon-ability:hazardous"
HEAVY_RULE_ID = "weapon-ability:heavy"
IGNORES_COVER_RULE_ID = "weapon-ability:ignores-cover"
INDIRECT_FIRE_NO_VISIBLE_RULE_ID = "weapon-ability:indirect-fire:no-visible-target"
INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID = "weapon-ability:indirect-fire:benefit-of-cover"
INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID = "weapon-ability:indirect-fire:no-hit-rerolls"
INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID = (
    "weapon-ability:indirect-fire:stationary-friendly-visible"
)
LETHAL_HITS_RULE_ID = "weapon-ability:lethal-hits"
MELTA_RULE_ID = "weapon-ability:melta"
PRECISION_RULE_ID = "weapon-ability:precision"
RAPID_FIRE_RULE_ID = "weapon-ability:rapid-fire"
SNAP_SHOOTING_RULE_ID = "core:snap-shooting"
SUSTAINED_HITS_RULE_ID = "weapon-ability:sustained-hits"
TORRENT_RULE_ID = "weapon-ability:torrent"
TWIN_LINKED_RULE_ID = "weapon-ability:twin-linked"

_PARAMETERIZED_KEYWORDS_BY_KIND = {
    AbilityKind.CLEAVE: WeaponKeyword.CLEAVE,
    AbilityKind.MELTA: WeaponKeyword.MELTA,
    AbilityKind.RAPID_FIRE: WeaponKeyword.RAPID_FIRE,
    AbilityKind.SUSTAINED_HITS: WeaponKeyword.SUSTAINED_HITS,
}


class DevastatingWoundsResolution(StrEnum):
    MORTAL_WOUNDS = "mortal_wounds"
    NO_SAVES = "no_saves"


def has_weapon_keyword(profile: WeaponProfile, keyword: WeaponKeyword) -> bool:
    _validate_weapon_profile(profile)
    _validate_weapon_keyword(keyword)
    return keyword in profile.keywords


def has_close_quarters_weapon_keyword(profile: WeaponProfile) -> bool:
    _validate_weapon_profile(profile)
    return (
        WeaponKeyword.PISTOL in profile.keywords or WeaponKeyword.CLOSE_QUARTERS in profile.keywords
    )


def weapon_ability_int_value(profile: WeaponProfile, ability_kind: AbilityKind) -> int | None:
    _validate_weapon_profile(profile)
    _validate_ability_kind(ability_kind)
    descriptors = tuple(
        ability for ability in profile.abilities if ability.ability_kind is ability_kind
    )
    if len(descriptors) > 1:
        raise GameLifecycleError("Weapon profile has duplicate ability descriptors.")
    if descriptors:
        value = _ability_parameter_value(profile=profile, ability_kind=ability_kind)
        if type(value) is not int:
            raise GameLifecycleError("Weapon ability value parameter must be an integer.")
        if value < 1:
            raise GameLifecycleError("Weapon ability value parameter must be positive.")
        return value
    expected_keyword = _PARAMETERIZED_KEYWORDS_BY_KIND.get(ability_kind)
    if expected_keyword is not None and expected_keyword in profile.keywords:
        raise GameLifecycleError(
            f"{expected_keyword.value} requires a structured ability descriptor."
        )
    return None


def anti_keyword_critical_threshold(
    *,
    profile: WeaponProfile,
    target_keywords: tuple[str, ...],
) -> int | None:
    _validate_weapon_profile(profile)
    target_keyword_set = {_canonical_keyword(keyword) for keyword in target_keywords}
    matching_thresholds: list[int] = []
    for ability in profile.abilities:
        if ability.ability_kind is not AbilityKind.ANTI_KEYWORD:
            continue
        keyword = _ability_parameter_by_name(
            profile=profile,
            ability_kind=AbilityKind.ANTI_KEYWORD,
            parameter_name="keyword",
            ability_id=ability.ability_id,
        )
        threshold = _ability_parameter_by_name(
            profile=profile,
            ability_kind=AbilityKind.ANTI_KEYWORD,
            parameter_name="threshold",
            ability_id=ability.ability_id,
        )
        if type(keyword) is not str:
            raise GameLifecycleError("Anti ability keyword parameter must be a string.")
        if type(threshold) is not int:
            raise GameLifecycleError("Anti ability threshold parameter must be an integer.")
        if _canonical_keyword(keyword) in target_keyword_set:
            matching_thresholds.append(threshold)
    if not matching_thresholds:
        return None
    return min(matching_thresholds)


def devastating_wounds_resolution(profile: WeaponProfile) -> DevastatingWoundsResolution | None:
    _validate_weapon_profile(profile)
    descriptors = tuple(
        ability
        for ability in profile.abilities
        if ability.ability_kind is AbilityKind.DEVASTATING_WOUNDS
    )
    if len(descriptors) > 1:
        raise GameLifecycleError("Weapon profile has duplicate Devastating Wounds descriptors.")
    if WeaponKeyword.DEVASTATING_WOUNDS not in profile.keywords:
        if descriptors:
            raise GameLifecycleError("Devastating Wounds descriptor requires the weapon keyword.")
        return None
    if not descriptors:
        raise GameLifecycleError("Devastating Wounds requires a structured ability descriptor.")
    descriptor = descriptors[0]
    if len(descriptor.parameters) != 1 or descriptor.parameters[0].name != "effect":
        raise GameLifecycleError("Devastating Wounds descriptor requires one effect parameter.")
    effect = devastating_wounds_effect_from_token(descriptor.parameters[0].value)
    if effect is DevastatingWoundsEffect.MORTAL_WOUNDS:
        return DevastatingWoundsResolution.MORTAL_WOUNDS
    if effect is DevastatingWoundsEffect.NO_SAVES:
        return DevastatingWoundsResolution.NO_SAVES
    raise GameLifecycleError("Unsupported Devastating Wounds effect.")


def rapid_fire_attack_bonus(profile: WeaponProfile, *, target_within_half_range: bool) -> int:
    value = weapon_ability_int_value(profile, AbilityKind.RAPID_FIRE)
    if value is None or not target_within_half_range:
        return 0
    return value


def blast_attack_bonus(*, target_model_count: int) -> int:
    if type(target_model_count) is not int:
        raise GameLifecycleError("Blast target_model_count must be an integer.")
    if target_model_count < 0:
        raise GameLifecycleError("Blast target_model_count must not be negative.")
    return target_model_count // 5


def cleave_attack_bonus(
    profile: WeaponProfile, *, single_target: bool, target_model_count: int
) -> int:
    value = weapon_ability_int_value(profile, AbilityKind.CLEAVE)
    if value is None or not single_target:
        return 0
    if type(target_model_count) is not int:
        raise GameLifecycleError("Cleave target_model_count must be an integer.")
    if target_model_count < 0:
        raise GameLifecycleError("Cleave target_model_count must not be negative.")
    return value * (target_model_count // 5)


def melta_damage_bonus(profile: WeaponProfile, *, target_within_half_range: bool) -> int:
    value = weapon_ability_int_value(profile, AbilityKind.MELTA)
    if value is None or not target_within_half_range:
        return 0
    return value


def sustained_hits_generated_hits(profile: WeaponProfile, *, critical_hit: bool) -> int:
    value = weapon_ability_int_value(profile, AbilityKind.SUSTAINED_HITS)
    if value is None or not critical_hit:
        return 1
    return 1 + value


def rapid_fire_rule_id(value: int) -> str:
    return f"{RAPID_FIRE_RULE_ID}:{_validate_positive_int('Rapid Fire value', value)}"


def blast_rule_id(value: int) -> str:
    return f"{BLAST_RULE_ID}:{_validate_positive_int('Blast value', value)}"


def cleave_rule_id(value: int) -> str:
    return f"{CLEAVE_RULE_ID}:{_validate_positive_int('Cleave value', value)}"


def melta_rule_id(value: int) -> str:
    return f"{MELTA_RULE_ID}:{_validate_positive_int('Melta value', value)}"


def heavy_rule_id() -> str:
    return HEAVY_RULE_ID


def _ability_parameter_value(
    *,
    profile: WeaponProfile,
    ability_kind: AbilityKind,
) -> object:
    descriptors = tuple(
        ability for ability in profile.abilities if ability.ability_kind is ability_kind
    )
    if len(descriptors) != 1:
        raise GameLifecycleError("Weapon ability lookup requires exactly one descriptor.")
    descriptor = descriptors[0]
    if len(descriptor.parameters) != 1 or descriptor.parameters[0].name != "value":
        raise GameLifecycleError("Parameterized weapon ability requires one value parameter.")
    return descriptor.parameters[0].value


def _ability_parameter_by_name(
    *,
    profile: WeaponProfile,
    ability_kind: AbilityKind,
    parameter_name: str,
    ability_id: str,
) -> object:
    matching = tuple(
        ability
        for ability in profile.abilities
        if ability.ability_kind is ability_kind and ability.ability_id == ability_id
    )
    if len(matching) != 1:
        raise GameLifecycleError("Weapon ability parameter lookup requires one descriptor.")
    for parameter in matching[0].parameters:
        if parameter.name == parameter_name:
            return parameter.value
    raise GameLifecycleError("Weapon ability descriptor is missing a required parameter.")


def _canonical_keyword(keyword: str) -> str:
    if type(keyword) is not str:
        raise GameLifecycleError("Weapon ability keyword must be a string.")
    stripped = keyword.strip()
    if not stripped:
        raise GameLifecycleError("Weapon ability keyword must not be empty.")
    return stripped.upper().replace(" ", "_").replace("-", "_")


def _validate_weapon_profile(profile: object) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("Weapon ability helpers require a WeaponProfile.")
    return profile


def _validate_weapon_keyword(keyword: object) -> WeaponKeyword:
    if type(keyword) is not WeaponKeyword:
        raise GameLifecycleError("Weapon ability helpers require WeaponKeyword values.")
    return keyword


def _validate_ability_kind(kind: object) -> AbilityKind:
    if type(kind) is not AbilityKind:
        raise GameLifecycleError("Weapon ability helpers require AbilityKind values.")
    return kind


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
