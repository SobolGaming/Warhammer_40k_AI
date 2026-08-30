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

ARTIFACT_SCHEMA: Final = "core-v2-movement-phase-source-v1"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-movement-phase"
EXPECTED_SOURCE_VERSION: Final = "40k-app-move-units-observed-2026-08-29"
EXPECTED_SOURCE_URL: Final = "https://www.40k.app/rules/09-movement-phase"
EXPECTED_OBSERVED_AT: Final = "2026-08-29T20:56:52-04:00"
EXPECTED_RULE_SOURCE_ID: Final = "gw-11e-core-rules:movement-phase:move-units-step"
EXPECTED_TRANSCRIPTION_SHA256: Final = (
    "6ea310aedead79971d092f9ae035b0c0b79499bcc656e3899a5546ba6234c54f"
)
EXPECTED_REVIEW_OBSERVATION_SHA256: Final = (
    "5aa9978655e58af7c7d41cabd57c47d3bc8dc0daa884e2d2243206bd68f17afc"
)
EXPECTED_MIRROR_OBSERVATION_SHA256: Final = (
    "a881b7623692015b3c92772f7fd508da782f832a225a922226735c9ed3e8fbc9"
)
EXPECTED_PACKAGE_HASH: Final = "199be38f35856eddfb6f72395ffff7448f48be1b099db784788a8b64f0e97058"


class CoreMovementPhaseSourceArtifactError(ValueError):
    """Raised when the reviewed 09.02 source artifact is invalid."""


class CoreMovementPhaseSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_url: str
    observed_at: str
    project_authority_policy_id: str


class CoreMovementPhaseSourceRuleArtifact(
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


class CoreMovementPhaseEvidenceArtifact(
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
            review_audit_source_observation_sha256=(self.review_audit_source_observation_sha256),
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


class CoreMovementPhaseSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreMovementPhaseSourceDocumentArtifact
    rule: CoreMovementPhaseSourceRuleArtifact
    evidence: tuple[CoreMovementPhaseEvidenceArtifact, ...]
    package_hash: str


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def core_movement_phase_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreMovementPhaseSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreMovementPhaseSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source artifact schema is invalid."
        ) from exc
    if (
        artifact.artifact_schema != ARTIFACT_SCHEMA
        or artifact.source_package_id != EXPECTED_SOURCE_PACKAGE_ID
        or artifact.source_version != EXPECTED_SOURCE_VERSION
        or artifact.source_document.source_url != EXPECTED_SOURCE_URL
        or artifact.source_document.observed_at != EXPECTED_OBSERVED_AT
        or artifact.rule.rule_id != "move-units-step"
        or artifact.rule.source_id != EXPECTED_RULE_SOURCE_ID
        or artifact.rule.section_id != "09.02"
        or artifact.rule.section_heading != "MOVE UNITS STEP"
        or artifact.rule.transcription_sha256 != EXPECTED_TRANSCRIPTION_SHA256
        or hashlib.sha256(artifact.rule.source_text.encode()).hexdigest()
        != EXPECTED_TRANSCRIPTION_SHA256
        or len(artifact.evidence) != 2
        or any(row.rule_source_id != EXPECTED_RULE_SOURCE_ID for row in artifact.evidence)
        or any(
            row.transcription_sha256 != EXPECTED_TRANSCRIPTION_SHA256 for row in artifact.evidence
        )
        or tuple(row.observation_sha256 for row in artifact.evidence)
        != (
            EXPECTED_REVIEW_OBSERVATION_SHA256,
            EXPECTED_MIRROR_OBSERVATION_SHA256,
        )
        or artifact.package_hash != EXPECTED_PACKAGE_HASH
    ):
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source artifact drifted from its reviewed identity."
        )
    decoded_payload: object = json.loads(raw)
    if type(decoded_payload) is not dict:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source artifact must be an object."
        )
    payload = copy.deepcopy(cast(dict[str, object], decoded_payload))
    payload["package_hash"] = ""
    if _sha256_payload(payload) != artifact.package_hash:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source artifact package hash is stale."
        )
    try:
        for evidence in artifact.evidence:
            evidence.to_rule_evidence_record()
    except ValueError as exc:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source evidence is invalid."
        ) from exc
    return artifact


__all__ = (
    "EXPECTED_MIRROR_OBSERVATION_SHA256",
    "EXPECTED_OBSERVED_AT",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_REVIEW_OBSERVATION_SHA256",
    "EXPECTED_RULE_SOURCE_ID",
    "EXPECTED_SOURCE_URL",
    "EXPECTED_TRANSCRIPTION_SHA256",
    "CoreMovementPhaseSourceArtifactError",
    "CoreMovementPhaseSourcePackageArtifact",
    "CoreMovementPhaseSourceRuleArtifact",
    "core_movement_phase_source_artifact_from_json_bytes",
)
