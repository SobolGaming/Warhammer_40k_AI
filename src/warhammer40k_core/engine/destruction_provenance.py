from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import (
    RangeProfileKind,
    WeaponProfile,
    WeaponProfilePayload,
)
from warhammer40k_core.engine.phase import GameLifecycleError


class DestructionSourceKind(StrEnum):
    ATTACK = "attack"
    DEADLY_DEMISE = "deadly_demise"
    HAZARDOUS = "hazardous"
    ABILITY = "ability"


class DestructionAttackKind(StrEnum):
    MELEE = "melee"
    RANGED = "ranged"
    NONE = "none"


class DestructionProvenancePayload(TypedDict):
    destruction_source_kind: str
    attack_kind: str
    source_weapon_profile: WeaponProfilePayload | None
    attack_context_id: str | None


@dataclass(frozen=True, slots=True)
class DestructionProvenance:
    destruction_source_kind: DestructionSourceKind
    attack_kind: DestructionAttackKind
    source_weapon_profile: WeaponProfile | None = None
    attack_context_id: str | None = None

    def __post_init__(self) -> None:
        source_kind = _destruction_source_kind(self.destruction_source_kind)
        attack_kind = _destruction_attack_kind(self.attack_kind)
        object.__setattr__(self, "destruction_source_kind", source_kind)
        object.__setattr__(self, "attack_kind", attack_kind)
        if source_kind is DestructionSourceKind.ATTACK:
            if attack_kind is DestructionAttackKind.NONE:
                raise GameLifecycleError("Attack destruction provenance requires an attack kind.")
            if type(self.source_weapon_profile) is not WeaponProfile:
                raise GameLifecycleError(
                    "Attack destruction provenance requires a source weapon profile."
                )
            derived_attack_kind = (
                DestructionAttackKind.MELEE
                if self.source_weapon_profile.range_profile.kind is RangeProfileKind.MELEE
                else DestructionAttackKind.RANGED
            )
            if attack_kind is not derived_attack_kind:
                raise GameLifecycleError("Destruction provenance attack kind drift.")
            object.__setattr__(
                self,
                "attack_context_id",
                _validate_identifier(
                    "DestructionProvenance attack_context_id",
                    self.attack_context_id,
                ),
            )
            return
        if attack_kind is not DestructionAttackKind.NONE:
            raise GameLifecycleError(
                "Non-attack destruction provenance cannot have an attack kind."
            )
        if self.source_weapon_profile is not None or self.attack_context_id is not None:
            raise GameLifecycleError(
                "Non-attack destruction provenance cannot have attack context."
            )

    @classmethod
    def for_attack(
        cls,
        *,
        weapon_profile: WeaponProfile,
        attack_context_id: str,
    ) -> Self:
        if type(weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Attack destruction provenance requires WeaponProfile.")
        attack_kind = (
            DestructionAttackKind.MELEE
            if weapon_profile.range_profile.kind is RangeProfileKind.MELEE
            else DestructionAttackKind.RANGED
        )
        return cls(
            destruction_source_kind=DestructionSourceKind.ATTACK,
            attack_kind=attack_kind,
            source_weapon_profile=weapon_profile,
            attack_context_id=attack_context_id,
        )

    @classmethod
    def for_non_attack(cls, source_kind: DestructionSourceKind) -> Self:
        resolved_kind = _destruction_source_kind(source_kind)
        if resolved_kind is DestructionSourceKind.ATTACK:
            raise GameLifecycleError("Attack destruction provenance requires weapon context.")
        return cls(
            destruction_source_kind=resolved_kind,
            attack_kind=DestructionAttackKind.NONE,
        )

    def to_payload(self) -> DestructionProvenancePayload:
        return {
            "destruction_source_kind": self.destruction_source_kind.value,
            "attack_kind": self.attack_kind.value,
            "source_weapon_profile": (
                None
                if self.source_weapon_profile is None
                else self.source_weapon_profile.to_payload()
            ),
            "attack_context_id": self.attack_context_id,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        if not isinstance(payload, dict):
            raise GameLifecycleError("Destruction provenance payload must be an object.")
        raw = cast(dict[str, object], payload)
        expected_keys = {
            "destruction_source_kind",
            "attack_kind",
            "source_weapon_profile",
            "attack_context_id",
        }
        if set(raw) != expected_keys:
            raise GameLifecycleError("Destruction provenance payload fields are invalid.")
        source_weapon_profile_payload = raw["source_weapon_profile"]
        attack_context_id = raw["attack_context_id"]
        if source_weapon_profile_payload is not None and not isinstance(
            source_weapon_profile_payload, dict
        ):
            raise GameLifecycleError("Destruction provenance weapon profile is invalid.")
        if attack_context_id is not None and type(attack_context_id) is not str:
            raise GameLifecycleError("Destruction provenance attack context ID is invalid.")
        return cls(
            destruction_source_kind=_destruction_source_kind(raw["destruction_source_kind"]),
            attack_kind=_destruction_attack_kind(raw["attack_kind"]),
            source_weapon_profile=(
                None
                if source_weapon_profile_payload is None
                else WeaponProfile.from_payload(
                    cast(WeaponProfilePayload, source_weapon_profile_payload)
                )
            ),
            attack_context_id=attack_context_id,
        )


def _destruction_source_kind(value: object) -> DestructionSourceKind:
    if isinstance(value, DestructionSourceKind):
        return value
    if type(value) is not str:
        raise GameLifecycleError("Destruction provenance source kind must be a string.")
    try:
        return DestructionSourceKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Destruction provenance source kind is unsupported.") from exc


def _destruction_attack_kind(value: object) -> DestructionAttackKind:
    if isinstance(value, DestructionAttackKind):
        return value
    if type(value) is not str:
        raise GameLifecycleError("Destruction provenance attack kind must be a string.")
    try:
        return DestructionAttackKind(value)
    except ValueError as exc:
        raise GameLifecycleError("Destruction provenance attack kind is unsupported.") from exc


_validate_identifier = IdentifierValidator(GameLifecycleError)
