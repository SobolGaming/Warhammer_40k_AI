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
    EXPECTED_ANOMALY_OBSERVATION_SHA256,
    EXPECTED_ANOMALY_TRANSCRIPTION_SHA256,
    EXPECTED_ARTIFACT_SHA256,
    EXPECTED_INSANE_BRAVERY_FAQ_OBSERVED_AT,
    EXPECTED_INSANE_BRAVERY_FAQ_SOURCE_URL,
    EXPECTED_OBSERVED_AT,
    EXPECTED_SOURCE_URL,
    CoreStratagemAppSourceArtifactError,
    CoreStratagemAppSourcePackageArtifact,
    CoreStratagemNumberingAnomalyArtifact,
    CoreStratagemSourceRuleArtifact,
    core_stratagem_app_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"


def _load_artifact() -> CoreStratagemAppSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source artifact could not be loaded."
        ) from exc
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source artifact bytes drifted from their reviewed pin."
        )
    return core_stratagem_app_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_TITLE: Final = _ARTIFACT.source_document.source_title
SOURCE_URL: Final = EXPECTED_SOURCE_URL
OBSERVED_AT: Final = EXPECTED_OBSERVED_AT
FAQ_SOURCE_TITLE: Final = _ARTIFACT.faq_source_document.source_title
FAQ_SOURCE_URL: Final = EXPECTED_INSANE_BRAVERY_FAQ_SOURCE_URL
FAQ_OBSERVED_AT: Final = EXPECTED_INSANE_BRAVERY_FAQ_OBSERVED_AT
PACKAGE_HASH: Final = _ARTIFACT.package_hash
RULE_SOURCE_IDS: Final = {rule.rule_id: rule.source_id for rule in _ARTIFACT.rules}
TRANSCRIPTION_SHA256_BY_RULE_ID: Final = {
    rule.rule_id: rule.transcription_sha256 for rule in _ARTIFACT.rules
}
SOURCE_OBSERVATION_SHA256_BY_RULE_ID: Final = {
    rule.rule_id: rule.source_observation_sha256 for rule in _ARTIFACT.rules
}


def validate_core_stratagem_app_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source artifact bytes drifted from their reviewed pin."
        )
    core_stratagem_app_source_artifact_from_json_bytes(raw)


def source_rule_records() -> tuple[CoreStratagemSourceRuleArtifact, ...]:
    return _ARTIFACT.rules


def source_rule_by_id(rule_id: str) -> CoreStratagemSourceRuleArtifact:
    if type(rule_id) is not str or not rule_id or rule_id != rule_id.strip():
        raise CoreStratagemAppSourceArtifactError(
            "Core Stratagem App-source rule_id must be non-empty stripped text."
        )
    for rule in _ARTIFACT.rules:
        if rule.rule_id == rule_id:
            return rule
    raise CoreStratagemAppSourceArtifactError("Core Stratagem App-source rule_id was not found.")


def numbering_anomalies() -> tuple[CoreStratagemNumberingAnomalyArtifact, ...]:
    return _ARTIFACT.numbering_anomalies


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return _ARTIFACT.evidence_record_values()


def _build_source_catalog() -> SourceCatalog:
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
    faq_document_id = SourceDocumentId(
        package_id=package_id,
        document_id=_ARTIFACT.faq_source_document.document_id,
    )
    provenance = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id=f"{SOURCE_PACKAGE_ID}:manifest:p15d-source-provenance",
        raw_text=(
            "P15D records reviewed Core Stratagem source rows 15.05 through 15.09 from "
            "the project-authoritative maintained App mirror at 40k.app, observed "
            f"{OBSERVED_AT}. Provider numbering remains locator metadata; stable title and "
            "complete operative text resolve the stale Fight 12.01 Crushing Impact 15.06 "
            "cross-reference to current heading 15.05 without changing runtime identity. "
            "40k.app remains a non-affiliated hosting provider. The retained official Core "
            f"Rules PDF hash is {_ARTIFACT.source_document.official_pdf_sha256}."
        ),
    )
    faq_provenance = RuleSourceText.from_raw(
        objective_scope=ObjectiveRuleScope.CORE_RULES,
        source_id=f"{SOURCE_PACKAGE_ID}:manifest:p15f-source-provenance",
        raw_text=(
            "P15F records the reviewed Insane Bravery FAQ from the project-authoritative "
            "maintained Game Datamissions App-data mirror v931, observed "
            f"{FAQ_OBSERVED_AT}. The provider is non-affiliated, and the FAQ preserves the "
            "stable Insane Bravery source and runtime identities while forbidding a "
            "controlling player from targeting an already Battle-shocked unit."
        ),
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=f"{SOURCE_TITLE} (reviewed App-mirror observation {OBSERVED_AT})",
                source_texts=(
                    provenance,
                    *tuple(
                        RuleSourceText.from_raw(
                            objective_scope=ObjectiveRuleScope.CORE_RULES,
                            source_id=rule.source_id,
                            raw_text=rule.source_text,
                        )
                        for rule in _ARTIFACT.rules
                        if rule.rule_id != "insane-bravery"
                    ),
                ),
            ),
            SourceDocument(
                document_id=faq_document_id,
                title=f"{FAQ_SOURCE_TITLE} (reviewed App-data observation {FAQ_OBSERVED_AT})",
                source_texts=(
                    faq_provenance,
                    RuleSourceText.from_raw(
                        objective_scope=ObjectiveRuleScope.CORE_RULES,
                        source_id=source_rule_by_id("insane-bravery").source_id,
                        raw_text=source_rule_by_id("insane-bravery").source_text,
                    ),
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-core-stratagem-source-observed-2026-09-02"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id, faq_document_id),
            ),
        ),
    )


def source_package() -> RuleSourcePackage:
    required_source_ids = tuple(sorted(rule.source_id for rule in _ARTIFACT.rules))
    return RuleSourcePackage(
        source_catalog=_build_source_catalog(),
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=required_source_ids,
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


__all__ = (
    "EXPECTED_ANOMALY_OBSERVATION_SHA256",
    "EXPECTED_ANOMALY_TRANSCRIPTION_SHA256",
    "EXPECTED_ARTIFACT_SHA256",
    "FAQ_OBSERVED_AT",
    "FAQ_SOURCE_TITLE",
    "FAQ_SOURCE_URL",
    "OBSERVED_AT",
    "PACKAGE_HASH",
    "RULE_SOURCE_IDS",
    "SOURCE_OBSERVATION_SHA256_BY_RULE_ID",
    "SOURCE_PACKAGE_ID",
    "SOURCE_TITLE",
    "SOURCE_URL",
    "SOURCE_VERSION",
    "TRANSCRIPTION_SHA256_BY_RULE_ID",
    "CoreStratagemAppSourceArtifactError",
    "core_stratagem_app_source_artifact_from_json_bytes",
    "numbering_anomalies",
    "source_evidence_records",
    "source_package",
    "source_rule_by_id",
    "source_rule_records",
    "validate_core_stratagem_app_source_artifact_bytes",
)
