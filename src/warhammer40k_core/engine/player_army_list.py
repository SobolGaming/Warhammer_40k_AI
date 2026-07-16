from __future__ import annotations

from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path
from typing import Self, TypedDict, cast

import msgspec

from warhammer40k_core.core.army_catalog import ArmyCatalog
from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.engine.army_mustering import (
    ArmyMusteringError,
    ArmyMusterRequest,
    DedicatedTransportManifest,
    DedicatedTransportManifestPayload,
    EnhancementAssignment,
    EnhancementAssignmentPayload,
    WarlordSelection,
    WarlordSelectionPayload,
)
from warhammer40k_core.engine.army_points import (
    ArmyPointsError,
    MfmArmyPointCalculation,
    calculate_mfm_army_points,
)
from warhammer40k_core.engine.list_validation import (
    AttachmentDeclaration,
    AttachmentDeclarationPayload,
    BattleSize,
    DetachmentSelection,
    DetachmentSelectionPayload,
    UnitMusterSelection,
    UnitMusterSelectionPayload,
    battle_size_from_token,
)
from warhammer40k_core.engine.list_validation_errors import (
    ListValidationError,
)
from warhammer40k_core.rules.mfm_source import MfmSourcePackage

PLAYER_ARMY_LIST_ARTIFACT_SCHEMA = "core-v2-player-army-list-v1"


class PlayerArmyListError(ValueError):
    """Raised when a player-provided army-list artifact is invalid or stale."""


class PlayerArmyListGameResult(StrEnum):
    WIN = "win"
    LOSS = "loss"
    DRAW = "draw"


class PlayerArmyListProvenancePayload(TypedDict):
    source_format: str
    app_version: str
    data_version: str
    game_result: str
    points_source_package_id: str


class PlayerArmyListUnitPayload(TypedDict):
    selection: UnitMusterSelectionPayload
    declared_points: int


class PlayerArmyListPayload(TypedDict):
    artifact_schema: str
    army_list_id: str
    name: str
    faction_id: str
    detachment_selection: DetachmentSelectionPayload
    force_disposition_id: str
    battle_size: str
    declared_total_points: int
    units: list[PlayerArmyListUnitPayload]
    attachment_declarations: list[AttachmentDeclarationPayload]
    enhancement_assignments: list[EnhancementAssignmentPayload]
    warlord_selection: WarlordSelectionPayload | None
    dedicated_transport_manifests: list[DedicatedTransportManifestPayload]
    provenance: PlayerArmyListProvenancePayload


@dataclass(frozen=True, slots=True)
class PlayerArmyListProvenance:
    source_format: str
    app_version: str
    data_version: str
    game_result: PlayerArmyListGameResult
    points_source_package_id: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_format",
            _validate_text("PlayerArmyListProvenance source_format", self.source_format),
        )
        object.__setattr__(
            self,
            "app_version",
            _validate_text("PlayerArmyListProvenance app_version", self.app_version),
        )
        object.__setattr__(
            self,
            "data_version",
            _validate_text("PlayerArmyListProvenance data_version", self.data_version),
        )
        if type(self.game_result) is not PlayerArmyListGameResult:
            raise PlayerArmyListError(
                "PlayerArmyListProvenance game_result must be a PlayerArmyListGameResult."
            )
        object.__setattr__(
            self,
            "points_source_package_id",
            _validate_identifier(
                "PlayerArmyListProvenance points_source_package_id",
                self.points_source_package_id,
            ),
        )

    def to_payload(self) -> PlayerArmyListProvenancePayload:
        return {
            "source_format": self.source_format,
            "app_version": self.app_version,
            "data_version": self.data_version,
            "game_result": self.game_result.value,
            "points_source_package_id": self.points_source_package_id,
        }

    @classmethod
    def from_payload(cls, payload: PlayerArmyListProvenancePayload) -> Self:
        try:
            game_result = PlayerArmyListGameResult(payload["game_result"])
        except ValueError as exc:
            raise PlayerArmyListError(
                "PlayerArmyListProvenance game_result is unsupported."
            ) from exc
        return cls(
            source_format=payload["source_format"],
            app_version=payload["app_version"],
            data_version=payload["data_version"],
            game_result=game_result,
            points_source_package_id=payload["points_source_package_id"],
        )


@dataclass(frozen=True, slots=True)
class PlayerArmyListUnit:
    selection: UnitMusterSelection
    declared_points: int

    def __post_init__(self) -> None:
        if type(self.selection) is not UnitMusterSelection:
            raise PlayerArmyListError("PlayerArmyListUnit selection must be a UnitMusterSelection.")
        object.__setattr__(
            self,
            "declared_points",
            _validate_positive_int(
                "PlayerArmyListUnit declared_points",
                self.declared_points,
            ),
        )

    def to_payload(self) -> PlayerArmyListUnitPayload:
        return {
            "selection": self.selection.to_payload(),
            "declared_points": self.declared_points,
        }

    @classmethod
    def from_payload(cls, payload: PlayerArmyListUnitPayload) -> Self:
        return cls(
            selection=UnitMusterSelection.from_payload(payload["selection"]),
            declared_points=payload["declared_points"],
        )


@dataclass(frozen=True, slots=True)
class PlayerArmyList:
    army_list_id: str
    name: str
    faction_id: str
    detachment_selection: DetachmentSelection
    force_disposition_id: str
    battle_size: BattleSize
    declared_total_points: int
    units: tuple[PlayerArmyListUnit, ...]
    provenance: PlayerArmyListProvenance
    attachment_declarations: tuple[AttachmentDeclaration, ...] = ()
    enhancement_assignments: tuple[EnhancementAssignment, ...] = ()
    warlord_selection: WarlordSelection | None = None
    dedicated_transport_manifests: tuple[DedicatedTransportManifest, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "army_list_id",
            _validate_unprefixed_identifier(
                "PlayerArmyList army_list_id",
                self.army_list_id,
                "army-list:",
            ),
        )
        object.__setattr__(self, "name", _validate_text("PlayerArmyList name", self.name))
        object.__setattr__(
            self,
            "faction_id",
            _validate_unprefixed_identifier(
                "PlayerArmyList faction_id",
                self.faction_id,
                "faction:",
            ),
        )
        if type(self.detachment_selection) is not DetachmentSelection:
            raise PlayerArmyListError(
                "PlayerArmyList detachment_selection must be a DetachmentSelection."
            )
        if self.detachment_selection.faction_id != self.faction_id:
            raise PlayerArmyListError(
                "PlayerArmyList faction_id must match its DetachmentSelection."
            )
        object.__setattr__(
            self,
            "force_disposition_id",
            _validate_unprefixed_identifier(
                "PlayerArmyList force_disposition_id",
                self.force_disposition_id,
                "force-disposition:",
            ),
        )
        try:
            battle_size = battle_size_from_token(self.battle_size)
        except ListValidationError as exc:
            raise PlayerArmyListError("PlayerArmyList battle_size is invalid.") from exc
        object.__setattr__(self, "battle_size", battle_size)
        object.__setattr__(
            self,
            "declared_total_points",
            _validate_positive_int(
                "PlayerArmyList declared_total_points",
                self.declared_total_points,
            ),
        )
        units = _validate_units(self.units)
        if sum(unit.declared_points for unit in units) != self.declared_total_points:
            raise PlayerArmyListError(
                "PlayerArmyList declared unit points must sum to declared_total_points."
            )
        object.__setattr__(self, "units", units)
        if type(self.provenance) is not PlayerArmyListProvenance:
            raise PlayerArmyListError("PlayerArmyList provenance must be PlayerArmyListProvenance.")
        object.__setattr__(
            self,
            "attachment_declarations",
            _validate_domain_tuple(
                "PlayerArmyList attachment_declarations",
                self.attachment_declarations,
                AttachmentDeclaration,
            ),
        )
        object.__setattr__(
            self,
            "enhancement_assignments",
            _validate_domain_tuple(
                "PlayerArmyList enhancement_assignments",
                self.enhancement_assignments,
                EnhancementAssignment,
            ),
        )
        if (
            self.warlord_selection is not None
            and type(self.warlord_selection) is not WarlordSelection
        ):
            raise PlayerArmyListError(
                "PlayerArmyList warlord_selection must be a WarlordSelection or None."
            )
        object.__setattr__(
            self,
            "dedicated_transport_manifests",
            _validate_domain_tuple(
                "PlayerArmyList dedicated_transport_manifests",
                self.dedicated_transport_manifests,
                DedicatedTransportManifest,
            ),
        )

    def to_payload(self) -> PlayerArmyListPayload:
        return {
            "artifact_schema": PLAYER_ARMY_LIST_ARTIFACT_SCHEMA,
            "army_list_id": self.army_list_id,
            "name": self.name,
            "faction_id": self.faction_id,
            "detachment_selection": self.detachment_selection.to_payload(),
            "force_disposition_id": self.force_disposition_id,
            "battle_size": self.battle_size.value,
            "declared_total_points": self.declared_total_points,
            "units": [unit.to_payload() for unit in self.units],
            "attachment_declarations": [
                declaration.to_payload() for declaration in self.attachment_declarations
            ],
            "enhancement_assignments": [
                assignment.to_payload() for assignment in self.enhancement_assignments
            ],
            "warlord_selection": (
                None if self.warlord_selection is None else self.warlord_selection.to_payload()
            ),
            "dedicated_transport_manifests": [
                manifest.to_payload() for manifest in self.dedicated_transport_manifests
            ],
            "provenance": self.provenance.to_payload(),
        }

    @classmethod
    def from_payload(cls, payload: PlayerArmyListPayload) -> Self:
        if payload["artifact_schema"] != PLAYER_ARMY_LIST_ARTIFACT_SCHEMA:
            raise PlayerArmyListError("Player army-list artifact schema is unsupported.")
        warlord_payload = payload["warlord_selection"]
        return cls(
            army_list_id=payload["army_list_id"],
            name=payload["name"],
            faction_id=payload["faction_id"],
            detachment_selection=DetachmentSelection.from_payload(payload["detachment_selection"]),
            force_disposition_id=payload["force_disposition_id"],
            battle_size=battle_size_from_token(payload["battle_size"]),
            declared_total_points=payload["declared_total_points"],
            units=tuple(PlayerArmyListUnit.from_payload(unit) for unit in payload["units"]),
            attachment_declarations=tuple(
                AttachmentDeclaration.from_payload(declaration)
                for declaration in payload["attachment_declarations"]
            ),
            enhancement_assignments=tuple(
                EnhancementAssignment.from_payload(assignment)
                for assignment in payload["enhancement_assignments"]
            ),
            warlord_selection=(
                None if warlord_payload is None else WarlordSelection.from_payload(warlord_payload)
            ),
            dedicated_transport_manifests=tuple(
                DedicatedTransportManifest.from_payload(manifest)
                for manifest in payload["dedicated_transport_manifests"]
            ),
            provenance=PlayerArmyListProvenance.from_payload(payload["provenance"]),
        )


class _PlayerArmyListArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    army_list_id: str
    name: str
    faction_id: str
    detachment_selection: dict[str, object]
    force_disposition_id: str
    battle_size: str
    declared_total_points: int
    units: list[dict[str, object]]
    attachment_declarations: list[dict[str, object]]
    enhancement_assignments: list[dict[str, object]]
    warlord_selection: dict[str, object] | None
    dedicated_transport_manifests: list[dict[str, object]]
    provenance: dict[str, object]


def player_army_list_from_json_bytes(raw: bytes) -> PlayerArmyList:
    if type(raw) is not bytes:
        raise PlayerArmyListError("Player army-list artifact input must be bytes.")
    try:
        artifact = msgspec.json.decode(raw, type=_PlayerArmyListArtifact)
    except msgspec.DecodeError as exc:
        raise PlayerArmyListError("Player army-list JSON artifact is invalid.") from exc
    builtins = msgspec.to_builtins(artifact)
    if type(builtins) is not dict:
        raise PlayerArmyListError("Player army-list JSON artifact must be an object.")
    payload = cast(PlayerArmyListPayload, builtins)
    try:
        army_list = PlayerArmyList.from_payload(payload)
    except (ArmyMusteringError, KeyError, ListValidationError, TypeError) as exc:
        raise PlayerArmyListError("Player army-list payload is invalid.") from exc
    if cast(dict[str, object], army_list.to_payload()) != builtins:
        raise PlayerArmyListError(
            "Player army-list payload contains unsupported or non-canonical fields."
        )
    return army_list


def load_player_army_list(path: Path) -> PlayerArmyList:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise PlayerArmyListError("Player army-list artifact could not be read.") from exc
    return player_army_list_from_json_bytes(raw)


def army_muster_request_from_player_army_list(
    *,
    catalog: ArmyCatalog,
    army_list: PlayerArmyList,
    points_source_package: MfmSourcePackage,
    army_id: str,
    player_id: str,
) -> ArmyMusterRequest:
    if type(catalog) is not ArmyCatalog:
        raise PlayerArmyListError("Player army-list mustering requires an ArmyCatalog.")
    if type(army_list) is not PlayerArmyList:
        raise PlayerArmyListError("army_list must be a PlayerArmyList.")
    if type(points_source_package) is not MfmSourcePackage:
        raise PlayerArmyListError("Player army-list mustering requires an MfmSourcePackage.")
    if army_list.provenance.points_source_package_id != points_source_package.source_package_id:
        raise PlayerArmyListError("Player army-list MFM source package identity drifted.")
    request = ArmyMusterRequest(
        army_id=army_id,
        player_id=player_id,
        catalog_id=catalog.catalog_id,
        source_package_id=catalog.source_package_id,
        ruleset_id=catalog.ruleset_id,
        detachment_selection=army_list.detachment_selection,
        force_disposition_id=army_list.force_disposition_id,
        unit_selections=tuple(unit.selection for unit in army_list.units),
        attachment_declarations=army_list.attachment_declarations,
        enhancement_assignments=army_list.enhancement_assignments,
        warlord_selection=army_list.warlord_selection,
        dedicated_transport_manifests=army_list.dedicated_transport_manifests,
        roster_legality_required=True,
        battle_size=army_list.battle_size,
    )
    try:
        calculation = calculate_mfm_army_points(
            catalog=catalog,
            request=request,
            source_package=points_source_package,
        )
    except ArmyPointsError as exc:
        raise PlayerArmyListError(
            "Player army-list points could not be resolved from the selected MFM package."
        ) from exc
    _validate_declared_points(army_list=army_list, calculation=calculation)
    return replace(request, unit_points=calculation.roster_unit_point_values())


def _validate_declared_points(
    *,
    army_list: PlayerArmyList,
    calculation: MfmArmyPointCalculation,
) -> None:
    calculated_by_unit_id = {
        line.unit_selection_id: line.total_points for line in calculation.unit_lines
    }
    for enhancement_line in calculation.enhancement_lines:
        if enhancement_line.target_unit_selection_id not in calculated_by_unit_id:
            raise PlayerArmyListError(
                "Player army-list Enhancement target does not reference a selected unit."
            )
        calculated_by_unit_id[enhancement_line.target_unit_selection_id] += enhancement_line.points
    for unit in army_list.units:
        calculated_points = calculated_by_unit_id.get(unit.selection.unit_selection_id)
        if calculated_points is None or calculated_points != unit.declared_points:
            raise PlayerArmyListError(
                "Player army-list declared unit points do not match MFM calculation."
            )
    if calculation.total_points != army_list.declared_total_points:
        raise PlayerArmyListError(
            "Player army-list declared_total_points does not match MFM calculation."
        )


def _validate_units(value: object) -> tuple[PlayerArmyListUnit, ...]:
    if type(value) is not tuple or not value:
        raise PlayerArmyListError("PlayerArmyList units must be a non-empty tuple.")
    units = cast(tuple[object, ...], value)
    if any(type(unit) is not PlayerArmyListUnit for unit in units):
        raise PlayerArmyListError(
            "PlayerArmyList units must contain only PlayerArmyListUnit values."
        )
    validated = cast(tuple[PlayerArmyListUnit, ...], units)
    unit_selection_ids = tuple(unit.selection.unit_selection_id for unit in validated)
    if len(unit_selection_ids) != len(set(unit_selection_ids)):
        raise PlayerArmyListError("PlayerArmyList unit selection IDs must be unique.")
    return validated


def _validate_domain_tuple[DomainT](
    field_name: str,
    value: object,
    expected_type: type[DomainT],
) -> tuple[DomainT, ...]:
    if type(value) is not tuple:
        raise PlayerArmyListError(f"{field_name} must be a tuple.")
    items = cast(tuple[object, ...], value)
    if any(type(item) is not expected_type for item in items):
        raise PlayerArmyListError(f"{field_name} contains an invalid value.")
    return cast(tuple[DomainT, ...], items)


_validate_identifier = IdentifierValidator(PlayerArmyListError)


def _validate_unprefixed_identifier(field_name: str, value: object, prefix: str) -> str:
    token = _validate_identifier(field_name, value)
    if token.startswith(prefix):
        raise PlayerArmyListError(f"{field_name} must not include the '{prefix}' prefix.")
    return token


def _validate_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value.strip() or value != value.strip():
        raise PlayerArmyListError(f"{field_name} must be non-empty stripped text.")
    return value


def _validate_positive_int(field_name: str, value: object) -> int:
    if type(value) is not int or value <= 0:
        raise PlayerArmyListError(f"{field_name} must be a positive integer.")
    return value
