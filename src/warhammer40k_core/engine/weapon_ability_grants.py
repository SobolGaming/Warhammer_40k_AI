"""Shared structured descriptors for catalog and RuleIR weapon grants."""

from __future__ import annotations

from collections.abc import Mapping

from warhammer40k_core.core.weapon_profiles import AbilityDescriptor, WeaponKeyword
from warhammer40k_core.engine.phase import GameLifecycleError


def weapon_ability_descriptor_for_grant(
    *, parameters: Mapping[str, object], keyword: WeaponKeyword
) -> AbilityDescriptor | None:
    if keyword is WeaponKeyword.LETHAL_HITS:
        return AbilityDescriptor.lethal_hits()
    if keyword is WeaponKeyword.DEVASTATING_WOUNDS:
        return AbilityDescriptor.devastating_wounds()
    if keyword is WeaponKeyword.HEAVY:
        return AbilityDescriptor.heavy()
    if keyword is WeaponKeyword.SUSTAINED_HITS:
        value = parameters.get("weapon_ability_value")
        if type(value) not in {int, str} or (type(value) is int and value < 1):
            raise GameLifecycleError("weapon_ability_value must be positive or D3.")
        if isinstance(value, (int, str)):
            return AbilityDescriptor.sustained_hits(value)
        raise GameLifecycleError("weapon_ability_value is required.")
    if keyword is WeaponKeyword.BLAST and "weapon_ability_value" not in parameters:
        # Bare Blast has its own source-defined one-per-five form (24.05).
        return None
    builders = {
        WeaponKeyword.BLAST: AbilityDescriptor.blast,
        WeaponKeyword.CLEAVE: AbilityDescriptor.cleave,
        WeaponKeyword.MELTA: AbilityDescriptor.melta,
        WeaponKeyword.RAPID_FIRE: AbilityDescriptor.rapid_fire,
    }
    if keyword in builders:
        value = parameters.get("weapon_ability_value")
        if type(value) is not int or value < 1:
            raise GameLifecycleError("weapon_ability_value must be a positive integer.")
        return builders[keyword](value)
    if keyword is WeaponKeyword.HUNTER:
        raise GameLifecycleError("Weapon keyword grant cannot infer Hunter targets.")
    return None
