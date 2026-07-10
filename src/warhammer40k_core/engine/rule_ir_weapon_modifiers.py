from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import cast

from warhammer40k_core.core.attributes import Characteristic, CharacteristicValue
from warhammer40k_core.core.weapon_profiles import (
    AttackProfile,
    DamageProfile,
    RangeProfileKind,
    WeaponProfile,
)
from warhammer40k_core.engine.phase import GameLifecycleError


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
    *, parameters: Mapping[str, object], profile: WeaponProfile, source_id: str
) -> WeaponProfile:
    if not rule_ir_weapon_selector_applies(parameters=parameters, profile=profile):
        return profile
    characteristic = _characteristic(parameters)
    delta = _int_parameter(parameters, "delta")
    source_ids = _source_ids_with(profile.source_ids, source_id)
    if characteristic is Characteristic.STRENGTH:
        return replace(
            profile,
            strength=_modified_characteristic_value(profile.strength, delta),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.ARMOR_PENETRATION:
        return replace(
            profile,
            armor_penetration=_modified_characteristic_value(profile.armor_penetration, delta),
            source_ids=source_ids,
        )
    if characteristic in {Characteristic.BALLISTIC_SKILL, Characteristic.WEAPON_SKILL}:
        if profile.skill.characteristic is not characteristic:
            return profile
        return replace(
            profile,
            skill=_modified_characteristic_value(profile.skill, delta),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.ATTACKS:
        return replace(
            profile,
            attack_profile=_modified_attack_profile(profile.attack_profile, delta),
            source_ids=source_ids,
        )
    if characteristic is Characteristic.DAMAGE:
        return replace(
            profile,
            damage_profile=_modified_damage_profile(profile.damage_profile, delta),
            source_ids=source_ids,
        )
    raise GameLifecycleError("RuleIR weapon modifier characteristic is unsupported.")


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


def _int_parameter(parameters: Mapping[str, object], key: str) -> int:
    value = parameters.get(key)
    if type(value) is not int:
        raise GameLifecycleError(f"RuleIR weapon modifier {key} must be an integer.")
    return value


def _modified_characteristic_value(value: CharacteristicValue, delta: int) -> CharacteristicValue:
    if type(value) is not CharacteristicValue or not value.is_numeric:
        raise GameLifecycleError("RuleIR weapon modifier requires a numeric characteristic.")
    return CharacteristicValue.from_raw(value.characteristic, value.final + delta)


def _modified_attack_profile(profile: AttackProfile, delta: int) -> AttackProfile:
    if type(profile) is not AttackProfile:
        raise GameLifecycleError("RuleIR Attacks modifier requires AttackProfile.")
    if profile.fixed_attacks is not None:
        return AttackProfile.fixed(max(1, profile.fixed_attacks + delta))
    if profile.dice_expression is None:
        raise GameLifecycleError("AttackProfile requires fixed attacks or dice expression.")
    return AttackProfile.dice(
        replace(profile.dice_expression, modifier=profile.dice_expression.modifier + delta)
    )


def _modified_damage_profile(profile: DamageProfile, delta: int) -> DamageProfile:
    if type(profile) is not DamageProfile:
        raise GameLifecycleError("RuleIR Damage modifier requires DamageProfile.")
    if profile.fixed_damage is not None:
        return DamageProfile.fixed(max(1, profile.fixed_damage + delta))
    if profile.dice_expression is None:
        raise GameLifecycleError("DamageProfile requires fixed damage or dice expression.")
    return DamageProfile.dice(
        replace(profile.dice_expression, modifier=profile.dice_expression.modifier + delta)
    )


def _source_ids_with(source_ids: tuple[str, ...], source_id: str) -> tuple[str, ...]:
    if type(source_id) is not str or not source_id:
        raise GameLifecycleError("RuleIR weapon modifier source_id must be non-empty.")
    if source_id in source_ids:
        return source_ids
    return tuple(sorted((*source_ids, source_id)))
