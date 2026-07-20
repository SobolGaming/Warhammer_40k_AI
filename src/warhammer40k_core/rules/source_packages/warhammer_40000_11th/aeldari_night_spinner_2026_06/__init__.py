from __future__ import annotations

from typing import Final

from warhammer40k_core.rules.rule_ir import RuleIRPayload
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    NightSpinnerRuleIrArtifactError,
    NightSpinnerRuleIrPackageArtifact,
    night_spinner_rule_ir_package_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/rule_ir.json"

__all__ = (
    "DATASHEET_ID",
    "DATASHEET_NAME",
    "PACKAGE_HASH",
    "SOURCE_ARTIFACT_HASH",
    "SOURCE_PACKAGE_ID",
    "SOURCE_SNAPSHOT_FILENAME",
    "SOURCE_SNAPSHOT_SHA256",
    "NightSpinnerRuleIrArtifactError",
    "datasheet_rule_ir_payload_by_source_row_id",
    "supported_datasheet_source_row_ids",
    "validate_generated_artifact_bytes",
)


def _load_artifact() -> NightSpinnerRuleIrPackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise NightSpinnerRuleIrArtifactError(
            "Night Spinner generated RuleIR artifact could not be loaded."
        ) from exc
    return night_spinner_rule_ir_package_artifact_from_json_bytes(raw)


_ARTIFACT: Final[NightSpinnerRuleIrPackageArtifact] = _load_artifact()

SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_SNAPSHOT_FILENAME: Final = _ARTIFACT.source_snapshot_filename
SOURCE_SNAPSHOT_SHA256: Final = _ARTIFACT.source_snapshot_sha256
SOURCE_ARTIFACT_HASH: Final = _ARTIFACT.source_artifact_hash
DATASHEET_ID: Final = _ARTIFACT.datasheet_id
DATASHEET_NAME: Final = _ARTIFACT.datasheet_name
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def supported_datasheet_source_row_ids() -> tuple[str, ...]:
    return tuple(sorted(_ARTIFACT.records))


def datasheet_rule_ir_payload_by_source_row_id(source_row_id: str) -> RuleIRPayload | None:
    return _ARTIFACT.rule_ir_payload_by_source_row_id(source_row_id)


def validate_generated_artifact_bytes(raw: bytes) -> None:
    night_spinner_rule_ir_package_artifact_from_json_bytes(raw)
