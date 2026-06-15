from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from typing import Self, TypedDict

from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    CatalogVersionPayload,
    DataPackageError,
    DataPackageId,
    DataPackageIdPayload,
)
from warhammer40k_core.rules.source_catalog import SourceArtifactHash
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact, source_row_hash
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    NormalizedSourceRowPayload,
    SourceTextField,
    WahapediaCsvRow,
    WahapediaJsonArtifact,
    schema_for_table,
)


class SourceOverlayError(ValueError):
    """Raised when edition source overlay data violates CORE V2 invariants."""


class SourceOverlayOperationKind(StrEnum):
    ADD_ROW = "add_row"
    UPDATE_ROW = "update_row"
    SUPERSEDE_ROW = "supersede_row"


class SourceOverlayDiagnosticReason(StrEnum):
    DUPLICATE_FIELD_EDIT = "duplicate_field_edit"
    DUPLICATE_ROW = "duplicate_row"
    MISSING_SOURCE_TABLE = "missing_source_table"
    MALFORMED_OPERATION = "malformed_operation"
    ROW_ID_DRIFT = "row_id_drift"
    TARGET_DRIFT = "target_drift"
    UNRESOLVED_ROW = "unresolved_row"


class SourceTextRefPayload(TypedDict):
    source_text_id: str
    source_package_id: DataPackageIdPayload
    source_table: str
    source_row_id: str
    column_name: str


class SourceOverlayOperationPayload(TypedDict):
    op_id: str
    order_index: int
    operation_kind: str
    target_edition: str
    source_table: str
    source_row_id: str
    source_reference: str
    effective_date: str
    reason: str
    expected_preimage_hash: str | None
    fields: dict[str, str]


class SourceOverlayPackPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    base_source_package_id: DataPackageIdPayload
    target_edition: str
    effective_date: str
    operations: list[SourceOverlayOperationPayload]
    schema_version: str
    package_hash: str


class SourceOverlayPackDraftPayload(TypedDict):
    package_id: DataPackageIdPayload
    catalog_version: CatalogVersionPayload
    base_source_package_id: DataPackageIdPayload
    target_edition: str
    effective_date: str
    operations: list[SourceOverlayOperationPayload]
    schema_version: str


class SourceReleaseManifestPayload(TypedDict):
    release_id: str
    catalog_version: CatalogVersionPayload
    base_source_package_id: DataPackageIdPayload
    base_source_edition: str
    target_edition: str
    overlay_package_ids: list[DataPackageIdPayload]
    schema_version: str
    release_hash: str


class OverlaySourceArtifactPayload(TypedDict):
    source_package_id: DataPackageIdPayload
    source_table: str
    source_artifact_hash: str
    overlay_package_hashes: list[str]
    target_edition: str
    rows: list[NormalizedSourceRowPayload]
    diagnostics: list[SourceOverlayDiagnosticPayload]
    artifact_hash: str


class SourceOverlayDiagnosticPayload(TypedDict):
    op_id: str
    source_table: str
    source_row_id: str | None
    reason: str
    message: str
    blocking: bool


@dataclass(frozen=True, slots=True)
class SourceTextRef:
    source_text_id: str
    source_package_id: DataPackageId
    source_table: str
    source_row_id: str
    column_name: str

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "source_text_id",
            _validate_identifier("SourceTextRef source_text_id", self.source_text_id),
        )
        if type(self.source_package_id) is not DataPackageId:
            raise SourceOverlayError("SourceTextRef source_package_id must be DataPackageId.")
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("SourceTextRef source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_row_id",
            _validate_identifier("SourceTextRef source_row_id", self.source_row_id),
        )
        object.__setattr__(
            self,
            "column_name",
            _validate_identifier("SourceTextRef column_name", self.column_name),
        )

    @classmethod
    def from_text_field(cls, *, row: NormalizedSourceRow, text_field: SourceTextField) -> Self:
        return cls(
            source_text_id=text_field.source_text_id,
            source_package_id=row.source_package_id,
            source_table=row.source_table,
            source_row_id=row.source_row_id,
            column_name=text_field.column_name,
        )

    def to_payload(self) -> SourceTextRefPayload:
        return {
            "source_text_id": self.source_text_id,
            "source_package_id": self.source_package_id.to_payload(),
            "source_table": self.source_table,
            "source_row_id": self.source_row_id,
            "column_name": self.column_name,
        }

    @classmethod
    def from_payload(cls, payload: SourceTextRefPayload) -> Self:
        return cls(
            source_text_id=payload["source_text_id"],
            source_package_id=_data_package_id_from_payload(payload["source_package_id"]),
            source_table=payload["source_table"],
            source_row_id=payload["source_row_id"],
            column_name=payload["column_name"],
        )


