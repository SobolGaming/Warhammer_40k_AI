"""Reviewed, immutable flying source authority."""

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

EXPECTED_ARTIFACT_SHA256: Final = "e3e59cb5903b1d582464be68f60deebce0b28cef5e8d67a2ea16ba564599dbb5"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-flying"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-15"
TAKE_TO_THE_SKIES_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:take-to-the-skies"


class FlyingSourceError(ValueError):
    """The reviewed flying source or its provenance has drifted."""


class FlyingSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class FlyingSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[FlyingSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> FlyingSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise FlyingSourceError("Flying distance source bytes drifted from their reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=FlyingSourceArtifact)
    except msgspec.DecodeError as exc:
        raise FlyingSourceError("Flying distance source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-flying-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules) != (TAKE_TO_THE_SKIES_SOURCE_ID,)
    ):
        raise FlyingSourceError("Flying distance source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise FlyingSourceError("Flying distance transcription hash drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise FlyingSourceError("Flying distance execution evidence is incomplete.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[FlyingSourceRule, ...]:
    return _ARTIFACT.rules


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(RuleEvidenceRecord.from_payload(row) for row in _ARTIFACT.evidence)


def _build_source_package() -> RuleSourcePackage:
    package_id = DataPackageId(
        namespace="games-workshop", package_name=SOURCE_PACKAGE_ID, version=SOURCE_VERSION
    )
    return RuleSourcePackage(
        source_catalog=SourceCatalog(
            package_id=package_id,
            catalog_version=CatalogVersion.dated(
                version_id=SOURCE_VERSION, source_date=date(2026, 9, 15)
            ),
            documents=(
                SourceDocument(
                    document_id=SourceDocumentId(package_id=package_id, document_id="p21a"),
                    title="Reviewed maintained App-data rules flying",
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
        ),
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE
