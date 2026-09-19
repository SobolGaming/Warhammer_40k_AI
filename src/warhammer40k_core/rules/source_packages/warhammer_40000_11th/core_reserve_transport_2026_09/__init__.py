"""Hash-pinned reviewed 18.04.01 Rapid Disembark inheritance source."""

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

EXPECTED_ARTIFACT_SHA256: Final = "425ec8d96ee5bab05cf3852cb6762c38c2ecc197c94c19c93a1cf507dfe31c4c"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-reserve-transport"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-19"
RESERVE_TRANSPORT_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:reserve-transport"


class ReserveTransportSourceError(ValueError):
    """Reviewed Reserve Transport source bytes, schema or provenance drifted."""


class ReserveTransportPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    inherits_ingress_placement: bool
    cargo_remains_embarked: bool


class ReserveTransportSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class ReserveTransportSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[ReserveTransportSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str
    reserve_transport_policy: ReserveTransportPolicy


def validate_source_artifact_bytes(raw: bytes) -> ReserveTransportSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise ReserveTransportSourceError("Reserve Transport source differs from its reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=ReserveTransportSourceArtifact)
    except msgspec.DecodeError as exc:
        raise ReserveTransportSourceError("Reserve Transport source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-reserve-transport-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (
            RESERVE_TRANSPORT_SOURCE_ID,
            f"{SOURCE_PACKAGE_ID}:placing-reserves",
            f"{SOURCE_PACKAGE_ID}:ingress",
        )
    ):
        raise ReserveTransportSourceError("Reserve Transport source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise ReserveTransportSourceError("Reserve Transport transcription hash drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status
            != (
                "executable_engine_runtime"
                if rule.source_id == RESERVE_TRANSPORT_SOURCE_ID
                else "partial_engine_runtime"
            )
            or not rule.runtime_consumer_ids
        ):
            raise ReserveTransportSourceError("Reserve Transport execution evidence is incomplete.")
    policy = artifact.reserve_transport_policy
    if (
        policy.source_rule_id != RESERVE_TRANSPORT_SOURCE_ID
        or policy.inherits_ingress_placement is not True
        or policy.cargo_remains_embarked is not True
    ):
        raise ReserveTransportSourceError("Reserve Transport policy drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[ReserveTransportSourceRule, ...]:
    return _ARTIFACT.rules


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(RuleEvidenceRecord.from_payload(row) for row in _ARTIFACT.evidence)


def source_catalog() -> SourceCatalog:
    package_id = DataPackageId(
        namespace="games-workshop", package_name=SOURCE_PACKAGE_ID, version=SOURCE_VERSION
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=CatalogVersion.dated(
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 19)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p20"),
                title="Reviewed maintained App-data 18.04.01 Rapid Disembark inheritance",
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


def _build_source_package() -> RuleSourcePackage:
    return RuleSourcePackage(
        source_catalog=source_catalog(),
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


RESERVE_TRANSPORT_POLICY: Final = _ARTIFACT.reserve_transport_policy
