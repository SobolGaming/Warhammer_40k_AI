from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicError,
    CharacteristicValue,
    CharacteristicValuePayload,
    characteristic_from_token,
)


class DatasheetCatalogError(ValueError):
    """Raised when datasheet catalog data violates CORE V2 invariants."""


class BaseSizeKind(StrEnum):
    CIRCULAR = "circular"
    OVAL = "oval"
    RECTANGULAR = "rectangular"


class CatalogAbilitySupport(StrEnum):
    DESCRIPTOR_ONLY = "descriptor_only"
    UNSUPPORTED = "unsupported"


CatalogParameterValue = int | float | str | bool

REQUIRED_MODEL_CHARACTERISTICS = frozenset(
    {
        Characteristic.MOVEMENT,
        Characteristic.TOUGHNESS,
        Characteristic.SAVE,
        Characteristic.WOUNDS,
        Characteristic.LEADERSHIP,
        Characteristic.OBJECTIVE_CONTROL,
        Characteristic.WEAPON_SKILL,
        Characteristic.BALLISTIC_SKILL,
    }
)


class BaseSizeDefinitionPayload(TypedDict):
    kind: str
    diameter_mm: float | None
    length_mm: float | None
    width_mm: float | None


class ModelProfileDefinitionPayload(TypedDict):
    model_profile_id: str
    name: str
    characteristics: list[CharacteristicValuePayload]
    base_size: BaseSizeDefinitionPayload
    source_ids: list[str]


class UnitCompositionDefinitionPayload(TypedDict):
    model_profile_id: str
    min_models: int
    max_models: int


class DatasheetKeywordSetPayload(TypedDict):
    keywords: list[str]
    faction_keywords: list[str]


class DatasheetWargearOptionPayload(TypedDict):
    option_id: str
    model_profile_id: str
    default_wargear_ids: list[str]
    allowed_wargear_ids: list[str]
    min_selections: int
    max_selections: int


class DatasheetAbilityDescriptorPayload(TypedDict):
    ability_id: str
    name: str
    source_id: str
    support: str
    timing_tags: list[str]
    parameter_tokens: list[str]


class DatasheetDefinitionPayload(TypedDict):
    datasheet_id: str
    name: str
    keywords: DatasheetKeywordSetPayload
    model_profiles: list[ModelProfileDefinitionPayload]
    composition: list[UnitCompositionDefinitionPayload]
    wargear_options: list[DatasheetWargearOptionPayload]
    abilities: list[DatasheetAbilityDescriptorPayload]
    source_ids: list[str]


@dataclass(frozen=True, slots=True)
class BaseSizeDefinition:
    kind: BaseSizeKind
    diameter_mm: float | None = None
    length_mm: float | None = None
    width_mm: float | None = None

    def __post_init__(self) -> None:
        kind = base_size_kind_from_token(self.kind)
        object.__setattr__(self, "kind", kind)

        if kind is BaseSizeKind.CIRCULAR:
            diameter_mm = _validate_positive_number(
                "BaseSizeDefinition diameter_mm",
                self.diameter_mm,
            )
            if self.length_mm is not None or self.width_mm is not None:
                raise DatasheetCatalogError(
                    "Circular BaseSizeDefinition must include only diameter_mm."
                )
            object.__setattr__(self, "diameter_mm", diameter_mm)
            return

        if self.diameter_mm is not None:
            raise DatasheetCatalogError(
                "Non-circular BaseSizeDefinition must not include diameter_mm."
            )
        length_mm = _validate_positive_number("BaseSizeDefinition length_mm", self.length_mm)
        width_mm = _validate_positive_number("BaseSizeDefinition width_mm", self.width_mm)
        if kind is BaseSizeKind.OVAL and length_mm < width_mm:
            raise DatasheetCatalogError("Oval BaseSizeDefinition length must be at least width.")
        object.__setattr__(self, "length_mm", length_mm)
        object.__setattr__(self, "width_mm", width_mm)

    @classmethod
    def circular(cls, diameter_mm: float) -> Self:
        return cls(kind=BaseSizeKind.CIRCULAR, diameter_mm=diameter_mm)

    @classmethod
    def oval(cls, *, length_mm: float, width_mm: float) -> Self:
        return cls(kind=BaseSizeKind.OVAL, length_mm=length_mm, width_mm=width_mm)

    @classmethod
    def rectangular(cls, *, length_mm: float, width_mm: float) -> Self:
        return cls(kind=BaseSizeKind.RECTANGULAR, length_mm=length_mm, width_mm=width_mm)

    def to_payload(self) -> BaseSizeDefinitionPayload:
        return {
            "kind": self.kind.value,
            "diameter_mm": self.diameter_mm,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
        }

    @classmethod
    def from_payload(cls, payload: BaseSizeDefinitionPayload) -> Self:
        return cls(
            kind=base_size_kind_from_token(payload["kind"]),
            diameter_mm=payload["diameter_mm"],
            length_mm=payload["length_mm"],
            width_mm=payload["width_mm"],
        )


