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

ARTIFACT_SCHEMA: Final = "core-v2-movement-phase-source-v2"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-core-movement-phase"
EXPECTED_SOURCE_VERSION: Final = "40k-app-movement-phase-observed-2026-08-30"
EXPECTED_SOURCE_URL: Final = "https://www.40k.app/rules/09-movement-phase"
EXPECTED_OBSERVED_AT: Final = "2026-08-30T13:55:17-04:00"
EXPECTED_RULE_IDENTITIES: Final = {
    "move-units-step": (
        "gw-11e-core-rules:movement-phase:move-units-step",
        "09.02",
        "MOVE UNITS STEP",
        "6ea310aedead79971d092f9ae035b0c0b79499bcc656e3899a5546ba6234c54f",
    ),
    "selecting-modes": (
        "gw-11e-core-rules:movement-phase:selecting-modes",
        "09.02.02",
        "SELECTING MODES",
        "094c4bf218bd4c900864ee622364987378851fc06f23610ca95bd6574ee3c2d6",
    ),
    "fall-back-move": (
        "gw-11e-core-rules:movement-phase:fall-back-move",
        "09.07",
        "FALL-BACK MOVE",
        "2f9a2b3a35e8ca0f2d76a43b788c93b9feccaa66f2bba19a8b0ce348d401db0b",
    ),
}
EXPECTED_OBSERVATION_SHA256S: Final = (
    "cc1d33663295747bf678e49ed908e9d23e98874f076fb2cadfe37133aef7ad13",
    "fe123e0660e231a31e550414e2289ee66922b20312e055c69f077ab186e21800",
    "d573029a847de5780c46b2f4047b9057ed71c6258f27f9c16690ca7e529f7d7a",
    "e5c209da27f60c11654788ed26c561e63374791fb345a032f3ce9a4620838db0",
    "10a4ebcba3fb3c33df9e32ac9917d0ba0a2c7b2048cc9767c60ee587c909bd20",
    "97d7323f54195e968c0cff8e7c8434ce5b5f8fe9dca4be3dc558359b3d1e9d23",
)
EXPECTED_PACKAGE_HASH: Final = "0aacec8d0c56e882c0b03329a202a00512d9ace632d2b5f0e3bb53370e001105"


class CoreMovementPhaseSourceArtifactError(ValueError):
    """Raised when the reviewed movement-phase source artifact is invalid."""


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
    rules: tuple[CoreMovementPhaseSourceRuleArtifact, ...]
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
    actual_rule_identities = {
        rule.rule_id: (
            rule.source_id,
            rule.section_id,
            rule.section_heading,
            rule.transcription_sha256,
        )
        for rule in artifact.rules
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
        or len(artifact.evidence) != 6
        or any(
            row.rule_source_id
            not in {identity[0] for identity in EXPECTED_RULE_IDENTITIES.values()}
            for row in artifact.evidence
        )
        or any(
            row.transcription_sha256
            != next(
                identity[3]
                for identity in EXPECTED_RULE_IDENTITIES.values()
                if identity[0] == row.rule_source_id
            )
            for row in artifact.evidence
        )
        or tuple(row.observation_sha256 for row in artifact.evidence)
        != EXPECTED_OBSERVATION_SHA256S
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
    "EXPECTED_OBSERVATION_SHA256S",
    "EXPECTED_OBSERVED_AT",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_RULE_IDENTITIES",
    "EXPECTED_SOURCE_URL",
    "CoreMovementPhaseSourceArtifactError",
    "CoreMovementPhaseSourcePackageArtifact",
    "CoreMovementPhaseSourceRuleArtifact",
    "core_movement_phase_source_artifact_from_json_bytes",
)
