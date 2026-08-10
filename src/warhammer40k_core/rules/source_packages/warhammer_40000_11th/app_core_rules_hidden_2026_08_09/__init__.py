from __future__ import annotations

import hashlib
from datetime import date
from typing import Final

from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    DataPackageId,
    RulesetBundle,
    SourceDocumentId,
)
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    AppHiddenRuleArtifact,
    AppHiddenTranscriptionArtifactError,
    AppHiddenTranscriptionPackageArtifact,
    app_hidden_transcription_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/hidden.json"
EXPECTED_ARTIFACT_SHA256: Final = "808b7ad12c18f500efc84a21cdd91d5e7db98d6f8290c6610f1f5377765c5ceb"


def _load_artifact() -> AppHiddenTranscriptionPackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription artifact could not be loaded."
        ) from exc
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription artifact bytes drifted from their reviewed pin."
        )
    return app_hidden_transcription_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_TITLE: Final = _ARTIFACT.source_capture.source_title
SOURCE_PLATFORM: Final = _ARTIFACT.source_capture.source_platform
OBSERVATION_DATE: Final = _ARTIFACT.source_capture.observation_date
RULE_SOURCE_ID: Final = _ARTIFACT.rule.source_id
TRANSCRIPTION_SHA256: Final = _ARTIFACT.rule.transcription_sha256
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def hidden_rule_record() -> AppHiddenRuleArtifact:
    return _ARTIFACT.rule


def hidden_transcription_artifact() -> AppHiddenTranscriptionPackageArtifact:
    return _ARTIFACT


def validate_hidden_transcription_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription artifact bytes drifted from their reviewed pin."
        )
    app_hidden_transcription_artifact_from_json_bytes(raw)


def source_catalog() -> SourceCatalog:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version="observed-2026-08-09",
    )
    catalog_version = CatalogVersion.dated(
        version_id="observed-2026-08-09",
        source_date=date.fromisoformat(OBSERVATION_DATE),
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id="warhammer-40000-app-hidden-transcription-observed-2026-08-09",
    )
    provenance_text = RuleSourceText.from_raw(
        source_id=f"{SOURCE_PACKAGE_ID}:manifest:provenance",
        raw_text=(
            "Project-owner-supplied official Warhammer 40,000 App transcription, "
            "observed 2026-08-09. The App version, source URL, screenshot, and source "
            "binary were not supplied, so no upstream artifact hash is claimed. The "
            "later App wording supersedes the terrain-area feature eligibility in "
            "Warhammer 40,000 11th Edition Core Rules section 13.09 Hidden."
        ),
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=(
                    f"{SOURCE_TITLE} (project-owner-supplied official App transcription; "
                    f"observed {OBSERVATION_DATE}; App version unavailable)"
                ),
                source_texts=(
                    provenance_text,
                    RuleSourceText.from_raw(
                        source_id=RULE_SOURCE_ID,
                        raw_text=_ARTIFACT.rule.source_text,
                    ),
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-app-hidden-observed-2026-08-09"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id,),
            ),
        ),
    )


__all__ = (
    "EXPECTED_ARTIFACT_SHA256",
    "OBSERVATION_DATE",
    "PACKAGE_HASH",
    "RULE_SOURCE_ID",
    "SOURCE_PACKAGE_ID",
    "SOURCE_PLATFORM",
    "SOURCE_TITLE",
    "TRANSCRIPTION_SHA256",
    "AppHiddenTranscriptionArtifactError",
    "app_hidden_transcription_artifact_from_json_bytes",
    "hidden_rule_record",
    "hidden_transcription_artifact",
    "source_catalog",
    "validate_hidden_transcription_artifact_bytes",
)
