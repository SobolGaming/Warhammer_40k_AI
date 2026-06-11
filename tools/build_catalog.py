from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import cast

from tools.build_model_geometry_overrides import load_model_geometry_overrides
from warhammer40k_core.rules.catalog_generation import build_canonical_catalog_package
from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_patch import PatchedSourceArtifact, PatchedSourceArtifactPayload
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaJsonArtifact,
    WahapediaJsonArtifactPayload,
)


def load_source_artifact(path: Path) -> WahapediaJsonArtifact | PatchedSourceArtifact:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if type(payload) is not dict:
        raise ValueError("Source artifact JSON must contain an object.")
    if "patch_package_hash" in payload:
        return PatchedSourceArtifact.from_payload(cast(PatchedSourceArtifactPayload, payload))
    return WahapediaJsonArtifact.from_payload(cast(WahapediaJsonArtifactPayload, payload))


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Phase 17B canonical catalog package.")
    parser.add_argument("--namespace", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--artifact", action="append", type=Path, required=True)
    parser.add_argument("--geometry-overrides", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    geometry_overrides = (
        ()
        if args.geometry_overrides is None
        else load_model_geometry_overrides(args.geometry_overrides)
    )
    package = build_canonical_catalog_package(
        package_id=DataPackageId(
            namespace=args.namespace,
            package_name=args.package_name,
            version=args.package_version,
        ),
        catalog_version=CatalogVersion(
            version_id=args.catalog_version,
            source_date=args.source_date,
        ),
        source_artifacts=tuple(load_source_artifact(path) for path in args.artifact),
        geometry_overrides=geometry_overrides,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(package.to_payload(), sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
