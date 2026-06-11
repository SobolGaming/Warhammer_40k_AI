from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogError
from warhammer40k_core.core.attributes import (
    Characteristic,
    CharacteristicValue,
    CharacteristicValuePayload,
)
from warhammer40k_core.core.datasheet import (
    BaseSizeDefinition,
    BaseSizeDefinitionPayload,
    DatasheetDefinition,
    ModelProfileDefinition,
)
from warhammer40k_core.core.model_geometry_catalog import ModelGeometryCatalogRecord
from warhammer40k_core.engine.list_validation import (
    ListValidationError,
    UnitMusterSelection,
    WargearSelection,
    WargearSelectionPayload,
    resolve_model_profile_selections,
    resolve_wargear_selections,
)
from warhammer40k_core.geometry.model_geometry import (
    GeometrySourceKind,
    ModelGeometry,
    ModelGeometryPayload,
)
from warhammer40k_core.geometry.pose import GeometryError


class UnitFactoryError(ValueError):
    """Raised when runtime unit instantiation violates CORE V2 invariants."""


class ModelInstancePayload(TypedDict):
    model_instance_id: str
    datasheet_id: str
    model_profile_id: str
    name: str
    characteristics: list[CharacteristicValuePayload]
    base_size: BaseSizeDefinitionPayload
    geometry: ModelGeometryPayload
    starting_wounds: int
    wounds_remaining: int
    source_ids: list[str]


class UnitInstancePayload(TypedDict):
    unit_instance_id: str
    datasheet_id: str
    name: str
    keywords: list[str]
    faction_keywords: list[str]
    datasheet_source_ids: list[str]
    own_models: list[ModelInstancePayload]
    wargear_selections: list[WargearSelectionPayload]