@dataclass(frozen=True, slots=True)
class ModelProfileDefinition:
    model_profile_id: str
    name: str
    characteristics: tuple[CharacteristicValue, ...]
    base_size: BaseSizeDefinition
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_unprefixed_identifier(
                "ModelProfileDefinition model_profile_id",
                self.model_profile_id,
                "model-profile:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("ModelProfileDefinition name", self.name),
        )
        characteristics = _canonical_characteristic_values(self.characteristics)
        if not characteristics:
            raise DatasheetCatalogError("ModelProfileDefinition characteristics must not be empty.")
        _validate_required_model_characteristics(characteristics)
        object.__setattr__(self, "characteristics", characteristics)
        if type(self.base_size) is not BaseSizeDefinition:
            raise DatasheetCatalogError(
                "ModelProfileDefinition base_size must be a BaseSizeDefinition."
            )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("ModelProfileDefinition source_ids", self.source_ids),
        )

    def characteristic(self, characteristic: Characteristic) -> CharacteristicValue:
        requested_characteristic = _characteristic_from_token(characteristic)
        for value in self.characteristics:
            if value.characteristic is requested_characteristic:
                return value
        raise DatasheetCatalogError("ModelProfileDefinition characteristic was not found.")

    def to_payload(self) -> ModelProfileDefinitionPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "name": self.name,
            "characteristics": [value.to_payload() for value in self.characteristics],
            "base_size": self.base_size.to_payload(),
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: ModelProfileDefinitionPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            name=payload["name"],
            characteristics=tuple(
                _characteristic_value_from_payload(value) for value in payload["characteristics"]
            ),
            base_size=BaseSizeDefinition.from_payload(payload["base_size"]),
            source_ids=tuple(payload["source_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitCompositionDefinition:
    model_profile_id: str
    min_models: int
    max_models: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier(
                "UnitCompositionDefinition model_profile_id", self.model_profile_id
            ),
        )
        min_models = _validate_positive_int("UnitCompositionDefinition min_models", self.min_models)
        max_models = _validate_positive_int("UnitCompositionDefinition max_models", self.max_models)
        if max_models < min_models:
            raise DatasheetCatalogError(
                "UnitCompositionDefinition max_models must be at least min_models."
            )
        object.__setattr__(self, "min_models", min_models)
        object.__setattr__(self, "max_models", max_models)

    def to_payload(self) -> UnitCompositionDefinitionPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "min_models": self.min_models,
            "max_models": self.max_models,
        }

    @classmethod
    def from_payload(cls, payload: UnitCompositionDefinitionPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            min_models=payload["min_models"],
            max_models=payload["max_models"],
        )


@dataclass(frozen=True, slots=True)
class DatasheetKeywordSet:
    keywords: tuple[str, ...] = ()
    faction_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "keywords",
            _validate_identifier_tuple("DatasheetKeywordSet keywords", self.keywords),
        )
        object.__setattr__(
            self,
            "faction_keywords",
            _validate_identifier_tuple(
                "DatasheetKeywordSet faction_keywords",
                self.faction_keywords,
            ),
        )

    def to_payload(self) -> DatasheetKeywordSetPayload:
        return {
            "keywords": list(self.keywords),
            "faction_keywords": list(self.faction_keywords),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetKeywordSetPayload) -> Self:
        return cls(
            keywords=tuple(payload["keywords"]),
            faction_keywords=tuple(payload["faction_keywords"]),
        )


