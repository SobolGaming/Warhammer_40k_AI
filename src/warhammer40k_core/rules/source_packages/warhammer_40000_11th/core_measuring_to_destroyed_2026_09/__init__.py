"""Hash-pinned reviewed 05.04.06 Measuring To A Destroyed Model Or Unit source."""

from __future__ import annotations

import hashlib
from datetime import date
from typing import Final

import msgspec

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId, SourceDocumentId
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_evidence import (
    CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    LoadSupportStatus,
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RuleSourcePackage,
    SemanticExecutionStatus,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

EXPECTED_ARTIFACT_SHA256: Final = "ca8c2ea2b8dbae29b046cfc8c1d11062e773b8b83e64c4a855c6cd0ad9a498c7"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-measuring-to-destroyed"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-18"
MEASURING_TO_DESTROYED_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:measuring-to-destroyed"


class MeasuringToDestroyedSourceError(ValueError):
    """Reviewed measuring-to-destroyed source bytes, schema or provenance drifted."""


class MeasuringToDestroyedPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    uses_former_footprint: bool
    destroyed_unit_resolves_to_last_destroyed_model: bool
    grants_living_battlefield_authority: bool
    uses_catalog_geometry_for_base_or_hull: bool


class MeasuringToDestroyedSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class MeasuringToDestroyedSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[MeasuringToDestroyedSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str
    measurement_policy: MeasuringToDestroyedPolicy


def validate_source_artifact_bytes(raw: bytes) -> MeasuringToDestroyedSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise MeasuringToDestroyedSourceError(
            "Measuring-to-destroyed source differs from its reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=MeasuringToDestroyedSourceArtifact)
    except msgspec.DecodeError as exc:
        raise MeasuringToDestroyedSourceError(
            "Measuring-to-destroyed source schema is invalid."
        ) from exc
    if (
        artifact.artifact_schema != "core-v2-core-measuring-to-destroyed-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules) != (MEASURING_TO_DESTROYED_SOURCE_ID,)
    ):
        raise MeasuringToDestroyedSourceError("Measuring-to-destroyed source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise MeasuringToDestroyedSourceError(
                "Measuring-to-destroyed transcription hash drifted."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise MeasuringToDestroyedSourceError(
                "Measuring-to-destroyed execution evidence is incomplete."
            )
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[MeasuringToDestroyedSourceRule, ...]:
    return _ARTIFACT.rules


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(RuleEvidenceRecord.from_payload(row) for row in _ARTIFACT.evidence)


def source_catalog() -> SourceCatalog:
    package_id = DataPackageId(
        namespace="games-workshop", package_name=SOURCE_PACKAGE_ID, version=SOURCE_VERSION
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=CatalogVersion.dated(
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 18)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p05c"),
                title="Reviewed maintained App-data Measuring To A Destroyed Model Or Unit",
                source_texts=tuple(
                    RuleSourceText.from_raw(
                        source_id=rule.source_id,
                        raw_text=rule.source_text,
                        objective_scope=ObjectiveRuleScope.CORE_RULES,
                    )
                    for rule in _ARTIFACT.rules
                ),
            ),
        ),
        ruleset_bundles=(),
    )


def _build_source_package() -> RuleSourcePackage:
    return RuleSourcePackage(
        source_catalog=source_catalog(),
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=(MEASURING_TO_DESTROYED_SOURCE_ID,),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


MEASUREMENT_POLICY: Final = _ARTIFACT.measurement_policy
