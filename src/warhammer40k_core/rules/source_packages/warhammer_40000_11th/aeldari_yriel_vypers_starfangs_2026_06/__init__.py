from __future__ import annotations

from typing import Final

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    AeldariDatasheetRuleIrArtifactError,
    AeldariDatasheetRuleIrPackageArtifact,
    aeldari_datasheet_rule_ir_package_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/rule_ir.json"

__all__ = (
    "DATASHEET_SOURCE_PAGES",
    "PACKAGE_HASH",
    "SOURCE_PACKAGE_ID",
    "SOURCE_PDF_FILENAME",
    "SOURCE_PDF_SHA256",
    "AeldariDatasheetRuleIrArtifactError",
    "datasheet_rule_ir_payload_by_source_row_id",
    "supported_datasheet_source_row_ids",
    "validate_generated_artifact_bytes",
)


def _load_artifact() -> AeldariDatasheetRuleIrPackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise AeldariDatasheetRuleIrArtifactError(
            "Aeldari datasheet generated RuleIR artifact could not be loaded."
        ) from exc
    return aeldari_datasheet_rule_ir_package_artifact_from_json_bytes(raw)


_ARTIFACT: Final[AeldariDatasheetRuleIrPackageArtifact] = _load_artifact()

SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_PDF_FILENAME: Final = _ARTIFACT.source_pdf_filename
SOURCE_PDF_SHA256: Final = _ARTIFACT.source_pdf_sha256
DATASHEET_SOURCE_PAGES: Final = {
    row.datasheet_id: tuple(row.source_page_numbers) for row in _ARTIFACT.datasheets
}
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def supported_datasheet_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_ARTIFACT.records))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return _ARTIFACT.rule_ir_payload_by_source_row_id(source_row_id)


def validate_generated_artifact_bytes(raw: bytes) -> None:
    aeldari_datasheet_rule_ir_package_artifact_from_json_bytes(raw)
