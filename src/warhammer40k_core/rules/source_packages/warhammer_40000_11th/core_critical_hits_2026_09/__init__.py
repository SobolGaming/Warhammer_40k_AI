"""Reviewed, immutable critical-hits source authority."""

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

EXPECTED_ARTIFACT_SHA256: Final = "d4e25297d34f21a9f3b504b78eb010f9c667914a87d6332a4c9a72bb4ca3badb"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-critical-hits"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-13"
CRITICAL_SUCCESS_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:critical-hit-success-faq"
SNAP_CRITICAL_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:snap-critical-hit-faq"


class CriticalHitsSourceError(ValueError):
    """The reviewed critical-hits source or its provenance has drifted."""


class CriticalHitsSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class CriticalHitsSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[CriticalHitsSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> CriticalHitsSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CriticalHitsSourceError("Critical hits source bytes drifted from their reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=CriticalHitsSourceArtifact)
    except msgspec.DecodeError as exc:
        raise CriticalHitsSourceError("Critical hits source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-critical-hits-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (CRITICAL_SUCCESS_SOURCE_ID, SNAP_CRITICAL_SOURCE_ID)
    ):
        raise CriticalHitsSourceError("Critical hits source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise CriticalHitsSourceError("Critical hits transcription hash drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise CriticalHitsSourceError("Critical hits execution evidence is incomplete.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[CriticalHitsSourceRule, ...]:
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
                version_id=SOURCE_VERSION, source_date=date(2026, 9, 13)
            ),
            documents=(
                SourceDocument(
                    document_id=SourceDocumentId(package_id=package_id, document_id="p04b"),
                    title="Reviewed maintained App-data rules critical-hits",
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