@dataclass(frozen=True, slots=True)
class DatasheetWargearOption:
    option_id: str
    model_profile_id: str
    default_wargear_ids: tuple[str, ...]
    allowed_wargear_ids: tuple[str, ...]
    min_selections: int = 0
    max_selections: int = 1

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_unprefixed_identifier(
                "DatasheetWargearOption option_id",
                self.option_id,
                "wargear-option:",
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier("DatasheetWargearOption model_profile_id", self.model_profile_id),
        )
        default_wargear_ids = _validate_identifier_tuple(
            "DatasheetWargearOption default_wargear_ids",
            self.default_wargear_ids,
        )
        allowed_wargear_ids = _validate_identifier_tuple(
            "DatasheetWargearOption allowed_wargear_ids",
            self.allowed_wargear_ids,
        )
        if not allowed_wargear_ids:
            raise DatasheetCatalogError(
                "DatasheetWargearOption allowed_wargear_ids must not be empty."
            )
        allowed_set = set(allowed_wargear_ids)
        for wargear_id in default_wargear_ids:
            if wargear_id not in allowed_set:
                raise DatasheetCatalogError(
                    "DatasheetWargearOption default wargear must be allowed."
                )
        min_selections = _validate_non_negative_int(
            "DatasheetWargearOption min_selections",
            self.min_selections,
        )
        max_selections = _validate_positive_int(
            "DatasheetWargearOption max_selections",
            self.max_selections,
        )
        if max_selections < min_selections:
            raise DatasheetCatalogError(
                "DatasheetWargearOption max_selections must be at least min_selections."
            )
        if len(default_wargear_ids) > max_selections:
            raise DatasheetCatalogError(
                "DatasheetWargearOption default_wargear_ids must not exceed max_selections."
            )
        object.__setattr__(self, "default_wargear_ids", default_wargear_ids)
        object.__setattr__(self, "allowed_wargear_ids", allowed_wargear_ids)
        object.__setattr__(self, "min_selections", min_selections)
        object.__setattr__(self, "max_selections", max_selections)

    def to_payload(self) -> DatasheetWargearOptionPayload:
        return {
            "option_id": self.option_id,
            "model_profile_id": self.model_profile_id,
            "default_wargear_ids": list(self.default_wargear_ids),
            "allowed_wargear_ids": list(self.allowed_wargear_ids),
            "min_selections": self.min_selections,
            "max_selections": self.max_selections,
        }

    @classmethod
    def from_payload(cls, payload: DatasheetWargearOptionPayload) -> Self:
        return cls(
            option_id=payload["option_id"],
            model_profile_id=payload["model_profile_id"],
            default_wargear_ids=tuple(payload["default_wargear_ids"]),
            allowed_wargear_ids=tuple(payload["allowed_wargear_ids"]),
            min_selections=payload["min_selections"],
            max_selections=payload["max_selections"],
        )


@dataclass(frozen=True, slots=True)
class DatasheetAbilityDescriptor:
    ability_id: str
    name: str
    source_id: str
    support: CatalogAbilitySupport
    timing_tags: tuple[str, ...] = ()
    parameter_tokens: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "ability_id",
            _validate_unprefixed_identifier(
                "DatasheetAbilityDescriptor ability_id",
                self.ability_id,
                "ability:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("DatasheetAbilityDescriptor name", self.name),
        )
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("DatasheetAbilityDescriptor source_id", self.source_id),
        )
        object.__setattr__(self, "support", catalog_ability_support_from_token(self.support))
        object.__setattr__(
            self,
            "timing_tags",
            _validate_identifier_tuple(
                "DatasheetAbilityDescriptor timing_tags",
                self.timing_tags,
            ),
        )
        object.__setattr__(
            self,
            "parameter_tokens",
            _validate_identifier_tuple(
                "DatasheetAbilityDescriptor parameter_tokens",
                self.parameter_tokens,
            ),
        )

    def to_payload(self) -> DatasheetAbilityDescriptorPayload:
        return {
            "ability_id": self.ability_id,
            "name": self.name,
            "source_id": self.source_id,
            "support": self.support.value,
            "timing_tags": list(self.timing_tags),
            "parameter_tokens": list(self.parameter_tokens),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetAbilityDescriptorPayload) -> Self:
        return cls(
            ability_id=payload["ability_id"],
            name=payload["name"],
            source_id=payload["source_id"],
            support=catalog_ability_support_from_token(payload["support"]),
            timing_tags=tuple(payload["timing_tags"]),
            parameter_tokens=tuple(payload["parameter_tokens"]),
        )


