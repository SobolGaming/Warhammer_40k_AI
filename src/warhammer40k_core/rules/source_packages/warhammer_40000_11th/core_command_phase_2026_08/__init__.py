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
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_CATEGORY_OBSERVED_AT,
    EXPECTED_CATEGORY_URL,
    EXPECTED_OFFICIAL_PDF_SHA256,
    EXPECTED_PACKAGE_HASH,
    EXPECTED_SEARCH_INDEX_OBSERVED_AT,
    EXPECTED_SEARCH_INDEX_SEQUENCE_TRANSCRIPTION_SHA256,
    EXPECTED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256,
    EXPECTED_SEARCH_INDEX_URL,
    CoreCommandPhaseSearchIndexObservationArtifact,
    CoreCommandPhaseSourceArtifactError,
    CoreCommandPhaseSourcePackageArtifact,
    CoreCommandPhaseSourceRuleArtifact,
    core_command_phase_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"


def _load_artifact() -> CoreCommandPhaseSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source artifact could not be loaded."
        ) from exc
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source artifact bytes drifted from their reviewed pin."
        )
    return core_command_phase_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_TITLE: Final = _ARTIFACT.source_document.source_title
SOURCE_URL: Final = EXPECTED_SEARCH_INDEX_URL
OBSERVED_AT: Final = EXPECTED_SEARCH_INDEX_OBSERVED_AT
CATEGORY_URL: Final = EXPECTED_CATEGORY_URL
CATEGORY_OBSERVED_AT: Final = EXPECTED_CATEGORY_OBSERVED_AT
PACKAGE_HASH: Final = _ARTIFACT.package_hash
RULE_SOURCE_IDS: Final = {rule.rule_id: rule.source_id for rule in _ARTIFACT.rules}
START_OF_COMMAND_PHASE_SOURCE_ID: Final = RULE_SOURCE_IDS["start-of-command-phase"]
GAIN_CORE_CP_SOURCE_ID: Final = RULE_SOURCE_IDS["gain-core-cp"]
BATTLE_SHOCK_SOURCE_ID: Final = RULE_SOURCE_IDS["battle-shock"]
TRANSCRIPTION_SHA256_BY_RULE_ID: Final = {
    rule.rule_id: rule.transcription_sha256 for rule in _ARTIFACT.rules
}
OFFICIAL_PDF_TRANSCRIPTION_SHA256_BY_RULE_ID: Final = {
    rule.rule_id: rule.official_pdf_transcription_sha256 for rule in _ARTIFACT.rules
}
SOURCE_OBSERVATION_SHA256_BY_RULE_ID: Final = {
    rule.rule_id: rule.source_observation_sha256 for rule in _ARTIFACT.rules
}


def validate_core_command_phase_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source artifact bytes drifted from their reviewed pin."
        )
    core_command_phase_source_artifact_from_json_bytes(raw)


def source_rule_records() -> tuple[CoreCommandPhaseSourceRuleArtifact, ...]:
    return _ARTIFACT.rules


def source_rule_by_id(rule_id: str) -> CoreCommandPhaseSourceRuleArtifact:
    if type(rule_id) is not str or not rule_id or rule_id != rule_id.strip():
        raise CoreCommandPhaseSourceArtifactError(
            "Command-phase source rule_id must be non-empty stripped text."
        )
    for rule in _ARTIFACT.rules:
        if rule.rule_id == rule_id:
            return rule
    raise CoreCommandPhaseSourceArtifactError("Command-phase source rule_id was not found.")


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(evidence.to_rule_evidence_record() for evidence in _ARTIFACT.evidence_records)


def search_index_observation() -> CoreCommandPhaseSearchIndexObservationArtifact:
    return _ARTIFACT.search_index_observation


def _build_source_catalog() -> SourceCatalog:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version=SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=SOURCE_VERSION,
        source_date=date(2026, 8, 26),
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id=_ARTIFACT.source_document.document_id,
    )
    provenance = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id=f"{SOURCE_PACKAGE_ID}:manifest:p08ab-source-provenance",
        raw_text=(
            "P08A and P08B pair reviewed Command-phase section headings with the retained "
            f"project-authoritative 40k.app search-index observation at {SOURCE_URL}, observed "
            f"{OBSERVED_AT}. That RuleEvidence pins the exact five-heading sequence only and "
            "contains no operative body text; the "
            f"older category-08 audit at {CATEGORY_URL}, observed {CATEGORY_OBSERVED_AT}, remains "
            "category-locator metadata and retains no page body. Complete operative text for "
            "sections 08.01 through 08.03 is separately transcribed from official Core Rules PDF "
            "source "
            f"{_ARTIFACT.source_document.official_pdf_source_id}, SHA-256 "
            f"{EXPECTED_OFFICIAL_PDF_SHA256}. Battle-shock runtime support remains partial only "
            "because P01 retains the off-battlefield embarked and Strategic Reserve extension; "
            "P08B's on-battlefield scope is executable."
        ),
    )
    source_texts = [provenance]
    for rule in _ARTIFACT.rules:
        source_texts.extend(
            (
                RuleSourceText.from_raw(
                    objective_scope=ObjectiveRuleScope.CORE_RULES,
                    source_id=rule.source_id,
                    raw_text=rule.source_text,
                ),
                RuleSourceText.from_raw(
                    objective_scope=ObjectiveRuleScope.CORE_RULES,
                    source_id=f"{rule.source_id}:official-pdf-body",
                    raw_text=rule.official_pdf_source_text,
                ),
            )
        )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=(
                    f"{SOURCE_TITLE} (observed heading sequence plus retained official-PDF text)"
                ),
                source_texts=tuple(source_texts),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-command-phase-source-observed-2026-08-26"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id,),
            ),
        ),
    )


def source_package() -> RuleSourcePackage:
    return RuleSourcePackage(
        source_catalog=_build_source_catalog(),
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


__all__ = (
    "BATTLE_SHOCK_SOURCE_ID",
    "CATEGORY_OBSERVED_AT",
    "CATEGORY_URL",
    "EXPECTED_ARTIFACT_SHA256",
    "EXPECTED_OFFICIAL_PDF_SHA256",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_SEARCH_INDEX_SEQUENCE_TRANSCRIPTION_SHA256",
    "EXPECTED_SEARCH_INDEX_SOURCE_OBSERVATION_SHA256",
    "GAIN_CORE_CP_SOURCE_ID",
    "OBSERVED_AT",
    "OFFICIAL_PDF_TRANSCRIPTION_SHA256_BY_RULE_ID",
    "PACKAGE_HASH",
    "RULE_SOURCE_IDS",
    "SOURCE_OBSERVATION_SHA256_BY_RULE_ID",
    "SOURCE_PACKAGE_ID",
    "SOURCE_TITLE",
    "SOURCE_URL",
    "SOURCE_VERSION",
    "START_OF_COMMAND_PHASE_SOURCE_ID",
    "TRANSCRIPTION_SHA256_BY_RULE_ID",
    "CoreCommandPhaseSourceArtifactError",
    "core_command_phase_source_artifact_from_json_bytes",
    "search_index_observation",
    "source_evidence_records",
    "source_package",
    "source_rule_by_id",
    "source_rule_records",
    "validate_core_command_phase_source_artifact_bytes",
)
