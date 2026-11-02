from __future__ import annotations

import argparse
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
    aeldari_banshee_eldrad_2026_11 as current,
)

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / "data/source_audits/aeldari_banshee_eldrad_2026_11/review.json"
REVIEW_SHA256 = "19582c8752051ea1b7553535b19d224c7e0d97e9d8cfcc0494112368f896ee24"
OUTPUT_PATH = Path(current.__file__).with_name(current.ARTIFACT_NAME)


def generated_overlay_pack() -> SourceOverlayPack:
    raw = REVIEW_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REVIEW_SHA256:
        raise ValueError("Banshee/Eldrad source review drifted.")
    review = json.loads(raw)
    source = current.source_package().source_catalog.source_text_by_id(review["source_id"])
    leader_section = source.raw_text.split("\nLeads\n", 1)[1].split("\nCORE ABILITIES", 1)[0]
    if leader_section.splitlines() != ["STORM GUARDIANS", "GUARDIAN DEFENDERS"]:
        raise ValueError("Eldrad current bodyguard inventory drifted.")
    return SourceOverlayPack(
        package_id=DataPackageId(
            namespace="40k-app",
            package_name="aeldari-banshee-eldrad",
            version="reviewed-2026-11-02",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-aeldari-banshee-eldrad-2026-11",
            source_date=date(2026, 11, 2),
        ),
        base_source_package_id=DataPackageId(
            namespace="wahapedia", package_name="source-mirror", version="10th-edition-2026-06-14"
        ),
        target_edition="warhammer-40000-11th",
        effective_date="2026-11-02",
        operations=(
            SourceOverlayOperation(
                op_id="eldrad-retire-warlock-conclave-2026-11-02",
                order_index=1,
                operation_kind=SourceOverlayOperationKind.SUPERSEDE_ROW,
                target_edition="warhammer-40000-11th",
                source_table=review["table"],
                source_row_id=review["row_id"],
                source_reference=review["source_url"],
                effective_date="2026-11-02",
                reason=review["reason"],
                expected_preimage_hash=review["expected_preimage_hash"],
                fields=(),
            ),
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build the bounded Eldrad relationship correction."
    )
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(generated_overlay_pack().to_payload(), sort_keys=True, indent=2) + "\n"
    if args.check:
        if OUTPUT_PATH.read_text(encoding="utf-8") != text:
            raise ValueError("Generated Banshee/Eldrad source overlay is stale.")
    else:
        OUTPUT_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
