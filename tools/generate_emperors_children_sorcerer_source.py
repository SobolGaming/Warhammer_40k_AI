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
    emperors_children_sorcerer_2026_11 as current,
)

ROOT = Path(__file__).resolve().parents[1]
OUTPUT_PATH = Path(current.__file__).with_name(current.ARTIFACT_NAME)
CAPTURE_PATH = ROOT / "data/source_audits/sorcerer_2026_11/source-observation-current.json"
CAPTURE_SHA256 = "7045ea750defe53c819b69828490a9fa644ed8520c335a49fd574c6986e61a8b"
PROFILE_CORRECTIONS = (
    (
        "Datasheets_models",
        "000004085:1",
        "014a630ddab29885d725691996376e7558cc1ce7bab2264e6e67c12b1497710f",
        (("T", "5"),),
    ),
    (
        "Datasheets_wargear",
        "000004085:3:1:8679",
        "3a8c706522829d972fc649963dfe5e1a5dc5988728c110d06ab0c952276124c8",
        (("S", "5"), ("AP", "-1")),
    ),
)


def generated_overlay_pack() -> SourceOverlayPack:
    if hashlib.sha256(CAPTURE_PATH.read_bytes()).hexdigest() != CAPTURE_SHA256:
        raise ValueError("Sorcerer current-source capture drifted.")
    return SourceOverlayPack(
        package_id=DataPackageId(
            namespace="40k-app",
            package_name="emperors-children-sorcerer",
            version="reviewed-2026-11-01",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-sorcerer-2026-11", source_date=date(2026, 11, 1)
        ),
        base_source_package_id=DataPackageId(
            namespace="wahapedia", package_name="source-mirror", version="10th-edition-2026-06-14"
        ),
        target_edition="warhammer-40000-11th",
        effective_date="2026-11-01",
        operations=tuple(
            SourceOverlayOperation(
                op_id=f"sorcerer-current-profile-{index}",
                order_index=index,
                operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
                target_edition="warhammer-40000-11th",
                source_table=table,
                source_row_id=row,
                source_reference="https://www.40k.app/factions/emperors-children/units/sorcerer",
                effective_date="2026-11-01",
                reason=(
                    "Apply the complete current observed Sorcerer profile; "
                    "observation date is not a per-field release date."
                ),
                expected_preimage_hash=preimage,
                fields=tuple(sorted(fields)),
            )
            for index, (table, row, preimage, fields) in enumerate(PROFILE_CORRECTIONS, 1)
        ),
    )


def main() -> None:
    OUTPUT_PATH.write_text(
        json.dumps(generated_overlay_pack().to_payload(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
