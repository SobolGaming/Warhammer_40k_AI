from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, cast

from tools.aeldari_datasheet_semantic_coverage import (
    COVERAGE_PATH,
    OVERLAY_PACK_PATH,
    RELEASE_MANIFEST_PATH,
    SEMANTIC_BUCKETS,
    aeldari_datasheet_semantic_coverage,
)
from tools.faction_pack_datasheet_review import (
    SOURCE_DATASHEETS_PATH,
    DatasheetSourceTreatment,
    faction_pack_datasheet_review,
    faction_pack_datasheet_review_markdown,
    faction_pack_datasheet_reviews,
    reviewed_faction_ids,
)
from tools.generate_ability_support_matrix import (
    ability_support_matrix_rows,
    datasheet_support_rows,
    faction_support_markdown_files,
)
from tools.generate_aeldari_datasheet_semantic_coverage import (
    generated_aeldari_datasheet_semantic_coverage,
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


def test_non_daemons_semantic_support_rows_remain_in_faction_documents() -> None:
    ability_rows = ability_support_matrix_rows()
    support_rows = datasheet_support_rows()
    markdown_by_filename = faction_support_markdown_files(
        datasheet_support_rows=support_rows,
        ability_rows=ability_rows,
    )
    ability_rows_by_id = {row.coverage_row_id: row for row in ability_rows}

    non_daemons_rows = tuple(row for row in support_rows if row.faction_id != "chaos-daemons")
    assert {(row.faction_id, row.datasheet_id, row.overall) for row in non_daemons_rows} == {
        ("death-guard", "000004209", "Partial"),
        ("emperors-children", "000004208", "Partial"),
        ("thousand-sons", "000001030", "Playable"),
        ("world-eaters", "000004207", "Partial"),
    }
    for row in non_daemons_rows:
        markdown = markdown_by_filename[f"{row.faction_id}.md"]
        assert markdown.index("## Datasheet Source Review") < markdown.index(
            "## Datasheet / Unit Support"
        )
        assert f"| {row.datasheet_name} (`{row.datasheet_id}`) | `{row.overall}` |" in markdown
        for coverage_row_id in row.ability_coverage_row_ids:
            coverage_row = ability_rows_by_id[coverage_row_id]
            assert (
                f"| {row.datasheet_name} (`{row.datasheet_id}`) | "
                f"{coverage_row.ability_name} (`{coverage_row.ability_id}`) |"
            ) in markdown

    world_eaters_markdown = markdown_by_filename["world-eaters.md"]
    assert "`catalog-ir:movement-transit-permission`" in world_eaters_markdown
    assert "`catalog-ir:setup-reactive-shoot-charge`" in world_eaters_markdown
    assert "Blessings of Khorne (`000008428`) | `faction` | `descriptor_only`" in (
        world_eaters_markdown
    )

    aeldari_markdown = markdown_by_filename["aeldari.md"]
    snapshot = aeldari_markdown.split("### Unit Datasheets", 1)[1].split(
        "## Detachment Rule Support", 1
    )[0]
    assert "### Unit Datasheet Source Treatments" not in snapshot
    semantic_coverage = aeldari_datasheet_semantic_coverage()
    for group_name in tuple(dict.fromkeys(row.group for row in semantic_coverage.rows)):
        table_row = next(
            line for line in snapshot.splitlines() if line.startswith(f"| {group_name} |")
        )
        cells = [cell.strip() for cell in table_row.strip("|").split(" | ")]
        for bucket_index, bucket in enumerate(SEMANTIC_BUCKETS, start=1):
            expected_labels = {
                f"{row.datasheet_name} (`{row.datasheet_id}`)"
                for row in semantic_coverage.rows
                if row.group == group_name and row.semantic_bucket == bucket
            }
            actual_labels: set[str] = (
                set() if cells[bucket_index] == "None" else set(cells[bucket_index].split("<br>"))
            )
            assert actual_labels == expected_labels


def test_aeldari_semantic_coverage_bridges_every_exact_ability() -> None:
    artifact = aeldari_datasheet_semantic_coverage()
    rows_by_id = {row.datasheet_id: row for row in artifact.rows}

    assert len(rows_by_id) == 70
    assert sum(len(row.abilities) for row in artifact.rows) == 145
    assert Counter(row.semantic_bucket for row in artifact.rows) == {
        "All consumed": 1,
        "IR parsed; host needed": 5,
        "Unsupported IR": 64,
    }
    assert rows_by_id["000000597"].semantic_bucket == "All consumed"
    assert rows_by_id["000000603"].semantic_bucket == "IR parsed; host needed"
    assert rows_by_id["000000571"].semantic_bucket == "Unsupported IR"
    assert all(row.semantic_bucket != "Bridge/catalog blocked" for row in artifact.rows)
    rangers_text = next(
        ability.raw_text
        for ability in rows_by_id["000000592"].abilities
        if ability.ability_name == "Path of the Outcast"
    )
    starweaver_text = next(
        ability.raw_text
        for ability in rows_by_id["000002541"].abilities
        if ability.ability_name == "Rapid Embarkation"
    )
    aspect_token_text = next(
        ability.raw_text
        for ability in rows_by_id["000000593"].abilities
        if ability.ability_name == "Aspect Shrine Token"
    )
    assert 'ends a move within 8"' in rangers_text
    assert "in a turn it disembarked from this TRANSPORT" in starweaver_text
    assert "Designer's Note" not in aspect_token_text


def test_aeldari_semantic_coverage_artifacts_are_current() -> None:
    overlay_pack, release_manifest, coverage_payload = (
        generated_aeldari_datasheet_semantic_coverage()
    )

    assert json.loads(COVERAGE_PATH.read_text(encoding="utf-8")) == coverage_payload
    assert json.loads(OVERLAY_PACK_PATH.read_text(encoding="utf-8")) == (overlay_pack.to_payload())
    assert json.loads(RELEASE_MANIFEST_PATH.read_text(encoding="utf-8")) == (
        release_manifest.to_payload()
    )
