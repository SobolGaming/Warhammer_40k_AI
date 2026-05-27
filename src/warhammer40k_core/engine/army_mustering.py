from __future__ import annotations

from dataclasses import dataclass
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.ruleset import RulesetError, RulesetId, RulesetIdPayload
from warhammer40k_core.engine.list_validation import (
    DetachmentSelection,
    DetachmentSelectionPayload,
    ListValidationError,
    UnitMusterSelection,
    UnitMusterSelectionPayload,
    validate_detachment_selection,
    validate_unit_selection_for_faction,
)
from warhammer40k_core.engine.unit_factory import (
    UnitFactory,
    UnitFactoryError,
    UnitInstance,
    UnitInstancePayload,
)


class ArmyMusteringError(ValueError):
    """Raised when army mustering violates CORE V2 invariants."""


class ArmyMusterRequestPayload(TypedDict):
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetIdPayload
    detachment_selection: DetachmentSelectionPayload
    unit_selections: list[UnitMusterSelectionPayload]


class ArmyDefinitionPayload(TypedDict):
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetIdPayload
    detachment_selection: DetachmentSelectionPayload
    units: list[UnitInstancePayload]


@dataclass(frozen=True, slots=True)
class ArmyMusterRequest:
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetId
    detachment_selection: DetachmentSelection
    unit_selections: tuple[UnitMusterSelection, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("ArmyMusterRequest army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ArmyMusterRequest player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "catalog_id",
            _validate_unprefixed_identifier(
                "ArmyMusterRequest catalog_id",
                self.catalog_id,
                "catalog:",
            ),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier(
                "ArmyMusterRequest source_package_id",
                self.source_package_id,
            ),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise ArmyMusteringError("ArmyMusterRequest ruleset_id must be a RulesetId.")
        if type(self.detachment_selection) is not DetachmentSelection:
            raise ArmyMusteringError(
                "ArmyMusterRequest detachment_selection must be a DetachmentSelection."
            )
        unit_selections = _validate_unit_muster_selection_tuple(
            "ArmyMusterRequest unit_selections",
            self.unit_selections,
        )
        _validate_unique_unit_selection_ids(unit_selections)
        object.__setattr__(self, "unit_selections", unit_selections)

    def to_payload(self) -> ArmyMusterRequestPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "detachment_selection": self.detachment_selection.to_payload(),
            "unit_selections": [selection.to_payload() for selection in self.unit_selections],
        }

    @classmethod
    def from_payload(cls, payload: ArmyMusterRequestPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            catalog_id=payload["catalog_id"],
            source_package_id=payload["source_package_id"],
            ruleset_id=_ruleset_id_from_payload(payload["ruleset_id"]),
            detachment_selection=DetachmentSelection.from_payload(payload["detachment_selection"]),
            unit_selections=tuple(
                UnitMusterSelection.from_payload(selection)
                for selection in payload["unit_selections"]
            ),
        )


@dataclass(frozen=True, slots=True)
class ArmyDefinition:
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetId
    detachment_selection: DetachmentSelection
    units: tuple[UnitInstance, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_id",
            _validate_unprefixed_identifier("ArmyDefinition army_id", self.army_id, "army:"),
        )
        object.__setattr__(
            self,
            "player_id",
            _validate_identifier("ArmyDefinition player_id", self.player_id),
        )
        object.__setattr__(
            self,
            "catalog_id",
            _validate_unprefixed_identifier(
                "ArmyDefinition catalog_id",
                self.catalog_id,
                "catalog:",
            ),
        )
        object.__setattr__(
            self,
            "source_package_id",
            _validate_identifier("ArmyDefinition source_package_id", self.source_package_id),
        )
        if type(self.ruleset_id) is not RulesetId:
            raise ArmyMusteringError("ArmyDefinition ruleset_id must be a RulesetId.")
        if type(self.detachment_selection) is not DetachmentSelection:
            raise ArmyMusteringError(
                "ArmyDefinition detachment_selection must be a DetachmentSelection."
            )
        units = _validate_unit_instance_tuple("ArmyDefinition units", self.units)
        _validate_unique_unit_instance_ids(units)
        _validate_unit_ids_scoped_to_army(army_id=self.army_id, units=units)
        object.__setattr__(self, "units", units)

    def stable_identity(self) -> str:
        return f"army:{self.army_id}"

    def unit_by_id(self, unit_instance_id: str) -> UnitInstance:
        requested_id = _validate_unprefixed_identifier(
            "unit_instance_id",
            unit_instance_id,
            "unit:",
        )
        for unit in self.units:
            if unit.unit_instance_id == requested_id:
                return unit
        raise ArmyMusteringError("ArmyDefinition unit_instance_id was not found.")

    def to_payload(self) -> ArmyDefinitionPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "detachment_selection": self.detachment_selection.to_payload(),
            "units": [unit.to_payload() for unit in self.units],
        }

    @classmethod
    def from_payload(cls, payload: ArmyDefinitionPayload) -> Self:
        return cls(
            army_id=payload["army_id"],
            player_id=payload["player_id"],
            catalog_id=payload["catalog_id"],
            source_package_id=payload["source_package_id"],
            ruleset_id=_ruleset_id_from_payload(payload["ruleset_id"]),
            detachment_selection=DetachmentSelection.from_payload(payload["detachment_selection"]),
            units=tuple(_unit_instance_from_payload(unit) for unit in payload["units"]),
        )