@dataclass(frozen=True, slots=True)
class SourceOverlayDiagnostic:
    op_id: str
    source_table: str
    source_row_id: str | None
    reason: SourceOverlayDiagnosticReason
    message: str
    blocking: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "op_id",
            _validate_identifier("SourceOverlayDiagnostic op_id", self.op_id),
        )
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("SourceOverlayDiagnostic source_table", self.source_table),
        )
        if self.source_row_id is not None:
            object.__setattr__(
                self,
                "source_row_id",
                _validate_identifier(
                    "SourceOverlayDiagnostic source_row_id",
                    self.source_row_id,
                ),
            )
        if type(self.reason) is not SourceOverlayDiagnosticReason:
            raise SourceOverlayError(
                "SourceOverlayDiagnostic reason must be SourceOverlayDiagnosticReason."
            )
        object.__setattr__(
            self,
            "message",
            _validate_identifier("SourceOverlayDiagnostic message", self.message),
        )
        if type(self.blocking) is not bool:
            raise SourceOverlayError("SourceOverlayDiagnostic blocking must be a boolean.")

    def to_payload(self) -> SourceOverlayDiagnosticPayload:
        return {
            "op_id": self.op_id,
            "source_table": self.source_table,
            "source_row_id": self.source_row_id,
            "reason": self.reason.value,
            "message": self.message,
            "blocking": self.blocking,
        }

    @classmethod
    def from_payload(cls, payload: SourceOverlayDiagnosticPayload) -> Self:
        return cls(
            op_id=payload["op_id"],
            source_table=payload["source_table"],
            source_row_id=payload["source_row_id"],
            reason=_diagnostic_reason_from_token(payload["reason"]),
            message=payload["message"],
            blocking=payload["blocking"],
        )


@dataclass(frozen=True, slots=True)
class SourceOverlayOperation:
    op_id: str
    order_index: int
    operation_kind: SourceOverlayOperationKind
    target_edition: str
    source_table: str
    source_row_id: str
    source_reference: str
    effective_date: str
    reason: str
    expected_preimage_hash: str | None
    fields: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "op_id",
            _validate_identifier("SourceOverlayOperation op_id", self.op_id),
        )
        if type(self.order_index) is not int:
            raise SourceOverlayError("SourceOverlayOperation order_index must be an integer.")
        if self.order_index < 0:
            raise SourceOverlayError("SourceOverlayOperation order_index must not be negative.")
        if type(self.operation_kind) is not SourceOverlayOperationKind:
            raise SourceOverlayError(
                "SourceOverlayOperation operation_kind must be SourceOverlayOperationKind."
            )
        object.__setattr__(
            self,
            "target_edition",
            _validate_identifier("SourceOverlayOperation target_edition", self.target_edition),
        )
        if self.target_edition != "warhammer-40000-11th":
            raise SourceOverlayError("SourceOverlayOperation target_edition must be 11th Edition.")
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("SourceOverlayOperation source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_row_id",
            _validate_identifier("SourceOverlayOperation source_row_id", self.source_row_id),
        )
        object.__setattr__(
            self,
            "source_reference",
            _validate_identifier(
                "SourceOverlayOperation source_reference",
                self.source_reference,
            ),
        )
        object.__setattr__(
            self,
            "effective_date",
            _validate_source_date("SourceOverlayOperation effective_date", self.effective_date),
        )
        object.__setattr__(
            self,
            "reason",
            _validate_identifier("SourceOverlayOperation reason", self.reason),
        )
        if self.expected_preimage_hash is not None:
            object.__setattr__(
                self,
                "expected_preimage_hash",
                _validate_sha256(
                    "SourceOverlayOperation expected_preimage_hash",
                    self.expected_preimage_hash,
                ),
            )
        if (
            self.operation_kind
            in {
                SourceOverlayOperationKind.UPDATE_ROW,
                SourceOverlayOperationKind.SUPERSEDE_ROW,
            }
            and self.expected_preimage_hash is None
        ):
            raise SourceOverlayError(
                "SourceOverlayOperation expected_preimage_hash is required for mutations."
            )
        if (
            self.operation_kind
            in {
                SourceOverlayOperationKind.ADD_ROW,
                SourceOverlayOperationKind.UPDATE_ROW,
            }
            and not self.fields
        ):
            raise SourceOverlayError("SourceOverlayOperation fields must not be empty.")
        object.__setattr__(
            self,
            "fields",
            _validate_string_pair_tuple("SourceOverlayOperation fields", self.fields),
        )

    def to_payload(self) -> SourceOverlayOperationPayload:
        return {
            "op_id": self.op_id,
            "order_index": self.order_index,
            "operation_kind": self.operation_kind.value,
            "target_edition": self.target_edition,
            "source_table": self.source_table,
            "source_row_id": self.source_row_id,
            "source_reference": self.source_reference,
            "effective_date": self.effective_date,
            "reason": self.reason,
            "expected_preimage_hash": self.expected_preimage_hash,
            "fields": dict(self.fields),
        }

    @classmethod
    def from_payload(cls, payload: SourceOverlayOperationPayload) -> Self:
        return cls(
            op_id=payload["op_id"],
            order_index=payload["order_index"],
            operation_kind=_operation_kind_from_token(payload["operation_kind"]),
            target_edition=payload["target_edition"],
            source_table=payload["source_table"],
            source_row_id=payload["source_row_id"],
            source_reference=payload["source_reference"],
            effective_date=payload["effective_date"],
            reason=payload["reason"],
            expected_preimage_hash=payload["expected_preimage_hash"],
            fields=tuple(payload["fields"].items()),
        )


