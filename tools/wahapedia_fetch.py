from __future__ import annotations

import argparse
import io
import json
import urllib.parse
import urllib.request
import zipfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path, PurePosixPath, PureWindowsPath
from xml.etree import ElementTree

from warhammer40k_core.rules.data_package import CatalogVersion, DataPackageId
from warhammer40k_core.rules.source_catalog import SourceFileChecksum
from warhammer40k_core.rules.wahapedia_schema import (
    EditionSourceConfig,
    WahapediaSourceSnapshot,
)

_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
_SPREADSHEET_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_OFFICE_RELATIONSHIP_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"


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


def discover_wahapedia_sources_from_export_specs(
    *,
    xlsx_bytes: bytes,
    source_config: EditionSourceConfig,
) -> tuple[WahapediaFetchSource, ...]:
    if type(xlsx_bytes) is not bytes:
        raise ValueError("xlsx_bytes must be bytes.")
    if type(source_config) is not EditionSourceConfig:
        raise ValueError("source_config must be EditionSourceConfig.")
    try:
        with zipfile.ZipFile(io.BytesIO(xlsx_bytes)) as archive:
            workbook_xml = archive.read("xl/workbook.xml")
            workbook_rels_xml = archive.read("xl/_rels/workbook.xml.rels")
            sheet_path = _english_sheet_path(
                workbook_xml=workbook_xml,
                workbook_rels_xml=workbook_rels_xml,
            )
            sheet_xml = archive.read(sheet_path)
            sheet_rels_path = _sheet_relationship_path(sheet_path)
            sheet_rels_xml = archive.read(sheet_rels_path)
    except zipfile.BadZipFile as exc:
        raise ValueError("Wahapedia export specs file must be a valid XLSX archive.") from exc
    except KeyError as exc:
        raise ValueError("Wahapedia export specs XLSX is missing required workbook parts.") from exc

    csv_targets = _csv_hyperlink_targets(
        sheet_xml=sheet_xml,
        sheet_rels_xml=sheet_rels_xml,
    )
    if not csv_targets:
        raise ValueError("Wahapedia export specs XLSX did not contain CSV hyperlinks.")

    discovered: list[WahapediaFetchSource] = []
    seen_paths: set[str] = set()
    for target in csv_targets:
        url = urllib.parse.urljoin(source_config.export_specs_url, target)
        _validate_wahapedia_source_url(url=url, source_config=source_config)
        parsed = urllib.parse.urlparse(url)
        filename = urllib.parse.unquote(PurePosixPath(parsed.path).name)
        relative_path = _validate_source_relative_path(filename)
        if relative_path in seen_paths:
            raise ValueError("Wahapedia export specs XLSX contains duplicate CSV filenames.")
        seen_paths.add(relative_path)
        discovered.append(WahapediaFetchSource(url=url, relative_path=relative_path))

    return tuple(sorted(discovered, key=lambda source: source.relative_path))


def discover_wahapedia_sources(
    *,
    source_config: EditionSourceConfig,
) -> tuple[WahapediaFetchSource, ...]:
    with urllib.request.urlopen(source_config.export_specs_url) as response:
        xlsx_bytes = response.read()
    return discover_wahapedia_sources_from_export_specs(
        xlsx_bytes=xlsx_bytes,
        source_config=source_config,
    )


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
        "--discover-edition",
        choices=("10th", "11th"),
        help="Discover CSV source mappings from Wahapedia's export spreadsheet.",
    )
    parser.add_argument(
        "--source",
        action="append",
        required=False,
        help="Source mapping in URL=relative/path.csv form.",
    )
    args = parser.parse_args()
    source_mappings = tuple(_source_from_argument(value) for value in args.source or ())
    if args.discover_edition is not None:
        source_config = _source_config_from_cli_token(args.discover_edition)
        if source_config.source_edition != args.source_edition:
            raise ValueError("--discover-edition source edition must match --source-edition.")
        discovered_sources = discover_wahapedia_sources(source_config=source_config)
        source_mappings = (*source_mappings, *discovered_sources)
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


