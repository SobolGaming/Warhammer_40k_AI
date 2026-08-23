from __future__ import annotations

from typing import Final

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError,
    EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact,
    artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/rule_ir.json"

__all__ = (
    "DATASHEET_REVIEWS",
    "OFFICIAL_DOCUMENT_FILENAME",
    "OFFICIAL_DOCUMENT_SHA256",
    "OVERLAY_PACKAGE_HASH",
    "PACKAGE_HASH",
    "REVIEW_MANIFEST_FILENAME",
    "REVIEW_MANIFEST_SHA256",
    "SOURCE_ARTIFACT_HASH",
    "SOURCE_PACKAGE_ID",
    "SOURCE_SNAPSHOT_FILENAME",
    "SOURCE_SNAPSHOT_SHA256",
    "EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError",
    "datasheet_rule_ir_payload_by_source_row_id",
    "supported_datasheet_source_row_ids",
    "validate_generated_artifact_bytes",
)


def _load_artifact() -> EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise EmperorsChildrenLordMaulerfiendSpawnRuleIrArtifactError(
            "Grouped Emperor's Children generated RuleIR artifact could not be loaded."
        ) from exc
    return artifact_from_json_bytes(raw)


_ARTIFACT: Final[EmperorsChildrenLordMaulerfiendSpawnRuleIrPackageArtifact] = _load_artifact()

SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_SNAPSHOT_FILENAME: Final = _ARTIFACT.source_snapshot_filename
SOURCE_SNAPSHOT_SHA256: Final = _ARTIFACT.source_snapshot_sha256
SOURCE_ARTIFACT_HASH: Final = _ARTIFACT.source_artifact_hash
OFFICIAL_DOCUMENT_FILENAME: Final = _ARTIFACT.official_document_filename
OFFICIAL_DOCUMENT_SHA256: Final = _ARTIFACT.official_document_sha256
REVIEW_MANIFEST_FILENAME: Final = _ARTIFACT.review_manifest_filename
REVIEW_MANIFEST_SHA256: Final = _ARTIFACT.review_manifest_sha256
OVERLAY_PACKAGE_HASH: Final = _ARTIFACT.overlay_package_hash
DATASHEET_REVIEWS: Final[dict[str, tuple[str, str, str, str | None]]] = {
    row.datasheet_id: (
        row.datasheet_name,
        row.review_row_id,
        row.review_treatment,
        row.pdf_page_reference,
    )
    for row in _ARTIFACT.datasheets
}
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def supported_datasheet_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_ARTIFACT.records))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return _ARTIFACT.rule_ir_payload_by_source_row_id(source_row_id)


def validate_generated_artifact_bytes(raw: bytes) -> None:
    artifact_from_json_bytes(raw)
