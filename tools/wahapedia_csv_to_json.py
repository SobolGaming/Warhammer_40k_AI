from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_catalog import SourceFileChecksum, SourcePackageManifest
from warhammer40k_core.rules.wahapedia_schema import (
    WahapediaCsvTable,
    WahapediaJsonArtifact,
    WahapediaSourceSnapshot,
)


def build_wahapedia_json_artifacts(
    *,
    input_dir: Path,
    output_dir: Path,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    upstream_identity: str,
    source_edition: str,
    csv_delimiter: str = ",",
) -> SourcePackageManifest:
    csv_paths = tuple(sorted(input_dir.glob("*.csv")))
    if not csv_paths:
        raise ValueError("input_dir must contain at least one CSV file.")

    source_files = tuple(
        SourceFileChecksum.from_path(root=input_dir, path=csv_path) for csv_path in csv_paths
    )
    snapshot = WahapediaSourceSnapshot(
        package_id=package_id,
        catalog_version=catalog_version,
        upstream_identity=upstream_identity,
        source_edition=source_edition,
        source_files=source_files,
    )

    output_dir.mkdir(parents=True, exist_ok=True)
    artifacts: list[WahapediaJsonArtifact] = []
    for csv_path, source_file in zip(csv_paths, source_files, strict=True):
        table = WahapediaCsvTable.from_csv_text(
            table_name=csv_path.stem,
            csv_text=csv_path.read_text(encoding="utf-8-sig"),
            delimiter=csv_delimiter,
        )
        artifact = WahapediaJsonArtifact.from_csv_table(
            source_package_id=package_id,
            table=table,
            source_checksum_sha256=source_file.checksum_sha256,
        )
        (output_dir / f"{artifact.source_table}.json").write_bytes(artifact.to_json_bytes())
        artifacts.append(artifact)

    manifest = snapshot.manifest(
        artifacts=tuple(artifact.source_artifact_hash() for artifact in artifacts)
    )
    (output_dir / "source_package_manifest.json").write_text(
        json.dumps(manifest.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build deterministic Phase 17A Wahapedia source-mirror JSON artifacts."
    )
    parser.add_argument("--input-dir", required=True)
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--package-namespace", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--upstream-identity", required=True)
    parser.add_argument("--source-edition", required=True)
    parser.add_argument("--csv-delimiter", default="|")
    args = parser.parse_args()

    build_wahapedia_json_artifacts(
        input_dir=Path(args.input_dir),
        output_dir=Path(args.output_dir),
        package_id=DataPackageId(
            namespace=args.package_namespace,
            package_name=args.package_name,
            version=args.package_version,
        ),
        catalog_version=CatalogVersion.dated(
            version_id=args.catalog_version,
            source_date=date.fromisoformat(args.source_date),
        ),
        upstream_identity=args.upstream_identity,
        source_edition=args.source_edition,
        csv_delimiter=args.csv_delimiter,
    )


if __name__ == "__main__":
    main()
