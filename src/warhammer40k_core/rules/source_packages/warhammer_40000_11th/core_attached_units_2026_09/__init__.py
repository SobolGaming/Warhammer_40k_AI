from __future__ import annotations

import hashlib
from datetime import date
from typing import Final

from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    DataPackageId,
    RulesetBundle,
    SourceDocumentId,
)
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_evidence import (
    RuleEvidenceRecord,
    RuleSourcePackage,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    EXPECTED_OBSERVED_AT,
    EXPECTED_PACKAGE_HASH,
    EXPECTED_RULE_IDENTITY,
    EXPECTED_SOURCE_URL,
    CoreAttachedUnitsSourceArtifactError,
    CoreAttachedUnitsSourcePackageArtifact,
    CoreAttachedUnitsSourceRuleArtifact,
    core_attached_units_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"
EXPECTED_ARTIFACT_SHA256: Final = "748cf1bc4cbd2749655abab43e97c7e04acfa4e63e79b9f84b565001b9c17b66"


def _load_artifact() -> CoreAttachedUnitsSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact could not be loaded."
        ) from exc
    validate_core_attached_units_source_artifact_bytes(raw)
    return core_attached_units_source_artifact_from_json_bytes(raw)


def validate_core_attached_units_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact bytes drifted from their reviewed pin."
        )
    core_attached_units_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_URL: Final = EXPECTED_SOURCE_URL
OBSERVED_AT: Final = EXPECTED_OBSERVED_AT
PACKAGE_HASH: Final = EXPECTED_PACKAGE_HASH
BODYGUARD_UNIT_DESTROYED_SOURCE_ID: Final = EXPECTED_RULE_IDENTITY[1]
TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITY[4]


def source_rule_record() -> CoreAttachedUnitsSourceRuleArtifact:
    return _ARTIFACT.rules[0]


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(evidence.to_rule_evidence_record() for evidence in _ARTIFACT.evidence)


def source_package() -> RuleSourcePackage:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version=SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=SOURCE_VERSION,
        source_date=date(2026, 9, 1),
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id=_ARTIFACT.source_document.document_id,
    )
    source_catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=_ARTIFACT.source_document.source_title,
                source_texts=(
                    RuleSourceText.from_raw(
                        source_id=source_rule_record().source_id,
                        raw_text=source_rule_record().source_text,
                    ),
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-attached-units-source-observed-2026-09-01"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id,),
            ),
        ),
    )
    return RuleSourcePackage(
        source_catalog=source_catalog,
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=(BODYGUARD_UNIT_DESTROYED_SOURCE_ID,),
    )


__all__ = (
    "BODYGUARD_UNIT_DESTROYED_SOURCE_ID",
    "EXPECTED_ARTIFACT_SHA256",
    "OBSERVED_AT",
    "PACKAGE_HASH",
    "SOURCE_PACKAGE_ID",
    "SOURCE_URL",
    "SOURCE_VERSION",
    "TRANSCRIPTION_SHA256",
    "CoreAttachedUnitsSourceArtifactError",
    "core_attached_units_source_artifact_from_json_bytes",
    "source_evidence_records",
    "source_package",
    "source_rule_record",
    "validate_core_attached_units_source_artifact_bytes",
)
