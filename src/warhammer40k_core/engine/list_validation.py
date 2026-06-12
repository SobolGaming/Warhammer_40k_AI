from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogError
from warhammer40k_core.core.datasheet import (
    DatasheetDefinition,
    DatasheetWargearOption,
    UnitCompositionDefinition,
)
from warhammer40k_core.core.detachment import DetachmentDefinition
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.wargear import Wargear


class ListValidationError(ValueError):
    """Raised when army list data violates CORE V2 mustering invariants."""


class BattleSize(StrEnum):
    STRIKE_FORCE = "strike_force"


DAEMONIC_PACT_FACTION_KEYWORD = "LEGIONES DAEMONICA"
DAEMONIC_PACT_BASE_FACTION_KEYWORDS = frozenset({"CHAOS KNIGHTS", "HERETIC ASTARTES"})


class BattleSizeMusteringPolicyPayload(TypedDict):
    battle_size: str
    points_limit: int
    battlefield_width_inches: float
    battlefield_depth_inches: float
    detachment_point_limit: int
    enhancement_limit: int
    unit_limit: int
    battleline_unit_limit: int


class ModelProfileSelectionPayload(TypedDict):
    model_profile_id: str
    model_count: int


class WargearSelectionPayload(TypedDict):
    option_id: str
    model_profile_id: str
    wargear_ids: list[str]


class DetachmentSelectionPayload(TypedDict):
    faction_id: str
    detachment_ids: list[str]
    enhancement_ids: list[str]
    stratagem_ids: list[str]


class UnitMusterSelectionPayload(TypedDict):
    unit_selection_id: str
    datasheet_id: str
    model_profile_selections: list[ModelProfileSelectionPayload]
    wargear_selections: list[WargearSelectionPayload]


class AttachmentDeclarationPayload(TypedDict):
    source_unit_selection_id: str
    bodyguard_unit_selection_id: str


@dataclass(frozen=True, slots=True)
class BattleSizeMusteringPolicy:
    battle_size: BattleSize
    points_limit: int
    battlefield_width_inches: float
    battlefield_depth_inches: float
    detachment_point_limit: int
    enhancement_limit: int
    unit_limit: int
    battleline_unit_limit: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "battle_size", battle_size_from_token(self.battle_size))
        object.__setattr__(
            self,
            "points_limit",
            _validate_positive_int("BattleSizeMusteringPolicy points_limit", self.points_limit),
        )
        object.__setattr__(
            self,
            "battlefield_width_inches",
            _validate_positive_number(
                "BattleSizeMusteringPolicy battlefield_width_inches",
                self.battlefield_width_inches,
            ),
        )
        object.__setattr__(
            self,
            "battlefield_depth_inches",
            _validate_positive_number(
                "BattleSizeMusteringPolicy battlefield_depth_inches",
                self.battlefield_depth_inches,
            ),
        )
        object.__setattr__(
            self,
            "detachment_point_limit",
            _validate_positive_int(
                "BattleSizeMusteringPolicy detachment_point_limit",
                self.detachment_point_limit,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_limit",
            _validate_positive_int(
                "BattleSizeMusteringPolicy enhancement_limit",
                self.enhancement_limit,
            ),
        )
        object.__setattr__(
            self,
            "unit_limit",
            _validate_positive_int("BattleSizeMusteringPolicy unit_limit", self.unit_limit),
        )
        object.__setattr__(
            self,
            "battleline_unit_limit",
            _validate_positive_int(
                "BattleSizeMusteringPolicy battleline_unit_limit",
                self.battleline_unit_limit,
            ),
        )
        if self.battleline_unit_limit < self.unit_limit:
            raise ListValidationError(
                "BattleSizeMusteringPolicy battleline_unit_limit must be at least unit_limit."
            )

    @classmethod
    def strike_force(cls) -> Self:
        return cls(
            battle_size=BattleSize.STRIKE_FORCE,
            points_limit=2000,
            battlefield_width_inches=60.0,
            battlefield_depth_inches=44.0,
            detachment_point_limit=3,
            enhancement_limit=4,
            unit_limit=3,
            battleline_unit_limit=6,
        )

    def to_payload(self) -> BattleSizeMusteringPolicyPayload:
        return {
            "battle_size": self.battle_size.value,
            "points_limit": self.points_limit,
            "battlefield_width_inches": self.battlefield_width_inches,
            "battlefield_depth_inches": self.battlefield_depth_inches,
            "detachment_point_limit": self.detachment_point_limit,
            "enhancement_limit": self.enhancement_limit,
            "unit_limit": self.unit_limit,
            "battleline_unit_limit": self.battleline_unit_limit,
        }


@dataclass(frozen=True, slots=True)
class ModelProfileSelection:
    model_profile_id: str
    model_count: int

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier("ModelProfileSelection model_profile_id", self.model_profile_id),
        )
        object.__setattr__(
            self,
            "model_count",
            _validate_positive_int("ModelProfileSelection model_count", self.model_count),
        )

    def to_payload(self) -> ModelProfileSelectionPayload:
        return {
            "model_profile_id": self.model_profile_id,
            "model_count": self.model_count,
        }

    @classmethod
    def from_payload(cls, payload: ModelProfileSelectionPayload) -> Self:
        return cls(
            model_profile_id=payload["model_profile_id"],
            model_count=payload["model_count"],
        )


