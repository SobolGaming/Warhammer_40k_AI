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
    EXPECTED_OBSERVED_AT,
    EXPECTED_PACKAGE_HASH,
    EXPECTED_RULE_IDENTITIES,
    EXPECTED_SOURCE_URL,
    CoreOtherConceptsSourceArtifactError,
    CoreOtherConceptsSourcePackageArtifact,
    CoreOtherConceptsSourceRuleArtifact,
    core_other_concepts_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"
EXPECTED_ARTIFACT_SHA256: Final = "044f2edc2f7b45263601f0dacb4dceeb6d76ec3da0ba61a7d112a7fbc5973f92"


def _load_artifact() -> CoreOtherConceptsSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact could not be loaded."
        ) from exc
    validate_core_other_concepts_source_artifact_bytes(raw)
    return core_other_concepts_source_artifact_from_json_bytes(raw)


def validate_core_other_concepts_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact bytes drifted from their reviewed pin."
        )
    core_other_concepts_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_URL: Final = EXPECTED_SOURCE_URL
OBSERVED_AT: Final = EXPECTED_OBSERVED_AT
PACKAGE_HASH: Final = EXPECTED_PACKAGE_HASH
VISIBILITY_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES[0][1]
TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITIES[0][4]
VISIBILITY_BATTLEFIELD_EDGE_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES[4][1]
BATTLEFIELD_EDGE_PACKAGE_ID: Final = "gw-11e-core-other-concepts-battlefield-edge"
BATTLEFIELD_EDGE_SOURCE_VERSION: Final = "maintained-app-mirror-observed-2026-10-01"
MORTAL_WOUNDS_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES[1][1]
MORTAL_WOUNDS_TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITIES[1][4]


def source_rule_record() -> CoreOtherConceptsSourceRuleArtifact:
    return _ARTIFACT.rules[0]


def source_rule_record_by_id(rule_id: str) -> CoreOtherConceptsSourceRuleArtifact:
    if type(rule_id) is not str or not rule_id:
        raise CoreOtherConceptsSourceArtifactError("Other Concepts rule_id must be a string.")
    for rule in _ARTIFACT.rules:
        if rule.rule_id == rule_id:
            return rule
    raise CoreOtherConceptsSourceArtifactError("Other Concepts rule_id is unknown.")


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(evidence.to_rule_evidence_record() for evidence in _ARTIFACT.evidence[:8])


def source_package() -> RuleSourcePackage:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version=SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=SOURCE_VERSION,
        source_date=date(2026, 9, 8),
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
                    for rule in _ARTIFACT.rules[:4]
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-other-concepts-source-observed-2026-09-08"
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
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules[:4])),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


def battlefield_edge_source_catalog() -> SourceCatalog:
    """The appended observation has its own mandatory, dated source package.

    The original four-source catalog/eight-observation public package remains
    unchanged. Both packages use the same eagerly authenticated JSON artifact.
    """
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=BATTLEFIELD_EDGE_PACKAGE_ID,
        version=BATTLEFIELD_EDGE_SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=BATTLEFIELD_EDGE_SOURCE_VERSION, source_date=date(2026, 10, 1)
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id="maintained-app-mirror-visibility-battlefield-edge-2026-10-01",
    )
    rule = _ARTIFACT.rules[4]
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title="Game Datamissions Visibility Battlefield Edge FAQ",
                source_texts=(
                    RuleSourceText.from_raw(
                        objective_scope=ObjectiveRuleScope.CORE_RULES,
                        source_id=rule.source_id,
                        raw_text=rule.source_text,
                    ),
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=BATTLEFIELD_EDGE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-visibility-battlefield-edge-source-observed-2026-10-01"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id,),
            ),
        ),
    )


def battlefield_edge_source_package() -> RuleSourcePackage:
    return RuleSourcePackage(
        source_catalog=battlefield_edge_source_catalog(),
        source_evidence_catalog=SourceEvidenceCatalog(
            records=tuple(evidence.to_rule_evidence_record() for evidence in _ARTIFACT.evidence[8:])
        ),
        evidence_required_source_ids=(VISIBILITY_BATTLEFIELD_EDGE_SOURCE_ID,),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


def source_packages() -> tuple[RuleSourcePackage, ...]:
    """Compose the preserved Core package and mandatory current FAQ package."""
    return source_package(), battlefield_edge_source_package()


__all__ = (
    "BATTLEFIELD_EDGE_PACKAGE_ID",
    "BATTLEFIELD_EDGE_SOURCE_VERSION",
    "EXPECTED_ARTIFACT_SHA256",
    "MORTAL_WOUNDS_SOURCE_ID",
    "MORTAL_WOUNDS_TRANSCRIPTION_SHA256",
    "OBSERVED_AT",
    "PACKAGE_HASH",
    "SOURCE_PACKAGE_ID",
    "SOURCE_URL",
    "SOURCE_VERSION",
    "TRANSCRIPTION_SHA256",
    "VISIBILITY_BATTLEFIELD_EDGE_SOURCE_ID",
    "VISIBILITY_SOURCE_ID",
    "CoreOtherConceptsSourceArtifactError",
    "battlefield_edge_source_catalog",
    "battlefield_edge_source_package",
    "core_other_concepts_source_artifact_from_json_bytes",
    "source_evidence_records",
    "source_package",
    "source_packages",
    "source_rule_record",
    "source_rule_record_by_id",
    "validate_core_other_concepts_source_artifact_bytes",
)