@dataclass(frozen=True, slots=True)
class SourceOverlayPack:
    package_id: DataPackageId
    catalog_version: CatalogVersion
    base_source_package_id: DataPackageId
    target_edition: str
    effective_date: str
    operations: tuple[SourceOverlayOperation, ...]
    schema_version: str = "phase17-source-overlay-v1"

    def __post_init__(self) -> None:
        if type(self.package_id) is not DataPackageId:
            raise SourceOverlayError("SourceOverlayPack package_id must be DataPackageId.")
        if type(self.catalog_version) is not CatalogVersion:
            raise SourceOverlayError("SourceOverlayPack catalog_version must be CatalogVersion.")
        if type(self.base_source_package_id) is not DataPackageId:
            raise SourceOverlayError(
                "SourceOverlayPack base_source_package_id must be DataPackageId."
            )
        object.__setattr__(
            self,
            "target_edition",
            _validate_identifier("SourceOverlayPack target_edition", self.target_edition),
        )
        if self.target_edition != "warhammer-40000-11th":
            raise SourceOverlayError("SourceOverlayPack target_edition must be 11th Edition.")
        object.__setattr__(
            self,
            "effective_date",
            _validate_source_date("SourceOverlayPack effective_date", self.effective_date),
        )
        object.__setattr__(
            self,
            "operations",
            _validate_operation_tuple(self.operations),
        )
        for operation in self.operations:
            if operation.target_edition != self.target_edition:
                raise SourceOverlayError("SourceOverlayPack operation edition mismatch.")
            if operation.effective_date != self.effective_date:
                raise SourceOverlayError("SourceOverlayPack operation effective date mismatch.")
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("SourceOverlayPack schema_version", self.schema_version),
        )

    def package_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_payload(self) -> SourceOverlayPackPayload:
        payload = self._payload_without_hash()
        payload["package_hash"] = self.package_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: SourceOverlayPackPayload) -> Self:
        package = cls.from_unhashed_payload(payload)
        if payload["package_hash"] != package.package_hash():
            raise SourceOverlayError("SourceOverlayPack package_hash is stale.")
        return package

    @classmethod
    def from_unhashed_payload(cls, payload: SourceOverlayPackDraftPayload) -> Self:
        return cls(
            package_id=_data_package_id_from_payload(payload["package_id"]),
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            base_source_package_id=_data_package_id_from_payload(payload["base_source_package_id"]),
            target_edition=payload["target_edition"],
            effective_date=payload["effective_date"],
            operations=tuple(
                SourceOverlayOperation.from_payload(operation)
                for operation in payload["operations"]
            ),
            schema_version=payload["schema_version"],
        )

    def _payload_without_hash(self) -> SourceOverlayPackPayload:
        return {
            "package_id": self.package_id.to_payload(),
            "catalog_version": self.catalog_version.to_payload(),
            "base_source_package_id": self.base_source_package_id.to_payload(),
            "target_edition": self.target_edition,
            "effective_date": self.effective_date,
            "operations": [operation.to_payload() for operation in self.operations],
            "schema_version": self.schema_version,
            "package_hash": "",
        }


@dataclass(frozen=True, slots=True)
class SourceReleaseManifest:
    release_id: str
    catalog_version: CatalogVersion
    base_source_package_id: DataPackageId
    base_source_edition: str
    target_edition: str
    overlay_package_ids: tuple[DataPackageId, ...]
    schema_version: str = "phase17-source-release-v1"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "release_id",
            _validate_identifier("SourceReleaseManifest release_id", self.release_id),
        )
        if type(self.catalog_version) is not CatalogVersion:
            raise SourceOverlayError(
                "SourceReleaseManifest catalog_version must be CatalogVersion."
            )
        if type(self.base_source_package_id) is not DataPackageId:
            raise SourceOverlayError(
                "SourceReleaseManifest base_source_package_id must be DataPackageId."
            )
        object.__setattr__(
            self,
            "base_source_edition",
            _validate_identifier(
                "SourceReleaseManifest base_source_edition",
                self.base_source_edition,
            ),
        )
        object.__setattr__(
            self,
            "target_edition",
            _validate_identifier("SourceReleaseManifest target_edition", self.target_edition),
        )
        if self.target_edition != "warhammer-40000-11th":
            raise SourceOverlayError("SourceReleaseManifest target_edition must be 11th Edition.")
        object.__setattr__(
            self,
            "overlay_package_ids",
            _validate_data_package_id_tuple(self.overlay_package_ids),
        )
        if self.base_source_edition != self.target_edition and not self.overlay_package_ids:
            raise SourceOverlayError(
                "1" + "0" + "th-edition bridge releases require at least one overlay package."
            )
        object.__setattr__(
            self,
            "schema_version",
            _validate_identifier("SourceReleaseManifest schema_version", self.schema_version),
        )

    def release_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def to_payload(self) -> SourceReleaseManifestPayload:
        payload = self._payload_without_hash()
        payload["release_hash"] = self.release_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: SourceReleaseManifestPayload) -> Self:
        manifest = cls(
            release_id=payload["release_id"],
            catalog_version=_catalog_version_from_payload(payload["catalog_version"]),
            base_source_package_id=_data_package_id_from_payload(payload["base_source_package_id"]),
            base_source_edition=payload["base_source_edition"],
            target_edition=payload["target_edition"],
            overlay_package_ids=tuple(
                _data_package_id_from_payload(package_id)
                for package_id in payload["overlay_package_ids"]
            ),
            schema_version=payload["schema_version"],
        )
        if payload["release_hash"] != manifest.release_hash():
            raise SourceOverlayError("SourceReleaseManifest release_hash is stale.")
        return manifest

    def _payload_without_hash(self) -> SourceReleaseManifestPayload:
        return {
            "release_id": self.release_id,
            "catalog_version": self.catalog_version.to_payload(),
            "base_source_package_id": self.base_source_package_id.to_payload(),
            "base_source_edition": self.base_source_edition,
            "target_edition": self.target_edition,
            "overlay_package_ids": [
                package_id.to_payload() for package_id in self.overlay_package_ids
            ],
            "schema_version": self.schema_version,
            "release_hash": "",
        }


