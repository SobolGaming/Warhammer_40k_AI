"""Hash-pinned reviewed v931 FAQ: incoming Damage-to-0 applies after saves."""

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

EXPECTED_ARTIFACT_SHA256: Final = "e3928ede0f5a5cad6fa01cbd0237b7f55d28a7ec68449df4b54887bb5c6ceed1"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-failed-save-damage-timing"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-18"
FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:damage-to-0-after-saves-faq"


class FailedSaveDamageTimingSourceError(ValueError):
    """Reviewed failed-save Damage-to-0 source bytes, schema or provenance drifted."""


class FailedSaveDamageTimingPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    applies_after_saving_throw: bool
    applies_before_saving_throw: bool
    replacement_damage: int


class FailedSaveDamageTimingSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class FailedSaveDamageTimingSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[FailedSaveDamageTimingSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str
    timing_policy: FailedSaveDamageTimingPolicy


def validate_source_artifact_bytes(raw: bytes) -> FailedSaveDamageTimingSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise FailedSaveDamageTimingSourceError(
            "Failed-save Damage-to-0 source differs from its reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=FailedSaveDamageTimingSourceArtifact)
    except msgspec.DecodeError as exc:
        raise FailedSaveDamageTimingSourceError(
            "Failed-save Damage-to-0 source schema is invalid."
        ) from exc
    if (
        artifact.artifact_schema != "core-v2-core-failed-save-damage-timing-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID,)
    ):
        raise FailedSaveDamageTimingSourceError("Failed-save Damage-to-0 source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise FailedSaveDamageTimingSourceError(
                "Failed-save Damage-to-0 transcription hash drifted."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise FailedSaveDamageTimingSourceError(
                "Failed-save Damage-to-0 execution evidence is incomplete."
            )
    policy = artifact.timing_policy
    if (
        policy.source_rule_id != FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID
        or policy.applies_after_saving_throw is not True
        or policy.applies_before_saving_throw is not False
        or policy.replacement_damage != 0
    ):
        raise FailedSaveDamageTimingSourceError("Failed-save Damage-to-0 timing policy drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[FailedSaveDamageTimingSourceRule, ...]:
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
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 18)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p05d"),
                title="Reviewed maintained App-data v931 Damage-to-0 after saves FAQ",
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
        evidence_required_source_ids=(FAILED_SAVE_DAMAGE_TO_ZERO_SOURCE_ID,),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


TIMING_POLICY: Final = _ARTIFACT.timing_policy
