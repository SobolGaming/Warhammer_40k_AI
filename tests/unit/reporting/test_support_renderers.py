# pyright: reportPrivateUsage=false
from __future__ import annotations

from tools.faction_pack_datasheet_review import faction_pack_datasheet_review
from tools.generate_ability_support_matrix import (
    _ability_datasheet_pairs_text,
    _inline_code_list,
    _markdown_text,
    ability_support_matrix_rows,
    faction_support_markdown_files,
    runtime_content_semantic_coverage_payload,
    support_matrix_markdown,
)

from warhammer40k_core.engine.ability_coverage import (
    ability_coverage_category_rows,
    ability_coverage_category_rows_payload,
    ability_coverage_rows_payload,
)


def test_global_support_renderer_preserves_section_order_and_runtime_inventory() -> None:
    ability_rows = ability_support_matrix_rows()
    category_rows = ability_coverage_category_rows(ability_rows)
    markdown = support_matrix_markdown(
        ability_coverage_category_rows_payload(category_rows),
        ability_rows=ability_coverage_rows_payload(ability_rows),
        runtime_semantic_coverage=runtime_content_semantic_coverage_payload(),
    )

    headings = (
        "## Runtime Content Semantic Coverage",
        "## Mustering / List Construction Support",
        "## Factions",
        "## Runtime Hook Inventory",
    )
    assert all(heading in markdown for heading in headings)
    assert tuple(markdown.index(heading) for heading in headings) == tuple(
        sorted(markdown.index(heading) for heading in headings)
    )

    represented_consumer_ids = {
        consumer_id for row in ability_rows for consumer_id in row.runtime_consumer_ids
    }
    assert represented_consumer_ids
    assert all(f"`{consumer_id}`" in markdown for consumer_id in represented_consumer_ids)


def test_faction_support_renderer_preserves_section_order() -> None:
    aeldari = faction_support_markdown_files()["aeldari.md"]
    emperors_children = faction_support_markdown_files()["emperors-children.md"]

    assert aeldari.startswith("# Aeldari Support Matrix\n")
    assert aeldari.index("## Detachment Rule Support") < aeldari.index(
        "## Datasheet / Unit Support"
    )
    assert "## 11th Edition Faction Pack Review" in emperors_children
    assert "Elegant Brutes | Yes | Physical PDF page 2" in emperors_children
    assert "Frenzied Host | Yes | Physical PDF page 3" in emperors_children
    assert "Spectacle of Slaughter | Yes | Physical PDF page 4" in emperors_children
    assert "Court of the Phoenician | No - reprinted/updated" in emperors_children
    assert "Cacophonic Accompaniment<br>Frenzied Ferocity Upgrade" in emperors_children
    assert "Possessive Mania<br>Agonised Cacophony<br>Absolute Sensory Overload" in (
        emperors_children
    )
    assert "are not yet present in the structured Phase17E artifacts" in emperors_children
    assert "## Semantic Support Snapshot" in emperors_children
    assert (
        emperors_children.index("## 11th Edition Faction Pack Review")
        < emperors_children.index("## Semantic Support Snapshot")
        < emperors_children.index("## Detachment Rule Support")
        < emperors_children.index("## Datasheet Source Review")
        < emperors_children.index("## Datasheet / Unit Support")
    )
    assert "Court of the Phoenician | `Full`" in emperors_children
    assert "### Unit Datasheet Source Treatments" not in emperors_children
    assert "### Datasheet Ability Details" not in emperors_children
    support_markdown = emperors_children.split("## Datasheet / Unit Support", 1)[1]
    assert "### Emperor's Children" in support_markdown
    assert "### Vehicles and Daemon Engines" in support_markdown
    assert "### Slaanesh Daemons" in support_markdown
    expected_header = (
        "| Datasheet | Source basis | IR coverage | Supported semantics | "
        "IR semantics still needed | Bridge / catalog blockers |"
    )
    assert support_markdown.count(expected_header) == 3
    review = faction_pack_datasheet_review("emperors-children")
    assert len(review.rows) == 23
    for row in review.rows:
        assert row.datasheet_id is not None
        assert support_markdown.count(f"| {row.datasheet_name} (`{row.datasheet_id}`) |") == 1
    assert "## Detachment Rule Coverage Rows" not in emperors_children


def test_support_renderer_escapes_tables_and_renders_empty_cells() -> None:
    assert _markdown_text("Alpha | Beta") == "Alpha \\| Beta"
    assert _inline_code_list(()) == "None"
    assert _ability_datasheet_pairs_text([]) == "None"