@dataclass(frozen=True, slots=True)
class WargearSelection:
    option_id: str
    model_profile_id: str
    wargear_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "option_id",
            _validate_unprefixed_identifier(
                "WargearSelection option_id",
                self.option_id,
                "wargear-option:",
            ),
        )
        object.__setattr__(
            self,
            "model_profile_id",
            _validate_identifier("WargearSelection model_profile_id", self.model_profile_id),
        )
        object.__setattr__(
            self,
            "wargear_ids",
            _validate_identifier_tuple(
                "WargearSelection wargear_ids",
                self.wargear_ids,
                min_length=0,
            ),
        )

    def to_payload(self) -> WargearSelectionPayload:
        return {
            "option_id": self.option_id,
            "model_profile_id": self.model_profile_id,
            "wargear_ids": list(self.wargear_ids),
        }

    @classmethod
    def from_payload(cls, payload: WargearSelectionPayload) -> Self:
        return cls(
            option_id=payload["option_id"],
            model_profile_id=payload["model_profile_id"],
            wargear_ids=tuple(payload["wargear_ids"]),
        )


@dataclass(frozen=True, slots=True)
class DetachmentSelection:
    faction_id: str
    detachment_ids: tuple[str, ...]
    enhancement_ids: tuple[str, ...] = ()
    stratagem_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "faction_id",
            _validate_unprefixed_identifier(
                "DetachmentSelection faction_id",
                self.faction_id,
                "faction:",
            ),
        )
        object.__setattr__(
            self,
            "detachment_ids",
            _validate_unprefixed_identifier_tuple(
                "DetachmentSelection detachment_ids",
                self.detachment_ids,
                "detachment:",
                min_length=1,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_ids",
            _validate_identifier_tuple(
                "DetachmentSelection enhancement_ids",
                self.enhancement_ids,
                min_length=0,
            ),
        )
        object.__setattr__(
            self,
            "stratagem_ids",
            _validate_identifier_tuple(
                "DetachmentSelection stratagem_ids",
                self.stratagem_ids,
                min_length=0,
            ),
        )

    def to_payload(self) -> DetachmentSelectionPayload:
        return {
            "faction_id": self.faction_id,
            "detachment_ids": list(self.detachment_ids),
            "enhancement_ids": list(self.enhancement_ids),
            "stratagem_ids": list(self.stratagem_ids),
        }

    @classmethod
    def from_payload(cls, payload: DetachmentSelectionPayload) -> Self:
        return cls(
            faction_id=payload["faction_id"],
            detachment_ids=tuple(payload["detachment_ids"]),
            enhancement_ids=tuple(payload["enhancement_ids"]),
            stratagem_ids=tuple(payload["stratagem_ids"]),
        )


@dataclass(frozen=True, slots=True)
class UnitMusterSelection:
    unit_selection_id: str
    datasheet_id: str
    model_profile_selections: tuple[ModelProfileSelection, ...]
    wargear_selections: tuple[WargearSelection, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "unit_selection_id",
            _validate_unprefixed_identifier(
                "UnitMusterSelection unit_selection_id",
                self.unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "datasheet_id",
            _validate_unprefixed_identifier(
                "UnitMusterSelection datasheet_id",
                self.datasheet_id,
                "datasheet:",
            ),
        )
        model_profile_selections = _validate_model_profile_selection_tuple(
            "UnitMusterSelection model_profile_selections",
            self.model_profile_selections,
        )
        _validate_unique_model_profile_selections(model_profile_selections)
        wargear_selections = _validate_wargear_selection_tuple(
            "UnitMusterSelection wargear_selections",
            self.wargear_selections,
        )
        _validate_unique_wargear_selections(wargear_selections)
        object.__setattr__(self, "model_profile_selections", model_profile_selections)
        object.__setattr__(self, "wargear_selections", wargear_selections)

    def to_payload(self) -> UnitMusterSelectionPayload:
        return {
            "unit_selection_id": self.unit_selection_id,
            "datasheet_id": self.datasheet_id,
            "model_profile_selections": [
                selection.to_payload() for selection in self.model_profile_selections
            ],
            "wargear_selections": [selection.to_payload() for selection in self.wargear_selections],
        }

    @classmethod
    def from_payload(cls, payload: UnitMusterSelectionPayload) -> Self:
        return cls(
            unit_selection_id=payload["unit_selection_id"],
            datasheet_id=payload["datasheet_id"],
            model_profile_selections=tuple(
                ModelProfileSelection.from_payload(selection)
                for selection in payload["model_profile_selections"]
            ),
            wargear_selections=tuple(
                WargearSelection.from_payload(selection)
                for selection in payload["wargear_selections"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AttachmentDeclaration:
    source_unit_selection_id: str
    bodyguard_unit_selection_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_unit_selection_id",
            _validate_unprefixed_identifier(
                "AttachmentDeclaration source_unit_selection_id",
                self.source_unit_selection_id,
                "unit-selection:",
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_unit_selection_id",
            _validate_unprefixed_identifier(
                "AttachmentDeclaration bodyguard_unit_selection_id",
                self.bodyguard_unit_selection_id,
                "unit-selection:",
            ),
        )
        if self.source_unit_selection_id == self.bodyguard_unit_selection_id:
            raise ListValidationError("AttachmentDeclaration cannot attach a unit to itself.")

    def to_payload(self) -> AttachmentDeclarationPayload:
        return {
            "source_unit_selection_id": self.source_unit_selection_id,
            "bodyguard_unit_selection_id": self.bodyguard_unit_selection_id,
        }

    @classmethod
    def from_payload(cls, payload: AttachmentDeclarationPayload) -> Self:
        return cls(
            source_unit_selection_id=payload["source_unit_selection_id"],
            bodyguard_unit_selection_id=payload["bodyguard_unit_selection_id"],
        )


def validate_detachment_selection(
    *,
    catalog: ArmyCatalog,
    selection: DetachmentSelection,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> tuple[FactionDefinition, tuple[DetachmentDefinition, ...]]:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(selection) is not DetachmentSelection:
        raise ListValidationError("selection must be a DetachmentSelection.")
    policy = battle_size_mustering_policy(battle_size)
    faction = _catalog_faction_by_id(catalog, selection.faction_id)
    detachments = tuple(
        _catalog_detachment_by_id(catalog, detachment_id)
        for detachment_id in selection.detachment_ids
    )
    detachment_point_costs: list[int] = []
    for detachment in detachments:
        if detachment.faction_id != faction.faction_id:
            raise ListValidationError("DetachmentSelection detachment does not belong to faction.")
        if detachment.detachment_point_cost is None:
            raise ListValidationError(
                "DetachmentSelection detachment point cost is awaiting source."
            )
        detachment_point_costs.append(detachment.detachment_point_cost)
        if not detachment.unit_datasheet_ids:
            raise ListValidationError(
                "DetachmentSelection detachment unit grants are awaiting source."
            )
        if not detachment.force_disposition_ids:
            raise ListValidationError(
                "DetachmentSelection detachment force disposition is awaiting source."
            )
    total_detachment_points = sum(detachment_point_costs)
    if total_detachment_points > policy.detachment_point_limit:
        raise ListValidationError("DetachmentSelection exceeds battle size Detachment Points.")
    allowed_enhancement_ids = tuple(
        enhancement_id
        for detachment in detachments
        for enhancement_id in detachment.enhancement_ids
    )
    allowed_stratagem_ids = tuple(
        stratagem_id for detachment in detachments for stratagem_id in detachment.stratagem_ids
    )
    _validate_selected_ids_are_allowed(
        field_name="DetachmentSelection enhancement_ids",
        selected_ids=selection.enhancement_ids,
        allowed_ids=allowed_enhancement_ids,
    )
    _validate_selected_ids_are_allowed(
        field_name="DetachmentSelection stratagem_ids",
        selected_ids=selection.stratagem_ids,
        allowed_ids=allowed_stratagem_ids,
    )
    _validate_catalog_contains_enhancements(catalog, selection.enhancement_ids)
    _validate_catalog_contains_stratagems(catalog, selection.stratagem_ids)
    return faction, tuple(sorted(detachments, key=lambda detachment: detachment.detachment_id))


def selected_force_disposition_ids(
    *,
    catalog: ArmyCatalog,
    selection: DetachmentSelection,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> tuple[str, ...]:
    _faction, detachments = validate_detachment_selection(
        catalog=catalog,
        selection=selection,
        battle_size=battle_size,
    )
    force_disposition_ids = {
        force_disposition_id
        for detachment in detachments
        for force_disposition_id in detachment.force_disposition_ids
    }
    return tuple(sorted(force_disposition_ids))


def validate_unit_selection_for_faction(
    *,
    catalog: ArmyCatalog,
    selection: UnitMusterSelection,
    faction: FactionDefinition,
) -> DatasheetDefinition:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(selection) is not UnitMusterSelection:
        raise ListValidationError("selection must be a UnitMusterSelection.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("faction must be a FactionDefinition.")
    datasheet = _catalog_datasheet_by_id(catalog, selection.datasheet_id)
    if not set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords):
        raise ListValidationError("UnitMusterSelection datasheet is not legal for faction.")
    return datasheet


def validate_unit_selection_for_army(
    *,
    catalog: ArmyCatalog,
    selection: UnitMusterSelection,
    faction: FactionDefinition,
    detachment_selection: DetachmentSelection,
    battle_size: BattleSize = BattleSize.STRIKE_FORCE,
) -> DatasheetDefinition:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(selection) is not UnitMusterSelection:
        raise ListValidationError("selection must be a UnitMusterSelection.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("faction must be a FactionDefinition.")
    datasheet = _catalog_datasheet_by_id(catalog, selection.datasheet_id)
    shares_selected_faction = bool(
        set(datasheet.keywords.faction_keywords).intersection(faction.faction_keywords)
    )
    daemonic_pact_allowed = daemonic_pact_datasheet_allowed_for_faction(
        datasheet=datasheet,
        faction=faction,
    )
    if not shares_selected_faction and not daemonic_pact_allowed:
        raise ListValidationError("UnitMusterSelection datasheet is not legal for faction.")
    _selected_faction, detachments = validate_detachment_selection(
        catalog=catalog,
        selection=detachment_selection,
        battle_size=battle_size,
    )
    allowed_datasheet_ids = {
        datasheet_id for detachment in detachments for datasheet_id in detachment.unit_datasheet_ids
    }
    if datasheet.datasheet_id not in allowed_datasheet_ids and not daemonic_pact_allowed:
        raise ListValidationError(
            "UnitMusterSelection datasheet is not provided by selected detachments."
        )
    return datasheet


def daemonic_pact_datasheet_allowed_for_faction(
    *,
    datasheet: DatasheetDefinition,
    faction: FactionDefinition,
) -> bool:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("Daemonic Pact datasheet must be a DatasheetDefinition.")
    if type(faction) is not FactionDefinition:
        raise ListValidationError("Daemonic Pact faction must be a FactionDefinition.")
    if not _datasheet_has_faction_keyword(datasheet, DAEMONIC_PACT_FACTION_KEYWORD):
        return False
    faction_keywords = {_canonical_keyword(keyword) for keyword in faction.faction_keywords}
    return bool(faction_keywords & DAEMONIC_PACT_BASE_FACTION_KEYWORDS)


def resolve_model_profile_selections(
    *,
    datasheet: DatasheetDefinition,
    selections: tuple[ModelProfileSelection, ...],
) -> tuple[ModelProfileSelection, ...]:
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("datasheet must be a DatasheetDefinition.")
    selections = _validate_model_profile_selection_tuple("model_profile_selections", selections)
    _validate_unique_model_profile_selections(selections)
    composition_by_profile = {part.model_profile_id: part for part in datasheet.composition}
    selection_by_profile = {selection.model_profile_id: selection for selection in selections}
    if set(selection_by_profile) != set(composition_by_profile):
        raise ListValidationError(
            "UnitMusterSelection model_profile_selections must match datasheet composition."
        )
    for model_profile_id, selection in selection_by_profile.items():
        composition = composition_by_profile[model_profile_id]
        _validate_model_count_against_composition(selection, composition)
        datasheet.model_profile_by_id(model_profile_id)
    return tuple(sorted(selections, key=lambda selection: selection.model_profile_id))


def resolve_wargear_selections(
    *,
    catalog: ArmyCatalog,
    datasheet: DatasheetDefinition,
    requested_selections: tuple[WargearSelection, ...],
) -> tuple[WargearSelection, ...]:
    if type(catalog) is not ArmyCatalog:
        raise ListValidationError("catalog must be an ArmyCatalog.")
    if type(datasheet) is not DatasheetDefinition:
        raise ListValidationError("datasheet must be a DatasheetDefinition.")
    requested_selections = _validate_wargear_selection_tuple(
        "requested_selections",
        requested_selections,
    )
    _validate_unique_wargear_selections(requested_selections)
    options_by_id = {option.option_id: option for option in datasheet.wargear_options}
    requested_by_id = {selection.option_id: selection for selection in requested_selections}
    unknown_requested = tuple(sorted(set(requested_by_id).difference(options_by_id)))
    if unknown_requested:
        raise ListValidationError("WargearSelection references an unknown datasheet option.")

    resolved: list[WargearSelection] = []
    for option in datasheet.wargear_options:
        selection = requested_by_id.get(option.option_id)
        if selection is None:
            selection = WargearSelection(
                option_id=option.option_id,
                model_profile_id=option.model_profile_id,
                wargear_ids=option.default_wargear_ids,
            )
        _validate_wargear_selection_against_option(selection, option)
        for wargear_id in selection.wargear_ids:
            _catalog_wargear_by_id(catalog, wargear_id)
        resolved.append(selection)
    return tuple(sorted(resolved, key=lambda selection: selection.option_id))


def _catalog_datasheet_by_id(catalog: ArmyCatalog, datasheet_id: str) -> DatasheetDefinition:
    try:
        return catalog.datasheet_by_id(datasheet_id)
    except ArmyCatalogError as exc:
        raise ListValidationError("UnitMusterSelection datasheet_id was not found.") from exc


def _datasheet_has_faction_keyword(
    datasheet: DatasheetDefinition,
    keyword: str,
) -> bool:
    canonical = _canonical_keyword(keyword)
    return any(
        _canonical_keyword(stored) == canonical for stored in datasheet.keywords.faction_keywords
    )


def _canonical_keyword(value: str) -> str:
    return value.strip().replace("_", " ").replace("-", " ").upper()


def _catalog_faction_by_id(catalog: ArmyCatalog, faction_id: str) -> FactionDefinition:
    try:
        return catalog.faction_by_id(faction_id)
    except ArmyCatalogError as exc:
        raise ListValidationError("DetachmentSelection faction_id was not found.") from exc


def _catalog_detachment_by_id(
    catalog: ArmyCatalog,
    detachment_id: str,
) -> DetachmentDefinition:
    requested_id = _validate_identifier("detachment_id", detachment_id)
    for detachment in catalog.detachments:
        if detachment.detachment_id == requested_id:
            return detachment
    raise ListValidationError("DetachmentSelection detachment_id was not found.")


def _catalog_wargear_by_id(catalog: ArmyCatalog, wargear_id: str) -> Wargear:
    requested_id = _validate_identifier("wargear_id", wargear_id)
    for item in catalog.wargear:
        if item.wargear_id == requested_id:
            return item
    raise ListValidationError("WargearSelection wargear_id was not found in catalog.")


def _validate_catalog_contains_enhancements(
    catalog: ArmyCatalog,
    enhancement_ids: tuple[str, ...],
) -> None:
    catalog_ids = {enhancement.enhancement_id for enhancement in catalog.enhancements}
    for enhancement_id in enhancement_ids:
        if enhancement_id not in catalog_ids:
            raise ListValidationError("DetachmentSelection enhancement_id was not found.")


def _validate_catalog_contains_stratagems(
    catalog: ArmyCatalog,
    stratagem_ids: tuple[str, ...],
) -> None:
    catalog_ids = {stratagem.stratagem_id for stratagem in catalog.stratagems}
    for stratagem_id in stratagem_ids:
        if stratagem_id not in catalog_ids:
            raise ListValidationError("DetachmentSelection stratagem_id was not found.")


def _validate_selected_ids_are_allowed(
    *,
    field_name: str,
    selected_ids: tuple[str, ...],
    allowed_ids: tuple[str, ...],
) -> None:
    allowed = set(allowed_ids)
    for selected_id in selected_ids:
        if selected_id not in allowed:
            raise ListValidationError(f"{field_name} includes an ID not allowed by detachment.")


def _validate_model_count_against_composition(
    selection: ModelProfileSelection,
    composition: UnitCompositionDefinition,
) -> None:
    if selection.model_count < composition.min_models:
        raise ListValidationError("ModelProfileSelection model_count is below datasheet minimum.")
    if selection.model_count > composition.max_models:
        raise ListValidationError("ModelProfileSelection model_count exceeds datasheet maximum.")


def _validate_wargear_selection_against_option(
    selection: WargearSelection,
    option: DatasheetWargearOption,
) -> None:
    if selection.model_profile_id != option.model_profile_id:
        raise ListValidationError("WargearSelection model_profile_id does not match option.")
    selected_count = len(selection.wargear_ids)
    if selected_count < option.min_selections:
        raise ListValidationError("WargearSelection does not satisfy minimum selections.")
    if selected_count > option.max_selections:
        raise ListValidationError("WargearSelection exceeds maximum selections.")
    allowed = set(option.allowed_wargear_ids)
    for wargear_id in selection.wargear_ids:
        if wargear_id not in allowed:
            raise ListValidationError("WargearSelection includes wargear not allowed by option.")


def _validate_model_profile_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[ModelProfileSelection, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    if not values:
        raise ListValidationError(f"{field_name} must not be empty.")
    validated: list[ModelProfileSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not ModelProfileSelection:
            raise ListValidationError(f"{field_name} must contain ModelProfileSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_model_profile_selections(
    selections: tuple[ModelProfileSelection, ...],
) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.model_profile_id in seen:
            raise ListValidationError(
                "UnitMusterSelection model_profile_selections must not contain duplicates."
            )
        seen.add(selection.model_profile_id)


def _validate_wargear_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[WargearSelection, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[WargearSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not WargearSelection:
            raise ListValidationError(f"{field_name} must contain WargearSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_wargear_selections(
    selections: tuple[WargearSelection, ...],
) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.option_id in seen:
            raise ListValidationError("WargearSelection option_ids must be unique.")
        seen.add(selection.option_id)


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ListValidationError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ListValidationError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_unprefixed_identifier_tuple(
    field_name: str,
    values: object,
    prefix: str,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ListValidationError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        identifier = _validate_unprefixed_identifier(f"{field_name} value", value, prefix)
        if identifier in seen:
            raise ListValidationError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ListValidationError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise ListValidationError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise ListValidationError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ListValidationError(f"{field_name} must not be empty.")
    return stripped


def battle_size_from_token(token: object) -> BattleSize:
    if type(token) is BattleSize:
        return token
    if type(token) is not str:
        raise ListValidationError("BattleSize token must be a string.")
    try:
        return BattleSize(token)
    except ValueError as exc:
        raise ListValidationError(f"Unsupported BattleSize token: {token}.") from exc


def battle_size_mustering_policy(battle_size: BattleSize) -> BattleSizeMusteringPolicy:
    resolved_battle_size = battle_size_from_token(battle_size)
    if resolved_battle_size is BattleSize.STRIKE_FORCE:
        return BattleSizeMusteringPolicy.strike_force()
    raise ListValidationError(f"Unsupported BattleSize: {resolved_battle_size.value}.")


def _validate_positive_number(field_name: str, value: object) -> float:
    if not isinstance(value, int | float) or type(value) is bool:
        raise ListValidationError(f"{field_name} must be a number.")
    number = float(value)
    if number <= 0.0:
        raise ListValidationError(f"{field_name} must be greater than 0.")
    return number


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int:
        raise ListValidationError(f"{field_name} must be an integer.")
    if value < 1:
        raise ListValidationError(f"{field_name} must be at least 1.")
    return value
