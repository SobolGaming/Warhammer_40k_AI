"""Hash-pinned P14 geometry and terminology source authority."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Final

import msgspec

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId, SourceDocumentId
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_evidence import (
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    LoadSupportStatus,
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RuleSourcePackage,
    SemanticExecutionStatus,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

EXPECTED_ARTIFACT_SHA256: Final = "184a3fe08b6da5ce85dc2bfd99c72d1d0bbd3b7b2a136d4f0c374d31de374be1"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-objectives"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-05"
TERRAIN_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:terrain-objectives"
MARKER_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:objectives-not-within-a-terrain-area"
CONTROL_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:terrain-objective-control-range"
TERMINOLOGY_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:objective-marker-terminology-faq"


class ObjectiveSourceError(ValueError):
    """The reviewed objective source identity or provenance has drifted."""


class ObjectiveSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class ObjectiveSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[ObjectiveSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_objective_source_artifact_bytes(raw: bytes) -> ObjectiveSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise ObjectiveSourceError(
            "Objective source artifact bytes drifted from their reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=ObjectiveSourceArtifact)
    except msgspec.DecodeError as exc:
        raise ObjectiveSourceError("Objective source artifact schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-objectives-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (TERRAIN_SOURCE_ID, MARKER_SOURCE_ID, CONTROL_SOURCE_ID, TERMINOLOGY_SOURCE_ID)
    ):
        raise ObjectiveSourceError("Objective source artifact identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise ObjectiveSourceError("Objective source transcription hash drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise ObjectiveSourceError("Objective source execution evidence is incomplete.")
    return artifact


_ARTIFACT: Final = validate_objective_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[ObjectiveSourceRule, ...]:
    return _ARTIFACT.rules


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(RuleEvidenceRecord.from_payload(row) for row in _ARTIFACT.evidence)


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


def _build_source_package() -> RuleSourcePackage:
    package_id = DataPackageId(
        namespace="games-workshop", package_name=SOURCE_PACKAGE_ID, version=SOURCE_VERSION
    )
    catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=CatalogVersion.dated(
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 5)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p14-objectives"),
                title="Reviewed maintained App-data objective geometry and terminology",
                source_texts=tuple(
                    RuleSourceText.from_raw(
                        source_id=rule.source_id,
                        raw_text=rule.source_text,
                        objective_scope=ObjectiveRuleScope.CORE_RULES,
                    )
                    for rule in _ARTIFACT.rules
                ),
            ),
        ),
        ruleset_bundles=(),
    )
    return RuleSourcePackage(
        source_catalog=catalog,
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()
