from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import replace
from pathlib import Path, PurePosixPath
from typing import cast
from urllib.parse import urlparse

import pytest
from tools.fetch_official_sources import load_official_source_manifest

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_subrules_2026_27 as faction_subrule_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    Phase17ECoverageKind,
    Phase17ECoverageRow,
    Phase17ECoverageStatus,
    Phase17EFactionCoverageError,
    Phase17EUnsupportedReason,
)

ROOT = Path(__file__).resolve().parents[2]
FACTION_PACK_MANIFEST = ROOT / "data" / "source_manifests" / "gw_11e_faction_packs.yaml"
RAW_FACTION_PDF_DIR = ROOT / "data" / "raw" / "faction_packs"
BRIDGE_JSON_DIR = (
    ROOT
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
)
APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS = frozenset(
    (
        "enhancement:aeldari:corsair-coterie:infamy",
        "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:assassins-eye-upgrade",
        "enhancement:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:camouflaged-snipers-upgrade",
        "enhancement:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:apocalyptic-steeds-upgrade",
        "enhancement:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:soul-shattering-charge-upgrade",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:casting-back-the-veil",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:eldritch-suppression",
        "stratagem:aeldari:path-of-the-outcast:aeldari:path-of-the-outcast:nomads-of-the-hidden-way",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:from-beyond-the-veil",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:inescapable-manifestations",
        "stratagem:chaos-daemons:cavalcade-of-chaos:chaos-daemons:cavalcade-of-chaos:warp-riders",
    )
)


def test_phase17e_payload_is_deterministic_json_safe_and_round_trips() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    payload = package.to_payload()

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert (
        payload["source_payload_checksum_sha256"]
        == (
            faction_coverage_source.source_package_identity_payload()[
                "source_payload_checksum_sha256"
            ]
        )
    )
    assert faction_coverage_source.Phase17ECoveragePackage.from_payload(payload) == package

    stale_payload = payload.copy()
    stale_payload["source_payload_checksum_sha256"] = "0" * 64
    with pytest.raises(Phase17EFactionCoverageError, match="checksum is stale"):
        faction_coverage_source.Phase17ECoveragePackage.from_payload(stale_payload)


def test_phase17e_exact_subrule_source_payloads_are_deterministic_and_validated() -> None:
    enhancement = next(
        row for row in faction_subrule_source.enhancement_rows() if row.runtime_consumer_ids
    )
    stratagem = next(
        row for row in faction_subrule_source.stratagem_rows() if row.runtime_consumer_ids
    )
    enhancement_payload = enhancement.to_payload()
    stratagem_payload = stratagem.to_payload()
    payload = {
        "identity": faction_subrule_source.source_package_identity_payload(),
        "enhancement": enhancement_payload,
        "stratagem": stratagem_payload,
    }

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert " object at 0x" not in encoded
    assert enhancement.source_id in enhancement_payload["source_ids"]
    assert stratagem.source_id in stratagem_payload["source_ids"]
    assert faction_subrule_source.SourceEnhancementRow.from_payload(enhancement_payload) == (
        enhancement
    )
    assert faction_subrule_source.SourceStratagemRow.from_payload(stratagem_payload) == stratagem

    with pytest.raises(ValueError, match="points"):
        replace(enhancement, points=-1)

    with pytest.raises(ValueError, match="must not be empty"):
        replace(enhancement, source_ids=())

    with pytest.raises(ValueError, match="command_point_cost"):
        replace(stratagem, command_point_cost=-1)

    with pytest.raises(ValueError, match="must be unique"):
        replace(stratagem, runtime_consumer_ids=("duplicate", "duplicate"))


