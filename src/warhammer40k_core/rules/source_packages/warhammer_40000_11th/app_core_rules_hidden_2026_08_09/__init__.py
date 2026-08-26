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
from warhammer40k_core.rules.source_evidence import (
    RuleSourcePackage,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    AppHiddenTranscriptionArtifactError,
    AppHiddenTranscriptionPackageArtifact,
    app_hidden_transcription_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/hidden.json"
EXPECTED_ARTIFACT_SHA256: Final = "a63c25996e95c03f0953fc3841e47228d6d9533cdb4ef34a8e2324bc29d0f902"


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


def validate_hidden_transcription_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise AppHiddenTranscriptionArtifactError(
            "App Hidden transcription artifact bytes drifted from their reviewed pin."
        )
    app_hidden_transcription_artifact_from_json_bytes(raw)


def _build_source_catalog() -> SourceCatalog:
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
            "Project-owner-supplied transcription attributed to the Warhammer 40,000 "
            "App, observed 2026-08-09. That historical transcription remains explicitly "
            "unverified on its own. A separate 40k.app observation on 2026-08-25 matches "
            "the wording and is governed by project source policy "
            "core-rules-source-policy:40k-app-verbatim-official-app-mirror:2026-08-26. "
            "Under that owner-approved policy, the maintained App wording supersedes the "
            "older official Core Rules PDF wording for this rule. 40k.app remains "
            "identified as a non-affiliated hosting provider, not as Games Workshop."
        ),
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=(
                    f"Hidden ({SOURCE_TITLE}; owner transcription observed {OBSERVATION_DATE}; "
                    "matched by project-authoritative 40k.app App mirror)"
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


def source_package() -> RuleSourcePackage:
    evidence_catalog = SourceEvidenceCatalog(
        records=tuple(evidence.to_rule_evidence_record() for evidence in _ARTIFACT.evidence_records)
    )
    return RuleSourcePackage(
        source_catalog=_build_source_catalog(),
        source_evidence_catalog=evidence_catalog,
        evidence_required_source_ids=(RULE_SOURCE_ID,),
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
    "source_package",
    "validate_hidden_transcription_artifact_bytes",
)
