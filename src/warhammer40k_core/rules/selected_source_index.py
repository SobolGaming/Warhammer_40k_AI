"""Explicit, version-bound partitions of fully validated, overlaid source rows.

Building is deliberately separate from loading. No automatic regeneration, pickle,
mtime shortcut or process-global cache is used. The manifest is published last;
an interrupted build cannot be loaded. Canonical row payloads are preserved.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TypedDict, cast

from warhammer40k_core.core.validation import IdentifierValidator
from warhammer40k_core.rules.wahapedia_bridge_rows import (
    BridgeSourceArtifact,
    SelectedSourceRows,
    bridge_rows_by_table,
)
from warhammer40k_core.rules.wahapedia_schema import (
    NormalizedSourceRow,
    NormalizedSourceRowPayload,
)

INDEX_VERSION = "selected-source-index-v1"
OWNED_TABLES = frozenset(
    {
        "Datasheets_abilities",
        "Datasheets_keywords",
        "Datasheets_models",
        "Datasheets_models_cost",
        "Datasheets_options",
        "Datasheets_unit_composition",
        "Datasheets_wargear",
    }
)
GLOBAL_TABLES = frozenset({"Abilities", "Datasheets", "Factions", "Datasheets_leader"})


class SourceIndexError(ValueError):
    """A selected source index is absent, stale, corrupt or incomplete."""


class Partition(TypedDict):
    offset: int
    length: int
    sha256: str
    rows: int


class IndexedRow(TypedDict):
    ordinal: int
    row: NormalizedSourceRowPayload


class Manifest(TypedDict):
    version: str
    python: str
    inputs: dict[str, str]
    source_artifacts: list[dict[str, str]]
    partitions: dict[str, Partition]
    index_hash: str


def _json_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def source_input_hashes(input_files: tuple[Path, ...]) -> dict[str, str]:
    """Read every authoritative input; missing files propagate as explicit errors."""
    if not input_files or len(set(input_files)) != len(input_files):
        raise SourceIndexError("Index input files must be non-empty and unique.")
    return {str(path.resolve()): _sha256(path.read_bytes()) for path in sorted(input_files)}


def build_selected_source_index(
    directory: Path,
    *,
    input_files: tuple[Path, ...],
    load_sources: Callable[[], tuple[BridgeSourceArtifact, ...]],
) -> None:
    """Run full source/overlay validation once and generate a new index directory."""
    # Require a new destination; no partial update or replacement of an existing index.
    directory.mkdir(parents=True, exist_ok=False)
    before = source_input_hashes(input_files)
    artifacts = load_sources()
    rows_by_table = bridge_rows_by_table(artifacts, error_type=SourceIndexError)
    if frozenset(rows_by_table) != OWNED_TABLES | GLOBAL_TABLES:
        raise SourceIndexError("Index table scope changed; review the dependency partition.")
    groups: dict[str, list[IndexedRow]] = {"": []}
    for row in rows_by_table["Datasheets"]:
        groups.setdefault(row.source_row_id, [])
    for table, rows in rows_by_table.items():
        for ordinal, row in enumerate(rows):
            owner = (
                row.runtime_fields_payload()["datasheet_id"].strip()
                if table in OWNED_TABLES
                else ""
            )
            if table in OWNED_TABLES and not owner:
                raise SourceIndexError("Owned source row requires a datasheet identifier.")
            # Historical child rows can outlive a superseded global datasheet.
            # Preserve them; only active global datasheets are loadable below.
            groups.setdefault(owner, []).append({"ordinal": ordinal, "row": row.to_payload()})
    partitions: dict[str, Partition] = {}
    with (directory / "rows.jsonl").open("xb") as stream:
        for owner, records in sorted(groups.items()):
            data = json.dumps(records, separators=(",", ":")).encode("utf-8") + b"\n"
            partitions[owner] = {
                "offset": stream.tell(),
                "length": len(data),
                "sha256": _sha256(data),
                "rows": len(records),
            }
            stream.write(data)
    if source_input_hashes(input_files) != before:
        raise SourceIndexError("Source inputs changed during index construction.")
    manifest: Manifest = {
        "version": INDEX_VERSION,
        "python": sys.version,
        "inputs": before,
        "source_artifacts": [
            {
                "table": artifact.source_table,
                "hash": artifact.artifact_hash(),
                "package": artifact.source_package_id.stable_identity(),
            }
            for artifact in artifacts
        ],
        "partitions": partitions,
        "index_hash": "",
    }
    manifest["index_hash"] = _sha256(_json_bytes(manifest))
    with (directory / "manifest.json").open("xb") as stream:
        stream.write(_json_bytes(manifest))


def load_selected_source_rows(
    directory: Path,
    *,
    input_files: tuple[Path, ...],
    datasheet_ids: tuple[str, ...],
) -> SelectedSourceRows:
    """Validate versions and input bytes, then validate only dependency partitions.

    Shared tables retain all ability variants, leader endpoints and datasheet
    geometry references, including cross-faction references. Child tables are
    indexed by their owner; no inferred army/faction filtering is performed.
    """
    if type(datasheet_ids) is not tuple or not datasheet_ids:
        raise SourceIndexError("Selected datasheets must be a non-empty tuple of identifiers.")
    validate = IdentifierValidator(SourceIndexError)
    datasheet_ids = tuple(validate("Selected datasheet", value) for value in datasheet_ids)
    manifest = cast(Manifest, json.loads((directory / "manifest.json").read_bytes()))
    expected_hash = manifest["index_hash"]
    manifest["index_hash"] = ""
    if _sha256(_json_bytes(manifest)) != expected_hash:
        raise SourceIndexError("Source index manifest hash mismatch.")
    if manifest["version"] != INDEX_VERSION or manifest["python"] != sys.version:
        raise SourceIndexError("Source index builder version changed; rebuild explicitly.")
    if source_input_hashes(input_files) != manifest["inputs"]:
        raise SourceIndexError("Source index inputs changed; rebuild explicitly.")
    partitions = manifest["partitions"]
    owners = ("", *sorted(set(datasheet_ids)))
    if any(owner not in partitions for owner in owners):
        raise SourceIndexError("Selected datasheet is absent from the source index.")
    offset = 0
    for partition in partitions.values():
        if (
            type(partition["offset"]) is not int
            or type(partition["length"]) is not int
            or partition["offset"] != offset
            or partition["length"] <= 0
            or type(partition["rows"]) is not int
            or partition["rows"] < 0
        ):
            raise SourceIndexError("Source index partition ranges are invalid.")
        offset += partition["length"]
    ordered: dict[str, list[tuple[int, NormalizedSourceRow]]] = {
        table: [] for table in sorted(OWNED_TABLES | GLOBAL_TABLES)
    }
    with (directory / "rows.jsonl").open("rb") as stream:
        if stream.seek(0, 2) != offset:
            raise SourceIndexError("Source index data length changed.")
        for owner in owners:
            part = partitions[owner]
            stream.seek(part["offset"])
            data = stream.read(part["length"])
            if _sha256(data) != part["sha256"]:
                raise SourceIndexError("Source index partition hash mismatch.")
            records = cast(list[IndexedRow], json.loads(data))
            if len(records) != part["rows"]:
                raise SourceIndexError("Source index partition row count changed.")
            for record in records:
                row = NormalizedSourceRow.from_payload(record["row"])
                if row.source_table not in ordered:
                    raise SourceIndexError("Source index row table is invalid.")
                actual_owner = (
                    row.runtime_fields_payload()["datasheet_id"].strip()
                    if row.source_table in OWNED_TABLES
                    else ""
                )
                if (
                    actual_owner != owner
                    or type(record["ordinal"]) is not int
                    or record["ordinal"] < 0
                ):
                    raise SourceIndexError("Source index row owner or order changed.")
                ordered[row.source_table].append((record["ordinal"], row))
    if source_input_hashes(input_files) != manifest["inputs"]:
        raise SourceIndexError("Source inputs changed during selected loading.")
    result: list[tuple[str, tuple[NormalizedSourceRow, ...]]] = []
    for table, entries in ordered.items():
        if len({ordinal for ordinal, _ in entries}) != len(entries):
            raise SourceIndexError("Source index row ordinals must be unique per table.")
        result.append((table, tuple(row for _, row in sorted(entries, key=lambda item: item[0]))))
    active_ids = {row.source_row_id for _, row in ordered["Datasheets"]}
    if not set(datasheet_ids).issubset(active_ids):
        raise SourceIndexError("Selected datasheet has no active source record.")
    return SelectedSourceRows(tuple(result), tuple(sorted(set(datasheet_ids))))
