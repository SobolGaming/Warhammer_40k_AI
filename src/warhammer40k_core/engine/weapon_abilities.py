from __future__ import annotations

from enum import StrEnum
from typing import cast

from warhammer40k_core.core.keyword_membership import keyword_inventory_contains
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    TARGET_KEYWORD_MATCH_MODE_PARAMETER,
    AbilityDescriptor,
    AbilityKind,
    AntiKeywordMatchMode,
    DevastatingWoundsEffect,
    TargetKeywordMatchMode,
    WeaponKeyword,
    WeaponProfile,
    anti_keyword_match_mode_from_token,
    devastating_wounds_effect_from_token,
    target_keyword_match_mode_from_token,
)
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    core_indirect_shooting_2026_09 as indirect_shooting_source,
)

ASSAULT_RULE_ID = "weapon-ability:assault"
BLAST_RULE_ID = "weapon-ability:blast"
CLEAVE_RULE_ID = "weapon-ability:cleave"
CLOSE_QUARTERS_RULE_ID = "weapon-ability:close-quarters"
DEVASTATING_WOUNDS_RULE_ID = "weapon-ability:devastating-wounds"
FIRE_OVERWATCH_RULE_ID = "core:fire-overwatch"
HAZARDOUS_RULE_ID = "gw-11e-core-abilities:core:hazardous"
HEAVY_RULE_ID = "weapon-ability:heavy"
HUNTER_RULE_ID = "weapon-ability:hunter"
IGNORES_COVER_RULE_ID = "weapon-ability:ignores-cover"
INDIRECT_SHOOTING_POLICY = indirect_shooting_source.ATTACK_POLICY
INDIRECT_FIRE_NO_VISIBLE_RULE_ID = INDIRECT_SHOOTING_POLICY.no_visible_rule_id
INDIRECT_FIRE_BENEFIT_OF_COVER_RULE_ID = INDIRECT_SHOOTING_POLICY.cover_rule_id
INDIRECT_FIRE_NO_HIT_REROLLS_RULE_ID = INDIRECT_SHOOTING_POLICY.no_hit_rerolls_rule_id
INDIRECT_FIRE_STATIONARY_VISIBLE_RULE_ID = INDIRECT_SHOOTING_POLICY.stationary_visible_rule_id
LANCE_RULE_ID = "weapon-ability:lance"
LETHAL_HITS_RULE_ID = "weapon-ability:lethal-hits"
MELTA_RULE_ID = "weapon-ability:melta"
ONE_SHOT_RULE_ID = "weapon-ability:one-shot"
PRECISION_RULE_ID = "weapon-ability:precision"
PSYCHIC_RULE_ID = "weapon-ability:psychic"
RAPID_FIRE_RULE_ID = "weapon-ability:rapid-fire"
SNAP_SHOOTING_RULE_ID = "core:snap-shooting"
SUSTAINED_HITS_RULE_ID = "weapon-ability:sustained-hits"
TORRENT_RULE_ID = "weapon-ability:torrent"
TWIN_LINKED_RULE_ID = "weapon-ability:twin-linked"
WEAPON_ABILITY_SELECTION_DECISION_TYPE = "select_weapon_ability_instance"
SUSTAINED_HITS_D3_VALUE = "D3"

