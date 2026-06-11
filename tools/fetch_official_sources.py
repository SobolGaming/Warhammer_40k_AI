from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, TypedDict


class OfficialSourceFetchError(ValueError):
    """Raised when an official source manifest or download violates local-cache policy."""


class OfficialSourceManifestEntryPayload(TypedDict, total=False):
    package_id: str
    title: str
    source_url: str
    source_page_url: str
    publisher: str
    language: str
    edition: str
    source_date: str
    retrieved_at: str
    sha256: str
    bytes: int
    license_note: str
    local_cache_path: str


@dataclass(frozen=True, slots=True)
class OfficialSourceManifestEntry:
    package_id: str
    title: str
    source_url: str
    source_page_url: str
    publisher: str
    language: str
    edition: str
    source_date: str
    sha256: str
    expected_bytes: int | None
    license_note: str
    local_cache_path: str | None

    @classmethod
    def from_mapping(cls, raw_payload: dict[object, object]) -> OfficialSourceManifestEntry:
        payload = _string_key_mapping(raw_payload)
        expected_bytes = payload.get("bytes")
        if expected_bytes is not None and type(expected_bytes) is not int:
            raise OfficialSourceFetchError("Official source bytes must be an integer.")
        return cls(
            package_id=_required_string(payload, "package_id"),
            title=_required_string(payload, "title"),
            source_url=_required_string(payload, "source_url"),
            source_page_url=_required_string(payload, "source_page_url"),
            publisher=_required_string(payload, "publisher"),
            language=_required_string(payload, "language"),
            edition=_required_string(payload, "edition"),
            source_date=_required_string(payload, "source_date"),
            sha256=_optional_string(payload, "sha256"),
            expected_bytes=expected_bytes,
            license_note=_required_string(payload, "license_note"),
            local_cache_path=_optional_string_or_none(payload, "local_cache_path"),
        )


@dataclass(frozen=True, slots=True)
class OfficialSourceFetchResult:
    entry: OfficialSourceManifestEntry
    cache_path: Path
    sha256: str
    bytes_written: int
    retrieved_at: str

    def to_payload(self) -> OfficialSourceManifestEntryPayload:
        return {
            "package_id": self.entry.package_id,
            "title": self.entry.title,
            "source_url": self.entry.source_url,
            "source_page_url": self.entry.source_page_url,
            "publisher": self.entry.publisher,
            "language": self.entry.language,
            "edition": self.entry.edition,
            "source_date": self.entry.source_date,
            "retrieved_at": self.retrieved_at,
            "sha256": self.sha256,
            "bytes": self.bytes_written,
            "license_note": self.entry.license_note,
            "local_cache_path": self.cache_path.as_posix(),
        }


def fetch_official_sources(
    *,
    manifest_path: Path,
    cache_dir: Path,
    refresh: bool = False,
    metadata_out: Path | None = None,
) -> tuple[OfficialSourceFetchResult, ...]:
    entries = _load_manifest_entries(manifest_path)
    cache_dir.mkdir(parents=True, exist_ok=True)
    resolved_cache_dir = cache_dir.resolve()
    results: list[OfficialSourceFetchResult] = []
    for entry in entries:
        cache_path = _cache_path_for_entry(entry=entry, cache_dir=cache_dir)
        resolved_cache_path = cache_path.resolve()
        if resolved_cache_path != resolved_cache_dir and resolved_cache_dir not in (
            resolved_cache_path.parents
        ):
            raise OfficialSourceFetchError("Official source cache path must be inside cache-dir.")

        data = _download(entry.source_url)
        sha256 = _sha256(data)
        if entry.sha256 and entry.sha256 != sha256 and not refresh:
            raise OfficialSourceFetchError(
                f"Hash drift for {entry.package_id}: expected {entry.sha256}, got {sha256}."
            )
        if entry.expected_bytes is not None and entry.expected_bytes != len(data) and not refresh:
            raise OfficialSourceFetchError(
                f"Byte-count drift for {entry.package_id}: "
                f"expected {entry.expected_bytes}, got {len(data)}."
            )

        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_bytes(data)
        results.append(
            OfficialSourceFetchResult(
                entry=entry,
                cache_path=cache_path,
                sha256=sha256,
                bytes_written=len(data),
                retrieved_at=datetime.now(UTC).replace(microsecond=0).isoformat(),
            )
        )

    if metadata_out is not None:
        metadata_out.parent.mkdir(parents=True, exist_ok=True)
        metadata_out.write_text(
            json.dumps([result.to_payload() for result in results], sort_keys=True, indent=2),
            encoding="utf-8",
        )
    return tuple(results)


