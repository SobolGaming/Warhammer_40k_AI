from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.engine.army_mustering import ArmyDefinition, muster_army
from warhammer40k_core.engine.event_log import JsonValue, canonical_json
from warhammer40k_core.engine.phase import GameLifecycleError


class RuntimeContentActivationPayload(TypedDict):
    selected_faction_ids: list[str]
    selected_detachment_ids: list[str]
    selected_enhancement_ids: list[str]
    selected_stratagem_ids: list[str]
    selected_datasheet_ids: list[str]
    selected_wargear_ids: list[str]
    selected_weapon_profile_ids: list[str]
    selected_weapon_keywords: list[str]
    loaded_unit_instance_ids: list[str]
    reachable_content_ids: list[str]
    selected_module_paths: list[str]
    source_package_ids: list[str]
    source_package_hashes: list[str]
    selected_execution_record_ids: list[str]
    unsupported_content_ids: list[str]
    unsupported_reasons_by_content_id: dict[str, str]
    activation_hash: str


@dataclass(frozen=True, slots=True)
class RuntimeContentActivation:
    selected_faction_ids: tuple[str, ...]
    selected_detachment_ids: tuple[str, ...]
    selected_enhancement_ids: tuple[str, ...]
    selected_stratagem_ids: tuple[str, ...]
    selected_datasheet_ids: tuple[str, ...]
    selected_wargear_ids: tuple[str, ...]
    selected_weapon_profile_ids: tuple[str, ...]
    selected_weapon_keywords: tuple[str, ...]
    loaded_unit_instance_ids: tuple[str, ...]
    reachable_content_ids: tuple[str, ...] = ()
    selected_module_paths: tuple[str, ...] = ()
    source_package_ids: tuple[str, ...] = ()
    source_package_hashes: tuple[str, ...] = ()
    selected_execution_record_ids: tuple[str, ...] = ()
    unsupported_content_ids: tuple[str, ...] = ()
    unsupported_reasons_by_content_id: Mapping[str, str] | None = None
    activation_hash: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "selected_faction_ids",
            _validate_identifier_tuple("selected_faction_ids", self.selected_faction_ids),
        )
        object.__setattr__(
            self,
            "selected_detachment_ids",
            _validate_identifier_tuple("selected_detachment_ids", self.selected_detachment_ids),
        )
        object.__setattr__(
            self,
            "selected_enhancement_ids",
            _validate_identifier_tuple("selected_enhancement_ids", self.selected_enhancement_ids),
        )
        object.__setattr__(
            self,
            "selected_stratagem_ids",
            _validate_identifier_tuple("selected_stratagem_ids", self.selected_stratagem_ids),
        )
        object.__setattr__(
            self,
            "selected_datasheet_ids",
            _validate_identifier_tuple("selected_datasheet_ids", self.selected_datasheet_ids),
        )
        object.__setattr__(
            self,
            "selected_wargear_ids",
            _validate_identifier_tuple("selected_wargear_ids", self.selected_wargear_ids),
        )
        object.__setattr__(
            self,
            "selected_weapon_profile_ids",
            _validate_identifier_tuple(
                "selected_weapon_profile_ids",
                self.selected_weapon_profile_ids,
            ),
        )
        object.__setattr__(
            self,
            "selected_weapon_keywords",
            _validate_identifier_tuple("selected_weapon_keywords", self.selected_weapon_keywords),
        )
        object.__setattr__(
            self,
            "loaded_unit_instance_ids",
            _validate_identifier_tuple("loaded_unit_instance_ids", self.loaded_unit_instance_ids),
        )
        object.__setattr__(
            self,
            "reachable_content_ids",
            _validate_identifier_tuple("reachable_content_ids", self.reachable_content_ids),
        )
        object.__setattr__(
            self,
            "selected_module_paths",
            _validate_identifier_tuple("selected_module_paths", self.selected_module_paths),
        )
        object.__setattr__(
            self,
            "source_package_ids",
            _validate_identifier_tuple("source_package_ids", self.source_package_ids),
        )
        object.__setattr__(
            self,
            "source_package_hashes",
            _validate_identifier_tuple("source_package_hashes", self.source_package_hashes),
        )
        object.__setattr__(
            self,
            "selected_execution_record_ids",
            _validate_identifier_tuple(
                "selected_execution_record_ids",
                self.selected_execution_record_ids,
            ),
        )
        object.__setattr__(
            self,
            "unsupported_content_ids",
            _validate_identifier_tuple("unsupported_content_ids", self.unsupported_content_ids),
        )
        object.__setattr__(
            self,
            "unsupported_reasons_by_content_id",
            _validate_reason_mapping(
                "unsupported_reasons_by_content_id",
                self.unsupported_reasons_by_content_id,
            ),
        )
        object.__setattr__(
            self,
            "activation_hash",
            _validate_optional_identifier("activation_hash", self.activation_hash),
        )

    @classmethod
    def from_armies(
        cls,
        *,
        armies: tuple[ArmyDefinition, ...],
        catalog: ArmyCatalog,
        loaded_unit_instance_ids: tuple[str, ...] | None = None,
    ) -> Self:
        validated_armies = _validate_armies(armies)
        if type(catalog) is not ArmyCatalog:
            raise GameLifecycleError("Runtime content activation requires an ArmyCatalog.")
        faction_ids: set[str] = set()
        detachment_ids: set[str] = set()
        enhancement_ids: set[str] = set()
        stratagem_ids: set[str] = set()
        datasheet_ids: set[str] = set()
        wargear_ids: set[str] = set()
        unit_ids: set[str] = set()
        for army in validated_armies:
            faction_ids.add(army.detachment_selection.faction_id)
            detachment_ids.update(army.detachment_selection.detachment_ids)
            enhancement_ids.update(army.detachment_selection.enhancement_ids)
            stratagem_ids.update(army.detachment_selection.stratagem_ids)
            enhancement_ids.update(
                assignment.enhancement_id for assignment in army.enhancement_assignments
            )
            unit_ids.update(unit.unit_instance_id for unit in army.units)
            unit_ids.update(attached.attached_unit_instance_id for attached in army.attached_units)
            for unit in army.units:
                datasheet_ids.add(unit.datasheet_id)
                for selection in unit.wargear_selections:
                    wargear_ids.update(selection.wargear_ids)
        weapon_profile_ids = _selected_weapon_profile_ids(catalog=catalog, wargear_ids=wargear_ids)
        weapon_keywords = _selected_weapon_keywords(catalog=catalog, wargear_ids=wargear_ids)
        loaded_ids = (
            set(unit_ids)
            if loaded_unit_instance_ids is None
            else set(
                _validate_identifier_tuple(
                    "loaded_unit_instance_ids",
                    loaded_unit_instance_ids,
                )
            )
        )
        return cls(
            selected_faction_ids=tuple(faction_ids),
            selected_detachment_ids=tuple(detachment_ids),
            selected_enhancement_ids=tuple(enhancement_ids),
            selected_stratagem_ids=tuple(stratagem_ids),
            selected_datasheet_ids=tuple(datasheet_ids),
            selected_wargear_ids=tuple(wargear_ids),
            selected_weapon_profile_ids=tuple(weapon_profile_ids),
            selected_weapon_keywords=tuple(weapon_keywords),
            loaded_unit_instance_ids=tuple(loaded_ids),
        )

    @classmethod
    def from_config(cls, config: object) -> Self:
        from warhammer40k_core.engine.game_state import GameConfig

        if type(config) is not GameConfig:
            raise GameLifecycleError("Runtime content activation requires a GameConfig.")
        armies = tuple(
            muster_army(catalog=config.army_catalog, request=request)
            for request in config.army_muster_requests
        )
        return cls.from_armies(armies=armies, catalog=config.army_catalog)

    def to_payload(self) -> RuntimeContentActivationPayload:
        return {
            "selected_faction_ids": list(self.selected_faction_ids),
            "selected_detachment_ids": list(self.selected_detachment_ids),
            "selected_enhancement_ids": list(self.selected_enhancement_ids),
            "selected_stratagem_ids": list(self.selected_stratagem_ids),
            "selected_datasheet_ids": list(self.selected_datasheet_ids),
            "selected_wargear_ids": list(self.selected_wargear_ids),
            "selected_weapon_profile_ids": list(self.selected_weapon_profile_ids),
            "selected_weapon_keywords": list(self.selected_weapon_keywords),
            "loaded_unit_instance_ids": list(self.loaded_unit_instance_ids),
            "reachable_content_ids": list(self.reachable_content_ids),
            "selected_module_paths": list(self.selected_module_paths),
            "source_package_ids": list(self.source_package_ids),
            "source_package_hashes": list(self.source_package_hashes),
            "selected_execution_record_ids": list(self.selected_execution_record_ids),
            "unsupported_content_ids": list(self.unsupported_content_ids),
            "unsupported_reasons_by_content_id": dict(self.unsupported_reasons_by_content_id or {}),
            "activation_hash": self.activation_hash,
        }

    @classmethod
    def from_payload(cls, payload: RuntimeContentActivationPayload) -> Self:
        return cls(
            selected_faction_ids=tuple(payload["selected_faction_ids"]),
            selected_detachment_ids=tuple(payload["selected_detachment_ids"]),
            selected_enhancement_ids=tuple(payload["selected_enhancement_ids"]),
            selected_stratagem_ids=tuple(payload["selected_stratagem_ids"]),
            selected_datasheet_ids=tuple(payload["selected_datasheet_ids"]),
            selected_wargear_ids=tuple(payload["selected_wargear_ids"]),
            selected_weapon_profile_ids=tuple(payload["selected_weapon_profile_ids"]),
            selected_weapon_keywords=tuple(payload["selected_weapon_keywords"]),
            loaded_unit_instance_ids=tuple(payload["loaded_unit_instance_ids"]),
            reachable_content_ids=tuple(payload["reachable_content_ids"]),
            selected_module_paths=tuple(payload["selected_module_paths"]),
            source_package_ids=tuple(payload["source_package_ids"]),
            source_package_hashes=tuple(payload["source_package_hashes"]),
            selected_execution_record_ids=tuple(payload["selected_execution_record_ids"]),
            unsupported_content_ids=tuple(payload["unsupported_content_ids"]),
            unsupported_reasons_by_content_id=dict(payload["unsupported_reasons_by_content_id"]),
            activation_hash=payload["activation_hash"],
        )

    def roster_content_ids(self) -> tuple[str, ...]:
        return _validate_identifier_tuple(
            "roster_content_ids",
            (
                *self.selected_faction_ids,
                *self.selected_detachment_ids,
                *self.selected_enhancement_ids,
                *self.selected_stratagem_ids,
                *self.selected_datasheet_ids,
                *self.selected_wargear_ids,
                *self.selected_weapon_profile_ids,
            ),
        )

    def with_reachable_content(
        self,
        *,
        reachable_content_ids: tuple[str, ...],
        selected_module_paths: tuple[str, ...],
        source_package_ids: tuple[str, ...],
        source_package_hashes: tuple[str, ...],
        selected_execution_record_ids: tuple[str, ...],
        unsupported_content_ids: tuple[str, ...],
        unsupported_reasons_by_content_id: Mapping[str, str],
    ) -> Self:
        resolved = type(self)(
            selected_faction_ids=self.selected_faction_ids,
            selected_detachment_ids=self.selected_detachment_ids,
            selected_enhancement_ids=self.selected_enhancement_ids,
            selected_stratagem_ids=self.selected_stratagem_ids,
            selected_datasheet_ids=self.selected_datasheet_ids,
            selected_wargear_ids=self.selected_wargear_ids,
            selected_weapon_profile_ids=self.selected_weapon_profile_ids,
            selected_weapon_keywords=self.selected_weapon_keywords,
            loaded_unit_instance_ids=self.loaded_unit_instance_ids,
            reachable_content_ids=reachable_content_ids,
            selected_module_paths=selected_module_paths,
            source_package_ids=source_package_ids,
            source_package_hashes=source_package_hashes,
            selected_execution_record_ids=selected_execution_record_ids,
            unsupported_content_ids=unsupported_content_ids,
            unsupported_reasons_by_content_id=unsupported_reasons_by_content_id,
            activation_hash="",
        )
        return type(self)(
            selected_faction_ids=resolved.selected_faction_ids,
            selected_detachment_ids=resolved.selected_detachment_ids,
            selected_enhancement_ids=resolved.selected_enhancement_ids,
            selected_stratagem_ids=resolved.selected_stratagem_ids,
            selected_datasheet_ids=resolved.selected_datasheet_ids,
            selected_wargear_ids=resolved.selected_wargear_ids,
            selected_weapon_profile_ids=resolved.selected_weapon_profile_ids,
            selected_weapon_keywords=resolved.selected_weapon_keywords,
            loaded_unit_instance_ids=resolved.loaded_unit_instance_ids,
            reachable_content_ids=resolved.reachable_content_ids,
            selected_module_paths=resolved.selected_module_paths,
            source_package_ids=resolved.source_package_ids,
            source_package_hashes=resolved.source_package_hashes,
            selected_execution_record_ids=resolved.selected_execution_record_ids,
            unsupported_content_ids=resolved.unsupported_content_ids,
            unsupported_reasons_by_content_id=resolved.unsupported_reasons_by_content_id,
            activation_hash=_activation_hash(resolved),
        )


def _validate_armies(armies: object) -> tuple[ArmyDefinition, ...]:
    if type(armies) is not tuple:
        raise GameLifecycleError("Runtime content activation armies must be a tuple.")
    validated: list[ArmyDefinition] = []
    seen: set[str] = set()
    for army in cast(tuple[object, ...], armies):
        if type(army) is not ArmyDefinition:
            raise GameLifecycleError(
                "Runtime content activation armies must contain ArmyDefinition values."
            )
        if army.army_id in seen:
            raise GameLifecycleError("Runtime content activation army IDs must be unique.")
        seen.add(army.army_id)
        validated.append(army)
    return tuple(sorted(validated, key=lambda army: army.army_id))


def _selected_weapon_profile_ids(
    *,
    catalog: ArmyCatalog,
    wargear_ids: set[str],
) -> tuple[str, ...]:
    selected: set[str] = set()
    for wargear_id in wargear_ids:
        wargear = _wargear_by_id(catalog=catalog, wargear_id=wargear_id)
        selected.update(profile.profile_id for profile in wargear.weapon_profiles)
    return tuple(selected)


def _selected_weapon_keywords(
    *,
    catalog: ArmyCatalog,
    wargear_ids: set[str],
) -> tuple[str, ...]:
    selected: set[str] = set()
    for wargear_id in wargear_ids:
        wargear = _wargear_by_id(catalog=catalog, wargear_id=wargear_id)
        for profile in wargear.weapon_profiles:
            selected.update(_canonical_keyword(keyword.value) for keyword in profile.keywords)
            selected.update(
                _canonical_keyword(ability.ability_kind.value) for ability in profile.abilities
            )
    return tuple(selected)


