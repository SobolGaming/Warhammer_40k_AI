from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path
from urllib.request import Request, urlopen

from warhammer40k_core.rules.mfm_source import (
    MfmFactionRecord,
    MfmIndexFaction,
    MfmSourceError,
    MfmSourcePackage,
    parse_mfm_faction_html,
    parse_mfm_index_html,
    parse_mfm_version_html,
)

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = (
    ROOT
    / "src"
    / "warhammer40k_core"
    / "rules"
    / "source_packages"
    / "warhammer_40000_11th"
    / "mfm_2026_07"
)
SOURCE_URL = "https://mfm.warhammer-community.com/en/"
SOURCE_PACKAGE_ID = "gw-11e-mfm-2026-07"
SOURCE_TITLE = "Warhammer 40,000: Munitorum Field Manual"
SOURCE_VERSION = "v1.1"
SOURCE_DATE = "2026-07-22"
EXCLUDED_FACTION_IDS = ("chaos-titan-legions", "titan-legions")


class MfmImportToolError(ValueError):
    """Raised when the MFM import tool cannot build the source package."""


def main() -> None:
    args = _parse_args()
    index_html = _fetch_url(SOURCE_URL, use_curl=args.use_curl)
    _validate_source_version(html=index_html, url=SOURCE_URL)
    factions = tuple(
        faction
        for faction in parse_mfm_index_html(index_html)
        if faction.faction_id not in EXCLUDED_FACTION_IDS
    )
    if not factions:
        raise MfmImportToolError("MFM import found no supported factions.")

    records: list[MfmFactionRecord] = []
    for faction in factions:
        faction_url = _absolute_url(faction)
        faction_html = _fetch_url(faction_url, use_curl=args.use_curl)
        _validate_source_version(html=faction_html, url=faction_url)
        try:
            records.append(
                parse_mfm_faction_html(
                    html=faction_html,
                    faction=faction,
                    source_package_id=SOURCE_PACKAGE_ID,
                )
            )
        except MfmSourceError as exc:
            raise MfmImportToolError(
                f"MFM faction import failed for {faction.faction_id}."
            ) from exc
    package = MfmSourcePackage(
        source_package_id=SOURCE_PACKAGE_ID,
        source_title=SOURCE_TITLE,
        source_version=SOURCE_VERSION,
        source_date=SOURCE_DATE,
        source_url=SOURCE_URL,
        excluded_faction_ids=EXCLUDED_FACTION_IDS,
        factions=tuple(records),
    )
    output_path = args.output
    output_path.mkdir(parents=True, exist_ok=True)
    _write_package_artifacts(output_path=output_path, package=package)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import live Warhammer Community MFM points into a source package."
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Generated source-package artifact directory path.",
    )
    parser.add_argument(
        "--use-curl",
        action="store_true",
        help="Fetch pages through curl instead of urllib.",
    )
    return parser.parse_args()


def _fetch_url(url: str, *, use_curl: bool) -> str:
    if use_curl:
        completed = subprocess.run(
            ("curl", "-L", "--compressed", "-s", url),
            check=True,
            capture_output=True,
            text=True,
        )
        return completed.stdout
    request = Request(url, headers={"User-Agent": "warhammer40k-core-v2-mfm-importer/1"})
    with urlopen(request, timeout=30) as response:
        body = response.read()
        if type(body) is not bytes:
            raise MfmImportToolError("MFM import received a non-bytes HTTP response body.")
        return body.decode("utf-8")


def _absolute_url(faction: MfmIndexFaction) -> str:
    return "https://mfm.warhammer-community.com" + faction.url_path


def _validate_source_version(*, html: str, url: str) -> None:
    actual_version = parse_mfm_version_html(html)
    if actual_version != SOURCE_VERSION:
        raise MfmImportToolError(
            f"MFM source version drift at {url}: expected {SOURCE_VERSION}, got {actual_version}."
        )


def _write_package_artifacts(*, output_path: Path, package: MfmSourcePackage) -> None:
    artifacts_path = output_path / "artifacts"
    factions_path = artifacts_path / "factions"
    factions_path.mkdir(parents=True, exist_ok=True)

    for path in output_path.glob("*.py"):
        if path.name not in {"__init__.py", "_artifacts.py"}:
            path.unlink()

    expected_faction_artifacts = {f"{faction.faction_id}.json" for faction in package.factions}
    for path in factions_path.glob("*.json"):
        if path.name not in expected_faction_artifacts:
            path.unlink()

    for faction in package.factions:
        artifact_path = factions_path / f"{faction.faction_id}.json"
        artifact_path.write_text(_json_artifact_text(faction.to_payload()), encoding="utf-8")

    manifest = {
        "artifact_schema": "core-v2-mfm-source-package-v2",
        "source_package_id": package.source_package_id,
        "source_title": package.source_title,
        "source_version": package.source_version,
        "source_date": package.source_date,
        "source_url": package.source_url,
        "excluded_faction_ids": list(package.excluded_faction_ids),
        "faction_artifacts": {
            faction.faction_id: f"factions/{faction.faction_id}.json"
            for faction in package.factions
        },
        "source_payload_checksum_sha256": package.source_payload_checksum_sha256(),
    }
    (artifacts_path / "package.json").write_text(_json_artifact_text(manifest), encoding="utf-8")


def _json_artifact_text(payload: object) -> str:
    return json.dumps(payload, sort_keys=True, indent=2) + "\n"


if __name__ == "__main__":
    main()
