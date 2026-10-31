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
    emperors_children_profiles_2026_10,
)

OUTPUT_PATH = Path(emperors_children_profiles_2026_10.__file__).with_name(
    emperors_children_profiles_2026_10.ARTIFACT_NAME
)
# Closed, separately observed v981 profile corrections. June source remains historical.
PROFILE_CORRECTIONS = (
    (
        "Datasheets_models",
        "000004078:1",
        "lord-exultant",
        "642c4d142f1b541fee4cb7fa145d9daaa7189e7faef6e1e26671e264a6a6d5a0",
        (("T", "5"),),
    ),
    (
        "Datasheets_models",
        "000004079:1",
        "tormentors",
        "38a849e709e2521096ed8197dc4d57fbda4423e73076aa3acbd840efc6c94695",
        (("T", "5"),),
    ),
    (
        "Datasheets_models",
        "000004080:1",
        "infractors",
        "29df31e0a1efb5994893dca44010ce23676740251aad10ddaad50560b9bdd815",
        (("T", "5"),),
    ),
    (
        "Datasheets_models",
        "000004084:1",
        "lord-kakophonist",
        "cd53f6ff4f8934aac1786368a228c59a5677151086d43cdc06cbbbca13e111fe",
        (("T", "6"),),
    ),
    (
        "Datasheets_models",
        "000004088:1",
        "noise-marines",
        "7f0f65eb66cf2c9984add6c30d76a3e1185d7b6689aa15e5809de93aa2e86285",
        (("W", "3"),),
    ),
    (
        "Datasheets_wargear",
        "000004078:1:1:8633",
        "lord-exultant",
        "eb398373ff17f00e40d390ce3d70c11ae554801fcb04a8243f9f28cce6f70cf5",
        (("S", "5"), ("AP", "-1")),
    ),
    (
        "Datasheets_wargear",
        "000004078:5:1:8637",
        "lord-exultant",
        "492e310cb7175de22b348d4644b83f0214d07b9eac688d0c2b288e05d0192743",
        (("S", "5"),),
    ),
    (
        "Datasheets_wargear",
        "000004079:1:1:8642",
        "tormentors",
        "7e3b25e34da8a22c9aa195262a9261e4bf041e1f700ae1bafa719e620db41666",
        (("S", "5"), ("AP", "-1")),
    ),
    (
        "Datasheets_wargear",
        "000004079:2:1:8643",
        "tormentors",
        "2dbbc8e2a2549a3e9d010e1cdcf41d92033ef41af5414dbf01a012e4fe1e2847",
        (("S", "5"), ("AP", "-1")),
    ),
    (
        "Datasheets_wargear",
        "000004079:8:1:8649",
        "tormentors",
        "fa32af2bc616db391abd34c1fe016deca850fdb7da0c257fb171f9bbf93faa7b",
        (("S", "5"),),
    ),
    (
        "Datasheets_wargear",
        "000004080:1:1:8652",
        "infractors",
        "3ccdac16bfd94f9046b1307ac3f553680c08a0f0df0296b3b4e089a7d791b0d8",
        (("S", "5"), ("AP", "-1")),
    ),
    (
        "Datasheets_wargear",
        "000004080:4:1:8655",
        "infractors",
        "54b13e94a47ece270f797facd8f003e6665bbf9aff3caf8cb7b79ad0c8d9fa1f",
        (("S", "5"),),
    ),
    (
        "Datasheets_wargear",
        "000004084:2:1:8675",
        "lord-kakophonist",
        "f32bf5af489d974dc93e7c82254e9855b1f640c3fb68c71b3415740a5e4ce14a",
        (("S", "5"),),
    ),
    (
        "Datasheets_wargear",
        "000004088:5:1:8691",
        "noise-marines",
        "539dde0dcb7b5e8832e1269085de074dff0a30c564a7bbcdd4d3437232ed7112",
        (("S", "5"),),
    ),
    (
        "Datasheets_wargear",
        "000004089:1:1:8693",
        "flawless-blades",
        "96d930ee17e7c91d26b76f835a7585dbac3417d5f061ec6537c0b92f434cb24d",
        (("S", "5"), ("AP", "-1")),
    ),
)


def generated_overlay_pack() -> SourceOverlayPack:
    return SourceOverlayPack(
        package_id=DataPackageId(
            namespace="40k-app",
            package_name="emperors-children-profiles",
            version="v981-reviewed-2026-10-31",
        ),
        catalog_version=CatalogVersion.dated(
            version_id="warhammer-40000-11th-emperors-children-profiles-2026-10",
            source_date=date(2026, 10, 31),
        ),
        base_source_package_id=DataPackageId(
            namespace="wahapedia", package_name="source-mirror", version="10th-edition-2026-06-14"
        ),
        target_edition="warhammer-40000-11th",
        effective_date="2026-10-31",
        operations=tuple(
            SourceOverlayOperation(
                op_id=f"ec-current-profile-{index}",
                order_index=index,
                operation_kind=SourceOverlayOperationKind.UPDATE_ROW,
                target_edition="warhammer-40000-11th",
                source_table=table,
                source_row_id=row,
                source_reference=f"https://www.40k.app/981/factions/emperors-children/units/{slug}",
                effective_date="2026-10-31",
                reason=(
                    "Apply the separately observed preferred v981 numeric profile; "
                    "preserve stable identities and all other fields."
                ),
                expected_preimage_hash=preimage,
                fields=tuple(sorted(fields)),
            )
            for index, (table, row, slug, preimage, fields) in enumerate(PROFILE_CORRECTIONS, 1)
        ),
    )


def main() -> None:
    OUTPUT_PATH.write_text(
        json.dumps(generated_overlay_pack().to_payload(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