def test_phase17e_exact_subrule_source_audit_accounts_for_every_bridge_input_row() -> None:
    skipped_rows = faction_subrule_source.skipped_bridge_rows()
    runtime_only_rows = faction_subrule_source.runtime_only_rows()
    identity = faction_subrule_source.source_package_identity_payload()
    emitted_bridge_source_ids = {
        source_id
        for row in faction_subrule_source.enhancement_rows()
        for source_id in row.source_ids
        if ":bridge-source-row:" in source_id
    }
    emitted_bridge_source_ids.update(
        source_id
        for row in faction_subrule_source.stratagem_rows()
        for source_id in row.source_ids
        if ":bridge-source-row:" in source_id
    )
    skipped_bridge_source_ids = {
        _bridge_source_id(row.table, row.bridge_source_row_id) for row in skipped_rows
    }
    bridge_input_source_ids = {
        _bridge_source_id(table, source_row_id)
        for table in ("Enhancements", "Stratagems")
        for source_row_id in _bridge_source_row_ids(table)
    }

    assert identity["skipped_bridge_row_count"] == str(len(skipped_rows))
    assert identity["runtime_only_row_count"] == str(len(runtime_only_rows))
    assert len(skipped_rows) == 601
    assert Counter(row.skip_reason for row in skipped_rows) == Counter(
        {
            "owner_not_in_current_source_package": 573,
            "missing_owner_fields": 28,
        }
    )
    assert emitted_bridge_source_ids.isdisjoint(skipped_bridge_source_ids)
    assert emitted_bridge_source_ids.union(skipped_bridge_source_ids) == bridge_input_source_ids
    assert all(
        row.skip_reason in faction_subrule_source.APPROVED_SKIPPED_BRIDGE_REASONS
        for row in skipped_rows
    )
    assert all(
        (row.derived_faction_id, row.derived_detachment_id)
        not in {
            (detachment.faction_id, detachment.detachment_id)
            for detachment in faction_detachment_source.detachment_rows()
        }
        for row in skipped_rows
        if row.skip_reason == "owner_not_in_current_source_package"
    )
    assert all(
        faction_subrule_source.SourceSkippedBridgeRow.from_payload(row.to_payload()) == row
        for row in skipped_rows[:3]
    )
    assert {row.source_row_id for row in runtime_only_rows} == APPROVED_RUNTIME_ONLY_SOURCE_ROW_IDS
    assert all(
        row.provenance_reason in faction_subrule_source.APPROVED_RUNTIME_ONLY_PROVENANCE_REASONS
        for row in runtime_only_rows
    )
    assert all(
        faction_subrule_source.SourceRuntimeOnlyRow.from_payload(row.to_payload()) == row
        for row in runtime_only_rows
    )


def test_phase17e_manifest_records_match_official_source_manifest() -> None:
    manifest_entries = load_official_source_manifest(FACTION_PACK_MANIFEST)
    entries_by_package_id = {entry.package_id: entry for entry in manifest_entries}
    records_by_package_id = {
        record.package_id: record for record in faction_coverage_source.faction_pdf_records()
    }

    assert len(manifest_entries) == len(faction_detachment_source.faction_rows())
    assert set(records_by_package_id) == set(entries_by_package_id)
    for package_id, record in records_by_package_id.items():
        entry = entries_by_package_id[package_id]
        assert record.title == entry.title
        assert record.source_date == entry.source_date
        assert record.sha256 == entry.sha256
        assert record.bytes == entry.expected_bytes
        assert record.pdf_filename == PurePosixPath(urlparse(entry.source_url).path).name
        assert entry.local_cache_path is not None
        assert record.pdf_filename == PurePosixPath(entry.local_cache_path).name