_PARAMETERIZED_KEYWORDS_BY_KIND = {
    AbilityKind.BLAST: WeaponKeyword.BLAST,
    AbilityKind.CLEAVE: WeaponKeyword.CLEAVE,
    AbilityKind.MELTA: WeaponKeyword.MELTA,
    AbilityKind.RAPID_FIRE: WeaponKeyword.RAPID_FIRE,
    AbilityKind.SUSTAINED_HITS: WeaponKeyword.SUSTAINED_HITS,
}
_ABILITY_KEYWORDS_BY_KIND = {
    **_PARAMETERIZED_KEYWORDS_BY_KIND,
    AbilityKind.LETHAL_HITS: WeaponKeyword.LETHAL_HITS,
    AbilityKind.HUNTER: WeaponKeyword.HUNTER,
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


def is_psychic_weapon_profile(profile: WeaponProfile) -> bool:
    return has_weapon_keyword(profile, WeaponKeyword.PSYCHIC)


def weapon_ability_int_value(
    profile: WeaponProfile,
    ability_kind: AbilityKind,
    *,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> int | None:
    value = weapon_ability_value(
        profile,
        ability_kind,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    if value is None:
        return None
    if type(value) is not int:
        raise GameLifecycleError("Weapon ability value parameter must be an integer.")
    if value < 1:
        raise GameLifecycleError("Weapon ability value parameter must be positive.")
    return value


def weapon_ability_value(
    profile: WeaponProfile,
    ability_kind: AbilityKind,
    *,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> int | str | None:
    _validate_weapon_profile(profile)
    _validate_ability_kind(ability_kind)
    _target_keyword_set(target_keywords)
    descriptors = _ability_descriptors(profile, ability_kind)
    expected_keyword = _ABILITY_KEYWORDS_BY_KIND.get(ability_kind)
    if descriptors and expected_keyword is not None and expected_keyword not in profile.keywords:
        raise GameLifecycleError(
            f"{expected_keyword.value} descriptor requires the weapon keyword."
        )
    matching_descriptors = _matching_ability_descriptors(
        profile,
        ability_kind,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    descriptor = matching_descriptors[0] if matching_descriptors else None
    if descriptor is not None:
        value = _ability_parameter_value(descriptor)
        if type(value) is int or type(value) is str:
            return value
        raise GameLifecycleError("Weapon ability value parameter must be an integer or string.")
    if descriptors:
        return None
    if ability_kind is AbilityKind.BLAST and WeaponKeyword.BLAST in profile.keywords:
        # Core 24.05 explicitly defines bare Blast as one die per five models.
        return 1
    if expected_keyword is not None and expected_keyword in profile.keywords:
        raise GameLifecycleError(
            f"{expected_keyword.value} requires a structured ability descriptor."
        )
    return None


def weapon_ability_applies(
    profile: WeaponProfile,
    ability_kind: AbilityKind,
    *,
    target_keywords: tuple[str, ...],
    name_keywords: tuple[str, ...] = (),
) -> bool:
    _validate_weapon_profile(profile)
    _validate_ability_kind(ability_kind)
    _target_keyword_set(target_keywords)
    descriptors = _ability_descriptors(profile, ability_kind)
    expected_keyword = _ABILITY_KEYWORDS_BY_KIND.get(ability_kind)
    if descriptors and expected_keyword is not None and expected_keyword not in profile.keywords:
        raise GameLifecycleError(
            f"{expected_keyword.value} descriptor requires the weapon keyword."
        )
    if descriptors:
        return any(
            _target_keyword_gate_matches_descriptor(
                descriptor,
                target_keywords=target_keywords,
                name_keywords=name_keywords,
            )
            for descriptor in descriptors
        )
    if expected_keyword is not None and expected_keyword in profile.keywords:
        if ability_kind is AbilityKind.BLAST:
            return True
        raise GameLifecycleError(
            f"{expected_keyword.value} requires a structured ability descriptor."
        )
    return False


def lethal_hits_applies(
    profile: WeaponProfile, *, target_keywords: tuple[str, ...], name_keywords: tuple[str, ...] = ()
) -> bool:
    return weapon_ability_applies(
        profile,
        AbilityKind.LETHAL_HITS,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )


def hunter_target_allowed(
    profile: WeaponProfile, *, target_keywords: tuple[str, ...], name_keywords: tuple[str, ...] = ()
) -> bool:
    _validate_weapon_profile(profile)
    _target_keyword_set(target_keywords)
    descriptors = tuple(
        ability for ability in profile.abilities if ability.ability_kind is AbilityKind.HUNTER
    )
    if descriptors and WeaponKeyword.HUNTER not in profile.keywords:
        raise GameLifecycleError("Hunter descriptor requires the weapon keyword.")
    if not descriptors:
        if WeaponKeyword.HUNTER in profile.keywords:
            raise GameLifecycleError("Hunter requires a structured ability descriptor.")
        return True
    return any(
        _target_keyword_gate_matches_descriptor(
            descriptor,
            target_keywords=target_keywords,
            name_keywords=name_keywords,
        )
        for descriptor in descriptors
    )


def hunter_targeting_rule_ids(
    profile: WeaponProfile,
    *,
    target_keywords: tuple[str, ...],
    name_keywords: tuple[str, ...] = (),
) -> tuple[str, ...]:
    if hunter_target_allowed(profile, target_keywords=target_keywords, name_keywords=name_keywords):
        if any(ability.ability_kind is AbilityKind.HUNTER for ability in profile.abilities):
            return (HUNTER_RULE_ID,)
        return ()
    return ()


def anti_keyword_critical_threshold(
    *,
    profile: WeaponProfile,
    target_keywords: tuple[str, ...],
    name_keywords: tuple[str, ...] = (),
) -> int | None:
    _validate_weapon_profile(profile)
    _target_keyword_set(target_keywords)
    matching_descriptors = list(
        _matching_ability_descriptors(
            profile,
            AbilityKind.ANTI_KEYWORD,
            target_keywords=target_keywords,
            name_keywords=name_keywords,
        )
    )
    if not matching_descriptors:
        return None
    selected_descriptor = matching_descriptors[0]
    threshold = _ability_parameter_by_name_from_descriptor(
        descriptor=selected_descriptor,
        parameter_name="threshold",
    )
    if type(threshold) is not int:
        raise GameLifecycleError("Anti ability threshold parameter must be an integer.")
    return threshold


def devastating_wounds_resolution(
    profile: WeaponProfile,
    *,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> DevastatingWoundsResolution | None:
    _validate_weapon_profile(profile)
    _target_keyword_set(target_keywords)
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
    matching_descriptors = _matching_ability_descriptors(
        profile,
        AbilityKind.DEVASTATING_WOUNDS,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    if not matching_descriptors:
        return None
    descriptor = matching_descriptors[0]
    effect = _ability_parameter_by_name_from_descriptor(
        descriptor=descriptor,
        parameter_name="effect",
    )
    if type(effect) is not str:
        raise GameLifecycleError("Devastating Wounds descriptor requires one effect parameter.")
    resolved_effect = devastating_wounds_effect_from_token(effect)
    if resolved_effect is DevastatingWoundsEffect.MORTAL_WOUNDS:
        return DevastatingWoundsResolution.MORTAL_WOUNDS
    if resolved_effect is DevastatingWoundsEffect.NO_SAVES:
        return DevastatingWoundsResolution.NO_SAVES
    raise GameLifecycleError("Unsupported Devastating Wounds effect.")


def rapid_fire_attack_bonus(
    profile: WeaponProfile,
    *,
    target_within_half_range: bool,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> int:
    value = weapon_ability_int_value(
        profile,
        AbilityKind.RAPID_FIRE,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    if value is None or not target_within_half_range:
        return 0
    return value


def blast_attack_bonus(*, target_model_count: int, blast_value: int = 1) -> int:
    return _attack_bonus_per_five(
        value=blast_value, target_model_count=target_model_count, ability_label="Blast"
    )


def blast_attack_bonus_for_profile(
    profile: WeaponProfile,
    *,
    target_model_count: int,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> int:
    value = weapon_ability_int_value(
        profile, AbilityKind.BLAST, target_keywords=target_keywords, name_keywords=name_keywords
    )
    if value is None:
        return 0
    return blast_attack_bonus(target_model_count=target_model_count, blast_value=value)


def cleave_attack_bonus(
    profile: WeaponProfile,
    *,
    single_target: bool,
    target_model_count: int,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> int:
    value = weapon_ability_int_value(
        profile,
        AbilityKind.CLEAVE,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    if value is None or not single_target:
        return 0
    return _attack_bonus_per_five(
        value=value, target_model_count=target_model_count, ability_label="Cleave"
    )


def _attack_bonus_per_five(*, value: int, target_model_count: int, ability_label: str) -> int:
    if type(target_model_count) is not int:
        raise GameLifecycleError(f"{ability_label} target_model_count must be an integer.")
    if target_model_count < 0:
        raise GameLifecycleError(f"{ability_label} target_model_count must not be negative.")
    return _validate_positive_int(f"{ability_label} value", value) * (target_model_count // 5)


def melta_damage_bonus(
    profile: WeaponProfile,
    *,
    target_within_half_range: bool,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
) -> int:
    value = weapon_ability_int_value(
        profile,
        AbilityKind.MELTA,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    if value is None or not target_within_half_range:
        return 0
    return value


def sustained_hits_generated_hits(
    profile: WeaponProfile,
    *,
    critical_hit: bool,
    target_keywords: tuple[str, ...] = (),
    name_keywords: tuple[str, ...] = (),
    d3_value: int | None = None,
) -> int:
    value = weapon_ability_value(
        profile,
        AbilityKind.SUSTAINED_HITS,
        target_keywords=target_keywords,
        name_keywords=name_keywords,
    )
    if value is None or not critical_hit:
        return 1
    if value == SUSTAINED_HITS_D3_VALUE:
        if d3_value is None:
            raise GameLifecycleError("Sustained Hits D3 requires a resolved D3 value.")
        return 1 + _validate_positive_int("Sustained Hits D3 value", d3_value)
    if type(value) is not int:
        raise GameLifecycleError("Sustained Hits value parameter must be an integer or D3.")
    if value < 1:
        raise GameLifecycleError("Sustained Hits value parameter must be positive.")
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


def _ability_parameter_value(descriptor: AbilityDescriptor) -> object:
    if type(descriptor) is not AbilityDescriptor:
        raise GameLifecycleError("Weapon ability lookup requires an ability descriptor.")
    value_parameters = tuple(
        parameter for parameter in descriptor.parameters if parameter.name == "value"
    )
    if len(value_parameters) != 1:
        raise GameLifecycleError("Parameterized weapon ability requires one value parameter.")
    return value_parameters[0].value


def _ability_descriptors(
    profile: WeaponProfile,
    ability_kind: AbilityKind,
) -> tuple[AbilityDescriptor, ...]:
    from warhammer40k_core.engine.ability_instance_selection import weapon_instance_groups

    descriptors = tuple(
        ability for ability in profile.abilities if ability.ability_kind is ability_kind
    )
    ability_ids = {descriptor.ability_id for descriptor in descriptors}
    if any(
        len(sources) > 1
        and (
            any(source.ability_id in ability_ids for source in sources)
            or (
                ability_kind is AbilityKind.BLAST
                and family == f"weapon-keyword:{WeaponKeyword.BLAST.value}"
            )
        )
        for family, sources in weapon_instance_groups(profile)
    ):
        raise GameLifecycleError("Weapon ability requires controlling-player selection.")
    return descriptors


def _matching_ability_descriptors(
    profile: WeaponProfile,
    ability_kind: AbilityKind,
    *,
    target_keywords: tuple[str, ...],
    name_keywords: tuple[str, ...] = (),
) -> tuple[AbilityDescriptor, ...]:
    if ability_kind is AbilityKind.ANTI_KEYWORD:
        _target_keyword_set(target_keywords)
        return tuple(
            descriptor
            for descriptor in _ability_descriptors(profile, ability_kind)
            if _target_keyword_gate_matches_descriptor(
                descriptor,
                target_keywords=target_keywords,
                name_keywords=name_keywords,
            )
            and _anti_keyword_descriptor_matches(
                descriptor=descriptor,
                target_keywords=target_keywords,
                name_keywords=name_keywords,
            )
        )
    return tuple(
        descriptor
        for descriptor in _ability_descriptors(profile, ability_kind)
        if _target_keyword_gate_matches_descriptor(
            descriptor,
            target_keywords=target_keywords,
            name_keywords=name_keywords,
        )
    )


def _ability_parameter_by_name_from_descriptor(
    *,
    descriptor: AbilityDescriptor,
    parameter_name: str,
) -> object:
    if type(descriptor) is not AbilityDescriptor:
        raise GameLifecycleError("Weapon ability parameter lookup requires one descriptor.")
    requested_name = _validate_identifier("parameter_name", parameter_name)
    for parameter in descriptor.parameters:
        if parameter.name == requested_name:
            return parameter.value
    raise GameLifecycleError("Weapon ability descriptor is missing a required parameter.")


def _optional_ability_parameter_by_name_from_descriptor(
    *,
    descriptor: AbilityDescriptor,
    parameter_name: str,
) -> object | None:
    if type(descriptor) is not AbilityDescriptor:
        raise GameLifecycleError("Weapon ability parameter lookup requires one descriptor.")
    requested_name = _validate_identifier("parameter_name", parameter_name)
    for parameter in descriptor.parameters:
        if parameter.name == requested_name:
            return parameter.value
    return None


def _anti_keyword_descriptor_matches(
    *,
    descriptor: AbilityDescriptor,
    target_keywords: tuple[str, ...],
    name_keywords: tuple[str, ...] = (),
) -> bool:
    if descriptor.ability_kind is not AbilityKind.ANTI_KEYWORD:
        raise GameLifecycleError("Anti keyword matching requires an Anti descriptor.")
    has_matching_keyword = any(
        keyword_inventory_contains(
            keywords=target_keywords,
            keyword=keyword,
            name_keywords=name_keywords,
            normalizer=_canonical_keyword,
        )
        for keyword in _anti_keyword_descriptor_keywords(descriptor)
    )
    match_mode = _anti_keyword_descriptor_match_mode(descriptor)
    if match_mode is AntiKeywordMatchMode.HAS_KEYWORD:
        return has_matching_keyword
    if match_mode is AntiKeywordMatchMode.MISSING_KEYWORD:
        return not has_matching_keyword
    raise GameLifecycleError("Unsupported Anti keyword match mode.")


def _anti_keyword_descriptor_keywords(descriptor: AbilityDescriptor) -> tuple[str, ...]:
    keyword = _ability_parameter_by_name_from_descriptor(
        descriptor=descriptor,
        parameter_name="keyword",
    )
    if type(keyword) is not str:
        raise GameLifecycleError("Anti ability keyword parameter must be a string.")
    keywords: list[str] = []
    seen: set[str] = set()
    parts = (
        (keyword,)
        if keyword.strip().upper() in descriptor.native_keyword_selectors
        else keyword.split("/")
    )
    for part in parts:
        native = part.strip().upper()
        canonical = (
            native if native in descriptor.native_keyword_selectors else _canonical_keyword(part)
        )
        if canonical in seen:
            raise GameLifecycleError("Anti ability keyword parameter must not duplicate keywords.")
        seen.add(canonical)
        keywords.append(part.strip().upper())
    return tuple(keywords)


def _anti_keyword_descriptor_match_mode(descriptor: AbilityDescriptor) -> AntiKeywordMatchMode:
    mode = _optional_ability_parameter_by_name_from_descriptor(
        descriptor=descriptor,
        parameter_name="match_mode",
    )
    if mode is None:
        return AntiKeywordMatchMode.HAS_KEYWORD
    return anti_keyword_match_mode_from_token(mode)


def _target_keyword_gate_matches_descriptor(
    descriptor: AbilityDescriptor,
    *,
    target_keywords: tuple[str, ...],
    name_keywords: tuple[str, ...] = (),
) -> bool:
    if type(descriptor) is not AbilityDescriptor:
        raise GameLifecycleError("Weapon ability target gate requires an ability descriptor.")
    gate_keywords = descriptor.target_keywords
    validated_gate_keywords = _validate_target_keyword_tuple(
        "Weapon ability target keyword gate",
        gate_keywords,
    )
    if not validated_gate_keywords:
        return True
    has_matching_keyword = any(
        keyword_inventory_contains(
            keywords=target_keywords,
            keyword=keyword,
            name_keywords=name_keywords,
            normalizer=_canonical_keyword,
        )
        for keyword in gate_keywords
    )
    match_mode = _target_keyword_match_mode_from_descriptor(descriptor)
    if match_mode is TargetKeywordMatchMode.HAS_KEYWORD:
        return has_matching_keyword
    if match_mode is TargetKeywordMatchMode.MISSING_KEYWORD:
        return not has_matching_keyword
    raise GameLifecycleError("Unsupported target keyword match mode.")


def _target_keyword_match_mode_from_descriptor(
    descriptor: AbilityDescriptor,
) -> TargetKeywordMatchMode:
    mode = _optional_ability_parameter_by_name_from_descriptor(
        descriptor=descriptor,
        parameter_name=TARGET_KEYWORD_MATCH_MODE_PARAMETER,
    )
    if mode is None:
        return TargetKeywordMatchMode.HAS_KEYWORD
    return target_keyword_match_mode_from_token(mode)


def _target_keyword_set(target_keywords: tuple[str, ...]) -> frozenset[str]:
    return frozenset(
        _validate_target_keyword_tuple("Weapon ability target keywords", target_keywords)
    )


def _validate_target_keyword_tuple(field_name: str, keywords: object) -> tuple[str, ...]:
    if type(keywords) is not tuple:
        raise GameLifecycleError(f"{field_name} must be a tuple.")
    return tuple(_canonical_keyword(keyword) for keyword in cast(tuple[object, ...], keywords))


def _canonical_keyword(keyword: object) -> str:
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


_validate_identifier = IdentifierValidator(GameLifecycleError)


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise GameLifecycleError(f"{field_name} must be an integer.")
    if value < 1:
        raise GameLifecycleError(f"{field_name} must be at least 1.")
    return value
