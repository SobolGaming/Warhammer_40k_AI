"""Hash-pinned P12 consolidation source authority."""

from __future__ import annotations

import hashlib
import json
from datetime import date
from typing import Final

import msgspec

from warhammer40k_core.core.ruleset_descriptor import ConsolidationModeKind
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

EXPECTED_ARTIFACT_SHA256: Final = "df45dfddbb5e851346fa355063b9cd92298c0c68f2491c6b312dc594c8ee15a9"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-fight"
SOURCE_VERSION: Final = "maintained-app-mirrors-owner-resolved-v946-2026-09-21"
CONSOLIDATION_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:consolidation-move"
ONGOING_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:ongoing-consolidation-erratum"
STEP_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:consolidate-step"


class FightSourceError(ValueError):
    """The reviewed Fight source identity or provenance has drifted."""


class FightSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class ConsolidationSourceResolution(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    resolution_id: str
    recorded_at: str
    evidence_kind: str
    provider_name: str
    source_platform: str
    source_url: None
    app_version: str
    app_build: None
    locale: None
    capture_sha256: None
    source_id: str
    mirror_observation_sha256: str
    after_moving_text: str
    transcription_sha256: str
    superseded_source_id: str
    supersession_scope: str
    forced_fight_modes: tuple[ConsolidationModeKind, ...]
    observation_sha256: str


class FightSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[FightSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    resolution: ConsolidationSourceResolution
    package_hash: str


def validate_fight_source_artifact_bytes(raw: bytes) -> FightSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise FightSourceError("Fight source artifact bytes drifted from their reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=FightSourceArtifact)
    except msgspec.DecodeError as exc:
        raise FightSourceError("Fight source artifact schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-fight-source-v2"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (CONSOLIDATION_SOURCE_ID, ONGOING_SOURCE_ID, STEP_SOURCE_ID)
    ):
        raise FightSourceError("Fight source artifact identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise FightSourceError("Fight source transcription hash drifted.")
        historical_only = rule.source_id == ONGOING_SOURCE_ID
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status
            != ("not_certified" if historical_only else "executable_engine_runtime")
            or bool(rule.runtime_consumer_ids) == historical_only
        ):
            raise FightSourceError("Fight source execution evidence is incomplete.")
    resolution = artifact.resolution
    observation = msgspec.to_builtins(resolution)
    observation["observation_sha256"] = ""
    digest = hashlib.sha256(
        json.dumps(observation, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    if (
        resolution.app_version != "946"
        or resolution.source_id != CONSOLIDATION_SOURCE_ID
        or resolution.superseded_source_id != ONGOING_SOURCE_ID
        or resolution.forced_fight_modes != (ConsolidationModeKind.ENGAGING,)
        or resolution.observation_sha256 != digest
        or hashlib.sha256(resolution.after_moving_text.encode()).hexdigest()
        != resolution.transcription_sha256
        or resolution.mirror_observation_sha256
        not in {row["observation_sha256"] for row in artifact.evidence}
    ):
        raise FightSourceError("Consolidation v946 source resolution drifted.")
    return artifact


_ARTIFACT: Final = validate_fight_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def consolidation_response_source_id(mode: ConsolidationModeKind | None) -> str | None:
    """Return the source grant, or explicit absence for a mode with no response."""
    return (
        _ARTIFACT.resolution.source_id if mode in _ARTIFACT.resolution.forced_fight_modes else None
    )


def source_resolution() -> ConsolidationSourceResolution:
    return _ARTIFACT.resolution


def source_rules() -> tuple[FightSourceRule, ...]:
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
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 21)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(
                    package_id=package_id, document_id="p12-consolidation"
                ),
                title="Reviewed maintained App-data consolidation",
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
