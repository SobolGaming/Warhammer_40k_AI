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
EXPECTED_SOURCE_VERSION: Final = "reviewed-transports-observed-2026-09-03"
EXPECTED_DOCUMENT_IDENTITIES: Final = (
    (
        "40k-app-transports-2026-09-01",
        "https://www.40k.app/rules/18-transports",
        "2026-09-01T18:46:11-04:00",
        None,
        ("gw-11e-core-rules:transports:emergency-disembark-move",),
    ),
    (
        "game-datamissions-core-rules-data-931",
        "https://game-datamissions.com/11th/rules/changelog",
        "2026-09-02T12:30:09-04:00",
        "931",
        (
            "gw-11e-core-rules:transports:assault-disembark-move",
            "gw-11e-core-rules:transports:shock-disembark-move",
        ),
    ),
)
EXPECTED_RULE_IDENTITIES: Final = (
    (
        "emergency-disembark-move",
        "gw-11e-core-rules:transports:emergency-disembark-move",
        "18.05",
        "EMERGENCY DISEMBARK MOVE",
        "3d2ae5c7c61267b25d42f7139353d31528f5b4f7c66acbc63c64b596f3f8eb56",
    ),
    (
        "assault-disembark-move",
        "gw-11e-core-rules:transports:assault-disembark-move",
        "18.06",
        "ASSAULT DISEMBARK MOVE",
        "93b5d311d7bce309e94f93c6b501a6980a820505786f59e0cb2bbfc6e53e4bee",
    ),
    (
        "shock-disembark-move",
        "gw-11e-core-rules:transports:shock-disembark-move",
        "18.07",
        "SHOCK DISEMBARK MOVE",
        "d8dae354aabcc30c582b66e70939dd67c010055637f86923292c0c76ffe7252c",
    ),
)
EXPECTED_OBSERVATION_SHA256S: Final = (
    "41830aeaa0b2d711ad77a31e60092acf543b4d31b24c6cd286e1818948237b63",
    "645e8e96af35d4aefe38c755c2ce6b72579d925865ace9e5b16e5b58158c5b98",
    "21dde0c665b4a09fecc0ddc6f4e09ee252b6a3b27af1779f858aa8a4fcfc0dae",
    "afa51f8bbba769ecf4c34cf7acfa62c02addc247f11b42d830cc91bbded0066b",
    "3c866ae008d4085ac1c09d21b794221bb72eb18d62a9dd7415668733bfb722cc",
    "cc8a85d4bcd88e7eb0ec3d9228721e5c1e4d1e4287b57d02a18ae3e8b3523efe",
)
EXPECTED_PACKAGE_HASH: Final = "62c267ae792834ddd371541f177e78056492656db964cfdcaaa1a3de6581472f"


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
    app_version: str | None
    project_authority_policy_id: str
    rule_source_ids: tuple[str, ...]


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
    source_documents: tuple[CoreTransportsSourceDocumentArtifact, ...]
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
    if len(artifact.rules) != 3 or len(artifact.source_documents) != 2:
        raise CoreTransportsSourceArtifactError(
            "Transports source artifact drifted from its reviewed identity."
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
    actual_document_identities = tuple(
        (
            document.document_id,
            document.source_url,
            document.observed_at,
            document.app_version,
            document.rule_source_ids,
        )
        for document in artifact.source_documents
    )
    rule_by_source_id = {rule.source_id: rule for rule in artifact.rules}
    if (
        artifact.artifact_schema != ARTIFACT_SCHEMA
        or artifact.source_package_id != EXPECTED_SOURCE_PACKAGE_ID
        or artifact.source_version != EXPECTED_SOURCE_VERSION
        or actual_document_identities != EXPECTED_DOCUMENT_IDENTITIES
        or actual_rule_identities != EXPECTED_RULE_IDENTITIES
        or any(
            hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256
            for rule in artifact.rules
        )
        or tuple(
            source_id
            for document in artifact.source_documents
            for source_id in document.rule_source_ids
        )
        != tuple(rule.source_id for rule in artifact.rules)
        or len(artifact.evidence) != 6
        or any(
            evidence.rule_source_id not in rule_by_source_id
            or evidence.transcription_sha256
            != rule_by_source_id[evidence.rule_source_id].transcription_sha256
            for evidence in artifact.evidence
        )
        or any(
            len(
                tuple(
                    evidence
                    for evidence in artifact.evidence
                    if evidence.rule_source_id == rule.source_id
                )
            )
            != 2
            for rule in artifact.rules
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
    "EXPECTED_DOCUMENT_IDENTITIES",
    "EXPECTED_OBSERVATION_SHA256S",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RULE_IDENTITIES",
    "CoreTransportsSourceArtifactError",
    "CoreTransportsSourcePackageArtifact",
    "CoreTransportsSourceRuleArtifact",
    "core_transports_source_artifact_from_json_bytes",
)
