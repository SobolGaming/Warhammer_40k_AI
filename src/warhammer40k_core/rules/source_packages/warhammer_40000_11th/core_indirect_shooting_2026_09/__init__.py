"""Hash-pinned 10.07 Indirect Shooting policy for P10."""

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

EXPECTED_ARTIFACT_SHA256: Final = "ce825fb4882d3cfe009afa2f49572adb6e464e48ef9082dfe058e26b52bcaf3e"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-indirect-shooting"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-09"
INDIRECT_SHOOTING_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:indirect-shooting"
REMAIN_STATIONARY_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:remain-stationary"


class IndirectShootingSourceError(ValueError):
    """The reviewed Indirect Shooting source identity or provenance has drifted."""


class IndirectShootingSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class IndirectShootingAttackPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    no_visible_rule_id: str
    cover_rule_id: str
    no_hit_rerolls_rule_id: str
    stationary_visible_rule_id: str
    minimum_unmodified_success: int
    stationary_visible_minimum_unmodified_success: int


class IndirectShootingSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[IndirectShootingSourceRule, ...]
    attack_policy: IndirectShootingAttackPolicy
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> IndirectShootingSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise IndirectShootingSourceError(
            "Indirect Shooting source bytes drifted from their reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=IndirectShootingSourceArtifact)
    except msgspec.DecodeError as exc:
        raise IndirectShootingSourceError("Indirect Shooting source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-indirect-shooting-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (INDIRECT_SHOOTING_SOURCE_ID, REMAIN_STATIONARY_SOURCE_ID)
    ):
        raise IndirectShootingSourceError("Indirect Shooting source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise IndirectShootingSourceError(
                "Indirect Shooting source transcription hash drifted."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "partial_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise IndirectShootingSourceError(
                "Indirect Shooting source execution evidence is incomplete."
            )
    policy = artifact.attack_policy
    if (
        policy.source_rule_id != INDIRECT_SHOOTING_SOURCE_ID
        or policy.minimum_unmodified_success != 6
        or policy.stationary_visible_minimum_unmodified_success != 4
        or not all(
            (
                policy.no_visible_rule_id,
                policy.cover_rule_id,
                policy.no_hit_rerolls_rule_id,
                policy.stationary_visible_rule_id,
            )
        )
    ):
        raise IndirectShootingSourceError("Indirect Shooting attack descriptor drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash
ATTACK_POLICY: Final = _ARTIFACT.attack_policy


def source_rules() -> tuple[IndirectShootingSourceRule, ...]:
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
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 9)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p10"),
                title="Reviewed maintained App-data Indirect Shooting",
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