def load_official_source_manifest(
    manifest_path: Path,
) -> tuple[OfficialSourceManifestEntry, ...]:
    return _load_manifest_entries(manifest_path)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fetch official GW source PDFs into an ignored local cache and verify hashes."
    )
    parser.add_argument("--manifest", required=True, type=Path)
    parser.add_argument("--cache-dir", required=True, type=Path)
    parser.add_argument("--metadata-out", type=Path)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Allow changed hash/byte metadata and emit refreshed metadata.",
    )
    args = parser.parse_args()
    results = fetch_official_sources(
        manifest_path=args.manifest,
        cache_dir=args.cache_dir,
        refresh=args.refresh,
        metadata_out=args.metadata_out,
    )
    print(json.dumps([result.to_payload() for result in results], sort_keys=True, indent=2))


def _load_manifest_entries(manifest_path: Path) -> tuple[OfficialSourceManifestEntry, ...]:
    text = manifest_path.read_text(encoding="utf-8")
    payload = _load_json_or_simple_yaml(manifest_path=manifest_path, text=text)
    if isinstance(payload, list):
        raw_entries = payload
    elif isinstance(payload, dict) and isinstance(payload.get("sources"), list):
        raw_entries = payload["sources"]
    elif isinstance(payload, dict):
        raw_entries = [payload]
    else:
        raise OfficialSourceFetchError("Official source manifest must be a mapping or list.")

    entries: list[OfficialSourceManifestEntry] = []
    for raw_entry in raw_entries:
        if not isinstance(raw_entry, dict):
            raise OfficialSourceFetchError("Official source manifest entries must be mappings.")
        entries.append(OfficialSourceManifestEntry.from_mapping(raw_entry))
    if not entries:
        raise OfficialSourceFetchError("Official source manifest must contain at least one source.")
    return tuple(entries)


def _load_json_or_simple_yaml(*, manifest_path: Path, text: str) -> Any:
    stripped = text.strip()
    if manifest_path.suffix.lower() == ".json" or stripped.startswith(("{", "[")):
        return json.loads(text)
    return _load_simple_yaml_mapping_or_list(text)


def _load_simple_yaml_mapping_or_list(text: str) -> dict[str, object] | list[dict[str, object]]:
    lines = tuple(
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    )
    if not lines:
        raise OfficialSourceFetchError("Official source manifest must not be empty.")
    if lines[0].strip() == "sources:":
        entries: list[dict[str, object]] = []
        current: dict[str, object] | None = None
        for line in lines[1:]:
            stripped = line.strip()
            if stripped.startswith("- "):
                if current is not None:
                    entries.append(current)
                current = {}
                first_field = stripped.removeprefix("- ").strip()
                if first_field:
                    key, value = _parse_yaml_scalar_field(first_field)
                    current[key] = value
                continue
            if current is None:
                raise OfficialSourceFetchError("YAML source list field appears before an item.")
            key, value = _parse_yaml_scalar_field(stripped)
            current[key] = value
        if current is not None:
            entries.append(current)
        return entries

    mapping: dict[str, object] = {}
    for line in lines:
        key, value = _parse_yaml_scalar_field(line.strip())
        mapping[key] = value
    return mapping


def _parse_yaml_scalar_field(line: str) -> tuple[str, object]:
    if ":" not in line:
        raise OfficialSourceFetchError("Only scalar YAML key/value fields are supported.")
    key, raw_value = line.split(":", 1)
    key = key.strip()
    value = raw_value.strip()
    if not key:
        raise OfficialSourceFetchError("YAML manifest keys must not be empty.")
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    if value.isdecimal():
        return key, int(value)
    return key, value


def _string_key_mapping(raw_entry: dict[object, object]) -> dict[str, object]:
    payload: dict[str, object] = {}
    for key, value in raw_entry.items():
        if type(key) is not str:
            raise OfficialSourceFetchError("Official source manifest keys must be strings.")
        payload[key] = value
    return payload


def _cache_path_for_entry(*, entry: OfficialSourceManifestEntry, cache_dir: Path) -> Path:
    if entry.local_cache_path is None:
        return cache_dir / f"{entry.package_id}.pdf"
    cache_path = Path(entry.local_cache_path)
    if cache_path.is_absolute():
        return cache_path
    return Path.cwd() / cache_path


def _download(source_url: str) -> bytes:
    with urllib.request.urlopen(source_url, timeout=60) as response:
        data = response.read()
    if type(data) is not bytes:
        raise OfficialSourceFetchError("Official source download did not return bytes.")
    return data


def _sha256(data: bytes) -> str:
    import hashlib

    return hashlib.sha256(data).hexdigest()


def _required_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if type(value) is not str or not value.strip():
        raise OfficialSourceFetchError(f"Official source manifest requires {key}.")
    return value.strip()


def _optional_string(payload: dict[str, object], key: str) -> str:
    value = payload.get(key, "")
    if type(value) is not str:
        raise OfficialSourceFetchError(f"Official source manifest field {key} must be a string.")
    return value.strip()


def _optional_string_or_none(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    if type(value) is not str:
        raise OfficialSourceFetchError(f"Official source manifest field {key} must be a string.")
    stripped = value.strip()
    return stripped if stripped else None


if __name__ == "__main__":
    try:
        main()
    except OfficialSourceFetchError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc
