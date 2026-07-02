from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    WeaponProfile,
    WeaponProfileError,
    WeaponProfilePayload,
)


class WargearError(ValueError):
    """Raised when wargear data violates CORE V2 invariants."""


class WargearPayload(TypedDict):
    wargear_id: str
    name: str
    weapon_profiles: list[WeaponProfilePayload]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class Wargear:
    wargear_id: str
    name: str
    weapon_profiles: tuple[WeaponProfile, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "wargear_id",
            _validate_wargear_id(self.wargear_id),
        )
        object.__setattr__(self, "name", _validate_identifier("Wargear name", self.name))
        profiles = tuple(_validate_weapon_profile(profile) for profile in self.weapon_profiles)
        _validate_unique_profile_ids(profiles)
        if profiles != self.weapon_profiles:
            object.__setattr__(self, "weapon_profiles", profiles)
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("Wargear source_ids", self.source_ids),
        )

    def stable_identity(self) -> str:
        return f"wargear:{self.wargear_id}"

    def weapon_profile_by_id(self, profile_id: str) -> WeaponProfile:
        requested_id = _validate_identifier("profile_id", profile_id)
        for profile in self.weapon_profiles:
            if profile.profile_id == requested_id:
                return profile
        raise WargearError("Wargear weapon profile ID was not found.")

    def to_payload(self) -> WargearPayload:
        return {
            "wargear_id": self.wargear_id,
            "name": self.name,
            "weapon_profiles": [profile.to_payload() for profile in self.weapon_profiles],
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: WargearPayload) -> Self:
        return cls(
            wargear_id=payload["wargear_id"],
            name=payload["name"],
            weapon_profiles=tuple(
                _weapon_profile_from_payload(profile) for profile in payload["weapon_profiles"]
            ),
            source_ids=tuple(payload["source_ids"]),
        )


_validate_identifier = IdentifierValidator(WargearError)


def _validate_wargear_id(value: object) -> str:
    identifier = _validate_identifier("Wargear wargear_id", value)
    if identifier.startswith("wargear:"):
        raise WargearError("Wargear wargear_id must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise WargearError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise WargearError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(validated)


def _validate_weapon_profile(profile: object) -> WeaponProfile:
    if type(profile) is not WeaponProfile:
        raise WargearError("Wargear weapon_profiles must contain WeaponProfile values.")
    return profile


def _validate_unique_profile_ids(profiles: tuple[WeaponProfile, ...]) -> None:
    seen: set[str] = set()
    for profile in profiles:
        if profile.profile_id in seen:
            raise WargearError("Wargear weapon profile IDs must be unique.")
        seen.add(profile.profile_id)


def _weapon_profile_from_payload(payload: WeaponProfilePayload) -> WeaponProfile:
    try:
        return WeaponProfile.from_payload(payload)
    except WeaponProfileError as exc:
        raise WargearError("Wargear weapon profile payload is invalid.") from exc
