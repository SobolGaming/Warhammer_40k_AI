from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from tools.faction_pack_datasheet_review import (
    SOURCE_DATASHEETS_PATH,
    DatasheetSourceTreatment,
    faction_pack_datasheet_review,
    faction_pack_datasheet_review_markdown,
    faction_pack_datasheet_reviews,
    reviewed_faction_ids,
)

from warhammer40k_core.rules.source_packages.warhammer_40000_11th.faction_coverage_2026_27 import (
    faction_pdf_records,
)

AELDARI_COMPLETE_IDS = frozenset({"000000605", "000004193", "000004194", "000004195", "000004196"})
AELDARI_UPDATE_IDS = frozenset(
    {
        "000000571",
        "000000575",
        "000000582",
        "000000584",
        "000000585",
        "000000587",
        "000000592",
        "000000593",
        "000000594",
        "000000595",
        "000000596",
        "000000599",
        "000000600",
        "000000601",
        "000000603",
        "000000606",
        "000000607",
        "000000609",
        "000002531",
        "000002535",
        "000002541",
        "000002542",
        "000003918",
        "000003921",
    }
)


def test_reviews_cover_every_non_daemons_faction_pack() -> None:
    expected_pdf_records = {
        record.faction_id: record
        for record in faction_pdf_records()
        if record.faction_id != "chaos-daemons"
    }

    assert reviewed_faction_ids() == expected_pdf_records.keys()
    assert len(faction_pack_datasheet_reviews()) == 27
    for review in faction_pack_datasheet_reviews():
        expected_pdf = expected_pdf_records[review.faction_id]
        assert review.faction_name == expected_pdf.faction_name
        assert review.pdf_filename == expected_pdf.pdf_filename
        assert review.pdf_sha256 == expected_pdf.sha256


def test_every_review_is_an_exhaustive_explicit_source_partition_with_matching_names() -> None:
    payload = cast(dict[str, Any], json.loads(SOURCE_DATASHEETS_PATH.read_text(encoding="utf-8")))
    source_rows = cast(list[dict[str, Any]], payload["rows"])
    source_by_id = {cast(str, row["fields"]["id"]): row for row in source_rows}

    for review in faction_pack_datasheet_reviews():
        expected_ids = {
            cast(str, row["fields"]["id"])
            for row in source_rows
            if row["fields"]["faction_id"] == review.source_faction_id
            and row["fields"]["source_id"] == review.source_id
            and row["fields"]["virtual"] == "false"
        } | set(review.additional_source_datasheet_ids)
        rows_by_treatment = {
            treatment: review.rows_for(treatment) for treatment in DatasheetSourceTreatment
        }
        treatment_ids = {
            treatment: {row.datasheet_id for row in rows if row.datasheet_id is not None}
            for treatment, rows in rows_by_treatment.items()
        }

        assert set().union(*treatment_ids.values()) == expected_ids
        assert treatment_ids[DatasheetSourceTreatment.COMPLETE_PDF].isdisjoint(
            treatment_ids[DatasheetSourceTreatment.RULES_UPDATE]
        )
        assert treatment_ids[DatasheetSourceTreatment.COMPLETE_PDF].isdisjoint(
            treatment_ids[DatasheetSourceTreatment.UNCHANGED_PREDECESSOR]
        )
        assert treatment_ids[DatasheetSourceTreatment.RULES_UPDATE].isdisjoint(
            treatment_ids[DatasheetSourceTreatment.UNCHANGED_PREDECESSOR]
        )
        assert sum(review.treatment_counts().values()) == len(review.rows)
        for row in review.rows:
            if row.datasheet_id is not None:
                assert row.datasheet_name == source_by_id[row.datasheet_id]["fields"]["name"]
            if row.treatment is not DatasheetSourceTreatment.UNCHANGED_PREDECESSOR:
                assert row.pdf_page_reference


def test_aeldari_treatments_are_the_exact_reviewed_sets() -> None:
    review = faction_pack_datasheet_review("aeldari")
    complete_ids = {
        cast(str, row.datasheet_id)
        for row in review.rows_for(DatasheetSourceTreatment.COMPLETE_PDF)
    }
    updated_ids = {
        cast(str, row.datasheet_id)
        for row in review.rows_for(DatasheetSourceTreatment.RULES_UPDATE)
    }
    unchanged_ids = {
        cast(str, row.datasheet_id)
        for row in review.rows_for(DatasheetSourceTreatment.UNCHANGED_PREDECESSOR)
    }
    all_ids = {cast(str, row.datasheet_id) for row in review.rows}

    assert complete_ids == AELDARI_COMPLETE_IDS
    assert updated_ids == AELDARI_UPDATE_IDS
    assert unchanged_ids == all_ids - AELDARI_COMPLETE_IDS - AELDARI_UPDATE_IDS
    assert review.treatment_counts() == {
        DatasheetSourceTreatment.COMPLETE_PDF: 5,
        DatasheetSourceTreatment.RULES_UPDATE: 24,
        DatasheetSourceTreatment.UNCHANGED_PREDECESSOR: 41,
    }


def test_aeldari_markdown_preserves_groups_provenance_and_exclusions() -> None:
    markdown = "\n".join(faction_pack_datasheet_review_markdown("aeldari"))

    assert "### Craftworlds / Asuryani" in markdown
    assert "### Anhrathe / Corsairs" in markdown
    assert "### Harlequins" in markdown
    assert "### Ynnari" in markdown
    assert "Prince Yriel (`000004193`) | `complete_pdf`" in markdown
    assert "Asurmen (`000000571`) | `rules_update`" in markdown
    assert "Eldrad Ulthran (`000000568`) | `unchanged_predecessor`" in markdown
    assert "48cf09f605dc29b42555d5800c239879c1fc590f85a6a45b0a1f14739b03f0a9" in markdown
    assert (
        "Warhammer Legends, Legends, Forge World, and Imperial Armour rows are excluded" in markdown
    )
    assert "(`000000569`)" not in markdown
    assert "(`000000628`)" not in markdown


def test_manifest_is_a_versioned_data_artifact() -> None:
    manifest_path = (
        Path(__file__).resolve().parents[2]
        / "data"
        / "source_manifests"
        / "faction_pack_datasheet_review_v1.json"
    )
    payload = cast(dict[str, Any], json.loads(manifest_path.read_text(encoding="utf-8")))

    assert payload["schema_version"] == "1"
    assert payload["source_snapshot"]["datasheets_artifact_hash"]
    assert payload["source_snapshot"]["datasheets_sha256"]