@dataclass(frozen=True, slots=True)
class OverlaySourceArtifact:
    source_package_id: DataPackageId
    source_table: str
    source_artifact_hash: str
    overlay_package_hashes: tuple[str, ...]
    target_edition: str
    rows: tuple[NormalizedSourceRow, ...]
    diagnostics: tuple[SourceOverlayDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.source_package_id) is not DataPackageId:
            raise SourceOverlayError(
                "OverlaySourceArtifact source_package_id must be DataPackageId."
            )
        object.__setattr__(
            self,
            "source_table",
            _validate_identifier("OverlaySourceArtifact source_table", self.source_table),
        )
        object.__setattr__(
            self,
            "source_artifact_hash",
            _validate_sha256(
                "OverlaySourceArtifact source_artifact_hash",
                self.source_artifact_hash,
            ),
        )
        object.__setattr__(
            self,
            "overlay_package_hashes",
            _validate_sha_tuple(
                "OverlaySourceArtifact overlay_package_hashes",
                self.overlay_package_hashes,
            ),
        )
        object.__setattr__(
            self,
            "target_edition",
            _validate_identifier("OverlaySourceArtifact target_edition", self.target_edition),
        )
        object.__setattr__(self, "rows", _validate_rows(self))
        object.__setattr__(
            self,
            "diagnostics",
            _validate_diagnostic_tuple(self.diagnostics),
        )

    def blocking_diagnostics(self) -> tuple[SourceOverlayDiagnostic, ...]:
        return tuple(diagnostic for diagnostic in self.diagnostics if diagnostic.blocking)

    def require_success(self) -> Self:
        blocking = self.blocking_diagnostics()
        if blocking:
            reasons = ", ".join(sorted({diagnostic.reason.value for diagnostic in blocking}))
            raise SourceOverlayError(
                f"Source overlay application failed with diagnostics: {reasons}."
            )
        return self

    def artifact_hash(self) -> str:
        return _sha256_payload(self._payload_without_hash())

    def source_artifact_hash_record(self) -> SourceArtifactHash:
        return SourceArtifactHash(
            artifact_name=f"{self.source_table}.overlay.json",
            artifact_hash=self.artifact_hash(),
        )

    def to_json_bytes(self) -> bytes:
        return json.dumps(self.to_payload(), sort_keys=True, separators=(",", ":")).encode()

    def to_payload(self) -> OverlaySourceArtifactPayload:
        payload = self._payload_without_hash()
        payload["artifact_hash"] = self.artifact_hash()
        return payload

    @classmethod
    def from_payload(cls, payload: OverlaySourceArtifactPayload) -> Self:
        artifact = cls(
            source_package_id=_data_package_id_from_payload(payload["source_package_id"]),
            source_table=payload["source_table"],
            source_artifact_hash=payload["source_artifact_hash"],
            overlay_package_hashes=tuple(payload["overlay_package_hashes"]),
            target_edition=payload["target_edition"],
            rows=tuple(NormalizedSourceRow.from_payload(row) for row in payload["rows"]),
            diagnostics=tuple(
                SourceOverlayDiagnostic.from_payload(diagnostic)
                for diagnostic in payload["diagnostics"]
            ),
        )
        if payload["artifact_hash"] != artifact.artifact_hash():
            raise SourceOverlayError("OverlaySourceArtifact artifact_hash is stale.")
        return artifact

    def _payload_without_hash(self) -> OverlaySourceArtifactPayload:
        return {
            "source_package_id": self.source_package_id.to_payload(),
            "source_table": self.source_table,
            "source_artifact_hash": self.source_artifact_hash,
            "overlay_package_hashes": list(self.overlay_package_hashes),
            "target_edition": self.target_edition,
            "rows": [row.to_payload() for row in self.rows],
            "diagnostics": [diagnostic.to_payload() for diagnostic in self.diagnostics],
            "artifact_hash": "",
        }


