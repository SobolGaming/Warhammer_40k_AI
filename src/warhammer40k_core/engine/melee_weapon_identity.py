"""Resolve a melee declaration to exactly one physical weapon, never a profile copy."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from warhammer40k_core.engine.fight_resolution import _AvailableMeleeWeapon
    from warhammer40k_core.engine.fight_weapon_selection import MeleeWeaponDeclaration


def declared_melee_weapon(
    available: dict[tuple[str, str, str, str], _AvailableMeleeWeapon],
    declaration: MeleeWeaponDeclaration,
) -> _AvailableMeleeWeapon | None:
    matches = [
        weapon
        for key, weapon in available.items()
        if key[:3] == declaration.weapon_key
        and (declaration.weapon_instance_id is None or key[3] == declaration.weapon_instance_id)
    ]
    return matches[0] if len(matches) == 1 else None
