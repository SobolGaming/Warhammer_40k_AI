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
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    RuleEvidenceRecord,
    RuleSourcePackage,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    EXPECTED_PACKAGE_HASH,
    EXPECTED_RULE_IDENTITIES,
    CoreTransportsSourceArtifactError,
    CoreTransportsSourcePackageArtifact,
    CoreTransportsSourceRuleArtifact,
    core_transports_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"
EXPECTED_ARTIFACT_SHA256: Final = "861a86d603ea1c9e676c2f9c505760b3130eb006a278f7e387fbffaedfe6e190"


def _load_artifact() -> CoreTransportsSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreTransportsSourceArtifactError(
            "Transports source artifact could not be loaded."
        ) from exc
    validate_core_transports_source_artifact_bytes(raw)
    return core_transports_source_artifact_from_json_bytes(raw)


def validate_core_transports_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreTransportsSourceArtifactError(
            "Transports source artifact bytes drifted from their reviewed pin."
        )
    core_transports_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
PACKAGE_HASH: Final = EXPECTED_PACKAGE_HASH
EMERGENCY_DISEMBARK_MOVE_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES[0][1]
EMERGENCY_DISEMBARK_TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITIES[0][4]
ASSAULT_DISEMBARK_MOVE_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES[1][1]
ASSAULT_DISEMBARK_TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITIES[1][4]


def source_rule_records() -> tuple[CoreTransportsSourceRuleArtifact, ...]:
    return _ARTIFACT.rules


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
        source_date=date(2026, 9, 2),
    )
    document_ids = tuple(
        SourceDocumentId(package_id=package_id, document_id=document.document_id)
        for document in _ARTIFACT.source_documents
    )
    rule_by_source_id = {rule.source_id: rule for rule in source_rule_records()}
    source_catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=tuple(
            SourceDocument(
                document_id=document_id,
                title=document.source_title,
                source_texts=tuple(
                    RuleSourceText.from_raw(
                        source_id=source_id,
                        raw_text=rule_by_source_id[source_id].source_text,
                    )
                    for source_id in document.rule_source_ids
                ),
            )
            for document_id, document in zip(
                document_ids,
                _ARTIFACT.source_documents,
                strict=True,
            )
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-transports-source-observed-2026-09-02"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=document_ids,
            ),
        ),
    )
    return RuleSourcePackage(
        source_catalog=source_catalog,
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=(
            ASSAULT_DISEMBARK_MOVE_SOURCE_ID,
            EMERGENCY_DISEMBARK_MOVE_SOURCE_ID,
        ),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


__all__ = (
    "ASSAULT_DISEMBARK_MOVE_SOURCE_ID",
    "ASSAULT_DISEMBARK_TRANSCRIPTION_SHA256",
    "EMERGENCY_DISEMBARK_MOVE_SOURCE_ID",
    "EMERGENCY_DISEMBARK_TRANSCRIPTION_SHA256",
    "EXPECTED_ARTIFACT_SHA256",
    "PACKAGE_HASH",
    "SOURCE_PACKAGE_ID",
    "SOURCE_VERSION",
    "CoreTransportsSourceArtifactError",
    "core_transports_source_artifact_from_json_bytes",
    "source_evidence_records",
    "source_package",
    "source_rule_records",
    "validate_core_transports_source_artifact_bytes",
)
