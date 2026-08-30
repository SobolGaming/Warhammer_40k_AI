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
    RuleEvidenceRecord,
    RuleSourcePackage,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    EXPECTED_OBSERVED_AT,
    EXPECTED_PACKAGE_HASH,
    EXPECTED_RULE_IDENTITIES,
    EXPECTED_SOURCE_URL,
    CoreMovementPhaseSourceArtifactError,
    CoreMovementPhaseSourcePackageArtifact,
    CoreMovementPhaseSourceRuleArtifact,
    core_movement_phase_source_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"
EXPECTED_ARTIFACT_SHA256: Final = "f3e378e933f70c8b4b579acdd7d46a5c8ec519ee3fbfb5efda1611edc747cff2"


def _load_artifact() -> CoreMovementPhaseSourcePackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source artifact could not be loaded."
        ) from exc
    validate_core_movement_phase_source_artifact_bytes(raw)
    return core_movement_phase_source_artifact_from_json_bytes(raw)


def validate_core_movement_phase_source_artifact_bytes(raw: bytes) -> None:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source artifact bytes drifted from their reviewed pin."
        )
    core_movement_phase_source_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_URL: Final = EXPECTED_SOURCE_URL
OBSERVED_AT: Final = EXPECTED_OBSERVED_AT
PACKAGE_HASH: Final = EXPECTED_PACKAGE_HASH
SELECTING_MODES_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES["selecting-modes"][0]
FALL_BACK_MOVE_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES["fall-back-move"][0]
MOVE_UNITS_STEP_SOURCE_ID: Final = EXPECTED_RULE_IDENTITIES["move-units-step"][0]
TRANSCRIPTION_SHA256: Final = EXPECTED_RULE_IDENTITIES["move-units-step"][3]


def source_rule_record() -> CoreMovementPhaseSourceRuleArtifact:
    return source_rule_record_by_id("move-units-step")


def source_rule_record_by_id(rule_id: str) -> CoreMovementPhaseSourceRuleArtifact:
    matches = tuple(rule for rule in _ARTIFACT.rules if rule.rule_id == rule_id)
    if len(matches) != 1:
        raise CoreMovementPhaseSourceArtifactError(
            "Movement-phase source rule identity is unknown or duplicated."
        )
    return matches[0]


def source_rule_records() -> tuple[CoreMovementPhaseSourceRuleArtifact, ...]:
    return _ARTIFACT.rules


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(evidence.to_rule_evidence_record() for evidence in _ARTIFACT.evidence)


def source_package() -> RuleSourcePackage:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version=SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=SOURCE_VERSION,
        source_date=date(2026, 8, 30),
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id=_ARTIFACT.source_document.document_id,
    )
    source_catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=_ARTIFACT.source_document.source_title,
                source_texts=tuple(
                    RuleSourceText.from_raw(
                        source_id=rule.source_id,
                        raw_text=rule.source_text,
                    )
                    for rule in _ARTIFACT.rules
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-movement-phase-source-observed-2026-08-30"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id,),
            ),
        ),
    )
    return RuleSourcePackage(
        source_catalog=source_catalog,
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
    )


__all__ = (
    "EXPECTED_ARTIFACT_SHA256",
    "FALL_BACK_MOVE_SOURCE_ID",
    "MOVE_UNITS_STEP_SOURCE_ID",
    "OBSERVED_AT",
    "PACKAGE_HASH",
    "SELECTING_MODES_SOURCE_ID",
    "SOURCE_PACKAGE_ID",
    "SOURCE_URL",
    "SOURCE_VERSION",
    "TRANSCRIPTION_SHA256",
    "CoreMovementPhaseSourceArtifactError",
    "core_movement_phase_source_artifact_from_json_bytes",
    "source_evidence_records",
    "source_package",
    "source_rule_record",
    "source_rule_record_by_id",
    "source_rule_records",
    "validate_core_movement_phase_source_artifact_bytes",
)
