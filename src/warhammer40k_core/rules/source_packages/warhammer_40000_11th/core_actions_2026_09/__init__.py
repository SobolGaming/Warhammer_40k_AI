"""Hash-pinned 16.01 Action restriction policy for P16."""

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

EXPECTED_ARTIFACT_SHA256: Final = "b9027d83c608961b9cde5baae546bbb97336235b8b9a6297b182cf0e93fad8aa"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-actions"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-09"
ACTION_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:performing-actions"
SOURCE_IDS: Final = tuple(
    f"{SOURCE_PACKAGE_ID}:{slug}"
    for slug in (
        "performing-actions",
        "normal-shooting",
        "assault-shooting",
        "close-quarters-shooting",
    )
)


class ActionRestrictionSourceError(ValueError):
    """The reviewed Action restriction source identity or provenance has drifted."""


class ActionRestrictionSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class ActionRestrictionPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    action_source_rule_id: str
    after_shooting_descriptor_id: str
    after_shooting_source_rule_ids: tuple[str, ...]
    action_expiration: str
    shooting_expiration: str
    shooting_exempt_keyword: str


class ActionRestrictionSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[ActionRestrictionSourceRule, ...]
    restriction_policy: ActionRestrictionPolicy
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> ActionRestrictionSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise ActionRestrictionSourceError(
            "Action restriction source bytes drifted from their reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=ActionRestrictionSourceArtifact)
    except msgspec.DecodeError as exc:
        raise ActionRestrictionSourceError("Action restriction source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-actions-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules) != SOURCE_IDS
    ):
        raise ActionRestrictionSourceError("Action restriction source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise ActionRestrictionSourceError(
                "Action restriction source transcription hash drifted."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "partial_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise ActionRestrictionSourceError(
                "Action restriction source execution evidence is incomplete."
            )
    policy = artifact.restriction_policy
    if (
        policy.action_source_rule_id != ACTION_SOURCE_ID
        or policy.after_shooting_descriptor_id != "core:after-shooting-action-restriction"
        or policy.after_shooting_source_rule_ids
        != (
            *SOURCE_IDS[1:],
            "gw-11e-core-indirect-shooting:indirect-shooting",
            "gw-11e-core-stratagems:rule:snap-shooting",
        )
        or policy.action_expiration != "end_turn"
        or policy.shooting_expiration != "end_phase"
        or policy.shooting_exempt_keyword != "TITANIC"
    ):
        raise ActionRestrictionSourceError("Action restriction descriptor drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash
RESTRICTION_POLICY: Final = _ARTIFACT.restriction_policy


def source_rules() -> tuple[ActionRestrictionSourceRule, ...]:
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
                document_id=SourceDocumentId(package_id=package_id, document_id="p16"),
                title="Reviewed maintained App-data Action restriction",
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
