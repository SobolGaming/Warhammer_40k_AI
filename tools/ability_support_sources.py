from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING or __package__:
    from tools import aeldari_datasheet_semantic_coverage
else:
    import aeldari_datasheet_semantic_coverage
from warhammer40k_core.rules import selected_source_index, wahapedia_schema
from warhammer40k_core.rules.selected_source_index import build_selected_source_index
from warhammer40k_core.rules.source_overlay import (
    SourceOverlayPack,
    SourceOverlayPackPayload,
    SourceReleaseManifest,
    SourceReleaseManifestPayload,
    apply_source_release_overlays,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    aeldari_vyper_title_2026_10 as vyper_title_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_maulerfiend_datasheet_overlay_2026_07 as maulerfiend_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    chaos_space_marines_defiler_datasheet_overlay_2026_07 as csm_defiler_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_datasheet_overlay_2026_06 as emperors_children_overlay,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    emperors_children_profiles_2026_10 as emperors_children_profiles,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    thousand_sons_defiler_datasheet_overlay_2026_07 as chaos_defiler_overlay,
)
from warhammer40k_core.rules.wahapedia_bridge_rows import BridgeSourceArtifact
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)

REQUIRED_TABLES = (
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


def load_source_artifacts(source_json_dir: Path) -> tuple[WahapediaJsonArtifact, ...]:
    if not source_json_dir.is_dir():
        raise ValueError("Ability support matrix source JSON directory must exist.")
    artifacts: list[WahapediaJsonArtifact] = []
    for table_name in REQUIRED_TABLES:
        artifact_path = source_json_dir / f"{table_name}.json"
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        if type(payload) is not dict:
            raise ValueError("Wahapedia source artifact JSON must contain an object.")
        artifacts.append(
            WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
        )
    return tuple(artifacts)


def load_ability_support_sources(source_json_dir: Path) -> tuple[BridgeSourceArtifact, ...]:
    artifacts = load_source_artifacts(source_json_dir)
    chaos_overlaid_artifacts = apply_source_release_overlays(
        source_artifacts=artifacts,
        release_manifest=chaos_defiler_overlay.source_release_manifest(),
        overlay_packs=(chaos_defiler_overlay.overlay_pack(),),
    )
    csm_overlaid_artifacts = apply_source_release_overlays(
        source_artifacts=chaos_overlaid_artifacts,
        release_manifest=csm_defiler_overlay.source_release_manifest(),
        overlay_packs=(csm_defiler_overlay.overlay_pack(),),
    )
    emperors_children_overlaid_artifacts = apply_source_release_overlays(
        source_artifacts=csm_overlaid_artifacts,
        release_manifest=emperors_children_overlay.source_release_manifest(),
        overlay_packs=(emperors_children_overlay.overlay_pack(),),
    )
    current_ec_artifacts = apply_source_release_overlays(
        source_artifacts=emperors_children_overlaid_artifacts,
        release_manifest=emperors_children_profiles.source_release_manifest(),
        overlay_packs=(emperors_children_profiles.overlay_pack(),),
    )
    maulerfiend_overlaid_artifacts = apply_source_release_overlays(
        source_artifacts=current_ec_artifacts,
        release_manifest=maulerfiend_overlay.source_release_manifest(),
        overlay_packs=(maulerfiend_overlay.overlay_pack(),),
    )
    aeldari_overlay_pack = SourceOverlayPack.from_payload(
        cast(
            SourceOverlayPackPayload,
            json.loads(
                aeldari_datasheet_semantic_coverage.OVERLAY_PACK_PATH.read_text(encoding="utf-8")
            ),
        )
    )
    aeldari_tacoma_overlay_pack = SourceOverlayPack.from_payload(
        cast(
            SourceOverlayPackPayload,
            json.loads(
                aeldari_datasheet_semantic_coverage.TACOMA_OVERLAY_PACK_PATH.read_text(
                    encoding="utf-8"
                )
            ),
        )
    )
    aeldari_july_overlay_pack = SourceOverlayPack.from_payload(
        cast(
            SourceOverlayPackPayload,
            json.loads(
                aeldari_datasheet_semantic_coverage.JULY_OVERLAY_PACK_PATH.read_text(
                    encoding="utf-8"
                )
            ),
        )
    )
    aeldari_release_manifest = SourceReleaseManifest.from_payload(
        cast(
            SourceReleaseManifestPayload,
            json.loads(
                aeldari_datasheet_semantic_coverage.RELEASE_MANIFEST_PATH.read_text(
                    encoding="utf-8"
                )
            ),
        )
    )
    aeldari_overlaid_artifacts = apply_source_release_overlays(
        source_artifacts=maulerfiend_overlaid_artifacts,
        release_manifest=aeldari_release_manifest,
        overlay_packs=(
            aeldari_overlay_pack,
            aeldari_tacoma_overlay_pack,
            aeldari_july_overlay_pack,
        ),
    )
    return apply_source_release_overlays(
        source_artifacts=aeldari_overlaid_artifacts,
        release_manifest=vyper_title_overlay.source_release_manifest(),
        overlay_packs=(vyper_title_overlay.overlay_pack(),),
    )


def ability_support_index_inputs(source_json_dir: Path) -> tuple[Path, ...]:
    """Bind all source-processing code and authoritative bytes, including overlays.

    Hash bytes rather than timestamps. Conservative rules/core invalidation also
    catches added/deleted source-processing modules. Absolute paths intentionally
    require regeneration after moving a checkout.
    """
    rules = Path(wahapedia_schema.__file__).resolve().parent
    repo = rules.parents[2]
    coverage = aeldari_datasheet_semantic_coverage
    return tuple(
        sorted(
            {
                *(source_json_dir / f"{table}.json" for table in REQUIRED_TABLES),
                *rules.rglob("*.py"),
                *(rules.parent / "core").rglob("*.py"),
                rules.parent / "geometry" / "validation.py",
                Path(selected_source_index.__file__).resolve(),
                Path(__file__).resolve(),
                Path(coverage.__file__).resolve(),
                repo / "uv.lock",
                repo / "pyproject.toml",
                coverage.OVERLAY_PACK_PATH,
                coverage.TACOMA_OVERLAY_PACK_PATH,
                coverage.JULY_OVERLAY_PACK_PATH,
                coverage.RELEASE_MANIFEST_PATH,
                Path(vyper_title_overlay.__file__).with_name(vyper_title_overlay.ARTIFACT_NAME),
                Path(emperors_children_profiles.__file__).with_name(
                    emperors_children_profiles.ARTIFACT_NAME
                ),
            }
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Build validated selected-army source partitions.")
    parser.add_argument("source_json_dir", type=Path)
    parser.add_argument(
        "index_dir", type=Path, help="New directory; existing indexes are never overwritten."
    )
    args = parser.parse_args()
    build_selected_source_index(
        args.index_dir,
        input_files=ability_support_index_inputs(args.source_json_dir),
        load_sources=lambda: load_ability_support_sources(args.source_json_dir),
    )


if __name__ == "__main__":
    main()