SourceArtifact = WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact


@dataclass(frozen=True, slots=True)
class SourceOverlayApplicationReport:
    artifacts: tuple[OverlaySourceArtifact, ...]
    release_diagnostics: tuple[SourceOverlayDiagnostic, ...] = ()

    def __post_init__(self) -> None:
        if type(self.artifacts) is not tuple:
            raise SourceOverlayError("SourceOverlayApplicationReport artifacts must be a tuple.")
        for artifact in self.artifacts:
            if type(artifact) is not OverlaySourceArtifact:
                raise SourceOverlayError(
                    "SourceOverlayApplicationReport artifacts must contain overlay artifacts."
                )
        object.__setattr__(
            self,
            "release_diagnostics",
            _validate_diagnostic_tuple(self.release_diagnostics),
        )

    def blocking_diagnostics(self) -> tuple[SourceOverlayDiagnostic, ...]:
        return tuple(
            diagnostic
            for diagnostic in (
                *self.release_diagnostics,
                *(diagnostic for artifact in self.artifacts for diagnostic in artifact.diagnostics),
            )
            if diagnostic.blocking
        )

    def require_success(self) -> Self:
        blocking = self.blocking_diagnostics()
        if blocking:
            reasons = ", ".join(sorted({diagnostic.reason.value for diagnostic in blocking}))
            raise SourceOverlayError(
                f"Source overlay application failed with diagnostics: {reasons}."
            )
        return self

    def all_diagnostics(self) -> tuple[SourceOverlayDiagnostic, ...]:
        return (
            *self.release_diagnostics,
            *(diagnostic for artifact in self.artifacts for diagnostic in artifact.diagnostics),
        )


def apply_source_release_overlays(
    *,
    source_artifacts: tuple[SourceArtifact, ...],
    release_manifest: SourceReleaseManifest,
    overlay_packs: tuple[SourceOverlayPack, ...],
    raise_on_blocking: bool = True,
) -> tuple[OverlaySourceArtifact, ...]:
    if type(raise_on_blocking) is not bool:
        raise SourceOverlayError("raise_on_blocking must be a boolean.")
    report = build_source_release_overlay_report(
        source_artifacts=source_artifacts,
        release_manifest=release_manifest,
        overlay_packs=overlay_packs,
    )
    if raise_on_blocking:
        report.require_success()
    return report.artifacts


def build_source_release_overlay_report(
    *,
    source_artifacts: tuple[SourceArtifact, ...],
    release_manifest: SourceReleaseManifest,
    overlay_packs: tuple[SourceOverlayPack, ...],
) -> SourceOverlayApplicationReport:
    if type(source_artifacts) is not tuple:
        raise SourceOverlayError("source_artifacts must be a tuple.")
    if not source_artifacts:
        raise SourceOverlayError("source_artifacts must not be empty.")
    if type(release_manifest) is not SourceReleaseManifest:
        raise SourceOverlayError("release_manifest must be SourceReleaseManifest.")
    if type(overlay_packs) is not tuple:
        raise SourceOverlayError("overlay_packs must be a tuple.")

    _validate_supplied_overlay_packs(
        overlay_packs=overlay_packs,
        release_manifest=release_manifest,
    )
    packs_by_id = {pack.package_id.stable_identity(): pack for pack in overlay_packs}
    ordered_packs: list[SourceOverlayPack] = []
    for package_id in release_manifest.overlay_package_ids:
        pack = packs_by_id.get(package_id.stable_identity())
        if pack is None:
            raise SourceOverlayError("SourceReleaseManifest references a missing overlay pack.")
        _validate_pack_against_manifest(pack=pack, manifest=release_manifest)
        ordered_packs.append(pack)

    rows_by_table: dict[str, list[NormalizedSourceRow]] = {}
    source_hash_by_table: dict[str, str] = {}
    base_package = release_manifest.base_source_package_id
    for artifact in source_artifacts:
        if type(artifact) not in {
            WahapediaJsonArtifact,
            PatchedSourceArtifact,
            OverlaySourceArtifact,
        }:
            raise SourceOverlayError("source_artifacts must contain source artifacts.")
        if artifact.source_package_id != base_package:
            raise SourceOverlayError("Source artifact package does not match release manifest.")
        rows_by_table.setdefault(artifact.source_table, []).extend(artifact.rows)
        source_hash_by_table[artifact.source_table] = _artifact_hash(artifact)

    release_diagnostics: list[SourceOverlayDiagnostic] = []
    diagnostics: list[SourceOverlayDiagnostic] = []
    for pack in ordered_packs:
        for operation in pack.operations:
            table_rows = rows_by_table.get(operation.source_table)
            if table_rows is None:
                release_diagnostics.append(
                    _diagnostic(
                        operation=operation,
                        reason=SourceOverlayDiagnosticReason.MISSING_SOURCE_TABLE,
                        message="Overlay operation references a missing source table.",
                    )
                )
                continue
            _apply_overlay_operation(
                rows=table_rows,
                operation=operation,
                package_id=release_manifest.base_source_package_id,
                diagnostics=diagnostics,
            )

    overlay_hashes = tuple(pack.package_hash() for pack in ordered_packs)
    artifacts = tuple(
        OverlaySourceArtifact(
            source_package_id=release_manifest.base_source_package_id,
            source_table=source_table,
            source_artifact_hash=source_hash_by_table[source_table],
            overlay_package_hashes=overlay_hashes,
            target_edition=release_manifest.target_edition,
            rows=tuple(rows),
            diagnostics=tuple(
                diagnostic for diagnostic in diagnostics if diagnostic.source_table == source_table
            ),
        )
        for source_table, rows in sorted(rows_by_table.items())
    )
    return SourceOverlayApplicationReport(
        artifacts=artifacts,
        release_diagnostics=tuple(release_diagnostics),
    )


