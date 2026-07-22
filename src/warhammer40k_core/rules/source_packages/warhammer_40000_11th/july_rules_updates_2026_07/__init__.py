from __future__ import annotations

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
from warhammer40k_core.rules.source_packages.artifact_loader import (
    SourcePackageArtifactError,
    package_artifact_bytes,
)

from ._artifacts import (
    EventCompanionRuleUpdateRecord,
    EventLayoutRevisionRecord,
    JulyRulesUpdateArtifactError,
    JulyRulesUpdatesPackageArtifact,
    UniversalRuleUpdateRecord,
    july_rules_updates_package_artifact_from_json_bytes,
)

_ARTIFACT_PATH: Final = "artifacts/package.json"


def _load_artifact() -> JulyRulesUpdatesPackageArtifact:
    try:
        raw = package_artifact_bytes(__name__, _ARTIFACT_PATH)
    except SourcePackageArtifactError as exc:
        raise JulyRulesUpdateArtifactError(
            "July rules-update generated data package could not be loaded."
        ) from exc
    return july_rules_updates_package_artifact_from_json_bytes(raw)


_ARTIFACT: Final = _load_artifact()
SOURCE_PACKAGE_ID: Final = _ARTIFACT.source_package_id
SOURCE_TITLE: Final = _ARTIFACT.source_title
SOURCE_VERSION: Final = _ARTIFACT.source_version
SOURCE_DATE: Final = _ARTIFACT.source_date
UNIVERSAL_RULES_SOURCE_URL: Final = _ARTIFACT.universal_rules_update.source_url
UNIVERSAL_RULES_LOCAL_PDF: Final = _ARTIFACT.universal_rules_update.local_pdf
UNIVERSAL_RULES_PDF_SHA256: Final = _ARTIFACT.universal_rules_update.source_pdf_sha256
EVENT_COMPANION_SOURCE_URL: Final = _ARTIFACT.event_companion.source_url
EVENT_COMPANION_LOCAL_PDF: Final = _ARTIFACT.event_companion.local_pdf
EVENT_COMPANION_PDF_SHA256: Final = _ARTIFACT.event_companion.source_pdf_sha256
EVENT_COMPANION_SOURCE_PACKAGE_ID: Final = _ARTIFACT.event_companion.updated_source_package_id
IDENTICAL_UNIT_REPLACEMENT_STRATAGEM_SOURCE_IDS: Final = frozenset(
    _ARTIFACT.universal_rules_update.identical_unit_replacement_stratagem_source_ids
)
PROTECTIVE_TARGETING_STRATAGEM_SOURCE_IDS: Final = frozenset(
    _ARTIFACT.universal_rules_update.protective_targeting_stratagem_source_ids
)
NON_CORE_CP_GAIN_CAP_SOURCE_ID: Final = _ARTIFACT.event_companion.rules[0].source_id


def universal_rule_records() -> tuple[UniversalRuleUpdateRecord, ...]:
    return _ARTIFACT.universal_rules_update.rules


def changed_event_layouts() -> tuple[EventLayoutRevisionRecord, ...]:
    return _ARTIFACT.event_companion.changed_layouts


def event_companion_rule_records() -> tuple[EventCompanionRuleUpdateRecord, ...]:
    return _ARTIFACT.event_companion.rules


def source_catalog() -> SourceCatalog:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version=SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=SOURCE_VERSION,
        source_date=date.fromisoformat(SOURCE_DATE),
    )
    universal_document_id = SourceDocumentId(
        package_id=package_id,
        document_id=_ARTIFACT.universal_rules_update.document_id,
    )
    event_document_id = SourceDocumentId(
        package_id=package_id,
        document_id=_ARTIFACT.event_companion.document_id,
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=universal_document_id,
                title=(
                    f"{_ARTIFACT.universal_rules_update.source_title} "
                    f"({_ARTIFACT.universal_rules_update.local_pdf})"
                ),
                source_texts=(
                    RuleSourceText.from_raw(
                        source_id=f"{SOURCE_PACKAGE_ID}:manifest:universal-rules-update",
                        raw_text=(
                            "Local Universal Rules Updates PDF: "
                            f"{_ARTIFACT.universal_rules_update.local_pdf}; SHA-256: "
                            f"{_ARTIFACT.universal_rules_update.source_pdf_sha256}"
                        ),
                    ),
                    *tuple(
                        RuleSourceText.from_raw(
                            source_id=rule.source_id,
                            raw_text=rule.source_text,
                        )
                        for rule in event_companion_rule_records()
                    ),
                    *tuple(
                        RuleSourceText.from_raw(
                            source_id=rule.source_id,
                            raw_text=rule.source_text,
                        )
                        for rule in universal_rule_records()
                    ),
                ),
            ),
            SourceDocument(
                document_id=event_document_id,
                title=(
                    f"{_ARTIFACT.event_companion.source_title} "
                    f"({_ARTIFACT.event_companion.local_pdf})"
                ),
                source_texts=(
                    RuleSourceText.from_raw(
                        source_id=f"{SOURCE_PACKAGE_ID}:manifest:event-companion-v1-1",
                        raw_text=(
                            "Local Warhammer Event Companion v1.1 PDF: "
                            f"{_ARTIFACT.event_companion.local_pdf}; SHA-256: "
                            f"{_ARTIFACT.event_companion.source_pdf_sha256}"
                        ),
                    ),
                    *tuple(
                        RuleSourceText.from_raw(
                            source_id=row.source_id,
                            raw_text=(
                                f"Event Companion v1.1 page {row.source_page} revises terrain "
                                f"for {row.layout_id}; deployment-zone template "
                                f"{row.deployment_zone_template_number} is unchanged."
                            ),
                        )
                        for row in changed_event_layouts()
                    ),
                ),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(
                    version="core-v2-july-rules-updates-2026-07"
                ),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(universal_document_id, event_document_id),
            ),
        ),
    )


__all__ = (
    "EVENT_COMPANION_LOCAL_PDF",
    "EVENT_COMPANION_PDF_SHA256",
    "EVENT_COMPANION_SOURCE_PACKAGE_ID",
    "EVENT_COMPANION_SOURCE_URL",
    "IDENTICAL_UNIT_REPLACEMENT_STRATAGEM_SOURCE_IDS",
    "NON_CORE_CP_GAIN_CAP_SOURCE_ID",
    "PROTECTIVE_TARGETING_STRATAGEM_SOURCE_IDS",
    "SOURCE_DATE",
    "SOURCE_PACKAGE_ID",
    "SOURCE_TITLE",
    "SOURCE_VERSION",
    "UNIVERSAL_RULES_LOCAL_PDF",
    "UNIVERSAL_RULES_PDF_SHA256",
    "UNIVERSAL_RULES_SOURCE_URL",
    "JulyRulesUpdateArtifactError",
    "changed_event_layouts",
    "event_companion_rule_records",
    "july_rules_updates_package_artifact_from_json_bytes",
    "source_catalog",
    "universal_rule_records",
)
