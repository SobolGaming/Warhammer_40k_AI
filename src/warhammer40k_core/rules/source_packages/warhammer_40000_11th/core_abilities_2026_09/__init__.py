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
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
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
    EXPECTED_DOCUMENT_IDENTITY,
    EXPECTED_HAZARDOUS_RULE_IDENTITY,
    EXPECTED_PACKAGE_HASH,
    EXPECTED_RULE_IDENTITY,
    EXPECTED_SCOUT_ALTERNATION_RULE_IDENTITY,
    CoreAbilitiesSourceArtifactError,
    CoreAbilitiesSourcePackageArtifact,
    CoreAbilitiesSourceRuleArtifact,
    core_abilities_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"
EXPECTED_ARTIFACT_SHA256: Final = "fbfb7dae154292d33963a9c81d5c14025aa6c44873b7ee7a60c1fce754909bf7"


def _load_artifact() -> CoreAbilitiesSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source artifact could not be loaded."
        ) from exc
    validate_core_abilities_source_artifact_bytes(raw)
    return core_abilities_source_artifact_from_json_bytes(raw)


def validate_core_abilities_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreAbilitiesSourceArtifactError(
            "Core Abilities source artifact bytes drifted from their reviewed pin."
        )
    core_abilities_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_URL: Final = EXPECTED_DOCUMENT_IDENTITY[1]
OBSERVED_AT: Final = EXPECTED_DOCUMENT_IDENTITY[2]
APP_VERSION: Final = EXPECTED_DOCUMENT_IDENTITY[3]
PACKAGE_HASH: Final = EXPECTED_PACKAGE_HASH
DEADLY_DEMISE_SOURCE_ID: Final = EXPECTED_RULE_IDENTITY[3]
TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITY[7]
SCOUT_ALTERNATION_FAQ_SOURCE_ID: Final = EXPECTED_SCOUT_ALTERNATION_RULE_IDENTITY[3]
SCOUT_ALTERNATION_TRANSCRIPTION_SHA256: Final = EXPECTED_SCOUT_ALTERNATION_RULE_IDENTITY[7]
HAZARDOUS_SOURCE_ID: Final = EXPECTED_HAZARDOUS_RULE_IDENTITY[3]
HAZARDOUS_TRANSCRIPTION_SHA256: Final = EXPECTED_HAZARDOUS_RULE_IDENTITY[7]


def source_rule_record() -> CoreAbilitiesSourceRuleArtifact:
    return _ARTIFACT.rules[0]


def scout_alternation_faq_record() -> CoreAbilitiesSourceRuleArtifact:
    return _ARTIFACT.rules[1]


def hazardous_rule_record() -> CoreAbilitiesSourceRuleArtifact:
    return _ARTIFACT.rules[2]


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
                source_texts=tuple(
                    RuleSourceText.from_raw(
                        objective_scope=ObjectiveRuleScope.CORE_RULES,
                        source_id=rule.source_id,
                        raw_text=rule.source_text,
                    )
                    for rule in _ARTIFACT.rules
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-core-abilities-source-observed-2026-09-02"
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
        evidence_required_source_ids=(
            DEADLY_DEMISE_SOURCE_ID,
            HAZARDOUS_SOURCE_ID,
            SCOUT_ALTERNATION_FAQ_SOURCE_ID,
        ),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


__all__ = (
    "APP_VERSION",
    "DEADLY_DEMISE_SOURCE_ID",
    "EXPECTED_ARTIFACT_SHA256",
    "HAZARDOUS_SOURCE_ID",
    "HAZARDOUS_TRANSCRIPTION_SHA256",
    "OBSERVED_AT",
    "PACKAGE_HASH",
    "SCOUT_ALTERNATION_FAQ_SOURCE_ID",
    "SCOUT_ALTERNATION_TRANSCRIPTION_SHA256",
    "SOURCE_PACKAGE_ID",
    "SOURCE_URL",
    "SOURCE_VERSION",
    "TRANSCRIPTION_SHA256",
    "CoreAbilitiesSourceArtifactError",
    "core_abilities_source_artifact_from_json_bytes",
    "hazardous_rule_record",
    "scout_alternation_faq_record",
    "source_evidence_records",
    "source_package",
    "source_rule_record",
    "validate_core_abilities_source_artifact_bytes",
)