def _apply_overlay_operation(
    *,
    rows: list[NormalizedSourceRow],
    operation: SourceOverlayOperation,
    package_id: DataPackageId,
    diagnostics: list[SourceOverlayDiagnostic],
) -> None:
    if operation.operation_kind is SourceOverlayOperationKind.ADD_ROW:
        if any(row.source_row_id == operation.source_row_id for row in rows):
            diagnostics.append(
                _diagnostic(
                    operation=operation,
                    reason=SourceOverlayDiagnosticReason.DUPLICATE_ROW,
                    message="Overlay add_row target already exists.",
                )
            )
            return
        rows.append(_added_row(operation=operation, package_id=package_id))
        return

    index = _row_index_by_id(rows=rows, source_row_id=operation.source_row_id)
    if index is None:
        diagnostics.append(
            _diagnostic(
                operation=operation,
                reason=SourceOverlayDiagnosticReason.UNRESOLVED_ROW,
                message="Overlay operation target row was not found.",
            )
        )
        return
    row = rows[index]
    if source_row_hash(row) != operation.expected_preimage_hash:
        diagnostics.append(
            _diagnostic(
                operation=operation,
                reason=SourceOverlayDiagnosticReason.TARGET_DRIFT,
                message="Overlay target preimage hash is stale.",
            )
        )
        return
    if operation.operation_kind is SourceOverlayOperationKind.UPDATE_ROW:
        rows[index] = _updated_row(row=row, operation=operation)
        return
    if operation.operation_kind is SourceOverlayOperationKind.SUPERSEDE_ROW:
        rows[index] = _superseded_row(row=row, operation=operation)
        return


def _added_row(
    *,
    operation: SourceOverlayOperation,
    package_id: DataPackageId,
) -> NormalizedSourceRow:
    schema = schema_for_table(operation.source_table)
    fields = tuple((key, value) for key, value in operation.fields)
    csv_row = WahapediaCsvRow(row_number=operation.order_index + 2, values=fields)
    row = NormalizedSourceRow.from_csv_row(
        source_package_id=package_id,
        schema=schema,
        row=csv_row,
    )
    if row.source_row_id != operation.source_row_id:
        raise SourceOverlayError("Overlay add_row source_row_id does not match row identity.")
    return row


def _updated_row(
    *,
    row: NormalizedSourceRow,
    operation: SourceOverlayOperation,
) -> NormalizedSourceRow:
    field_map = dict(row.fields)
    for column_name, raw_value in operation.fields:
        field_map[column_name] = raw_value
    return _row_from_field_map(row=row, field_map=field_map, operation=operation)


def _superseded_row(
    *,
    row: NormalizedSourceRow,
    operation: SourceOverlayOperation,
) -> NormalizedSourceRow:
    field_map = dict(row.fields)
    field_map["core_v2_superseded_by"] = operation.op_id
    field_map["core_v2_superseded_reason"] = operation.reason
    field_map["core_v2_superseded_source_reference"] = operation.source_reference
    return _row_from_field_map(row=row, field_map=field_map, operation=operation)


def _row_from_field_map(
    *,
    row: NormalizedSourceRow,
    field_map: dict[str, str],
    operation: SourceOverlayOperation,
) -> NormalizedSourceRow:
    schema = schema_for_table(row.source_table)
    fields = tuple((key, field_map[key]) for key in field_map)
    csv_row = WahapediaCsvRow(row_number=row.source_row_number, values=fields)
    updated = NormalizedSourceRow.from_csv_row(
        source_package_id=row.source_package_id,
        schema=schema,
        row=csv_row,
    )
    if updated.source_row_id != row.source_row_id:
        raise SourceOverlayError("Overlay update changed source row identity.")
    if updated.source_row_id != operation.source_row_id:
        raise SourceOverlayError("Overlay update source_row_id drift.")
    return updated


