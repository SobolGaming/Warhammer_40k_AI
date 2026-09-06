"""Expose the F00 observations through the shared source/evidence boundary."""

from __future__ import annotations

import hashlib
import json
from functools import cache

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId, SourceDocumentId
from warhammer40k_core.rules.faction_source_governance import (
    FACTION_SOURCE_PACKAGE_NAME,
    FACTION_SOURCE_POLICY_ID,
    FactionSourceAudit,
    FactionSourceObservation,
    faction_source_audit,
)
from warhammer40k_core.rules.objective_terminology import ObjectiveRuleScope
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText
from warhammer40k_core.rules.source_evidence import (
    RuleEvidencePayload,
    RuleEvidenceRecord,
    RuleSourcePackage,
    SourceEvidenceCatalog,
)


@cache
def faction_source_package() -> RuleSourcePackage:
    audit = faction_source_audit()
    return RuleSourcePackage(
        source_catalog=faction_source_catalog(audit),
        source_evidence_catalog=SourceEvidenceCatalog(
            records=tuple(
                record for row in audit.observations for record in _evidence(row, audit.audit_id)
            )
        ),
        evidence_required_source_ids=tuple(sorted(audit.selected_source_ids)),
        source_authority_scope="warhammer_40000_11th_factions",
    )


def faction_source_catalog(audit: FactionSourceAudit) -> SourceCatalog:
    """Derive the complete catalog from a validated audit, without granting authority."""
    version = audit.package_version()
    package_id = DataPackageId(
        namespace="core-v2-reviewed-app-mirror",
        package_name=FACTION_SOURCE_PACKAGE_NAME,
        version=version,
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=CatalogVersion.dated(
            version_id=version, source_date=audit.observation_date()
        ),
        documents=tuple(
            SourceDocument(
                document_id=SourceDocumentId(package_id=package_id, document_id=row.source_id),
                title=row.source_title,
                source_texts=(
                    RuleSourceText.from_raw(
                        source_id=row.source_id,
                        raw_text=row.operative_text,
                        objective_scope=ObjectiveRuleScope.NON_CORE_RULES,
                    ),
                ),
            )
            for row in audit.observations
        ),
        ruleset_bundles=(),
    )


def _evidence(row: FactionSourceObservation, audit_id: str) -> tuple[RuleEvidenceRecord, ...]:
    reviewed: RuleEvidencePayload = {
        "evidence_id": f"project-review:{row.observation_id}",
        "rule_source_id": row.source_id,
        "evidence_kind": "project_reviewed_app_transcription",
        "authority": "unverified_transcription_only",
        "project_authority_policy_id": None,
        "review_audit_id": None,
        "review_audit_row_id": None,
        "review_audit_source_observation_sha256": None,
        "provider_name": "CORE V2 Source Review",
        "source_title": row.source_title,
        "source_platform": "Repository",
        "source_url": None,
        "observed_at": row.observed_at,
        "app_version": None,
        "app_build": None,
        "capture_artifact_path": None,
        "capture_sha256": None,
        "transcription_sha256": row.transcription_sha256,
        "official_corroborating_source_ids": [],
        "verification_status": "unverified",
        "provider_non_affiliation_recorded": False,
        "observation_sha256": "",
        "load_support_status": "loaded",
        "semantic_execution_status": "not_certified",
        "runtime_consumer_ids": [],
    }
    mirror = reviewed.copy()
    mirror.update(
        {
            "evidence_id": f"40k-app:{row.observation_id}",
            "evidence_kind": "third_party_mirror",
            "authority": "project_authoritative_app_mirror",
            "project_authority_policy_id": FACTION_SOURCE_POLICY_ID,
            "review_audit_id": audit_id,
            "review_audit_row_id": row.observation_id,
            "review_audit_source_observation_sha256": row.source_observation_sha256,
            "provider_name": row.provider_name,
            "source_platform": "Web",
            "source_url": row.source_url,
            "app_version": row.app_version,
            "verification_status": "authoritative_app_mirror",
            "provider_non_affiliation_recorded": True,
        }
    )
    for payload in (reviewed, mirror):
        observed = payload.copy()
        observed["load_support_status"] = "not_loaded"
        payload["observation_sha256"] = hashlib.sha256(
            json.dumps(observed, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
    return tuple(RuleEvidenceRecord.from_payload(payload) for payload in (reviewed, mirror))
