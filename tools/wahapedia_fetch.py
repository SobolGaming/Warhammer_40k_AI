from __future__ import annotations

import argparse
import json
import urllib.request
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_catalog import SourceFileChecksum
from warhammer40k_core.rules.wahapedia_schema import WahapediaSourceSnapshot


@dataclass(frozen=True, slots=True)
class WahapediaFetchSource:
    url: str
    relative_path: str

    def __post_init__(self) -> None:
        if type(self.url) is not str:
            raise ValueError("WahapediaFetchSource URL must be a string.")
        if type(self.relative_path) is not str:
            raise ValueError("WahapediaFetchSource relative path must be a string.")
        url = self.url.strip()
        relative_path = _validate_source_relative_path(self.relative_path)
        if not url:
            raise ValueError("WahapediaFetchSource URL must not be empty.")
        object.__setattr__(self, "url", url)
        object.__setattr__(self, "relative_path", relative_path)


def fetch_wahapedia_sources(
    *,
    sources: tuple[WahapediaFetchSource, ...],
    output_dir: Path,
    package_id: DataPackageId,
    catalog_version: CatalogVersion,
    upstream_identity: str,
    source_edition: str,
) -> WahapediaSourceSnapshot:
    if not sources:
        raise ValueError("At least one source URL is required.")
    output_dir.mkdir(parents=True, exist_ok=True)
    written_paths: list[Path] = []
    for source in sources:
        target_path = _target_path_inside_output_dir(output_dir, source.relative_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with urllib.request.urlopen(source.url) as response:
            target_path.write_bytes(response.read())
        written_paths.append(target_path)

    snapshot = WahapediaSourceSnapshot(
        package_id=package_id,
        catalog_version=catalog_version,
        upstream_identity=upstream_identity,
        source_edition=source_edition,
        source_files=tuple(
            SourceFileChecksum.from_path(root=output_dir, path=path) for path in written_paths
        ),
    )
    (output_dir / "source_snapshot.json").write_text(
        json.dumps(snapshot.to_payload(), sort_keys=True, indent=2),
        encoding="utf-8",
    )
    return snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch Wahapedia CSV/source files and record Phase 17A checksums."
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--package-namespace", required=True)
    parser.add_argument("--package-name", required=True)
    parser.add_argument("--package-version", required=True)
    parser.add_argument("--catalog-version", required=True)
    parser.add_argument("--source-date", required=True)
    parser.add_argument("--upstream-identity", required=True)
    parser.add_argument("--source-edition", required=True)
    parser.add_argument(
        "--source",
        action="append",
        required=True,
        help="Source mapping in URL=relative/path.csv form.",
    )
    args = parser.parse_args()
    source_mappings = tuple(_source_from_argument(value) for value in args.source)
    fetch_wahapedia_sources(
        sources=source_mappings,
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
    )


def _source_from_argument(value: str) -> WahapediaFetchSource:
    if "=" not in value:
        raise ValueError("--source must use URL=relative/path.csv form.")
    url, relative_path = value.split("=", 1)
    return WahapediaFetchSource(url=url, relative_path=relative_path)


def _target_path_inside_output_dir(output_dir: Path, relative_path: str) -> Path:
    rel = Path(_validate_source_relative_path(relative_path))
    resolved_output_dir = output_dir.resolve()
    resolved_target = (resolved_output_dir / rel).resolve()
    if (
        resolved_target != resolved_output_dir
        and resolved_output_dir not in resolved_target.parents
    ):
        raise ValueError("--source target path must be inside output-dir.")
    return resolved_target


def _validate_source_relative_path(relative_path: str) -> str:
    path = relative_path.strip()
    if not path:
        raise ValueError("--source relative path must not be empty.")
    windows_path = PureWindowsPath(path)
    path_views = (Path(path), PurePosixPath(path), windows_path)
    if any(path_view.is_absolute() for path_view in path_views) or any(
        part == ".." for path_view in path_views for part in path_view.parts
    ):
        raise ValueError("--source relative path must be relative and must not contain '..'.")
    if windows_path.drive or windows_path.root:
        raise ValueError("--source relative path must be relative and must not contain '..'.")
    return path


if __name__ == "__main__":
    main()
