from __future__ import annotations

import hashlib
import json
from typing import Final

import msgspec

ARTIFACT_SCHEMA: Final = "core-v2-warhammer-40000-app-hidden-transcription-v1"
EXPECTED_SOURCE_PACKAGE_ID: Final = "gw-11e-app-core-rules-hidden-transcription-observed-2026-08-09"
EXPECTED_TRANSCRIPTION_SHA256: Final = (
    "f296139496b5385347ec6c91bf2b898b9ac7ead996ae4f345cc2122002cf769e"
)
EXPECTED_PACKAGE_HASH: Final = "12061dc13eda2edeeb1efaaec2725ed0048a306858fbb8a92e9a9d3ac603f984"


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


class AppHiddenSupersessionArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    supersedes_source_package_id: str
    supersedes_document_id: str
    supersedes_rule_reference: str
    supersession_scope: str
    relationship: str


class AppHiddenTranscriptionPackageArtifact(
    msgspec.Struct,
    frozen=True,
    forbid_unknown_fields=True,
):
    artifact_schema: str
    source_package_id: str
    source_capture: AppSourceCaptureArtifact
    rule: AppHiddenRuleArtifact
    supersession: AppHiddenSupersessionArtifact
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
        _validate_supersession(self.supersession)
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
        "project_owner_supplied_official_app_transcription",
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


def _validate_supersession(source: AppHiddenSupersessionArtifact) -> None:
    if (
        source.supersedes_source_package_id,
        source.supersedes_document_id,
        source.supersedes_rule_reference,
        source.supersession_scope,
        source.relationship,
    ) != (
        "gw-11e-core-rules",
        "eng_01-06_warhammer40k_new40k_core_rules",
        "13.09 Hidden",
        "hidden_terrain_area_feature_eligibility",
        "later_official_app_wording_supersedes_older_core_rules_pdf",
    ):
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription supersession provenance drifted."
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
    "AppHiddenSupersessionArtifact",
    "AppHiddenTranscriptionArtifactError",
    "AppHiddenTranscriptionPackageArtifact",
    "AppSourceCaptureArtifact",
    "app_hidden_transcription_artifact_from_json_bytes",
    "app_hidden_transcription_package_hash",
)