def test_phase17e_loads_every_seeded_faction_and_detachment() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    faction_rows = faction_detachment_source.faction_rows()
    detachment_rows = faction_detachment_source.detachment_rows()
    rows_by_kind = _rows_by_kind(package.coverage_rows)
    pdf_by_faction_id = {record.faction_id: record for record in package.pdf_records}

    assert set(pdf_by_faction_id) == {row.faction_id for row in faction_rows}
    assert len(rows_by_kind[Phase17ECoverageKind.FACTION_ARMY_RULE]) == len(faction_rows)
    assert len(rows_by_kind[Phase17ECoverageKind.DATASHEET_INTAKE]) == len(faction_rows)
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_RULE]) == len(detachment_rows)
    assert rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT_DESCRIPTORS] == []
    assert rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM_DESCRIPTORS] == []
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT]) == len(
        faction_subrule_source.enhancement_rows()
    )
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM]) == len(
        faction_subrule_source.stratagem_rows()
    )

    army_rule_rows = {
        row.faction_id: row for row in rows_by_kind[Phase17ECoverageKind.FACTION_ARMY_RULE]
    }
    datasheet_rows = {
        row.faction_id: row for row in rows_by_kind[Phase17ECoverageKind.DATASHEET_INTAKE]
    }
    detachment_rule_rows = _detachment_row_map(rows_by_kind[Phase17ECoverageKind.DETACHMENT_RULE])

    for faction_row in faction_rows:
        pdf_record = pdf_by_faction_id[faction_row.faction_id]
        army_row = army_rule_rows[faction_row.faction_id]
        datasheet_row = datasheet_rows[faction_row.faction_id]

        assert faction_row.source_id in army_row.source_ids
        assert pdf_record.source_id in army_row.source_ids
        assert army_row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
        assert army_row.handler_id == f"phase17e:faction:{faction_row.faction_id}:army-rule"
        assert faction_row.source_id in datasheet_row.source_ids
        assert pdf_record.source_id in datasheet_row.source_ids
        assert datasheet_row.unsupported_reason is (
            Phase17EUnsupportedReason.DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS
        )

    for detachment_row in detachment_rows:
        key = (detachment_row.faction_id, detachment_row.detachment_id)
        pdf_record = pdf_by_faction_id[detachment_row.faction_id]
        coverage_row = detachment_rule_rows[key]
        assert detachment_row.source_id in coverage_row.source_ids
        assert pdf_record.source_id in coverage_row.source_ids
        assert coverage_row.detachment_name == detachment_row.name
        assert coverage_row.force_disposition_id == detachment_row.force_disposition_id
        assert coverage_row.detachment_point_cost == detachment_row.detachment_point_cost
        assert coverage_row.is_new_for_eleventh is detachment_row.is_new_for_eleventh


def test_phase17e_exact_enhancement_and_stratagem_rows_cover_source_catalog() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    rows_by_kind = _rows_by_kind(package.coverage_rows)
    pdf_by_faction_id = {record.faction_id: record for record in package.pdf_records}
    detachment_rows_by_owner_id = {
        (row.faction_id, row.detachment_id): row
        for row in faction_detachment_source.detachment_rows()
    }

    enhancement_rows = {
        (row.faction_id, row.detachment_id, row.rule_id): row
        for row in rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT]
    }
    stratagem_rows = {
        (row.faction_id, row.detachment_id, row.rule_id): row
        for row in rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM]
    }

    assert set(enhancement_rows) == {
        (row.faction_id, row.detachment_id, row.enhancement_id)
        for row in faction_subrule_source.enhancement_rows()
    }
    assert set(stratagem_rows) == {
        (row.faction_id, row.detachment_id, row.stratagem_id)
        for row in faction_subrule_source.stratagem_rows()
    }

    for enhancement_source_row in faction_subrule_source.enhancement_rows():
        coverage_row = enhancement_rows[
            (
                enhancement_source_row.faction_id,
                enhancement_source_row.detachment_id,
                enhancement_source_row.enhancement_id,
            )
        ]
        detachment_row = detachment_rows_by_owner_id[
            (enhancement_source_row.faction_id, enhancement_source_row.detachment_id)
        ]
        _assert_exact_subrule_coverage_matches_source(
            coverage_row=coverage_row,
            source_ids=enhancement_source_row.all_source_ids,
            rule_id=enhancement_source_row.enhancement_id,
            rule_name=enhancement_source_row.name,
            timing_descriptor=enhancement_source_row.timing_descriptor,
            rule_category=enhancement_source_row.category,
            runtime_support_status=enhancement_source_row.runtime_support_status.value,
            runtime_consumer_ids=enhancement_source_row.runtime_consumer_ids,
            detachment_source_id=detachment_row.source_id,
            pdf_source_id=pdf_by_faction_id[enhancement_source_row.faction_id].source_id,
        )

    for stratagem_source_row in faction_subrule_source.stratagem_rows():
        coverage_row = stratagem_rows[
            (
                stratagem_source_row.faction_id,
                stratagem_source_row.detachment_id,
                stratagem_source_row.stratagem_id,
            )
        ]
        detachment_row = detachment_rows_by_owner_id[
            (stratagem_source_row.faction_id, stratagem_source_row.detachment_id)
        ]
        _assert_exact_subrule_coverage_matches_source(
            coverage_row=coverage_row,
            source_ids=stratagem_source_row.all_source_ids,
            rule_id=stratagem_source_row.stratagem_id,
            rule_name=stratagem_source_row.name,
            timing_descriptor=stratagem_source_row.timing_descriptor,
            rule_category=stratagem_source_row.category,
            runtime_support_status=stratagem_source_row.runtime_support_status.value,
            runtime_consumer_ids=stratagem_source_row.runtime_consumer_ids,
            detachment_source_id=detachment_row.source_id,
            pdf_source_id=pdf_by_faction_id[stratagem_source_row.faction_id].source_id,
        )


