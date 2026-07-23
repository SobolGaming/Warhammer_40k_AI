from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    JULY_FACTION_PACK_SOURCE_PACKAGE_ID,
    JulyDeltaLedgerArtifact,
    JulyFactionPackStagingError,
    JulyStagingPackageArtifact,
    audit_manifest_links,
    audit_runtime_predecessor_references,
    canonical_json_sha256_from_bytes,
    july_delta_ledger_from_json_bytes,
    july_staging_package_from_json_bytes,
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
    return frozenset(
        {
            JULY_FACTION_PACK_SOURCE_PACKAGE_ID,
            *(review.successor_package_id for review in ledger.pack_reviews),
            *(artifact.artifact_id for artifact in _PACKAGE.staged_data_artifacts),
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
    "JulyDeltaLedgerArtifact",
    "JulyFactionPackStagingError",
    "JulyStagingPackageArtifact",
    "audit_manifest_links",
    "audit_runtime_predecessor_references",
    "audit_staged_package_is_not_active",
    "delta_ledger",
    "source_package_identity_payload",
    "staged_identity_tokens",
    "staging_package",
)
