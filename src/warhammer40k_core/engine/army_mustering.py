from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Self, TypedDict, cast

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.datasheet import (
    AttachmentEligibility,
    AttachmentRole,
    DatasheetDefinition,
)
from warhammer40k_core.core.ruleset import RulesetError, RulesetId, RulesetIdPayload
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    AttachmentDeclarationPayload,
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
    attachment_declarations: list[AttachmentDeclarationPayload]


class AttachedUnitFormationPayload(TypedDict):
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: list[str]
    support_unit_instance_ids: list[str]
    component_unit_instance_ids: list[str]
    source_id: str


class ArmyDefinitionPayload(TypedDict):
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetIdPayload
    detachment_selection: DetachmentSelectionPayload
    units: list[UnitInstancePayload]
    attached_units: list[AttachedUnitFormationPayload]


@dataclass(frozen=True, slots=True)
class ArmyMusterRequest:
    army_id: str
    player_id: str
    catalog_id: str
    source_package_id: str
    ruleset_id: RulesetId
    detachment_selection: DetachmentSelection
    unit_selections: tuple[UnitMusterSelection, ...]
    attachment_declarations: tuple[AttachmentDeclaration, ...] = ()

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
        attachment_declarations = _validate_attachment_declaration_tuple(
            "ArmyMusterRequest attachment_declarations",
            self.attachment_declarations,
        )
        _validate_unique_attachment_source_ids(attachment_declarations)
        object.__setattr__(self, "attachment_declarations", attachment_declarations)

    def to_payload(self) -> ArmyMusterRequestPayload:
        return {
            "army_id": self.army_id,
            "player_id": self.player_id,
            "catalog_id": self.catalog_id,
            "source_package_id": self.source_package_id,
            "ruleset_id": self.ruleset_id.to_payload(),
            "detachment_selection": self.detachment_selection.to_payload(),
            "unit_selections": [selection.to_payload() for selection in self.unit_selections],
            "attachment_declarations": [
                declaration.to_payload() for declaration in self.attachment_declarations
            ],
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
            attachment_declarations=tuple(
                AttachmentDeclaration.from_payload(declaration)
                for declaration in payload["attachment_declarations"]
            ),
        )


