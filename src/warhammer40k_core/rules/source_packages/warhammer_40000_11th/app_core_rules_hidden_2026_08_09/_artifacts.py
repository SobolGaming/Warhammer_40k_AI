from __future__ import annotations

import hashlib
import json
from typing import Final

import msgspec

from warhammer40k_core.rules.source_evidence import (
    LoadSupportStatus,
    RuleEvidenceAuthority,
    RuleEvidenceError,
    RuleEvidenceKind,
    RuleEvidenceRecord,
    RuleVerificationStatus,
    SemanticExecutionStatus,
)

ARTIFACT_SCHEMA: Final = "core-v2-warhammer-40000-app-hidden-transcription-v4"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-app-core-rules-hidden-transcription-observed-2026-08-09"
EXPECTED_TRANSCRIPTION_SHA256: Final = (
    "f296139496b5385347ec6c91bf2b898b9ac7ead996ae4f345cc2122002cf769e"
)
PROJECT_AUTHORITY_POLICY_ID: Final = (
    "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26"
)
EXPECTED_RUNTIME_CONSUMERS: Final = (
    "warhammer40k_core.engine.shooting_targets:unit_has_line_of_sight_to_target",
    "warhammer40k_core.engine.terrain_hidden:terrain_hidden_model_ids",
)
EXPECTED_PACKAGE_HASH: Final = "b65d4058463a2825b8808d1d7dfff2e82c8c87641f4241bf600e1bb82a866058"


class AppHiddenTranscriptionArtifactError(ValueError):
    """Raised when the App Hidden transcription artifact is invalid."""


class AppSourceCaptureArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    provenance_kind: str
    source_title: str
    source_platform: str
    observation_date: str
    supplied_by: str
    availability: str


class AppHiddenRuleArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    rule_id: str
    source_id: str
    behavior_descriptor: str
    source_text: str
    transcription_sha256: str


class AppHiddenRuleEvidenceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
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


class AppHiddenSourceRelationshipArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    official_pdf_source_package_id: str
    official_pdf_document_id: str
    official_pdf_rule_reference: str
    comparison_scope: str
    relationship_status: str


class AppHiddenTranscriptionPackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_capture: AppSourceCaptureArtifact
    rule: AppHiddenRuleArtifact
    evidence_records: tuple[AppHiddenRuleEvidenceArtifact, ...]
    source_relationship: AppHiddenSourceRelationshipArtifact
    package_hash: str

    def validate(self) -> None:
        if self.artifact_schema != ARTIFACT_SCHEMA:
            raise AppHiddenTranscriptionArtifactError(
                "App Hidden transcription artifact schema is unsupported."
            )
        if self.source_package_id != EXPECTED_SOURCE_PACKAGE_ID:
            raise AppHiddenTranscriptionArtifactError(
                "App Hidden transcription source package identity drifted."
            )
        _validate_source_capture(self.source_capture)
        _validate_rule(self.rule, source_package_id=self.source_package_id)
        _validate_evidence_records(self.evidence_records, rule=self.rule)
        _validate_source_relationship(self.source_relationship)
        _validate_sha256("package_hash", self.package_hash)
        if self.package_hash != app_hidden_transcription_package_hash(self):
            raise AppHiddenTranscriptionArtifactError(
                "App Hidden transcription package hash is stale."
            )
        if self.package_hash != EXPECTED_PACKAGE_HASH:
            raise AppHiddenTranscriptionArtifactError(
                "App Hidden transcription package hash drifted from its reviewed pin."
            )


def app_hidden_transcription_artifact_from_json_bytes(
    raw: bytes,
) -> AppHiddenTranscriptionPackageArtifact:
    try:
        artifact = msgspec.json.decode(raw, type=AppHiddenTranscriptionPackageArtifact)
    except msgspec.DecodeError as exc:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription artifact is invalid."
        ) from exc
    artifact.validate()
    return artifact


def app_hidden_transcription_package_hash(
    artifact: AppHiddenTranscriptionPackageArtifact,
) -> str:
    payload = msgspec.to_builtins(artifact)
    if type(payload) is not dict:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription artifact payload is invalid."
        )
    payload["package_hash"] = ""
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def _validate_source_capture(source: AppSourceCaptureArtifact) -> None:
    if (
        source.provenance_kind,
        source.source_title,
        source.source_platform,
        source.observation_date,
        source.supplied_by,
        source.availability,
    ) != (
        "owner_supplied_app_transcription",
        "Warhammer 40,000 App Core Rules",
        "Warhammer 40,000 App",
        "2026-08-09",
        "project_owner",
        "transcription_only_no_source_url_app_version_or_binary",
    ):
        raise AppHiddenTranscriptionArtifactError("App Hidden transcription provenance drifted.")


def _validate_rule(rule: AppHiddenRuleArtifact, *, source_package_id: str) -> None:
    if (
        rule.rule_id,
        rule.source_id,
        rule.behavior_descriptor,
    ) != (
        "13.09-hidden",
        f"{source_package_id}:rule:13.09-hidden",
        "hidden_applies_in_light_or_dense_terrain_areas",
    ):
        raise AppHiddenTranscriptionArtifactError("App Hidden transcription rule identity drifted.")
    _validate_non_empty_text("source_text", rule.source_text)
    _validate_sha256("transcription_sha256", rule.transcription_sha256)
    if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription source-text hash is stale."
        )
    if rule.transcription_sha256 != EXPECTED_TRANSCRIPTION_SHA256:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription source text drifted from its reviewed pin."
        )


