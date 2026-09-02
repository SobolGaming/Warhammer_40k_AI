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

ARTIFACT_SCHEMA: Final = "core-v2-transports-source-v1"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-transports"
EXPECTED_SOURCE_VERSION: Final = "40k-app-transports-observed-2026-09-01"
EXPECTED_SOURCE_URL: Final = "https://www.40k.app/rules/18-transports"
EXPECTED_OBSERVED_AT: Final = "2026-09-01T18:46:11-04:00"
EXPECTED_RULE_IDENTITY: Final = (
    "emergency-disembark-move",
    "gw-11e-core-rules:transports:emergency-disembark-move",
    "18.05",
    "EMERGENCY DISEMBARK MOVE",
    "3d2ae5c7c61267b25d42f7139353d31528f5b4f7c66acbc63c64b596f3f8eb56",
)
EXPECTED_OBSERVATION_SHA256S: Final = (
    "41830aeaa0b2d711ad77a31e60092acf543b4d31b24c6cd286e1818948237b63",
    "645e8e96af35d4aefe38c755c2ce6b72579d925865ace9e5b16e5b58158c5b98",
)
EXPECTED_PACKAGE_HASH: Final = "11ef8c6081238b8271effc171f9cd90cd85f1ec0028589db833b517bbe3fede0"


class CoreTransportsSourceArtifactError(ValueError):
    """Raised when the reviewed Transports source artifact is invalid."""


class CoreTransportsSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_url: str
    observed_at: str
    project_authority_policy_id: str


class CoreTransportsSourceRuleArtifact(
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


class CoreTransportsEvidenceArtifact(
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


class CoreTransportsSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreTransportsSourceDocumentArtifact
    rules: tuple[CoreTransportsSourceRuleArtifact, ...]
    evidence: tuple[CoreTransportsEvidenceArtifact, ...]
    package_hash: str


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def core_transports_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreTransportsSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreTransportsSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreTransportsSourceArtifactError(
            "Transports source artifact schema is invalid."
        ) from exc
    if len(artifact.rules) != 1:
        raise CoreTransportsSourceArtifactError(
            "Transports source artifact drifted from its reviewed identity."
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
        raise CoreTransportsSourceArtifactError(
            "Transports source artifact drifted from its reviewed identity."
        )
    decoded_payload: object = json.loads(raw)
    if type(decoded_payload) is not dict:
        raise CoreTransportsSourceArtifactError("Transports source artifact must be an object.")
    payload = copy.deepcopy(cast(dict[str, object], decoded_payload))
    payload["package_hash"] = ""
    if _sha256_payload(payload) != artifact.package_hash:
        raise CoreTransportsSourceArtifactError("Transports source artifact package hash is stale.")
    try:
        for evidence in artifact.evidence:
            evidence.to_rule_evidence_record()
    except ValueError as exc:
        raise CoreTransportsSourceArtifactError("Transports source evidence is invalid.") from exc
    return artifact


__all__ = (
    "EXPECTED_OBSERVATION_SHA256S",
    "EXPECTED_OBSERVED_AT",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RULE_IDENTITY",
    "EXPECTED_SOURCE_URL",
    "CoreTransportsSourceArtifactError",
    "CoreTransportsSourcePackageArtifact",
    "CoreTransportsSourceRuleArtifact",
    "core_transports_source_artifact_from_json_bytes",
)
