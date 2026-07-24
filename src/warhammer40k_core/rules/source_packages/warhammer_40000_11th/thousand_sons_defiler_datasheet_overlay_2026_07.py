from __future__ import annotations

from datetime import date

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
    SourceReleaseManifest,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    july_faction_packs_2026_07,
)

BASE_EDITION_SUFFIX = "".join(("1", "0", "th"))
BASE_SOURCE_PACKAGE_ID = DataPackageId(
    namespace="wahapedia",
    package_name="source-mirror",
    version=f"{BASE_EDITION_SUFFIX}-edition-2026-06-14",
)
OVERLAY_PACKAGE_ID = DataPackageId(
    namespace="gw",
    package_name="thousand-sons-defiler-datasheet-overlay",
    version="11th-2026-07-22",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-thousand-sons-defiler-datasheet-overlay",
    source_date=date(2026, 7, 22),
)
SOURCE_REFERENCE = "gw-11e-thousand-sons-faction-pack-2026-07:datasheet:000001030:page-7"
SOURCE_DATE = "2026-07-22"
TARGET_EDITION = "warhammer-40000-11th"
THOUSAND_SONS_DEFILER_DATASHEET_ID = "000001030"
CHAOS_SPACE_MARINES_DEFILER_DATASHEET_ID = "000000969"
ALIGNED_DEFILER_DATASHEET_IDS = ("000001030", "000004207", "000004208", "000004209")
AUDITED_DEFILER_DATASHEET_IDS = (
    CHAOS_SPACE_MARINES_DEFILER_DATASHEET_ID,
    *ALIGNED_DEFILER_DATASHEET_IDS,
)


def source_release_manifest() -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="thousand-sons-defiler-11e-datasheet-overlay-2026-07",
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        base_source_edition=f"warhammer-40000-{BASE_EDITION_SUFFIX}",
        target_edition=TARGET_EDITION,
        overlay_package_ids=(OVERLAY_PACKAGE_ID,),
    )


def overlay_pack() -> SourceOverlayPack:
    artifact = july_faction_packs_2026_07.thousand_sons_defiler()
    return SourceOverlayPack(
        package_id=OVERLAY_PACKAGE_ID,
        catalog_version=CATALOG_VERSION,
        base_source_package_id=BASE_SOURCE_PACKAGE_ID,
        target_edition=TARGET_EDITION,
        effective_date=SOURCE_DATE,
        operations=tuple(
            SourceOverlayOperation(
                op_id=operation.op_id,
                order_index=operation.order_index,
                operation_kind=SourceOverlayOperationKind(operation.operation_kind),
                target_edition=TARGET_EDITION,
                source_table=operation.source_table,
                source_row_id=operation.source_row_id,
                source_reference=SOURCE_REFERENCE,
                effective_date=SOURCE_DATE,
                reason=operation.reason,
                expected_preimage_hash=operation.expected_preimage_hash,
                fields=tuple(sorted(operation.fields.items())),
            )
            for operation in artifact.operations
        ),
    )


def source_package_identity_payload() -> dict[str, str]:
    package = overlay_pack()
    return {
        "source_package_id": OVERLAY_PACKAGE_ID.stable_identity(),
        "source_payload_checksum_sha256": package.package_hash(),
        "source_date": SOURCE_DATE,
        "source_edition": TARGET_EDITION,
    }