@dataclass(frozen=True, slots=True)
class ModelInstance:
    model_instance_id: str
    datasheet_id: str
    model_profile_id: str
    name: str
    characteristics: tuple[CharacteristicValue, ...]
    base_size: BaseSizeDefinition
    geometry: ModelGeometry
    starting_wounds: int
    wounds_remaining: int
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_instance_id",
            _validate_unprefixed_identifier(
                "ModelInstance model_instance_id",
                self.model_instance_id,
                "model:",
            ),
        )
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_unprefixed_identifier(
                "ModelInstance datasheet_id",
                self.datasheet_id,
                "datasheet:",
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_unprefixed_identifier(
                "ModelInstance model_profile_id",
                self.model_profile_id,
                "model-profile:",
            ),
        )
        object.__setattr__(self, "name", _validate_identifier("ModelInstance name", self.name))
        characteristics = _validate_characteristics(self.characteristics)
        object.__setattr__(self, "characteristics", characteristics)
        if type(self.base_size) is not BaseSizeDefinition:
            raise UnitFactoryError("ModelInstance base_size must be a BaseSizeDefinition.")
        if type(self.geometry) is not ModelGeometry:
            raise UnitFactoryError("ModelInstance geometry must be a ModelGeometry.")
        _validate_geometry_matches_base_size(base_size=self.base_size, geometry=self.geometry)
        starting_wounds = _validate_positive_int(
            "ModelInstance starting_wounds",
            self.starting_wounds,
        )
        wounds_remaining = _validate_non_negative_int(
            "ModelInstance wounds_remaining",
            self.wounds_remaining,
        )
        if wounds_remaining > starting_wounds:
            raise UnitFactoryError(
                "ModelInstance wounds_remaining must not exceed starting_wounds."
            )
        object.__setattr__(self, "starting_wounds", starting_wounds)
        object.__setattr__(self, "wounds_remaining", wounds_remaining)
        object.__setattr__(
            self,
            "source_ids",
            _validate_identifier_tuple(
                "ModelInstance source_ids",
                self.source_ids,
                min_length=1,
            ),
        )

    def stable_identity(self) -> str:
        return f"model:{self.model_instance_id}"

    @property
    def is_alive(self) -> bool:
        return self.wounds_remaining > 0

    def to_payload(self) -> ModelInstancePayload:
        return {
            "model_instance_id": self.model_instance_id,
            "datasheet_id": self.datasheet_id,
            "model_profile_id": self.model_profile_id,
            "name": self.name,
            "characteristics": [value.to_payload() for value in self.characteristics],
            "base_size": self.base_size.to_payload(),
            "geometry": self.geometry.to_payload(),
            "starting_wounds": self.starting_wounds,
            "wounds_remaining": self.wounds_remaining,
            "source_ids": list(self.source_ids),
        }

    @classmethod
    def from_payload(cls, payload: ModelInstancePayload) -> Self:
        return cls(
            model_instance_id=payload["model_instance_id"],
            datasheet_id=payload["datasheet_id"],
            model_profile_id=payload["model_profile_id"],
            name=payload["name"],
            characteristics=tuple(
                CharacteristicValue.from_payload(value) for value in payload["characteristics"]
            ),
            base_size=BaseSizeDefinition.from_payload(payload["base_size"]),
            geometry=ModelGeometry.from_payload(payload["geometry"]),
            starting_wounds=payload["starting_wounds"],
            wounds_remaining=payload["wounds_remaining"],
            source_ids=tuple(payload["source_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitInstance:
    unit_instance_id: str
    datasheet_id: str
    name: str
    keywords: tuple[str, ...]
    faction_keywords: tuple[str, ...]
    datasheet_source_ids: tuple[str, ...]
    own_models: tuple[ModelInstance, ...]
    wargear_selections: tuple[WargearSelection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_instance_id",
            _validate_unprefixed_identifier(
                "UnitInstance unit_instance_id",
                self.unit_instance_id,
                "unit:",
            ),
        )
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_unprefixed_identifier(
                "UnitInstance datasheet_id",
                self.datasheet_id,
                "datasheet:",
            ),
        )
        object.__setattr__(self, "name", _validate_identifier("UnitInstance name", self.name))
        object.__setattr__(
            self,
            "keywords",
            _validate_identifier_tuple("UnitInstance keywords", self.keywords, min_length=0),
        )
        object.__setattr__(
            self,
            "faction_keywords",
            _validate_identifier_tuple(
                "UnitInstance faction_keywords",
                self.faction_keywords,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "datasheet_source_ids",
            _validate_identifier_tuple(
                "UnitInstance datasheet_source_ids",
                self.datasheet_source_ids,
                min_length=1,
            ),
        )
        own_models = _validate_model_instance_tuple("UnitInstance own_models", self.own_models)
        _validate_unique_model_instance_ids(own_models)
        _validate_model_instance_links(unit_instance=self, own_models=own_models)
        object.__setattr__(self, "own_models", own_models)
        wargear_selections = _validate_wargear_selection_tuple(
            "UnitInstance wargear_selections",
            self.wargear_selections,
        )
        object.__setattr__(self, "wargear_selections", wargear_selections)

    def stable_identity(self) -> str:
        return f"unit:{self.unit_instance_id}"

    def own_model_ids(self) -> tuple[str, ...]:
        return tuple(model.model_instance_id for model in self.own_models)

    def alive_own_models(self) -> tuple[ModelInstance, ...]:
        return tuple(model for model in self.own_models if model.is_alive)

    def to_payload(self) -> UnitInstancePayload:
        return {
            "unit_instance_id": self.unit_instance_id,
            "datasheet_id": self.datasheet_id,
            "name": self.name,
            "keywords": list(self.keywords),
            "faction_keywords": list(self.faction_keywords),
            "datasheet_source_ids": list(self.datasheet_source_ids),
            "own_models": [model.to_payload() for model in self.own_models],
            "wargear_selections": [selection.to_payload() for selection in self.wargear_selections],
        }

    @classmethod
    def from_payload(cls, payload: UnitInstancePayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            datasheet_id=payload["datasheet_id"],
            name=payload["name"],
            keywords=tuple(payload["keywords"]),
            faction_keywords=tuple(payload["faction_keywords"]),
            datasheet_source_ids=tuple(payload["datasheet_source_ids"]),
            own_models=tuple(ModelInstance.from_payload(model) for model in payload["own_models"]),
            wargear_selections=tuple(
                WargearSelection.from_payload(selection)
                for selection in payload["wargear_selections"]
            ),
        )


@dataclass(frozen=True, slots=True)
class UnitFactory:
    catalog: ArmyCatalog
    model_geometries: tuple[ModelGeometryCatalogRecord, ...] = ()

    def __post_init__(self) -> None:
        if type(self.catalog) is not ArmyCatalog:
            raise UnitFactoryError("UnitFactory catalog must be an ArmyCatalog.")
        model_geometries = _validate_model_geometry_catalog_records(
            "UnitFactory model_geometries",
            self.model_geometries,
        )
        _validate_model_geometry_records_reference_catalog(
            catalog=self.catalog,
            model_geometries=model_geometries,
        )
        object.__setattr__(self, "model_geometries", model_geometries)

    def instantiate_unit(
        self,
        *,
        army_id: str,
        selection: UnitMusterSelection,
        datasheet: DatasheetDefinition,
    ) -> UnitInstance:
        army_id = _validate_unprefixed_identifier("army_id", army_id, "army:")
        if type(selection) is not UnitMusterSelection:
            raise UnitFactoryError("selection must be a UnitMusterSelection.")
        if type(datasheet) is not DatasheetDefinition:
            raise UnitFactoryError("datasheet must be a DatasheetDefinition.")
        if datasheet.datasheet_id != selection.datasheet_id:
            raise UnitFactoryError("UnitMusterSelection datasheet_id does not match datasheet.")
        datasheet = self._catalog_datasheet(datasheet)
        try:
            model_profile_selections = resolve_model_profile_selections(
                datasheet=datasheet,
                selections=selection.model_profile_selections,
            )
            wargear_selections = resolve_wargear_selections(
                catalog=self.catalog,
                datasheet=datasheet,
                requested_selections=selection.wargear_selections,
            )
        except ListValidationError as exc:
            raise UnitFactoryError("UnitMusterSelection is invalid.") from exc
        own_models: list[ModelInstance] = []
        for profile_selection in model_profile_selections:
            profile = datasheet.model_profile_by_id(profile_selection.model_profile_id)
            own_models.extend(
                _instantiate_models_for_profile(
                    army_id=army_id,
                    unit_selection_id=selection.unit_selection_id,
                    datasheet=datasheet,
                    profile=profile,
                    model_count=profile_selection.model_count,
                    geometry_record=self._catalog_model_geometry(profile.model_profile_id),
                )
            )
        return UnitInstance(
            unit_instance_id=f"{army_id}:{selection.unit_selection_id}",
            datasheet_id=datasheet.datasheet_id,
            name=datasheet.name,
            keywords=datasheet.keywords.keywords,
            faction_keywords=datasheet.keywords.faction_keywords,
            datasheet_source_ids=datasheet.source_ids,
            own_models=tuple(own_models),
            wargear_selections=wargear_selections,
        )

    def _catalog_datasheet(self, datasheet: DatasheetDefinition) -> DatasheetDefinition:
        try:
            catalog_datasheet = self.catalog.datasheet_by_id(datasheet.datasheet_id)
        except ArmyCatalogError as exc:
            raise UnitFactoryError("datasheet must exist in the factory catalog.") from exc
        if catalog_datasheet.to_payload() != datasheet.to_payload():
            raise UnitFactoryError("datasheet must match the factory catalog definition.")
        return catalog_datasheet

    def _catalog_model_geometry(self, model_profile_id: str) -> ModelGeometryCatalogRecord | None:
        requested_model_profile_id = _validate_unprefixed_identifier(
            "model_profile_id",
            model_profile_id,
            "model-profile:",
        )
        for record in self.model_geometries:
            if record.model_profile_id == requested_model_profile_id:
                return record
        if self.model_geometries:
            raise UnitFactoryError("Catalog model geometry is incomplete for selected profile.")
        return None


def _instantiate_models_for_profile(
    *,
    army_id: str,
    unit_selection_id: str,
    datasheet: DatasheetDefinition,
    profile: ModelProfileDefinition,
    model_count: int,
    geometry_record: ModelGeometryCatalogRecord | None,
) -> tuple[ModelInstance, ...]:
    starting_wounds = profile.characteristic(Characteristic.WOUNDS).final
    source_ids = _merge_source_ids(datasheet.source_ids, profile.source_ids)
    geometry = _model_geometry_for_profile(
        datasheet=datasheet,
        profile=profile,
        geometry_record=geometry_record,
    )
    return tuple(
        ModelInstance(
            model_instance_id=(
                f"{army_id}:{unit_selection_id}:{profile.model_profile_id}:{index:03d}"
            ),
            datasheet_id=datasheet.datasheet_id,
            model_profile_id=profile.model_profile_id,
            name=profile.name,
            characteristics=profile.characteristics,
            base_size=profile.base_size,
            geometry=geometry,
            starting_wounds=starting_wounds,
            wounds_remaining=starting_wounds,
            source_ids=source_ids,
        )
        for index in range(1, model_count + 1)
    )


def _model_geometry_for_profile(
    *,
    datasheet: DatasheetDefinition,
    profile: ModelProfileDefinition,
    geometry_record: ModelGeometryCatalogRecord | None,
) -> ModelGeometry:
    try:
        if geometry_record is not None:
            if geometry_record.model_profile_id != profile.model_profile_id:
                raise UnitFactoryError("Model geometry record model_profile_id drift.")
            return ModelGeometry.from_catalog_record(geometry_record)
        return ModelGeometry.from_base_size(
            profile.base_size,
            keywords=datasheet.keywords.keywords,
            geometry_source_id=profile.model_profile_id,
        )
    except GeometryError as exc:
        raise UnitFactoryError("Model profile geometry is invalid.") from exc


def _merge_source_ids(
    datasheet_source_ids: tuple[str, ...],
    model_profile_source_ids: tuple[str, ...],
) -> tuple[str, ...]:
    return tuple(sorted({*datasheet_source_ids, *model_profile_source_ids}))


def _validate_model_geometry_catalog_records(
    field_name: str,
    values: object,
) -> tuple[ModelGeometryCatalogRecord, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[ModelGeometryCatalogRecord] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not ModelGeometryCatalogRecord:
            raise UnitFactoryError(f"{field_name} must contain ModelGeometryCatalogRecord values.")
        if value.model_profile_id in seen:
            raise UnitFactoryError(f"{field_name} must not duplicate model_profile_id values.")
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda record: record.model_profile_id))


def _validate_model_geometry_records_reference_catalog(
    *,
    catalog: ArmyCatalog,
    model_geometries: tuple[ModelGeometryCatalogRecord, ...],
) -> None:
    catalog_model_profile_ids = {
        profile.model_profile_id
        for datasheet in catalog.datasheets
        for profile in datasheet.model_profiles
    }
    extra_profile_ids = sorted(
        record.model_profile_id
        for record in model_geometries
        if record.model_profile_id not in catalog_model_profile_ids
    )
    if extra_profile_ids:
        raise UnitFactoryError(
            "UnitFactory model_geometries reference unknown model profiles: "
            + ", ".join(extra_profile_ids)
        )


def _validate_geometry_matches_base_size(
    *,
    base_size: BaseSizeDefinition,
    geometry: ModelGeometry,
) -> None:
    if geometry.geometry_source_kind is not GeometrySourceKind.CATALOG_BASE_SIZE:
        return
    geometry_source_id = geometry.geometry_source_id
    if geometry_source_id is None:
        raise UnitFactoryError("ModelInstance catalog-derived geometry requires source ID.")
    expected = ModelGeometry.from_base_size(
        base_size,
        geometry_source_id=geometry_source_id,
        keywords=(),
    )
    if len(geometry.parts) != 1:
        raise UnitFactoryError("ModelInstance geometry footprint does not match base_size.")
    expected_part = expected.primary_part()
    actual_part = geometry.primary_part()
    if actual_part.footprint_kind is not expected_part.footprint_kind:
        raise UnitFactoryError("ModelInstance geometry footprint does not match base_size.")
    if not math.isclose(actual_part.radius_x_inches, expected_part.radius_x_inches):
        raise UnitFactoryError("ModelInstance geometry radius_x_inches does not match base_size.")
    if not math.isclose(actual_part.radius_y_inches, expected_part.radius_y_inches):
        raise UnitFactoryError("ModelInstance geometry radius_y_inches does not match base_size.")


def _validate_characteristics(values: object) -> tuple[CharacteristicValue, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError("ModelInstance characteristics must be a tuple.")
    if not values:
        raise UnitFactoryError("ModelInstance characteristics must not be empty.")
    validated: list[CharacteristicValue] = []
    seen: set[Characteristic] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not CharacteristicValue:
            raise UnitFactoryError(
                "ModelInstance characteristics must contain CharacteristicValue values."
            )
        if value.characteristic in seen:
            raise UnitFactoryError("ModelInstance characteristics must not contain duplicates.")
        seen.add(value.characteristic)
        validated.append(value)
    return tuple(sorted(validated, key=lambda value: value.characteristic.value))


def _validate_model_instance_tuple(
    field_name: str,
    values: object,
) -> tuple[ModelInstance, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    if not values:
        raise UnitFactoryError(f"{field_name} must not be empty.")
    validated: list[ModelInstance] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not ModelInstance:
            raise UnitFactoryError(f"{field_name} must contain ModelInstance values.")
        validated.append(value)
    return tuple(sorted(validated, key=lambda model: model.model_instance_id))


def _validate_unique_model_instance_ids(models: tuple[ModelInstance, ...]) -> None:
    seen: set[str] = set()
    for model in models:
        if model.model_instance_id in seen:
            raise UnitFactoryError("UnitInstance own_models must not contain duplicate IDs.")
        seen.add(model.model_instance_id)


def _validate_model_instance_links(
    *,
    unit_instance: UnitInstance,
    own_models: tuple[ModelInstance, ...],
) -> None:
    for model in own_models:
        if model.datasheet_id != unit_instance.datasheet_id:
            raise UnitFactoryError("UnitInstance own_models must match unit datasheet_id.")
        if not model.model_instance_id.startswith(f"{unit_instance.unit_instance_id}:"):
            raise UnitFactoryError("UnitInstance own_model IDs must be scoped to unit_instance_id.")


def _validate_wargear_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[WargearSelection, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[WargearSelection] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not WargearSelection:
            raise UnitFactoryError(f"{field_name} must contain WargearSelection values.")
        if value.option_id in seen:
            raise UnitFactoryError(f"{field_name} must not contain duplicate option IDs.")
        seen.add(value.option_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda selection: selection.option_id))


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise UnitFactoryError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise UnitFactoryError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise UnitFactoryError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise UnitFactoryError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise UnitFactoryError(f"{field_name} must not be empty.")
    return stripped


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise UnitFactoryError(f"{field_name} must be an integer.")
    if value < 1:
        raise UnitFactoryError(f"{field_name} must be at least 1.")
    return value


def _validate_non_negative_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise UnitFactoryError(f"{field_name} must be an integer.")
    if value < 0:
        raise UnitFactoryError(f"{field_name} must not be negative.")
    return value
