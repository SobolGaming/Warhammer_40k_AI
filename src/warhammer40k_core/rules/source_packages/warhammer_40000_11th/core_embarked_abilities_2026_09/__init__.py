"""Hash-pinned 01.02.04 and embarked ability FAQ for P01C."""

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

EXPECTED_ARTIFACT_SHA256: Final = "3102868123dc8f612999dffcc069fad97a1d0ed1bbf6f3e663e39cc97c4d05ff"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-embarked-abilities"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-07"
EMBARKED_ABILITIES_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:embarked-abilities"
OFF_BATTLEFIELD_ABILITY_CONDITIONS_SOURCE_ID: Final = (
    f"{SOURCE_PACKAGE_ID}:off-battlefield-ability-conditions"
)


class EmbarkedAbilitiesSourceError(ValueError):
    """The reviewed Embarked abilities source identity or provenance has drifted."""


class EmbarkedAbilitiesSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class EmbarkedAbilitiesSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[EmbarkedAbilitiesSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> EmbarkedAbilitiesSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EmbarkedAbilitiesSourceError(
            "Embarked abilities source bytes drifted from their reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=EmbarkedAbilitiesSourceArtifact)
    except msgspec.DecodeError as exc:
        raise EmbarkedAbilitiesSourceError("Embarked abilities source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-embarked-abilities-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (EMBARKED_ABILITIES_SOURCE_ID, OFF_BATTLEFIELD_ABILITY_CONDITIONS_SOURCE_ID)
    ):
        raise EmbarkedAbilitiesSourceError("Embarked abilities source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise EmbarkedAbilitiesSourceError(
                "Embarked abilities source transcription hash drifted."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise EmbarkedAbilitiesSourceError(
                "Embarked abilities source execution evidence is incomplete."
            )
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[EmbarkedAbilitiesSourceRule, ...]:
    return _ARTIFACT.rules


def source_evidence_records() -> tuple[RuleEvidenceRecord, ...]:
    return tuple(RuleEvidenceRecord.from_payload(row) for row in _ARTIFACT.evidence)


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


def _build_source_package() -> RuleSourcePackage:
    package_id = DataPackageId(
        namespace="games-workshop", package_name=SOURCE_PACKAGE_ID, version=SOURCE_VERSION
    )
    catalog = SourceCatalog(
        package_id=package_id,
        catalog_version=CatalogVersion.dated(
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 7)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p01c"),
                title="Reviewed maintained App-data embarked abilities",
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
    return RuleSourcePackage(
        source_catalog=catalog,
        source_evidence_catalog=SourceEvidenceCatalog(records=source_evidence_records()),
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()
