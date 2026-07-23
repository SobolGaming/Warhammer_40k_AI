from __future__ import annotations

import hashlib
import shutil
import subprocess
from pathlib import Path, PurePosixPath

from tools.fetch_official_sources import load_official_source_manifest

_FORBIDDEN_TRACKED_SOURCE_PATTERNS = (
    "data/raw/faction_packs/*.txt",
    "data/raw/faction_packs/extracted_pages/*.md",
    "data/raw/gw/**/*.pdf",
    "data/raw/gw/**/*.txt",
    "data/raw/gw/**/extracted_pages/*.md",
)
_TRACKED_FACTION_PACK_PDF_PATTERN = "data/raw/faction_packs/*.pdf"
_ROOT = Path(__file__).resolve().parents[2]
_FACTION_PACK_MANIFEST_PATHS = (
    _ROOT / "data" / "source_manifests" / "gw_11e_faction_packs.yaml",
    _ROOT / "data" / "source_manifests" / "gw_11e_pending_faction_packs_2026_07.yaml",
)
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
        "Official GW extracted source text/page files and generic data/raw/gw downloads "
        "must remain local-only cache files. Commit source manifests, hashes, structured "
        "patches, generated catalogs, and approved faction-pack PDFs instead:\n"
        + "\n".join(violations)
    )
    _assert_tracked_faction_pack_pdfs_match_manifest(tracked_files)


def test_official_gw_faction_pack_manifest_uses_tracked_pdf_policy() -> None:
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
        PurePosixPath(entry.local_cache_path or "").match("data/raw/faction_packs/*.pdf")
        for entry in entries
    )
    assert all(entry.sha256 and len(entry.sha256) == 64 for entry in entries)
    assert all(entry.expected_bytes is not None and entry.expected_bytes > 0 for entry in entries)
    assert all("tracked as source evidence" in entry.license_note for entry in entries)


def test_official_gw_pending_faction_pack_manifest_uses_evidence_only_policy() -> None:
    entries = load_official_source_manifest(_FACTION_PACK_MANIFEST_PATHS[1])

    assert len(entries) == 27
    assert all(
        entry.source_page_url == _OFFICIAL_WARHAMMER_40000_DOWNLOADS_PAGE for entry in entries
    )
    assert all(entry.source_date == "2026-07-22" for entry in entries)
    assert all(entry.package_id.endswith("-2026-07") for entry in entries)
    assert all(entry.local_cache_path is not None for entry in entries)
    assert all(
        PurePosixPath(entry.local_cache_path or "").match("data/raw/faction_packs/*.pdf")
        for entry in entries
    )
    assert all("not a semantic-support claim" in entry.license_note for entry in entries)


def _assert_tracked_faction_pack_pdfs_match_manifest(tracked_files: tuple[str, ...]) -> None:
    tracked_pdf_paths = tuple(
        path
        for path in tracked_files
        if PurePosixPath(path).match(_TRACKED_FACTION_PACK_PDF_PATTERN)
    )
    if not tracked_pdf_paths:
        return
    entries_by_path = {
        entry.local_cache_path: entry
        for manifest_path in _FACTION_PACK_MANIFEST_PATHS
        for entry in load_official_source_manifest(manifest_path)
        if entry.local_cache_path is not None
    }
    missing_from_manifest = tuple(path for path in tracked_pdf_paths if path not in entries_by_path)
    assert not missing_from_manifest, (
        "Tracked official faction-pack PDFs must be declared in the source manifest:\n"
        + "\n".join(missing_from_manifest)
    )
    drifted_files: list[str] = []
    for path in tracked_pdf_paths:
        entry = entries_by_path[path]
        pdf_bytes = (_ROOT / path).read_bytes()
        actual_sha256 = hashlib.sha256(pdf_bytes).hexdigest()
        if actual_sha256 != entry.sha256:
            drifted_files.append(f"{path}: sha256 {actual_sha256} != {entry.sha256}")
        if len(pdf_bytes) != entry.expected_bytes:
            drifted_files.append(f"{path}: bytes {len(pdf_bytes)} != {entry.expected_bytes}")
    assert not drifted_files, (
        "Tracked official faction-pack PDFs must match manifest hashes and byte counts:\n"
        + "\n".join(drifted_files)
    )


def _git_tracked_files() -> tuple[str, ...]:
    git = shutil.which("git")
    assert git is not None, "Official source redistribution policy test requires git on PATH."
    result = subprocess.run(
        [git, "ls-files"],
        check=True,
        capture_output=True,
        cwd=_ROOT,
        encoding="utf-8",
    )
    return tuple(line for line in result.stdout.splitlines() if line)
