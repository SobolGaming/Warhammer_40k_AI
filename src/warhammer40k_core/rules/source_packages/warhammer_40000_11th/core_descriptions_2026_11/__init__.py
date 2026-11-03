"""Complete Core description evidence; source admission is not runtime certification."""

from __future__ import annotations

import hashlib
import json
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

EXPECTED_ARTIFACT_SHA256: Final = "8a82ba2800f48d34993ed332cc1a4d11e7eda895ee61bd2af36a51a98a51649e"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-descriptions"
SOURCE_VERSION: Final = "maintained-app-mirror-observed-2026-11-03"
SCOUT_MOVE_SOURCE_ID: Final = "gw-11e-core-abilities:core:scout-move"
EXPECTED_RULES: Final = (
    ("gw-11e-core-abilities:core:infiltrators", "24.20"),
    ("gw-11e-core-abilities:core:lone-operative", "24.24"),
    ("gw-11e-core-abilities:core:scouts", "24.31"),
    (SCOUT_MOVE_SOURCE_ID, "24.32"),
)


class CoreDescriptionSourceError(ValueError):
    """The reviewed complete source or its admission tuple drifted."""


class CoreDescriptionSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    dependency_source_ids: tuple[str, ...]
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class CoreDescriptionSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[CoreDescriptionSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> CoreDescriptionSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreDescriptionSourceError("Core description source bytes drifted from reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=CoreDescriptionSourceArtifact)
    except msgspec.DecodeError as exc:
        raise CoreDescriptionSourceError("Core description source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-descriptions-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple((rule.source_id, rule.section_id) for rule in artifact.rules) != EXPECTED_RULES
    ):
        raise CoreDescriptionSourceError("Core description source identity drifted.")
    payload = msgspec.to_builtins(artifact)
    payload["package_hash"] = ""
    if (
        hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        != artifact.package_hash
    ):
        raise CoreDescriptionSourceError("Core description source package hash drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise CoreDescriptionSourceError("Core description source transcription drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "not_certified"
            or rule.runtime_consumer_ids
            or rule.dependency_source_ids
            != ((SCOUT_MOVE_SOURCE_ID,) if rule.section_id == "24.31" else ())
        ):
            raise CoreDescriptionSourceError(
                "Core description source-only status or dependency drifted."
            )
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[CoreDescriptionSourceRule, ...]:
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
            version_id=SOURCE_VERSION, source_date=date(2026, 11, 3)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(
                    package_id=package_id, document_id="core-descriptions"
                ),
                title="Reviewed complete maintained App-data Core descriptions",
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
