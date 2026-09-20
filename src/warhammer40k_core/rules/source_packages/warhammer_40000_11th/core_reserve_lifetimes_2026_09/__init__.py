"""Hash-pinned reviewed 20.01.02-20.04 reserve lifetimes source."""

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

EXPECTED_ARTIFACT_SHA256: Final = "d22f5ca58b27172445f595ebe4a4763e372162950cb825d48cb7816073c488c1"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-reserve-lifetimes"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-19"
ARRIVAL_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:arrival"


class ReserveLifetimesSourceError(ValueError):
    """Reviewed Reserve lifetimes source bytes, schema or provenance drifted."""


class ReserveLifetimesPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    arrival_source_id: str
    reposition_source_id: str
    cleanup_source_id: str
    ingress_source_id: str
    earliest_arrival_battle_round: int
    destruction_battle_round: int
    movement_lock_expires_at: str


class ReserveLifetimesSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class ReserveLifetimesSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[ReserveLifetimesSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str
    reserve_lifetimes_policy: ReserveLifetimesPolicy


def validate_source_artifact_bytes(raw: bytes) -> ReserveLifetimesSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise ReserveLifetimesSourceError("Reserve lifetimes source differs from its reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=ReserveLifetimesSourceArtifact)
    except msgspec.DecodeError as exc:
        raise ReserveLifetimesSourceError("Reserve lifetimes source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-reserve-lifetimes-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (
            f"{SOURCE_PACKAGE_ID}:final-turn-cleanup",
            f"{SOURCE_PACKAGE_ID}:reposition",
            ARRIVAL_SOURCE_ID,
            f"{SOURCE_PACKAGE_ID}:ingress",
        )
    ):
        raise ReserveLifetimesSourceError("Reserve lifetimes source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise ReserveLifetimesSourceError("Reserve lifetimes transcription hash drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise ReserveLifetimesSourceError("Reserve lifetimes execution evidence is incomplete.")
    policy = artifact.reserve_lifetimes_policy
    if (
        policy.arrival_source_id != ARRIVAL_SOURCE_ID
        or policy.earliest_arrival_battle_round != 2
        or policy.destruction_battle_round != 3
        or policy.movement_lock_expires_at != "next_charge_phase_start"
        or policy.cleanup_source_id != f"{SOURCE_PACKAGE_ID}:final-turn-cleanup"
        or policy.reposition_source_id != f"{SOURCE_PACKAGE_ID}:reposition"
        or policy.ingress_source_id != f"{SOURCE_PACKAGE_ID}:ingress"
    ):
        raise ReserveLifetimesSourceError("Reserve lifetimes policy drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[ReserveLifetimesSourceRule, ...]:
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
            version_id=SOURCE_VERSION, source_date=date(2026, 9, 19)
        ),
        documents=(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id="p20b"),
                title="Reviewed maintained App-data 20.01.02-20.04 reserve lifetimes",
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
        evidence_required_source_ids=tuple(sorted(rule.source_id for rule in _ARTIFACT.rules)),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


RESERVE_LIFETIMES_POLICY: Final = _ARTIFACT.reserve_lifetimes_policy