def test_phase17e_coverage_report_groups_supported_and_approved_unsupported_rows() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    faction_count = len(faction_detachment_source.faction_rows())
    detachment_count = len(faction_detachment_source.detachment_rows())
    enhancement_rows = faction_subrule_source.enhancement_rows()
    stratagem_rows = faction_subrule_source.stratagem_rows()
    implemented_exact_count = sum(1 for row in enhancement_rows if row.runtime_consumer_ids) + sum(
        1 for row in stratagem_rows if row.runtime_consumer_ids
    )
    source_only_exact_count = len(enhancement_rows) + len(stratagem_rows) - implemented_exact_count
    status_counts = package.status_counts()

    assert status_counts[Phase17ECoverageStatus.IMPLEMENTED.value] == implemented_exact_count
    assert status_counts[Phase17ECoverageStatus.GENERIC_SUPPORTED.value] == 0
    assert status_counts[Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED.value] == (
        faction_count + detachment_count + source_only_exact_count
    )
    assert status_counts[Phase17ECoverageStatus.UNSUPPORTED.value] == faction_count
    unsupported_count = status_counts[Phase17ECoverageStatus.UNSUPPORTED.value]
    assert len(package.unsupported_rows()) == unsupported_count
    assert package.unapproved_unsupported_rows() == ()
    assert all(row.is_approved_unsupported for row in package.unsupported_rows())


def test_phase17e_coverage_rows_reject_unapproved_or_incomplete_status_shapes() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    named_handler_row = next(
        row
        for row in package.coverage_rows
        if row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
    )
    unsupported_row = package.unsupported_rows()[0]

    with pytest.raises(Phase17EFactionCoverageError, match="require handler_id"):
        replace(named_handler_row, handler_id=None)

    with pytest.raises(Phase17EFactionCoverageError, match="Only unsupported"):
        replace(
            named_handler_row,
            unsupported_reason=(
                Phase17EUnsupportedReason.DATASHEET_INTAKE_REQUIRES_GENERATED_SOURCE_ROWS
            ),
        )

    with pytest.raises(Phase17EFactionCoverageError, match="require a reason"):
        replace(unsupported_row, unsupported_reason=None)


def test_phase17e_local_raw_faction_pdfs_match_manifest_when_present() -> None:
    present_pdf_filenames: set[str]
    present_pdf_filenames = (
        {path.name for path in RAW_FACTION_PDF_DIR.glob("*.pdf")}
        if RAW_FACTION_PDF_DIR.exists()
        else set()
    )
    if not present_pdf_filenames:
        pytest.skip("No local raw faction PDFs are present.")
    records_by_filename = {
        record.pdf_filename: record for record in faction_coverage_source.faction_pdf_records()
    }
    unknown_pdf_filenames = present_pdf_filenames.difference(records_by_filename)
    assert not unknown_pdf_filenames

    for pdf_filename in sorted(present_pdf_filenames):
        record = records_by_filename[pdf_filename]
        pdf_path = RAW_FACTION_PDF_DIR / record.pdf_filename
        assert pdf_path.is_file()
        pdf_data = pdf_path.read_bytes()
        assert len(pdf_data) == record.bytes
        assert hashlib.sha256(pdf_data).hexdigest() == record.sha256


def _bridge_source_row_ids(table: str) -> set[str]:
    raw_payload = json.loads((BRIDGE_JSON_DIR / f"{table}.json").read_text(encoding="utf-8"))
    if type(raw_payload) is not dict:
        raise AssertionError("bridge source payload must be a JSON object")
    payload = cast(dict[str, object], raw_payload)
    raw_rows = payload["rows"]
    if type(raw_rows) is not list:
        raise AssertionError("bridge source payload rows must be a list")
    source_row_ids: set[str] = set()
    for raw_row in cast(list[object], raw_rows):
        if type(raw_row) is not dict:
            raise AssertionError("bridge source payload row must be a JSON object")
        row = cast(dict[str, object], raw_row)
        source_row_id = row["source_row_id"]
        if type(source_row_id) is not str:
            raise AssertionError("bridge source_row_id must be a string")
        source_row_ids.add(source_row_id)
    return source_row_ids


def _bridge_source_id(table: str, source_row_id: str) -> str:
    return (
        f"gw-11e-phase17e-exact-faction-subrules-2026-27:bridge-source-row:{table}:{source_row_id}"
    )


def _rows_by_kind(
    rows: tuple[Phase17ECoverageRow, ...],
) -> dict[Phase17ECoverageKind, list[Phase17ECoverageRow]]:
    rows_by_kind: dict[Phase17ECoverageKind, list[Phase17ECoverageRow]] = {
        kind: [] for kind in Phase17ECoverageKind
    }
    for row in rows:
        rows_by_kind[row.coverage_kind].append(row)
    return rows_by_kind


def _detachment_row_map(
    rows: list[Phase17ECoverageRow],
) -> dict[tuple[str, str], Phase17ECoverageRow]:
    mapped_rows: dict[tuple[str, str], Phase17ECoverageRow] = {}
    for row in rows:
        assert row.detachment_id is not None
        mapped_rows[(row.faction_id, row.detachment_id)] = row
    return mapped_rows


def _assert_exact_subrule_coverage_matches_source(
    *,
    coverage_row: Phase17ECoverageRow,
    source_ids: tuple[str, ...],
    rule_id: str,
    rule_name: str,
    timing_descriptor: str,
    rule_category: str,
    runtime_support_status: str,
    runtime_consumer_ids: tuple[str, ...],
    detachment_source_id: str,
    pdf_source_id: str,
) -> None:
    assert coverage_row.rule_id == rule_id
    assert coverage_row.rule_name == rule_name
    assert coverage_row.timing_descriptor == timing_descriptor
    assert coverage_row.rule_category == rule_category
    assert coverage_row.runtime_support_status is not None
    assert coverage_row.runtime_support_status.value == runtime_support_status
    assert coverage_row.runtime_consumer_ids == runtime_consumer_ids
    assert all(source_id in coverage_row.source_ids for source_id in source_ids)
    assert detachment_source_id in coverage_row.source_ids
    assert pdf_source_id in coverage_row.source_ids
    if runtime_consumer_ids:
        assert coverage_row.status is Phase17ECoverageStatus.IMPLEMENTED
        assert coverage_row.handler_id == runtime_consumer_ids[0]
    else:
        assert coverage_row.status is Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED
