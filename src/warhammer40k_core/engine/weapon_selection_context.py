"""Immutable Select Weapons inventory shared by requests, validation and attacks."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import NotRequired, Self, TypedDict

from warhammer40k_core.core.ability_sources import AbilitySourceInstance
from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload
from warhammer40k_core.engine.ability_instance_selection import (
    DUPLICATED_ABILITIES_SOURCE_ID,
    WeaponInstanceSelectionError,
    project_weapon_instances,
    retained_weapon_instance_ids,
    weapon_instance_groups,
)
from warhammer40k_core.engine.decision_request import DecisionOption, DecisionRequest
from warhammer40k_core.engine.event_log import validate_json_value


class TargetWeaponProfilePayload(TypedDict):
    target_unit_instance_id: str
    weapon_profile: WeaponProfilePayload


class WeaponSelectionContextPayload(TypedDict):
    weapon_instance_id: str
    source_request_id: str
    target_profiles: list[TargetWeaponProfilePayload]
    resolved_target_profiles: NotRequired[list[TargetWeaponProfilePayload]]


@dataclass(frozen=True, slots=True)
class WeaponSelectionContext:
    weapon_instance_id: str
    source_request_id: str
    target_profiles: tuple[tuple[str, WeaponProfile], ...]
    resolved_target_profiles: tuple[tuple[str, WeaponProfile], ...] = ()

    def __post_init__(self) -> None:
        for value in (self.weapon_instance_id, self.source_request_id):
            if type(value) is not str or not value or value.strip() != value:
                raise WeaponInstanceSelectionError("Weapon selection context requires identifiers.")
        if type(self.target_profiles) is not tuple or not self.target_profiles:
            raise WeaponInstanceSelectionError("Weapon selection context requires target profiles.")
        seen: set[str] = set()
        profile_ids: set[str] = set()
        for entry in self.target_profiles:
            if type(entry) is not tuple or len(entry) != 2:
                raise WeaponInstanceSelectionError("Weapon selection target entry must be a pair.")
            target, profile = entry
            if type(target) is not str or not target or target.strip() != target or target in seen:
                raise WeaponInstanceSelectionError("Weapon selection target identity is invalid.")
            if type(profile) is not WeaponProfile:
                raise WeaponInstanceSelectionError("Weapon selection requires typed profiles.")
            seen.add(target)
            profile_ids.add(profile.profile_id)
        if len(profile_ids) != 1:
            raise WeaponInstanceSelectionError("Weapon selection profile identity drift.")
        object.__setattr__(self, "target_profiles", tuple(sorted(self.target_profiles)))
        if self.resolved_target_profiles:
            # Use the same strict row validation without widening the frozen inventory.
            validated = WeaponSelectionContext(
                self.weapon_instance_id, self.source_request_id, self.resolved_target_profiles
            )
            if {profile.profile_id for _, profile in validated.target_profiles} != profile_ids:
                raise WeaponInstanceSelectionError("Resolved weapon profile identity drift.")
            object.__setattr__(self, "resolved_target_profiles", validated.target_profiles)
        self.instance_groups()

    def raw_profile_for_target(self, target_id: str) -> WeaponProfile:
        profiles = dict((*self.target_profiles, *self.resolved_target_profiles))
        if target_id not in profiles:
            raise WeaponInstanceSelectionError("Weapon selection target is unavailable.")
        return profiles[target_id]

    def with_resolved_profile(
        self, target_id: str, profile: WeaponProfile
    ) -> WeaponSelectionContext:
        profiles = dict(self.resolved_target_profiles)
        profiles[target_id] = profile
        return replace(self, resolved_target_profiles=tuple(sorted(profiles.items())))

    def instance_groups(self) -> tuple[tuple[str, tuple[AbilitySourceInstance, ...]], ...]:
        groups: dict[str, dict[str, AbilitySourceInstance]] = {}
        families: dict[str, str] = {}
        for _, profile in self.target_profiles:
            for family, sources in weapon_instance_groups(profile):
                for source in sources:
                    if source.instance_id in families and families[source.instance_id] != family:
                        raise WeaponInstanceSelectionError("Weapon selection source family drift.")
                    families[source.instance_id] = family
                    groups.setdefault(family, {}).setdefault(source.instance_id, source)
        return tuple(
            (family, tuple(sources[key] for key in sorted(sources)))
            for family, sources in sorted(groups.items())
        )

    def selection_requests(self, *, actor_id: str) -> tuple[DecisionRequest, ...]:
        return tuple(
            DecisionRequest(
                request_id=(
                    f"{self.source_request_id}:{self.weapon_instance_id}:"
                    f"{':'.join(target for target, _ in self.target_profiles)}:ability:{family}"
                ),
                decision_type="select_weapon_ability_instance",
                actor_id=actor_id,
                payload=validate_json_value(
                    {
                        "submission_kind": "select_weapon_ability_instance",
                        "source_rule_id": DUPLICATED_ABILITIES_SOURCE_ID,
                        "ability_family": family,
                        "selection_context": self.to_payload(),
                    }
                ),
                options=tuple(
                    DecisionOption(
                        option_id=source.instance_id,
                        label=source.ability_id,
                        payload=validate_json_value(
                            {
                                "submission_kind": "select_weapon_ability_instance",
                                "selected_ability_instance_id": source.instance_id,
                                "ability_family": family,
                                "ability_source": source.to_payload(),
                            }
                        ),
                    )
                    for source in sources
                ),
            )
            for family, sources in self.instance_groups()
            if len(sources) > 1
        )

    def selected_profile(
        self, target_unit_instance_id: str, selected_instance_ids: tuple[str, ...]
    ) -> WeaponProfile:
        retained = retained_weapon_instance_ids(self.instance_groups(), selected_instance_ids)
        return project_weapon_instances(
            self.raw_profile_for_target(target_unit_instance_id), retained
        )

    def for_targets(self, target_ids: tuple[str, ...]) -> WeaponSelectionContext:
        if not target_ids or len(set(target_ids)) != len(target_ids):
            raise WeaponInstanceSelectionError("Weapon selection requires unique targets.")
        profiles = dict(self.target_profiles)
        if not set(target_ids) <= profiles.keys():
            raise WeaponInstanceSelectionError("Weapon selection target is unavailable.")
        return WeaponSelectionContext(
            weapon_instance_id=self.weapon_instance_id,
            source_request_id=self.source_request_id,
            target_profiles=tuple((target, profiles[target]) for target in target_ids),
        )

    def to_payload(self) -> WeaponSelectionContextPayload:
        payload: WeaponSelectionContextPayload = {
            "weapon_instance_id": self.weapon_instance_id,
            "source_request_id": self.source_request_id,
            "target_profiles": [
                {"target_unit_instance_id": target, "weapon_profile": profile.to_payload()}
                for target, profile in self.target_profiles
            ],
        }
        if self.resolved_target_profiles:
            payload["resolved_target_profiles"] = [
                {"target_unit_instance_id": target, "weapon_profile": profile.to_payload()}
                for target, profile in self.resolved_target_profiles
            ]
        return payload

    @classmethod
    def from_payload(cls, payload: WeaponSelectionContextPayload) -> Self:
        return cls(
            weapon_instance_id=payload["weapon_instance_id"],
            source_request_id=payload["source_request_id"],
            resolved_target_profiles=tuple(
                (
                    entry["target_unit_instance_id"],
                    WeaponProfile.from_payload(entry["weapon_profile"]),
                )
                for entry in payload.get("resolved_target_profiles", [])
            ),
            target_profiles=tuple(
                (
                    entry["target_unit_instance_id"],
                    WeaponProfile.from_payload(entry["weapon_profile"]),
                )
                for entry in payload["target_profiles"]
            ),
        )


def shooting_context_matches_request(
    request: DecisionRequest, context: WeaponSelectionContext
) -> bool:
    """Authenticate the live inventory against the inventory offered to the player."""
    payload = request.payload
    if not isinstance(payload, dict):
        return False
    proposal = payload.get("proposal_request")
    if not isinstance(proposal, dict):
        return False
    candidates = proposal.get("target_candidates")
    if not isinstance(candidates, list):
        return False
    expected = validate_json_value(context.to_payload())
    return any(
        isinstance(candidate, dict)
        and candidate.get("weapon_instance_id") == context.weapon_instance_id
        and candidate.get("weapon_ability_selection_context") == expected
        for candidate in candidates
    )


def reidentify_selection_context(
    context: WeaponSelectionContext,
    *,
    weapon_instance_id: str,
    profile_id: str,
    profile_name: str,
    selected_instance_ids: tuple[str, ...],
) -> tuple[WeaponSelectionContext, tuple[str, ...]]:
    """Rebind a synthetic gathered carrier; original pools retain physical evidence."""
    from warhammer40k_core.core.weapon_ability_sources import reidentify_weapon_profile

    sources = tuple(source for _, group in context.instance_groups() for source in group)
    remapped = {
        source.instance_id: replace(source, owner_id=f"weapon-profile:{profile_id}").instance_id
        for source in sources
    }
    return (
        WeaponSelectionContext(
            weapon_instance_id=weapon_instance_id,
            source_request_id=context.source_request_id,
            resolved_target_profiles=tuple(
                (
                    target,
                    reidentify_weapon_profile(profile, profile_id=profile_id, name=profile_name),
                )
                for target, profile in context.resolved_target_profiles
            ),
            target_profiles=tuple(
                (
                    target,
                    reidentify_weapon_profile(profile, profile_id=profile_id, name=profile_name),
                )
                for target, profile in context.target_profiles
            ),
        ),
        tuple(remapped[instance_id] for instance_id in selected_instance_ids),
    )


def rebind_selection_targets(
    context: WeaponSelectionContext, target_ids: dict[str, str]
) -> WeaponSelectionContext:
    profiles: dict[str, WeaponProfile] = {}
    for target_id, profile in context.target_profiles:
        canonical_id = target_ids[target_id]
        if canonical_id in profiles and profiles[canonical_id] != profile:
            raise WeaponInstanceSelectionError(
                "Attached target weapon source inventories disagree."
            )
        profiles[canonical_id] = profile
    return replace(context, target_profiles=tuple(sorted(profiles.items())))