@dataclass(frozen=True, slots=True)
class AttachedUnitFormation:
    attached_unit_instance_id: str
    bodyguard_unit_instance_id: str
    leader_unit_instance_ids: tuple[str, ...] = ()
    support_unit_instance_ids: tuple[str, ...] = ()
    component_unit_instance_ids: tuple[str, ...] = ()
    source_id: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "attached_unit_instance_id",
            _validate_attached_unit_instance_id(
                "AttachedUnitFormation attached_unit_instance_id",
                self.attached_unit_instance_id,
            ),
        )
        object.__setattr__(
            self,
            "bodyguard_unit_instance_id",
            _validate_identifier(
                "AttachedUnitFormation bodyguard_unit_instance_id",
                self.bodyguard_unit_instance_id,
            ),
        )
        leader_ids = _validate_identifier_tuple(
            "AttachedUnitFormation leader_unit_instance_ids",
            self.leader_unit_instance_ids,
            min_length=0,
        )
        support_ids = _validate_identifier_tuple(
            "AttachedUnitFormation support_unit_instance_ids",
            self.support_unit_instance_ids,
            min_length=0,
        )
        if not leader_ids and not support_ids:
            raise ArmyMusteringError("AttachedUnitFormation requires a leader or support unit.")
        component_ids = _validate_identifier_tuple(
            "AttachedUnitFormation component_unit_instance_ids",
            self.component_unit_instance_ids,
            min_length=2,
        )
        expected_component_ids = tuple(
            sorted((self.bodyguard_unit_instance_id, *leader_ids, *support_ids))
        )
        if component_ids != expected_component_ids:
            raise ArmyMusteringError(
                "AttachedUnitFormation component_unit_instance_ids must match components."
            )
        object.__setattr__(self, "leader_unit_instance_ids", leader_ids)
        object.__setattr__(self, "support_unit_instance_ids", support_ids)
        object.__setattr__(self, "component_unit_instance_ids", component_ids)
        object.__setattr__(
            self,
            "source_id",
            _validate_identifier("AttachedUnitFormation source_id", self.source_id),
        )

    def to_payload(self) -> AttachedUnitFormationPayload:
        return {
            "attached_unit_instance_id": self.attached_unit_instance_id,
            "bodyguard_unit_instance_id": self.bodyguard_unit_instance_id,
            "leader_unit_instance_ids": list(self.leader_unit_instance_ids),
            "support_unit_instance_ids": list(self.support_unit_instance_ids),
            "component_unit_instance_ids": list(self.component_unit_instance_ids),
            "source_id": self.source_id,
        }

    @classmethod
    def from_payload(cls, payload: AttachedUnitFormationPayload) -> Self:
        return cls(
            attached_unit_instance_id=payload["attached_unit_instance_id"],
            bodyguard_unit_instance_id=payload["bodyguard_unit_instance_id"],
            leader_unit_instance_ids=tuple(payload["leader_unit_instance_ids"]),
            support_unit_instance_ids=tuple(payload["support_unit_instance_ids"]),
            component_unit_instance_ids=tuple(payload["component_unit_instance_ids"]),
            source_id=payload["source_id"],
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
    attached_units: tuple[AttachedUnitFormation, ...] = ()

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
        attached_units = _validate_attached_unit_formation_tuple(
            "ArmyDefinition attached_units",
            self.attached_units,
        )
        _validate_attached_unit_formations_reference_units(
            army_id=self.army_id,
            units=units,
            attached_units=attached_units,
        )
        object.__setattr__(self, "attached_units", attached_units)

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
            "attached_units": [attached.to_payload() for attached in self.attached_units],
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
            attached_units=tuple(
                AttachedUnitFormation.from_payload(attached)
                for attached in payload["attached_units"]
            ),
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
    datasheets_by_selection_id: dict[str, DatasheetDefinition] = {}
    for selection in request.unit_selections:
        try:
            datasheet = validate_unit_selection_for_faction(
                catalog=catalog,
                selection=selection,
                faction=faction,
            )
            datasheets_by_selection_id[selection.unit_selection_id] = datasheet
            units.append(
                factory.instantiate_unit(
                    army_id=request.army_id,
                    selection=selection,
                    datasheet=datasheet,
                )
            )
        except (ListValidationError, UnitFactoryError) as exc:
            raise ArmyMusteringError("ArmyMusterRequest unit selection is invalid.") from exc
    resolved_units, attached_units = _resolve_attached_unit_formations(
        request=request,
        units=tuple(units),
        datasheets_by_selection_id=datasheets_by_selection_id,
    )
    return ArmyDefinition(
        army_id=request.army_id,
        player_id=request.player_id,
        catalog_id=request.catalog_id,
        source_package_id=request.source_package_id,
        ruleset_id=request.ruleset_id,
        detachment_selection=request.detachment_selection,
        units=resolved_units,
        attached_units=attached_units,
    )


def _resolve_attached_unit_formations(
    *,
    request: ArmyMusterRequest,
    units: tuple[UnitInstance, ...],
    datasheets_by_selection_id: dict[str, DatasheetDefinition],
) -> tuple[tuple[UnitInstance, ...], tuple[AttachedUnitFormation, ...]]:
    if not request.attachment_declarations:
        return units, ()
    units_by_selection_id = {
        unit.unit_instance_id.removeprefix(f"{request.army_id}:"): unit for unit in units
    }
    grouped: dict[str, dict[AttachmentRole, UnitInstance]] = {}
    for declaration in request.attachment_declarations:
        source_unit = units_by_selection_id.get(declaration.source_unit_selection_id)
        bodyguard_unit = units_by_selection_id.get(declaration.bodyguard_unit_selection_id)
        if source_unit is None:
            raise ArmyMusteringError("AttachmentDeclaration source unit was not mustered.")
        if bodyguard_unit is None:
            raise ArmyMusteringError("AttachmentDeclaration bodyguard unit was not mustered.")
        source_datasheet = datasheets_by_selection_id[declaration.source_unit_selection_id]
        bodyguard_datasheet = datasheets_by_selection_id[declaration.bodyguard_unit_selection_id]
        eligibility = _attachment_eligibility_for_datasheet(source_datasheet)
        if bodyguard_datasheet.datasheet_id not in eligibility.allowed_bodyguard_datasheet_ids:
            raise ArmyMusteringError(
                "AttachmentDeclaration bodyguard datasheet is not allowed by source datasheet."
            )
        role_group = grouped.setdefault(declaration.bodyguard_unit_selection_id, {})
        if eligibility.role in role_group:
            raise ArmyMusteringError(
                "AttachmentDeclaration exceeds one Leader or one Support per bodyguard."
            )
        role_group[eligibility.role] = source_unit

    formations: list[AttachedUnitFormation] = []
    roles_by_unit_id: dict[str, str] = {}
    claimed_component_ids: set[str] = set()
    for bodyguard_selection_id in sorted(grouped):
        bodyguard_unit = units_by_selection_id[bodyguard_selection_id]
        role_group = grouped[bodyguard_selection_id]
        leader_ids = tuple(
            sorted(
                unit.unit_instance_id
                for role, unit in role_group.items()
                if role is AttachmentRole.LEADER
            )
        )
        support_ids = tuple(
            sorted(
                unit.unit_instance_id
                for role, unit in role_group.items()
                if role is AttachmentRole.SUPPORT
            )
        )
        component_ids = tuple(sorted((bodyguard_unit.unit_instance_id, *leader_ids, *support_ids)))
        overlap = claimed_component_ids.intersection(component_ids)
        if overlap:
            raise ArmyMusteringError(
                "AttachmentDeclaration cannot place a unit in multiple attached units."
            )
        claimed_component_ids.update(component_ids)
        attached_unit_id = f"attached-unit:{request.army_id}:{bodyguard_selection_id}"
        source_id = f"attached-unit-join:{request.army_id}:{bodyguard_selection_id}"
        formations.append(
            AttachedUnitFormation(
                attached_unit_instance_id=attached_unit_id,
                bodyguard_unit_instance_id=bodyguard_unit.unit_instance_id,
                leader_unit_instance_ids=leader_ids,
                support_unit_instance_ids=support_ids,
                component_unit_instance_ids=component_ids,
                source_id=source_id,
            )
        )
        roles_by_unit_id[bodyguard_unit.unit_instance_id] = "bodyguard"
        for unit_id in leader_ids:
            roles_by_unit_id[unit_id] = "leader"
        for unit_id in support_ids:
            roles_by_unit_id[unit_id] = "support"

    return (
        tuple(
            _unit_with_attached_role_evidence(
                unit,
                role=roles_by_unit_id.get(unit.unit_instance_id),
            )
            for unit in units
        ),
        tuple(sorted(formations, key=lambda formation: formation.attached_unit_instance_id)),
    )


def _attachment_eligibility_for_datasheet(
    datasheet: DatasheetDefinition,
) -> AttachmentEligibility:
    if type(datasheet) is not DatasheetDefinition:
        raise ArmyMusteringError("Attachment eligibility lookup requires a DatasheetDefinition.")
    eligibilities: tuple[AttachmentEligibility, ...] = datasheet.attachment_eligibilities
    if not eligibilities:
        raise ArmyMusteringError(
            "AttachmentDeclaration source datasheet has no attachment eligibility."
        )
    if len(eligibilities) > 1:
        raise ArmyMusteringError(
            "AttachmentDeclaration source datasheet must declare exactly one attachment role."
        )
    for eligibility in eligibilities:
        return eligibility
    raise ArmyMusteringError(
        "AttachmentDeclaration source datasheet has no attachment eligibility."
    )


def _unit_with_attached_role_evidence(
    unit: UnitInstance,
    *,
    role: str | None,
) -> UnitInstance:
    if role is None:
        return unit
    evidence = {f"runtime-attached-unit:{role}"}
    if role in {"leader", "support"}:
        evidence.add(f"attached-role:{role}")
    return replace(
        unit,
        keywords=tuple(sorted({*unit.keywords, "ATTACHED_UNIT"})),
        own_models=tuple(
            replace(
                model,
                source_ids=tuple(sorted({*model.source_ids, *evidence})),
            )
            for model in unit.own_models
        ),
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


def _validate_attachment_declaration_tuple(
    field_name: str,
    values: object,
) -> tuple[AttachmentDeclaration, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[AttachmentDeclaration] = []
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not AttachmentDeclaration:
            raise ArmyMusteringError(f"{field_name} must contain AttachmentDeclaration values.")
        validated.append(value)
    return tuple(
        sorted(
            validated,
            key=lambda declaration: (
                declaration.bodyguard_unit_selection_id,
                declaration.source_unit_selection_id,
            ),
        )
    )


def _validate_unique_unit_selection_ids(selections: tuple[UnitMusterSelection, ...]) -> None:
    seen: set[str] = set()
    for selection in selections:
        if selection.unit_selection_id in seen:
            raise ArmyMusteringError("ArmyMusterRequest unit_selections must have unique IDs.")
        seen.add(selection.unit_selection_id)


def _validate_unique_attachment_source_ids(
    declarations: tuple[AttachmentDeclaration, ...],
) -> None:
    seen: set[str] = set()
    for declaration in declarations:
        if declaration.source_unit_selection_id in seen:
            raise ArmyMusteringError(
                "ArmyMusterRequest attachment_declarations must have unique source unit IDs."
            )
        seen.add(declaration.source_unit_selection_id)


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


def _validate_attached_unit_formation_tuple(
    field_name: str,
    values: object,
) -> tuple[AttachedUnitFormation, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[AttachedUnitFormation] = []
    seen_ids: set[str] = set()
    raw_values = cast(tuple[object, ...], values)
    for value in raw_values:
        if type(value) is not AttachedUnitFormation:
            raise ArmyMusteringError(f"{field_name} must contain AttachedUnitFormation values.")
        if value.attached_unit_instance_id in seen_ids:
            raise ArmyMusteringError(f"{field_name} must not contain duplicate attached IDs.")
        seen_ids.add(value.attached_unit_instance_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda formation: formation.attached_unit_instance_id))


def _validate_unique_unit_instance_ids(units: tuple[UnitInstance, ...]) -> None:
    seen: set[str] = set()
    for unit in units:
        if unit.unit_instance_id in seen:
            raise ArmyMusteringError("ArmyDefinition units must have unique IDs.")
        seen.add(unit.unit_instance_id)


def _validate_attached_unit_formations_reference_units(
    *,
    army_id: str,
    units: tuple[UnitInstance, ...],
    attached_units: tuple[AttachedUnitFormation, ...],
) -> None:
    requested_army_id = _validate_unprefixed_identifier("army_id", army_id, "army:")
    unit_ids = {unit.unit_instance_id for unit in units}
    claimed_component_ids: set[str] = set()
    for attached_unit in attached_units:
        if not attached_unit.attached_unit_instance_id.startswith(
            f"attached-unit:{requested_army_id}:"
        ):
            raise ArmyMusteringError("AttachedUnitFormation attached ID must be scoped to army_id.")
        if attached_unit.attached_unit_instance_id in unit_ids:
            raise ArmyMusteringError("AttachedUnitFormation identity must not be a physical unit.")
        for component_id in attached_unit.component_unit_instance_ids:
            if component_id not in unit_ids:
                raise ArmyMusteringError("AttachedUnitFormation references an unknown unit.")
            if component_id in claimed_component_ids:
                raise ArmyMusteringError("AttachedUnitFormation component units must not overlap.")
            claimed_component_ids.add(component_id)


def _validate_unit_ids_scoped_to_army(
    *,
    army_id: str,
    units: tuple[UnitInstance, ...],
) -> None:
    for unit in units:
        if not unit.unit_instance_id.startswith(f"{army_id}:"):
            raise ArmyMusteringError("ArmyDefinition unit IDs must be scoped to army_id.")


def _validate_identifier_tuple(
    field_name: str,
    values: object,
    *,
    min_length: int,
) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise ArmyMusteringError(f"{field_name} must be a tuple.")
    validated: list[str] = []
    seen: set[str] = set()
    for value in cast(tuple[object, ...], values):
        identifier = _validate_identifier(f"{field_name} value", value)
        if identifier in seen:
            raise ArmyMusteringError(f"{field_name} must not contain duplicates.")
        seen.add(identifier)
        validated.append(identifier)
    if len(validated) < min_length:
        raise ArmyMusteringError(f"{field_name} must contain at least {min_length} values.")
    return tuple(sorted(validated))


def _validate_attached_unit_instance_id(field_name: str, value: object) -> str:
    identifier = _validate_identifier(field_name, value)
    if not identifier.startswith("attached-unit:"):
        raise ArmyMusteringError(f"{field_name} must use attached-unit identity.")
    return identifier


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