def _source_config_from_cli_token(token: str) -> EditionSourceConfig:
    if token == "10th":
        return EditionSourceConfig.wahapedia_previous_edition_bridge()
    if token == "11th":
        return EditionSourceConfig.wahapedia_11th()
    raise ValueError("Unsupported --discover-edition token.")


def _english_sheet_path(*, workbook_xml: bytes, workbook_rels_xml: bytes) -> str:
    try:
        workbook_root = ElementTree.fromstring(workbook_xml)
        rels_root = ElementTree.fromstring(workbook_rels_xml)
    except ElementTree.ParseError as exc:
        raise ValueError("Wahapedia export specs workbook XML is malformed.") from exc
    relationship_targets = {
        rel.attrib["Id"]: rel.attrib["Target"]
        for rel in rels_root.findall(f"{{{_RELATIONSHIP_NS}}}Relationship")
        if "Id" in rel.attrib and "Target" in rel.attrib
    }
    for sheet in workbook_root.findall(f".//{{{_SPREADSHEET_NS}}}sheet"):
        if sheet.attrib.get("name") != "EN":
            continue
        rel_id = sheet.attrib.get(f"{{{_OFFICE_RELATIONSHIP_NS}}}id")
        if rel_id is None:
            raise ValueError("Wahapedia export specs EN sheet is missing a relationship ID.")
        target = relationship_targets.get(rel_id)
        if target is None:
            raise ValueError("Wahapedia export specs EN sheet relationship is missing.")
        return _workbook_part_path(target)
    raise ValueError("Wahapedia export specs XLSX is missing the EN sheet.")


def _workbook_part_path(target: str) -> str:
    path = PurePosixPath(target)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("Wahapedia export specs workbook relationship target is invalid.")
    if path.parts and path.parts[0] == "xl":
        return path.as_posix()
    return PurePosixPath("xl", path).as_posix()


def _sheet_relationship_path(sheet_path: str) -> str:
    path = PurePosixPath(sheet_path)
    if len(path.parts) < 2:
        raise ValueError("Wahapedia export specs sheet path is invalid.")
    return PurePosixPath(
        *path.parts[:-1],
        "_rels",
        f"{path.name}.rels",
    ).as_posix()


def _csv_hyperlink_targets(*, sheet_xml: bytes, sheet_rels_xml: bytes) -> tuple[str, ...]:
    try:
        sheet_root = ElementTree.fromstring(sheet_xml)
        rels_root = ElementTree.fromstring(sheet_rels_xml)
    except ElementTree.ParseError as exc:
        raise ValueError("Wahapedia export specs sheet XML is malformed.") from exc
    hyperlink_rel_ids = {
        hyperlink.attrib[f"{{{_OFFICE_RELATIONSHIP_NS}}}id"]
        for hyperlink in sheet_root.findall(f".//{{{_SPREADSHEET_NS}}}hyperlink")
        if f"{{{_OFFICE_RELATIONSHIP_NS}}}id" in hyperlink.attrib
    }
    targets: list[str] = []
    for rel in rels_root.findall(f"{{{_RELATIONSHIP_NS}}}Relationship"):
        rel_id = rel.attrib.get("Id")
        target = rel.attrib.get("Target")
        if rel_id not in hyperlink_rel_ids or target is None:
            continue
        parsed = urllib.parse.urlparse(target)
        if PurePosixPath(parsed.path).suffix.casefold() == ".csv":
            targets.append(target)
    return tuple(sorted(targets))


def _validate_wahapedia_source_url(*, url: str, source_config: EditionSourceConfig) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError("Discovered Wahapedia CSV URLs must use https.")
    if parsed.netloc.casefold() != "wahapedia.ru":
        raise ValueError("Discovered CSV URL host must be wahapedia.ru.")
    required_prefix = f"/{source_config.wahapedia_edition_slug}/"
    if not parsed.path.startswith(required_prefix):
        raise ValueError("Discovered CSV URL path does not match the requested edition.")
    if PurePosixPath(parsed.path).suffix.casefold() != ".csv":
        raise ValueError("Discovered source URL must reference a CSV file.")


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
