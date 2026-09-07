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

if TYPE_CHECKING:
    from warhammer40k_core.core.weapon_profiles import WeaponProfile


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

    if type(profile) is not WeaponProfile or not profile.skill.is_numeric:
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
    skill = ModifierStack(profile.skill.characteristic, profile.skill.raw, modifiers).resolve()
    return replace(
        profile,
        skill=skill,
        skill_modifiers=modifiers,
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
    )
