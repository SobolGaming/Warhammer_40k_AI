from __future__ import annotations

from datetime import date

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceReleaseManifest,
)

BASE_EDITION_SUFFIX = "".join(("1", "0", "th"))
BASE_SOURCE_PACKAGE_ID = DataPackageId(
    namespace="wahapedia",
    package_name="source-mirror",
    version=f"{BASE_EDITION_SUFFIX}-edition-2026-06-14",
)
OVERLAY_PACKAGE_ID = DataPackageId(
    namespace="gw",
    package_name="chaos-defiler-datasheet-overlay",
    version="11th-2026-06-10",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-chaos-defiler-datasheet-overlay",
    source_date=date(2026, 6, 10),
)
SOURCE_REFERENCE = "gw-11e-chaos-defiler-faction-pack-datasheets-2026-06:datasheets"
SOURCE_DATE = "2026-06-10"
TARGET_EDITION = "warhammer-40000-11th"

DEATH_GUARD_DEFILER_DATASHEET_ID = "000004209"
WORLD_EATERS_DEFILER_DATASHEET_ID = "000004207"
THOUSAND_SONS_DEFILER_DATASHEET_ID = "000001030"
EMPERORS_CHILDREN_DEFILER_DATASHEET_ID = "000004208"
DEFILER_DATASHEET_IDS = (
    DEATH_GUARD_DEFILER_DATASHEET_ID,
    WORLD_EATERS_DEFILER_DATASHEET_ID,
    THOUSAND_SONS_DEFILER_DATASHEET_ID,
    EMPERORS_CHILDREN_DEFILER_DATASHEET_ID,
)


def source_release_manifest() -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="chaos-defiler-11e-datasheet-overlay-2026-06",
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        base_source_edition=f"warhammer-40000-{BASE_EDITION_SUFFIX}",
        target_edition=TARGET_EDITION,
        overlay_package_ids=(OVERLAY_PACKAGE_ID,),
    )


def overlay_pack() -> SourceOverlayPack:
    return SourceOverlayPack(
        package_id=OVERLAY_PACKAGE_ID,
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        target_edition=TARGET_EDITION,
        effective_date=SOURCE_DATE,
        operations=_operations(),
    )


def source_package_identity_payload() -> dict[str, str]:
    package = overlay_pack()
    return {
        "source_package_id": OVERLAY_PACKAGE_ID.stable_identity(),
        "source_payload_checksum_sha256": package.package_hash(),
        "source_date": SOURCE_DATE,
        "source_edition": TARGET_EDITION,
    }


def _operations() -> tuple[SourceOverlayOperation, ...]:
    return (
        _supersede_blank_keyword_row(
            op_id="chaos-defiler-thousand-sons-remove-empty-keyword",
            order_index=10,
            source_row_id="000001030:blank-keyword:global:true:4079",
            expected_preimage_hash=(
                "a131c8969fe780eefdb815c36fb247c299d9231321e0a90f2ad5ce06b524c978"
            ),
        ),
        _supersede_blank_keyword_row(
            op_id="chaos-defiler-world-eaters-remove-empty-keyword",
            order_index=20,
            source_row_id="000004207:blank-keyword:global:true:15727",
            expected_preimage_hash=(
                "e8c91f47e38689afa7b59c36721643fee719c36c9440f7cb96ba72f9951a67bc"
            ),
        ),
        _supersede_blank_keyword_row(
            op_id="chaos-defiler-emperors-children-remove-empty-keyword",
            order_index=30,
            source_row_id="000004208:blank-keyword:global:true:15734",
            expected_preimage_hash=(
                "bb0bd82976f6829978c930144924225dff06654ffae55fde2df78865d2dcde52"
            ),
        ),
        _supersede_blank_keyword_row(
            op_id="chaos-defiler-death-guard-remove-empty-keyword",
            order_index=40,
            source_row_id="000004209:blank-keyword:global:true:15742",
            expected_preimage_hash=(
                "fca69bb8584c336c3e97a9ca4cbb64dd1eb515ee48c871e7c3b5ee28aaefa342"
            ),
        ),
    )


def _supersede_blank_keyword_row(
    *,
    op_id: str,
    order_index: int,
    source_row_id: str,
    expected_preimage_hash: str,
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
        target_edition=TARGET_EDITION,
        source_table="Datasheets_keywords",
        source_row_id=source_row_id,
        source_reference=SOURCE_REFERENCE,
        effective_date=SOURCE_DATE,
        reason="Supersede empty keyword source row before 11e Defiler bridge.",
        expected_preimage_hash=expected_preimage_hash,
        fields=(),
    )