def _artifact_hash(artifact: SourceArtifact) -> str:
    if type(artifact) is WahapediaJsonArtifact:
        return artifact.artifact_hash()
    if type(artifact) is PatchedSourceArtifact:
        return artifact.artifact_hash()
    if type(artifact) is OverlaySourceArtifact:
        return artifact.artifact_hash()
    raise SourceOverlayError("Unsupported source artifact type.")


def _row_index_by_id(*, rows: list[NormalizedSourceRow], source_row_id: str) -> int | None:
    matches = [index for index, row in enumerate(rows) if row.source_row_id == source_row_id]
    if not matches:
        return None
    if len(matches) > 1:
        raise SourceOverlayError("Source artifact rows must not duplicate source row IDs.")
    return matches[0]


def _diagnostic(
    *,
    operation: SourceOverlayOperation,
    reason: SourceOverlayDiagnosticReason,
    message: str,
) -> SourceOverlayDiagnostic:
    return SourceOverlayDiagnostic(
        op_id=operation.op_id,
        source_table=operation.source_table,
        source_row_id=operation.source_row_id,
        reason=reason,
        message=message,
        blocking=True,
    )


def _validate_pack_against_manifest(
    *,
    pack: SourceOverlayPack,
    manifest: SourceReleaseManifest,
) -> None:
    if pack.base_source_package_id != manifest.base_source_package_id:
        raise SourceOverlayError("SourceOverlayPack base package does not match manifest.")
    if pack.target_edition != manifest.target_edition:
        raise SourceOverlayError("SourceOverlayPack target edition does not match manifest.")
    if pack.catalog_version != manifest.catalog_version:
        raise SourceOverlayError("SourceOverlayPack catalog version does not match manifest.")


def _validate_supplied_overlay_packs(
    *,
    overlay_packs: tuple[SourceOverlayPack, ...],
    release_manifest: SourceReleaseManifest,
) -> None:
    manifest_ids = {
        package_id.stable_identity() for package_id in release_manifest.overlay_package_ids
    }
    supplied_ids: list[str] = []
    for pack in overlay_packs:
        if type(pack) is not SourceOverlayPack:
            raise SourceOverlayError("overlay_packs must contain SourceOverlayPack values.")
        supplied_ids.append(pack.package_id.stable_identity())
    if len(supplied_ids) != len(set(supplied_ids)):
        raise SourceOverlayError("overlay_packs must not duplicate package IDs.")
    if set(supplied_ids) != manifest_ids:
        raise SourceOverlayError("overlay_packs must exactly match the release manifest.")


def _validate_operation_tuple(
    values: tuple[SourceOverlayOperation, ...],
) -> tuple[SourceOverlayOperation, ...]:
    if type(values) is not tuple:
        raise SourceOverlayError("SourceOverlayPack operations must be a tuple.")
    if not values:
        raise SourceOverlayError("SourceOverlayPack operations must not be empty.")
    seen_ops: set[str] = set()
    seen_field_edits: set[tuple[str, str, str]] = set()
    operations: list[SourceOverlayOperation] = []
    for operation in values:
        if type(operation) is not SourceOverlayOperation:
            raise SourceOverlayError(
                "SourceOverlayPack operations must contain overlay operations."
            )
        if operation.op_id in seen_ops:
            raise SourceOverlayError("SourceOverlayPack operations must not duplicate op_id.")
        seen_ops.add(operation.op_id)
        if operation.operation_kind is SourceOverlayOperationKind.SUPERSEDE_ROW:
            edit_key = (operation.source_table, operation.source_row_id, "__supersede__")
            if edit_key in seen_field_edits:
                raise SourceOverlayError("SourceOverlayPack duplicate field edit.")
            seen_field_edits.add(edit_key)
        for column_name, _value in operation.fields:
            edit_key = (operation.source_table, operation.source_row_id, column_name)
            if edit_key in seen_field_edits:
                raise SourceOverlayError("SourceOverlayPack duplicate field edit.")
            seen_field_edits.add(edit_key)
        operations.append(operation)
    return tuple(sorted(operations, key=lambda operation: (operation.order_index, operation.op_id)))


def _validate_rows(artifact: OverlaySourceArtifact) -> tuple[NormalizedSourceRow, ...]:
    if type(artifact.rows) is not tuple:
        raise SourceOverlayError("OverlaySourceArtifact rows must be a tuple.")
    if not artifact.rows:
        raise SourceOverlayError("OverlaySourceArtifact rows must not be empty.")
    seen: set[str] = set()
    rows: list[NormalizedSourceRow] = []
    for row in artifact.rows:
        if type(row) is not NormalizedSourceRow:
            raise SourceOverlayError("OverlaySourceArtifact rows must contain source rows.")
        if row.source_package_id != artifact.source_package_id:
            raise SourceOverlayError("OverlaySourceArtifact row package IDs must match.")
        if row.source_table != artifact.source_table:
            raise SourceOverlayError("OverlaySourceArtifact row tables must match.")
        if row.source_row_id in seen:
            raise SourceOverlayError("OverlaySourceArtifact rows must not duplicate IDs.")
        seen.add(row.source_row_id)
        rows.append(row)
    return tuple(sorted(rows, key=lambda item: item.source_row_id))


