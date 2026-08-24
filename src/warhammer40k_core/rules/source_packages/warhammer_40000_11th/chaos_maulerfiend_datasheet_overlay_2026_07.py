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
    package_name="chaos-maulerfiend-datasheet-overlay",
    version="11th-2026-07-22",
)
CATALOG_VERSION = CatalogVersion.dated(
    version_id="warhammer-40000-11th-chaos-maulerfiend-datasheet-overlay",
    source_date=date(2026, 7, 22),
)
SOURCE_DATE = "2026-07-22"
TARGET_EDITION = "warhammer-40000-11th"

CHAOS_SPACE_MARINES_MAULERFIEND_DATASHEET_ID = "000000968"
THOUSAND_SONS_MAULERFIEND_DATASHEET_ID = "000001029"
WORLD_EATERS_MAULERFIEND_DATASHEET_ID = "000002639"
EMPERORS_CHILDREN_MAULERFIEND_DATASHEET_ID = "000004091"
CURRENT_MAULERFIEND_DATASHEET_IDS = (
    CHAOS_SPACE_MARINES_MAULERFIEND_DATASHEET_ID,
    THOUSAND_SONS_MAULERFIEND_DATASHEET_ID,
    WORLD_EATERS_MAULERFIEND_DATASHEET_ID,
    EMPERORS_CHILDREN_MAULERFIEND_DATASHEET_ID,
)

THOUSAND_SONS_SNARLING_PROTECTOR_DESCRIPTION = (
    "You can target this unit with the Heroic Intervention Stratagem, regardless of any "
    "other uses of that Stratagem this phase. If you do:\n"
    "- That use is -1CP.\n"
    "- That use does not prevent any uses of that Stratagem on other units this phase.\n"
    'When this unit declares a charge, if a friendly engaged Psyker unit is within 12" of '
    "this unit, you can use this part of this ability. If you do:\n"
    "- This unit can re-roll that Charge roll.\n"
    "- This unit must end that Charge move engaged with an enemy unit engaged with that "
    "friendly Psyker unit."
)
WORLD_EATERS_SCENT_OF_BLOOD_DESCRIPTION = (
    "In the Charge phase, when this unit declares a charge:\n"
    '- If an enemy unit below Starting Strength is within 9" of this unit, this unit has +1 '
    "to Charge rolls.\n"
    '- Or: If an enemy unit Below Half-strength is within 9" of this unit, this unit has +2 '
    "to Charge rolls."
)

_THOUSAND_SONS_SOURCE_REFERENCE = (
    "gw-11e-thousand-sons-faction-pack-2026-07:datasheet:000001029:rules-update:page-10"
)
_WORLD_EATERS_SOURCE_REFERENCE = (
    "gw-11e-world-eaters-faction-pack-2026-07:datasheet:000002639:rules-update:page-8"
)


def source_release_manifest() -> SourceReleaseManifest:
    return SourceReleaseManifest(
        release_id="chaos-maulerfiend-11e-datasheet-overlay-2026-07",
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
        operations=(
            _update_ability(
                op_id="thousand-sons-maulerfiend-snarling-protector",
                order_index=10,
                source_row_id="000001029:2",
                source_reference=_THOUSAND_SONS_SOURCE_REFERENCE,
                expected_preimage_hash=(
                    "cbffd6a2a49a08b3e706c0aab0750595ddc79655e2d4a1991b6a0b35b45556dc"
                ),
                description=THOUSAND_SONS_SNARLING_PROTECTOR_DESCRIPTION,
            ),
            _update_ability(
                op_id="world-eaters-maulerfiend-scent-of-blood",
                order_index=20,
                source_row_id="000002639:3",
                source_reference=_WORLD_EATERS_SOURCE_REFERENCE,
                expected_preimage_hash=(
                    "707c63b07e149509849ae5f7d1c7bd21d1c25ad55d1dd6c562cc9f5cd3ebdb21"
                ),
                description=WORLD_EATERS_SCENT_OF_BLOOD_DESCRIPTION,
            ),
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


def _update_ability(
    *,
    op_id: str,
    order_index: int,
    source_row_id: str,
    source_reference: str,
    expected_preimage_hash: str,
    description: str,
) -> SourceOverlayOperation:
    return SourceOverlayOperation(
        op_id=op_id,
        order_index=order_index,
        operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
        target_edition=TARGET_EDITION,
        source_table="Datasheets_abilities",
        source_row_id=source_row_id,
        source_reference=source_reference,
        effective_date=SOURCE_DATE,
        reason="Apply the current 11th Edition Maulerfiend datasheet rules update.",
        expected_preimage_hash=expected_preimage_hash,
        fields=(("description", description),),
    )