def muster_army(*, catalog: ArmyCatalog, request: ArmyMusterRequest) -> ArmyDefinition:
    if type(catalog) is not ArmyCatalog:
        raise ArmyMusteringError("catalog must be an ArmyCatalog.")
    if type(request) is not ArmyMusterRequest:
        raise ArmyMusteringError("request must be an ArmyMusterRequest.")
    _validate_request_matches_catalog(catalog=catalog, request=request)
    try:
        faction, _detachment = validate_detachment_selection(
            catalog=catalog,
            selection=request.detachment_selection,
        )
    except ListValidationError as exc:
        raise ArmyMusteringError("ArmyMusterRequest detachment selection is invalid.") from exc

    factory = UnitFactory(catalog)
    units: list[UnitInstance] = []
    for selection in request.unit_selections:
        try:
            datasheet = validate_unit_selection_for_faction(
                catalog=catalog,
                selection=selection,
                faction=faction,
            )
            units.append(
                factory.instantiate_unit(
                    army_id=request.army_id,
                    selection=selection,
                    datasheet=datasheet,
                )
            )
        except (ListValidationError, UnitFactoryError) as exc:
            raise ArmyMusteringError("ArmyMusterRequest unit selection is invalid.") from exc
    return ArmyDefinition(
        army_id=request.army_id,
        player_id=request.player_id,
        catalog_id=request.catalog_id,
        source_package_id=request.source_package_id,
        ruleset_id=request.ruleset_id,
        detachment_selection=request.detachment_selection,
        units=tuple(units),
    )


def _validate_request_matches_catalog(
    *,
    catalog: ArmyCatalog,
    request: ArmyMusterRequest,
) -> None:
    if request.catalog_id != catalog.catalog_id:
        raise ArmyMusteringError("ArmyMusterRequest catalog_id does not match catalog.")
    if request.source_package_id != catalog.source_package_id:
        raise ArmyMusteringError("ArmyMusterRequest source_package_id does not match catalog.")
    if request.ruleset_id != catalog.ruleset_id:
        raise ArmyMusteringError("ArmyMusterRequest ruleset_id does not match catalog.")


def _ruleset_id_from_payload(payload: RulesetIdPayload) -> RulesetId:
    try:
        return RulesetId.from_payload(payload)
    except RulesetError as exc:
        raise ArmyMusteringError("ruleset_id payload is invalid.") from exc


def _unit_instance_from_payload(payload: UnitInstancePayload) -> UnitInstance:
    try:
        return UnitInstance.from_payload(payload)
    except UnitFactoryError as exc:
        raise ArmyMusteringError("ArmyDefinition unit payload is invalid.") from exc


def _validate_unit_muster_selection_tuple(
    field_name: str,
    values: object,
) -> tuple[UnitMusterSelection, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyMusteringError(f"{field_name} must not be empty.")
    validated: list[UnitMusterSelection] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not UnitMusterSelection:
            raise ArmyMusteringError(f"{field_name} must contain UnitMusterSelection values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_unit_selection_ids(selections: tuple[UnitMusterSelection, ...]) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.unit_selection_id in seen:
            raise ArmyMusteringError("ArmyMusterRequest unit_selections must have unique IDs.")
        seen.add(selection.unit_selection_id)


def _validate_unit_instance_tuple(
    field_name: str,
    values: object,
) -> tuple[UnitInstance, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    if not values:
        raise ArmyMusteringError(f"{field_name} must not be empty.")
    validated: list[UnitInstance] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not UnitInstance:
            raise ArmyMusteringError(f"{field_name} must contain UnitInstance values.")
        validated.append(value)
    return tuple(validated)


def _validate_unique_unit_instance_ids(units: tuple[UnitInstance, ...]) -> None:
    seen: set[str] = set()
    for unit in units:
        if unit.unit_instance_id in seen:
            raise ArmyMusteringError("ArmyDefinition units must have unique IDs.")
        seen.add(unit.unit_instance_id)


def _validate_unit_ids_scoped_to_army(
    *,
    army_id: str,
    units: tuple[UnitInstance, ...],
) -> None:
    for unit in units:
        if not unit.unit_instance_id.startswith(f"{army_id}:"):
            raise ArmyMusteringError("ArmyDefinition unit IDs must be scoped to army_id.")


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    identifier = _validate_identifier(field_name, value)
    if identifier.startswith(prefix):
        raise ArmyMusteringError(f"{field_name} must not include the stable identity prefix.")
    return identifier


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise ArmyMusteringError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise ArmyMusteringError(f"{field_name} must not be empty.")
    return stripped
