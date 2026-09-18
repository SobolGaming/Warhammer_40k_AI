"""Hash-pinned reviewed 18.05 Emergency Disembark placement source."""

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

EXPECTED_ARTIFACT_SHA256: Final = "81fbfdb90b7d747b99d7be582ba7a4c006dadd38fea1ccf2a0dad93f85a80bb4"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-emergency-disembark-placement"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-18"
EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID: Final = (
    f"{SOURCE_PACKAGE_ID}:emergency-disembark-placement"
)


class EmergencyDisembarkPlacementSourceError(ValueError):
    """Reviewed Emergency Disembark placement source bytes, schema or provenance drifted."""


class EmergencyDisembarkPlacementPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    setup_distance_inches: int
    requires_closest_possible: bool
    prefers_unengaged: bool
    allows_engaged_when_unengaged_impossible: bool
    destroys_only_unplaceable_models: bool
    closest_tolerance_inches: float


class EmergencyDisembarkPlacementSourceRule(
    msgspec.Struct, frozen=True, forbid_unknown_fields=True
):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class EmergencyDisembarkPlacementSourceArtifact(
    msgspec.Struct, frozen=True, forbid_unknown_fields=True
):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[EmergencyDisembarkPlacementSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str
    placement_policy: EmergencyDisembarkPlacementPolicy


def validate_source_artifact_bytes(raw: bytes) -> EmergencyDisembarkPlacementSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EmergencyDisembarkPlacementSourceError(
            "Emergency Disembark placement source differs from its reviewed pin."
        )
    try:
        artifact = msgspec.json.decode(raw, type=EmergencyDisembarkPlacementSourceArtifact)
    except msgspec.DecodeError as exc:
        raise EmergencyDisembarkPlacementSourceError(
            "Emergency Disembark placement source schema is invalid."
        ) from exc
    if (
        artifact.artifact_schema != "core-v2-core-emergency-disembark-placement-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules)
        != (EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID,)
    ):
        raise EmergencyDisembarkPlacementSourceError(
            "Emergency Disembark placement source identity drifted."
        )
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise EmergencyDisembarkPlacementSourceError(
                "Emergency Disembark placement transcription hash drifted."
            )
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise EmergencyDisembarkPlacementSourceError(
                "Emergency Disembark placement execution evidence is incomplete."
            )
    policy = artifact.placement_policy
    if (
        policy.source_rule_id != EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID
        or policy.setup_distance_inches != 6
        or policy.requires_closest_possible is not True
        or policy.prefers_unengaged is not True
        or policy.allows_engaged_when_unengaged_impossible is not True
        or policy.destroys_only_unplaceable_models is not True
        or policy.closest_tolerance_inches != 0.04
    ):
        raise EmergencyDisembarkPlacementSourceError(
            "Emergency Disembark placement policy drifted."
        )
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[EmergencyDisembarkPlacementSourceRule, ...]:
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
                document_id=SourceDocumentId(package_id=package_id, document_id="p18b"),
                title="Reviewed maintained App-data 18.05 Emergency Disembark placement",
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
        evidence_required_source_ids=(EMERGENCY_DISEMBARK_PLACEMENT_SOURCE_ID,),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


PLACEMENT_POLICY: Final = _ARTIFACT.placement_policy
_SOURCE_PACKAGE: Final = _build_source_package()
