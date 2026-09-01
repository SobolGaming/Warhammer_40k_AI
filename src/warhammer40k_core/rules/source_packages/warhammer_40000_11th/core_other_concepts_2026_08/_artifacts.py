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

ARTIFACT_SCHEMA: Final = "core-v2-other-concepts-source-v1"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-other-concepts"
EXPECTED_SOURCE_VERSION: Final = "40k-app-other-concepts-observed-2026-08-31"
EXPECTED_SOURCE_URL: Final = "https://www.40k.app/rules/06-other-concepts"
EXPECTED_OBSERVED_AT: Final = "2026-08-31T13:01:46-04:00"
EXPECTED_RULE_IDENTITIES: Final = (
    (
        "visibility",
        "gw-11e-core-rules:other-concepts:visibility",
        "06.01",
        "VISIBILITY",
        "eefe89c9c39b6d8560ba274d414567faebfad2aa17f2b84b5745eb714ffd9883",
    ),
    (
        "mortal-wounds",
        "gw-11e-core-rules:other-concepts:mortal-wounds",
        "06.02",
        "MORTAL WOUNDS",
        "9b8eedb42371fc609796c18ede005681d025fba136d3a8b9578f74c5a550d831",
    ),
)
EXPECTED_OBSERVATION_SHA256S: Final = (
    "7c9700d51718a74421b3a992336fef7ed34ba40e77c1f3ad6f70a4c91e2f7a30",
    "cf12c5ecc2b7fdc082246161fcbab2e301df0a1eb8134f4b69175f0884a35a9a",
    "57b9542afdef85452b316c1bf695591d5d66165a01bf2b0a6fc0b9104890516d",
    "faa8f4b08ebb8663e2ae5f84373465d5691b58ca56d67e461b9e81fdea4abc8a",
)
EXPECTED_PACKAGE_HASH: Final = "3e7a13f4483549fda41111147601d4f51fd6f513203ca328143df2eb3fa7335a"


class CoreOtherConceptsSourceArtifactError(ValueError):
    """Raised when the reviewed Other Concepts source artifact is invalid."""


class CoreOtherConceptsSourceDocumentArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    document_id: str
    source_title: str
    source_url: str
    observed_at: str
    project_authority_policy_id: str


class CoreOtherConceptsSourceRuleArtifact(
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


class CoreOtherConceptsEvidenceArtifact(
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


class CoreOtherConceptsSourcePackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_document: CoreOtherConceptsSourceDocumentArtifact
    rules: tuple[CoreOtherConceptsSourceRuleArtifact, ...]
    evidence: tuple[CoreOtherConceptsEvidenceArtifact, ...]
    package_hash: str


def _sha256_payload(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def core_other_concepts_source_artifact_from_json_bytes(
    raw: bytes,
) -> CoreOtherConceptsSourcePackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=CoreOtherConceptsSourcePackageArtifact)
    except msgspec.DecodeError as exc:
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact schema is invalid."
        ) from exc
    if len(artifact.rules) != len(EXPECTED_RULE_IDENTITIES):
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact drifted from its reviewed identity."
        )
    actual_rule_identities = tuple(
        (
            rule.rule_id,
            rule.source_id,
            rule.section_id,
            rule.section_heading,
            rule.transcription_sha256,
        )
        for rule in artifact.rules
    )
    expected_transcriptions = {
        source_id: transcription_sha256
        for _, source_id, _, _, transcription_sha256 in EXPECTED_RULE_IDENTITIES
    }
    if (
        artifact.artifact_schema != ARTIFACT_SCHEMA
        or artifact.source_package_id != EXPECTED_SOURCE_PACKAGE_ID
        or artifact.source_version != EXPECTED_SOURCE_VERSION
        or artifact.source_document.source_url != EXPECTED_SOURCE_URL
        or artifact.source_document.observed_at != EXPECTED_OBSERVED_AT
        or actual_rule_identities != EXPECTED_RULE_IDENTITIES
        or any(
            hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256
            for rule in artifact.rules
        )
        or len(artifact.evidence) != len(EXPECTED_RULE_IDENTITIES) * 2
        or any(
            expected_transcriptions.get(row.rule_source_id) != row.transcription_sha256
            for row in artifact.evidence
        )
        or tuple(row.observation_sha256 for row in artifact.evidence)
        != EXPECTED_OBSERVATION_SHA256S
        or artifact.package_hash != EXPECTED_PACKAGE_HASH
    ):
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact drifted from its reviewed identity."
        )
    decoded_payload: object = json.loads(raw)
    if type(decoded_payload) is not dict:
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact must be an object."
        )
    payload = copy.deepcopy(cast(dict[str, object], decoded_payload))
    payload["package_hash"] = ""
    if _sha256_payload(payload) != artifact.package_hash:
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source artifact package hash is stale."
        )
    try:
        for evidence in artifact.evidence:
            evidence.to_rule_evidence_record()
    except ValueError as exc:
        raise CoreOtherConceptsSourceArtifactError(
            "Other Concepts source evidence is invalid."
        ) from exc
    return artifact


__all__ = (
    "EXPECTED_OBSERVATION_SHA256S",
    "EXPECTED_OBSERVED_AT",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RULE_IDENTITIES",
    "EXPECTED_SOURCE_URL",
    "CoreOtherConceptsSourceArtifactError",
    "CoreOtherConceptsSourcePackageArtifact",
    "CoreOtherConceptsSourceRuleArtifact",
    "core_other_concepts_source_artifact_from_json_bytes",
)
