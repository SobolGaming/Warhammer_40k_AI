from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path
from typing import cast

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_overlay import (
    OverlaySourceArtifact,
    OverlaySourceArtifactPayload,
)
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact, PatchedSourceArtifactPayload
from warhammer40k_core.rules.source_reference_generation import (
    SourceReferenceCatalog,
    build_source_reference_catalog,
)
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)


def build_source_references_from_dir(
    *,
    input_dir: Path,
    output_path: Path,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    target_edition: str,
) -> SourceReferenceCatalog:
    catalog = build_source_reference_catalog(
        package_id=package_id,
        catalog_version=catalog_version,
        target_edition=target_edition,
        source_artifacts=_load_source_artifacts(input_dir),
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(catalog.to_json_bytes())
    return catalog


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic source-reference catalog JSON from source artifacts."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-path", required=True)
    parser.add_argument("--package-namespace", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--target-edition", required=True)
    args = parser.parse_args()

    build_source_references_from_dir(
        input_dir=Path(args.input_dir),
        output_path=Path(args.output_path),
        package_id=DataPackageId(
            namespace=args.package_namespace,
            package_name=args.package_name,
            version=args.package_version,
        ),
        catalog_version=CatalogVersion.dated(
            version_id=args.catalog_version,
            source_date=date.fromisoformat(args.source_date),
        ),
        target_edition=args.target_edition,
    )


def _load_source_artifacts(
    input_dir: Path,
) -> tuple[
    WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact,
    ...,
]:
    artifacts: list[WahapediaJsonArtifact | PatchedSourceArtifact | OverlaySourceArtifact] = []
    for path in sorted(input_dir.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        if "overlay_package_hashes" in payload:
            artifacts.append(
                OverlaySourceArtifact.from_payload(cast(OverlaySourceArtifactPayload, payload))
            )
        elif "patch_package_hash" in payload:
            artifacts.append(
                PatchedSourceArtifact.from_payload(cast(PatchedSourceArtifactPayload, payload))
            )
        elif "source_checksum_sha256" in payload:
            artifacts.append(
                WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))
            )
    if not artifacts:
        raise ValueError("input_dir must contain at least one source artifact JSON file.")
    return tuple(artifacts)


if __name__ == "__main__":
    main()
