"""Hash-pinned reviewed 18.02 Embark setup-turn source."""

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

EXPECTED_ARTIFACT_SHA256: Final = "d318c7965bbd70b5ea1bf97995e6b3142b4c6e9f9cc6e06ea26f974537aa450e"
SOURCE_PACKAGE_ID: Final = "gw-11e-core-embark-setup-turn"
SOURCE_VERSION: Final = "maintained-app-mirrors-observed-2026-09-19"
EMBARK_SETUP_TURN_SOURCE_ID: Final = f"{SOURCE_PACKAGE_ID}:embark-setup-turn"


class EmbarkSetupTurnSourceError(ValueError):
    """Reviewed Embark setup-turn source bytes, schema or provenance drifted."""


class EmbarkSetupTurnPolicy(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_rule_id: str
    forbids_setup_this_turn: bool
    scopes_to_actual_turn_player: bool


class EmbarkSetupTurnSourceRule(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    source_id: str
    section_id: str
    source_text: str
    transcription_sha256: str
    load_support_status: LoadSupportStatus
    semantic_execution_status: SemanticExecutionStatus
    runtime_consumer_ids: tuple[str, ...]


class EmbarkSetupTurnSourceArtifact(msgspec.Struct, frozen=True, forbid_unknown_fields=True):
    artifact_schema: str
    source_package_id: str
    source_version: str
    rules: tuple[EmbarkSetupTurnSourceRule, ...]
    evidence: tuple[RuleEvidencePayload, ...]
    package_hash: str
    embark_policy: EmbarkSetupTurnPolicy


def validate_source_artifact_bytes(raw: bytes) -> EmbarkSetupTurnSourceArtifact:
    if hashlib.sha256(raw).hexdigest() != EXPECTED_ARTIFACT_SHA256:
        raise EmbarkSetupTurnSourceError("Embark setup-turn source differs from its reviewed pin.")
    try:
        artifact = msgspec.json.decode(raw, type=EmbarkSetupTurnSourceArtifact)
    except msgspec.DecodeError as exc:
        raise EmbarkSetupTurnSourceError("Embark setup-turn source schema is invalid.") from exc
    if (
        artifact.artifact_schema != "core-v2-core-embark-setup-turn-source-v1"
        or artifact.source_package_id != SOURCE_PACKAGE_ID
        or artifact.source_version != SOURCE_VERSION
        or tuple(rule.source_id for rule in artifact.rules) != (EMBARK_SETUP_TURN_SOURCE_ID,)
    ):
        raise EmbarkSetupTurnSourceError("Embark setup-turn source identity drifted.")
    for rule in artifact.rules:
        if hashlib.sha256(rule.source_text.encode()).hexdigest() != rule.transcription_sha256:
            raise EmbarkSetupTurnSourceError("Embark setup-turn transcription hash drifted.")
        if (
            rule.load_support_status != "loaded"
            or rule.semantic_execution_status != "executable_engine_runtime"
            or not rule.runtime_consumer_ids
        ):
            raise EmbarkSetupTurnSourceError("Embark setup-turn execution evidence is incomplete.")
    policy = artifact.embark_policy
    if (
        policy.source_rule_id != EMBARK_SETUP_TURN_SOURCE_ID
        or policy.forbids_setup_this_turn is not True
        or policy.scopes_to_actual_turn_player is not True
    ):
        raise EmbarkSetupTurnSourceError("Embark setup-turn policy drifted.")
    return artifact


_ARTIFACT: Final = validate_source_artifact_bytes(
    package_artifact_bytes(__name__, "artifacts/package.json")
)
PACKAGE_HASH: Final = _ARTIFACT.package_hash


def source_rules() -> tuple[EmbarkSetupTurnSourceRule, ...]:
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
                document_id=SourceDocumentId(package_id=package_id, document_id="p18h"),
                title="Reviewed maintained App-data 18.02 Embark setup-turn",
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
        evidence_required_source_ids=(EMBARK_SETUP_TURN_SOURCE_ID,),
        source_authority_scope=CORE_RULES_SOURCE_AUTHORITY_SCOPE,
    )


_SOURCE_PACKAGE: Final = _build_source_package()


def source_package() -> RuleSourcePackage:
    return _SOURCE_PACKAGE


EMBARK_POLICY: Final = _ARTIFACT.embark_policy
