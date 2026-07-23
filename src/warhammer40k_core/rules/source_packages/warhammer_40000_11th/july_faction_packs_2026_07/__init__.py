from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    JULY_FACTION_PACK_SOURCE_PACKAGE_ID,
    JulyDatasheetArtifact,
    JulyDatasheetPreviewArtifact,
    JulyDeltaLedgerArtifact,
    JulyDetachmentArtifact,
    JulyFactionPackStagingError,
    JulyPhase17ECoverageArtifact,
    JulyPhase17FExecutionArtifact,
    JulyRuntimeScaffoldArtifact,
    JulyStagingPackageArtifact,
    JulySubruleArtifact,
    audit_datasheet_preview_links,
    audit_load_only_artifact_links,
    audit_manifest_links,
    audit_runtime_predecessor_references,
    canonical_json_sha256_from_bytes,
    july_datasheet_preview_from_json_bytes,
    july_datasheets_from_json_bytes,
    july_delta_ledger_from_json_bytes,
    july_detachments_from_json_bytes,
    july_phase17e_from_json_bytes,
    july_phase17f_from_json_bytes,
    july_runtime_scaffolds_from_json_bytes,
    july_staging_package_from_json_bytes,
    july_subrules_from_json_bytes,
)
from ._runtime_artifacts import (
    JulyDaemonicManifestationArtifact,
    july_daemonic_manifestation_from_json_bytes,
)

_PACKAGE_ARTIFACT_PATH: Final = "artifacts/package.json"


def _artifact_bytes(relative_path: str) -> bytes:
    try:
        return package_artifact_bytes(__name__, relative_path)
    except SourcePackageArtifactError as exc:
        raise JulyFactionPackStagingError(
            "July faction-pack staged data artifact could not be loaded."
        ) from exc


def _load_package() -> JulyStagingPackageArtifact:
    return july_staging_package_from_json_bytes(_artifact_bytes(_PACKAGE_ARTIFACT_PATH))


_PACKAGE: Final = _load_package()

SOURCE_PACKAGE_ID: Final = _PACKAGE.source_package_id
SOURCE_TITLE: Final = _PACKAGE.source_title
SOURCE_VERSION: Final = _PACKAGE.source_version
SOURCE_DATE: Final = _PACKAGE.source_date
ACTIVATION_STATUS: Final = _PACKAGE.activation_status
SOURCE_PAYLOAD_CHECKSUM_SHA256: Final = _PACKAGE.source_payload_checksum_sha256()


def staging_package() -> JulyStagingPackageArtifact:
    return _PACKAGE


def delta_ledger() -> JulyDeltaLedgerArtifact:
    raw = _artifact_bytes(_PACKAGE.delta_ledger_artifact)
    if canonical_json_sha256_from_bytes(raw) != _PACKAGE.delta_ledger_sha256:
        raise JulyFactionPackStagingError("July faction-pack delta ledger artifact hash is stale.")
    ledger = july_delta_ledger_from_json_bytes(raw)
    if ledger.source_package_id != SOURCE_PACKAGE_ID:
        raise JulyFactionPackStagingError(
            "July faction-pack delta ledger does not belong to the staged package."
        )
    return ledger


def _staged_artifact_bytes(artifact_id: str) -> bytes:
    references = {artifact.artifact_id: artifact for artifact in _PACKAGE.staged_data_artifacts}
    try:
        reference = references[artifact_id]
    except KeyError as exc:
        raise JulyFactionPackStagingError(
            "July staged data artifact is not declared by the package."
        ) from exc
    raw = _artifact_bytes(reference.artifact_path)
    if canonical_json_sha256_from_bytes(raw) != reference.artifact_sha256:
        raise JulyFactionPackStagingError("July staged data artifact hash is stale.")
    return raw


def detachments() -> JulyDetachmentArtifact:
    return july_detachments_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-detachments-2026-07")
    )


def datasheets() -> JulyDatasheetArtifact:
    return july_datasheets_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-datasheets-2026-07")
    )


def datasheet_support_preview() -> JulyDatasheetPreviewArtifact:
    return july_datasheet_preview_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-datasheet-preview-2026-07")
    )


def daemonic_manifestation() -> JulyDaemonicManifestationArtifact:
    return july_daemonic_manifestation_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-chaos-daemons-daemonic-manifestation-2026-07")
    )