@dataclass(frozen=True, slots=True)
class DatasheetDefinition:
    datasheet_id: str
    name: str
    keywords: DatasheetKeywordSet
    model_profiles: tuple[ModelProfileDefinition, ...]
    composition: tuple[UnitCompositionDefinition, ...]
    wargear_options: tuple[DatasheetWargearOption, ...] = ()
    abilities: tuple[DatasheetAbilityDescriptor, ...] = ()
    source_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_unprefixed_identifier(
                "DatasheetDefinition datasheet_id",
                self.datasheet_id,
                "datasheet:",
            ),
        )
        object.__setattr__(
            self,
            "name",
            _validate_identifier("DatasheetDefinition name", self.name),
        )
        if type(self.keywords) is not DatasheetKeywordSet:
            raise DatasheetCatalogError("DatasheetDefinition keywords must be a keyword set.")
        model_profiles = _validate_model_profile_tuple(
            "DatasheetDefinition model_profiles",
            self.model_profiles,
        )
        composition = _validate_composition_tuple(
            "DatasheetDefinition composition",
            self.composition,
        )
        model_profile_ids = {profile.model_profile_id for profile in model_profiles}
        for composition_part in composition:
            if composition_part.model_profile_id not in model_profile_ids:
                raise DatasheetCatalogError(
                    "DatasheetDefinition composition references an unknown model profile."
                )
        wargear_options = _validate_wargear_option_tuple(
            "DatasheetDefinition wargear_options",
            self.wargear_options,
        )
        for option in wargear_options:
            if option.model_profile_id not in model_profile_ids:
                raise DatasheetCatalogError(
                    "DatasheetDefinition wargear option references an unknown model profile."
                )
        abilities = _validate_ability_descriptor_tuple(
            "DatasheetDefinition abilities",
            self.abilities,
        )
        object.__setattr__(
            self,
            "model_profiles",
            tuple(sorted(model_profiles, key=lambda profile: profile.model_profile_id)),
        )
        object.__setattr__(
            self,
            "composition",
            tuple(sorted(composition, key=lambda value: value.model_profile_id)),
        )
        object.__setattr__(
            self,
            "wargear_options",
            tuple(sorted(wargear_options, key=lambda option: option.option_id)),
        )
        object.__setattr__(
            self,
            "abilities",
            tuple(sorted(abilities, key=lambda ability: ability.ability_id)),
        )
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple("DatasheetDefinition source_ids", self.source_ids),
        )

    def stable_identity(self) -> str:
        return f"datasheet:{self.datasheet_id}"

    def model_profile_by_id(self, model_profile_id: str) -> ModelProfileDefinition:
        requested_id = _validate_identifier("model_profile_id", model_profile_id)
        for model_profile in self.model_profiles:
            if model_profile.model_profile_id == requested_id:
                return model_profile
        raise DatasheetCatalogError("DatasheetDefinition model_profile_id was not found.")

    def to_payload(self) -> DatasheetDefinitionPayload:
        return {
            "datasheet_id": self.datasheet_id,
            "name": self.name,
            "keywords": self.keywords.to_payload(),
            "model_profiles": [profile.to_payload() for profile in self.model_profiles],
            "composition": [part.to_payload() for part in self.composition],
            "wargear_options": [option.to_payload() for option in self.wargear_options],
            "abilities": [ability.to_payload() for ability in self.abilities],
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: DatasheetDefinitionPayload) -> Self:
        return cls(
            datasheet_id=payload["datasheet_id"],
            name=payload["name"],
            keywords=DatasheetKeywordSet.from_payload(payload["keywords"]),
            model_profiles=tuple(
                ModelProfileDefinition.from_payload(profile)
                for profile in payload["model_profiles"]
            ),
            composition=tuple(
                UnitCompositionDefinition.from_payload(part) for part in payload["composition"]
            ),
            wargear_options=tuple(
                DatasheetWargearOption.from_payload(option) for option in payload["wargear_options"]
            ),
            abilities=tuple(
                DatasheetAbilityDescriptor.from_payload(ability) for ability in payload["abilities"]
            ),
            source_ids=tuple(payload["source_ids"]),
        )