def _wargear_by_id(*, catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_id = _validate_identifier("wargear_id", wargear_id)
    for wargear in catalog.wargear:
        if wargear.wargear_id == requested_id:
            return wargear
    raise GameLifecycleError("Runtime content activation references unknown wargear.")


def _validate_identifier_tuple(field_name: str, values: object) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise GameLifecycleError(f"Runtime content {field_name} must be a tuple.")
    identifiers: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise GameLifecycleError(f"Runtime content {field_name} must not contain duplicates.")
        seen.add(identifier)
        identifiers.append(identifier)
    return tuple(sorted(identifiers))


def _validate_reason_mapping(
    field_name: str,
    value: object | None,
) -> Mapping[str, str]:
    if value is None:
        return MappingProxyType({})
    if not isinstance(value, Mapping):
        raise GameLifecycleError(f"Runtime content {field_name} must be a mapping.")
    reasons: dict[str, str] = {}
    for raw_key, raw_reason in cast(Mapping[object, object], value).items():
        content_id = _validate_identifier(f"{field_name} key", raw_key)
        reason = _validate_identifier(f"{field_name} value", raw_reason)
        if content_id in reasons:
            raise GameLifecycleError(f"Runtime content {field_name} keys must be unique.")
        reasons[content_id] = reason
    return MappingProxyType(dict(sorted(reasons.items())))


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Runtime content {field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise GameLifecycleError(f"Runtime content {field_name} must not be empty.")
    return stripped


def _validate_optional_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise GameLifecycleError(f"Runtime content {field_name} must be a string.")
    return value.strip()


def _canonical_keyword(value: str) -> str:
    return _validate_identifier("keyword", value).upper().replace(" ", "_").replace("-", "_")


def _activation_hash(activation: RuntimeContentActivation) -> str:
    payload = activation.to_payload()
    payload["activation_hash"] = ""
    encoded = canonical_json(cast(JsonValue, payload)).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()