def _validate_diagnostic_tuple(
    values: tuple[SourceOverlayDiagnostic, ...],
) -> tuple[SourceOverlayDiagnostic, ...]:
    if type(values) is not tuple:
        raise SourceOverlayError("OverlaySourceArtifact diagnostics must be a tuple.")
    diagnostics: list[SourceOverlayDiagnostic] = []
    for value in values:
        if type(value) is not SourceOverlayDiagnostic:
            raise SourceOverlayError(
                "OverlaySourceArtifact diagnostics must contain overlay diagnostics."
            )
        diagnostics.append(value)
    return tuple(
        sorted(
            diagnostics,
            key=lambda diagnostic: (
                diagnostic.op_id,
                diagnostic.source_table,
                diagnostic.source_row_id or "",
                diagnostic.reason.value,
            ),
        )
    )


def _validate_data_package_id_tuple(values: tuple[DataPackageId, ...]) -> tuple[DataPackageId, ...]:
    if type(values) is not tuple:
        raise SourceOverlayError("SourceReleaseManifest overlay_package_ids must be a tuple.")
    seen: set[str] = set()
    validated: list[DataPackageId] = []
    for value in values:
        if type(value) is not DataPackageId:
            raise SourceOverlayError(
                "SourceReleaseManifest overlay_package_ids must contain DataPackageId values."
            )
        stable_identity = value.stable_identity()
        if stable_identity in seen:
            raise SourceOverlayError(
                "SourceReleaseManifest overlay_package_ids must not duplicate packages."
            )
        seen.add(stable_identity)
        validated.append(value)
    return tuple(validated)


def _validate_string_pair_tuple(
    field_name: str,
    values: tuple[tuple[str, str], ...],
) -> tuple[tuple[str, str], ...]:
    if type(values) is not tuple:
        raise SourceOverlayError(f"{field_name} must be a tuple.")
    seen: set[str] = set()
    pairs: list[tuple[str, str]] = []
    for key, value in values:
        identifier = _validate_identifier(f"{field_name} key", key)
        if identifier in seen:
            raise SourceOverlayError(f"{field_name} must not contain duplicate keys.")
        if type(value) is not str:
            raise SourceOverlayError(f"{field_name} values must be strings.")
        seen.add(identifier)
        pairs.append((identifier, value))
    return tuple(pairs)


def _validate_sha_tuple(field_name: str, values: tuple[str, ...]) -> tuple[str, ...]:
    if type(values) is not tuple:
        raise SourceOverlayError(f"{field_name} must be a tuple.")
    return tuple(_validate_sha256(f"{field_name} value", value) for value in values)


def _validate_identifier(field_name: str, value: object) -> str:
    if type(value) is not str:
        raise SourceOverlayError(f"{field_name} must be a string.")
    stripped = value.strip()
    if not stripped:
        raise SourceOverlayError(f"{field_name} must not be empty.")
    return stripped


def _validate_sha256(field_name: str, value: object) -> str:
    digest = _validate_identifier(field_name, value)
    if len(digest) != 64:
        raise SourceOverlayError(f"{field_name} must be a SHA-256 hex digest.")
    if any(character not in "0123456789abcdef" for character in digest):
        raise SourceOverlayError(f"{field_name} must be a lowercase SHA-256 hex digest.")
    return digest


def _validate_source_date(field_name: str, value: object) -> str:
    source_date = _validate_identifier(field_name, value)
    try:
        date.fromisoformat(source_date)
    except ValueError as exc:
        raise SourceOverlayError(f"{field_name} must be an ISO date.") from exc
    return source_date


def _operation_kind_from_token(token: object) -> SourceOverlayOperationKind:
    if type(token) is SourceOverlayOperationKind:
        return token
    if type(token) is not str:
        raise SourceOverlayError("operation_kind token must be a string.")
    try:
        return SourceOverlayOperationKind(token)
    except ValueError as exc:
        raise SourceOverlayError(f"Unsupported source overlay operation kind: {token}.") from exc


def _diagnostic_reason_from_token(token: object) -> SourceOverlayDiagnosticReason:
    if type(token) is SourceOverlayDiagnosticReason:
        return token
    if type(token) is not str:
        raise SourceOverlayError("diagnostic reason token must be a string.")
    try:
        return SourceOverlayDiagnosticReason(token)
    except ValueError as exc:
        raise SourceOverlayError(f"Unsupported source overlay diagnostic reason: {token}.") from exc


def _data_package_id_from_payload(payload: DataPackageIdPayload) -> DataPackageId:
    try:
        return DataPackageId.from_payload(payload)
    except DataPackageError as exc:
        raise SourceOverlayError("DataPackageId payload is invalid.") from exc


def _catalog_version_from_payload(payload: CatalogVersionPayload) -> CatalogVersion:
    try:
        return CatalogVersion.from_payload(payload)
    except DataPackageError as exc:
        raise SourceOverlayError("CatalogVersion payload is invalid.") from exc


def _sha256_payload(payload: object) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(canonical).hexdigest()
