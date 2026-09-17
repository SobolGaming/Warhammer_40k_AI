"""Source-instance choices shared by every Select Weapons consumer (24.02)."""

from __future__ import annotations

from dataclasses import replace

from warhammer40k_core.core.ability_sources import AbilitySourceInstance
from warhammer40k_core.core.weapon_ability_sources import (
    weapon_ability_sources,
    weapon_keyword_ability_id,
    weapon_keyword_for_ability_kind,
)
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.phase import GameLifecycleError


class WeaponInstanceSelectionError(GameLifecycleError):
    """An attack declaration has missing, forged or conflicting finite choices."""


DUPLICATED_ABILITIES_SOURCE_ID = "gw-11e-core-duplicated-abilities:duplicated-abilities"


def weapon_instance_groups(
    profile: WeaponProfile,
) -> tuple[tuple[str, tuple[AbilitySourceInstance, ...]], ...]:
    """Group before target conditions; different Anti keywords are duplicates."""
    descriptor_families = {
        descriptor.ability_id: (
            weapon_keyword_ability_id(keyword)
            if (keyword := weapon_keyword_for_ability_kind(descriptor.ability_kind)) is not None
            else descriptor.ability_kind.value
        )
        for descriptor in profile.abilities
    }
    groups: dict[str, list[AbilitySourceInstance]] = {}
    for source in weapon_ability_sources(profile):
        family = descriptor_families.get(source.ability_id, source.ability_id)
        groups.setdefault(family, []).append(source)
    return tuple((family, tuple(sources)) for family, sources in sorted(groups.items()))


def weapon_instance_selection_requests(
    profile: WeaponProfile,
    *,
    actor_id: str,
    request_id: str,
    source_context: JsonValue = None,
) -> tuple[DecisionRequest, ...]:
    descriptors = {ability.ability_id: ability for ability in profile.abilities}
    return tuple(
        DecisionRequest(
            request_id=f"{request_id}:ability-instance:{family}",
            decision_type="select_weapon_ability_instance",
            actor_id=actor_id,
            payload=validate_json_value(
                {
                    "submission_kind": "select_weapon_ability_instance",
                    "weapon_profile_id": profile.profile_id,
                    "ability_family": family,
                    "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                    "source_context": source_context,
                    "ability_sources": [source.to_payload() for source in sources],
                }
            ),
            options=tuple(
                DecisionOption(
                    option_id=source.instance_id,
                    label=(
                        descriptors[source.ability_id].name
                        if source.ability_id in descriptors
                        else source.ability_id
                    ),
                    payload=validate_json_value(
                        {
                            "submission_kind": "select_weapon_ability_instance",
                            "weapon_profile_id": profile.profile_id,
                            "ability_family": family,
                            "selected_ability_instance_id": source.instance_id,
                            "ability_source": source.to_payload(),
                            "ability_descriptor": (
                                descriptors[source.ability_id].to_payload()
                                if source.ability_id in descriptors
                                else None
                            ),
                        }
                    ),
                )
                for source in sources
            ),
        )
        for family, sources in weapon_instance_groups(profile)
        if len(sources) > 1
    )


def selected_weapon_profile(
    profile: WeaponProfile, selected_instance_ids: tuple[str, ...]
) -> WeaponProfile:
    """Project an immutable attack carrier after validating every finite choice."""
    return project_weapon_instances(
        profile,
        retained_weapon_instance_ids(weapon_instance_groups(profile), selected_instance_ids),
    )


def retained_weapon_instance_ids(
    groups: tuple[tuple[str, tuple[AbilitySourceInstance, ...]], ...],
    selected_instance_ids: tuple[str, ...],
) -> set[str]:
    """One validation path for direct profiles and multi-target Select Weapons."""
    if type(selected_instance_ids) is not tuple or any(
        type(value) is not str for value in selected_instance_ids
    ):
        raise WeaponInstanceSelectionError("Weapon instance selection requires a tuple of IDs.")
    selected = set(selected_instance_ids)
    if len(selected) != len(selected_instance_ids):
        raise WeaponInstanceSelectionError("Weapon selection requires exactly one per family.")
    available = {
        source.instance_id for _, sources in groups if len(sources) > 1 for source in sources
    }
    if not selected <= available:
        raise WeaponInstanceSelectionError("Selected weapon ability instance is unavailable.")
    retained: set[str] = set()
    for _, sources in groups:
        if len(sources) == 1:
            retained.add(sources[0].instance_id)
            continue
        choices = {source.instance_id for source in sources} & selected
        if len(choices) != 1:
            raise WeaponInstanceSelectionError("Weapon selection requires exactly one per family.")
        retained.update(choices)
    return retained


def project_weapon_instances(
    profile: WeaponProfile, retained_instance_ids: set[str]
) -> WeaponProfile:
    """Project applicability after the complete attack inventory has been validated."""
    retained = tuple(
        source
        for source in weapon_ability_sources(profile)
        if source.instance_id in retained_instance_ids
    )
    if retained == weapon_ability_sources(profile):
        return profile
    retained_ids = {source.ability_id for source in retained}
    retained_families = {
        family
        for family, sources in weapon_instance_groups(profile)
        if any(source.instance_id in retained_instance_ids for source in sources)
    }
    return replace(
        profile,
        abilities=tuple(
            ability for ability in profile.abilities if ability.ability_id in retained_ids
        ),
        keywords=tuple(
            keyword
            for keyword in profile.keywords
            if weapon_keyword_ability_id(keyword) in retained_families
        ),
        ability_sources=retained,
    )
