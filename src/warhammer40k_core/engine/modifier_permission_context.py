"""Authenticated attack facts needed by restricted modifier-ignore grants."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Self, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile, WeaponProfilePayload
from warhammer40k_core.engine.event_log import JsonValue, validate_json_value
from warhammer40k_core.engine.generic_rule_effect_targets import AttackRole
from warhammer40k_core.engine.phase import BattlePhase, GameLifecycleError


class UnsupportedModifierPermissionContextError(GameLifecycleError):
    """A real permission restriction cannot be evaluated at this rules boundary."""


@dataclass(frozen=True, slots=True)
class ModifierPermissionAttackContext:
    attacking_unit_instance_id: str
    attacker_model_instance_id: str
    target_unit_instance_id: str
    subject_role: AttackRole
    source_phase: BattlePhase
    weapon_profile: WeaponProfile
    attack_strength: int | None
    target_toughness: int | None

    def __post_init__(self) -> None:
        for name in (
            "attacking_unit_instance_id",
            "attacker_model_instance_id",
            "target_unit_instance_id",
        ):
            object.__setattr__(self, name, _identifier(name, getattr(self, name)))
        object.__setattr__(self, "subject_role", _attack_role(self.subject_role))
        if type(self.source_phase) is not BattlePhase:
            raise GameLifecycleError("Modifier permission context requires a typed source phase.")
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("Modifier permission context requires a WeaponProfile.")
        _optional_positive_int("attack_strength", self.attack_strength)
        _optional_positive_int("target_toughness", self.target_toughness)

    def to_payload(self) -> dict[str, JsonValue]:
        return {
            "attacking_unit_instance_id": self.attacking_unit_instance_id,
            "attacker_model_instance_id": self.attacker_model_instance_id,
            "target_unit_instance_id": self.target_unit_instance_id,
            "subject_role": self.subject_role,
            "source_phase": self.source_phase.value,
            "weapon_profile": validate_json_value(self.weapon_profile.to_payload()),
            "attack_strength": self.attack_strength,
            "target_toughness": self.target_toughness,
        }

    @classmethod
    def from_payload(cls, payload: object) -> Self:
        fields = {
            "attacking_unit_instance_id",
            "attacker_model_instance_id",
            "target_unit_instance_id",
            "subject_role",
            "source_phase",
            "weapon_profile",
            "attack_strength",
            "target_toughness",
        }
        if not isinstance(payload, dict):
            raise GameLifecycleError("Modifier permission attack context fields drifted.")
        raw = cast(dict[str, object], payload)
        if set(raw) != fields:
            raise GameLifecycleError("Modifier permission attack context fields drifted.")
        phase = raw["source_phase"]
        if type(phase) is not str:
            raise GameLifecycleError("Modifier permission context requires a source phase token.")
        try:
            source_phase = BattlePhase(phase)
        except ValueError as exc:
            raise GameLifecycleError(
                "Modifier permission context source phase is unsupported."
            ) from exc
        profile_payload = raw["weapon_profile"]
        if not isinstance(profile_payload, dict):
            raise GameLifecycleError(
                "Modifier permission context weapon profile must be an object."
            )
        try:
            profile = WeaponProfile.from_payload(cast(WeaponProfilePayload, profile_payload))
        except (KeyError, TypeError, ValueError) as exc:
            raise GameLifecycleError(
                "Modifier permission context weapon profile is malformed."
            ) from exc
        if validate_json_value(profile.to_payload()) != profile_payload:
            raise GameLifecycleError("Modifier permission context weapon profile fields drifted.")
        role = _attack_role(raw["subject_role"])
        return cls(
            attacking_unit_instance_id=_identifier(
                "attacking_unit_instance_id", raw["attacking_unit_instance_id"]
            ),
            attacker_model_instance_id=_identifier(
                "attacker_model_instance_id", raw["attacker_model_instance_id"]
            ),
            target_unit_instance_id=_identifier(
                "target_unit_instance_id", raw["target_unit_instance_id"]
            ),
            subject_role=role,
            source_phase=source_phase,
            weapon_profile=profile,
            attack_strength=_optional_positive_int("attack_strength", raw["attack_strength"]),
            target_toughness=_optional_positive_int("target_toughness", raw["target_toughness"]),
        )


def _attack_role(value: object) -> AttackRole:
    if type(value) is not str or value not in {"attacker", "target"}:
        raise GameLifecycleError("Modifier permission context requires an attack subject role.")
    return cast(AttackRole, value)


def _optional_positive_int(name: str, value: object) -> int | None:
    if value is None:
        return None
    if type(value) is not int or value <= 0:
        raise GameLifecycleError(
            f"Modifier permission context {name} must be a positive integer or null."
        )
    return value


_identifier = IdentifierValidator(GameLifecycleError)