def subrules() -> JulySubruleArtifact:
    return july_subrules_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-subrules-2026-07")
    )


def phase17e_coverage() -> JulyPhase17ECoverageArtifact:
    return july_phase17e_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-phase17e-coverage-2026-07")
    )


def phase17f_execution() -> JulyPhase17FExecutionArtifact:
    return july_phase17f_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-phase17f-execution-2026-07")
    )


def runtime_scaffolds() -> JulyRuntimeScaffoldArtifact:
    return july_runtime_scaffolds_from_json_bytes(
        _staged_artifact_bytes("gw-11e-july-faction-pack-runtime-scaffolds-2026-07")
    )


def source_package_identity_payload() -> dict[str, str]:
    return {
        "source_package_id": SOURCE_PACKAGE_ID,
        "source_title": SOURCE_TITLE,
        "source_version": SOURCE_VERSION,
        "source_date": SOURCE_DATE,
        "activation_status": ACTIVATION_STATUS,
        "source_payload_checksum_sha256": SOURCE_PAYLOAD_CHECKSUM_SHA256,
    }


def staged_identity_tokens() -> frozenset[str]:
    ledger = delta_ledger()
    staged_source_row_ids = {
        *(row.source_row_id for row in datasheets().rows),
        *(row.source_row_id for row in detachments().rows),
        *(row.source_row_id for row in subrules().rows),
    }
    return frozenset(
        {
            JULY_FACTION_PACK_SOURCE_PACKAGE_ID,
            *(review.successor_package_id for review in ledger.pack_reviews),
            *(artifact.artifact_id for artifact in _PACKAGE.staged_data_artifacts),
            *staged_source_row_ids,
        }
    )


def audit_staged_package_is_not_active(
    *,
    current_source_package_ids: tuple[str, ...],
    phase17_source_package_ids: tuple[str, ...],
    runtime_source_package_ids: tuple[str, ...],
    generated_current_documents: Mapping[str, str],
) -> None:
    groups = (
        current_source_package_ids,
        phase17_source_package_ids,
        runtime_source_package_ids,
    )
    if any(type(group) is not tuple for group in groups):
        raise JulyFactionPackStagingError("July cutover guard package-ID groups must be tuples.")
    forbidden = staged_identity_tokens()
    active_tokens = {value for group in groups for value in group}
    leaked_package_ids = forbidden.intersection(active_tokens)
    if leaked_package_ids:
        raise JulyFactionPackStagingError(
            "Staged July package identity leaked into an active source or runtime mapping."
        )
    for filename, document in generated_current_documents.items():
        if type(filename) is not str or type(document) is not str:
            raise JulyFactionPackStagingError(
                "July cutover guard documents must map filenames to text."
            )
        if any(token in document for token in forbidden):
            raise JulyFactionPackStagingError(
                "Staged July package identity leaked into generated current documentation."
            )


__all__ = (
    "ACTIVATION_STATUS",
    "SOURCE_DATE",
    "SOURCE_PACKAGE_ID",
    "SOURCE_PAYLOAD_CHECKSUM_SHA256",
    "SOURCE_TITLE",
    "SOURCE_VERSION",
    "JulyDaemonicManifestationArtifact",
    "JulyDatasheetArtifact",
    "JulyDatasheetPreviewArtifact",
    "JulyDeltaLedgerArtifact",
    "JulyDetachmentArtifact",
    "JulyFactionPackStagingError",
    "JulyPhase17ECoverageArtifact",
    "JulyPhase17FExecutionArtifact",
    "JulyRuntimeScaffoldArtifact",
    "JulyStagingPackageArtifact",
    "JulySubruleArtifact",
    "audit_datasheet_preview_links",
    "audit_load_only_artifact_links",
    "audit_manifest_links",
    "audit_runtime_predecessor_references",
    "audit_staged_package_is_not_active",
    "daemonic_manifestation",
    "datasheet_support_preview",
    "datasheets",
    "delta_ledger",
    "detachments",
    "phase17e_coverage",
    "phase17f_execution",
    "runtime_scaffolds",
    "source_package_identity_payload",
    "staged_identity_tokens",
    "staging_package",
    "subrules",
)
