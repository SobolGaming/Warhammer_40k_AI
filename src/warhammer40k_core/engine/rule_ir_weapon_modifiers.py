from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import (
    Characteristic,
)
from warhammer40k_core.core.modifiers import ModifierOperation, ModifierTerm
from warhammer40k_core.core.weapon_ability_sources import grant_weapon_ability
from warhammer40k_core.core.weapon_profiles import (
    AbilityDescriptor,
    RangeProfileKind,
    WeaponKeyword,
    WeaponProfile,
    WeaponProfileError,
    weapon_keyword_from_token,
)
from warhammer40k_core.core.weapon_skill_modifiers import with_weapon_skill_modifier
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.profile_modifiers import profile_with_delta, range_with_delta


def rule_ir_weapon_selector_applies(
    *, parameters: Mapping[str, object], profile: WeaponProfile
) -> bool:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("RuleIR weapon selector requires WeaponProfile.")
    scope = parameters.get("weapon_scope")
    if scope is not None:
        if type(scope) is not str:
            raise GameLifecycleError("RuleIR weapon_scope must be a string.")
        if scope == "melee" and profile.range_profile.kind is not RangeProfileKind.MELEE:
            return False
        if scope == "ranged" and profile.range_profile.kind is not RangeProfileKind.DISTANCE:
            return False
        if scope not in {"all", "melee", "ranged"}:
            raise GameLifecycleError("Unsupported RuleIR weapon_scope.")
    names = _weapon_names(parameters)
    return not names or _weapon_name_token(profile.name) in names


def rule_ir_modified_weapon_profile(
    *, parameters: Mapping[str, object], profile: WeaponProfile, source_id: str, modifier_id: str
) -> WeaponProfile:
    if not rule_ir_weapon_selector_applies(parameters=parameters, profile=profile):
        return profile
    characteristic = _characteristic(parameters)
    delta = _int_parameter(parameters, "delta")
    source_ids = _source_ids_with(profile.source_ids, source_id)
    if characteristic is Characteristic.STRENGTH:
        return replace(
            profile,
            strength=profile_with_delta(
                profile.strength,
                delta,
                source_id=source_id,
                modifier_id=modifier_id,
                bound_numeric=True,
            ),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.ARMOR_PENETRATION:
        return replace(
            profile,
            armor_penetration=profile_with_delta(
                profile.armor_penetration,
                delta,
                source_id=source_id,
                modifier_id=modifier_id,
                bound_numeric=True,
            ),
            source_ids=source_ids,
        )
    if characteristic in {Characteristic.BALLISTIC_SKILL, Characteristic.WEAPON_SKILL}:
        if profile.skill.characteristic is not characteristic:
            return profile
        return with_weapon_skill_modifier(
            profile, modifier_id=modifier_id, source_id=source_id, delta=delta
        )
    if characteristic is Characteristic.RANGE:
        if profile.range_profile.kind is not RangeProfileKind.DISTANCE:
            return profile
        return replace(
            profile,
            range_profile=range_with_delta(
                profile.range_profile,
                delta,
                source_id=source_id,
                modifier_id=modifier_id,
                target_id=profile.profile_id,
            ),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.ATTACKS:
        return replace(
            profile,
            attack_profile=profile.attack_profile.with_modifier(
                ModifierTerm(ModifierOperation.ADD, delta).bind(
                    modifier_id=modifier_id, source_id=source_id, characteristic=characteristic
                )
            ),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.DAMAGE:
        return replace(
            profile,
            damage_profile=profile.damage_profile.with_modifier(
                ModifierTerm(ModifierOperation.ADD, delta).bind(
                    modifier_id=modifier_id, source_id=source_id, characteristic=characteristic
                )
            ),
            source_ids=source_ids,
        )
    raise GameLifecycleError("RuleIR weapon modifier characteristic is unsupported.")


def rule_ir_weapon_ability_granted_profile(
    *,
    parameters: Mapping[str, object],
    profile: WeaponProfile,
    source_id: str,
    source_instance_id: str,
) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise GameLifecycleError("RuleIR weapon ability grant requires WeaponProfile.")
    if not rule_ir_weapon_selector_applies(parameters=parameters, profile=profile):
        return profile
    keyword = _weapon_keyword_parameter(parameters)
    ability = _weapon_ability_descriptor(parameters, keyword=keyword)
    return grant_weapon_ability(
        profile,
        keyword=keyword,
        ability=ability,
        source_id=source_id,
        source_instance_id=source_instance_id,
    )


def _weapon_names(parameters: Mapping[str, object]) -> frozenset[str]:
    single_name = parameters.get("weapon_name")
    raw_names = parameters.get("weapon_names")
    if single_name is not None and raw_names is not None:
        raise GameLifecycleError("RuleIR weapon selector cannot define both weapon name forms.")
    if single_name is not None:
        if type(single_name) is not str or not single_name.strip():
            raise GameLifecycleError("RuleIR weapon_name must be a non-empty string.")
        return frozenset((_weapon_name_token(single_name),))
    if raw_names is None:
        return frozenset()
    if not isinstance(raw_names, list | tuple) or not raw_names:
        raise GameLifecycleError("RuleIR weapon_names must be a non-empty string sequence.")
    names: set[str] = set()
    for value in cast(list[object] | tuple[object, ...], raw_names):
        if type(value) is not str or not value.strip():
            raise GameLifecycleError("RuleIR weapon_names must contain non-empty strings.")
        names.add(_weapon_name_token(value))
    return frozenset(names)


def _weapon_name_token(value: str) -> str:
    return " ".join(value.casefold().split())


def _characteristic(parameters: Mapping[str, object]) -> Characteristic:
    value = parameters.get("characteristic")
    if type(value) is not str:
        raise GameLifecycleError("RuleIR weapon modifier characteristic must be a string.")
    try:
        return Characteristic(value)
    except ValueError as exc:
        raise GameLifecycleError("RuleIR weapon modifier characteristic is invalid.") from exc


def _weapon_keyword_parameter(parameters: Mapping[str, object]) -> WeaponKeyword:
    value = _required_string_parameter(parameters, "weapon_ability")
    try:
        return weapon_keyword_from_token(value)
    except WeaponProfileError as exc:
        raise GameLifecycleError("RuleIR weapon ability grant has unsupported keyword.") from exc


def _weapon_ability_descriptor(
    parameters: Mapping[str, object],
    *,
    keyword: WeaponKeyword,
) -> AbilityDescriptor | None:
    from warhammer40k_core.engine.weapon_ability_grants import weapon_ability_descriptor_for_grant

    return weapon_ability_descriptor_for_grant(parameters=parameters, keyword=keyword)


def _int_parameter(parameters: Mapping[str, object], key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"RuleIR weapon modifier {key} must be an integer.")
    return value


def _required_string_parameter(parameters: Mapping[str, object], key: str) -> str:
    value = parameters.get(key)
    if type(value) is not str or not value.strip():
        raise GameLifecycleError(f"RuleIR weapon modifier {key} must be a string.")
    return value


def _source_ids_with(source_ids: tuple[str, ...], source_id: str) -> tuple[str, ...]:
    if type(source_id) is not str or not source_id:
        raise GameLifecycleError("RuleIR weapon modifier source_id must be non-empty.")
    if source_id in source_ids:
        return source_ids
    return tuple(sorted((*source_ids, source_id)))
