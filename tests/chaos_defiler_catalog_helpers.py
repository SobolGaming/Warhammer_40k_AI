from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import cast

from warhammer40k_core.engine.list_validation import UnitMusterSelection
from warhammer40k_core.engine.unit_factory import UnitFactory, UnitInstance
from warhammer40k_core.engine.wargear_selections import ModelProfileSelection, WargearSelection
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.catalog_package import CanonicalCatalogPackage
from warhammer40k_core.rules.data_package import DataPackageId
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_defiler_datasheet_overlay_2026_06 as defiler_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    thousand_sons_defiler_datasheet_overlay_2026_07 as july_defiler_overlay,
)
from warhammer40k_core.rules.wahapedia_bridge import (
    build_wahapedia_canonical_bridge_artifacts,
)
from warhammer40k_core.rules.wahapedia_bridge_defaults import CHAOS_DEFILER_HEIGHT_OVERRIDES
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

_WAHAPEDIA_10E_JSON = (
    Path(__file__).resolve().parents[1]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("".join(("1", "0", "th")) + "-edition")
    / "2026-06-14"
    / "json"
)
_REQUIRED_TABLES = (
    "Abilities",
    "Datasheets",
    "Datasheets_abilities",
    "Datasheets_keywords",
    "Datasheets_leader",
    "Datasheets_models",
    "Datasheets_models_cost",
    "Datasheets_options",
    "Datasheets_unit_composition",
    "Datasheets_wargear",
    "Factions",
)


@lru_cache(maxsize=1)
def defiler_catalog_package() -> CanonicalCatalogPackage:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=defiler_overlay_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="chaos-defiler-11e-bridge-test",
            version="2026-06-10",
        ),
        datasheet_ids=defiler_overlay.DEFILER_DATASHEET_IDS,
        height_overrides=CHAOS_DEFILER_HEIGHT_OVERRIDES,
    )
    return build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="chaos-defiler-11e-catalog-test",
            version="2026-06-10",
        ),
        catalog_version=defiler_overlay.CATALOG_VERSION,
        source_artifacts=bridge_artifacts,
    )


@lru_cache(maxsize=1)
def july_defiler_catalog_package() -> CanonicalCatalogPackage:
    bridge_artifacts = build_wahapedia_canonical_bridge_artifacts(
        source_artifacts=july_defiler_overlay_artifacts(),
        bridge_package_id=DataPackageId(
            namespace="core-v2",
            package_name="july-thousand-sons-defiler-11e-bridge-test",
            version="2026-07-22",
        ),
        datasheet_ids=july_defiler_overlay.ALIGNED_DEFILER_DATASHEET_IDS,
        height_overrides=CHAOS_DEFILER_HEIGHT_OVERRIDES,
    )
    return build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace="core-v2",
            package_name="july-thousand-sons-defiler-11e-catalog-test",
            version="2026-07-22",
        ),
        catalog_version=july_defiler_overlay.CATALOG_VERSION,
        source_artifacts=bridge_artifacts,
    )


def instantiate_defiler(
    *,
    package: CanonicalCatalogPackage,
    datasheet_id: str,
    wargear_selections: tuple[WargearSelection, ...] = (),
) -> UnitInstance:
    datasheet = package.army_catalog.datasheet_by_id(datasheet_id)
    return UnitFactory(
        catalog=package.army_catalog,
        model_geometries=package.model_geometries,
    ).instantiate_unit(
        army_id="chaos-defiler-test-army",
        selection=UnitMusterSelection(
            unit_selection_id=f"defiler-{datasheet_id}",
            datasheet_id=datasheet_id,
            model_profile_selections=(
                ModelProfileSelection(
                    model_profile_id=f"{datasheet_id}:defiler",
                    model_count=1,
                ),
            ),
            wargear_selections=wargear_selections,
        ),
        datasheet=datasheet,
    )


@lru_cache(maxsize=1)
def defiler_overlay_artifacts() -> tuple[OverlaySourceArtifact, ...]:
    return apply_source_release_overlays(
        source_artifacts=_wahapedia_source_artifacts(),
        release_manifest=defiler_overlay.source_release_manifest(),
        overlay_packs=(defiler_overlay.overlay_pack(),),
    )


@lru_cache(maxsize=1)
def july_defiler_overlay_artifacts() -> tuple[OverlaySourceArtifact, ...]:
    return apply_source_release_overlays(
        source_artifacts=_wahapedia_source_artifacts(),
        release_manifest=july_defiler_overlay.source_release_manifest(),
        overlay_packs=(july_defiler_overlay.overlay_pack(),),
    )


@lru_cache(maxsize=1)
def _wahapedia_source_artifacts() -> tuple[WahapediaJsonArtifact, ...]:
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in _REQUIRED_TABLES:
        payload = json.loads(
            (_WAHAPEDIA_10E_JSON / f"{table_name}.json").read_text(encoding="utf-8")
        )
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


__all__ = (
    "defiler_catalog_package",
    "defiler_overlay_artifacts",
    "instantiate_defiler",
    "july_defiler_catalog_package",
    "july_defiler_overlay_artifacts",
)
