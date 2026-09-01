from __future__ import annotations

import copy
import hashlib
import json
from typing import Final, cast

import msgspec

from warhammer40k_core.rules.source_evidence import (
    LoadSupportStatus,
    RuleEvidenceAuthority,
    RuleEvidenceKind,
    RuleEvidenceRecord,
    RuleVerificationStatus,
    SemanticExecutionStatus,
)

ARTIFACT_SCHEMA: Final = "core-v2-attached-units-source-v1"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-attached-units"
EXPECTED_SOURCE_VERSION: Final = "40k-app-attached-units-observed-2026-09-01"
EXPECTED_SOURCE_URL: Final = "https://www.40k.app/rules/19-attached-units"
EXPECTED_OBSERVED_AT: Final = "2026-09-01T09:02:35-04:00"
EXPECTED_RULE_IDENTITY: Final = (
    "bodyguard-unit-destroyed",
    "gw-11e-core-rules:attached-units:bodyguard-unit-destroyed",
    "19.01.01",
    "ATTACHED UNITS AFTER THEIR BODYGUARD UNIT IS DESTROYED",
    "cb8ea6a1b9633420c8a2c59989edf8bfd97987ce1847faca6820f08b99931bbe",
)
EXPECTED_OBSERVATION_SHA256S: Final = (
    "29c65f1de8ddfd855323b8d0ef6f99b5ce6d28e322034ca2e68097398e408aec",
    "ee513960052396784786dee07ff736c25c0c120f06e56d6940b020fdf71f2d5d",
)
EXPECTED_PACKAGE_HASH: Final = "3f6e0c6b6c3b9a96d19967e2ef5c8ab0429fd7fc8b025304b84e3dc5cb243570"


class CoreAttachedUnitsSourceArtifactError(ValueError):
    """Raised when the reviewed Attached Units source artifact is invalid."""


class CoreAttachedUnitsSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_url: str
    observed_at: str
    project_authority_policy_id: str


class CoreAttachedUnitsSourceRuleArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    rule_id: str
    source_id: str
    section_id: str
    section_heading: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class CoreAttachedUnitsEvidenceArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    evidence_id: str
    rule_source_id: str
    evidence_kind: RuleEvidenceKind
    authority: RuleEvidenceAuthority
    project_authority_policy_id: str | None
    review_audit_id: str | None
    review_audit_row_id: str | None
    review_audit_source_observation_sha256: str | None
    provider_name: str
    source_title: str
    source_platform: str
    source_url: str | None
    observed_at: str | None
    app_version: str | None
    app_build: str | None
    capture_artifact_path: str | None
    capture_sha256: str | None
    transcription_sha256: str
    official_corroborating_source_ids: tuple[str, ...]
    verification_status: RuleVerificationStatus
    provider_non_affiliation_recorded: bool
    observation_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]

    def to_rule_evidence_record(self) -> RuleEvidenceRecord:
        return RuleEvidenceRecord(
            evidence_id=self.evidence_id,
            rule_source_id=self.rule_source_id,
            evidence_kind=self.evidence_kind,
            authority=self.authority,
            project_authority_policy_id=self.project_authority_policy_id,
            review_audit_id=self.review_audit_id,
            review_audit_row_id=self.review_audit_row_id,
            review_audit_source_observation_sha256=self.review_audit_source_observation_sha256,
            provider_name=self.provider_name,
            source_title=self.source_title,
            source_platform=self.source_platform,
            source_url=self.source_url,
            observed_at=self.observed_at,
            app_version=self.app_version,
            app_build=self.app_build,
            capture_artifact_path=self.capture_artifact_path,
            capture_sha256=self.capture_sha256,
            transcription_sha256=self.transcription_sha256,
            official_corroborating_source_ids=self.official_corroborating_source_ids,
            verification_status=self.verification_status,
            provider_non_affiliation_recorded=self.provider_non_affiliation_recorded,
            observation_sha256=self.observation_sha256,
            load_support_status=self.load_support_status,
            semantic_execution_status=self.semantic_execution_status,
            runtime_consumer_ids=self.runtime_consumer_ids,
        )


class CoreAttachedUnitsSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreAttachedUnitsSourceDocumentArtifact
    rules: tuple[CoreAttachedUnitsSourceRuleArtifact, ...]
    evidence: tuple[CoreAttachedUnitsEvidenceArtifact, ...]
    package_hash: str


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def core_attached_units_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreAttachedUnitsSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreAttachedUnitsSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact schema is invalid."
        ) from exc
    if len(artifact.rules) != 1:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact drifted from its reviewed identity."
        )
    rule = artifact.rules[0]
    actual_identity = (
        rule.rule_id,
        rule.source_id,
        rule.section_id,
        rule.section_heading,
        rule.transcription_sha256,
    )
    if (
        artifact.artifact_schema != ARTIFACT_SCHEMA
        or artifact.source_package_id != EXPECTED_SOURCE_PACKAGE_ID
        or artifact.source_version != EXPECTED_SOURCE_VERSION
        or artifact.source_document.source_url != EXPECTED_SOURCE_URL
        or artifact.source_document.observed_at != EXPECTED_OBSERVED_AT
        or actual_identity != EXPECTED_RULE_IDENTITY
        or hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256
        or len(artifact.evidence) != 2
        or any(
            evidence.rule_source_id != rule.source_id
            or evidence.transcription_sha256 != rule.transcription_sha256
            for evidence in artifact.evidence
        )
        or tuple(evidence.observation_sha256 for evidence in artifact.evidence)
        != EXPECTED_OBSERVATION_SHA256S
        or artifact.package_hash != EXPECTED_PACKAGE_HASH
    ):
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact drifted from its reviewed identity."
        )
    decoded_payload: object = json.loads(raw)
    if type(decoded_payload) is not dict:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact must be an object."
        )
    payload = copy.deepcopy(cast(dict[str, object], decoded_payload))
    payload["package_hash"] = ""
    if _sha256_payload(payload) != artifact.package_hash:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source artifact package hash is stale."
        )
    try:
        for evidence in artifact.evidence:
            evidence.to_rule_evidence_record()
    except ValueError as exc:
        raise CoreAttachedUnitsSourceArtifactError(
            "Attached Units source evidence is invalid."
        ) from exc
    return artifact


__all__ = (
    "EXPECTED_OBSERVATION_SHA256S",
    "EXPECTED_OBSERVED_AT",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RULE_IDENTITY",
    "EXPECTED_SOURCE_URL",
    "CoreAttachedUnitsSourceArtifactError",
    "CoreAttachedUnitsSourcePackageArtifact",
    "CoreAttachedUnitsSourceRuleArtifact",
    "core_attached_units_source_artifact_from_json_bytes",
)
