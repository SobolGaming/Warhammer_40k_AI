"""Individual, source-linked weapon skill operations, retained before final bounds."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.attributes import Characteristic
from warhammer40k_core.core.modifiers import (
    Modifier,
    ModifierOperation,
    ModifierStack,
    ModifierTerm,
)
from warhammer40k_core.core.random_profile_values import RandomProfileValue

if TYPE_CHECKING:
    from warhammer40k_core.core.weapon_profiles import WeaponProfile


def same_weapon_skill_source(left: WeaponProfile, right: WeaponProfile) -> bool:
    """Compare the source before runtime operations without evaluating random skill."""
    if isinstance(left.skill, RandomProfileValue):
        return isinstance(right.skill, RandomProfileValue) and replace(
            left.skill, modifiers=(), evaluation=None, evaluation_id=None
        ) == replace(right.skill, modifiers=(), evaluation=None, evaluation_id=None)
    return not isinstance(right.skill, RandomProfileValue) and (
        left.skill.characteristic == right.skill.characteristic
        and left.skill.raw == right.skill.raw
    )


def validate_weapon_skill_modifiers(profile: WeaponProfile) -> None:
    from warhammer40k_core.core.weapon_profiles import WeaponProfileError

    modifiers = profile.skill_modifiers
    if type(modifiers) is not tuple or any(type(item) is not Modifier for item in modifiers):
        raise WeaponProfileError("Weapon skill modifiers require typed operations.")
    if any(
        item.source_id is None
        or item.scope.characteristics != frozenset({profile.skill.characteristic})
        or item.scope.target_ids is not None
        for item in modifiers
    ):
        raise WeaponProfileError("Weapon skill modifier source or characteristic drift.")
    if isinstance(profile.skill, RandomProfileValue):
        if profile.skill.modifiers != modifiers:
            raise WeaponProfileError("Random weapon skill modifier provenance drift.")
        return
    if modifiers:
        expected = ModifierStack(
            profile.skill.characteristic, profile.skill.raw, modifiers
        ).resolve()
        if expected != profile.skill:
            raise WeaponProfileError("Weapon skill modifier arithmetic or provenance drift.")


def with_weapon_skill_modifier(
    profile: WeaponProfile,
    *,
    modifier_id: str,
    source_id: str,
    delta: int,
) -> WeaponProfile:
    from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfileError

    if type(profile) is not WeaponProfile or (
        not isinstance(profile.skill, RandomProfileValue) and not profile.skill.is_numeric
    ):
        raise WeaponProfileError("Weapon skill operation requires a numeric weapon profile.")
    if profile.skill.characteristic not in {
        Characteristic.BALLISTIC_SKILL,
        Characteristic.WEAPON_SKILL,
    }:
        raise WeaponProfileError("Weapon skill operation requires BS or WS.")
    modifier = ModifierTerm(ModifierOperation.ADD, delta).bind(
        modifier_id=modifier_id, source_id=source_id, characteristic=profile.skill.characteristic
    )
    modifiers = tuple(
        sorted((*profile.skill_modifiers, modifier), key=lambda item: item.modifier_id)
    )
    skill = (
        replace(profile.skill, modifiers=modifiers, evaluation=None, evaluation_id=None)
        if isinstance(profile.skill, RandomProfileValue)
        else ModifierStack(profile.skill.characteristic, profile.skill.raw, modifiers).resolve()
    )
    return replace(
        profile,
        skill=skill,
        skill_modifiers=modifiers,
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )
