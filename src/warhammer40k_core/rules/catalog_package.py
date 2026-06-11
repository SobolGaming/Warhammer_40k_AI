from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Self, TypedDict

from warhammer40k_core.core.army_catalog import ArmyCatalog, ArmyCatalogPayload
from warhammer40k_core.core.datasheet import DatasheetDefinition
from warhammer40k_core.core.detachment import (
    DetachmentDefinition,
    EnhancementDefinition,
    StratagemDefinition,
)
from warhammer40k_core.core.faction import FactionDefinition
from warhammer40k_core.core.model_geometry_catalog import (
    ModelGeometryCatalogRecord,
    ModelGeometryCatalogRecordPayload,
    ModelGeometryImportDiagnostic,
    ModelGeometryImportDiagnosticPayload,
)
from warhammer40k_core.core.wargear import Wargear
from warhammer40k_core.core.weapon_profiles import WeaponProfile
from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    CatalogVersionPayload,
    DataPackageError,
    DataPackageId,
    DataPackageIdPayload,
)
from warhammer40k_core.rules.source_catalog import SourceArtifactHash, SourceArtifactHashPayload


class CanonicalCatalogPackageError(ValueError):
    """Raised when a canonical catalog package violates Phase 17B invariants."""


type DatasheetCatalogRecord = DatasheetDefinition
type WargearCatalogRecord = Wargear
type WeaponProfileCatalogRecord = WeaponProfile
type FactionCatalogRecord = FactionDefinition
type DetachmentCatalogRecord = DetachmentDefinition
type EnhancementCatalogRecord = EnhancementDefinition
type StratagemCatalogRecord = StratagemDefinition


class CanonicalCatalogPackagePayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    source_edition: str
    source_artifacts: list[SourceArtifactHashPayload]
    army_catalog: ArmyCatalogPayload
    model_geometries: list[ModelGeometryCatalogRecordPayload]
    diagnostics: list[ModelGeometryImportDiagnosticPayload]
    schema_version: str
    package_hash: str


@dataclass(frozen=True, slots=True)
class CanonicalCatalogPackage:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    source_edition: str
    source_artifacts: tuple[SourceArtifactHash, ...]
    army_catalog: ArmyCatalog
    model_geometries: tuple[ModelGeometryCatalogRecord, ...]
    diagnostics: tuple[ModelGeometryImportDiagnostic, ...] = ()
    schema_version: str = "phase17b-canonical-catalog-v1"

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage package_id must be DataPackageId."
            )
        if type(self.catalog_version) is not CatalogVersion:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage catalog_version must be CatalogVersion."
            )
        object.__setattr__(
            self,
            "source_edition",
            _validate_identifier("CanonicalCatalogPackage source_edition", self.source_edition),
        )
        if self.source_edition != "warhammer-40000-11th":
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage source_edition must be warhammer-40000-11th."
            )
        object.__setattr__(
            self,
            "source_artifacts",
            _validate_source_artifact_tuple(self.source_artifacts),
        )
        if type(self.army_catalog) is not ArmyCatalog:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage army_catalog must be ArmyCatalog."
            )
        model_geometries = _validate_model_geometry_tuple(self.model_geometries)
        diagnostics = _validate_diagnostic_tuple(self.diagnostics)
        _validate_every_model_profile_has_geometry(
            catalog=self.army_catalog,
            model_geometries=model_geometries,
        )
        object.__setattr__(self, "model_geometries", model_geometries)
        object.__setattr__(self, "diagnostics", diagnostics)
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("CanonicalCatalogPackage schema_version", self.schema_version),
        )

    def package_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()

    def to_payload(self) -> CanonicalCatalogPackagePayload:
        payload = self._payload_without_hash()
        payload["package_hash"] = self.package_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: CanonicalCatalogPackagePayload) -> Self:
        package = cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            source_edition=payload["source_edition"],
            source_artifacts=tuple(
                SourceArtifactHash.from_payload(artifact)
                for artifact in payload["source_artifacts"]
            ),
            army_catalog=ArmyCatalog.from_payload(payload["army_catalog"]),
            model_geometries=tuple(
                ModelGeometryCatalogRecord.from_payload(record)
                for record in payload["model_geometries"]
            ),
            diagnostics=tuple(
                ModelGeometryImportDiagnostic.from_payload(diagnostic)
                for diagnostic in payload["diagnostics"]
            ),
            schema_version=payload["schema_version"],
        )
        if package.package_hash() != payload["package_hash"]:
            raise CanonicalCatalogPackageError("CanonicalCatalogPackage package_hash is stale.")
        return package

    def _payload_without_hash(self) -> CanonicalCatalogPackagePayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "source_edition": self.source_edition,
            "source_artifacts": [artifact.to_payload() for artifact in self.source_artifacts],
            "army_catalog": self.army_catalog.to_payload(),
            "model_geometries": [record.to_payload() for record in self.model_geometries],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "schema_version": self.schema_version,
            "package_hash": "",
        }


def _validate_every_model_profile_has_geometry(
    *,
    catalog: ArmyCatalog,
    model_geometries: tuple[ModelGeometryCatalogRecord, ...],
) -> None:
    model_profile_ids = {
        model_profile.model_profile_id
        for datasheet in catalog.datasheets
        for model_profile in datasheet.model_profiles
    }
    geometry_profile_ids = {record.model_profile_id for record in model_geometries}
    missing = sorted(model_profile_ids.difference(geometry_profile_ids))
    if missing:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage missing model geometry for: " + ", ".join(missing)
        )
    extra = sorted(geometry_profile_ids.difference(model_profile_ids))
    if extra:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage has model geometry for unknown profiles: " + ", ".join(extra)
        )


def _validate_model_geometry_tuple(
    values: tuple[ModelGeometryCatalogRecord, ...],
) -> tuple[ModelGeometryCatalogRecord, ...]:
    if type(values) is not tuple:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage model_geometries must be a tuple."
        )
    if not values:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage model_geometries must not be empty."
        )
    seen: set[str] = set()
    validated: list[ModelGeometryCatalogRecord] = []
    for value in values:
        if type(value) is not ModelGeometryCatalogRecord:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage model_geometries must contain records."
            )
        if value.model_profile_id in seen:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage model_geometries must not duplicate model profiles."
            )
        seen.add(value.model_profile_id)
        validated.append(value)
    return tuple(sorted(validated, key=lambda record: record.model_profile_id))


def _validate_diagnostic_tuple(
    values: tuple[ModelGeometryImportDiagnostic, ...],
) -> tuple[ModelGeometryImportDiagnostic, ...]:
    if type(values) is not tuple:
        raise CanonicalCatalogPackageError("CanonicalCatalogPackage diagnostics must be a tuple.")
    for value in values:
        if type(value) is not ModelGeometryImportDiagnostic:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage diagnostics must contain geometry diagnostics."
            )
    return tuple(
        sorted(
            values,
            key=lambda diagnostic: (
                diagnostic.model_profile_id,
                diagnostic.source_id,
                diagnostic.reason.value,
            ),
        )
    )


def _validate_source_artifact_tuple(
    values: tuple[SourceArtifactHash, ...],
) -> tuple[SourceArtifactHash, ...]:
    if type(values) is not tuple:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage source_artifacts must be a tuple."
        )
    if not values:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage source_artifacts must not be empty."
        )
    seen: set[str] = set()
    validated: list[SourceArtifactHash] = []
    for value in values:
        if type(value) is not SourceArtifactHash:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage source_artifacts must contain SourceArtifactHash values."
            )
        if value.artifact_name in seen:
            raise CanonicalCatalogPackageError(
                "CanonicalCatalogPackage source_artifacts must be unique."
            )
        seen.add(value.artifact_name)
        validated.append(value)
    return tuple(sorted(validated, key=lambda artifact: artifact.artifact_name))


def _data_package_id_from_payload(payload: DataPackageIdPayload) -> DataPackageId:
    try:
        return DataPackageId.from_payload(payload)
    except DataPackageError as exc:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage package_id is invalid."
        ) from exc


def _catalog_version_from_payload(payload: CatalogVersionPayload) -> CatalogVersion:
    try:
        return CatalogVersion.from_payload(payload)
    except DataPackageError as exc:
        raise CanonicalCatalogPackageError(
            "CanonicalCatalogPackage catalog_version is invalid."
        ) from exc


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise CanonicalCatalogPackageError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise CanonicalCatalogPackageError(f"{field_name} must not be empty.")
    return stripped
