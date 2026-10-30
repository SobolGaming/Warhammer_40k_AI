from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayOperation,
    SourceOverlayOperationKind,
    SourceOverlayPack,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_vyper_title_2026_10,
)

OUTPUT_PATH = Path(aeldari_vyper_title_2026_10.__file__).with_name(
    aeldari_vyper_title_2026_10.ARTIFACT_NAME
)
SOURCE_URL = "https://www.40k.app/963/factions/aeldari/units/vyper"


def generated_overlay_pack() -> SourceOverlayPack:
    # The observation date is not a claim about when the title changed. v963 is
    # the latest Aeldari snapshot listed by the preferred updates index.
    return SourceOverlayPack(
        package_id=DataPackageId(
            namespace="40k-app",
            package_name="aeldari-vyper-title",
            version="v963-reviewed-2026-10-30",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-aeldari-vyper-title-2026-10",
            source_date=date(2026, 10, 30),
        ),
        base_source_package_id=DataPackageId(
            namespace="wahapedia", package_name="source-mirror", version="10th-edition-2026-06-14"
        ),
        target_edition="warhammer-40000-11th",
        effective_date="2026-10-30",
        operations=(
            SourceOverlayOperation(
                op_id="aeldari-vyper-current-source-title",
                order_index=1,
                operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
                target_edition="warhammer-40000-11th",
                source_table="Datasheets",
                source_row_id="000000605",
                source_reference=SOURCE_URL,
                effective_date="2026-10-30",
                reason=(
                    "Use the preferred App mirror title after source-bound continuity review; "
                    "preserve the stable datasheet ID, plural model identity and all rule fields."
                ),
                expected_preimage_hash="058dcfcc7221f364643673a29137c06474bc8c495179c0b6b89f15ee96bfa0ca",
                fields=(("name", "Vyper"),),
            ),
        ),
    )


def main() -> None:
    OUTPUT_PATH.write_text(
        json.dumps(generated_overlay_pack().to_payload(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
