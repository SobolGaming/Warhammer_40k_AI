"""Reviewed faction RuleIR consumers; this package does not certify fieldability."""

from __future__ import annotations

import hashlib
from functools import cache
from typing import Final

import msgspec

from warhammer40k_core.rules.rule_ir import RuleIR, RuleIRPayload
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceCatalogPayload
from warhammer40k_core.rules.source_evidence import (
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RuleSourcePackage,
    SourceEvidenceCatalog,
)
from warhammer40k_core.rules.source_packages.artifact_loader import package_artifact_bytes

EXPECTED_ARTIFACT_SHA256: Final = "db0180dc622c1b77fc8963a271024bd005e676402dbb103528dfe5d16c091f87"
FOR_THE_CHAPTER_SOURCE_ID: Final = "faction-app:space-marines:hellblaster-squad:for-the-chapter"
UNENDING_FIDELITY_SOURCE_ID: Final = "faction-app:grey-knights:hallowed-conclave:unending-fidelity"


class RetainedAttackSourceError(ValueError):
    """A reviewed source or executable RuleIR identity has drifted."""


class RetainedAttackSourceRow(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    source_text: str
    transcription_sha256: str
    rule_ir: RuleIRPayload
    load_support_status: str
    semantic_execution_status: str
    runtime_consumer_ids: tuple[str, ...]
    fieldability_certified: bool


class RetainedAttackStratagemProfile(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    stratagem_id: str
    detachment_id: str
    name: str
    command_point_cost: int
    category: str
    trigger_kind: str
    phases: tuple[str, ...]
    target_policy_id: str
    required_keywords: tuple[str, ...]
    required_faction_keywords: tuple[str, ...]
    opponent_turn_phases: tuple[str, ...]


class RetainedAttackSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    stratagem_profile: RetainedAttackStratagemProfile
    historical_official_sources: tuple[dict[str, str], ...]
    artifact_schema: str
    source_package_id: str
    source_version: str
    source_catalog: SourceCatalogPayload
    rules: tuple[RetainedAttackSourceRow, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    audit_rows: tuple[dict[str, str | bool], ...]
    version_evidence: dict[str, str]
    capture_method: str
    scope: str
    package_hash: str


def validate_source_artifact_bytes(raw: bytes) -> RetainedAttackSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise RetainedAttackSourceError("Retained attack source bytes drifted.")
    try:
        artifact = msgspec.json.decode(raw, type=RetainedAttackSourceArtifact)
    except msgspec.DecodeError as exc:
        raise RetainedAttackSourceError("Retained attack source schema is invalid.") from exc
    if tuple(row.source_id for row in artifact.rules) != (
        FOR_THE_CHAPTER_SOURCE_ID,
        UNENDING_FIDELITY_SOURCE_ID,
    ):
        raise RetainedAttackSourceError("Retained attack source inventory drifted.")
    for row in artifact.rules:
        rule_ir = RuleIR.from_payload(row.rule_ir)
        if (
            rule_ir.source_id != row.source_id
            or hashlib.sha256(row.source_text.encode()).hexdigest() != row.transcription_sha256
            or row.load_support_status != "loaded"
            or row.semantic_execution_status != "executable_engine_runtime"
            or not row.runtime_consumer_ids
            or row.fieldability_certified
        ):
            raise RetainedAttackSourceError("Retained attack source execution identity drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)


@cache
def source_package() -> RuleSourcePackage:
    return RuleSourcePackage(
        source_catalog=SourceCatalog.from_payload(_ARTIFACT.source_catalog),
        source_evidence_catalog=SourceEvidenceCatalog(
            records=tuple(RuleEvidenceRecord.from_payload(row) for row in _ARTIFACT.evidence)
        ),
        evidence_required_source_ids=tuple(sorted(row.source_id for row in _ARTIFACT.rules)),
        source_authority_scope="warhammer_40000_11th_factions",
    )


def observation_identity(*, row_id: str) -> tuple[str, str, str, str, str]:
    for row in _ARTIFACT.audit_rows:
        if row["row_id"] == row_id:
            values = tuple(
                row[key]
                for key in (
                    "rule_source_id",
                    "transcription_sha256",
                    "row_id",
                    "observed_at",
                    "app_version",
                )
            )
            if len(values) != 5 or not all(isinstance(value, str) for value in values):
                raise RetainedAttackSourceError("Retained attack observation fields drifted.")
            return (str(values[0]), str(values[1]), str(values[2]), str(values[3]), str(values[4]))
    raise RetainedAttackSourceError("Retained attack observation is unregistered.")


def rule_ir_for_source(source_id: str) -> RuleIR:
    source_package()
    for row in _ARTIFACT.rules:
        if row.source_id == source_id:
            return RuleIR.from_payload(row.rule_ir)
    raise RetainedAttackSourceError(f"Unreviewed retained attack source: {source_id}.")


def stratagem_profile() -> RetainedAttackStratagemProfile:
    source_package()
    return _ARTIFACT.stratagem_profile
