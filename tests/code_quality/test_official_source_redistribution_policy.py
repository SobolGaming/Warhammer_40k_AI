from __future__ import annotations

import subprocess
from pathlib import Path, PurePosixPath

from tools.fetch_official_sources import load_official_source_manifest

_FORBIDDEN_TRACKED_SOURCE_PATTERNS = (
    "data/raw/faction_packs/*.pdf",
    "data/raw/faction_packs/*.txt",
    "data/raw/faction_packs/extracted_pages/*.md",
    "data/raw/gw/**/*.pdf",
    "data/raw/gw/**/*.txt",
    "data/raw/gw/**/extracted_pages/*.md",
)
_ROOT = Path(__file__).resolve().parents[2]
_OFFICIAL_WARHAMMER_40000_DOWNLOADS_PAGE = (
    "https://www.warhammer-community.com/en-gb/downloads/warhammer-40000/"
)


def test_official_gw_source_downloads_are_not_tracked() -> None:
    tracked_files = _git_tracked_files()
    violations = tuple(
        path
        for path in tracked_files
        if any(PurePosixPath(path).match(pattern) for pattern in _FORBIDDEN_TRACKED_SOURCE_PATTERNS)
    )

    assert not violations, (
        "Official GW source downloads must remain local-only cache files. "
        "Commit source manifests, hashes, structured patches, and generated catalogs instead:\n"
        + "\n".join(violations)
    )


def test_official_gw_faction_pack_manifest_uses_local_cache_policy() -> None:
    manifest_path = _ROOT / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
    entries = load_official_source_manifest(manifest_path)

    assert len(entries) == 28
    assert all(
        entry.source_page_url == _OFFICIAL_WARHAMMER_40000_DOWNLOADS_PAGE for entry in entries
    )
    assert all(
        entry.source_url.startswith("https://assets.warhammer-community.com/") for entry in entries
    )
    assert all(entry.local_cache_path is not None for entry in entries)
    assert all(
        PurePosixPath(entry.local_cache_path or "").match(".cache/gw/faction-packs/*.pdf")
        for entry in entries
    )
    assert all(entry.sha256 and len(entry.sha256) == 64 for entry in entries)
    assert all(entry.expected_bytes is not None and entry.expected_bytes > 0 for entry in entries)
    assert all("not redistributed" in entry.license_note for entry in entries)


def _git_tracked_files() -> tuple[str, ...]:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        encoding="utf-8",
    )
    return tuple(line for line in result.stdout.splitlines() if line)
