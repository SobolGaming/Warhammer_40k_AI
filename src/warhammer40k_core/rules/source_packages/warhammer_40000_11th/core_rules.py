from __future__ import annotations

from datetime import date

from warhammer40k_core.core.ruleset import RulesetId
from warhammer40k_core.rules.data_package import (
    CatalogVersion,
    DataPackageId,
    RulesetBundle,
    SourceDocumentId,
)
from warhammer40k_core.rules.source_catalog import SourceCatalog, SourceDocument
from warhammer40k_core.rules.source_data import RuleSourceText

EDITION_ID = "warhammer_40000_11th"
SOURCE_PACKAGE_ID = "gw-11e-core-rules"
SOURCE_TITLE = "Warhammer 40,000 11th Edition Core Rules"
SOURCE_VERSION = "11e-core-rules"
LOCAL_CORE_RULES_PDF = (
    "docs/source_rules/eng_01-06_warhammer40k_new40k_core_rules-was6fbu1ix-hfewhmxyiy.pdf"
)


def source_catalog() -> SourceCatalog:
    package_id = DataPackageId(
        namespace="games-workshop",
        package_name=SOURCE_PACKAGE_ID,
        version=SOURCE_VERSION,
    )
    catalog_version = CatalogVersion.dated(
        version_id=SOURCE_VERSION,
        source_date=date(2026, 6, 1),
    )
    document_id = SourceDocumentId(
        package_id=package_id,
        document_id="eng_01-06_warhammer40k_new40k_core_rules",
    )
    source_text = RuleSourceText.from_raw(
        source_id=f"{SOURCE_PACKAGE_ID}:manifest:local-core-rules-pdf",
        raw_text=f"Local 11th Edition Core Rules PDF: {LOCAL_CORE_RULES_PDF}",
    )
    return SourceCatalog(
        package_id=package_id,
        catalog_version=catalog_version,
        documents=(
            SourceDocument(
                document_id=document_id,
                title=f"{SOURCE_TITLE} ({LOCAL_CORE_RULES_PDF})",
                source_texts=(source_text,),
            ),
        ),
        ruleset_bundles=(
            RulesetBundle(
                bundle_id=SOURCE_PACKAGE_ID,
                ruleset_id=RulesetId.warhammer_40000_eleventh(version="core-v2-phase14a"),
                package_id=package_id,
                catalog_version=catalog_version,
                source_document_ids=(document_id,),
            ),
        ),
    )
