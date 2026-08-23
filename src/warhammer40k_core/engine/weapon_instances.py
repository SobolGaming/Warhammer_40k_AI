from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.engine.event_log import canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError
from warhammer40k_core.engine.unit_factory import ModelInstance

__all__ = (
    "EquippedWeaponInstance",
    "EquippedWeaponProfileInstance",
    "equipped_weapon_instance_by_id",
    "equipped_weapon_instances_for_model",
    "equipped_weapon_profile_instances_for_model",
    "weapon_instance_id_for_copy",
)


@dataclass(frozen=True, slots=True)
class EquippedWeaponInstance:
    weapon_instance_id: str
    model_instance_id: str
    wargear_id: str
    copy_ordinal: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "weapon_instance_id",
            _validate_identifier(
                "EquippedWeaponInstance weapon_instance_id",
                self.weapon_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_identifier(
                "EquippedWeaponInstance model_instance_id",
                self.model_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "wargear_id",
            _validate_identifier("EquippedWeaponInstance wargear_id", self.wargear_id),
        )
        if type(self.copy_ordinal) is not int or self.copy_ordinal < 1:
            raise GameLifecycleError(
                "EquippedWeaponInstance copy_ordinal must be a positive integer."
            )


@dataclass(frozen=True, slots=True)
class EquippedWeaponProfileInstance:
    weapon_instance: EquippedWeaponInstance
    weapon_profile: WeaponProfile

    def __post_init__(self) -> None:
        if type(self.weapon_instance) is not EquippedWeaponInstance:
            raise GameLifecycleError(
                "EquippedWeaponProfileInstance requires an EquippedWeaponInstance."
            )
        if type(self.weapon_profile) is not WeaponProfile:
            raise GameLifecycleError("EquippedWeaponProfileInstance requires a WeaponProfile.")

    @property
    def weapon_instance_id(self) -> str:
        return self.weapon_instance.weapon_instance_id

    @property
    def model_instance_id(self) -> str:
        return self.weapon_instance.model_instance_id

    @property
    def wargear_id(self) -> str:
        return self.weapon_instance.wargear_id


def equipped_weapon_instances_for_model(
    model: ModelInstance,
) -> tuple[EquippedWeaponInstance, ...]:
    if type(model) is not ModelInstance:
        raise GameLifecycleError("Equipped weapon instance lookup requires a ModelInstance.")
    next_ordinal_by_wargear_id: dict[str, int] = {}
    instances: list[EquippedWeaponInstance] = []
    for wargear_id in model.wargear_ids:
        copy_ordinal = next_ordinal_by_wargear_id.get(wargear_id, 0) + 1
        next_ordinal_by_wargear_id[wargear_id] = copy_ordinal
        instances.append(
            EquippedWeaponInstance(
                weapon_instance_id=weapon_instance_id_for_copy(
                    model_instance_id=model.model_instance_id,
                    wargear_id=wargear_id,
                    copy_ordinal=copy_ordinal,
                ),
                model_instance_id=model.model_instance_id,
                wargear_id=wargear_id,
                copy_ordinal=copy_ordinal,
            )
        )
    return tuple(instances)


def equipped_weapon_profile_instances_for_model(
    *,
    model: ModelInstance,
    army_catalog: ArmyCatalog,
) -> tuple[EquippedWeaponProfileInstance, ...]:
    if type(army_catalog) is not ArmyCatalog:
        raise GameLifecycleError("Equipped weapon profile instance lookup requires an ArmyCatalog.")
    wargear_by_id = {wargear.wargear_id: wargear for wargear in army_catalog.wargear}
    profile_instances: list[EquippedWeaponProfileInstance] = []
    for weapon_instance in equipped_weapon_instances_for_model(model):
        wargear = wargear_by_id.get(weapon_instance.wargear_id)
        if wargear is None:
            raise GameLifecycleError(
                "Equipped weapon instance wargear_id is not in the ArmyCatalog."
            )
        profile_instances.extend(
            EquippedWeaponProfileInstance(
                weapon_instance=weapon_instance,
                weapon_profile=weapon_profile,
            )
            for weapon_profile in wargear.weapon_profiles
        )
    return tuple(profile_instances)


def equipped_weapon_instance_by_id(
    *,
    model: ModelInstance,
    weapon_instance_id: str,
) -> EquippedWeaponInstance | None:
    requested_id = _validate_identifier("weapon_instance_id", weapon_instance_id)
    for weapon_instance in equipped_weapon_instances_for_model(model):
        if weapon_instance.weapon_instance_id == requested_id:
            return weapon_instance
    return None


def weapon_instance_id_for_copy(
    *,
    model_instance_id: str,
    wargear_id: str,
    copy_ordinal: int,
) -> str:
    model_id = _validate_identifier("model_instance_id", model_instance_id)
    equipped_wargear_id = _validate_identifier("wargear_id", wargear_id)
    if type(copy_ordinal) is not int or copy_ordinal < 1:
        raise GameLifecycleError("copy_ordinal must be a positive integer.")
    identity_payload = {
        "model_instance_id": model_id,
        "wargear_id": equipped_wargear_id,
        "copy_ordinal": copy_ordinal,
    }
    digest = sha256(canonical_json(identity_payload).encode("utf-8")).hexdigest()
    return f"weapon-instance:{digest}"


_validate_identifier = IdentifierValidator(GameLifecycleError)
