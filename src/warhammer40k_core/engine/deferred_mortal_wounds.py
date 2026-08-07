from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload
from warhammer40k_core.engine.phase import GameLifecycleError


class DeferredMortalWoundsPayload(TypedDict):
    source_rule_id: str
    source_model_instance_id: str
    source_weapon_profile: WeaponProfilePayload
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int
    priority_model_ids: list[str]


_validate_identifier = IdentifierValidator(GameLifecycleError)


@dataclass(frozen=True, slots=True)
class DeferredMortalWounds:
    source_rule_id: str
    source_model_instance_id: str
    source_weapon_profile: WeaponProfile
    target_unit_instance_id: str
    attack_context_id: str
    mortal_wounds: int
    priority_model_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_rule_id",
            _validate_identifier("DeferredMortalWounds source_rule_id", self.source_rule_id),
        )
        object.__setattr__(
            self,
            "source_model_instance_id",
            _validate_identifier(
                "DeferredMortalWounds source_model_instance_id",
                self.source_model_instance_id,
            ),
        )
        if type(self.source_weapon_profile) is not WeaponProfile:
            raise GameLifecycleError(
                "DeferredMortalWounds source_weapon_profile must be WeaponProfile."
            )
        object.__setattr__(
            self,
            "target_unit_instance_id",
            _validate_identifier(
                "DeferredMortalWounds target_unit_instance_id",
                self.target_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "attack_context_id",
            _validate_identifier(
                "DeferredMortalWounds attack_context_id",
                self.attack_context_id,
            ),
        )
        if type(self.mortal_wounds) is not int or self.mortal_wounds < 1:
            raise GameLifecycleError("DeferredMortalWounds mortal_wounds must be positive.")
        priority_ids = tuple(
            _validate_identifier("DeferredMortalWounds priority_model_id", value)
            for value in self.priority_model_ids
        )
        if len(set(priority_ids)) != len(priority_ids):
            raise GameLifecycleError(
                "DeferredMortalWounds priority_model_ids must not contain duplicates."
            )
        object.__setattr__(self, "priority_model_ids", tuple(sorted(priority_ids)))

    def to_payload(self) -> DeferredMortalWoundsPayload:
        return {
            "source_rule_id": self.source_rule_id,
            "source_model_instance_id": self.source_model_instance_id,
            "source_weapon_profile": self.source_weapon_profile.to_payload(),
            "target_unit_instance_id": self.target_unit_instance_id,
            "attack_context_id": self.attack_context_id,
            "mortal_wounds": self.mortal_wounds,
            "priority_model_ids": list(self.priority_model_ids),
        }

    @classmethod
    def from_payload(cls, payload: DeferredMortalWoundsPayload) -> Self:
        return cls(
            source_rule_id=payload["source_rule_id"],
            source_model_instance_id=payload["source_model_instance_id"],
            source_weapon_profile=WeaponProfile.from_payload(payload["source_weapon_profile"]),
            target_unit_instance_id=payload["target_unit_instance_id"],
            attack_context_id=payload["attack_context_id"],
            mortal_wounds=payload["mortal_wounds"],
            priority_model_ids=tuple(payload["priority_model_ids"]),
        )
