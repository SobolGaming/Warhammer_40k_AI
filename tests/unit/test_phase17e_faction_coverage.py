from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from pathlib import Path, PurePosixPath
from urllib.parse import urlparse

import pytest
from tools.fetch_official_sources import load_official_source_manifest

from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_coverage_2026_27 as faction_coverage_source,
)
from warhammer40k_core.rules.source_packages.warhammer_40000_11th import (
    faction_detachments_2026_27 as faction_detachment_source,
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
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT_DESCRIPTORS]) == (
        len(detachment_rows)
    )
    assert len(rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM_DESCRIPTORS]) == (
        len(detachment_rows)
    )

    army_rule_rows = {
        row.faction_id: row for row in rows_by_kind[Phase17ECoverageKind.FACTION_ARMY_RULE]
    }
    datasheet_rows = {
        row.faction_id: row for row in rows_by_kind[Phase17ECoverageKind.DATASHEET_INTAKE]
    }
    detachment_rule_rows = _detachment_row_map(rows_by_kind[Phase17ECoverageKind.DETACHMENT_RULE])
    enhancement_rows = _detachment_row_map(
        rows_by_kind[Phase17ECoverageKind.DETACHMENT_ENHANCEMENT_DESCRIPTORS]
    )
    stratagem_rows = _detachment_row_map(
        rows_by_kind[Phase17ECoverageKind.DETACHMENT_STRATAGEM_DESCRIPTORS]
    )

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
        for coverage_row in (
            detachment_rule_rows[key],
            enhancement_rows[key],
            stratagem_rows[key],
        ):
            assert detachment_row.source_id in coverage_row.source_ids
            assert pdf_record.source_id in coverage_row.source_ids
            assert coverage_row.detachment_name == detachment_row.name
            assert coverage_row.force_disposition_id == detachment_row.force_disposition_id
            assert coverage_row.detachment_point_cost == detachment_row.detachment_point_cost
            assert coverage_row.is_new_for_eleventh is detachment_row.is_new_for_eleventh


def test_phase17e_coverage_report_groups_supported_and_approved_unsupported_rows() -> None:
    package = faction_coverage_source.phase17e_coverage_package()
    faction_count = len(faction_detachment_source.faction_rows())
    detachment_count = len(faction_detachment_source.detachment_rows())
    status_counts = package.status_counts()

    assert status_counts[Phase17ECoverageStatus.IMPLEMENTED.value] == 0
    assert status_counts[Phase17ECoverageStatus.GENERIC_SUPPORTED.value] == 0
    assert status_counts[Phase17ECoverageStatus.NAMED_HANDLER_REQUIRED.value] == (
        faction_count + detachment_count
    )
    assert status_counts[Phase17ECoverageStatus.UNSUPPORTED.value] == (
        faction_count + (detachment_count * 2)
    )
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
            unsupported_reason=Phase17EUnsupportedReason.EXACT_DETACHMENT_SUBROWS_REQUIRE_NATIVE_SOURCE,
        )

    with pytest.raises(Phase17EFactionCoverageError, match="require a reason"):
        replace(unsupported_row, unsupported_reason=None)


def test_phase17e_local_raw_faction_pdfs_match_manifest_when_present() -> None:
    if not RAW_FACTION_PDF_DIR.exists() or not tuple(RAW_FACTION_PDF_DIR.glob("*.pdf")):
        pytest.skip("Local raw faction PDFs are optional and are not redistributed in git.")

    for record in faction_coverage_source.faction_pdf_records():
        pdf_path = RAW_FACTION_PDF_DIR / record.pdf_filename
        assert pdf_path.is_file()
        pdf_data = pdf_path.read_bytes()
        assert len(pdf_data) == record.bytes
        assert hashlib.sha256(pdf_data).hexdigest() == record.sha256


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