def _validate_evidence_records(
    evidence_records: tuple[AppHiddenRuleEvidenceArtifact, ...],
    *,
    rule: AppHiddenRuleArtifact,
) -> None:
    if type(evidence_records) is not tuple or len(evidence_records) != 2:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden requires owner-transcription and authoritative-mirror evidence."
        )
    records: list[RuleEvidenceRecord] = []
    for evidence in evidence_records:
        try:
            records.append(evidence.to_rule_evidence_record())
        except RuleEvidenceError as exc:
            raise AppHiddenTranscriptionArtifactError(
                "App Hidden transcription evidence is invalid."
            ) from exc
    records_by_kind = {record.evidence_kind: record for record in records}
    if len(records_by_kind) != 2 or set(records_by_kind) != {
        "owner_supplied_app_transcription",
        "third_party_mirror",
    }:
        raise AppHiddenTranscriptionArtifactError("App Hidden evidence-kind inventory drifted.")
    owner = records_by_kind["owner_supplied_app_transcription"]
    if (
        owner.evidence_id,
        owner.rule_source_id,
        owner.authority,
        owner.project_authority_policy_id,
        owner.review_audit_id,
        owner.review_audit_row_id,
        owner.review_audit_source_observation_sha256,
        owner.provider_name,
        owner.source_title,
        owner.source_platform,
        owner.source_url,
        owner.observed_at,
        owner.app_version,
        owner.app_build,
        owner.capture_artifact_path,
        owner.capture_sha256,
        owner.transcription_sha256,
        owner.official_corroborating_source_ids,
        owner.verification_status,
        owner.provider_non_affiliation_recorded,
        owner.load_support_status,
        owner.semantic_execution_status,
        owner.runtime_consumer_ids,
    ) != (
        "project-owner-hidden-transcription-2026-08-09:13.09-hidden",
        rule.source_id,
        "unverified_transcription_only",
        None,
        None,
        None,
        None,
        "Project Owner",
        "Uncaptured transcription attributed to Warhammer 40,000 App Core Rules",
        "Repository",
        None,
        None,
        None,
        None,
        None,
        None,
        rule.transcription_sha256,
        (),
        "unverified",
        False,
        "loaded",
        "executable_engine_runtime",
        EXPECTED_RUNTIME_CONSUMERS,
    ):
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden owner-transcription evidence provenance drifted."
        )
    mirror = records_by_kind["third_party_mirror"]
    if (
        mirror.evidence_id,
        mirror.rule_source_id,
        mirror.authority,
        mirror.project_authority_policy_id,
        mirror.review_audit_id,
        mirror.review_audit_row_id,
        mirror.review_audit_source_observation_sha256,
        mirror.provider_name,
        mirror.source_title,
        mirror.source_platform,
        mirror.source_url,
        mirror.observed_at,
        mirror.transcription_sha256,
        mirror.official_corroborating_source_ids,
        mirror.verification_status,
        mirror.provider_non_affiliation_recorded,
        mirror.load_support_status,
        mirror.semantic_execution_status,
        mirror.runtime_consumer_ids,
    ) != (
        "40k-app-core-rules-2026-08-25:13.09-hidden",
        rule.source_id,
        "project_authoritative_app_mirror",
        PROJECT_AUTHORITY_POLICY_ID,
        "40k-app-core-rules-2026-08-25",
        "finding:hidden-unverified-source-13-09",
        "62d982be96a81f69059f11def8a0ee75e6ae64f2dfd6f7132e4913140e9aaaf4",
        "40k.app",
        "40k.app Core Rules",
        "Web",
        "https://www.40k.app/rules/13-terrain",
        "2026-08-25T00:00:00-04:00",
        rule.transcription_sha256,
        (),
        "authoritative_app_mirror",
        True,
        "loaded",
        "executable_engine_runtime",
        EXPECTED_RUNTIME_CONSUMERS,
    ):
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden authoritative-mirror evidence provenance drifted."
        )


def _validate_source_relationship(source: AppHiddenSourceRelationshipArtifact) -> None:
    if (
        source.official_pdf_source_package_id,
        source.official_pdf_document_id,
        source.official_pdf_rule_reference,
        source.comparison_scope,
        source.relationship_status,
    ) != (
        "gw-11e-core-rules",
        "eng_01-06_warhammer40k_new40k_core_rules",
        "13.09 Hidden",
        "hidden_terrain_area_feature_eligibility",
        "maintained_app_wording_supersedes_pdf_by_project_source_policy",
    ):
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription source relationship drifted."
        )


def _validate_non_empty_text(field_name: str, value: object) -> str:
    if type(value) is not str or not value or value != value.strip():
        raise AppHiddenTranscriptionArtifactError(
            f"App Hidden transcription {field_name} must be non-empty canonical text."
        )
    return value


def _validate_sha256(field_name: str, value: object) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AppHiddenTranscriptionArtifactError(
            f"App Hidden transcription {field_name} must be lowercase SHA-256."
        )
    return value


__all__ = (
    "ARTIFACT_SCHEMA",
    "EXPECTED_PACKAGE_HASH",
    "EXPECTED_SOURCE_PACKAGE_ID",
    "EXPECTED_TRANSCRIPTION_SHA256",
    "AppHiddenRuleArtifact",
    "AppHiddenRuleEvidenceArtifact",
    "AppHiddenSourceRelationshipArtifact",
    "AppHiddenTranscriptionArtifactError",
    "AppHiddenTranscriptionPackageArtifact",
    "AppSourceCaptureArtifact",
    "app_hidden_transcription_artifact_from_json_bytes",
    "app_hidden_transcription_package_hash",
)