def base_size_kind_from_token(token: object) -> BaseSizeKind:
    if type(token) is BaseSizeKind:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("BaseSizeKind token must be a string.")
    try:
        return BaseSizeKind(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported BaseSizeKind token: {token}.") from exc


def catalog_ability_support_from_token(token: object) -> CatalogAbilitySupport:
    if type(token) is CatalogAbilitySupport:
        return token
    if type(token) is not str:
        raise DatasheetCatalogError("CatalogAbilitySupport token must be a string.")
    try:
        return CatalogAbilitySupport(token)
    except ValueError as exc:
        raise DatasheetCatalogError(f"Unsupported CatalogAbilitySupport token: {token}.") from exc


def _characteristic_from_token(token: object) -> Characteristic:
    if type(token) is Characteristic:
        return token
    try:
        return characteristic_from_token(token)
    except CharacteristicError as exc:
        raise DatasheetCatalogError("Characteristic token is invalid.") from exc


def _characteristic_value_from_payload(payload: CharacteristicValuePayload) -> CharacteristicValue:
    try:
        return CharacteristicValue.from_payload(payload)
    except CharacteristicError as exc:
        raise DatasheetCatalogError("CharacteristicValue payload is invalid.") from exc


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise DatasheetCatalogError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    return stripped


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise DatasheetCatalogError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[str] = []
    for value in values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    return tuple(sorted(validated))


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise DatasheetCatalogError(f"{field_name} must be a number.")
    number = float(value)
    if not math.isfinite(number):
        raise DatasheetCatalogError(f"{field_name} must be finite.")
    if number <= 0.0:
        raise DatasheetCatalogError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise DatasheetCatalogError(f"{field_name} must be an integer.")
    if value < 1:
        raise DatasheetCatalogError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise DatasheetCatalogError(f"{field_name} must be an integer.")
    if value < 0:
        raise DatasheetCatalogError(f"{field_name} must not be negative.")
    return value


def _canonical_characteristic_values(
    values: tuple[CharacteristicValue, ...],
) -> tuple[CharacteristicValue, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError("ModelProfileDefinition characteristics must be a tuple.")
    seen: set[Characteristic] = set()
    validated: list[CharacteristicValue] = []
    for value in values:
        if type(value) is not CharacteristicValue:
            raise DatasheetCatalogError(
                "ModelProfileDefinition characteristics must be CharacteristicValue values."
            )
        if value.characteristic in seen:
            raise DatasheetCatalogError(
                "ModelProfileDefinition characteristics must not contain duplicates."
            )
        seen.add(value.characteristic)
        validated.append(value)
    return tuple(sorted(validated, key=lambda value: value.characteristic.value))


def _validate_required_model_characteristics(
    values: tuple[CharacteristicValue, ...],
) -> None:
    present = {value.characteristic for value in values}
    missing = tuple(
        sorted(
            REQUIRED_MODEL_CHARACTERISTICS.difference(present),
            key=lambda characteristic: characteristic.value,
        )
    )
    if missing:
        missing_tokens = ", ".join(characteristic.value for characteristic in missing)
        raise DatasheetCatalogError(
            f"ModelProfileDefinition missing required characteristics: {missing_tokens}."
        )


def _validate_model_profile_tuple(
    field_name: str,
    values: tuple[ModelProfileDefinition, ...],
) -> tuple[ModelProfileDefinition, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[ModelProfileDefinition] = []
    for value in values:
        if type(value) is not ModelProfileDefinition:
            raise DatasheetCatalogError(f"{field_name} must contain model profile definitions.")
        if value.model_profile_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(validated)


def _validate_composition_tuple(
    field_name: str,
    values: tuple[UnitCompositionDefinition, ...],
) -> tuple[UnitCompositionDefinition, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    if not values:
        raise DatasheetCatalogError(f"{field_name} must not be empty.")
    seen: set[str] = set()
    validated: list[UnitCompositionDefinition] = []
    for value in values:
        if type(value) is not UnitCompositionDefinition:
            raise DatasheetCatalogError(f"{field_name} must contain composition definitions.")
        if value.model_profile_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate model profiles.")
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(validated)


def _validate_wargear_option_tuple(
    field_name: str,
    values: tuple[DatasheetWargearOption, ...],
) -> tuple[DatasheetWargearOption, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[DatasheetWargearOption] = []
    for value in values:
        if type(value) is not DatasheetWargearOption:
            raise DatasheetCatalogError(f"{field_name} must contain wargear option definitions.")
        if value.option_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate option IDs.")
        seen.add(value.option_id)
        validated.append(value)
    return tuple(validated)


def _validate_ability_descriptor_tuple(
    field_name: str,
    values: tuple[DatasheetAbilityDescriptor, ...],
) -> tuple[DatasheetAbilityDescriptor, ...]:
    if type(values) is not tuple:
        raise DatasheetCatalogError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    validated: list[DatasheetAbilityDescriptor] = []
    for value in values:
        if type(value) is not DatasheetAbilityDescriptor:
            raise DatasheetCatalogError(f"{field_name} must contain ability descriptors.")
        if value.ability_id in seen:
            raise DatasheetCatalogError(f"{field_name} must not contain duplicate ability IDs.")
        seen.add(value.ability_id)
        validated.append(value)
    return tuple(validated)
