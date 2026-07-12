from __future__ import annotations

import json
from pathlib import Path
from typing import Any, cast

from tools.aeldari_support_review import (
    aeldari_datasheet_counts,
    aeldari_datasheet_review_groups,
    aeldari_datasheet_review_markdown,
)

SOURCE_DATASHEETS_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "source_snapshots"
    / "wahapedia"
    / ("1" + "0" + "th-edition")
    / "2026-06-14"
    / "json"
    / "Datasheets.json"
)


def test_aeldari_review_matches_current_non_legends_source_scope() -> None:
    payload = cast(dict[str, Any], json.loads(SOURCE_DATASHEETS_PATH.read_text(encoding="utf-8")))
    source_rows = cast(list[dict[str, Any]], payload["rows"])
    current_ids = {
        cast(str, row["fields"]["id"])
        for row in source_rows
        if row["fields"]["faction_id"] == "AE" and row["fields"]["source_id"] == "000000186"
    }
    legends_ids = {
        cast(str, row["fields"]["id"])
        for row in source_rows
        if row["fields"]["faction_id"] == "AE" and row["fields"]["source_id"] == "000000366"
    }
    imperial_armour_ids = {
        cast(str, row["fields"]["id"])
        for row in source_rows
        if row["fields"]["faction_id"] == "AE" and row["fields"]["source_id"] == "000000367"
    }
    review_ids = {
        row.datasheet_id for group in aeldari_datasheet_review_groups() for row in group.rows
    }

    assert review_ids == current_ids
    assert review_ids.isdisjoint(legends_ids)
    assert review_ids.isdisjoint(imperial_armour_ids)
    assert len(legends_ids) == 25
    assert len(imperial_armour_ids) == 2


def test_aeldari_review_records_pdf_overrides_updates_groups_and_exclusions() -> None:
    groups = aeldari_datasheet_review_groups()
    markdown = "\n".join(aeldari_datasheet_review_markdown())

    assert aeldari_datasheet_counts() == (70, 5, 24)
    assert tuple((group.name, len(group.rows)) for group in groups) == (
        ("Craftworlds / Asuryani", 45),
        ("Anhrathe / Corsairs", 6),
        ("Harlequins", 8),
        ("Ynnari", 11),
    )
    assert "Prince Yriel (`000004193`) | Faction Pack pages 12-13" in markdown
    assert "Kharseth (`000004194`) | Faction Pack pages 14-15" in markdown
    assert "Vypers (`000000605`) | Faction Pack pages 16-17" in markdown
    assert "Starfangs (`000004195`) | Faction Pack pages 18-19" in markdown
    assert "Corsair Skyreavers (`000004196`) | Faction Pack pages 20-21" in markdown
    assert "physical PDF page 23; contents page 27" in markdown
    assert "Warhammer Legends section begins at physical PDF page 25" in markdown
    assert "Imperial Armour is outside CORE V2 scope" in markdown
    assert "(`000000569`)" not in markdown
    assert "(`000000628`)" not in markdown
