from __future__ import annotations

import math
from dataclasses import dataclass, replace
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
    DamagedEffectDefinition,
    DamagedEffectDefinitionPayload,
    DatasheetAbilityDescriptor,
    DatasheetAbilityDescriptorPayload,
    DatasheetDefinition,
    DatasheetMusteringOption,
    DatasheetMusteringOptionEffect,
    DatasheetMusteringOptionEffectKind,
    DatasheetWargearOption,
    DatasheetWargearOptionEffect,
    ModelProfileDefinition,
    WargearOptionConditionKind,
    WargearOptionEffectKind,
)
from warhammer40k_core.core.model_geometry_catalog import ModelGeometryCatalogRecord
from warhammer40k_core.core.validation import IdentifierValidator, canonical_keyword_token
from warhammer40k_core.engine.list_validation import (
    MusteringOptionSelection,
    MusteringOptionSelectionPayload,
    UnitMusterSelection,
    resolve_model_profile_selections,
    resolve_mustering_option_selections,
    resolve_wargear_selections,
)
from warhammer40k_core.engine.list_validation_errors import (
    ListValidationError,
)
from warhammer40k_core.engine.wargear_selections import (
    WargearSelection,
    WargearSelectionPayload,
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
    wargear_ids: list[str]
    source_ids: list[str]


class UnitInstancePayload(TypedDict):
    unit_instance_id: str
    datasheet_id: str
    name: str
    keywords: list[str]
    faction_keywords: list[str]
    datasheet_abilities: list[DatasheetAbilityDescriptorPayload]
    damaged_effects: list[DamagedEffectDefinitionPayload]
    datasheet_source_ids: list[str]
    own_models: list[ModelInstancePayload]
    wargear_selections: list[WargearSelectionPayload]
    mustering_option_selections: list[MusteringOptionSelectionPayload]


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
    wargear_ids: tuple[str, ...]
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
            "wargear_ids",
            _validate_ordered_identifier_tuple(
                "ModelInstance wargear_ids",
                self.wargear_ids,
                min_length=0,
            ),
        )
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

    def characteristic(self, characteristic: Characteristic) -> CharacteristicValue:
        requested_characteristic = _ensure_characteristic(characteristic)
        for value in self.characteristics:
            if value.characteristic is requested_characteristic:
                return value
        raise UnitFactoryError("ModelInstance characteristic was not found.")

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
            "wargear_ids": list(self.wargear_ids),
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
            wargear_ids=tuple(payload["wargear_ids"]),
            source_ids=tuple(payload["source_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitInstance:
    unit_instance_id: str
    datasheet_id: str
    name: str
    keywords: tuple[str, ...]
    faction_keywords: tuple[str, ...]
    datasheet_abilities: tuple[DatasheetAbilityDescriptor, ...]
    datasheet_source_ids: tuple[str, ...]
    own_models: tuple[ModelInstance, ...]
    wargear_selections: tuple[WargearSelection, ...]
    mustering_option_selections: tuple[MusteringOptionSelection, ...] = ()
    damaged_effects: tuple[DamagedEffectDefinition, ...] = ()

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
            _validate_identifier_tuple(
                "UnitInstance keywords",
                self.keywords,
                min_length=0,
                canonicalize_keywords=True,
            ),
        )
        object.__setattr__(
            self,
            "faction_keywords",
            _validate_identifier_tuple(
                "UnitInstance faction_keywords",
                self.faction_keywords,
                min_length=0,
                canonicalize_keywords=True,
            ),
        )
        object.__setattr__(
            self,
            "datasheet_abilities",
            _validate_datasheet_ability_tuple(
                "UnitInstance datasheet_abilities",
                self.datasheet_abilities,
            ),
        )
        object.__setattr__(
            self,
            "damaged_effects",
            _validate_damaged_effect_tuple(
                "UnitInstance damaged_effects",
                self.damaged_effects,
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
        mustering_option_selections = _validate_mustering_option_selection_tuple(
            "UnitInstance mustering_option_selections",
            self.mustering_option_selections,
        )
        object.__setattr__(
            self,
            "mustering_option_selections",
            mustering_option_selections,
        )

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
            "datasheet_abilities": [ability.to_payload() for ability in self.datasheet_abilities],
            "damaged_effects": [effect.to_payload() for effect in self.damaged_effects],
            "datasheet_source_ids": list(self.datasheet_source_ids),
            "own_models": [model.to_payload() for model in self.own_models],
            "wargear_selections": [selection.to_payload() for selection in self.wargear_selections],
            "mustering_option_selections": [
                selection.to_payload() for selection in self.mustering_option_selections
            ],
        }

    @classmethod
    def from_payload(cls, payload: UnitInstancePayload) -> Self:
        return cls(
            unit_instance_id=payload["unit_instance_id"],
            datasheet_id=payload["datasheet_id"],
            name=payload["name"],
            keywords=tuple(payload["keywords"]),
            faction_keywords=tuple(payload["faction_keywords"]),
            datasheet_abilities=tuple(
                DatasheetAbilityDescriptor.from_payload(ability)
                for ability in payload["datasheet_abilities"]
            ),
            damaged_effects=tuple(
                DamagedEffectDefinition.from_payload(effect)
                for effect in payload["damaged_effects"]
            ),
            datasheet_source_ids=tuple(payload["datasheet_source_ids"]),
            own_models=tuple(ModelInstance.from_payload(model) for model in payload["own_models"]),
            wargear_selections=tuple(
                WargearSelection.from_payload(selection)
                for selection in payload["wargear_selections"]
            ),
            mustering_option_selections=tuple(
                MusteringOptionSelection.from_payload(selection)
                for selection in payload["mustering_option_selections"]
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
            selected_mustering_options = resolve_mustering_option_selections(
                datasheet=datasheet,
                requested_selections=selection.mustering_option_selections,
            )
            wargear_selections = resolve_wargear_selections(
                catalog=self.catalog,
                datasheet=datasheet,
                requested_selections=selection.wargear_selections,
                model_profile_selections=model_profile_selections,
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
        model_wargear_ids = _model_wargear_ids_by_model_id(
            datasheet=datasheet,
            own_models=tuple(own_models),
            wargear_selections=wargear_selections,
            selected_mustering_options=selected_mustering_options,
        )
        own_models = [
            replace(model, wargear_ids=model_wargear_ids[model.model_instance_id])
            for model in own_models
        ]
        return UnitInstance(
            unit_instance_id=f"{army_id}:{selection.unit_selection_id}",
            datasheet_id=datasheet.datasheet_id,
            name=datasheet.name,
            keywords=_keywords_with_mustering_effects(
                base_keywords=datasheet.keywords.keywords,
                selected_mustering_options=selected_mustering_options,
            ),
            faction_keywords=datasheet.keywords.faction_keywords,
            datasheet_abilities=datasheet.abilities,
            damaged_effects=datasheet.damaged_effects,
            datasheet_source_ids=datasheet.source_ids,
            own_models=tuple(own_models),
            wargear_selections=wargear_selections,
            mustering_option_selections=tuple(
                MusteringOptionSelection(option_id=option.option_id)
                for option in selected_mustering_options
            ),
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
            wargear_ids=(),
            source_ids=source_ids,
        )
        for index in range(1, model_count + 1)
    )


def _model_wargear_ids_by_model_id(
    *,
    datasheet: DatasheetDefinition,
    own_models: tuple[ModelInstance, ...],
    wargear_selections: tuple[WargearSelection, ...],
    selected_mustering_options: tuple[DatasheetMusteringOption, ...],
) -> dict[str, tuple[str, ...]]:
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    models_by_profile: dict[str, tuple[ModelInstance, ...]] = {}
    for model in own_models:
        profile_models = models_by_profile.get(model.model_profile_id, ())
        models_by_profile[model.model_profile_id] = tuple(
            sorted((*profile_models, model), key=lambda item: item.model_instance_id)
        )
    wargear_by_model_id: dict[str, list[str]] = {
        model.model_instance_id: [] for model in own_models
    }

    structured_selections: list[tuple[DatasheetWargearOption, WargearSelection]] = []
    for selection in wargear_selections:
        option = options_by_id.get(selection.option_id)
        if option is None:
            raise UnitFactoryError("WargearSelection references an unknown datasheet option.")
        if not selection.wargear_ids:
            continue
        if option.effects:
            structured_selections.append((option, selection))
            continue
        if selection.wargear_ids != option.default_wargear_ids:
            raise UnitFactoryError(
                "Non-default wargear selection requires structured model assignment effects."
            )
        for model in models_by_profile.get(option.model_profile_id, ()):
            wargear_by_model_id[model.model_instance_id].extend(selection.wargear_ids)

    for option, selection in _ordered_structured_wargear_selections(structured_selections):
        _apply_structured_wargear_selection_to_models(
            option=option,
            selection=selection,
            models=models_by_profile.get(option.model_profile_id, ()),
            wargear_by_model_id=wargear_by_model_id,
        )

    for mustering_option in selected_mustering_options:
        _apply_mustering_option_wargear_effects_to_models(
            option=mustering_option,
            models=(
                own_models
                if mustering_option.model_profile_id is None
                else models_by_profile.get(mustering_option.model_profile_id, ())
            ),
            wargear_by_model_id=wargear_by_model_id,
        )

    return {
        model_id: tuple(wargear_ids)
        for model_id, wargear_ids in sorted(wargear_by_model_id.items())
    }


def _ordered_structured_wargear_selections(
    selections: list[tuple[DatasheetWargearOption, WargearSelection]],
) -> tuple[tuple[DatasheetWargearOption, WargearSelection], ...]:
    remaining = sorted(selections, key=lambda item: item[0].option_id)
    ordered: list[tuple[DatasheetWargearOption, WargearSelection]] = []
    while remaining:
        produced_by_remaining = {
            effect.wargear_id: option.option_id
            for option, selection in remaining
            for effect in option.effects
            if effect.wargear_id in selection.wargear_ids
        }
        ready = tuple(
            item
            for item in remaining
            if not _structured_selection_dependencies(
                option=item[0],
                produced_by_option_id=produced_by_remaining,
            )
        )
        if not ready:
            raise UnitFactoryError("Structured wargear option dependencies contain a cycle.")
        ready_ids = {option.option_id for option, _selection in ready}
        ordered.extend(ready)
        remaining = [item for item in remaining if item[0].option_id not in ready_ids]
    return tuple(ordered)


def _structured_selection_dependencies(
    *,
    option: DatasheetWargearOption,
    produced_by_option_id: dict[str, str],
) -> tuple[str, ...]:
    required_wargear_ids = {
        effect.replaced_wargear_id
        for effect in option.effects
        if effect.replaced_wargear_id is not None
    }
    required_wargear_ids.update(
        wargear_id
        for condition in option.conditions
        if condition.kind is WargearOptionConditionKind.MODEL_EQUIPPED_WITH
        for wargear_id in condition.wargear_ids
    )
    return tuple(
        sorted(
            producer_id
            for wargear_id in required_wargear_ids
            if (producer_id := produced_by_option_id.get(wargear_id)) is not None
            and producer_id != option.option_id
        )
    )


def _apply_structured_wargear_selection_to_models(
    *,
    option: DatasheetWargearOption,
    selection: WargearSelection,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> None:
    selected_wargear = list(selection.wargear_ids)
    for effect in option.effects:
        effect_selection_count = selection.selection_count_for_wargear(effect.wargear_id)
        if effect.kind in {
            WargearOptionEffectKind.ADD_WARGEAR,
            WargearOptionEffectKind.ADD_WARGEAR_IF_SELECTED,
        }:
            _apply_add_wargear_effect_to_models(
                option=option,
                effect=effect,
                selected_wargear=tuple(selected_wargear),
                selection_count=effect_selection_count,
                selection=selection,
                models=models,
                wargear_by_model_id=wargear_by_model_id,
            )
            continue
        if effect.kind is WargearOptionEffectKind.REPLACE_WARGEAR:
            _apply_replace_wargear_effect_to_models(
                option=option,
                effect=effect,
                selected_wargear=tuple(selected_wargear),
                selection_count=effect_selection_count,
                selection=selection,
                models=models,
                wargear_by_model_id=wargear_by_model_id,
            )
            continue
        if effect.kind is WargearOptionEffectKind.REMOVE_WARGEAR_IF_SELECTED:
            _apply_remove_wargear_effect_from_models(
                option=option,
                effect=effect,
                selected_wargear=tuple(selected_wargear),
                selection_count=effect_selection_count,
                selection=selection,
                models=models,
                wargear_by_model_id=wargear_by_model_id,
            )
            continue
        raise UnitFactoryError("Unsupported structured wargear option effect.")


def _apply_add_wargear_effect_to_models(
    *,
    option: DatasheetWargearOption,
    effect: DatasheetWargearOptionEffect,
    selected_wargear: tuple[str, ...],
    selection_count: int,
    selection: WargearSelection,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> None:
    if effect.wargear_id not in selected_wargear:
        return
    candidates = _eligible_wargear_effect_models(
        option=option,
        models=models,
        wargear_by_model_id=wargear_by_model_id,
    )
    per_model_capacity = _wargear_option_selection_capacity_per_model(option)
    if per_model_capacity > 1 and effect.model_count != 1:
        raise UnitFactoryError(
            "Structured multi-copy wargear option requires one model per selection."
        )
    candidate_slots = _assigned_or_default_wargear_effect_slots(
        selection=selection,
        wargear_id=effect.wargear_id,
        models=models,
        eligible_models=candidates,
        default_capacity_per_model=per_model_capacity,
    )
    affected_model_count = effect.model_count * selection_count
    if len(candidate_slots) < affected_model_count:
        raise UnitFactoryError(
            "Structured wargear option has fewer eligible model bearers than required."
        )
    for model in candidate_slots[:affected_model_count]:
        wargear_by_model_id[model.model_instance_id].extend(
            effect.wargear_id for _index in range(effect.wargear_count)
        )


def _apply_replace_wargear_effect_to_models(
    *,
    option: DatasheetWargearOption,
    effect: DatasheetWargearOptionEffect,
    selected_wargear: tuple[str, ...],
    selection_count: int,
    selection: WargearSelection,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> None:
    if effect.wargear_id not in selected_wargear:
        return
    if effect.replaced_wargear_id is None:
        raise UnitFactoryError("Structured wargear replacement target is missing.")
    eligible_models = _eligible_wargear_effect_models(
        option=option,
        models=models,
        wargear_by_model_id=wargear_by_model_id,
    )
    candidates = _assigned_or_default_wargear_effect_slots(
        selection=selection,
        wargear_id=effect.wargear_id,
        models=models,
        eligible_models=eligible_models,
        default_capacity_by_model={
            model.model_instance_id: wargear_by_model_id[model.model_instance_id].count(
                effect.replaced_wargear_id
            )
            for model in eligible_models
        },
    )
    affected_model_count = effect.model_count * selection_count
    if len(candidates) < affected_model_count:
        raise UnitFactoryError(
            "Structured wargear replacement has fewer eligible model bearers than required."
        )
    for model in candidates[:affected_model_count]:
        model_wargear = wargear_by_model_id[model.model_instance_id]
        model_wargear.remove(effect.replaced_wargear_id)
        model_wargear.extend(effect.wargear_id for _index in range(effect.wargear_count))


def _apply_remove_wargear_effect_from_models(
    *,
    option: DatasheetWargearOption,
    effect: DatasheetWargearOptionEffect,
    selected_wargear: tuple[str, ...],
    selection_count: int,
    selection: WargearSelection,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> None:
    if effect.wargear_id not in selected_wargear:
        return
    if effect.replaced_wargear_id is None:
        raise UnitFactoryError("Structured wargear removal target is missing.")
    eligible_models = _eligible_wargear_effect_models(
        option=option,
        models=models,
        wargear_by_model_id=wargear_by_model_id,
    )
    candidates = _assigned_or_default_wargear_effect_slots(
        selection=selection,
        wargear_id=effect.wargear_id,
        models=models,
        eligible_models=eligible_models,
        default_capacity_by_model={
            model.model_instance_id: wargear_by_model_id[model.model_instance_id].count(
                effect.replaced_wargear_id
            )
            for model in eligible_models
        },
    )
    affected_model_count = effect.model_count * selection_count
    if len(candidates) < affected_model_count:
        raise UnitFactoryError(
            "Structured wargear removal has fewer eligible model bearers than required."
        )
    for model in candidates[:affected_model_count]:
        wargear_by_model_id[model.model_instance_id].remove(effect.replaced_wargear_id)


def _assigned_or_default_wargear_effect_slots(
    *,
    selection: WargearSelection,
    wargear_id: str,
    models: tuple[ModelInstance, ...],
    eligible_models: tuple[ModelInstance, ...],
    default_capacity_per_model: int | None = None,
    default_capacity_by_model: dict[str, int] | None = None,
) -> tuple[ModelInstance, ...]:
    if selection.bearer_assignments:
        eligible_model_ids = {model.model_instance_id for model in eligible_models}
        slots: list[ModelInstance] = []
        for assignment in selection.bearer_assignments:
            if assignment.wargear_id != wargear_id:
                continue
            if assignment.model_ordinal > len(models):
                raise UnitFactoryError(
                    "WargearSelection bearer assignment references a missing model ordinal."
                )
            model = models[assignment.model_ordinal - 1]
            if model.model_instance_id not in eligible_model_ids:
                raise UnitFactoryError(
                    "WargearSelection bearer assignment references an ineligible model."
                )
            capacity = (
                default_capacity_per_model
                if default_capacity_by_model is None
                else default_capacity_by_model[model.model_instance_id]
            )
            if capacity is None or assignment.selection_count > capacity:
                raise UnitFactoryError(
                    "WargearSelection bearer assignment exceeds the model's effect capacity."
                )
            slots.extend(model for _index in range(assignment.selection_count))
        return tuple(slots)
    if default_capacity_by_model is not None:
        return tuple(
            model
            for model in eligible_models
            for _index in range(default_capacity_by_model[model.model_instance_id])
        )
    if default_capacity_per_model is None:
        raise UnitFactoryError("Structured wargear effect assignment capacity is missing.")
    return tuple(model for model in eligible_models for _index in range(default_capacity_per_model))


def _wargear_option_selection_capacity_per_model(
    option: DatasheetWargearOption,
) -> int:
    limit = option.selection_limit
    if limit is None or limit.models_per_increment != 1:
        return 1
    return limit.max_option_selections_per_increment


def _eligible_wargear_effect_models(
    *,
    option: DatasheetWargearOption,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> tuple[ModelInstance, ...]:
    return tuple(
        model
        for model in models
        if _model_satisfies_wargear_option_conditions(
            option=option,
            current_wargear_ids=tuple(wargear_by_model_id[model.model_instance_id]),
        )
    )


def _model_satisfies_wargear_option_conditions(
    *,
    option: DatasheetWargearOption,
    current_wargear_ids: tuple[str, ...],
) -> bool:
    current_wargear = set(current_wargear_ids)
    for condition in option.conditions:
        if condition.kind is WargearOptionConditionKind.MODEL_NOT_EQUIPPED_WITH and (
            current_wargear.intersection(condition.wargear_ids)
        ):
            return False
        if condition.kind is WargearOptionConditionKind.MODEL_EQUIPPED_WITH and not set(
            condition.wargear_ids
        ).issubset(current_wargear):
            return False
    return True


def _apply_mustering_option_wargear_effects_to_models(
    *,
    option: DatasheetMusteringOption,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> None:
    for effect in option.effects:
        if effect.kind is DatasheetMusteringOptionEffectKind.ADD_KEYWORD:
            continue
        if effect.kind is DatasheetMusteringOptionEffectKind.ADD_WARGEAR:
            _apply_mustering_add_wargear_effect_to_models(
                effect=effect,
                models=models,
                wargear_by_model_id=wargear_by_model_id,
            )
            continue
        raise UnitFactoryError("Unsupported mustering option effect.")


def _apply_mustering_add_wargear_effect_to_models(
    *,
    effect: DatasheetMusteringOptionEffect,
    models: tuple[ModelInstance, ...],
    wargear_by_model_id: dict[str, list[str]],
) -> None:
    if effect.model_count != 1 or effect.wargear_count != 1:
        raise UnitFactoryError("Mustering option wargear effects support one model bearer.")
    if effect.wargear_id is None:
        raise UnitFactoryError("Mustering option wargear effect is missing wargear_id.")
    if not models:
        raise UnitFactoryError("Mustering option has no eligible model bearers.")
    model = sorted(models, key=lambda item: item.model_instance_id)[0]
    wargear_by_model_id[model.model_instance_id].append(effect.wargear_id)


def _keywords_with_mustering_effects(
    *,
    base_keywords: tuple[str, ...],
    selected_mustering_options: tuple[DatasheetMusteringOption, ...],
) -> tuple[str, ...]:
    keywords = set(base_keywords)
    for option in selected_mustering_options:
        for effect in option.effects:
            if effect.kind is DatasheetMusteringOptionEffectKind.ADD_KEYWORD:
                if effect.keyword is None:
                    raise UnitFactoryError("Mustering option keyword effect is missing keyword.")
                keywords.add(effect.keyword)
                continue
            if effect.kind is DatasheetMusteringOptionEffectKind.ADD_WARGEAR:
                continue
            raise UnitFactoryError("Unsupported mustering option effect.")
    return tuple(sorted(keywords))


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


def _validate_datasheet_ability_tuple(
    field_name: str,
    values: object,
) -> tuple[DatasheetAbilityDescriptor, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[DatasheetAbilityDescriptor] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not DatasheetAbilityDescriptor:
            raise UnitFactoryError(f"{field_name} must contain DatasheetAbilityDescriptor values.")
        if value.ability_id in seen:
            raise UnitFactoryError(f"{field_name} must not contain duplicate ability IDs.")
        seen.add(value.ability_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda ability: ability.ability_id))


def _validate_damaged_effect_tuple(
    field_name: str,
    values: object,
) -> tuple[DamagedEffectDefinition, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[DamagedEffectDefinition] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not DamagedEffectDefinition:
            raise UnitFactoryError(f"{field_name} must contain DamagedEffectDefinition values.")
        if value.damaged_effect_id in seen:
            raise UnitFactoryError(f"{field_name} must not contain duplicate IDs.")
        seen.add(value.damaged_effect_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda effect: effect.damaged_effect_id))


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


def _validate_mustering_option_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[MusteringOptionSelection, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[MusteringOptionSelection] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not MusteringOptionSelection:
            raise UnitFactoryError(f"{field_name} must contain MusteringOptionSelection values.")
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
    canonicalize_keywords: bool = False,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if canonicalize_keywords:
            identifier = canonical_keyword_token(identifier)
        if identifier in seen:
            raise UnitFactoryError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise UnitFactoryError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_ordered_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise UnitFactoryError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        validated.append(_validate_identifier(f"{field_name} value", value))
    if len(validated) < min_length:
        raise UnitFactoryError(f"{field_name} must contain at least {min_length} values.")
    return tuple(validated)


def _ensure_characteristic(value: object) -> Characteristic:
    if type(value) is not Characteristic:
        raise UnitFactoryError("Expected a Characteristic.")
    return value


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise UnitFactoryError(f"{field_name} must not include the stable identity prefix.")
    return identifier


_validate_identifier = IdentifierValidator(UnitFactoryError)


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
