"""Native profile occurrences and explicit, source-backed weapon ability grants."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import replace
from typing import TYPE_CHECKING

from warhammer40k_core.core.ability_sources import AbilitySourceError, AbilitySourceInstance

if TYPE_CHECKING:
    from warhammer40k_core.core.weapon_profiles import (
        AbilityDescriptor,
        WeaponKeyword,
        WeaponProfile,
    )


def weapon_keyword_ability_id(keyword: WeaponKeyword) -> str:
    return f"weapon-keyword:{keyword.value}"


def weapon_ability_sources(profile: WeaponProfile) -> tuple[AbilitySourceInstance, ...]:
    from warhammer40k_core.core.weapon_profiles import WeaponProfile

    if type(profile) is not WeaponProfile:
        raise AbilitySourceError("Weapon ability sources require a WeaponProfile.")
    # Absence is the native-profile representation, not an unknown source. Explicit
    # grants first snapshot those native occurrences before adding any source.
    if profile.ability_sources:
        return profile.ability_sources
    ids = _native_ability_ids(profile)
    return tuple(
        sorted(
            (
                AbilitySourceInstance(
                    owner_id=profile.stable_identity(),
                    source_id=profile.stable_identity(),
                    source_instance_id=profile.stable_identity(),
                    slot_id=ability_id,
                    ability_id=ability_id,
                )
                for ability_id in ids
            ),
            key=lambda source: source.instance_id,
        )
    )


def _native_ability_ids(profile: WeaponProfile) -> tuple[str, ...]:
    from warhammer40k_core.core.weapon_profiles import AbilityKind, WeaponKeyword

    descriptor_keywords = {
        AbilityKind.DEVASTATING_WOUNDS: WeaponKeyword.DEVASTATING_WOUNDS,
        AbilityKind.SUSTAINED_HITS: WeaponKeyword.SUSTAINED_HITS,
        AbilityKind.LETHAL_HITS: WeaponKeyword.LETHAL_HITS,
        AbilityKind.CLEAVE: WeaponKeyword.CLEAVE,
        AbilityKind.MELTA: WeaponKeyword.MELTA,
        AbilityKind.RAPID_FIRE: WeaponKeyword.RAPID_FIRE,
        AbilityKind.HEAVY: WeaponKeyword.HEAVY,
        AbilityKind.HUNTER: WeaponKeyword.HUNTER,
    }
    described = {
        descriptor_keywords[a.ability_kind]
        for a in profile.abilities
        if a.ability_kind in descriptor_keywords
    }
    return (
        *(ability.ability_id for ability in profile.abilities),
        *(
            weapon_keyword_ability_id(keyword)
            for keyword in profile.keywords
            if keyword not in described
        ),
    )


def validate_weapon_ability_sources(profile: WeaponProfile) -> tuple[AbilitySourceInstance, ...]:
    sources = profile.ability_sources
    if type(sources) is not tuple:
        raise AbilitySourceError("Weapon ability sources must be a tuple.")
    if not sources:
        return sources
    required = set(_native_ability_ids(profile))
    expected = required | {weapon_keyword_ability_id(keyword) for keyword in profile.keywords}
    seen: set[str] = set()
    for source in sources:
        if type(source) is not AbilitySourceInstance:
            raise AbilitySourceError("Weapon ability sources must contain typed instances.")
        if source.owner_id != profile.stable_identity() or source.ability_id not in expected:
            raise AbilitySourceError(
                "Weapon ability source references a different owner or missing ability."
            )
        if (
            source.source_id != profile.stable_identity()
            and source.source_id not in profile.source_ids
        ):
            raise AbilitySourceError("Weapon ability source has no profile provenance.")
        if source.instance_id in seen:
            raise AbilitySourceError("Weapon ability sources must not duplicate an instance ID.")
        seen.add(source.instance_id)
    if not required.issubset({source.ability_id for source in sources}):
        raise AbilitySourceError("Weapon ability sources must cover every profile ability.")
    return tuple(sorted(sources, key=lambda source: source.instance_id))


def preserve_native_keyword_occurrences(
    profile: WeaponProfile, keyword_occurrences: tuple[WeaponKeyword, ...]
) -> WeaponProfile:
    """Retain repeated native keyword slots after catalog keyword canonicalization."""
    counts = Counter(weapon_keyword_ability_id(keyword) for keyword in keyword_occurrences)
    if not any(count > 1 for count in counts.values()):
        return profile
    sources = weapon_ability_sources(profile)
    repeated = tuple(
        replace(source, slot_id=f"{source.slot_id}:source-occurrence:{occurrence}")
        for source in sources
        for occurrence in range(2, counts[source.ability_id] + 1)
    )
    # Descriptor-bearing keywords already have one occurrence per descriptor.
    if not repeated:
        return profile
    return replace(profile, ability_sources=(*sources, *repeated))


def grant_weapon_ability(
    profile: WeaponProfile,
    *,
    keyword: WeaponKeyword,
    ability: AbilityDescriptor | None,
    source_id: str,
    source_instance_id: str,
) -> WeaponProfile:
    from warhammer40k_core.core.weapon_profiles import (
        AbilityDescriptor,
        WeaponKeyword,
        WeaponProfile,
    )

    if type(profile) is not WeaponProfile or type(keyword) is not WeaponKeyword:
        raise AbilitySourceError("Weapon ability grants require a profile and canonical keyword.")
    if ability is not None and type(ability) is not AbilityDescriptor:
        raise AbilitySourceError("Weapon ability grants require a typed descriptor.")
    ability_id = weapon_keyword_ability_id(keyword) if ability is None else ability.ability_id
    source = AbilitySourceInstance(
        owner_id=profile.stable_identity(),
        source_id=source_id,
        source_instance_id=source_instance_id,
        slot_id=weapon_keyword_ability_id(keyword),
        ability_id=ability_id,
    )
    sources = weapon_ability_sources(profile)
    abilities = profile.abilities
    if ability is not None:
        matches = tuple(item for item in abilities if item.ability_id == ability.ability_id)
        if matches and matches != (ability,):
            raise AbilitySourceError("Weapon grant descriptor identity has conflicting semantics.")
        if not matches:
            abilities = (*abilities, ability)
    for existing in sources:
        if existing.instance_id == source.instance_id:
            if existing != source:
                raise AbilitySourceError("Weapon grant source instance changed its ability.")
            return profile
    return replace(
        profile,
        keywords=tuple(sorted({*profile.keywords, keyword}, key=lambda value: value.value)),
        abilities=abilities,
        source_ids=tuple(sorted({*profile.source_ids, source_id})),
        ability_sources=(*sources, source),
    )


def reidentify_weapon_profile(
    profile: WeaponProfile, *, profile_id: str, name: str
) -> WeaponProfile:
    """Move a synthetic attack carrier while retaining its original source occurrences."""
    return replace(
        profile,
        profile_id=profile_id,
        name=name,
        source_ids=tuple(sorted({*profile.source_ids, profile.stable_identity()})),
        ability_sources=tuple(
            replace(source, owner_id=f"weapon-profile:{profile_id}")
            for source in weapon_ability_sources(profile)
        ),
    )


def replace_weapon_ability_descriptors(
    profile: WeaponProfile,
    replacements: Mapping[str, AbilityDescriptor],
) -> WeaponProfile:
    """Change descriptor values without replacing the sources that granted them."""
    from warhammer40k_core.core.weapon_profiles import AbilityDescriptor

    existing = {ability.ability_id: ability for ability in profile.abilities}
    if not set(replacements).issubset(existing):
        raise AbilitySourceError("Weapon descriptor replacement references an unknown ability.")
    updated: dict[str, AbilityDescriptor] = {}
    for old_id, old in existing.items():
        replacement = replacements.get(old_id, old)
        if (
            type(replacement) is not AbilityDescriptor
            or replacement.ability_kind is not old.ability_kind
        ):
            raise AbilitySourceError(
                "Weapon descriptor replacement must retain its ability family."
            )
        if replacement.ability_id in updated and updated[replacement.ability_id] != replacement:
            raise AbilitySourceError("Weapon descriptor replacement has conflicting semantics.")
        updated[replacement.ability_id] = replacement
    return replace(
        profile,
        abilities=tuple(updated.values()),
        ability_sources=tuple(
            replace(source, ability_id=replacements[source.ability_id].ability_id)
            if source.ability_id in replacements
            else source
            for source in weapon_ability_sources(profile)
        ),
    )
