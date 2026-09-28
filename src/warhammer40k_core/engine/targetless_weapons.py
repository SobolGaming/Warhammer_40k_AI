"""Selected ranged weapons with explicitly declined targets, never attack pools."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload
from warhammer40k_core.engine.ability_instance_selection import selected_weapon_profile
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.weapon_declaration import WeaponDeclaration, WeaponDeclarationPayload


class TargetlessWeaponPayload(TypedDict):
    declaration: WeaponDeclarationPayload
    source_profile: WeaponProfilePayload


@dataclass(frozen=True, slots=True)
class TargetlessWeapon:
    declaration: WeaponDeclaration
    source_profile: WeaponProfile

    def __post_init__(self) -> None:
        if (
            type(self.declaration) is not WeaponDeclaration
            or type(self.source_profile) is not WeaponProfile
        ):
            raise GameLifecycleError(
                "Targetless selection requires a typed declaration and profile."
            )
        if self.declaration.target_unit_instance_id is not None:
            raise GameLifecycleError("Targetless weapons cannot contain targets.")
        if self.source_profile.profile_id != self.declaration.weapon_profile_id:
            raise GameLifecycleError("Targetless selected profile identity drift.")
        # Validate the source-instance choice eagerly, including redundant/unknown IDs.
        selected_weapon_profile(self.source_profile, self.declaration.selected_weapon_ability_ids)

    @property
    def weapon_profile(self) -> WeaponProfile:
        return selected_weapon_profile(
            self.source_profile, self.declaration.selected_weapon_ability_ids
        )

    @property
    def weapon_instance_id(self) -> str:
        return self.declaration.weapon_instance_id

    @property
    def weapon_profile_id(self) -> str:
        return self.declaration.weapon_profile_id

    @property
    def attacker_model_instance_id(self) -> str:
        return self.declaration.attacker_model_instance_id

    @property
    def wargear_id(self) -> str:
        return self.declaration.wargear_id

    @property
    def firing_deck_source_model_instance_id(self) -> str | None:
        return self.declaration.firing_deck_source_model_instance_id

    def to_payload(self) -> TargetlessWeaponPayload:
        return {
            "declaration": self.declaration.to_payload(),
            "source_profile": self.source_profile.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: TargetlessWeaponPayload) -> Self:
        if type(cast(object, payload)) is not dict or set(payload) != {
            "declaration",
            "source_profile",
        }:
            raise GameLifecycleError("Targetless weapon payload fields are invalid.")
        if not isinstance(cast(object, payload["declaration"]), dict) or not isinstance(
            cast(object, payload["source_profile"]), dict
        ):
            raise GameLifecycleError("Targetless weapon payload requires typed objects.")
        try:
            return cls(
                WeaponDeclaration.from_payload(payload["declaration"]),
                WeaponProfile.from_payload(payload["source_profile"]),
            )
        except KeyError as exc:
            raise GameLifecycleError(
                "Targetless weapon payload is missing a required field."
            ) from exc
