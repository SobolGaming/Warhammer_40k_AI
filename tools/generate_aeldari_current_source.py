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
    aeldari_current_2026_11 as current,
)
from warhammer40k_core.rules.text_normalization import normalize_source_characters

ROOT = Path(__file__).resolve().parents[1]
REVIEW_PATH = ROOT / "data/source_audits/aeldari_current_2026_11/review.json"
REVIEW_SHA256 = "bef7c5ae5a8b7500657d9b70987f4e3529ae5b143358c91b3621a7d4ab902539"
OUTPUT_PATH = Path(current.__file__).with_name(current.ARTIFACT_NAME)


def generated_overlay_pack() -> SourceOverlayPack:
    raw = REVIEW_PATH.read_bytes()
    if hashlib.sha256(raw).hexdigest() != REVIEW_SHA256:
        raise ValueError("Aeldari source correction review drifted.")
    review = json.loads(raw)
    package = current.source_package()
    operations = []
    for index, change in enumerate(review["changes"], 1):
        source = package.source_catalog.source_text_by_id(change["source_id"])
        if change["field"] == "loadout" and change["after"] not in source.raw_text:
            raise ValueError("Aeldari loadout is absent from its complete source page.")
        if change["field"] == "description":
            clause = (
                change["after"].split("SUDDEN STRIKE\n", 1)[1].split("\nOPPORTUNITY SEIZED", 1)[0]
            )
            # The preserved composed source uses uppercase labels and single line breaks.
            captured_clause = (
                clause.replace("TRIGGER:", "Trigger:")
                .replace("EFFECT:", "Effect:")
                .replace("\n", "\n\n")
            )
            if normalize_source_characters(captured_clause) not in normalize_source_characters(
                source.raw_text
            ):
                raise ValueError(
                    "Sudden Strike correction is absent from its complete source page."
                )
        operations.append(
            SourceOverlayOperation(
                op_id=f"aeldari-current-source-{index}",
                order_index=index,
                operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
                target_edition="warhammer-40000-11th",
                source_table=change["table"],
                source_row_id=change["row_id"],
                source_reference=change["source_url"],
                effective_date="2026-11-02",
                reason=change["reason"],
                expected_preimage_hash=change["expected_preimage_hash"],
                fields=((change["field"], change["after"]),),
            )
        )
    return SourceOverlayPack(
        package_id=DataPackageId(
            namespace="40k-app", package_name="aeldari-current", version="reviewed-2026-11-02"
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-aeldari-current-2026-11",
            source_date=date(2026, 11, 2),
        ),
        base_source_package_id=DataPackageId(
            namespace="wahapedia", package_name="source-mirror", version="10th-edition-2026-06-14"
        ),
        target_edition="warhammer-40000-11th",
        effective_date="2026-11-02",
        operations=tuple(operations),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build the reviewed Aeldari source correction.")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    text = json.dumps(generated_overlay_pack().to_payload(), sort_keys=True, indent=2) + "\n"
    if args.check:
        if OUTPUT_PATH.read_text(encoding="utf-8") != text:
            raise ValueError("Generated Aeldari source overlay is stale.")
    else:
        OUTPUT_PATH.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
