from __future__ import annotations

import hashlib
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
    emperors_children_current_2026_11 as current,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = Path(current.__file__).with_name(current.ARTIFACT_NAME)
CAPTURE_PATH = ROOT / "data/source_audits/ec_current_2026_11/browser-captures.json"
CAPTURE_SHA256 = "a7ad87299193bc05dce2ed65e12e015d3669d876e8dc10840ff2d19d4aff172e"
# Observation date, not an assertion that every field changed on that date.
PROFILE_CORRECTIONS = (
    (
        "Datasheets_models",
        "000004081:1",
        "chaos-terminators",
        "5ca5308819c871754d987f791a4f7f4f219f469c8afb3b3513542be2bea9db43",
        (("T", "6"),),
    ),
    (
        "Datasheets_wargear",
        "000004081:1:1:8658",
        "chaos-terminators",
        "4fd17f955a5795dc1019893fd16ee8a12ee3333f06a49b9305e9467de277d078",
        (("S", "5"), ("AP", "-1")),
    ),
    (
        "Datasheets_wargear",
        "000004081:2:1:8659",
        "chaos-terminators",
        "f9906d6e879246111d122bebef4bd2a1d7a0b70e59a21da9d6fdb4f701d3f033",
        (("S", "5"), ("AP", "-1")),
    ),
    (
        "Datasheets_models",
        "000004083:1",
        "lucius-the-eternal",
        "8804ac361ef81533fbc9d138b311b5dc821617df894acfb7f4a8966ffbb7c94b",
        (("T", "6"),),
    ),
)


def generated_overlay_pack() -> SourceOverlayPack:
    if hashlib.sha256(CAPTURE_PATH.read_bytes()).hexdigest() != CAPTURE_SHA256:
        raise ValueError("Current Emperor's Children browser capture drifted.")
    operations = tuple(
        SourceOverlayOperation(
            op_id=f"ec-current-profile-{index}",
            order_index=index,
            operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
            target_edition="warhammer-40000-11th",
            source_table=table,
            source_row_id=row,
            source_reference=f"https://www.40k.app/factions/emperors-children/units/{slug}",
            effective_date="2026-11-01",
            reason="Apply the observed current profile; preserve all other fields and raw history.",
            expected_preimage_hash=preimage,
            fields=tuple(sorted(fields)),
        )
        for index, (table, row, slug, preimage, fields) in enumerate(PROFILE_CORRECTIONS, 1)
    )
    return SourceOverlayPack(
        package_id=DataPackageId(
            namespace="40k-app",
            package_name="emperors-children-current",
            version="reviewed-2026-11-01",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-emperors-children-current-2026-11",
            source_date=date(2026, 11, 1),
        ),
        base_source_package_id=DataPackageId(
            namespace="wahapedia", package_name="source-mirror", version="10th-edition-2026-06-14"
        ),
        target_edition="warhammer-40000-11th",
        effective_date="2026-11-01",
        operations=(
            *operations,
            SourceOverlayOperation(
                op_id="ec-fulgrim-retire-serpentine",
                order_index=5,
                operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
                target_edition="warhammer-40000-11th",
                source_table="Datasheets_abilities",
                source_row_id="000004077:6",
                source_reference="https://www.40k.app/factions/emperors-children/units/fulgrim",
                effective_date="2026-11-01",
                reason=(
                    "Current Fulgrim has no Serpentine; own-unit history records removal at v909."
                ),
                expected_preimage_hash="d8ea1ab6f6cb8dee2cf190bbab5878dd8c0d9b2a111b7e224eac1c87d10351bf",
                fields=(),
            ),
            SourceOverlayOperation(
                op_id="ec-fulgrim-mobile",
                order_index=6,
                operation_kind=SourceOverlayOperationKind.ADD_ROW,
                target_edition="warhammer-40000-11th",
                source_table="Datasheets_keywords",
                source_row_id="000004077:Mobile:global:false:8",
                source_reference="https://www.40k.app/factions/emperors-children/units/fulgrim",
                effective_date="2026-11-01",
                reason=(
                    "Current Fulgrim carries MOBILE; "
                    "consume the existing generic keyword authority."
                ),
                expected_preimage_hash=None,
                fields=(
                    ("datasheet_id", "000004077"),
                    ("is_faction_keyword", "false"),
                    ("keyword", "Mobile"),
                    ("model", ""),
                ),
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
